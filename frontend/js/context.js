/* DevCity Pulse — Shared cross-page context
 *
 * Persists the active location/district being investigated across
 * Iris → Oracle → Analytics so all three pages feel like one tool.
 *
 * Storage: localStorage key "cp-context" (expires 2h)
 * Usage:   CityPulseContext.set({...}) / .get() / .clear()
 */
(function (global) {
  'use strict';

  const KEY     = 'cp-context';
  const TTL_MS  = 7_200_000; // 2 hours

  const TIER_COLORS = {
    CRITICAL: { bg: 'rgba(196,112,112,0.16)', color: '#C47070', border: 'rgba(196,112,112,0.42)' },
    ELEVATED: { bg: 'rgba(196,168,64,0.12)',  color: '#C4A840', border: 'rgba(196,168,64,0.35)' },
    WATCH:    { bg: 'rgba(106,157,196,0.12)', color: '#6A9DC4', border: 'rgba(106,157,196,0.35)' },
    NOMINAL:  { bg: 'rgba(93,175,120,0.10)',  color: '#5DAF78', border: 'rgba(93,175,120,0.30)' },
  };

  /* ── Core state ────────────────────────────────────────────────────────── */

  function set(data) {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...data, _ts: Date.now() }));
    } catch (_) {}
  }

  function get() {
    try {
      const raw = localStorage.getItem(KEY);
      if (!raw) return null;
      const d = JSON.parse(raw);
      if (Date.now() - (d._ts || 0) > TTL_MS) { localStorage.removeItem(KEY); return null; }
      return d;
    } catch (_) { return null; }
  }

  function clear() {
    try { localStorage.removeItem(KEY); } catch (_) {}
  }

  function tierColor(tier) {
    return TIER_COLORS[tier] || TIER_COLORS.NOMINAL;
  }

  /* ── Context banner ────────────────────────────────────────────────────── */
  /**
   * Inject a slim context banner below the topbar if a context is active.
   * The banner shows: "Analysing: [Place] · [TIER] [score]%  [Iris] [Oracle] [Analytics]"
   *
   * @param {string} currentPage  — 'iris' | 'oracle' | 'analytics'
   */
  function renderBanner(currentPage) {
    const ctx = get();
    if (!ctx || !ctx.label) return;

    const tier  = ctx.risk_tier  || 'NOMINAL';
    const score = ctx.risk_score != null ? Math.round(ctx.risk_score * 100) : null;
    const tc    = tierColor(tier);

    const banner = document.createElement('div');
    banner.id = 'cp-context-banner';
    banner.style.cssText = [
      'display:flex', 'align-items:center', 'gap:12px',
      'padding:5px 20px',
      `background:${tc.bg}`,
      `border-bottom:1px solid ${tc.border}`,
      'font-family:var(--font-mono,monospace)',
      'font-size:9px',
      'color:var(--text-secondary,#888)',
      'letter-spacing:.04em',
      'flex-shrink:0',
      'z-index:90',
      'position:relative',
    ].join(';');

    const tierBadge = `<span style="font-weight:700;color:${tc.color};margin-left:2px">${tier}</span>`;
    const scoreStr  = score != null ? ` <span style="color:${tc.color}">${score}%</span>` : '';
    const driversStr = ctx.top_drivers && ctx.top_drivers.length
      ? `<span style="color:var(--text-muted,#444);margin-left:6px">· ${ctx.top_drivers.slice(0,2).join(', ')}</span>` : '';

    const navLinks = [
      currentPage !== 'iris'      ? `<a href="/dashboard" style="color:var(--text-muted,#444);text-decoration:none;padding:2px 6px;border:1px solid var(--bg-border,#272727);border-radius:3px;transition:color .15s" onmouseover="this.style.color='var(--text-primary)'" onmouseout="this.style.color='var(--text-muted,#444)'">Iris</a>` : '',
      currentPage !== 'oracle'    ? `<a href="${_oracleHref(ctx)}" style="color:var(--text-muted,#444);text-decoration:none;padding:2px 6px;border:1px solid var(--bg-border,#272727);border-radius:3px;transition:color .15s" onmouseover="this.style.color='var(--text-primary)'" onmouseout="this.style.color='var(--text-muted,#444)'">Oracle</a>` : '',
      currentPage !== 'analytics' ? `<a href="/analytics" style="color:var(--text-muted,#444);text-decoration:none;padding:2px 6px;border:1px solid var(--bg-border,#272727);border-radius:3px;transition:color .15s" onmouseover="this.style.color='var(--text-primary)'" onmouseout="this.style.color='var(--text-muted,#444)'">Analytics</a>` : '',
    ].filter(Boolean).join('');

    banner.innerHTML = `
      <span style="color:var(--text-muted,#444)">ACTIVE CONTEXT</span>
      <span style="color:var(--text-primary,#eaeaea);font-weight:600">${_esc(ctx.label)}</span>
      <span>·</span>
      <span>Risk ${tierBadge}${scoreStr}</span>
      ${driversStr}
      <span style="flex:1"></span>
      <span style="display:flex;gap:6px;align-items:center">${navLinks}</span>
      <button onclick="(function(){var C=window.CityPulseContext;if(C)C.clear();document.getElementById('cp-context-banner')?.remove();})()"
        style="background:none;border:none;cursor:pointer;color:var(--text-muted,#444);font-size:11px;padding:0 4px;line-height:1"
        title="Clear context">×</button>`;

    /* Insert after topbar */
    const topbar = document.querySelector('.dc-topbar') || document.querySelector('header');
    if (topbar && topbar.parentNode) {
      topbar.parentNode.insertBefore(banner, topbar.nextSibling);
    } else {
      const shell = document.querySelector('.dc-shell');
      if (shell) shell.prepend(banner);
    }
  }

  function _oracleHref(ctx) {
    const params = new URLSearchParams();
    if (ctx.district_id) params.set('zone', ctx.district_id);
    else if (ctx.lat && ctx.lon) params.set('zone', `geo_${Number(ctx.lat).toFixed(4)}_${Number(ctx.lon).toFixed(4)}`);
    if (ctx.label)      params.set('place', ctx.label);
    if (ctx.risk_tier)  params.set('risk_tier', ctx.risk_tier);
    if (ctx.risk_score != null) params.set('risk_score', String(ctx.risk_score));
    if (ctx.top_drivers) params.set('top_drivers', (ctx.top_drivers || []).join(','));
    return `/simulator?${params.toString()}`;
  }

  function _esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  /* ── Expose ────────────────────────────────────────────────────────────── */
  global.CityPulseContext = { set, get, clear, tierColor, renderBanner };

})(typeof window !== 'undefined' ? window : globalThis);
