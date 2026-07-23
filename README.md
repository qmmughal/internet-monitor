<p align="center">
  <img src="src/assets/logo.svg" alt="WiFi Monitor Logo" width="80" />
</p>

<h1 align="center">📡 WiFi Monitor</h1>

<p align="center">
  <strong>Open-source real-time WiFi network analyzer, signal monitor, and device discovery dashboard</strong>
</p>

<p align="center">
  <a href="https://github.com/qmmughal/wifi-monitor/stargazers"><img src="https://img.shields.io/github/stars/qmmughal/wifi-monitor?style=flat-square&color=38bdf8" alt="Stars"/></a>
  <a href="https://github.com/qmmughal/wifi-monitor/network/members"><img src="https://img.shields.io/github/forks/qmmughal/wifi-monitor?style=flat-square&color=818cf8" alt="Forks"/></a>
  <a href="https://github.com/qmmughal/wifi-monitor/issues"><img src="https://img.shields.io/github/issues/qmmughal/wifi-monitor?style=flat-square&color=f59e0b" alt="Issues"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"/></a>
  <a href="https://github.com/qmmughal/wifi-monitor/pulls"><img src="https://img.shields.io/github/issues-pr/qmmughal/wifi-monitor?style=flat-square" alt="PRs"/></a>
  <img src="https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square" alt="PRs Welcome"/>
</p>

---

> **Runs entirely in the browser, no native WiFi hardware access.** Signal/scanner/device data uses `navigator.connection` and simulated data where the browser sandbox restricts real hardware access — see [Browser API Support](#-browser-api-support) below. For real hardware scanning, see [Extending to Native](#️-extending-to-nativeelectronnode).

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Live Signal Dashboard** | Real-time RSSI/dBm meter with animated signal gauge |
| 🔍 **Network Scanner** | Enumerate nearby APs: SSID, BSSID, band, channel, security |
| 🖥️ **Device Discovery** | ARP-style scan with MAC vendor lookup |
| ⚡ **Speed Test** | Download, upload, latency, and jitter measurement |
| 📈 **Signal History** | Time-series chart with CSV/JSON export |
| 🔔 **Smart Alerts** | Configurable rules: weak signal, new device, congestion, high latency |
| 🌗 **Dark / Light Mode** | Toggleable theme with system preference detection |
| 🔌 **Zero Cloud** | 100% local — no data leaves your machine |
| 🖥️ **CLI Tool** | Python-based terminal monitor with rich output |

## 🚀 Quick Start

### Option 1: Open directly (no build step)

```bash
git clone https://github.com/qmmughal/wifi-monitor.git
cd wifi-monitor
# Open src/index.html in your browser
open src/index.html       # macOS
start src/index.html      # Windows
xdg-open src/index.html   # Linux
```

### Option 2: Local dev server (recommended)

```bash
cd wifi-monitor
npx serve src             # or: python3 -m http.server 8080 --directory src
# Visit http://localhost:8080
```

### Option 3: Python CLI

```bash
cd wifi-monitor/cli
pip install rich
python wifi-monitor.py
```

## 📸 Screenshots

Screenshots coming soon — open `src/index.html` in a browser to see the live Dashboard, Network Scanner, Device Discovery, and Speed Test views in the meantime.

## 🏗️ Architecture

```
wifi-monitor/
├── src/                    # Web dashboard (HTML/CSS/JS)
│   ├── index.html          # Main entry point
│   ├── css/style.css       # Design system
│   └── js/
│       ├── app.js          # Application controller
│       ├── scanner.js      # Network scanning engine
│       ├── charts.js       # Chart.js visualizations
│       ├── devices.js      # Device discovery
│       ├── speedtest.js    # Speed measurement
│       ├── logger.js       # History & alerts
│       └── utils.js        # Shared utilities
├── cli/
│   └── wifi-monitor.py     # Python CLI monitor
├── docs/                   # Developer documentation
└── tests/                  # Unit tests
```

## 🌐 Browser API Support

WiFi Monitor uses these web APIs where available and gracefully simulates data in environments where they are restricted:

| API | Purpose | Notes |
|---|---|---|
| `navigator.connection` | Connection type & speed hint | Chrome/Edge |
| `performance.now()` | Latency measurement | All modern browsers |
| `fetch()` | Download/upload simulation | All modern browsers |
| `localStorage` | History persistence | All modern browsers |
| `Notification API` | Desktop alerts | Requires permission |

## 🖥️ Extending to Native (Electron/Node)

The simulation layer in `scanner.js` and `devices.js` is designed to be replaced with native system calls. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for integration guides with:

- **Node.js**: `wireless-tools`, `node-wifi`
- **Electron**: IPC bridge to native WiFi APIs
- **Python backend**: FastAPI + `pywifi`/`scapy` REST API
- **Rust**: `wlan-rs` crate (high performance)

## 🤝 Contributing

We love contributions! Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a PR.

**Good first issues** are labeled [`good first issue`](https://github.com/qmmughal/wifi-monitor/labels/good%20first%20issue).

Quick contribution flow:

```bash
# Fork & clone
git clone https://github.com/YOUR_USERNAME/wifi-monitor.git
cd wifi-monitor

# Create a feature branch
git checkout -b feature/my-awesome-feature

# Make your changes, then commit
git add .
git commit -m "feat: add channel interference visualization"

# Push and open a PR
git push origin feature/my-awesome-feature
```

## 🧪 Tests

```bash
# Run unit tests (Node.js required)
node tests/unit.test.js

# Or with npm
npm test
```

## 📋 Roadmap

- [ ] Electron desktop app wrapper
- [ ] Python FastAPI backend for native WiFi access
- [ ] Historical trend analysis & anomaly detection
- [ ] 2.4/5/6 GHz channel recommendation engine
- [ ] Multi-AP roaming tracker
- [ ] Network topology visualization
- [ ] WebSocket live updates between tabs
- [ ] i18n / localization support

## 📄 License

MIT © 2025 WiFi Monitor Contributors. See [`LICENSE`](LICENSE) for details.

## ⭐ Support

If this project helps you, please consider:
- ⭐ **Starring** the repo
- 🐛 **Reporting bugs** via [GitHub Issues](https://github.com/qmmughal/wifi-monitor/issues)
- 💡 **Requesting features** via [GitHub Discussions](https://github.com/qmmughal/wifi-monitor/discussions)
- 📢 **Sharing** with your developer community

---

<p align="center">Built with ❤️ for the open-source developer community</p>
