from wifi_monitor import channels, standards
from wifi_monitor.models import AccessPoint, WifiInterface
from wifi_monitor.providers import linux, macos

import fixtures as fx


def ap(ch, band, dbm, ssid="N"):
    return AccessPoint(ssid=ssid, bssid=None, channel=ch, band=band, signal_dbm=dbm, signal_mode="estimated")


def test_24ghz_recommends_least_crowded_non_overlapping():
    aps = [ap(1, "2.4 GHz", -45), ap(1, "2.4 GHz", -50), ap(2, "2.4 GHz", -55),
           ap(6, "2.4 GHz", -80), ap(11, "2.4 GHz", -60), ap(6, "2.4 GHz", -60, ssid="Mine")]
    r = channels.analyze(aps, "live", own_ssid="Mine")
    b = r["bands"]["2.4 GHz"]
    assert b["your_channels"] == [6]
    assert b["neighbour_access_points"] == 5
    assert b["candidates"][0]["channel"] == 6  # weakest overlap
    assert b["recommendation"]["change_recommended"] is False


def test_recommends_change_when_much_better_channel_exists():
    aps = [ap(1, "2.4 GHz", -40, ssid="Mine")] + [ap(1, "2.4 GHz", -45) for _ in range(4)] + [ap(11, "2.4 GHz", -90)]
    rec = channels.analyze(aps, "live", own_ssid="Mine")["bands"]["2.4 GHz"]["recommendation"]
    assert rec["channel"] == 6 and rec["change_recommended"] is True


def test_overlap_model_24ghz():
    assert channels._overlap("2.4 GHz", 1, 1) == 1.0
    assert channels._overlap("2.4 GHz", 1, 3) == 0.6
    assert channels._overlap("2.4 GHz", 1, 6) == 0.0
    assert channels._overlap("5 GHz", 36, 40) == 0.0


def test_dfs_flagged_and_5ghz():
    aps = [ap(36, "5 GHz", -50), ap(149, "5 GHz", -50), ap(44, "5 GHz", -55, ssid="Mine")]
    b = channels.analyze(aps, "live", own_ssid="Mine")["bands"]["5 GHz"]
    assert all(c["dfs"] is False for c in b["candidates"])  # default candidates avoid DFS
    assert channels.DFS_5GHZ and 100 in channels.DFS_5GHZ


def test_no_recommendation_from_simulated_data():
    r = channels.analyze([ap(1, "2.4 GHz", -40)], "simulated")
    b = r["bands"]["2.4 GHz"]
    assert b["recommendation"] is None and "real scans" in b["recommendation_withheld"]


def test_empty_band_says_any_channel():
    rec = channels.analyze([ap(6, "2.4 GHz", -50, ssid="Mine")], "live", own_ssid="Mine")["bands"]["2.4 GHz"]["recommendation"]
    assert rec["channel"] is None and "No neighbouring" in rec["reason"]


def test_assumptions_always_present():
    r = channels.analyze([], "live")
    assert any("never changes router settings" in a for a in r["assumptions"])


# ── standards ───────────────────────────────────────────────────

def iface(**kw):
    return WifiInterface(name="w", connected=True, **kw)


def test_generation_from_phy():
    assert standards.describe(iface(radio_type="802.11ax", band="5 GHz"))["generation"] == "Wi-Fi 6"
    assert standards.describe(iface(radio_type="802.11ax", band="6 GHz"))["generation"] == "Wi-Fi 6E"
    assert standards.describe(iface(radio_type="802.11be"))["generation"] == "Wi-Fi 7"
    assert standards.describe(iface(radio_type="802.11ac"))["generation"] == "Wi-Fi 5"
    assert standards.describe(iface(radio_type="802.11n"))["generation"] == "Wi-Fi 4"


def test_no_generation_guessed_from_band():
    d = standards.describe(iface(band="6 GHz"))
    assert d["generation"] is None and d["six_ghz"] is True
    assert any("6E" in n for n in d["notes"])


def test_mlo_is_unavailable_not_invented():
    assert standards.describe(iface(radio_type="802.11be"))["mlo"]["status"] == "unavailable"


def test_linux_iw_reports_width_and_phy():
    link = linux.parse_iw_link(fx.IW_LINK)
    assert link["width"] == 80 and link["phy"] == "802.11ac"
    eht = linux.parse_iw_link(fx.IW_LINK.replace("VHT-MCS 9 80MHz", "EHT-MCS 11 320MHz"))
    assert eht["phy"] == "802.11be" and eht["width"] == 320


def test_macos_reports_width():
    [i] = macos.parse_system_profiler(fx.SYSTEM_PROFILER_JSON)["interfaces"]
    assert i.channel_width_mhz == 80
