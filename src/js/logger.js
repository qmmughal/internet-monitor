/**
 * logger.js — Signal history and data export for WiFi Monitor
 */

'use strict';

const Logger = (() => {
  const STORAGE_KEY = 'wifimonitor_history';
  let _history = [];
  let _alertHistory = [];
  let _alertRules = {
    weakSignal: { enabled: true, threshold: -75 },
    newDevice:  { enabled: true },
    congestion: { enabled: false },
    latency:    { enabled: false, threshold: 100 },
  };

  /* ── Persistence ─────────────────────────────────────────────── */
  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        _history = parsed.history || [];
        _alertHistory = parsed.alerts || [];
      }
    } catch (_) {
      _history = [];
    }
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        history: _history.slice(-500),  // Keep last 500 entries
        alerts: _alertHistory.slice(-100),
      }));
    } catch (_) { /* Storage may be unavailable */ }
  }

  /* ── Signal Logging ──────────────────────────────────────────── */
  function logSignal(net, signal) {
    const entry = {
      ts: Date.now(),
      ssid: net?.ssid || '—',
      signal,
      quality: SignalUtils.dbmToPercent(signal),
      channel: net?.channel || 0,
      band: net?.band || '—',
    };
    _history.push(entry);
    if (_history.length > 5000) _history.shift();
    save();
    return entry;
  }

  /* ── Alert Engine ────────────────────────────────────────────── */
  function checkAlerts(signal, network, latency) {
    const now = Date.now();

    // Weak signal
    if (_alertRules.weakSignal.enabled && signal < _alertRules.weakSignal.threshold) {
      const last = _alertHistory.findLast?.(a => a.type === 'weakSignal');
      if (!last || (now - last.ts) > 30000) {
        addAlert('weakSignal', 'warn', 'Weak Signal Detected',
          `Signal dropped to ${signal} dBm on ${network?.ssid || 'current network'}`);
      }
    }

    // High latency
    if (_alertRules.latency.enabled && latency && latency > _alertRules.latency.threshold) {
      const last = _alertHistory.findLast?.(a => a.type === 'latency');
      if (!last || (now - last.ts) > 60000) {
        addAlert('latency', 'warn', 'High Latency',
          `Latency reached ${latency}ms (threshold: ${_alertRules.latency.threshold}ms)`);
      }
    }
  }

  function handleNewDevice(device) {
    if (!_alertRules.newDevice.enabled) return;
    addAlert('newDevice', 'info', 'New Device Joined',
      `${device.name} (${device.ip}) connected to the network`);
  }

  function addAlert(type, severity, title, desc) {
    const alert = {
      id: `${type}_${Date.now()}`,
      type,
      severity,
      title,
      desc,
      ts: Date.now(),
    };
    _alertHistory.push(alert);
    save();
    renderAlerts();
    updateAlertBadge();

    // Toast notification
    const toastMap = { warn: 'warning', info: 'info', danger: 'error' };
    Toast[toastMap[severity] || 'info']?.(title, desc);

    EventBus.emit('alert', alert);
    return alert;
  }

  /* ── Alert rendering ─────────────────────────────────────────── */
  function renderAlerts() {
    const list = document.getElementById('alerts-list');
    if (!list) return;

    const recent = [..._alertHistory].reverse().slice(0, 20);
    if (!recent.length) {
      list.innerHTML = '<div class="empty-state">No alerts triggered yet</div>';
      return;
    }

    const severityIcons = {
      warn: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
      info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
      danger: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
    };

    list.innerHTML = recent.map(a => `
      <div class="alert-item">
        <div class="alert-dot-wrap ${a.severity}">${severityIcons[a.severity] || severityIcons.info}</div>
        <div class="alert-content">
          <div class="alert-title">${a.title}</div>
          <div class="alert-desc">${a.desc}</div>
        </div>
        <div class="alert-time">${formatTime(new Date(a.ts))}</div>
      </div>
    `).join('');
  }

  function updateAlertBadge() {
    const badge = document.getElementById('alert-badge');
    if (!badge) return;
    const unread = _alertHistory.length;
    badge.textContent = unread > 9 ? '9+' : unread;
    badge.style.display = unread > 0 ? '' : 'none';
  }

  function clearAlerts() {
    _alertHistory = [];
    save();
    renderAlerts();
    updateAlertBadge();
  }

  /* ── History rendering ───────────────────────────────────────── */
  function renderHistoryTable(filter = '', maxRows = 100) {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    const rows = [..._history].reverse().slice(0, maxRows);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">No history recorded yet</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(h => {
      const qual = SignalUtils.qualityClass(h.signal);
      return `
        <tr>
          <td class="mono" style="font-size:12px">${formatDateTime(new Date(h.ts))}</td>
          <td>${h.ssid}</td>
          <td class="mono">${h.signal}</td>
          <td><span class="quality-pill quality-${qual}">${h.quality}%</span></td>
          <td>${h.channel}</td>
          <td>${h.band}</td>
        </tr>
      `;
    }).join('');
  }

  /* ── Export ──────────────────────────────────────────────────── */
  function exportCSV() {
    const headers = ['Timestamp', 'SSID', 'Signal (dBm)', 'Quality %', 'Channel', 'Band'];
    const rows = _history.map(h => [
      formatDateTime(new Date(h.ts)),
      h.ssid,
      h.signal,
      h.quality,
      h.channel,
      h.band,
    ]);
    downloadFile(arrayToCSV(headers, rows), `wifi_monitor_${Date.now()}.csv`, 'text/csv');
  }

  function exportJSON() {
    downloadFile(JSON.stringify(_history, null, 2), `wifi_monitor_${Date.now()}.json`, 'application/json');
  }

  function clearHistory() {
    _history = [];
    save();
    renderHistoryTable();
    ChartManager.initHistoryChart([]);
  }

  /* ── Rule setters ────────────────────────────────────────────── */
  function setRule(key, enabled, threshold) {
    if (_alertRules[key]) {
      _alertRules[key].enabled = enabled;
      if (threshold !== undefined) _alertRules[key].threshold = threshold;
    }
  }

  return {
    load,
    logSignal,
    checkAlerts,
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
