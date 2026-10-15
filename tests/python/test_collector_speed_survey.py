import pytest

from wifi_monitor import speedtest, survey
from wifi_monitor.collector import Collector
from wifi_monitor.history import History
from wifi_monitor.models import Measurement, ProviderResult, WifiInterface
from wifi_monitor.probes import LatencySample
from wifi_monitor.providers import DemoProvider


class OneIface:
    name = "fake"

    def __init__(self, dbm=-60, ok=True):
        self.dbm, self.ok = dbm, ok

    def connected_interface(self):
        if not self.ok:
            return ProviderResult(mode="unavailable", source="t", error="no Wi-Fi")
        return ProviderResult(mode="live", source="t", data=WifiInterface(
            name="w", connected=True, ssid="Home", bssid="02:00:00:00:00:01", channel=36, band="5 GHz",
            signal_dbm=Measurement(self.dbm, "dBm", "t", "estimated")))


def route():
    return ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1"})


def make(provider, demo=False, every=2):
    calls = {"ping": 0}

    def ping(host, count=3, timeout_s=1.0):
        calls["ping"] += 1
        return LatencySample(host, "icmp", 3, 3, [1.0, 2.0, 3.0])

    c = Collector(provider, History(), interval_s=2, latency_every=every, demo=demo, route_fn=route, ping_fn=ping,
                  tcp_fn=lambda h, p, count=1, timeout_s=2.0: LatencySample(h, "tcp", 1, 1, [20.0]),
                  dns_fn=lambda h, timeout_s=3.0: {"ok": True, "ms": 5.0})
    return c, calls


def test_collector_measures_and_records():
    c, calls = make(OneIface())
    s1 = c.tick()
    s2 = c.tick()
    assert s1.signal_dbm == -60 and s1.signal_mode == "estimated"
    assert s1.gateway_ms == 2.0 and s1.internet_ms == 20.0 and s1.dns_ms == 5.0
    assert s2.gateway_ms is None  # latency only every 2nd cycle
    assert calls["ping"] == 1 and len(c.history.window(None)) == 2


def test_collector_unavailable_wifi_still_measures_network():
    c, _ = make(OneIface(ok=False))
    s = c.tick()
    assert not s.connected and s.error == "no Wi-Fi" and s.gateway_ms == 2.0


def test_collector_demo_sends_no_probes():
    c, calls = make(DemoProvider(seed=1), demo=True)
    s = c.tick()
    assert s.mode == "simulated" and calls["ping"] == 0 and s.internet_ms is None


def test_collector_listener_failure_contained():
    c, _ = make(OneIface())

    def bad(_):
        raise RuntimeError("mqtt down")
    c.listeners.append(bad)
    c.tick()
    assert "mqtt down" in c.last_error


def test_collector_thread_start_stop():
    c, _ = make(OneIface())
    c.interval_s = 2
    c.start()
    assert c.running
    c.stop()
    assert not c.running and c.history.window(None)


# ── speed test (fake transfers) ──────────────────────────────────

def fake_lat(host, port, count=8, timeout_s=2.0):
    return LatencySample(host, "tcp", count, count, [10.0, 12.0, 11.0])


def test_speedtest_respects_budget_and_picks_largest():
    downs, ups = [], []

    def down(n):
        downs.append(n)
        return {"bytes": n, "seconds": n / 12.5e6, "mbps": 100.0 if n >= 10_000_000 else 40.0, "error": None}

    def up(n):
        ups.append(n)
        return {"bytes": n, "seconds": 0.5, "mbps": 20.0, "error": None}

    r = speedtest.run(max_mb=50, latency_fn=fake_lat, down_fn=down, up_fn=up)
    assert r["mode"] == "live" and r["download_mbps"] == 100.0 and r["upload_mbps"] == 20.0
    assert sum(downs) + sum(ups) <= 50_000_000
    assert r["data_used_mb"] <= 50 and r["latency"]["median_ms"] == 11.0


def test_speedtest_failure_is_unavailable():
    r = speedtest.run(max_mb=10, latency_fn=fake_lat, down_fn=lambda n: {"bytes": 0, "error": "timed out"},
                      up_fn=lambda n: {"bytes": 0, "error": "timed out"})
    assert r["mode"] == "unavailable" and r["download_mbps"] is None and "timed out" in r["errors"]


def test_speedtest_clamps_budget():
    seen = []
    speedtest.run(max_mb=10_000, latency_fn=fake_lat,
                  down_fn=lambda n: seen.append(n) or {"bytes": n, "seconds": 0.1, "mbps": 1.0, "error": None},
                  up_fn=lambda n: seen.append(n) or {"bytes": n, "seconds": 0.1, "mbps": 1.0, "error": None})
    assert sum(seen) <= 500_000_000


# ── survey ───────────────────────────────────────────────────────

def test_survey_record_and_report():
    survey.record("Kitchen", OneIface(-55), samples=3, sleep=lambda s: None)
    survey.record("Garage", OneIface(-85), samples=3, sleep=lambda s: None)
    survey.record("Bedroom", OneIface(-72), samples=3, sleep=lambda s: None)
    rep = survey.report()
    assert [p["label"] for p in rep["points"]] == ["Kitchen", "Bedroom", "Garage"]
    assert [p["zone"] for p in rep["points"]] == ["ok", "weak", "dead"]
    assert rep["weak_spots"] == ["Bedroom", "Garage"] and rep["advice"]
    assert rep["points"][0]["mode"] == "estimated"


def test_survey_rerecord_replaces_and_clear():
    survey.record("Kitchen", OneIface(-55), samples=1, sleep=lambda s: None)
    survey.record("Kitchen", OneIface(-65), samples=1, sleep=lambda s: None)
    assert [p["median_dbm"] for p in survey.load()] == [-65]
    survey.clear()
    assert survey.load() == []


def test_survey_unavailable_and_label_validation():
    assert survey.record("Hall", OneIface(ok=False), samples=1, sleep=lambda s: None)["ok"] is False
    with pytest.raises(ValueError):
        survey.clean_label("\x00\x01")
    assert survey.clean_label("  Kitchen\x1b  ") == "Kitchen"


def test_survey_demo_is_simulated():
    res = survey.record("Demo", DemoProvider(seed=2), samples=2, sleep=lambda s: None, persist=False)
    assert res["point"]["mode"] == "simulated"
