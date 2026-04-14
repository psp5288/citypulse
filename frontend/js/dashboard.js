/* DevCity Pulse — Global monitor: search any location → intel + severity circle */
(function (global) {
  const Api = global.DevCityApi;
  const Map = global.DevCityMap;

  let customLocation = null;
  let searchedPlaces = [];
  let ws;
  let reconnectN = 0;
  let lastUpdateMs = Date.now();

  const $ = (id) => document.getElementById(id);

  /* ── Tiny helpers ──────────────────────────────────────────────────────── */
  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function weatherIcon(condition) {
    const c = (condition || "").toLowerCase();
    if (c.includes("thunder")) return "⛈";
    if (c.includes("snow") || c.includes("blizzard")) return "❄";
    if (c.includes("heavy rain") || c.includes("heavy shower")) return "🌧";
    if (c.includes("rain") || c.includes("drizzle") || c.includes("shower")) return "🌦";
    if (c.includes("fog") || c.includes("mist")) return "🌫";
    if (c.includes("overcast") || c.includes("cloudy")) return "☁";
    if (c.includes("partly") || c.includes("few cloud")) return "⛅";
    return "☀";
  }

  /* ── Clock ─────────────────────────────────────────────────────────────── */
  function updateClock() {
    const now = new Date();
    if ($("topbar-clock")) $("topbar-clock").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if ($("topbar-date"))  $("topbar-date").textContent  = now.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  /* ── WS live badge ─────────────────────────────────────────────────────── */
  function setLive(connected) {
    const badge = $("live-badge");
    if (badge) {
      badge.classList.toggle("disconnected", !connected);
      const lbl = badge.querySelector(".live-label");
      if (lbl) lbl.textContent = connected ? "LIVE" : "OFFLINE";
    }
    const wsPill = $("sys-ws");
    if (wsPill) {
      wsPill.className = "dc-sys-pill " + (connected ? "online" : "offline");
      wsPill.textContent = connected ? "WS ●" : "WS ✕";
    }
  }

  function showToast(alert) {
    let container = $("alert-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "alert-container";
      document.body.appendChild(container);
    }
    const sev = (alert.severity || "medium").toLowerCase();
    const toast = document.createElement("div");
    toast.className = `alert-toast alert-toast--${sev}`;
    toast.innerHTML = `
      <span class="alert-toast__icon">${sev === "critical" ? "🔴" : sev === "high" ? "🟠" : "⚠"}</span>
      <div class="alert-toast__body">
        <div class="alert-toast__title">${esc(alert.title || alert.zone_name || "Alert")}</div>
        <div class="alert-toast__msg">${esc(alert.message || alert.description || "")}</div>
      </div>
      <button class="alert-toast__close" aria-label="dismiss">&times;</button>`;
    toast.querySelector(".alert-toast__close").addEventListener("click", () => toast.remove());
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.transition = "opacity .3s";
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 9000);
  }

  /* ── WebSocket (kept alive for future district alerts) ──────────────────── */
  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    try { ws = new WebSocket(`${proto}//${location.host}/ws/districts`); } catch { setLive(false); schedule(); return; }
    ws.onopen  = () => { reconnectN = 0; setLive(true); };
    ws.onclose = () => { setLive(false); schedule(); };
    ws.onerror = () => { try { ws.close(); } catch {} };
    ws.onmessage = (ev) => {
      let msg; try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.type === "alert" && msg.alert) showToast(msg.alert);
      lastUpdateMs = Date.now();
      if ($("last-update")) $("last-update").textContent = new Date().toLocaleTimeString();
    };
  }
  function schedule() {
    const ms = Math.min(30000, 1000 * Math.pow(2, reconnectN++));
    setTimeout(connect, ms);
  }

  /* ── Pinned places ─────────────────────────────────────────────────────── */
  function addToSearchedPlaces(loc) {
    if (!loc || !loc.label) return;
    const key = `${Number(loc.lat).toFixed(4)}_${Number(loc.lng).toFixed(4)}`;
    if (searchedPlaces.find((p) => p.key === key)) return;
    searchedPlaces.unshift({ key, label: loc.label, lat: loc.lat, lng: loc.lng });
    if (searchedPlaces.length > 8) searchedPlaces.pop();
    renderSearchedPlaces();
  }

  function renderSearchedPlaces() {
    const section = $("searched-places-section");
    const list    = $("searched-places-list");
    if (!section || !list) return;
    if (!searchedPlaces.length) { section.style.display = "none"; return; }
    section.style.display = "block";
    list.innerHTML = searchedPlaces.map((p) => {
      const sel = customLocation && customLocation.key === p.key;
      return `<div class="searched-place-item${sel ? " selected" : ""}" data-key="${esc(p.key)}">
        <div class="searched-place__icon">⊕</div>
        <div class="searched-place__body">
          <div class="searched-place__name">${esc(p.label.split(",")[0])}</div>
          <div class="searched-place__sub">${esc(p.label.split(",").slice(1, 3).join(",").trim())}</div>
        </div>
        <button class="searched-place__remove" data-key="${esc(p.key)}" title="Remove">×</button>
      </div>`;
    }).join("");

    list.querySelectorAll(".searched-place-item").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.classList.contains("searched-place__remove")) return;
        const p = searchedPlaces.find((x) => x.key === el.dataset.key);
        if (!p) return;
        Map.selectPoint(p.lat, p.lng, p.label, { skipFly: false });
        selectCustomLocation({ type: "map_pick", lat: p.lat, lng: p.lng, label: p.label, key: p.key });
      });
    });
    list.querySelectorAll(".searched-place__remove").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        searchedPlaces = searchedPlaces.filter((p) => p.key !== btn.dataset.key);
        if (customLocation && customLocation.key === btn.dataset.key) {
          customLocation = null;
          renderDetail();
        }
        renderSearchedPlaces();
      });
    });
  }

  /* ── Detail panel default state ────────────────────────────────────────── */
  function renderDetail() {
    const title = $("detail-title");
    const body  = $("detail-body");
    const tag   = $("detail-tag");
    if (!title || !body) return;
    title.textContent = "Select a location";
    if (tag) tag.textContent = "";
    body.innerHTML = `<div class="dc-detail--empty">
      <p style="color:var(--text-muted);font-family:var(--font-mono);font-size:11px;line-height:1.9">
        Search a city above, or click anywhere on the map<br/>to pull live intelligence for that location
      </p>
    </div>`;
  }

  /* ── Location selection → intel panel + map circle ─────────────────────── */
  function selectCustomLocation(loc) {
    if (!loc) return;
    customLocation = { ...loc, key: loc.key || `${Number(loc.lat).toFixed(4)}_${Number(loc.lng).toFixed(4)}` };
    addToSearchedPlaces(loc);
    renderSearchedPlaces();

    const n = (loc.label || loc.display_name || "").split(",")[0];
    const hudLoc = $("hud-location-label");
    if (hudLoc) hudLoc.textContent = n.length > 14 ? n.slice(0, 12) + "…" : (n || "—");

    renderIntelPanel(loc.lat, loc.lng, loc.label || loc.display_name || "");
  }

  async function renderIntelPanel(lat, lon, name) {
    const title = $("detail-title");
    const tag   = $("detail-tag");
    const body  = $("detail-body");
    if (!body) return;

    const shortName = (name || "Location").split(",")[0];
    if (title) title.textContent = shortName;
    if (tag)   tag.textContent   = "GLOBAL";

    body.innerHTML = `<div class="intel-loading">
      <div class="intel-loading__spinner"></div>
      <div class="intel-loading__text">Assembling intelligence for ${esc(shortName)}…</div>
    </div>`;

    try {
      const intel = await Api.getLocationIntel(lat, lon, name);
      if (title) title.textContent = intel.location.short_name || shortName;

      // ── Paint severity circle on the map ──────────────────────────────────
      const risk = intel.ai_scores ? intel.ai_scores.safety_risk : 0;
      Map.showIntelCircle(lat, lon, risk, intel.location.short_name || shortName, intel.ai_scores);

      body.innerHTML = buildIntelHTML(intel);
    } catch (e) {
      console.error("Intel fetch failed:", e);
      body.innerHTML = `<div class="dc-detail--empty"><p style="color:var(--text-muted);font-size:.8rem">Failed to load intelligence for this location.</p></div>`;
    }
  }

  /* ── Intel HTML builder ─────────────────────────────────────────────────── */
  function buildIntelHTML(intel) {
    const { location, weather, news, finance, ai_scores, insights } = intel;
    const scores = ai_scores || {};
    const w      = weather  || {};
    const fin    = finance  || {};

    return `
      <div class="intel-location-header">
        <div class="intel-location-name">${esc(location.short_name || location.name || "")}</div>
        <div class="intel-location-sub">${esc(location.country || "")}</div>
        <div class="intel-freshness">${intel.cached ? "⚡ Cached" : "🔄 Live"} · ${_intelTimeAgo(intel.fetched_at)}</div>
      </div>

      <div class="intel-score-strip">
        ${_scoreChip("Crowd",     scores.crowd_density,   "#0F62FE")}
        ${_scoreChip("Sentiment", scores.sentiment_score, "#24A148")}
        ${_scoreChip("Risk",      scores.safety_risk,     "#DA1E28")}
        ${_scoreChip("Weather",   scores.weather_impact,  "#F0A500")}
      </div>
      ${scores.summary ? `<div class="intel-summary">${esc(scores.summary)}</div>` : ""}

      ${insights && insights.length ? `
      <div class="intel-section-label">Live Insights</div>
      <div class="intel-insights">
        ${insights.map(i => `
          <div class="insight-item insight-item--${esc(i.severity)}">
            <span class="insight-icon">${_insightIcon(i.type)}</span>
            <span class="insight-text">${esc(i.text)}</span>
          </div>`).join("")}
      </div>` : ""}

      ${buildFinanceHTML(fin, location)}

      <div class="intel-section-label">Weather</div>
      ${buildWeatherHTML(w)}

      <div class="intel-section-label">News · Real-time</div>
      <div class="intel-news-feed">
        ${(news || []).slice(0, 12).map(n => `
          <a class="news-item news-item--${esc(n.sentiment)}" href="${esc(n.url)}" target="_blank" rel="noopener noreferrer">
            <div class="news-item__title">${esc(n.title)}</div>
            <div class="news-item__meta">${n.source ? esc(n.source) + " · " : ""}${_intelTimeAgo(n.published)}</div>
          </a>`).join("") || '<div style="color:var(--text-muted);font-size:.76rem;padding:8px 0">No recent news found.</div>'}
      </div>

      <a class="btn-sim-zone" href="/simulator?zone=${encodeURIComponent("geo_" + Number(location.lat).toFixed(4) + "_" + Number(location.lon).toFixed(4))}&place=${encodeURIComponent(location.short_name || location.name || "")}">
        Run Oracle Simulation →
      </a>`;
  }

  function buildFinanceHTML(fin, location) {
    const idx   = fin.index    || null;
    const fx    = fin.currency || null;
    const macro = fin.macro    || null;
    if (!idx && !fx && !macro) return "";

    const indexHTML = idx ? (() => {
      const chg = idx.change_pct;
      const chgClass = chg == null ? "" : chg >= 0 ? "fin-change--up" : "fin-change--down";
      const chgArrow = chg == null ? "" : chg >= 0 ? "▲" : "▼";
      const stateLabel = { REGULAR: "Open", CLOSED: "Closed", PRE: "Pre-mkt", POST: "After-hrs" }[idx.market_state] || idx.market_state || "";
      return `<div class="fin-index">
        <div class="fin-index__name">${esc(idx.name)}</div>
        <div class="fin-index__row">
          <span class="fin-index__price">${idx.price != null ? Number(idx.price).toLocaleString() : "—"}</span>
          ${chg != null ? `<span class="fin-change ${chgClass}">${chgArrow} ${Math.abs(chg).toFixed(2)}%</span>` : ""}
          ${stateLabel ? `<span class="fin-state">${stateLabel}</span>` : ""}
        </div>
      </div>`;
    })() : "";

    const fxHTML = fx ? (() => {
      if (fx.rates) {
        const rateItems = Object.entries(fx.rates).slice(0, 3).map(([k, v]) =>
          `<div class="fin-fx-item"><span class="fin-fx-code">${k}</span><span class="fin-fx-rate">${Number(v).toFixed(4)}</span></div>`
        ).join("");
        return `<div class="fin-fx"><div class="fin-fx__label">USD Rates <span class="fin-date">${fx.date || ""}</span></div><div class="fin-fx__grid">${rateItems}</div></div>`;
      }
      return `<div class="fin-fx"><div class="fin-fx__label">FX <span class="fin-date">${fx.date || ""}</span></div><div class="fin-fx__rate">${esc(fx.label || "")}</div></div>`;
    })() : "";

    const macroHTML = macro ? (() => {
      const items = [
        macro.gdp_growth_pct   != null ? `<div class="fin-macro-item"><span class="fin-macro-label">GDP Growth</span><span class="fin-macro-val ${macro.gdp_growth_pct >= 0 ? "fin-change--up" : "fin-change--down"}">${macro.gdp_growth_pct > 0 ? "+" : ""}${macro.gdp_growth_pct}%</span></div>` : "",
        macro.inflation_pct    != null ? `<div class="fin-macro-item"><span class="fin-macro-label">Inflation</span><span class="fin-macro-val">${macro.inflation_pct}%</span></div>` : "",
        macro.unemployment_pct != null ? `<div class="fin-macro-item"><span class="fin-macro-label">Unemployment</span><span class="fin-macro-val">${macro.unemployment_pct}%</span></div>` : "",
      ].filter(Boolean).join("");
      return items ? `<div class="fin-macro"><div class="fin-macro__label">Macro · ${macro.year || "Latest"}</div><div class="fin-macro__grid">${items}</div></div>` : "";
    })() : "";

    if (!indexHTML && !fxHTML && !macroHTML) return "";
    return `<div class="intel-section-label">Finance · ${esc((location || {}).country || "")}</div>
      <div class="intel-finance">${indexHTML}${fxHTML}${macroHTML}</div>`;
  }

  function buildWeatherHTML(w) {
    if (!w || (w.temp_c == null && w.condition == null)) {
      return `<div style="color:var(--text-muted);font-size:.76rem;padding:4px 0">Weather unavailable</div>`;
    }
    const icon = weatherIcon(w.condition || "");
    const forecast = (w.forecast_3h || []).map((h, i) =>
      `<div class="weather-forecast-slot">
        <div class="wf-label">+${i + 1}h</div>
        <div class="wf-icon">${weatherIcon(h.condition)}</div>
        <div class="wf-temp">${h.temp_c != null ? Number(h.temp_c).toFixed(1) + "°" : "—"}</div>
      </div>`
    ).join("");
    return `<div class="weather-widget">
      <div class="weather-current">
        <div class="weather-icon">${icon}</div>
        <div class="weather-temp-block">
          <div class="weather-temp">${w.temp_c != null ? Number(w.temp_c).toFixed(1) : "—"}°C</div>
          <div class="weather-condition">${esc(w.condition || "")}</div>
        </div>
      </div>
      <div class="weather-grid">
        <div class="weather-metric"><span class="wm-label">Feels</span><span class="wm-val">${w.feels_like_c != null ? Number(w.feels_like_c).toFixed(1) + "°" : "—"}</span></div>
        <div class="weather-metric"><span class="wm-label">Humidity</span><span class="wm-val">${w.humidity != null ? w.humidity + "%" : "—"}</span></div>
        <div class="weather-metric"><span class="wm-label">Wind</span><span class="wm-val">${w.wind_ms != null ? Number(w.wind_ms).toFixed(1) + " m/s" : "—"}</span></div>
        <div class="weather-metric"><span class="wm-label">Rain</span><span class="wm-val">${w.rain_mm != null ? Number(w.rain_mm).toFixed(1) + " mm" : "—"}</span></div>
      </div>
      ${forecast ? `<div class="weather-forecast">${forecast}</div>` : ""}
    </div>`;
  }

  /* ── Chip / icon / time helpers ─────────────────────────────────────────── */
  function _scoreChip(label, value, color) {
    const pct = Math.round(Math.min(1, Math.max(0, Number(value) || 0)) * 100);
    return `<div class="score-chip">
      <div class="score-chip__bar" style="--pct:${pct}%;--color:${color}"></div>
      <div class="score-chip__label">${label}</div>
      <div class="score-chip__val">${pct}%</div>
    </div>`;
  }

  function _insightIcon(type) {
    return { news: "📰", weather: "🌤", social: "💬", risk: "⚠️", finance: "📈" }[type] || "•";
  }

  function _intelTimeAgo(iso) {
    if (!iso) return "";
    try {
      const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
      if (isNaN(mins) || mins < 0) return "";
      if (mins < 60)   return `${mins}m ago`;
      if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
      return `${Math.round(mins / 1440)}d ago`;
    } catch { return ""; }
  }

  /* ── Map search ─────────────────────────────────────────────────────────── */
  function initMapSearch() {
    const input   = $("map-search");
    const btn     = $("map-search-btn");
    const suggest = $("map-search-suggest");
    const PS = global.DevCityPlaceSearch;
    if (!input || !btn || !suggest || !PS || !Api.geoSearch) return;

    PS.attach({
      input, button: btn, suggest,
      debounceMs: 220,
      fetchRows: async (q) => {
        const res = await Api.geoSearch(q, 6);
        return (res.places || []).map((p) => ({ label: p.label, lat: Number(p.lat), lng: Number(p.lon) }));
      },
      onPick: (row) => {
        input.value = row.label || "";
        Map.selectPoint(row.lat, row.lng, row.label, { skipFly: false });
        const loc = { type: "map_pick", lat: row.lat, lng: row.lng, label: row.label, display_name: row.label };
        addToSearchedPlaces(loc);
        selectCustomLocation(loc);
      },
      onSubmitQuery: async () => {
        const q = input.value.trim();
        if (!q) return;
        const rows = await Map.searchPlace(q);
        const row = rows[0];
        if (!row) return;
        input.value = row.label;
        const loc = { type: "map_pick", lat: row.lat, lng: row.lng, label: row.label, display_name: row.label };
        addToSearchedPlaces(loc);
        Map.selectPoint(row.lat, row.lng, row.label, { skipFly: false });
        selectCustomLocation(loc);
      },
    });
  }

  /* ── Boot ───────────────────────────────────────────────────────────────── */
  async function boot() {
    Map.initMap("dc-map", (payload) => {
      if (payload && payload.type === "map_pick") {
        addToSearchedPlaces(payload);
        selectCustomLocation(payload);
      }
    });

    renderDetail();
    renderSearchedPlaces();
    Map.flyToContinent("Americas");
    initMapSearch();
    updateClock();
    setInterval(updateClock, 1000);

    const clearBtn = $("clear-places-btn");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        searchedPlaces = [];
        customLocation = null;
        renderSearchedPlaces();
        renderDetail();
      });
    }

    connect();
    setInterval(() => { if (Date.now() - lastUpdateMs > 90000) setLive(false); }, 15000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(typeof window !== "undefined" ? window : globalThis);
