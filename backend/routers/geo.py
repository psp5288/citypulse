"""Proxy geocoding (Nominatim) with caching — mirrors WorldMonitor-style reverse/search, server-side User-Agent."""

from __future__ import annotations

import time
from typing import Any

import httpx
from fastapi import APIRouter, Query

router = APIRouter()

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"
UA = "CityPulse/1.0 (https://github.com/citypulse; geocoding proxy)"

_f_cache: dict[str, tuple[float, Any]] = {}
_r_cache: dict[str, tuple[float, Any]] = {}
TTL_SEARCH = 900.0
TTL_REVERSE = 3600.0


def _get_cached(table: dict[str, tuple[float, Any]], key: str, ttl: float) -> Any | None:
    row = table.get(key)
    if not row:
        return None
    exp, val = row
    if time.time() > exp:
        del table[key]
        return None
    return val


def _set_cached(table: dict[str, tuple[float, Any]], key: str, val: Any, ttl: float) -> None:
    table[key] = (time.time() + ttl, val)


@router.get("/geo/search")
async def geo_search(
    q: str = Query(..., min_length=1, max_length=256),
    limit: int = Query(5, ge=1, le=10),
) -> dict[str, Any]:
    qn = q.strip()
    cache_key = f"s:{qn.lower()}:{limit}"
    hit = _get_cached(_f_cache, cache_key, TTL_SEARCH)
    if hit is not None:
        return hit

    params = {
        "format": "jsonv2",
        "q": qn,
        "limit": str(limit),
        "dedupe": "1",
        "addressdetails": "1",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            NOMINATIM_SEARCH,
            params=params,
            headers={"User-Agent": UA, "Accept": "application/json", "Accept-Language": "en"},
        )
    if r.status_code != 200:
        out: dict[str, Any] = {"places": [], "error": f"nominatim_http_{r.status_code}"}
        _set_cached(_f_cache, cache_key, out, 60.0)
        return out

    rows = r.json()
    places = []
    for item in rows if isinstance(rows, list) else []:
        try:
            lat = float(item.get("lat"))
            lon = float(item.get("lon"))
        except (TypeError, ValueError):
            continue
        places.append(
            {
                "label": item.get("display_name") or qn,
                "lat": lat,
                "lon": lon,
            }
        )
    out = {"places": places}
    _set_cached(_f_cache, cache_key, out, TTL_SEARCH)
    return out


@router.get("/geo/weather")
async def geo_weather(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict:
    """Proxy Open-Meteo weather for a lat/lon — no API key required."""
    from backend.services.weather_service import fetch_weather
    return await fetch_weather(lat, lon)


@router.get("/geo/reverse")
async def geo_reverse(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    cache_key = f"r:{lat:.4f},{lon:.4f}"
    hit = _get_cached(_r_cache, cache_key, TTL_REVERSE)
    if hit is not None:
        return hit

    params = {
        "format": "jsonv2",
        "lat": str(lat),
        "lon": str(lon),
        "zoom": "10",
        "addressdetails": "1",
        "accept-language": "en",
    }
    async with httpx.AsyncClient(timeout=12.0) as client:
        r = await client.get(
            NOMINATIM_REVERSE,
            params=params,
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
    if r.status_code != 200:
        out = {"ok": False, "label": None, "lat": lat, "lon": lon}
        _set_cached(_r_cache, cache_key, out, 120.0)
        return out

    data = r.json()
    if not isinstance(data, dict) or data.get("error"):
        out = {"ok": False, "label": None, "lat": lat, "lon": lon}
        _set_cached(_r_cache, cache_key, out, 120.0)
        return out

    disp = data.get("display_name") or ""
    addr = data.get("address") or {}
    country = addr.get("country")
    cc = (addr.get("country_code") or "").upper() if addr.get("country_code") else None
    out = {
        "ok": True,
        "label": disp or f"{lat:.4f}, {lon:.4f}",
        "display_name": disp,
        "country": country,
        "country_code": cc,
        "lat": lat,
        "lon": lon,
    }
    _set_cached(_r_cache, cache_key, out, TTL_REVERSE)
    return out
