/**
 * scanner.js — Network scanning engine for WiFi Monitor
 * Uses the Network Information API and simulated data for browser environments.
 * In Electron/Node environments, native APIs would replace the simulation layer.
 */

'use strict';

const NetworkScanner = (() => {
  let _networks = [];
  let _currentNetwork = null;

  /* ── SSIDs and channels pool for simulation ─────────────────── */
  const SSIDS = [
    { ssid: 'HomeNetwork_5G',    bssid: null, ch: 36,  security: 'WPA3',  band: '5 GHz' },
    { ssid: 'TechHub-WiFi',      bssid: null, ch: 6,   security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'Office_Net',        bssid: null, ch: 11,  security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'SKYNET-2.4',        bssid: null, ch: 1,   security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'CoffeeShop_Free',   bssid: null, ch: 6,   security: 'Open',  band: '2.4 GHz' },
    { ssid: 'GuestNetwork',      bssid: null, ch: 11,  security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'Starlink-Home',     bssid: null, ch: 149, security: 'WPA3',  band: '5 GHz' },
    { ssid: 'ApartmentWiFi',     bssid: null, ch: 6,   security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'SecureNet-Corp',    bssid: null, ch: 100, security: 'WPA3',  band: '5 GHz' },
    { ssid: 'FamilyRouter',      bssid: null, ch: 1,   security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'NetGear_6E',        bssid: null, ch: 37,  security: 'WPA3',  band: '6 GHz' },
    { ssid: 'ASUS-Router-Pro',   bssid: null, ch: 44,  security: 'WPA3',  band: '5 GHz' },
    { ssid: 'TP-Link_AX90',      bssid: null, ch: 6,   security: 'WPA2',  band: '2.4 GHz' },
    { ssid: 'xfinitywifi',       bssid: null, ch: 1,   security: 'Open',  band: '2.4 GHz' },
    { ssid: 'MySpectrumWiFi',    bssid: null, ch: 11,  security: 'WPA2',  band: '2.4 GHz' },
  ];

  /** Generate a fresh randomized network list */
  function _generateNetworks() {
    const connected = Sim.pick(SSIDS.filter(n => n.band === '5 GHz' || n.band === '2.4 GHz'));
    const seen = new Set();
    const nets = [];

    for (const template of SSIDS) {
      const isConnected = template.ssid === connected.ssid;
      const signal = isConnected
        ? Sim.int(-55, -45)
        : Sim.int(-90, -45);

      const bssid = template.bssid || Sim.mac();
      if (seen.has(bssid)) continue;
      seen.add(bssid);

      nets.push({
        ssid:      template.ssid,
        bssid,
        channel:   template.ch,
        security:  template.security,
        band:      template.band,
        signal,
        quality:   SignalUtils.dbmToPercent(signal),
        connected: isConnected,
      });
    }

    // Sort by signal descending
    nets.sort((a, b) => b.signal - a.signal);
    _networks = nets;
    _currentNetwork = nets.find(n => n.connected) || nets[0];
    return nets;
  }

  /** Scan networks — returns a Promise (simulates async scan) */
  function scan() {
    return new Promise(resolve => {
      setTimeout(() => {
        resolve(_generateNetworks());
      }, Sim.int(800, 1800));
    });
  }

  /** Get the current connected network */
  function getCurrentNetwork() {
    if (!_currentNetwork) _generateNetworks();
    return _currentNetwork;
  }

  /** Build channel map data (channel → [networks]) */
  function getChannelMap() {
    const map = {};
    for (const net of _networks) {
      const ch = net.channel;
      if (!map[ch]) map[ch] = [];
      map[ch].push(net);
    }
    return map;
  }

  /** Live signal update (simulates RSSI fluctuation) */
  function getLiveSignal() {
    if (!_currentNetwork) return -70;
    // Drift the signal slightly
    const drift = Sim.gaussian(0, 2);
    _currentNetwork.signal = Math.max(-100, Math.min(-30, _currentNetwork.signal + drift));
    _currentNetwork.quality = SignalUtils.dbmToPercent(_currentNetwork.signal);
    return Math.round(_currentNetwork.signal);
  }

  /** Render network row HTML */
  function renderNetworkRow(net) {
    const qual = SignalUtils.qualityClass(net.signal);
    const pct  = net.quality;
    const bars = [25, 50, 75, 100].map((threshold, i) => {
      const lit = pct >= threshold;
      const cls = lit ? `lit ${qual !== 'excellent' && qual !== 'good' && i > 1 ? qual : ''}` : '';
      return `<div class="signal-bar-seg ${cls}" style="height:${(i+1)*4}px"></div>`;
    }).join('');

    const lockIcon = net.security !== 'Open'
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>`
      : '';

    const connBadge = net.connected
      ? `<span class="quality-pill quality-excellent" style="margin-left:4px;font-size:10px">Connected</span>`
      : '';

    return `
      <tr>
        <td>
          <div class="signal-bar-wrap">
            <div class="signal-bars">${bars}</div>
          </div>
        </td>
        <td>
          <strong>${net.ssid}</strong>${connBadge}
        </td>
        <td class="mono" style="font-size:11px">${net.bssid}</td>
        <td>${net.band}</td>
        <td>${net.channel}</td>
        <td class="lock-icon">${lockIcon} ${net.security}</td>
        <td class="mono">${net.signal}</td>
        <td>
          <span class="quality-pill quality-${qual}">${SignalUtils.qualityLabel(net.signal)} (${pct}%)</span>
        </td>
      </tr>
    `;
  }

  /** Render the channel heatmap */
  function renderChannelMap(currentChannel) {
    const map = getChannelMap();
    const container = document.getElementById('channel-map');
    if (!container) return;

    container.innerHTML = '';
    const channels = Object.keys(map).map(Number).sort((a, b) => a - b);
    const maxCount = Math.max(...Object.values(map).map(v => v.length), 1);

    for (const ch of channels) {
      const nets = map[ch];
      const heightPx = Math.round((nets.length / maxCount) * 80) + 4;
      const isMine = ch === currentChannel;
      const hasOverlap = !isMine && nets.length > 0 && Math.abs(ch - currentChannel) <= 4;

      const cls = isMine ? 'mine' : hasOverlap ? 'overlap' : 'other';
      const wrap = document.createElement('div');
      wrap.className = 'channel-bar-wrap';
      wrap.title = `Ch ${ch}: ${nets.map(n => n.ssid).join(', ')}`;
      wrap.innerHTML = `
        <div class="channel-bar ${cls}" style="height:${heightPx}px"></div>
        <div class="channel-num">${ch}</div>
      `;
      container.appendChild(wrap);
    }

    const badge = document.getElementById('active-channel-badge');
    if (badge) badge.textContent = `Ch ${currentChannel}`;
  }

  return { scan, getCurrentNetwork, getChannelMap, getLiveSignal, renderNetworkRow, renderChannelMap };
})();
