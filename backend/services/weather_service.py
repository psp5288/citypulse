import httpx
from backend.core.logger import logger

BASE = "https://api.open-meteo.com/v1/forecast"

# WMO weather code → human-readable condition
_WMO_CODES = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current + 3h forecast from Open-Meteo (free, no API key required)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(BASE, params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
                "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
                "forecast_days": 1,
                "wind_speed_unit": "ms",
                "timezone": "auto",
            }, timeout=10)

        if r.status_code != 200:
            logger.warning(f"Open-Meteo returned {r.status_code}")
            return _mock_weather()

        data = r.json()
        current = data.get("current", {})
        hourly = data.get("hourly", {})

        condition_code = current.get("weather_code", 0)
        condition = _WMO_CODES.get(condition_code, "unknown")

        # Next 3 hourly slots
        forecast_3h = []
        for i in range(1, 4):
            try:
                h_code = hourly.get("weather_code", [])[i]
                forecast_3h.append({
                    "condition": _WMO_CODES.get(h_code, "unknown"),
                    "temp_c": hourly.get("temperature_2m", [])[i],
                    "rain_mm": hourly.get("precipitation", [])[i],
                    "pop": round(hourly.get("precipitation_probability", [])[i] / 100, 2),
                })
            except (IndexError, TypeError):
                break

        return {
            "condition": condition,
            "temp_c": current.get("temperature_2m", 0),
            "feels_like_c": current.get("apparent_temperature", 0),
            "humidity": current.get("relative_humidity_2m", 0),
            "wind_ms": current.get("wind_speed_10m", 0),
            "rain_mm": current.get("precipitation", 0),
            "forecast_3h": forecast_3h,
        }

    except Exception as e:
        logger.warning(f"Open-Meteo fetch failed: {e}")
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
            {
                "condition": random.choice(conditions),
                "temp_c": round(random.uniform(10, 30), 1),
                "rain_mm": 0,
                "pop": round(random.uniform(0, 0.5), 2),
            }
            for _ in range(3)
        ],
    }
