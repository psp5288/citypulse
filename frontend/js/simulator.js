/* DevCity Pulse — The Oracle: simulation form, polling, Chart.js results */
(function (global) {
  const Api = global.DevCityApi;

  let sentimentChart = null;
  let pollTimer      = null;
  let selectedSector = 'general';
  let monitorPrompt = '';

  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ── Zone dropdown ───────────────────────────────────────────────────── */

  async function loadDistricts() {
    const sel = $('field-zone');
    if (!sel) return;
    try {
      const districts = await Api.getDistricts();
      const list = Array.isArray(districts) ? districts : (districts.districts || []);
      sel.innerHTML = list.map(
        (d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`
      ).join('') || '<option value="downtown">Downtown Core</option>';
    } catch {
      sel.innerHTML = '<option value="downtown">Downtown Core</option>';
    }

    /* Pre-select from query string */
    const p = new URLSearchParams(location.search);
    const q = p.get('district') || p.get('zone');
    if (q) { const o = Array.from(sel.options).find((o) => o.value === q); if (o) sel.value = q; }
  }

  /* ── Sector selector ─────────────────────────────────────────────────── */

  function initSectors() {
    document.querySelectorAll('.sector-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.sector-btn').forEach((b) => b.classList.remove('active'));
        btn.classList.add('active');
        selectedSector = btn.dataset.sector || 'general';
      });
    });
  }

  /* ── Agent slider ────────────────────────────────────────────────────── */

  function initSlider() {
    const sl = $('field-agents');
    const lbl = $('agents-val');
    if (!sl || !lbl) return;
    sl.addEventListener('input', () => { lbl.textContent = sl.value; });
  }

  /* ── Collapsible external factors ────────────────────────────────────── */

  function initCollapsible() {
    const header = document.querySelector('.collapsible-header');
    const body   = document.querySelector('.collapsible-body');
    const arrow  = document.querySelector('.collapsible-arrow');
    if (!header || !body) return;
    header.addEventListener('click', () => {
      body.classList.toggle('open');
      if (arrow) arrow.textContent = body.classList.contains('open') ? '▲' : '▼';
    });
  }

  function addFactorRow(prefill) {
    const host = $('external-factors');
    if (!host) return;
    if (host.querySelectorAll('.factor-row').length >= 3) return;
    const row = document.createElement('div');
    row.className = 'factor-row';
    row.innerHTML = `
      <div>
        <label class="form-label">Type</label>
        <select class="factor-type" style="padding:8px;background:var(--bg-surface);border:1px solid var(--bg-border);color:var(--text-primary);border-radius:4px;width:100%;font-family:var(--font-mono);font-size:11px">
          <option value="counter_rumour">Counter Rumour</option>
          <option value="authority_denial">Authority Denial</option>
          <option value="viral_controversy">Viral Controversy</option>
          <option value="confirmation_leak">Confirmation Leak</option>
        </select>
      </div>
      <div>
        <label class="form-label">Content</label>
        <input type="text" class="factor-content" placeholder="Describe the factor..." style="padding:8px;background:var(--bg-surface);border:1px solid var(--bg-border);color:var(--text-primary);border-radius:4px;width:100%;font-family:var(--font-mono);font-size:11px"/>
      </div>
      <button type="button" class="factor-remove" title="Remove">&times;</button>`;
    row.querySelector('.factor-remove').addEventListener('click', () => row.remove());
    if (prefill) {
      row.querySelector('.factor-type').value         = prefill.type || 'counter_rumour';
      row.querySelector('.factor-content').value      = prefill.content || '';
    }
    host.appendChild(row);
  }

  function collectFactors() {
    const host = $('external-factors');
    if (!host) return [];
    return [...host.querySelectorAll('.factor-row')].map((row) => ({
      type:             row.querySelector('.factor-type')?.value || 'counter_rumour',
      content:          row.querySelector('.factor-content')?.value?.trim() || '',
      inject_at_minute: 0,
    })).filter((f) => f.content);
  }

  /* ── Scenarios ───────────────────────────────────────────────────────── */

  const SCENARIOS = {
    banking_crisis: {
      news_item: 'The Federal Reserve has announced an emergency 1.5% interest rate increase effective immediately, citing persistent inflation concerns.',
      sector: 'banking',
      factors: [{ type: 'counter_rumour', content: 'Anonymous sources suggest the rate hike may be reversed within 90 days', inject_at_minute: 45 }],
    },
    policy_announcement: {
      news_item: 'Mayor announces new $15 daily congestion pricing charge for all vehicles entering the downtown zone, effective next month.',
      sector: 'government',
      factors: [{ type: 'viral_controversy', content: 'Leaked memo suggests exemptions for wealthy neighbourhoods', inject_at_minute: 30 }],
    },
    news_breakout: {
      news_item: 'Breaking: Major cyber-attack has disrupted critical city infrastructure including traffic systems and emergency services.',
      sector: 'crisis',
      factors: [{ type: 'authority_denial', content: 'City officials deny severity of the incident, claim systems restored', inject_at_minute: 20 }],
    },
  };

  function applyScenario(key) {
    const sc = SCENARIOS[key];
    if (!sc) return;
    const news = $('field-news');
    if (news) news.value = sc.news_item;
    selectedSector = sc.sector;
    document.querySelectorAll('.sector-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.sector === sc.sector);
    });
    const host = $('external-factors');
    if (host) host.innerHTML = '';
    (sc.factors || []).forEach((f) => addFactorRow(f));
    const body = document.querySelector('.collapsible-body');
    const arrow = document.querySelector('.collapsible-arrow');
    if (body && sc.factors?.length) { body.classList.add('open'); if (arrow) arrow.textContent = '▲'; }
  }

  /* ── Run button state ────────────────────────────────────────────────── */

  function setRunning(running, label) {
    const btn = $('run-btn');
    if (!btn) return;
    btn.disabled = running;
    btn.textContent = label || (running ? 'Running…' : '→ Run Simulation');
    const prog = $('run-progress');
    if (prog) prog.style.display = running ? 'block' : 'none';
  }

  /* ── Results rendering ───────────────────────────────────────────────── */

  function renderEmpty() {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `<div class="results-empty">
      <div class="oracle-glyph">◈</div>
      <div>Configure and run a simulation<br/>to see predictions appear here</div>
    </div>`;
  }

  function renderSkeleton() {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `<div style="padding:24px">
      <div class="skeleton" style="height:160px;margin-bottom:16px"></div>
      <div class="skeleton" style="height:80px;margin-bottom:16px"></div>
      <div class="skeleton" style="height:80px"></div>
    </div>`;
  }

  function renderRunning(res) {
    const panel = $('results-panel');
    if (!panel) return;
    const progress = Math.round((Number(res.progress_pct) || 0) * 100);
    const processed = Number(res.processed_agents || 0);
    const total = Number(res.total_agents || 0);
    const actions = Array.isArray(res.recent_actions) ? res.recent_actions : [];
    const breakdown = res.action_breakdown || {};

    const filtered = monitorPrompt
      ? actions.filter((a) => {
          const s = `${a.archetype || ''} ${a.action || ''} ${a.sentiment || ''} ${a.reasoning || ''}`.toLowerCase();
          return s.includes(monitorPrompt.toLowerCase());
        })
      : actions;

    const actionRows = filtered.slice(-16).reverse().map((a) => `
      <div style="display:flex;gap:8px;align-items:flex-start;padding:8px 10px;border-bottom:1px solid var(--bg-border)">
        <span style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted);min-width:72px">${esc(a.archetype || 'agent')}</span>
        <span style="font-family:var(--font-mono);font-size:9px;color:var(--accent);min-width:56px">${esc(a.action || '-')}</span>
        <span style="font-family:var(--font-mono);font-size:9px;color:var(--text-secondary);min-width:56px">${esc(a.sentiment || '-')}</span>
        <span style="font-size:10px;color:var(--text-secondary);line-height:1.5">${esc((a.reasoning || '').slice(0, 96))}</span>
      </div>
    `).join('');

    const chips = Object.entries(breakdown).map(([k, v]) =>
      `<span style="display:inline-flex;gap:5px;padding:4px 8px;border:1px solid var(--bg-border);border-radius:12px;font-family:var(--font-mono);font-size:9px;color:var(--text-secondary)">${esc(k)}<strong style="color:var(--text-primary)">${v}</strong></span>`
    ).join('');

    panel.innerHTML = `<div style="padding:24px">
      <p style="font-family:var(--font-mono);font-size:12px;color:var(--accent);margin-bottom:16px">
        ⏳ Agents processing... (${esc(res.status || 'running')})
      </p>
      <p style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);margin-bottom:16px">
        Simulation ID: <span style="color:var(--cyan)">${esc(res.simulation_id)}</span>
      </p>
      <div style="margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;font-family:var(--font-mono);font-size:10px;color:var(--text-muted);margin-bottom:6px">
          <span>Swarm Progress</span>
          <span>${processed}/${total} (${progress}%)</span>
        </div>
        <div class="score-track" style="height:6px"><div class="score-fill" style="height:100%;width:${progress}%;background:var(--accent)"></div></div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">${chips || '<span style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted)">No actions yet</span>'}</div>
      <div style="display:flex;gap:8px;align-items:center;margin-bottom:10px">
        <input id="monitor-prompt" value="${esc(monitorPrompt)}" placeholder="Prompt bar: filter by action/archetype/sentiment" style="flex:1;padding:8px 10px;background:var(--bg-elevated);border:1px solid var(--bg-border);color:var(--text-primary);border-radius:6px;font-family:var(--font-mono);font-size:10px" />
        <button id="monitor-apply" class="btn btn--ghost btn--sm">Apply</button>
      </div>
      <div style="border:1px solid var(--bg-border);border-radius:8px;max-height:220px;overflow:auto;background:var(--bg-surface)">
        ${actionRows || '<div style="padding:12px;font-family:var(--font-mono);font-size:10px;color:var(--text-muted)">Waiting for live agent actions…</div>'}
      </div>
    </div>`;
    const input = $('monitor-prompt');
    const apply = $('monitor-apply');
    if (apply && input) {
      const submit = () => {
        monitorPrompt = input.value.trim();
        renderRunning(res);
      };
      apply.addEventListener('click', submit);
      input.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    }
  }

  function renderFailed(msg) {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `<div style="padding:24px;color:var(--red);font-family:var(--font-mono);font-size:12px">
      ✗ ${esc(msg || 'Simulation failed.')}
    </div>`;
  }

  function renderComplete(res) {
    const panel = $('results-panel');
    if (!panel) return;
    const ps   = res.predicted_sentiment || {};
    const pos  = Number(ps.positive  || 0);
    const neu  = Number(ps.neutral   || 0);
    const neg  = Number(ps.negative  || 0);
    const vir  = Number(res.predicted_virality   || 0);
    const back = Number(res.risk_of_backlash      || 0);
    const conf = res.confidence ? `${Math.round(res.confidence * 100)}%` : '—';
    const vs   = res.vs_real_time || {};

    function bar(label, val, good) {
      const col = val > 0.66 ? (good ? '#24A148' : '#DA1E28')
                : val > 0.33 ? '#F0A500'
                : (good ? '#DA1E28' : '#24A148');
      return `<div class="score-bar">
        <span class="score-label">${label}</span>
        <div class="score-track"><div class="score-fill" style="width:${Math.round(val*100)}%;background:${col}"></div></div>
        <span class="score-value">${val.toFixed(2)}</span>
      </div>`;
    }

    panel.innerHTML = `
      <div class="result-card">
        <div class="result-card__header">
          <span class="result-card__title">Simulation Complete ✓</span>
          <span class="result-card__confidence">Confidence ${conf}</span>
        </div>
        <div class="result-card__body">
          <div class="chart-box"><canvas id="sentiment-donut"></canvas></div>
        </div>
      </div>

      <div class="result-card">
        <div class="result-card__header"><span class="result-card__title">Predicted Metrics</span></div>
        <div class="result-card__body">
          ${bar('Virality', vir, false)}
          ${bar('Backlash', back, false)}
          <div class="result-metric">
            <span class="result-metric__label">Peak Reaction</span>
            <span class="result-metric__value">${esc(res.peak_reaction_time || '—')}</span>
          </div>
        </div>
      </div>

      ${vs.accuracy ? `<div class="result-card">
        <div class="result-card__header"><span class="result-card__title">vs. Real-Time Baseline</span></div>
        <div class="result-card__body">
          <div class="result-metric">
            <span class="result-metric__label">Predicted Negative</span>
            <span class="result-metric__value">${((vs.predicted_negative||0)*100).toFixed(1)}%</span>
          </div>
          <div class="result-metric">
            <span class="result-metric__label">Actual Negative</span>
            <span class="result-metric__value">${((vs.real_sentiment_negative||0)*100).toFixed(1)}%</span>
          </div>
          <div class="result-metric">
            <span class="result-metric__label">Accuracy</span>
            <span class="result-metric__value" style="color:var(--green)">${esc(vs.accuracy)}</span>
          </div>
        </div>
      </div>` : ''}`;

    /* Donut chart */
    const ctx = $('sentiment-donut');
    if (ctx && global.Chart) {
      if (sentimentChart) sentimentChart.destroy();
      sentimentChart = new global.Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['Positive', 'Neutral', 'Negative'],
          datasets: [{ data: [pos, neu, neg], backgroundColor: ['#24A148', '#F0A500', '#DA1E28'], borderWidth: 0 }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '65%',
          plugins: {
            legend: { position: 'bottom', labels: { color: '#A8B8CC', font: { size: 11, family: "'IBM Plex Mono'" } } },
          },
        },
      });
    }
  }

  /* ── Polling ─────────────────────────────────────────────────────────── */

  async function pollOnce(id) {
    try {
      const res = await Api.getSimulation(id);
      if (res.error)           { renderFailed('Simulation not found.'); return true; }
      if (res.status === 'complete') { renderComplete(res); loadHistory(); return true; }
      if (res.status === 'failed')   { renderFailed('Swarm run failed.'); return true; }
      renderRunning(res);
      return false;
    } catch {
      renderFailed('Polling error — check server.');
      return true;
    }
  }

  async function pollSimulation(id) {
    if (pollTimer) clearInterval(pollTimer);
    const done = await pollOnce(id);
    if (done) { setRunning(false); return; }
    pollTimer = setInterval(async () => {
      const finished = await pollOnce(id);
      if (finished) { clearInterval(pollTimer); setRunning(false); }
    }, 2000);
  }

  /* ── Form submit ─────────────────────────────────────────────────────── */

  async function onSubmit(ev) {
    ev.preventDefault();
    const zone      = $('field-zone')?.value;
    const news_item = $('field-news')?.value?.trim();
    const n_agents  = parseInt($('field-agents')?.value || '1000', 10);
    if (!zone || !news_item) return;

    const body = {
      zone,
      news_item,
      sector: selectedSector,
      n_agents: Math.min(1000, Math.max(50, n_agents)),
      external_factors: collectFactors(),
    };

    renderSkeleton();
    setRunning(true, `⏳ Running 0/${body.n_agents} agents…`);

    try {
      const res = await Api.postSimulate(body);
      renderRunning(res);
      await pollSimulation(res.simulation_id);
    } catch (e) {
      renderFailed(e.message || 'Request failed');
      setRunning(false);
    }
  }

  /* ── History table ───────────────────────────────────────────────────── */

  async function loadHistory() {
    const tbody = $('history-body');
    if (!tbody) return;
    try {
      const rows = await Api.getSimulationHistory(20);
      if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center">No simulations yet</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map((r) => {
        const ps  = r.predicted_sentiment || {};
        const neg = ps.negative ? `${((ps.negative)*100).toFixed(0)}% neg` : '—';
        return `<tr>
          <td style="font-family:var(--font-mono)">${esc((r.simulation_id||'').slice(0,8))}…</td>
          <td>${esc(r.zone||'')}</td>
          <td title="${esc(r.news_item||'')}">${esc((r.news_item||'').slice(0,40))}${(r.news_item||'').length>40?'…':''}</td>
          <td>${esc(neg)}</td>
          <td>${r.predicted_virality!=null ? Number(r.predicted_virality).toFixed(2) : '—'}</td>
          <td style="color:var(--green)">${esc(r.vs_real_time?.accuracy||'—')}</td>
        </tr>`;
      }).join('');
    } catch {
      tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted)">Failed to load history</td></tr>';
    }
  }

  /* ── Boot ────────────────────────────────────────────────────────────── */

  async function boot() {
    await loadDistricts();
    initSectors();
    initSlider();
    initCollapsible();
    renderEmpty();

    $('sim-form')?.addEventListener('submit', onSubmit);
    $('btn-add-factor')?.addEventListener('click', () => addFactorRow());
    $('btn-sc-banking')?.addEventListener('click', () => applyScenario('banking_crisis'));
    $('btn-sc-policy') ?.addEventListener('click', () => applyScenario('policy_announcement'));
    $('btn-sc-news')   ?.addEventListener('click', () => applyScenario('news_breakout'));

    await loadHistory();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})(typeof window !== 'undefined' ? window : globalThis);
