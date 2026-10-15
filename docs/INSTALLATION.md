# Installation

## Requirements

- Python 3.9 or newer
- [psutil](https://pypi.org/project/psutil/) — installed automatically by `pip` (interface counters,
  per-app connections)
- Optional: [Rich](https://pypi.org/project/rich/) for formatted terminal output (`[rich]` extra)
- Optional: `[ai]` (Claude explanations, Python 3.10+) and `[mqtt]` (Home Assistant) extras
- Optional: Node.js 18+ only to run the dashboard's JavaScript tests

No administrator/root rights are needed. Platform tools are normally pre-installed:

| Platform | Tools used |
|---|---|
| Windows 10/11 | `netsh`, `route`, `ping`, `arp`, PowerShell (per-app usage, adapter health) |
| Linux | NetworkManager (`nmcli`), `ping`, `ip`, `ss`; optional `iw` for live dBm |
| macOS | `system_profiler`, `route`, `ping`, `arp`, `nettop` |

## Windows (PowerShell)

```powershell
git clone https://github.com/qmmughal/internet-monitor.git
cd internet-monitor
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install ".[rich]"
internet-monitor --version
```

If `Activate.ps1` is blocked ("running scripts is disabled on this system"), allow local scripts
for your user once, then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Each new terminal needs `cd` into the folder and `.\.venv\Scripts\Activate.ps1` before
`internet-monitor` is available.

**Windows 11 24H2 and later:** Wi-Fi details require Location access — **Settings → Privacy &
security → Location**, turn on *Location services* and *Let desktop apps access your location*.

### Run it from any folder (optional)

Install into your user Python instead of (or as well as) the virtual environment:

```powershell
pip install --user "C:\path\to\internet-monitor[rich]"
```

If `internet-monitor` is then "not recognized", open a new terminal; if it still is not found,
add the folder printed by `python -c "import sysconfig; print(sysconfig.get_path('scripts', 'nt_user'))"`
to your PATH.

## Linux / macOS

```bash
git clone https://github.com/qmmughal/internet-monitor.git
cd internet-monitor
python3 -m venv .venv
source .venv/bin/activate
pip install ".[rich]"
internet-monitor --version
```

Linux, if missing: `sudo apt install network-manager iw iproute2` (Debian/Ubuntu).
macOS 14+: give your terminal app Location permission to see network names.

## Without installing

From the repository folder (with Python and psutil available):

```bash
python cli/internet-monitor.py status
python -m internet_monitor status
```

## First run

```bash
internet-monitor capabilities   # what your platform can report
internet-monitor status         # current connection
internet-monitor diagnose       # troubleshooter
internet-monitor serve          # dashboard at http://127.0.0.1:8765
```

Then see [USAGE.md](USAGE.md). If something reports *unavailable*, the message and hint explain
why — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Update

```bash
cd internet-monitor
git pull
pip install ".[rich]"     # picks up new dependencies, if any
```

## Upgrading from WiFi Monitor

The project was renamed. The `wifi-monitor` command, `cli/wifi-monitor.py`, `WIFI_MONITOR_*`
environment variables and an existing `wifi-monitor` settings folder keep working. A local clone
in a folder called `wifi-monitor` works as-is; `git remote -v` should point to
`https://github.com/qmmughal/internet-monitor.git` (GitHub also redirects the old address).

## Dashboard only (demo)

Opening `src/index.html` directly, or `npm run start:demo`, shows the dashboard with simulated
data. Use `internet-monitor serve` for real measurements.

## Uninstall

```bash
pip uninstall internet-monitor
```

Then delete the folder. Optional settings live in `%APPDATA%\internet-monitor` (Windows) or
`~/.config/internet-monitor` — delete that folder to remove known-device names, survey points and
config. History collected by `serve` is never written to disk.
