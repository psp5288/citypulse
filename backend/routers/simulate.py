import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks

from backend.core.models import SimulationRequest, SimulationResult
from backend.services.swarm_engine import run_swarm
from backend.services.postgres_service import get_simulation, get_simulation_history, save_simulation

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/simulate", response_model=SimulationResult)
async def start_simulation(request: SimulationRequest, background_tasks: BackgroundTasks):
    simulation_id = str(uuid.uuid4())

    placeholder = SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=request.n_agents,
        status="running",
        created_at=datetime.utcnow(),
    )

    # Persist placeholder so polling works immediately
    await save_simulation(placeholder)

    background_tasks.add_task(run_swarm, simulation_id, request)
    logger.info(f"Simulation {simulation_id} queued: {request.n_agents} agents, zone={request.zone}")
    return placeholder


@router.get("/simulate/history")
async def get_history(limit: int = 20):
    return await get_simulation_history(limit)


@router.get("/simulate/{simulation_id}")
async def get_simulation_result(simulation_id: str):
    result = await get_simulation(simulation_id)
    if not result:
        return {"error": "not found", "simulation_id": simulation_id}
    return result
