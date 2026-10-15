import fixtures as fx
import pytest

from wifi_monitor import netinfo, probes
from wifi_monitor.models import ESTIMATED, LIVE, Measurement
from wifi_monitor.providers import get_provider
from wifi_monitor.providers import linux, macos, windows
from wifi_monitor.runner import CommandResult


def fake_runner(mapping):
    """Return canned CommandResults keyed by the first two args."""

    def run(args, timeout=5.0):
        for key, result in mapping.items():
            if tuple(args[: len(key)]) == key:
                return result if isinstance(result, CommandResult) else CommandResult(args, 0, stdout=result)
        return CommandResult(args, None, error="not_found")

    return run


# ── Windows ──────────────────────────────────────────────────────

def test_netsh_connected_with_rssi_is_live():
    [iface] = windows.parse_interfaces(fx.NETSH_IFACE_CONNECTED_RSSI)
    assert iface.connected
    assert iface.ssid == "Home: Upstairs"  # colon inside SSID survives
    assert iface.bssid == "02:aa:bb:cc:dd:01"
    assert iface.channel == 44 and iface.band == "5 GHz" and iface.frequency_mhz == 5220
    assert iface.signal_dbm.value == -52 and iface.signal_dbm.mode == LIVE
    assert iface.signal_percent == 88
    assert iface.rx_rate_mbps == 1201 and iface.tx_rate_mbps == 960


def test_netsh_percent_only_is_estimated():
    [iface] = windows.parse_interfaces(fx.NETSH_IFACE_CONNECTED_PCT_ONLY)
    assert iface.bssid == "02:aa:bb:cc:dd:02"  # older "BSSID" label
    assert iface.signal_dbm.mode == ESTIMATED
    assert iface.signal_dbm.value == -70
    assert iface.band == "2.4 GHz"  # derived from channel when Band line is missing
    assert iface.rx_rate_mbps == 72.2


def test_netsh_two_interfaces_picks_connected():
    ifaces = windows.parse_interfaces(fx.NETSH_IFACE_TWO)
    assert [i.name for i in ifaces] == ["Wi-Fi", "Wi-Fi 2"]
    assert not ifaces[0].connected and ifaces[0].ssid is None and ifaces[0].signal_dbm is None
    assert ifaces[1].connected and ifaces[1].ssid == "Office"


def test_netsh_non_english_is_unavailable_not_guessed():
    p = windows.WindowsProvider(runner=fake_runner({("netsh", "wlan"): fx.NETSH_IFACE_GERMAN}))
    res = p.interfaces()
    # "Name" is the same in German, but without "State" we must not report "disconnected".
    assert not res.ok and res.hint == windows.LOCALE_HINT and res.data is None


def test_netsh_unparseable_output_reports_locale_hint():
    p = windows.WindowsProvider(runner=fake_runner({("netsh", "wlan"): "Schnittstelle: irgendwas\n"}))
    res = p.interfaces()
    assert not res.ok and res.hint == windows.LOCALE_HINT


@pytest.mark.parametrize(
    "text,error",
    [(fx.NETSH_NO_WIRELESS, "no Wi-Fi interface"), (fx.NETSH_LOCATION_DENIED, "location permission")],
)
def test_netsh_known_errors(text, error):
    p = windows.WindowsProvider(runner=fake_runner({("netsh", "wlan"): CommandResult(["netsh"], 1, stdout=text)}))
    res = p.interfaces()
    assert not res.ok and error in res.error
    assert res.data is None


def test_netsh_location_denied_has_hint():
    p = windows.WindowsProvider(runner=fake_runner({("netsh", "wlan"): CommandResult(["netsh"], 1, stdout=fx.NETSH_LOCATION_DENIED)}))
    assert "Location" in p.interfaces().hint


def test_netsh_networks():
    aps = windows.parse_networks(fx.NETSH_NETWORKS)
    assert len(aps) == 4
    a, b, hidden, six = aps
    assert a.ssid == "Home: Upstairs" and a.bssid == "02:aa:bb:cc:dd:01" and a.channel == 44 and a.band == "5 GHz"
    assert a.signal_percent == 88 and a.signal_mode == ESTIMATED
    assert b.ssid == "Home: Upstairs" and b.band == "2.4 GHz" and b.channel == 1
    assert hidden.ssid is None and hidden.channel == 149
    assert six.band == "6 GHz" and six.frequency_mhz == 6135 and six.security == "Open"
    assert six.ssid == "<script>alert(1)</script>"  # stored raw; escaping is the renderer's job


def test_windows_access_points_marks_connected():
    p = windows.WindowsProvider(runner=fake_runner({
        ("netsh", "wlan", "show", "networks"): fx.NETSH_NETWORKS,
        ("netsh", "wlan", "show", "interfaces"): fx.NETSH_IFACE_CONNECTED_RSSI,
    }))
    res = p.access_points()
    assert res.ok
    assert [ap.connected for ap in res.data] == [True, False, False, False]


def test_windows_netsh_missing():
    p = windows.WindowsProvider(runner=fake_runner({}))
    res = p.interfaces()
    assert not res.ok and "not installed" in res.error


def test_windows_netsh_timeout():
    p = windows.WindowsProvider(runner=lambda args, timeout=5: CommandResult(args, None, error="timeout"))
    assert p.interfaces().error == "'netsh' timed out"


# ── Linux ────────────────────────────────────────────────────────

def test_nmcli_split_terse_handles_escapes():
    assert linux.split_terse(r"a\:b:c\\d:") == ["a:b", "c\\d", ""]


def test_nmcli_ap_list():
    aps = linux.parse_ap_list(fx.NMCLI_AP_LIST)
    assert len(aps) == 4
    home, hidden, cafe, six = aps
    assert home.connected and home.ssid == "Home: Upstairs" and home.bssid == "02:aa:bb:cc:dd:01"
    assert home.frequency_mhz == 5220 and home.band == "5 GHz" and home.signal_mode == ESTIMATED
    assert hidden.ssid is None
    assert cafe.security == "Open"
    assert six.band == "6 GHz" and six.channel == 37  # frequency disambiguates 6 GHz channel numbers


def test_linux_provider_uses_iw_for_live_dbm():
    p = linux.LinuxProvider(runner=fake_runner({
        ("nmcli", "-t", "-e", "yes", "-f", ",".join(linux.DEV_FIELDS)): fx.NMCLI_DEVICE_STATUS,
        ("nmcli",): fx.NMCLI_AP_LIST,
        ("iw",): fx.IW_LINK,
    }))
    res = p.interfaces()
    assert res.ok
    [iface] = res.data  # wifi-p2p and ethernet are filtered out
    assert iface.name == "wlp2s0" and iface.ssid == "Home: Upstairs"
    assert iface.signal_dbm.value == -57 and iface.signal_dbm.mode == LIVE
    assert iface.rx_rate_mbps == 866.7


def test_linux_provider_without_iw_is_estimated():
    p = linux.LinuxProvider(runner=fake_runner({
        ("nmcli", "-t", "-e", "yes", "-f", ",".join(linux.DEV_FIELDS)): fx.NMCLI_DEVICE_STATUS,
        ("nmcli",): fx.NMCLI_AP_LIST,
    }))
    [iface] = p.interfaces().data
    assert iface.signal_dbm.mode == ESTIMATED and iface.signal_dbm.value == -59


def test_linux_no_nmcli():
    res = linux.LinuxProvider(runner=fake_runner({})).interfaces()
    assert not res.ok and "NetworkManager" in res.hint


def test_iw_not_connected():
    assert linux.parse_iw_link("Not connected.\n") == {}


# ── macOS ────────────────────────────────────────────────────────

def test_system_profiler_redacted_ssid_and_live_rssi():
    parsed = macos.parse_system_profiler(fx.SYSTEM_PROFILER_JSON)
    [iface] = parsed["interfaces"]  # awdl0 skipped
    assert iface.connected and iface.ssid is None  # redacted → unknown, not guessed
    assert iface.signal_dbm.value == -55 and iface.signal_dbm.mode == LIVE
    assert iface.noise_dbm == -94
    assert iface.channel == 44 and iface.band == "5 GHz"
    assert parsed["redacted"] is True
    names = [ap.ssid for ap in parsed["access_points"]]
    assert names == [None, "Neighbour"]
    assert parsed["access_points"][1].band == "2.4 GHz"


def test_system_profiler_bad_json():
    assert macos.parse_system_profiler("not json") is None


def test_airport_legacy():
    iface = macos.parse_airport_info(fx.AIRPORT_I)
    assert iface.signal_dbm.value == -61 and iface.channel == 149 and iface.noise_dbm == -92


def test_mac_provider_falls_back_to_system_profiler():
    p = macos.MacProvider(runner=fake_runner({("system_profiler",): fx.SYSTEM_PROFILER_JSON}))
    res = p.interfaces()
    assert res.ok and res.source == "system_profiler" and res.hint == macos.REDACTED_HINT


# ── Routing / ping ───────────────────────────────────────────────

def test_windows_route_lowest_metric():
    assert netinfo.parse_windows_route(fx.ROUTE_PRINT_WIN) == ("10.0.0.1", "10.0.0.42")


def test_proc_net_route():
    assert netinfo.parse_proc_net_route(fx.PROC_NET_ROUTE) == ("192.168.1.1", "wlp2s0")


def test_bsd_route_get():
    assert netinfo.parse_bsd_route_get(fx.ROUTE_GET_MAC) == ("192.168.0.1", "en0")


def test_default_route_unavailable_when_no_route():
    res = netinfo.default_route("Windows", runner=lambda a, timeout=5: CommandResult(a, 0, stdout="nothing"))
    assert not res.ok and res.data["gateway"] is None


@pytest.mark.parametrize(
    "text,expected",
    [(fx.PING_WIN_EN, [3.0, 1.0, 12.0]), (fx.PING_WIN_DE, [4.0, 5.0]), (fx.PING_LINUX, [2.31, 1.95, 3.4])],
)
def test_parse_ping(text, expected):
    assert probes.parse_ping_output(text) == expected


def test_ping_rejects_hostnames():
    called = []
    s = probes.ping("example.com; rm -rf /", runner=lambda *a, **k: called.append(a))
    assert s.error and not called


def test_ping_builds_safe_args_and_counts_loss():
    seen = {}

    def runner(args, timeout=5):
        seen["args"] = args
        return CommandResult(args, 1, stdout=fx.PING_WIN_EN)

    s = probes.ping("192.168.1.1", count=4, system="Windows", runner=runner)
    assert seen["args"] == ["ping", "-n", "4", "-w", "1000", "192.168.1.1"]
    assert s.sent == 4 and s.received == 3 and s.loss_pct == 25.0


def test_latency_stats():
    s = probes.LatencySample("x", "tcp", 4, 4, [10.0, 20.0, 10.0, 30.0])
    assert s.median_ms == 15.0
    assert s.jitter_ms == round((10 + 10 + 20) / 3, 1)
    assert probes.LatencySample("x", "tcp", 2, 2, [1.0, 2.0]).jitter_ms is None  # too few samples


def test_https_only():
    assert probes.https_check("http://example.com")["error"]


# ── Provider selection / demo ────────────────────────────────────

def test_demo_is_always_labelled_simulated():
    p = get_provider(demo=True)
    i = p.interfaces()
    a = p.access_points()
    assert i.mode == a.mode == "simulated"
    assert i.data[0].signal_dbm.mode == "simulated"
    assert all(ap.signal_mode == "simulated" for ap in a.data)


def test_unsupported_platform():
    res = get_provider(system="Plan9").interfaces()
    assert not res.ok and "Plan9" in res.error


def test_measurement_rejects_unknown_mode():
    with pytest.raises(ValueError):
        Measurement(1, "dBm", "x", "guessed")
