import pytest

from backend.routers import risk


@pytest.mark.asyncio
async def test_get_all_risk_scores_computes_only_cache_misses(monkeypatch):
    class _FakeScore:
        def __init__(self, district_id, risk_score=0.4):
            self.district_id = district_id
            self.risk_score = risk_score
            self.alert_tier = "WATCH"
            self.top_drivers = ["sentiment_velocity"]
            self.feature_values = {}
            self.freshness_decay = 1.0
            self.input_coverage = 1.0
            self.algorithm_version = "v1"
            self.feature_schema_hash = "abc"
            self.weight_profile = {}
            self.warnings = []
            self.computed_at = __import__("datetime").datetime.utcnow()
            self.valid_until = self.computed_at

        def model_dump(self):
            return {
                "district_id": self.district_id,
                "risk_score": self.risk_score,
                "alert_tier": self.alert_tier,
                "top_drivers": self.top_drivers,
                "feature_values": self.feature_values,
                "freshness_decay": self.freshness_decay,
                "input_coverage": self.input_coverage,
                "algorithm_version": self.algorithm_version,
                "feature_schema_hash": self.feature_schema_hash,
                "weight_profile": self.weight_profile,
                "warnings": self.warnings,
                "computed_at": self.computed_at,
                "valid_until": self.valid_until,
            }

    calls = {"compute": []}

    monkeypatch.setattr("backend.core.zones.get_all_zone_ids", lambda: ["a", "b", "c"])

    async def _cached(did):
        if did == "a":
            return _FakeScore("a", 0.2)
        return None

    async def _compute(did, persist=False):
        calls["compute"].append((did, persist))
        return _FakeScore(did, 0.5)

    async def _set_cached(_score):
        return None

    monkeypatch.setattr(risk, "_get_cached", _cached)
    monkeypatch.setattr(risk, "_set_cached", _set_cached)
    monkeypatch.setattr(risk, "compute_risk_score", _compute)

    out = await risk.get_all_risk_scores()
    assert len(out) == 3
    assert [c[0] for c in calls["compute"]] == ["b", "c"]
    assert all(persist is False for _, persist in calls["compute"])
