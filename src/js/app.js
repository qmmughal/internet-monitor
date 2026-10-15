/**
 * app.js — Main application controller for WiFi Monitor
 */

'use strict';

/* ═══════════════════════════════════════════════════════════════
   State
   ═══════════════════════════════════════════════════════════════ */
const POLL_MS = 3000;
const STALE_MS = 15000;

const State = {
  currentSection: 'dashboard',
  theme: (() => { try { return localStorage.getItem('wm_theme') || 'dark'; } catch (_) { return 'dark'; } })(),
  monitorInterval: null,
  polling: false,
  snap: null,
  lastGoodTs: null,
  lastLatency: null,
};

/* ═══════════════════════════════════════════════════════════════
   Init
   ═══════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  Toast.init();
  Logger.load();
  applyTheme(State.theme);
  initNavigation();
  initControls();
  ChartManager.init();
  EventBus.on('newDevice', device => Logger.handleNewDevice(device));

  await DataSource.detect();
  applyModeUI();
  await LiveFeatures.init();
  const hash = location.hash.replace('#', '');
  if (hash) navigateTo(hash); // after detection, so sections load from the right data source
  startMonitoring();
});

/* ═══════════════════════════════════════════════════════════════
   Data-source UI (live vs simulated)
   ═══════════════════════════════════════════════════════════════ */
function applyModeUI() {
  const mode = DataSource.mode();
  const banner = document.getElementById('mode-banner');
  if (mode === 'browser-demo') {
    banner.hidden = false;
    banner.className = 'mode-banner mode-banner-demo';
    banner.innerHTML = '<strong>Demo mode — all values are SIMULATED.</strong> Browsers cannot read Wi-Fi hardware. '
      + 'For real measurements run <code>wifi-monitor serve</code> and open <code>http://127.0.0.1:8765</code>.';
  } else if (mode === 'server-demo') {
    banner.hidden = false;
    banner.className = 'mode-banner mode-banner-demo';
    banner.innerHTML = '<strong>Demo mode — the server is generating SIMULATED data</strong> '
      + '(<code>wifi-monitor serve --demo</code>). Restart without <code>--demo</code> for real measurements.';
  } else {
    banner.hidden = true;
  }

  const diagBtn = document.getElementById('btn-diagnose');
  const diagOut = document.getElementById('diagnostics-result');
  if (mode !== 'live') {
    diagBtn.disabled = true;
    diagOut.innerHTML = '<div class="empty-state">The connectivity check runs real network tests through the local API. '
      + 'Start <code>wifi-monitor serve</code> (without <code>--demo</code>) to use it.</div>';
  }

  if (mode === 'live') {
    setText('kpi-devices-value', '—');
    setText('kpi-devices-sub', 'Not scanned');
    document.getElementById('devices-grid').innerHTML = '<div class="empty-state">Click <strong>Discover</strong> to list devices '
      + 'from your computer’s neighbour table (passive, no packets sent).</div>';
  } else {
    setText('kpi-devices-sub', 'Simulated — not scanned');
  }

  setText('speed-note', DataSource.isSimulated()
    ? 'Download/upload values in demo mode are SIMULATED. Latency is measured for real by this browser.'
    : 'Measured by the local server against speed.cloudflare.com (uses up to ~50 MB of data).');
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ═══════════════════════════════════════════════════════════════
   Navigation
   ═══════════════════════════════════════════════════════════════ */
function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      navigateTo(item.dataset.section);
      if (window.innerWidth <= 860) document.getElementById('sidebar').classList.remove('open');
    });
  });
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });
}

function navigateTo(section) {
  const target = document.getElementById(`section-${section}`);
  const navItem = document.getElementById(`nav-${section}`);
  if (!target || !navItem) return;

  document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(n => { n.classList.remove('active'); n.removeAttribute('aria-current'); });
  target.classList.remove('hidden');
  navItem.classList.add('active');
  navItem.setAttribute('aria-current', 'page');

  State.currentSection = section;
  setText('page-title', navItem.textContent.trim());
  location.hash = section;

  if (section === 'history') {
    if (LiveFeatures.enabled()) {
      LiveFeatures.refreshHistory();
    } else {
      Logger.renderHistoryTable();
      ChartManager.initHistoryChart(Logger.getHistory());
    }
  }
  if (section === 'alerts') {
    if (LiveFeatures.enabled()) LiveFeatures.showAlerts();
    else Logger.renderAlerts();
  }
  if (section === 'speedtest') ChartManager.initSpeedHistoryChart(SpeedTest.getResults());
}

/* ═══════════════════════════════════════════════════════════════
   Controls
   ═══════════════════════════════════════════════════════════════ */
function initControls() {
  document.getElementById('theme-toggle').addEventListener('click', () => {
    applyTheme(State.theme === 'dark' ? 'light' : 'dark');
  });
  document.getElementById('btn-refresh').addEventListener('click', async () => {
    await tickMonitor();
    Toast.info('Refreshed', 'Dashboard data updated');
  });

  document.getElementById('btn-scan').addEventListener('click', () => runNetworkScan());
  document.getElementById('scanner-filter').addEventListener('input', e => filterNetworkTable(e.target.value));

  document.getElementById('btn-device-scan').addEventListener('click', () => runDeviceScan());
  document.getElementById('device-filter').addEventListener('input', e => {
    if (LiveFeatures.isLive()) LiveFeatures.renderDevices(e.target.value);
    else DeviceDiscovery.renderDevices(DeviceDiscovery.getDevices(), e.target.value);
  });

  document.getElementById('btn-speedtest').addEventListener('click', () => runSpeedTest());
  document.getElementById('btn-diagnose').addEventListener('click', () => runDiagnostics());

  document.getElementById('btn-export-csv').addEventListener('click', () => {
    if (LiveFeatures.enabled()) LiveFeatures.exportHistory('csv');
    else Logger.exportCSV();
    Toast.success('Exported', 'Signal history exported as CSV');
  });
  document.getElementById('btn-export-json').addEventListener('click', () => {
    if (LiveFeatures.enabled()) LiveFeatures.exportHistory('json');
    else Logger.exportJSON();
    Toast.success('Exported', 'Signal history exported as JSON');
  });
  document.getElementById('btn-clear-history').addEventListener('click', async () => {
    if (LiveFeatures.enabled()) {
      if (!(await LiveFeatures.clearHistory())) return;
    } else {
      Logger.clearHistory();
    }
    Toast.info('Cleared', 'History has been cleared');
  });
  document.getElementById('btn-clear-alerts').addEventListener('click', async () => {
    if (LiveFeatures.enabled()) await LiveFeatures.clearAlerts();
    else Logger.clearAlerts();
    Toast.info('Cleared', 'All alerts cleared');
  });

  const num = id => parseInt(document.getElementById(id).value, 10);
  const checked = id => document.getElementById(id).checked;
  const bind = (ids, fn) => ids.forEach(id => document.getElementById(id).addEventListener('change', fn));
  bind(['rule-weak-signal', 'threshold-signal'], () => Logger.setRule('weakSignal', checked('rule-weak-signal'), num('threshold-signal')));
  bind(['rule-new-device'], () => Logger.setRule('newDevice', checked('rule-new-device')));
  bind(['rule-congestion'], () => Logger.setRule('congestion', checked('rule-congestion')));
  bind(['rule-latency', 'threshold-latency'], () => Logger.setRule('latency', checked('rule-latency'), num('threshold-latency')));
}

/* ═══════════════════════════════════════════════════════════════
   Monitoring
   ═══════════════════════════════════════════════════════════════ */
function startMonitoring() {
  tickMonitor();
  State.monitorInterval = setInterval(tickMonitor, POLL_MS);
}

async function tickMonitor() {
  if (State.polling) return; // never stack requests when the API is slow
  State.polling = true;
  try {
    const snap = await NetworkScanner.poll();
    State.snap = snap;
    if (snap.signal != null) State.lastGoodTs = snap.ts;

    renderSnapshot(snap);
    if (!DataSource.usesApi()) { // with the API, the server records history and raises alerts
      Logger.logSignal(snap);
      Logger.checkAlerts(snap);
    }
    ChartManager.pushSignalPoint(formatTime(new Date(snap.ts)), snap.signal); // null leaves a visible gap
    ChartManager.drawGauge('gauge-canvas', document.getElementById('gauge-value'), snap.signal);
    NetworkScanner.renderChannelMap(snap.network?.channel ?? null, snap.network?.band ?? null);

    if (State.currentSection === 'history' && !DataSource.usesApi()) {
      Logger.renderHistoryTable();
      ChartManager.initHistoryChart(Logger.getHistory());
    }
  } finally {
    State.polling = false;
  }
}

const MODE_TEXT = { live: 'measured', estimated: 'estimated from OS %', simulated: 'SIMULATED' };

function renderSnapshot(snap) {
  const net = snap.network;

  // Status indicator
  const dot = document.getElementById('status-dot');
  let status;
  if (snap.mode === 'unavailable') {
    status = 'Wi-Fi unavailable';
    dot.className = 'status-dot warning';
  } else if (snap.simulated) {
    status = 'Demo · simulated';
    dot.className = 'status-dot warning';
  } else {
    status = 'Live monitoring';
    dot.className = 'status-dot active';
  }
  setText('status-text', status);

  // Signal KPI
  if (snap.signal != null) {
    setText('kpi-signal-value', `${snap.signal} dBm`);
    setText('kpi-signal-quality',
      `${SignalUtils.qualityLabel(snap.signal)} · ${MODE_TEXT[snap.signalMode] || snap.signalMode}`);
  } else {
    setText('kpi-signal-value', '—');
    setText('kpi-signal-quality', snap.mode === 'unavailable' ? (snap.error || 'Unavailable') : 'Not reported by OS');
  }

  // Network KPI
  if (net) {
    const name = net.ssid || (snap.simulated ? '—' : 'Name hidden by OS');
    setText('kpi-network-value', name.length > 14 ? `${name.substring(0, 14)}…` : name);
    setText('kpi-network-band', [snap.standard?.generation, net.band, net.channel != null ? `Ch ${net.channel}` : null]
      .filter(Boolean).join(' · ') || '—');
  } else {
    setText('kpi-network-value', '—');
    setText('kpi-network-band', snap.hint || snap.error || '—');
  }

  // Latency KPI (from the last browser latency test)
  const last = SpeedTest.getResults().at(-1);
  if (last && last.ping != null) {
    setText('kpi-latency-value', `${last.ping} ms`);
    setText('kpi-latency-sub', `Jitter ${last.jitter} ms · browser HTTP`);
  }

  // Connection info
  const freq = net ? (net.frequency ? `${(net.frequency / 1000).toFixed(3)} GHz` : SignalUtils.channelToFreq(net.channel, net.band)) : '—';
  setText('info-ssid', net ? (net.ssid || '—') : '—');
  setText('info-bssid', net?.bssid || '—');
  setText('info-security', net?.security || '—');
  setText('info-freq', net && net.channel != null ? freq : '—');
  setText('info-channel', net?.channel ?? '—');
  setText('info-rate', net && (net.rx || net.tx)
    ? `${net.rx ? `↓${net.rx}` : ''} ${net.tx ? `↑${net.tx}` : ''} Mbps (negotiated)`.trim() : '—');
  setText('info-ip', snap.ip || (snap.simulated ? '— (demo)' : '—'));
  setText('info-gateway', snap.gateway || (snap.simulated ? '— (demo)' : '—'));
  const stale = State.lastGoodTs && Date.now() - State.lastGoodTs > STALE_MS;
  setText('info-updated', stale
    ? `stale — last signal ${formatTime(new Date(State.lastGoodTs))}`
    : `${formatTime(new Date(snap.ts))}${snap.simulated ? ' (simulated)' : ''}`);
}

/* ═══════════════════════════════════════════════════════════════
   Scanner
   ═══════════════════════════════════════════════════════════════ */
async function runNetworkScan() {
  const btn = document.getElementById('btn-scan');
  const tbody = document.getElementById('networks-tbody');
  btn.disabled = true;
  btn.textContent = 'Scanning…';
  tbody.innerHTML = '<tr><td colspan="8" class="empty-state scanning">Reading the access point list…</td></tr>';

  try {
    const { networks, simulated, hint } = await NetworkScanner.scan();
    tbody.innerHTML = networks.length
      ? networks.map(n => NetworkScanner.renderNetworkRow(n)).join('')
      : '<tr><td colspan="8" class="empty-state">No access points reported by the operating system</td></tr>';
    ChartManager.initNetworksBarChart(networks);
    ChartManager.initBandDonutChart(networks);
    NetworkScanner.renderChannelMap(State.snap?.network?.channel ?? null, State.snap?.network?.band ?? null);
    if (LiveFeatures.enabled()) LiveFeatures.renderChannels();
    else Logger.checkCongestion(networks, State.snap?.network, simulated);
    Toast.success(simulated ? 'Scan complete (simulated)' : 'Scan complete', hint || `Found ${networks.length} access points`);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">Scan unavailable: ${escapeHTML(err.message)}`
      + `${err.hint ? `<br><span class="muted">${escapeHTML(err.hint)}</span>` : ''}</td></tr>`;
    Toast.error('Scan unavailable', err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> Scan';
  }
}

function filterNetworkTable(query) {
  const q = query.toLowerCase();
  document.querySelectorAll('#networks-tbody tr').forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

/* ═══════════════════════════════════════════════════════════════
   Devices (simulated in demo modes only)
   ═══════════════════════════════════════════════════════════════ */
async function runDeviceScan() {
  const btn = document.getElementById('btn-device-scan');
  const grid = document.getElementById('devices-grid');
  if (LiveFeatures.isLive()) {
    btn.disabled = true;
    grid.innerHTML = '<div class="empty-state scanning">Reading the neighbour table…</div>';
    try {
      const result = await LiveFeatures.scanDevices();
      if (result) {
        const n = result.result.data.length;
        setText('kpi-devices-value', n);
        setText('kpi-devices-sub', `${result.new_devices.length} new · neighbour table`);
        Toast.success('Discovery complete', `${n} devices, ${result.new_devices.length} new`);
      } else {
        LiveFeatures.renderDevices('');
      }
    } catch (err) {
      grid.innerHTML = `<div class="empty-state">Discovery unavailable: ${escapeHTML(err.message)}</div>`;
      Toast.error('Discovery unavailable', err.message);
    } finally {
      btn.disabled = false;
    }
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Discovering…';
  grid.innerHTML = '<div class="empty-state scanning">Generating simulated devices…</div>';
  try {
    const devices = await DeviceDiscovery.discover();
    DeviceDiscovery.renderDevices(devices);
    setText('kpi-devices-value', devices.length);
    setText('kpi-devices-sub', 'Simulated devices');
    Toast.success('Discovery complete (simulated)', `${devices.length} simulated devices`);
  } catch (err) {
    DeviceDiscovery.renderDevices([]);
    Toast.error('Discovery unavailable', err.message);
  } finally {
    btn.disabled = !DeviceDiscovery.isAvailable();
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg> Discover';
  }
}

/* ═══════════════════════════════════════════════════════════════
   Speed / latency test
   ═══════════════════════════════════════════════════════════════ */
async function runLiveSpeedTest() {
  const btn = document.getElementById('btn-speedtest');
  btn.disabled = true;
  btn.textContent = 'Running…';
  ['result-ping-value', 'result-download-value', 'result-upload-value', 'result-jitter-value'].forEach(id => setText(id, '—'));
  setText('speed-phase', 'Testing (about 20 s)…');
  setText('speed-value', '…');
  try {
    const r = await LiveFeatures.runSpeedTest();
    if (r.mode !== 'live') throw new Error((r.errors || []).join(', ') || 'no data');
    setText('result-ping-value', r.latency.median_ms ?? 'n/a');
    setText('result-jitter-value', r.latency.jitter_ms ?? 'n/a');
    setText('result-download-value', r.download_mbps ?? 'n/a');
    setText('result-upload-value', r.upload_mbps ?? 'n/a');
    setText('speed-value', (r.download_mbps ?? 0).toFixed(1));
    ChartManager.drawSpeedGauge('speed-gauge', r.download_mbps || 0);
    SpeedTest.getResults().push({
      ts: Date.now(), ping: r.latency.median_ms, jitter: r.latency.jitter_ms,
      download: r.download_mbps, upload: r.upload_mbps, throughputSimulated: false,
    });
    ChartManager.initSpeedHistoryChart(SpeedTest.getResults());
    setText('speed-phase', `Done · ${r.data_used_mb} MB used`);
    Toast.success('Speed test complete', `↓ ${r.download_mbps} Mbps · ↑ ${r.upload_mbps} Mbps · ${r.latency.median_ms} ms`);
  } catch (err) {
    setText('speed-phase', 'Failed');
    Toast.error('Speed test failed', err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Start Test';
  }
}

async function runSpeedTest() {
  if (LiveFeatures.isLive()) return runLiveSpeedTest();
  if (SpeedTest.isRunning()) return;
  const btn = document.getElementById('btn-speedtest');
  btn.textContent = 'Running…';
  btn.classList.add('running');
  ['result-ping-value', 'result-download-value', 'result-upload-value', 'result-jitter-value'].forEach(id => setText(id, '—'));
  setText('speed-value', '0');

  try {
    await SpeedTest.run({
      onPhase: phase => setText('speed-phase', phase),
      onProgress: mbps => {
        setText('speed-value', mbps.toFixed(1));
        setText('speed-unit', 'Mbps');
      },
      onPing: lat => {
        setText('result-ping-value', lat.ping ?? 'n/a');
        setText('result-jitter-value', lat.jitter ?? 'n/a');
        if (lat.error) Toast.warning('Latency unavailable', lat.error);
        Logger.checkAlerts(null, lat.ping);
      },
      onComplete: result => {
        const fmt = v => (v == null ? 'n/a' : `${v}${result.throughputSimulated ? '*' : ''}`);
        setText('result-download-value', fmt(result.download));
        setText('result-upload-value', fmt(result.upload));
        if (State.snap) renderSnapshot(State.snap);
        ChartManager.initSpeedHistoryChart(SpeedTest.getResults());
        const lat = result.ping != null ? `Latency ${result.ping} ms, jitter ${result.jitter} ms` : 'Latency unavailable';
        Toast.success('Test complete', result.throughputSimulated
          ? `${lat}. ↓ ${result.download} / ↑ ${result.upload} Mbps are SIMULATED.`
          : `${lat}. Throughput not measured.`);
      },
    });
  } finally {
    btn.textContent = 'Start Test';
    btn.classList.remove('running');
    setText('speed-phase', 'Complete');
  }
}

/* ═══════════════════════════════════════════════════════════════
   Connectivity check (local API)
   ═══════════════════════════════════════════════════════════════ */
const SEVERITY_CLASS = { ok: 'diag-ok', info: 'diag-info', warning: 'diag-warning', critical: 'diag-critical' };

async function runDiagnostics() {
  const btn = document.getElementById('btn-diagnose');
  const out = document.getElementById('diagnostics-result');
  btn.disabled = true;
  btn.textContent = 'Checking…';
  out.innerHTML = '<div class="empty-state scanning">Testing link, router, DNS, HTTPS and latency… (about 10 seconds)</div>';
  try {
    const report = await DataSource.fetchJSON('api/v1/diagnostics', { method: 'POST', timeout: 90000 });
    out.innerHTML = renderReport(report);
  } catch (err) {
    out.innerHTML = `<div class="empty-state">Connectivity check failed: ${escapeHTML(err.message)}</div>`;
  } finally {
    btn.disabled = DataSource.mode() !== 'live';
    btn.textContent = 'Run check';
  }
}

function renderReport(report) {
  const overall = { healthy: 'Healthy', degraded: 'Degraded', offline: 'Offline' }[report.overall] || report.overall;
  const items = report.findings.map(f => `
    <div class="diag-finding ${SEVERITY_CLASS[f.severity] || 'diag-info'}">
      <div class="diag-title">
        <span class="diag-sev">${escapeHTML(f.severity.toUpperCase())}</span> ${escapeHTML(f.title)}
        ${f.confidence ? `<span class="muted small">confidence: ${escapeHTML(f.confidence)}</span>` : ''}
      </div>
      ${f.evidence.length ? `<ul class="diag-evidence">${f.evidence.map(e => `<li>${escapeHTML(e)}</li>`).join('')}</ul>` : ''}
      ${f.likely_cause ? `<div class="small"><strong>Likely cause:</strong> ${escapeHTML(f.likely_cause)}</div>` : ''}
      ${f.next_step ? `<div class="small"><strong>Try next:</strong> ${escapeHTML(f.next_step)}</div>` : ''}
    </div>`).join('');
  return `
    <div class="diag-overall diag-overall-${escapeHTML(report.overall)}">Overall: ${escapeHTML(overall)}
      <span class="muted small">· ${escapeHTML(report.duration_ms)} ms · ${escapeHTML(formatTime(new Date(report.finished)))}</span></div>
    ${items}
    <div class="muted small">No settings were changed. Full evidence: <code>wifi-monitor diagnose --json</code></div>`;
}

/* ═══════════════════════════════════════════════════════════════
   Theme
   ═══════════════════════════════════════════════════════════════ */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  State.theme = theme;
  try { localStorage.setItem('wm_theme', theme); } catch (_) { /* storage unavailable */ }
}
