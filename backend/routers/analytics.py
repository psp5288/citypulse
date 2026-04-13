from fastapi import APIRouter, Query
from typing import Literal
import asyncio

from backend.services.redis_service import get_cached_analytics, cache_analytics
from backend.services.postgres_service import compute_analytics

router = APIRouter()
_inflight: dict[str, asyncio.Task] = {}


@router.get("/analytics")
async def get_analytics(
    range_key: Literal["1h", "6h", "24h", "7d"] = Query(default="1h", alias="range"),
):
    cached = await get_cached_analytics(range_key)
    if cached:
        return cached

    existing = _inflight.get(range_key)
    if existing:
        return await existing

    async def _compute_and_cache() -> dict:
        data = await compute_analytics(range_key)
        await cache_analytics(range_key, data)
        return data

    task = asyncio.create_task(_compute_and_cache(), name=f"analytics-{range_key}")
    _inflight[range_key] = task
    try:
        return await task
    finally:
        _inflight.pop(range_key, None)
