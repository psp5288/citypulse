"""
CityPulse Risk API

Endpoints:
  GET  /api/risk                              — risk scores for all districts (bulk)
  GET  /api/risk/{district_id}                — risk score for one district (Redis cached 5 min)
  POST /api/risk/outcome/{id}                 — manually record an outcome for IC tracking
  GET  /api/risk/ic                           — information coefficient diagnostics
  GET  /api/risk/backtest/{district_id}       — walk-forward backtest for one district
  GET  /api/risk/backtest                     — backtest all districts (returns summary table)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend.services.predictor_service import (
    CityPulseRiskScore,
    compute_risk_score,
    CACHE_TTL_SECONDS,
)
from backend.services.backtest_service import run_backtest

logger = logging.getLogger(__name__)
router = APIRouter()
_DEBUG_LOG_PATH = Path("/Users/parin/Desktop/citypulse.v1.1/.cursor/debug-0139ff.log")


def _debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "0139ff",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
    # endregion


# ── Redis cache helpers ───────────────────────────────────────────────────────

async def _get_cached(district_id: str) -> CityPulseRiskScore | None:
    try:
        from backend.services.redis_service import get_redis
        r = get_redis()
        raw = await r.get(f"risk:{district_id}")
        if raw:
            return CityPulseRiskScore(**json.loads(raw))
    except Exception as e:
        logger.debug("[Risk] Cache miss for %s: %s", district_id, e)
    return None


async def _set_cached(score: CityPulseRiskScore) -> None:
    try:
        from backend.services.redis_service import get_redis
        r = get_redis()
        payload = score.model_dump_json()
        await r.setex(f"risk:{score.district_id}", CACHE_TTL_SECONDS, payload)
    except Exception as e:
        logger.warning("[Risk] Cache write failed for %s: %s", score.district_id, e)


# ── GET /api/risk ─────────────────────────────────────────────────────────────

@router.get("/risk")
async def get_all_risk_scores():
    """
    Return risk scores for all districts.
    Each district uses its own 5-min Redis cache independently.
    Uncached districts are computed fresh and cached on-the-fly.
    """
    from backend.core.zones import get_all_zone_ids
    zone_ids = get_all_zone_ids()
    out = []
    for zone_id in zone_ids:
        cached = await _get_cached(zone_id)
        if cached:
            out.append(_serialize(cached))
            continue
        s = await compute_risk_score(zone_id, persist=False)
        await _set_cached(s)
        out.append(_serialize(s))
    return out


# ── GET /api/risk/district/{district_id} ──────────────────────────────────────

@router.get("/risk/district/{district_id}")
async def get_district_risk(district_id: str, force: bool = Query(default=False)):
    """
    Return the risk score for a single district.

    - Reads from Redis cache (TTL 5 min) unless `?force=true` is passed.
    - On cache miss: computes fresh score, stores in cache, returns result.
    - Score includes: risk_score (0-1), alert_tier, top_drivers, feature_values,
      freshness_decay, input_coverage, algorithm_version, valid_until.
    """
    if not force:
        cached = await _get_cached(district_id)
        if cached:
            return {**_serialize(cached), "cache": "hit"}

    try:
        score = await compute_risk_score(district_id, persist=False)
    except Exception as e:
        logger.error("[Risk] compute_risk_score failed for %s: %s", district_id, e)
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e), "district_id": district_id},
        )

    await _set_cached(score)
    return {**_serialize(score), "cache": "miss"}


# ── POST /api/risk/outcome/{district_id} ──────────────────────────────────────

@router.post("/risk/outcome/{district_id}")
async def record_outcome(district_id: str, body: dict):
    """
    Manually record outcome for a prediction (for IC calibration).
    Body: { "significant_event": true/false, "sentiment_6h_later": 45.2 }
    """
    from backend.services.postgres_service import record_manual_risk_outcome
    prediction_id = body.get("prediction_id")
    if prediction_id is None:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "error": "prediction_id is required", "district_id": district_id},
        )
    ok = await record_manual_risk_outcome(
        prediction_id=int(prediction_id),
        district_id=district_id,
        sentiment_6h_later=body.get("sentiment_6h_later"),
        significant_event=body.get("significant_event"),
    )
    if not ok:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "prediction row not found for district", "district_id": district_id},
        )
    return {"ok": True, "district_id": district_id, "prediction_id": int(prediction_id)}


# ── GET /api/risk/ic ──────────────────────────────────────────────────────────

@router.get("/risk/ic")
async def get_ic_stats(
    district_id: str = Query(default=None),
    days: int = Query(default=30),
):
    """
    Return Information Coefficient diagnostics.
    IC > 0.05 = tradeable signal. IC > 0.15 = world-class.
    """
    from backend.services.postgres_service import get_ic_stats
    stats = await get_ic_stats(district_id=district_id, days=days)
    return stats


@router.get("/risk/config")
async def get_risk_config():
    from backend.services.postgres_service import get_active_risk_model_config
    cfg = await get_active_risk_model_config()
    return cfg or {"status": "default_config_in_use"}


@router.post("/risk/config")
async def set_risk_config(body: dict):
    from backend.services.postgres_service import save_risk_model_config
    algorithm_version = str(body.get("algorithm_version") or f"runtime-{datetime.now(timezone.utc).isoformat()}")
    row_id = await save_risk_model_config(
        algorithm_version=algorithm_version,
        weights=body.get("weights") or {},
        thresholds=body.get("thresholds") or {},
        params=body.get("params") or {},
        make_active=bool(body.get("make_active", True)),
    )
    return {"ok": True, "config_id": row_id, "algorithm_version": algorithm_version}


@router.get("/risk/calibration/{district_id}")
async def get_risk_calibration(district_id: str):
    _debug_log("H8", "backend/routers/risk.py:get_risk_calibration", "Calibration endpoint hit", {"district_id": district_id})
    from backend.services.risk_calibration_service import get_calibration_params
    return await get_calibration_params(district_id)


@router.get("/risk/drift")
async def get_risk_drift(limit: int = Query(default=100, ge=1, le=500)):
    _debug_log("H8", "backend/routers/risk.py:get_risk_drift", "Drift endpoint hit", {"limit": limit})
    from backend.services.postgres_service import list_recent_drift_alerts
    return {"alerts": await list_recent_drift_alerts(limit=limit)}


@router.post("/risk/drift/run")
async def run_risk_drift_scan():
    from backend.services.risk_drift_service import scan_drift_once
    return await scan_drift_once()


# ── Serializer ────────────────────────────────────────────────────────────────

# ── GET /api/risk/backtest/{district_id} ─────────────────────────────────────

@router.get("/risk/backtest/{district_id}")
async def backtest_district(
    district_id: str,
    lookback_days: int = Query(default=14, ge=1, le=90),
    horizon_hours: int = Query(default=6,  ge=1, le=48),
    step_hours:    int = Query(default=6,  ge=1, le=24),
):
    """
    Walk-forward backtest for one district.

    Recomputes what the algorithm *would have predicted* at each past
    time window using only data available at that point — then checks
    what sentiment actually did `horizon_hours` later.

    Returns IC, AUC-ROC, precision/recall at ELEVATED tier, calibration
    curve, per-feature IC, and per-window raw predictions.

    Query params:
      lookback_days  How many days of history to walk through (default 14)
      horizon_hours  Prediction window to verify against (default 6)
      step_hours     Sampling interval between windows (default 6)
    """
    result = await run_backtest(
        district_id   = district_id,
        lookback_days = lookback_days,
        horizon_hours = horizon_hours,
        step_hours    = step_hours,
    )
    return result


# ── GET /api/risk/backtest ────────────────────────────────────────────────────

@router.get("/risk/backtest")
async def backtest_all(
    lookback_days: int = Query(default=7, ge=1, le=30),
    horizon_hours: int = Query(default=6, ge=1, le=24),
):
    """
    Run backtest across all districts and return a summary leaderboard.
    Ordered by IC descending — shows which districts the algorithm predicts best.

    Uses shorter defaults (7d lookback, 6h steps) to avoid long wait times.
    For full per-window data, use /api/risk/backtest/{district_id}.
    """
    import asyncio
    from backend.core.zones import get_all_zone_ids

    zone_ids = get_all_zone_ids()
    tasks    = [
        run_backtest(zid, lookback_days=lookback_days, horizon_hours=horizon_hours, step_hours=6)
        for zid in zone_ids
    ]
    results  = await asyncio.gather(*tasks, return_exceptions=True)

    summary_rows = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            logger.error("[Backtest] %s failed: %s", zone_ids[i], r)
            continue
        if not isinstance(r, dict):
            continue
        m = r.get("metrics") or {}
        summary_rows.append({
            "district_id":         r["district_id"],
            "n_windows":           r["n_windows"],
            "n_events":            r["n_events"],
            "event_base_rate":     r.get("event_base_rate", 0),
            "ic":                  m.get("ic"),
            "auc_roc":             m.get("auc_roc"),
            "precision_elevated":  m.get("precision_elevated"),
            "recall_elevated":     m.get("recall_elevated"),
            "signal_quality":      m.get("signal_quality"),
            "summary":             r.get("summary"),
        })

    # Sort by IC descending, nulls last
    summary_rows.sort(key=lambda x: x["ic"] or -999, reverse=True)

    return {
        "lookback_days": lookback_days,
        "horizon_hours": horizon_hours,
        "districts":     summary_rows,
        "caveats": [
            "weather_stress and event_density features use historical approximations",
            "Small n_windows → high IC variance. Trust IC more as windows grow.",
            "IC > 0.05 = real signal. IC > 0.15 = world-class.",
        ],
    }


# ── Serializer ────────────────────────────────────────────────────────────────

def _serialize(score: CityPulseRiskScore) -> dict:
    d = score.model_dump()
    d["computed_at"] = score.computed_at.isoformat()
    d["valid_until"]  = score.valid_until.isoformat()
    return d
