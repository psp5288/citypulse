/* DevCity Pulse — shared API helpers */
(function (global) {
  const BASE = global.location.origin;

  async function get(path) {
    const res = await fetch(BASE + path, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
    return res.json();
  }

  async function post(path, body) {
    const res = await fetch(BASE + path, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
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
    postSimulate:         (body) => post('/api/simulate', body),
    getSimulation:        (id) => get(`/api/simulate/${id}`),
    getSimulationHistory: (n=20) => get(`/api/simulate/history?limit=${n}`),
  };

  global.DevCityApi = { get, post, ...api };
})(typeof window !== 'undefined' ? window : globalThis);
