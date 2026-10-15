<p align="center">
  <img src="src/assets/logo.svg" alt="WiFi Monitor Logo" width="80" />
</p>

<h1 align="center">📡 WiFi Monitor</h1>

<p align="center">
  <strong>Local-first Wi-Fi monitoring and connectivity troubleshooting — with honest data.</strong>
</p>

<p align="center">
  <a href="https://github.com/qmmughal/wifi-monitor/stargazers"><img src="https://img.shields.io/github/stars/qmmughal/wifi-monitor?style=flat-square&color=38bdf8" alt="Stars"/></a>
  <a href="https://github.com/qmmughal/wifi-monitor/issues"><img src="https://img.shields.io/github/issues/qmmughal/wifi-monitor?style=flat-square&color=f59e0b" alt="Issues"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"/></a>
</p>

---

WiFi Monitor reads your Wi-Fi link from the operating system, runs a step-by-step
connectivity check (link → router → DNS → HTTPS → latency), and explains what it finds
with the evidence behind each conclusion. It runs on your machine; nothing is uploaded.

**Every value says where it came from.** Measurements are tagged `live` (read from the OS),
`estimated` (derived, e.g. dBm from Windows' signal %), `simulated` (demo mode only) or
`unavailable` (with the reason). WiFi Monitor never fills a gap with made-up numbers.

## ✨ What it does today

| Feature | Status |
|---|---|
| Connected Wi-Fi details: SSID, BSSID, signal, band/channel/frequency, radio, security, link rate | ✅ Windows (`netsh`), Linux (`nmcli` + `iw`); macOS implemented, not yet verified on hardware |
| Nearby access point list | ✅ From the OS scan list (see [capabilities](docs/CAPABILITIES.md)) |
| Connectivity troubleshooter with findings, evidence, likely cause, next step, confidence | ✅ CLI and dashboard |
| Default gateway and local IP | ✅ Windows, Linux, macOS |
| Dashboard with live data via a local, loopback-only API | ✅ `wifi-monitor serve` |
| Live signal monitor with CSV/JSON export (includes provenance columns) | ✅ CLI and dashboard |
| Alerts: weak signal, high latency, crowded channel (AP count) | ✅ Dashboard |
| Browser latency/jitter test (HTTP round-trip) | ✅ Real measurement |
| Download/upload throughput test | ⏳ Not implemented — shown only as *simulated* in demo mode |
| Device discovery on the LAN | ⏳ Not implemented — demo mode shows *simulated* devices |
| History database, anomaly detection, AI explanations, MCP server | 🗺️ [Roadmap](docs/IMPLEMENTATION_PLAN.md) |

## 🚀 Quick start

Requires **Python 3.9+**. No other dependencies are needed; [Rich](https://github.com/Textualize/rich) is optional for nicer terminal output.

```bash
git clone https://github.com/qmmughal/wifi-monitor.git
cd wifi-monitor
pip install ".[rich]"          # or just run python cli/wifi-monitor.py without installing
```

### Troubleshoot your connection

```console
$ wifi-monitor diagnose
Running connectivity diagnostics…

Overall: HEALTHY  (6916 ms)

OK       No connectivity problems detected  (confidence: high)
           evidence: Router answered in 1.0 ms median with 0.0% loss.
           evidence: 3/3 DNS lookups succeeded.
           evidence: 3/3 HTTPS endpoints responded.
           evidence: Best internet handshake latency 30.6 ms.
```

When something is wrong you get, for example, *"DNS resolution is failing — none of 3 hostnames
resolved, but direct TCP connections to 1.1.1.1 succeeded, so the internet path works"* with a
suggested next step. Nothing on your system is ever changed.

### Open the dashboard with real data

```bash
wifi-monitor serve            # http://127.0.0.1:8765
```

Opening `src/index.html` directly (or via any static server) runs the dashboard in **demo mode**:
browsers cannot read Wi-Fi hardware, so all values are simulated and a banner says so.

### All commands

```bash
wifi-monitor status              # current Wi-Fi link, gateway and local IP
wifi-monitor scan                # nearby access points
wifi-monitor diagnose            # connectivity troubleshooter
wifi-monitor monitor -o log.csv  # live signal monitor, saved to CSV (or .json)
wifi-monitor capabilities        # what this platform can measure
wifi-monitor serve [--demo]      # dashboard + read-only local API

# add --json to status/scan/diagnose/capabilities/monitor for machine-readable output
# add --demo to status/scan/monitor/capabilities for clearly labelled simulated data
```

Exit codes: `0` ok · `1` diagnostics found a problem · `2` usage error · `3` data unavailable on this system.
The v1.0 flags (`--scan`, `--signal`, `--export csv|json`) still work.

## 🌐 Platform support

| | Windows 10/11 | Linux (NetworkManager) | macOS 13+ |
|---|---|---|---|
| Signal (dBm) | live `Rssi` on newer builds, otherwise estimated from % | live with `iw`, otherwise estimated from % | live |
| SSID / BSSID | ✅ / ✅ | ✅ / ✅ | needs Location permission / ❌ |
| Access point list | ✅ (cached by Windows) | ✅ | ✅ (slow) |
| Diagnostics | ✅ | ✅ | ✅ |
| Notes | 24H2+ needs **Location** access; English `netsh` output only | — | not yet verified on hardware |

Full details: [docs/CAPABILITIES.md](docs/CAPABILITIES.md). Problems: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 🔒 Privacy and security

- Monitoring data stays on your machine. The dashboard keeps history only in your browser's `localStorage`.
- **Network requests the tool makes:** `diagnose` (and the dashboard's Connectivity Check) contacts public test endpoints
  (`www.google.com`, `cp.cloudflare.com`, `www.microsoft.com`, `1.1.1.1`, `8.8.8.8`). The browser latency test contacts
  `www.cloudflare.com`. The dashboard page loads Chart.js and fonts from public CDNs.
- `wifi-monitor serve` binds to `127.0.0.1` only, rejects foreign `Host` headers (DNS rebinding), sends no CORS headers,
  and exposes read-only endpoints. No request parameter ever reaches an OS command.

See [docs/PRIVACY.md](docs/PRIVACY.md) and [SECURITY.md](SECURITY.md).

## 🏗️ Architecture

```text
wifi_monitor/            Python package (standard library only)
  models.py              Measurement / provenance data model
  providers/             windows.py · linux.py · macos.py · demo.py
  netinfo.py             default gateway + local IP
  probes.py              bounded ping / TCP / DNS / HTTPS probes
  diagnostics.py         staged troubleshooter + explainable rules
  cli.py                 command-line interface
  server.py              local dashboard server + /api/v1 (read-only)
src/                     dashboard (vanilla JS, no build step)
  js/api.js              live-vs-demo data source detection
cli/wifi-monitor.py      backwards-compatible entry point
tests/python/            pytest suite with captured OS output fixtures
tests/unit.test.js       dashboard tests (loads the shipped JS)
```

More: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 🧪 Development

```bash
python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest -q          # Python tests (no Wi-Fi hardware needed)
npm test                     # dashboard tests (Node 18+, no npm install needed)
```

Contributions are welcome — please read [CONTRIBUTING.md](CONTRIBUTING.md). Sample OS output for
non-English locales or other hardware is especially useful for improving the parsers.

## 📋 Roadmap

Completed work and next steps are tracked in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).
Next up: persistent history with retention, explainable anomaly detection, then an optional
read-only MCP server and AI explanations (off by default).

## 📄 License

MIT © 2025 WiFi Monitor Contributors. See [`LICENSE`](LICENSE).
