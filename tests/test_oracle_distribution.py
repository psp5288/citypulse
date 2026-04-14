from backend.services.oracle_forecast_service import _distribution_from_prior


def test_distribution_sums_to_one():
    dist = _distribution_from_prior(73, 65, analog_boost=0.05)
    total = dist["positive"] + dist["neutral"] + dist["negative"]
    assert 0.99 <= total <= 1.01
