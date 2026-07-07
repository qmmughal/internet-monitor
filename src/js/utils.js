/**
 * utils.js — Shared utilities for WiFi Monitor
 */

'use strict';

/* ── Signal Quality Helpers ────────────────────────────────────── */
const SignalUtils = {
  /** Convert dBm to quality percentage (0–100) */
  dbmToPercent(dbm) {
    if (dbm >= -50) return 100;
    if (dbm <= -100) return 0;
    return Math.round(((dbm + 100) / 50) * 100);
  },

  /** Return quality label from dBm */
  qualityLabel(dbm) {
    if (dbm >= -50) return 'Excellent';
    if (dbm >= -60) return 'Good';
    if (dbm >= -70) return 'Fair';
    return 'Poor';
  },

  /** Return CSS class suffix from dBm */
  qualityClass(dbm) {
    if (dbm >= -50) return 'excellent';
    if (dbm >= -60) return 'good';
    if (dbm >= -70) return 'fair';
    return 'poor';
  },

  /** Return color hex from dBm */
  qualityColor(dbm) {
    const style = getComputedStyle(document.documentElement);
    if (dbm >= -50) return style.getPropertyValue('--signal-excellent').trim();
    if (dbm >= -60) return style.getPropertyValue('--signal-good').trim();
    if (dbm >= -70) return style.getPropertyValue('--signal-fair').trim();
    return style.getPropertyValue('--signal-poor').trim();
  },

  /** Convert channel to frequency */
  channelToFreq(ch) {
    if (ch >= 1 && ch <= 14) {
      return ch === 14 ? '2.484 GHz' : `${2.407 + ch * 0.005} GHz`;
    }
    if (ch >= 36) return `${5.000 + (ch - 36) * 0.005 + Math.floor((ch - 36) / 4) * 0.020} GHz`;
    return 'Unknown';
  },

  /** Determine band from channel */
  channelBand(ch) {
    if (ch >= 1 && ch <= 14) return '2.4 GHz';
    if (ch >= 36 && ch <= 177) return '5 GHz';
    if (ch >= 1 && ch <= 233 && ch > 177) return '6 GHz';
    return 'Unknown';
  },
};

/* ── Random Simulation Helpers ──────────────────────────────────── */
const Sim = {
  /** Gaussian random with mean and std-dev */
  gaussian(mean, std) {
    let u = 0, v = 0;
    while (u === 0) u = Math.random();
    while (v === 0) v = Math.random();
    return mean + std * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  },

  /** Integer in range [min, max] */
  int(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  },

  /** Float in range */
  float(min, max, dp = 1) {
    return parseFloat((Math.random() * (max - min) + min).toFixed(dp));
  },

  /** Pick random element */
  pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; },

  /** Random MAC address */
  mac() {
    return Array.from({ length: 6 }, () =>
      Math.floor(Math.random() * 256).toString(16).padStart(2, '0').toUpperCase()
    ).join(':');
  },

  /** Random local IP */
  ip(subnet = '192.168.1') {
    return `${subnet}.${Sim.int(2, 254)}`;
  },

  /** Random SSID from pool */
  ssid() {
    const names = [
      'HomeNetwork_5G', 'TechHub-WiFi', 'Office_Net', 'SKYNET-2.4',
      'CoffeeShop_Free', 'GuestNetwork', 'Starlink-Home', 'ApartmentWiFi',
      'SecureNet-Corp', 'FamilyRouter', 'NetGear_6E', 'ASUS-Router-Pro',
    ];
    return Sim.pick(names);
  },

  /** Random OUI vendor */
  vendor() {
    const vendors = [
      'Apple Inc.', 'Samsung Electronics', 'Intel Corporate', 'Qualcomm Inc.',
      'TP-Link Technologies', 'NETGEAR', 'Cisco Systems', 'Raspberry Pi Foundation',
      'Google LLC', 'Amazon Technologies', 'Dell Technologies', 'ASUS',
    ];
    return Sim.pick(vendors);
  },
};

/* ── DOM Helpers ────────────────────────────────────────────────── */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

function el(tag, attrs = {}, ...children) {
  const element = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') element.className = v;
    else if (k === 'html') element.innerHTML = v;
    else element.setAttribute(k, v);
  }
  for (const child of children) {
    if (typeof child === 'string') element.insertAdjacentHTML('beforeend', child);
    else if (child) element.appendChild(child);
  }
  return element;
}

/* ── Toast Notifications ────────────────────────────────────────── */
const Toast = {
  container: null,

  init() { this.container = $('#toast-container'); },

  show(title, message = '', type = 'info', duration = 4000) {
    const icons = {
      success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
      info:    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
      warning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
      error:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    };
    const t = el('div', { class: `toast toast-${type}` },
      el('div', { class: 'toast-icon', html: icons[type] || icons.info }),
      el('div', { class: 'toast-body' },
        el('div', { class: 'toast-title', html: title }),
        message ? el('div', { class: 'toast-message', html: message }) : null,
      ),
    );
    this.container.appendChild(t);
    setTimeout(() => {
      t.classList.add('removing');
      t.addEventListener('animationend', () => t.remove());
    }, duration);
  },

  success(title, msg) { this.show(title, msg, 'success'); },
  info(title, msg)    { this.show(title, msg, 'info'); },
  warning(title, msg) { this.show(title, msg, 'warning'); },
  error(title, msg)   { this.show(title, msg, 'error'); },
};

/* ── Timestamp ──────────────────────────────────────────────────── */
function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function formatDateTime(date = new Date()) {
  return date.toLocaleString();
}

/* ── Export Helpers ─────────────────────────────────────────────── */
function downloadFile(content, filename, type = 'text/plain') {
  const blob = new Blob([content], { type });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

function arrayToCSV(headers, rows) {
  const header = headers.join(',');
  const body = rows.map(r => r.map(c => `"${c}"`).join(',')).join('\n');
  return `${header}\n${body}`;
}

/* ── EventBus (simple pub/sub) ──────────────────────────────────── */
const EventBus = {
  _listeners: {},
  on(event, fn) {
    (this._listeners[event] ??= []).push(fn);
  },
  emit(event, data) {
    (this._listeners[event] ?? []).forEach(fn => fn(data));
  },
  off(event, fn) {
    this._listeners[event] = (this._listeners[event] ?? []).filter(f => f !== fn);
  },
};
