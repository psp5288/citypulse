from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.core.models import OracleForecastRequest, OracleForecastResult
from backend.services.iris_service import get_iris_state
from backend.services.postgres_service import get_historical_analogs, save_oracle_forecast


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _distribution_from_prior(reaction_score: float, sentiment_score: float, analog_boost: float = 0.0) -> dict:
    positivity = _clamp(((reaction_score - 50) / 100) + ((sentiment_score - 50) / 120) + analog_boost, -0.4, 0.4)
    positive = _clamp(0.38 + positivity)
    negative = _clamp(0.34 - positivity * 0.9)
    neutral = _clamp(1.0 - positive - negative)
    total = positive + neutral + negative
    return {
        "positive": round(positive / total, 3),
        "neutral": round(neutral / total, 3),
        "negative": round(negative / total, 3),
    }


def _build_timeline(dist: dict, horizon_hours: int) -> list[dict]:
    now = datetime.now(timezone.utc)
    timeline = []
    for i in range(max(2, horizon_hours)):
        t = now + timedelta(hours=i + 1)
        risk = _clamp(dist["negative"] * 0.75 + (i / max(1, horizon_hours)) * 0.12)
        timeline.append(
            {
                "at": t.isoformat(),
                "expected_positive": round(dist["positive"] * (1 - i * 0.01), 3),
                "expected_negative": round(dist["negative"] * (1 + i * 0.012), 3),
                "risk_index": round(risk * 100, 2),
            }
        )
    return timeline


async def run_oracle_forecast(request: OracleForecastRequest) -> OracleForecastResult:
    iris = await get_iris_state(request.location, request.topic, lookback_hours=24)
    analogs = await get_historical_analogs(request.location, request.topic, limit=8) if request.include_historical_analogs else []
    analog_boost = 0.0
    if analogs:
        negatives = []
        for a in analogs:
            probs = (a.get("result") or {}).get("probabilities") or {}
            if "negative" in probs:
                negatives.append(float(probs["negative"]))
        if negatives:
            avg_neg = sum(negatives) / len(negatives)
            analog_boost = (0.33 - avg_neg) * 0.2

    probs = _distribution_from_prior(iris.reaction_score, iris.sentiment_score, analog_boost=analog_boost)
    timeline = _build_timeline(probs, request.horizon_hours)
    confidence = round(max(0.25, min(0.97, iris.confidence * 0.65 + min(0.25, len(analogs) * 0.02))), 3)
    rationale = [
        f"Iris reaction score in {request.location} for {request.topic} is {iris.reaction_score}/100.",
        f"Current sentiment score is {iris.sentiment_score}/100 with confidence {iris.confidence:.2f}.",
        "Historical analogs were blended into forecast priors." if analogs else "No close historical analogs; forecast relies more on live prior.",
    ]
    payload = {
        "location": request.location,
        "topic": request.topic,
        "scenario_text": request.scenario_text,
        "horizon_hours": request.horizon_hours,
        "reaction_prior": iris.model_dump(mode="json"),
        "probabilities": probs,
        "timeline": timeline,
        "rationale": rationale,
        "confidence": confidence,
        "analogs": analogs[:5],
    }
    forecast_id = await save_oracle_forecast(request.location, request.topic, request.scenario_text, payload)
    return OracleForecastResult(
        forecast_id=forecast_id,
        location=request.location,
        topic=request.topic,
        scenario_text=request.scenario_text,
        horizon_hours=request.horizon_hours,
        reaction_prior=iris,
        probabilities=probs,
        timeline=timeline,
        rationale=rationale,
        confidence=confidence,
        analogs=analogs[:5],
        created_at=datetime.now(timezone.utc),
    )
