import time
import httpx
from backend.config import settings
from backend.core.logger import logger

AUTH_URL = "https://www.reddit.com/api/v1/access_token"
BASE = "https://oauth.reddit.com"

_token_cache = {"token": None, "expires_at": 0}


async def _get_token() -> str:
    if _token_cache["token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["token"]

    if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
        return ""

    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                AUTH_URL,
                data={"grant_type": "client_credentials"},
                auth=(settings.REDDIT_CLIENT_ID, settings.REDDIT_CLIENT_SECRET),
                headers={"User-Agent": "CityPulse/1.0"},
                timeout=10,
            )
            data = r.json()
            _token_cache["token"] = data["access_token"]
            _token_cache["expires_at"] = time.time() + data.get("expires_in", 3600)
        return _token_cache["token"]
    except Exception as e:
        logger.error(f"Reddit auth failed: {e}")
        return ""


async def fetch_posts(subreddits: list[str], keywords: list[str], limit: int = 25) -> list[str]:
    token = await _get_token()
    if not token:
        return _mock_posts(keywords)

    posts = []
    query = " OR ".join(keywords[:3])

    try:
        async with httpx.AsyncClient() as client:
            for sub in subreddits[:2]:
                r = await client.get(
                    f"{BASE}/r/{sub}/search.json",
                    params={"q": query, "sort": "new", "limit": limit, "restrict_sr": "true", "t": "day"},
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "CityPulse/1.0"},
                    timeout=10,
                )
                if r.status_code == 200:
                    for post in r.json().get("data", {}).get("children", []):
                        d = post["data"]
                        text = d.get("title", "") + " " + d.get("selftext", "")[:200]
                        posts.append(text.strip())
    except Exception as e:
        logger.warning(f"Reddit fetch failed: {e}")
        return _mock_posts(keywords)

    return posts[:25] if posts else _mock_posts(keywords)


def _mock_posts(keywords: list[str]) -> list[str]:
    area = keywords[0] if keywords else "the area"
    return [
        f"Beautiful day in {area} today, lots of people out walking",
        f"Traffic seems heavier than usual near {area}",
        f"Great food festival happening this weekend in {area}!",
        f"Anyone else notice more police presence in {area} lately?",
        f"The new park improvements in {area} look amazing",
        f"Parking is impossible near {area} tonight",
        f"Love the energy in {area} on Friday nights",
        f"Construction on the main road through {area} is frustrating",
    ]
