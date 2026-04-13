from typing import Optional

import asyncpg
import logging

from backend.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None

SCHEMA_SQL = """
-- Legacy zone / simulation (optional)
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

-- City Pulse: district history
CREATE TABLE IF NOT EXISTS district_snapshots (
    id              SERIAL PRIMARY KEY,
    district_id     VARCHAR(64) NOT NULL,
    crowd           FLOAT,
    sentiment       FLOAT,
    risk            FLOAT,
    events_count    INT DEFAULT 0,
    source_data     JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_district_snapshots_district ON district_snapshots(district_id);
CREATE INDEX IF NOT EXISTS idx_district_snapshots_created ON district_snapshots(created_at DESC);

-- Feed / event log
CREATE TABLE IF NOT EXISTS stream_events (
    id              SERIAL PRIMARY KEY,
    type            VARCHAR(32),
    district_id     VARCHAR(64),
    message         TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_stream_events_created ON stream_events(created_at DESC);

-- Alerts (City Pulse schema)
CREATE TABLE IF NOT EXISTS citypulse_alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity        VARCHAR(16) NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT,
    district_id     VARCHAR(64),
    status          VARCHAR(16) DEFAULT 'open',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_citypulse_alerts_status ON citypulse_alerts(status);
CREATE INDEX IF NOT EXISTS idx_citypulse_alerts_district ON citypulse_alerts(district_id);

-- Legacy alerts table (older routers)
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

-- Users (JWT auth)
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    role            VARCHAR(32) DEFAULT 'user',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
"""


async def init_db():
    global _pool
    _pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)
        # Backward-compatible additive migration for older local schemas.
        await conn.execute("ALTER TABLE district_snapshots ADD COLUMN IF NOT EXISTS crowd FLOAT")
        await conn.execute("ALTER TABLE district_snapshots ADD COLUMN IF NOT EXISTS sentiment FLOAT")
        await conn.execute("ALTER TABLE district_snapshots ADD COLUMN IF NOT EXISTS risk FLOAT")
        await conn.execute("ALTER TABLE district_snapshots ADD COLUMN IF NOT EXISTS events_count INT DEFAULT 0")
        await conn.execute("ALTER TABLE district_snapshots ADD COLUMN IF NOT EXISTS source_data JSONB")
        # Some older local schemas used legacy columns with NOT NULL constraints.
        # Keep compatibility by relaxing those constraints if columns exist.
        await conn.execute(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='district_snapshots' AND column_name='crowd_density'
              ) THEN
                ALTER TABLE district_snapshots ALTER COLUMN crowd_density DROP NOT NULL;
              END IF;
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='district_snapshots' AND column_name='sentiment_score'
              ) THEN
                ALTER TABLE district_snapshots ALTER COLUMN sentiment_score DROP NOT NULL;
              END IF;
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='district_snapshots' AND column_name='safety_risk'
              ) THEN
                ALTER TABLE district_snapshots ALTER COLUMN safety_risk DROP NOT NULL;
              END IF;
              IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='district_snapshots' AND column_name='reactivity'
              ) THEN
                ALTER TABLE district_snapshots ALTER COLUMN reactivity DROP NOT NULL;
              END IF;
            END$$;
            """
        )

        # Fail fast if required columns are still missing.
        missing = await conn.fetch(
            """
            SELECT required.col
            FROM (
              VALUES ('district_id'), ('crowd'), ('sentiment'), ('risk'),
                     ('events_count'), ('source_data'), ('created_at')
            ) AS required(col)
            LEFT JOIN information_schema.columns c
              ON c.table_schema = 'public'
             AND c.table_name = 'district_snapshots'
             AND c.column_name = required.col
            WHERE c.column_name IS NULL
            """
        )
        if missing:
            missing_cols = ", ".join(r["col"] for r in missing)
            raise RuntimeError(
                f"database schema incompatible: district_snapshots missing columns [{missing_cols}]"
            )
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
