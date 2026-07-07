/**
 * custom-plugin.js — Example: Adding a custom WiFi Monitor plugin
 * 
 * This example shows how to extend WiFi Monitor with a custom
 * module that adds a "packet loss" metric to the dashboard.
 */

'use strict';

/* ── 1. Define your plugin ──────────────────────────────────────── */
const PacketLossPlugin = (() => {
  const PING_COUNT = 5;
  let _lossHistory = [];

  /**
   * Simulate packet loss measurement.
   * In a native environment, replace this with actual ICMP ping logic.
   * 
   * @returns {Promise<number>} Packet loss percentage (0-100)
   */
  async function measurePacketLoss() {
    let lost = 0;
    for (let i = 0; i < PING_COUNT; i++) {
      // Simulate random packet loss (0-10%)
      if (Math.random() < 0.05) lost++;
      await new Promise(r => setTimeout(r, 100));
    }
    const lossPercent = Math.round((lost / PING_COUNT) * 100);
    _lossHistory.push(lossPercent);
    return lossPercent;
  }

  /** Render the plugin's UI into a container element */
  function renderWidget(containerId) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.warn(`[PacketLossPlugin] Container #${containerId} not found`);
      return;
    }

    const widget = document.createElement('div');
    widget.className = 'kpi-card';
    widget.id = 'plugin-packet-loss';
    widget.innerHTML = `
      <div class="kpi-icon" style="background:rgba(248,113,113,0.15);color:var(--accent-danger)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div class="kpi-info">
        <div class="kpi-value" id="plugin-loss-value">—</div>
        <div class="kpi-label">Packet Loss</div>
        <div class="kpi-sub" id="plugin-loss-sub">Not measured</div>
      </div>
    `;
    container.appendChild(widget);
  }

  /** Start polling packet loss and updating the widget */
  function start(intervalMs = 5000) {
    const updateWidget = async () => {
      const loss = await measurePacketLoss();
      const el = document.getElementById('plugin-loss-value');
      const sub = document.getElementById('plugin-loss-sub');
      if (el) el.textContent = `${loss}%`;
      if (sub) {
        sub.textContent = loss === 0 ? 'No loss' : loss < 5 ? 'Minimal loss' : 'High loss!';
        sub.style.color = loss === 0 ? 'var(--signal-excellent)' : loss < 5 ? 'var(--signal-fair)' : 'var(--signal-poor)';
      }

      // Emit event so other modules can react
      EventBus.emit('packetLoss', { loss, history: _lossHistory });

      // Trigger alert if loss is high
      if (loss > 10) {
        Toast.warning('Packet Loss Detected', `${loss}% packet loss on current network`);
      }
    };

    updateWidget(); // immediate first run
    return setInterval(updateWidget, intervalMs);
  }

  return { measurePacketLoss, renderWidget, start };
})();


/* ── 2. Register the plugin when the app loads ──────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Wait for main app to initialize, then inject our widget
  setTimeout(() => {
    // Inject into the KPI grid on the dashboard
    PacketLossPlugin.renderWidget('kpi-grid');
    PacketLossPlugin.start(5000);
    console.log('[PacketLossPlugin] Initialized successfully');
  }, 1000);
});


/* ── 3. Listen to EventBus events from other modules ────────────── */
EventBus.on('alert', alert => {
  // React to alerts from the main app
  if (alert.type === 'weakSignal') {
    console.log('[PacketLossPlugin] Weak signal detected — measuring packet loss...');
    PacketLossPlugin.measurePacketLoss().then(loss => {
      console.log(`[PacketLossPlugin] Packet loss during weak signal: ${loss}%`);
    });
  }
});

/*
 * ── HOW TO USE THIS PLUGIN ─────────────────────────────────────
 * 
 * 1. Include this script AFTER app.js in index.html:
 *    <script src="../examples/custom-plugin.js"></script>
 * 
 * 2. The plugin will auto-register and inject its widget into the dashboard.
 * 
 * 3. To build a more complex plugin, follow the same pattern:
 *    - Define your module as an IIFE
 *    - Use EventBus to communicate with other modules
 *    - Use Toast for notifications
 *    - Use the CSS design system classes for consistent styling
 * 
 * See docs/ARCHITECTURE.md for the full plugin API reference.
 */
