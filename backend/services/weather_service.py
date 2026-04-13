import httpx
from backend.config import settings
from backend.core.logger import logger

BASE = "https://api.openweathermap.org/data/3.0/onecall"


async def fetch_weather(lat: float, lon: float) -> dict:
    if not settings.OPENWEATHER_API_KEY:
        return _mock_weather()

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(BASE, params={
                "lat": lat, "lon": lon,
                "exclude": "minutely,daily,alerts",
                "appid": settings.OPENWEATHER_API_KEY,
                "units": "metric",
            }, timeout=10)

            if r.status_code != 200:
                logger.warning(f"OpenWeather returned {r.status_code}")
                return _mock_weather()

            data = r.json()

        current = data.get("current", {})
        hourly = data.get("hourly", [{}])[:3]

        return {
            "condition": current.get("weather", [{}])[0].get("description", "unknown"),
            "temp_c": current.get("temp", 0),
            "feels_like_c": current.get("feels_like", 0),
            "humidity": current.get("humidity", 0),
            "wind_ms": current.get("wind_speed", 0),
            "rain_mm": current.get("rain", {}).get("1h", 0),
            "forecast_3h": [
                {
                    "condition": h.get("weather", [{}])[0].get("description", ""),
                    "temp_c": h.get("temp", 0),
                    "rain_mm": h.get("rain", {}).get("1h", 0),
                    "pop": h.get("pop", 0),
                }
                for h in hourly
            ],
        }
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return _mock_weather()


def _mock_weather() -> dict:
    import random
    conditions = ["clear sky", "few clouds", "scattered clouds", "light rain", "overcast clouds"]
    return {
        "condition": random.choice(conditions),
        "temp_c": round(random.uniform(10, 30), 1),
        "feels_like_c": round(random.uniform(8, 32), 1),
        "humidity": random.randint(30, 85),
        "wind_ms": round(random.uniform(1, 12), 1),
        "rain_mm": round(random.uniform(0, 2), 1),
        "forecast_3h": [
            {"condition": random.choice(conditions), "temp_c": round(random.uniform(10, 30), 1), "rain_mm": 0, "pop": round(random.uniform(0, 0.5), 2)}
            for _ in range(3)
        ],
    }
