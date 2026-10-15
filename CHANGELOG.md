# Changelog

All notable changes to Internet Monitor are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — 1.3.0

**Renamed from WiFi Monitor to Internet Monitor.** The command is now `internet-monitor` and the Python
package `internet_monitor`. `wifi-monitor`, `cli/wifi-monitor.py`, `WIFI_MONITOR_*` environment variables
and an existing `wifi-monitor` config folder keep working. Prometheus metrics are now `internet_monitor_*`,
the API header is `X-Internet-Monitor` and MQTT topics default to `internet_monitor/…`.

Focus: monitor internet of any kind, and show which apps use it.

### Added
- **Any connection type**: live download/upload per interface (Wi-Fi, Ethernet, VPN, mobile, virtual),
  primary-interface detection; throughput recorded in history, stats, CSV, Prometheus, MQTT and hub.
- **Per-app usage** (`apps`, Apps & Traffic page): bytes downloaded/uploaded per app over any period and
  per-app rates now — Windows via the system usage records (no admin), Linux via `ss`, macOS via `nettop`.
- **Live connections per app** (`connections`): remote addresses, services, states, listening ports.
- **Wi-Fi adapter health** on Windows: broken driver (Device Manager code), disabled adapter, Wi-Fi off.
- Diagnostics report network activity and the busiest apps, and link heavy traffic to latency problems.
- Dashboard: Network Activity card with live chart; new Apps & Traffic page; status shows the active
  connection of any type.

### Fixed (from testing on real Wi-Fi hardware)
- Windows: request a fresh Wi-Fi scan before listing access points; some USB adapters do not
  scan in the background, so the cached list held only the connected network.
- Channel advice no longer suggests moving onto a channel used by access points that are probably
  your own (same router brand); a 1/6/11 layout across your access points is recognised.
- `security` confirms WPA2 is fine instead of saying nothing; healthy diagnostics include the Wi-Fi link.
- Dashboard fills the channel map automatically in live mode.

### Changed
- `psutil` is now a dependency.
- `status` exits 0 when online through any connection, even without Wi-Fi.

## [Unreleased] — 1.2.0

Focus: everything beyond the core, except a database and an MCP server (deliberately out of scope).

### Added
- **History & anomalies** (`serve`, `history`, `alerts`): background collector, in-memory history
  with retention, rolling stats/percentiles, baseline vs previous hour, explainable rules (sudden
  signal drop, sustained weak signal, latency spikes, router packet loss, slow DNS, disconnects,
  repeated disconnects), alert acknowledge/clear, roaming and network-change events, CSV/JSON export.
- **Throughput test** (`speedtest`, dashboard): real download/upload against Cloudflare with a data cap.
- **Channel analysis** (`channels`, scanner page): weighted neighbour scores and transparent
  recommendations; withheld for simulated data.
- **Wi-Fi generation** (Wi-Fi 4/5/6/6E/7) and channel width from OS evidence; MLO reported as unavailable.
- **Device discovery** (`devices`, devices page): passive neighbour table, opt-in bounded /24 sweep,
  known devices with friendly names, new-device alerts, randomized-MAC detection, local OUI lookup.
- **Security observations** (`security`): open/WEP/TKIP networks, router MAC change, ARP anomalies.
- **Signal survey** (`survey`, history page): record signal per location and list weak spots.
- **Explanations** (`ask`, dashboard): rule-based by default; optional AI via the Anthropic SDK
  (`claude-opus-5-5`, structured output, refusal fallbacks) or any OpenAI-compatible/local model,
  with redaction, prompt-injection defences, schema validation and preview.
- **Distributed monitoring**: `hub` with hashed, revocable, role-separated tokens and TLS; `agent`
  with identifier stripping and bounded queue; Prometheus `/metrics`; MQTT with Home Assistant discovery.
- Docs: AI, DISTRIBUTED, CONFIG; `.env.example`.

### Fixed
- TCP latency to a hostname re-resolved DNS on every sample, inflating latency and jitter.
- Opening the dashboard directly on `#history`/`#alerts` loaded before the data source was known.
- HTML validation: button types, accessible names for icon buttons, table header scopes, `rel="noopener"`.

## Unreleased — trustworthy core (PR #1)

Focus: trustworthy measurements. Every value now carries its provenance
(`live` / `estimated` / `simulated` / `unavailable`) and nothing is fabricated.

### Added
- `internet_monitor` Python package (standard library only; Rich optional) with per-OS providers:
  Windows `netsh` (multi-interface, `Rssi`, Location-permission and locale detection),
  Linux `nmcli` + `iw`, macOS `system_profiler` (replaces the removed `airport`).
- Connectivity troubleshooter (`internet-monitor diagnose`): link → router (ICMP + TCP fallback)
  → DNS → HTTPS (captive-portal detection) → TCP latency/jitter, with findings that state
  evidence, likely cause, next step and confidence.
- CLI subcommands `status`, `scan`, `diagnose`, `monitor`, `capabilities`, `serve`;
  `--json` output, `--demo` mode, exit codes. v1.0 flags still work.
- `internet-monitor serve`: loopback-only dashboard server and read-only `/api/v1` API
  (DNS-rebinding protection, no CORS, CSP, path-traversal protection).
- Dashboard: live data via the local API, demo-mode banner, Connectivity Check card,
  provenance column in history and exports, crowded-channel alert (AP count).
- pytest suite (OS output fixtures, diagnostics scenarios, CLI, server) and JS tests that load
  the shipped modules, including XSS regression tests.
- Docs: CAPABILITIES, INSTALLATION, TROUBLESHOOTING, PRIVACY, IMPLEMENTATION_PLAN.

### Fixed
- CLI silently showed simulated signal and the fabricated SSID `WiFi_Network` when no
  Wi-Fi reading was available; it now reports the reason.
- CLI `--export` always reported "no data" (it ran in a fresh process).
- CLI `--scan` printed a hard-coded fake network list; it now reads the OS scan list.
- Dashboard showed random IP, MAC and gateway as if real.
- Latency test substituted random numbers when requests failed; jitter was random.
- 5 GHz channel→frequency conversion was wrong (ch 36 showed 5.000 GHz instead of 5.180 GHz).
- SSIDs, device names and alert text were inserted as raw HTML (XSS once real SSIDs are shown).
- CSV export did not escape quotes and allowed spreadsheet formula injection.
- Signal charts grew without bound because they had no fixed height.
- CI could not pass (`npm ci` without a lockfile, ESLint without a config).

### Changed
- Download/upload "speed test" numbers were always random. They are now shown only in
  demo mode, labelled *simulated*; with live data throughput is reported as not measured.
- Device discovery was always simulated. Demo mode still shows labelled simulated devices;
  live mode states that the feature is not implemented yet.
- Dashboard history uses a new storage key; v1 history (no provenance) is discarded.
- Python 3.9+ required (was 3.8).

---

## [1.0.0] — 2025-01-01

### Added
- 🎉 Initial release
- Real-time signal dashboard with animated RSSI gauge
- Signal history chart with configurable time range (1 min – 1 hr)
- Network scanner: SSID, BSSID, band, channel, security, signal quality
- Channel heatmap with interference detection
- Device discovery with MAC vendor lookup
- Speed test: download, upload, latency, jitter with animated speedometer
- Smart alert engine: weak signal, new device, congestion, high latency rules
- Signal history export: CSV and JSON formats
- Dark / Light mode with system preference detection
- LocalStorage-based history persistence (up to 500 entries)
- Python CLI tool with rich terminal output
- Toast notification system
- Responsive layout for mobile, tablet, and desktop
- GitHub community files: CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates
- GitHub Actions CI workflow
- Unit test foundation

### Technical Details
- Zero runtime dependencies in production (Chart.js loaded via CDN)
- Modular JavaScript architecture (6 modules + main app controller)
- CSS custom properties design system with full dark/light theme support
- EventBus publish/subscribe for loose module coupling

---

[Unreleased]: https://github.com/qmmughal/internet-monitor/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/qmmughal/internet-monitor/releases/tag/v1.0.0
