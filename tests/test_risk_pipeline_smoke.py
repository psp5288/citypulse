import pytest

from backend.services import predictor_service


@pytest.mark.asyncio
async def test_smoke_compute_and_guarded_metadata(monkeypatch):
    async def _events(_district, _topic, lookback_hours=1):
        if lookback_hours <= 3:
            return [{"sentiment": -0.5, "occurred_at": "2026-01-01T00:00:00+00:00"}] * 10
        return [{"sentiment": -0.4, "occurred_at": "2026-01-01T00:00:00+00:00"}] * 20

    async def _rolling(*_args, **_kwargs):
        return 2.0

    async def _latest(*_args, **_kwargs):
        return {"risk_score": 0.2, "alert_tier": "NOMINAL", "predicted_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)}

    async def _weather(*_args, **_kwargs):
        return {"temp_c": 20, "rain_mm": 0, "wind_ms": 2}

    async def _events_live(*_args, **_kwargs):
        return []

    monkeypatch.setattr("backend.services.postgres_service.fetch_recent_iris_events", _events)
    monkeypatch.setattr("backend.services.postgres_service.fetch_rolling_signal_avg", _rolling)
    monkeypatch.setattr("backend.services.postgres_service.get_latest_risk_prediction_row", _latest)
    monkeypatch.setattr("backend.services.weather_service.fetch_weather", _weather)
    monkeypatch.setattr("backend.services.ticketmaster_service.fetch_events", _events_live)

    score = await predictor_service.compute_risk_score("downtown", persist=False)
    assert 0.0 <= score.risk_score <= 1.0
    assert score.feature_schema_hash
    assert isinstance(score.weight_profile, dict)
