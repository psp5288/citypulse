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

  /**
   * GET with exponential back-off retry (MiroFish requestWithRetry pattern).
   * Retries on network errors and 5xx responses; does NOT retry 4xx.
   *
   * @param {string} path
   * @param {object} opts
   * @param {number} [opts.timeoutMs=30000]
   * @param {number} [opts.retries=3]       max additional attempts after first failure
   * @param {number} [opts.baseDelayMs=800] initial back-off delay
   */
  async function retryGet(path, { timeoutMs = 30000, retries = 3, baseDelayMs = 800 } = {}) {
    let lastErr;
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        return await get(path, timeoutMs);
      } catch (err) {
        lastErr = err;
        /* Don't retry client errors (404, 422, etc.) */
        const status = err.message.match(/→ (\d+)/)?.[1];
        if (status && Number(status) >= 400 && Number(status) < 500) throw err;
        if (attempt < retries) {
          const delay = baseDelayMs * Math.pow(2, attempt);
          await new Promise(r => setTimeout(r, delay));
        }
      }
    }
    throw lastErr;
  }

  /* Convenience wrappers */
  const api = {
    getDistricts:         () => get('/api/districts'),
    getDistrict:          (id) => get(`/api/districts/${id}`),
    getAlerts:            (s='open') => get(`/api/alerts?status=${s}&limit=99`),
    getAnalytics:         (r='1h') => get(`/api/analytics?range=${r}`),
    postSimulate:         (body) => post('/api/simulate', body, 120000),

    /** Poll a running simulation — retries up to 3× on transient failures. */
    getSimulation:        (id) => retryGet(`/api/simulate/${id}`, { timeoutMs: 30000 }),

    /** Request graceful stop of a running simulation. */
    stopSimulation:       (id) => post(`/api/simulate/${id}/stop`, {}, 10000),

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

  global.DevCityApi = { get, post, retryGet, ...api };
})(typeof window !== 'undefined' ? window : globalThis);
