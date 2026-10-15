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
git clone https://github.com/qmmughal/internet-monitor.git
cd internet-monitor
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install ".[rich]"
internet-monitor --version
```

Without installing, every command also works as `python cli/internet-monitor.py <command>` or
`python -m internet_monitor <command>` from the repository root.

## First run

```bash
internet-monitor capabilities   # what your platform can report
internet-monitor status         # current link
internet-monitor diagnose       # troubleshooter
internet-monitor serve          # dashboard at http://127.0.0.1:8765
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
data. Use `internet-monitor serve` for real measurements.

## Uninstall

```bash
pip uninstall internet-monitor
```

The CLI stores nothing unless you pass `-o FILE`. The dashboard's history lives in your
browser's `localStorage` for the page origin; use **History → Clear** to remove it.
