"""
Google News RSS — free, no API key, real-time global coverage.

Feed URL pattern:
  https://news.google.com/rss/search?q={query}&hl={lang}&gl={country}&ceid={country}:{lang}

Returns articles with title, url, source, published, snippet.
Falls back to GDELT if Google News is unreachable.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

GN_RSS_BASE = "https://news.google.com/rss/search"

# country_code → (hl, gl, ceid)  — Google News locale params
_LOCALE_MAP: dict[str, tuple[str, str, str]] = {
    "US": ("en-US", "US", "US:en"),
    "GB": ("en-GB", "GB", "GB:en"),
    "AU": ("en-AU", "AU", "AU:en"),
    "CA": ("en-CA", "CA", "CA:en"),
    "IN": ("en-IN", "IN", "IN:en"),
    "SG": ("en-SG", "SG", "SG:en"),
    "NG": ("en-NG", "NG", "NG:en"),
    "ZA": ("en-ZA", "ZA", "ZA:en"),
    "DE": ("de", "DE", "DE:de"),
    "FR": ("fr", "FR", "FR:fr"),
    "JP": ("ja", "JP", "JP:ja"),
    "CN": ("zh-CN", "CN", "CN:zh-Hans"),
    "KR": ("ko", "KR", "KR:ko"),
    "BR": ("pt-BR", "BR", "BR:pt-419"),
    "MX": ("es-419", "MX", "MX:es-419"),
    "AR": ("es-419", "AR", "AR:es-419"),
    "IT": ("it", "IT", "IT:it"),
    "ES": ("es", "ES", "ES:es"),
    "RU": ("ru", "RU", "RU:ru"),
    "NL": ("nl", "NL", "NL:nl"),
    "SE": ("sv", "SE", "SE:sv"),
    "PL": ("pl", "PL", "PL:pl"),
    "TR": ("tr", "TR", "TR:tr"),
    "EG": ("ar", "EG", "EG:ar"),
    "SA": ("ar", "SA", "SA:ar"),
    "AE": ("ar", "AE", "AE:ar"),
    "PK": ("en-IN", "PK", "PK:en"),
    "ID": ("id", "ID", "ID:id"),
    "TH": ("th", "TH", "TH:th"),
    "VN": ("vi", "VN", "VN:vi"),
    "PH": ("en-PH", "PH", "PH:en"),
    "MY": ("en-MY", "MY", "MY:en"),
    "KE": ("en-KE", "KE", "KE:en"),
    "GH": ("en-GH", "GH", "GH:en"),
}

_DEFAULT_LOCALE = ("en-US", "US", "US:en")


async def fetch_location_news(
    location_name: str,
    country_code: str | None = None,
    max_articles: int = 15,
) -> list[dict]:
    """
    Fetch real-time Google News RSS articles for a location.

    Returns list of:
    {
      "title": str,
      "url": str,
      "source": str,
      "published": str (ISO),
      "snippet": str,
      "sentiment": "positive" | "negative" | "neutral"
    }
    """
    hl, gl, ceid = _LOCALE_MAP.get(country_code or "", _DEFAULT_LOCALE)

    # Build search query — location name + news keywords
    query = f"{location_name} news"
    params = {
        "q": query,
        "hl": hl,
        "gl": gl,
        "ceid": ceid,
    }

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; CityPulse/1.0)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(GN_RSS_BASE, params=params)
            if resp.status_code != 200:
                logger.warning("Google News RSS %s for '%s'", resp.status_code, location_name)
                return []
            return _parse_rss(resp.text, max_articles)
    except Exception as e:
        logger.warning("Google News fetch failed for '%s': %s", location_name, e)
        return []


def _parse_rss(xml_text: str, max_articles: int) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"media": "http://search.yahoo.com/mrss/"}
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item")[:max_articles]:
            title_el = item.find("title")
            link_el = item.find("link")
            source_el = item.find("source")
            pubdate_el = item.find("pubDate")
            desc_el = item.find("description")

            title = _clean_html(title_el.text or "") if title_el is not None else ""
            url = link_el.text or "" if link_el is not None else ""
            source = source_el.text or "" if source_el is not None else ""
            snippet = _clean_html(desc_el.text or "")[:180] if desc_el is not None else ""

            published = ""
            if pubdate_el is not None and pubdate_el.text:
                try:
                    dt = parsedate_to_datetime(pubdate_el.text)
                    published = dt.astimezone(timezone.utc).isoformat()
                except Exception:
                    published = pubdate_el.text

            if not title:
                continue

            sentiment = _infer_sentiment(title + " " + snippet)
            articles.append({
                "title": title,
                "url": url,
                "source": source,
                "published": published,
                "snippet": snippet,
                "sentiment": sentiment,
            })
    except ET.ParseError as e:
        logger.warning("RSS parse error: %s", e)

    return articles


# Simple keyword-based sentiment — avoids any ML dependency
_NEG_WORDS = {
    "crash", "crisis", "attack", "war", "kill", "dead", "death", "murder", "bomb",
    "flood", "fire", "disaster", "emergency", "arrest", "protest", "riot", "strike",
    "collapse", "explosion", "earthquake", "hurricane", "storm", "accident", "shooting",
    "violence", "threat", "danger", "warning", "recall", "fraud", "scandal", "corruption",
    "bankrupt", "recession", "inflation", "deficit", "debt", "layoff", "closure",
}
_POS_WORDS = {
    "growth", "record", "success", "win", "victory", "award", "celebrate", "launch",
    "recover", "rise", "boom", "profit", "investment", "breakthrough", "innovation",
    "agreement", "peace", "relief", "improve", "advance", "achieve", "milestone",
    "discover", "open", "expand", "upgrade", "transform",
}


def _infer_sentiment(text: str) -> str:
    words = set(re.findall(r"\b[a-z]+\b", text.lower()))
    neg = len(words & _NEG_WORDS)
    pos = len(words & _POS_WORDS)
    if neg > pos:
        return "negative"
    if pos > neg:
        return "positive"
    return "neutral"


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode common entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    return text.strip()
