import httpx
from datetime import datetime, timedelta, timezone
from backend.config import settings
from backend.core.logger import logger

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"


async def fetch_events(lat: float, lon: float, radius_km: float = 2) -> list[dict]:
    if not settings.TICKETMASTER_API_KEY:
        return _mock_events()

    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=6)

    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(BASE, params={
                "apikey": settings.TICKETMASTER_API_KEY,
                "latlong": f"{lat},{lon}",
                "radius": max(1, int(radius_km)),
                "unit": "km",
                "startDateTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "endDateTime": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "size": 10,
            }, timeout=10)

        if r.status_code != 200:
            logger.warning(f"Ticketmaster returned {r.status_code}")
            return _mock_events()

        events = []
        for e in r.json().get("_embedded", {}).get("events", []):
            venue = e.get("_embedded", {}).get("venues", [{}])[0]
            events.append({
                "name": e.get("name", "Unknown Event"),
                "venue": venue.get("name", "Unknown Venue"),
                "start_time": e.get("dates", {}).get("start", {}).get("dateTime", ""),
                "attendees_estimate": e.get("pleaseNote", ""),
                "genre": e.get("classifications", [{}])[0].get("genre", {}).get("name", ""),
            })
        return events

    except Exception as e:
        logger.warning(f"Ticketmaster fetch failed: {e}")
        return _mock_events()


def _mock_events() -> list[dict]:
    import random
    venues = ["City Arena", "Harbor Amphitheater", "Arts Center", "Convention Hall", "Open Air Stage"]
    genres = ["Music", "Sports", "Comedy", "Theater", "Festival"]
    count = random.randint(0, 4)
    return [
        {
            "name": f"{random.choice(genres)} Event",
            "venue": random.choice(venues),
            "start_time": (datetime.now(timezone.utc) + timedelta(hours=random.randint(1, 5))).isoformat(),
            "attendees_estimate": str(random.randint(200, 3000)),
            "genre": random.choice(genres),
        }
        for _ in range(count)
    ]
