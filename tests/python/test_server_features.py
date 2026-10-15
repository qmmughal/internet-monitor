"""New API endpoints: history, alerts, devices, speed test, survey, AI, metrics."""

import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from internet_monitor import server
from internet_monitor.diagnostics import Report
from internet_monitor.history import History, Sample
from internet_monitor.models import ProviderResult
from internet_monitor.providers import DemoProvider


def route():
    return ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1", "local_ip": "192.168.1.5"})


def report():
    return Report(started="a", finished="b", overall="healthy", duration_ms=1, evidence={}, findings=[])


def discover(probe=False):
    return {"result": {"mode": "live", "data": [
        {"ip": "192.168.1.1", "mac": "aa:aa:aa:00:00:01", "is_gateway": True, "randomized_mac": False, "vendor": None},
        {"ip": "192.168.1.9", "mac": "aa:aa:aa:00:00:09", "is_gateway": False, "randomized_mac": True, "vendor": None}]},
        "new_devices": ["aa:aa:aa:00:00:09"], "sweep": None, "method": "passive", "limitations": []}


def app(**kw):
    h = History()
    t = time.time()
    for i in range(5):
        h.add(Sample(ts=t - 50 + i * 10, mode="live", connected=True, ssid="Home", bssid="02:00:00:00:00:01",
                     signal_dbm=-60 + i, signal_mode="live", gateway_ms=2.0))
    defaults = dict(provider=DemoProvider(seed=1), route_fn=route, diagnostics_fn=report, history=h,
                    discover_fn=discover, speedtest_fn=lambda max_mb: {"mode": "live", "download_mbps": 90.0, "max_mb": max_mb})
    defaults.update(kw)
    return server.App(**defaults)


def test_history_and_stats():
    a = app()
    status, body = a.get("/api/v1/history", {"limit": ["3"]})
    assert status == 200 and body["count"] == 3 and "memory" in body["storage"]
    status, body = a.get("/api/v1/history/stats", {"window": ["3600"]})
    assert body["stats"]["samples"] == 5 and body["thresholds"]["weak_signal_dbm"] == -75


@pytest.mark.parametrize("q", [{"window": ["abc"]}, {"window": ["1"]}, {"limit": ["0"]}, {"limit": ["99999"]}])
def test_query_validation(q):
    assert app().get("/api/v1/history", q)[0] == 400


def test_export_csv_and_json():
    status, raw = app().get("/api/v1/history/export", {"format": ["csv"]})
    assert isinstance(raw, server.Raw) and raw.content_type.startswith("text/csv") and raw.filename.endswith(".csv")
    assert raw.body.decode().startswith("timestamp,mode,is_simulated")
    status, raw = app().get("/api/v1/history/export", {"format": ["json"]})
    assert len(json.loads(raw.body)) == 5
    assert app().get("/api/v1/history/export", {"format": ["xml"]})[0] == 400


def test_devices_scan_raises_new_device_alert_and_name():
    a = app(provider=DemoProvider(), demo=False)
    assert a.get("/api/v1/devices")[0] == 404
    status, body = a.post("/api/v1/devices/scan", {"probe": False})
    assert status == 200 and a.get("/api/v1/devices")[0] == 200
    alerts = a.get("/api/v1/alerts")[1]["alerts"]
    assert alerts[-1]["type"] == "new_device" and "randomized" in " ".join(alerts[-1]["evidence"])
    assert a.post("/api/v1/devices/scan", {"probe": "yes"})[0] == 400
    assert a.post("/api/v1/devices/name", {"mac": "aa:aa:aa:00:00:09", "name": "Phone"})[0] == 200
    assert a.post("/api/v1/devices/name", {"mac": "nope", "name": "x"})[0] == 400


def test_security_endpoint():
    a = app()
    body = a.get("/api/v1/security")[1]
    assert body["devices_scanned"] is False and "not proof" in body["note"]


def test_alert_ack_and_clear():
    a = app()
    a.history.alerts.raise_alert("k", "t", "warning", "T", "D", [], False, now=1)
    aid = a.get("/api/v1/alerts")[1]["alerts"][0]["id"]
    assert a.post("/api/v1/alerts/ack", {"id": aid})[0] == 200
    assert a.get("/api/v1/alerts", {"active": ["1"]})[1]["alerts"] == []
    assert a.post("/api/v1/alerts/ack", {"id": 999})[0] == 404
    assert a.post("/api/v1/alerts/ack", {"id": "1"})[0] == 400
    assert a.post("/api/v1/alerts/clear")[0] == 200 and a.get("/api/v1/alerts")[1]["alerts"] == []


def test_speedtest_validation_and_demo():
    a = app()
    assert a.post("/api/v1/speedtest", {"max_mb": 1})[0] == 400
    assert a.post("/api/v1/speedtest", {"max_mb": True})[0] == 400
    status, body = a.post("/api/v1/speedtest", {"max_mb": 20})
    assert status == 200 and body["max_mb"] == 20 and a.get("/api/v1/speedtest")[0] == 200
    assert app(demo=True).post("/api/v1/speedtest", {})[0] == 400
    assert app(demo=True).post("/api/v1/devices/scan", {})[0] == 400


def test_survey_endpoints():
    a = app()
    status, body = a.post("/api/v1/survey/points", {"label": "Kitchen", "samples": 1})
    assert status == 200 and body["ok"] and body["point"]["mode"] == "simulated"
    assert a.get("/api/v1/survey")[1]["points"][0]["label"] == "Kitchen"
    assert a.post("/api/v1/survey/points", {"label": "x", "samples": 99})[0] == 400
    assert a.post("/api/v1/survey/points", {"label": ""})[0] == 400
    assert a.post("/api/v1/survey/clear")[0] == 200


def test_ai_ask_runs_diagnostics_first_and_falls_back():
    a = app()
    assert a.last_report is None
    status, body = a.post("/api/v1/ai/ask", {"question": "why?"})
    assert status == 200 and body["source"] == "deterministic" and a.last_report is not None
    assert a.post("/api/v1/ai/ask", {"question": "x" * 600})[0] == 400
    assert a.get("/api/v1/ai/status")[1]["enabled"] is False
    preview = a.post("/api/v1/ai/preview", {"question": "why?"})[1]
    assert "<network_data>" in preview["user"]


def test_channels_and_standard_demo():
    a = app(demo=True)
    body = a.get("/api/v1/channels")[1]
    assert body["mode"] == "simulated"
    assert all(b["recommendation"] is None for b in body["bands"].values())
    assert a.get("/api/v1/wifi/standard")[1]["generation"] == "Wi-Fi 6"


def test_metrics_endpoint():
    status, raw = app().get("/metrics")
    assert status == 200 and b"internet_monitor_signal_dbm" in raw.body and raw.content_type.startswith("text/plain")


def test_history_clear():
    a = app()
    assert a.post("/api/v1/history/clear")[0] == 200 and a.get("/api/v1/history")[1]["count"] == 0


# ── HTTP-level body handling ─────────────────────────────────────

@pytest.fixture
def port(tmp_path):
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app(), False, static_root=tmp_path))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def post(port, path, body, ctype="application/json"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body=body, headers={server.API_HEADER: "1", "Content-Type": ctype})
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


def test_post_body_rules(port):
    assert post(port, "/api/v1/alerts/clear", b"{}")[0] == 200
    assert post(port, "/api/v1/alerts/clear", b"{}", ctype="text/plain")[0] == 415
    assert post(port, "/api/v1/alerts/clear", b"{bad")[0] == 400
    assert post(port, "/api/v1/alerts/clear", b"[1,2]")[0] == 400
    assert post(port, "/api/v1/alerts/clear", b"x" * (server.MAX_POST_BODY + 1))[0] == 413


def test_export_download_headers(port):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("GET", "/api/v1/history/export?format=csv")
    r = conn.getresponse()
    r.read()
    conn.close()
    assert r.status == 200 and "attachment" in r.getheader("Content-Disposition")
