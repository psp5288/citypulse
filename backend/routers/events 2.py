from fastapi import APIRouter, Query
from typing import Optional

from backend.services.postgres_service import get_events

router = APIRouter()

_COLOR = {
    "ALERT": "#c0392b",
    "WARNING": "#b35a00",
    "INFO": "#888580",
    "EVENT": "#555555",
    "alert": "#c0392b",
}


@router.get("/events")
async def list_events(
    limit: int = Query(default=20, ge=1, le=100),
    district: Optional[str] = Query(default=None),
):
    rows = await get_events(limit=limit, district_id=district)
    out = []
    for e in rows:
        t = e.get("type") or "INFO"
        out.append(
            {
                "type": t.upper() if isinstance(t, str) else "INFO",
                "color": _COLOR.get(t.upper(), _COLOR.get(t, "#888580")),
                "text": e.get("message", ""),
                "time": e.get("created_at", ""),
                "time_ago": "",
                "district_id": e.get("district_id"),
            }
        )
    return out
