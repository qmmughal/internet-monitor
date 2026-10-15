# Implementation Plan & Audit

This file records the repository audit (Phase 0) and tracks implementation
progress so each work session can pick up where the last one stopped.

Guiding principle: **trustworthy measurements first, useful diagnostics second,
AI third, integrations and scale afterwards.**

---

## Phase 0 — Audit of v1.0.0 (baseline commit `31fb6b1`)

### Architecture at baseline

- `src/` — zero-build browser dashboard (IIFE modules, Chart.js from CDN).
  Has no connection to native data. Everything is generated in the browser.
- `cli/wifi-monitor.py` — single-file Rich CLI. Calls `netsh` / `nmcli` /
  `airport` for signal and SSID, and silently falls back to random data.
- `tests/unit.test.js` — tests *copies* of helper functions pasted into the
  test file, not the shipped `src/js/utils.js`.
- No Python tests, no Python package, no backend.

### Feature inventory

| Feature | Where | Actual status at baseline |
|---|---|---|
| Live signal gauge (dashboard) | `scanner.js#getLiveSignal` | **Simulated**: Gaussian drift around a random value |
| Connected network info (dashboard) | `app.js#updateConnectionInfo` | **Simulated**: random SSID; IP, MAC and gateway are `Sim.ip()`/`Sim.mac()`/hard-coded `192.168.1.1` |
| Network scanner (dashboard) | `scanner.js#scan` | **Simulated**: fixed SSID list with random BSSIDs and signal |
| Channel map | `scanner.js#renderChannelMap` | **Simulated** input; re-rendered at random (`Math.random() < 0.2`) |
| Device discovery | `devices.js#discover` | **Simulated**: random devices; described as "ARP scan" |
| New-device alerts | `devices.js` → `logger.js` | Fire for **fabricated** devices |
| Speed test latency | `speedtest.js#measureLatency` | Partly real (`fetch` timing to Cloudflare, `no-cors`), but on failure it **substitutes random values** |
| Speed test jitter | `speedtest.js#run` | **Simulated**: `Sim.int(1, ping*0.2)` |
| Download / upload | `speedtest.js` | **Simulated**: random target Mbps with an animated ramp |
| Signal history + CSV/JSON export | `logger.js` | Works, but records simulated values with no provenance |
| Alert rules | `logger.js#checkAlerts` | Weak-signal and latency work on (simulated) inputs; "congestion" rule has no implementation |
| Theme toggle | `app.js` | Works |
| CLI live monitor | `cli/wifi-monitor.py` | Real on Windows/Linux when Wi-Fi is present (percentage → dBm **estimate** shown as a measurement); otherwise **silent simulation** |
| CLI SSID | `get_native_ssid` | Falls back to fabricated `"WiFi_Network"` |
| CLI `--scan` | `run_scan` | **Simulated**: `FAKE_NETWORKS` with random dBm |
| CLI `--export` | `export_data` | **Broken**: runs in a fresh process with empty log, always prints "no data" |
| CLI `--devices` | docstring only | **Not implemented** |
| macOS signal | `airport -I` | **Broken on macOS 14.4+** (`airport` removed) |

### Defects and risks

Data integrity (P0)
1. CLI silently substitutes simulated signal when no native reading exists
   (reproduced on an Ethernet-only Windows machine: prints `-58 dBm`).
2. Dashboard shows random IP/MAC/gateway/SSID as if real; no demo labelling.
3. Latency test fabricates timings when `fetch` fails.
4. Percent-to-dBm conversion presented as a measured dBm value.
5. `channelToFreq` is wrong for 5 GHz (ch 36 → "5 GHz" instead of 5.180 GHz);
   `channelBand` cannot tell 6 GHz from 2.4/5 GHz by channel number alone.

Security (P0)
6. HTML built by string interpolation (`innerHTML`) with SSIDs, device names,
   alert text and toast messages. Harmless while data is simulated, but an
   XSS sink as soon as real SSIDs (attacker-controlled broadcast names) arrive.
7. Windows `netsh` parsing assumes English labels; no locale detection.
8. Bare `except Exception: pass` hides every failure, including permission
   errors (e.g. Windows 11 24H2 requires Location permission for `netsh wlan`).

Engineering (P1)
9. CI uses `npm ci` without a `package-lock.json` and runs ESLint with no
   config, so the test/lint/validate jobs cannot pass as written.
10. JS unit tests do not exercise shipped code.
11. No Python tests; CLI parsing untested.
12. CLI `--export` broken; `--signal` identical to default.

### Dependencies

- Dashboard: Chart.js 4.4.0 (CDN). No npm runtime dependencies.
- CLI: `rich` (required at baseline; now optional). Python ≥ 3.9.
- Native tools: `netsh` (Windows), `nmcli`/`iw` (Linux),
  `system_profiler` (macOS). `ping` for gateway checks.

---

## Prioritized backlog

Legend: ✅ done · 🔄 in progress · ⬜ not started

### P0 — correctness, security, data integrity
- ✅ Python package `wifi_monitor/` with a provenance-aware data model
  (`live` / `estimated` / `simulated` / `unavailable`).
- ✅ Safe subprocess runner: argument lists only, no shell, timeouts,
  bounded output, structured errors.
- ✅ Windows provider (`netsh`): multi-interface parsing, Location-permission
  and non-English-locale detection, `Rssi` field when present, otherwise
  percentage → dBm marked `estimated`.
- ✅ Linux provider (`nmcli`, optional `iw` for real dBm).
- ✅ macOS provider (`system_profiler -json`, legacy `airport` if present). *Untested on real hardware.*
- ✅ No silent simulation: demo data only with explicit `--demo`, labelled SIMULATED.
- ✅ Dashboard: escape all interpolated HTML; demo-mode banner; stop fabricating IP/MAC/gateway; stop fabricating latency; fix channel→frequency maths.

### P1 — core functionality and tests
- ✅ Network basics: default gateway + local IP per platform.
- ✅ Diagnostics engine: link → gateway → DNS → HTTPS → latency/jitter, rule-based findings with evidence and confidence.
- ✅ CLI subcommands `status`, `scan`, `diagnose`, `capabilities`, `monitor`, `--json`, exit codes; legacy flags kept.
- ✅ Local loopback API (`wifi-monitor serve`, stdlib only) serving the dashboard and `/api/v1/*`; dashboard switches to live mode when the API is present.
- ✅ pytest suite with fixtures for all parsers; JS tests load the real `utils.js`.
- 🔄 CI rewritten (no `npm ci` without lockfile; Python tests on Linux/Windows/macOS). **Not yet run on GitHub** — verify on first push.
- ✅ Docs: README, capability matrix, INSTALLATION, TROUBLESHOOTING, PRIVACY.

### P2 — historical intelligence (session 2; no database by request)
- ✖ SQLite history store — **out of scope by owner decision**; history is an in-memory ring buffer
  with configurable retention, clear and CSV/JSON export.
- ✅ Background collector in `serve` (configurable interval; latency probes every N samples).
- ✅ Rolling stats, percentiles, baseline vs previous hour, explainable anomaly rules.
- ✅ Alert management (cooldown, acknowledge, clear) backed by real observations; simulated flagged.
- ✅ Dashboard history/alerts from the API; diagnostics + explanation view.

### P3 — AI copilot and MCP
- ✅ Provider-independent interface: Anthropic SDK and OpenAI-compatible/local; off by default;
  redaction; prompt-injection defences; schema validation; rule-based fallback; payload preview.
- ✖ MCP server — **out of scope by owner decision**.

### P4 — advanced wireless
- ✅ Channel analysis and recommendations from real scans only.
- ✅ BSSID roaming / network-change / disconnect tracking.
- ✅ Wi-Fi generation (4/5/6/6E/7) and width where the OS exposes it; MLO reported unavailable.
- ✅ Device discovery (neighbour table; opt-in bounded sweep), known devices, new-device alerts.
- ✅ Security observations; guided signal survey.
- ✅ Real throughput test (Cloudflare).

### P5 — distributed monitoring
- ✅ Prometheus `/metrics` (local and hub).
- ✅ Hub + agents: hashed role-separated tokens, revocation, TLS-or-explicit-opt-out, rate/size limits.
- ✅ MQTT with Home Assistant discovery (optional dependency).

### Session 3 — any connection type and per-app usage
- ✅ Interface-agnostic traffic monitoring (psutil), throughput in history/metrics/MQTT/hub.
- ✅ Per-app bytes: Windows usage records (WinRT, no admin), Linux `ss`, macOS `nettop` (unverified).
- ✅ Per-app rates now and open connections per app; dashboard Apps & Traffic page.
- ✅ Windows Wi-Fi adapter health (found a real code-43 failure on the dev machine).

### Remaining / ideas
- ⬜ Real-time (sub-second) per-app rates on Windows would need ETW or TCP EStats, which require admin.
- ⬜ Per-app UDP attribution on Linux (would need eBPF/pcap and root).
- ⬜ Verify Windows parsing on a machine with a Wi-Fi adapter; Linux and macOS on real hardware.
- ⬜ Non-English `netsh` parsing (needs sample output per locale), or native WLAN API via ctypes.
- ⬜ Hub token expiry and mTLS; hub persistence.
- ⬜ Dashboard: per-section browser tests (current coverage is unit tests + API tests + screenshots).
- ⬜ Evaluate a statistical anomaly model once real history has been collected.

---

## Session log

### Session 1 (2026-10-15)
See CHANGELOG `[Unreleased]` for the list of changes. Verification
environment: Windows 11, Python 3.14, Node 22, **Ethernet only (no Wi-Fi
adapter)** — so Windows Wi-Fi parsing is verified with fixtures, and the live
path was verified to report `unavailable` honestly rather than fabricating data.

Verified in session 1:
- `pytest`: 134 passed. `npm test`: 46 passed. `node --check` on all `src/js` files.
- Real run on this machine: `status`/`scan` report "no Wi-Fi interface found" (exit 3) with the
  real gateway/local IP; `diagnose` → healthy with real router/DNS/HTTPS/TCP evidence.
- `serve`: status API, Host-header rejection (421), POST without header (403), path traversal
  (404), real diagnostics via POST. Dashboard screenshots checked in live and browser-demo mode.
- No-Rich fallback output checked.

Not verified (needs other hardware/OS): Windows with a Wi-Fi adapter, Linux, macOS,
non-English Windows beyond the "refuse to guess" path, the GitHub Actions workflow.

### Session 2 (2026-10-15)
Implemented P2–P5 except the database and MCP server (owner decision). Branch `feat/phases-2-5`.

Verified in session 2 on the same Ethernet-only Windows machine:
- `pytest`: 255 passed. `npm test`: 51 passed. `html-validate`: clean. `node --check` on all JS.
- Real runs: `devices` (3 devices from `arp -a`, baseline then no false "new"), `security`,
  `speedtest --max-mb 10` (11.6 / 16.5 Mbps), `ask` (rule-based), `channels` (honest unavailable),
  `survey` (demo, labelled simulated).
- `serve`: collector produced real router/internet/DNS samples; history/stats/export/alerts/devices/
  metrics/AI endpoints exercised; live dashboard history page screenshot checked.
- Hub + agent end to end on loopback: identifiers stripped, 401 without token and with the wrong role.
- Real `anthropic` SDK 1.14 accepted the request parameters (checked offline against a dead endpoint;
  no API call was made). paho-mqtt 2.x client construction path present; no broker was available.

Not verified: real Claude/OpenAI-compatible responses, a real MQTT broker / Home Assistant, the hub
over TLS, Wi-Fi-specific features on real Wi-Fi hardware, click-driven dashboard flows
(devices/speed test/survey/explain were verified through their API endpoints).

**Recommended next task:** run on a Wi-Fi laptop (Windows with Location enabled, and Linux) to
confirm parsers, roaming events and channel recommendations on real data.
