from fastapi import APIRouter, Query
from typing import Optional

from backend.services.postgres_service import get_latest_snapshots, get_district_snapshots

router = APIRouter()


@router.get("/districts/snapshots")
async def list_snapshots(
    district_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    if district_id:
        return await get_district_snapshots(district_id, limit=limit)
    return await get_latest_snapshots()
