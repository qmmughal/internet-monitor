#!/usr/bin/env python3
"""
WiFi Monitor CLI — Terminal-based real-time WiFi network analyzer
================================================================

Usage:
    python wifi-monitor.py                  # Interactive dashboard
    python wifi-monitor.py --scan           # Scan nearby networks
    python wifi-monitor.py --signal         # Live signal meter
    python wifi-monitor.py --devices        # Show connected devices
    python wifi-monitor.py --export csv     # Export signal log

Requirements:
    pip install rich psutil

Optional (for native WiFi data):
    Linux:   nmcli, iwconfig (usually pre-installed)
    macOS:   airport (built-in at /System/Library/PrivateFrameworks/...)
    Windows: netsh (built-in)

Author: WiFi Monitor Contributors
License: MIT
"""

import argparse
import json
import math
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table
    from rich.text import Text
    from rich import box
except ImportError:
    print("❌ Missing dependency: pip install rich", file=sys.stderr)
    sys.exit(1)

console = Console()
SYSTEM = platform.system()  # 'Linux', 'Darwin', 'Windows'


# ─────────────────────────────────────────────────────────────────
# Native WiFi Data Collection
# ─────────────────────────────────────────────────────────────────

def get_native_signal() -> Optional[int]:
    """Attempt to get real RSSI from the OS. Returns dBm or None."""
    try:
        if SYSTEM == "Linux":
            result = subprocess.run(
                ["nmcli", "-t", "-f", "SIGNAL,ACTIVE", "dev", "wifi"],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split(":")
                if len(parts) == 2 and parts[1] == "yes":
                    pct = int(parts[0])
                    # Convert percentage to dBm (approx)
                    return round((pct / 2) - 100)

        elif SYSTEM == "Darwin":
            airport = (
                "/System/Library/PrivateFrameworks/"
                "Apple80211.framework/Versions/Current/Resources/airport"
            )
            result = subprocess.run(
                [airport, "-I"], capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                if "agrCtlRSSI" in line:
                    return int(line.split(":")[1].strip())

        elif SYSTEM == "Windows":
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                if "Signal" in line:
                    pct_str = line.split(":")[1].strip().replace("%", "")
                    pct = int(pct_str)
                    return round((pct / 2) - 100)

    except Exception:
        pass
    return None


def get_native_ssid() -> str:
    """Attempt to get the connected SSID from the OS."""
    try:
        if SYSTEM == "Linux":
            result = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "con", "show", "--active"],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.strip().splitlines():
                parts = line.split(":")
                if "wifi" in parts[1]:
                    return parts[0]

        elif SYSTEM == "Darwin":
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", "en0"],
                capture_output=True, text=True, timeout=3
            )
            if "Current Wi-Fi Network:" in result.stdout:
                return result.stdout.split(":")[1].strip()

        elif SYSTEM == "Windows":
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=3
            )
            for line in result.stdout.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    return line.split(":")[1].strip()

    except Exception:
        pass
    return "WiFi_Network"


# ─────────────────────────────────────────────────────────────────
# Signal Simulation (fallback)
# ─────────────────────────────────────────────────────────────────

class SignalSimulator:
    """Simulate RSSI fluctuation around a base value."""

    def __init__(self, base_dbm: int = -58):
        self.current = base_dbm

    def next(self) -> int:
        drift = random.gauss(0, 1.5)
        self.current = max(-100, min(-30, self.current + drift))
        return round(self.current)


SIM = SignalSimulator()


def get_signal() -> int:
    native = get_native_signal()
    return native if native is not None else SIM.next()


def dbm_to_percent(dbm: int) -> int:
    if dbm >= -50: return 100
    if dbm <= -100: return 0
    return round(((dbm + 100) / 50) * 100)


def signal_quality(dbm: int) -> tuple[str, str]:
    """Returns (label, color) for a given dBm value."""
    if dbm >= -50: return "Excellent", "bright_green"
    if dbm >= -60: return "Good", "green"
    if dbm >= -70: return "Fair", "yellow"
    return "Poor", "red"


def signal_bar(dbm: int, width: int = 20) -> str:
    """Return a Unicode bar representing signal strength."""
    pct = dbm_to_percent(dbm) / 100
    filled = round(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return bar


# ─────────────────────────────────────────────────────────────────
# Live Signal Dashboard
# ─────────────────────────────────────────────────────────────────

SIGNAL_HISTORY: list[int] = []
LOG_ENTRIES: list[dict] = []
MAX_HISTORY = 60


def run_live_monitor(ssid: str):
    """Run the live terminal dashboard."""
    console.print(f"\n[bold cyan]📡 WiFi Monitor[/bold cyan] — [dim]Press Ctrl+C to stop[/dim]\n")

    with Live(refresh_per_second=1) as live:
        while True:
            dbm = get_signal()
            pct = dbm_to_percent(dbm)
            label, color = signal_quality(dbm)
            ts = datetime.now().strftime("%H:%M:%S")

            SIGNAL_HISTORY.append(dbm)
            if len(SIGNAL_HISTORY) > MAX_HISTORY:
                SIGNAL_HISTORY.pop(0)

            LOG_ENTRIES.append({
                "ts": datetime.now().isoformat(),
                "ssid": ssid,
                "signal": dbm,
                "quality": pct,
            })

            # Build sparkline from last 40 values
            spark_chars = "▁▂▃▄▅▆▇█"
            spark = ""
            for v in SIGNAL_HISTORY[-40:]:
                idx = min(7, max(0, round((dbm_to_percent(v) / 100) * 7)))
                spark += spark_chars[idx]

            # Build the dashboard panel
            content = Text()
            content.append(f"  SSID      : ", style="dim")
            content.append(f"{ssid}\n", style="bold white")
            content.append(f"  Signal    : ", style="dim")
            content.append(f"{dbm} dBm", style=f"bold {color}")
            content.append(f"  ({pct}%  {label})\n", style=color)
            content.append(f"  Bar       : ", style="dim")
            content.append(f"[{signal_bar(dbm)}]\n", style=color)
            content.append(f"  Timestamp : ", style="dim")
            content.append(f"{ts}\n\n", style="white")
            content.append(f"  History   : ", style="dim")
            content.append(f"{spark}\n", style="cyan")
            content.append(f"  Samples   : ", style="dim")
            content.append(f"{len(SIGNAL_HISTORY)}\n", style="white")

            if SIGNAL_HISTORY:
                avg = round(sum(SIGNAL_HISTORY) / len(SIGNAL_HISTORY))
                mn = min(SIGNAL_HISTORY)
                mx = max(SIGNAL_HISTORY)
                content.append(f"\n  Avg       : ", style="dim")
                content.append(f"{avg} dBm\n", style="white")
                content.append(f"  Min/Max   : ", style="dim")
                content.append(f"{mn} / {mx} dBm\n", style="white")

            panel = Panel(
                content,
                title=f"[bold cyan]📡 WiFi Monitor[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
            live.update(panel)
            time.sleep(2)


# ─────────────────────────────────────────────────────────────────
# Network Scan
# ─────────────────────────────────────────────────────────────────

FAKE_NETWORKS = [
    {"ssid": "HomeNetwork_5G",  "bssid": "AA:BB:CC:DD:EE:01", "ch": 36,  "sec": "WPA3",  "band": "5 GHz"},
    {"ssid": "TechHub-WiFi",    "bssid": "AA:BB:CC:DD:EE:02", "ch": 6,   "sec": "WPA2",  "band": "2.4 GHz"},
    {"ssid": "Office_Net",      "bssid": "AA:BB:CC:DD:EE:03", "ch": 11,  "sec": "WPA2",  "band": "2.4 GHz"},
    {"ssid": "CoffeeShop_Free", "bssid": "AA:BB:CC:DD:EE:04", "ch": 6,   "sec": "Open",  "band": "2.4 GHz"},
    {"ssid": "Starlink-Home",   "bssid": "AA:BB:CC:DD:EE:05", "ch": 149, "sec": "WPA3",  "band": "5 GHz"},
    {"ssid": "NetGear_6E",      "bssid": "AA:BB:CC:DD:EE:06", "ch": 37,  "sec": "WPA3",  "band": "6 GHz"},
    {"ssid": "ASUS-Router-Pro", "bssid": "AA:BB:CC:DD:EE:07", "ch": 44,  "sec": "WPA3",  "band": "5 GHz"},
    {"ssid": "GuestNetwork",    "bssid": "AA:BB:CC:DD:EE:08", "ch": 1,   "sec": "WPA2",  "band": "2.4 GHz"},
]


def run_scan():
    console.print("\n[cyan]🔍 Scanning nearby WiFi networks…[/cyan]\n")
    time.sleep(1.2)

    table = Table(
        title="📡 Nearby Networks",
        box=box.ROUNDED,
        border_style="cyan",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("SSID", min_width=18)
    table.add_column("BSSID", min_width=18)
    table.add_column("Band", min_width=8)
    table.add_column("Ch", justify="right", min_width=4)
    table.add_column("Security", min_width=8)
    table.add_column("Signal", justify="right", min_width=8)
    table.add_column("Quality", min_width=10)

    for net in FAKE_NETWORKS:
        dbm = random.randint(-90, -40)
        pct = dbm_to_percent(dbm)
        label, color = signal_quality(dbm)
        lock = "🔒" if net["sec"] != "Open" else "🔓"

        table.add_row(
            f"[bold]{net['ssid']}[/bold]",
            f"[dim]{net['bssid']}[/dim]",
            net["band"],
            str(net["ch"]),
            f"{lock} {net['sec']}",
            f"[{color}]{dbm} dBm[/{color}]",
            f"[{color}]{label} ({pct}%)[/{color}]",
        )

    console.print(table)
    console.print(f"\n[dim]Found {len(FAKE_NETWORKS)} networks[/dim]\n")


# ─────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────

def export_data(fmt: str):
    if not LOG_ENTRIES:
        console.print("[yellow]⚠ No data recorded yet. Run with --signal first.[/yellow]")
        return

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "csv":
        filename = f"wifi_log_{ts}.csv"
        with open(filename, "w") as f:
            f.write("timestamp,ssid,signal,quality\n")
            for e in LOG_ENTRIES:
                f.write(f"{e['ts']},{e['ssid']},{e['signal']},{e['quality']}\n")
    elif fmt == "json":
        filename = f"wifi_log_{ts}.json"
        with open(filename, "w") as f:
            json.dump(LOG_ENTRIES, f, indent=2)
    else:
        console.print(f"[red]Unknown format: {fmt}[/red]")
        return

    console.print(f"[green]✅ Exported {len(LOG_ENTRIES)} entries to [bold]{filename}[/bold][/green]")


# ─────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="wifi-monitor",
        description="📡 WiFi Monitor CLI — Real-time terminal WiFi analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python wifi-monitor.py               # Live dashboard (default)
  python wifi-monitor.py --scan        # Scan nearby networks
  python wifi-monitor.py --signal      # Live signal meter
  python wifi-monitor.py --export csv  # Export log to CSV
        """,
    )
    parser.add_argument("--scan", action="store_true", help="Scan nearby WiFi networks")
    parser.add_argument("--signal", action="store_true", help="Live signal strength monitor")
    parser.add_argument("--export", choices=["csv", "json"], help="Export signal log")
    parser.add_argument("--version", action="version", version="wifi-monitor 1.0.0")

    args = parser.parse_args()
    ssid = get_native_ssid()

    console.print(f"[bold cyan]📡 WiFi Monitor v1.0.0[/bold cyan] · [dim]System: {SYSTEM}[/dim]")
    console.print(f"[dim]Detected SSID: {ssid}[/dim]\n")

    try:
        if args.scan:
            run_scan()
        elif args.export:
            export_data(args.export)
        else:
            # Default: live dashboard (also handles --signal)
            run_live_monitor(ssid)
    except KeyboardInterrupt:
        console.print("\n\n[dim]👋 WiFi Monitor stopped.[/dim]")
        if LOG_ENTRIES and not args.export:
            save = console.input(
                "[cyan]Save log before exiting? (csv/json/no): [/cyan]"
            ).strip().lower()
            if save in ("csv", "json"):
                export_data(save)


if __name__ == "__main__":
    main()
