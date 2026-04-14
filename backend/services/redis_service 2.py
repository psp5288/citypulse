import json
import logging
from typing import Optional

import redis.asyncio as aioredis

from backend.config import settings
from backend.core.models import ZoneScore

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None

ZONE_TTL = 65  # seconds — slightly more than 30s update interval


async def init_redis():
    global _redis
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    await _redis.ping()
    logger.info("Redis connected: %s", settings.redis_url.split("@")[-1] if "@" in settings.redis_url else settings.redis_url)


async def close_redis():
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> aioredis.Redis:
    if not _redis:
        raise RuntimeError("Redis not initialized")
    return _redis


async def set_zone_score(zone_id: str, score: ZoneScore):
    r = get_redis()
    await r.setex(f"zone:{zone_id}", ZONE_TTL, score.model_dump_json())


async def get_zone_score(zone_id: str) -> dict | None:
    r = get_redis()
    data = await r.get(f"zone:{zone_id}")
    return json.loads(data) if data else None


async def get_all_zone_scores() -> list[dict]:
    r = get_redis()
    keys = await r.keys("zone:*")
    scores = []
    for key in keys:
        data = await r.get(key)
        if data:
            scores.append(json.loads(data))
    return scores


async def health_check() -> bool:
    try:
        await get_redis().ping()
        return True
    except Exception:
        return False


ANALYTICS_CACHE_TTL = 300  # seconds


async def get_cached_analytics(range_key: str) -> dict | None:
    r = get_redis()
    raw = await r.get(f"analytics:{range_key}")
    return json.loads(raw) if raw else None


async def cache_analytics(range_key: str, payload: dict) -> None:
    r = get_redis()
    await r.setex(f"analytics:{range_key}", ANALYTICS_CACHE_TTL, json.dumps(payload))
