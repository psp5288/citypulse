/* DevCity Pulse analytics with resilient mock fallback */
(function (global) {
  const Api = global.DevCityApi;
  let trendChart = null;
  let riskChart = null;
  const $ = (id) => document.getElementById(id);

  function mockData(range) {
    const n = { "1h": 12, "6h": 24, "24h": 24, "7d": 28 }[range] || 12;
    const labels = Array.from({ length: n }, (_, i) => `${i * (range === "7d" ? 6 : range === "24h" ? 1 : 0.5)}h`);
    return {
      labels,
      crowd_series: labels.map(() => 30 + Math.random() * 40),
      risk_series: labels.map(() => 20 + Math.random() * 50),
      sentiment_series: labels.map(() => 40 + Math.random() * 45),
      risk_distribution: [2, 3, 2, 1],
      kpis: { peak_density: "67%", inference_latency: "340ms", active_events: "12", cache_hit_rate: "89%" },
    };
  }

  function chartOptions() {
    return {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { color: "#444444" }, grid: { color: "rgba(39,39,39,0.8)" } },
        y: { ticks: { color: "#444444" }, grid: { color: "rgba(39,39,39,0.8)" }, min: 0, max: 100 },
      },
      plugins: {
        legend: { labels: { color: "#888888" } },
        tooltip: { backgroundColor: "#111111", titleColor: "#EAEAEA", bodyColor: "#888888", borderColor: "#272727", borderWidth: 1 },
      },
    };
  }

  function renderKPIs(kpis) {
    if ($("kpi-density")) $("kpi-density").textContent = kpis.peak_density || "—";
    if ($("kpi-latency")) $("kpi-latency").textContent = kpis.inference_latency || "—";
    if ($("kpi-events")) $("kpi-events").textContent = kpis.active_events || "—";
    if ($("kpi-cache")) $("kpi-cache").textContent = kpis.cache_hit_rate || "—";
  }

  function renderTrend(data) {
    const canvas = $("trend-chart");
    if (!canvas || !global.Chart) return;
    if (trendChart) trendChart.destroy();
    trendChart = new global.Chart(canvas, {
      type: "line",
      data: {
        labels: data.labels || [],
        datasets: [
          { label: "Crowd", data: data.crowd_series || [], borderColor: "#6A9DC4", backgroundColor: "rgba(106,157,196,0.10)", tension: 0.35, borderWidth: 2, pointRadius: 0, fill: true },
          { label: "Risk", data: data.risk_series || [], borderColor: "#C47070", backgroundColor: "rgba(196,112,112,0.10)", tension: 0.35, borderWidth: 2, pointRadius: 0, fill: true },
          { label: "Sentiment", data: data.sentiment_series || [], borderColor: "#5DAF78", backgroundColor: "rgba(93,175,120,0.10)", tension: 0.35, borderWidth: 2, pointRadius: 0, fill: true },
        ],
      },
      options: chartOptions(),
    });
  }

  function renderRisk(data) {
    const canvas = $("risk-chart");
    if (!canvas || !global.Chart) return;
    if (riskChart) riskChart.destroy();
    riskChart = new global.Chart(canvas, {
      type: "doughnut",
      data: {
        labels: ["Critical", "High", "Moderate", "Low"],
        datasets: [
          {
            data: data.risk_distribution || [2, 3, 2, 1],
            backgroundColor: ["#C47070", "#C4A840", "#6A9DC4", "#5DAF78"],
            borderWidth: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "62%",
        plugins: { legend: { position: "bottom", labels: { color: "#888888" } } },
      },
    });
  }

  function statusBadge(risk) {
    const v = Number(risk) || 0;
    if (v > 0.6) return `<span style="color:#C47070;font-weight:600">CRITICAL</span>`;
    if (v > 0.38) return `<span style="color:#C4A840;font-weight:600">HIGH</span>`;
    if (v > 0.2) return `<span style="color:#6A9DC4">MODERATE</span>`;
    return `<span style="color:#5DAF78">LOW</span>`;
  }

  async function renderSnapshotTable() {
    const tbody = $("district-snapshot-body");
    if (!tbody) return;
    try {
      const data = await Api.getDistricts();
      const list = Array.isArray(data) ? data : data.districts || [];
      const sorted = [...list].sort((a, b) => (Number(b.risk) || 0) - (Number(a.risk) || 0));
      if (!sorted.length) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">No district data</td></tr>`;
        return;
      }
      tbody.innerHTML = sorted
        .map(
          (d) => `<tr>
            <td style="font-weight:600;color:var(--text-primary)">${d.name || d.id}</td>
            <td>${((Number(d.crowd) || 0) * 100).toFixed(0)}%</td>
            <td>${((Number(d.sentiment) || 0) * 100).toFixed(0)}%</td>
            <td>${((Number(d.risk) || 0) * 100).toFixed(0)}%</td>
            <td>${d.events != null ? d.events : "—"}</td>
            <td>${statusBadge(d.risk)}</td>
          </tr>`
        )
        .join("");
    } catch {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted)">District API unavailable</td></tr>`;
    }
  }

  async function load(range) {
    let analytics;
    try {
      analytics = await Api.getAnalytics(range);
      if (!analytics || !analytics.labels || !analytics.labels.length) analytics = mockData(range);
    } catch {
      analytics = mockData(range);
    }
    renderKPIs(analytics.kpis || {});
    renderTrend(analytics);
    renderRisk(analytics);
    await renderSnapshotTable();
  }

  function clockTick() {
    const now = new Date();
    if ($("topbar-clock")) $("topbar-clock").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if ($("topbar-date")) $("topbar-date").textContent = now.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  async function boot() {
    clockTick();
    setInterval(clockTick, 1000);
    const rangeEl = $("range-select");
    await load(rangeEl ? rangeEl.value : "1h");
    if (rangeEl) rangeEl.addEventListener("change", () => load(rangeEl.value));
    setInterval(() => load(rangeEl ? rangeEl.value : "1h"), 60000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(typeof window !== "undefined" ? window : globalThis);
