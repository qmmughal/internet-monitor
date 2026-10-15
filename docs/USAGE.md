# Using Internet Monitor

A practical guide for everyday use. Install it first ([INSTALLATION.md](INSTALLATION.md)).

## Start it

**Windows (PowerShell)**

```powershell
cd path\to\internet-monitor
.\.venv\Scripts\Activate.ps1
internet-monitor serve
```

**Linux / macOS**

```bash
cd path/to/internet-monitor
source .venv/bin/activate
internet-monitor serve
```

Open **http://127.0.0.1:8765** in your browser. Keep the terminal open while you use it and
press **Ctrl+C** to stop. While it runs it samples your connection every 10 seconds to build
history and alerts.

> If you installed it with `pip install --user …` (see INSTALLATION.md) you can skip the `cd`
> and activate steps and run `internet-monitor` from any terminal.

## The dashboard

| Page | What you see |
|---|---|
| **Dashboard** | Active connection (Wi-Fi, Ethernet, VPN…), Wi-Fi signal and gauge, live download/upload chart, the busiest apps, and **Run check** — a step-by-step connectivity test with an explanation |
| **Network Scanner** | Nearby Wi-Fi networks and a channel recommendation |
| **Apps & Traffic** | Which apps used the most data (right now, 5 min … 7 days), live rate per network interface, and which apps are connected to where |
| **Devices** | Devices your computer has seen on the local network; rename them; security observations |
| **Speed Test** | Download/upload speed, latency and jitter |
| **History** | Signal, router and internet latency, DNS time and throughput over time, roaming and disconnect events, CSV/JSON export, and the signal survey |
| **Alerts** | Problems detected automatically (weak signal, latency spikes, slow DNS, disconnects, new devices), with the evidence |

Every value says where it came from: *measured*, *estimated* (for example dBm derived from a
percentage), or *simulated* (demo mode only). Missing data is shown as missing, never invented.

## Common tasks

### "Why is my internet slow?"

```powershell
internet-monitor diagnose
```

It tests your connection, router, DNS, websites and latency, and tells you what it found, why,
and what to try next — including whether another app was using the connection heavily. Or use
**Run check** on the dashboard. To ask in your own words:

```powershell
internet-monitor ask "why are my video calls unstable?"
```

(Rule-based answers by default; AI explanations are optional — see [AI.md](AI.md).)

### "Which app is using my internet?"

```powershell
internet-monitor apps --window 1h       # most data in the last hour (also 5m, 1d, 7d)
internet-monitor apps --live            # what is downloading/uploading right now (~60 s)
internet-monitor connections            # which apps are connected to where, right now
internet-monitor connections --app chrome
```

On Windows the per-app numbers come from Windows' own data-usage records and appear 30–60
seconds after the traffic. The live total for the whole connection is instant:

```powershell
internet-monitor traffic -n 10          # ten one-second readings per interface
```

### "Is my Wi-Fi signal good, and where is it weak?"

```powershell
internet-monitor status                 # signal, band, channel, Wi-Fi generation, link rate
internet-monitor monitor                # live signal meter (Ctrl+C to stop)
internet-monitor survey add "Kitchen"   # walk to a spot, record it; repeat per room
internet-monitor survey report          # lists weak spots and what to do about them
```

Rough guide: −50 dBm or better excellent, −60 good, −70 fair, below −75 weak.

### "Which Wi-Fi channel should my router use?"

```powershell
internet-monitor channels
```

It scores each channel by how many neighbouring networks overlap it and how strong they are.
Networks that use the same router brand as yours are treated as probably your own, and their
channels are never suggested. It only recommends — change the channel in your router's settings.

### "How fast is my connection?"

```powershell
internet-monitor speedtest              # uses up to ~50 MB of data
```

### "What is on my network?"

```powershell
internet-monitor devices                         # passive: sends nothing
internet-monitor devices --name 70:f1:96:00:00:01 "Router"
internet-monitor devices --probe                 # pings your local network first (opt-in)
internet-monitor security
```

Only use `--probe` on networks you own or are allowed to scan.

### Keep a record

History lives in the running `serve` process's memory and is lost when it stops. Before
stopping, export it from **History → Export CSV/JSON**, or:

```powershell
internet-monitor history --export csv -o my-history.csv
```

For a simple log without the dashboard:

```powershell
internet-monitor monitor -o signal-log.csv
```

## Tips

- Add `--json` to most commands for machine-readable output.
- `internet-monitor --help` and `internet-monitor <command> --help` list every option.
- Exit codes: `0` ok · `1` a problem was found · `2` usage error · `3` data unavailable here.
- Nothing ever changes your router, Wi-Fi, DNS, firewall or Windows settings.
- Settings (alert thresholds, AI, MQTT) are optional: [CONFIG.md](CONFIG.md).
- Monitoring several computers, Prometheus/Grafana, Home Assistant: [DISTRIBUTED.md](DISTRIBUTED.md).
- Something not working? [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
