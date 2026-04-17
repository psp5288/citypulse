import pytest


@pytest.mark.asyncio
async def test_e2e_risk_compute_backfill_ic_flow(monkeypatch):
    from backend.services import predictor_service

    async def _events(_district, _topic, lookback_hours=1):
        return [{"sentiment": -0.2, "occurred_at": "2026-01-01T00:00:00+00:00"}] * max(3, lookback_hours)

    async def _rolling(*_args, **_kwargs):
        return 2.0

    async def _latest(*_args, **_kwargs):
        return None

    async def _weather(*_args, **_kwargs):
        return {"temp_c": 21, "rain_mm": 0, "wind_ms": 1}

    async def _tm(*_args, **_kwargs):
        return []

    async def _cfg(*_args, **_kwargs):
        return None

    monkeypatch.setattr("backend.services.postgres_service.fetch_recent_iris_events", _events)
    monkeypatch.setattr("backend.services.postgres_service.fetch_rolling_signal_avg", _rolling)
    monkeypatch.setattr("backend.services.postgres_service.get_latest_risk_prediction_row", _latest)
    monkeypatch.setattr("backend.services.postgres_service.get_active_risk_model_config", _cfg)
    monkeypatch.setattr("backend.services.weather_service.fetch_weather", _weather)
    monkeypatch.setattr("backend.services.ticketmaster_service.fetch_events", _tm)

    score = await predictor_service.compute_risk_score("downtown", persist=False)
    assert score.alert_tier in ("NOMINAL", "WATCH", "ELEVATED", "CRITICAL")
    assert 0.0 <= score.risk_score <= 1.0
