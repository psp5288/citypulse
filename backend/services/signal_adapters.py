from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class AdapterResult:
    source: str
    raw: dict[str, Any]
    events: list[dict[str, Any]]


def to_iris_event(
    *,
    source: str,
    location: str,
    topic: str,
    text: str,
    sentiment: float,
    confidence: float,
    engagement: float = 1.0,
) -> dict[str, Any]:
    return {
        "source": source,
        "location": (location or "unknown").lower(),
        "topic": topic or "early_signals",
        "sentiment": max(-1.0, min(1.0, float(sentiment))),
        "engagement": max(0.0, float(engagement)),
        "confidence": max(0.0, min(1.0, float(confidence))),
        "payload": {"text": text},
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }


def firms_to_events(location: str, data: dict[str, Any]) -> AdapterResult:
    hotspots = int(data.get("wildfire_hotspots", 0) or 0)
    sev = data.get("severity", "low")
    sentiment = -0.55 if sev == "high" else -0.35 if sev == "medium" else -0.15
    events = []
    if data.get("status") == "ok":
        events.append(
            to_iris_event(
                source="nasa_firms",
                location=location,
                topic="geospatial",
                text=f"FIRMS hotspots={hotspots} severity={sev}",
                sentiment=sentiment,
                confidence=0.72,
                engagement=min(4.0, 1.0 + hotspots / 5.0),
            )
        )
    return AdapterResult(source="nasa_firms", raw=data, events=events)


def trends_to_events(location: str, data: dict[str, Any]) -> AdapterResult:
    mentions = int(data.get("trend_mentions", 0) or 0)
    sev = data.get("severity", "low")
    sentiment = -0.25 if sev == "high" else -0.10 if sev == "medium" else 0.05
    events = []
    if data.get("status") == "ok":
        events.append(
            to_iris_event(
                source="google_trends",
                location=location,
                topic="market_nlp",
                text=f"Trends mentions={mentions} severity={sev}",
                sentiment=sentiment,
                confidence=0.64,
                engagement=min(5.0, 1.0 + mentions / 4.0),
            )
        )
    return AdapterResult(source="google_trends", raw=data, events=events)


def comtrade_to_events(location: str, data: dict[str, Any]) -> AdapterResult:
    score = float(data.get("trade_anomaly_score", 0) or 0)
    sev = data.get("severity", "low")
    sentiment = -0.45 if sev == "high" else -0.20 if sev == "medium" else -0.05
    events = []
    if data.get("status") == "ok":
        events.append(
            to_iris_event(
                source="un_comtrade",
                location=location,
                topic="supply_chain",
                text=f"Trade anomaly score={score:.3f} severity={sev}",
                sentiment=sentiment,
                confidence=0.69,
                engagement=1.2 + score * 3.0,
            )
        )
    return AdapterResult(source="un_comtrade", raw=data, events=events)
