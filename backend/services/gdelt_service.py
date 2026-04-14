"""
GDELT 2.0 DOC API — free, no key required, ~15-min update cycle.

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
  ?query=<location+keywords>&mode=artlist&maxrecords=25
  &format=json&timespan=1440min  (last 24h)

Returns articles with: url, title, seendate, sourcecountry, tone, domain
tone: composite sentiment float (negative = alarming, positive = good)
"""

import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

GDELT_BASE = "https://api.gdeltproject.org/api/v2/doc/doc"


async def fetch_location_news(
    location_name: str,
    country_code: str | None = None,
    max_records: int = 20,
    timespan_hours: int = 24,
) -> list[dict]:
    """
    Fetch recent news articles mentioning location_name from GDELT.

    Returns list of:
    {
      "title": str,
      "url": str,
      "source": str,
      "published": str (ISO datetime or GDELT seendate),
      "tone": float,           # negative = alarming, positive = good
      "sentiment": "positive" | "negative" | "neutral",
      "domain": str
    }
    """
    query_str = f'"{location_name}" sourcelang:english'
    params = {
        "query": query_str,
        "mode": "artlist",
        "maxrecords": max_records,
        "format": "json",
        "timespan": f"{timespan_hours * 60}min",
        "sort": "DateDesc",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(GDELT_BASE, params=params)
            if resp.status_code != 200:
                logger.warning("GDELT returned %s for '%s'", resp.status_code, location_name)
                return []
            data = resp.json()
    except Exception as e:
        logger.warning("GDELT fetch failed for '%s': %s", location_name, e)
        return []

    articles = data.get("articles") or []
    return [_normalise_article(a) for a in articles if a.get("title")]


def _normalise_article(a: dict) -> dict:
    tone = float(a.get("tone") or 0)
    if tone < -2:
        sentiment = "negative"
    elif tone > 2:
        sentiment = "positive"
    else:
        sentiment = "neutral"

    # GDELT seendate format: "20240413T120000Z" → convert to ISO
    raw_date = a.get("seendate", "")
    published = _parse_gdelt_date(raw_date)

    return {
        "title": (a.get("title") or "").strip(),
        "url": a.get("url", ""),
        "source": a.get("domain", ""),
        "published": published,
        "tone": round(tone, 2),
        "sentiment": sentiment,
        "domain": a.get("domain", ""),
    }


def _parse_gdelt_date(raw: str) -> str:
    """Convert GDELT date format 20240413T120000Z to ISO 2024-04-13T12:00:00Z."""
    if not raw or len(raw) < 8:
        return raw
    try:
        # Format: YYYYMMDDTHHMMSSZ
        date_part = raw[:8]
        time_part = raw[9:15] if len(raw) >= 15 else "000000"
        return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}T{time_part[:2]}:{time_part[2:4]}:{time_part[4:6]}Z"
    except Exception:
        return raw
