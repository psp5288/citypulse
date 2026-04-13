# ARCHITECTURE.md — DevCity Pulse

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Browser)                                │
│  dashboard.html   simulator.html   analytics.html   index.html          │
│  Vanilla JS · Leaflet.js map · Chart.js · WebSocket client              │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTP + WebSocket
┌──────────────────────────────▼──────────────────────────────────────────┐
│                      FASTAPI BACKEND (Python 3.11)                       │
│                                                                          │
│  /api/zones          /api/simulate         /api/alerts                  │
│  /api/analytics      /ws/zones (WebSocket) /api/simulate/history        │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │ watsonx_svc  │  │ swarm_engine │  │ social_svc   │                  │
│  │ (NLP + agent)│  │ (1000 agents)│  │ (Reddit+RSS) │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                  │                           │
│  ┌──────▼─────────────────▼──────────────────▼───────┐                  │
│  │              redis_service (zone score cache)       │                  │
│  │              postgres_service (history + sims)      │                  │
│  └────────────────────────────────────────────────────┘                  │
└──────────────────────────────────────────────────────────────────────────┘
         │                        │
┌────────▼───────┐      ┌─────────▼──────────┐
│  IBM WatsonX   │      │  External APIs      │
│  watsonx.ai    │      │  Reddit API (PRAW)  │
│  Granite 13B   │      │  News RSS feeds     │
│  WatsonX Asst  │      │  (no auth needed)   │
└────────────────┘      └────────────────────┘
```

---

## Project Folder Structure

```
devcity-pulse/
│
├── CLAUDE.md                        ← Claude Code reads this first
├── README.md                        ← Project overview
├── .env                             ← Local secrets (gitignored)
├── .env.example                     ← Template committed to GitHub
├── .gitignore
├── requirements.txt
├── docker-compose.yml               ← PostgreSQL + Redis local dev
│
├── backend/
│   ├── main.py                      ← FastAPI app, startup, CORS, routers
│   ├── config.py                    ← Settings class, reads .env
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── zones.py                 ← GET /api/zones, WS /ws/zones
│   │   ├── simulate.py              ← POST /api/simulate, GET /api/simulate/:id
│   │   ├── alerts.py                ← GET /api/alerts
│   │   └── analytics.py             ← GET /api/analytics
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── watsonx_service.py       ← All WatsonX calls (NLP + agent)
│   │   ├── swarm_engine.py          ← Swarm orchestration
│   │   ├── personality_pool.py      ← Agent pool generation
│   │   ├── social_service.py        ← Reddit + RSS ingestion
│   │   ├── redis_service.py         ← Zone score cache layer
│   │   └── postgres_service.py      ← DB reads/writes
│   │
│   └── core/
│       ├── __init__.py
│       ├── zones.py                 ← Zone definitions (8 NYC zones)
│       ├── archetypes.py            ← Personality archetype library
│       ├── models.py                ← Pydantic schemas (all of them)
│       └── alert_rules.py           ← Threshold logic
│
├── simulation/
│   ├── scenarios/
│   │   ├── banking_crisis.json
│   │   ├── policy_announcement.json
│   │   └── news_breakout.json
│   └── external_factors/
│       └── factor_library.json
│
├── frontend/
│   ├── index.html                   ← Landing page
│   ├── dashboard.html               ← Live city map (The Eye)
│   ├── simulator.html               ← Swarm control panel (The Oracle)
│   ├── analytics.html               ← Historical charts + accuracy
│   ├── css/
│   │   └── main.css                 ← All styles (see FRONTEND.md)
│   └── js/
│       ├── map.js                   ← Leaflet map + zone overlays
│       ├── dashboard.js             ← WebSocket + score rendering
│       ├── simulator.js             ← Simulation form + results
│       ├── analytics.js             ← Chart.js graphs
│       └── api.js                   ← Shared fetch wrapper
│
└── docs/                            ← Claude Code instruction files
    ├── ARCHITECTURE.md  (this file)
    ├── BACKEND.md
    ├── SWARM.md
    ├── WATSONX.md
    ├── FRONTEND.md
    ├── DATA.md
    ├── API.md
    ├── ENV.md
    └── ROADMAP.md
```

---

## Data Flow — Real-Time Layer (The Eye)

```
Every 30 seconds:

social_service.py
  └── fetch_reddit_posts(zone)       → list of posts (last 30 min)
  └── fetch_news_feed(zone)          → list of headlines

watsonx_service.py
  └── score_zone(zone_id, posts, news)
        └── builds prompt → sends to WatsonX Granite
        └── parses JSON response → ZoneScore object

redis_service.py
  └── set_zone_score(zone_id, score) → cache for 35s TTL

zones router
  └── GET /api/zones → reads all zones from Redis
  └── WS /ws/zones  → pushes new scores every 30s to all connected clients

postgres_service.py
  └── snapshot_zone_scores()         → saves to DB every 5 min (history)
```

## Data Flow — Simulation Layer (The Oracle)

```
User submits form on simulator.html:

POST /api/simulate
  {zone, news_item, sector, n_agents, external_factors[]}

simulate router
  └── creates SimulationRecord in DB (status: "running")
  └── launches background task:

swarm_engine.py
  └── personality_pool.py → generate_pool(zone_demographics, n_agents)
  └── asyncio.gather → run_agent(profile, news_item) × n_agents
        each agent → watsonx_service.agent_react(profile, news_item, rumour)
  └── aggregate_results(agent_responses)
  └── compare_to_realtime(zone_id)
  └── postgres_service.save_simulation(result)
  └── WebSocket push to client: simulation complete

GET /api/simulate/:id → returns result
```

---

## Key Design Decisions

1. **No React** — pure HTML/CSS/JS. Faster to build, easier to demo, no build step.
2. **Background tasks for simulation** — WatsonX calls for 1000 agents take time. Never block the HTTP response. Use FastAPI `BackgroundTasks` + WebSocket notification when done.
3. **Redis as truth for live scores** — PostgreSQL only for history. The map reads Redis, not Postgres.
4. **Batch WatsonX calls** — don't fire 1000 individual API calls. Batch agents in groups of 50 with `asyncio.gather`, respect rate limits.
5. **Zone scores never go null** — if WatsonX fails, serve last cached score with a `stale: true` flag.
