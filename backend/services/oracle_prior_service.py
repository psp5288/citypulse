from __future__ import annotations

from backend.core.models import IrisReactionVector


def build_swarm_prior(iris: IrisReactionVector, analogs: list[dict] | None = None) -> dict:
    analogs = analogs or []
    historical_negative = []
    for a in analogs:
        probs = (a.get("result") or {}).get("probabilities") or {}
        if "negative" in probs:
            historical_negative.append(float(probs["negative"]))

    avg_hist_neg = sum(historical_negative) / len(historical_negative) if historical_negative else 0.33
    sentiment_bias = (iris.sentiment_score - 50.0) / 100.0
    attention_bias = (iris.attention_score - 50.0) / 100.0
    volatility = max(0.1, min(1.2, (100 - iris.stability_score) / 100 + abs(sentiment_bias)))

    return {
        "sentiment_bias": round(sentiment_bias, 4),
        "attention_bias": round(attention_bias, 4),
        "historical_negative": round(avg_hist_neg, 4),
        "volatility_multiplier": round(volatility, 4),
        "action_propensity_shift": {
            "amplify": round(max(-0.2, min(0.25, attention_bias * 0.35)), 4),
            "counter": round(max(-0.2, min(0.25, (avg_hist_neg - 0.33) * 0.6)), 4),
        },
        "explain": [
            f"Sentiment bias={sentiment_bias:.2f} from Iris sentiment score {iris.sentiment_score}.",
            f"Attention bias={attention_bias:.2f} from Iris attention score {iris.attention_score}.",
            f"Historical negative prior={avg_hist_neg:.2f} from {len(historical_negative)} analog(s).",
        ],
    }
