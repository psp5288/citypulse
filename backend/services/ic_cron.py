"""
IC Backfill Cron — Information Coefficient tracking loop.

Runs every 30 minutes. Finds risk predictions made ~6+ hours ago
with no outcome recorded, fetches current sentiment, computes delta,
and marks significant_event = True/False for IC calibration.

This is the feedback loop that enables:
  1. Calibration checks (are our scores well-calibrated?)
  2. v2 ML training data (features → actual outcome)
  3. IC monitoring (is our signal improving over time?)
"""

from __future__ import annotations

import asyncio
import logging
from backend.config import settings

logger = logging.getLogger(__name__)

IC_BACKFILL_INTERVAL_SECONDS = 1800   # every 30 minutes


async def run_ic_backfill_loop() -> None:
    """Background task: periodically backfill outcome labels for past predictions."""
    logger.info("[IC Cron] Backfill loop started (interval=%ds)", IC_BACKFILL_INTERVAL_SECONDS)

    while True:
        try:
            await asyncio.sleep(IC_BACKFILL_INTERVAL_SECONDS)
            from backend.services.postgres_service import backfill_risk_outcomes
            updated = await backfill_risk_outcomes(
                lookback_hours=48,
                horizon_hours=max(1, settings.risk_horizon_hours),
                window_hours=1,
            )
            if updated > 0:
                logger.info("[IC Cron] Backfilled outcomes for %d prediction(s)", updated)
        except asyncio.CancelledError:
            logger.info("[IC Cron] Backfill loop cancelled")
            break
        except Exception as e:
            logger.error("[IC Cron] Backfill error: %s", e, exc_info=True)
            # Never crash the loop — just wait and retry next cycle
