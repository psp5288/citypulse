import random
from backend.core.archetypes import ARCHETYPES, get_archetype_for_index
from backend.core.zones import ZONES, get_zone_by_id


def _sample_big_five(archetype_name: str, prior: dict | None = None) -> dict:
    prior = prior or {}
    sentiment_bias = float(prior.get("sentiment_bias", 0))
    attention_bias = float(prior.get("attention_bias", 0))
    volatility = float(prior.get("volatility_multiplier", 0.5))
    base = {
        "openness": random.uniform(0.35, 0.75),
        "conscientiousness": random.uniform(0.3, 0.8),
        "extraversion": random.uniform(0.25, 0.85),
        "agreeableness": random.uniform(0.3, 0.85),
        "neuroticism": random.uniform(0.2, 0.8),
    }
    if archetype_name in ("emotional_reactor", "amplifier"):
        base["extraversion"] = min(1.0, base["extraversion"] + 0.15 + attention_bias * 0.1)
        base["neuroticism"] = min(1.0, base["neuroticism"] + 0.1 * volatility)
    if archetype_name in ("skeptic", "institutional"):
        base["conscientiousness"] = min(1.0, base["conscientiousness"] + 0.1)
    base["agreeableness"] = max(0.0, min(1.0, base["agreeableness"] + sentiment_bias * 0.12))
    return {k: round(v, 3) for k, v in base.items()}


def _policy_from_traits(traits: dict, share_probability: float) -> dict:
    amplify = min(1.0, share_probability + traits["extraversion"] * 0.2 - traits["conscientiousness"] * 0.1)
    counter = max(0.0, traits["neuroticism"] * 0.35 + (1 - traits["agreeableness"]) * 0.25)
    ignore = max(0.0, 1 - amplify - counter)
    return {
        "amplify_probability": round(amplify, 3),
        "counter_probability": round(counter, 3),
        "ignore_probability": round(ignore, 3),
        "rumor_susceptibility": round((traits["openness"] + traits["neuroticism"]) / 2, 3),
        "sentiment_sensitivity": round((traits["agreeableness"] + traits["neuroticism"]) / 2, 3),
    }


def generate_personality_pool(zone_id: str, n_agents: int = 1000, prior: dict | None = None) -> list[dict]:
    """
    Generate n_agents profiles calibrated to the zone's demographic data.
    Zone demographics can override the default archetype weights.
    """
    try:
        zone = get_zone_by_id(zone_id)
    except Exception:
        # Allow custom geo targets (city/country/state/town) without hard failure.
        label = (zone_id or "custom-location").replace("_", " ").replace("-", " ").strip()
        zone = {
            "id": zone_id,
            "name": label.title() if label else "Custom Location",
            "city": "User Selected",
            "demographic_weights": None,
        }
    demographic_weights = zone.get("demographic_weights", None)

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
        traits = _sample_big_five(archetype_name, prior=prior)
        agent["big_five"] = traits
        agent["policy"] = _policy_from_traits(traits, archetype.share_probability)
        agents.append(agent)

    return agents


def get_archetype_distribution(agents: list[dict]) -> dict:
    """Count actual archetype distribution in a pool."""
    from collections import Counter
    counts = Counter(a["archetype"] for a in agents)
    total = len(agents)
    return {k: {"count": v, "pct": round(v / total, 3)} for k, v in counts.items()}
