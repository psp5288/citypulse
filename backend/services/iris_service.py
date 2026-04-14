from __future__ import annotations

import json
from datetime import datetime, timezone

from backend.core.models import IrisEvent, IrisReactionVector
from backend.services.postgres_service import (
    fetch_recent_iris_events,
    save_iris_event,
    upsert_iris_state_cache,
)


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def normalize_signal_event(
    source: str,
    location: str,
    topic: str,
    text: str,
    occurred_at: datetime | None = None,
    engagement: float = 1.0,
    confidence: float = 0.6,
) -> IrisEvent:
    raw = (text or "").lower()
    positive_terms = ("good", "great", "safe", "love", "improve", "success")
    negative_terms = ("bad", "risk", "delay", "unsafe", "angry", "fail", "protest")
    sentiment = 0.0
    for term in positive_terms:
        if term in raw:
            sentiment += 0.2
    for term in negative_terms:
        if term in raw:
            sentiment -= 0.2
    return IrisEvent(
        source=source,
        location=location.lower().strip(),
        topic=topic.lower().strip(),
        sentiment=max(-1.0, min(1.0, sentiment)),
        engagement=max(0.1, float(engagement)),
        confidence=max(0.1, min(1.0, float(confidence))),
        payload={"text": text[:500]},
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )


async def ingest_events(events: list[IrisEvent]) -> None:
    for ev in events:
        await save_iris_event(ev)


def _compute_vector(location: str, topic: str, events: list[dict]) -> IrisReactionVector:
    now = datetime.now(timezone.utc)
    if not events:
        return IrisReactionVector(
            location=location,
            topic=topic,
            sentiment_score=50.0,
            attention_score=5.0,
            stability_score=50.0,
            trust_score=40.0,
            novelty_score=45.0,
            reaction_score=38.0,
            confidence=0.25,
            volume=0,
            freshness_seconds=9999,
            as_of=now,
        )

    sentiments = [float(e.get("sentiment", 0)) for e in events]
    engagements = [float(e.get("engagement", 1)) for e in events]
    confidences = [float(e.get("confidence", 0.5)) for e in events]
    latest = max(datetime.fromisoformat(e["occurred_at"]) for e in events if e.get("occurred_at"))

    sentiment_score = _clamp((sum(sentiments) / len(sentiments) + 1) * 50)
    attention_score = _clamp(min(100.0, sum(engagements) * 2.5))
    sentiment_var = sum(abs(s - (sum(sentiments) / len(sentiments))) for s in sentiments) / len(sentiments)
    stability_score = _clamp(100 - sentiment_var * 100)
    trust_score = _clamp((sum(confidences) / len(confidences)) * 100)
    novelty_score = _clamp(20 + min(80, len(events) * 1.4))
    reaction_score = _clamp(
        sentiment_score * 0.30
        + attention_score * 0.25
        + stability_score * 0.15
        + trust_score * 0.20
        + novelty_score * 0.10
    )
    freshness = int((now - latest).total_seconds())
    confidence = max(0.2, min(0.98, (trust_score / 100) * min(1.0, len(events) / 40)))

    return IrisReactionVector(
        location=location,
        topic=topic,
        sentiment_score=round(sentiment_score, 2),
        attention_score=round(attention_score, 2),
        stability_score=round(stability_score, 2),
        trust_score=round(trust_score, 2),
        novelty_score=round(novelty_score, 2),
        reaction_score=round(reaction_score, 2),
        confidence=round(confidence, 3),
        volume=len(events),
        freshness_seconds=max(0, freshness),
        as_of=now,
    )


async def get_iris_state(location: str, topic: str, lookback_hours: int = 24) -> IrisReactionVector:
    rows = await fetch_recent_iris_events(location=location, topic=topic, lookback_hours=lookback_hours)
    vector = _compute_vector(location=location, topic=topic, events=rows)
    await upsert_iris_state_cache(f"{location.lower()}::{topic.lower()}", json.loads(vector.model_dump_json()))
    return vector


async def get_iris_trend(location: str, topic: str, buckets: int = 12, lookback_hours: int = 24) -> dict:
    rows = await fetch_recent_iris_events(location=location, topic=topic, lookback_hours=lookback_hours)
    if not rows:
        return {"labels": [], "reaction": [], "sentiment": [], "attention": []}

    # Small MVP bucketing: fixed-size chunks from historical list.
    rows_sorted = sorted(rows, key=lambda r: r.get("occurred_at", ""))
    chunk = max(1, len(rows_sorted) // buckets)
    labels: list[str] = []
    reaction: list[float] = []
    sentiment: list[float] = []
    attention: list[float] = []

    for i in range(0, len(rows_sorted), chunk):
        group = rows_sorted[i:i + chunk]
        if not group:
            continue
        ts = group[-1].get("occurred_at")
        labels.append(ts[11:16] if ts else f"t{i}")
        vec = _compute_vector(location, topic, group)
        reaction.append(vec.reaction_score)
        sentiment.append(vec.sentiment_score)
        attention.append(vec.attention_score)
        if len(labels) >= buckets:
            break
    return {"labels": labels, "reaction": reaction, "sentiment": sentiment, "attention": attention}
