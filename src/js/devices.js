/**
 * devices.js — Device discovery for WiFi Monitor
 *
 * Real device discovery is not implemented yet (see docs/IMPLEMENTATION_PLAN.md).
 * In demo modes this module generates SIMULATED devices, labelled as such.
 * With live data it reports the feature as unavailable instead of inventing devices.
 */

'use strict';

const DeviceDiscovery = (() => {
  let _devices = [];
  let _knownDevices = new Set();

  const DEVICE_TYPES = [
    {
      name: 'MacBook Pro',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`,
      vendor: 'Apple Inc.',
    },
    {
      name: 'iPhone 15',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`,
      vendor: 'Apple Inc.',
    },
    {
      name: 'Samsung Galaxy',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/></svg>`,
      vendor: 'Samsung Electronics',
    },
    {
      name: 'Smart TV',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="15" rx="2" ry="2"/><polyline points="17 2 12 7 7 2"/></svg>`,
      vendor: 'LG Electronics',
    },
    {
      name: 'Raspberry Pi',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>`,
      vendor: 'Raspberry Pi Foundation',
    },
    {
      name: 'Windows PC',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>`,
      vendor: 'Intel Corporate',
    },
    {
      name: 'Amazon Echo',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M8.56 2.75c4.37 6.03 6.02 9.42 8.03 17.72m2.54-15.38c-3.72 4.35-8.94 5.66-16.88 5.85m19.5 1.9c-3.5-.93-6.63-.82-8.94 0-2.58.92-5.01 2.86-7.44 6.32"/></svg>`,
      vendor: 'Amazon Technologies',
    },
    {
      name: 'Google Home',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
      vendor: 'Google LLC',
    },
    {
      name: 'Network Printer',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>`,
      vendor: 'HP Inc.',
    },
    {
      name: 'NAS Server',
      icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>`,
      vendor: 'Synology Inc.',
    },
  ];

  const UNAVAILABLE_MSG = 'Live device discovery is not implemented yet. WiFi Monitor will not show invented devices.';

  function isAvailable() {
    return DataSource.isSimulated();
  }

  /** Generate SIMULATED devices (demo modes only). */
  function discover() {
    if (!isAvailable()) {
      _devices = [];
      return Promise.reject(new Error(UNAVAILABLE_MSG));
    }
    return new Promise(resolve => {
      setTimeout(() => {
        const count = Sim.int(3, 10);
        const subnet = '192.168.1';
        const usedIPs = new Set();
        const devices = [];

        // Always include the gateway
        devices.push({
          id: 'gateway',
          name: 'Router / Gateway',
          ip: `${subnet}.1`,
          mac: '02:00:00:00:00:fe',
          vendor: 'NETGEAR',
          type: 'router',
          status: 'online',
          simulated: true,
          latency: Sim.int(1, 5),
          icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M10.54 16.1a6 6 0 0 1 2.92 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>`,
        });
        usedIPs.add(`${subnet}.1`);

        for (let i = 0; i < count; i++) {
          let ip;
          do { ip = Sim.ip(subnet); } while (usedIPs.has(ip));
          usedIPs.add(ip);

          const dt = Sim.pick(DEVICE_TYPES);
          const mac = `02:${Sim.mac().slice(3)}`; // locally administered: cannot collide with a real vendor
          const isNew = !_knownDevices.has(mac);

          if (isNew) {
            _knownDevices.add(mac);
            EventBus.emit('newDevice', { name: dt.name, ip, mac, simulated: true });
          }

          devices.push({
            id: mac,
            name: dt.name,
            ip,
            mac,
            vendor: dt.vendor,
            type: 'client',
            status: 'online',
            latency: Sim.int(2, 30),
            icon: dt.icon,
            simulated: true,
          });
        }

        _devices = devices;
        resolve(devices);
      }, Sim.int(1000, 2500));
    });
  }

  /** Render devices to the grid */
  function renderDevices(devices, filter = '') {
    const grid = document.getElementById('devices-grid');
    if (!grid) return;

    const filtered = filter
      ? devices.filter(d =>
          d.name.toLowerCase().includes(filter.toLowerCase()) ||
          d.ip.includes(filter) ||
          d.mac.toLowerCase().includes(filter.toLowerCase())
        )
      : devices;

    if (!isAvailable()) {
      grid.innerHTML = `<div class="empty-state">${escapeHTML(UNAVAILABLE_MSG)}<br>`
        + 'Restart with <code>wifi-monitor serve --demo</code> to preview the interface with simulated devices.</div>';
      return;
    }
    if (!filtered.length) {
      grid.innerHTML = '<div class="empty-state">No devices match your filter</div>';
      return;
    }

    // d.icon comes from the built-in DEVICE_TYPES table above, never from scan data.
    grid.innerHTML = filtered.map(d => `
      <div class="device-card" data-id="${escapeHTML(d.id)}">
        ${d.simulated ? '<span class="sim-tag">Simulated</span>' : ''}
        <div class="device-icon">${d.icon}</div>
        <div class="device-name">${escapeHTML(d.name)}</div>
        <div class="device-ip">${escapeHTML(d.ip)}</div>
        <div class="device-mac">${escapeHTML(d.mac)}</div>
        <div class="device-vendor">${escapeHTML(d.vendor)}</div>
        <div class="device-status">
          <div class="device-status-dot"></div>
          Online · ${escapeHTML(d.latency)}ms
        </div>
      </div>
    `).join('');
  }

  return { discover, renderDevices, isAvailable, getDevices: () => _devices };
})();
