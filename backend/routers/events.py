from fastapi import APIRouter, Query
from typing import Optional

from backend.services.postgres_service import get_events

router = APIRouter()


@router.get("/events")
async def list_events(
    limit: int = Query(default=20, ge=1, le=100),
    district: Optional[str] = Query(default=None),
):
    return await get_events(limit=limit, district_id=district)
