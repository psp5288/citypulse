"""
City Pulse — FastAPI application.
IBM WatsonX scoring, Redis live districts, PostgreSQL history, WebSocket push, optional Kafka.
"""

from __future__ import annotations

import backend.core.logger  # noqa: F401 — ring buffer for /api/logs

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings
from backend.database import close_db, init_db
from backend.routers import alerts, analytics, auth, districts, events, geo, iris_oracle, location_intel, logs, simulate
from backend.services.ingestion_loop import run_city_pulse_loop
from backend.services.kafka_consumer import start_kafka_consumer
from backend.services.postgres_service import get_freshness_timestamps
from backend.services.redis_service import close_redis, get_freshness_meta, health_check as redis_health, init_redis
from backend.services.watsonx_service import health_check as watsonx_health

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)
_rate_window: dict[str, list[float]] = {}


def _freshness_state(ts: str | None, stale_after_seconds: int) -> str:
    if not ts:
        return "empty"
    try:
        value = datetime.fromisoformat(ts)
        age = (datetime.now(timezone.utc) - value).total_seconds()
        return "ok" if age <= stale_after_seconds else "stale"
    except Exception:
        return "unknown"


async def _postgres_health() -> bool:
    try:
        from backend.database import get_pool

        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception:
        return False


def _is_serverless() -> bool:
    import os
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
    except Exception as e:
        logger.warning("PostgreSQL unavailable at startup (will retry per-request): %s", e)
    try:
        await init_redis()
    except Exception as e:
        logger.warning("Redis unavailable at startup (will retry per-request): %s", e)
    app.state.bg_tasks = []
    # Background tasks require a persistent runtime — skip in serverless environments
    if not _is_serverless():
        app.state.bg_tasks.append(asyncio.create_task(run_city_pulse_loop(), name="citypulse-loop"))
        app.state.bg_tasks.append(asyncio.create_task(start_kafka_consumer(), name="kafka-consumer"))
    logger.info("City Pulse API started (WatsonX + district loop + Kafka stub)")
    yield
    for t in getattr(app.state, "bg_tasks", []):
        t.cancel()
    if getattr(app.state, "bg_tasks", None):
        await asyncio.gather(*app.state.bg_tasks, return_exceptions=True)
    await close_redis()
    await close_db()
    logger.info("City Pulse API shut down")


app = FastAPI(title="City Pulse API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_guardrails(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = datetime.now(timezone.utc).timestamp()
    window = _rate_window.setdefault(ip, [])
    while window and now - window[0] > 60:
        window.pop(0)
    if len(window) >= 180:
        return JSONResponse(
            status_code=429,
            content={"ok": False, "error": "rate_limited", "detail": "Too many requests. Retry in ~1 minute."},
        )
    window.append(now)
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled error on %s: %s", request.url.path, exc)
        return JSONResponse(status_code=500, content={"ok": False, "error": "internal_error", "detail": str(exc)})


app.include_router(districts.router, prefix="/api")
app.include_router(districts.ws_router)
app.include_router(analytics.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(events.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(simulate.router, prefix="/api")
app.include_router(iris_oracle.router, prefix="/api")
app.include_router(geo.router, prefix="/api")
app.include_router(location_intel.router)


@app.get("/api/health")
async def health():
    redis_ok = await redis_health()
    pg_ok = await _postgres_health()
    wx_ok = await watsonx_health()
    freshness_pg = {"snapshots_last_write": None, "events_last_write": None}
    freshness_cache = {"districts_last_update": None, "analytics_last_update": None}
    if pg_ok:
        try:
            freshness_pg = await get_freshness_timestamps()
        except Exception:
            pass
    if redis_ok:
        try:
            freshness_cache = await get_freshness_meta()
        except Exception:
            pass
    status = "ok" if redis_ok and pg_ok else "degraded"
    return {
        "status": status,
        "services": {
            "redis": redis_ok,
            "postgres": pg_ok,
            "watsonx": wx_ok,
            "kafka_configured": bool(settings.kafka_bootstrap_servers),
        },
        "freshness": {
            "districts_cache": {
                "last_update": freshness_cache.get("districts_last_update"),
                "status": _freshness_state(freshness_cache.get("districts_last_update"), stale_after_seconds=120),
            },
            "analytics_cache": {
                "last_update": freshness_cache.get("analytics_last_update"),
                "status": _freshness_state(freshness_cache.get("analytics_last_update"), stale_after_seconds=300),
            },
            "snapshots_db": {
                "last_write": freshness_pg.get("snapshots_last_write"),
                "status": _freshness_state(freshness_pg.get("snapshots_last_write"), stale_after_seconds=300),
            },
            "events_db": {
                "last_write": freshness_pg.get("events_last_write"),
                "status": _freshness_state(freshness_pg.get("events_last_write"), stale_after_seconds=900),
            },
        },
    }


@app.get("/api/debug-health")
async def debug_health():
    import ssl, re, os
    db_url = os.environ.get("DATABASE_URL") or settings.database_url
    redis_url = os.environ.get("REDIS_URL") or settings.redis_url
    db_raw = os.environ.get("DATABASE_URL", "")
    redis_raw = os.environ.get("REDIS_URL", "")
    results = {
        "db_url_starts_with": db_raw[:30] if db_raw else "EMPTY",
        "redis_url_starts_with": redis_raw[:20] if redis_raw else "EMPTY",
    }
    # Test Postgres
    try:
        import asyncpg
        dsn = db_url
        ssl_ctx = None
        if "sslmode=require" in dsn or "sslmode=verify" in dsn:
            dsn = re.sub(r"[?&]sslmode=[^&]*", "", dsn).rstrip("?")
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=1, ssl=ssl_ctx, timeout=10)
        await pool.fetchval("SELECT 1")
        await pool.close()
        results["postgres"] = "ok"
    except Exception as e:
        results["postgres"] = str(e)
    # Test Redis
    try:
        import redis.asyncio as aioredis
        ssl_kwargs = {"ssl_cert_reqs": "none"} if redis_url.startswith("rediss://") else {}
        r = aioredis.from_url(redis_url, decode_responses=True, **ssl_kwargs, socket_connect_timeout=10)
        await r.ping()
        await r.aclose()
        results["redis"] = "ok"
    except Exception as e:
        results["redis"] = str(e)
    return results


@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")


@app.get("/dashboard")
async def serve_dashboard():
    return FileResponse("frontend/dashboard.html")


@app.get("/dashboard.html")
async def serve_dashboard_html():
    return FileResponse("frontend/dashboard.html")


@app.get("/city-pulse.html")
async def serve_city_pulse():
    return FileResponse("frontend/city-pulse.html")


@app.get("/login")
async def serve_login():
    return FileResponse("frontend/login.html")


@app.get("/simulator")
async def serve_simulator():
    return FileResponse("frontend/simulator.html")


@app.get("/analytics")
async def serve_analytics():
    return FileResponse("frontend/analytics.html")


import os as _os
for _dir, _name in [("frontend/assets", "assets"), ("frontend/css", "css"), ("frontend/js", "js")]:
    if _os.path.isdir(_dir):
        app.mount(f"/{_name}", StaticFiles(directory=_dir), name=_name)
