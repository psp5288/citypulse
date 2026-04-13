import asyncio
import re
import logging
from datetime import datetime

from backend.config import settings
from backend.core.zones import ZONES
from backend.services.watsonx_service import score_zone
from backend.services.redis_service import set_zone_score
from backend.core.models import ZoneScore

logger = logging.getLogger(__name__)


# ── Text preprocessing ────────────────────────────────────────────────────────

def clean_post(text: str) -> str:
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'@\w+', '', text)
    text = re.sub(r'u/\w+', '', text)
    text = re.sub(r'[^\w\s\.\!\?\,\-]', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:280]


def preprocess_posts(posts: list[str]) -> list[str]:
    cleaned = [clean_post(p) for p in posts]
    return [p for p in cleaned if len(p) > 20]


# ── Reddit fetching ───────────────────────────────────────────────────────────

def _get_reddit():
    try:
        import praw
        if not settings.reddit_client_id:
            return None
        return praw.Reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
        )
    except ImportError:
        logger.warning("praw not installed — Reddit fetching disabled")
        return None


async def fetch_reddit_posts(subreddits: list[str], limit: int = 25) -> list[str]:
    """Fetch recent post titles from a list of subreddits."""
    posts = []
    try:
        reddit = _get_reddit()
        if not reddit:
            return _mock_posts(subreddits[0] if subreddits else "nyc")

        loop = asyncio.get_event_loop()
        for sub in subreddits:
            try:
                subreddit = await loop.run_in_executor(None, lambda s=sub: reddit.subreddit(s))
                hot = await loop.run_in_executor(None, lambda sr=subreddit: list(sr.hot(limit=limit)))
                posts.extend([p.title for p in hot if p.score > 0])
            except Exception as e:
                logger.warning(f"Reddit fetch failed for r/{sub}: {e}")
    except Exception as e:
        logger.warning(f"Reddit client error: {e}")
        return _mock_posts(subreddits[0] if subreddits else "nyc")

    return preprocess_posts(posts) if posts else _mock_posts(subreddits[0] if subreddits else "nyc")


# ── RSS fetching ──────────────────────────────────────────────────────────────

async def fetch_news_feed(rss_url: str) -> list[str]:
    """Fetch recent headlines from an RSS feed."""
    try:
        import feedparser
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, lambda: feedparser.parse(rss_url))
        headlines = [entry.title for entry in feed.entries[:15]]
        return preprocess_posts(headlines)
    except ImportError:
        logger.warning("feedparser not installed — RSS fetching disabled")
        return _mock_headlines()
    except Exception as e:
        logger.warning(f"RSS fetch failed for {rss_url}: {e}")
        return _mock_headlines()


# ── Zone scoring loop ─────────────────────────────────────────────────────────

async def score_all_zones():
    """Score every zone and cache results. Called every 30s."""
    for zone in ZONES:
        try:
            posts = await fetch_reddit_posts(zone["subreddits"])
            news = await fetch_news_feed(zone["rss_feed"])
            scores = await score_zone(zone["id"], zone["name"], posts, news)
            if scores:
                zone_score = ZoneScore(
                    zone_id=zone["id"],
                    zone_name=zone["name"],
                    city=zone["city"],
                    lat=zone["lat"],
                    lng=zone["lng"],
                    post_count=len(posts),
                    scored_at=datetime.utcnow(),
                    **scores,
                )
                await set_zone_score(zone["id"], zone_score)
                logger.info(f"Scored zone {zone['id']}: sentiment={scores['sentiment_score']:.2f}")
        except Exception as e:
            logger.error(f"Zone scoring failed for {zone['id']}: {e}")


async def start_ingestion_loop():
    """Runs forever. Scores all zones every 30 seconds."""
    logger.info("Starting social ingestion loop")
    while True:
        await score_all_zones()
        await asyncio.sleep(settings.update_interval_seconds)


# ── Mock data (used when Reddit/RSS credentials not set) ─────────────────────

_MOCK_POSTS = {
    "nyc": [
        "Subway delays again on the A line this morning",
        "Massive crowds at Central Park for the weekend festival",
        "Local businesses report surge in foot traffic downtown",
        "Police presence increased near Times Square",
        "Community board meeting draws large turnout over housing proposals",
        "New restaurant opening causes buzz in the neighbourhood",
        "Traffic congestion on FDR Drive backing up significantly",
        "Protesters gather near City Hall over policy announcement",
    ],
    "manhattan": [
        "Midtown hotel prices spike as conference season kicks off",
        "Financial district sees early morning commuter crowds",
        "Construction noise complaints flood local social media",
    ],
    "brooklyn": [
        "Williamsburg market sees record weekend foot traffic",
        "Gentrification debate heats up on local forums",
        "New bike lane opens along Atlantic Avenue",
    ],
}


def _mock_posts(subreddit: str) -> list[str]:
    base = _MOCK_POSTS.get(subreddit, _MOCK_POSTS["nyc"])
    return base


def _mock_headlines() -> list[str]:
    return [
        "City council votes on new urban development plan",
        "Transit authority announces service changes for next month",
        "Local economy shows mixed signals in latest report",
        "Community groups call for increased police presence in key areas",
        "New housing developments break ground across five boroughs",
    ]
