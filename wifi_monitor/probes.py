"""Bounded network probes used by the diagnostics engine.

Every probe has an explicit timeout and returns data instead of raising.
Only IP literals are passed to ``ping``; hostnames go through the resolver.
"""

from __future__ import annotations

import errno
import ipaddress
import platform
import re
import socket
import ssl
import statistics
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import List, Optional

from .runner import run

_REPLY_TIME = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)


@dataclass
class LatencySample:
    target: str
    method: str  # "icmp" | "tcp"
    sent: int
    received: int
    rtts_ms: List[float] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def loss_pct(self) -> Optional[float]:
        return None if self.sent == 0 else round(100.0 * (self.sent - self.received) / self.sent, 1)

    @property
    def median_ms(self) -> Optional[float]:
        return round(statistics.median(self.rtts_ms), 1) if self.rtts_ms else None

    @property
    def jitter_ms(self) -> Optional[float]:
        """Mean absolute difference between consecutive samples (needs ≥3 samples)."""
        r = self.rtts_ms
        if len(r) < 3:
            return None
        return round(sum(abs(b - a) for a, b in zip(r, r[1:])) / (len(r) - 1), 1)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update(loss_pct=self.loss_pct, median_ms=self.median_ms, jitter_ms=self.jitter_ms)
        return d


def parse_ping_output(text: str) -> List[float]:
    """Extract round-trip times from reply lines. Reply lines contain 'TTL' in every locale."""
    rtts = []
    for line in text.splitlines():
        if "ttl" not in line.lower():
            continue
        m = _REPLY_TIME.search(line)
        if m:
            rtts.append(float(m.group(1).replace(",", ".")))
    return rtts


def ping(host: str, count: int = 4, timeout_s: float = 1.0, system: Optional[str] = None, runner=run) -> LatencySample:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return LatencySample(host, "icmp", 0, 0, error="ping target must be an IP address")
    count = max(1, min(int(count), 10))
    system = system or platform.system()
    if system == "Windows":
        args = ["ping", "-n", str(count), "-w", str(int(timeout_s * 1000)), host]
    elif system == "Darwin":
        args = ["ping", "-c", str(count), "-W", str(int(timeout_s * 1000)), host]
    else:
        args = ["ping", "-c", str(count), "-W", str(max(1, int(timeout_s))), "-i", "0.5", host]
    cmd = runner(args, timeout=count * (timeout_s + 1.0) + 2)
    if cmd.error:
        return LatencySample(host, "icmp", 0, 0, error=f"ping unavailable ({cmd.error})")
    rtts = parse_ping_output(cmd.stdout)
    return LatencySample(host, "icmp", count, len(rtts), rtts)


def tcp_connect(host: str, port: int, timeout_s: float = 2.0) -> dict:
    """One TCP handshake. A refused connection still proves the host answered."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
        return {"reachable": True, "open": True, "rtt_ms": round((time.perf_counter() - start) * 1000, 1)}
    except ConnectionRefusedError:
        return {"reachable": True, "open": False, "rtt_ms": round((time.perf_counter() - start) * 1000, 1)}
    except socket.timeout:
        return {"reachable": False, "open": False, "error": "timeout"}
    except OSError as exc:
        if exc.errno in (errno.ECONNREFUSED, getattr(errno, "WSAECONNREFUSED", -1)):
            return {"reachable": True, "open": False, "rtt_ms": round((time.perf_counter() - start) * 1000, 1)}
        return {"reachable": False, "open": False, "error": exc.strerror or str(exc)}


def tcp_latency(host: str, port: int = 443, count: int = 5, timeout_s: float = 2.0) -> LatencySample:
    sample = LatencySample(f"{host}:{port}", "tcp", 0, 0)
    for _ in range(max(1, min(count, 10))):
        sample.sent += 1
        r = tcp_connect(host, port, timeout_s)
        if r.get("open"):
            sample.received += 1
            sample.rtts_ms.append(r["rtt_ms"])
        elif r.get("error"):
            sample.error = r["error"]
    return sample


def resolve(hostname: str, timeout_s: float = 3.0) -> dict:
    """Resolve via the system resolver, bounded by a timeout (getaddrinfo itself has none)."""
    box: dict = {}

    def work() -> None:
        start = time.perf_counter()
        try:
            infos = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
            box["addresses"] = sorted({i[4][0] for i in infos})
        except socket.gaierror as exc:
            box["error"] = exc.strerror or str(exc)
        box["ms"] = round((time.perf_counter() - start) * 1000, 1)

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout_s)
    if t.is_alive():
        return {"host": hostname, "ok": False, "error": "timeout", "ms": None}
    ok = bool(box.get("addresses"))
    return {"host": hostname, "ok": ok, "ms": box.get("ms"), "addresses": box.get("addresses", [])[:4], "error": box.get("error")}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - urllib API
        return None


def https_check(url: str, expect_status: Optional[int] = None, timeout_s: float = 5.0) -> dict:
    """GET ``url`` without following redirects. A redirect from a 204 endpoint suggests a captive portal."""
    if not url.startswith("https://"):
        return {"url": url, "ok": False, "error": "only https:// endpoints are allowed"}
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, headers={"User-Agent": "wifi-monitor-diagnostics"})
    start = time.perf_counter()
    status, error = None, None
    try:
        with opener.open(req, timeout=timeout_s) as resp:
            status = resp.status
            resp.read(1024)
    except urllib.error.HTTPError as exc:
        status = exc.code
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            error = "tls_certificate_invalid"
        elif isinstance(reason, socket.timeout) or "timed out" in str(reason):
            error = "timeout"
        elif isinstance(reason, socket.gaierror):
            error = "dns_failure"
        else:
            error = str(reason)
    except (socket.timeout, TimeoutError):
        error = "timeout"
    except (ssl.SSLError, OSError) as exc:
        error = f"connection_error: {exc}"
    ms = round((time.perf_counter() - start) * 1000, 1)
    ok = status is not None and (expect_status is None or status == expect_status) and status < 400
    captive = expect_status is not None and status is not None and status != expect_status and 200 <= status < 400
    return {"url": url, "ok": ok, "status": status, "ms": ms if status is not None else None, "error": error, "captive_portal_suspected": captive}
