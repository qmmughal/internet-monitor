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
| History with rolling stats, percentiles and baseline comparison (in memory, CSV/JSON export) | ✅ `serve`, `history` |
| Explainable anomaly alerts: signal drop, sustained weak signal, latency spikes, slow DNS, packet loss, repeated disconnects | ✅ `serve`, `alerts` |
| Roaming (BSSID change) and disconnect tracking | ✅ |
| Download/upload throughput test (Cloudflare, data-capped) | ✅ `speedtest` |
| Channel congestion analysis and transparent channel recommendations | ✅ `channels` |
| Wi-Fi generation (4/5/6/6E/7) and channel width from OS evidence | ✅ where the OS reports it |
| Device discovery (passive neighbour table; opt-in bounded sweep), known devices, new-device alerts | ✅ `devices` |
| Security observations (open/WEP/TKIP networks, router MAC change) | ✅ `security` |
| Guided signal survey to find weak spots | ✅ `survey` |
| Plain-language explanations — rule-based, or AI (Claude or any OpenAI-compatible/local model), off by default | ✅ `ask` |
| Multi-machine hub + agents with token auth, Prometheus metrics, MQTT / Home Assistant | ✅ `hub`, `agent`, `/metrics`, `serve --mqtt` |
| Persistent database, MCP server | ✖ Not planned in this release (history is in memory by design) |

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
wifi-monitor status              # current Wi-Fi link, generation, gateway and local IP
wifi-monitor scan                # nearby access points
wifi-monitor diagnose            # connectivity troubleshooter
wifi-monitor speedtest           # download/upload throughput (uses up to 50 MB)
wifi-monitor channels            # channel congestion + recommendation
wifi-monitor devices [--probe]   # devices on your network; --name MAC "TV" to label one
wifi-monitor security            # security observations for this connection
wifi-monitor survey add Kitchen  # record signal here; `survey report` lists weak spots
wifi-monitor ask "why are my calls unstable?"   # plain-language explanation
wifi-monitor monitor -o log.csv  # live signal monitor, saved to CSV (or .json)
wifi-monitor capabilities        # what this platform can measure

wifi-monitor serve [--demo] [--mqtt]   # dashboard + local API + background history
wifi-monitor history | alerts          # read history/alerts from a running `serve`
wifi-monitor hub serve | hub token …   # central hub for other machines
wifi-monitor agent --hub https://…     # report this machine to a hub

# --json for machine-readable output; --demo for clearly labelled simulated data
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

- Monitoring data stays on your machine; history lives in the `serve` process's memory. No account, no telemetry.
- **Network requests the tool makes:** diagnostics and the background collector contact public test endpoints
  (`www.google.com`, `cp.cloudflare.com`, `www.microsoft.com`, `www.cloudflare.com`, `1.1.1.1`, `8.8.8.8`);
  `speedtest` transfers data with `speed.cloudflare.com`. The dashboard loads Chart.js and fonts from public CDNs.
- **Off by default:** AI explanations (send a *redacted* summary to the provider you configure), the hub/agents and MQTT.
- `wifi-monitor serve` binds to `127.0.0.1` only, rejects foreign `Host` headers (DNS rebinding), sends no CORS headers,
  and requires a custom header on every POST. No request value ever reaches an OS command, and nothing changes your
  router, DNS, firewall or OS settings.

See [docs/PRIVACY.md](docs/PRIVACY.md), [docs/AI.md](docs/AI.md), [docs/DISTRIBUTED.md](docs/DISTRIBUTED.md) and
[SECURITY.md](SECURITY.md). Settings: [docs/CONFIG.md](docs/CONFIG.md).

## 🏗️ Architecture

```text
wifi_monitor/            Python package (standard library only; rich/anthropic/paho-mqtt optional)
  models.py              Measurement / provenance data model
  providers/             windows.py · linux.py · macos.py · demo.py
  netinfo.py, probes.py  gateway/local IP; bounded ping / TCP / DNS / HTTPS probes
  diagnostics.py         staged troubleshooter + explainable rules
  history.py             in-memory history, stats, anomaly rules, alerts, roaming events
  collector.py           background sampler used by serve and agent
  channels.py            channel analysis and recommendations
  standards.py           Wi-Fi generation / width reporting
  devices.py             neighbour-table discovery, known devices, security observations
  speedtest.py, survey.py, ai.py, metrics.py, hub.py, mqtt.py
  cli.py, commands.py    command-line interface
  server.py              local dashboard server + /api/v1
src/                     dashboard (vanilla JS, no build step)
  js/api.js, js/live.js  data-source detection and API-backed features
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

Completed work and remaining items are tracked in [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md).

## 📄 License

MIT © 2025 WiFi Monitor Contributors. See [`LICENSE`](LICENSE).
