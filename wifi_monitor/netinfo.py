"""Default gateway and local IP discovery (works for Wi-Fi and wired links)."""

from __future__ import annotations

import ipaddress
import platform
import socket
from typing import List, Optional, Tuple

from .models import LIVE, UNAVAILABLE, ProviderResult
from .runner import run


def _is_ipv4(s: str) -> bool:
    try:
        ipaddress.IPv4Address(s)
        return True
    except ValueError:
        return False


def parse_windows_route(text: str) -> Optional[Tuple[str, str]]:
    """Return (gateway, interface_ip) with the lowest metric from ``route print -4 0.0.0.0``.

    Only numeric rows are read, so the parse does not depend on the display language.
    Persistent-route rows have 4 columns and are ignored.
    """
    best = None
    for line in text.splitlines():
        cols = line.split()
        if len(cols) != 5 or cols[0] != "0.0.0.0" or cols[1] != "0.0.0.0":
            continue
        gw, iface, metric = cols[2], cols[3], cols[4]
        if not (_is_ipv4(gw) and _is_ipv4(iface) and metric.isdigit()):
            continue
        if best is None or int(metric) < best[0]:
            best = (int(metric), gw, iface)
    return (best[1], best[2]) if best else None


def parse_proc_net_route(text: str) -> Optional[Tuple[str, str]]:
    """Return (gateway, interface_name) from ``/proc/net/route``."""
    best = None
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) < 8 or f[1] != "00000000":
            continue
        try:
            flags = int(f[3], 16)
            gw = socket.inet_ntoa(int(f[2], 16).to_bytes(4, "little"))
            metric = int(f[6])
        except ValueError:
            continue
        if not flags & 0x2:  # RTF_GATEWAY
            continue
        if best is None or metric < best[0]:
            best = (metric, gw, f[0])
    return (best[1], best[2]) if best else None


def parse_bsd_route_get(text: str) -> Optional[Tuple[str, str]]:
    gw = iface = None
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = (x.strip() for x in line.split(":", 1))
        if k == "gateway" and _is_ipv4(v):
            gw = v
        elif k == "interface":
            iface = v
    return (gw, iface or "") if gw else None


def local_ip(target: str = "192.0.2.1") -> Optional[str]:
    """Source address the OS would use for outbound traffic. Connecting a UDP socket sends no packets."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((target, 9))
        ip = s.getsockname()[0]
        return None if ip.startswith("0.") else ip
    except OSError:
        return None
    finally:
        s.close()


def default_route(system: Optional[str] = None, runner=run) -> ProviderResult:
    system = system or platform.system()
    found, source = None, ""
    if system == "Windows":
        source = "route print"
        cmd = runner(["route", "print", "-4", "0.0.0.0"], timeout=5)
        found = parse_windows_route(cmd.stdout) if cmd.ok else None
    elif system == "Linux":
        source = "/proc/net/route"
        try:
            with open("/proc/net/route", encoding="ascii") as fh:
                found = parse_proc_net_route(fh.read())
        except OSError:
            found = None
    elif system == "Darwin":
        source = "route get default"
        cmd = runner(["route", "-n", "get", "default"], timeout=5)
        found = parse_bsd_route_get(cmd.stdout) if cmd.ok else None

    ip = local_ip()
    if not found:
        return ProviderResult(
            mode=UNAVAILABLE,
            source=source or "none",
            data={"gateway": None, "interface": None, "local_ip": ip},
            error="no IPv4 default gateway found",
            hint="The computer does not appear to be connected to a network.",
        )
    gw, iface = found
    return ProviderResult(mode=LIVE, source=source, data={"gateway": gw, "interface": iface or None, "local_ip": ip})


__all__: List[str] = ["default_route", "local_ip", "parse_windows_route", "parse_proc_net_route", "parse_bsd_route_get"]
