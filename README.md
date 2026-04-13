# City Pulse

Real-time urban intelligence: public signals (social, traffic, weather, events) are fused per **district**, scored with **IBM WatsonX**, cached in **Redis**, historized in **PostgreSQL**, with optional **Kafka** ingestion and **JWT** auth.

## Quick start (local)

1. Copy env and set `WATSONX_API_KEY`, `WATSONX_PROJECT_ID` (and `JWT_SECRET` for auth):

   ```bash
   cp .env.example .env
   ```

2. Start infrastructure:

   ```bash
   docker compose up -d postgres redis zookeeper kafka kafka-ui
   ```

3. Python 3.11+ and venv:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn backend.main:app --reload --port 8000
   ```

4. Open [http://localhost:8000/](http://localhost:8000/) (landing), [http://localhost:8000/dashboard](http://localhost:8000/dashboard) (live dashboard), [http://localhost:8000/simulator](http://localhost:8000/simulator) (Oracle swarm simulator), [http://localhost:8000/analytics](http://localhost:8000/analytics) (analytics page), [http://localhost:8000/docs](http://localhost:8000/docs).

## API (summary)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/districts` | Live district scores (Redis) |
| GET | `/api/districts/{id}` | Detail + last 10 snapshots |
| GET | `/api/districts/snapshots` | Historical points (`from`, `to`, `district`) |
| WS | `/ws/districts` | Push `districts_update` + server `ping` every 30s |
| GET | `/api/analytics?range=1h\|6h\|24h\|7d` | Chart series + KPIs |
| GET | `/api/alerts` | Filter by `status`, `severity` |
| POST | `/api/alerts/{id}/resolve` | Resolve alert |
| GET | `/api/events` | Feed items |
| GET | `/api/logs` | Recent log lines |
| POST | `/api/simulate` | Start Oracle swarm simulation |
| GET | `/api/simulate/{simulation_id}` | Poll simulation status/result |
| GET | `/api/simulate/history` | Recent simulation runs |
| POST | `/api/auth/login`, `/register`, `/refresh` | JWT |

## Oracle swarm monitor

- The Oracle page (`/simulator`) now includes a minimal live monitor while a run is in progress.
- Live UI elements:
  - Progress bar with processed agent count
  - Action breakdown chips (`share`, `amplify`, `counter`, `ignore`, etc.)
  - Prompt/filter bar to inspect live swarm actions
  - Rolling recent actions panel (archetype, action, sentiment, reasoning)
- Backend now persists running telemetry on each batch so polling can render live state instead of only final results.

### Simulation telemetry fields

`GET /api/simulate/{simulation_id}` may now include:

- `progress_pct` - float from `0.0` to `1.0`
- `processed_agents` - number of agents processed so far
- `total_agents` - total agents for this run
- `action_breakdown` - map of action to count
- `recent_actions` - rolling list of recent agent outcomes

## Stack

- **Backend:** FastAPI, `asyncpg`, `redis.asyncio`, `ibm-watson-machine-learning`, `aiokafka`, `python-jose`, `passlib`
- **Frontend:** `frontend/city-pulse.html` (wired dashboard), `frontend/index.html`, `frontend/login.html`, `frontend/assets/style.css`
- **Compose:** `app`, Postgres 15, Redis 7, Zookeeper + Kafka 7.5, Kafka UI on port 8080

## Notes

- Without WatsonX credentials (or if the SDK cannot reach IBM Cloud), scoring uses deterministic **mock** outputs (still drives the map). Health reports `watsonx: false` in that case.
- Kafka consumer runs as a background task; if the broker is down, it logs and continues—district scoring still runs on the timer.
- Database name defaults to `citypulse` (see `.env.example`).
