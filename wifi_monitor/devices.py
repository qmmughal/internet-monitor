"""LAN device discovery and a simple security posture summary.

Default discovery is **passive**: it reads the operating system's neighbour
(ARP) table, which lists devices this computer has recently talked to. It
sends no packets and will miss quiet devices.

An optional active sweep (``probe=True``) pings each address of the local
private /24 once, bounded in concurrency and time, so that responding devices
appear in the neighbour table. It never runs unless explicitly requested and
refuses public or oversized networks.

Accuracy limits (reported in results): devices using randomized/private MAC
addresses cannot be identified across reconnects; vendor names come only from
an OUI database installed on this system; a new device is not necessarily a
threat and a missing one is not necessarily offline.
"""

from __future__ import annotations

import ipaddress
import platform
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from . import config, netinfo, probes
from .models import LIVE, UNAVAILABLE, ProviderResult
from .runner import run

KNOWN_FILE = "known_devices.json"
OUI_PATHS = [
    "/usr/share/ieee-data/oui.txt",
    "/usr/share/misc/oui.txt",
    "/usr/share/nmap/nmap-mac-prefixes",
    "/usr/share/wireshark/manuf",
    "/usr/local/share/nmap/nmap-mac-prefixes",
    "/opt/homebrew/share/nmap/nmap-mac-prefixes",
]
_MAC = re.compile(r"([0-9a-fA-F]{1,2}[:-]){5}[0-9a-fA-F]{1,2}")


@dataclass
class Device:
    ip: str
    mac: str
    interface: Optional[str] = None
    state: Optional[str] = None
    vendor: Optional[str] = None
    randomized_mac: bool = False
    is_gateway: bool = False
    name: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    new: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_mac(raw: str) -> Optional[str]:
    m = _MAC.search(raw or "")
    if not m:
        return None
    parts = re.split(r"[:-]", m.group(0))
    return ":".join(p.zfill(2).lower() for p in parts)


def is_randomized(mac: str) -> bool:
    """Locally-administered bit set → randomized/private address (vendor unknowable)."""
    try:
        return bool(int(mac.split(":")[0], 16) & 0x02)
    except (ValueError, IndexError):
        return False


def _keep(ip: str, mac: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.is_multicast or addr.is_unspecified or addr.is_loopback or str(addr).endswith(".255"):
        return False
    if mac in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00") or mac.startswith("01:00:5e") or mac.startswith("33:33"):
        return False
    return True


def parse_arp_windows(text: str) -> List[Device]:
    out, iface = [], None
    for line in text.splitlines():
        m = re.match(r"\s*\S+:\s*(\d+\.\d+\.\d+\.\d+)\s+---", line)  # "Interface: 192.168.1.10 --- 0xb" (any language)
        if m:
            iface = m.group(1)
            continue
        cols = line.split()
        if len(cols) >= 2 and re.fullmatch(r"\d+\.\d+\.\d+\.\d+", cols[0]):
            mac = normalize_mac(cols[1])
            if mac and _keep(cols[0], mac):
                out.append(Device(ip=cols[0], mac=mac, interface=iface, state=cols[2] if len(cols) > 2 else None))
    return out


def parse_ip_neigh(text: str) -> List[Device]:
    out = []
    for line in text.splitlines():
        cols = line.split()
        if not cols or "lladdr" not in cols:
            continue
        mac = normalize_mac(cols[cols.index("lladdr") + 1]) if cols.index("lladdr") + 1 < len(cols) else None
        state = cols[-1] if cols[-1].isupper() else None
        if state in ("FAILED", "INCOMPLETE") or not mac:
            continue
        iface = cols[cols.index("dev") + 1] if "dev" in cols and cols.index("dev") + 1 < len(cols) else None
        if _keep(cols[0], mac):
            out.append(Device(ip=cols[0], mac=mac, interface=iface, state=state))
    return out


def parse_arp_bsd(text: str) -> List[Device]:
    out = []
    for line in text.splitlines():
        m = re.match(r"\S+ \((\d+\.\d+\.\d+\.\d+)\) at (\S+)(?: on (\S+))?", line)
        if not m or "incomplete" in m.group(2):
            continue
        mac = normalize_mac(m.group(2))
        if mac and _keep(m.group(1), mac):
            out.append(Device(ip=m.group(1), mac=mac, interface=m.group(3)))
    return out


class OuiDatabase:
    """Vendor lookup from an OUI file already on this system (or ``oui.txt`` in the config dir)."""

    def __init__(self, paths: Optional[List[str]] = None) -> None:
        self._paths = paths
        self._table: Optional[Dict[str, str]] = None
        self.source: Optional[str] = None

    def _load(self) -> Dict[str, str]:
        if self._table is not None:
            return self._table
        table: Dict[str, str] = {}
        candidates = self._paths if self._paths is not None else [str(config.home() / "oui.txt"), *OUI_PATHS]
        for path in candidates:
            p = Path(path)
            if not p.is_file():
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        self._parse_line(line, table)
            except OSError:
                continue
            if table:
                self.source = str(p)
                break
        self._table = table
        return table

    @staticmethod
    def _parse_line(line: str, table: Dict[str, str]) -> None:
        line = line.strip()
        if not line or line.startswith("#"):
            return
        m = re.match(r"([0-9A-Fa-f]{2})[-:]?([0-9A-Fa-f]{2})[-:]?([0-9A-Fa-f]{2})(?:\s+\(hex\))?\s+(.+)", line)
        if not m:
            return
        key = (m.group(1) + m.group(2) + m.group(3)).upper()
        vendor = m.group(4).split("\t")[-1].strip()
        if vendor and key not in table:
            table[key] = vendor[:80]

    def lookup(self, mac: str) -> Optional[str]:
        if is_randomized(mac):
            return None
        return self._load().get(mac.replace(":", "")[:6].upper())

    @property
    def available(self) -> bool:
        return bool(self._load())


def neighbor_table(system: Optional[str] = None, runner=run) -> ProviderResult:
    system = system or platform.system()
    if system == "Windows":
        cmd, parse, source = ["arp", "-a"], parse_arp_windows, "arp -a"
    elif system == "Linux":
        cmd, parse, source = ["ip", "neigh", "show"], parse_ip_neigh, "ip neigh"
    elif system == "Darwin":
        cmd, parse, source = ["arp", "-an"], parse_arp_bsd, "arp -an"
    else:
        return ProviderResult(mode=UNAVAILABLE, source="none", error=f"platform '{system}' is not supported")
    res = runner(cmd, timeout=10)
    if res.error:
        return ProviderResult(mode=UNAVAILABLE, source=source, error=f"{source} unavailable ({res.error})")
    devices = parse(res.stdout)
    seen, unique = set(), []
    for d in devices:  # one row per IP/MAC pair (Windows lists per interface)
        if (d.ip, d.mac) not in seen:
            seen.add((d.ip, d.mac))
            unique.append(d)
    return ProviderResult(mode=LIVE, source=source, data=unique)


def sweep_targets(local_ip: Optional[str]) -> List[str]:
    """Addresses of the local private /24, or [] if the network is not private."""
    if not local_ip:
        return []
    try:
        net = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return []
    if not net.is_private or net.is_loopback:
        return []
    return [str(h) for h in net.hosts() if str(h) != local_ip]


def active_sweep(local_ip: Optional[str], ping_fn=probes.ping, workers: int = 32, deadline_s: float = 60.0) -> dict:
    targets = sweep_targets(local_ip)
    if not targets:
        return {"probed": 0, "error": "active probing only runs on a private /24 network"}
    start = time.monotonic()
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 64))) as pool:
        futures = [pool.submit(ping_fn, ip, 1, 1.0) for ip in targets]
        for f in futures:
            remaining = deadline_s - (time.monotonic() - start)
            if remaining <= 0:
                break
            try:
                f.result(timeout=remaining)
                done += 1
            except Exception:
                pass
        for f in futures:
            f.cancel()
    return {"probed": done, "network": f"{targets[0].rsplit('.', 1)[0]}.0/24", "duration_s": round(time.monotonic() - start, 1)}


class KnownDevices:
    """Friendly names and first/last-seen times, stored as JSON in the config directory."""

    def __init__(self, filename: str = KNOWN_FILE) -> None:
        self.filename = filename
        data = config.read_json(filename, {})
        self.data: Dict[str, dict] = data if isinstance(data, dict) else {}

    def observe(self, devices: List[Device], now: Optional[str] = None, persist: bool = True) -> List[Device]:
        from .models import utc_now

        now = now or utc_now()
        first_run = not self.data
        new = []
        for d in devices:
            rec = self.data.get(d.mac)
            if rec is None:
                rec = {"first_seen": now, "name": None}
                self.data[d.mac] = rec
                d.new = not first_run  # the very first observation establishes the baseline
                if d.new:
                    new.append(d)
            rec["last_seen"] = now
            rec["last_ip"] = d.ip
            d.name, d.first_seen, d.last_seen = rec.get("name"), rec["first_seen"], now
        if persist:
            config.write_json(self.filename, self.data)
        return new

    def set_name(self, mac: str, name: Optional[str]) -> bool:
        mac = normalize_mac(mac) or ""
        if not mac:
            raise ValueError("invalid MAC address")
        if name is not None:
            name = "".join(ch for ch in name if ch.isprintable()).strip()[:64] or None
        rec = self.data.setdefault(mac, {"first_seen": None})
        rec["name"] = name
        config.write_json(self.filename, self.data)
        return True

    def forget(self, mac: str) -> bool:
        mac = normalize_mac(mac) or ""
        if self.data.pop(mac, None) is None:
            return False
        config.write_json(self.filename, self.data)
        return True


def discover(probe: bool = False, persist: bool = True, runner=run, oui: Optional[OuiDatabase] = None,
             route=None, sweep_fn=active_sweep, known: Optional[KnownDevices] = None) -> dict:
    """Read the neighbour table (optionally after an active sweep) and annotate devices."""
    r = (route or netinfo.default_route)()
    rd = r.data or {}
    sweep = sweep_fn(rd.get("local_ip")) if probe else None
    table = neighbor_table(runner=runner)
    if not table.ok:
        return {"result": table.to_dict(), "sweep": sweep}
    oui = oui or OuiDatabase()
    devices: List[Device] = table.data
    for d in devices:
        d.randomized_mac = is_randomized(d.mac)
        d.vendor = oui.lookup(d.mac)
        d.is_gateway = d.ip == rd.get("gateway")
    known = known or KnownDevices()
    new = known.observe(devices, persist=persist)
    return {
        "result": ProviderResult(mode=LIVE, source=table.source, data=devices).to_dict(),
        "new_devices": [d.mac for d in new],
        "sweep": sweep,
        "method": "active sweep + neighbour table" if probe else "passive neighbour table (no packets sent)",
        "vendor_database": oui.source,
        "limitations": [
            "Only devices this computer has recently exchanged traffic with appear without an active sweep.",
            "Randomized (private) MAC addresses change between connections; their vendor is unknowable.",
            "Vendor names require an OUI database on this system"
            + ("" if oui.available else " (none found; place IEEE oui.txt in the config directory)") + ".",
            "A new device is not necessarily a threat; a missing device is not necessarily offline.",
        ],
    }


def gateway_history(devices: List[dict], persist: bool = True) -> dict:
    """Return the previously recorded gateway IP→MAC map, then record the current one."""
    previous = config.read_json("gateway_macs.json", {})
    previous = previous if isinstance(previous, dict) else {}
    current = dict(previous)
    for d in devices:
        if d.get("is_gateway"):
            current[d["ip"]] = d["mac"]
    if persist and current != previous:
        config.write_json("gateway_macs.json", current)
    return previous


def security_posture(wifi_iface, devices: Optional[List[dict]], gateway_mac_history: Optional[dict] = None) -> List[dict]:
    """Observations about the connection's security, each with evidence. Never conclusive about attacks."""
    findings = []
    if wifi_iface is not None and getattr(wifi_iface, "connected", False):
        sec = (wifi_iface.security or "").lower()
        if not sec:
            pass
        elif sec in ("open", "none") or "open" in sec and "owe" not in sec:
            findings.append({"severity": "warning", "title": "Open (unencrypted) Wi-Fi",
                             "evidence": f"Authentication reported as '{wifi_iface.security}'.",
                             "advice": "Traffic on this network can be observed by others nearby; prefer HTTPS/VPN."})
        elif "wep" in sec:
            findings.append({"severity": "critical", "title": "WEP encryption",
                             "evidence": f"Authentication reported as '{wifi_iface.security}'.",
                             "advice": "WEP is broken. Switch the router to WPA2 or WPA3."})
        elif "wpa-" in sec and "wpa2" not in sec and "wpa3" not in sec or "tkip" in sec:
            findings.append({"severity": "warning", "title": "Legacy WPA/TKIP",
                             "evidence": f"Authentication reported as '{wifi_iface.security}'.",
                             "advice": "Use WPA2-AES (CCMP) or WPA3."})
        elif "wpa3" in sec:
            findings.append({"severity": "ok", "title": "WPA3 in use", "evidence": wifi_iface.security, "advice": None})
    if devices:
        gw = [d for d in devices if d.get("is_gateway")]
        if gw and gateway_mac_history is not None:
            prev = gateway_mac_history.get(gw[0]["ip"])
            if prev and prev != gw[0]["mac"]:
                findings.append({"severity": "warning", "title": "Router MAC address changed",
                                 "evidence": f"Gateway {gw[0]['ip']} was {prev}, now {gw[0]['mac']}.",
                                 "advice": "Expected after replacing the router. Otherwise it can indicate ARP "
                                           "spoofing; verify the router and run diagnostics again."})
        macs: Dict[str, List[str]] = {}
        for d in devices:
            macs.setdefault(d["mac"], []).append(d["ip"])
        for mac, ips in macs.items():
            if len(set(ips)) > 1 and any(d["is_gateway"] and d["mac"] == mac for d in devices):
                findings.append({"severity": "warning", "title": "Router MAC also claims other addresses",
                                 "evidence": f"{mac} answers for {', '.join(sorted(set(ips)))}.",
                                 "advice": "Can be normal for some routers, but is also a sign of ARP spoofing."})
        randomized = sum(1 for d in devices if d.get("randomized_mac"))
        if randomized:
            findings.append({"severity": "info", "title": f"{randomized} device(s) use private MAC addresses",
                             "evidence": "Locally-administered MAC bit set.",
                             "advice": "Normal for modern phones and laptops; such devices may appear 'new' after "
                                       "reconnecting."})
    return findings
