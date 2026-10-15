<p align="center">
  <img src="src/assets/logo.svg" alt="Internet Monitor Logo" width="80" />
</p>

<h1 align="center">📡 Internet Monitor</h1>

<p align="center">
  <strong>Local-first internet monitoring — any connection, every app, Wi-Fi included — with honest data.</strong>
</p>

<p align="center">
  <a href="https://github.com/qmmughal/internet-monitor/stargazers"><img src="https://img.shields.io/github/stars/qmmughal/internet-monitor?style=flat-square&color=38bdf8" alt="Stars"/></a>
  <a href="https://github.com/qmmughal/internet-monitor/issues"><img src="https://img.shields.io/github/issues/qmmughal/internet-monitor?style=flat-square&color=f59e0b" alt="Issues"/></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License"/></a>
</p>

---

Internet Monitor watches your internet connection of any kind — Wi-Fi, Ethernet, VPN or mobile data —
shows which apps are downloading and uploading, reads your Wi-Fi link from the operating system, runs a step-by-step
connectivity check (link → router → DNS → HTTPS → latency), and explains what it finds
with the evidence behind each conclusion. It runs on your machine; nothing is uploaded.

**Every value says where it came from.** Measurements are tagged `live` (read from the OS),
`estimated` (derived, e.g. dBm from Windows' signal %), `simulated` (demo mode only) or
`unavailable` (with the reason). Internet Monitor never fills a gap with made-up numbers.

## ✨ What it does today

| Feature | Status |
|---|---|
| Live download/upload rates for **any connection type** (Wi-Fi, Ethernet, VPN, mobile, virtual) | ✅ `traffic`, dashboard |
| **Which apps use the most internet** — downloaded/uploaded per app (last 5 min … 7 days, or right now) | ✅ `apps` — Windows without admin, Linux (`ss`), macOS (`nettop`) |
| **Live connections per app** — who each app is talking to right now, listening ports | ✅ `connections` |
| Wi-Fi adapter health (broken driver, disabled adapter, Wi-Fi switched off) | ✅ Windows |
| Connected Wi-Fi details: SSID, BSSID, signal, band/channel/frequency, radio, security, link rate | ✅ Windows (`netsh`), Linux (`nmcli` + `iw`); macOS implemented, not yet verified on hardware |
| Nearby access point list | ✅ From the OS scan list (see [capabilities](docs/CAPABILITIES.md)) |
| Connectivity troubleshooter with findings, evidence, likely cause, next step, confidence | ✅ CLI and dashboard |
| Default gateway and local IP | ✅ Windows, Linux, macOS |
| Dashboard with live data via a local, loopback-only API | ✅ `internet-monitor serve` |
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

Requires **Python 3.9+**. `pip install` also installs [psutil](https://github.com/giampaolo/psutil) (interface
counters and per-app connections); [Rich](https://github.com/Textualize/rich) is optional for nicer terminal output.
No administrator rights are needed.

**Windows (PowerShell)**

```powershell
git clone https://github.com/qmmughal/internet-monitor.git
cd internet-monitor
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install ".[rich]"
internet-monitor serve               # then open http://127.0.0.1:8765
```

**Linux / macOS**

```bash
git clone https://github.com/qmmughal/internet-monitor.git
cd internet-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install ".[rich]"
internet-monitor serve               # then open http://127.0.0.1:8765
```

Next time, just `cd` into the folder, activate the environment and run `internet-monitor serve`.
**Everyday tasks — "why is it slow?", "which app is using my internet?", "where is my Wi-Fi weak?" —
are in the [usage guide](docs/USAGE.md).** Full install options: [INSTALLATION.md](docs/INSTALLATION.md).

### Troubleshoot your connection

```console
$ internet-monitor diagnose
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
internet-monitor serve            # http://127.0.0.1:8765
```

Opening `src/index.html` directly (or via any static server) runs the dashboard in **demo mode**:
browsers cannot read Wi-Fi hardware, so all values are simulated and a banner says so.

### All commands

```bash
internet-monitor status              # active connection (any type), Wi-Fi link, gateway and local IP
internet-monitor traffic -n 10       # live download/upload per interface
internet-monitor apps --window 1h    # which apps used the most data (or --live for right now)
internet-monitor connections         # which apps are connected to where, right now
internet-monitor scan                # nearby access points
internet-monitor diagnose            # connectivity troubleshooter
internet-monitor speedtest           # download/upload throughput (uses up to 50 MB)
internet-monitor channels            # channel congestion + recommendation
internet-monitor devices [--probe]   # devices on your network; --name MAC "TV" to label one
internet-monitor security            # security observations for this connection
internet-monitor survey add Kitchen  # record signal here; `survey report` lists weak spots
internet-monitor ask "why are my calls unstable?"   # plain-language explanation
internet-monitor monitor -o log.csv  # live signal monitor, saved to CSV (or .json)
internet-monitor capabilities        # what this platform can measure

internet-monitor serve [--demo] [--mqtt]   # dashboard + local API + background history
internet-monitor history | alerts          # read history/alerts from a running `serve`
internet-monitor hub serve | hub token …   # central hub for other machines
internet-monitor agent --hub https://…     # report this machine to a hub

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

**Tested on real hardware:** Windows 11 over Ethernet and over Wi-Fi (Realtek USB adapter, 2.4 GHz),
including a failed internal adapter (reported as Device Manager code 43). Linux and macOS are covered
by CI with captured command output but have not yet been run on real hardware.

## 🔒 Privacy and security

- Monitoring data stays on your machine; history lives in the `serve` process's memory. No account, no telemetry.
- **Network requests the tool makes:** diagnostics and the background collector contact public test endpoints
  (`www.google.com`, `cp.cloudflare.com`, `www.microsoft.com`, `www.cloudflare.com`, `1.1.1.1`, `8.8.8.8`);
  `speedtest` transfers data with `speed.cloudflare.com`. The dashboard loads Chart.js and fonts from public CDNs.
- **Off by default:** AI explanations (send a *redacted* summary to the provider you configure), the hub/agents and MQTT.
- `internet-monitor serve` binds to `127.0.0.1` only, rejects foreign `Host` headers (DNS rebinding), sends no CORS headers,
  and requires a custom header on every POST. No request value ever reaches an OS command, and nothing changes your
  router, DNS, firewall or OS settings.

See [docs/PRIVACY.md](docs/PRIVACY.md), [docs/AI.md](docs/AI.md), [docs/DISTRIBUTED.md](docs/DISTRIBUTED.md) and
[SECURITY.md](SECURITY.md). Settings: [docs/CONFIG.md](docs/CONFIG.md).

## 🏗️ Architecture

```text
internet_monitor/            Python package (standard library only; rich/anthropic/paho-mqtt optional)
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
cli/internet-monitor.py      backwards-compatible entry point
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

MIT © 2025 Internet Monitor Contributors. See [`LICENSE`](LICENSE).
