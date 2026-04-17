from backend.services.backtest_service import _compute_metrics


def test_backtest_metrics_include_calibration_and_probabilistic_scores():
    preds = []
    for i in range(20):
        score = i / 20
        event = score >= 0.5
        preds.append(
            {
                "risk_score": score,
                "sentiment_delta": -20.0 if event else 5.0,
                "significant_event": event,
                "features": {
                    "sentiment_velocity": score,
                    "source_consensus": score,
                    "volume_spike": score,
                    "weather_stress": 0.2,
                    "event_density": 0.2,
                    "geo_spillover": score,
                    "time_of_day": 0.5,
                },
            }
        )

    m = _compute_metrics(preds)
    assert "brier_score" in m
    assert "ece" in m
    assert "tier_metrics" in m
    assert m["brier_score"] >= 0.0
    assert m["ece"] >= 0.0
