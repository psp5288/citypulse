from __future__ import annotations

from backend.services.postgres_service import get_historical_analogs


async def compute_calibration_report(location: str, topic: str) -> dict:
    rows = await get_historical_analogs(location=location, topic=topic, limit=50)
    if not rows:
        return {
            "location": location,
            "topic": topic,
            "sample_size": 0,
            "mean_predicted_negative": None,
            "mean_observed_negative_proxy": None,
            "calibration_gap": None,
            "status": "insufficient_data",
        }

    predicted_neg = []
    observed_proxy = []
    for row in rows:
        probs = (row.get("result") or {}).get("probabilities") or {}
        timeline = (row.get("result") or {}).get("timeline") or []
        if "negative" in probs:
            predicted_neg.append(float(probs["negative"]))
        if timeline:
            # Proxy observation for MVP: normalize max risk_index as observed negativity proxy.
            mx = max(float(t.get("risk_index", 0)) for t in timeline)
            observed_proxy.append(max(0.0, min(1.0, mx / 100)))

    if not predicted_neg or not observed_proxy:
        return {
            "location": location,
            "topic": topic,
            "sample_size": len(rows),
            "mean_predicted_negative": None,
            "mean_observed_negative_proxy": None,
            "calibration_gap": None,
            "status": "insufficient_signal",
        }

    mean_pred = sum(predicted_neg) / len(predicted_neg)
    mean_obs = sum(observed_proxy) / len(observed_proxy)
    gap = mean_pred - mean_obs
    return {
        "location": location,
        "topic": topic,
        "sample_size": len(rows),
        "mean_predicted_negative": round(mean_pred, 4),
        "mean_observed_negative_proxy": round(mean_obs, 4),
        "calibration_gap": round(gap, 4),
        "status": "ok",
    }
