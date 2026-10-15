/**
 * logger.js — Signal history, alerts and export for Internet Monitor
 *
 * Every history entry and alert records whether it came from a live,
 * estimated or simulated measurement.
 */

'use strict';

const Logger = (() => {
  const STORAGE_KEY = 'internetmonitor_history_v2';
  const MAX_ENTRIES = 2000;
  const MAX_ALERTS = 200;
  let _history = [];
  let _alertHistory = [];
  const _alertRules = {
    weakSignal: { enabled: true, threshold: -75 },
    newDevice:  { enabled: true },
    congestion: { enabled: false, threshold: 5 },
    latency:    { enabled: false, threshold: 100 },
  };

  /* ── Persistence (browser localStorage, this browser only) ───── */
  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        _history = Array.isArray(parsed.history) ? parsed.history : [];
        _alertHistory = Array.isArray(parsed.alerts) ? parsed.alerts : [];
      }
      // Older keys: v1 data had no provenance; 'wifimonitor_*' predates the rename to Internet Monitor.
      ['wifimonitor_history', 'wifimonitor_history_v2'].forEach(k => localStorage.removeItem(k));
    } catch (_) {
      _history = [];
      _alertHistory = [];
    }
    updateAlertBadge();
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        history: _history.slice(-MAX_ENTRIES),
        alerts: _alertHistory.slice(-MAX_ALERTS),
      }));
    } catch (_) { /* storage may be unavailable or full */ }
  }

  /* ── Signal logging ──────────────────────────────────────────── */
  function logSignal(snap) {
    if (snap.signal == null) return null; // nothing measured → nothing logged
    const net = snap.network || {};
    const entry = {
      ts: snap.ts || Date.now(),
      ssid: net.ssid ?? null,
      signal: snap.signal,
      quality: SignalUtils.dbmToPercent(snap.signal),
      channel: net.channel ?? null,
      band: net.band ?? null,
      mode: snap.signalMode,
      source: snap.source,
    };
    _history.push(entry);
    if (_history.length > MAX_ENTRIES) _history.splice(0, _history.length - MAX_ENTRIES);
    save();
    return entry;
  }

  /* ── Alert engine ────────────────────────────────────────────── */
  function _recent(type, ms) {
    const now = Date.now();
    return _alertHistory.some(a => a.type === type && now - a.ts < ms);
  }

  function checkAlerts(snap, latency) {
    if (_alertRules.weakSignal.enabled && snap && snap.signal != null
        && snap.signal < _alertRules.weakSignal.threshold && !_recent('weakSignal', 30000)) {
      const est = snap.signalMode === 'estimated' ? ' (estimated from OS signal %)' : '';
      addAlert('weakSignal', 'warn', 'Weak Signal Detected',
        `Signal dropped to ${snap.signal} dBm${est} on ${snap.network?.ssid || 'current network'}`,
        snap.simulated);
    }
    if (_alertRules.latency.enabled && latency != null
        && latency > _alertRules.latency.threshold && !_recent('latency', 60000)) {
      addAlert('latency', 'warn', 'High Latency',
        `HTTP round-trip reached ${latency} ms (threshold: ${_alertRules.latency.threshold} ms)`, false);
    }
  }

  /** Count-based congestion check on scan results (AP count, not measured RF utilization). */
  function checkCongestion(networks, current, simulated) {
    if (!_alertRules.congestion.enabled || !current || current.channel == null) return;
    const same = networks.filter(n => !n.connected && n.channel === current.channel && n.band === current.band);
    if (same.length > _alertRules.congestion.threshold && !_recent('congestion', 300000)) {
      addAlert('congestion', 'info', 'Crowded Channel',
        `${same.length} other access points share ${current.band || ''} channel ${current.channel}. `
        + 'This is a count of networks, not a measurement of interference.', simulated);
    }
  }

  function handleNewDevice(device) {
    if (!_alertRules.newDevice.enabled) return;
    addAlert('newDevice', 'info', 'New Device Seen',
      `${device.name} (${device.ip}) appeared on the network`, !!device.simulated);
  }

  function addAlert(type, severity, title, desc, simulated = false) {
    const alert = { id: `${type}_${Date.now()}`, type, severity, title, desc, simulated, ts: Date.now() };
    _alertHistory.push(alert);
    if (_alertHistory.length > MAX_ALERTS) _alertHistory.splice(0, _alertHistory.length - MAX_ALERTS);
    save();
    renderAlerts();
    updateAlertBadge();

    const toastMap = { warn: 'warning', info: 'info', danger: 'error' };
    Toast[toastMap[severity] || 'info']?.(simulated ? `${title} (simulated)` : title, desc);
    EventBus.emit('alert', alert);
    return alert;
  }

  /* ── Alert rendering ─────────────────────────────────────────── */
  const SEVERITY_ICONS = {
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    danger: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
  };

  function renderAlerts() {
    const list = document.getElementById('alerts-list');
    if (!list) return;
    const recent = [..._alertHistory].reverse().slice(0, 50);
    if (!recent.length) {
      list.innerHTML = '<div class="empty-state">No alerts triggered yet</div>';
      return;
    }
    list.innerHTML = recent.map(a => {
      const sev = SEVERITY_ICONS[a.severity] ? a.severity : 'info';
      return `
      <div class="alert-item">
        <div class="alert-dot-wrap ${sev}">${SEVERITY_ICONS[sev]}</div>
        <div class="alert-content">
          <div class="alert-title">${escapeHTML(a.title)}${a.simulated ? ' <span class="sim-tag">Simulated</span>' : ''}</div>
          <div class="alert-desc">${escapeHTML(a.desc)}</div>
        </div>
        <div class="alert-time">${escapeHTML(formatTime(new Date(a.ts)))}</div>
      </div>`;
    }).join('');
  }

  function updateAlertBadge() {
    const badge = document.getElementById('alert-badge');
    if (!badge) return;
    const n = _alertHistory.length;
    badge.textContent = n > 9 ? '9+' : n;
    badge.style.display = n > 0 ? '' : 'none';
  }

  function clearAlerts() {
    _alertHistory = [];
    save();
    renderAlerts();
    updateAlertBadge();
  }

  /* ── History rendering ───────────────────────────────────────── */
  const MODE_LABEL = { live: 'Live', estimated: 'Estimated', simulated: 'Simulated' };

  function renderHistoryTable(maxRows = 100) {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;
    const rows = [..._history].reverse().slice(0, maxRows);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No measurements recorded yet</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(h => `
      <tr>
        <td class="mono small">${escapeHTML(formatDateTime(new Date(h.ts)))}</td>
        <td>${h.ssid ? escapeHTML(h.ssid) : '<span class="muted">—</span>'}</td>
        <td class="mono">${escapeHTML(h.signal)}</td>
        <td><span class="quality-pill quality-${SignalUtils.qualityClass(h.signal)}">${escapeHTML(h.quality)}%</span></td>
        <td>${escapeHTML(h.channel ?? '—')}</td>
        <td>${escapeHTML(h.band ?? '—')}</td>
        <td><span class="mode-pill mode-${escapeHTML(h.mode)}">${escapeHTML(MODE_LABEL[h.mode] || h.mode)}</span></td>
      </tr>`).join('');
  }

  /* ── Export ──────────────────────────────────────────────────── */
  function exportCSV() {
    const headers = ['Timestamp (UTC)', 'SSID', 'Signal (dBm)', 'Quality %', 'Channel', 'Band', 'Mode', 'Source'];
    const rows = _history.map(h => [
      new Date(h.ts).toISOString(), h.ssid ?? '', h.signal, h.quality, h.channel ?? '', h.band ?? '', h.mode, h.source ?? '',
    ]);
    downloadFile(arrayToCSV(headers, rows), `internet_monitor_${Date.now()}.csv`, 'text/csv');
  }

  function exportJSON() {
    const data = _history.map(h => ({ ...h, timestamp: new Date(h.ts).toISOString(), is_simulated: h.mode === 'simulated' }));
    downloadFile(JSON.stringify(data, null, 2), `internet_monitor_${Date.now()}.json`, 'application/json');
  }

  function clearHistory() {
    _history = [];
    save();
    renderHistoryTable();
    ChartManager.initHistoryChart([]);
  }

  function setRule(key, enabled, threshold) {
    if (_alertRules[key]) {
      _alertRules[key].enabled = enabled;
      if (threshold !== undefined && Number.isFinite(threshold)) _alertRules[key].threshold = threshold;
    }
  }

  return {
    load,
    logSignal,
    checkAlerts,
    checkCongestion,
    handleNewDevice,
    addAlert,
    renderAlerts,
    renderHistoryTable,
    clearAlerts,
    clearHistory,
    exportCSV,
    exportJSON,
    setRule,
    getHistory: () => _history,
    getAlertHistory: () => _alertHistory,
  };
})();
