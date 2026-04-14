from backend.core.models import IrisReactionVector
from backend.services.oracle_prior_service import build_swarm_prior
from datetime import datetime, timezone


def test_prior_contains_expected_keys():
    iris = IrisReactionVector(
        location="downtown",
        topic="sports",
        sentiment_score=68,
        attention_score=72,
        stability_score=55,
        trust_score=63,
        novelty_score=60,
        reaction_score=66,
        confidence=0.72,
        volume=120,
        freshness_seconds=20,
        as_of=datetime.now(timezone.utc),
    )
    prior = build_swarm_prior(iris, analogs=[])
    assert "sentiment_bias" in prior
    assert "attention_bias" in prior
    assert "volatility_multiplier" in prior
    assert "action_propensity_shift" in prior
