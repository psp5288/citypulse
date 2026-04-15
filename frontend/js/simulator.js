/* DevCity Pulse — The Oracle  (D3 force-graph + simulation UI) */
(function (global) {
  'use strict';
  const Api = global.DevCityApi;

  let sentimentChart  = null;
  let forecastChart   = null;
  let pollTimer       = null;
  let pollFailures    = 0;
  let selectedSector  = 'general';
  let monitorPrompt   = '';
  let customTarget    = null;
  let agentGraph      = null;

  const $ = (id) => document.getElementById(id);
  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ════════════════════════════════════════════════════════════════════════
     ARCHETYPE / ACTION METADATA
     ════════════════════════════════════════════════════════════════════════ */
  const ARCHETYPE_META = {
    passive_consumer:  { label: 'Passive Consumer', color: '#6A9DC4', short: 'PASS' },
    skeptic:           { label: 'Skeptic',           color: '#8A6AC4', short: 'SKPT' },
    emotional_reactor: { label: 'Emotional',         color: '#C47070', short: 'EMOT' },
    early_adopter:     { label: 'Early Adopter',     color: '#70B8C4', short: 'ADPT' },
    amplifier:         { label: 'Amplifier',         color: '#C4A840', short: 'AMPL' },
    contrarian:        { label: 'Contrarian',        color: '#C4708A', short: 'CONT' },
    institutional:     { label: 'Institutional',     color: '#5DAF78', short: 'INST' },
  };

  const ACTION_META = {
    SHARE:    { label: 'SHARE',    cls: 'action-share'    },
    REACT:    { label: 'REACT',    cls: 'action-react'    },
    PROTEST:  { label: 'PROTEST',  cls: 'action-protest'  },
    PASS:     { label: 'PASS',     cls: 'action-pass'     },
    INVEST:   { label: 'INVEST',   cls: 'action-invest'   },
    WITHDRAW: { label: 'WITHDRAW', cls: 'action-withdraw' },
    AMPLIFY:  { label: 'AMPLIFY',  cls: 'action-amplify'  },
    DISMISS:  { label: 'DISMISS',  cls: 'action-dismiss'  },
  };

  function archetypeKey(raw) { return (raw || '').toLowerCase().replace(/\s+/g, '_'); }
  function archetypeMeta(raw) { return ARCHETYPE_META[archetypeKey(raw)] || { label: raw || 'Agent', color: '#888', short: (raw||'AGT').slice(0,4).toUpperCase() }; }
  function actionMeta(raw)    { return ACTION_META[(raw||'').toUpperCase()] || { label: (raw||'—').toUpperCase(), cls: 'action-default' }; }
  function sentimentClass(s)  { return { positive:'sent-positive', negative:'sent-negative' }[(s||'').toLowerCase()] || 'sent-neutral'; }

  /* ════════════════════════════════════════════════════════════════════════
     D3 AGENT WEB GRAPH — MiroFish-exact SVG force-directed network
     • 10px base radius, white stroke (MiroFish style)
     • Pink #E91E63 selected, blue #3498db connected edges
     • Quadratic bezier curves, drag-threshold 3px, zoom 0.1-4x
     • Floating legend (bottom-left) + detail panel (top-right)
     ════════════════════════════════════════════════════════════════════════ */
  class AgentWebGraph {
    constructor(wrap) {
      this.wrap = wrap;
      this.d3   = global.d3;
      this._running    = false;
      this._sim        = null;
      this._svg        = null;
      this._g          = null;
      this._nodeEl     = null;
      this._linkEl     = null;
      this._linkLblEl  = null;
      this._resizeObs  = null;
      this._selectedId = null;

      /* Base radius (MiroFish: 10px) */
      this.BASE_R = 10;

      /* Node data */
      this.nodeData = Object.entries(ARCHETYPE_META).map(([id, m]) => ({
        id, label: m.label, short: m.short, color: m.color,
        count: 0, r: this.BASE_R, lastActive: 0, sentiment: {}, topAction: null,
      }));

      /* Edge topology (matches cascade logic in swarm_engine) */
      this.edgeData = [
        { source: 'emotional_reactor', target: 'passive_consumer',  rel: 'cascade' },
        { source: 'emotional_reactor', target: 'skeptic',           rel: 'cascade' },
        { source: 'amplifier',         target: 'passive_consumer',  rel: 'cascade' },
        { source: 'amplifier',         target: 'institutional',     rel: 'cascade' },
        { source: 'early_adopter',     target: 'amplifier',         rel: 'cascade' },
        { source: 'early_adopter',     target: 'emotional_reactor', rel: 'cascade' },
        { source: 'passive_consumer',  target: 'institutional',     rel: 'cascade' },
        { source: 'contrarian',        target: 'skeptic',           rel: 'counter' },
        { source: 'contrarian',        target: 'institutional',     rel: 'counter' },
        { source: 'skeptic',           target: 'passive_consumer',  rel: 'counter' },
      ].map(e => ({ ...e, active: false, weight: 1 }));

      this._init();
    }

    /* ─ helpers ─ */
    _isLight() { return document.documentElement.dataset.theme === 'light'; }
    _edgeDefault(d) {
      if (this._isLight()) return d.rel === 'counter' ? 'rgba(196,112,138,0.35)' : '#C0C0C0';
      return d.rel === 'counter' ? 'rgba(196,112,138,0.4)' : 'rgba(255,255,255,0.15)';
    }
    _edgeActive(d) {
      if (this._isLight()) return d.rel === 'counter' ? '#E91E63' : '#3498db';
      return d.rel === 'counter' ? '#E91E63' : '#3498db';
    }
    _nodeStroke(_d, selected) {
      if (selected) return '#E91E63';
      return this._isLight() ? '#FFFFFF' : 'rgba(255,255,255,0.85)';
    }
    _labelColor() { return this._isLight() ? '#333333' : 'rgba(255,255,255,0.6)'; }
    _edgeLabelColor() { return this._isLight() ? '#999999' : '#444444'; }

    /* ── Init SVG + simulation ── */
    _init() {
      const d3 = this.d3;
      if (!d3) { console.warn('[AgentWebGraph] D3 not loaded'); return; }

      d3.select(this.wrap).selectAll('*:not(#graph-node-detail):not(.graph-float-legend)').remove();

      const rect = this.wrap.getBoundingClientRect();
      this.W = Math.max(300, rect.width);
      this.H = Math.max(320, rect.height);

      /* SVG */
      const svg = d3.select(this.wrap).insert('svg', ':first-child')
        .attr('width',  '100%')
        .attr('height', '100%')
        .style('position', 'absolute')
        .style('inset', '0')
        .style('overflow', 'hidden');
      this._svg = svg;

      /* Defs: arrowhead markers — MiroFish exact */
      const defs = svg.append('defs');
      const addArrow = (id, color) =>
        defs.append('marker')
          .attr('id', id)
          .attr('viewBox', '0 -4 8 8')
          .attr('refX', 14).attr('refY', 0)
          .attr('markerWidth', 6).attr('markerHeight', 6)
          .attr('orient', 'auto')
          .append('path').attr('d', 'M0,-4L8,0L0,4').attr('fill', color);
      addArrow('arr-cas',  this._isLight() ? '#AAAAAA' : '#555555');
      addArrow('arr-cas-a', '#3498db');
      addArrow('arr-cnt',  this._isLight() ? '#E91E6355' : '#C4708A55');
      addArrow('arr-cnt-a', '#E91E63');

      /* Zoom / pan — 0.1x to 4x (MiroFish) */
      const g = svg.append('g');
      this._g = g;
      svg.call(
        d3.zoom().scaleExtent([0.1, 4])
          .on('zoom', (ev) => g.attr('transform', ev.transform))
      );

      /* Layer order: links → link-labels → nodes */
      this._linkG    = g.append('g').attr('class', 'links');
      this._linkLblG = g.append('g').attr('class', 'link-labels');
      this._nodeG    = g.append('g').attr('class', 'nodes');

      /* Force simulation — MiroFish params */
      this._sim = d3.forceSimulation(this.nodeData)
        .force('link',    d3.forceLink(this.edgeData).id(d => d.id).distance(150))
        .force('charge',  d3.forceManyBody().strength(-400))
        .force('center',  d3.forceCenter(this.W / 2, this.H / 2))
        .force('collide', d3.forceCollide(50))
        .force('x',       d3.forceX(this.W / 2).strength(0.04))
        .force('y',       d3.forceY(this.H / 2).strength(0.04))
        .on('tick', () => this._tick());

      this._renderElements();

      /* Click background → deselect */
      svg.on('click', (ev) => {
        if (ev.target.tagName === 'svg') {
          this._selectedId = null;
          this._hideDetail();
          this._resetHighlight();
        }
      });

      /* ResizeObserver */
      this._resizeObs = new ResizeObserver(() => {
        const r = this.wrap.getBoundingClientRect();
        this.W = r.width; this.H = r.height;
        this._sim
          .force('center', d3.forceCenter(this.W / 2, this.H / 2))
          .force('x', d3.forceX(this.W / 2).strength(0.04))
          .force('y', d3.forceY(this.H / 2).strength(0.04))
          .alpha(0.2).restart();
      });
      this._resizeObs.observe(this.wrap);

      this._buildFloatLegend();
    }

    /* ── Build floating legend (bottom-left, MiroFish style) ── */
    _buildFloatLegend() {
      let leg = this.wrap.querySelector('.graph-float-legend');
      if (!leg) {
        leg = document.createElement('div');
        leg.className = 'graph-float-legend';
        this.wrap.appendChild(leg);
      }
      leg.innerHTML = `
        <div class="gfl-title">ARCHETYPE KEY</div>
        <div class="gfl-items">
          ${Object.values(ARCHETYPE_META).map(m =>
            `<div class="gfl-item">
              <span class="gfl-dot" style="background:${m.color}"></span>
              <span class="gfl-lbl">${m.label}</span>
            </div>`).join('')}
        </div>`;
    }

    /* ── Draw all SVG elements ── */
    _renderElements() {
      const d3 = this.d3;

      /* Links — straight lines (MiroFish default for single edges) */
      this._linkEl = this._linkG.selectAll('path')
        .data(this.edgeData).enter().append('path')
        .attr('fill', 'none')
        .attr('stroke', d => this._edgeDefault(d))
        .attr('stroke-width', 1.5)
        .attr('marker-end', d => `url(#arr-${d.rel === 'counter' ? 'cnt' : 'cas'})`)
        .style('cursor', 'default');

      /* Edge relation labels (9px, midpoint, MiroFish style) */
      this._linkLblEl = this._linkLblG.selectAll('text')
        .data(this.edgeData).enter().append('text')
        .text(d => d.rel === 'counter' ? 'COUNTER' : '')
        .attr('font-size', '8px')
        .attr('fill', this._edgeLabelColor())
        .attr('text-anchor', 'middle')
        .attr('dominant-baseline', 'middle')
        .style('pointer-events', 'none')
        .style('font-family', "'JetBrains Mono','IBM Plex Mono',monospace");

      /* Node groups — drag (threshold 3px) + click */
      this._nodeEl = this._nodeG.selectAll('g')
        .data(this.nodeData).enter().append('g')
        .style('cursor', 'pointer')
        .call(
          d3.drag()
            .on('start', (ev, d) => { d._dsx = ev.x; d._dsy = ev.y; d._dragging = false; })
            .on('drag', (ev, d) => {
              if (!d._dragging && Math.hypot(ev.x - d._dsx, ev.y - d._dsy) > 3) {
                d._dragging = true;
                this._sim.alphaTarget(0.3).restart();
              }
              if (d._dragging) { d.fx = ev.x; d.fy = ev.y; }
            })
            .on('end', (_ev, d) => {
              if (d._dragging) this._sim.alphaTarget(0);
              d.fx = null; d.fy = null; d._dragging = false;
            })
        )
        .on('click', (ev, d) => {
          ev.stopPropagation();
          this._selectedId = d.id;
          this._highlightNode(d);
          this._showDetail(d);
        })
        .on('mouseenter', (ev, d) => {
          if (this._selectedId !== d.id) {
            d3.select(ev.currentTarget).select('circle')
              .attr('stroke', '#333333')
              .attr('stroke-width', 3);
          }
        })
        .on('mouseleave', (ev, d) => {
          if (this._selectedId !== d.id) this._styleNode(d3.select(ev.currentTarget), d, false);
        });

      /* Circle — fill color at low opacity, white stroke (MiroFish) */
      this._nodeEl.append('circle')
        .attr('r', d => d.r)
        .attr('fill', d => d.color + '22')
        .attr('stroke', d => this._nodeStroke(d, false))
        .attr('stroke-width', 2.5);

      /* Label — offset dx:14 dy:4 from node center, 11px (MiroFish) */
      this._nodeEl.append('text')
        .attr('class', 'node-lbl')
        .attr('dx', d => d.r + 5)
        .attr('dy', '4px')
        .attr('font-size', '11px')
        .attr('font-weight', '500')
        .attr('fill', this._labelColor())
        .attr('pointer-events', 'none')
        .style('font-family', "'Inter','IBM Plex Sans',system-ui,sans-serif")
        .text(d => d.label);

      /* Count sub-label (shows action count when > 0) */
      this._nodeEl.append('text')
        .attr('class', 'node-count-lbl')
        .attr('dx', d => d.r + 5)
        .attr('dy', '18px')
        .attr('font-size', '9px')
        .attr('fill', 'transparent')
        .attr('pointer-events', 'none')
        .style('font-family', "'JetBrains Mono','IBM Plex Mono',monospace")
        .text('');
    }

    /* ── Tick: update positions ── */
    _tick() {
      if (this._linkEl) {
        this._linkEl.attr('d', d => {
          if (!d.source?.x) return '';
          const sx = d.source.x, sy = d.source.y;
          const tx = d.target.x, ty = d.target.y;
          if (sx === tx && sy === ty) return '';
          /* Quadratic bezier with slight perpendicular offset (MiroFish) */
          const dist = Math.hypot(tx - sx, ty - sy) || 1;
          const ox = -(ty - sy) / dist * 24;
          const oy =  (tx - sx) / dist * 24;
          const cx = (sx + tx) / 2 + ox;
          const cy = (sy + ty) / 2 + oy;
          return `M${sx},${sy} Q${cx},${cy} ${tx},${ty}`;
        });
      }
      if (this._linkLblEl) {
        this._linkLblEl
          .attr('x', d => d.source?.x ? (d.source.x + d.target.x) / 2 : 0)
          .attr('y', d => d.source?.y ? (d.source.y + d.target.y) / 2 : 0);
      }
      if (this._nodeEl) {
        this._nodeEl.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
      }
    }

    /* ── Style helpers ── */
    _styleNode(sel, d, selected) {
      const dom = _domSentiment(d.sentiment);
      let fill = d.color + '22';
      let stroke = this._nodeStroke(d, !!selected);
      if (!selected) {
        if (dom === 'positive') { fill = '#1A8A4722'; stroke = 'rgba(26,138,71,0.8)'; }
        else if (dom === 'negative') { fill = '#C4707022'; stroke = 'rgba(196,112,112,0.8)'; }
      }
      sel.select('circle')
        .attr('r', d.r)
        .attr('fill', fill)
        .attr('stroke', stroke)
        .attr('stroke-width', selected ? 4 : 2.5);

      sel.select('.node-lbl')
        .attr('fill', selected ? d.color : this._labelColor())
        .attr('font-weight', selected ? '700' : '500');

      sel.select('.node-count-lbl')
        .text(d.count > 0 ? `${d.count} actions` : '')
        .attr('fill', d.count > 0 ? (this._isLight() ? '#888888' : 'rgba(255,255,255,0.4)') : 'transparent');
    }

    _highlightNode(d) {
      this._resetHighlight();
      /* Selected node — pink stroke */
      this._nodeEl.filter(n => n.id === d.id).call(sel => this._styleNode(sel, d, true));
      /* Edges connected → blue; others → dim */
      this._linkEl
        .attr('stroke', e => {
          const hit = e.source.id === d.id || e.target.id === d.id;
          return hit ? this._edgeActive(e) : (this._isLight() ? '#DDDDDD' : 'rgba(255,255,255,0.06)');
        })
        .attr('stroke-width', e => (e.source.id === d.id || e.target.id === d.id) ? 3 : 1)
        .attr('marker-end', e => {
          const hit = e.source.id === d.id || e.target.id === d.id;
          return `url(#arr-${e.rel === 'counter' ? 'cnt' : 'cas'}${hit ? '-a' : ''})`;
        });
    }

    _resetHighlight() {
      if (!this._nodeEl || !this._linkEl) return;
      this._nodeEl.each((d, i, nodes) => this._styleNode(this.d3.select(nodes[i]), d, false));
      this._linkEl
        .attr('stroke', d => d.active ? this._edgeActive(d) : this._edgeDefault(d))
        .attr('stroke-width', d => d.active ? Math.max(2, d.weight) : 1.5)
        .attr('marker-end', d => `url(#arr-${d.rel === 'counter' ? 'cnt' : 'cas'}${d.active ? '-a' : ''})`);
      if (this._linkLblEl) this._linkLblEl.attr('fill', this._edgeLabelColor());
    }

    /* ── Node detail panel — top-right floating (MiroFish) ── */
    _showDetail(d) {
      const el = $('graph-node-detail');
      if (!el) return;
      const sentRows = Object.entries(d.sentiment)
        .sort((a, b) => b[1] - a[1]).slice(0, 3)
        .map(([k, v]) => `<div class="gnd-sent-row gnd-sent--${k}">
          <span>${k}</span><span>${(v * 100).toFixed(0)}%</span>
        </div>`).join('');
      const topAct = d.topAction ? actionMeta(d.topAction) : null;
      el.innerHTML = `
        <div class="gnd-header">
          <div class="gnd-avatar" style="background:${d.color}22;color:${d.color};border-color:${d.color}55">${d.short}</div>
          <div class="gnd-meta">
            <div class="gnd-name">${d.label}</div>
            <div class="gnd-count">${d.count} actions recorded</div>
          </div>
          <button class="gnd-close" id="gnd-close">×</button>
        </div>
        ${sentRows ? `<div class="gnd-section"><div class="gnd-section-label">Sentiment split</div>${sentRows}</div>` : ''}
        ${topAct ? `<div class="gnd-section"><div class="gnd-section-label">Top action</div><span class="tl-action-badge ${topAct.cls}">${topAct.label}</span></div>` : ''}
        ${!sentRows && !topAct ? '<div style="font-size:10px;color:var(--text-muted);padding:8px 0">Run a simulation to see agent data.</div>' : ''}
      `;
      el.style.display = 'block';
      $('gnd-close')?.addEventListener('click', e => {
        e.stopPropagation();
        this._selectedId = null;
        this._hideDetail();
        this._resetHighlight();
      });
    }

    _hideDetail() {
      const el = $('graph-node-detail');
      if (el) el.style.display = 'none';
    }

    /* ── Public API ── */
    reset() {
      this._running = false;
      this._selectedId = null;
      this._hideDetail();
      this.nodeData.forEach(n => {
        n.count = 0; n.r = this.BASE_R; n.lastActive = 0;
        n.sentiment = {}; n.topAction = null;
      });
      this.edgeData.forEach(e => { e.active = false; e.weight = 1; });
      this._resetHighlight();
      if (this._sim) this._sim.alpha(0.4).restart();
    }

    start() { this._running = true; }
    stop()  { this._running = false; }

    destroy() {
      if (this._sim) this._sim.stop();
      if (this._resizeObs) this._resizeObs.disconnect();
    }

    /* Called on each poll result */
    update(recentActions, cascadeRound) {
      const now = Date.now();
      recentActions.forEach(a => {
        const k = archetypeKey(a.archetype);
        const n = this.nodeData.find(x => x.id === k);
        if (!n) return;
        n.count++;
        n.lastActive = now;
        /* Grow radius gently — max 22px (MiroFish-like) */
        n.r = Math.min(22, this.BASE_R + Math.sqrt(n.count) * 1.2);
        if (a.sentiment) {
          const t = n.count;
          n.sentiment[a.sentiment] = ((n.sentiment[a.sentiment] || 0) * (t - 1) + 1) / t;
        }
        if (a.action) n.topAction = a.action;
      });

      if (cascadeRound >= 2) {
        ['emotional_reactor', 'amplifier'].forEach(src => {
          this.edgeData
            .filter(e => (e.source.id || e.source) === src && e.rel === 'cascade')
            .forEach(e => { e.active = true; e.weight = Math.min(4, e.weight + 0.5); });
        });
      }
      if (cascadeRound >= 3) {
        this.edgeData
          .filter(e => (e.target.id || e.target) === 'institutional')
          .forEach(e => { e.active = true; e.weight = Math.min(4, e.weight + 0.3); });
      }

      this._applyVisualUpdates();
      if (this._sim) this._sim.alpha(0.05).restart();
    }

    finalize(result) {
      this._running = false;
      const breakdown = result.archetype_breakdown || {};
      Object.entries(breakdown).forEach(([k, v]) => {
        const n = this.nodeData.find(x => x.id === k);
        if (!n) return;
        n.sentiment = v.sentiment  || {};
        n.topAction = v.top_action || null;
      });
      this._applyVisualUpdates();
    }

    _applyVisualUpdates() {
      if (!this._nodeEl || !this._linkEl) return;
      const d3 = this.d3;
      this._nodeEl.each((d, i, nodes) => this._styleNode(d3.select(nodes[i]), d, false));
      this._linkEl
        .attr('stroke', d => d.active ? this._edgeActive(d) : this._edgeDefault(d))
        .attr('stroke-width', d => d.active ? Math.max(2, d.weight) : 1.5)
        .attr('marker-end', d => `url(#arr-${d.rel === 'counter' ? 'cnt' : 'cas'}${d.active ? '-a' : ''})`);
      if (this._linkLblEl) this._linkLblEl.attr('fill', this._edgeLabelColor());
      /* Update link distance based on activity */
      if (this._sim) {
        this._sim.force('collide', d3.forceCollide(d => d.r + 40));
      }
    }
  }

  function _domSentiment(sentiment) {
    const e = Object.entries(sentiment || {}).sort((a, b) => b[1] - a[1])[0];
    return e ? e[0] : null;
  }

  /* ── Legend (bottom bar — kept for compatibility) ── */
  function buildGraphLegend() {
    const el = $('graph-legend');
    if (!el) return;
    el.innerHTML = Object.values(ARCHETYPE_META).map(m =>
      `<div class="graph-legend-item">
        <span class="graph-legend-dot" style="background:${m.color}"></span>
        <span class="graph-legend-label">${m.short}</span>
      </div>`
    ).join('');
  }

  /* ════════════════════════════════════════════════════════════════════════
     ZONE DROPDOWN
     ════════════════════════════════════════════════════════════════════════ */
  async function loadDistricts() {
    const sel = $('field-zone');
    if (!sel) return;
    try {
      const data = await Api.getDistricts();
      const list = Array.isArray(data) ? data : (data.districts || []);
      sel.innerHTML = list.map(d => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('')
        || '<option value="downtown">Downtown Core</option>';
    } catch {
      sel.innerHTML = '<option value="downtown">Downtown Core</option>';
    }

    const p = new URLSearchParams(location.search);
    const q = p.get('district') || p.get('zone');
    if (q) {
      const o = Array.from(sel.options).find(o => o.value === q);
      if (o) sel.value = q;
    }
    const place = p.get('place');
    if (q && place && !Array.from(sel.options).find(o => o.value === q)) {
      const opt = document.createElement('option');
      opt.value = q; opt.textContent = `${place} (Custom)`;
      sel.appendChild(opt); sel.value = q;
      customTarget = { key: q, label: place };
      const picked = $('field-target-picked');
      if (picked) picked.textContent = `Custom target: ${place}`;
    }
  }

  function initTargetSearch() {
    const input   = $('field-target-search');
    const btn     = $('btn-target-search');
    const sel     = $('field-zone');
    const picked  = $('field-target-picked');
    const suggest = $('field-target-suggest');
    const PS  = global.DevCityPlaceSearch;
    const api = global.DevCityApi;
    if (!input || !btn || !sel || !suggest || !PS || !api || typeof api.geoSearch !== 'function') return;

    const choose = (geo) => {
      if (!geo) return;
      customTarget = geo;
      let opt = Array.from(sel.options).find(o => o.value === geo.key);
      if (!opt) {
        opt = document.createElement('option');
        opt.value = geo.key; opt.textContent = `${geo.label} (Custom)`;
        sel.appendChild(opt);
      }
      sel.value = geo.key;
      if (picked) picked.textContent = `Custom target: ${geo.label}`;
    };

    PS.attach({
      input, button: btn, suggest, debounceMs: 220,
      fetchRows: async (q) => {
        const res = await api.geoSearch(q, 6);
        return (res.places || []).map(p => ({
          label: p.label, lat: Number(p.lat), lng: Number(p.lon),
          key: `geo_${Number(p.lat).toFixed(4)}_${Number(p.lon).toFixed(4)}`,
        }));
      },
      onPick: (row) => {
        input.value = row.label || '';
        choose({ key: row.key, label: row.label, lat: row.lat, lng: row.lng });
      },
      onSubmitQuery: async () => {
        const query = input.value.trim();
        if (!query) return;
        const res = await api.geoSearch(query, 1);
        const p = (res.places || [])[0];
        if (!p) { if (picked) picked.textContent = 'No place found.'; return; }
        input.value = p.label;
        choose({ key: `geo_${Number(p.lat).toFixed(4)}_${Number(p.lon).toFixed(4)}`, label: p.label, lat: Number(p.lat), lng: Number(p.lon) });
      },
    });

    sel.addEventListener('change', () => {
      if (!sel.value.startsWith('geo_')) {
        customTarget = null;
        if (picked) picked.textContent = 'Tip: search any place or keep district presets.';
      }
    });
  }

  /* ════════════════════════════════════════════════════════════════════════
     FORM HELPERS
     ════════════════════════════════════════════════════════════════════════ */
  function initSectors() {
    document.querySelectorAll('.sector-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.sector-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedSector = btn.dataset.sector || 'general';
      });
    });
  }

  function initSlider() {
    const sl = $('field-agents'), lbl = $('agents-val');
    if (sl && lbl) sl.addEventListener('input', () => { lbl.textContent = Number(sl.value).toLocaleString(); });
  }

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
    if (!host || host.querySelectorAll('.factor-row').length >= 3) return;
    const row = document.createElement('div');
    row.className = 'factor-row';
    row.innerHTML = `
      <div>
        <label class="form-label">Type</label>
        <select class="factor-type" style="padding:7px 8px;background:var(--bg-surface);border:1px solid var(--bg-border);color:var(--text-primary);border-radius:4px;width:100%;font-family:var(--font-mono);font-size:10px">
          <option value="counter_rumour">Counter Rumour</option>
          <option value="authority_denial">Authority Denial</option>
          <option value="viral_controversy">Viral Controversy</option>
          <option value="confirmation_leak">Confirmation Leak</option>
        </select>
      </div>
      <div>
        <label class="form-label">Content</label>
        <input type="text" class="factor-content" placeholder="Describe the factor…"
          style="padding:7px 8px;background:var(--bg-surface);border:1px solid var(--bg-border);color:var(--text-primary);border-radius:4px;width:100%;font-family:var(--font-mono);font-size:10px"/>
      </div>
      <button type="button" class="factor-remove" title="Remove">&times;</button>`;
    row.querySelector('.factor-remove').addEventListener('click', () => row.remove());
    if (prefill) {
      row.querySelector('.factor-type').value    = prefill.type    || 'counter_rumour';
      row.querySelector('.factor-content').value = prefill.content || '';
    }
    host.appendChild(row);
  }

  function collectFactors() {
    const host = $('external-factors');
    if (!host) return [];
    return [...host.querySelectorAll('.factor-row')].map(row => ({
      type: row.querySelector('.factor-type')?.value || 'counter_rumour',
      content: row.querySelector('.factor-content')?.value?.trim() || '',
      inject_at_minute: 0,
    })).filter(f => f.content);
  }

  /* ════════════════════════════════════════════════════════════════════════
     SCENARIOS
     ════════════════════════════════════════════════════════════════════════ */
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
    document.querySelectorAll('.sector-btn').forEach(b => b.classList.toggle('active', b.dataset.sector === sc.sector));
    const host = $('external-factors');
    if (host) host.innerHTML = '';
    (sc.factors || []).forEach(f => addFactorRow(f));
    const body = document.querySelector('.collapsible-body');
    const arrow = document.querySelector('.collapsible-arrow');
    if (body && sc.factors?.length) { body.classList.add('open'); if (arrow) arrow.textContent = '▲'; }
  }

  /* ════════════════════════════════════════════════════════════════════════
     RUN STATE
     ════════════════════════════════════════════════════════════════════════ */
  let _currentSimId = null;

  function setRunning(running, label) {
    const btn = $('run-btn');
    if (!btn) return;
    btn.disabled = running;
    btn.textContent = label || (running ? 'Running…' : '→ Run Simulation');
    const prog = $('run-progress');
    if (prog) prog.style.display = running ? 'block' : 'none';
    /* Show / hide stop button */
    let stopBtn = $('stop-btn');
    if (!stopBtn && running) {
      stopBtn = document.createElement('button');
      stopBtn.id = 'stop-btn';
      stopBtn.type = 'button';
      stopBtn.className = 'btn btn--danger btn--sm';
      stopBtn.style.marginTop = '8px';
      stopBtn.style.width = '100%';
      stopBtn.textContent = '■ Stop Simulation';
      btn.parentNode.insertBefore(stopBtn, btn.nextSibling);
      stopBtn.addEventListener('click', async () => {
        if (!_currentSimId) return;
        stopBtn.disabled = true;
        stopBtn.textContent = 'Stopping…';
        try {
          await Api.stopSimulation(_currentSimId);
        } catch (_) { /* ignore — backend will eventually timeout */ }
      });
    }
    if (stopBtn) stopBtn.style.display = running ? 'block' : 'none';
  }

  function setGraphStatus(text, round) {
    const st = $('graph-status');
    if (st) st.textContent = text;
    const ci = $('graph-cascade-info'), cb = $('graph-cascade-badge');
    if (ci) ci.style.display = round ? 'flex' : 'none';
    if (cb && round) cb.textContent = `R${round}`;
  }

  /* ════════════════════════════════════════════════════════════════════════
     RESULTS RENDERING
     ════════════════════════════════════════════════════════════════════════ */
  function renderEmpty() {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `
      <div class="results-empty">
        <div class="oracle-glyph">◈</div>
        <div>Configure a scenario and<br/>run the simulation to see<br/>agent predictions here</div>
      </div>`;
    setGraphStatus('Idle · configure and run a simulation', null);
  }

  function renderSkeleton() {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `
      <div style="padding:20px">
        <p style="font-family:var(--font-mono);font-size:11px;color:var(--text-secondary);margin-bottom:16px;line-height:1.6">
          Deploying agents across the network…
        </p>
        <div class="skeleton" style="height:90px;margin-bottom:12px;border-radius:6px"></div>
        <div class="skeleton" style="height:56px;margin-bottom:10px;border-radius:6px"></div>
        <div class="skeleton" style="height:56px;border-radius:6px"></div>
      </div>`;
  }

  /* Running: compact progress + archetype chips + mini action log */
  function renderRunning(res) {
    const panel = $('results-panel');
    if (!panel) return;

    const progress  = Math.round((Number(res.progress_pct) || 0) * 100);
    const processed = Number(res.processed_agents || 0);
    const total     = Number(res.total_agents     || 0);
    const actions   = Array.isArray(res.recent_actions) ? res.recent_actions : [];
    const breakdown = res.action_breakdown || {};
    const round     = Number(res.cascade_rounds || 1);

    const stage         = res.stage || '';
    const runnerStatus  = res.runner_status || 'running';
    const stageLabel    = {
      building_agents: 'Building agents',
      round_1:         'Round 1 · individual reactions',
      round_2:         'Round 2 · cascade',
      round_3:         'Round 3 · institutional',
      delayed_factors: 'Applying external factors',
      aggregating:     'Aggregating results',
      done:            'Complete',
      error:           'Error',
      timeout:         'Timed out',
      stopped:         'Stopped',
    }[stage] || (stage || 'Deploying agents');

    /* Feed graph */
    if (agentGraph) agentGraph.update(actions, round);
    setGraphStatus(`${runnerStatus === 'cancelling' ? 'Stopping' : 'Running'} · ${stageLabel}`, round);

    /* Count actions per archetype */
    const archCounts = {};
    actions.forEach(a => { const k = archetypeKey(a.archetype); archCounts[k] = (archCounts[k]||0) + 1; });

    /* Archetype chip row */
    const archChips = Object.entries(ARCHETYPE_META).map(([k, m]) => {
      const n = archCounts[k] || 0;
      return `<div class="arch-chip${n > 0 ? ' arch-chip--active' : ''}">
        <span class="arch-chip__dot" style="background:${m.color}"></span>
        <span class="arch-chip__name">${m.short}</span>
        ${n > 0 ? `<span class="arch-chip__count">${n}</span>` : ''}
      </div>`;
    }).join('');

    /* Action breakdown chips */
    const actionChips = Object.entries(breakdown)
      .map(([k, v]) => `<span class="sim-chip">${esc(k)} <strong>${v}</strong></span>`).join('');

    /* Filtered mini log */
    const filtered = monitorPrompt
      ? actions.filter(a => `${a.archetype} ${a.action} ${a.sentiment} ${a.reasoning}`.toLowerCase().includes(monitorPrompt.toLowerCase()))
      : actions;

    const logItems = filtered.slice(-10).reverse().map(a => {
      const am  = archetypeMeta(a.archetype);
      const act = actionMeta(a.action);
      return `<div class="mini-log-item">
        <span class="mini-log-dot" style="background:${am.color}"></span>
        <span class="mini-log-arch" style="color:${am.color}">${am.short}</span>
        <span class="mini-log-action ${act.cls}">${act.label}</span>
        <span class="mini-log-sent ${sentimentClass(a.sentiment)}">${(a.sentiment||'').slice(0,3).toUpperCase()}</span>
        ${a.reasoning ? `<span class="mini-log-reason">${esc(a.reasoning.slice(0,60))}</span>` : ''}
      </div>`;
    }).join('');

    panel.innerHTML = `
      <!-- Progress row -->
      <div class="running-header">
        <div class="sim-progress-wrap">
          <span class="sim-progress-label">${processed}/${total}</span>
          <div class="sim-progress-track"><div class="sim-progress-fill" style="width:${progress}%"></div></div>
          <span class="sim-progress-pct">${progress}%</span>
        </div>
        <div class="sim-status-dot ${runnerStatus === 'cancelling' ? 'stopping' : (progress >= 100 ? 'done' : 'running')}"></div>
      </div>
      <div class="sim-stage-label">${esc(stageLabel)}</div>

      <!-- Archetype activity -->
      <div class="arch-chips-row">${archChips}</div>

      <!-- Action summary chips -->
      ${actionChips ? `<div class="action-chips-row">${actionChips}</div>` : ''}

      <!-- Mini log -->
      <div class="running-log-head">
        <span class="running-log-title">AGENT LOG</span>
        <span style="font-family:var(--font-mono);font-size:8px;color:var(--text-muted)">${filtered.length} events</span>
      </div>
      <div class="sim-mini-log" id="sim-mini-log">
        ${logItems || '<div class="tl-waiting"><div class="tl-pulse"></div><span>Agents deploying…</span></div>'}
      </div>

      <!-- Filter -->
      <div class="sim-monitor-bar">
        <input id="monitor-prompt" value="${esc(monitorPrompt)}"
          placeholder="Filter by archetype / action / sentiment…"
          class="sim-monitor-input" />
        <button id="monitor-apply" class="btn btn--ghost btn--sm">Filter</button>
      </div>`;

    const input = $('monitor-prompt'), apply = $('monitor-apply');
    if (apply && input) {
      const submit = () => { monitorPrompt = input.value.trim(); renderRunning(res); };
      apply.addEventListener('click', submit);
      input.addEventListener('keydown', e => { if (e.key === 'Enter') submit(); });
    }
  }

  /* ── Iris + Oracle forecast previews ── */
  function renderIrisState(state) {
    const panel = $('results-panel');
    if (!panel || !state) return;
    panel.insertAdjacentHTML('afterbegin', `
      <div class="result-card" style="margin-bottom:12px">
        <div class="result-card__header">
          <span class="result-card__title">Iris Live Context</span>
          <span class="result-card__confidence">Confidence ${(Number(state.confidence||0)*100).toFixed(0)}%</span>
        </div>
        <div class="result-card__body">
          <div class="score-bar"><span class="score-label">Reaction</span><div class="score-track"><div class="score-fill" style="width:${Number(state.reaction_score||0)}%;background:#B8936A"></div></div><span class="score-value">${Number(state.reaction_score||0).toFixed(1)}</span></div>
          <div class="score-bar"><span class="score-label">Sentiment</span><div class="score-track"><div class="score-fill" style="width:${Number(state.sentiment_score||0)}%;background:#5DAF78"></div></div><span class="score-value">${Number(state.sentiment_score||0).toFixed(1)}</span></div>
          <div class="score-bar"><span class="score-label">Attention</span><div class="score-track"><div class="score-fill" style="width:${Number(state.attention_score||0)}%;background:#6A9DC4"></div></div><span class="score-value">${Number(state.attention_score||0).toFixed(1)}</span></div>
        </div>
      </div>`);
  }

  function renderOracleForecast(forecast) {
    const panel = $('results-panel');
    if (!panel || !forecast) return;
    const probs = forecast.probabilities || {};
    panel.insertAdjacentHTML('afterbegin', `
      <div class="result-card" style="margin-bottom:12px">
        <div class="result-card__header">
          <span class="result-card__title">Oracle Probability Forecast</span>
          <span class="result-card__confidence">Confidence ${(Number(forecast.confidence||0)*100).toFixed(0)}%</span>
        </div>
        <div class="result-card__body">
          <div class="score-bar"><span class="score-label">Positive</span><div class="score-track"><div class="score-fill" style="width:${(Number(probs.positive||0)*100).toFixed(1)}%;background:#5DAF78"></div></div><span class="score-value">${(Number(probs.positive||0)*100).toFixed(1)}%</span></div>
          <div class="score-bar"><span class="score-label">Neutral</span><div class="score-track"><div class="score-fill" style="width:${(Number(probs.neutral||0)*100).toFixed(1)}%;background:#6A9DC4"></div></div><span class="score-value">${(Number(probs.neutral||0)*100).toFixed(1)}%</span></div>
          <div class="score-bar"><span class="score-label">Negative</span><div class="score-track"><div class="score-fill" style="width:${(Number(probs.negative||0)*100).toFixed(1)}%;background:#C47070"></div></div><span class="score-value">${(Number(probs.negative||0)*100).toFixed(1)}%</span></div>
          <div style="height:140px;margin-top:10px"><canvas id="forecast-timeline"></canvas></div>
        </div>
      </div>`);

    const timeline = Array.isArray(forecast.timeline) ? forecast.timeline : [];
    const ctx = $('forecast-timeline');
    if (!ctx || !global.Chart || !timeline.length) return;
    if (forecastChart) forecastChart.destroy();
    forecastChart = new global.Chart(ctx, {
      type: 'line',
      data: {
        labels: timeline.map(x => (x.at||'').slice(11,16)),
        datasets: [{ label: 'Risk Index', data: timeline.map(x => Number(x.risk_index||0)), borderColor: '#C47070', backgroundColor: 'rgba(196,112,112,0.1)', tension: 0.3, fill: true, pointRadius: 0 }],
      },
      options: { responsive: true, maintainAspectRatio: false, animation: false,
        scales: { x: { ticks: { color: '#444' }, grid: { color: 'rgba(39,39,39,0.8)' } }, y: { min: 0, max: 100, ticks: { color: '#444' }, grid: { color: 'rgba(39,39,39,0.8)' } } },
        plugins: { legend: { labels: { color: '#888' } } } },
    });
  }

  async function loadIrisAndForecast(zone, topic, scenarioText, nAgents) {
    try {
      const location = zone || 'downtown';
      const sector   = topic || selectedSector || 'general';
      const ctl = new AbortController();
      const t   = setTimeout(() => ctl.abort(), 12000);
      const getWith = (path) =>
        fetch(`${global.location.origin}${path}`, { headers: { Accept: 'application/json' }, signal: ctl.signal })
          .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); });
      const [iris, forecast] = await Promise.all([
        getWith(`/api/iris/state?location=${encodeURIComponent(location)}&topic=${encodeURIComponent(sector)}`),
        (async () => {
          const r = await fetch(`${global.location.origin}/api/oracle/forecast`, {
            method: 'POST', headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            body: JSON.stringify({ location, topic: sector, scenario_text: scenarioText, horizon_hours: 6, n_agents: nAgents, include_historical_analogs: true }),
            signal: ctl.signal,
          });
          if (!r.ok) throw new Error(String(r.status)); return r.json();
        })(),
      ]);
      clearTimeout(t);
      renderIrisState(iris);
      renderOracleForecast(forecast);
    } catch { /* preview optional */ }
  }

  function renderFailed(msg) {
    const panel = $('results-panel');
    if (!panel) return;
    panel.innerHTML = `<div style="padding:24px;color:var(--red);font-family:var(--font-mono);font-size:12px;line-height:1.5">
      ✗ ${esc(msg || 'Simulation failed.')}<br/>
      <span style="font-size:10px;color:var(--text-muted)">Check the server is running and retry.</span>
    </div>`;
    setGraphStatus('Simulation failed', null);
    if (agentGraph) agentGraph.stop();
  }

  /* ── Complete state ── */
  function renderComplete(res) {
    const panel = $('results-panel');
    if (!panel) return;

    const ps   = res.predicted_sentiment || {};
    const pos  = Number(ps.positive || 0);
    const neu  = Number(ps.neutral  || 0);
    const neg  = Number(ps.negative || 0);
    const vir  = Number(res.predicted_virality || 0);
    const back = Number(res.risk_of_backlash    || 0);
    const conf = res.confidence ? `${Math.round(res.confidence * 100)}%` : '—';
    const vs   = res.vs_real_time || {};
    const coalition     = res.coalition_dynamic || null;
    const rumourRisk    = res.rumour_risk != null ? Number(res.rumour_risk) : null;
    const cascadeRounds = res.cascade_rounds || 1;
    const archBreakdown = res.archetype_breakdown || {};
    const timeline      = Array.isArray(res.temporal_timeline) ? res.temporal_timeline : [];

    if (agentGraph) agentGraph.finalize(res);
    setGraphStatus(`Complete · ${cascadeRounds} cascade round${cascadeRounds !== 1 ? 's' : ''}`, null);

    function bar(label, val, good) {
      const col = val > 0.66 ? (good ? '#24A148' : '#DA1E28') : val > 0.33 ? '#F0A500' : (good ? '#DA1E28' : '#24A148');
      return `<div class="score-bar">
        <span class="score-label">${label}</span>
        <div class="score-track"><div class="score-fill" style="width:${Math.round(val*100)}%;background:${col}"></div></div>
        <span class="score-value">${val.toFixed(2)}</span>
      </div>`;
    }

    const coalitionMeta = {
      consensus:  { color: '#5DAF78', bg: 'rgba(93,175,120,0.10)',  icon: '◎', label: 'CONSENSUS',  sub: 'Fast narrative lock-in likely' },
      polarised:  { color: '#C47070', bg: 'rgba(196,112,112,0.10)', icon: '⊘', label: 'POLARISED',  sub: 'Civil unrest risk — split opinion' },
      fragmented: { color: '#C4A840', bg: 'rgba(196,168,64,0.10)',  icon: '◌', label: 'FRAGMENTED', sub: 'Unpredictable escalation pattern' },
    };
    const cm = coalition ? (coalitionMeta[coalition] || coalitionMeta.fragmented) : null;
    const coalitionBlock = cm ? `
      <div class="coalition-badge" style="background:${cm.bg};border-color:${cm.color}22">
        <span class="coalition-icon" style="color:${cm.color}">${cm.icon}</span>
        <div><div class="coalition-label" style="color:${cm.color}">${cm.label}</div><div class="coalition-sub">${cm.sub}</div></div>
      </div>` : '';

    const rumourBlock = rumourRisk != null && rumourRisk > 0 ? `
      <div class="rumour-risk-block">
        <div class="result-section-label">Rumour Propagation Risk</div>
        <div class="rumour-risk-row">
          <div class="score-track" style="flex:1"><div class="score-fill" style="width:${Math.round(rumourRisk*100)}%;background:#C4A840"></div></div>
          <span class="rumour-risk-val">${Math.round(rumourRisk*100)}%</span>
        </div>
        <div class="rumour-risk-caption">~${Math.round(rumourRisk*100)}% adoption within 2h if false narrative emerges</div>
      </div>` : '';

    const archColors = { passive_consumer:'#6A9DC4',skeptic:'#8A6AC4',emotional_reactor:'#C47070',early_adopter:'#70B8C4',amplifier:'#C4A840',contrarian:'#C4708A',institutional:'#5DAF78' };
    const archRows = Object.entries(archBreakdown).map(([k, v]) => {
      const col = archColors[k] || '#888';
      const domSent = Object.entries(v.sentiment||{}).sort((a,b)=>b[1]-a[1])[0];
      return `<div class="arch-row">
        <div class="arch-row__dot" style="background:${col}"></div>
        <div class="arch-row__name">${k.replace(/_/g,' ')}</div>
        <div class="arch-row__sent" style="color:${col}">${domSent ? domSent[0] : '—'} ${domSent ? Math.round(domSent[1]*100)+'%' : ''}</div>
        <div class="arch-row__action">${esc(v.top_action||'—')}</div>
      </div>`;
    }).join('');

    panel.innerHTML = `
      <div class="result-card">
        <div class="result-card__header">
          <span class="result-card__title">Simulation Complete ✓</span>
          <span class="result-card__confidence">Confidence ${conf} · ${cascadeRounds} round${cascadeRounds!==1?'s':''}</span>
        </div>
        <div class="result-card__body result-top-row">
          <div class="chart-box"><canvas id="sentiment-donut"></canvas></div>
          <div class="result-top-right">${coalitionBlock}${rumourBlock}</div>
        </div>
      </div>

      <div class="result-card">
        <div class="result-card__header"><span class="result-card__title">Predicted Metrics</span></div>
        <div class="result-card__body">
          ${bar('Network Virality', vir,  false)}
          ${bar('Backlash Risk',   back, false)}
          <div class="result-metric"><span class="result-metric__label">Peak Reaction</span><span class="result-metric__value">${esc(res.peak_reaction_time||'—')}</span></div>
        </div>
      </div>

      ${timeline.length ? `<div class="result-card">
        <div class="result-card__header"><span class="result-card__title">Reaction Wave</span></div>
        <div class="result-card__body"><div style="height:120px"><canvas id="temporal-timeline-chart"></canvas></div></div>
      </div>` : ''}

      ${archRows ? `<div class="result-card">
        <div class="result-card__header"><span class="result-card__title">Archetype Breakdown</span></div>
        <div class="result-card__body arch-breakdown-list">${archRows}</div>
      </div>` : ''}

      ${vs.accuracy ? `<div class="result-card">
        <div class="result-card__header"><span class="result-card__title">vs. Real-Time Baseline</span></div>
        <div class="result-card__body">
          <div class="result-metric"><span class="result-metric__label">Predicted Negative</span><span class="result-metric__value">${((vs.predicted_negative||0)*100).toFixed(1)}%</span></div>
          <div class="result-metric"><span class="result-metric__label">Actual Negative</span><span class="result-metric__value">${((vs.real_sentiment_negative||0)*100).toFixed(1)}%</span></div>
          <div class="result-metric"><span class="result-metric__label">Oracle Accuracy</span><span class="result-metric__value" style="color:var(--green)">${esc(vs.accuracy)}</span></div>
        </div>
      </div>` : ''}`;

    /* Sentiment donut */
    const ctx = $('sentiment-donut');
    if (ctx && global.Chart) {
      if (sentimentChart) sentimentChart.destroy();
      sentimentChart = new global.Chart(ctx, {
        type: 'doughnut',
        data: { labels: ['Positive','Neutral','Negative'], datasets: [{ data: [pos,neu,neg], backgroundColor: ['#5DAF78','#C4A840','#C47070'], borderWidth: 0 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: '65%',
          plugins: { legend: { position: 'bottom', labels: { color: '#888', font: { size: 10, family: "'IBM Plex Mono'" } } } } },
      });
    }

    /* Temporal wave */
    const tlCtx = $('temporal-timeline-chart');
    if (tlCtx && global.Chart && timeline.length) {
      if (forecastChart) forecastChart.destroy();
      forecastChart = new global.Chart(tlCtx, {
        type: 'line',
        data: {
          labels: timeline.map(p => p.minute < 60 ? `${p.minute}m` : `${Math.round(p.minute/60)}h`),
          datasets: [
            { label: 'Negative', data: timeline.map(p => Math.round(p.negative*100)), borderColor: '#C47070', backgroundColor: 'rgba(196,112,112,0.07)', fill: true, tension: 0.35, pointRadius: 2 },
            { label: 'Positive', data: timeline.map(p => Math.round(p.positive*100)), borderColor: '#5DAF78', backgroundColor: 'rgba(93,175,120,0.07)',  fill: true, tension: 0.35, pointRadius: 2 },
            { label: 'Neutral',  data: timeline.map(p => Math.round(p.neutral*100)),  borderColor: '#C4A840', fill: false, tension: 0.35, pointRadius: 2 },
          ],
        },
        options: { responsive: true, maintainAspectRatio: false, animation: false,
          scales: {
            x: { ticks: { color: '#444', font: { size: 9, family: "'IBM Plex Mono'" } }, grid: { color: 'rgba(39,39,39,0.6)' } },
            y: { min: 0, max: 100, ticks: { color: '#444', font: { size: 9, family: "'IBM Plex Mono'" }, callback: v => v+'%' }, grid: { color: 'rgba(39,39,39,0.6)' } },
          },
          plugins: { legend: { labels: { color: '#666', font: { size: 9, family: "'IBM Plex Mono'" } } } },
        },
      });
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     POLLING
     ════════════════════════════════════════════════════════════════════════ */
  async function pollOnce(id) {
    try {
      const res = await Api.getSimulation(id);
      pollFailures = 0;
      if (res.error)               { renderFailed('Simulation not found.'); return true; }
      if (res.status === 'complete') { renderComplete(res); loadHistory(); return true; }
      if (res.status === 'failed')   { renderFailed('Swarm run failed.'); return true; }
      renderRunning(res);
      return false;
    } catch {
      pollFailures += 1;
      if (pollFailures >= 5) {
        renderFailed('Polling failed repeatedly — check server/network.');
        return true;
      }
      setGraphStatus(`Polling retry ${pollFailures}/5…`, null);
      return false;
    }
  }

  async function pollSimulation(id) {
    if (pollTimer) clearTimeout(pollTimer);
    pollFailures = 0;

    const loop = async () => {
      const finished = await pollOnce(id);
      if (finished) {
        if (pollTimer) clearTimeout(pollTimer);
        setRunning(false);
        return;
      }
      // Backoff on transient poll failures; keep normal 2s cadence otherwise.
      const delayMs = pollFailures
        ? Math.min(10000, 1500 * Math.pow(2, pollFailures - 1))
        : 2000;
      pollTimer = setTimeout(loop, delayMs);
    };

    await loop();
  }

  /* ════════════════════════════════════════════════════════════════════════
     FORM SUBMIT
     ════════════════════════════════════════════════════════════════════════ */
  async function onSubmit(ev) {
    ev.preventDefault();
    const zone      = $('field-zone')?.value;
    const news_item = $('field-news')?.value?.trim();
    const n_agents  = parseInt($('field-agents')?.value || '1000', 10);
    if (!zone || !news_item) return;

    const body = {
      zone, news_item, sector: selectedSector,
      n_agents: Math.min(1000, Math.max(50, n_agents)),
      external_factors: collectFactors(),
    };

    if (agentGraph) { agentGraph.reset(); agentGraph.start(); }

    renderSkeleton();
    setRunning(true, 'Starting…');
    monitorPrompt = '';

    try {
      const irisLocation = customTarget?.label || zone;
      loadIrisAndForecast(irisLocation, selectedSector, news_item, body.n_agents);
      const res = await Api.postSimulate(body);
      _currentSimId = res.simulation_id;
      setRunning(true, `Running 0/${body.n_agents}…`);
      renderRunning(res);
      await pollSimulation(res.simulation_id);
    } catch (e) {
      renderFailed(e.message || 'Request failed');
      setRunning(false);
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     HISTORY
     ════════════════════════════════════════════════════════════════════════ */
  async function loadHistory() {
    const tbody = $('history-body');
    if (!tbody) return;
    try {
      const rows = await Api.getSimulationHistory(20);
      if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted);text-align:center;padding:20px">No simulations yet</td></tr>';
        return;
      }
      const cnt = $('history-count');
      if (cnt) cnt.textContent = `${rows.length} run${rows.length !== 1 ? 's' : ''}`;
      tbody.innerHTML = rows.map(r => {
        const ps  = r.predicted_sentiment || {};
        const neg = ps.negative ? `${((ps.negative)*100).toFixed(0)}%` : '—';
        return `<tr>
          <td style="font-family:var(--font-mono)">${esc((r.simulation_id||'').slice(0,8))}…</td>
          <td>${esc(r.zone||'')}</td>
          <td title="${esc(r.news_item||'')}">${esc((r.news_item||'').slice(0,34))}${(r.news_item||'').length>34?'…':''}</td>
          <td>${esc(neg)}</td>
          <td>${r.predicted_virality!=null ? Number(r.predicted_virality).toFixed(2) : '—'}</td>
          <td style="color:var(--green)">${esc(r.vs_real_time?.accuracy||'—')}</td>
        </tr>`;
      }).join('');
    } catch {
      tbody.innerHTML = '<tr><td colspan="6" style="color:var(--text-muted)">Failed to load history</td></tr>';
    }
  }

  /* ════════════════════════════════════════════════════════════════════════
     BOOT
     ════════════════════════════════════════════════════════════════════════ */
  async function boot() {
    try { await loadDistricts(); } catch (e) { console.warn('[simulator] loadDistricts', e); }

    /* Init D3 graph */
    const wrap = $('agent-graph-wrap');
    if (wrap && global.d3) {
      agentGraph = new AgentWebGraph(wrap);
      buildGraphLegend();
    }

    try {
      initTargetSearch();
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
    } catch (e) {
      console.error('[simulator] boot failed', e);
      renderFailed('Page init failed — refresh or check API is running on the same host.');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

})(typeof window !== 'undefined' ? window : globalThis);
