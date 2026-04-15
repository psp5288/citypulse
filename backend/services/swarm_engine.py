"""
CityPulse Swarm Engine — multi-round cascade simulation.

Round 1  : All agents react independently to the raw news item.
Round 2  : passive_consumer + skeptic re-react seeing the social signal from
           the top 10% of amplifiers + emotional_reactors (cascade effect).
Round 3  : institutional agents respond to the full social noise.

Additionally computes:
  - Network-weighted virality  (weighted by network_size, not headcount)
  - Temporal reaction timeline (per-archetype delay buckets → chart data)
  - Rumour propagation score   (rumor_susceptibility × exposed fraction)
  - Coalition dynamic label    (consensus / polarised / fragmented)
  - Per-archetype breakdown    (each archetype's sentiment + action summary)
"""

import asyncio
import logging
from collections import Counter, defaultdict
from datetime import datetime

from backend.services.iris_service import get_iris_state
from backend.services.oracle_prior_service import build_swarm_prior
from backend.services.personality_pool import generate_personality_pool
from backend.services.postgres_service import get_historical_analogs
from backend.services.watsonx_service import agent_react
from backend.services.redis_service import get_zone_score
from backend.services.postgres_service import save_simulation, update_simulation_status
from backend.services import run_state
from backend.core.models import SimulationRequest, SimulationResult
from backend.config import settings

logger = logging.getLogger(__name__)

# ── Temporal buckets (minutes) used to build the reaction timeline chart ──────
_TIME_BUCKETS = [0, 5, 15, 30, 60, 120, 240, 480, 720, 1440]


# ── Batch helpers ─────────────────────────────────────────────────────────────

async def run_batch(
    agents: list[dict],
    news_item: str,
    rumour: str = None,
    social_context: list[str] | None = None,
) -> list[dict]:
    """
    Run agent reactions in bounded chunks.

    Important: Round 2/3 can pass hundreds of agents here; unbounded gather can
    saturate model backends and cause stalls. Chunking keeps throughput stable.
    """
    if not agents:
        return []

    chunk_size = max(1, settings.simulation_batch_size)
    out: list[dict] = []

    for i in range(0, len(agents), chunk_size):
        chunk = agents[i : i + chunk_size]
        tasks = [agent_react(a, news_item, rumour, social_context) for a in chunk]
        rows = await asyncio.gather(*tasks, return_exceptions=True)
        for agent, row in zip(chunk, rows):
            if isinstance(row, Exception):
                logger.warning(
                    "[Swarm] agent_react failed for agent_id=%s: %s",
                    agent.get("agent_id"),
                    row,
                )
                out.append(
                    {
                        "agent_id": agent.get("agent_id"),
                        "archetype": agent.get("archetype", "unknown"),
                        "sentiment": "neutral",
                        "action": "ignore",
                        "intensity": 0.0,
                        "reasoning": "Fallback response due to processing error.",
                        "network_size": agent.get("network_size", 50),
                        "reaction_delay_minutes": agent.get("reaction_delay_minutes", 60),
                    }
                )
            else:
                out.append(row)
    return out


# ── Social-context builder ────────────────────────────────────────────────────

def _build_social_context(results: list[dict], top_n_pct: float = 0.10) -> list[str]:
    """
    Extract short opinion strings from the top N% amplifiers + emotional_reactors
    (sorted by intensity) to use as social context in Round 2.
    """
    influencer_types = {"amplifier", "emotional_reactor", "early_adopter"}
    influencers = sorted(
        [r for r in results if r.get("archetype") in influencer_types],
        key=lambda r: float(r.get("intensity", 0)),
        reverse=True,
    )
    top = influencers[: max(1, int(len(influencers) * top_n_pct + 0.5))]
    snippets = []
    for r in top:
        sent = r.get("sentiment", "neutral")
        arch = r.get("archetype", "user")
        reason = (r.get("reasoning") or "")[:80]
        snippets.append(f"[{arch}|{sent}] {reason}")
    return snippets


def _build_full_context(results: list[dict], max_items: int = 12) -> list[str]:
    """Full social noise summary for Round 3 institutional agents."""
    sharers = [r for r in results if r.get("action") in ("share", "amplify")]
    counter = [r for r in results if r.get("action") == "counter"]
    sample = (sharers + counter)[:max_items]
    snippets = []
    for r in sample:
        sent = r.get("sentiment", "neutral")
        arch = r.get("archetype", "user")
        reason = (r.get("reasoning") or "")[:80]
        snippets.append(f"[{arch}|{sent}] {reason}")
    return snippets


# ── Temporal timeline ─────────────────────────────────────────────────────────

def _build_temporal_timeline(results: list[dict], agents_map: dict[int, dict]) -> list[dict]:
    """
    For each time bucket T, include every agent whose reaction_delay_minutes <= T
    and compute cumulative sentiment fractions and reach at that moment.
    """
    timeline = []
    prev_bucket_results: list[dict] = []

    for t in _TIME_BUCKETS:
        bucket_results = [
            r for r in results
            if float(r.get("reaction_delay_minutes", 9999)) <= t
        ]
        new_count = len(bucket_results) - len(prev_bucket_results)
        prev_bucket_results = bucket_results

        if not bucket_results:
            timeline.append({
                "minute": t,
                "positive": 0.0, "negative": 0.0, "neutral": 0.0,
                "cumulative_agents": 0,
                "cumulative_reach": 0,
                "new_agents": 0,
            })
            continue

        total = len(bucket_results)
        sent_c = Counter(r.get("sentiment", "neutral") for r in bucket_results)
        reach = sum(
            agents_map.get(r.get("agent_id"), {}).get("network_size", 50)
            for r in bucket_results
        )
        timeline.append({
            "minute": t,
            "positive": round(sent_c.get("positive", 0) / total, 3),
            "negative": round(sent_c.get("negative", 0) / total, 3),
            "neutral":  round(sent_c.get("neutral",  0) / total, 3),
            "cumulative_agents": total,
            "cumulative_reach": reach,
            "new_agents": new_count,
        })

    return timeline


# ── Rumour propagation score ──────────────────────────────────────────────────

def _compute_rumour_risk(agents: list[dict], rumour_present: bool) -> float:
    """
    Fraction of susceptible agents (rumor_susceptibility > 0.6) scaled by
    presence of a rumour. Returns 0.0 when no rumour is injected.
    """
    if not rumour_present:
        return 0.0
    susceptible = [
        a for a in agents
        if a.get("policy", {}).get("rumor_susceptibility", 0) > 0.6
    ]
    raw = len(susceptible) / max(1, len(agents))
    return round(min(1.0, raw * 1.4), 3)   # slight amplification — susceptibles cluster


# ── Coalition detection ───────────────────────────────────────────────────────

def _detect_coalition(pos: float, neg: float, neu: float) -> str:
    """
    Label the group dynamic based on sentiment distribution.
      consensus   — 60%+ agree on one sentiment → fast narrative lock-in
      polarised   — ~equal pos/neg split with little neutral → civil unrest risk
      fragmented  — no dominant signal → unpredictable escalation
    """
    dominant = max(pos, neg, neu)
    if dominant >= 0.60:
        return "consensus"
    if pos >= 0.32 and neg >= 0.32:
        return "polarised"
    return "fragmented"


# ── Per-archetype breakdown ───────────────────────────────────────────────────

def _archetype_breakdown(results: list[dict]) -> dict:
    """Summarise sentiment and action counts per archetype."""
    by_arch: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_arch[r.get("archetype", "unknown")].append(r)

    breakdown = {}
    for arch, rows in by_arch.items():
        n = len(rows)
        sents = Counter(r.get("sentiment", "neutral") for r in rows)
        acts = Counter(r.get("action", "ignore") for r in rows)
        breakdown[arch] = {
            "count": n,
            "sentiment": {
                "positive": round(sents.get("positive", 0) / n, 3),
                "negative": round(sents.get("negative", 0) / n, 3),
                "neutral":  round(sents.get("neutral",  0) / n, 3),
            },
            "top_action": acts.most_common(1)[0][0] if acts else "ignore",
            "avg_intensity": round(
                sum(float(r.get("intensity", 0)) for r in rows) / n, 3
            ),
        }
    return breakdown


# ── Main simulation loop ──────────────────────────────────────────────────────

async def run_swarm(simulation_id: str, request: SimulationRequest):
    """
    Full 3-round cascade swarm simulation.
    Saves intermediate progress to DB; updates run-state heartbeat every batch.
    Respects cancellation flag set by POST /api/simulate/{id}/stop.
    """
    logger.info(f"[Swarm {simulation_id}] Starting: {request.n_agents} agents, zone={request.zone}")

    try:
        run_state.update_run(simulation_id, runner_status="running", stage="building_agents")

        iris_vector = await get_iris_state(location=request.zone, topic=request.sector, lookback_hours=24)
        analogs = await get_historical_analogs(request.zone, request.sector, limit=6)
        prior = build_swarm_prior(iris_vector, analogs)
        agents = generate_personality_pool(request.zone, request.n_agents, prior=prior)

        agents_map: dict[int, dict] = {a["agent_id"]: a for a in agents}

        rumour_at_start: str | None = None
        delayed_factors = []
        for factor in request.external_factors:
            if factor.inject_at_minute == 0:
                rumour_at_start = factor.content
            else:
                delayed_factors.append(factor)

        batch_size = settings.simulation_batch_size
        all_results: list[dict] = []
        action_counts: Counter = Counter()
        recent_actions: list[dict] = []

        # ── ROUND 1: All agents react to raw news ────────────────────────────
        logger.info(f"[Swarm {simulation_id}] Round 1 — {len(agents)} agents")
        run_state.update_run(simulation_id, stage="round_1", total=len(agents))

        for i in range(0, len(agents), batch_size):
            # ── Cancellation check ────────────────────────────────────────────
            if run_state.is_cancelled(simulation_id):
                logger.info(f"[Swarm {simulation_id}] Cancelled during Round 1 batch {i}")
                await update_simulation_status(simulation_id, "failed")
                run_state.update_run(simulation_id, runner_status="cancelled", stage="stopped")
                return

            batch = agents[i : i + batch_size]
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
                    "round": 1,
                }
                for r in batch_results
            )
            if len(recent_actions) > 150:
                recent_actions = recent_actions[-150:]

            processed = min(i + batch_size, len(agents))
            run_state.update_run(simulation_id, processed=processed,
                                 progress_pct=round(processed / len(agents) * 0.6, 3))
            await _save_running(simulation_id, request, processed, len(agents),
                                action_counts, recent_actions, prior)
            logger.info(f"[Swarm {simulation_id}] R1 progress {processed}/{len(agents)}")

        # ── ROUND 2: Cascade — passive_consumer + skeptic see social signal ──
        if run_state.is_cancelled(simulation_id):
            await update_simulation_status(simulation_id, "failed")
            run_state.update_run(simulation_id, runner_status="cancelled", stage="stopped")
            return

        social_ctx = _build_social_context(all_results, top_n_pct=0.12)
        cascade_r2 = [a for a in agents if a["archetype"] in ("passive_consumer", "skeptic")]
        if cascade_r2 and social_ctx:
            logger.info(f"[Swarm {simulation_id}] Round 2 — {len(cascade_r2)} agents")
            run_state.update_run(simulation_id, stage="round_2", progress_pct=0.65)
            r2_results = await run_batch(cascade_r2, request.news_item, rumour_at_start, social_ctx)
            r2_ids = {r["agent_id"] for r in r2_results}
            all_results = [r for r in all_results if r["agent_id"] not in r2_ids] + r2_results
            action_counts.update(r["action"] for r in r2_results)
            recent_actions.extend(
                {**r, "round": 2} for r in
                [{"agent_id": r.get("agent_id"), "archetype": r.get("archetype"),
                  "action": r.get("action"), "sentiment": r.get("sentiment"),
                  "intensity": r.get("intensity"), "reasoning": r.get("reasoning", "")}
                 for r in r2_results]
            )
            if len(recent_actions) > 200:
                recent_actions = recent_actions[-200:]

        # ── ROUND 3: Institutional agents respond to full social noise ────────
        if run_state.is_cancelled(simulation_id):
            await update_simulation_status(simulation_id, "failed")
            run_state.update_run(simulation_id, runner_status="cancelled", stage="stopped")
            return

        full_ctx = _build_full_context(all_results)
        cascade_r3 = [a for a in agents if a["archetype"] == "institutional"]
        if cascade_r3 and full_ctx:
            logger.info(f"[Swarm {simulation_id}] Round 3 — {len(cascade_r3)} institutional agents")
            run_state.update_run(simulation_id, stage="round_3", progress_pct=0.82)
            r3_results = await run_batch(cascade_r3, request.news_item, rumour_at_start, full_ctx)
            r3_ids = {r["agent_id"] for r in r3_results}
            all_results = [r for r in all_results if r["agent_id"] not in r3_ids] + r3_results
            action_counts.update(r["action"] for r in r3_results)
            recent_actions.extend(
                {**r, "round": 3} for r in
                [{"agent_id": r.get("agent_id"), "archetype": r.get("archetype"),
                  "action": r.get("action"), "sentiment": r.get("sentiment"),
                  "intensity": r.get("intensity"), "reasoning": r.get("reasoning", "")}
                 for r in r3_results]
            )
            if len(recent_actions) > 250:
                recent_actions = recent_actions[-250:]

        cascade_rounds_ran = 1 + (1 if cascade_r2 and social_ctx else 0) + (1 if cascade_r3 and full_ctx else 0)

        # ── Delayed external factors ──────────────────────────────────────────
        if delayed_factors:
            run_state.update_run(simulation_id, stage="delayed_factors", progress_pct=0.90)
            for factor in delayed_factors:
                second_wave = agents[: int(len(agents) * 0.3)]
                wave_results = await run_batch(second_wave, request.news_item, factor.content)
                factor_ids = {r["agent_id"] for r in second_wave}
                all_results = [r for r in all_results if r["agent_id"] not in factor_ids]
                all_results.extend(wave_results)

        # ── Final aggregation ─────────────────────────────────────────────────
        run_state.update_run(simulation_id, stage="aggregating", progress_pct=0.95)
        result = aggregate_results(
            simulation_id, request, all_results, agents, agents_map,
            rumour_present=rumour_at_start is not None,
            cascade_rounds=cascade_rounds_ran,
        )
        result.processed_agents = len(all_results)
        result.total_agents = len(agents)
        result.progress_pct = 1.0
        result.action_breakdown = dict(action_counts)
        result.recent_actions = recent_actions[-80:]
        result.prior_context = prior
        result.forecast_distribution = {
            "positive": result.predicted_sentiment.get("positive", 0) if result.predicted_sentiment else 0,
            "neutral":  result.predicted_sentiment.get("neutral", 0)  if result.predicted_sentiment else 0,
            "negative": result.predicted_sentiment.get("negative", 0) if result.predicted_sentiment else 0,
        }

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
        run_state.update_run(simulation_id, runner_status="completed", stage="done", progress_pct=1.0)
        logger.info(
            f"[Swarm {simulation_id}] Complete — virality={result.predicted_virality:.3f} "
            f"coalition={result.coalition_dynamic} rounds={cascade_rounds_ran}"
        )

    except asyncio.CancelledError:
        logger.info(f"[Swarm {simulation_id}] CancelledError received")
        await update_simulation_status(simulation_id, "failed")
        run_state.update_run(simulation_id, runner_status="cancelled", stage="stopped")

    except Exception as e:
        logger.error(f"[Swarm {simulation_id}] Failed: {e}", exc_info=True)
        await update_simulation_status(simulation_id, "failed")
        run_state.update_run(simulation_id, runner_status="failed", stage="error")


# ── Progress save helper ──────────────────────────────────────────────────────

async def _save_running(
    simulation_id: str,
    request: SimulationRequest,
    processed: int,
    total: int,
    action_counts: Counter,
    recent_actions: list[dict],
    prior: dict,
):
    state = SimulationResult(
        simulation_id=simulation_id,
        zone=request.zone,
        news_item=request.news_item,
        sector=request.sector,
        n_agents=request.n_agents,
        status="running",
        progress_pct=round(processed / total, 3),
        processed_agents=processed,
        total_agents=total,
        action_breakdown=dict(action_counts),
        recent_actions=recent_actions[-40:],
        prior_context=prior,
        created_at=datetime.utcnow(),
    )
    await save_simulation(state)


# ── Aggregate ─────────────────────────────────────────────────────────────────

def aggregate_results(
    simulation_id: str,
    request: SimulationRequest,
    results: list[dict],
    agents: list[dict],
    agents_map: dict[int, dict] | None = None,
    rumour_present: bool = False,
    cascade_rounds: int = 1,
) -> SimulationResult:
    """
    Aggregate agent results into the full prediction surface.
    Implements network-weighted virality, temporal timeline, rumour risk,
    coalition detection, and per-archetype breakdown.
    """
    if agents_map is None:
        agents_map = {a["agent_id"]: a for a in agents}

    total = len(results)
    sentiments = Counter(r.get("sentiment", "neutral") for r in results)
    actions = Counter(r.get("action", "ignore") for r in results)

    pos = sentiments.get("positive", 0) / total
    neg = sentiments.get("negative", 0) / total
    neu = sentiments.get("neutral",  0) / total

    # ── Network-weighted virality ─────────────────────────────────────────────
    sharers = [r for r in results if r.get("action") in ("share", "amplify")]
    weighted_reach = sum(
        agents_map.get(r.get("agent_id"), {}).get("network_size", 50) for r in sharers
    )
    total_possible_reach = sum(a.get("network_size", 50) for a in agents)
    virality = round(min(1.0, weighted_reach / max(1, total_possible_reach) * 1.5), 3)

    # ── Backlash ──────────────────────────────────────────────────────────────
    counter_ratio = actions.get("counter", 0) / total
    backlash = round(min(1.0, neg * 0.7 + counter_ratio * 0.3), 3)

    # ── Confidence ────────────────────────────────────────────────────────────
    top_sentiment_pct = max(pos, neg, neu)
    confidence = 0.5 + (top_sentiment_pct - 0.33) * 1.5
    confidence = round(min(0.98, max(0.5, confidence)), 2)

    # ── Peak reaction time from actual per-archetype delays ──────────────────
    fast_actors = [
        r for r in results
        if r.get("archetype") in ("emotional_reactor", "early_adopter", "amplifier")
    ]
    if fast_actors:
        avg_fast_delay = sum(
            float(agents_map.get(r.get("agent_id"), {}).get("reaction_delay_minutes", 10))
            for r in fast_actors
        ) / len(fast_actors)
        peak_hours = round(avg_fast_delay / 60 + 0.25, 1)
    else:
        peak_hours = 1.0 + (1 - len(fast_actors) / max(1, total)) * 6
    peak_str = f"{peak_hours:.1f} hours"

    # ── Temporal timeline ─────────────────────────────────────────────────────
    temporal_timeline = _build_temporal_timeline(results, agents_map)

    # ── Rumour risk ───────────────────────────────────────────────────────────
    rumour_risk = _compute_rumour_risk(agents, rumour_present)

    # ── Coalition dynamic ─────────────────────────────────────────────────────
    coalition_dynamic = _detect_coalition(pos, neg, neu)

    # ── Per-archetype breakdown ───────────────────────────────────────────────
    arch_breakdown = _archetype_breakdown(results)

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
            "neutral":  round(neu, 3),
        },
        predicted_virality=virality,
        peak_reaction_time=peak_str,
        risk_of_backlash=backlash,
        confidence=confidence,
        cascade_rounds=cascade_rounds,
        rumour_risk=rumour_risk,
        coalition_dynamic=coalition_dynamic,
        temporal_timeline=temporal_timeline,
        archetype_breakdown=arch_breakdown,
        created_at=datetime.utcnow(),
    )
