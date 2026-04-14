"""
/api/location/intel — on-demand global location intelligence.

Query params:
  lat:   float  (required, -90..90)
  lon:   float  (required, -180..180)
  name:  str    (optional hint — also reverse-geocoded to confirm)
  force: bool   (skip Redis cache)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from backend.services import gdelt_service, google_news_service, weather_service, reddit_service, finance_service
from backend.services.watsonx_service import score_district

router = APIRouter(prefix="/api/location", tags=["location"])
logger = logging.getLogger(__name__)

CACHE_TTL = 600  # 10 minutes


def _cache_key(lat: float, lon: float) -> str:
    key = f"{round(lat, 2)}_{round(lon, 2)}"
    return f"loc_intel:{hashlib.md5(key.encode()).hexdigest()[:12]}"


@router.get("/intel")
async def get_location_intel(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    name: str = Query(None),
    force: bool = Query(False),
) -> dict:
    """Return unified live intelligence for any lat/lon on Earth."""

    # ── Redis cache check ────────────────────────────────────────────────────
    redis = None
    try:
        from backend.services.redis_service import get_redis
        redis = get_redis()
    except Exception:
        pass  # Redis unavailable — proceed without cache

    cache_key = _cache_key(lat, lon)
    if not force and redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                return data
        except Exception:
            pass

    # ── 1. Reverse geocode → authoritative location metadata ─────────────────
    location_meta = await _resolve_location(lat, lon, name)

    # ── 2. Parallel fetch: weather + news (Google+GDELT) + Reddit + finance ──
    import asyncio

    cc = location_meta.get("country_code") or None
    short_name = location_meta["short_name"]
    country_name = location_meta.get("country", "")

    weather_task = weather_service.fetch_weather(lat, lon)

    # Google News RSS — real-time, locale-aware
    gnews_task = google_news_service.fetch_location_news(
        location_name=name or short_name,
        country_code=cc,
        max_articles=15,
    )
    # GDELT — broader historical signals
    gdelt_task = gdelt_service.fetch_location_news(
        location_name=name or short_name,
        country_code=cc,
        max_records=10,
    )
    posts_task = reddit_service.fetch_posts_for_location(
        location_name=short_name,
        max_posts=25,
    )
    finance_task = finance_service.fetch_country_finance(
        country_code=cc or "",
        country_name=country_name,
    )

    weather, gnews, gdelt_news, posts, finance = await asyncio.gather(
        weather_task, gnews_task, gdelt_task, posts_task, finance_task,
        return_exceptions=True,
    )
    if isinstance(weather, Exception):
        logger.warning("Weather fetch error: %s", weather)
        weather = {}
    if isinstance(gnews, Exception):
        logger.warning("Google News error: %s", gnews)
        gnews = []
    if isinstance(gdelt_news, Exception):
        logger.warning("GDELT fetch error: %s", gdelt_news)
        gdelt_news = []
    if isinstance(posts, Exception):
        logger.warning("Reddit fetch error: %s", posts)
        posts = []
    if isinstance(finance, Exception):
        logger.warning("Finance fetch error: %s", finance)
        finance = {}

    # Merge news: Google News first (real-time), then GDELT (de-duped by title)
    seen_titles: set[str] = set()
    news: list[dict] = []
    for article in list(gnews) + list(gdelt_news):
        key = (article.get("title") or "")[:60].lower()
        if key and key not in seen_titles:
            seen_titles.add(key)
            news.append(article)

    # ── 3. WatsonX AI scoring ────────────────────────────────────────────────
    context = {
        "district_name": short_name,
        "social_posts": posts if isinstance(posts, list) else [],
        "weather": weather if isinstance(weather, dict) else {},
        "events": [],
        "traffic": {},
    }
    try:
        ai_scores = await score_district(short_name.lower(), context)
    except Exception as e:
        logger.warning("WatsonX scoring error: %s", e)
        ai_scores = {
            "crowd_density": 0.5,
            "sentiment_score": 0.5,
            "safety_risk": 0.3,
            "weather_impact": 0.2,
            "confidence": 0.1,
            "summary": "AI scoring unavailable",
            "flags": [],
        }

    # ── 4. Derive live insights ──────────────────────────────────────────────
    insights = _derive_insights(
        weather if isinstance(weather, dict) else {},
        news,
        ai_scores,
        finance if isinstance(finance, dict) else None,
    )

    result = {
        "location": location_meta,
        "weather": weather if isinstance(weather, dict) else {},
        "news": news,
        "finance": finance if isinstance(finance, dict) else {},
        "ai_scores": ai_scores,
        "insights": insights,
        "cached": False,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    # ── 5. Cache in Redis ────────────────────────────────────────────────────
    if redis:
        try:
            await redis.setex(cache_key, CACHE_TTL, json.dumps(result, default=str))
        except Exception:
            pass

    return result


async def _resolve_location(lat: float, lon: float, name_hint: str | None) -> dict:
    """Nominatim reverse geocode with fallback to name_hint."""
    import httpx

    NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
    UA = "CityPulse/1.0 (https://github.com/citypulse; geocoding proxy)"
    try:
        params = {
            "format": "jsonv2",
            "lat": str(lat),
            "lon": str(lon),
            "zoom": "10",
            "addressdetails": "1",
            "accept-language": "en",
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(
                NOMINATIM_REVERSE,
                params=params,
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
        if r.status_code == 200:
            data = r.json()
            addr = data.get("address") or {}
            short = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("county")
                or name_hint
                or "Location"
            )
            country = addr.get("country", "")
            cc = (addr.get("country_code") or "").upper()
            display = data.get("display_name") or short
            return {
                "name": display,
                "short_name": short,
                "country": country,
                "country_code": cc,
                "lat": lat,
                "lon": lon,
                "timezone": "",
            }
    except Exception as e:
        logger.debug("Nominatim reverse geocode failed: %s", e)

    fallback_name = name_hint or f"{lat:.4f},{lon:.4f}"
    return {
        "name": fallback_name,
        "short_name": name_hint or "Location",
        "country": "",
        "country_code": "",
        "lat": lat,
        "lon": lon,
        "timezone": "",
    }


def _derive_insights(weather: dict, news: list[dict], scores: dict, finance: dict | None = None) -> list[dict]:
    insights: list[dict] = []

    # Weather alerts — weather_service returns flat keys: rain_mm, wind_ms
    precip = weather.get("rain_mm", 0) or 0
    wind_ms = weather.get("wind_ms", 0) or 0
    wind = wind_ms * 3.6  # convert m/s → km/h for threshold comparison
    if precip > 10:
        insights.append({"type": "weather", "text": f"Heavy rain: {precip:.1f}mm in last hour", "severity": "high"})
    elif precip > 3:
        insights.append({"type": "weather", "text": f"Light rain: {precip:.1f}mm", "severity": "low"})
    if wind > 50:  # >50 km/h
        insights.append({"type": "weather", "text": f"High winds: {wind:.0f} km/h ({wind_ms:.1f} m/s)", "severity": "medium"})

    # News tone analysis
    neg_news = [n for n in news if n.get("sentiment") == "negative"]
    pos_news = [n for n in news if n.get("sentiment") == "positive"]
    if len(neg_news) >= 5:
        insights.append({"type": "news", "text": f"{len(neg_news)} negative news signals in last 24h", "severity": "high"})
    elif len(neg_news) >= 2:
        insights.append({"type": "news", "text": f"{len(neg_news)} concerning articles detected", "severity": "medium"})
    if len(pos_news) >= 4:
        insights.append({"type": "news", "text": f"{len(pos_news)} positive stories trending", "severity": "low"})

    # Finance signals
    if finance:
        idx = finance.get("index") or {}
        chg = idx.get("change_pct")
        if chg is not None:
            if chg <= -2:
                insights.append({"type": "finance", "text": f"{idx.get('name','Index')} down {abs(chg):.1f}% today", "severity": "high"})
            elif chg >= 2:
                insights.append({"type": "finance", "text": f"{idx.get('name','Index')} up {chg:.1f}% today", "severity": "low"})
        macro = finance.get("macro") or {}
        infl = macro.get("inflation_pct")
        if infl and infl > 8:
            insights.append({"type": "finance", "text": f"High inflation: {infl:.1f}% (World Bank {macro.get('year','')})", "severity": "high"})

    # AI risk flags
    for flag in (scores.get("flags") or []):
        insights.append({"type": "risk", "text": flag.replace("_", " ").title(), "severity": "medium"})
    if (scores.get("safety_risk") or 0) > 0.7:
        insights.append({"type": "risk", "text": "Elevated safety risk in area", "severity": "high"})

    return insights[:8]
