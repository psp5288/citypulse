/* City Pulse — Oracle Analytics Bento orchestration
 * Drives all data loading, charts, history table, compare mode, and chat.
 * Depends on: Chart.js (global), DevCityApi (global), CityPulseContext (global).
 */
(function (global) {
  'use strict';
  const Api = global.DevCityApi;
  const $ = (id) => document.getElementById(id);

  /* ── State ───────────────────────────────────────────────────────────── */
  let charts      = {};         // canvasId → Chart instance
  let histPage    = 0;
  const HIST_LIMIT = 20;
  let histTotal   = 0;
  let selectedIds = new Set();  // run IDs chosen for compare (max 3)

  /* ── Helpers ─────────────────────────────────────────────────────────── */
  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function setText(id, val) {
    const el = $(id);
    if (el) el.textContent = val;
  }

  function filters() {
    return {
      zone:   $('oa-zone')?.value   || undefined,
      sector: $('oa-sector')?.value || undefined,
      days:   Number($('oa-days')?.value   || 14),
      status: $('oa-status')?.value || undefined,
    };
  }

  function tierClass(tier) {
    const m = {
      NOMINAL:  'oa-tier--nominal',
      WATCH:    'oa-tier--watch',
      ELEVATED: 'oa-tier--elevated',
      CRITICAL: 'oa-tier--critical',
    };
    return m[tier] || 'oa-tier--nominal';
  }

  function tierFromRisk(risk) {
    if (risk >= 0.75) return 'CRITICAL';
    if (risk >= 0.50) return 'ELEVATED';
    if (risk >= 0.25) return 'WATCH';
    return 'NOMINAL';
  }

  /* ── Chart factory ───────────────────────────────────────────────────── */
  const CHART_BASE = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        labels: { color: '#888', font: { family: "'JetBrains Mono'", size: 9 } },
      },
      tooltip: {
        backgroundColor: '#111',
        titleColor: '#EEE',
        bodyColor: '#888',
        borderColor: '#272727',
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        ticks: { color: '#444', maxTicksLimit: 8, font: { family: "'JetBrains Mono'", size: 8 } },
        grid:  { color: 'rgba(39,39,39,0.8)' },
      },
      y: {
        ticks: { color: '#444', font: { family: "'JetBrains Mono'", size: 8 } },
        grid:  { color: 'rgba(39,39,39,0.8)' },
      },
    },
  };

  function mkChart(id, cfg) {
    const canvas = $(id);
    if (!canvas || !global.Chart) return null;
    if (charts[id]) { charts[id].destroy(); delete charts[id]; }
    charts[id] = new global.Chart(canvas, cfg);
    return charts[id];
  }

  /* ── Load all ────────────────────────────────────────────────────────── */
  async function loadAll() {
    const f = filters();
    const bento  = document.querySelector('.oa-bento');
    const metaEl = $('oa-meta');
    if (bento)  bento.classList.add('oa-loading');
    if (metaEl) metaEl.textContent = 'Loading…';

    const [chartsRes, insightRes] = await Promise.allSettled([
      Api.getOracleCharts({
        days:   f.days,
        zone:   f.zone,
        sector: f.sector,
        status: f.status || 'complete',
      }),
      Api.getOracleFinalInsight({
        days:   f.days,
        zone:   f.zone,
        sector: f.sector,
      }),
    ]);

    if (chartsRes.status === 'fulfilled' && chartsRes.value) {
      const { charts: c, meta } = chartsRes.value;
      renderKPIs(c, meta);
      renderTimeline(c.timeline);
      renderTierDist(c.tier_distribution);
      renderScatter(c.confidence_vs_risk);
      renderSector(c.sector_impact);
      renderDriver(c.driver_contribution);
      renderFunnel(c.run_funnel);
      renderLeadTime(c.lead_time);
      if (metaEl) {
        metaEl.textContent =
          `${meta?.count ?? 0} runs · ${f.days}d window · ${new Date().toLocaleTimeString()}`;
      }
    } else {
      if (metaEl) metaEl.textContent = 'Chart data unavailable';
    }

    if (insightRes.status === 'fulfilled' && insightRes.value) {
      renderInsight(insightRes.value);
    }

    histPage = 0;
    await loadHistory();

    if (bento) bento.classList.remove('oa-loading');
  }

  /* ── KPIs ────────────────────────────────────────────────────────────── */
  function renderKPIs(c) {
    const funnel = c.run_funnel || {};
    const tier   = c.tier_distribution || {};
    const total    = funnel.started || 0;
    const critical = tier.values ? (tier.values[3] || 0) : 0; // CRITICAL = index 3

    const risks = c.timeline?.risk       || [];
    const confs = c.timeline?.confidence || [];
    const avgRisk = risks.length ? risks.reduce((a, b) => a + b, 0) / risks.length : 0;
    const avgConf = confs.length ? confs.reduce((a, b) => a + b, 0) / confs.length : 0;

    setText('kpi-runs',       String(total));
    setText('kpi-avg-risk',   `${avgRisk.toFixed(1)}%`);
    setText('kpi-avg-conf',   `${avgConf.toFixed(1)}%`);
    setText('kpi-critical',   String(critical));
    setText('kpi-actionable', String(funnel.actionable || 0));
    setText('kpi-completion',
      total ? `${(((funnel.completed || 0) / total) * 100).toFixed(0)}%` : '—'
    );
  }

  /* ── Final insight card ──────────────────────────────────────────────── */
  function renderInsight(ins) {
    const fo   = ins.final_outlook || {};
    const tier = fo.tier || 'NOMINAL';

    const tierEl  = $('oa-final-tier');
    const probEl  = $('oa-final-prob');
    const horizEl = $('oa-final-horizon');
    const gridEl  = $('oa-final-grid');
    const noteEl  = $('oa-confidence-note');

    if (tierEl)  { tierEl.className = `oa-tier ${tierClass(tier)}`; tierEl.textContent = tier; }
    if (probEl)  probEl.textContent  = `Probability ${((fo.probability || 0) * 100).toFixed(1)}%`;
    if (horizEl) horizEl.textContent = `Horizon ${fo.horizon_hours || 6}h`;

    if (gridEl) {
      const drivers = (ins.key_drivers || [])
        .map(d => `<div class="oa-list-item">· ${esc(d)}</div>`).join('');
      const actions = (ins.recommended_actions || [])
        .map(a => `<div class="oa-list-item">→ ${esc(a)}</div>`).join('');
      const signals = (ins.watch_signals || [])
        .map(s => `<div class="oa-list-item">⚡ ${esc(s)}</div>`).join('');
      gridEl.innerHTML = `
        <div>
          <div class="oa-subtitle">KEY DRIVERS</div>
          ${drivers || '<div class="oa-list-item" style="color:var(--text-muted)">No drivers found</div>'}
        </div>
        <div>
          <div class="oa-subtitle">RECOMMENDED ACTIONS</div>
          ${actions || '<div class="oa-list-item" style="color:var(--text-muted)">No actions</div>'}
        </div>
        <div>
          <div class="oa-subtitle">WATCH SIGNALS</div>
          ${signals || '<div class="oa-list-item" style="color:var(--text-muted)">No signals</div>'}
        </div>`;
    }
    if (noteEl) noteEl.textContent = ins.confidence_note || '';
  }

  /* ── Chart 1: Risk Timeline + MA5 overlay ────────────────────────────── */
  function renderTimeline(t) {
    if (!t) return;
    mkChart('oa-chart-timeline', {
      type: 'line',
      data: {
        labels: t.labels || [],
        datasets: [
          {
            label: 'Risk',
            data: t.risk || [],
            borderColor: '#C47070',
            backgroundColor: 'rgba(196,112,112,.07)',
            tension: 0.4, borderWidth: 2, pointRadius: 0, fill: true,
          },
          {
            label: 'MA5',
            data: t.risk_ma5 || [],
            borderColor: '#C4A840',
            backgroundColor: 'transparent',
            tension: 0.4, borderWidth: 1.5, pointRadius: 0, borderDash: [4, 3],
          },
          {
            label: 'Confidence',
            data: t.confidence || [],
            borderColor: '#5DAF78',
            backgroundColor: 'rgba(93,175,120,.07)',
            tension: 0.4, borderWidth: 1.5, pointRadius: 0, fill: true,
          },
          {
            label: 'Virality',
            data: t.virality || [],
            borderColor: '#6A9DC4',
            backgroundColor: 'transparent',
            tension: 0.4, borderWidth: 1, pointRadius: 0,
          },
        ],
      },
      options: {
        ...CHART_BASE,
        scales: {
          x: CHART_BASE.scales.x,
          y: { ...CHART_BASE.scales.y, min: 0, max: 100 },
        },
      },
    });
  }

  /* ── Chart 2: Tier Distribution (doughnut) ────────────────────────────── */
  function renderTierDist(td) {
    if (!td) return;
    mkChart('oa-chart-tier', {
      type: 'doughnut',
      data: {
        labels: td.labels || ['NOMINAL', 'WATCH', 'ELEVATED', 'CRITICAL'],
        datasets: [{
          data: td.values || [0, 0, 0, 0],
          backgroundColor: ['#5DAF78', '#6A9DC4', '#C4A840', '#C47070'],
          borderWidth: 0,
        }],
      },
      options: {
        ...CHART_BASE,
        cutout: '60%',
        plugins: {
          ...CHART_BASE.plugins,
          legend: {
            position: 'bottom',
            labels: { color: '#888', font: { family: "'JetBrains Mono'", size: 9 } },
          },
        },
      },
    });
  }

  /* ── Chart 3: Confidence vs Risk (scatter) ────────────────────────────── */
  function renderScatter(pts) {
    if (!pts?.length) return;
    const ptColor = (y) =>
      y >= 75 ? '#C47070CC' : y >= 50 ? '#C4A840CC' : y >= 25 ? '#6A9DC4CC' : '#5DAF78CC';
    mkChart('oa-chart-scatter', {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Runs',
          data: pts.map(p => ({ x: p.x, y: p.y })),
          backgroundColor: pts.map(p => ptColor(p.y)),
          pointRadius: 5,
          pointHoverRadius: 7,
        }],
      },
      options: {
        ...CHART_BASE,
        plugins: { ...CHART_BASE.plugins, legend: { display: false } },
        scales: {
          x: {
            ...CHART_BASE.scales.x,
            min: 0, max: 100,
            title: {
              display: true, text: 'Confidence %', color: '#444',
              font: { size: 8, family: "'JetBrains Mono'" },
            },
          },
          y: {
            ...CHART_BASE.scales.y,
            min: 0, max: 100,
            title: {
              display: true, text: 'Risk %', color: '#444',
              font: { size: 8, family: "'JetBrains Mono'" },
            },
          },
        },
      },
    });
  }

  /* ── Chart 4: Sector Avg Risk (horizontal bar) ────────────────────────── */
  function renderSector(items) {
    if (!items?.length) return;
    const sorted = [...items].sort((a, b) => b.avg_risk - a.avg_risk).slice(0, 8);
    mkChart('oa-chart-sector', {
      type: 'bar',
      data: {
        labels: sorted.map(i => i.sector),
        datasets: [{
          label: 'Avg Risk %',
          data: sorted.map(i => i.avg_risk),
          backgroundColor: sorted.map(i =>
            i.avg_risk >= 75 ? '#C47070' : i.avg_risk >= 50 ? '#C4A840' : '#6A9DC4'
          ),
          borderWidth: 0,
        }],
      },
      options: {
        ...CHART_BASE,
        indexAxis: 'y',
        plugins: { ...CHART_BASE.plugins, legend: { display: false } },
        scales: {
          x: { ...CHART_BASE.scales.x, min: 0, max: 100 },
          y: CHART_BASE.scales.y,
        },
      },
    });
  }

  /* ── Chart 5: Driver Contribution (horizontal bar) ────────────────────── */
  function renderDriver(drivers) {
    if (!drivers?.length) return;
    mkChart('oa-chart-driver', {
      type: 'bar',
      data: {
        labels: drivers.map(d => d.driver),
        datasets: [{
          label: 'Count',
          data: drivers.map(d => d.count),
          backgroundColor: '#B8936A',
          borderWidth: 0,
        }],
      },
      options: {
        ...CHART_BASE,
        indexAxis: 'y',
        plugins: { ...CHART_BASE.plugins, legend: { display: false } },
      },
    });
  }

  /* ── Chart 6: Run Funnel (vertical bar) ───────────────────────────────── */
  function renderFunnel(funnel) {
    if (!funnel) return;
    mkChart('oa-chart-funnel', {
      type: 'bar',
      data: {
        labels: ['Started', 'Completed', 'Actionable', 'Confirmed'],
        datasets: [{
          label: 'Runs',
          data: [funnel.started, funnel.completed, funnel.actionable, funnel.confirmed],
          backgroundColor: ['#6A9DC4', '#5DAF78', '#C4A840', '#C47070'],
          borderWidth: 0,
        }],
      },
      options: {
        ...CHART_BASE,
        plugins: { ...CHART_BASE.plugins, legend: { display: false } },
      },
    });
  }

  /* ── Chart 7: Lead-time Trend (line) ──────────────────────────────────── */
  function renderLeadTime(lt) {
    if (!lt?.length) return;
    mkChart('oa-chart-leadtime', {
      type: 'line',
      data: {
        labels: lt.map(p => p.label),
        datasets: [{
          label: 'Minutes',
          data: lt.map(p => p.minutes),
          borderColor: '#6A9DC4',
          backgroundColor: 'rgba(106,157,196,.08)',
          tension: 0.4, borderWidth: 2, pointRadius: 0, fill: true,
        }],
      },
      options: {
        ...CHART_BASE,
        plugins: { ...CHART_BASE.plugins, legend: { display: false } },
      },
    });
  }

  /* ── History table ───────────────────────────────────────────────────── */
  async function loadHistory() {
    const f    = filters();
    const body = $('oa-history-body');
    if (body) body.innerHTML = '<tr><td colspan="9" class="oa-empty">Loading…</td></tr>';

    let data;
    try {
      data = await Api.getOracleHistory({
        limit:  HIST_LIMIT,
        offset: histPage * HIST_LIMIT,
        zone:   f.zone,
        sector: f.sector,
        status: f.status,
      });
    } catch {
      if (body) body.innerHTML = '<tr><td colspan="9" class="oa-empty">Failed to load history.</td></tr>';
      return;
    }

    const items = data?.items || [];
    histTotal = data?.total || 0;

    setText('oa-history-total', `${histTotal} total runs`);

    const prevBtn   = $('oa-prev-page');
    const nextBtn   = $('oa-next-page');
    const pageLabel = $('oa-page-label');
    const totalPages = Math.max(1, Math.ceil(histTotal / HIST_LIMIT));
    if (prevBtn)   prevBtn.disabled  = histPage === 0;
    if (nextBtn)   nextBtn.disabled  = (histPage + 1) * HIST_LIMIT >= histTotal;
    if (pageLabel) pageLabel.textContent = `Page ${histPage + 1} of ${totalPages}`;

    if (!items.length) {
      if (body) body.innerHTML = '<tr><td colspan="9" class="oa-empty">No runs found for this filter.</td></tr>';
      return;
    }

    if (body) {
      body.innerHTML = items.map(r => {
        const id   = r.simulation_id || r.id || '—';
        const risk = Number(r.risk_of_backlash || 0);
        const conf = Number(r.confidence || 0);
        const tier = tierFromRisk(risk);
        const chk  = selectedIds.has(id) ? ' checked' : '';
        const created = r.created_at
          ? new Date(r.created_at).toLocaleString([], {
              month: 'short', day: 'numeric',
              hour: '2-digit', minute: '2-digit',
            })
          : '—';
        return `<tr data-id="${esc(id)}">
          <td><input type="checkbox" class="oa-row-check" data-id="${esc(id)}"${chk}></td>
          <td style="font-family:var(--font-mono);font-size:9px;color:var(--text-secondary)"
              title="${esc(id)}">${esc(id.slice(0, 12))}…</td>
          <td>${esc(r.zone   || '—')}</td>
          <td>${esc(r.sector || '—')}</td>
          <td><span class="oa-tier ${tierClass(tier)}">${tier}</span></td>
          <td style="font-family:var(--font-mono)">${(risk * 100).toFixed(1)}</td>
          <td style="font-family:var(--font-mono)">${(conf * 100).toFixed(1)}</td>
          <td><span style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">${esc(r.status || '—')}</span></td>
          <td style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">${esc(created)}</td>
        </tr>`;
      }).join('');

      body.querySelectorAll('.oa-row-check').forEach(cb => {
        cb.addEventListener('change', () => onRowCheck(cb));
      });
    }

    refreshSelectAll();
    updateCompareBtn();
  }

  function onRowCheck(cb) {
    const id = cb.dataset.id;
    if (cb.checked) {
      if (selectedIds.size >= 3) { cb.checked = false; return; }
      selectedIds.add(id);
    } else {
      selectedIds.delete(id);
    }
    refreshSelectAll();
    updateCompareBtn();
  }

  function refreshSelectAll() {
    const sa = $('oa-select-all');
    if (!sa) return;
    const checks = document.querySelectorAll('.oa-row-check');
    const allChecked = checks.length > 0 && [...checks].every(c => c.checked);
    sa.checked      = allChecked;
    sa.indeterminate = !allChecked && selectedIds.size > 0;

    const countEl = $('oa-selected-count');
    if (countEl) {
      countEl.textContent = selectedIds.size ? `${selectedIds.size} selected (max 3)` : '';
    }
  }

  /* ── Compare ─────────────────────────────────────────────────────────── */
  function updateCompareBtn() {
    const btn = $('oa-compare-btn');
    if (btn) btn.disabled = selectedIds.size < 2;
  }

  async function runCompare() {
    if (selectedIds.size < 2) return;
    const btn = $('oa-compare-btn');
    if (btn) { btn.disabled = true; btn.textContent = 'Loading…'; }

    let data;
    try {
      data = await Api.compareOracleRuns([...selectedIds]);
    } catch {
      if (btn) { btn.disabled = false; btn.textContent = 'Compare Selected'; }
      return;
    }

    const items = data?.items || [];
    if (!items.length) {
      if (btn) { btn.disabled = false; btn.textContent = 'Compare Selected'; }
      return;
    }

    $('oa-compare-hint')?.setAttribute('style', 'display:none');
    const canvas = $('oa-chart-compare');
    if (canvas) canvas.style.display = 'block';

    mkChart('oa-chart-compare', {
      type: 'bar',
      data: {
        labels: items.map(r => (r.simulation_id || '').slice(0, 8)),
        datasets: [
          {
            label: 'Risk %',
            data: items.map(r => ((r.risk_of_backlash || 0) * 100).toFixed(1)),
            backgroundColor: '#C47070', borderWidth: 0,
          },
          {
            label: 'Confidence %',
            data: items.map(r => ((r.confidence || 0) * 100).toFixed(1)),
            backgroundColor: '#5DAF78', borderWidth: 0,
          },
        ],
      },
      options: CHART_BASE,
    });

    const detail = $('oa-compare-detail');
    if (detail) {
      detail.innerHTML = items.map(r => {
        const tier = tierFromRisk(Number(r.risk_of_backlash || 0));
        return `<div style="margin-bottom:4px">
          <span class="oa-tier ${tierClass(tier)}">${tier}</span>
          <span style="margin-left:6px">${esc(r.zone || '—')} · ${esc(r.sector || '—')} · ${((r.confidence || 0) * 100).toFixed(0)}% conf</span>
        </div>`;
      }).join('');
    }

    const clearBtn = $('oa-compare-clear');
    if (clearBtn) clearBtn.style.display = 'inline-block';

    if (btn) { btn.disabled = false; btn.textContent = 'Compare Selected'; }
  }

  function clearCompare() {
    selectedIds.clear();
    updateCompareBtn();
    refreshSelectAll();
    document.querySelectorAll('.oa-row-check').forEach(cb => { cb.checked = false; });

    const canvas = $('oa-chart-compare');
    if (canvas) canvas.style.display = 'none';
    const hint = $('oa-compare-hint');
    if (hint) hint.style.display = 'block';
    const detail = $('oa-compare-detail');
    if (detail) detail.innerHTML = '';
    const clearBtn = $('oa-compare-clear');
    if (clearBtn) clearBtn.style.display = 'none';

    if (charts['oa-chart-compare']) {
      charts['oa-chart-compare'].destroy();
      delete charts['oa-chart-compare'];
    }
  }

  /* ── Chat ────────────────────────────────────────────────────────────── */
  function appendMsg(role, text) {
    const log = $('oa-chat-log');
    if (!log) return;
    const empty = log.querySelector('.oa-chat-empty');
    if (empty) empty.remove();
    const el = document.createElement('div');
    el.className = `oa-chat-msg oa-chat-msg--${role}`;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  async function sendChat() {
    const input   = $('oa-chat-input');
    const sendBtn = $('oa-chat-send');
    const q = (input?.value || '').trim();
    if (!q) return;
    if (input)   input.value = '';
    if (sendBtn) sendBtn.disabled = true;

    appendMsg('user', q);

    const chatLog = $('oa-chat-log');
    const pending = document.createElement('div');
    pending.className = 'oa-chat-pending';
    pending.textContent = 'Thinking…';
    chatLog?.appendChild(pending);
    if (chatLog) chatLog.scrollTop = chatLog.scrollHeight;

    const f = filters();
    let resp;
    try {
      resp = await Api.askOracleChat({
        question: q,
        zone:     f.zone,
        sector:   f.sector,
        status:   f.status || 'complete',
      });
    } catch {
      pending.remove();
      appendMsg('ai', 'Oracle chat is temporarily unavailable — try again shortly.');
      if (sendBtn) sendBtn.disabled = false;
      return;
    }

    pending.remove();
    appendMsg('ai', resp.answer || '—');

    const modeEl = $('oa-chat-mode');
    if (modeEl) {
      modeEl.textContent =
        `Mode: ${resp.mode_used || 'rule_based'} · confidence ${((resp.confidence || 0) * 100).toFixed(0)}%`;
    }

    const evBox = $('oa-chat-evidence');
    if (evBox && resp.evidence?.length) {
      evBox.style.display = 'block';
      evBox.innerHTML =
        `<div style="font-size:9px;color:var(--text-muted);font-family:var(--font-mono);margin-bottom:4px">EVIDENCE</div>` +
        resp.evidence.map(e =>
          `<div class="oa-evidence-item">` +
          `${esc(e.zone || '—')} · ${esc(e.risk_pct)}% risk · ${esc(e.confidence_pct)}% conf ` +
          `<span style="color:var(--text-muted)">${esc((e.simulation_id || '').slice(0, 12))}</span>` +
          `</div>`
        ).join('');
    }

    if (sendBtn) sendBtn.disabled = false;
  }

  /* ── Boot ────────────────────────────────────────────────────────────── */
  async function boot() {
    const Ctx = global.CityPulseContext;
    if (Ctx) Ctx.renderBanner('analytics');

    /* Toolbar */
    $('oa-refresh')?.addEventListener('click', () => {
      clearCompare();
      loadAll();
    });

    ['oa-zone', 'oa-sector', 'oa-days', 'oa-status'].forEach(id => {
      $(id)?.addEventListener('change', () => {
        clearCompare();
        loadAll();
      });
    });

    /* Pagination */
    $('oa-prev-page')?.addEventListener('click', () => {
      if (histPage > 0) { histPage--; loadHistory(); }
    });
    $('oa-next-page')?.addEventListener('click', () => {
      histPage++;
      loadHistory();
    });

    /* Select-all */
    $('oa-select-all')?.addEventListener('change', (e) => {
      document.querySelectorAll('.oa-row-check').forEach(cb => {
        if (e.target.checked) {
          if (selectedIds.size < 3) {
            selectedIds.add(cb.dataset.id);
            cb.checked = true;
          }
        } else {
          selectedIds.delete(cb.dataset.id);
          cb.checked = false;
        }
      });
      updateCompareBtn();
      refreshSelectAll();
    });

    /* Compare */
    $('oa-compare-btn')?.addEventListener('click', runCompare);
    $('oa-compare-clear')?.addEventListener('click', clearCompare);

    /* Chat */
    $('oa-chat-send')?.addEventListener('click', sendChat);
    $('oa-chat-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendChat();
    });

    /* Initial load */
    await loadAll();

    /* Auto-refresh every 5 min */
    setInterval(loadAll, 300_000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})(typeof window !== 'undefined' ? window : globalThis);
