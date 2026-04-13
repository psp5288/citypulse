import asyncio
import logging
from collections import Counter
from datetime import datetime

from backend.services.personality_pool import generate_personality_pool
from backend.services.watsonx_service import agent_react
from backend.services.redis_service import get_zone_score
from backend.services.postgres_service import save_simulation, update_simulation_status
from backend.core.models import SimulationRequest, SimulationResult
from backend.config import settings

logger = logging.getLogger(__name__)


async def run_batch(agents: list[dict], news_item: str, rumour: str = None) -> list[dict]:
    """Run a batch of agents concurrently."""
    tasks = [agent_react(agent, news_item, rumour) for agent in agents]
    return await asyncio.gather(*tasks, return_exceptions=False)


async def run_swarm(simulation_id: str, request: SimulationRequest):
    """
    Full swarm simulation. Runs as a background task.
    Updates DB as it progresses. Notifies via WebSocket when done.
    """
    logger.info(f"Starting swarm sim {simulation_id}: {request.n_agents} agents, zone={request.zone}")

    try:
        agents = generate_personality_pool(request.zone, request.n_agents)

        rumour_at_start = None
        delayed_factors = []
        for factor in request.external_factors:
            if factor.inject_at_minute == 0:
                rumour_at_start = factor.content
            else:
                delayed_factors.append(factor)

        batch_size = settings.simulation_batch_size
        all_results = []
        action_counts = Counter()
        recent_actions: list[dict] = []

        for i in range(0, len(agents), batch_size):
            batch = agents[i:i + batch_size]
            batch_results = await run_batch(batch, request.news_item, rumour_at_start)
            all_results.extend(batch_results)
            action_counts.update(r["action"] for r in batch_results)
            recent_actions.extend(
                {
                    "agent_id": r.get("agent_id"),
                    "archetype": r.get("archetype"),
                    "action": r.get("action"),
                    "sentiment": r.get("sentiment"),
                    "intensity": r.get("intensity"),
                    "reasoning": r.get("reasoning", ""),
                }
                for r in batch_results
            )
            if len(recent_actions) > 120:
                recent_actions = recent_actions[-120:]

            processed = min(i + batch_size, len(agents))
            running_state = SimulationResult(
                simulation_id=simulation_id,
                zone=request.zone,
                news_item=request.news_item,
                sector=request.sector,
                n_agents=request.n_agents,
                status="running",
                progress_pct=round(processed / len(agents), 3),
                processed_agents=processed,
                total_agents=len(agents),
                action_breakdown=dict(action_counts),
                recent_actions=recent_actions[-40:],
                created_at=datetime.utcnow(),
            )
            await save_simulation(running_state)
            logger.info(
                f"Sim {simulation_id}: completed {min(i + batch_size, len(agents))}/{len(agents)} agents"
            )

        if delayed_factors:
            for factor in delayed_factors:
                second_wave = agents[: int(len(agents) * 0.3)]
                wave_results = await run_batch(second_wave, request.news_item, factor.content)
                agent_ids = {r["agent_id"] for r in second_wave}
                all_results = [r for r in all_results if r["agent_id"] not in agent_ids]
                all_results.extend(wave_results)

        result = aggregate_results(simulation_id, request, all_results)
        result.processed_agents = len(all_results)
        result.total_agents = len(agents)
        result.progress_pct = 1.0
        result.action_breakdown = dict(action_counts)
        result.recent_actions = recent_actions[-60:]

        real_score = await get_zone_score(request.zone)
        if real_score:
            real_negative = 1.0 - real_score["sentiment_score"]
            predicted_negative = result.predicted_sentiment["negative"]
            delta = abs(predicted_negative - real_negative)
            accuracy = max(0, 1 - delta)
            result.vs_real_time = {
                "real_sentiment_negative": round(real_negative, 3),
                "predicted_negative": round(predicted_negative, 3),
                "delta": round(delta, 3),
                "accuracy": f"{accuracy * 100:.1f}%",
            }

        result.completed_at = datetime.utcnow()
        result.status = "complete"
        await save_simulation(result)
        logger.info(f"Sim {simulation_id} complete. Virality={result.predicted_virality:.2f}")

    except Exception as e:
        logger.error(f"Swarm sim {simulation_id} failed: {e}")
        await update_simulation_status(simulation_id, "failed")


def aggregate_results(
    simulation_id: str, request: SimulationRequest, results: list[dict]
) -> SimulationResult:
    """Aggregate agent results into a prediction surface."""
    total = len(results)
    sentiments = Counter(r["sentiment"] for r in results)
    actions = Counter(r["action"] for r in results)

    pos = sentiments.get("positive", 0) / total
    neg = sentiments.get("negative", 0) / total
    neu = sentiments.get("neutral", 0) / total

    sharers = [r for r in results if r["action"] in ("share", "amplify")]
    virality = min(1.0, len(sharers) / total * 1.5)

    counter_ratio = actions.get("counter", 0) / total
    backlash = min(1.0, neg * 0.7 + counter_ratio * 0.3)

    top_sentiment_pct = max(pos, neg, neu)
    confidence = 0.5 + (top_sentiment_pct - 0.33) * 1.5
    confidence = round(min(0.98, max(0.5, confidence)), 2)

    fast_actors = [
        r for r in results
        if r.get("archetype") in ("emotional_reactor", "early_adopter", "amplifier")
    ]
    peak_hours = 1.0 + (1 - len(fast_actors) / total) * 6
    peak_str = f"{peak_hours:.1f} hours"

    return SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=total,
        status="complete",
        predicted_sentiment={
            "positive": round(pos, 3),
            "negative": round(neg, 3),
            "neutral": round(neu, 3),
        },
        predicted_virality=round(virality, 3),
        peak_reaction_time=peak_str,
        risk_of_backlash=round(backlash, 3),
        confidence=confidence,
        created_at=datetime.utcnow(),
    )
