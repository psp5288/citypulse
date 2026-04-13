# WATSONX.md — IBM WatsonX Integration Guide

## Model Selection

| Task | Model | Why |
|---|---|---|
| Zone NLP scoring | `ibm/granite-13b-chat-v2` | Fast, structured output, good JSON adherence |
| Swarm agent reactions | `ibm/granite-13b-chat-v2` | Same model, consistent personality simulation |
| WatsonX Assistant | Configure separately in IBM Cloud console | Conversational queries |

Do NOT use GPT, Claude, or Gemini models. WatsonX only.

---

## Authentication

```python
from ibm_watson_machine_learning.foundation_models import Model

credentials = {
    "apikey": settings.watsonx_api_key,
    "url": settings.watsonx_url       # "https://us-south.ml.cloud.ibm.com"
}

model = Model(
    model_id=settings.watsonx_model_id,
    credentials=credentials,
    project_id=settings.watsonx_project_id,
    params={
        "max_new_tokens": 512,
        "temperature": 0.3,            # Low temp = more consistent JSON
        "repetition_penalty": 1.1,
        "stop_sequences": ["```"],     # Stop if model wraps output in code blocks
    }
)
```

---

## Prompt Engineering Rules

The Granite model responds well to these patterns:

1. **Always say "Return ONLY JSON"** — the model will still sometimes add preamble, so also strip it in code
2. **Give the exact schema** — don't say "return a JSON with scores", show the exact keys and value ranges
3. **Low temperature (0.3)** — higher temps cause hallucinated fields and malformed JSON
4. **Add `stop_sequences: ["```"]`** — prevents the model wrapping JSON in markdown fences

**Stripping output (always do this):**
```python
def parse_json_response(response: str) -> dict:
    clean = response.strip()
    clean = clean.replace("```json", "").replace("```", "")
    clean = clean.strip()
    # Find the first { and last } to extract JSON even if there's preamble
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON found in response: {response[:100]}")
    return json.loads(clean[start:end])
```

---

## Rate Limits & Batching

WatsonX free tier (SkillBuild credits) limits:
- ~20 requests/minute sustained
- ~1000 requests/day

**For zone scoring (8 zones × every 30s):**
- 8 calls per cycle = 16/min = fine
- Space out with `asyncio.sleep(1)` between zone calls if hitting limits

**For swarm simulation (1000 agents):**
- Batch in groups of 50 using `asyncio.gather`
- Add `asyncio.sleep(3)` between batches
- Total time for 1000 agents: ~3-5 minutes (acceptable for background task)
- If credits are low, set `n_agents=100` for demo, scale to 1000 for submission

```python
# Batched swarm execution
async def run_swarm_batched(agents: list, news_item: str, batch_size: int = 50):
    results = []
    for i in range(0, len(agents), batch_size):
        batch = agents[i:i + batch_size]
        batch_results = await asyncio.gather(*[
            agent_react(agent, news_item) for agent in batch
        ])
        results.extend(batch_results)
        await asyncio.sleep(3)  # Rate limit breathing room
    return results
```

---

## WatsonX Assistant (Week 3)

Create a WatsonX Assistant instance in IBM Cloud console:

1. Go to IBM Cloud → WatsonX Assistant → Create instance
2. Create an assistant called "DevCity Oracle"
3. Add intents:
   - `query_simulation` — "What would happen if..."
   - `query_zone` — "What's the sentiment in..."
   - `run_prediction` — "Predict how... would react to..."
4. Add webhook to your FastAPI backend at `/api/assistant`
5. Embed in dashboard with the provided JS snippet

**Assistant webhook endpoint:**
```python
@router.post("/assistant")
async def assistant_query(body: dict):
    user_query = body.get("input", {}).get("text", "")
    # Parse intent and call appropriate service
    # Return WatsonX Assistant-compatible response format
    return {
        "output": {
            "generic": [{"response_type": "text", "text": result}]
        }
    }
```

---

## Fallback Strategy

When WatsonX is unavailable (quota exceeded, network error):

```python
FALLBACK_ZONE_SCORE = {
    "crowd_density": 0.5,
    "sentiment_score": 0.5,
    "safety_risk": 0.5,
    "reactivity": 0.5,
    "summary": "Score unavailable — showing cached data."
}

async def score_zone_with_fallback(zone_id, zone_name, posts, news):
    try:
        return await score_zone(zone_id, zone_name, posts, news)
    except Exception as e:
        logger.warning(f"WatsonX unavailable for {zone_id}, using fallback: {e}")
        cached = await get_zone_score(zone_id)
        if cached:
            cached["stale"] = True
            return cached
        return {**FALLBACK_ZONE_SCORE, "stale": True}
```
