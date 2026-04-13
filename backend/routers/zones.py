import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.services.redis_service import get_all_zone_scores

logger = logging.getLogger(__name__)

router = APIRouter()
ws_router = APIRouter()

_connected_clients: list[WebSocket] = []


@router.get("/zones")
async def get_zones():
    scores = await get_all_zone_scores()
    return {"zones": scores, "count": len(scores), "timestamp": datetime.utcnow().isoformat()}


@ws_router.websocket("/ws/zones")
async def websocket_zones(ws: WebSocket):
    await ws.accept()
    _connected_clients.append(ws)
    logger.info(f"WebSocket client connected. Total: {len(_connected_clients)}")
    try:
        while True:
            scores = await get_all_zone_scores()
            await ws.send_json({
                "type": "zone_update",
                "zones": scores,
                "timestamp": datetime.utcnow().isoformat(),
            })
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        _connected_clients.remove(ws)
        logger.info(f"WebSocket client disconnected. Total: {len(_connected_clients)}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if ws in _connected_clients:
            _connected_clients.remove(ws)


async def broadcast_alert(alert: dict):
    """Push alert to all connected WebSocket clients."""
    dead = []
    for ws in _connected_clients:
        try:
            await ws.send_json({"type": "alert", "alert": alert})
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _connected_clients:
            _connected_clients.remove(ws)
