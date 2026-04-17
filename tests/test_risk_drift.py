from backend.services.risk_drift_service import compute_drift_score


def test_compute_drift_score_uses_std_floor():
    score = compute_drift_score(recent_mean=0.9, baseline_mean=0.3, baseline_std=0.0)
    assert score > 1.0
