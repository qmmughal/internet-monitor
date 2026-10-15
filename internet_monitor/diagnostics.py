"""Staged connectivity troubleshooter.

1. link      – is there a default route (and a connected Wi-Fi interface)?
2. gateway   – does the router answer (ICMP, then TCP fallback)?
3. dns       – does the system resolver answer?
4. https     – do the configured HTTPS endpoints answer?
5. latency   – TCP handshake latency/jitter to IP endpoints (independent of DNS).

``run_diagnostics`` collects evidence; ``classify`` turns evidence into
findings with explicit rules. No setting is ever changed.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional, Tuple

from . import netinfo, probes
from .models import ProviderResult, utc_now

OK, INFO, WARNING, CRITICAL = "ok", "info", "warning", "critical"


@dataclass
class DiagnosticsConfig:
    dns_hosts: Tuple[str, ...] = ("www.google.com", "www.cloudflare.com", "www.microsoft.com")
    https_endpoints: Tuple[Tuple[str, Optional[int]], ...] = (
        ("https://www.google.com/generate_204", 204),
        ("https://cp.cloudflare.com/generate_204", 204),
        ("https://www.microsoft.com/", None),
    )
    tcp_targets: Tuple[Tuple[str, int], ...] = (("1.1.1.1", 443), ("8.8.8.8", 443))
    ping_count: int = 4
    probe_timeout_s: float = 2.0
    tcp_samples: int = 5
    # thresholds
    gateway_latency_warn_ms: float = 50.0
    external_latency_warn_ms: float = 150.0
    jitter_warn_ms: float = 30.0
    dns_slow_ms: float = 300.0
    weak_signal_dbm: int = -75


@dataclass
class Finding:
    severity: str
    title: str
    evidence: List[str]
    likely_cause: Optional[str] = None
    next_step: Optional[str] = None
    confidence: Optional[str] = None  # "high" | "medium" | "low"


@dataclass
class Report:
    started: str
    finished: str
    overall: str  # "healthy" | "degraded" | "offline"
    duration_ms: float
    evidence: dict
    findings: List[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Probes:
    """Injection points so the engine can be tested without a network."""

    route: Callable[[], ProviderResult] = netinfo.default_route
    wifi: Optional[Callable[[], ProviderResult]] = None
    ping: Callable[..., probes.LatencySample] = probes.ping
    tcp_connect: Callable[..., dict] = probes.tcp_connect
    tcp_latency: Callable[..., probes.LatencySample] = probes.tcp_latency
    resolve: Callable[..., dict] = probes.resolve
    https: Callable[..., dict] = probes.https_check
    activity: Optional[Callable[[], dict]] = None  # current traffic + top apps (optional)


def run_diagnostics(config: Optional[DiagnosticsConfig] = None, p: Optional[Probes] = None, on_stage=None) -> Report:
    cfg = config or DiagnosticsConfig()
    p = p or Probes()
    started, t0 = utc_now(), time.perf_counter()
    ev: dict = {}

    def stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    stage("link")
    route = p.route()
    ev["link"] = route.to_dict()
    if p.wifi is not None:
        wifi = p.wifi()
        ev["wifi"] = wifi.to_dict()

    gateway = (route.data or {}).get("gateway") if route.ok else None
    if gateway:
        stage("gateway")
        icmp = p.ping(gateway, count=cfg.ping_count, timeout_s=min(cfg.probe_timeout_s, 2.0))
        gw = {"icmp": icmp.to_dict(), "tcp": None}
        if icmp.received == 0:
            for port in (53, 80, 443):
                r = p.tcp_connect(gateway, port, timeout_s=cfg.probe_timeout_s)
                gw["tcp"] = dict(r, port=port)
                if r.get("reachable"):
                    break
        ev["gateway"] = gw

    # Upstream probes run even without a known gateway, so "offline" is never assumed.
    stage("dns")
    ev["dns"] = [p.resolve(h, timeout_s=cfg.probe_timeout_s + 1) for h in cfg.dns_hosts]
    stage("https")
    ev["https"] = [p.https(u, expect_status=s, timeout_s=cfg.probe_timeout_s + 3) for u, s in cfg.https_endpoints]
    stage("latency")
    ev["latency"] = [
        p.tcp_latency(h, port, count=cfg.tcp_samples, timeout_s=cfg.probe_timeout_s).to_dict()
        for h, port in cfg.tcp_targets
    ]

    if p.activity is not None:
        stage("activity")
        try:
            ev["activity"] = p.activity()
        except Exception as exc:  # activity is context, never a reason to fail diagnostics
            ev["activity"] = {"error": str(exc)}

    findings = classify(ev, cfg)
    overall = "offline" if any(f.severity == CRITICAL for f in findings) else (
        "degraded" if any(f.severity == WARNING for f in findings) else "healthy"
    )
    return Report(
        started=started,
        finished=utc_now(),
        overall=overall,
        duration_ms=round((time.perf_counter() - t0) * 1000),
        evidence=ev,
        findings=findings,
    )


def _wifi_iface(ev: dict) -> Optional[dict]:
    wifi = ev.get("wifi")
    if not wifi or wifi.get("mode") == "unavailable":
        return None
    data = wifi.get("data")
    if isinstance(data, list):
        return next((i for i in data if i.get("connected")), None)
    return data if isinstance(data, dict) and data.get("connected") else None


def classify(ev: dict, cfg: DiagnosticsConfig) -> List[Finding]:
    """Turn collected evidence into findings. Pure function: no I/O."""
    f: List[Finding] = []
    link = ev.get("link", {})
    wifi = _wifi_iface(ev)

    dns = ev.get("dns", [])
    https = ev.get("https", [])
    lat = ev.get("latency", [])
    dns_ok = [d for d in dns if d.get("ok")]
    https_ok = [h for h in https if h.get("ok")]
    tcp_ok = [s for s in lat if s.get("received", 0) > 0]
    internet_ok = bool(https_ok) or bool(tcp_ok)
    captive = [h for h in https if h.get("captive_portal_suspected")]

    # ── Stage 1: link ────────────────────────────────────────────
    if link.get("mode") == "unavailable":
        if not internet_ok and not dns_ok:
            wifi_state = ev.get("wifi", {})
            evidence = ["No IPv4 default gateway is configured.", "No DNS, HTTPS or TCP probe succeeded."]
            if wifi_state and wifi_state.get("error"):
                evidence.append(f"Wi-Fi: {wifi_state['error']}.")
            f.append(Finding(CRITICAL, "Not connected to a network", evidence,
                             "The computer has no active network connection (Wi-Fi or wired).",
                             "Connect to Wi-Fi or plug in a cable, then run diagnostics again.", "high"))
            return f
        f.append(Finding(INFO, "Default gateway could not be determined",
                         [f"Gateway lookup failed ({link.get('error')}), but upstream probes responded."],
                         "Unusual routing (VPN, IPv6-only) or an unsupported platform.",
                         None, "medium"))

    # ── Signal (informational context) ──────────────────────────
    wifi_state = ev.get("wifi")
    if wifi_state and not wifi:
        f.append(Finding(INFO, "Wi-Fi details unavailable",
                         [f"Wi-Fi: {wifi_state.get('error') or 'no connected Wi-Fi interface'}."]
                         + ([wifi_state["hint"]] if wifi_state.get("hint") else []),
                         None if wifi_state.get("hint") else
                         "This device may be using a wired connection, or the OS withheld Wi-Fi data.",
                         None, "high"))
    if wifi and wifi.get("signal_dbm") and wifi["signal_dbm"].get("value") is not None:
        sig = wifi["signal_dbm"]
        if sig["value"] < cfg.weak_signal_dbm:
            qual = "estimated from the OS signal percentage" if sig["mode"] == "estimated" else "measured"
            f.append(Finding(WARNING, "Weak Wi-Fi signal",
                             [f"Signal is {sig['value']} dBm ({qual}); below {cfg.weak_signal_dbm} dBm is weak."],
                             "Distance or obstacles between this device and the access point.",
                             "Move closer to the router or access point, or consider a mesh node/extender.",
                             "medium" if sig["mode"] == "estimated" else "high"))

    # ── Stage 2: gateway ────────────────────────────────────────
    gw = ev.get("gateway") or {}
    icmp = gw.get("icmp") or {}
    tcp = gw.get("tcp")
    gw_icmp_ok = icmp.get("received", 0) > 0
    gw_tcp_ok = bool(tcp and tcp.get("reachable"))
    gw_reachable = gw_icmp_ok or gw_tcp_ok
    gateway_ip = (link.get("data") or {}).get("gateway")

    # ── Stage 3–5: upstream ─────────────────────────────────────
    if gateway_ip and not gw_reachable and not internet_ok:
        f.append(Finding(CRITICAL, "Cannot reach the router or the internet",
                         [f"Gateway {gateway_ip} did not answer ICMP ping or TCP on ports 53/80/443.",
                          "No HTTPS endpoint and no TCP latency target responded."],
                         "The Wi-Fi/LAN link to the router is down or the router is not responding.",
                         "Check the Wi-Fi connection on this device, then restart the router.", "high"))
        return f
    if gateway_ip and not gw_reachable and internet_ok:
        f.append(Finding(INFO, "Router does not answer ping",
                         [f"Gateway {gateway_ip} ignored ICMP and TCP probes, but the internet is reachable."],
                         "Many routers block ping; this is usually not a problem.", None, "high"))

    if gw_icmp_ok:
        loss, med = icmp.get("loss_pct"), icmp.get("median_ms")
        if loss and loss > 0:
            f.append(Finding(WARNING, "Packet loss to the router",
                             [f"{loss}% of {icmp.get('sent')} ICMP pings to {gateway_ip} were lost."],
                             "Wireless interference, weak signal, or an overloaded router.",
                             "Move closer to the router or try a less congested channel/band (5 GHz).",
                             "medium" if icmp.get("sent", 0) < 10 else "high"))
        if med is not None and med > cfg.gateway_latency_warn_ms:
            f.append(Finding(WARNING, "High latency to the router",
                             [f"Median round-trip to {gateway_ip} is {med} ms (local links are usually under 10 ms)."],
                             "Congestion or interference on the local Wi-Fi link.",
                             "Check for large uploads/downloads on the network and try moving closer to the router.",
                             "medium"))

    if captive:
        f.append(Finding(WARNING, "Captive portal or proxy suspected",
                         [f"{h['url']} returned HTTP {h['status']} instead of the expected response." for h in captive],
                         "The network requires a sign-in page, or traffic passes through a proxy.",
                         "Open a browser and look for a network sign-in page.", "medium"))

    if not dns_ok and dns:
        if tcp_ok:
            f.append(Finding(CRITICAL, "DNS resolution is failing",
                             [f"None of {len(dns)} hostnames resolved ({_errors(dns)}).",
                              f"Direct TCP connections to {', '.join(s['target'] for s in tcp_ok)} succeeded, so the internet path works."],
                             "The configured DNS resolver is not responding or is misconfigured.",
                             "Inspect this device's and the router's DNS settings and test a known public resolver.",
                             "high"))
        else:
            f.append(Finding(CRITICAL, "No internet access beyond the router",
                             ["The router is reachable." if gw_reachable else "Router reachability is unknown.",
                              "DNS lookups failed and direct TCP connections to public IPs failed."],
                             "The internet connection (modem/ISP) is down, or the router has no upstream link.",
                             "Check the modem/router internet status lights, restart the modem, or contact the ISP.",
                             "high" if gw_reachable else "medium"))
        return f

    if dns and not https_ok and not captive:
        if tcp_ok:
            f.append(Finding(WARNING, "HTTPS endpoints are failing",
                             [f"DNS works and TCP to public IPs works, but no HTTPS test endpoint responded ({_errors(https)})."],
                             "A firewall, proxy, TLS inspection or the test endpoints themselves.",
                             "Try another website; check firewall/antivirus web filtering and proxy settings.", "medium"))
        else:
            f.append(Finding(CRITICAL, "No internet access beyond the router",
                             ["DNS answers (possibly from the router's cache), but no HTTPS endpoint or public IP responded."],
                             "The upstream internet connection (modem/ISP) is down.",
                             "Check the modem status lights, restart it, or contact the ISP.", "medium"))
        return f

    failed_endpoints = [h for h in https if not h.get("ok") and not h.get("captive_portal_suspected")]
    if https_ok and failed_endpoints:
        f.append(Finding(INFO, "Some test endpoints failed",
                         [f"{h['url']}: {h.get('error') or 'HTTP ' + str(h.get('status'))}" for h in failed_endpoints],
                         "A specific service is unreachable; general internet access works.", None, "high"))

    slow_dns = [d for d in dns_ok if d.get("ms") and d["ms"] > cfg.dns_slow_ms]
    if slow_dns and len(slow_dns) == len(dns_ok):
        f.append(Finding(WARNING, "Slow DNS responses",
                         [f"{d['host']}: {d['ms']} ms" for d in slow_dns],
                         "The DNS resolver is slow or distant.",
                         "Compare with another resolver; slow DNS delays every new connection.", "medium"))

    medians = [s["median_ms"] for s in tcp_ok if s.get("median_ms") is not None]
    if medians and min(medians) > cfg.external_latency_warn_ms:
        f.append(Finding(WARNING, "High internet latency",
                         [f"Best median TCP handshake time is {min(medians)} ms."]
                         + _gateway_context(icmp, gw_icmp_ok),
                         _latency_cause(icmp, gw_icmp_ok, cfg),
                         "Check for heavy usage on the network; if the router link is fast, contact the ISP.",
                         "medium"))
    jitters = [s["jitter_ms"] for s in tcp_ok if s.get("jitter_ms") is not None]
    if jitters and min(jitters) > cfg.jitter_warn_ms:
        f.append(Finding(WARNING, "Unstable latency (jitter)",
                         [f"Lowest jitter across targets is {min(jitters)} ms; over {cfg.jitter_warn_ms} ms hurts calls and games."],
                         "Congestion on the Wi-Fi link or upstream.",
                         "Pause large transfers and retest; prefer 5 GHz or a wired connection for calls.", "medium"))
    lossy = [s for s in lat if s.get("sent") and 0 < s.get("received", 0) < s["sent"]]
    if lossy and len(lossy) == len(lat):
        f.append(Finding(WARNING, "Intermittent connection failures",
                         [f"{s['target']}: {s['sent'] - s['received']} of {s['sent']} TCP handshakes failed" for s in lossy],
                         "Packet loss on the Wi-Fi link or upstream.",
                         "Run diagnostics again; if it persists, check signal strength and the router.", "low"))

    _activity_findings(ev.get("activity"), f)

    if not any(x.severity in (WARNING, CRITICAL) for x in f):
        evidence = []
        if gw_icmp_ok and icmp.get("median_ms") is not None:
            evidence.append(f"Router answered in {icmp['median_ms']} ms median with {icmp.get('loss_pct')}% loss.")
        if dns_ok:
            evidence.append(f"{len(dns_ok)}/{len(dns)} DNS lookups succeeded.")
        if https_ok:
            evidence.append(f"{len(https_ok)}/{len(https)} HTTPS endpoints responded.")
        if medians:
            evidence.append(f"Best internet handshake latency {min(medians)} ms.")
        if wifi:
            sig = wifi.get("signal_dbm") or {}
            parts = [f"Wi-Fi: {wifi.get('ssid') or 'connected'}"]
            if sig.get("value") is not None:
                parts.append(f"{sig['value']} dBm ({sig.get('mode')})")
            if wifi.get("band"):
                parts.append(f"{wifi['band']} channel {wifi.get('channel')}")
            evidence.append(", ".join(parts) + ".")
        f.insert(0, Finding(OK, "No connectivity problems detected", evidence, confidence="high"))
    return f


def _errors(items: list) -> str:
    errs = sorted({str(i.get("error") or ("HTTP " + str(i.get("status")))) for i in items})
    return ", ".join(errs[:3])


def _gateway_context(icmp: dict, gw_ok: bool) -> List[str]:
    if gw_ok and icmp.get("median_ms") is not None:
        return [f"Router round-trip is {icmp['median_ms']} ms."]
    return []


def _latency_cause(icmp: dict, gw_ok: bool, cfg: DiagnosticsConfig) -> str:
    if gw_ok and icmp.get("median_ms") is not None:
        if icmp["median_ms"] > cfg.gateway_latency_warn_ms:
            return "Most of the delay is on the local Wi-Fi link."
        return "The local link is fast, so the delay is upstream (ISP or beyond)."
    return "Unknown whether the delay is local or upstream (router does not answer ping)."


BUSY_BPS = 250_000  # ~2 Mbit/s


def _rate(bps) -> str:
    from .traffic import human_rate

    return human_rate(bps) if bps is not None else "unknown"


def _activity_findings(act: Optional[dict], f: List[Finding]) -> None:
    """Report heavy traffic during the check and link it to latency problems."""
    if not act or act.get("error"):
        return
    t = act.get("traffic") or {}
    rx, tx = t.get("rx_bps"), t.get("tx_bps")
    if rx is None and tx is None:
        return
    busy = (rx or 0) >= BUSY_BPS or (tx or 0) >= BUSY_BPS
    apps = act.get("top_apps") or []
    evidence = [f"{t.get('primary') or 'Primary interface'} ({t.get('primary_type') or 'unknown type'}): "
                f"downloading {_rate(rx)}, uploading {_rate(tx)} during the check."]
    if apps:
        evidence.append("Busiest apps in the last 5 minutes: " + "; ".join(
            f"{a['app']} ↓{a['bytes_received'] / 1e6:.1f} MB ↑{a['bytes_sent'] / 1e6:.1f} MB" for a in apps[:3]) + ".")
    if busy:
        f.append(Finding(INFO, "Heavy network use during the check", evidence,
                         "Other traffic from this computer shares the connection and can slow everything else.",
                         "Pause large transfers (cloud sync, updates, streaming) and run the check again.", "medium"))
        for x in f:
            if x.severity == WARNING and ("latency" in x.title.lower() or "jitter" in x.title.lower()):
                x.evidence.append(f"This computer was transferring {_rate(rx)} down / {_rate(tx)} up at the time.")
                x.likely_cause = (x.likely_cause or "") + " Heavy traffic from this computer may be a cause."
    else:
        f.append(Finding(INFO, "Network activity during the check", evidence, None, None, "high"))
