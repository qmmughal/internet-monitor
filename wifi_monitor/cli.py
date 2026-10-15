"""Command-line interface.

Exit codes:
  0  success / healthy
  1  diagnostics found a problem (degraded or offline)
  2  usage error
  3  the requested data is unavailable on this system
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import re
import sys
import time
from datetime import datetime
from typing import List, Optional

from . import __version__, netinfo
from .diagnostics import DiagnosticsConfig, Probes, run_diagnostics
from .models import ESTIMATED, LIVE, SIMULATED, ProviderResult, utc_now
from .providers import get_provider
from .signal import dbm_to_percent, quality_label

EXIT_OK, EXIT_PROBLEM, EXIT_USAGE, EXIT_UNAVAILABLE = 0, 1, 2, 3

try:  # Rich is optional; plain text is used without it.
    from rich import box
    from rich.console import Console
    from rich.live import Live
    from rich.markup import escape
    from rich.panel import Panel
    from rich.table import Table

    _console: Optional["Console"] = Console()
except ImportError:  # pragma: no cover - exercised manually
    _console = None

    def escape(text: str) -> str:  # type: ignore[no-redef]
        return text


_STYLES = "bold|dim|red|green|yellow|cyan|magenta|white|bright_green"
_TAG = re.compile(rf"\[/?(?:(?:{_STYLES})(?: (?:{_STYLES}))*)?\]")  # only our own style tags


def out(markup: str = "") -> None:
    if _console is not None:
        _console.print(markup)
    else:
        print(_TAG.sub("", markup))


def safe(value) -> str:
    """Render untrusted text (SSIDs are attacker-controlled) without markup injection."""
    if value is None:
        return "—"
    text = "".join(ch if ch.isprintable() else "?" for ch in str(value))
    return escape(text)


def mode_tag(mode: str) -> str:
    return {
        LIVE: "[green]live[/green]",
        ESTIMATED: "[yellow]estimated[/yellow]",
        SIMULATED: "[magenta]SIMULATED[/magenta]",
    }.get(mode, "[red]unavailable[/red]")


def table(title: str, columns: List[str], rows: List[List[str]]) -> None:
    if _console is not None:
        t = Table(title=title, box=box.ROUNDED, header_style="bold cyan", border_style="cyan")
        for c in columns:
            t.add_column(c)
        for r in rows:
            t.add_row(*r)
        _console.print(t)
        return
    plain = [[_TAG.sub("", c) for c in r] for r in rows]
    widths = [max(len(columns[i]), *(len(r[i]) for r in plain)) if plain else len(columns[i]) for i in range(len(columns))]
    print(title)
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    for r in plain:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def emit_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def unavailable_msg(res: ProviderResult) -> None:
    out(f"[red]✗ Unavailable:[/red] {safe(res.error)}  [dim](source: {safe(res.source)})[/dim]")
    if res.hint:
        out(f"  [yellow]→ {safe(res.hint)}[/yellow]")


def demo_banner(args) -> None:
    if getattr(args, "demo", False) and not getattr(args, "json", False):
        out("[bold magenta]DEMO MODE — all Wi-Fi values below are SIMULATED, not measured.[/bold magenta]\n")


# ─── status ──────────────────────────────────────────────────────

def cmd_status(args) -> int:
    provider = get_provider(demo=args.demo)
    wifi = provider.interfaces()
    route = netinfo.default_route() if not args.demo else ProviderResult(mode=SIMULATED, source="demo", data={})
    from .traffic import human_rate, measure

    traffic = measure(0.5) if not args.demo else None
    online = bool(route.ok or (traffic and traffic.get("primary")))
    if args.json:
        emit_json({"timestamp": utc_now(), "platform": platform.system(), "provider": provider.name,
                   "wifi": wifi.to_dict(), "network": route.to_dict(), "traffic": traffic})
        return EXIT_OK if wifi.ok or online else EXIT_UNAVAILABLE

    if traffic and traffic.get("mode") == "live" and traffic.get("primary"):
        prim = next(i for i in traffic["interfaces"] if i["primary"])
        link = f", {prim['link_speed_mbps']} Mbps link" if prim["link_speed_mbps"] else ""
        out(f"[bold]Active connection:[/bold] {safe(prim['name'])} [dim]({prim['type']}{link})[/dim]  "
            f"↓ {human_rate(prim['rx_bps'])}  ↑ {human_rate(prim['tx_bps'])}\n")

    demo_banner(args)
    if not wifi.ok:
        out("[bold]Wi-Fi[/bold]")
        unavailable_msg(wifi)
    for iface in wifi.data or []:
        rows = [["State", safe(iface.state)], ["Mode", mode_tag(wifi.mode)]]
        if iface.connected:
            sig = iface.signal_dbm
            if sig and sig.value is not None:
                sig_text = f"{sig.value} dBm ({quality_label(sig.value)}) {mode_tag(sig.mode)}"
            else:
                sig_text = "[dim]not reported[/dim]"
            rows += [
                ["SSID", safe(iface.ssid)],
                ["BSSID", safe(iface.bssid)],
                ["Signal", sig_text],
                ["Signal %", f"{iface.signal_percent}%" if iface.signal_percent is not None else "—"],
                ["Band / channel", f"{safe(iface.band)} / {safe(iface.channel)}"
                 + (f" ({iface.frequency_mhz} MHz)" if iface.frequency_mhz else "")],
                ["Radio", safe(iface.radio_type)],
                ["Generation", _generation(iface)],
                ["Security", safe(iface.security)],
                ["Link rate", _rate(iface)],
            ]
            if iface.noise_dbm is not None:
                rows.append(["Noise", f"{iface.noise_dbm} dBm"])
        table(f"Wi-Fi interface: {safe(iface.name)}", ["Field", "Value"], rows)
    if wifi.hint and wifi.ok:
        out(f"[yellow]→ {safe(wifi.hint)}[/yellow]")

    if not args.demo:
        out("")
        d = route.data or {}
        rows = [["Default gateway", safe(d.get("gateway"))], ["Local IP", safe(d.get("local_ip"))],
                ["Route interface", safe(d.get("interface"))], ["Mode", mode_tag(route.mode)]]
        table("Network", ["Field", "Value"], rows)
    out(f"[dim]Measured at {utc_now()} via {safe(wifi.source)}[/dim]")
    return EXIT_OK if wifi.ok or online else EXIT_UNAVAILABLE


def _generation(iface) -> str:
    from .standards import describe

    std = describe(iface)
    text = std["generation"] or "unknown (not reported by the OS)"
    if std["channel_width_mhz"]:
        text += f", {std['channel_width_mhz']} MHz wide"
    return safe(text) + " [dim](this connection)[/dim]"


def _rate(iface) -> str:
    parts = []
    if iface.rx_rate_mbps is not None:
        parts.append(f"↓ {iface.rx_rate_mbps:g} Mbps")
    if iface.tx_rate_mbps is not None:
        parts.append(f"↑ {iface.tx_rate_mbps:g} Mbps")
    return "  ".join(parts) + " (negotiated, not throughput)" if parts else "—"


# ─── scan ────────────────────────────────────────────────────────

def cmd_scan(args) -> int:
    res = get_provider(demo=args.demo).access_points()
    if args.json:
        emit_json(res.to_dict())
        return EXIT_OK if res.ok else EXIT_UNAVAILABLE
    demo_banner(args)
    if not res.ok:
        unavailable_msg(res)
        return EXIT_UNAVAILABLE
    aps = sorted(res.data, key=lambda a: a.signal_dbm if a.signal_dbm is not None else -999, reverse=True)
    rows = []
    for ap in aps:
        sig = "—"
        if ap.signal_dbm is not None:
            color = {"Excellent": "bright_green", "Good": "green", "Fair": "yellow"}.get(quality_label(ap.signal_dbm), "red")
            approx = "≈" if ap.signal_mode == ESTIMATED else ""
            sig = f"[{color}]{approx}{ap.signal_dbm} dBm[/{color}]"
        rows.append([
            ("[bold]" + safe(ap.ssid) + "[/bold]" if ap.ssid else "[dim]<hidden>[/dim]") + (" ★" if ap.connected else ""),
            safe(ap.bssid), safe(ap.band), safe(ap.channel), safe(ap.security), sig,
            f"{ap.signal_percent}%" if ap.signal_percent is not None else "—",
        ])
    table("Nearby access points", ["SSID", "BSSID", "Band", "Ch", "Security", "Signal", "Quality"], rows)
    out(f"[dim]{len(aps)} access points · mode: {res.mode} · source: {safe(res.source)} · ★ = connected"
        + (" · ≈ = estimated from %" if any(a.signal_mode == ESTIMATED for a in aps) else "") + "[/dim]")
    if res.hint:
        out(f"[dim]{safe(res.hint)}[/dim]")
    return EXIT_OK


# ─── diagnose ────────────────────────────────────────────────────

SEVERITY_STYLE = {"ok": "green", "info": "cyan", "warning": "yellow", "critical": "red"}


def cmd_diagnose(args) -> int:
    if args.demo:
        out("[red]Diagnostics always use real measurements; --demo is not supported here.[/red]")
        return EXIT_USAGE
    cfg = DiagnosticsConfig(probe_timeout_s=args.timeout)
    provider = get_provider()
    on_stage = None
    if not args.json:
        out("[cyan]Running connectivity diagnostics…[/cyan]")
        on_stage = lambda s: out(f"  [dim]· {s}[/dim]")  # noqa: E731
    from .apps import activity_snapshot

    report = run_diagnostics(cfg, Probes(wifi=provider.interfaces, activity=activity_snapshot), on_stage=on_stage)
    code = EXIT_OK if report.overall == "healthy" else EXIT_PROBLEM
    if args.json:
        emit_json(report.to_dict())
        return code

    color = {"healthy": "green", "degraded": "yellow", "offline": "red"}[report.overall]
    out(f"\n[bold {color}]Overall: {report.overall.upper()}[/bold {color}]  [dim]({report.duration_ms} ms)[/dim]\n")
    for f in report.findings:
        st = SEVERITY_STYLE.get(f.severity, "white")
        out(f"[bold {st}]{f.severity.upper():8}[/bold {st}] [bold]{safe(f.title)}[/bold]"
            + (f"  [dim](confidence: {f.confidence})[/dim]" if f.confidence else ""))
        for e in f.evidence:
            out(f"           [dim]evidence:[/dim] {safe(e)}")
        if f.likely_cause:
            out(f"           [dim]likely cause:[/dim] {safe(f.likely_cause)}")
        if f.next_step:
            out(f"           [dim]try next:[/dim] {safe(f.next_step)}")
        out("")
    out("[dim]Run with --json for the full evidence. No settings were changed.[/dim]")
    return code


# ─── capabilities ────────────────────────────────────────────────

def cmd_capabilities(args) -> int:
    provider = get_provider(demo=args.demo)
    caps = provider.capabilities()
    if args.json:
        emit_json({"platform": platform.system(), "provider": provider.name, "capabilities": caps})
        return EXIT_OK
    demo_banner(args)
    rows = []
    for metric, info in caps.items():
        sup = info.get("supported")
        mark = {True: "[green]yes[/green]", False: "[red]no[/red]", "partial": "[yellow]partial[/yellow]"}.get(sup, safe(sup) if sup is not None else "")
        rows.append([metric, mark, safe(info.get("notes", ""))])
    table(f"Capabilities — {provider.name} ({platform.system()})", ["Metric", "Supported", "Notes"], rows)
    return EXIT_OK


# ─── monitor ─────────────────────────────────────────────────────

SPARK = "▁▂▃▄▅▆▇█"
CSV_FIELDS = ["timestamp", "mode", "source", "ssid", "bssid", "signal_dbm", "signal_mode", "signal_percent", "channel", "band", "error"]


def sample(provider) -> dict:
    res = provider.connected_interface()
    row = {k: None for k in CSV_FIELDS}
    row.update(timestamp=res.timestamp, mode=res.mode, source=res.source, error=res.error)
    if res.ok:
        i = res.data
        row.update(ssid=i.ssid, bssid=i.bssid, signal_percent=i.signal_percent, channel=i.channel, band=i.band)
        if i.signal_dbm:
            row.update(signal_dbm=i.signal_dbm.value, signal_mode=i.signal_dbm.mode)
    row["_hint"] = res.hint
    return row


def write_log(entries: List[dict], path: str) -> None:
    rows = [{k: e.get(k) for k in CSV_FIELDS} for e in entries]
    if path.lower().endswith(".json"):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, indent=2)
    else:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            w.writeheader()
            w.writerows(rows)


def render_monitor(entries: List[dict]):
    e = entries[-1]
    lines = []
    if e["mode"] == SIMULATED:
        lines.append("[bold magenta]SIMULATED DATA — demo mode[/bold magenta]")
    if e["error"]:
        lines.append(f"[red]Signal unavailable:[/red] {safe(e['error'])}")
        if e.get("_hint"):
            lines.append(f"[yellow]→ {safe(e['_hint'])}[/yellow]")
    else:
        dbm = e["signal_dbm"]
        lines.append(f"SSID      : [bold]{safe(e['ssid'])}[/bold]   BSSID {safe(e['bssid'])}")
        if dbm is not None:
            color = {"Excellent": "bright_green", "Good": "green", "Fair": "yellow"}.get(quality_label(dbm), "red")
            pct = dbm_to_percent(dbm)
            bar = "█" * round(pct / 5) + "░" * (20 - round(pct / 5))
            lines.append(f"Signal    : [bold {color}]{dbm} dBm[/bold {color}] {quality_label(dbm)}  {mode_tag(e['signal_mode'])}")
            lines.append(f"Bar       : [{color}]{bar}[/{color}]")
        lines.append(f"Band / Ch : {safe(e['band'])} / {safe(e['channel'])}")
    vals = [x["signal_dbm"] for x in entries if x["signal_dbm"] is not None]
    if vals:
        spark = "".join(SPARK[min(7, round(dbm_to_percent(v) / 100 * 7))] for v in vals[-40:])
        lines.append(f"History   : [cyan]{spark}[/cyan]")
        lines.append(f"Avg / Min / Max : {round(sum(vals) / len(vals))} / {min(vals)} / {max(vals)} dBm  ({len(vals)} samples)")
    lines.append(f"[dim]Last sample {e['timestamp']} · source {safe(e['source'])} · Ctrl+C to stop[/dim]")
    text = "\n".join(lines)
    if _console is not None:
        return Panel(text, title="[bold cyan]📡 WiFi Monitor[/bold cyan]", border_style="cyan")
    return text


def plain_sample_line(e: dict) -> str:
    if e["error"]:
        return f"{e['timestamp']}  unavailable: {e['error']}"
    dbm = f"{e['signal_dbm']} dBm ({e['signal_mode']})" if e["signal_dbm"] is not None else "signal not reported"
    return f"{e['timestamp']}  {e['ssid'] or '<hidden>'}  {dbm}  {e['band'] or ''} ch {e['channel'] or '?'}"


def cmd_monitor(args) -> int:
    provider = get_provider(demo=args.demo)
    entries: List[dict] = []
    interval = max(1.0, args.interval)
    try:
        if _console is not None and not args.json:
            with Live(refresh_per_second=4, console=_console) as live:
                while args.count is None or len(entries) < args.count:
                    entries.append(sample(provider))
                    live.update(render_monitor(entries))
                    if args.count is None or len(entries) < args.count:
                        time.sleep(interval)
        else:
            while args.count is None or len(entries) < args.count:
                entries.append(sample(provider))
                if args.json:
                    print(json.dumps({k: v for k, v in entries[-1].items() if not k.startswith("_")}), flush=True)
                else:
                    print(plain_sample_line(entries[-1]), flush=True)
                if args.count is None or len(entries) < args.count:
                    time.sleep(interval)
    except KeyboardInterrupt:
        out("\n[dim]Stopped.[/dim]")
    finally:
        path = args.output
        if not path and args.export_format and entries:
            path = f"wifi_log_{datetime.now():%Y%m%d_%H%M%S}.{args.export_format}"
        if path and entries:
            write_log(entries, path)
            out(f"[green]Saved {len(entries)} samples to {safe(path)}[/green]")
    if entries and all(e["mode"] == "unavailable" for e in entries):
        return EXIT_UNAVAILABLE
    return EXIT_OK


# ─── serve ───────────────────────────────────────────────────────

def cmd_serve(args) -> int:
    from .server import serve

    return serve(host=args.host, port=args.port, demo=args.demo, allow_remote=args.allow_remote,
                 collect=not args.no_collect, interval_s=args.interval, mqtt=args.mqtt)


# ─── argument parsing ────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="machine-readable JSON output")
    common.add_argument("--demo", action="store_true", help="use SIMULATED data (clearly labelled) instead of the OS")

    parser = argparse.ArgumentParser(
        prog="wifi-monitor",
        description="WiFi Monitor — local Wi-Fi monitoring and connectivity diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  wifi-monitor status              current Wi-Fi link, gateway and local IP
  wifi-monitor scan                nearby access points (from the OS scan list)
  wifi-monitor diagnose            step-by-step internet troubleshooter
  wifi-monitor monitor -o log.csv  live signal monitor, saved to CSV
  wifi-monitor serve               dashboard + local API on http://127.0.0.1:8765
  wifi-monitor capabilities        what this platform can measure
  wifi-monitor speedtest           download/upload throughput (uses data)
  wifi-monitor channels            channel congestion and recommendation
  wifi-monitor devices             devices on your network (passive)
  wifi-monitor ask "why is my wifi slow?"   plain-language explanation
  wifi-monitor history / alerts    from a running `serve`

legacy flags (v1.0): --scan, --signal, --export csv|json

exit codes: 0 ok · 1 problem found · 2 usage error · 3 data unavailable""",
    )
    parser.add_argument("--version", action="version", version=f"wifi-monitor {__version__}")
    parser.add_argument("--scan", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--signal", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--export", choices=["csv", "json"], dest="legacy_export", help=argparse.SUPPRESS)
    parser.add_argument("--demo", action="store_true", dest="legacy_demo", help=argparse.SUPPRESS)

    sub = parser.add_subparsers(dest="command", metavar="command")
    sub.add_parser("status", parents=[common], help="current Wi-Fi and network state").set_defaults(func=cmd_status)
    sub.add_parser("scan", parents=[common], help="list nearby access points").set_defaults(func=cmd_scan)
    sub.add_parser("capabilities", parents=[common], help="what this platform can measure").set_defaults(func=cmd_capabilities)

    d = sub.add_parser("diagnose", parents=[common], help="run the connectivity troubleshooter")
    d.add_argument("--timeout", type=float, default=2.0, help="per-probe timeout in seconds (default 2)")
    d.set_defaults(func=cmd_diagnose)

    m = sub.add_parser("monitor", parents=[common], help="live signal monitor")
    m.add_argument("-i", "--interval", type=float, default=2.0, help="seconds between samples (min 1, default 2)")
    m.add_argument("-n", "--count", type=int, default=None, help="stop after N samples")
    m.add_argument("-o", "--output", help="save samples to FILE (.csv or .json)")
    m.set_defaults(func=cmd_monitor, export_format=None)

    s = sub.add_parser("serve", help="dashboard + local read-only API")
    s.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--demo", action="store_true", help="serve SIMULATED data")
    s.add_argument("--allow-remote", action="store_true", help="permit binding to a non-loopback address (unauthenticated!)")
    s.add_argument("--interval", type=float, default=None, help="history sampling interval in seconds (default 10)")
    s.add_argument("--no-collect", action="store_true", help="do not collect history in the background")
    s.add_argument("--mqtt", action="store_true", help="publish samples to MQTT (configure in config.json)")
    s.set_defaults(func=cmd_serve)

    from .commands import register

    register(sub, common)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # never crash on consoles that cannot print symbols
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:  # v1.0 flag compatibility
        demo = args.legacy_demo
        if args.scan:
            ns = argparse.Namespace(json=False, demo=demo)
            return cmd_scan(ns)
        ns = argparse.Namespace(json=False, demo=demo, interval=2.0, count=None, output=None,
                                export_format=args.legacy_export)
        return cmd_monitor(ns)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
