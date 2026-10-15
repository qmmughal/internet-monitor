"""Throughput test against Cloudflare's public speed-test endpoints.

* Download: GET https://speed.cloudflare.com/__down?bytes=N
* Upload:   POST https://speed.cloudflare.com/__up

Single HTTPS connection per transfer, bounded by data volume and time. It
measures this device's path to the nearest Cloudflare edge, which is a good
proxy for internet throughput but can under-report very fast links (one TCP
stream) and includes Wi-Fi and router limits. Uses up to ~``max_mb`` MB of data.
"""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.request
from typing import Callable, List, Optional

from . import probes
from .models import utc_now

DOWN_URL = "https://speed.cloudflare.com/__down?bytes={n}"
UP_URL = "https://speed.cloudflare.com/__up"
CHUNK = 64 * 1024


def _opener():
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl.create_default_context()))


def _mbps(nbytes: int, seconds: float) -> Optional[float]:
    return round(nbytes * 8 / seconds / 1e6, 1) if seconds > 0 and nbytes > 0 else None


def download(nbytes: int, timeout_s: float = 15.0, deadline_s: float = 12.0, opener=None,
             on_progress: Optional[Callable[[float], None]] = None) -> dict:
    req = urllib.request.Request(DOWN_URL.format(n=int(nbytes)), headers={"User-Agent": "wifi-monitor-speedtest"})
    got, start, first_byte = 0, time.perf_counter(), None
    try:
        with (opener or _opener()).open(req, timeout=timeout_s) as resp:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                if first_byte is None:
                    first_byte = time.perf_counter()
                got += len(chunk)
                elapsed = time.perf_counter() - first_byte
                if on_progress and elapsed > 0.2:
                    on_progress(_mbps(got, elapsed) or 0.0)
                if elapsed > deadline_s:
                    break
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        return {"bytes": got, "error": str(getattr(exc, "reason", exc))}
    end = time.perf_counter()
    secs = end - (first_byte or start)
    return {"bytes": got, "seconds": round(secs, 3), "mbps": _mbps(got, secs), "error": None}


def upload(nbytes: int, timeout_s: float = 20.0, opener=None) -> dict:
    payload = b"\0" * int(nbytes)
    req = urllib.request.Request(UP_URL, data=payload, method="POST",
                                 headers={"User-Agent": "wifi-monitor-speedtest",
                                          "Content-Type": "application/octet-stream"})
    start = time.perf_counter()
    try:
        with (opener or _opener()).open(req, timeout=timeout_s) as resp:
            resp.read(1024)
    except (urllib.error.URLError, OSError, ssl.SSLError) as exc:
        return {"bytes": 0, "error": str(getattr(exc, "reason", exc))}
    secs = time.perf_counter() - start
    return {"bytes": len(payload), "seconds": round(secs, 3), "mbps": _mbps(len(payload), secs), "error": None}


def run(max_mb: int = 50, latency_fn=probes.tcp_latency, down_fn=download, up_fn=upload,
        on_phase: Optional[Callable[[str], None]] = None) -> dict:
    """Latency, then download and upload with growing sizes until the data budget or time is used."""
    max_mb = max(5, min(int(max_mb), 500))
    budget = max_mb * 1_000_000
    started = utc_now()

    def phase(p: str) -> None:
        if on_phase:
            on_phase(p)

    phase("latency")
    lat = latency_fn("speed.cloudflare.com", 443, count=8, timeout_s=2.0)

    phase("download")
    downs: List[dict] = []
    used = 0
    for size in (1_000_000, 10_000_000, 25_000_000, 50_000_000, 100_000_000):
        if used + size > budget * 0.7:
            break
        r = down_fn(size)
        downs.append(dict(r, requested=size))
        used += r.get("bytes", 0)
        if r.get("error") or (r.get("seconds") or 0) > 5:
            break

    phase("upload")
    ups: List[dict] = []
    for size in (1_000_000, 5_000_000, 15_000_000):
        if used + size > budget:
            break
        r = up_fn(size)
        ups.append(dict(r, requested=size))
        used += r.get("bytes", 0)
        if r.get("error") or (r.get("seconds") or 0) > 5:
            break

    def best(results: List[dict]) -> Optional[float]:
        # The largest successful transfer is least affected by TCP slow start.
        ok = [r for r in results if r.get("mbps") and r.get("bytes", 0) >= 1_000_000]
        return max(ok, key=lambda r: r["bytes"])["mbps"] if ok else None

    errors = [r["error"] for r in downs + ups if r.get("error")]
    return {
        "started": started,
        "finished": utc_now(),
        "mode": "live" if best(downs) or best(ups) else "unavailable",
        "server": "speed.cloudflare.com (nearest Cloudflare edge)",
        "latency": {"median_ms": lat.median_ms, "jitter_ms": lat.jitter_ms, "loss_pct": lat.loss_pct,
                    "method": "TCP handshake"},
        "download_mbps": best(downs),
        "upload_mbps": best(ups),
        "transfers": {"download": downs, "upload": ups},
        "data_used_mb": round(used / 1e6, 1),
        "errors": errors[:3],
        "caveats": [
            "Single connection; very fast links (>500 Mbps) may be under-reported.",
            "Measures the whole path: Wi-Fi, router and ISP. Other traffic on the network lowers results.",
        ],
    }
