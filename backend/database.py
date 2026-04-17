from typing import Optional
import asyncpg
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS zone_snapshots (
    id              SERIAL PRIMARY KEY,
    zone_id         VARCHAR(64) NOT NULL,
    zone_name       VARCHAR(128),
    city            VARCHAR(64),
    crowd_density   FLOAT,
    sentiment_score FLOAT,
    safety_risk     FLOAT,
    reactivity      FLOAT,
    summary         TEXT,
    post_count      INT DEFAULT 0,
    scored_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_zone_snapshots_zone_id ON zone_snapshots(zone_id);
CREATE INDEX IF NOT EXISTS idx_zone_snapshots_scored_at ON zone_snapshots(scored_at DESC);

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
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_id VARCHAR(64);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS zone_name VARCHAR(128);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS alert_type VARCHAR(64);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS message TEXT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS severity VARCHAR(16);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS value FLOAT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS threshold_val FLOAT;
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS triggered_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS acknowledged BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_alerts_zone_id ON alerts(zone_id);
CREATE INDEX IF NOT EXISTS idx_alerts_triggered_at ON alerts(triggered_at DESC);

CREATE TABLE IF NOT EXISTS district_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    district_id     VARCHAR(64) NOT NULL,
    crowd           FLOAT,
    sentiment       FLOAT,
    risk            FLOAT,
    events_count    INT DEFAULT 0,
    source_data     JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_district_snapshots_district_id ON district_snapshots(district_id);
CREATE INDEX IF NOT EXISTS idx_district_snapshots_created_at ON district_snapshots(created_at DESC);

CREATE TABLE IF NOT EXISTS citypulse_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity        VARCHAR(16) NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    district_id     VARCHAR(64),
    status          VARCHAR(32) DEFAULT 'open',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_citypulse_alerts_created_at ON citypulse_alerts(created_at DESC);

CREATE TABLE IF NOT EXISTS stream_events (
    id              BIGSERIAL PRIMARY KEY,
    type            VARCHAR(64) NOT NULL,
    district_id     VARCHAR(64),
    message         TEXT NOT NULL,
    metadata        JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stream_events_created_at ON stream_events(created_at DESC);

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            VARCHAR(32) DEFAULT 'user',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS iris_events (
    id              BIGSERIAL PRIMARY KEY,
    source          VARCHAR(64) NOT NULL,
    location        VARCHAR(128) NOT NULL,
    topic           VARCHAR(128) NOT NULL,
    sentiment       FLOAT NOT NULL,
    engagement      FLOAT NOT NULL,
    confidence      FLOAT NOT NULL,
    payload         JSONB DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_iris_events_loc_topic_time ON iris_events(location, topic, occurred_at DESC);

CREATE TABLE IF NOT EXISTS iris_state_cache (
    key             VARCHAR(255) PRIMARY KEY,
    state_json      JSONB NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oracle_forecasts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    location        VARCHAR(128) NOT NULL,
    topic           VARCHAR(128) NOT NULL,
    scenario_text   TEXT NOT NULL,
    result_json     JSONB NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_oracle_forecasts_loc_topic_created_at ON oracle_forecasts(location, topic, created_at DESC);
"""


async def init_db():
    global _pool
    import ssl, os
    # Read directly from env to bypass any pydantic-settings caching issues
    dsn = os.environ.get("DATABASE_URL") or settings.database_url
    ssl_ctx: ssl.SSLContext | bool = False
    if "sslmode=require" in dsn or "sslmode=verify" in dsn or dsn.startswith("postgresql+ssl"):
        import re
        dsn = re.sub(r"[?&]sslmode=[^&]*", "", dsn).rstrip("?")
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, ssl=ssl_ctx or None)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
    logger.info("PostgreSQL connected and schema initialized")


async def close_db():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    if not _pool:
        raise RuntimeError("Database pool not initialized")
    return _pool
