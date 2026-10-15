/**
 * charts.js — Chart.js chart management for WiFi Monitor
 */

'use strict';

/* ── Chart defaults ─────────────────────────────────────────────── */
Chart.defaults.color = 'var(--text-muted)';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";
Chart.defaults.plugins.legend.display = false;

const ChartManager = (() => {
  const charts = {};

  function getStyle(prop) {
    return getComputedStyle(document.documentElement).getPropertyValue(prop).trim();
  }

  /* ── Signal History Line Chart ──────────────────────────────── */
  function initSignalChart() {
    const ctx = document.getElementById('signal-chart');
    if (!ctx) return;

    const accent = getStyle('--accent');
    const accentGlow = getStyle('--accent-glow');

    charts.signal = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Signal (dBm)',
          data: [],
          borderColor: accent || '#38bdf8',
          backgroundColor: `rgba(56, 189, 248, 0.08)`,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { maxTicksLimit: 6, font: { size: 11 } },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            min: -100,
            max: -20,
            ticks: {
              font: { size: 11 },
              callback: v => `${v} dBm`,
            },
          },
        },
        plugins: {
          tooltip: {
            callbacks: { label: ctx => `${ctx.raw} dBm` },
          },
        },
      },
    });
  }

  /* ── Gauge (arc) canvas drawing ─────────────────────────────── */
  function drawGauge(canvasId, valueEl, dbm) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx2d = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const cx = W / 2, cy = H * 0.72;
    const R = Math.min(W, H) * 0.44;
    const startAngle = Math.PI * 0.75;
    const endAngle   = Math.PI * 2.25;

    ctx2d.clearRect(0, 0, W, H);
    const hasValue = typeof dbm === 'number' && Number.isFinite(dbm);
    const pct = hasValue ? SignalUtils.dbmToPercent(dbm) / 100 : 0;
    const arcEnd = startAngle + pct * (endAngle - startAngle);

    // Background arc
    ctx2d.beginPath();
    ctx2d.arc(cx, cy, R, startAngle, endAngle);
    ctx2d.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx2d.lineWidth = 12;
    ctx2d.lineCap = 'round';
    ctx2d.stroke();

    if (!hasValue) {  // unavailable: draw the empty track only
      if (valueEl) valueEl.textContent = '—';
      return;
    }

    // Coloured arc with gradient
    const grad = ctx2d.createLinearGradient(cx - R, cy, cx + R, cy);
    grad.addColorStop(0, '#f87171');  // poor
    grad.addColorStop(0.4, '#f59e0b'); // fair
    grad.addColorStop(0.7, '#84cc16'); // good
    grad.addColorStop(1, '#34d399');   // excellent

    ctx2d.beginPath();
    ctx2d.arc(cx, cy, R, startAngle, arcEnd);
    ctx2d.strokeStyle = grad;
    ctx2d.lineWidth = 12;
    ctx2d.lineCap = 'round';
    ctx2d.stroke();

    // Glow
    ctx2d.shadowBlur = 14;
    ctx2d.shadowColor = SignalUtils.qualityColor(dbm);
    ctx2d.beginPath();
    ctx2d.arc(cx, cy, R, arcEnd - 0.05, arcEnd);
    ctx2d.stroke();
    ctx2d.shadowBlur = 0;

    // Update text
    if (valueEl) valueEl.textContent = `${dbm}`;
  }

  /* ── Speed Gauge ─────────────────────────────────────────────── */
  function drawSpeedGauge(canvasId, value, max = 1000) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx2d = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const cx = W / 2, cy = H * 0.65;
    const R = Math.min(W, H) * 0.38;

    const startAngle = Math.PI * 0.75;
    const endAngle   = Math.PI * 2.25;
    const pct = Math.min(value / max, 1);
    const arcEnd = startAngle + pct * (endAngle - startAngle);

    ctx2d.clearRect(0, 0, W, H);

    // Track
    ctx2d.beginPath();
    ctx2d.arc(cx, cy, R, startAngle, endAngle);
    ctx2d.strokeStyle = 'rgba(255,255,255,0.07)';
    ctx2d.lineWidth = 16;
    ctx2d.lineCap = 'round';
    ctx2d.stroke();

    // Fill
    const grad = ctx2d.createLinearGradient(0, 0, W, 0);
    grad.addColorStop(0, '#818cf8');
    grad.addColorStop(1, '#38bdf8');

    ctx2d.beginPath();
    ctx2d.arc(cx, cy, R, startAngle, arcEnd);
    ctx2d.strokeStyle = grad;
    ctx2d.lineWidth = 16;
    ctx2d.lineCap = 'round';
    ctx2d.stroke();

    // Speed ticks
    for (let i = 0; i <= 10; i++) {
      const a = startAngle + (i / 10) * (endAngle - startAngle);
      const inner = R - 20, outer = R - 8;
      ctx2d.beginPath();
      ctx2d.moveTo(cx + inner * Math.cos(a), cy + inner * Math.sin(a));
      ctx2d.lineTo(cx + outer * Math.cos(a), cy + outer * Math.sin(a));
      ctx2d.strokeStyle = i % 5 === 0 ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.1)';
      ctx2d.lineWidth = i % 5 === 0 ? 2 : 1;
      ctx2d.stroke();
    }
  }

  /* ── Networks Bar Chart ─────────────────────────────────────── */
  function initNetworksBarChart(networks) {
    const ctx = document.getElementById('networks-bar-chart');
    if (!ctx) return;
    if (charts.networksBar) { charts.networksBar.destroy(); }

    const sorted = networks.filter(n => n.signal != null).sort((a, b) => b.signal - a.signal).slice(0, 10);
    const colors = sorted.map(n => `rgba(${n.signal >= -60 ? '52,211,153' : n.signal >= -75 ? '245,158,11' : '248,113,113'},0.8)`);

    charts.networksBar = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: sorted.map(n => (n.ssid || '<hidden>').substring(0, 14)),
        datasets: [{
          label: 'Signal (dBm)',
          data: sorted.map(n => n.signal),
          backgroundColor: colors,
          borderRadius: 4,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: {
            min: -100, max: -20,
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { font: { size: 11 }, callback: v => `${v} dBm` },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => `${c.raw} dBm` } },
        },
      },
    });
  }

  /* ── Band Donut Chart ───────────────────────────────────────── */
  function initBandDonutChart(networks) {
    const ctx = document.getElementById('band-donut-chart');
    if (!ctx) return;
    if (charts.band) { charts.band.destroy(); }

    const count24 = networks.filter(n => n.band === '2.4 GHz').length;
    const count5  = networks.filter(n => n.band === '5 GHz').length;
    const count6  = networks.filter(n => n.band === '6 GHz').length;

    charts.band = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: ['2.4 GHz', '5 GHz', '6 GHz'],
        datasets: [{
          data: [count24, count5, count6],
          backgroundColor: ['rgba(245,158,11,0.8)', 'rgba(56,189,248,0.8)', 'rgba(129,140,248,0.8)'],
          borderColor: 'transparent',
          borderWidth: 0,
          hoverOffset: 8,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '65%',
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: { padding: 12, font: { size: 12 } },
          },
        },
      },
    });
  }

  /* ── History Chart ──────────────────────────────────────────── */
  function initHistoryChart(history) {
    const ctx = document.getElementById('history-chart');
    if (!ctx) return;
    if (charts.history) { charts.history.destroy(); }

    charts.history = new Chart(ctx, {
      type: 'line',
      data: {
        labels: history.map(h => formatTime(new Date(h.ts))),
        datasets: [{
          label: 'Signal (dBm)',
          data: history.map(h => h.signal),
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56,189,248,0.06)',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { maxTicksLimit: 8, font: { size: 11 } },
          },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            min: -100, max: -20,
            ticks: { font: { size: 11 }, callback: v => `${v} dBm` },
          },
        },
      },
    });
  }

  /* ── Speed History Chart ────────────────────────────────────── */
  function initSpeedHistoryChart(results) {
    const ctx = document.getElementById('speed-history-chart');
    if (!ctx) return;
    if (charts.speedHistory) { charts.speedHistory.destroy(); }
    if (!results.length) return;

    charts.speedHistory = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: results.map((_, i) => `Test ${i + 1}`),
        datasets: [
          {
            label: results.some(r => r.throughputSimulated) ? 'Download (simulated)' : 'Download',
            data: results.map(r => r.download),
            backgroundColor: 'rgba(52,211,153,0.7)',
            borderRadius: 4,
          },
          {
            label: results.some(r => r.throughputSimulated) ? 'Upload (simulated)' : 'Upload',
            data: results.map(r => r.upload),
            backgroundColor: 'rgba(56,189,248,0.7)',
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            position: 'top',
            labels: { font: { size: 12 }, padding: 12 },
          },
        },
        scales: {
          x: { grid: { display: false }, stacked: false },
          y: {
            grid: { color: 'rgba(255,255,255,0.04)' },
            ticks: { font: { size: 11 }, callback: v => `${v} Mbps` },
          },
        },
      },
    });
  }

  /* ── Update signal chart with new data point ────────────────── */
  function pushSignalPoint(label, value, maxPoints = 60) {
    if (!charts.signal) return;
    const ds = charts.signal.data;
    ds.labels.push(label);
    ds.datasets[0].data.push(value);
    if (ds.labels.length > maxPoints) {
      ds.labels.shift();
      ds.datasets[0].data.shift();
    }
    charts.signal.update('none');
  }

  return {
    init: initSignalChart,
    drawGauge,
    drawSpeedGauge,
    pushSignalPoint,
    initNetworksBarChart,
    initBandDonutChart,
    initHistoryChart,
    initSpeedHistoryChart,
  };
})();
