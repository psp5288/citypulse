import json
import logging
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from backend.config import settings
from backend.core.models import ZoneScore

logger = logging.getLogger(__name__)

_redis: Optional[aioredis.Redis] = None

ZONE_TTL = 65
DISTRICT_TTL = 65


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


# ── Legacy zone keys (DevCity) ───────────────────────────────────────────────

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


# ── City Pulse: district:{id} + districts:all ────────────────────────────────


def _normalize_for_cache(score: dict) -> dict:
    """Ensure JSON-serializable district record for Redis."""
    return {
        "id": score.get("id"),
        "name": score.get("name"),
        "crowd_density": float(score.get("crowd_density", 0)),
        "sentiment_score": float(score.get("sentiment_score", 0)),
        "safety_risk": float(score.get("safety_risk", 0)),
        "weather_impact": float(score.get("weather_impact", 0)),
        "confidence": float(score.get("confidence", 0)),
        "summary": score.get("summary", ""),
        "flags": score.get("flags", []),
        "events_count": int(score.get("events_count", 0)),
        "source_data": score.get("source_data", {}),
        "updated_at": score.get("updated_at"),
    }


async def set_district_score(district_id: str, score: dict):
    r = get_redis()
    payload = json.dumps(_normalize_for_cache({**score, "id": district_id}))
    await r.setex(f"district:{district_id}", DISTRICT_TTL, payload)


async def set_all_scores(scores: list[dict]):
    """Atomic multi-key refresh: district:* + districts:all + alerts:active cache untouched."""
    if not scores:
        return
    r = get_redis()
    pipe = r.pipeline()
    normalized = []
    for s in scores:
        n = _normalize_for_cache(s)
        if not n.get("id"):
            continue
        normalized.append(n)
        pipe.setex(f"district:{n['id']}", DISTRICT_TTL, json.dumps(n))
    if not normalized:
        return
    pipe.setex("districts:all", DISTRICT_TTL, json.dumps(normalized))
    # Freshness metadata for health diagnostics.
    pipe.setex("meta:districts:last_update", 86400, normalized[0].get("updated_at") or "")
    await pipe.execute()


async def get_district_score(district_id: str) -> dict | None:
    r = get_redis()
    raw = await r.get(f"district:{district_id}")
    return json.loads(raw) if raw else None


async def get_all_scores() -> list[dict]:
    """Primary read for GET /api/districts."""
    r = get_redis()
    raw = await r.get("districts:all")
    if raw:
        return json.loads(raw)
    keys = await r.keys("district:*")
    out = []
    for key in keys:
        if key == "districts:all":
            continue
        data = await r.get(key)
        if data:
            out.append(json.loads(data))
    return sorted(out, key=lambda x: x.get("name", x.get("id", "")))


async def set_alerts_active_cache(alerts: list[dict]):
    r = get_redis()
    await r.setex("alerts:active", 120, json.dumps(alerts))


async def get_alerts_active_cache() -> list[dict] | None:
    r = get_redis()
    raw = await r.get("alerts:active")
    return json.loads(raw) if raw else None


# Alert rule dedup (15–60 min cooldown)
async def check_alert_dedup(district_id: str, rule_key: str) -> bool:
    r = get_redis()
    return bool(await r.exists(f"dedup:alert:{district_id}:{rule_key}"))


async def set_alert_dedup(district_id: str, rule_key: str, minutes: int):
    r = get_redis()
    await r.setex(f"dedup:alert:{district_id}:{rule_key}", max(60, minutes * 60), "1")


async def health_check() -> bool:
    try:
        await get_redis().ping()
        return True
    except Exception:
        return False


ANALYTICS_CACHE_TTL = 60


async def get_cached_analytics(range_key: str) -> dict | None:
    r = get_redis()
    raw = await r.get(f"analytics:{range_key}")
    return json.loads(raw) if raw else None


async def cache_analytics(range_key: str, payload: dict) -> None:
    r = get_redis()
    pipe = r.pipeline()
    pipe.setex(f"analytics:{range_key}", ANALYTICS_CACHE_TTL, json.dumps(payload))
    pipe.setex(
        "meta:analytics:last_update",
        86400,
        datetime.now(timezone.utc).isoformat(),
    )
    await pipe.execute()


async def get_freshness_meta() -> dict:
    r = get_redis()
    district_ts = await r.get("meta:districts:last_update")
    analytics_meta = await r.get("meta:analytics:last_update")
    return {
        "districts_last_update": district_ts,
        "analytics_last_update": analytics_meta,
    }
