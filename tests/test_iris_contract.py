from datetime import datetime, timezone

from backend.services.iris_service import normalize_signal_event


def test_iris_event_normalization_contract():
    ev = normalize_signal_event(
        source="reddit",
        location="NYC",
        topic="sports",
        text="Great turnout and good vibes at the sports event!",
        occurred_at=datetime.now(timezone.utc),
        engagement=2.4,
        confidence=0.7,
    )
    payload = ev.model_dump()
    assert payload["source"] == "reddit"
    assert payload["location"] == "nyc"
    assert payload["topic"] == "sports"
    assert -1.0 <= payload["sentiment"] <= 1.0
    assert payload["engagement"] >= 0.1
    assert 0.1 <= payload["confidence"] <= 1.0
