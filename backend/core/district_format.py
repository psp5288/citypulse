"""API / WebSocket shaping for district scores (canvas dashboard)."""

from backend.core.districts import DISTRICT_MAP, DISTRICT_POSITIONS


def format_one(score: dict) -> dict:
    did = score.get("id", "")
    meta = DISTRICT_MAP.get(did, {})
    name = score.get("name") or meta.get("name", did)
    pos = DISTRICT_POSITIONS.get(did, {"x": 0.5, "y": 0.5, "r": 45})
    return {
        "id": did,
        "name": name,
        "crowd": float(score.get("crowd_density", 0)),
        "sentiment": float(score.get("sentiment_score", 0)),
        "risk": float(score.get("safety_risk", 0)),
        "events": int(score.get("events_count", 0)),
        "updated_at": score.get("updated_at"),
        "summary": score.get("summary", ""),
        "lat": meta.get("lat"),
        "lon": meta.get("lon"),
        "x": pos["x"],
        "y": pos["y"],
        "r": pos["r"],
    }


def format_many(scores: list[dict]) -> list[dict]:
    return [format_one(s) for s in scores]
