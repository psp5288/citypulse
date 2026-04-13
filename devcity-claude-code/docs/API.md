# API.md — All Endpoints & Schemas

## REST Endpoints

### GET /api/zones
Returns live scores for all monitored zones (reads from Redis).

**Response:**
```json
{
  "zones": [
    {
      "zone_id": "nyc-manhattan",
      "zone_name": "Manhattan",
      "city": "New York City",
      "lat": 40.7831,
      "lng": -73.9712,
      "crowd_density": 0.78,
      "sentiment_score": 0.38,
      "safety_risk": 0.71,
      "reactivity": 0.65,
      "summary": "High tension signals near transit hubs. Negative sentiment rising.",
      "scored_at": "2026-04-09T14:32:11Z",
      "stale": false,
      "post_count": 42
    }
  ],
  "count": 8
}
```

---

### WebSocket /ws/zones
Pushes zone updates every 30 seconds to all connected clients.

**Message format:**
```json
{
  "type": "zone_update",
  "zones": [ ...same as GET /api/zones zones array... ],
  "timestamp": "2026-04-09T14:32:11Z"
}
```

**Alert message (pushed when threshold breached):**
```json
{
  "type": "alert",
  "alert": {
    "alert_id": "uuid",
    "zone_id": "nyc-manhattan",
    "zone_name": "Manhattan",
    "alert_type": "safety_critical",
    "message": "CRITICAL: Safety risk at 91% in Manhattan",
    "severity": "critical",
    "triggered_at": "2026-04-09T14:33:01Z",
    "value": 0.91,
    "threshold": 0.90
  }
}
```

---

### POST /api/simulate
Launch a swarm simulation. Returns immediately with `status: "running"`. Poll or use WebSocket for completion.

**Request:**
```json
{
  "zone": "nyc-manhattan",
  "news_item": "Mayor announces 15% property tax increase effective January",
  "sector": "government",
  "n_agents": 1000,
  "external_factors": [
    {
      "type": "counter_rumour",
      "content": "Sources say the increase may be capped at 8%",
      "inject_at_minute": 30
    }
  ]
}
```

**Response (running):**
```json
{
  "simulation_id": "550e8400-e29b-41d4-a716-446655440000",
  "zone": "nyc-manhattan",
  "news_item": "Mayor announces...",
  "sector": "government",
  "n_agents": 1000,
  "status": "running",
  "created_at": "2026-04-09T14:35:00Z"
}
```

---

### GET /api/simulate/{simulation_id}
Fetch simulation status and results.

**Response (complete):**
```json
{
  "simulation_id": "550e8400-...",
  "zone": "nyc-manhattan",
  "news_item": "Mayor announces...",
  "sector": "government",
  "n_agents": 1000,
  "status": "complete",
  "predicted_sentiment": {
    "positive": 0.28,
    "negative": 0.54,
    "neutral": 0.18
  },
  "predicted_virality": 0.72,
  "peak_reaction_time": "4.2 hours",
  "risk_of_backlash": 0.61,
  "confidence": 0.84,
  "vs_real_time": {
    "real_sentiment_negative": 0.58,
    "predicted_negative": 0.54,
    "delta": 0.04,
    "accuracy": "95.1%"
  },
  "created_at": "2026-04-09T14:35:00Z",
  "completed_at": "2026-04-09T14:37:22Z"
}
```

---

### GET /api/simulate/history?limit=20
Returns list of past simulations.

---

### GET /api/alerts
Returns active (unacknowledged) alerts sorted by severity.

---

### GET /api/analytics?zone_id=nyc-manhattan&hours=24
Returns time-series snapshots for a zone.

**Response:**
```json
{
  "zone_id": "nyc-manhattan",
  "hours": 24,
  "snapshots": [
    {
      "scored_at": "2026-04-09T13:00:00Z",
      "crowd_density": 0.62,
      "sentiment_score": 0.55,
      "safety_risk": 0.41,
      "reactivity": 0.48
    }
  ]
}
```

---

### GET /api/health
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "services": {
    "watsonx": true,
    "redis": true,
    "postgres": true,
    "reddit": true
  }
}
```
