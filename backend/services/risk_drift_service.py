from __future__ import annotations

import asyncio
import logging

from backend.core.zones import get_all_zone_ids
from backend.services.predictor_service import WEIGHTS

logger = logging.getLogger(__name__)

DRIFT_INTERVAL_SECONDS = 3600


def compute_drift_score(recent_mean: float, baseline_mean: float, baseline_std: float) -> float:
    denom = max(0.05, baseline_std)
    return abs(recent_mean - baseline_mean) / denom


async def run_risk_drift_monitor_loop() -> None:
    logger.info("[Risk Drift] Monitor started (interval=%ds)", DRIFT_INTERVAL_SECONDS)
    while True:
        try:
            await asyncio.sleep(DRIFT_INTERVAL_SECONDS)
            await scan_drift_once()
        except asyncio.CancelledError:
            logger.info("[Risk Drift] Monitor cancelled")
            break
        except Exception as e:
            logger.error("[Risk Drift] Monitor error: %s", e, exc_info=True)


async def scan_drift_once() -> dict:
    from backend.services.postgres_service import (
        fetch_feature_distribution_stats,
        create_risk_drift_alert,
        get_active_risk_model_config,
    )

    profile = await get_active_risk_model_config() or {}
    params = profile.get("params") or {}
    threshold = float(params.get("drift_z_threshold", 2.5))
    alerts = 0

    for district_id in get_all_zone_ids():
        for feature_name in WEIGHTS.keys():
            stats = await fetch_feature_distribution_stats(district_id, feature_name)
            if stats.get("recent_mean") is None or stats.get("baseline_mean") is None:
                continue
            drift = compute_drift_score(
                recent_mean=float(stats["recent_mean"]),
                baseline_mean=float(stats["baseline_mean"]),
                baseline_std=float(stats.get("baseline_std") or 0.0),
            )
            if drift >= threshold:
                await create_risk_drift_alert(
                    district_id=district_id,
                    feature_name=feature_name,
                    baseline_mean=float(stats["baseline_mean"]),
                    recent_mean=float(stats["recent_mean"]),
                    drift_score=drift,
                    threshold=threshold,
                    metadata={"recent_n": len(stats.get("recent") or []), "baseline_n": len(stats.get("baseline") or [])},
                )
                alerts += 1

    if alerts:
        logger.warning("[Risk Drift] %d drift alert(s) created", alerts)
    return {"ok": True, "alerts_created": alerts, "threshold": threshold}
