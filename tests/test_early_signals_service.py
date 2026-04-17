from __future__ import annotations

import asyncio

from backend.services import early_signals_service as es


def test_fetch_early_signals_graceful(monkeypatch):
    async def fake_firms(lat, lon):
        return {"wildfire_hotspots": 4, "severity": "medium", "status": "ok"}

    async def fake_trends(name):
        return {"trend_mentions": 6, "severity": "medium", "status": "ok"}

    async def fake_comtrade(cc):
        return {"trade_anomaly_score": 0.5, "severity": "medium", "status": "ok"}

    monkeypatch.setattr(es, "_fetch_firms", fake_firms)
    monkeypatch.setattr(es, "_fetch_trends", fake_trends)
    monkeypatch.setattr(es, "_fetch_comtrade", fake_comtrade)

    out = asyncio.run(es.fetch_early_signals(location_name="Paris", country_code="FR", lat=48.85, lon=2.35))
    assert out["firms"]["status"] == "ok"
    assert out["trends"]["trend_mentions"] == 6
    assert out["comtrade"]["trade_anomaly_score"] == 0.5
