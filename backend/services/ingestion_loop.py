import asyncio
import logging
from datetime import datetime, timezone

from backend.config import settings
from backend.core.districts import DISTRICTS
from backend.core.district_format import format_many
from backend.services.iris_service import ingest_events, normalize_signal_event
from backend.services.reddit_service import fetch_posts as fetch_reddit_posts
from backend.services.scoring_engine import score_all_districts
from backend.services.ticketmaster_service import fetch_events
from backend.services.weather_service import fetch_weather
from backend.websocket.manager import manager

logger = logging.getLogger(__name__)


def _topic_candidates(district: dict) -> list[str]:
    base = district.get("keywords") or ["general"]
    out = [k.lower().strip() for k in base[:4] if k]
    if "sports" not in out:
        out.append("sports")
    return out


async def _ingest_free_signals() -> None:
    events = []
    for district in DISTRICTS:
        subreddits = district.get("subreddits") or []
        keywords = district.get("keywords") or [district.get("name", "city")]
        topic = _topic_candidates(district)[0]
        location = district.get("name", district.get("id", "unknown"))
        social_posts, weather, nearby_events = await asyncio.gather(
            fetch_reddit_posts(subreddits=subreddits, keywords=keywords, limit=15),
            fetch_weather(district["lat"], district["lon"]),
            fetch_events(district["lat"], district["lon"], district.get("radius_km", 3)),
            return_exceptions=True,
        )
        now = datetime.now(timezone.utc)
        if isinstance(social_posts, list):
            for text in social_posts[:20]:
                events.append(
                    normalize_signal_event(
                        source="reddit",
                        location=location,
                        topic=topic,
                        text=text,
                        occurred_at=now,
                        engagement=1.5,
                        confidence=0.62,
                    )
                )
        if isinstance(weather, dict):
            weather_text = f"weather {weather.get('condition','unknown')} temp {weather.get('temp_c', 0)}C"
            events.append(
                normalize_signal_event(
                    source="weather",
                    location=location,
                    topic=topic,
                    text=weather_text,
                    occurred_at=now,
                    engagement=0.5,
                    confidence=0.8,
                )
            )
        if isinstance(nearby_events, list):
            for ev in nearby_events[:6]:
                desc = f"{ev.get('name','event')} at {ev.get('venue','venue')} genre {ev.get('genre','')}"
                events.append(
                    normalize_signal_event(
                        source="ticketmaster",
                        location=location,
                        topic=topic,
                        text=desc,
                        occurred_at=now,
                        engagement=2.0,
                        confidence=0.75,
                    )
                )
    if events:
        await ingest_events(events)


async def run_city_pulse_loop():
    """Score all districts on an interval and push to WebSocket subscribers."""
    while True:
        try:
            await _ingest_free_signals()
            scored = await score_all_districts()
            payload = format_many(scored)
            await manager.broadcast_json({"type": "districts_update", "data": payload})
        except Exception as e:
            logger.exception("City Pulse scoring loop failed: %s", e)
        await asyncio.sleep(settings.update_interval_seconds)
