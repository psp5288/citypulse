import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from backend.core.district_format import format_many, format_one
from backend.core.districts import DISTRICTS, DISTRICT_MAP
from backend.services.postgres_service import get_district_snapshots, get_snapshots_range
from backend.services.redis_service import get_all_scores, get_district_score
from backend.websocket.manager import manager

logger = logging.getLogger(__name__)

router = APIRouter()
ws_router = APIRouter()


def _fallback_raw() -> list[dict]:
    return [
        {
            "id": d["id"],
            "name": d["name"],
            "crowd_density": 0.5,
            "sentiment_score": 0.5,
            "safety_risk": 0.35,
            "weather_impact": 0.1,
            "confidence": 0.5,
            "summary": "Awaiting first WatsonX scoring cycle…",
            "flags": [],
            "events_count": 0,
            "updated_at": None,
        }
        for d in DISTRICTS
    ]


@router.get("/districts")
async def list_districts():
    raw = await get_all_scores()
    if not raw:
        raw = _fallback_raw()
    return format_many(raw)


@router.get("/districts/{district_id}")
async def get_district_detail(district_id: str):
    d = await get_district_score(district_id)
    if not d:
        meta = DISTRICT_MAP.get(district_id)
        if not meta:
            return {"error": "not found", "district_id": district_id}
        d = {
            "id": district_id,
            "name": meta["name"],
            "crowd_density": 0.5,
            "sentiment_score": 0.5,
            "safety_risk": 0.35,
            "events_count": 0,
            "summary": "",
        }
    history = await get_district_snapshots(district_id, limit=10)
    return {"district": format_one(d), "history": history}


@router.get("/districts/snapshots")
async def district_snapshots(
    district: Optional[str] = Query(default=None),
    time_from: Optional[datetime] = Query(default=None, alias="from"),
    time_to: Optional[datetime] = Query(default=None, alias="to"),
):
    return await get_snapshots_range(district, time_from, time_to)


async def _ws_ping_loop(ws: WebSocket):
    try:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
    except Exception:
        pass


@ws_router.websocket("/ws/districts")
async def ws_districts(websocket: WebSocket):
    await manager.connect(websocket)
    raw = await get_all_scores()
    if not raw:
        raw = _fallback_raw()
    payload = format_many(raw)
    try:
        await websocket.send_json({"type": "districts_update", "data": payload})
    except Exception:
        manager.disconnect(websocket)
        return

    ping_task = asyncio.create_task(_ws_ping_loop(websocket))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        manager.disconnect(websocket)
