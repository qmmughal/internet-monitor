import csv
import io

from internet_monitor.history import AlertManager, History, Sample, detect_anomalies, percentile, summarize
from internet_monitor.config import DEFAULTS

TH = DEFAULTS["thresholds"]


def s(ts, sig=-55, bssid="02:00:00:00:00:01", ssid="Home", connected=True, **kw):
    return Sample(ts=ts, mode="live", connected=connected, ssid=ssid if connected else None,
                  bssid=bssid if connected else None, signal_dbm=sig if connected else None,
                  signal_mode="live" if connected else None, **kw)


def test_percentile_and_summary():
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 50) is None
    sm = summarize([10.0, 20.0, 30.0])
    assert sm["avg"] == 20.0 and sm["min"] == 10.0 and sm["max"] == 30.0 and sm["latest"] == 30.0


def test_retention_is_bounded():
    h = History(max_samples=10)
    for i in range(50):
        h.add(s(1000 + i))
    assert len(h.window(None)) == 10


def test_stats_window_and_provenance_counts():
    h = History()
    for i in range(10):
        h.add(s(1000 + i * 10, sig=-60, gateway_ms=2.0))
    st = h.stats(45, now=1090)
    assert st["samples"] == 5
    assert st["signal_dbm"]["avg"] == -60
    assert st["connected_pct"] == 100.0
    assert st["simulated_samples"] == 0


def test_baseline_needs_enough_samples():
    h = History()
    now = 10_000
    for i in range(12):  # baseline hour: -50 dBm
        h.add(s(now - 3000 + i * 60, sig=-50))
    for i in range(4):   # last 5 minutes: -65 dBm
        h.add(s(now - 200 + i * 40, sig=-65))
    b = h.baseline(now=now)
    assert b["signal_dbm"]["change"] == -15
    assert b["gateway_ms"] is None  # no data → no comparison, not zero


def test_roam_and_network_change_events():
    h = History()
    h.add(s(1, bssid="02:00:00:00:00:01"))
    h.add(s(2, bssid="02:00:00:00:00:02"))
    h.add(s(3, bssid="02:00:00:00:00:03", ssid="Other"))
    types = [e.type for e in h.event_list(None)]
    assert types == ["roam", "network_change"]
    roam = h.event_list(None)[0]
    assert roam.data["from_bssid"] == "02:00:00:00:00:01" and roam.data["to_bssid"] == "02:00:00:00:00:02"


def test_disconnect_reconnect_and_alert():
    h = History()
    h.add(s(1))
    found = h.add(s(2, connected=False, error="no Wi-Fi interface is connected"))
    assert any(a["rule"] == "disconnect" for a in found)
    h.add(s(3))
    assert [e.type for e in h.event_list(None)] == ["disconnect", "reconnect"]
    assert h.alerts.list()[0].type == "disconnect"


def test_sudden_signal_drop_needs_baseline():
    hist = [s(i, sig=-50) for i in range(3)] + [s(3, sig=-70)]
    assert not any(a["rule"] == "signal_drop" for a in detect_anomalies(hist, [], TH))  # too few samples
    hist = [s(i, sig=-50) for i in range(8)] + [s(8, sig=-65)]
    drop = next(a for a in detect_anomalies(hist, [], TH) if a["rule"] == "signal_drop")
    assert "median" in " ".join(drop["evidence"])


def test_signal_drop_ignores_roam_to_other_ap():
    hist = [s(i, sig=-45, bssid="02:00:00:00:00:01") for i in range(8)] + [s(8, sig=-70, bssid="02:00:00:00:00:02")]
    assert not any(a["rule"] == "signal_drop" for a in detect_anomalies(hist, [], TH))


def test_weak_signal_requires_three_samples():
    assert not any(a["rule"] == "weak_signal" for a in detect_anomalies([s(0, -60), s(1, -80), s(2, -80)], [], TH))
    weak = [a for a in detect_anomalies([s(0, -80), s(1, -81), s(2, -82)], [], TH) if a["rule"] == "weak_signal"]
    assert weak and "-80, -81, -82" in weak[0]["evidence"][0]


def test_estimated_signal_is_disclosed():
    hist = [Sample(ts=i, mode="live", connected=True, signal_dbm=-82, signal_mode="estimated") for i in range(3)]
    weak = next(a for a in detect_anomalies(hist, [], TH) if a["rule"] == "weak_signal")
    assert "estimated" in weak["detail"]


def test_latency_spike():
    hist = [s(i, gateway_ms=2.0) for i in range(8)] + [s(8, gateway_ms=80.0)]
    spike = next(a for a in detect_anomalies(hist, [], TH) if a["rule"] == "gateway_ms_spike")
    assert "40.0×" in spike["detail"]
    # small absolute values never alert even when relatively large
    hist = [s(i, gateway_ms=1.0) for i in range(8)] + [s(8, gateway_ms=10.0)]
    assert not any(a["rule"] == "gateway_ms_spike" for a in detect_anomalies(hist, [], TH))


def test_dns_slow_and_gateway_loss():
    hist = [s(i, dns_ms=500.0) for i in range(3)]
    assert any(a["rule"] == "dns_slow" for a in detect_anomalies(hist, [], TH))
    assert any(a["rule"] == "gateway_loss" for a in detect_anomalies([s(0, gateway_loss_pct=33.3)], [], TH))


def test_repeated_disconnects():
    h = History()
    t = 0
    for _ in range(3):
        h.add(s(t)); t += 10
        found = h.add(s(t, connected=False)); t += 10
    assert any(a["rule"] == "repeated_disconnects" and a["severity"] == "critical" for a in found)


def test_alert_cooldown_and_ack():
    am = AlertManager()
    a = am.raise_alert("k", "t", "warning", "x", "d", [], False, now=100, cooldown_s=300)
    assert am.raise_alert("k", "t", "warning", "x", "d", [], False, now=200, cooldown_s=300) is None
    assert am.raise_alert("k", "t", "warning", "x", "d", [], False, now=500, cooldown_s=300) is not None
    assert am.acknowledge(a.id) and not am.acknowledge(9999)
    assert len(am.list(include_acknowledged=False)) == 1


def test_alert_listener_errors_are_contained():
    def boom(_):
        raise RuntimeError("integration down")
    am = AlertManager(on_alert=boom)
    assert am.raise_alert("k", "t", "info", "x", "d", [], False, now=1) is not None


def test_simulated_samples_mark_alerts():
    h = History()
    h.add(Sample(ts=1, mode="simulated", connected=True, signal_dbm=-50, signal_mode="simulated"))
    h.add(Sample(ts=2, mode="simulated", connected=False))
    assert h.alerts.list()[0].simulated is True


def test_csv_export_neutralises_formulas():
    h = History()
    h.add(s(1, ssid="=HYPERLINK(\"x\")"))
    rows = list(csv.DictReader(io.StringIO(h.to_csv())))
    assert rows[0]["ssid"].startswith("'=")
    assert rows[0]["is_simulated"] == "False"


def test_clear():
    h = History()
    h.add(s(1)); h.add(s(2, connected=False))
    h.clear()
    assert not h.window(None) and not h.event_list(None) and not h.alerts.list()
