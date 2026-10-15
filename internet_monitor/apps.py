"""Which apps use the network: bytes per app, and live connections per app.

Per-app bytes, by platform (no administrator rights needed):

* Windows — the system's own per-app network usage records (the data behind
  Settings › Network › Data usage), read through the WinRT
  ``ConnectionProfile.GetAttributedNetworkUsageAsync`` API. Accurate totals for
  any time window, including apps that have already exited, but Windows
  updates them periodically, so the newest ~30–60 s may not be included yet.
* Linux — per-socket TCP byte counters from ``ss -tinp`` sampled twice; real
  time, TCP only, and only your own processes unless run as root.
* macOS — ``nettop`` per-process deltas (not yet verified on hardware).

Live connections (all platforms, via psutil): which processes currently have
TCP/UDP sockets open and to which remote addresses. A connection says nothing
about how much data flows over it.
"""

from __future__ import annotations

import os
import platform
import re
import socket
import threading
import time
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Tuple

from . import pwsh
from .models import LIVE, UNAVAILABLE, utc_now
from .runner import run

try:
    import psutil  # type: ignore
except ImportError:  # pragma: no cover
    psutil = None

PSUTIL_HINT = 'Install psutil for per-app features: pip install "psutil>=5.9"'

SERVICES = {20: "ftp-data", 21: "ftp", 22: "ssh", 25: "smtp", 53: "dns", 80: "http", 110: "pop3", 123: "ntp",
            143: "imap", 443: "https", 465: "smtps", 587: "smtp", 853: "dns-over-tls", 993: "imaps", 995: "pop3s",
            1194: "openvpn", 1883: "mqtt", 3389: "rdp", 3478: "stun/turn", 5222: "xmpp", 5228: "google-push",
            5223: "apple-push", 8080: "http-alt", 8443: "https-alt", 51820: "wireguard"}

FRIENDLY = {"chrome": "Google Chrome", "msedge": "Microsoft Edge", "firefox": "Firefox", "code": "Visual Studio Code",
            "teams": "Microsoft Teams", "ms-teams": "Microsoft Teams", "msteams": "Microsoft Teams", "onedrive": "OneDrive", "dropbox": "Dropbox",
            "svchost": "Windows services (svchost)", "steam": "Steam", "spotify": "Spotify", "zoom": "Zoom",
            "slack": "Slack", "discord": "Discord", "outlook": "Outlook", "winword": "Word", "olk": "Outlook",
            "msmpeng": "Microsoft Defender", "wuauclt": "Windows Update", "backgroundtransferhost": "Background transfers",
            "deliveryoptimization": "Delivery Optimization (Windows Update)", "system": "System"}


# ── naming ───────────────────────────────────────────────────────

def friendly_name(attribution_id: str, attribution_name: str = "") -> Tuple[str, Optional[str]]:
    """(display name, executable path or None) for a Windows attribution id or a process name."""
    if attribution_name:
        return attribution_name, None
    ident = attribution_id or ""
    if "\\" in ident or "/" in ident:
        base = re.split(r"[\\/]", ident)[-1]
        stem = re.sub(r"\.exe$", "", base, flags=re.I)
        return FRIENDLY.get(stem.lower(), stem), ident
    if re.fullmatch(r"[A-Za-z0-9.\-]+_[a-z0-9]{13}", ident):  # packaged app family name
        name = re.sub(r"^[0-9A-F]{6,10}\.", "", ident.rsplit("_", 1)[0])  # drop publisher id prefix
        return FRIENDLY.get(name.lower(), name), None
    ident = re.sub(r"\.exe$", "", ident, flags=re.I) if "." in ident else ident
    return FRIENDLY.get(ident.lower(), ident or "Unknown"), None


def _dos_device_map() -> Dict[str, str]:
    """'\\device\\harddiskvolume3' → 'C:' (Windows only)."""
    mapping: Dict[str, str] = {}
    if os.name != "nt":
        return mapping
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(1024)
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if ctypes.windll.kernel32.QueryDosDeviceW(f"{letter}:", buf, 1024):
                mapping[buf.value.lower()] = f"{letter}:"
    except Exception:
        pass
    return mapping


def to_drive_path(device_path: Optional[str], mapping: Optional[Dict[str, str]] = None) -> Optional[str]:
    if not device_path:
        return None
    mapping = _dos_device_map() if mapping is None else mapping
    low = device_path.lower()
    for dev, drive in mapping.items():
        if low.startswith(dev + "\\"):
            return drive + device_path[len(dev):]
    return device_path


# ── Windows: system per-app usage records ────────────────────────

NDU_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Networking.Connectivity.NetworkInformation, Windows.Networking.Connectivity, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
  $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$listType = [System.Collections.Generic.IReadOnlyList[Windows.Networking.Connectivity.AttributedNetworkUsage]]
$end = [DateTimeOffset]::Now
$start = $end.AddSeconds(-__SECONDS__)
$states = New-Object Windows.Networking.Connectivity.NetworkUsageStates
$out = New-Object System.Collections.ArrayList
foreach ($p in [Windows.Networking.Connectivity.NetworkInformation]::GetConnectionProfiles()) {
  try {
    $task = $asTask.MakeGenericMethod($listType).Invoke($null, @($p.GetAttributedNetworkUsageAsync($start, $end, $states)))
    if (-not $task.Wait(15000)) { continue }
    foreach ($u in $task.Result) {
      [void]$out.Add([pscustomobject]@{ id = $u.AttributionId; name = $u.AttributionName;
        sent = [int64]$u.BytesSent; recv = [int64]$u.BytesReceived; network = $p.ProfileName })
    }
  } catch { }
}
ConvertTo-Json -InputObject @($out) -Compress -Depth 3
"""


def parse_ndu(rows, device_map: Optional[Dict[str, str]] = None) -> List[dict]:
    """Aggregate raw attribution rows (possibly several networks per app) into one entry per app."""
    if isinstance(rows, dict):
        rows = [rows]
    apps: Dict[str, dict] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ident = str(r.get("id") or "")
        sent, recv = int(r.get("sent") or 0), int(r.get("recv") or 0)
        if not ident or sent + recv == 0:
            continue
        name, path = friendly_name(ident, str(r.get("name") or ""))
        e = apps.setdefault(ident.lower(), {"app": name, "id": ident, "path": to_drive_path(path, device_map),
                                            "bytes_sent": 0, "bytes_received": 0, "networks": []})
        e["bytes_sent"] += sent
        e["bytes_received"] += recv
        net = r.get("network")
        if net and net not in e["networks"]:
            e["networks"].append(str(net))
    return sorted(apps.values(), key=lambda a: a["bytes_sent"] + a["bytes_received"], reverse=True)


def windows_usage(window_s: int, runner=run, device_map: Optional[Dict[str, str]] = None) -> dict:
    window_s = max(60, min(int(window_s), 30 * 86400))
    rows, err = pwsh.run_json(NDU_SCRIPT.replace("__SECONDS__", str(window_s)), timeout=30, runner=runner)
    if err:
        return {"mode": UNAVAILABLE, "error": err,
                "hint": "Per-app usage comes from Windows' network usage records (Windows 10/11)."}
    return {"mode": LIVE, "source": "Windows network usage records (Settings › Data usage)",
            "apps": parse_ndu(rows, device_map), "realtime": False,
            "note": "Windows updates these records periodically; the last ~30–60 s may not be included yet."}


# ── Linux: ss per-socket counters ────────────────────────────────

_SS_USER = re.compile(r'users:\(\("([^"]+)",pid=(\d+)')
_SS_BYTES = {k: re.compile(rf"\b{k}:(\d+)") for k in ("bytes_sent", "bytes_acked", "bytes_received")}


def parse_ss(text: str) -> Dict[Tuple[str, str], dict]:
    """``ss -tinpH`` → {(local, peer): {name, pid, sent, recv}}."""
    sockets: Dict[Tuple[str, str], dict] = {}
    current: Optional[dict] = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            cols = line.split()
            if len(cols) < 5:
                current = None
                continue
            local, peer = cols[3], cols[4]
            m = _SS_USER.search(line)
            current = {"name": m.group(1) if m else None, "pid": int(m.group(2)) if m else None, "sent": 0, "recv": 0}
            sockets[(local, peer)] = current
        elif current is not None:
            vals = {k: int(m.group(1)) for k, rx in _SS_BYTES.items() if (m := rx.search(line))}
            current["sent"] = vals.get("bytes_sent", vals.get("bytes_acked", current["sent"]))
            current["recv"] = vals.get("bytes_received", current["recv"])
    return sockets


def socket_deltas(before: Dict, after: Dict) -> Dict[str, dict]:
    """Per-process bytes between two ``parse_ss`` snapshots. New sockets count from zero."""
    per: Dict[str, dict] = defaultdict(lambda: {"bytes_sent": 0, "bytes_received": 0, "pids": set()})
    for key, s in after.items():
        if not s["name"]:
            continue
        b = before.get(key)
        sent = s["sent"] - (b["sent"] if b else 0)
        recv = s["recv"] - (b["recv"] if b else 0)
        if sent < 0 or recv < 0:  # socket reused between samples
            sent, recv = s["sent"], s["recv"]
        e = per[s["name"]]
        e["bytes_sent"] += sent
        e["bytes_received"] += recv
        e["pids"].add(s["pid"])
    return per


def linux_usage(sample_s: float = 2.0, runner=run, sleep: Callable[[float], None] = time.sleep) -> dict:
    args = ["ss", "-tinpH"]
    a = runner(args, timeout=10)
    if a.error:
        return {"mode": UNAVAILABLE, "error": f"ss unavailable ({a.error})", "hint": "Install iproute2 (ss)."}
    t0 = time.monotonic()
    sleep(sample_s)
    b = runner(args, timeout=10)
    dt = max(0.1, time.monotonic() - t0) if sleep is time.sleep else sample_s
    per = socket_deltas(parse_ss(a.stdout), parse_ss(b.stdout))
    apps = [{"app": name, "id": name, "path": None, "bytes_sent": e["bytes_sent"], "bytes_received": e["bytes_received"],
             "tx_bps": round(e["bytes_sent"] / dt), "rx_bps": round(e["bytes_received"] / dt),
             "pids": sorted(p for p in e["pids"] if p)} for name, e in per.items()
            if e["bytes_sent"] or e["bytes_received"]]
    apps.sort(key=lambda x: x["bytes_sent"] + x["bytes_received"], reverse=True)
    return {"mode": LIVE, "source": "ss (per-socket TCP counters)", "apps": apps, "realtime": True,
            "sample_s": round(dt, 2),
            "note": "TCP only; processes of other users appear only when run as root."}


# ── macOS: nettop ────────────────────────────────────────────────

def parse_nettop(text: str) -> List[dict]:
    """CSV from ``nettop -P -L 2 -d -x -J bytes_in,bytes_out``; uses the last (delta) sample."""
    blocks: List[List[str]] = []
    for line in text.splitlines():
        if line.startswith("time,"):
            blocks.append([])
        elif blocks and line.strip():
            blocks[-1].append(line)
    rows = blocks[-1] if blocks else []
    apps = []
    for line in rows:
        cols = line.split(",")
        if len(cols) < 4:
            continue
        proc = cols[1]
        name, _, pid = proc.rpartition(".")
        try:
            rx, tx = int(cols[2] or 0), int(cols[3] or 0)
        except ValueError:
            continue
        if rx or tx:
            apps.append({"app": name or proc, "id": name or proc, "path": None, "bytes_received": rx, "bytes_sent": tx,
                         "pids": [int(pid)] if pid.isdigit() else []})
    return sorted(apps, key=lambda a: a["bytes_sent"] + a["bytes_received"], reverse=True)


def macos_usage(sample_s: int = 1, runner=run) -> dict:
    res = runner(["nettop", "-P", "-L", "2", "-s", str(max(1, int(sample_s))), "-d", "-x",
                  "-J", "bytes_in,bytes_out"], timeout=15)
    if res.error:
        return {"mode": UNAVAILABLE, "error": f"nettop unavailable ({res.error})"}
    apps = parse_nettop(res.stdout)
    for a in apps:
        a["rx_bps"] = round(a["bytes_received"] / max(1, sample_s))
        a["tx_bps"] = round(a["bytes_sent"] / max(1, sample_s))
    return {"mode": LIVE, "source": "nettop", "apps": apps, "realtime": True, "sample_s": sample_s,
            "note": "Not yet verified on Apple hardware."}


# ── entry points ─────────────────────────────────────────────────

def usage(window_s: int = 300, system: Optional[str] = None, runner=run) -> dict:
    """Per-app bytes. Windows: over ``window_s``; Linux/macOS: a short real-time sample."""
    system = system or platform.system()
    if system == "Windows":
        res = windows_usage(window_s, runner=runner)
        res["window_s"] = max(60, min(int(window_s), 30 * 86400))
    elif system == "Linux":
        res = linux_usage(runner=runner)
    elif system == "Darwin":
        res = macos_usage(runner=runner)
    else:
        res = {"mode": UNAVAILABLE, "error": f"platform '{system}' is not supported"}
    res.setdefault("timestamp", utc_now())
    if res.get("mode") == LIVE:
        _attach_running(res["apps"])
    return res


def _attach_running(apps: List[dict]) -> None:
    """Mark which apps are running now (matched by executable name)."""
    if psutil is None:
        return
    running: Dict[str, List[int]] = defaultdict(list)
    try:
        for p in psutil.process_iter(["name", "pid"]):
            if p.info.get("name"):
                running[p.info["name"].lower()].append(p.info["pid"])
    except Exception:
        return
    for a in apps:
        key = (a.get("path") or a.get("id") or "").replace("/", "\\").split("\\")[-1].lower()
        pids = running.get(key) or running.get(f"{key}.exe") or []
        a.setdefault("pids", sorted(pids)[:20])
        a["running"] = bool(a.get("pids"))


class AppRateTracker:
    """Per-app rates on Windows by differencing cumulative usage between polls."""

    def __init__(self, usage_fn=None, clock=time.monotonic) -> None:
        self._usage = usage_fn or (lambda: windows_usage(3600))
        self._clock = clock
        self._prev: Optional[Tuple[float, Dict[str, Tuple[int, int]]]] = None
        self._lock = threading.Lock()

    def poll(self) -> dict:
        with self._lock:
            res = self._usage()
            if res.get("mode") != LIVE:
                return res
            now = self._clock()
            cur = {a["id"].lower(): (a["bytes_sent"], a["bytes_received"]) for a in res["apps"]}
            rates = []
            dt = now - self._prev[0] if self._prev else None
            if self._prev:
                for a in res["apps"]:
                    before = self._prev[1].get(a["id"].lower())
                    if before is None or not dt or dt <= 0:
                        continue
                    tx, rx = a["bytes_sent"] - before[0], a["bytes_received"] - before[1]
                    if tx > 0 or rx > 0:
                        rates.append(dict(a, tx_bps=round(max(tx, 0) / dt), rx_bps=round(max(rx, 0) / dt),
                                          bytes_sent=max(tx, 0), bytes_received=max(rx, 0)))
                rates.sort(key=lambda a: a["tx_bps"] + a["rx_bps"], reverse=True)
            first = self._prev is None
            self._prev = (now, cur)
            return {"mode": LIVE, "source": res["source"], "apps": rates, "realtime": False,
                    "interval_s": round(dt, 1) if dt else None,
                    "first_poll": first,
                    "note": "Rates between polls of Windows' usage records; they lag real time by ~30–60 s."}


# ── live connections (all platforms) ─────────────────────────────

def _addr(a) -> Optional[str]:
    if not a:
        return None
    ip, port = a[0], a[1]
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"


def connections(conn_fn=None, proc_name_fn=None, max_remotes: int = 15) -> dict:
    """Group open sockets by process."""
    if psutil is None and conn_fn is None:
        return {"mode": UNAVAILABLE, "error": "psutil is not installed", "hint": PSUTIL_HINT}
    conn_fn = conn_fn or (lambda: psutil.net_connections(kind="inet"))
    names: Dict[int, str] = {}

    def name_of(pid: Optional[int]) -> str:
        if not pid:
            return "System / unknown"
        if pid not in names:
            try:
                names[pid] = proc_name_fn(pid) if proc_name_fn else psutil.Process(pid).name()
            except Exception:
                names[pid] = f"pid {pid}"
        return names[pid]

    try:
        conns = conn_fn()
    except Exception as exc:
        return {"mode": UNAVAILABLE, "error": f"cannot list connections: {exc}",
                "hint": "On macOS listing other processes' connections requires administrator rights."}
    apps: Dict[str, dict] = {}
    for c in conns:
        exe = name_of(c.pid)
        name = friendly_name(exe)[0] if not exe.startswith(("pid ", "System /")) else exe
        e = apps.setdefault(name, {"app": name, "process": exe, "pids": set(), "established": 0, "listening": [],
                                   "udp": 0, "remotes": defaultdict(int)})
        if c.pid:
            e["pids"].add(c.pid)
        proto = "udp" if c.type == socket.SOCK_DGRAM else "tcp"
        if proto == "udp":
            e["udp"] += 1
        if c.status == "LISTEN" or (proto == "udp" and not c.raddr):
            if c.laddr and len(e["listening"]) < 20:
                exposed = c.laddr[0] not in ("127.0.0.1", "::1")
                e["listening"].append({"address": _addr(c.laddr), "protocol": proto, "all_interfaces": exposed
                                       and c.laddr[0] in ("0.0.0.0", "::")})
            continue
        if c.raddr:
            rip = c.raddr[0]
            if rip.startswith("127.") or rip == "::1":
                continue
            if c.status == "ESTABLISHED" or proto == "udp":
                e["established"] += 1
            e["remotes"][(rip, c.raddr[1], proto, c.status)] += 1
    out = []
    for e in apps.values():
        remotes = sorted(e["remotes"].items(), key=lambda kv: -kv[1])[:max_remotes]
        if not remotes and not e["listening"]:
            continue
        out.append({
            "app": e["app"], "process": e["process"], "pids": sorted(e["pids"])[:20],
            "connections": sum(e["remotes"].values()),
            "established": e["established"], "udp_sockets": e["udp"], "listening": e["listening"],
            "remotes": [{"ip": ip, "port": port, "service": SERVICES.get(port), "protocol": proto, "state": st,
                         "count": n} for (ip, port, proto, st), n in remotes],
        })
    out.sort(key=lambda a: (a["established"], a["connections"]), reverse=True)
    return {"mode": LIVE, "source": "psutil (OS socket table)", "timestamp": utc_now(), "apps": out,
            "note": "Shows open connections, not how much data flows over them."}


def reverse_dns(ips: List[str], timeout_s: float = 1.5, limit: int = 50) -> Dict[str, Optional[str]]:
    """Opt-in PTR lookups (sends DNS queries), bounded in count and time."""
    out: Dict[str, Optional[str]] = {}

    def work(ip: str) -> None:
        try:
            out[ip] = socket.gethostbyaddr(ip)[0]
        except (OSError, UnicodeError):
            out[ip] = None

    threads = []
    for ip in list(dict.fromkeys(ips))[:limit]:
        t = threading.Thread(target=work, args=(ip,), daemon=True)
        t.start()
        threads.append(t)
    deadline = time.monotonic() + timeout_s
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    return out


def activity_snapshot(window_s: int = 300) -> dict:
    """Current primary-interface rates plus the busiest apps (used by diagnostics and AI context)."""
    from .traffic import measure

    t = measure(1.0)
    u = usage(window_s)
    return {
        "traffic": {k: t.get(k) for k in ("primary", "primary_type", "rx_bps", "tx_bps")} if t.get("mode") == LIVE else {},
        "top_apps": [{k: a.get(k) for k in ("app", "bytes_received", "bytes_sent")} for a in (u.get("apps") or [])[:5]]
        if u.get("mode") == LIVE else [],
    }
