from backend.services.predictor_service import _apply_guardrails


def test_guardrails_cap_high_tier_on_low_coverage():
    score, tier, warnings = _apply_guardrails(
        risk_score=0.82,
        raw_tier="CRITICAL",
        input_coverage=0.2,
        event_count_6h=20,
        previous_score=0.80,
    )
    assert score < 0.75
    assert tier in ("WATCH", "ELEVATED")
    assert any("coverage" in w for w in warnings)


def test_guardrails_limit_step_change():
    score, tier, warnings = _apply_guardrails(
        risk_score=0.95,
        raw_tier="CRITICAL",
        input_coverage=1.0,
        event_count_6h=20,
        previous_score=0.30,
    )
    assert score <= 0.50
    assert "score_step_capped" in warnings
    assert tier in ("WATCH", "ELEVATED")
