"""
CityPulse Prediction Algorithm — Walk-Forward Backtest Engine

Methodology:
  For each district, at each time window T (sampled every 6 hours going back
  up to `lookback_days`):
    1. Compute features using ONLY iris_events data before T  (no lookahead)
    2. Compute risk_score with the same formula as predictor_service.py
    3. Look up what sentiment was at T + horizon_hours
    4. Label "significant_event" = True if sentiment dropped > threshold

  Features that need live APIs (weather, ticketmaster) are approximated
  from historical context or zero-filled with a coverage flag.

Metrics returned:
  - IC (Information Coefficient): Pearson correlation(risk_score, actual_drop)
    IC > 0.05 = real signal, IC > 0.15 = world-class
  - Precision at ELEVATED (score ≥ 0.5): of those calls, how many events occurred?
  - Recall at ELEVATED: of actual events, what fraction were caught at score ≥ 0.5?
  - Calibration buckets: avg actual event rate inside each score decile
  - AUC-ROC approximation from precision/recall across thresholds
  - Per-feature importance: how much each feature correlated with outcomes
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Backtest constants ────────────────────────────────────────────────────────
from backend.services.predictor_service import (
    WEIGHTS,
    FRESHNESS_LAMBDA,
    risk_tier,
    RISK_TIER_THRESHOLDS,
    ALGORITHM_VERSION,
)
import hashlib

SIGNIFICANT_EVENT_THRESHOLD = -15.0  # sentiment drop > 15 pts (0-100 scale) = event


# ── Historical feature computation (DB-only, no live APIs) ───────────────────

def _avg_sentiment_100(events: list[dict]) -> float:
    if not events:
        return 50.0
    vals = [float(e.get("sentiment", 0)) for e in events]
    return (sum(vals) / len(vals) + 1.0) * 50.0


def _compute_features_historical(
    district_id: str,
    events_before_t: list[dict],
    neighbor_events: dict[str, list[dict]],
    as_of: datetime,
    rolling_hourly_avg: float,
) -> dict[str, float]:
    """
    Compute all features using ONLY historical data before `as_of`.
    Weather and event_density are approximated or zero-filled.
    """
    features: dict[str, float] = {}

    # ── Feature 1: Sentiment Velocity ──────────────────────────────────────
    recent = [e for e in events_before_t if _hours_before(e, as_of) <= 3]
    past   = [e for e in events_before_t if _hours_before(e, as_of) <= 9]

    current_sent = _avg_sentiment_100(recent)
    past_sent    = _avg_sentiment_100(past)
    velocity     = (current_sent - past_sent) / 6.0
    vel_raw      = max(-10.0, min(10.0, velocity))
    features["sentiment_velocity"] = round(max(0.0, min(1.0, ((-vel_raw) + 10.0) / 20.0)), 4)

    # ── Feature 2: Source Consensus ────────────────────────────────────────
    signals_6h = [e for e in events_before_t if _hours_before(e, as_of) <= 6]
    if signals_6h:
        neg = sum(1 for e in signals_6h if float(e.get("sentiment", 0)) < -0.15)
        features["source_consensus"] = round(min(1.0, neg / len(signals_6h)), 4)
    else:
        features["source_consensus"] = 0.25

    # ── Feature 3: Volume Spike ────────────────────────────────────────────
    last_hour = [e for e in events_before_t if _hours_before(e, as_of) <= 1]
    spike = len(last_hour) / max(1.0, float(rolling_hourly_avg))
    features["volume_spike"] = round(min(spike, 3.0) / 3.0, 4)

    # ── Feature 4: Weather Stress (historical approximation) ──────────────
    # No stored weather history. Approximate from source text mood signals:
    # if high fraction of negative + high volume → proxy for stress conditions
    if signals_6h:
        neg_ratio = features["source_consensus"]
        volume_ratio = features["volume_spike"]
        weather_proxy = min(0.6, neg_ratio * 0.4 + volume_ratio * 0.2)
    else:
        weather_proxy = 0.0
    features["weather_stress"] = round(weather_proxy, 4)

    # ── Feature 5: Event Density ───────────────────────────────────────────
    # No historical event store — use neutral placeholder (0.2 = baseline urban activity)
    features["event_density"] = 0.2

    # ── Feature 6: Geo Spillover ───────────────────────────────────────────
    neighbor_sents = []
    for n_events in neighbor_events.values():
        n_6h = [e for e in n_events if _hours_before(e, as_of) <= 6]
        if n_6h:
            neighbor_sents.append(_avg_sentiment_100(n_6h))
    if neighbor_sents:
        avg_n = sum(neighbor_sents) / len(neighbor_sents)
        spillover = max(0.0, min(1.0, (50.0 - avg_n) / 50.0 + 0.5))
    else:
        spillover = 0.2
    features["geo_spillover"] = round(spillover, 4)

    # ── Feature 7: Time of Day ─────────────────────────────────────────────
    hour = as_of.hour
    if 18 <= hour <= 23 or 0 <= hour < 2:
        tod_raw = 1.3
    elif 2 <= hour < 6:
        tod_raw = 0.8
    else:
        tod_raw = 1.0
    features["time_of_day"] = round((tod_raw - 0.8) / 0.5, 4)

    # ── Freshness Decay ────────────────────────────────────────────────────
    if events_before_t:
        ts_strs = [e.get("occurred_at", "") for e in events_before_t if e.get("occurred_at")]
        if ts_strs:
            latest_str = max(ts_strs)
            latest_dt  = datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
            hours_old  = max(0.0, (as_of - latest_dt).total_seconds() / 3600.0)
        else:
            hours_old = 12.0
    else:
        hours_old = 24.0
    decay = math.exp(-FRESHNESS_LAMBDA * hours_old)

    # ── Weighted Score ─────────────────────────────────────────────────────
    raw = sum(WEIGHTS[k] * features[k] for k in WEIGHTS)
    risk_score = round(max(0.0, min(1.0, raw * decay)), 4)

    return {
        "features": features,
        "decay": round(decay, 4),
        "risk_score": risk_score,
    }


def _hours_before(event: dict, as_of: datetime) -> float:
    ts = event.get("occurred_at", "")
    if not ts:
        return 999.0
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (as_of - dt).total_seconds() / 3600.0)
    except Exception:
        return 999.0


# ── Main backtest runner ──────────────────────────────────────────────────────

async def run_backtest(
    district_id: str,
    lookback_days: int = 14,
    horizon_hours: int = 6,
    step_hours: int = 6,
) -> dict:
    """
    Run a walk-forward backtest for one district.

    Returns:
      predictions: list of {as_of, risk_score, actual_sentiment_delta, significant_event, features}
      metrics:     {ic, precision_elevated, recall_elevated, n, calibration, auc_approx, feature_ic}
      summary:     human-readable verdict
    """
    from backend.services.postgres_service import fetch_recent_iris_events, fetch_rolling_signal_avg
    from backend.services.predictor_service import DISTRICT_NEIGHBORS

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=lookback_days)

    # Fetch ALL events for this district + neighbors for the full window
    # (fetching bulk once is far more efficient than per-window queries)
    all_events = await fetch_recent_iris_events(district_id, "general", lookback_hours=lookback_days * 24)
    if not all_events:
        return _empty_result(district_id, "No iris_events data found for this district. Ingest some signals first.")

    neighbors = DISTRICT_NEIGHBORS.get(district_id, [])
    neighbor_data: dict[str, list[dict]] = {}
    for n_id in neighbors[:4]:
        n_evts = await fetch_recent_iris_events(n_id, "general", lookback_hours=lookback_days * 24)
        if n_evts:
            neighbor_data[n_id] = n_evts

    rolling_avg = await fetch_rolling_signal_avg(district_id, days=lookback_days)

    # Normalize all event timestamps to UTC-aware datetimes
    def _to_dt(e: dict) -> datetime:
        ts = e.get("occurred_at", "")
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return now

    for e in all_events:
        e["_dt"] = _to_dt(e)
    for evts in neighbor_data.values():
        for e in evts:
            e["_dt"] = _to_dt(e)

    # ── Walk-forward windows ──────────────────────────────────────────────────
    predictions: list[dict] = []
    t = start + timedelta(hours=step_hours)   # need lookback before first window

    while t + timedelta(hours=horizon_hours) <= now:
        # Events strictly before t (no lookahead)
        before_t = [e for e in all_events if e["_dt"] < t]
        if len(before_t) < 3:
            t += timedelta(hours=step_hours)
            continue

        # Neighbor events before t
        n_before = {nid: [e for e in evts if e["_dt"] < t]
                    for nid, evts in neighbor_data.items()}

        # Compute features + score at time t
        result = _compute_features_historical(district_id, before_t, n_before, t, rolling_avg)

        # Outcome: actual sentiment at t + horizon
        t_plus = t + timedelta(hours=horizon_hours)
        outcome_window = [
            e for e in all_events
            if t <= e["_dt"] < t_plus + timedelta(hours=1)
        ]

        if not outcome_window:
            t += timedelta(hours=step_hours)
            continue

        sent_at_t   = _avg_sentiment_100(before_t[-min(20, len(before_t)):])
        sent_future = _avg_sentiment_100(outcome_window)
        delta       = sent_future - sent_at_t
        significant = bool(delta < SIGNIFICANT_EVENT_THRESHOLD)

        predictions.append({
            "as_of":                 t.isoformat(),
            "risk_score":            result["risk_score"],
            "features":              result["features"],
            "freshness_decay":       result["decay"],
            "feature_quality": {
                "sentiment_velocity": "real",
                "source_consensus": "real",
                "volume_spike": "real",
                "weather_stress": "approximated",
                "event_density": "approximated",
                "geo_spillover": "real",
                "time_of_day": "real",
            },
            "sentiment_at_t":        round(sent_at_t, 2),
            "sentiment_future":      round(sent_future, 2),
            "sentiment_delta":       round(delta, 3),
            "significant_event":     significant,
            "alert_tier":            risk_tier(result["risk_score"]),
        })

        t += timedelta(hours=step_hours)

    if len(predictions) < 5:
        return _empty_result(
            district_id,
            f"Only {len(predictions)} usable windows found (need ≥5). "
            f"Ingest more signals or increase lookback_days.",
        )

    metrics = _compute_metrics(predictions)

    weekly_oos = _weekly_oos_report(predictions)
    return {
        "district_id":    district_id,
        "lookback_days":  lookback_days,
        "horizon_hours":  horizon_hours,
        "step_hours":     step_hours,
        "n_windows":      len(predictions),
        "n_events":       sum(1 for p in predictions if p["significant_event"]),
        "event_base_rate": round(sum(1 for p in predictions if p["significant_event"]) / len(predictions), 3),
        "predictions":    predictions,
        "metrics":        metrics,
        "metrics_confidence": _metrics_confidence(len(predictions)),
        "weekly_oos": weekly_oos,
        "model_run": {
            "algorithm_version": ALGORITHM_VERSION,
            "weight_profile": {"weights": WEIGHTS, "freshness_lambda": FRESHNESS_LAMBDA, "thresholds": RISK_TIER_THRESHOLDS},
            "feature_schema_hash": hashlib.sha256("|".join(sorted(WEIGHTS.keys())).encode()).hexdigest()[:16],
        },
        "summary":        _verdict(metrics),
        "caveats": [
            "weather_stress feature approximated from signal mood (no stored weather history)",
            "event_density fixed at 0.2 baseline (no historical ticketmaster store)",
            "IC is directional only — calibration requires Platt scaling after 200+ samples",
        ],
    }


# ── Metrics computation ───────────────────────────────────────────────────────

def _compute_metrics(predictions: list[dict]) -> dict:
    n = len(predictions)
    scores  = [p["risk_score"]    for p in predictions]
    deltas  = [p["sentiment_delta"] for p in predictions]
    events  = [p["significant_event"] for p in predictions]

    # ── IC (Pearson correlation: risk_score vs -sentiment_delta) ─────────────
    # We invert delta: a DROP in sentiment = positive risk outcome
    outcomes = [-d for d in deltas]   # positive = sentiment fell = risk realised
    ic = _pearson(scores, outcomes)

    # ── Precision / Recall at ELEVATED threshold (score ≥ configured threshold) ───────────────
    elevated_th = RISK_TIER_THRESHOLDS["elevated"]
    elevated    = [p for p in predictions if p["risk_score"] >= elevated_th]
    tp_elevated = sum(1 for p in elevated if p["significant_event"])
    precision_elevated = tp_elevated / max(1, len(elevated))
    recall_elevated    = tp_elevated / max(1, sum(1 for e in events if e))

    # Tier-level precision/recall
    tier_metrics = {}
    for tier_name, th in (("WATCH", RISK_TIER_THRESHOLDS["watch"]), ("ELEVATED", RISK_TIER_THRESHOLDS["elevated"]), ("CRITICAL", RISK_TIER_THRESHOLDS["critical"])):
        bucket = [p for p in predictions if p["risk_score"] >= th]
        tp = sum(1 for p in bucket if p["significant_event"])
        tier_metrics[tier_name] = {
            "threshold": th,
            "n_calls": len(bucket),
            "precision": round(tp / max(1, len(bucket)), 3),
            "recall": round(tp / max(1, sum(1 for e in events if e)), 3),
        }

    # ── Calibration: actual event rate per risk decile ────────────────────────
    calibration: list[dict] = []
    for lo in range(0, 10):
        lo_val  = lo / 10
        hi_val  = (lo + 1) / 10
        bucket  = [p for p in predictions if lo_val <= p["risk_score"] < hi_val]
        if bucket:
            actual_rate = sum(1 for p in bucket if p["significant_event"]) / len(bucket)
            calibration.append({
                "bucket":      f"{int(lo_val*100)}-{int(hi_val*100)}%",
                "n":           len(bucket),
                "predicted":   round((lo_val + hi_val) / 2, 2),
                "actual_rate": round(actual_rate, 3),
            })
    # ECE (Expected Calibration Error)
    ece = 0.0
    for b in calibration:
        ece += (b["n"] / n) * abs(float(b["predicted"]) - float(b["actual_rate"]))

    # ── AUC-ROC approximation via trapezoidal rule ────────────────────────────
    thresholds = [i / 20 for i in range(21)]
    roc_points: list[tuple[float, float]] = []
    total_pos = max(1, sum(1 for e in events if e))
    total_neg = max(1, sum(1 for e in events if not e))
    for th in thresholds:
        tp = sum(1 for p in predictions if p["risk_score"] >= th and p["significant_event"])
        fp = sum(1 for p in predictions if p["risk_score"] >= th and not p["significant_event"])
        tpr = tp / total_pos
        fpr = fp / total_neg
        roc_points.append((fpr, tpr))
    roc_sorted = sorted(roc_points, key=lambda x: x[0])
    auc = sum(
        (roc_sorted[i][0] - roc_sorted[i-1][0]) * (roc_sorted[i][1] + roc_sorted[i-1][1]) / 2
        for i in range(1, len(roc_sorted))
    )

    # ── Per-feature IC ────────────────────────────────────────────────────────
    feature_names = list(WEIGHTS.keys())
    feature_ic: dict[str, float] = {}
    for fname in feature_names:
        feat_vals = [p["features"].get(fname, 0) for p in predictions]
        fic = _pearson(feat_vals, outcomes)
        feature_ic[fname] = round(fic, 4) if fic is not None else 0.0

    # Brier score for event probability forecasts.
    brier = sum((scores[i] - (1.0 if events[i] else 0.0)) ** 2 for i in range(n)) / max(1, n)

    return {
        "ic":                  round(ic, 4) if ic is not None else None,
        "precision_elevated":  round(precision_elevated, 3),
        "recall_elevated":     round(recall_elevated, 3),
        "auc_roc":             round(max(0.0, auc), 3),
        "brier_score":         round(brier, 4),
        "ece":                 round(ece, 4),
        "n_elevated_calls":    len(elevated),
        "calibration":         calibration,
        "feature_ic":          feature_ic,
        "tier_metrics":        tier_metrics,
        "signal_quality": (
            "world_class" if ic and ic > 0.15 else
            "tradeable"   if ic and ic > 0.05 else
            "weak"        if ic and ic > 0   else
            "no_signal"
        ),
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    cov  = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    sx   = math.sqrt(sum((x - mx)**2 for x in xs)) or 1e-9
    sy   = math.sqrt(sum((y - my)**2 for y in ys)) or 1e-9
    return cov / (sx * sy * n)


def _verdict(metrics: dict) -> str:
    ic = metrics.get("ic")
    auc = metrics.get("auc_roc", 0.5)
    prec = metrics.get("precision_elevated", 0)
    quality = metrics.get("signal_quality", "no_signal")

    if ic is None:
        return "Insufficient data for IC computation."

    lines = [
        f"IC = {ic:.4f} → {quality.replace('_', ' ').upper()} signal.",
        f"AUC-ROC = {auc:.3f} (0.5 = random, 1.0 = perfect).",
        f"Precision at ELEVATED threshold = {prec:.1%}.",
    ]
    if quality == "world_class":
        lines.append("Algorithm is performing at institutional-grade level.")
    elif quality == "tradeable":
        lines.append("Algorithm has a real predictive edge. Consider Platt calibration.")
    elif quality == "weak":
        lines.append("Weak signal detected. Collect more data or tune feature weights.")
    else:
        lines.append("No signal found. Check data quality and ingestion pipeline.")

    if auc > 0.65:
        lines.append("AUC > 0.65: algorithm discriminates events from non-events well.")
    if prec > 0.6:
        lines.append("High precision: when ELEVATED fires, it's usually correct.")

    return " ".join(lines)


def _empty_result(district_id: str, reason: str) -> dict:
    return {
        "district_id":   district_id,
        "n_windows":     0,
        "n_events":      0,
        "predictions":   [],
        "metrics":       None,
        "summary":       reason,
        "caveats":       [],
    }


def _metrics_confidence(n_windows: int) -> str:
    if n_windows >= 120:
        return "high"
    if n_windows >= 60:
        return "medium"
    return "low"


def _weekly_oos_report(predictions: list[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for p in predictions:
        try:
            dt = datetime.fromisoformat(str(p["as_of"]).replace("Z", "+00:00"))
            key = f"{dt.isocalendar().year}-W{dt.isocalendar().week:02d}"
        except Exception:
            key = "unknown"
        buckets.setdefault(key, []).append(p)

    report: list[dict] = []
    for week_key, rows in sorted(buckets.items()):
        m = _compute_metrics(rows) if len(rows) >= 5 else None
        report.append(
            {
                "week": week_key,
                "n_windows": len(rows),
                "event_rate": round(sum(1 for r in rows if r["significant_event"]) / max(1, len(rows)), 3),
                "ic": None if not m else m.get("ic"),
                "auc_roc": None if not m else m.get("auc_roc"),
                "precision_elevated": None if not m else m.get("precision_elevated"),
            }
        )
    return report
