# CLAUDE.md — DevCity Pulse
## Instructions for Claude Code

This file is read automatically by Claude Code at session start.
Read every linked doc in `/docs/` before touching any code.

---

## What This Project Is

**DevCity Pulse** is a God's Eye urban intelligence platform with two pillars:

1. **The Eye** — Real-time social signal monitoring. Ingests Reddit + news feeds per city zone → WatsonX NLP scoring → live map with crowd density, sentiment, safety risk, reactivity scores updating every 30s.

2. **The Oracle** — Swarm AI simulation. 1,000 virtual agents with demographically-calibrated personality archetypes receive a news item → react via WatsonX → produce predicted sentiment split, virality, backlash risk, peak reaction time. External factors (rumours, controversies) can be injected mid-simulation.

**Submission:** IBM SkillBuild Lab — end of April 2026.
**AI Engine:** IBM WatsonX ONLY (no OpenAI, no Claude, no Gemini in production code).

---

## Doc Map — Read These First

| File | Purpose |
|---|---|
| `docs/ARCHITECTURE.md` | Full system architecture, data flow, service map |
| `docs/BACKEND.md` | FastAPI structure, all services, Pydantic models, DB schema |
| `docs/SWARM.md` | Swarm engine deep-dive, personality archetypes, agent prompt templates |
| `docs/WATSONX.md` | WatsonX integration, credentials, model usage, async patterns |
| `docs/FRONTEND.md` | UI/UX spec, design system, all pages, components, colour tokens |
| `docs/DATA.md` | Zone definitions, Reddit subreddits, social ingestion pipeline |
| `docs/API.md` | All endpoints, request/response schemas, WebSocket protocol |
| `docs/ENV.md` | All environment variables, local setup, Docker Compose |
| `docs/ROADMAP.md` | 4-week build order, what to build when, current week tasks |

---

## Tech Stack (non-negotiable)

```
AI:           IBM WatsonX (ibm/granite-13b-chat-v2)
Backend:      Python 3.11 + FastAPI + asyncio
Database:     PostgreSQL (via asyncpg)
Cache:        Redis (via aioredis)
Social data:  PRAW (Reddit) + feedparser (RSS news)
Frontend:     Vanilla HTML/CSS/JS — NO React, NO framework
Deployment:   IBM Cloud (Code Engine or Cloud Foundry)
Dev tools:    Cursor + Claude Code
Version:      GitHub
```

---

## Coding Standards

- All async — use `async/await` everywhere in backend services
- Type hints on every function signature
- Pydantic models for all request/response schemas
- No hardcoded credentials — always from `config.py` which reads `.env`
- Log every WatsonX call with prompt hash, response time, token count
- Every service has a `health_check()` method
- No `print()` — use `logging` module with structured JSON logs
- Error handling: never let a failed zone score crash the whole loop — catch, log, return last known value

---

## File Creation Rules

When creating files, always follow the exact structure in `docs/ARCHITECTURE.md`.
Never create files outside the defined structure without flagging it first.

---

## Current Phase

**WEEK 1 — Real-Time Layer**
See `docs/ROADMAP.md` for exact tasks. Start here:
1. `backend/config.py`
2. `backend/core/zones.py`
3. `backend/services/watsonx_service.py`
4. `backend/services/social_service.py`
5. `backend/services/redis_service.py`
6. `backend/routers/zones.py`
7. `backend/main.py`
8. Wire frontend `dashboard.html` to `/api/zones` + WebSocket

Do not start Week 2 tasks until Week 1 is fully working end-to-end.
