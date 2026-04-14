/* DevCity Pulse — Real-time Analytics with WebSocket live feed */
(function (global) {
  'use strict';
  const Api = global.DevCityApi;
  const $ = (id) => document.getElementById(id);

  /* ── State ────────────────────────────────────────────────────────────── */
  let trendChart = null;
  let riskChart  = null;
  let wsConn     = null;
  let wsReconnTimer = null;

  const MAX_POINTS = 60;
  const MAX_FEED   = 50;

  const rolling = { labels: [], crowd: [], risk: [], sentiment: [] };
  let feedItems      = [];
  let signalCount    = 0;
  let rateWindow     = [];       // timestamps in last 60s
  let districtCache  = {};       // id → latest district object

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ── Clock ────────────────────────────────────────────────────────────── */
  function clockTick() {
    const now = new Date();
    if ($('topbar-clock')) $('topbar-clock').textContent =
      now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if ($('topbar-date')) $('topbar-date').textContent =
      now.toLocaleDateString([], { month: 'short', day: 'numeric' });
  }

  /* ── WebSocket ────────────────────────────────────────────────────────── */
  function connectWS() {
    if (wsConn && wsConn.readyState <= WebSocket.OPEN) return;
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    try {
      wsConn = new WebSocket(`${proto}//${location.host}/ws/districts`);
      wsConn.onopen  = () => {
        setStatus('live', 'Connected · receiving live district updates');
        if (wsReconnTimer) { clearTimeout(wsReconnTimer); wsReconnTimer = null; }
      };
      wsConn.onmessage = (ev) => {
        try { handleMessage(JSON.parse(ev.data)); } catch { /* ignore */ }
      };
      wsConn.onclose = () => {
        setStatus('offline', 'Disconnected · retrying in 5s…');
        wsReconnTimer = setTimeout(connectWS, 5000);
      };
      wsConn.onerror = () => setStatus('error', 'WebSocket error');
    } catch {
      setStatus('error', 'WebSocket unavailable · using poll fallback');
      wsReconnTimer = setTimeout(connectWS, 8000);
    }
  }

  function setStatus(state, meta) {
    const stateLabels = { live: 'LIVE', offline: 'OFFLINE', error: 'ERROR', connecting: 'CONNECTING' };
    const dot   = $('live-dot');
    const label = $('live-label');
    const badge = $('live-badge');
    const metaEl = $('live-meta');
    if (dot)   dot.className   = `live-dot live-dot--${state}`;
    if (label) label.textContent = stateLabels[state] || state.toUpperCase();
    if (badge) badge.className = `live-badge live-badge--${state}`;
    if (metaEl && meta) metaEl.textContent = meta;
  }

  /* ── Message handler ──────────────────────────────────────────────────── */
  function handleMessage(data) {
    /* Normalise to array of districts */
    let list = [];
    if (Array.isArray(data))                                    list = data;
    else if (data.districts && Array.isArray(data.districts))   list = data.districts;
    else if (data.type === 'district_update' && data.district)  list = [data.district];
    else if (data.id)                                           list = [data];
    if (!list.length) return;

    const now = new Date();

    /* Cache */
    list.forEach(d => {
      const id = d.id || d.district_id;
      if (id) districtCache[id] = { ...d, _ts: now };
    });

    /* Signal-rate window */
    const nowMs = Date.now();
    rateWindow.push(nowMs);
    rateWindow = rateWindow.filter(t => nowMs - t < 60000);
    signalCount += list.length;

    /* Rolling chart data */
    const avgOf = (arr, key1, key2) => {
      const vals = arr.map(d => Number(d[key1] ?? d[key2] ?? 0));
      return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
    };
    const crowd = avgOf(list, 'crowd', 'crowd_density') * 100;
    const risk  = avgOf(list, 'risk',  'safety_risk')   * 100;
    const sent  = avgOf(list, 'sentiment', 'sentiment_score') * 100;
    pushRolling(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }), crowd, risk, sent);

    /* Feed */
    list.forEach(d => appendFeedItem(d, now));

    /* Update charts & KPIs */
    updateTrendChart();
    updateKPIs();
    updateRiskChart();
    updateSnapshotTable();

    /* Meta label */
    const metaEl = $('live-meta');
    if (metaEl) metaEl.textContent = `${signalCount} signals received · last at ${now.toLocaleTimeString()}`;
    const tut = $('trend-update-time');
    if (tut) tut.textContent = now.toLocaleTimeString();
  }

  /* ── Rolling buffer ───────────────────────────────────────────────────── */
  function pushRolling(label, crowd, risk, sent) {
    rolling.labels.push(label);
    rolling.crowd.push(crowd);
    rolling.risk.push(risk);
    rolling.sentiment.push(sent);
    if (rolling.labels.length > MAX_POINTS) {
      rolling.labels.shift(); rolling.crowd.shift();
      rolling.risk.shift();   rolling.sentiment.shift();
    }
  }

  /* ── Chart updates ────────────────────────────────────────────────────── */
  function updateTrendChart() {
    if (!trendChart) return;
    trendChart.data.labels          = [...rolling.labels];
    trendChart.data.datasets[0].data = [...rolling.crowd];
    trendChart.data.datasets[1].data = [...rolling.risk];
    trendChart.data.datasets[2].data = [...rolling.sentiment];
    trendChart.update('none');
  }

  function updateRiskChart() {
    if (!riskChart) return;
    const all = Object.values(districtCache);
    const r = (d) => Number(d.risk ?? d.safety_risk ?? 0);
    const critical = all.filter(d => r(d) > 0.6).length;
    const high     = all.filter(d => r(d) > 0.38 && r(d) <= 0.6).length;
    const moderate = all.filter(d => r(d) > 0.2  && r(d) <= 0.38).length;
    const low      = all.filter(d => r(d) <= 0.2).length;
    riskChart.data.datasets[0].data = [critical, high, moderate, low];
    riskChart.update('none');
    const ru = $('risk-update-time');
    if (ru) ru.textContent = new Date().toLocaleTimeString();
  }

  /* ── KPIs ─────────────────────────────────────────────────────────────── */
  function updateKPIs() {
    const all = Object.values(districtCache);
    if (!all.length) return;
    const n  = (d, k1, k2) => Number(d[k1] ?? d[k2] ?? 0);
    const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;

    const maxCrowd = Math.max(...all.map(d => n(d, 'crowd', 'crowd_density')));
    const avgRisk  = avg(all.map(d => n(d, 'risk', 'safety_risk')));
    const totalEvt = all.reduce((s, d) => s + Number(d.events ?? d.events_count ?? 0), 0);

    setText('kpi-density',     `${(maxCrowd * 100).toFixed(0)}%`);
    setText('kpi-avg-risk',    `${(avgRisk  * 100).toFixed(0)}%`);
    setText('kpi-events',      String(totalEvt));
    setText('kpi-signal-rate', `${rateWindow.length}/min`);
  }

  function setText(id, val) {
    const el = $(id);
    if (el && el.textContent !== val) el.textContent = val;
  }

  /* ── Live feed ────────────────────────────────────────────────────────── */
  function appendFeedItem(d, ts) {
    const crowd = Number(d.crowd ?? d.crowd_density ?? 0);
    const risk  = Number(d.risk  ?? d.safety_risk   ?? 0);
    const sent  = Number(d.sentiment ?? d.sentiment_score ?? 0);
    const name  = d.name || d.id || 'District';

    let type = 'normal', icon = '●';
    if (risk  > 0.6)  { type = 'alert';    icon = '⚠'; }
    else if (crowd > 0.75) { type = 'busy', icon = '↑'; }
    else if (sent  > 0.7)  { type = 'positive', icon = '↑'; }
    else if (risk  < 0.15) { type = 'calm', icon = '✓'; }

    feedItems.unshift({
      name,
      crowd: (crowd * 100).toFixed(0),
      risk:  (risk  * 100).toFixed(0),
      sent:  (sent  * 100).toFixed(0),
      type, icon,
      summary: (d.summary || '').slice(0, 72),
      ts: ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
    });
    if (feedItems.length > MAX_FEED) feedItems.length = MAX_FEED;
    renderFeed();
  }

  function renderFeed() {
    const el = $('analytics-live-feed');
    if (!el) return;
    const cnt = $('feed-count');
    if (cnt) cnt.textContent = `${signalCount} signal${signalCount !== 1 ? 's' : ''}`;

    if (!feedItems.length) {
      el.innerHTML = '<div class="feed-empty"><div class="feed-empty__dot"></div>Waiting for live signals…</div>';
      return;
    }
    el.innerHTML = feedItems.slice(0, 40).map(item => `
      <div class="feed-item feed-item--${item.type}">
        <span class="feed-item__icon">${item.icon}</span>
        <div class="feed-item__body">
          <div class="feed-item__name">${esc(item.name)}</div>
          ${item.summary ? `<div class="feed-item__summary">${esc(item.summary)}</div>` : ''}
          <div class="feed-item__metrics">
            <span title="Crowd">C&nbsp;${item.crowd}%</span>
            <span title="Risk">R&nbsp;${item.risk}%</span>
            <span title="Sentiment">S&nbsp;${item.sent}%</span>
          </div>
        </div>
        <span class="feed-item__time">${item.ts}</span>
      </div>`).join('');
  }

  /* ── Snapshot table ───────────────────────────────────────────────────── */
  function updateSnapshotTable() {
    const tbody = $('district-snapshot-body');
    if (!tbody) return;
    const all = Object.values(districtCache);
    if (!all.length) return;

    const sorted = [...all].sort((a, b) =>
      (Number(b.risk ?? b.safety_risk ?? 0)) - (Number(a.risk ?? a.safety_risk ?? 0))
    );

    tbody.innerHTML = sorted.map(d => {
      const crowd = ((Number(d.crowd ?? d.crowd_density ?? 0)) * 100).toFixed(0);
      const sent  = ((Number(d.sentiment ?? d.sentiment_score ?? 0)) * 100).toFixed(0);
      const risk  = Number(d.risk ?? d.safety_risk ?? 0);
      const events = d.events ?? d.events_count ?? '—';
      const updatedAt = d._ts ? d._ts.toLocaleTimeString() : '—';
      return `<tr>
        <td style="font-weight:600;color:var(--text-primary)">${esc(d.name || d.id)}</td>
        <td>${crowd}%</td>
        <td>${sent}%</td>
        <td>${(risk * 100).toFixed(0)}%</td>
        <td>${esc(events)}</td>
        <td>${statusBadge(risk)}</td>
        <td style="font-family:var(--font-mono);font-size:8px;color:var(--text-muted)">${updatedAt}</td>
      </tr>`;
    }).join('');

    const sut = $('snapshot-update-time');
    if (sut) sut.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  function statusBadge(risk) {
    const v = Number(risk) || 0;
    if (v > 0.6)  return `<span style="color:#C47070;font-weight:600">CRITICAL</span>`;
    if (v > 0.38) return `<span style="color:#C4A840;font-weight:600">HIGH</span>`;
    if (v > 0.2)  return `<span style="color:#6A9DC4">MODERATE</span>`;
    return `<span style="color:#5DAF78">LOW</span>`;
  }

  /* ── Chart init ───────────────────────────────────────────────────────── */
  const CHART_DEFAULTS = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { labels: { color: '#888888', font: { family: "'IBM Plex Mono'", size: 10 } } },
      tooltip: { backgroundColor: '#111', titleColor: '#EEE', bodyColor: '#888', borderColor: '#272727', borderWidth: 1 },
    },
  };

  function initTrendChart() {
    const canvas = $('trend-chart');
    if (!canvas || !global.Chart) return;
    if (trendChart) trendChart.destroy();
    trendChart = new global.Chart(canvas, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Crowd',     data: [], borderColor: '#6A9DC4', backgroundColor: 'rgba(106,157,196,0.08)', tension: 0.4, borderWidth: 2, pointRadius: 0, fill: true },
          { label: 'Risk',      data: [], borderColor: '#C47070', backgroundColor: 'rgba(196,112,112,0.08)', tension: 0.4, borderWidth: 2, pointRadius: 0, fill: true },
          { label: 'Sentiment', data: [], borderColor: '#5DAF78', backgroundColor: 'rgba(93,175,120,0.08)',  tension: 0.4, borderWidth: 2, pointRadius: 0, fill: true },
        ],
      },
      options: {
        ...CHART_DEFAULTS,
        scales: {
          x: { ticks: { color: '#444', maxTicksLimit: 8, font: { family: "'IBM Plex Mono'", size: 9 } }, grid: { color: 'rgba(39,39,39,0.8)' } },
          y: { min: 0, max: 100, ticks: { color: '#444', font: { family: "'IBM Plex Mono'", size: 9 } }, grid: { color: 'rgba(39,39,39,0.8)' } },
        },
      },
    });
  }

  function initRiskChart() {
    const canvas = $('risk-chart');
    if (!canvas || !global.Chart) return;
    if (riskChart) riskChart.destroy();
    riskChart = new global.Chart(canvas, {
      type: 'doughnut',
      data: {
        labels: ['Critical', 'High', 'Moderate', 'Low'],
        datasets: [{ data: [0, 0, 0, 0], backgroundColor: ['#C47070', '#C4A840', '#6A9DC4', '#5DAF78'], borderWidth: 0 }],
      },
      options: {
        ...CHART_DEFAULTS,
        cutout: '62%',
        plugins: { ...CHART_DEFAULTS.plugins, legend: { position: 'bottom', labels: { color: '#888888', font: { family: "'IBM Plex Mono'", size: 9 } } } },
      },
    });
  }

  /* ── Historical seed data ─────────────────────────────────────────────── */
  async function loadHistoricalData(range) {
    let analytics = null;
    try {
      analytics = await Api.getAnalytics(range);
      if (!analytics?.labels?.length) analytics = null;
    } catch { /* use mock */ }

    if (!analytics) {
      const n = { '1h': 12, '6h': 24, '24h': 24, '7d': 28 }[range] || 12;
      const step = range === '7d' ? 6 : range === '24h' ? 1 : 0.5;
      const labels = Array.from({ length: n }, (_, i) => `${(i * step).toFixed(1)}h`);
      analytics = {
        labels,
        crowd_series:    labels.map(() => 30 + Math.random() * 40),
        risk_series:     labels.map(() => 20 + Math.random() * 50),
        sentiment_series:labels.map(() => 40 + Math.random() * 45),
        kpis: { inference_latency: '340ms', cache_hit_rate: '89%' },
      };
    }

    /* Seed rolling buffer from historical */
    rolling.labels    = analytics.labels.slice(-MAX_POINTS);
    rolling.crowd     = (analytics.crowd_series     || []).map(Number).slice(-MAX_POINTS);
    rolling.risk      = (analytics.risk_series      || []).map(Number).slice(-MAX_POINTS);
    rolling.sentiment = (analytics.sentiment_series || []).map(Number).slice(-MAX_POINTS);

    const kpis = analytics.kpis || {};
    setText('kpi-latency', kpis.inference_latency || '—');
    setText('kpi-cache',   kpis.cache_hit_rate    || '—');

    updateTrendChart();

    /* Seed district table */
    try {
      const data = await Api.getDistricts();
      const list = Array.isArray(data) ? data : (data.districts || []);
      list.forEach(d => { districtCache[d.id] = { ...d, _ts: new Date() }; });
      updateSnapshotTable();
      updateKPIs();
      updateRiskChart();
    } catch { /* non-fatal */ }
  }

  /* ── Boot ─────────────────────────────────────────────────────────────── */
  async function boot() {
    clockTick();
    setInterval(clockTick, 1000);

    initTrendChart();
    initRiskChart();

    const rangeEl = $('range-select');
    const range = rangeEl?.value || '1h';
    await loadHistoricalData(range);
    if (rangeEl) rangeEl.addEventListener('change', () => loadHistoricalData(rangeEl.value));

    /* Connect live WebSocket */
    setStatus('connecting', 'Connecting to live feed…');
    connectWS();

    /* Poll fallback every 10s when WS is down */
    setInterval(() => {
      if (!wsConn || wsConn.readyState !== WebSocket.OPEN) {
        Api.getDistricts()
          .then(data => {
            const list = Array.isArray(data) ? data : (data.districts || []);
            if (list.length) handleMessage({ districts: list });
          })
          .catch(() => { /* ignore */ });
      }
    }, 10000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})(typeof window !== 'undefined' ? window : globalThis);
