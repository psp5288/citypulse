# FRONTEND.md — UI/UX Specification

## Design Philosophy

DevCity Pulse is a **God's Eye intelligence platform** — the UI must feel like a mission control center. Think:
- NASA/NORAD control room aesthetic
- Dark-first, data-dense but never cluttered
- Real-time signals that feel alive
- IBM design language (IBM Carbon Design System colours)

The UI must feel like you are watching a city breathe.

---

## Design System — Tokens

```css
/* paste into frontend/css/main.css */
:root {
  /* Backgrounds */
  --bg-base:        #0A0F1E;   /* near-black navy — main background */
  --bg-surface:     #131929;   /* card/panel backgrounds */
  --bg-elevated:    #1A2237;   /* hover states, selected items */
  --bg-border:      #1E2D45;   /* subtle borders */

  /* IBM Brand */
  --ibm-blue:       #0F62FE;   /* primary action, selected zones */
  --ibm-blue-light: #4589FF;   /* hover state */
  --ibm-blue-dark:  #0043CE;   /* pressed state */

  /* Status colours */
  --green:          #24A148;   /* safe / positive sentiment */
  --green-light:    #42BE65;
  --yellow:         #F0A500;   /* caution / medium risk */
  --red:            #DA1E28;   /* danger / high risk */
  --red-light:      #FF8389;
  --cyan:           #00D4FF;   /* accent / reactivity / live indicator */
  --purple:         #8A3FFC;   /* simulation / oracle theme */

  /* Text */
  --text-primary:   #FFFFFF;
  --text-secondary: #A8B8CC;
  --text-muted:     #4A5E78;
  --text-accent:    #00D4FF;

  /* Scores → colours mapping */
  --score-low:      #24A148;   /* 0.0–0.33 */
  --score-mid:      #F0A500;   /* 0.33–0.66 */
  --score-high:     #DA1E28;   /* 0.66–1.0 */

  /* Typography */
  --font-display:   'IBM Plex Sans', 'Segoe UI', sans-serif;
  --font-mono:      'IBM Plex Mono', 'Courier New', monospace;

  /* Spacing */
  --gap-xs:  4px;
  --gap-sm:  8px;
  --gap-md:  16px;
  --gap-lg:  24px;
  --gap-xl:  40px;

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;

  /* Transitions */
  --transition: 0.2s ease;
}
```

---

## Pages

### 1. `index.html` — Landing Page

**Purpose:** First impression. Sells the concept in 5 seconds.

**Layout:**
- Full dark background
- Centered hero: large "DevCity Pulse" title in IBM Plex Sans
- Tagline: *"See the pulse. Predict the future."* in cyan
- Two CTA buttons: `[ → Live Dashboard ]`  `[ → Run Simulation ]`
- Subtle animated dot grid in background (CSS animation, no canvas)
- Bottom bar: "IBM SkillBuild Lab · WatsonX AI · April 2026"

**No nav. No sidebar. Pure hero.**

---

### 2. `dashboard.html` — The Eye (Live Map)

**Purpose:** God's Eye view. Main monitoring screen.

**Layout — Three Columns:**

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP BAR: DevCity Pulse logo | LIVE ● | time | alerts badge     │
├────────────┬────────────────────────────────┬───────────────────┤
│  LEFT      │  CENTER — LEAFLET MAP          │  RIGHT            │
│  PANEL     │  (full height, dark tiles)     │  PANEL            │
│  ~280px    │  Coloured zone overlays        │  ~300px           │
│            │  Pulsing rings on hot zones    │                   │
│  Zone list │  Click zone → sidebar update  │  Selected zone    │
│  with live │                               │  detail cards     │
│  scores    │                               │  Score breakdown  │
│            │                               │  Recent posts     │
│            │                               │  summary          │
└────────────┴────────────────────────────────┴───────────────────┘
│  BOTTOM BAR: 8 zone mini-scorecards scrollable horizontally      │
└─────────────────────────────────────────────────────────────────┘
```

**Map spec:**
- Library: Leaflet.js (CDN)
- Tiles: CartoDB Dark Matter — `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
- Starting view: NYC, zoom 11
- Each zone: `L.circle()` with radius proportional to crowd_density
- Zone colour: maps to overall threat level (green → yellow → red)
- Pulsing ring animation: CSS `@keyframes` on circle SVG marker
- Click zone → updates right panel + highlights left panel item

**Left panel — Zone List:**
```
┌──────────────────────────────────┐
│ 🔴 Manhattan          RISK: 0.82 │  ← coloured left bar
│    Sentiment ████░░░░  0.38      │
│    Updated 12s ago               │
├──────────────────────────────────┤
│ 🟡 Brooklyn           RISK: 0.54 │
│    Sentiment ██████░░  0.61      │
│    Updated 8s ago                │
└──────────────────────────────────┘
```

**Right panel — Zone Detail:**
```
┌──────────────────────────────────┐
│  MANHATTAN                 LIVE  │
│  ─────────────────────────────── │
│  Crowd Density    ████████░  0.8 │
│  Sentiment        ████░░░░░  0.4 │
│  Safety Risk      ███████░░  0.7 │
│  Reactivity       ██████░░░  0.6 │
│  ─────────────────────────────── │
│  "High tension signals detected  │
│   around transit hubs. Negative  │
│   sentiment rising."             │
│  ─────────────────────────────── │
│  [ → Run Simulation for zone ]   │
└──────────────────────────────────┘
```

**Bottom bar — Mini scorecards:**
Each zone gets a compact card: name, risk badge, sentiment bar, updated time. Scrolls horizontally on overflow.

**LIVE indicator:** Top bar shows `● LIVE` in blinking cyan. Goes amber if WebSocket disconnects.

**Score → Colour mapping:**
```javascript
function scoreToColor(val, metric) {
  if (metric === 'sentiment_score') {
    // High sentiment = good = green
    if (val > 0.66) return 'var(--green)';
    if (val > 0.33) return 'var(--yellow)';
    return 'var(--red)';
  } else {
    // High risk/density/reactivity = bad = red
    if (val > 0.66) return 'var(--red)';
    if (val > 0.33) return 'var(--yellow)';
    return 'var(--green)';
  }
}
```

---

### 3. `simulator.html` — The Oracle (Swarm Simulation)

**Purpose:** Run predictions. Control panel feel.

**Layout:**

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP BAR: DevCity Pulse | THE ORACLE                            │
├────────────────────────────┬────────────────────────────────────┤
│  LEFT — SIMULATION SETUP   │  RIGHT — RESULTS                   │
│                            │                                    │
│  [ Zone selector ]         │  (empty until sim runs)            │
│  [ Sector selector ]       │  Shows:                            │
│  [ Text area: news item ]  │  - Sentiment donut chart           │
│  [ Agent count slider ]    │  - Virality bar                    │
│  [ + Add External Factor ] │  - Backlash risk                   │
│                            │  - Personality breakdown           │
│  Pre-built scenarios:      │  - Peak reaction time              │
│  [ Banking Crisis ]        │  - vs. Real-time comparison        │
│  [ Policy Announcement ]   │  - Archetype breakdown chart       │
│  [ News Breakout ]         │                                    │
│                            │                                    │
│  [ RUN SIMULATION → ]      │                                    │
└────────────────────────────┴────────────────────────────────────┘
│  BOTTOM — SIMULATION HISTORY TABLE                               │
│  id | zone | news snippet | sentiment | virality | accuracy      │
└─────────────────────────────────────────────────────────────────┘
```

**Simulation control panel spec:**

Zone selector: dropdown populated from `/api/zones`
Sector: radio buttons — General | Banking | Government | News | Crisis
News item: `<textarea>` — 3 rows, monospace font, placeholder: *"Enter news headline or policy statement..."*
Agent count: range slider 100–1000 (default 1000), shows value live
External factors: collapsible section. Add up to 3 factors. Each factor: type dropdown + text field + inject time (minutes)
Scenarios: three preset buttons that auto-fill the form

**Running state:**
When simulation is submitted:
- Button becomes `[ ⏳ Running 0/1000 agents... ]`
- Progress bar fills as agents complete (poll `/api/simulate/:id` every 2s)
- Right panel shows skeleton loaders
- Agent count increments visually

**Results panel spec:**

```
┌──────────────────────────────────────────────────────┐
│  SIMULATION COMPLETE  ✓  Confidence: 84%             │
│  ────────────────────────────────────────────────── │
│  Predicted Sentiment                                  │
│  ████████████████░░░░  Negative  54%                 │
│  ███████████░░░░░░░░░  Positive  28%                 │
│  █████░░░░░░░░░░░░░░░  Neutral   18%                 │
│  ────────────────────────────────────────────────── │
│  Virality Score         ████████░░  0.72             │
│  Risk of Backlash       ███████░░░  0.61             │
│  Peak Reaction          4.2 hours                    │
│  ────────────────────────────────────────────────── │
│  vs. Real-Time Baseline                               │
│  Predicted negative:  54%  │  Actual:  58%           │
│  Delta: 4pp  │  Accuracy: 95.1%                      │
│  ────────────────────────────────────────────────── │
│  Archetype Breakdown                                  │
│  [donut chart of who drove what reaction]             │
└──────────────────────────────────────────────────────┘
```

Charts: use Chart.js (CDN). Donut for sentiment, horizontal bar for virality/risk, radar for archetype breakdown.

---

### 4. `analytics.html` — Historical View

**Purpose:** Time-series analysis, simulation accuracy tracking.

**Layout:**
- Top: date range picker + zone filter
- Main: line chart of zone scores over time (Chart.js, multi-line, one per zone)
- Right sidebar: simulation accuracy leaderboard (which predictions were most accurate)
- Bottom: simulation history table with filter/sort

---

## Navigation

Persistent top bar across all pages:
```
[ DevCity Pulse ]  [ Dashboard ]  [ Simulate ]  [ Analytics ]  [ ● LIVE ]
```

Active page highlighted in IBM blue. Mobile: hamburger collapses to drawer.

---

## Component Patterns

### Score Bar
```html
<div class="score-bar">
  <span class="score-label">Safety Risk</span>
  <div class="score-track">
    <div class="score-fill" style="width: 72%; background: var(--red)"></div>
  </div>
  <span class="score-value">0.72</span>
</div>
```

### Zone Card (left panel)
```html
<div class="zone-card" data-zone="nyc-manhattan" onclick="selectZone(this)">
  <div class="zone-card__bar" style="background: var(--red)"></div>
  <div class="zone-card__content">
    <div class="zone-card__name">Manhattan</div>
    <div class="zone-card__risk">RISK: 0.82</div>
    <div class="score-bar mini">...</div>
    <div class="zone-card__updated">12s ago</div>
  </div>
</div>
```

### Alert Toast
```html
<div class="alert-toast alert-toast--critical">
  <span class="alert-toast__icon">⚠️</span>
  <div>
    <strong>CRITICAL: Manhattan</strong>
    <p>Safety risk at 90% in Manhattan</p>
  </div>
  <button onclick="dismissAlert(this)">✕</button>
</div>
```

### Live Badge
```html
<span class="live-badge">
  <span class="live-dot"></span>
  LIVE
</span>
```
```css
.live-dot {
  width: 8px; height: 8px;
  background: var(--cyan);
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50%       { opacity: 0.4; transform: scale(0.8); }
}
```

---

## WebSocket Integration (dashboard.js)

```javascript
let ws;
let reconnectAttempts = 0;

function connectWebSocket() {
  ws = new WebSocket(`ws://${location.host}/ws/zones`);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'zone_update') {
      updateAllZones(data.zones);
      updateLastRefreshedTime();
    }
    if (data.type === 'alert') {
      showAlertToast(data.alert);
    }
  };

  ws.onclose = () => {
    setLiveBadgeDisconnected();
    // Exponential backoff reconnect
    setTimeout(connectWebSocket, Math.min(30000, 1000 * 2 ** reconnectAttempts++));
  };

  ws.onopen = () => {
    setLiveBadgeConnected();
    reconnectAttempts = 0;
  };
}

function updateAllZones(zones) {
  zones.forEach(zone => {
    updateZoneCard(zone);
    updateMapCircle(zone);
    if (selectedZoneId === zone.zone_id) {
      updateDetailPanel(zone);
    }
  });
  updateBottomBar(zones);
}
```

---

## Mobile Responsiveness

- Below 768px: collapse left and right panels, show map full width
- Bottom scorecards scroll horizontally (touch-enabled)
- Simulator: stack form on top, results below (single column)
- Navigation: hamburger → slide-in drawer
- Min font size: 14px. No text below 12px on mobile.

---

## External Libraries (CDN only — no npm, no build step)

```html
<!-- Leaflet.js (map) -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<!-- Chart.js (charts) -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.2/dist/chart.umd.min.js"></script>

<!-- IBM Plex Sans font -->
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono&family=IBM+Plex+Sans:wght@300;400;600;700&display=swap" rel="stylesheet">
```

---

## DO NOT

- No React, Vue, or any JS framework
- No Tailwind (write CSS from scratch using the design tokens above)
- No Bootstrap
- No light mode (this is a mission-control tool, always dark)
- No stock chart libraries with built-in colour schemes (use Chart.js and set colours manually to match our palette)
- No placeholder images or stock photos
- No emoji in production UI (only in code comments/docs)
