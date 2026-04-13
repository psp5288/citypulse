/* DevCity Pulse — The Eye with continent/country/district hierarchy */
(function (global) {
  const Api = global.DevCityApi;
  const Map = global.DevCityMap;

  let selectedContinent = "Americas";
  let selectedCountry = null;
  let selectedDistrict = null;
  let districtsMap = new global.Map();
  let ws;
  let reconnectN = 0;
  let lastUpdateMs = Date.now();

  const CONTINENTS = {
    Americas: ["United States", "Canada", "Brazil", "Mexico", "Argentina"],
    Europe: ["United Kingdom", "Germany", "France", "Italy", "Spain"],
    Asia: ["Japan", "China", "India", "South Korea", "Singapore"],
    Africa: ["South Africa", "Nigeria", "Kenya", "Egypt", "Ethiopia"],
    Oceania: ["Australia", "New Zealand", "Fiji"],
  };
  const ACTIVE_COUNTRIES = ["United States"];

  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }
  function pct(v) {
    return Math.round(Math.min(1, Math.max(0, Number(v) || 0)) * 100);
  }
  function riskLevel(r) {
    const v = Number(r) || 0;
    if (v > 0.6) return "critical";
    if (v > 0.38) return "high";
    if (v > 0.2) return "moderate";
    return "low";
  }
  function timeAgo(iso) {
    if (!iso) return "—";
    const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
    if (secs < 60) return `${secs}s ago`;
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    return `${Math.floor(secs / 3600)}h ago`;
  }

  function scoreBar(label, val, positiveGood) {
    const c = Map.scoreColor(val, positiveGood);
    const w = pct(val);
    const num = (Number(val) || 0).toFixed(2);
    return `<div class="score-bar">
      <span class="score-label">${label}</span>
      <div class="score-track"><div class="score-fill" style="width:${w}%;background:${c}"></div></div>
      <span class="score-value">${num}</span>
    </div>`;
  }

  function signalBadge(label, value, unit, level) {
    return `<div class="signal-badge signal-badge--${level || "info"}">
      <div class="signal-badge__label">${label}</div>
      <div class="signal-badge__value">${value}</div>
      <div class="signal-badge__trend">${unit}</div>
    </div>`;
  }

  function buildTickerContent(districts) {
    const inner = $("ticker-inner");
    if (!inner || !districts.length) return;
    const items = districts.map((d) => {
      const risk = riskLevel(d.risk);
      const cls = risk === "critical" ? "critical" : risk === "high" ? "warning" : "";
      const sent = ((Number(d.sentiment) || 0) * 100).toFixed(0);
      const rsk = ((Number(d.risk) || 0) * 100).toFixed(0);
      return `<span class="dc-ticker__item ${cls}">
        <span class="dc-ticker__item-zone">${esc(d.name)}</span>
        Risk ${rsk}% · Sentiment ${sent}% · ${d.summary ? esc(d.summary.slice(0, 60)) + "…" : "Monitoring"}
      </span>`;
    });
    inner.innerHTML = [...items, ...items].join("");
  }

  function updateHUD(districts) {
    const counts = { critical: 0, high: 0, low: 0 };
    districts.forEach((d) => {
      const lvl = riskLevel(d.risk);
      if (lvl === "critical") counts.critical++;
      else if (lvl === "high") counts.high++;
      else counts.low++;
    });
    if ($("hud-critical")) $("hud-critical").textContent = counts.critical;
    if ($("hud-high")) $("hud-high").textContent = counts.high;
    if ($("hud-low")) $("hud-low").textContent = counts.low;
  }

  function renderContinentTabs() {
    const host = $("continent-tabs");
    if (!host) return;
    host.innerHTML = Object.keys(CONTINENTS)
      .map((name) => {
        const active = name === selectedContinent;
        return `<button class="btn btn--ghost btn--sm" data-continent="${esc(name)}" style="margin:2px;${active ? "border-color:var(--accent);color:var(--accent);background:var(--accent-dim);" : ""}">
          ${esc(name)}
        </button>`;
      })
      .join("");
    host.querySelectorAll("button[data-continent]").forEach((btn) => {
      btn.addEventListener("click", () => {
        selectedContinent = btn.dataset.continent;
        selectedCountry = null;
        selectedDistrict = null;
        renderContinentTabs();
        renderCountryList(selectedContinent);
        renderDistrictList();
        renderDetail();
        renderBottomBar();
        Map.flyToContinent(selectedContinent);
        Map.hideDistrictMarkers();
      });
    });
  }

  function renderCountryList(continent) {
    const host = $("country-list");
    if (!host) return;
    const countries = CONTINENTS[continent] || [];
    const districtCount = districtsMap.size;
    host.innerHTML = countries
      .map((name) => {
        const active = ACTIVE_COUNTRIES.includes(name);
        const selected = name === selectedCountry;
        const status = active ? "Live data" : "No monitoring data";
        return `<div class="zone-card${selected ? " selected" : ""}" data-country="${esc(name)}" style="${active ? "" : "opacity:.7;"}">
          <div class="zone-card__bar" style="background:${active ? "var(--s-blue)" : "var(--bg-border)"}"></div>
          <div class="zone-card__content">
            <div class="zone-card__row1">
              <span class="zone-card__name">${esc(name)}</span>
              <span class="zone-card__risk" style="color:${active ? "var(--s-blue)" : "var(--text-muted)"}">${active ? `${districtCount} districts` : "No data"}</span>
            </div>
            <div class="zone-card__updated">${status}</div>
          </div>
        </div>`;
      })
      .join("");

    host.querySelectorAll("[data-country]").forEach((el) => {
      el.addEventListener("click", () => selectCountry(el.dataset.country));
    });
  }

  function selectCountry(name) {
    selectedCountry = name;
    selectedDistrict = null;
    renderCountryList(selectedContinent);

    if (!ACTIVE_COUNTRIES.includes(name)) {
      Map.hideDistrictMarkers();
      renderDistrictList();
      renderDetail();
      renderBottomBar();
      return;
    }

    Map.flyToCountry(name);
    Map.showDistrictMarkers([...districtsMap.values()]);
    const first = [...districtsMap.values()][0];
    selectedDistrict = first ? first.id : null;
    if (selectedDistrict) Map.highlightDistrict(selectedDistrict, true);
    renderDistrictList();
    renderDetail();
    renderBottomBar();
  }

  function renderDistrictList() {
    const host = $("zone-list");
    if (!host) return;
    if (selectedCountry !== "United States") {
      host.innerHTML = `<div class="dc-detail--empty" style="height:auto;padding:16px">
        <p style="color:var(--text-muted);font-family:var(--font-mono);font-size:10px;line-height:1.8">
          Select an active country to view district monitoring
        </p>
      </div>`;
      if ($("district-count")) $("district-count").textContent = "0";
      return;
    }

    const sorted = [...districtsMap.values()].sort((a, b) => (Number(b.risk) || 0) - (Number(a.risk) || 0));
    host.innerHTML = sorted
      .map((d) => {
        const col = Map.threatColor(d);
        const sel = d.id === selectedDistrict ? " selected" : "";
        return `<div class="zone-card${sel}" data-id="${esc(d.id)}" role="button" tabindex="0">
          <div class="zone-card__bar" style="background:${col}"></div>
          <div class="zone-card__content">
            <div class="zone-card__row1">
              <span class="zone-card__name">${esc(d.name)}</span>
              <span class="zone-card__risk">${(Number(d.risk) || 0).toFixed(2)}</span>
            </div>
            ${scoreBar("Crowd", d.crowd, false)}
            ${scoreBar("Sentiment", d.sentiment, true)}
            <div class="zone-card__updated">${timeAgo(d.updated_at)}</div>
          </div>
        </div>`;
      })
      .join("");
    host.querySelectorAll(".zone-card").forEach((el) => {
      el.addEventListener("click", () => selectDistrict(el.dataset.id));
      el.addEventListener("keydown", (e) => e.key === "Enter" && selectDistrict(el.dataset.id));
    });
    if ($("district-count")) $("district-count").textContent = String(sorted.length);
  }

  function selectDistrict(id) {
    if (selectedCountry !== "United States") return;
    if (selectedDistrict) Map.highlightDistrict(selectedDistrict, false);
    selectedDistrict = id;
    Map.highlightDistrict(selectedDistrict, true);
    renderDistrictList();
    renderDetail();
    renderBottomBar();
  }

  function renderDetail() {
    const title = $("detail-title");
    const body = $("detail-body");
    const tag = $("detail-tag");
    if (!title || !body) return;

    if (selectedCountry && !ACTIVE_COUNTRIES.includes(selectedCountry)) {
      title.textContent = selectedCountry;
      if (tag) tag.textContent = "";
      body.innerHTML = `<div class="dc-detail--empty">
        <p style="color:var(--text-muted);font-family:var(--font-mono);font-size:11px;line-height:1.8">
          No live monitoring data for ${esc(selectedCountry)} yet
        </p>
      </div>`;
      return;
    }

    const d = selectedDistrict ? districtsMap.get(selectedDistrict) : null;
    if (!d) {
      title.textContent = "Select a district";
      if (tag) tag.textContent = "";
      body.innerHTML = `<div class="dc-detail--empty">
        <p style="color:var(--text-muted);font-family:var(--font-mono);font-size:11px;line-height:1.8">
          Select a monitored country and district
        </p>
      </div>`;
      return;
    }

    title.textContent = d.name || d.id;
    if (tag) tag.textContent = "LIVE";
    const risk = Number(d.risk) || 0;
    const sent = Number(d.sentiment) || 0;
    const crowd = Number(d.crowd) || 0;
    const lvl = riskLevel(risk);
    const riskBadge = lvl === "critical" ? "critical" : lvl === "high" ? "warning" : lvl === "moderate" ? "info" : "good";
    body.innerHTML = `
      <div class="detail-section" style="margin-top:0">
        <div class="detail-section__label">Signal Overview</div>
        ${scoreBar("Crowd Density", d.crowd, false)}
        ${scoreBar("Sentiment", d.sentiment, true)}
        ${scoreBar("Safety Risk", d.risk, false)}
      </div>
      <div class="detail-section">
        <div class="detail-section__label">Signal Badges</div>
        <div class="signal-grid">
          ${signalBadge("Risk Level", (risk * 100).toFixed(0) + "%", lvl.toUpperCase(), riskBadge)}
          ${signalBadge("Sentiment", (sent * 100).toFixed(0) + "%", sent > 0.5 ? "Positive" : "Negative", sent > 0.5 ? "good" : "critical")}
          ${signalBadge("Crowd", (crowd * 100).toFixed(0) + "%", crowd > 0.6 ? "High density" : "Normal", crowd > 0.6 ? "warning" : "info")}
          ${signalBadge("Events", d.events != null ? String(d.events) : "—", "Nearby", d.events > 3 ? "warning" : "info")}
        </div>
      </div>
      ${d.summary ? `<div class="detail-section"><div class="detail-section__label">AI Summary</div><p class="dc-summary">${esc(d.summary)}</p></div>` : ""}
      <a class="btn-sim-zone" href="/simulator?district=${encodeURIComponent(d.id)}">Run Oracle Simulation →</a>
    `;
  }

  function renderBottomBar() {
    const bar = $("bottom-bar");
    if (!bar) return;
    if (selectedCountry !== "United States") {
      bar.style.display = "none";
      bar.innerHTML = "";
      return;
    }
    bar.style.display = "flex";
    const sorted = [...districtsMap.values()].sort((a, b) => (Number(b.risk) || 0) - (Number(a.risk) || 0));
    bar.innerHTML = sorted
      .map((d) => {
        const col = Map.threatColor(d);
        const sel = d.id === selectedDistrict ? " selected" : "";
        return `<div class="mini-card${sel}" data-id="${esc(d.id)}" role="button" tabindex="0">
          <div class="mini-card__name" style="border-left:3px solid ${col};padding-left:8px">${esc(d.name)}</div>
          <div class="mini-card__meta">risk <span>${(Number(d.risk) || 0).toFixed(2)}</span> · sent <span>${(Number(d.sentiment) || 0).toFixed(2)}</span></div>
        </div>`;
      })
      .join("");
    bar.querySelectorAll(".mini-card").forEach((el) => {
      el.addEventListener("click", () => selectDistrict(el.dataset.id));
    });
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
      toast.style.transition = "opacity 0.3s";
      toast.style.opacity = "0";
      setTimeout(() => toast.remove(), 300);
    }, 9000);
  }

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

  function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      ws = new WebSocket(`${proto}//${location.host}/ws/districts`);
    } catch (e) {
      setLive(false);
      schedule();
      return;
    }
    ws.onopen = () => {
      reconnectN = 0;
      setLive(true);
    };
    ws.onclose = () => {
      setLive(false);
      schedule();
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch {}
    };
    ws.onmessage = (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "districts_update" && Array.isArray(msg.data)) ingest(msg.data);
      if (msg.type === "alert" && msg.alert) showToast(msg.alert);
    };
  }

  function schedule() {
    const ms = Math.min(30000, 1000 * Math.pow(2, reconnectN++));
    setTimeout(connect, ms);
  }

  function updateClock() {
    const now = new Date();
    if ($("topbar-clock")) $("topbar-clock").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if ($("topbar-date")) $("topbar-date").textContent = now.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  function ingest(districts) {
    if (!Array.isArray(districts)) return;
    districtsMap.clear();
    districts.forEach((d) => districtsMap.set(d.id, d));
    if (selectedCountry === "United States") {
      Map.updateDistricts(districts);
      if (!selectedDistrict && districts.length) selectedDistrict = districts[0].id;
      if (selectedDistrict) Map.highlightDistrict(selectedDistrict, true);
    } else {
      Map.hideDistrictMarkers();
    }
    renderCountryList(selectedContinent);
    renderDistrictList();
    renderDetail();
    renderBottomBar();
    updateHUD(districts);
    buildTickerContent(districts);
    lastUpdateMs = Date.now();
    if ($("last-update")) $("last-update").textContent = new Date().toLocaleTimeString();
    if ($("sr-last-update")) $("sr-last-update").textContent = new Date().toLocaleTimeString();
  }

  async function boot() {
    Map.initMap("dc-map", (id) => selectDistrict(id));
    renderContinentTabs();
    renderCountryList(selectedContinent);
    renderDistrictList();
    renderDetail();
    renderBottomBar();
    Map.flyToContinent(selectedContinent);
    updateClock();
    setInterval(updateClock, 1000);

    try {
      const data = await Api.getDistricts();
      const list = Array.isArray(data) ? data : data.districts || [];
      ingest(list);
    } catch {
      ingest([]);
    }

    connect();
    setInterval(() => {
      if (Date.now() - lastUpdateMs > 90000) setLive(false);
    }, 15000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(typeof window !== "undefined" ? window : globalThis);
