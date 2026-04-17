from datetime import datetime, timezone

from backend.services.postgres_service import _compute_outcome_window


def test_outcome_window_uses_predicted_at_anchor():
    predicted_at = datetime(2026, 4, 1, 10, 30, tzinfo=timezone.utc)
    start, end = _compute_outcome_window(predicted_at, horizon_hours=6, window_hours=1)
    assert start.isoformat() == "2026-04-01T16:30:00+00:00"
    assert end.isoformat() == "2026-04-01T17:30:00+00:00"
