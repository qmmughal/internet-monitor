# Changelog

All notable changes to WiFi Monitor are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

Focus: trustworthy measurements. Every value now carries its provenance
(`live` / `estimated` / `simulated` / `unavailable`) and nothing is fabricated.

### Added
- `wifi_monitor` Python package (standard library only; Rich optional) with per-OS providers:
  Windows `netsh` (multi-interface, `Rssi`, Location-permission and locale detection),
  Linux `nmcli` + `iw`, macOS `system_profiler` (replaces the removed `airport`).
- Connectivity troubleshooter (`wifi-monitor diagnose`): link → router (ICMP + TCP fallback)
  → DNS → HTTPS (captive-portal detection) → TCP latency/jitter, with findings that state
  evidence, likely cause, next step and confidence.
- CLI subcommands `status`, `scan`, `diagnose`, `monitor`, `capabilities`, `serve`;
  `--json` output, `--demo` mode, exit codes. v1.0 flags still work.
- `wifi-monitor serve`: loopback-only dashboard server and read-only `/api/v1` API
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

[Unreleased]: https://github.com/qmmughal/wifi-monitor/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/qmmughal/wifi-monitor/releases/tag/v1.0.0
