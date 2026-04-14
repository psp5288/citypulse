import asyncio
import json
import logging
import random
import re

from backend.config import settings

logger = logging.getLogger(__name__)

_watsonx_available = False


def _try_import_watsonx():
    global _watsonx_available
    try:
        from ibm_watson_machine_learning.foundation_models import Model
        _watsonx_available = True
        return Model
    except ImportError:
        logger.warning("ibm-watson-machine-learning not installed — using mock scoring")
        return None


def _get_model():
    Model = _try_import_watsonx()
    if not Model or not settings.watsonx_api_key:
        return None
    return Model(
        model_id=settings.watsonx_model_id,
        credentials={"apikey": settings.watsonx_api_key, "url": settings.watsonx_url},
        project_id=settings.watsonx_project_id,
        params={"max_new_tokens": 512, "temperature": 0.3},
    )


SYSTEM_DISTRICT_PROMPT = """
You are an urban intelligence scoring engine for City Pulse.

Given structured data about a city district, return ONLY a valid JSON object
with exactly these keys:

- crowd_density (float 0-1): estimated crowd level based on posts, events, traffic
- sentiment_score (float 0-1): public mood — 0 = very negative, 1 = very positive
- safety_risk (float 0-1): risk level — 0 = very safe, 1 = high risk
- weather_impact (float 0-1): weather disruption level — 0 = none, 1 = severe
- confidence (float 0-1): your confidence given the data completeness
- summary (string, max 100 chars): one-line human-readable status
- flags (array of strings, max 3): notable issues to surface

Return ONLY the JSON object. No markdown. No explanation. No code fences.
Invalid JSON will break the system.
"""


def _parse_json_response(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Could not parse WatsonX response: {raw[:200]}")


_CHICAGO_DISTRICT_BASE = {
    "downtown": (0.85, 0.55, 0.68, 0.15),
    "midtown": (0.70, 0.65, 0.45, 0.10),
    "harbor": (0.62, 0.72, 0.35, 0.25),
    "arts": (0.55, 0.80, 0.20, 0.10),
    "financial": (0.42, 0.60, 0.25, 0.08),
    "westside": (0.30, 0.85, 0.12, 0.05),
    "university": (0.58, 0.75, 0.28, 0.12),
    "market": (0.76, 0.46, 0.58, 0.20),
}


def _mock_district_score(district_id: str, context: dict) -> dict:
    crowd, sent, risk, weather = _CHICAGO_DISTRICT_BASE.get(
        district_id, (0.5, 0.5, 0.3, 0.15)
    )

    def j(v: float) -> float:
        return max(0.0, min(1.0, v + (random.random() - 0.5) * 0.1))

    n_posts = len(context.get("social_posts", []))
    n_events = len(context.get("events", []))
    flags = []
    if crowd > 0.8:
        flags.append("high_density")
    if risk > 0.5:
        flags.append("elevated_risk")
    if n_events > 3:
        flags.append("event_surge")

    return {
        "crowd_density": j(crowd),
        "sentiment_score": j(sent),
        "safety_risk": j(risk),
        "weather_impact": j(weather),
        "confidence": 0.6 + random.random() * 0.3,
        "summary": f"{district_id} — crowd {int(crowd * 100)}%, {'elevated' if risk > 0.5 else 'normal'} risk",
        "flags": flags[:3],
    }


def _normalize_district_scores(scores: dict) -> dict:
    scores.setdefault("crowd_density", 0.5)
    scores.setdefault("sentiment_score", 0.5)
    scores.setdefault("safety_risk", 0.3)
    scores.setdefault("weather_impact", 0.2)
    scores.setdefault("confidence", 0.5)
    scores.setdefault("summary", "Scored by WatsonX")
    scores.setdefault("flags", [])
    for key in ["crowd_density", "sentiment_score", "safety_risk", "weather_impact", "confidence"]:
        scores[key] = max(0.0, min(1.0, float(scores[key])))
    if not isinstance(scores["flags"], list):
        scores["flags"] = []
    scores["flags"] = [str(f) for f in scores["flags"][:3]]
    return scores


async def score_district(district_id: str, context: dict) -> dict:
    """City Pulse district scoring via WatsonX (crowd, sentiment, risk, weather, flags)."""
    user_content = f"""District: {context.get("district_name", district_id)}

Social posts (last 25 mentions):
{json.dumps(context.get("social_posts", [])[:25], indent=2)}

Current weather:
{json.dumps(context.get("weather", {}), indent=2)}

Upcoming events (next 6h):
{json.dumps(context.get("events", [])[:15], indent=2)}

Traffic conditions:
{json.dumps(context.get("traffic", {}), indent=2)}

Score this district now."""

    try:
        model = _get_model()
        if not model:
            return _mock_district_score(district_id, context)

        prompt = f"{SYSTEM_DISTRICT_PROMPT}\n\n{user_content}"
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_text(prompt))
        scores = _parse_json_response(response)
        scores = _normalize_district_scores(scores)
        logger.info(
            "WatsonX scored %s: crowd=%.2f risk=%.2f",
            district_id,
            scores["crowd_density"],
            scores["safety_risk"],
        )
        return scores
    except Exception as e:
        logger.error("WatsonX scoring failed for %s: %s", district_id, e)
        return _mock_district_score(district_id, context)


async def score_zone(zone_id: str, zone_name: str, posts: list, news: list) -> dict | None:
    """Score a zone using WatsonX NLP. Returns raw score dict."""
    prompt = f"""You are an urban intelligence scoring system.
Analyze the following social data for the zone "{zone_name}" and return ONLY a JSON object.

Social media posts (last 30 min):
{json.dumps(posts[:20], indent=2)}

Recent news headlines:
{json.dumps(news[:10], indent=2)}

Return ONLY this JSON with no other text:
{{
  "crowd_density": <float 0.0-1.0>,
  "sentiment_score": <float 0.0-1.0, where 1=very positive>,
  "safety_risk": <float 0.0-1.0, where 1=high risk>,
  "reactivity": <float 0.0-1.0>,
  "summary": "<one sentence describing the zone mood>"
}}"""

    try:
        model = _get_model()
        if not model:
            return _mock_zone_score(zone_id)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_text(prompt))
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        logger.info(f"WatsonX scored zone {zone_id}: sentiment={result.get('sentiment_score', 0):.2f}")
        return result
    except Exception as e:
        logger.error(f"WatsonX score_zone failed for {zone_id}: {e}")
        return _mock_zone_score(zone_id)


async def agent_react(
    agent_profile: dict,
    news_item: str,
    rumour: str = None,
    social_context: list[str] | None = None,
) -> dict:
    """Run a single swarm agent reaction through WatsonX.

    social_context: list of short strings summarising what influential agents in
    the previous cascade round said. Used for Round 2 (passive/skeptic) and
    Round 3 (institutional) to simulate information cascading.
    """
    rumour_line = f"\nYou have also heard this rumour: {rumour}" if rumour else ""
    context_block = ""
    if social_context:
        sample = social_context[:8]   # cap to keep prompt short
        context_block = (
            "\n\nYou have also seen these reactions from others in your network:\n"
            + "\n".join(f"- {s}" for s in sample)
        )

    prompt = f"""You are a {agent_profile['archetype']} person living in {agent_profile['zone']}.
Your political lean is {agent_profile['political_lean']} (scale: -1=far left, 1=far right).
Your trust in media is {agent_profile['media_trust']} (scale: 0=none, 1=full).
You have just read this news: {news_item}{rumour_line}{context_block}

How do you react? Return ONLY this JSON with no other text:
{{
  "sentiment": "<positive|negative|neutral>",
  "action": "<share|ignore|counter|amplify>",
  "intensity": <float 0.0-1.0>,
  "reasoning": "<one sentence>"
}}"""

    try:
        model = _get_model()
        if not model:
            return _mock_agent_react(agent_profile, social_context=social_context)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: model.generate_text(prompt))
        clean = response.strip().replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
        result["agent_id"] = agent_profile["agent_id"]
        result["archetype"] = agent_profile["archetype"]
        result["network_size"] = agent_profile.get("network_size", 50)
        result["reaction_delay_minutes"] = agent_profile.get("reaction_delay_minutes", 60)
        return result
    except Exception as e:
        logger.warning(f"Agent {agent_profile['agent_id']} WatsonX call failed: {e}")
        return _mock_agent_react(agent_profile, social_context=social_context)


async def health_check() -> bool:
    if not settings.watsonx_api_key or not settings.watsonx_project_id:
        return False
    try:
        model = _get_model()
        if not model:
            return False
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: model.generate_text("Reply with the word OK and nothing else."),
        )
        return "ok" in (resp or "").lower()
    except Exception:
        return False


# ── Mock fallbacks (used when WatsonX key not set) ───────────────────────────

_ZONE_BASE = {
    "nyc-manhattan":    (0.82, 0.42, 0.71, 0.68),
    "nyc-brooklyn":     (0.65, 0.60, 0.48, 0.52),
    "nyc-queens":       (0.58, 0.66, 0.38, 0.44),
    "nyc-bronx":        (0.74, 0.38, 0.72, 0.61),
    "nyc-statenisland": (0.41, 0.70, 0.28, 0.33),
    "nyc-harlem":       (0.69, 0.50, 0.62, 0.57),
    "nyc-lowereast":    (0.76, 0.55, 0.55, 0.65),
    "nyc-flushing":     (0.60, 0.63, 0.41, 0.48),
}

_SUMMARIES = {
    "nyc-manhattan":    "High activity near transit hubs; mixed sentiment with elevated risk signals.",
    "nyc-brooklyn":     "Moderate crowd levels; generally positive neighbourhood mood.",
    "nyc-queens":       "Steady foot traffic; community sentiment trending upward.",
    "nyc-bronx":        "Dense crowd signals; elevated safety concerns in key corridors.",
    "nyc-statenisland": "Lower density; calm conditions with institutional trust dominant.",
    "nyc-harlem":       "Active social scene; polarised sentiment around local developments.",
    "nyc-lowereast":    "High reactivity zone; early adopters amplifying breaking stories.",
    "nyc-flushing":     "Busy commercial activity; community cohesion holding steady.",
}


def _mock_zone_score(zone_id: str) -> dict:
    crowd, sent, risk, react = _ZONE_BASE.get(zone_id, (0.5, 0.5, 0.4, 0.5))
    jitter = lambda v: max(0.0, min(1.0, v + (random.random() - 0.5) * 0.12))
    return {
        "crowd_density": round(jitter(crowd), 3),
        "sentiment_score": round(jitter(sent), 3),
        "safety_risk": round(jitter(risk), 3),
        "reactivity": round(jitter(react), 3),
        "summary": _SUMMARIES.get(zone_id, "Zone data analysed."),
    }


def _mock_agent_react(agent_profile: dict, social_context: list[str] | None = None) -> dict:
    archetype = agent_profile.get("archetype", "passive_consumer")
    sentiments = {
        "emotional_reactor": ["negative", "positive"],
        "amplifier": ["negative", "positive", "positive"],
        "contrarian": ["positive", "neutral"],
        "passive_consumer": ["neutral", "neutral", "negative"],
        "skeptic": ["neutral", "negative"],
        "early_adopter": ["positive", "negative"],
        "institutional": ["neutral", "neutral"],
    }
    actions = {
        "emotional_reactor": "share",
        "amplifier": "amplify",
        "contrarian": "counter",
        "passive_consumer": "ignore",
        "skeptic": "ignore",
        "early_adopter": "share",
        "institutional": "ignore",
    }
    sentiment = random.choice(sentiments.get(archetype, ["neutral"]))

    # Social context nudges passive/skeptic toward prevailing sentiment in Round 2
    if social_context and archetype in ("passive_consumer", "skeptic", "institutional"):
        neg_count = sum(1 for s in social_context if "negative" in s.lower())
        pos_count = sum(1 for s in social_context if "positive" in s.lower())
        if neg_count > pos_count * 1.5:
            sentiment = random.choices(["negative", "neutral"], weights=[0.65, 0.35])[0]
        elif pos_count > neg_count * 1.5:
            sentiment = random.choices(["positive", "neutral"], weights=[0.65, 0.35])[0]

    reasoning = f"{archetype} processed the news through their typical lens."
    if social_context:
        reasoning = f"{archetype} considered the news alongside {len(social_context)} peer reactions."

    return {
        "agent_id": agent_profile["agent_id"],
        "archetype": archetype,
        "sentiment": sentiment,
        "action": actions.get(archetype, "ignore"),
        "intensity": round(random.uniform(0.2, 0.9), 2),
        "reasoning": reasoning,
        "network_size": agent_profile.get("network_size", 50),
        "reaction_delay_minutes": agent_profile.get("reaction_delay_minutes", 60),
    }
