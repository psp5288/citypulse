from backend.services.risk_calibration_service import apply_affine_calibration


def test_affine_calibration_clamps_probability_bounds():
    assert apply_affine_calibration(0.9, alpha=2.0, beta=0.5) == 1.0
    assert apply_affine_calibration(0.1, alpha=0.1, beta=-0.5) == 0.0
