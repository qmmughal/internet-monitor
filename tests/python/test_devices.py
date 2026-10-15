from wifi_monitor import devices
from wifi_monitor.models import ProviderResult, WifiInterface
from wifi_monitor.probes import LatencySample
from wifi_monitor.runner import CommandResult

ARP_WIN = """
Interface: 192.168.1.10 --- 0xb
  Internet Address      Physical Address      Type
  192.168.1.1           70-f1-96-00-00-01     dynamic
  192.168.1.100         8c-7a-b3-00-00-02     dynamic
  192.168.1.101         da-a1-19-00-00-03     dynamic
  192.168.1.255         ff-ff-ff-ff-ff-ff     static
  224.0.0.22            01-00-5e-00-00-16     static

Schnittstelle: 172.25.240.1 --- 0x23
  Internetadresse       Physische Adresse     Typ
  172.25.250.214        00-15-5d-2c-77-01     dynamisch
"""

IP_NEIGH = """192.168.1.1 dev wlp2s0 lladdr 70:f1:96:00:00:01 REACHABLE
192.168.1.50 dev wlp2s0 lladdr da:a1:19:00:00:03 STALE
192.168.1.77 dev wlp2s0  FAILED
fe80::1 dev wlp2s0 lladdr 70:f1:96:00:00:01 router STALE
"""

ARP_BSD = """? (192.168.0.1) at 0:11:22:33:44:55 on en0 ifscope [ethernet]
? (192.168.0.9) at (incomplete) on en0 ifscope [ethernet]
? (192.168.0.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]
"""


def test_parse_arp_windows_any_language():
    ds = devices.parse_arp_windows(ARP_WIN)
    assert [d.ip for d in ds] == ["192.168.1.1", "192.168.1.100", "192.168.1.101", "172.25.250.214"]
    assert ds[0].mac == "70:f1:96:00:00:01" and ds[0].interface == "192.168.1.10"
    assert ds[3].interface == "172.25.240.1"  # German header parsed by structure, not words


def test_parse_ip_neigh_skips_failed():
    ds = devices.parse_ip_neigh(IP_NEIGH)
    assert [d.ip for d in ds] == ["192.168.1.1", "192.168.1.50", "fe80::1"]
    assert ds[0].interface == "wlp2s0" and ds[0].state == "REACHABLE"


def test_parse_arp_bsd_pads_mac():
    [d] = devices.parse_arp_bsd(ARP_BSD)
    assert d.mac == "00:11:22:33:44:55" and d.interface == "en0"


def test_randomized_mac():
    assert devices.is_randomized("da:a1:19:00:00:03")
    assert devices.is_randomized("02:00:00:00:00:01")
    assert not devices.is_randomized("70:f1:96:00:00:01")


def test_oui_formats(tmp_path):
    for content, mac in [
        ("70-F1-96   (hex)\t\tExample Corp\n", "70:f1:96:00:00:01"),
        ("70F196 Example Corp\n", "70:f1:96:aa:bb:cc"),
        ("70:F1:96\tExample\tExample Corp\n", "70:f1:96:00:00:09"),
    ]:
        f = tmp_path / "oui.txt"
        f.write_text(content, encoding="utf-8")
        db = devices.OuiDatabase(paths=[str(f)])
        assert db.lookup(mac) == "Example Corp"


def test_oui_never_for_randomized(tmp_path):
    f = tmp_path / "oui.txt"
    f.write_text("DAA119 Somebody\n", encoding="utf-8")
    assert devices.OuiDatabase(paths=[str(f)]).lookup("da:a1:19:00:00:03") is None


def test_oui_missing_database():
    db = devices.OuiDatabase(paths=["/nonexistent/oui.txt"])
    assert db.lookup("70:f1:96:00:00:01") is None and not db.available


def test_known_devices_baseline_then_new():
    known = devices.KnownDevices()
    first = devices.parse_arp_windows(ARP_WIN)
    assert known.observe(first) == []  # first scan sets the baseline
    later = first + [devices.Device(ip="192.168.1.200", mac="aa:bb:cc:00:00:99")]
    new = devices.KnownDevices().observe(later)
    assert [d.mac for d in new] == ["aa:bb:cc:00:00:99"]


def test_set_name_sanitises_and_validates():
    k = devices.KnownDevices()
    k.set_name("70-F1-96-00-00-01", "Router\x1b[31m " + "x" * 100)
    rec = devices.KnownDevices().data["70:f1:96:00:00:01"]
    assert "\x1b" not in rec["name"] and len(rec["name"]) <= 64
    try:
        k.set_name("not a mac", "x")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert k.forget("70:f1:96:00:00:01") and not k.forget("70:f1:96:00:00:01")


def test_sweep_only_private_24():
    assert len(devices.sweep_targets("192.168.1.10")) == 253
    assert devices.sweep_targets("8.8.8.8") == []
    assert devices.sweep_targets(None) == []


def test_active_sweep_bounded():
    calls = []

    def ping(ip, count, timeout_s):
        calls.append((ip, count))
        return LatencySample(ip, "icmp", 1, 0)

    r = devices.active_sweep("10.0.0.5", ping_fn=ping, workers=8)
    assert r["probed"] == 253 and all(c == 1 for _, c in calls)
    assert devices.active_sweep("1.2.3.4", ping_fn=ping)["error"]


def test_discover_passive_does_not_sweep():
    swept = []
    res = devices.discover(
        probe=False, runner=lambda a, timeout=10: CommandResult(a, 0, stdout=ARP_WIN),
        oui=devices.OuiDatabase(paths=[]), sweep_fn=lambda ip: swept.append(ip),
        route=lambda: ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1", "local_ip": "192.168.1.10"}),
        known=devices.KnownDevices(),
    )
    assert not swept
    data = res["result"]["data"]
    assert data[0]["is_gateway"] and data[2]["randomized_mac"]
    assert "passive" in res["method"]


def test_discover_unavailable():
    res = devices.discover(runner=lambda a, timeout=10: CommandResult(a, None, error="not_found"),
                           route=lambda: ProviderResult(mode="live", source="t", data={}))
    assert res["result"]["mode"] == "unavailable"


def test_security_posture_rules():
    open_net = WifiInterface(name="w", connected=True, security="Open")
    wep = WifiInterface(name="w", connected=True, security="WEP")
    wpa3 = WifiInterface(name="w", connected=True, security="WPA3-Personal")
    assert devices.security_posture(open_net, None)[0]["title"].startswith("Open")
    assert devices.security_posture(wep, None)[0]["severity"] == "critical"
    assert devices.security_posture(wpa3, None)[0]["severity"] == "ok"
    devs = [{"ip": "192.168.1.1", "mac": "aa:aa:aa:00:00:01", "is_gateway": True, "randomized_mac": False},
            {"ip": "192.168.1.50", "mac": "aa:aa:aa:00:00:01", "is_gateway": False, "randomized_mac": False}]
    f = devices.security_posture(None, devs, {"192.168.1.1": "bb:bb:bb:00:00:02"})
    titles = [x["title"] for x in f]
    assert "Router MAC address changed" in titles and "Router MAC also claims other addresses" in titles


def test_gateway_history_records():
    devs = [{"ip": "192.168.1.1", "mac": "aa:aa:aa:00:00:01", "is_gateway": True}]
    assert devices.gateway_history(devs) == {}
    assert devices.gateway_history(devs) == {"192.168.1.1": "aa:aa:aa:00:00:01"}
