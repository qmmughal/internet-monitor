/**
 * app.js — Main application controller for WiFi Monitor
 */

'use strict';

/* ═══════════════════════════════════════════════════════════════
   State
   ═══════════════════════════════════════════════════════════════ */
const State = {
  currentSection: 'dashboard',
  theme: localStorage.getItem('wm_theme') || 'dark',
  monitorInterval: null,
  scanInterval: null,
  currentNetwork: null,
  networks: [],
};

/* ═══════════════════════════════════════════════════════════════
   Init
   ═══════════════════════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  // Core inits
  Toast.init();
  Logger.load();
  applyTheme(State.theme);

  // Wire up navigation
  initNavigation();

  // Wire up controls
  initControls();

  // Start monitoring
  startMonitoring();

  // EventBus listeners
  EventBus.on('newDevice', device => Logger.handleNewDevice(device));

  Toast.success('WiFi Monitor Ready', 'Real-time monitoring is active');
});

/* ═══════════════════════════════════════════════════════════════
   Navigation
   ═══════════════════════════════════════════════════════════════ */
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');

  navItems.forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const section = item.dataset.section;
      navigateTo(section);

      // Close sidebar on mobile
      if (window.innerWidth <= 860) {
        document.getElementById('sidebar').classList.remove('open');
      }
    });
  });

  // Sidebar toggle (mobile)
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('sidebar').classList.toggle('open');
  });

  // Hash routing
  const hash = location.hash.replace('#', '');
  if (hash) navigateTo(hash);
}

function navigateTo(section) {
  // Hide all sections
  document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  // Show target section
  const target = document.getElementById(`section-${section}`);
  const navItem = document.getElementById(`nav-${section}`);
  if (!target || !navItem) return;

  target.classList.remove('hidden');
  navItem.classList.add('active');

  State.currentSection = section;
  document.getElementById('page-title').textContent = navItem.textContent.trim();
  location.hash = section;

  // Section-specific init
  if (section === 'history') {
    Logger.renderHistoryTable();
    ChartManager.initHistoryChart(Logger.getHistory());
  }
  if (section === 'alerts') {
    Logger.renderAlerts();
  }
  if (section === 'speedtest') {
    ChartManager.initSpeedHistoryChart(SpeedTest.getResults());
  }
}

/* ═══════════════════════════════════════════════════════════════
   Controls Wiring
   ═══════════════════════════════════════════════════════════════ */
function initControls() {
  // Theme toggle
  document.getElementById('theme-toggle').addEventListener('click', () => {
    const next = State.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
  });

  // Refresh button
  document.getElementById('btn-refresh').addEventListener('click', () => {
    refreshDashboard();
    Toast.info('Refreshed', 'Dashboard data updated');
  });

  // Scanner
  document.getElementById('btn-scan').addEventListener('click', () => runNetworkScan());
  document.getElementById('scanner-filter').addEventListener('input', e => {
    filterNetworkTable(e.target.value);
  });

  // Devices
  document.getElementById('btn-device-scan').addEventListener('click', () => runDeviceScan());
  document.getElementById('device-filter').addEventListener('input', e => {
    DeviceDiscovery.renderDevices(DeviceDiscovery.getDevices(), e.target.value);
  });

  // Speed test
  document.getElementById('btn-speedtest').addEventListener('click', () => runSpeedTest());

  // History
  document.getElementById('btn-export-csv').addEventListener('click', () => {
    Logger.exportCSV();
    Toast.success('Exported', 'Signal history exported as CSV');
  });
  document.getElementById('btn-export-json').addEventListener('click', () => {
    Logger.exportJSON();
    Toast.success('Exported', 'Signal history exported as JSON');
  });
  document.getElementById('btn-clear-history').addEventListener('click', () => {
    Logger.clearHistory();
    Toast.info('Cleared', 'History has been cleared');
  });

  // Alerts
  document.getElementById('btn-clear-alerts').addEventListener('click', () => {
    Logger.clearAlerts();
    Toast.info('Cleared', 'All alerts cleared');
  });

  // Alert rules
  document.getElementById('rule-weak-signal').addEventListener('change', e => {
    Logger.setRule('weakSignal', e.target.checked,
      parseInt(document.getElementById('threshold-signal').value));
  });
  document.getElementById('threshold-signal').addEventListener('change', e => {
    Logger.setRule('weakSignal', document.getElementById('rule-weak-signal').checked,
      parseInt(e.target.value));
  });
  document.getElementById('rule-new-device').addEventListener('change', e => {
    Logger.setRule('newDevice', e.target.checked);
  });
  document.getElementById('rule-congestion').addEventListener('change', e => {
    Logger.setRule('congestion', e.target.checked);
  });
  document.getElementById('rule-latency').addEventListener('change', e => {
    Logger.setRule('latency', e.target.checked,
      parseInt(document.getElementById('threshold-latency').value));
  });
  document.getElementById('threshold-latency').addEventListener('change', e => {
    Logger.setRule('latency', document.getElementById('rule-latency').checked,
      parseInt(e.target.value));
  });

  // Signal range selector
  document.getElementById('signal-range').addEventListener('change', () => {
    // Re-filter history — future: filter history chart by range
  });
}

/* ═══════════════════════════════════════════════════════════════
   Monitoring Engine
   ═══════════════════════════════════════════════════════════════ */
function startMonitoring() {
  // Initial scan
  refreshDashboard();
  ChartManager.init();

  // Poll every 3 seconds
  State.monitorInterval = setInterval(() => {
    tickMonitor();
  }, 3000);
}

function tickMonitor() {
  const signal = NetworkScanner.getLiveSignal();
  const net = NetworkScanner.getCurrentNetwork();
  State.currentNetwork = net;

  // Update KPIs
  updateKPIs(signal, net);

  // Log signal
  const entry = Logger.logSignal(net, signal);

  // Check alerts
  Logger.checkAlerts(signal, net);

  // Update signal chart
  ChartManager.pushSignalPoint(formatTime(), signal);

  // Redraw gauge
  ChartManager.drawGauge('gauge-canvas', document.getElementById('gauge-value'), signal);

  // Update channel map (every 5 ticks)
  if (Math.random() < 0.2) {
    NetworkScanner.renderChannelMap(net?.channel || 6);
  }

  // Update history table if visible
  if (State.currentSection === 'history') {
    Logger.renderHistoryTable();
    ChartManager.initHistoryChart(Logger.getHistory());
  }
}

function refreshDashboard() {
  const net = NetworkScanner.getCurrentNetwork();
  State.currentNetwork = net;

  if (net) {
    updateConnectionInfo(net);
    NetworkScanner.renderChannelMap(net.channel);
    const signal = net.signal;
    updateKPIs(signal, net);
    ChartManager.drawGauge('gauge-canvas', document.getElementById('gauge-value'), signal);
  }
}

function updateKPIs(signal, net) {
  // Signal KPI
  const sigEl = document.getElementById('kpi-signal-value');
  const sigQEl = document.getElementById('kpi-signal-quality');
  if (sigEl) sigEl.textContent = `${signal} dBm`;
  if (sigQEl) {
    const qual = SignalUtils.qualityLabel(signal);
    const pct  = SignalUtils.dbmToPercent(signal);
    sigQEl.textContent = `${qual} · ${pct}%`;
  }

  // Network KPI
  const netEl   = document.getElementById('kpi-network-value');
  const netBand = document.getElementById('kpi-network-band');
  if (netEl && net) netEl.textContent = net.ssid.length > 14 ? net.ssid.substring(0, 14) + '…' : net.ssid;
  if (netBand && net) netBand.textContent = `${net.band} · Ch ${net.channel}`;

  // Devices KPI
  const devCount = DeviceDiscovery.getDevices().length;
  const devEl    = document.getElementById('kpi-devices-value');
  const devSub   = document.getElementById('kpi-devices-sub');
  if (devEl) devEl.textContent = devCount;
  if (devSub) devSub.textContent = devCount > 0 ? 'Devices connected' : 'Not scanned';

  // Latency KPI
  const results = SpeedTest.getResults();
  const latEl   = document.getElementById('kpi-latency-value');
  const latSub  = document.getElementById('kpi-latency-sub');
  if (latEl && results.length) {
    const last = results[results.length - 1];
    latEl.textContent = `${last.ping}ms`;
    if (latSub) latSub.textContent = `Jitter: ${last.jitter}ms`;
  }
}

function updateConnectionInfo(net) {
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  set('info-ssid', net.ssid);
  set('info-bssid', net.bssid);
  set('info-security', net.security);
  set('info-freq', SignalUtils.channelToFreq(net.channel));
  set('info-channel', net.channel);
  set('info-ip', Sim.ip());
  set('info-mac', Sim.mac());
  set('info-gateway', '192.168.1.1');

  // Page KPIs
  set('kpi-network-value', net.ssid.length > 14 ? net.ssid.substring(0, 14) + '…' : net.ssid);
  set('kpi-network-band', `${net.band} · Ch ${net.channel}`);
}

/* ═══════════════════════════════════════════════════════════════
   Scanner Actions
   ═══════════════════════════════════════════════════════════════ */
async function runNetworkScan() {
  const btn = document.getElementById('btn-scan');
  const tbody = document.getElementById('networks-tbody');

  btn.disabled = true;
  btn.textContent = 'Scanning…';
  tbody.innerHTML = '<tr><td colspan="8" class="empty-state scanning">Scanning nearby networks…</td></tr>';

  try {
    const networks = await NetworkScanner.scan();
    State.networks = networks;

    tbody.innerHTML = networks.map(n => NetworkScanner.renderNetworkRow(n)).join('');
    ChartManager.initNetworksBarChart(networks);
    ChartManager.initBandDonutChart(networks);

    Toast.success('Scan Complete', `Found ${networks.length} networks`);
  } catch (err) {
    Toast.error('Scan Failed', err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg> Scan`;
  }
}

function filterNetworkTable(query) {
  const rows = document.querySelectorAll('#networks-tbody tr');
  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(query.toLowerCase()) ? '' : 'none';
  });
}

/* ═══════════════════════════════════════════════════════════════
   Device Scan Actions
   ═══════════════════════════════════════════════════════════════ */
async function runDeviceScan() {
  const btn = document.getElementById('btn-device-scan');
  const grid = document.getElementById('devices-grid');

  btn.disabled = true;
  btn.textContent = 'Discovering…';
  grid.innerHTML = '<div class="empty-state scanning">Scanning network for devices…</div>';

  try {
    const devices = await DeviceDiscovery.discover();
    DeviceDiscovery.renderDevices(devices);
    updateKPIs(NetworkScanner.getLiveSignal(), State.currentNetwork);
    Toast.success('Discovery Complete', `Found ${devices.length} devices`);
  } catch (err) {
    Toast.error('Discovery Failed', err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg> Discover`;
  }
}

/* ═══════════════════════════════════════════════════════════════
   Speed Test Actions
   ═══════════════════════════════════════════════════════════════ */
async function runSpeedTest() {
  if (SpeedTest.isRunning()) return;
  const btn = document.getElementById('btn-speedtest');
  btn.textContent = 'Running…';
  btn.classList.add('running');

  const setResult = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val !== null ? val : '—';
  };

  // Reset display
  setResult('result-ping-value', null);
  setResult('result-download-value', null);
  setResult('result-upload-value', null);
  setResult('result-jitter-value', null);
  document.getElementById('speed-value').textContent = '0';

  try {
    await SpeedTest.run({
      onPhase: phase => {
        document.getElementById('speed-phase').textContent = phase;
      },
      onProgress: (mbps, phase) => {
        document.getElementById('speed-value').textContent = mbps.toFixed(1);
        document.getElementById('speed-unit').textContent = 'Mbps';
      },
      onPing: (ping, jitter) => {
        setResult('result-ping-value', ping);
        setResult('result-jitter-value', jitter);
        // Also check latency alert
        Logger.checkAlerts(NetworkScanner.getLiveSignal(), State.currentNetwork, ping);
        updateKPIs(NetworkScanner.getLiveSignal(), State.currentNetwork);
      },
      onComplete: result => {
        setResult('result-download-value', result.download);
        setResult('result-upload-value', result.upload);
        updateKPIs(NetworkScanner.getLiveSignal(), State.currentNetwork);
        ChartManager.initSpeedHistoryChart(SpeedTest.getResults());
        Toast.success('Speed Test Complete',
          `↓ ${result.download} Mbps | ↑ ${result.upload} Mbps | Ping ${result.ping}ms`);
      },
    });
  } finally {
    btn.textContent = 'Start Test';
    btn.classList.remove('running');
    document.getElementById('speed-phase').textContent = 'Complete';
  }
}

/* ═══════════════════════════════════════════════════════════════
   Theme
   ═══════════════════════════════════════════════════════════════ */
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  State.theme = theme;
  localStorage.setItem('wm_theme', theme);
}
