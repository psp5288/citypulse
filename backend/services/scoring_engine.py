import asyncio
from datetime import datetime, timezone

from backend.core.districts import DISTRICTS
from backend.services.reddit_service import fetch_posts
from backend.services.weather_service import fetch_weather
from backend.services.ticketmaster_service import fetch_events
from backend.services.watsonx_service import score_district
from backend.services.redis_service import set_district_score, set_all_scores
from backend.services.postgres_service import save_snapshot, create_event
from backend.core.alert_rules import evaluate_rules
from backend.core.logger import logger


async def score_single_district(district: dict) -> dict:
    start = datetime.now(timezone.utc)

    social, weather, events = await asyncio.gather(
        fetch_posts(district["subreddits"], district["keywords"]),
        fetch_weather(district["lat"], district["lon"]),
        fetch_events(district["lat"], district["lon"], district["radius_km"]),
        return_exceptions=True,
    )

    context = {
        "district_name": district["name"],
        "social_posts": social if isinstance(social, list) else [],
        "weather": weather if isinstance(weather, dict) else {},
        "events": events if isinstance(events, list) else [],
        "traffic": {},
    }

    scores = await score_district(district["id"], context)

    scores["id"] = district["id"]
    scores["name"] = district["name"]
    scores["updated_at"] = datetime.now(timezone.utc).isoformat()
    scores["events_count"] = len(context["events"])
    scores["source_data"] = {
        "social_count": len(context["social_posts"]),
        "weather_condition": context["weather"].get("condition", "unknown"),
        "events_nearby": len(context["events"]),
    }

    latency_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    logger.info(f"Scored {district['id']} in {latency_ms}ms | confidence={scores.get('confidence', 0):.2f}")

    return scores


async def score_all_districts() -> list[dict]:
    start = datetime.now(timezone.utc)

    tasks = [score_single_district(d) for d in DISTRICTS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scored = []
    for d, result in zip(DISTRICTS, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to score {d['id']}: {result}")
            continue
        scored.append(result)

    if scored:
        await set_all_scores(scored)
        for score in scored:
            try:
                await save_snapshot(score)
            except Exception as e:
                logger.error(f"Failed to save snapshot for {score['id']}: {e}")
            try:
                await evaluate_rules(score)
            except Exception as e:
                logger.error(f"Failed to evaluate rules for {score['id']}: {e}")

    total_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    logger.info(f"Scored {len(scored)}/{len(DISTRICTS)} districts in {total_ms}ms")

    return scored
