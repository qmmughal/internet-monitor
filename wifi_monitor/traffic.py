"""Live traffic per network interface — for any connection type.

Works for Wi-Fi, Ethernet, VPN, mobile broadband and virtual adapters using
the OS byte counters (via psutil). Rates are computed from two counter
readings, so they are real measurements of everything this computer sends and
receives on each interface.

The interface *type* is inferred from its name/description and labelled as
such; the *primary* interface is the one that owns the local IP of the default
route.
"""

from __future__ import annotations

import re
import socket
import threading
import time
from typing import List, Optional

from . import netinfo
from .models import LIVE, UNAVAILABLE, utc_now

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover - exercised when psutil is missing
    psutil = None

PSUTIL_HINT = 'Install psutil for traffic and per-app features: pip install "psutil>=5.9"'

_TYPE_RULES = [
    ("loopback", r"^lo$|loopback"),
    ("vpn", r"vpn|wireguard|^wg\d|tailscale|zerotier|^tun|^tap|^utun|^ppp|openvpn|anyconnect|fortinet|nordlynx|ipsec"),
    ("virtual", r"vethernet|virtual|hyper-v|vmware|vmnet|virtualbox|vbox|docker|^veth|^br-|bridge|wsl|^virbr|npcap|^awdl|^llw|^anpi|^ap\d|^bridge"),
    ("cellular", r"cellular|mobile|wwan|lte|5g|^rmnet|^pdp_ip"),
    ("wifi", r"wi-?fi|wlan|wireless|802\.11|^wl|^ath\d|airport"),
    ("ethernet", r"ethernet|^eth\d|^en[ops]|^enx|^em\d|^en\d|lan|gigabit|realtek|intel.*connection|usb.*(10/100|gbe)"),
]


def classify(name: str, description: str = "") -> str:
    text = f"{name} {description}".strip().lower()
    for kind, pattern in _TYPE_RULES:
        if re.search(pattern, text):
            return kind
    return "other"


class InterfaceSampler:
    """Keeps the previous counter reading and returns rates since then."""

    def __init__(self, counters_fn=None, stats_fn=None, addrs_fn=None, clock=time.monotonic) -> None:
        self._has_source = counters_fn is not None or psutil is not None
        self._counters = counters_fn or (lambda: psutil.net_io_counters(pernic=True))
        self._stats = stats_fn or (lambda: psutil.net_if_stats())
        self._addrs = addrs_fn or (lambda: psutil.net_if_addrs())
        self._clock = clock
        self._prev: Optional[tuple] = None
        self._lock = threading.Lock()

    @staticmethod
    def available() -> bool:
        return psutil is not None

    def sample(self, min_interval: float = 0.0) -> dict:
        if not self._has_source:
            return {"mode": UNAVAILABLE, "error": "psutil is not installed", "hint": PSUTIL_HINT}
        with self._lock:
            now = self._clock()
            try:
                cur = self._counters()
            except Exception as exc:  # psutil raises various OS errors
                return {"mode": UNAVAILABLE, "error": f"cannot read interface counters: {exc}"}
            if self._prev and now - self._prev[0] < min_interval and self._prev[2] is not None:
                return self._prev[2]
            prev = self._prev
            result = self._build(cur, prev, now)
            self._prev = (now, cur, result)
            return result

    def _build(self, cur: dict, prev: Optional[tuple], now: float) -> dict:
        try:
            stats = self._stats()
            addrs = self._addrs()
        except Exception:
            stats, addrs = {}, {}
        local_ip = netinfo.local_ip()
        dt = now - prev[0] if prev else None
        interfaces: List[dict] = []
        for name, c in cur.items():
            st = stats.get(name)
            v4 = [a.address for a in addrs.get(name, [])
                  if getattr(a, "family", None) == socket.AF_INET and not a.address.startswith("169.254.")]
            entry = {
                "name": name,
                "type": classify(name),
                "type_inferred": True,
                "is_up": bool(st.isup) if st else None,
                "link_speed_mbps": (st.speed or None) if st else None,
                "ipv4": v4,
                "primary": bool(local_ip and local_ip in v4),
                "bytes_recv_total": c.bytes_recv,
                "bytes_sent_total": c.bytes_sent,
                "rx_bps": None,
                "tx_bps": None,
            }
            if prev and dt and dt > 0 and name in prev[1]:
                p = prev[1][name]
                rx, tx = c.bytes_recv - p.bytes_recv, c.bytes_sent - p.bytes_sent
                if rx >= 0 and tx >= 0:  # counters can reset (adapter restart)
                    entry["rx_bps"] = round(rx / dt)
                    entry["tx_bps"] = round(tx / dt)
            interfaces.append(entry)
        interfaces.sort(key=lambda i: (not i["primary"], i["type"] in ("loopback", "virtual"), i["name"]))
        primary = next((i for i in interfaces if i["primary"]), None)
        measurable = [i for i in interfaces if i["type"] != "loopback" and i["rx_bps"] is not None]
        return {
            "mode": LIVE,
            "source": "psutil (OS interface counters)",
            "timestamp": utc_now(),
            "interval_s": round(dt, 2) if dt else None,
            "primary": primary["name"] if primary else None,
            "primary_type": primary["type"] if primary else None,
            "rx_bps": primary["rx_bps"] if primary else None,
            "tx_bps": primary["tx_bps"] if primary else None,
            "total_rx_bps": sum(i["rx_bps"] for i in measurable) if measurable else None,
            "total_tx_bps": sum(i["tx_bps"] for i in measurable) if measurable else None,
            "interfaces": interfaces,
            "note": None if dt else "First reading: rates need a second sample.",
        }


def measure(interval_s: float = 1.0, sampler: Optional[InterfaceSampler] = None) -> dict:
    """Two readings ``interval_s`` apart (for one-shot CLI use)."""
    s = sampler or InterfaceSampler()
    first = s.sample()
    if first.get("mode") == UNAVAILABLE:
        return first
    time.sleep(max(0.2, interval_s))
    return s.sample()


def human_rate(bps: Optional[float]) -> str:
    """Bytes/second → human string in bits per second (how ISPs quote speeds)."""
    if bps is None:
        return "—"
    bits = bps * 8
    for unit, div in (("Gbps", 1e9), ("Mbps", 1e6), ("kbps", 1e3)):
        if bits >= div:
            return f"{bits / div:.1f} {unit}"
    return f"{bits:.0f} bps"


def human_bytes(n: Optional[float]) -> str:
    if n is None:
        return "—"
    for unit, div in (("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if n >= div:
            return f"{n / div:.1f} {unit}"
    return f"{n:.0f} B"


__all__: List[str] = ["classify", "InterfaceSampler", "measure", "human_rate", "human_bytes", "PSUTIL_HINT"]
