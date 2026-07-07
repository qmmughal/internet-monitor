# Changelog

All notable changes to WiFi Monitor are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Planned
- Electron desktop app wrapper
- Python FastAPI backend for native WiFi system calls
- 6 GHz band channel recommendation
- WebSocket live multi-tab updates

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
