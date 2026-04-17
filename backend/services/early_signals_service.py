from __future__ import annotations

import time
from datetime import datetime, timezone

import httpx

from backend.config import settings
from backend.services.provider_resilience import mark_cache_hit, mark_stale_served, with_resilience

_CACHE: dict[str, dict] = {}
_CACHE_MAX = 256  # max unique location keys retained in memory


def _cache_get(key: str, ttl: int) -> dict | None:
    item = _CACHE.get(key)
    if not item:
        return None
    if time.time() - item.get("ts", 0) <= ttl:
        return item.get("data")
    return None


def _cache_set(key: str, data: dict) -> None:
    # Evict oldest entries when the cache is full
    if len(_CACHE) >= _CACHE_MAX:
        oldest_key = min(_CACHE, key=lambda k: _CACHE[k].get("ts", 0))
        del _CACHE[oldest_key]
    _CACHE[key] = {"ts": time.time(), "data": data}


async def _fetch_firms(lat: float, lon: float) -> dict:
    """
    NASA FIRMS adapter (best-effort): use recent wildfire proxy feeds.
    If source unavailable, degrade gracefully.
    """
    async def _call():
        # Public FIRMS area endpoint can be rate-limited/format-sensitive; keep safe fallback behavior.
        # 5-day MODIS around a small bbox.
        delta = 0.5
        bbox = f"{lon-delta},{lat-delta},{lon+delta},{lat+delta}"
        url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/no-key/MODIS_NRT/{bbox}/5"
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                raise RuntimeError(f"firms_http_{r.status_code}")
            lines = [ln for ln in (r.text or "").splitlines() if ln.strip()]
            # header + rows
            count = max(0, len(lines) - 1)
            return {"wildfire_hotspots": count}

    out = await with_resilience("nasa_firms", _call)
    if not isinstance(out, dict):
        return {"wildfire_hotspots": 0, "status": "unavailable"}
    hotspots = int(out.get("wildfire_hotspots", 0))
    return {
        "wildfire_hotspots": hotspots,
        "severity": "high" if hotspots >= 10 else "medium" if hotspots >= 3 else "low",
        "status": "ok",
    }


async def _fetch_trends(location_name: str) -> dict:
    """
    Google Trends proxy via dailytrends RSS (best-effort).
    """
    q = (location_name or "").strip() or "city"
    async def _call():
        url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US"
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                raise RuntimeError(f"trends_http_{r.status_code}")
            text = (r.text or "").lower()
            mentions = text.count(q.lower())
            return {"trend_mentions": mentions}

    out = await with_resilience("google_trends", _call)
    if not isinstance(out, dict):
        return {"trend_mentions": 0, "status": "unavailable"}
    mentions = int(out.get("trend_mentions", 0))
    return {
        "trend_mentions": mentions,
        "severity": "high" if mentions >= 8 else "medium" if mentions >= 3 else "low",
        "status": "ok",
    }


async def _fetch_comtrade(country_code: str) -> dict:
    """
    UN Comtrade adapter (country-level momentum proxy).
    """
    cc = (country_code or "").upper()
    if not cc:
        return {"trade_anomaly_score": None, "status": "no_country"}

    async def _call():
        # Lightweight endpoint; this can be sparse depending on reporter availability.
        url = f"https://comtradeapi.worldbank.org/data/v1/get/C/A/HS?reporter={cc}&partner=0&flow=2&format=json&count=5"
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
            if r.status_code != 200:
                raise RuntimeError(f"comtrade_http_{r.status_code}")
            data = r.json() if "json" in (r.headers.get("content-type", "")) else {}
            rows = data.get("data") or []
            values = [float(x.get("primaryValue") or 0) for x in rows[:5] if x.get("primaryValue") is not None]
            if not values:
                return {"score": 0.0}
            avg = sum(values) / len(values)
            max_v = max(values) if values else 1.0
            score = 0.0 if max_v <= 0 else min(1.0, max(0.0, abs(max_v - avg) / max_v))
            return {"score": round(score, 4)}

    out = await with_resilience("un_comtrade", _call)
    if not isinstance(out, dict):
        return {"trade_anomaly_score": None, "status": "unavailable"}
    score = float(out.get("score", 0.0))
    return {
        "trade_anomaly_score": score,
        "severity": "high" if score >= 0.6 else "medium" if score >= 0.3 else "low",
        "status": "ok",
    }


async def fetch_early_signals(
    *,
    location_name: str,
    country_code: str,
    lat: float,
    lon: float,
) -> dict:
    key = f"{(location_name or '').lower()}::{(country_code or '').upper()}::{round(lat,2)}::{round(lon,2)}"
    ttl = max(60, settings.provider_default_cache_ttl_seconds)
    stale_ttl = ttl * 6
    cached = _CACHE.get(key)
    fresh = _cache_get(key, ttl)
    if fresh:
        await mark_cache_hit("early_signals")
        return fresh

    async def _disabled() -> dict:
        return {"status": "disabled"}

    import asyncio
    firms, trends, comtrade = await asyncio.gather(
        _fetch_firms(lat, lon)       if settings.signals_enable_firms     else _disabled(),
        _fetch_trends(location_name) if settings.signals_enable_trends    else _disabled(),
        _fetch_comtrade(country_code) if settings.signals_enable_comtrade else _disabled(),
        return_exceptions=True,
    )
    out = {
        "firms": firms if isinstance(firms, dict) else {"status": "error"},
        "trends": trends if isinstance(trends, dict) else {"status": "error"},
        "comtrade": comtrade if isinstance(comtrade, dict) else {"status": "error"},
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    healthy = any(isinstance(v, dict) and v.get("status") == "ok" for v in [out["firms"], out["trends"], out["comtrade"]])
    if healthy:
        _cache_set(key, out)
        return out
    if cached and time.time() - cached.get("ts", 0) <= stale_ttl:
        await mark_stale_served("early_signals")
        return cached.get("data", out)
    return out
