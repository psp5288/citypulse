/* DevCity Pulse — Leaflet world map with continent/country drill-down */
(function (global) {
  let _map = null;
  let _onSelect = null;
  let _districtLayer = null;
  let _markers = {};
  let _markersVisible = true;

  const DISTRICT_COORDS = {
    downtown: { lat: 41.8827, lng: -87.6233 },
    midtown: { lat: 41.8950, lng: -87.61 },
    harbor: { lat: 41.87, lng: -87.615 },
    arts: { lat: 41.9, lng: -87.635 },
    financial: { lat: 41.878, lng: -87.635 },
    westside: { lat: 41.885, lng: -87.66 },
    university: { lat: 41.79, lng: -87.599 },
    market: { lat: 41.884, lng: -87.655 },
  };

  const CONTINENT_BOUNDS = {
    Americas: [[-60, -170], [85, -30]],
    Europe: [[35, -30], [75, 50]],
    Asia: [[-10, 25], [75, 150]],
    Africa: [[-40, -25], [40, 55]],
    Oceania: [[-55, 100], [-5, 180]],
  };

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
    const risk = Number(d.risk) || 0;
    if (risk > 0.6) return "#C47070";
    if (risk > 0.38) return "#C4A840";
    if (risk > 0.2) return "#6A9DC4";
    return "#5DAF78";
  }

  function markerHtml(d, isSelected) {
    const col = threatColor(d);
    const risk = Number(d.risk) || 0;
    const size = Math.round(24 + risk * 16);
    const ring = isSelected ? `box-shadow:0 0 0 2px ${col}, 0 0 0 4px rgba(0,0,0,0.45);` : "";
    return `<div style="
      width:${size}px;height:${size}px;border-radius:50%;
      background:${col}22;border:2px solid ${col};display:flex;
      align-items:center;justify-content:center;opacity:${isSelected ? "1" : "0.86"};
      transition:all .2s ease;${ring}
    "><div style="
      width:${Math.round(size * 0.44)}px;height:${Math.round(size * 0.44)}px;
      border-radius:50%;background:${col};opacity:.9;
    "></div></div>`;
  }

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
    _districtLayer = L.layerGroup().addTo(_map);
  }

  function flyToContinent(name) {
    if (!_map) return;
    const bounds = CONTINENT_BOUNDS[name];
    if (!bounds) return;
    _map.flyToBounds(bounds, { padding: [24, 24], duration: 1.2 });
  }

  function flyToCountry(name) {
    if (!_map) return;
    if (name === "United States") {
      _map.flyTo([41.85, -87.65], 11, { duration: 1.2 });
    }
  }

  function showDistrictMarkers(districts) {
    _markersVisible = true;
    updateDistricts(districts || Object.values(_markers).map((m) => m._districtData));
  }

  function hideDistrictMarkers() {
    _markersVisible = false;
    if (_districtLayer) _districtLayer.clearLayers();
  }

  function updateDistricts(districts) {
    if (!_map || !_districtLayer) return;
    const list = Array.isArray(districts) ? districts : [];
    const nextIds = new Set(list.map((d) => d.id));

    Object.keys(_markers).forEach((id) => {
      if (!nextIds.has(id)) {
        _districtLayer.removeLayer(_markers[id]);
        delete _markers[id];
      }
    });

    list.forEach((d) => {
      const coords = DISTRICT_COORDS[d.id];
      if (!coords) return;
      const icon = L.divIcon({
        html: markerHtml(d, false),
        className: "",
        iconSize: [56, 56],
        iconAnchor: [28, 28],
      });

      if (_markers[d.id]) {
        _markers[d.id].setIcon(icon);
        _markers[d.id]._districtData = d;
      } else {
        const marker = L.marker([coords.lat, coords.lng], { icon });
        marker._districtData = d;
        marker._districtId = d.id;
        marker.bindTooltip("", { className: "dc-map-tooltip", direction: "top", offset: [0, -14] });
        marker.on("mouseover", function () {
          const dd = this._districtData || {};
          this.setTooltipContent(
            `<strong>${dd.name || dd.id}</strong><br/>` +
              `Risk ${(Number(dd.risk || 0) * 100).toFixed(0)}% · ` +
              `Sent ${(Number(dd.sentiment || 0) * 100).toFixed(0)}% · ` +
              `Crowd ${(Number(dd.crowd || 0) * 100).toFixed(0)}%`
          );
        });
        marker.on("click", function () {
          if (_onSelect) _onSelect(this._districtId);
        });
        _markers[d.id] = marker;
      }

      if (_markersVisible && !_districtLayer.hasLayer(_markers[d.id])) {
        _markers[d.id].addTo(_districtLayer);
      }
    });

    if (!_markersVisible) _districtLayer.clearLayers();
  }

  function highlightDistrict(id, on) {
    const marker = _markers[id];
    if (!marker) return;
    marker.setIcon(
      L.divIcon({
        html: markerHtml(marker._districtData || {}, !!on),
        className: "",
        iconSize: [56, 56],
        iconAnchor: [28, 28],
      })
    );
    if (on && _map && DISTRICT_COORDS[id]) {
      _map.panTo([DISTRICT_COORDS[id].lat, DISTRICT_COORDS[id].lng], { animate: true, duration: 0.6 });
    }
  }

  global.DevCityMap = {
    initMap,
    flyToContinent,
    flyToCountry,
    showDistrictMarkers,
    hideDistrictMarkers,
    updateDistricts,
    highlightDistrict,
    scoreColor,
    threatColor,
    DISTRICT_COORDS,
  };
})(typeof window !== "undefined" ? window : globalThis);
