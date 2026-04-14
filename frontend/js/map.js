/* DevCity Pulse — Leaflet global map: click any point → intel circle */
(function (global) {
  let _map = null;
  let _onSelect = null;
  let _pickLayer = null;      // free-pick pin
  let _intelLayer = null;     // severity circle for selected location

  const CONTINENT_BOUNDS = {
    Americas: [[-60, -170], [85, -30]],
    Europe:   [[35, -30],   [75, 50]],
    Asia:     [[-10, 25],   [75, 150]],
    Africa:   [[-40, -25],  [40, 55]],
    Oceania:  [[-55, 100],  [-5, 180]],
  };

  /* ── Colour helpers ─────────────────────────────────────────────────────── */
  function scoreColor(val, positiveGood) {
    const v = Math.min(1, Math.max(0, Number(val) || 0));
    if (positiveGood) {
      if (v > 0.66) return "#5DAF78";
      if (v > 0.33) return "#C4A840";
      return "#C47070";
    }
    if (v > 0.6) return "#C47070";
    if (v > 0.38) return "#C4A840";
    return "#5DAF78";
  }

  function threatColor(d) {
    const risk = Number(d.risk || d.safety_risk) || 0;
    if (risk > 0.6) return "#DA1E28";   // red
    if (risk > 0.38) return "#F0A500";  // amber
    if (risk > 0.2) return "#6A9DC4";   // blue
    return "#24A148";                   // green
  }

  /* ── Severity → colour + label ──────────────────────────────────────────── */
  function _severityFromRisk(risk) {
    const r = Number(risk) || 0;
    if (r > 0.6)  return { color: "#DA1E28", label: "High Risk",    pulse: "pulse-red" };
    if (r > 0.38) return { color: "#F0A500", label: "Moderate Risk","pulse": "pulse-amber" };
    if (r > 0.15) return { color: "#6A9DC4", label: "Low Risk",     pulse: "pulse-blue" };
    return             { color: "#24A148", label: "Safe",           pulse: "pulse-green" };
  }

  /* ── Map init ───────────────────────────────────────────────────────────── */
  function initMap(containerId, onSelect) {
    _onSelect = onSelect;
    _map = L.map(containerId, {
      center: [20, 0],
      zoom: 2,
      zoomControl: true,
      attributionControl: false,
      worldCopyJump: true,
    });
    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 19,
      subdomains: "abcd",
    }).addTo(_map);

    _pickLayer  = L.layerGroup().addTo(_map);
    _intelLayer = L.layerGroup().addTo(_map);

    _map.on("click", (e) => {
      const lat = Number(e.latlng.lat.toFixed(6));
      const lng = Number(e.latlng.lng.toFixed(6));
      selectPoint(lat, lng, "Locating…", { skipFly: false });
      (async () => {
        const rev = await reverseGeocode(lat, lng);
        const fallback = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
        const label = rev && rev.ok && rev.label ? rev.label : fallback;
        selectPoint(lat, lng, label, { skipFly: true });
        if (_onSelect) _onSelect({
          type: "map_pick",
          lat, lng, label,
          display_name: (rev && rev.display_name) || label,
          country: rev && rev.country,
          country_code: rev && rev.country_code,
        });
      })();
    });
  }

  /* ── Navigation helpers ─────────────────────────────────────────────────── */
  function flyToContinent(name) {
    if (!_map) return;
    const bounds = CONTINENT_BOUNDS[name];
    if (bounds) _map.flyToBounds(bounds, { padding: [24, 24], duration: 1.2 });
  }

  function flyToCountry() {
    // no-op — global mode only
  }

  /* ── Free-pick pin ──────────────────────────────────────────────────────── */
  let _pickMarker = null;

  function selectPoint(lat, lng, label, options) {
    if (!_map || !_pickLayer) return null;
    const skipFly = !!(options || {}).skipFly;
    const text = label || `${lat.toFixed(3)}, ${lng.toFixed(3)}`;
    const icon = L.divIcon({
      html: `<div style="
        width:14px;height:14px;border-radius:50%;
        background:#B8936A;border:2px solid #EAEAEA;
        box-shadow:0 0 0 3px rgba(0,0,0,.5);
      "></div>`,
      className: "",
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
    if (_pickMarker) _pickLayer.removeLayer(_pickMarker);
    _pickMarker = L.marker([lat, lng], { icon, bubblingMouseEvents: false }).addTo(_pickLayer);
    _pickMarker.bindTooltip(text, { className: "dc-map-tooltip", direction: "top", offset: [0, -8] }).openTooltip();
    if (!skipFly) _map.flyTo([lat, lng], Math.max(_map.getZoom(), 7), { duration: 0.8 });
    return { type: "map_pick", lat, lng, label: text };
  }

  /* ── Intel severity circle ──────────────────────────────────────────────── */
  /*
    Called after /api/location/intel returns.
    Paints a colored ring on the map sized ~4km radius.
    Green = safe, Amber = moderate risk, Red = high risk.
  */
  function showIntelCircle(lat, lng, riskScore, locationLabel, scores) {
    if (!_map || !_intelLayer) return;
    _intelLayer.clearLayers();

    const { color, label: severityLabel } = _severityFromRisk(riskScore);
    const scores_ = scores || {};

    // Outer glow ring
    L.circle([lat, lng], {
      radius: 5200,
      color: color,
      weight: 1,
      opacity: 0.18,
      fillColor: color,
      fillOpacity: 0.04,
      className: "intel-circle-outer",
    }).addTo(_intelLayer);

    // Main circle
    const circle = L.circle([lat, lng], {
      radius: 3200,
      color: color,
      weight: 2,
      opacity: 0.85,
      fillColor: color,
      fillOpacity: 0.12,
      className: "intel-circle-main",
    }).addTo(_intelLayer);

    // Centre dot marker
    const dotSize = 20;
    const dotIcon = L.divIcon({
      html: `<div class="intel-dot" style="
        width:${dotSize}px;height:${dotSize}px;border-radius:50%;
        background:${color}22;border:2px solid ${color};
        display:flex;align-items:center;justify-content:center;
      "><div style="
        width:8px;height:8px;border-radius:50%;background:${color};
      "></div></div>`,
      className: "",
      iconSize: [dotSize, dotSize],
      iconAnchor: [dotSize / 2, dotSize / 2],
    });
    L.marker([lat, lng], { icon: dotIcon, bubblingMouseEvents: false })
      .addTo(_intelLayer);

    // Tooltip on the circle
    const crowd  = scores_.crowd_density   != null ? Math.round(scores_.crowd_density   * 100) + "%" : "—";
    const sent   = scores_.sentiment_score != null ? Math.round(scores_.sentiment_score  * 100) + "%" : "—";
    const riskPct = riskScore != null ? Math.round(Number(riskScore) * 100) + "%" : "—";
    const shortName = (locationLabel || "").split(",")[0];

    circle.bindTooltip(
      `<strong>${shortName}</strong><br/>` +
      `<span style="color:${color}">${severityLabel}</span><br/>` +
      `Risk ${riskPct} · Sent ${sent} · Crowd ${crowd}`,
      { className: "dc-map-tooltip", direction: "top", sticky: true }
    );
  }

  /* ── Stubs kept for dashboard.js compatibility ──────────────────────────── */
  function showDistrictMarkers() {}
  function hideDistrictMarkers() {}
  function updateDistricts() {}
  function highlightDistrict() {}

  /* ── Geocoding helpers ──────────────────────────────────────────────────── */
  async function reverseGeocode(lat, lng) {
    const Api = global.DevCityApi;
    if (!Api || !Api.geoReverse) return null;
    try { return await Api.geoReverse(lat, lng); } catch { return null; }
  }

  async function searchPlace(query) {
    const q = String(query || "").trim();
    if (!q) return [];
    const Api = global.DevCityApi;
    if (!Api || !Api.geoSearch) return [];
    try {
      const res = await Api.geoSearch(q, 6);
      return (res.places || []).map((p) => ({
        label: p.label || q,
        lat: Number(p.lat),
        lng: Number(p.lon),
      }));
    } catch { return []; }
  }

  async function flyToPlace(query) {
    const candidates = await searchPlace(query);
    if (!candidates.length) return null;
    const top = candidates[0];
    return selectPoint(top.lat, top.lng, top.label, { skipFly: false });
  }

  global.DevCityMap = {
    initMap,
    flyToContinent,
    flyToCountry,
    showDistrictMarkers,
    hideDistrictMarkers,
    updateDistricts,
    highlightDistrict,
    showIntelCircle,
    scoreColor,
    threatColor,
    selectPoint,
    searchPlace,
    flyToPlace,
    reverseGeocode,
  };
})(typeof window !== "undefined" ? window : globalThis);
