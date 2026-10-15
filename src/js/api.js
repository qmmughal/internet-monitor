/**
 * api.js — Data source selection for WiFi Monitor
 *
 * The browser cannot read Wi-Fi hardware. Real measurements come from the
 * local API started with `wifi-monitor serve`. Without it the dashboard runs
 * in browser demo mode, where every value is simulated and labelled as such.
 *
 * Modes:
 *   'live'        – served by `wifi-monitor serve` (real OS data)
 *   'server-demo' – served by `wifi-monitor serve --demo` (simulated by the server)
 *   'browser-demo'– no API reachable (simulated in the browser)
 */

'use strict';

const DataSource = (() => {
  let _mode = 'browser-demo';
  let _info = null;

  async function fetchJSON(path, { method = 'GET', timeout = 8000 } = {}) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), timeout);
    try {
      const res = await fetch(path, {
        method,
        cache: 'no-store',
        signal: ctrl.signal,
        headers: method === 'POST' ? { 'X-WiFi-Monitor': '1' } : {},
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        const err = new Error(body.error || `HTTP ${res.status}`);
        err.status = res.status;
        throw err;
      }
      return body;
    } catch (err) {
      if (err.name === 'AbortError') throw new Error('request timed out');
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  /** Detect the local API. Only attempted when the page is served over http(s). */
  async function detect() {
    if (!/^https?:$/.test(location.protocol)) return _mode;
    try {
      _info = await fetchJSON('api/v1/status', { timeout: 4000 });
      _mode = _info.demo ? 'server-demo' : 'live';
    } catch (_) {
      _mode = 'browser-demo';
    }
    return _mode;
  }

  return {
    detect,
    fetchJSON,
    mode: () => _mode,
    usesApi: () => _mode !== 'browser-demo',
    isSimulated: () => _mode !== 'live',
    info: () => _info,
  };
})();
