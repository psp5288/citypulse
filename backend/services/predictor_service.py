"""
CityPulse Prediction Algorithm — v1.0 (Deterministic + Kalman-smoothed)

Architecture:
  8 engineered features  →  freshness-decayed weighted sum  →  calibrated risk_score (0-1)
  Kalman filter on raw sentiment (one instance per district, in-memory)
  Redis cache: 5-min TTL per district
  PostgreSQL logging: every prediction + eventual outcome (for IC tracking / v2 training)

Features:
  1. sentiment_velocity   (0.30)  – how fast sentiment is falling
  2. source_consensus     (0.20)  – fraction of sources agreeing negative
  3. volume_spike         (0.15)  – current signal volume vs 7-day rolling avg
  4. weather_stress       (0.10)  – extreme conditions boolean/partial
  5. event_density        (0.10)  – upcoming event count in district
  6. geo_spillover        (0.08)  – negative pressure from neighbouring districts
  7. time_of_day          (0.07)  – risk multiplier by hour of day
  * freshness_decay        (mult)  – e^(-λt) discount on stale data
"""

from __future__ import annotations

import logging
import math
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel
from backend.config import settings

logger = logging.getLogger(__name__)

# ── Algorithm constants ───────────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {
    "sentiment_velocity": 0.30,
    "source_consensus":   0.20,
    "volume_spike":       0.15,
    "weather_stress":     0.10,
    "event_density":      0.10,
    "geo_spillover":      0.08,
    "time_of_day":        0.07,
}

FRESHNESS_LAMBDA = 0.3      # half-life: ~2.3 hours  (score halves every 2.3h of no data)
ALGORITHM_VERSION = "v1.0-deterministic"
CACHE_TTL_SECONDS = settings.risk_cache_ttl_seconds

RISK_TIER_THRESHOLDS = {
    "watch": settings.risk_tier_watch,
    "elevated": settings.risk_tier_elevated,
    "critical": settings.risk_tier_critical,
}
MIN_EVENTS_FOR_HIGH_TIER = settings.risk_min_events_for_high_tier
MIN_INPUT_COVERAGE_FOR_HIGH_TIER = settings.risk_min_input_coverage_for_high_tier
MAX_SCORE_STEP_DELTA = settings.risk_max_step_delta
LOG_MIN_INTERVAL_SECONDS = settings.risk_log_min_interval_seconds
LOG_MIN_DELTA = settings.risk_log_min_delta
_PROFILE_CACHE: dict = {"at": None, "profile": None}
_PROFILE_CACHE_TTL_SECONDS = 120


# ── Kalman Filter (per-district sentiment denoiser) ──────────────────────────

class KalmanFilter:
    """
    1-D Kalman filter for urban sentiment signal smoothing.
    Filters out viral-but-irrelevant spikes in Reddit / GDELT data.

    process_noise (Q):     how fast we expect the true signal to change
    measurement_noise (R): how much we distrust a single raw measurement
    High R/Q ratio → more smoothing, slower tracking.
    """

    def __init__(self, process_noise: float = 0.02, measurement_noise: float = 0.20):
        self.Q = process_noise
        self.R = measurement_noise
        self.x: float = 50.0   # initial estimate: neutral sentiment (0-100 scale)
        self.P: float = 10.0   # initial uncertainty — start uncertain

    def update(self, measurement: float) -> float:
        # ── Predict ──────────────────────────────────────────────────────────
        P_pred = self.P + self.Q
        # ── Kalman Gain ───────────────────────────────────────────────────────
        # K close to 1 → trust measurement; K close to 0 → trust model
        K = P_pred / (P_pred + self.R)
        # ── Update ────────────────────────────────────────────────────────────
        self.x = self.x + K * (measurement - self.x)
        self.P = (1.0 - K) * P_pred
        return round(self.x, 4)


# One Kalman filter instance per district (lives in process memory, reset on restart)
_kalman_filters: dict[str, KalmanFilter] = {}


def _get_kalman(district_id: str) -> KalmanFilter:
    if district_id not in _kalman_filters:
        _kalman_filters[district_id] = KalmanFilter()
    return _kalman_filters[district_id]


# ── District adjacency (geographic spillover graph) ───────────────────────────

DISTRICT_NEIGHBORS: dict[str, list[str]] = {
    "nyc-manhattan":    ["nyc-brooklyn", "nyc-queens", "nyc-bronx", "nyc-harlem", "nyc-lowereast"],
    "nyc-brooklyn":     ["nyc-manhattan", "nyc-queens", "nyc-lowereast"],
    "nyc-queens":       ["nyc-manhattan", "nyc-brooklyn", "nyc-bronx", "nyc-flushing"],
    "nyc-bronx":        ["nyc-manhattan", "nyc-queens", "nyc-harlem"],
    "nyc-statenisland": ["nyc-manhattan"],
    "nyc-harlem":       ["nyc-manhattan", "nyc-bronx"],
    "nyc-lowereast":    ["nyc-manhattan", "nyc-brooklyn"],
    "nyc-flushing":     ["nyc-queens"],
    # Chicago simulation zones
    "downtown":         ["midtown", "financial", "harbor"],
    "midtown":          ["downtown", "financial", "university"],
    "harbor":           ["downtown", "westside", "market"],
    "arts":             ["westside", "university", "market"],
    "financial":        ["downtown", "midtown"],
    "westside":         ["harbor", "arts"],
    "university":       ["midtown", "arts"],
    "market":           ["harbor", "arts"],
}


# ── Output model ──────────────────────────────────────────────────────────────

class CityPulseRiskScore(BaseModel):
    district_id: str
    risk_score: float           # 0.0–1.0 calibrated probability
    alert_tier: str             # NOMINAL / WATCH / ELEVATED / CRITICAL
    top_drivers: list[str]      # top 3 feature names by weighted contribution
    feature_values: dict        # all 7 normalized feature values (debug)
    freshness_decay: float      # the decay multiplier applied (0-1)
    input_coverage: float       # fraction of features with live data
    algorithm_version: str
    feature_schema_hash: str
    weight_profile: dict
    warnings: list[str]
    computed_at: datetime
    valid_until: datetime       # prediction window end (+6h)


def risk_tier(score: float) -> str:
    if score >= RISK_TIER_THRESHOLDS["critical"]:
        return "CRITICAL"
    if score >= RISK_TIER_THRESHOLDS["elevated"]:
        return "ELEVATED"
    if score >= RISK_TIER_THRESHOLDS["watch"]:
        return "WATCH"
    return "NOMINAL"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _avg_sentiment_100(events: list[dict]) -> float:
    """Convert IrisEvent sentiment [-1,+1] list to 0-100 average."""
    if not events:
        return 50.0
    vals = [float(e.get("sentiment", 0)) for e in events]
    avg = sum(vals) / len(vals)
    return (avg + 1.0) * 50.0   # [-1,+1] → [0,100]


# ── Main computation ──────────────────────────────────────────────────────────

def _feature_schema_hash() -> str:
    keys = "|".join(sorted(WEIGHTS.keys()))
    return hashlib.sha256(keys.encode()).hexdigest()[:16]


def _weight_profile() -> dict:
    return {"weights": WEIGHTS, "freshness_lambda": FRESHNESS_LAMBDA, "thresholds": RISK_TIER_THRESHOLDS}


async def _runtime_profile() -> dict:
    from backend.services.postgres_service import get_active_risk_model_config
    now = datetime.now(timezone.utc)
    if _PROFILE_CACHE.get("at") and _PROFILE_CACHE.get("profile"):
        age = (now - _PROFILE_CACHE["at"]).total_seconds()
        if age <= _PROFILE_CACHE_TTL_SECONDS:
            return _PROFILE_CACHE["profile"]
    profile = await get_active_risk_model_config()
    if profile:
        _PROFILE_CACHE["profile"] = profile
        _PROFILE_CACHE["at"] = now
    return profile or {}


def _should_log_prediction(
    previous: dict | None,
    now: datetime,
    risk_score: float,
    alert_tier: str,
) -> bool:
    if previous is None:
        return True
    prev_score = float(previous.get("risk_score", 0))
    prev_tier = previous.get("alert_tier")
    prev_ts = previous.get("predicted_at")
    seconds_since = (now - prev_ts).total_seconds() if isinstance(prev_ts, datetime) else 10**9
    return (abs(risk_score - prev_score) >= LOG_MIN_DELTA) or (alert_tier != prev_tier) or (seconds_since >= LOG_MIN_INTERVAL_SECONDS)


def _apply_guardrails(
    risk_score: float,
    raw_tier: str,
    input_coverage: float,
    event_count_6h: int,
    previous_score: float | None,
) -> tuple[float, str, list[str]]:
    warnings: list[str] = []
    guarded = risk_score

    if previous_score is not None:
        upper = min(1.0, previous_score + MAX_SCORE_STEP_DELTA)
        lower = max(0.0, previous_score - MAX_SCORE_STEP_DELTA)
        clipped = min(upper, max(lower, guarded))
        if abs(clipped - guarded) > 1e-6:
            warnings.append("score_step_capped")
        guarded = clipped

    tier = risk_tier(guarded)
    if input_coverage < MIN_INPUT_COVERAGE_FOR_HIGH_TIER and tier in ("ELEVATED", "CRITICAL"):
        warnings.append("low_input_coverage_tier_cap")
        tier = "WATCH"
        guarded = min(guarded, RISK_TIER_THRESHOLDS["elevated"] - 0.001)

    if event_count_6h < MIN_EVENTS_FOR_HIGH_TIER and tier == "CRITICAL":
        warnings.append("sparse_events_tier_cap")
        tier = "ELEVATED"
        guarded = min(guarded, 0.74)

    if raw_tier != tier:
        warnings.append(f"tier_adjusted_{raw_tier.lower()}_to_{tier.lower()}")

    return round(max(0.0, min(1.0, guarded)), 4), tier, warnings


async def compute_risk_score(district_id: str, *, persist: bool = True) -> CityPulseRiskScore:
    """
    Compute the CityPulse risk score for a district.

    Pulls live data from: Iris event DB, weather API, Ticketmaster.
    All external calls are try/caught — the algorithm always returns a score
    even when individual sources are unavailable (degrades gracefully).
    """
    from backend.services.postgres_service import fetch_recent_iris_events, fetch_rolling_signal_avg, get_latest_risk_prediction_row
    from backend.services.weather_service import fetch_weather
    from backend.services.ticketmaster_service import fetch_events
    from backend.core.zones import get_zone_by_id

    now = datetime.now(timezone.utc)
    profile = await _runtime_profile()
    effective_weights = dict(WEIGHTS)
    effective_thresholds = dict(RISK_TIER_THRESHOLDS)
    if profile.get("weights"):
        for k, v in profile.get("weights", {}).items():
            if k in effective_weights:
                try:
                    effective_weights[k] = float(v)
                except Exception:
                    pass
    if profile.get("thresholds"):
        for k, v in profile.get("thresholds", {}).items():
            if k in effective_thresholds:
                try:
                    effective_thresholds[k] = float(v)
                except Exception:
                    pass
    features: dict[str, float] = {}
    data_live: dict[str, bool] = {}

    # Resolve lat/lon for this district
    try:
        zone = get_zone_by_id(district_id)
        lat: float = float(zone.get("lat", 40.7831))
        lon: float = float(zone.get("lng", -73.9712))
    except (ValueError, KeyError):
        lat, lon = 40.7831, -73.9712  # default to Manhattan centroid
        logger.warning("[Predictor] Unknown district %s — using Manhattan centroid", district_id)

    # ── Feature 1: Sentiment Velocity ─────────────────────────────────────────
    # Measures the *rate* at which sentiment is deteriorating.
    # Formula: (smoothed_current - avg_past) / 6
    # Normalized: velocity in [-100/6, +100/6] per hour → 0-1 where drop = high risk
    try:
        recent_events   = await fetch_recent_iris_events(district_id, "general", lookback_hours=3)
        baseline_events = await fetch_recent_iris_events(district_id, "general", lookback_hours=9)

        current_sent = _avg_sentiment_100(recent_events)
        past_sent    = _avg_sentiment_100(baseline_events)

        # Apply Kalman filter to current measurement to remove noise
        kf = _get_kalman(district_id)
        smoothed_sent = kf.update(current_sent)

        # Velocity: positive = sentiment rising, negative = sentiment falling
        velocity = (smoothed_sent - past_sent) / 6.0   # per hour

        # Invert: falling sentiment → high risk
        # Map [-50/6 to +50/6] range (realistic) → [0,1] with center at 0.5
        vel_raw = max(-10.0, min(10.0, velocity))       # clamp outliers
        vel_normalized = ((-vel_raw) + 10.0) / 20.0    # invert + normalize
        features["sentiment_velocity"] = round(max(0.0, min(1.0, vel_normalized)), 4)
        data_live["sentiment_velocity"] = len(recent_events) > 0

    except Exception as e:
        logger.warning("[Predictor] sentiment_velocity error for %s: %s", district_id, e)
        features["sentiment_velocity"] = 0.35
        data_live["sentiment_velocity"] = False

    # ── Feature 2: Source Consensus ────────────────────────────────────────────
    # Fraction of recent signal sources with negative sentiment.
    # 0 = all positive, 1 = all negative → higher = more risk
    try:
        signals = await fetch_recent_iris_events(district_id, "general", lookback_hours=6)
        if signals:
            neg_count = sum(1 for e in signals if float(e.get("sentiment", 0)) < -0.15)
            consensus = neg_count / len(signals)
        else:
            consensus = 0.25
        features["source_consensus"] = round(min(1.0, max(0.0, consensus)), 4)
        data_live["source_consensus"] = len(signals) > 0

    except Exception as e:
        logger.warning("[Predictor] source_consensus error: %s", e)
        features["source_consensus"] = 0.25
        data_live["source_consensus"] = False

    # ── Feature 3: Volume Spike ────────────────────────────────────────────────
    # Current-hour signal count vs 7-day rolling hourly average.
    # Capped at 3× to prevent infinite scaling.
    try:
        last_hour  = await fetch_recent_iris_events(district_id, "general", lookback_hours=1)
        rolling_avg = await fetch_rolling_signal_avg(district_id, days=7)

        current_count = len(last_hour)
        avg_hourly    = max(1.0, float(rolling_avg))

        spike_ratio = current_count / avg_hourly
        vol_normalized = min(spike_ratio, 3.0) / 3.0   # saturation cap
        features["volume_spike"] = round(vol_normalized, 4)
        data_live["volume_spike"] = True

    except Exception as e:
        logger.warning("[Predictor] volume_spike error: %s", e)
        features["volume_spike"] = 0.2
        data_live["volume_spike"] = False

    # ── Feature 4: Weather Stress ──────────────────────────────────────────────
    # Boolean trigger on extreme conditions, partial credit for moderate stress.
    # Full (1.0): temp>35°C OR rain>10mm OR wind>60kph
    # Partial: graduated score for moderate conditions
    try:
        weather  = await fetch_weather(lat, lon)
        temp_c   = float(weather.get("temp_c", 20))
        rain_mm  = float(weather.get("rain_mm", 0))
        wind_ms  = float(weather.get("wind_ms", 0))
        wind_kph = wind_ms * 3.6

        # Full trigger
        if temp_c > 35 or rain_mm > 10 or wind_kph > 60:
            stress = 1.0
        else:
            # Graduated partial stress
            partial = 0.0
            if temp_c > 32:   partial += 0.30
            elif temp_c < -5: partial += 0.25   # extreme cold also stressful
            if rain_mm > 3:   partial += 0.30
            if wind_kph > 40: partial += 0.25
            stress = min(0.85, partial)

        features["weather_stress"] = round(stress, 4)
        data_live["weather_stress"] = True

    except Exception as e:
        logger.warning("[Predictor] weather_stress error: %s", e)
        features["weather_stress"] = 0.0
        data_live["weather_stress"] = False

    # ── Feature 5: Event Density ───────────────────────────────────────────────
    # Upcoming events in next 6h within district radius.
    # More events = more crowd = more risk potential.
    # 0 events → 0.0, 5+ events → 1.0 (saturation)
    try:
        events = await fetch_events(lat, lon, radius_km=3)
        count  = len(events)
        event_density = min(1.0, count / 5.0)
        features["event_density"] = round(event_density, 4)
        data_live["event_density"] = True

    except Exception as e:
        logger.warning("[Predictor] event_density error: %s", e)
        features["event_density"] = 0.1
        data_live["event_density"] = False

    # ── Feature 6: Geo Spillover ───────────────────────────────────────────────
    # Average negative pressure from neighbouring districts.
    # Uses simple adjacency from DISTRICT_NEIGHBORS map.
    # Low neighbor sentiment → high spillover risk.
    try:
        neighbors = DISTRICT_NEIGHBORS.get(district_id, [])
        neighbor_scores: list[float] = []

        for n_id in neighbors[:4]:    # cap lookups at 4 to stay fast
            n_events = await fetch_recent_iris_events(n_id, "general", lookback_hours=6)
            if n_events:
                n_sent = _avg_sentiment_100(n_events)
                neighbor_scores.append(n_sent)

        if neighbor_scores:
            avg_neighbor = sum(neighbor_scores) / len(neighbor_scores)
            # Map: 100 (very positive) → 0.0,  0 (very negative) → 1.0
            spillover = max(0.0, (50.0 - avg_neighbor) / 50.0 + 0.5)
            spillover = max(0.0, min(1.0, spillover))
        else:
            spillover = 0.2

        features["geo_spillover"] = round(spillover, 4)
        data_live["geo_spillover"] = len(neighbor_scores) > 0

    except Exception as e:
        logger.warning("[Predictor] geo_spillover error: %s", e)
        features["geo_spillover"] = 0.2
        data_live["geo_spillover"] = False

    # ── Feature 7: Time of Day ─────────────────────────────────────────────────
    # Risk is highest in evening/night hours.
    # 18:00–02:00 = peak (multiplier 1.3), 02:00–06:00 = quiet (0.8), else normal (1.0)
    try:
        hour = now.hour
        if 18 <= hour <= 23 or 0 <= hour < 2:
            tod_raw = 1.3
        elif 2 <= hour < 6:
            tod_raw = 0.8
        else:
            tod_raw = 1.0
        # Normalize [0.8, 1.3] → [0.0, 1.0]
        tod_normalized = (tod_raw - 0.8) / 0.5
        features["time_of_day"] = round(max(0.0, min(1.0, tod_normalized)), 4)
        data_live["time_of_day"] = True

    except Exception:
        features["time_of_day"] = 0.4   # default daytime
        data_live["time_of_day"] = True

    # ── Freshness Decay ────────────────────────────────────────────────────────
    # If last signal is hours old, discount the entire score.
    # e^(-λ*t): λ=0.3 means 50% decay after 2.3 hours, 90% decay after 7.7 hours.
    # This prevents stale CRITICAL alerts from persisting indefinitely.
    try:
        all_recent = await fetch_recent_iris_events(district_id, "general", lookback_hours=48)
        if all_recent:
            ts_strings = [e.get("occurred_at", "") for e in all_recent if e.get("occurred_at")]
            if ts_strings:
                latest_str = max(ts_strings)
                latest_dt  = datetime.fromisoformat(latest_str.replace("Z", "+00:00"))
                hours_old  = max(0.0, (now - latest_dt).total_seconds() / 3600.0)
            else:
                hours_old = 12.0
        else:
            hours_old = 24.0    # no data at all → treat as very stale

        decay = math.exp(-FRESHNESS_LAMBDA * hours_old)

    except Exception as e:
        logger.warning("[Predictor] freshness_decay error: %s", e)
        decay = 0.5

    event_count_6h = 0
    try:
        event_count_6h = len(await fetch_recent_iris_events(district_id, "general", lookback_hours=6))
    except Exception:
        event_count_6h = 0

    # ── Weighted Score Assembly ────────────────────────────────────────────────
    raw_score = sum(effective_weights[k] * features[k] for k in effective_weights)
    input_coverage = round(sum(data_live.values()) / max(1, len(data_live)), 3)
    # Penalize under-observed windows to reduce overconfident spikes.
    quality_penalty = 1.0
    if input_coverage < 0.75:
        quality_penalty -= min(0.30, (0.75 - input_coverage) * 0.6)
    if event_count_6h < 3:
        quality_penalty -= 0.08
    if event_count_6h == 0:
        quality_penalty -= 0.08
    quality_penalty = max(0.55, min(1.0, quality_penalty))
    risk_score = round(max(0.0, min(1.0, raw_score * decay * quality_penalty)), 4)
    raw_tier = risk_tier(risk_score)

    # Optional lightweight post-score calibration (affine)
    try:
        from backend.services.risk_calibration_service import get_calibration_params, apply_affine_calibration
        cal = await get_calibration_params(district_id)
        if cal.get("enabled"):
            risk_score = round(apply_affine_calibration(risk_score, float(cal["alpha"]), float(cal["beta"])), 4)
    except Exception as ce:
        logger.debug("[Predictor] calibration skipped for %s: %s", district_id, ce)

    # ── Top Drivers (top 3 feature contributions) ─────────────────────────────
    contributions = {k: round(effective_weights[k] * features[k], 5) for k in effective_weights}
    top_drivers   = sorted(contributions, key=lambda k: contributions[k], reverse=True)[:3]

    # ── Input Coverage ─────────────────────────────────────────────────────────

    latest = await get_latest_risk_prediction_row(district_id)
    previous_score = float(latest.get("risk_score")) if latest else None
    guarded_score, guarded_tier, warnings = _apply_guardrails(
        risk_score=risk_score,
        raw_tier=raw_tier,
        input_coverage=input_coverage,
        event_count_6h=event_count_6h,
        previous_score=previous_score,
    )

    result = CityPulseRiskScore(
        district_id     = district_id,
        risk_score      = guarded_score,
        alert_tier      = guarded_tier,
        top_drivers     = top_drivers,
        feature_values  = {k: round(v, 4) for k, v in features.items()},
        freshness_decay = round(decay, 4),
        input_coverage  = input_coverage,
        algorithm_version = ALGORITHM_VERSION,
        feature_schema_hash = _feature_schema_hash(),
        weight_profile = {
            "weights": effective_weights,
            "thresholds": effective_thresholds,
            "base": _weight_profile(),
            "runtime_profile_updated_at": profile.get("updated_at"),
        },
        warnings = warnings,
        computed_at     = now,
        valid_until     = now + timedelta(hours=max(1, settings.risk_horizon_hours)),
    )
    result.feature_values["quality_penalty"] = round(quality_penalty, 4)
    if quality_penalty < 0.85:
        result.warnings.append("data_quality_penalty_applied")

    # Log prediction to PostgreSQL for IC tracking + future ML training
    if persist and _should_log_prediction(latest, now, result.risk_score, result.alert_tier):
        try:
            from backend.services.postgres_service import log_risk_prediction
            await log_risk_prediction(
                district_id       = district_id,
                risk_score        = result.risk_score,
                alert_tier        = result.alert_tier,
                feature_values    = features,
                input_coverage    = input_coverage,
                algorithm_version = ALGORITHM_VERSION,
                sentiment_at_prediction = _avg_sentiment_100(
                    await fetch_recent_iris_events(district_id, "general", lookback_hours=1)
                ),
                weight_profile = result.weight_profile,
                feature_schema_hash = result.feature_schema_hash,
            )
        except Exception as e:
            logger.warning("[Predictor] Failed to log prediction: %s", e)

    logger.info(
        "[Predictor] %s → score=%.4f tier=%s drivers=%s decay=%.3f coverage=%.2f warnings=%s",
        district_id, result.risk_score, result.alert_tier, top_drivers, decay, input_coverage, warnings,
    )
    return result


async def get_all_district_scores(*, persist: bool = False) -> list[CityPulseRiskScore]:
    """Compute risk scores for all NYC districts in parallel."""
    import asyncio
    from backend.core.zones import get_all_zone_ids
    zone_ids = get_all_zone_ids()
    tasks    = [compute_risk_score(zid, persist=persist) for zid in zone_ids]
    results  = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[CityPulseRiskScore] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("[Predictor] bulk score failed for %s: %s", zone_ids[i], r)
        else:
            out.append(r)
    return out
