/**
 * scanner.js — Wi-Fi state and access point scanning for Internet Monitor
 *
 * With the local API (`internet-monitor serve`) data comes from the operating
 * system. Without it, this module generates clearly labelled demo data.
 */

'use strict';

const NetworkScanner = (() => {
  let _networks = [];
  let _demoCurrent = null;

  /* ── Browser demo data (never used when the API is available) ── */
  const DEMO_SSIDS = [
    { ssid: 'DEMO-Home_5G',     ch: 36,  security: 'WPA3', band: '5 GHz' },
    { ssid: 'DEMO-TechHub',     ch: 6,   security: 'WPA2', band: '2.4 GHz' },
    { ssid: 'DEMO-Office',      ch: 11,  security: 'WPA2', band: '2.4 GHz' },
    { ssid: 'DEMO-Neighbour',   ch: 1,   security: 'WPA2', band: '2.4 GHz' },
    { ssid: 'DEMO-Cafe',        ch: 6,   security: 'Open', band: '2.4 GHz' },
    { ssid: 'DEMO-Guest',       ch: 11,  security: 'WPA2', band: '2.4 GHz' },
    { ssid: 'DEMO-Upstairs',    ch: 149, security: 'WPA3', band: '5 GHz' },
    { ssid: 'DEMO-Apartment',   ch: 6,   security: 'WPA2', band: '2.4 GHz' },
    { ssid: 'DEMO-6E',          ch: 37,  security: 'WPA3', band: '6 GHz' },
    { ssid: 'DEMO-Router-Pro',  ch: 44,  security: 'WPA3', band: '5 GHz' },
  ];

  function _demoNetworks() {
    const nets = DEMO_SSIDS.map((t, i) => {
      const connected = i === 0;
      const signal = connected ? Sim.int(-58, -48) : Sim.int(-90, -45);
      return {
        ssid: t.ssid,
        bssid: `02:00:00:00:00:${(i + 1).toString(16).padStart(2, '0')}`, // locally administered, never a real vendor
        channel: t.ch,
        band: t.band,
        security: t.security,
        signal,
        signalMode: 'simulated',
        quality: SignalUtils.dbmToPercent(signal),
        connected,
      };
    });
    nets.sort((a, b) => b.signal - a.signal);
    return nets;
  }

  function _demoSnapshot() {
    if (!_demoCurrent) _demoCurrent = _demoNetworks().find(n => n.connected);
    const drift = Sim.gaussian(0, 2);
    _demoCurrent.signal = Math.max(-95, Math.min(-35, _demoCurrent.signal + drift));
    const signal = Math.round(_demoCurrent.signal);
    return {
      ts: Date.now(),
      mode: 'simulated',
      simulated: true,
      network: { ..._demoCurrent, signal, quality: SignalUtils.dbmToPercent(signal) },
      signal,
      signalMode: 'simulated',
      source: 'browser demo',
      error: null,
      hint: null,
      ip: null,
      gateway: null,
    };
  }

  /* ── API mapping ─────────────────────────────────────────────── */
  function _fromAccessPoint(ap) {
    return {
      ssid: ap.ssid,
      bssid: ap.bssid,
      channel: ap.channel,
      band: ap.band,
      security: ap.security,
      signal: ap.signal_dbm,
      signalMode: ap.signal_mode,
      quality: ap.signal_percent ?? (ap.signal_dbm != null ? SignalUtils.dbmToPercent(ap.signal_dbm) : null),
      connected: ap.connected,
    };
  }

  function _fromStatus(status) {
    const wifi = status.wifi || {};
    const net = (status.network && status.network.data) || {};
    const snap = {
      ts: Date.now(),
      mode: wifi.mode,
      simulated: !!wifi.is_simulated,
      network: null,
      signal: null,
      signalMode: 'unavailable',
      source: wifi.source,
      error: wifi.error,
      hint: wifi.hint,
      ip: net.local_ip ?? null,
      gateway: net.gateway ?? null,
      standard: status.wifi_standard || null,
      traffic: status.traffic || null,
    };
    if (wifi.mode === 'unavailable') return snap;
    const iface = (wifi.data || []).find(i => i.connected);
    if (!iface) {
      snap.mode = 'unavailable';
      snap.error = (wifi.data || []).length ? 'No Wi-Fi interface is connected' : 'No Wi-Fi interface found';
      return snap;
    }
    const sig = iface.signal_dbm;
    snap.network = {
      ssid: iface.ssid,
      bssid: iface.bssid,
      channel: iface.channel,
      band: iface.band,
      frequency: iface.frequency_mhz,
      security: iface.security,
      radio: iface.radio_type,
      rx: iface.rx_rate_mbps,
      tx: iface.tx_rate_mbps,
      connected: true,
    };
    if (sig && sig.value != null) {
      snap.signal = sig.value;
      snap.signalMode = sig.mode;
      snap.network.signal = sig.value;
      snap.network.quality = iface.signal_percent ?? SignalUtils.dbmToPercent(sig.value);
    }
    return snap;
  }

  /** Current connection snapshot with provenance. Never throws. */
  async function poll() {
    if (!DataSource.usesApi()) return _demoSnapshot();
    try {
      return _fromStatus(await DataSource.fetchJSON('api/v1/status'));
    } catch (err) {
      return {
        ts: Date.now(), mode: 'unavailable', simulated: false, network: null, signal: null,
        signalMode: 'unavailable', source: 'api', error: `Local API unreachable: ${err.message}`,
        hint: 'Is `internet-monitor serve` still running?', ip: null, gateway: null,
      };
    }
  }

  /** Scan nearby access points. Rejects with a user-facing message when unavailable. */
  async function scan() {
    if (!DataSource.usesApi()) {
      await new Promise(r => setTimeout(r, Sim.int(600, 1200)));
      _networks = _demoNetworks();
      return { networks: _networks, simulated: true, hint: null };
    }
    const res = await DataSource.fetchJSON('api/v1/wifi/access-points', { timeout: 30000 });
    if (res.mode === 'unavailable') {
      const err = new Error(res.error || 'Access point scan unavailable');
      err.hint = res.hint;
      throw err;
    }
    _networks = (res.data || []).map(_fromAccessPoint);
    _networks.sort((a, b) => (b.signal ?? -999) - (a.signal ?? -999));
    return { networks: _networks, simulated: !!res.is_simulated, hint: res.hint };
  }

  /** Group scanned access points by band + channel. */
  function getChannelMap() {
    const map = new Map();
    for (const net of _networks) {
      if (net.channel == null) continue;
      const key = `${net.band || '?'}|${net.channel}`;
      if (!map.has(key)) map.set(key, { band: net.band, channel: net.channel, nets: [] });
      map.get(key).nets.push(net);
    }
    return [...map.values()].sort((a, b) =>
      (SignalUtils.channelToMHz(a.channel, a.band) ?? 0) - (SignalUtils.channelToMHz(b.channel, b.band) ?? 0));
  }

  /** Render one access point row; every value is escaped. */
  function renderNetworkRow(net) {
    const hasSignal = net.signal != null;
    const qual = hasSignal ? SignalUtils.qualityClass(net.signal) : 'poor';
    const pct  = net.quality ?? 0;
    const bars = [25, 50, 75, 100].map((threshold, i) => {
      const lit = hasSignal && pct >= threshold;
      const cls = lit ? `lit ${qual !== 'excellent' && qual !== 'good' && i > 1 ? qual : ''}` : '';
      return `<div class="signal-bar-seg ${cls}" style="height:${(i + 1) * 4}px"></div>`;
    }).join('');

    const lockIcon = net.security && net.security !== 'Open'
      ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" aria-hidden="true"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
      : '';
    const connBadge = net.connected
      ? '<span class="quality-pill quality-excellent conn-badge">Connected</span>'
      : '';
    const name = net.ssid ? `<strong>${escapeHTML(net.ssid)}</strong>` : '<em class="muted">&lt;hidden&gt;</em>';
    const approx = net.signalMode === 'estimated' ? '<span title="Estimated from the OS signal percentage">≈</span>' : '';
    const quality = hasSignal
      ? `<span class="quality-pill quality-${qual}">${SignalUtils.qualityLabel(net.signal)} (${escapeHTML(pct)}%)</span>`
      : '<span class="muted">—</span>';

    return `
      <tr>
        <td><div class="signal-bar-wrap"><div class="signal-bars">${bars}</div></div></td>
        <td>${name}${connBadge}</td>
        <td class="mono small">${escapeHTML(net.bssid ?? '—')}</td>
        <td>${escapeHTML(net.band ?? '—')}</td>
        <td>${escapeHTML(net.channel ?? '—')}</td>
        <td class="lock-icon">${lockIcon} ${escapeHTML(net.security ?? '—')}</td>
        <td class="mono">${approx}${hasSignal ? escapeHTML(net.signal) : '—'}</td>
        <td>${quality}</td>
      </tr>
    `;
  }

  /** Render access-point counts per channel (a count, not measured RF utilization). */
  function renderChannelMap(currentChannel, currentBand) {
    const container = document.getElementById('channel-map');
    if (!container) return;
    const groups = getChannelMap();
    container.innerHTML = '';

    if (!groups.length) {
      container.innerHTML = `<div class="channel-loading">${
        DataSource.usesApi() ? 'Run a scan in Network Scanner to see channel usage.' : 'No scan data yet.'}</div>`;
    } else {
      const maxCount = Math.max(...groups.map(g => g.nets.length), 1);
      for (const g of groups) {
        const heightPx = Math.round((g.nets.length / maxCount) * 80) + 4;
        const isMine = g.channel === currentChannel && (!currentBand || g.band === currentBand);
        const overlap = !isMine && g.band === '2.4 GHz' && currentBand === '2.4 GHz'
          && currentChannel != null && Math.abs(g.channel - currentChannel) <= 4;
        const wrap = document.createElement('div');
        wrap.className = 'channel-bar-wrap';
        wrap.title = `${g.band || ''} ch ${g.channel}: ${g.nets.length} access point(s) — `
          + g.nets.map(n => n.ssid || '<hidden>').join(', ');
        const bar = document.createElement('div');
        bar.className = `channel-bar ${isMine ? 'mine' : overlap ? 'overlap' : 'other'}`;
        bar.style.height = `${heightPx}px`;
        const num = document.createElement('div');
        num.className = 'channel-num';
        num.textContent = g.channel;
        wrap.append(bar, num);
        container.appendChild(wrap);
      }
    }

    const badge = document.getElementById('active-channel-badge');
    if (badge) badge.textContent = currentChannel != null ? `Ch ${currentChannel}` : 'Ch —';
  }

  return { poll, scan, getChannelMap, renderNetworkRow, renderChannelMap, getNetworks: () => _networks };
})();
