import asyncio
import logging

from backend.config import settings
from backend.core.district_format import format_many
from backend.services.scoring_engine import score_all_districts
from backend.websocket.manager import manager

logger = logging.getLogger(__name__)


async def run_city_pulse_loop():
    """Score all districts on an interval and push to WebSocket subscribers."""
    while True:
        try:
            scored = await score_all_districts()
            payload = format_many(scored)
            await manager.broadcast_json({"type": "districts_update", "data": payload})
        except Exception as e:
            logger.exception("City Pulse scoring loop failed: %s", e)
        await asyncio.sleep(settings.update_interval_seconds)
