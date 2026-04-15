import asyncio
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.core.models import SimulationRequest, SimulationResult
from backend.services import run_state
from backend.services.swarm_engine import run_swarm
from backend.services.postgres_service import (
    get_simulation,
    get_simulation_history,
    save_simulation,
    update_simulation_status,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Timeout wrapper ───────────────────────────────────────────────────────────

async def _run_with_timeout(simulation_id: str, request: SimulationRequest) -> None:
    """
    Run run_swarm with a hard wall-clock timeout.
    On timeout, mark the simulation as failed and update run-state.
    """
    try:
        await asyncio.wait_for(
            run_swarm(simulation_id, request),
            timeout=float(settings.simulation_run_timeout_seconds),
        )
    except asyncio.TimeoutError:
        logger.error(
            "[simulate] %s timed out after %ds",
            simulation_id,
            settings.simulation_run_timeout_seconds,
        )
        run_state.update_run(simulation_id, runner_status="failed", stage="timeout")
        await update_simulation_status(simulation_id, "failed")


# ── POST /api/simulate ────────────────────────────────────────────────────────

@router.post("/simulate", response_model=SimulationResult)
async def start_simulation(request: SimulationRequest, background_tasks: BackgroundTasks):
    simulation_id = str(uuid.uuid4())

    # Persist placeholder so GET polling works immediately
    placeholder = SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=request.n_agents,
        status="running",
        created_at=datetime.utcnow(),
    )
    await save_simulation(placeholder)

    # Initialise in-memory run-state
    run_state.init_run(simulation_id, n_agents=request.n_agents)

    background_tasks.add_task(_run_with_timeout, simulation_id, request)
    logger.info(
        "[simulate] %s queued: %d agents zone=%s timeout=%ds",
        simulation_id, request.n_agents, request.zone,
        settings.simulation_run_timeout_seconds,
    )
    return placeholder


# ── POST /api/simulate/{id}/stop ─────────────────────────────────────────────

@router.post("/simulate/{simulation_id}/stop")
async def stop_simulation(simulation_id: str):
    """
    Request graceful cancellation of a running simulation.
    The swarm engine checks this flag between every batch and between rounds.
    """
    live = run_state.get_run(simulation_id)
    if live is None:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "error": "Simulation not found or already finalised."},
        )

    status = live.get("runner_status", "unknown")
    if status in ("completed", "failed", "cancelled"):
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": f"Cannot stop: simulation is already '{status}'."},
        )

    cancelled = run_state.cancel_run(simulation_id)
    if not cancelled:
        return JSONResponse(
            status_code=409,
            content={"ok": False, "error": "Cancellation request rejected (race condition)."},
        )

    logger.info("[simulate] Stop requested for %s", simulation_id)
    return {"ok": True, "simulation_id": simulation_id, "runner_status": "cancelling"}


# ── GET /api/simulate/history ─────────────────────────────────────────────────

@router.get("/simulate/history")
async def get_history(limit: int = 20):
    return await get_simulation_history(limit)


# ── GET /api/simulate/{id} ────────────────────────────────────────────────────

@router.get("/simulate/{simulation_id}")
async def get_simulation_result(simulation_id: str):
    result = await get_simulation(simulation_id)
    if not result:
        return {"error": "not found", "simulation_id": simulation_id}

    # Merge live run-state fields (heartbeat, stage, runner_status) into response
    snapshot = run_state.public_snapshot(simulation_id)
    if snapshot:
        result["runner_status"]  = snapshot.get("runner_status")
        result["stage"]          = snapshot.get("stage")
        result["last_heartbeat"] = snapshot.get("last_heartbeat")

    return result
