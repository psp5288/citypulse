import asyncio

from backend.services import weather_service


class _Resp:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self._responses = list(responses)

    async def get(self, *_args, **_kwargs):
        return self._responses.pop(0)


def test_fetch_from_provider_retries_429_then_succeeds(monkeypatch):
    payload = {
        "current": {
            "temperature_2m": 21,
            "apparent_temperature": 20,
            "relative_humidity_2m": 48,
            "wind_speed_10m": 4,
            "precipitation": 0,
            "weather_code": 0,
        },
        "hourly": {
            "temperature_2m": [21, 22, 23, 24],
            "precipitation_probability": [0, 10, 20, 30],
            "precipitation": [0, 0.1, 0.2, 0.3],
            "weather_code": [0, 1, 2, 3],
        },
    }
    client = _Client([_Resp(429), _Resp(200, payload)])

    async def _client():
        return client

    async def _noop():
        return

    monkeypatch.setattr(weather_service, "_get_client", _client)
    monkeypatch.setattr(weather_service, "_enforce_request_pacing", _noop)
    monkeypatch.setattr(weather_service.settings, "weather_retry_attempts", 2)
    monkeypatch.setattr(weather_service.settings, "weather_backoff_base_ms", 1)

    result = asyncio.run(weather_service._fetch_from_provider(41.88, -87.63))
    assert isinstance(result, dict)
    assert result["temp_c"] == 21
    assert result["condition"] == "clear sky"


def test_fetch_weather_uses_cache_before_provider(monkeypatch):
    cached = {"condition": "overcast", "temp_c": 12}

    async def _cached(_key):
        return cached

    async def _provider(_lat, _lon):
        raise AssertionError("Provider should not be called on cache hit")

    monkeypatch.setattr(weather_service, "_read_cache", _cached)
    monkeypatch.setattr(weather_service, "_fetch_from_provider", _provider)

    result = asyncio.run(weather_service.fetch_weather(10.0, 20.0))
    assert result == cached


def test_fetch_weather_uses_stale_when_circuit_open(monkeypatch):
    stale = {"condition": "stale", "temp_c": 15}

    async def _fresh(_key):
        return None

    async def _is_open():
        return True

    async def _stale(_lat, _lon):
        return stale

    def _never_mock():
        raise AssertionError("Mock should not be used when stale is available")

    monkeypatch.setattr(weather_service, "_read_cache", _fresh)
    monkeypatch.setattr(weather_service, "_circuit_is_open", _is_open)
    monkeypatch.setattr(weather_service, "_read_stale_cache", _stale)
    monkeypatch.setattr(weather_service, "_mock_weather", _never_mock)

    result = asyncio.run(weather_service.fetch_weather(1.0, 2.0))
    assert result == stale


def test_provider_health_snapshot_shape():
    snapshot = asyncio.run(weather_service.get_provider_health_snapshot())
    assert "provider" in snapshot
    assert "circuit" in snapshot
    assert "metrics" in snapshot
