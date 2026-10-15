/**
 * live.js — Dashboard features backed by the local API (`wifi-monitor serve`)
 *
 * History, alerts, channel recommendations, device discovery, the throughput
 * test, the signal survey and plain-language explanations. In browser demo
 * mode none of this runs; the dashboard keeps its simulated behaviour.
 * Every value from the API is escaped before it is inserted into the page.
 */

'use strict';

const LiveFeatures = (() => {
  let _lastAlertId = 0;
  let _alertTimer = null;
  let _devices = [];

  const api = (path, opts) => DataSource.fetchJSON(path, opts);
  const post = (path, body, timeout = 60000) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    return fetch(path, {
      method: 'POST',
      cache: 'no-store',
      signal: ctrl.signal,
      headers: { 'X-WiFi-Monitor': '1', 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }).then(async res => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
      return data;
    }).catch(err => {
      throw err.name === 'AbortError' ? new Error('request timed out') : err;
    }).finally(() => clearTimeout(timer));
  };
  const el = id => document.getElementById(id);
  const fmt = (v, unit = '') => (v === null || v === undefined ? '—' : `${escapeHTML(v)}${unit}`);
  const SEV = { ok: 'diag-ok', info: 'diag-info', warning: 'diag-warning', critical: 'diag-critical' };

  function enabled() { return DataSource.usesApi(); }
  function isLive() { return DataSource.mode() === 'live'; }

  /* ── Setup ───────────────────────────────────────────────────── */
  async function init() {
    if (!enabled()) return;
    el('history-subtitle').textContent = 'Collected by the local server every few seconds. Kept in memory only — lost when the server stops.';
    el('history-stats-card').hidden = false;
    el('events-card').hidden = false;
    el('browser-rules').hidden = true;
    el('live-rules').hidden = false;
    if (isLive()) el('probe-label').hidden = false;
    initAsk();
    initSurvey();
    refreshAlerts(true);
    _alertTimer = setInterval(() => refreshAlerts(false), 10000);
  }

  /* ── History ─────────────────────────────────────────────────── */
  async function refreshHistory() {
    try {
      const [hist, stats, events] = await Promise.all([
        api('api/v1/history?window=3600&limit=720'),
        api('api/v1/history/stats?window=3600'),
        api('api/v1/events?window=86400'),
      ]);
      const entries = hist.samples.filter(s => s.signal_dbm != null)
        .map(s => ({ ts: s.ts * 1000, signal: s.signal_dbm }));
      ChartManager.initHistoryChart(entries);
      renderHistoryTable(hist.samples);
      renderStats(stats);
      renderEvents(events.events);
      renderRules(stats.thresholds);
    } catch (err) {
      el('history-stats').innerHTML = `<div class="empty-state">History unavailable: ${escapeHTML(err.message)}</div>`;
    }
  }

  function renderHistoryTable(samples) {
    const tbody = el('history-tbody');
    const rows = [...samples].reverse().slice(0, 100);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No samples yet — the server samples every few seconds.</td></tr>';
      return;
    }
    const label = { live: 'Live', estimated: 'Estimated', simulated: 'Simulated', unavailable: 'Unavailable' };
    tbody.innerHTML = rows.map(s => {
      const mode = s.signal_mode || s.mode;
      const sig = s.signal_dbm;
      return `<tr>
        <td class="mono small">${escapeHTML(formatDateTime(new Date(s.ts * 1000)))}</td>
        <td>${s.ssid ? escapeHTML(s.ssid) : '<span class="muted">—</span>'}</td>
        <td class="mono">${sig == null ? '—' : escapeHTML(sig)}</td>
        <td>${sig == null ? '—' : `<span class="quality-pill quality-${SignalUtils.qualityClass(sig)}">${SignalUtils.dbmToPercent(sig)}%</span>`}</td>
        <td>${fmt(s.channel)}</td>
        <td>${fmt(s.band)}</td>
        <td><span class="mode-pill mode-${escapeHTML(mode)}">${escapeHTML(label[mode] || mode)}</span></td>
      </tr>`;
    }).join('');
  }

  function renderStats(data) {
    const st = data.stats;
    const base = data.baseline || {};
    const tile = (title, m, unit) => {
      const s = st[m];
      const b = base[m];
      const change = b ? `<div class="small muted">${b.change >= 0 ? '+' : ''}${escapeHTML(b.change)}${unit} vs previous hour</div>` : '';
      return `<div class="stat-tile">
        <div class="stat-title">${escapeHTML(title)}</div>
        <div class="stat-value">${s ? `${escapeHTML(s.p50)}${unit}` : '—'}</div>
        <div class="small muted">${s ? `median · min ${escapeHTML(s.min)} · max ${escapeHTML(s.max)} · p95 ${escapeHTML(s.p95)}` : 'no data yet'}</div>
        ${change}
      </div>`;
    };
    el('history-stats').innerHTML = [
      tile('Signal', 'signal_dbm', ' dBm'),
      tile('Router latency', 'gateway_ms', ' ms'),
      tile('Internet latency', 'internet_ms', ' ms'),
      tile('DNS lookup', 'dns_ms', ' ms'),
    ].join('');
    const notes = [`${st.samples} samples`];
    if (st.connected_pct != null) notes.push(`connected ${st.connected_pct}%`);
    if (st.estimated_signal_samples) notes.push(`${st.estimated_signal_samples} estimated`);
    if (st.simulated_samples) notes.push(`${st.simulated_samples} SIMULATED`);
    if (data.collector && !data.collector.running) notes.push('collector stopped');
    if (data.collector && data.collector.last_error) notes.push(`collector error: ${data.collector.last_error}`);
    el('history-stats-note').textContent = notes.join(' · ');
  }

  function renderEvents(events) {
    const list = el('events-list');
    const recent = [...events].reverse().slice(0, 20);
    list.innerHTML = recent.length
      ? recent.map(e => `<div class="diag-finding ${e.type === 'disconnect' ? 'diag-warning' : 'diag-info'}">
          <div class="diag-title"><span class="diag-sev">${escapeHTML(e.type.replace('_', ' ').toUpperCase())}</span>
          ${escapeHTML(e.detail)}</div>
          <div class="small muted">${escapeHTML(formatDateTime(new Date(e.ts * 1000)))}</div></div>`).join('')
      : '<div class="empty-state">No roaming or disconnect events in the last 24 hours.</div>';
  }

  function renderRules(th) {
    if (!th) return;
    el('live-rules').innerHTML = `
      <div class="small">Live alerts are raised by the server from real measurements using these thresholds
      (edit <code>config.json</code> to change them):</div>
      <ul class="diag-evidence">
        <li>Weak signal: below ${escapeHTML(th.weak_signal_dbm)} dBm for 3 samples</li>
        <li>Sudden drop: ${escapeHTML(th.signal_drop_db)} dB below the recent median</li>
        <li>Latency spike: ${escapeHTML(th.latency_spike_factor)}× the recent median and ≥ ${escapeHTML(th.latency_min_ms)} ms</li>
        <li>Slow DNS: over ${escapeHTML(th.dns_slow_ms)} ms three times in a row</li>
        <li>Repeated disconnects: ${escapeHTML(th.disconnects_per_hour)} or more per hour</li>
        <li>New devices: from device scans</li>
      </ul>`;
  }

  function exportHistory(format) {
    const a = document.createElement('a');
    a.href = `api/v1/history/export?format=${format === 'json' ? 'json' : 'csv'}`;
    a.download = '';
    a.click();
  }

  async function clearHistory() {
    if (!confirm('Delete all history and alerts held by the server?')) return false;
    await post('api/v1/history/clear');
    await refreshHistory();
    return true;
  }

  /* ── Alerts ──────────────────────────────────────────────────── */
  async function refreshAlerts(initial) {
    let data;
    try { data = await api('api/v1/alerts'); } catch (_) { return; }
    const alerts = data.alerts || [];
    const active = alerts.filter(a => !a.acknowledged);
    const badge = el('alert-badge');
    badge.textContent = active.length > 9 ? '9+' : active.length;
    badge.style.display = active.length ? '' : 'none';
    if (!initial) {
      alerts.filter(a => a.id > _lastAlertId).forEach(a =>
        Toast[a.severity === 'critical' ? 'error' : a.severity === 'warning' ? 'warning' : 'info'](
          a.simulated ? `${a.title} (simulated)` : a.title, a.detail));
    }
    _lastAlertId = alerts.reduce((m, a) => Math.max(m, a.id), _lastAlertId);
    if (State.currentSection === 'alerts') renderAlerts(alerts);
  }

  function renderAlerts(alerts) {
    const list = el('alerts-list');
    const recent = [...alerts].reverse().slice(0, 50);
    if (!recent.length) {
      list.innerHTML = '<div class="empty-state">No alerts. The server raises alerts from real measurements.</div>';
      return;
    }
    list.innerHTML = recent.map(a => `
      <div class="diag-finding ${SEV[a.severity] || 'diag-info'}${a.acknowledged ? ' acked' : ''}">
        <div class="diag-title"><span class="diag-sev">${escapeHTML(a.severity.toUpperCase())}</span> ${escapeHTML(a.title)}
          ${a.simulated ? '<span class="sim-tag">Simulated</span>' : ''}
          <span class="muted small">${escapeHTML(formatTime(new Date(a.ts * 1000)))}</span></div>
        <div class="small">${escapeHTML(a.detail)}</div>
        ${a.evidence && a.evidence.length ? `<ul class="diag-evidence">${a.evidence.map(e => `<li>${escapeHTML(e)}</li>`).join('')}</ul>` : ''}
        ${a.acknowledged ? '<div class="small muted">Acknowledged</div>'
          : `<div><button type="button" class="btn btn-outline btn-sm" data-ack="${Number(a.id)}">Acknowledge</button></div>`}
      </div>`).join('');
    list.querySelectorAll('[data-ack]').forEach(btn => btn.addEventListener('click', async () => {
      await post('api/v1/alerts/ack', { id: Number(btn.dataset.ack) });
      refreshAlerts(true).then(() => api('api/v1/alerts').then(d => renderAlerts(d.alerts)));
    }));
  }

  async function showAlerts() {
    const data = await api('api/v1/alerts').catch(() => ({ alerts: [] }));
    renderAlerts(data.alerts);
  }

  async function clearAlerts() {
    await post('api/v1/alerts/clear');
    await refreshAlerts(true);
    renderAlerts([]);
  }

  /* ── Channels ────────────────────────────────────────────────── */
  async function renderChannels() {
    const out = el('channel-result');
    let data;
    try { data = await api('api/v1/channels', { timeout: 30000 }); } catch (err) {
      out.innerHTML = `<div class="empty-state">Channel analysis unavailable: ${escapeHTML(err.message)}</div>`;
      return;
    }
    if (data.mode === 'unavailable') {
      out.innerHTML = `<div class="empty-state">Channel analysis unavailable: ${escapeHTML(data.error || '')}</div>`;
      return;
    }
    const parts = Object.entries(data.bands)
      .filter(([, b]) => b.access_points || b.your_channels.length)
      .map(([band, b]) => {
        const rec = b.recommendation;
        let body;
        if (b.recommendation_withheld) body = `<div class="small">${escapeHTML(b.recommendation_withheld)}</div>`;
        else if (rec) body = `<div class="small"><strong>${rec.channel ? `Suggested channel ${escapeHTML(rec.channel)}` : 'Any channel'}:</strong> ${escapeHTML(rec.reason)} <span class="muted">(confidence: ${escapeHTML(rec.confidence)})</span></div>`;
        else body = '<div class="small muted">Not enough data.</div>';
        const yours = b.your_channels.length ? ` · yours on ${b.your_channels.map(escapeHTML).join(', ')}` : '';
        return `<div class="diag-finding diag-info"><div class="diag-title">${escapeHTML(band)}
          <span class="muted small">${escapeHTML(b.access_points)} access points${yours}</span></div>${body}</div>`;
      });
    out.innerHTML = (parts.join('') || '<div class="empty-state">No access points in the scan.</div>')
      + `<div class="small muted">${escapeHTML(data.method)}</div>`
      + `<ul class="diag-evidence">${data.assumptions.map(a => `<li>${escapeHTML(a)}</li>`).join('')}</ul>`;
  }

  /* ── Devices ─────────────────────────────────────────────────── */
  async function scanDevices() {
    const probe = el('device-probe').checked;
    if (probe && !confirm('Active probe pings every address on your local network once. Only continue on a network you own or are authorised to scan.')) {
      return null;
    }
    const result = await post('api/v1/devices/scan', { probe }, 120000);
    if (result.result.mode === 'unavailable') throw new Error(result.result.error);
    _devices = result.result.data;
    renderDevices('');
    el('device-notes').innerHTML = `<div>${escapeHTML(result.method)}${result.sweep ? ` · probed ${escapeHTML(result.sweep.probed ?? 0)} addresses` : ''}</div>`
      + `<ul class="diag-evidence">${result.limitations.map(l => `<li>${escapeHTML(l)}</li>`).join('')}</ul>`;
    renderSecurity();
    return result;
  }

  function renderDevices(filter) {
    const grid = el('devices-grid');
    const f = (filter || '').toLowerCase();
    const list = _devices.filter(d => !f || [d.ip, d.mac, d.name, d.vendor].some(v => (v || '').toLowerCase().includes(f)));
    if (!list.length) {
      grid.innerHTML = `<div class="empty-state">${_devices.length ? 'No devices match your filter' : 'No devices in the neighbour table yet.'}</div>`;
      return;
    }
    grid.innerHTML = list.map(d => `
      <div class="device-card">
        ${d.new ? '<span class="sim-tag new-tag">New</span>' : ''}
        <div class="device-name">${escapeHTML(d.name || (d.is_gateway ? 'Router / gateway' : 'Unnamed device'))}</div>
        <div class="device-ip">${escapeHTML(d.ip)}</div>
        <div class="device-mac">${escapeHTML(d.mac)}${d.randomized_mac ? ' <span class="muted small">(private)</span>' : ''}</div>
        <div class="device-vendor">${escapeHTML(d.vendor || 'Vendor unknown')}</div>
        <div class="small muted">first seen ${escapeHTML(d.first_seen ? formatDateTime(new Date(d.first_seen)) : '—')}</div>
        <button type="button" class="btn btn-outline btn-sm" data-mac="${escapeHTML(d.mac)}">Rename</button>
      </div>`).join('');
    grid.querySelectorAll('[data-mac]').forEach(btn => btn.addEventListener('click', async () => {
      const mac = btn.dataset.mac;
      const current = (_devices.find(d => d.mac === mac) || {}).name || '';
      const name = prompt(`Name for ${mac}`, current);
      if (name === null) return;
      await post('api/v1/devices/name', { mac, name: name.trim() || null });
      const d = _devices.find(x => x.mac === mac);
      if (d) d.name = name.trim() || null;
      renderDevices(el('device-filter').value);
    }));
  }

  async function renderSecurity() {
    const card = el('security-card');
    const out = el('security-result');
    try {
      const data = await api('api/v1/security');
      card.hidden = false;
      out.innerHTML = (data.findings.length
        ? data.findings.map(f => `<div class="diag-finding ${SEV[f.severity] || 'diag-info'}">
            <div class="diag-title"><span class="diag-sev">${escapeHTML(f.severity.toUpperCase())}</span> ${escapeHTML(f.title)}</div>
            <div class="small">${escapeHTML(f.evidence)}</div>
            ${f.advice ? `<div class="small"><strong>Advice:</strong> ${escapeHTML(f.advice)}</div>` : ''}</div>`).join('')
        : '<div class="empty-state">No security observations.</div>')
        + `<div class="small muted">${escapeHTML(data.note)}</div>`;
    } catch (_) { card.hidden = true; }
  }

  /* ── Speed test (server-side, real throughput) ───────────────── */
  function runSpeedTest() {
    return post('api/v1/speedtest', { max_mb: 50 }, 180000);
  }

  /* ── Survey ──────────────────────────────────────────────────── */
  function initSurvey() {
    el('survey-form').addEventListener('submit', async e => {
      e.preventDefault();
      const label = el('survey-label').value.trim();
      if (!label) { el('survey-label').focus(); return; }
      const btn = el('btn-survey');
      btn.disabled = true;
      btn.textContent = 'Recording…';
      try {
        const res = await post('api/v1/survey/points', { label, samples: 5 }, 60000);
        if (!res.ok) throw new Error(res.error || 'no signal reading');
        el('survey-label').value = '';
        Toast.success('Location recorded', `${res.point.label}: ${res.point.median_dbm} dBm`);
        loadSurvey();
      } catch (err) {
        Toast.error('Could not record', err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Record here';
      }
    });
    loadSurvey();
  }

  async function loadSurvey() {
    const out = el('survey-result');
    let rep;
    try { rep = await api('api/v1/survey'); } catch (_) { return; }
    if (!rep.points.length) { out.innerHTML = ''; return; }
    const zone = { ok: 'diag-ok', weak: 'diag-warning', dead: 'diag-critical' };
    out.innerHTML = rep.points.map(p => `
      <div class="diag-finding ${zone[p.zone] || 'diag-info'}">
        <div class="diag-title">${escapeHTML(p.label)} <span class="muted small">${escapeHTML(p.median_dbm)} dBm · ${escapeHTML(p.quality)} · ${escapeHTML(p.zone)}</span>
        ${p.mode === 'simulated' ? '<span class="sim-tag">Simulated</span>' : ''}</div>
      </div>`).join('')
      + rep.advice.map(a => `<div class="small">${escapeHTML(a)}</div>`).join('');
  }

  /* ── Ask / explain ───────────────────────────────────────────── */
  async function initAsk() {
    const form = el('ask-form');
    form.hidden = false;
    try {
      const st = await api('api/v1/ai/status');
      el('ask-note').textContent = st.enabled
        ? `Explanations use ${st.provider} (${st.model})${st.external ? ', an external service' : ''}; identifiers are ${st.identifiers_redacted ? 'redacted' : 'NOT redacted'} before sending.`
        : 'AI is off: explanations are built from the rule-based check. Enable it in config.json (see docs/AI.md).';
    } catch (_) { /* status unavailable: keep the form, the server falls back to rule-based answers */ }
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const out = el('ask-result');
      const btn = el('btn-ask');
      btn.disabled = true;
      out.innerHTML = '<div class="empty-state scanning">Preparing an explanation…</div>';
      try {
        const res = await post('api/v1/ai/ask', { question: el('ask-input').value.slice(0, 500) }, 180000);
        out.innerHTML = renderAnswer(res);
      } catch (err) {
        out.innerHTML = `<div class="empty-state">Explanation failed: ${escapeHTML(err.message)}</div>`;
      } finally {
        btn.disabled = false;
      }
    });
  }

  function renderAnswer(res) {
    const a = res.answer;
    const list = (items, f) => items.length ? `<ul class="diag-evidence">${items.map(i => `<li>${f(i)}</li>`).join('')}</ul>` : '';
    const src = res.source === 'ai' ? `AI (${escapeHTML(res.provider)} ${escapeHTML(res.model || '')})` : 'rule-based';
    return `<div class="diag-finding diag-info">
      <div class="diag-title">${escapeHTML(a.summary)}</div>
      <div class="small muted">Source: ${src}${res.reason ? ` — ${escapeHTML(res.reason)}` : ''}</div>
      ${a.observations.length ? '<div class="small"><strong>Observed</strong></div>' : ''}${list(a.observations, o => `${escapeHTML(o.fact)} — ${escapeHTML(o.evidence)}`)}
      ${a.hypotheses.length ? '<div class="small"><strong>Possible causes</strong></div>' : ''}${list(a.hypotheses, h => `${escapeHTML(h.cause)} (${escapeHTML(h.confidence)})`)}
      ${a.recommendations.length ? '<div class="small"><strong>Suggested steps</strong> (not applied automatically)</div>' : ''}${list(a.recommendations, r => `${escapeHTML(r.action)} — ${escapeHTML(r.why)}`)}
      ${a.limitations.length ? `<div class="small muted">Limitations: ${a.limitations.map(escapeHTML).join('; ')}</div>` : ''}
    </div>`;
  }

  return {
    init, enabled, isLive, refreshHistory, exportHistory, clearHistory, refreshAlerts, showAlerts, clearAlerts,
    renderChannels, scanDevices, renderDevices, runSpeedTest, renderAnswer,
    stop: () => clearInterval(_alertTimer),
  };
})();
