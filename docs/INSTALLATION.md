# Installation

## Requirements

- Python 3.9 or newer (no third-party packages required)
- Optional: [Rich](https://pypi.org/project/rich/) for formatted terminal output
- Optional: Node.js 18+ only to run the dashboard's JavaScript tests

Platform tools (normally pre-installed):

| Platform | Tools used |
|---|---|
| Windows 10/11 | `netsh`, `route`, `ping` |
| Linux | NetworkManager (`nmcli`), `ping`; optional `iw` for live dBm |
| macOS | `system_profiler`, `route`, `ping` |

## Install

```bash
git clone https://github.com/qmmughal/wifi-monitor.git
cd wifi-monitor
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install ".[rich]"
wifi-monitor --version
```

Without installing, every command also works as `python cli/wifi-monitor.py <command>` or
`python -m wifi_monitor <command>` from the repository root.

## First run

```bash
wifi-monitor capabilities   # what your platform can report
wifi-monitor status         # current link
wifi-monitor diagnose       # troubleshooter
wifi-monitor serve          # dashboard at http://127.0.0.1:8765
```

If `status` reports *unavailable*, the message and hint explain why — see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Windows 11 24H2 and later

Wi-Fi details require Location access: **Settings → Privacy & security → Location**, turn on
*Location services* and *Let desktop apps access your location*.

### Linux

```bash
sudo apt install network-manager iw   # Debian/Ubuntu, if missing
```

## Dashboard only (demo)

Opening `src/index.html` directly, or `npm run start:demo`, shows the dashboard with simulated
data. Use `wifi-monitor serve` for real measurements.

## Uninstall

```bash
pip uninstall wifi-monitor
```

The CLI stores nothing unless you pass `-o FILE`. The dashboard's history lives in your
browser's `localStorage` for the page origin; use **History → Clear** to remove it.
