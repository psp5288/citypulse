from backend.services.postgres_service import create_alert, create_event
from backend.services.redis_service import check_alert_dedup, set_alert_dedup
from backend.core.logger import logger

RULES = [
    {
        "key": "crowd_high",
        "condition": lambda s: s.get("crowd_density", 0) > 0.85,
        "severity": "critical",
        "title": lambda s: f"Crowd surge — {s.get('name', s.get('id', '?'))}",
        "description": lambda s: f"Crowd density reached {s.get('crowd_density', 0)*100:.0f}% — above 85% threshold. {s.get('summary', '')}",
        "cooldown_minutes": 15,
    },
    {
        "key": "safety_critical",
        "condition": lambda s: s.get("safety_risk", 0) > 0.70,
        "severity": "critical",
        "title": lambda s: f"Safety risk elevated — {s.get('name', s.get('id', '?'))}",
        "description": lambda s: f"Safety risk: {s.get('safety_risk', 0)*100:.0f}%. Flags: {', '.join(s.get('flags', []))}",
        "cooldown_minutes": 15,
    },
    {
        "key": "sentiment_drop",
        "condition": lambda s: s.get("sentiment_score", 1) < 0.35,
        "severity": "warning",
        "title": lambda s: f"Negative sentiment spike — {s.get('name', s.get('id', '?'))}",
        "description": lambda s: f"Sentiment dropped to {s.get('sentiment_score', 0)*100:.0f}%. {s.get('summary', '')}",
        "cooldown_minutes": 30,
    },
    {
        "key": "weather_severe",
        "condition": lambda s: s.get("weather_impact", 0) > 0.70,
        "severity": "warning",
        "title": lambda s: f"Severe weather disruption — {s.get('name', s.get('id', '?'))}",
        "description": lambda s: f"Weather impact: {s.get('weather_impact', 0)*100:.0f}%. {s.get('summary', '')}",
        "cooldown_minutes": 60,
    },
]


async def evaluate_rules(scores: dict):
    district_id = scores.get("id", "")

    for rule in RULES:
        if not rule["condition"](scores):
            continue

        already = await check_alert_dedup(district_id, rule["key"])
        if already:
            continue

        alert_id = await create_alert({
            "severity": rule["severity"],
            "title": rule["title"](scores),
            "description": rule["description"](scores),
            "district_id": district_id,
            "status": "open",
        })

        await create_event(
            "alert", district_id,
            rule["title"](scores),
            {"alert_id": alert_id, "rule": rule["key"]},
        )

        await set_alert_dedup(district_id, rule["key"], rule["cooldown_minutes"])
        logger.warning(f"Alert fired: {rule['key']} for {district_id}")
