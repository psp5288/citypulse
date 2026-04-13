# BACKEND.md — FastAPI Backend Specification

## config.py

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # WatsonX
    watsonx_api_key: str
    watsonx_project_id: str
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_model_id: str = "ibm/granite-13b-chat-v2"

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "DevCityPulse/1.0"

    # Infrastructure
    database_url: str
    redis_url: str = "redis://localhost:6379"

    # Optional
    news_api_key: str = ""

    # App
    update_interval_seconds: int = 30
    simulation_batch_size: int = 50   # agents per WatsonX batch

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import logging

from backend.routers import zones, simulate, alerts, analytics
from backend.services.redis_service import init_redis
from backend.services.postgres_service import init_db
from backend.services.social_service import start_ingestion_loop

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_redis()
    await init_db()
    asyncio.create_task(start_ingestion_loop())   # begins 30s scoring loop
    logger.info("DevCity Pulse backend started")
    yield
    # Shutdown
    logger.info("DevCity Pulse backend shutting down")

app = FastAPI(title="DevCity Pulse API", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(zones.router, prefix="/api")
app.include_router(simulate.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")

app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
```

---

## core/models.py — All Pydantic Schemas

```python
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from enum import Enum

class Sector(str, Enum):
    banking = "banking"
    government = "government"
    news = "news"
    crisis = "crisis"
    general = "general"

class ExternalFactorType(str, Enum):
    counter_rumour = "counter_rumour"
    authority_denial = "authority_denial"
    viral_controversy = "viral_controversy"
    confirmation_leak = "confirmation_leak"

class ExternalFactor(BaseModel):
    type: ExternalFactorType
    content: str
    inject_at_minute: int = 0

class ZoneScore(BaseModel):
    zone_id: str
    zone_name: str
    city: str
    lat: float
    lng: float
    crowd_density: float        # 0.0–1.0
    sentiment_score: float      # 0.0–1.0 (1 = very positive)
    safety_risk: float          # 0.0–1.0 (1 = high risk)
    reactivity: float           # 0.0–1.0
    summary: str
    scored_at: datetime
    stale: bool = False         # True if WatsonX failed, serving cached value
    post_count: int = 0

class SimulationRequest(BaseModel):
    zone: str
    news_item: str
    sector: Sector = Sector.general
    n_agents: int = 1000
    external_factors: List[ExternalFactor] = []

class AgentResult(BaseModel):
    agent_id: int
    archetype: str
    sentiment: str              # positive / negative / neutral
    action: str                 # share / ignore / counter / amplify
    intensity: float            # 0.0–1.0
    reasoning: str

class SimulationResult(BaseModel):
    simulation_id: str
    zone: str
    news_item: str
    sector: str
    n_agents: int
    status: str                 # running / complete / failed
    predicted_sentiment: Optional[dict] = None   # {positive, negative, neutral}
    predicted_virality: Optional[float] = None
    peak_reaction_time: Optional[str] = None
    risk_of_backlash: Optional[float] = None
    confidence: Optional[float] = None
    vs_real_time: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class Alert(BaseModel):
    alert_id: str
    zone_id: str
    zone_name: str
    alert_type: str             # high_risk / sentiment_crash / crowd_spike
    message: str
    severity: str               # low / medium / high / critical
    triggered_at: datetime
    value: float
    threshold: float
```

---

## PostgreSQL Schema

```sql
-- Run on first startup via postgres_service.init_db()

CREATE TABLE IF NOT EXISTS zone_snapshots (
    id          SERIAL PRIMARY KEY,
    zone_id     VARCHAR(64) NOT NULL,
    zone_name   VARCHAR(128),
    city        VARCHAR(64),
    crowd_density   FLOAT,
    sentiment_score FLOAT,
    safety_risk     FLOAT,
    reactivity      FLOAT,
    summary         TEXT,
    post_count      INT,
    scored_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_zone_snapshots_zone_id ON zone_snapshots(zone_id);
CREATE INDEX idx_zone_snapshots_scored_at ON zone_snapshots(scored_at);

CREATE TABLE IF NOT EXISTS simulations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone            VARCHAR(64),
    news_item       TEXT,
    sector          VARCHAR(32),
    n_agents        INT,
    status          VARCHAR(16) DEFAULT 'running',
    result_json     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id         VARCHAR(64),
    zone_name       VARCHAR(128),
    alert_type      VARCHAR(64),
    message         TEXT,
    severity        VARCHAR(16),
    value           FLOAT,
    threshold_val   FLOAT,
    triggered_at    TIMESTAMPTZ DEFAULT NOW(),
    acknowledged    BOOLEAN DEFAULT FALSE
);
```

---

## services/watsonx_service.py — Key Functions

```python
import asyncio
import json
import logging
from ibm_watson_machine_learning.foundation_models import Model
from backend.config import settings
from backend.core.models import ZoneScore, AgentResult

logger = logging.getLogger(__name__)

def _get_model():
    return Model(
        model_id=settings.watsonx_model_id,
        credentials={"apikey": settings.watsonx_api_key, "url": settings.watsonx_url},
        project_id=settings.watsonx_project_id,
        params={"max_new_tokens": 512, "temperature": 0.3}
    )

async def score_zone(zone_id: str, zone_name: str, posts: list, news: list) -> dict:
    """Score a zone using WatsonX NLP. Returns raw score dict."""
    prompt = f"""You are an urban intelligence scoring system.
Analyze the following social data for the zone "{zone_name}" and return ONLY a JSON object.

Social media posts (last 30 min):
{json.dumps(posts[:20], indent=2)}

Recent news headlines:
{json.dumps(news[:10], indent=2)}

Return ONLY this JSON with no other text:
{{
  "crowd_density": <float 0.0-1.0>,
  "sentiment_score": <float 0.0-1.0, where 1=very positive>,
  "safety_risk": <float 0.0-1.0, where 1=high risk>,
  "reactivity": <float 0.0-1.0>,
  "summary": "<one sentence describing the zone mood>"
}}"""

    try:
        model = _get_model()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_text(prompt))
        # Strip markdown fences if present
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        logger.error(f"WatsonX score_zone failed for {zone_id}: {e}")
        return None


async def agent_react(agent_profile: dict, news_item: str, rumour: str = None) -> dict:
    """Run a single swarm agent reaction through WatsonX."""
    rumour_line = f"\nYou have also heard this rumour: {rumour}" if rumour else ""
    prompt = f"""You are a {agent_profile['archetype']} person living in {agent_profile['zone']}.
Your political lean is {agent_profile['political_lean']} (scale: -1=far left, 1=far right).
Your trust in media is {agent_profile['media_trust']} (scale: 0=none, 1=full).
You have just read this news: {news_item}{rumour_line}

How do you react? Return ONLY this JSON with no other text:
{{
  "sentiment": "<positive|negative|neutral>",
  "action": "<share|ignore|counter|amplify>",
  "intensity": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""

    try:
        model = _get_model()
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_text(prompt))
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        result["agent_id"] = agent_profile["agent_id"]
        result["archetype"] = agent_profile["archetype"]
        return result
    except Exception as e:
        logger.warning(f"Agent {agent_profile['agent_id']} failed: {e}")
        # Return neutral non-reaction on failure — don't crash the swarm
        return {
            "agent_id": agent_profile["agent_id"],
            "archetype": agent_profile["archetype"],
            "sentiment": "neutral",
            "action": "ignore",
            "intensity": 0.0,
            "reasoning": "parse_error"
        }


async def health_check() -> bool:
    try:
        model = _get_model()
        resp = model.generate_text("Reply with the word OK and nothing else.")
        return "ok" in resp.lower()
    except:
        return False
```

---

## services/social_service.py — Key Functions

```python
import asyncio
import praw
import feedparser
import logging
from backend.config import settings
from backend.core.zones import ZONES
from backend.services.watsonx_service import score_zone
from backend.services.redis_service import set_zone_score
from backend.core.models import ZoneScore
from datetime import datetime

logger = logging.getLogger(__name__)

def _get_reddit():
    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent
    )

async def fetch_reddit_posts(subreddits: list[str], limit: int = 25) -> list[str]:
    """Fetch recent post titles from a list of subreddits."""
    posts = []
    try:
        reddit = _get_reddit()
        loop = asyncio.get_event_loop()
        for sub in subreddits:
            subreddit = await loop.run_in_executor(None, lambda: reddit.subreddit(sub))
            hot = await loop.run_in_executor(None, lambda: list(subreddit.hot(limit=limit)))
            posts.extend([p.title for p in hot])
    except Exception as e:
        logger.warning(f"Reddit fetch failed for {subreddits}: {e}")
    return posts

async def fetch_news_feed(rss_url: str) -> list[str]:
    """Fetch recent headlines from an RSS feed."""
    try:
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, lambda: feedparser.parse(rss_url))
        return [entry.title for entry in feed.entries[:15]]
    except Exception as e:
        logger.warning(f"RSS fetch failed for {rss_url}: {e}")
        return []

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
                    **scores
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
```

---

## services/redis_service.py

```python
import aioredis
import json
from backend.config import settings
from backend.core.models import ZoneScore

_redis = None

async def init_redis():
    global _redis
    _redis = await aioredis.from_url(settings.redis_url, decode_responses=True)

async def set_zone_score(zone_id: str, score: ZoneScore):
    await _redis.setex(f"zone:{zone_id}", 65, score.model_dump_json())

async def get_zone_score(zone_id: str) -> dict | None:
    data = await _redis.get(f"zone:{zone_id}")
    return json.loads(data) if data else None

async def get_all_zone_scores() -> list[dict]:
    keys = await _redis.keys("zone:*")
    scores = []
    for key in keys:
        data = await _redis.get(key)
        if data:
            scores.append(json.loads(data))
    return scores

async def health_check() -> bool:
    try:
        await _redis.ping()
        return True
    except:
        return False
```

---

## routers/zones.py

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.redis_service import get_all_zone_scores
import asyncio
import json

router = APIRouter()
connected_clients: list[WebSocket] = []

@router.get("/zones")
async def get_zones():
    scores = await get_all_zone_scores()
    return {"zones": scores, "count": len(scores)}

@router.websocket("/ws/zones")
async def websocket_zones(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    try:
        while True:
            scores = await get_all_zone_scores()
            await ws.send_json({"type": "zone_update", "zones": scores})
            await asyncio.sleep(30)
    except WebSocketDisconnect:
        connected_clients.remove(ws)
```

---

## core/alert_rules.py

```python
from backend.core.models import Alert, ZoneScore
from datetime import datetime
import uuid

THRESHOLDS = {
    "safety_risk_high":     0.75,
    "safety_risk_critical": 0.90,
    "sentiment_crash":      0.25,   # sentiment_score below this = alert
    "crowd_spike":          0.85,
}

def evaluate_zone(score: ZoneScore) -> list[Alert]:
    alerts = []

    if score.safety_risk >= THRESHOLDS["safety_risk_critical"]:
        alerts.append(Alert(
            alert_id=str(uuid.uuid4()),
            zone_id=score.zone_id,
            zone_name=score.zone_name,
            alert_type="safety_critical",
            message=f"CRITICAL: Safety risk at {score.safety_risk:.0%} in {score.zone_name}",
            severity="critical",
            triggered_at=datetime.utcnow(),
            value=score.safety_risk,
            threshold=THRESHOLDS["safety_risk_critical"]
        ))
    elif score.safety_risk >= THRESHOLDS["safety_risk_high"]:
        alerts.append(Alert(
            alert_id=str(uuid.uuid4()),
            zone_id=score.zone_id,
            zone_name=score.zone_name,
            alert_type="high_risk",
            message=f"High safety risk ({score.safety_risk:.0%}) in {score.zone_name}",
            severity="high",
            triggered_at=datetime.utcnow(),
            value=score.safety_risk,
            threshold=THRESHOLDS["safety_risk_high"]
        ))

    if score.sentiment_score <= THRESHOLDS["sentiment_crash"]:
        alerts.append(Alert(
            alert_id=str(uuid.uuid4()),
            zone_id=score.zone_id,
            zone_name=score.zone_name,
            alert_type="sentiment_crash",
            message=f"Sentiment crash in {score.zone_name}: {score.sentiment_score:.0%} positive",
            severity="medium",
            triggered_at=datetime.utcnow(),
            value=score.sentiment_score,
            threshold=THRESHOLDS["sentiment_crash"]
        ))

    return alerts
```

---

## requirements.txt

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
pydantic==2.7.0
pydantic-settings==2.2.1
asyncpg==0.29.0
aioredis==2.0.1
praw==7.7.1
feedparser==6.0.11
ibm-watson-machine-learning==1.0.357
python-dotenv==1.0.1
httpx==0.27.0
```

---

## docker-compose.yml (local dev)

```yaml
version: '3.9'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: devcitypulse
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```
