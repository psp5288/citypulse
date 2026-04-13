# ROADMAP.md — 4-Week Build Plan

**Deadline: End of April 2026**
**Current phase: WEEK 1**

---

## Week 1 — Real-Time Layer (The Eye)
**Goal: Live city map with real WatsonX scores updating every 30s**

### Day 1–2: Foundation
- [ ] `git init`, push to GitHub, create `dev` branch
- [ ] `docker compose up` — PostgreSQL + Redis running locally
- [ ] `backend/config.py` — Settings class, reads .env
- [ ] `backend/core/models.py` — All Pydantic schemas
- [ ] `backend/core/zones.py` — 8 NYC zone definitions
- [ ] `backend/core/archetypes.py` — Personality archetype library
- [ ] `backend/services/redis_service.py` — init, get/set zone scores
- [ ] `backend/services/postgres_service.py` — init_db, save snapshot
- [ ] Verify: `docker compose up && python -m pytest backend/tests/test_db.py`

### Day 3–4: WatsonX + Social Ingestion
- [ ] `backend/services/watsonx_service.py` — score_zone(), health_check()
- [ ] Test WatsonX connection: run score_zone with 5 dummy posts → confirm JSON response
- [ ] `backend/services/social_service.py` — fetch_reddit_posts(), fetch_news_feed()
- [ ] Wire: score_all_zones() calls Reddit → WatsonX → Redis
- [ ] Run manually: `python -c "import asyncio; from backend.services.social_service import score_all_zones; asyncio.run(score_all_zones())"`
- [ ] Confirm: 8 zone scores appear in Redis

### Day 5–7: API + Frontend
- [ ] `backend/routers/zones.py` — GET /api/zones + WS /ws/zones
- [ ] `backend/main.py` — FastAPI app, lifespan, CORS, static files
- [ ] `frontend/css/main.css` — full design system (see FRONTEND.md tokens)
- [ ] `frontend/js/api.js` — shared fetch wrapper
- [ ] `frontend/dashboard.html` — Leaflet map, left panel, right panel, bottom bar
- [ ] `frontend/js/map.js` — zone circles, colour mapping, click handlers
- [ ] `frontend/js/dashboard.js` — WebSocket connection, updateAllZones()
- [ ] `frontend/index.html` — landing page

**Week 1 Done When:**
- Open `http://localhost:8000/dashboard.html`
- Map shows NYC with 8 coloured zone circles
- Zone scores update every 30 seconds
- Clicking a zone shows detail in right panel
- LIVE indicator blinks cyan in top bar

---

## Week 2 — Swarm Simulation Engine (The Oracle)
**Goal: POST /api/simulate works end-to-end with 1000 WatsonX agents**

### Day 8–9: Swarm Engine Core
- [ ] `backend/services/personality_pool.py` — generate_personality_pool()
- [ ] Test: generate 1000 agents for nyc-manhattan, verify archetype distribution
- [ ] `backend/services/swarm_engine.py` — run_batch(), run_swarm(), aggregate_results()
- [ ] Test swarm with 20 agents first (cheap, fast) → verify aggregation math

### Day 10–11: Simulation API
- [ ] `backend/routers/simulate.py` — POST /api/simulate, GET /api/simulate/:id
- [ ] `backend/services/postgres_service.py` — save_simulation(), get_simulation(), get_simulation_history()
- [ ] Wire: simulate endpoint → background task → run_swarm → save to DB → return result
- [ ] Test with Postman/curl: POST /api/simulate → poll for completion → get result

### Day 12–14: Simulator Frontend
- [ ] `frontend/simulator.html` — form, results panel, history table
- [ ] `frontend/js/simulator.js` — form submit, progress polling, results rendering
- [ ] Load pre-built scenarios (banking_crisis, policy_announcement, news_breakout)
- [ ] Chart.js: sentiment donut, virality bar, archetype breakdown

**Week 2 Done When:**
- Submit a simulation from the UI
- Progress bar fills as agents complete
- Results appear: sentiment split, virality, backlash risk, peak timing
- History table shows past simulations
- vs. Real-time comparison shows accuracy score

---

## Week 3 — Advanced Features + Sectors
**Goal: External factors, sector scenarios, WatsonX Assistant, accuracy tracking**

### Day 15–16: External Factor Injection
- [ ] Update swarm_engine.py to handle external_factors with inject_at_minute
- [ ] UI: collapsible "Add External Factor" section in simulator
- [ ] Test: run simulation, inject counter_rumour at minute 30, verify sentiment shift
- [ ] Load factor_library.json presets into UI dropdown

### Day 17–18: Sector Scenarios
- [ ] Banking crisis scenario template + test
- [ ] Government policy scenario template + test
- [ ] News breakout scenario template + test
- [ ] Add sector-specific archetype weight overrides (bankers react differently to rate changes)

### Day 19–20: Accuracy Tracking + WatsonX Assistant
- [ ] After simulation: save vs_real_time comparison to DB
- [ ] `frontend/analytics.html` — time-series charts, accuracy leaderboard
- [ ] `frontend/js/analytics.js` — load historical data, Chart.js multi-line
- [ ] `backend/routers/analytics.py` — GET /api/analytics
- [ ] WatsonX Assistant: create instance in IBM Cloud, wire webhook to /api/assistant
- [ ] Embed assistant widget in dashboard.html

### Day 21: Week 3 Polish
- [ ] Alert system: evaluate_zone() after each score, push alerts via WebSocket
- [ ] Alert toast UI in dashboard
- [ ] `backend/routers/alerts.py` — GET /api/alerts

**Week 3 Done When:**
- External factor injection changes simulation outcomes visibly
- 3 sector scenario presets work out of the box
- Analytics page shows 24h time-series for any zone
- WatsonX Assistant answers natural language queries
- Alerts fire when safety_risk > 0.75

---

## Week 4 — Polish, Multi-City, Deploy
**Goal: IBM Cloud deployment, demo video, submission-ready**

### Day 22–23: Multi-City Support
- [ ] Add London zones to zones.py (use BBC RSS feed)
- [ ] Add Chicago zones to zones.py
- [ ] City selector in dashboard top bar (dropdown: NYC / London / Chicago)
- [ ] Map re-centres on city selection

### Day 24–25: IBM Cloud Deployment
- [ ] Containerise: write Dockerfile for FastAPI backend
- [ ] Push to IBM Container Registry
- [ ] Deploy to IBM Code Engine (or Cloud Foundry)
- [ ] Set all env vars via IBM Cloud console
- [ ] Set up IBM Cloud Databases for PostgreSQL (or use Supabase as fallback)
- [ ] Verify: production URL works end-to-end

### Day 26–27: Historical Simulation Replay
- [ ] Store agent-level results in DB (optional, large — only if credits allow)
- [ ] Replay UI: select a past simulation, re-render result screen

### Day 28: Demo Video + Submission
- [ ] Record 3-minute demo video:
  - 0:00 – Intro (what is DevCity Pulse)
  - 0:30 – Live dashboard (show NYC zones pulsing)
  - 1:00 – Run a simulation (banking crisis, watch 1000 agents process)
  - 1:45 – Show results (sentiment split, virality, accuracy)
  - 2:15 – External factor injection demo
  - 2:45 – WatsonX Assistant query
  - 3:00 – IBM Cloud deployment proof
- [ ] Final README polish
- [ ] Submit to IBM SkillBuild Lab portal

---

## Emergency Fallbacks (if behind schedule)

| Feature | Full Version | Demo Version |
|---|---|---|
| Agent count | 1,000 agents | 100 agents (same code, smaller number) |
| Multi-city | NYC + London + Chicago | NYC only |
| WatsonX Assistant | Full integration | Skip, just use REST API |
| Swarm accuracy | Real vs. real-time comparison | Hardcoded demo comparison |
| IBM Cloud deploy | Full Code Engine | Just show running locally |

**Core non-negotiables for IBM judges:**
1. WatsonX is the AI engine (visible in code)
2. Real-time zone scoring works live
3. Swarm simulation runs and produces a result
4. Deployment attempted on IBM Cloud (even if partially)
