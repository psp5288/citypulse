# SWARM.md — Swarm AI Engine Specification

## Overview

The Oracle simulation engine creates 1,000 virtual agents with demographically-calibrated personality profiles. Each agent processes a news item through its personality lens via WatsonX, reacts, and the results are aggregated into a prediction surface.

---

## core/archetypes.py — Personality Archetype Library

```python
from dataclasses import dataclass
from typing import Tuple
import random

@dataclass
class Archetype:
    name: str
    weight: float                    # proportion of population
    media_trust_range: Tuple[float, float]
    political_lean_range: Tuple[float, float]  # -1=far left, 1=far right
    reaction_delay_range: Tuple[float, float]  # minutes before reacting
    network_size_range: Tuple[int, int]         # how many others they influence
    share_probability: float         # base probability of sharing
    description: str

ARCHETYPES = {
    "passive_consumer": Archetype(
        name="passive_consumer",
        weight=0.31,
        media_trust_range=(0.4, 0.7),
        political_lean_range=(-0.3, 0.3),
        reaction_delay_range=(60, 240),
        network_size_range=(10, 50),
        share_probability=0.05,
        description="Reads but rarely reacts. Mainstream lean. Low urgency."
    ),
    "skeptic": Archetype(
        name="skeptic",
        weight=0.18,
        media_trust_range=(0.1, 0.35),
        political_lean_range=(-0.5, 0.5),
        reaction_delay_range=(120, 480),
        network_size_range=(20, 100),
        share_probability=0.15,
        description="Waits for confirmation. Questions official narratives."
    ),
    "emotional_reactor": Archetype(
        name="emotional_reactor",
        weight=0.15,
        media_trust_range=(0.5, 0.9),
        political_lean_range=(-0.8, 0.8),
        reaction_delay_range=(1, 15),
        network_size_range=(30, 200),
        share_probability=0.70,
        description="Driven by feeling over fact. Reacts immediately and intensely."
    ),
    "early_adopter": Archetype(
        name="early_adopter",
        weight=0.12,
        media_trust_range=(0.3, 0.6),
        political_lean_range=(-0.2, 0.4),
        reaction_delay_range=(2, 20),
        network_size_range=(50, 300),
        share_probability=0.55,
        description="Quick to react, tech-savvy, shares immediately."
    ),
    "amplifier": Archetype(
        name="amplifier",
        weight=0.09,
        media_trust_range=(0.4, 0.75),
        political_lean_range=(-0.4, 0.4),
        reaction_delay_range=(5, 30),
        network_size_range=(500, 5000),
        share_probability=0.80,
        description="High follower count. Multiplies signal in both directions."
    ),
    "contrarian": Archetype(
        name="contrarian",
        weight=0.08,
        media_trust_range=(0.05, 0.3),
        political_lean_range=(-1.0, 1.0),
        reaction_delay_range=(10, 60),
        network_size_range=(40, 200),
        share_probability=0.45,
        description="Reacts opposite to dominant sentiment. Creates counter-narratives."
    ),
    "institutional": Archetype(
        name="institutional",
        weight=0.07,
        media_trust_range=(0.75, 1.0),
        political_lean_range=(-0.1, 0.3),
        reaction_delay_range=(180, 720),
        network_size_range=(100, 500),
        share_probability=0.20,
        description="Trusts official sources only. Slow but credible."
    ),
}

def get_archetype_for_index(i: int, weights: dict = None) -> str:
    """Pick an archetype based on weighted distribution."""
    if weights is None:
        weights = {k: v.weight for k, v in ARCHETYPES.items()}
    names = list(weights.keys())
    probs = [weights[n] for n in names]
    return random.choices(names, weights=probs)[0]
```

---

## services/personality_pool.py — Pool Generator

```python
import random
from backend.core.archetypes import ARCHETYPES, get_archetype_for_index
from backend.core.zones import ZONES, get_zone_by_id

def generate_personality_pool(zone_id: str, n_agents: int = 1000) -> list[dict]:
    """
    Generate n_agents profiles calibrated to the zone's demographic data.
    Zone demographics can override the default archetype weights.
    """
    zone = get_zone_by_id(zone_id)
    demographic_weights = zone.get("demographic_weights", None)  # zone-specific override

    agents = []
    for i in range(n_agents):
        archetype_name = get_archetype_for_index(i, demographic_weights)
        archetype = ARCHETYPES[archetype_name]

        agent = {
            "agent_id": i,
            "archetype": archetype_name,
            "zone": zone["name"],
            "city": zone["city"],
            "media_trust": round(random.uniform(*archetype.media_trust_range), 2),
            "political_lean": round(random.uniform(*archetype.political_lean_range), 2),
            "reaction_delay_minutes": round(random.uniform(*archetype.reaction_delay_range)),
            "network_size": random.randint(*archetype.network_size_range),
            "base_share_probability": archetype.share_probability,
        }
        agents.append(agent)

    return agents


def get_archetype_distribution(agents: list[dict]) -> dict:
    """Count actual archetype distribution in a pool."""
    from collections import Counter
    counts = Counter(a["archetype"] for a in agents)
    total = len(agents)
    return {k: {"count": v, "pct": round(v / total, 3)} for k, v in counts.items()}
```

---

## services/swarm_engine.py — Orchestration

```python
import asyncio
import uuid
import logging
from datetime import datetime
from collections import Counter

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
        # Generate agent pool
        agents = generate_personality_pool(request.zone, request.n_agents)

        # Determine if/when external factors inject
        rumour_at_start = None
        delayed_factors = []
        for factor in request.external_factors:
            if factor.inject_at_minute == 0:
                rumour_at_start = factor.content
            else:
                delayed_factors.append(factor)

        # Run agents in batches (respect WatsonX rate limits)
        batch_size = settings.simulation_batch_size
        all_results = []

        for i in range(0, len(agents), batch_size):
            batch = agents[i:i + batch_size]
            batch_results = await run_batch(batch, request.news_item, rumour_at_start)
            all_results.extend(batch_results)
            logger.info(f"Sim {simulation_id}: completed {min(i+batch_size, len(agents))}/{len(agents)} agents")

        # Run delayed factor injection (simulate second wave)
        if delayed_factors:
            for factor in delayed_factors:
                second_wave = agents[:int(len(agents) * 0.3)]  # expose 30% to second wave
                wave_results = await run_batch(second_wave, request.news_item, factor.content)
                # Merge: factor agents override their original result
                agent_ids = {r["agent_id"] for r in second_wave}
                all_results = [r for r in all_results if r["agent_id"] not in agent_ids]
                all_results.extend(wave_results)

        # Aggregate results
        result = aggregate_results(simulation_id, request, all_results)

        # Compare to real-time zone data
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
                "accuracy": f"{accuracy * 100:.1f}%"
            }

        result.completed_at = datetime.utcnow()
        result.status = "complete"
        await save_simulation(result)
        logger.info(f"Sim {simulation_id} complete. Virality={result.predicted_virality:.2f}")

    except Exception as e:
        logger.error(f"Swarm sim {simulation_id} failed: {e}")
        await update_simulation_status(simulation_id, "failed")


def aggregate_results(simulation_id: str, request: SimulationRequest, results: list[dict]) -> SimulationResult:
    """Aggregate 1000 agent results into a prediction surface."""
    total = len(results)
    sentiments = Counter(r["sentiment"] for r in results)
    actions = Counter(r["action"] for r in results)

    pos = sentiments.get("positive", 0) / total
    neg = sentiments.get("negative", 0) / total
    neu = sentiments.get("neutral", 0) / total

    # Virality = (share + amplify actions) weighted by network size
    sharers = [r for r in results if r["action"] in ("share", "amplify")]
    virality = min(1.0, len(sharers) / total * 1.5)

    # Backlash risk = negative sentiment × counter actions
    counter_ratio = actions.get("counter", 0) / total
    backlash = min(1.0, neg * 0.7 + counter_ratio * 0.3)

    # Confidence = agreement strength (how dominant is top sentiment)
    top_sentiment_pct = max(pos, neg, neu)
    confidence = 0.5 + (top_sentiment_pct - 0.33) * 1.5
    confidence = round(min(0.98, max(0.5, confidence)), 2)

    # Peak reaction estimate: driven by emotional reactors + early adopters
    fast_actors = [r for r in results if r.get("archetype") in ("emotional_reactor", "early_adopter", "amplifier")]
    peak_hours = 1.0 + (1 - len(fast_actors) / total) * 6
    peak_str = f"{peak_hours:.1f} hours"

    return SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=total,
        status="complete",
        predicted_sentiment={"positive": round(pos, 3), "negative": round(neg, 3), "neutral": round(neu, 3)},
        predicted_virality=round(virality, 3),
        peak_reaction_time=peak_str,
        risk_of_backlash=round(backlash, 3),
        confidence=confidence,
        created_at=datetime.utcnow()
    )
```

---

## routers/simulate.py

```python
from fastapi import APIRouter, BackgroundTasks
from backend.core.models import SimulationRequest, SimulationResult
from backend.services.swarm_engine import run_swarm
from backend.services.postgres_service import get_simulation, get_simulation_history
from datetime import datetime
import uuid

router = APIRouter()

@router.post("/simulate", response_model=SimulationResult)
async def start_simulation(request: SimulationRequest, background_tasks: BackgroundTasks):
    simulation_id = str(uuid.uuid4())
    # Create placeholder record
    placeholder = SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=request.n_agents,
        status="running",
        created_at=datetime.utcnow()
    )
    # Launch background task
    background_tasks.add_task(run_swarm, simulation_id, request)
    return placeholder

@router.get("/simulate/{simulation_id}")
async def get_simulation_result(simulation_id: str):
    result = await get_simulation(simulation_id)
    if not result:
        return {"error": "not found"}
    return result

@router.get("/simulate/history")
async def get_history(limit: int = 20):
    return await get_simulation_history(limit)
```

---

## Pre-Built Scenario Files

### simulation/scenarios/banking_crisis.json
```json
{
  "scenario_id": "banking_crisis",
  "title": "Bank announces interest rate increase",
  "description": "Central bank raises rates by 1.5% effective immediately",
  "sector": "banking",
  "default_zone": "nyc-manhattan",
  "news_item": "The Federal Reserve has announced an emergency 1.5% interest rate increase effective immediately, citing inflation concerns.",
  "external_factors": [
    {
      "type": "counter_rumour",
      "content": "Anonymous sources suggest the rate hike may be reversed within 90 days",
      "inject_at_minute": 45
    }
  ]
}
```

### simulation/scenarios/policy_announcement.json
```json
{
  "scenario_id": "policy_announcement",
  "title": "Mayor announces new congestion pricing",
  "description": "City introduces $15/day charge for driving in central zone",
  "sector": "government",
  "default_zone": "nyc-manhattan",
  "news_item": "Mayor announces new $15 daily congestion pricing charge for all vehicles entering Manhattan below 60th Street, effective next month.",
  "external_factors": [
    {
      "type": "viral_controversy",
      "content": "Leaked memo suggests exemptions for wealthy neighbourhoods",
      "inject_at_minute": 30
    }
  ]
}
```

### simulation/external_factors/factor_library.json
```json
{
  "factors": [
    {
      "id": "counter_rumour",
      "label": "Counter Rumour",
      "description": "A competing narrative contradicting the main news",
      "effect": "Reduces negative sentiment by 15-25%, increases neutral"
    },
    {
      "id": "authority_denial",
      "label": "Authority Denial",
      "description": "An official source publicly denies the news",
      "effect": "Splits reaction — increases skeptic engagement, reduces institutional trust"
    },
    {
      "id": "viral_controversy",
      "label": "Viral Controversy",
      "description": "An unrelated controversy floods the information space",
      "effect": "Reduces virality of main story by 30-50%, drowns passive consumers"
    },
    {
      "id": "confirmation_leak",
      "label": "Confirmation Leak",
      "description": "A leaked document appears to confirm the story",
      "effect": "Amplifies negative sentiment by 20-35%, spikes emotional reactors"
    }
  ]
}
```
