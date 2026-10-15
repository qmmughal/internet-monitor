import json
import socket
from collections import namedtuple

import pytest

from wifi_monitor import apps, traffic
from wifi_monitor.runner import CommandResult

Counters = namedtuple("Counters", "bytes_sent bytes_recv")
Stats = namedtuple("Stats", "isup speed")
Addr = namedtuple("Addr", "family address")
Conn = namedtuple("Conn", "fd family type laddr raddr status pid")


# ── interface classification and rates ──────────────────────────

@pytest.mark.parametrize("name,kind", [
    ("Wi-Fi", "wifi"), ("wlp2s0", "wifi"), ("wlan0", "wifi"), ("Ethernet", "ethernet"), ("eth0", "ethernet"),
    ("enp3s0", "ethernet"), ("en0", "ethernet"), ("vEthernet (WSL)", "virtual"), ("docker0", "virtual"),
    ("wg0", "vpn"), ("tun0", "vpn"), ("Tailscale", "vpn"), ("utun3", "vpn"), ("Cellular", "cellular"),
    ("wwan0", "cellular"), ("lo", "loopback"), ("Loopback Pseudo-Interface 1", "loopback"), ("weird0", "other"),
])
def test_classify(name, kind):
    assert traffic.classify(name) == kind


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def sampler(readings, clock):
    it = iter(readings)
    return traffic.InterfaceSampler(
        counters_fn=lambda: next(it),
        stats_fn=lambda: {"Ethernet": Stats(True, 1000), "Wi-Fi": Stats(False, 0), "lo": Stats(True, 0)},
        addrs_fn=lambda: {"Ethernet": [Addr(socket.AF_INET, "192.168.1.10"), Addr(socket.AF_INET, "169.254.1.1")],
                          "Wi-Fi": [], "lo": [Addr(socket.AF_INET, "127.0.0.1")]},
        clock=clock)


def test_rates_and_primary(monkeypatch):
    monkeypatch.setattr(traffic.netinfo, "local_ip", lambda: "192.168.1.10")
    clock = FakeClock()
    s = sampler([
        {"Ethernet": Counters(1000, 5000), "Wi-Fi": Counters(0, 0), "lo": Counters(10, 10)},
        {"Ethernet": Counters(3000, 25000), "Wi-Fi": Counters(0, 0), "lo": Counters(10, 10)},
    ], clock)
    first = s.sample()
    assert first["rx_bps"] is None and first["note"]
    clock.t += 2
    r = s.sample()
    assert r["primary"] == "Ethernet" and r["primary_type"] == "ethernet"
    assert r["rx_bps"] == 10000 and r["tx_bps"] == 1000
    eth = r["interfaces"][0]
    assert eth["primary"] and eth["ipv4"] == ["192.168.1.10"] and eth["link_speed_mbps"] == 1000
    assert r["total_rx_bps"] == 10000  # loopback excluded


def test_counter_reset_gives_no_rate(monkeypatch):
    monkeypatch.setattr(traffic.netinfo, "local_ip", lambda: None)
    clock = FakeClock()
    s = sampler([{"Ethernet": Counters(5000, 5000)}, {"Ethernet": Counters(10, 10)}], clock)
    s.sample()
    clock.t += 1
    r = s.sample()
    assert r["interfaces"][0]["rx_bps"] is None and r["primary"] is None


def test_min_interval_returns_cached(monkeypatch):
    monkeypatch.setattr(traffic.netinfo, "local_ip", lambda: None)
    clock = FakeClock()
    s = sampler([{"Ethernet": Counters(0, 0)}, {"Ethernet": Counters(0, 100)}, {"Ethernet": Counters(0, 999)}], clock)
    s.sample()
    clock.t += 1
    a = s.sample(min_interval=1.0)
    clock.t += 0.2
    assert s.sample(min_interval=1.0) is a  # too soon: same reading, no extra counter read


def test_unavailable_without_psutil(monkeypatch):
    monkeypatch.setattr(traffic, "psutil", None)
    r = traffic.InterfaceSampler().sample()
    assert r["mode"] == "unavailable" and "psutil" in r["hint"]


def test_human_formats():
    assert traffic.human_rate(125_000) == "1.0 Mbps"
    assert traffic.human_rate(None) == "—"
    assert traffic.human_bytes(1_500_000) == "1.5 MB"


# ── naming ──────────────────────────────────────────────────────

@pytest.mark.parametrize("ident,name", [
    (r"\device\harddiskvolume3\program files\google\chrome\application\chrome.exe", "Google Chrome"),
    (r"\device\harddiskvolume3\tools\mytool.exe", "mytool"),
    ("MSTeams_8wekyb3d8bbwe", "Microsoft Teams"),
    ("5319275A.WhatsAppDesktop_cv1g1gvanyjgm", "WhatsAppDesktop"),
    ("OpenAI.Codex_2p2nqsd0c76g0", "OpenAI.Codex"),
    ("svchost.exe", "Windows services (svchost)"),
])
def test_friendly_name(ident, name):
    assert apps.friendly_name(ident)[0] == name


def test_drive_path_mapping():
    m = {r"\device\harddiskvolume3": "C:"}
    assert apps.to_drive_path(r"\device\harddiskvolume3\x\y.exe", m) == r"C:\x\y.exe"
    assert apps.to_drive_path(r"\device\other\y.exe", m) == r"\device\other\y.exe"
    assert apps.to_drive_path(None, m) is None


# ── Windows usage records ───────────────────────────────────────

NDU_ROWS = [
    {"id": r"\device\harddiskvolume3\program files\google\chrome\application\chrome.exe", "name": "",
     "sent": 100, "recv": 900, "network": "Ethernet"},
    {"id": r"\device\harddiskvolume3\program files\google\chrome\application\chrome.exe", "name": "",
     "sent": 50, "recv": 50, "network": "HomeWiFi"},
    {"id": "MSTeams_8wekyb3d8bbwe", "name": "", "sent": 5000, "recv": 1, "network": "Ethernet"},
    {"id": "Idle_app", "name": "", "sent": 0, "recv": 0, "network": "Ethernet"},
]


def test_parse_ndu_aggregates_across_networks():
    out = apps.parse_ndu(NDU_ROWS, device_map={r"\device\harddiskvolume3": "C:"})
    assert [a["app"] for a in out] == ["Microsoft Teams", "Google Chrome"]  # sorted by total, zero rows dropped
    chrome = out[1]
    assert chrome["bytes_sent"] == 150 and chrome["bytes_received"] == 950
    assert chrome["networks"] == ["Ethernet", "HomeWiFi"]
    assert chrome["path"].startswith("C:\\program files")


def test_parse_ndu_single_object():
    assert len(apps.parse_ndu(NDU_ROWS[2])) == 1


def test_windows_usage_runs_fixed_script():
    seen = {}

    def runner(args, timeout=5):
        seen["args"] = args
        return CommandResult(args, 0, stdout=json.dumps(NDU_ROWS))

    res = apps.windows_usage(10_000_000, runner=runner, device_map={})
    assert res["mode"] == "live" and res["apps"][0]["app"] == "Microsoft Teams"
    assert seen["args"][:2] == ["powershell", "-NoProfile"] and "-EncodedCommand" in seen["args"]
    import base64
    script = base64.b64decode(seen["args"][-1]).decode("utf-16-le")
    assert "AddSeconds(-2592000)" in script  # window clamped to 30 days, a number, no user text


def test_windows_usage_unavailable():
    res = apps.windows_usage(300, runner=lambda a, timeout=5: CommandResult(a, None, error="not_found"))
    assert res["mode"] == "unavailable" and "PowerShell" in res["error"]


# ── Linux ss ────────────────────────────────────────────────────

SS_A = """ESTAB 0 0 192.168.1.5:43210 140.82.112.4:443 users:(("firefox",pid=2345,fd=110)) timer:(keepalive,1min,0)
\t cubic wscale:7,7 rto:204 rtt:3.5/2 mss:1448 bytes_sent:1000 bytes_acked:1001 bytes_received:50000 segs_out:20
ESTAB 0 0 192.168.1.5:43300 151.101.1.91:443 users:(("curl",pid=99,fd=3))
\t cubic bytes_sent:200 bytes_received:300
"""
SS_B = """ESTAB 0 0 192.168.1.5:43210 140.82.112.4:443 users:(("firefox",pid=2345,fd=110)) timer:(keepalive,1min,0)
\t cubic bytes_sent:3000 bytes_acked:3001 bytes_received:250000
ESTAB 0 0 192.168.1.5:43400 1.2.3.4:443 users:(("firefox",pid=2345,fd=120))
\t cubic bytes_sent:500 bytes_received:700
ESTAB 0 0 192.168.1.5:22 10.0.0.9:51000
\t cubic bytes_sent:10 bytes_received:10
"""


def test_parse_ss():
    socks = apps.parse_ss(SS_A)
    s = socks[("192.168.1.5:43210", "140.82.112.4:443")]
    assert s["name"] == "firefox" and s["pid"] == 2345 and s["sent"] == 1000 and s["recv"] == 50000


def test_socket_deltas():
    per = apps.socket_deltas(apps.parse_ss(SS_A), apps.parse_ss(SS_B))
    ff = per["firefox"]
    assert ff["bytes_sent"] == 2000 + 500 and ff["bytes_received"] == 200000 + 700  # existing delta + new socket
    assert "curl" not in per  # closed socket: no data after the first sample


def test_linux_usage_rates():
    outs = iter([SS_A, SS_B])
    res = apps.linux_usage(sample_s=2.0, runner=lambda a, timeout=10: CommandResult(a, 0, stdout=next(outs)),
                           sleep=lambda s: None)
    ff = res["apps"][0]
    assert res["mode"] == "live" and res["realtime"] and ff["app"] == "firefox"
    assert ff["rx_bps"] == round(200700 / 2.0) and ff["pids"] == [2345]


# ── macOS nettop ────────────────────────────────────────────────

NETTOP = """time,,bytes_in,bytes_out,
12:00:00.1,Safari.123,5000000,20000,
12:00:00.1,Dropbox.456,100,90000000,
time,,bytes_in,bytes_out,
12:00:01.1,Safari.123,250000,1000,
12:00:01.1,Dropbox.456,0,3000000,
12:00:01.1,idle.789,0,0,
"""


def test_parse_nettop_uses_delta_block():
    out = apps.parse_nettop(NETTOP)
    assert [a["app"] for a in out] == ["Dropbox", "Safari"]
    assert out[0]["bytes_sent"] == 3000000 and out[0]["pids"] == [456]


# ── connections ─────────────────────────────────────────────────

def conns():
    T, U = socket.SOCK_STREAM, socket.SOCK_DGRAM
    return [
        Conn(1, 2, T, ("192.168.1.10", 50000), ("142.250.1.1", 443), "ESTABLISHED", 10),
        Conn(2, 2, T, ("192.168.1.10", 50001), ("142.250.1.1", 443), "ESTABLISHED", 10),
        Conn(3, 2, T, ("192.168.1.10", 50002), ("151.101.1.1", 80), "TIME_WAIT", 10),
        Conn(4, 2, T, ("127.0.0.1", 50003), ("127.0.0.1", 9000), "ESTABLISHED", 10),  # loopback ignored
        Conn(5, 2, T, ("0.0.0.0", 8080), (), "LISTEN", 20),
        Conn(6, 2, U, ("0.0.0.0", 5353), (), "NONE", 20),
        Conn(7, 2, T, ("192.168.1.10", 50010), ("20.1.1.1", 443), "ESTABLISHED", None),
    ]


def test_connections_grouping():
    names = {10: "chrome.exe", 20: "server.exe"}
    res = apps.connections(conn_fn=conns, proc_name_fn=names.get)
    by = {a["app"]: a for a in res["apps"]}
    chrome = by["Google Chrome"]
    assert chrome["process"] == "chrome.exe" and chrome["established"] == 2 and chrome["connections"] == 3
    top = chrome["remotes"][0]
    assert (top["ip"], top["port"], top["service"], top["count"]) == ("142.250.1.1", 443, "https", 2)
    srv = by["server"]
    assert srv["established"] == 0 and {l["address"] for l in srv["listening"]} == {"0.0.0.0:8080", "0.0.0.0:5353"}
    assert all(l["all_interfaces"] for l in srv["listening"])
    assert "System / unknown" in by


def test_connections_errors():
    def boom():
        raise PermissionError("denied")
    res = apps.connections(conn_fn=boom)
    assert res["mode"] == "unavailable" and "denied" in res["error"]


# ── live rates on Windows ───────────────────────────────────────

def test_app_rate_tracker():
    readings = iter([
        {"mode": "live", "source": "t", "apps": [{"app": "A", "id": "a", "bytes_sent": 100, "bytes_received": 1000}]},
        {"mode": "live", "source": "t", "apps": [{"app": "A", "id": "a", "bytes_sent": 300, "bytes_received": 5000},
                                                  {"app": "B", "id": "b", "bytes_sent": 9, "bytes_received": 9}]},
    ])
    clock = FakeClock()
    tr = apps.AppRateTracker(usage_fn=lambda: next(readings), clock=clock)
    first = tr.poll()
    assert first["apps"] == [] and first["first_poll"] is True
    clock.t += 20
    r = tr.poll()
    assert r["interval_s"] == 20 and not r["first_poll"]
    assert r["apps"][0]["app"] == "A" and r["apps"][0]["rx_bps"] == 200 and r["apps"][0]["tx_bps"] == 10
    assert [a["app"] for a in r["apps"]] == ["A"]  # B has no previous reading yet


def test_usage_unsupported_platform():
    assert apps.usage(300, system="Plan9")["mode"] == "unavailable"


def test_reverse_dns_bounded(monkeypatch):
    monkeypatch.setattr(apps.socket, "gethostbyaddr", lambda ip: ("host.example", [], [ip]))
    assert apps.reverse_dns(["1.1.1.1", "1.1.1.1", "8.8.8.8"]) == {"1.1.1.1": "host.example", "8.8.8.8": "host.example"}
