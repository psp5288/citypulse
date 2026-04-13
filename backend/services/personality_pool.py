import random
from backend.core.archetypes import ARCHETYPES, get_archetype_for_index
from backend.core.zones import ZONES, get_zone_by_id


def generate_personality_pool(zone_id: str, n_agents: int = 1000) -> list[dict]:
    """
    Generate n_agents profiles calibrated to the zone's demographic data.
    Zone demographics can override the default archetype weights.
    """
    zone = get_zone_by_id(zone_id)
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
        agents.append(agent)

    return agents


def get_archetype_distribution(agents: list[dict]) -> dict:
    """Count actual archetype distribution in a pool."""
    from collections import Counter
    counts = Counter(a["archetype"] for a in agents)
    total = len(agents)
    return {k: {"count": v, "pct": round(v / total, 3)} for k, v in counts.items()}
