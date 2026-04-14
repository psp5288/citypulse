/* DevCity Pulse — shared API helpers */
(function (global) {
  const BASE = global.location.origin;

  function signalFromTimeout(ms) {
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      return AbortSignal.timeout(ms);
    }
    const c = new AbortController();
    setTimeout(() => c.abort(), ms);
    return c.signal;
  }

  async function get(path, timeoutMs) {
    const ms = timeoutMs ?? 45000;
    const res = await fetch(BASE + path, {
      headers: { Accept: 'application/json' },
      signal: signalFromTimeout(ms),
    });
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
    return res.json();
  }

  async function post(path, body, timeoutMs) {
    const ms = timeoutMs ?? 120000;
    const res = await fetch(BASE + path, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: signalFromTimeout(ms),
    });
    if (!res.ok) {
      const t = await res.text().catch(() => '');
      throw new Error(t || `POST ${path} → ${res.status}`);
    }
    return res.json();
  }

  /* Convenience wrappers */
  const api = {
    getDistricts:         () => get('/api/districts'),
    getDistrict:          (id) => get(`/api/districts/${id}`),
    getAlerts:            (s='open') => get(`/api/alerts?status=${s}&limit=99`),
    getAnalytics:         (r='1h') => get(`/api/analytics?range=${r}`),
    postSimulate:         (body) => post('/api/simulate', body, 120000),
    getSimulation:        (id) => get(`/api/simulate/${id}`, 30000),
    getSimulationHistory: (n=20) => get(`/api/simulate/history?limit=${n}`),
    getIrisState:         (location, topic) => get(`/api/iris/state?location=${encodeURIComponent(location)}&topic=${encodeURIComponent(topic)}`),
    getIrisTrend:         (location, topic, buckets=12) => get(`/api/iris/trend?location=${encodeURIComponent(location)}&topic=${encodeURIComponent(topic)}&buckets=${buckets}`),
    postOracleForecast:   (body) => post('/api/oracle/forecast', body),
    getOracleForecast:    (id) => get(`/api/oracle/forecast/${id}`),
    /** Nominatim via backend proxy (Usage-Policy–friendly User-Agent). */
    geoSearch:            (q, limit = 6) =>
      get(`/api/geo/search?q=${encodeURIComponent(q)}&limit=${limit}`),
    geoReverse:           (lat, lon) =>
      get(`/api/geo/reverse?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`),
    getWeather:           (lat, lon) =>
      get(`/api/geo/weather?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`),
    getLocationIntel:     (lat, lon, name = '', force = false) =>
      get(`/api/location/intel?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&name=${encodeURIComponent(name)}${force ? '&force=true' : ''}`, 30000),
  };

  global.DevCityApi = { get, post, ...api };
})(typeof window !== 'undefined' ? window : globalThis);
