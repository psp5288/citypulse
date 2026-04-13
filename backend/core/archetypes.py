from dataclasses import dataclass
from typing import Tuple
import random


@dataclass
class Archetype:
    name: str
    weight: float
    media_trust_range: Tuple[float, float]
    political_lean_range: Tuple[float, float]   # -1=far left, 1=far right
    reaction_delay_range: Tuple[float, float]   # minutes before reacting
    network_size_range: Tuple[int, int]          # how many others they influence
    share_probability: float
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
