/**
 * traffic.js — Network activity for any connection type, and per-app usage
 *
 * Data comes only from the local API (`internet-monitor serve`):
 *   status.traffic          live rates per interface (OS byte counters)
 *   /api/v1/apps            bytes per app over a period
 *   /api/v1/apps/live       per-app rates right now
 *   /api/v1/connections     open connections per app
 * Nothing here is simulated; without real data the section says so.
 */

'use strict';

const TrafficView = (() => {
  let _chart = null;
  let _enabled = false;
  let _appsTimer = null;
  const MAX_POINTS = 60;
  const el = id => document.getElementById(id);

  function rate(bps) {
    if (bps === null || bps === undefined) return '—';
    const bits = bps * 8;
    if (bits >= 1e9) return `${(bits / 1e9).toFixed(1)} Gbps`;
    if (bits >= 1e6) return `${(bits / 1e6).toFixed(1)} Mbps`;
    if (bits >= 1e3) return `${(bits / 1e3).toFixed(1)} kbps`;
    return `${Math.round(bits)} bps`;
  }

  function bytes(n) {
    if (n === null || n === undefined) return '—';
    if (n >= 1e9) return `${(n / 1e9).toFixed(2)} GB`;
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(1)} kB`;
    return `${n} B`;
  }

  /* ── Setup ───────────────────────────────────────────────────── */
  function init() {
    _enabled = DataSource.mode() === 'live';
    el('apps-unavailable').hidden = _enabled;
    el('apps-content').hidden = !_enabled;
    el('activity-card').hidden = !_enabled;
    if (!_enabled) return;
    initChart();
    el('apps-window').addEventListener('change', loadApps);
    el('btn-apps-refresh').addEventListener('click', loadApps);
    el('btn-conn-refresh').addEventListener('click', loadConnections);
    refreshDashboardApps();
    _appsTimer = setInterval(refreshDashboardApps, 30000);
  }

  function initChart() {
    const ctx = el('traffic-chart');
    if (!ctx || typeof Chart === 'undefined') return;
    _chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Download', data: [], borderColor: '#34d399', backgroundColor: 'rgba(52,211,153,0.08)',
            borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0 },
          { label: 'Upload', data: [], borderColor: '#38bdf8', backgroundColor: 'rgba(56,189,248,0.06)',
            borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        scales: {
          x: { ticks: { maxTicksLimit: 6, font: { size: 10 } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { font: { size: 10 }, callback: v => rate(v) } },
        },
        plugins: {
          legend: { display: true, position: 'top', labels: { boxWidth: 10, font: { size: 11 } } },
          tooltip: { callbacks: { label: c => `${c.dataset.label}: ${rate(c.raw)}` } },
        },
      },
    });
  }

  /* ── Live snapshot (every poll) ──────────────────────────────── */
  function onSnapshot(snap) {
    if (!_enabled) return;
    const t = snap.traffic;
    if (!t || t.mode !== 'live') {
      el('activity-conn').textContent = t && t.error ? t.error : 'Traffic unavailable';
      return;
    }
    const primary = (t.interfaces || []).find(i => i.primary);
    el('activity-conn').textContent = primary
      ? `${primary.name} · ${primary.type}${primary.link_speed_mbps ? ` · ${primary.link_speed_mbps} Mbps link` : ''}`
      : 'No primary interface';
    el('activity-rx').textContent = rate(t.rx_bps);
    el('activity-tx').textContent = rate(t.tx_bps);
    if (_chart && t.rx_bps !== null) {
      const d = _chart.data;
      d.labels.push(formatTime(new Date()));
      d.datasets[0].data.push(t.rx_bps);
      d.datasets[1].data.push(t.tx_bps);
      if (d.labels.length > MAX_POINTS) {
        d.labels.shift();
        d.datasets.forEach(ds => ds.data.shift());
      }
      _chart.update('none');
    }
    if (State.currentSection === 'apps') renderInterfaces(t.interfaces || []);
  }

  function renderInterfaces(list) {
    const rows = list.filter(i => i.type !== 'loopback');
    el('iface-tbody').innerHTML = rows.length ? rows.map(i => `
      <tr>
        <td>${i.primary ? '<strong>★ ' : ''}${escapeHTML(i.name)}${i.primary ? '</strong>' : ''}</td>
        <td>${escapeHTML(i.type)}${i.is_up === false ? ' <span class="muted small">(down)</span>' : ''}</td>
        <td>${i.link_speed_mbps ? `${escapeHTML(i.link_speed_mbps)} Mbps` : '—'}</td>
        <td class="mono small">${escapeHTML((i.ipv4 || []).join(', ') || '—')}</td>
        <td class="mono">${escapeHTML(rate(i.rx_bps))}</td>
        <td class="mono">${escapeHTML(rate(i.tx_bps))}</td>
      </tr>`).join('') : '<tr><td colspan="6" class="empty-state">No interfaces reported</td></tr>';
  }

  /* ── Apps ────────────────────────────────────────────────────── */
  async function refreshDashboardApps() {
    const out = el('activity-apps');
    try {
      const res = await DataSource.fetchJSON('api/v1/apps?window=300', { timeout: 40000 });
      if (res.mode !== 'live') {
        out.innerHTML = `<div class="small muted">${escapeHTML(res.error || 'Per-app usage unavailable')}</div>`;
        return;
      }
      const top = res.apps.slice(0, 5);
      out.innerHTML = top.length ? top.map(a => `
        <div class="diag-finding diag-info"><div class="diag-title">${escapeHTML(a.app)}
          <span class="muted small">↓ ${escapeHTML(bytes(a.bytes_received))} · ↑ ${escapeHTML(bytes(a.bytes_sent))}</span></div></div>`).join('')
        : '<div class="small muted">No app used the network in the last 5 minutes (or it has not been recorded yet).</div>';
    } catch (err) {
      out.innerHTML = `<div class="small muted">Per-app usage unavailable: ${escapeHTML(err.message)}</div>`;
    }
  }

  async function loadApps() {
    const sel = el('apps-window').value;
    const tbody = el('apps-tbody');
    const note = el('apps-note');
    tbody.innerHTML = '<tr><td colspan="5" class="empty-state scanning">Reading per-app usage…</td></tr>';
    let res;
    try {
      res = await DataSource.fetchJSON(sel === 'live' ? 'api/v1/apps/live' : `api/v1/apps?window=${encodeURIComponent(sel)}`,
        { timeout: 40000 });
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">Unavailable: ${escapeHTML(err.message)}</td></tr>`;
      return;
    }
    if (res.mode !== 'live') {
      tbody.innerHTML = `<tr><td colspan="5" class="empty-state">${escapeHTML(res.error || 'Unavailable')}${res.hint ? `<br><span class="muted">${escapeHTML(res.hint)}</span>` : ''}</td></tr>`;
      note.textContent = '';
      return;
    }
    const apps = res.apps || [];
    const max = Math.max(1, ...apps.map(a => a.bytes_received + a.bytes_sent));
    const total = apps.reduce((s, a) => s + a.bytes_received + a.bytes_sent, 0) || 1;
    const live = sel === 'live';
    tbody.innerHTML = apps.length ? apps.slice(0, 30).map(a => {
      const sum = a.bytes_received + a.bytes_sent;
      const rxW = (a.bytes_received / max) * 100;
      const txW = (a.bytes_sent / max) * 100;
      const down = live && a.rx_bps != null ? `${rate(a.rx_bps)}` : bytes(a.bytes_received);
      const up = live && a.tx_bps != null ? `${rate(a.tx_bps)}` : bytes(a.bytes_sent);
      return `<tr>
        <td class="app-cell"><strong>${escapeHTML(a.app)}</strong>${a.path ? `<div class="muted small mono app-path" title="${escapeHTML(a.path)}">${escapeHTML(a.path)}</div>` : ''}</td>
        <td class="mono">${escapeHTML(down)}</td>
        <td class="mono">${escapeHTML(up)}</td>
        <td><div class="usage-bar" title="${escapeHTML(Math.round((sum / total) * 100))}% of total">
          <span class="rx" style="width:${rxW.toFixed(1)}%"></span><span class="tx" style="width:${txW.toFixed(1)}%"></span></div></td>
        <td>${a.running === true ? 'yes' : a.running === false ? '<span class="muted">no</span>' : '—'}</td>
      </tr>`;
    }).join('') : `<tr><td colspan="5" class="empty-state">${live && res.first_poll
      ? 'Measuring… refresh in about 30 seconds to see current per-app rates.'
      : 'No app used the network in this period (or it has not been recorded yet).'}</td></tr>`;
    note.textContent = `Source: ${res.source}. ${res.note || ''} Green = download, blue = upload.`;
  }

  async function loadConnections() {
    const out = el('conn-list');
    let res;
    try { res = await DataSource.fetchJSON('api/v1/connections', { timeout: 20000 }); } catch (err) {
      out.innerHTML = `<div class="empty-state">Unavailable: ${escapeHTML(err.message)}</div>`;
      return;
    }
    if (res.mode !== 'live') {
      out.innerHTML = `<div class="empty-state">${escapeHTML(res.error || 'Unavailable')}</div>`;
      return;
    }
    out.innerHTML = res.apps.length ? res.apps.slice(0, 40).map(a => {
      const exposed = a.listening.filter(l => l.all_interfaces);
      return `<details class="conn-app diag-finding diag-info">
        <summary>${escapeHTML(a.app)} <span class="muted small">${escapeHTML(a.established)} active · ${escapeHTML(a.process || '')}
          ${a.listening.length ? ` · listening on ${escapeHTML(a.listening.length)} port(s)` : ''}</span></summary>
        <ul>${a.remotes.map(r => `<li class="mono">${escapeHTML(r.ip)}:${escapeHTML(r.port)}${r.service ? ` (${escapeHTML(r.service)})` : ''}
          · ${escapeHTML(r.protocol)} ${escapeHTML(r.state || '')}${r.count > 1 ? ` ×${escapeHTML(r.count)}` : ''}</li>`).join('')}
        ${exposed.length ? `<li class="warn-text">Listening on all interfaces: ${exposed.map(l => escapeHTML(l.address)).join(', ')}</li>` : ''}</ul>
      </details>`;
    }).join('') : '<div class="empty-state">No open connections.</div>';
  }

  function show() {
    if (!_enabled) return;
    loadApps();
    loadConnections();
  }

  return { init, onSnapshot, show, rate, bytes, stop: () => clearInterval(_appsTimer) };
})();
