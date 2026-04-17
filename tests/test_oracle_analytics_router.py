import asyncio

from backend.routers import oracle_analytics


def _sample_rows():
    return [
        {
            "simulation_id": "a1",
            "zone": "downtown",
            "sector": "government",
            "status": "complete",
            "risk_of_backlash": 0.78,
            "confidence": 0.66,
            "predicted_virality": 0.61,
            "flags": ["event_surge", "high_density"],
            "created_at": "2026-04-15T10:00:00+00:00",
            "completed_at": "2026-04-15T10:05:00+00:00",
            "predicted_sentiment": {"positive": 0.20, "negative": 0.62, "neutral": 0.18},
        },
        {
            "simulation_id": "a2",
            "zone": "harbor",
            "sector": "news",
            "status": "complete",
            "risk_of_backlash": 0.42,
            "confidence": 0.58,
            "predicted_virality": 0.48,
            "flags": ["event_surge"],
            "created_at": "2026-04-15T11:00:00+00:00",
            "completed_at": "2026-04-15T11:06:00+00:00",
            "predicted_sentiment": {"positive": 0.41, "negative": 0.40, "neutral": 0.19},
        },
    ]


def test_chart_payload_contains_expected_blocks():
    payload = oracle_analytics._chart_payload(_sample_rows())
    assert "timeline" in payload
    assert "tier_distribution" in payload
    assert "confidence_vs_risk" in payload
    assert payload["run_funnel"]["started"] == 2


def test_final_outlook_uses_recent_average():
    insight = oracle_analytics._build_final_outlook(_sample_rows())
    assert "final_outlook" in insight
    assert insight["final_outlook"]["tier"] in {"NOMINAL", "WATCH", "ELEVATED", "CRITICAL"}
    assert len(insight["recommended_actions"]) >= 1


def test_oracle_chat_rule_fallback(monkeypatch):
    async def _fake_history(**_kwargs):
        return {"items": _sample_rows(), "total": 2}

    async def _no_wx(_q, _e, _d):
        return None

    monkeypatch.setattr(oracle_analytics, "list_simulations_filtered", _fake_history)
    monkeypatch.setattr(oracle_analytics, "_watsonx_augment", _no_wx)

    out = asyncio.run(oracle_analytics.oracle_chat({"question": "top risk run?"}))
    assert out["ok"] is True
    assert out["mode_used"] == "rule_based"
    assert out["fallback_used"] is True
    assert len(out["evidence"]) >= 1
