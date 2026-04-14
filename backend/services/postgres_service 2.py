import json
import logging
from datetime import datetime, timezone
from typing import Optional

from backend.database import get_pool
from backend.core.models import ZoneScore, SimulationResult

logger = logging.getLogger(__name__)


# ── Zone snapshots ────────────────────────────────────────────────────────────

async def save_zone_snapshot(score: ZoneScore):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO zone_snapshots
               (zone_id, zone_name, city, crowd_density, sentiment_score,
                safety_risk, reactivity, summary, post_count, scored_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
            score.zone_id,
            score.zone_name,
            score.city,
            score.crowd_density,
            score.sentiment_score,
            score.safety_risk,
            score.reactivity,
            score.summary,
            score.post_count,
            score.scored_at,
        )


async def get_zone_analytics(zone_id: str, hours: int = 24) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT scored_at, crowd_density, sentiment_score, safety_risk, reactivity
               FROM zone_snapshots
               WHERE zone_id = $1 AND scored_at > NOW() - ($2 || ' hours')::interval
               ORDER BY scored_at ASC""",
            zone_id,
            str(hours),
        )
        return [
            {
                "scored_at": r["scored_at"].isoformat(),
                "crowd_density": r["crowd_density"],
                "sentiment_score": r["sentiment_score"],
                "safety_risk": r["safety_risk"],
                "reactivity": r["reactivity"],
            }
            for r in rows
        ]


# ── Simulations ───────────────────────────────────────────────────────────────

async def save_simulation(result: SimulationResult):
    pool = get_pool()
    result_data = result.model_dump()
    # Convert datetime objects to ISO strings for JSONB
    for key in ("created_at", "completed_at"):
        if result_data.get(key) and isinstance(result_data[key], datetime):
            result_data[key] = result_data[key].isoformat()

    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO simulations (id, zone, news_item, sector, n_agents, status, result_json, created_at, completed_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
               ON CONFLICT (id) DO UPDATE
               SET status=EXCLUDED.status, result_json=EXCLUDED.result_json, completed_at=EXCLUDED.completed_at""",
            result.simulation_id,
            result.zone,
            result.news_item,
            result.sector,
            result.n_agents,
            result.status,
            json.dumps(result_data),
            result.created_at,
            result.completed_at,
        )


async def update_simulation_status(simulation_id: str, status: str):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE simulations SET status=$1 WHERE id=$2",
            status,
            simulation_id,
        )


async def get_simulation(simulation_id: str) -> Optional[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT result_json FROM simulations WHERE id=$1",
            simulation_id,
        )
        if not row:
            return None
        return json.loads(row["result_json"])


async def get_simulation_history(limit: int = 20) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT result_json FROM simulations
               ORDER BY created_at DESC LIMIT $1""",
            limit,
        )
        return [json.loads(r["result_json"]) for r in rows]


# ── Alerts ────────────────────────────────────────────────────────────────────

async def save_alert(alert: dict):
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO alerts (id, zone_id, zone_name, alert_type, message, severity, value, threshold_val, triggered_at)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)""",
            alert["alert_id"],
            alert["zone_id"],
            alert["zone_name"],
            alert["alert_type"],
            alert["message"],
            alert["severity"],
            alert["value"],
            alert["threshold"],
            alert.get("triggered_at", datetime.utcnow()),
        )


async def get_active_alerts(limit: int = 50) -> list[dict]:
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, zone_id, zone_name, alert_type, message, severity,
                      value, threshold_val, triggered_at, acknowledged
               FROM alerts
               WHERE acknowledged = FALSE
               ORDER BY triggered_at DESC LIMIT $1""",
            limit,
        )
        return [
            {
                "alert_id": str(r["id"]),
                "zone_id": r["zone_id"],
                "zone_name": r["zone_name"],
                "alert_type": r["alert_type"],
                "message": r["message"],
                "severity": r["severity"],
                "value": r["value"],
                "threshold": r["threshold_val"],
                "triggered_at": r["triggered_at"].isoformat(),
            }
            for r in rows
        ]
