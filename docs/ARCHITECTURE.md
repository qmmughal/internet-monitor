# WiFi Monitor — Architecture Guide

## Overview

```text
            ┌──────────────── OS tools (argument lists, timeouts) ────────────────┐
            │ netsh · nmcli · iw · system_profiler · route · ping · /proc/net/route│
            └──────────────────────────────┬──────────────────────────────────────┘
                                           │ runner.run()
                        ┌──────────────────▼──────────────────┐
                        │ providers/ (one per OS) · netinfo   │  parse → models (with provenance)
                        └───────┬─────────────────────┬───────┘
                                │                     │
               probes.py ───────┤                     │
          (ping/TCP/DNS/HTTPS)  ▼                     ▼
                        diagnostics.py          server.py ── /api/v1 (loopback, read-only)
                         (evidence → rules)          │
                                │                    ▼
                             cli.py            src/ dashboard (api.js picks live vs demo)
```

Design rules:

1. **Collection is separate from presentation.** Providers return `ProviderResult` objects;
   the CLI, the API and the diagnostics engine all consume the same objects.
2. **Failures are data.** Providers and probes never raise for expected failures; they return
   `mode="unavailable"` with `error` and, when actionable, `hint`.
3. **No silent fallback.** Simulated data comes only from `DemoProvider` (`--demo`) or the
   browser demo mode, and is labelled at every layer.
4. **Pure rules.** `diagnostics.classify()` has no I/O, so every rule is unit-tested with
   hand-built evidence.

## Python package (`wifi_monitor/`)

| Module | Responsibility |
|---|---|
| `models.py` | `Measurement`, `WifiInterface`, `AccessPoint`, `ProviderResult`; modes `live`/`estimated`/`simulated`/`unavailable` |
| `runner.py` | Runs OS commands: list args only, no shell, timeout, output cap, OEM code-page decoding on Windows |
| `signal.py` | dBm↔%, channel↔frequency↔band (2.4/5/6 GHz) |
| `providers/windows.py` | `netsh wlan` parsing; Location-permission, service and locale detection |
| `providers/linux.py` | `nmcli` terse parsing (escaped colons), `iw dev <if> link` for live dBm |
| `providers/macos.py` | `system_profiler -json`; legacy `airport -I` when present |
| `providers/demo.py` | Simulated data, locally-administered MACs (`02:…`) |
| `netinfo.py` | Default gateway + local IP |
| `probes.py` | Bounded ICMP ping (IP literals only), TCP connect/latency, DNS with timeout, HTTPS without redirects |
| `diagnostics.py` | `run_diagnostics()` collects evidence; `classify()` produces findings |
| `cli.py` | Subcommands, `--json`, exit codes, optional Rich |
| `server.py` | `ThreadingHTTPServer` serving `src/` and `/api/v1/*` |

### Adding a platform

Subclass `providers.base.WifiProvider`, implement `interfaces()`, `access_points()` and
`capabilities()`, keep parsing in pure functions, add fixtures to `tests/python/fixtures.py`,
and register the class in `providers/__init__.py`.

### Adding a diagnostic rule

Add the evidence collection to `run_diagnostics()` (with a timeout) and the rule to
`classify()`. Each rule must cite its evidence and state a confidence. Add a scenario test in
`tests/python/test_diagnostics.py`.

## Local API (`wifi-monitor serve`)

| Method | Path | Returns |
|---|---|---|
| GET | `/api/v1/status` | Wi-Fi interfaces + network (gateway, local IP) + version/mode |
| GET | `/api/v1/wifi/interfaces` | `ProviderResult` with interfaces |
| GET | `/api/v1/wifi/signal` | Signal `Measurement` of the connected interface |
| GET | `/api/v1/wifi/access-points` | `ProviderResult` with access points (cached 10 s) |
| GET | `/api/v1/network` | Gateway / local IP |
| GET | `/api/v1/capabilities` | Static capability description |
| GET | `/api/v1/diagnostics` | Last diagnostics report (404 if none) |
| POST | `/api/v1/diagnostics` | Run diagnostics (needs header `X-WiFi-Monitor: 1`; one run at a time) |

Every `ProviderResult` JSON object has `mode`, `source`, `is_simulated`, `timestamp`,
`error`, `hint`, `data`. Security properties are listed in [SECURITY.md](../SECURITY.md).

## Dashboard (`src/`)

Vanilla JS, no build step, IIFE modules loaded in order:

| File | Role |
|---|---|
| `utils.js` | `SignalUtils`, `escapeHTML`, CSV, toasts, demo random helpers |
| `api.js` | `DataSource.detect()` → `live` / `server-demo` / `browser-demo` |
| `charts.js` | Chart.js wrappers (null values render as gaps) |
| `scanner.js` | `poll()` snapshot with provenance; access point scan; channel map |
| `devices.js` | Simulated devices in demo modes; "not available" in live mode |
| `speedtest.js` | Real browser HTTP latency/jitter; simulated throughput in demo modes only |
| `logger.js` | History/alerts in `localStorage` (with `mode`), CSV/JSON export |
| `app.js` | Controller: polling (no overlapping requests), rendering, diagnostics card |

All dynamic text is inserted with `textContent` or `escapeHTML()`; SSIDs are attacker-controlled.

## Testing

- `tests/python/` — pytest; OS output fixtures (`fixtures.py`) cover Windows (incl. German
  and Location-denied output), NetworkManager, `iw`, macOS JSON, routing tables and ping in
  several locales. Diagnostics scenarios use fake probes. Server tests use a real socket.
- `tests/unit.test.js` — loads the shipped `src/js` files (Node `vm`) and includes XSS
  regression tests.

No test needs Wi-Fi hardware or network access.
