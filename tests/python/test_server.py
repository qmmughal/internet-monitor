import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from internet_monitor import server
from internet_monitor.diagnostics import Report
from internet_monitor.models import ProviderResult
from internet_monitor.providers import DemoProvider
from internet_monitor.providers.base import WifiProvider


class NoWifi(WifiProvider):
    name = "nowifi"

    def interfaces(self):
        return ProviderResult(mode="unavailable", source="test", error="no Wi-Fi interface found")

    def access_points(self):
        return self.interfaces()

    def capabilities(self):
        return {}


def fake_report():
    return Report(started="t0", finished="t1", overall="healthy", duration_ms=1, evidence={}, findings=[])


@pytest.fixture
def make_server(tmp_path):
    (tmp_path / "index.html").write_text("<html>ok</html>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("inside", encoding="utf-8")
    started = []

    def start(app, allow_remote=False):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app, allow_remote, static_root=tmp_path))
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        started.append(httpd)
        return httpd.server_address[1]

    yield start
    for h in started:
        h.shutdown()
        h.server_close()


def request(port, method, path, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


def route():
    return ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1", "local_ip": "192.168.1.5"})


def test_status_unavailable_is_honest(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    resp, body = request(port, "GET", "/api/v1/status")
    data = json.loads(body)
    assert resp.status == 200
    assert data["wifi"]["mode"] == "unavailable" and data["wifi"]["data"] is None
    assert data["network"]["data"]["gateway"] == "192.168.1.1"
    assert resp.getheader("Access-Control-Allow-Origin") is None
    assert resp.getheader("Cache-Control") == "no-store"


def test_demo_status_is_labelled(make_server):
    port = make_server(server.App(demo=True, provider=DemoProvider(seed=1)))
    data = json.loads(request(port, "GET", "/api/v1/status")[1])
    assert data["demo"] is True and data["wifi"]["is_simulated"] is True


def test_signal_endpoint(make_server):
    port = make_server(server.App(demo=True, provider=DemoProvider(seed=1)))
    data = json.loads(request(port, "GET", "/api/v1/wifi/signal")[1])
    assert data["data"]["unit"] == "dBm" and data["data"]["mode"] == "simulated"


def test_dns_rebinding_host_rejected(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    resp, _ = request(port, "GET", "/api/v1/status", {"Host": "evil.example:8765"})
    assert resp.status == 421


@pytest.mark.parametrize("host", ["localhost:1", "127.0.0.1:1", "[::1]:1"])
def test_loopback_hosts_accepted(make_server, host):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    assert request(port, "GET", "/api/v1/capabilities", {"Host": host})[0].status == 200


def test_post_requires_custom_header(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route, diagnostics_fn=fake_report))
    assert request(port, "POST", "/api/v1/diagnostics")[0].status == 403
    resp, body = request(port, "POST", "/api/v1/diagnostics", {server.API_HEADER: "1"})
    assert resp.status == 200 and json.loads(body)["overall"] == "healthy"
    assert json.loads(request(port, "GET", "/api/v1/diagnostics")[1])["overall"] == "healthy"


def test_post_cross_origin_refused(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route, diagnostics_fn=fake_report))
    resp, _ = request(port, "POST", "/api/v1/diagnostics", {server.API_HEADER: "1", "Origin": "https://evil.example"})
    assert resp.status == 403


def test_diagnostics_disabled_in_demo(make_server):
    port = make_server(server.App(demo=True, provider=DemoProvider()))
    assert request(port, "POST", "/api/v1/diagnostics", {server.API_HEADER: "1"})[0].status == 400


def test_concurrent_diagnostics_rejected():
    app = server.App(provider=NoWifi(), route_fn=route, diagnostics_fn=fake_report)
    app.locks["diagnostics"].acquire()
    try:
        assert app.post("/api/v1/diagnostics")[0] == 409
    finally:
        app.locks["diagnostics"].release()


def test_static_and_csp(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    resp, body = request(port, "GET", "/")
    assert resp.status == 200 and body == b"<html>ok</html>"
    assert "default-src 'self'" in resp.getheader("Content-Security-Policy")


@pytest.mark.parametrize("path", ["/../pyproject.toml", "/%2e%2e/%2e%2e/etc/passwd", "/..%5c..%5cwindows/win.ini", "/nope.js"])
def test_path_traversal_blocked(make_server, path):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    assert request(port, "GET", path)[0].status == 404


def test_unknown_api_404(make_server):
    port = make_server(server.App(provider=NoWifi(), route_fn=route))
    assert request(port, "GET", "/api/v1/nope")[0].status == 404


def test_refuses_public_bind_without_flag(capsys):
    assert server.serve(host="0.0.0.0", port=0) == 2
    assert "Refusing" in capsys.readouterr().out


@pytest.mark.parametrize("host,ok", [("localhost", True), ("127.0.0.1", True), ("::1", True), ("[::1]", True),
                                     ("192.168.1.10", False), ("example.com", False)])
def test_is_loopback(host, ok):
    assert server.is_loopback(host) is ok
