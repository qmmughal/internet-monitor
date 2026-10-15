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
| `traffic.py` | Per-interface byte counters → rates for any connection type; primary interface; type inference |
| `apps.py` | Per-app bytes (Windows usage records via WinRT, Linux `ss`, macOS `nettop`), live rates, connections per app |
| `pwsh.py` | Runs fixed, package-internal PowerShell scripts with `-EncodedCommand` and parses JSON |
| `history.py` | Ring buffer of `Sample`s, stats/percentiles/baseline, anomaly rules, `AlertManager`, roaming/disconnect events |
| `collector.py` | Background sampler (Wi-Fi every cycle; router ping, TCP and DNS every N cycles) |
| `channels.py` | Weighted neighbour score per channel, recommendations with stated assumptions |
| `standards.py` | Wi-Fi generation from the reported PHY, 6 GHz, channel width; MLO reported as unavailable |
| `devices.py` | ARP/neighbour table parsing, OUI lookup from local files, known devices, opt-in /24 sweep, security observations |
| `speedtest.py` | Cloudflare download/upload with data and time caps |
| `survey.py` | Signal survey points (JSON) and weak-spot report |
| `ai.py` | Redaction, prompt construction, schema validation, Anthropic SDK / OpenAI-compatible adapters, rule-based fallback |
| `metrics.py` | Prometheus text exposition |
| `hub.py` | Token store (hashed), hub HTTP server, agent reporter |
| `mqtt.py` | MQTT publisher with Home Assistant discovery |
| `config.py` | `config.json` defaults/merge, atomic JSON state files |
| `cli.py`, `commands.py` | Subcommands, `--json`, exit codes, optional Rich |
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
| POST | `/api/v1/diagnostics` | Run diagnostics (one run at a time) |
| GET | `/api/v1/wifi/standard` | Wi-Fi generation, band, width, MLO status, evidence |
| GET | `/api/v1/channels` | Channel analysis and recommendations |
| GET | `/api/v1/traffic` | Live rates per interface (also included in `/api/v1/status`) |
| GET | `/api/v1/apps?window=` | Bytes per app over a period (60 s – 30 days) |
| GET | `/api/v1/apps/live` | Per-app rates now |
| GET | `/api/v1/connections` | Open connections grouped by app |
| GET | `/api/v1/history?window=&limit=` | Samples (in memory) |
| GET | `/api/v1/history/stats?window=` | Stats, baseline, thresholds, collector status |
| GET | `/api/v1/history/export?format=csv\|json` | Download |
| POST | `/api/v1/history/clear` | Delete history and alerts |
| GET | `/api/v1/events?window=` | Roaming / network change / disconnect / reconnect |
| GET | `/api/v1/alerts?active=1` | Alerts |
| POST | `/api/v1/alerts/ack` `{id}`, `/api/v1/alerts/clear` | Manage alerts |
| GET / POST | `/api/v1/devices`, `/api/v1/devices/scan` `{probe}` | Last / new device scan |
| POST | `/api/v1/devices/name` `{mac, name}` | Friendly name |
| GET | `/api/v1/security` | Security observations |
| GET / POST | `/api/v1/speedtest` `{max_mb}` | Last / new throughput test |
| GET / POST | `/api/v1/survey`, `/api/v1/survey/points` `{label, samples}`, `/api/v1/survey/clear` | Survey |
| GET | `/api/v1/ai/status` | Whether AI is enabled and where data would go |
| POST | `/api/v1/ai/ask`, `/api/v1/ai/preview` `{question}` | Explanation / exact payload preview |
| GET | `/metrics` | Prometheus |

All POSTs need the header `X-WiFi-Monitor: 1`, a loopback or absent `Origin`, and (when a body is
sent) `Content-Type: application/json` with at most 16 KB. Every `ProviderResult` JSON object has
`mode`, `source`, `is_simulated`, `timestamp`, `error`, `hint`, `data`. Security properties are
listed in [SECURITY.md](../SECURITY.md).

## Alerts and anomalies

History is a bounded in-memory ring buffer filled by the collector (default every 10 s,
latency probes every 3rd sample). After each sample `history.detect_anomalies()` evaluates
these rules; each result names the rule, the observed value and the baseline it was compared with.

| Rule | Fires when | Needs |
|---|---|---|
| `signal_drop` | Signal ≥ `signal_drop_db` below the median of the last ≤ 30 samples **on the same BSSID** | ≥ 6 prior samples |
| `weak_signal` | Below `weak_signal_dbm` for 3 consecutive samples | 3 samples |
| `gateway_ms_spike`, `internet_ms_spike` | ≥ `latency_spike_factor` × rolling median **and** ≥ `latency_min_ms` | ≥ 6 prior measurements |
| `gateway_loss` | Any ping loss to the router in the latest check | — |
| `dns_slow` | Last 3 DNS lookups over `dns_slow_ms` | 3 measurements |
| `disconnect` / `repeated_disconnects` | Connected → disconnected; ≥ `disconnects_per_hour` in an hour | — |
| `new_device` | A MAC not seen in earlier device scans (raised by device scans) | a baseline scan |

Alerts have a per-rule cooldown, can be acknowledged, and are marked `simulated` in demo mode.
Thresholds are configurable ([CONFIG.md](CONFIG.md)). Rules were chosen over a statistical/ML
model because they are explainable and need no training data; a model can be evaluated later
against collected history.

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
| `logger.js` | Browser-demo history/alerts in `localStorage` (with `mode`), CSV/JSON export |
| `live.js` | API-backed history, alerts, channels, devices, speed test, survey, explanations |
| `traffic.js` | Network activity card, Apps & Traffic page (interfaces, top apps, connections) |
| `app.js` | Controller: polling (no overlapping requests), rendering, diagnostics card |

All dynamic text is inserted with `textContent` or `escapeHTML()`; SSIDs are attacker-controlled.

## Testing

- `tests/python/` — pytest; OS output fixtures (`fixtures.py`) cover Windows (incl. German
  and Location-denied output), NetworkManager, `iw`, macOS JSON, routing tables and ping in
  several locales. Diagnostics scenarios use fake probes. Server tests use a real socket.
- `tests/unit.test.js` — loads the shipped `src/js` files (Node `vm`) and includes XSS
  regression tests.

No test needs Wi-Fi hardware or network access.
