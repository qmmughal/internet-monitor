"""CLI commands for history, alerts, devices, channels, speed test, survey, AI, hub and agent."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Optional

from . import ai, channels, config, devices, survey
from . import speedtest as speedtest_mod
from .cli import (EXIT_OK, EXIT_UNAVAILABLE, EXIT_USAGE, demo_banner, emit_json, mode_tag, out, safe,
                  table, unavailable_msg)
from .diagnostics import Probes, run_diagnostics
from .providers import get_provider

DEFAULT_URL = "http://127.0.0.1:8765"
SEV = {"ok": "green", "info": "cyan", "warning": "yellow", "critical": "red"}


# ── talking to a running `serve` (history lives in its memory) ──

def api(url: str, path: str, method: str = "GET", body: Optional[dict] = None, raw: bool = False):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-WiFi-Monitor": "1"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url.rstrip("/") + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read()
    return payload if raw else json.loads(payload)


def _server_unreachable(url: str, exc: Exception) -> int:
    out(f"[red]✗ Could not reach the WiFi Monitor server at {safe(url)}[/red] [dim]({safe(exc)})[/dim]")
    out("  [yellow]→ History and alerts are collected by a running server. Start it with: wifi-monitor serve[/yellow]")
    return EXIT_UNAVAILABLE


# ── history / alerts ─────────────────────────────────────────────

def cmd_history(args) -> int:
    try:
        if args.export:
            body = api(args.url, f"/api/v1/history/export?format={args.export}", raw=True)
            path = args.output or f"wifi_history_{time.strftime('%Y%m%d_%H%M%S')}.{args.export}"
            with open(path, "wb") as fh:
                fh.write(body)
            out(f"[green]Saved history to {safe(path)}[/green]")
            return EXIT_OK
        stats = api(args.url, f"/api/v1/history/stats?window={args.window}")
        events = api(args.url, f"/api/v1/events?window={args.window}")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _server_unreachable(args.url, exc)
    if args.json:
        emit_json({"stats": stats, "events": events["events"]})
        return EXIT_OK
    st = stats["stats"]
    out(f"[bold]History[/bold] — last {args.window} s · {st['samples']} samples · stored in server memory only")
    if st["simulated_samples"]:
        out(f"[magenta]{st['simulated_samples']} samples are SIMULATED (demo mode)[/magenta]")
    if st["estimated_signal_samples"]:
        out(f"[yellow]{st['estimated_signal_samples']} signal values are estimated from OS %[/yellow]")
    rows = []
    labels = {"signal_dbm": "Signal (dBm)", "gateway_ms": "Router latency (ms)", "gateway_loss_pct": "Router loss (%)",
              "internet_ms": "Internet latency (ms)", "dns_ms": "DNS (ms)"}
    for key, label in labels.items():
        s = st.get(key)
        b = (stats.get("baseline") or {}).get(key)
        change = f"{b['change']:+g} vs prior hour" if b else "—"
        rows.append([label, *(str(s[k]) if s else "—" for k in ("latest", "avg", "min", "max", "p95")), change])
    table("Statistics", ["Metric", "Latest", "Avg", "Min", "Max", "p95", "Baseline"], rows)
    if st.get("connected_pct") is not None:
        out(f"Connected {st['connected_pct']}% of samples")
    ev = events["events"][-15:]
    if ev:
        table("Events (roaming, disconnects)", ["Time", "Type", "Detail"],
              [[e["timestamp"], e["type"], safe(e["detail"])] for e in ev])
    return EXIT_OK


def cmd_alerts(args) -> int:
    try:
        if args.ack is not None:
            api(args.url, "/api/v1/alerts/ack", "POST", {"id": args.ack})
            out(f"[green]Alert {args.ack} acknowledged[/green]")
            return EXIT_OK
        if args.clear:
            api(args.url, "/api/v1/alerts/clear", "POST", {})
            out("[green]Alerts cleared[/green]")
            return EXIT_OK
        data = api(args.url, f"/api/v1/alerts?active={'1' if args.active else '0'}")
    except urllib.error.HTTPError as exc:
        out(f"[red]{safe(exc)}[/red]")
        return EXIT_USAGE
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return _server_unreachable(args.url, exc)
    if args.json:
        emit_json(data)
        return EXIT_OK
    alerts = data["alerts"]
    if not alerts:
        out("[green]No alerts.[/green]")
        return EXIT_OK
    rows = []
    for a in alerts[-30:]:
        sev = SEV.get(a["severity"], "white")
        rows.append([str(a["id"]), a["timestamp"], f"[{sev}]{a['severity']}[/{sev}]",
                     safe(a["title"]) + (" [magenta](simulated)[/magenta]" if a.get("simulated") else ""),
                     safe(a["detail"]), "✓" if a["acknowledged"] else ""])
    table("Alerts", ["ID", "Time", "Severity", "Title", "Detail", "Ack"], rows)
    return EXIT_OK


# ── devices / security ───────────────────────────────────────────

def cmd_devices(args) -> int:
    known = devices.KnownDevices()
    if args.name:
        try:
            known.set_name(args.name[0], args.name[1] or None)
        except ValueError as exc:
            out(f"[red]{safe(exc)}[/red]")
            return EXIT_USAGE
        out(f"[green]Named {safe(args.name[0])} → {safe(args.name[1])}[/green]")
        return EXIT_OK
    if args.forget:
        ok = known.forget(args.forget)
        out("[green]Forgotten[/green]" if ok else "[yellow]Not a known device[/yellow]")
        return EXIT_OK if ok else EXIT_USAGE
    if args.probe and not args.json:
        out("[yellow]Active probe: pinging every address of the local private /24 once (bounded). "
            "Only do this on networks you are authorised to scan.[/yellow]")
    result = devices.discover(probe=args.probe, known=known)
    res = result["result"]
    if args.json:
        emit_json(result)
        return EXIT_OK if res["mode"] != "unavailable" else EXIT_UNAVAILABLE
    if res["mode"] == "unavailable":
        out(f"[red]✗ {safe(res['error'])}[/red]")
        return EXIT_UNAVAILABLE
    rows = []
    for d in sorted(res["data"], key=lambda d: tuple(int(x) for x in d["ip"].split("."))):
        flags = []
        if d["is_gateway"]:
            flags.append("router")
        if d["new"]:
            flags.append("[yellow]NEW[/yellow]")
        if d["randomized_mac"]:
            flags.append("private MAC")
        rows.append([d["ip"], d["mac"], safe(d["name"] or ""), safe(d["vendor"] or "—"), ", ".join(flags),
                     d["first_seen"] or ""])
    table(f"Devices — {result['method']}", ["IP", "MAC", "Name", "Vendor", "Flags", "First seen"], rows)
    if result.get("sweep"):
        out(f"[dim]Sweep: {safe(result['sweep'])}[/dim]")
    for lim in result["limitations"]:
        out(f"[dim]· {safe(lim)}[/dim]")
    out("[dim]Name a device: wifi-monitor devices --name <MAC> \"Living room TV\"[/dim]")
    return EXIT_OK


def cmd_security(args) -> int:
    provider = get_provider()
    conn = provider.connected_interface()
    result = devices.discover(probe=False)
    devs = (result["result"].get("data") or [])
    prev = devices.gateway_history(devs)
    findings = devices.security_posture(conn.data if conn.ok else None, devs, prev)
    if args.json:
        emit_json({"findings": findings, "wifi": conn.to_dict(), "devices": len(devs)})
        return EXIT_OK
    if not conn.ok:
        out(f"[dim]Wi-Fi: {safe(conn.error)}[/dim]")
    if not findings:
        out("[green]No security observations.[/green]")
    for f in findings:
        st = SEV.get(f["severity"], "white")
        out(f"[bold {st}]{f['severity'].upper():8}[/bold {st}] [bold]{safe(f['title'])}[/bold]")
        out(f"           [dim]evidence:[/dim] {safe(f['evidence'])}")
        if f.get("advice"):
            out(f"           [dim]advice:[/dim] {safe(f['advice'])}")
    out("[dim]Observations only; a finding is not proof of an attack. Nothing was changed.[/dim]")
    return EXIT_OK


# ── channels ─────────────────────────────────────────────────────

def cmd_channels(args) -> int:
    provider = get_provider(demo=args.demo)
    aps = provider.access_points()
    if not aps.ok:
        if args.json:
            emit_json(aps.to_dict())
        else:
            unavailable_msg(aps)
        return EXIT_UNAVAILABLE
    conn = provider.connected_interface()
    result = channels.analyze(aps.data, aps.mode, own_ssid=conn.data.ssid if conn.ok else None)
    if args.json:
        emit_json(result)
        return EXIT_OK
    demo_banner(args)
    for band, b in result["bands"].items():
        if not b["access_points"] and not b["your_channels"]:
            continue
        out(f"\n[bold cyan]{band}[/bold cyan] — {b['access_points']} access points"
            + (f", yours on {', '.join(map(str, b['your_channels']))}" if b["your_channels"] else ""))
        rows = [[str(c["channel"]), str(c["access_points"]), str(c["own"]),
                 str(c["strongest_dbm"]) if c["strongest_dbm"] is not None else "—"] for c in b["channels"]]
        table("Seen channels", ["Channel", "APs", "Yours", "Strongest dBm"], rows)
        rec = b.get("recommendation")
        if rec:
            out(f"[green]→ {safe(rec['reason'])}[/green] [dim](confidence: {rec['confidence']})[/dim]")
        elif b.get("recommendation_withheld"):
            out(f"[magenta]{b['recommendation_withheld']}[/magenta]")
    out(f"\n[dim]{result['method']}[/dim]")
    for a in result["assumptions"]:
        out(f"[dim]· {a}[/dim]")
    return EXIT_OK


# ── speed test ───────────────────────────────────────────────────

def cmd_speedtest(args) -> int:
    if not args.json:
        out(f"[cyan]Testing throughput against speed.cloudflare.com (uses up to ~{args.max_mb} MB)…[/cyan]")
    r = speedtest_mod.run(max_mb=args.max_mb,
                          on_phase=None if args.json else (lambda p: out(f"  [dim]· {p}[/dim]")))
    if args.json:
        emit_json(r)
        return EXIT_OK if r["mode"] == "live" else EXIT_UNAVAILABLE
    if r["mode"] != "live":
        out(f"[red]✗ Speed test failed: {safe(', '.join(r['errors']) or 'no data')}[/red]")
        return EXIT_UNAVAILABLE
    lat = r["latency"]
    rows = [["Download", f"{r['download_mbps']} Mbps" if r["download_mbps"] else "—"],
            ["Upload", f"{r['upload_mbps']} Mbps" if r["upload_mbps"] else "—"],
            ["Latency (TCP)", f"{lat['median_ms']} ms" if lat["median_ms"] is not None else "—"],
            ["Jitter", f"{lat['jitter_ms']} ms" if lat["jitter_ms"] is not None else "—"],
            ["Data used", f"{r['data_used_mb']} MB"], ["Server", r["server"]]]
    table("Speed test", ["Metric", "Value"], rows)
    for c in r["caveats"]:
        out(f"[dim]· {c}[/dim]")
    return EXIT_OK


# ── survey ───────────────────────────────────────────────────────

def cmd_survey(args) -> int:
    if args.action == "add":
        if not args.label:
            out("[red]Give the location a name: wifi-monitor survey add \"Kitchen\"[/red]")
            return EXIT_USAGE
        provider = get_provider(demo=args.demo)
        demo_banner(args)
        out(f"[cyan]Recording {args.samples} samples at '{safe(args.label)}' — keep the device still…[/cyan]")
        try:
            res = survey.record(args.label, provider, samples=args.samples)
        except ValueError as exc:
            out(f"[red]{safe(exc)}[/red]")
            return EXIT_USAGE
        if not res["ok"]:
            out(f"[red]✗ {safe(res['error'])}[/red]")
            return EXIT_UNAVAILABLE
        p = res["point"]
        out(f"[green]Saved '{safe(p['label'])}': {p['median_dbm']} dBm median ({p['min_dbm']}…{p['max_dbm']}), "
            f"{mode_tag(p['mode'])}[/green]")
        return EXIT_OK
    if args.action == "clear":
        survey.clear()
        out("[green]Survey cleared[/green]")
        return EXIT_OK
    rep = survey.report()
    if args.json:
        emit_json(rep)
        return EXIT_OK
    if not rep["points"]:
        out("No survey points yet. Walk to a spot and run: wifi-monitor survey add \"Kitchen\"")
        return EXIT_OK
    zone_style = {"ok": "green", "weak": "yellow", "dead": "red"}
    rows = [[safe(p["label"]), f"{p['median_dbm']} dBm", p["quality"],
             f"[{zone_style[p['zone']]}]{p['zone']}[/{zone_style[p['zone']]}]", mode_tag(p["mode"]), p["timestamp"]]
            for p in rep["points"]]
    table("Signal survey", ["Location", "Median", "Quality", "Zone", "Data", "Recorded"], rows)
    for a in rep["advice"]:
        out(f"[yellow]→ {safe(a)}[/yellow]")
    return EXIT_OK


# ── AI copilot ───────────────────────────────────────────────────

def cmd_ask(args) -> int:
    cfg = config.load()
    provider = get_provider()
    data = {"wifi": provider.interfaces().to_dict()}
    if not args.no_diagnose:
        if not args.json:
            out("[cyan]Running diagnostics to give the explanation real data…[/cyan]")
        from .apps import activity_snapshot

        data["diagnostics"] = run_diagnostics(p=Probes(wifi=provider.interfaces, activity=activity_snapshot)).to_dict()
    question = " ".join(args.question) if args.question else ""
    if args.preview:
        p = ai.preview(question, data, cfg["ai"])
        if args.json:
            emit_json(p)
        else:
            out(f"[bold]Would send to:[/bold] {safe(p['provider'])} / {safe(p['model'])}"
                + (f" at {safe(p['base_url'])}" if p.get("base_url") else ""))
            out("[bold]User message:[/bold]")
            print(p["user"])
        return EXIT_OK
    if cfg["ai"]["enabled"] and not args.json:
        status = "redacted" if not cfg["ai"]["send_identifiers"] else "[red]NOT redacted[/red]"
        out(f"[dim]Sending a summary of the measurements to {safe(cfg['ai']['provider'])} "
            f"(identifiers {status}). Preview it with --preview.[/dim]")
    res = ai.ask(question, data, cfg["ai"])
    if args.json:
        emit_json(res)
        return EXIT_OK
    a = res["answer"]
    src = f"AI ({safe(res.get('provider'))} {safe(res.get('model'))})" if res["source"] == "ai" else "rule-based"
    out(f"\n[bold]Answer[/bold] [dim]— {src}[/dim]")
    if res.get("reason"):
        out(f"[dim]{safe(res['reason'])}[/dim]")
    out(safe(a["summary"]))
    sections = (("observations", "Observed", lambda x: f"{x['fact']} — {x['evidence']}"),
                ("hypotheses", "Possible causes", lambda x: f"{x['cause']} ({x['confidence']}) — {x['evidence']}"),
                ("recommendations", "Suggested steps", lambda x: f"{x['action']} — {x['why']}"))
    for key, title, fmt in sections:
        if a[key]:
            out(f"\n[bold]{title}[/bold]")
            for item in a[key]:
                out(f"  • {safe(fmt(item))}")
    if a["limitations"]:
        out("\n[dim]Limitations: " + safe("; ".join(a["limitations"])) + "[/dim]")
    out("[dim]Suggestions are not applied automatically.[/dim]")
    return EXIT_OK


# ── distributed monitoring ───────────────────────────────────────

def cmd_hub(args) -> int:
    from . import hub

    if args.hub_action == "serve":
        return hub.serve_hub(args.host, args.port, args.tls_cert, args.tls_key, args.insecure_http)
    store = hub.TokenStore()
    if args.hub_action == "token":
        if args.token_action == "add":
            try:
                token = store.create(args.kind, args.name)
            except ValueError as exc:
                out(f"[red]{safe(exc)}[/red]")
                return EXIT_USAGE
            out(f"[green]Created {args.kind[:-1]} token '{safe(args.name)}'. Store it now; it is not shown again:[/green]")
            print(token)
            return EXIT_OK
        if args.token_action == "revoke":
            ok = store.revoke(args.kind, args.name)
            out("[green]Revoked[/green]" if ok else "[yellow]No such token[/yellow]")
            return EXIT_OK if ok else EXIT_USAGE
        emit_json(store.list())
        return EXIT_OK
    return EXIT_USAGE


def cmd_agent(args) -> int:
    from .collector import Collector
    from .history import History
    from . import hub

    token = os.environ.get(args.token_env or "")
    if not token:
        out(f"[red]Set the agent token in the environment variable {safe(args.token_env)}[/red]")
        return EXIT_USAGE
    try:
        reporter = hub.AgentReporter(args.hub, token, include_identifiers=args.include_identifiers,
                                     ca_file=args.ca_file)
    except ValueError as exc:
        out(f"[red]{safe(exc)}[/red]")
        return EXIT_USAGE
    if reporter.insecure and not args.insecure_http:
        out("[red]Refusing to send reports over plain HTTP to a remote hub. Use https:// or --insecure-http.[/red]")
        return EXIT_USAGE
    collector = Collector(get_provider(), History(max_samples=100), interval_s=args.interval, latency_every=1)
    out(f"Agent reporting to {safe(args.hub)} every {collector.interval_s:g} s "
        f"(identifiers {'included' if args.include_identifiers else 'omitted'}). Ctrl+C to stop.")
    try:
        while True:
            s = collector.tick()
            reporter.enqueue(s)
            if not reporter.flush():
                out(f"[yellow]{safe(reporter.last_error)} — {len(reporter.queue)} samples queued[/yellow]")
            if args.once:
                return EXIT_OK if not reporter.queue else EXIT_UNAVAILABLE
            time.sleep(collector.interval_s)
    except KeyboardInterrupt:
        out("\n[dim]Stopped.[/dim]")
    return EXIT_OK


# ── traffic / apps / connections (any connection type) ───────────

def _window_seconds(text: str) -> int:
    m = __import__("re").fullmatch(r"(\d+)\s*([smhd]?)", text.strip().lower())
    if not m:
        raise ValueError("window must look like 300, 5m, 1h or 1d")
    return int(m.group(1)) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def cmd_traffic(args) -> int:
    from . import traffic

    sampler = traffic.InterfaceSampler()
    first = sampler.sample()
    if first.get("mode") == "unavailable":
        out(f"[red]✗ {safe(first['error'])}[/red]")
        if first.get("hint"):
            out(f"  [yellow]→ {safe(first['hint'])}[/yellow]")
        return EXIT_UNAVAILABLE
    readings = []
    try:
        for i in range(args.count):
            time.sleep(max(0.5, args.interval))
            r = sampler.sample()
            readings.append(r)
            if args.json:
                print(json.dumps(r), flush=True)
                continue
            shown = [x for x in r["interfaces"] if args.all or (x["type"] not in ("loopback",) and
                                                                (x["is_up"] or x["primary"]))]
            rows = [[("★ " if x["primary"] else "") + safe(x["name"]), x["type"],
                     f"{x['link_speed_mbps']} Mbps" if x["link_speed_mbps"] else "—",
                     f"[green]{traffic.human_rate(x['rx_bps'])}[/green]",
                     f"[cyan]{traffic.human_rate(x['tx_bps'])}[/cyan]",
                     f"{traffic.human_bytes(x['bytes_recv_total'])} / {traffic.human_bytes(x['bytes_sent_total'])}"]
                    for x in shown]
            table(f"Traffic ({r['interval_s']} s average) — {r['timestamp']}",
                  ["Interface", "Type", "Link", "Download", "Upload", "Total ↓ / ↑ since boot"], rows)
    except KeyboardInterrupt:
        pass
    if not args.json and readings:
        out("[dim]★ = primary internet interface. Type is inferred from the interface name. "
            "Rates are measured from OS byte counters.[/dim]")
    return EXIT_OK


def cmd_apps(args) -> int:
    from . import apps, traffic

    try:
        window = _window_seconds(args.window)
    except ValueError as exc:
        out(f"[red]{safe(exc)}[/red]")
        return EXIT_USAGE
    if args.live and platform_system() == "Windows":
        tracker = apps.AppRateTracker()
        tracker.poll()
        if not args.json:
            out(f"[dim]Measuring per-app rates over {args.live_seconds} s (Windows updates its records about every "
                "30 s, so allow at least 60 s)…[/dim]")
        time.sleep(max(15, args.live_seconds))
        res = tracker.poll()
    else:
        res = apps.usage(window)
    if args.json:
        emit_json(dict(res, window_s=window))
        return EXIT_OK if res.get("mode") == "live" else EXIT_UNAVAILABLE
    if res.get("mode") != "live":
        out(f"[red]✗ {safe(res.get('error'))}[/red]")
        if res.get("hint"):
            out(f"  [yellow]→ {safe(res['hint'])}[/yellow]")
        return EXIT_UNAVAILABLE
    items = res["apps"][: args.top]
    realtime = res.get("realtime") or args.live
    rows = []
    for a in items:
        row = [safe(a["app"]), f"[green]{traffic.human_bytes(a['bytes_received'])}[/green]",
               f"[cyan]{traffic.human_bytes(a['bytes_sent'])}[/cyan]"]
        if realtime:
            row += [traffic.human_rate(a.get("rx_bps")), traffic.human_rate(a.get("tx_bps"))]
        row.append("yes" if a.get("running") else ("" if a.get("running") is None else "no"))
        rows.append(row)
    cols = ["App", "Downloaded", "Uploaded"] + (["↓ rate", "↑ rate"] if realtime else []) + ["Running"]
    if res.get("realtime"):
        title = f"Network use by app — last {res.get('sample_s')} s"
    elif args.live:
        title = f"Network use by app — last {res.get('interval_s')} s"
    else:
        title = f"Network use by app — last {args.window}"
    if not items:
        out("[yellow]No app used the network in this period (or the system has not recorded it yet).[/yellow]")
    else:
        table(title, cols, rows)
    out(f"[dim]Source: {safe(res['source'])}. {safe(res.get('note') or '')}[/dim]")
    return EXIT_OK


def platform_system() -> str:
    import platform as _p

    return _p.system()


def cmd_connections(args) -> int:
    from . import apps

    res = apps.connections()
    if res.get("mode") != "live":
        if args.json:
            emit_json(res)
        else:
            out(f"[red]✗ {safe(res.get('error'))}[/red]")
        return EXIT_UNAVAILABLE
    items = res["apps"]
    if args.app:
        needle = args.app.lower()
        items = [a for a in items if needle in a["app"].lower() or needle in a.get("process", "").lower()]
    names = {}
    if args.resolve:
        names = apps.reverse_dns([r["ip"] for a in items for r in a["remotes"]])
        for a in items:
            for r in a["remotes"]:
                r["hostname"] = names.get(r["ip"])
    if args.json:
        emit_json(dict(res, apps=items))
        return EXIT_OK
    for a in items[: args.top]:
        listen = f", listening on {len(a['listening'])} port(s)" if a["listening"] else ""
        out(f"\n[bold]{safe(a['app'])}[/bold] [dim]({safe(a['process'])}, pid {', '.join(map(str, a['pids'][:5]))})[/dim]"
            f" — {a['established']} active connection(s){listen}")
        for r in a["remotes"][:8]:
            host = f" {safe(r['hostname'])}" if r.get("hostname") else ""
            svc = f" ({r['service']})" if r["service"] else ""
            out(f"   → {r['ip']}:{r['port']}{svc}{host} [dim]{r['protocol']} {r['state'] or ''}"
                + (f" ×{r['count']}" if r["count"] > 1 else "") + "[/dim]")
        exposed = [l for l in a["listening"] if l["all_interfaces"]]
        if exposed:
            out(f"   [yellow]listening on all interfaces: {', '.join(l['address'] for l in exposed[:5])}[/yellow]")
    out(f"\n[dim]{safe(res['note'])}" + ("" if args.resolve else " Add --resolve to look up host names (sends DNS "
                                         "queries).") + "[/dim]")
    return EXIT_OK


def register(sub, common) -> None:
    url_help = f"URL of a running `wifi-monitor serve` (default {DEFAULT_URL})"

    tr = sub.add_parser("traffic", parents=[common], help="live upload/download per interface (Wi-Fi, Ethernet, VPN…)")
    tr.add_argument("-i", "--interval", type=float, default=1.0, help="seconds per reading (default 1)")
    tr.add_argument("-n", "--count", type=int, default=1, help="number of readings (default 1)")
    tr.add_argument("--all", action="store_true", help="include loopback and down interfaces")
    tr.set_defaults(func=cmd_traffic)

    ap = sub.add_parser("apps", parents=[common], help="which apps use the most internet (download/upload per app)")
    ap.add_argument("--window", default="1h", help="period on Windows, e.g. 5m, 1h, 1d (default 1h)")
    ap.add_argument("--live", action="store_true", help="Windows: measure current per-app rates")
    ap.add_argument("--live-seconds", type=int, default=60, help="measurement period for --live (default 60)")
    ap.add_argument("--top", type=int, default=15, help="number of apps to show (default 15)")
    ap.set_defaults(func=cmd_apps)

    cn = sub.add_parser("connections", parents=[common], help="which apps are connected to where, right now")
    cn.add_argument("--app", help="only apps whose name contains this text")
    cn.add_argument("--resolve", action="store_true", help="reverse-DNS remote addresses (sends DNS queries)")
    cn.add_argument("--top", type=int, default=20, help="number of apps to show (default 20)")
    cn.set_defaults(func=cmd_connections)

    h = sub.add_parser("history", parents=[common], help="statistics and events from a running server")
    h.add_argument("--window", type=int, default=3600, help="seconds to summarise (default 3600)")
    h.add_argument("--export", choices=["csv", "json"], help="download the full history")
    h.add_argument("-o", "--output", help="file for --export")
    h.add_argument("--url", default=DEFAULT_URL, help=url_help)
    h.set_defaults(func=cmd_history)

    a = sub.add_parser("alerts", parents=[common], help="alerts raised by a running server")
    a.add_argument("--active", action="store_true", help="only unacknowledged alerts")
    a.add_argument("--ack", type=int, metavar="ID", help="acknowledge an alert")
    a.add_argument("--clear", action="store_true", help="delete all alerts")
    a.add_argument("--url", default=DEFAULT_URL, help=url_help)
    a.set_defaults(func=cmd_alerts)

    d = sub.add_parser("devices", parents=[common], help="devices on the local network (passive by default)")
    d.add_argument("--probe", action="store_true", help="actively ping the local private /24 first (opt-in)")
    d.add_argument("--name", nargs=2, metavar=("MAC", "NAME"), help="give a device a friendly name")
    d.add_argument("--forget", metavar="MAC", help="remove a device from the known list")
    d.set_defaults(func=cmd_devices)

    sub.add_parser("security", parents=[common], help="security observations for this connection") \
        .set_defaults(func=cmd_security)
    sub.add_parser("channels", parents=[common], help="channel congestion and recommendations") \
        .set_defaults(func=cmd_channels)

    st = sub.add_parser("speedtest", parents=[common], help="download/upload throughput test (uses data)")
    st.add_argument("--max-mb", type=int, default=50, help="data budget in MB (5–500, default 50)")
    st.set_defaults(func=cmd_speedtest)

    sv = sub.add_parser("survey", parents=[common], help="record signal at locations to find weak spots")
    sv.add_argument("action", choices=["add", "report", "clear"])
    sv.add_argument("label", nargs="?", help="location name for 'add'")
    sv.add_argument("--samples", type=int, default=5, help="readings per location (default 5)")
    sv.set_defaults(func=cmd_survey)

    k = sub.add_parser("ask", parents=[common], help="explain the connection in plain language (AI optional)")
    k.add_argument("question", nargs="*", help="e.g. why are my video calls unstable?")
    k.add_argument("--preview", action="store_true", help="show exactly what would be sent to the AI provider")
    k.add_argument("--no-diagnose", action="store_true", help="skip running diagnostics first")
    k.set_defaults(func=cmd_ask)

    hb = sub.add_parser("hub", help="central hub for remote agents (authenticated)")
    hsub = hb.add_subparsers(dest="hub_action", required=True)
    hs = hsub.add_parser("serve", help="run the hub")
    hs.add_argument("--host", default="127.0.0.1")
    hs.add_argument("--port", type=int, default=8766)
    hs.add_argument("--tls-cert")
    hs.add_argument("--tls-key")
    hs.add_argument("--insecure-http", action="store_true", help="allow plain HTTP on a network address")
    ht = hsub.add_parser("token", help="manage agent and viewer tokens")
    ht.add_argument("token_action", choices=["add", "revoke", "list"])
    ht.add_argument("kind", nargs="?", choices=["agents", "viewers"], default="agents")
    ht.add_argument("name", nargs="?", default="")
    hb.set_defaults(func=cmd_hub)

    ag = sub.add_parser("agent", help="report measurements to a hub")
    ag.add_argument("--hub", required=True, help="hub URL, e.g. https://monitor.lan:8766")
    ag.add_argument("--token-env", default="WIFI_MONITOR_AGENT_TOKEN", help="env var holding the agent token")
    ag.add_argument("--interval", type=float, default=60, help="seconds between reports (default 60)")
    ag.add_argument("--include-identifiers", action="store_true", help="also send SSID/BSSID")
    ag.add_argument("--ca-file", help="CA bundle for a hub with a private certificate")
    ag.add_argument("--insecure-http", action="store_true", help="allow http:// to a remote hub")
    ag.add_argument("--once", action="store_true", help="send one sample and exit")
    ag.set_defaults(func=cmd_agent)

