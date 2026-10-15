"""Diagnostics engine scenarios with fake probes (no network access)."""

from internet_monitor.diagnostics import DiagnosticsConfig, Probes, run_diagnostics
from internet_monitor.models import ESTIMATED, Measurement, ProviderResult, WifiInterface
from internet_monitor.probes import LatencySample

CFG = DiagnosticsConfig(dns_hosts=("a.test", "b.test"),
                        https_endpoints=(("https://a.test/generate_204", 204), ("https://b.test/", None)),
                        tcp_targets=(("192.0.2.1", 443), ("198.51.100.1", 443)))


def route_ok():
    return ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1", "interface": "x", "local_ip": "192.168.1.5"})


def route_none():
    return ProviderResult(mode="unavailable", source="t", error="no IPv4 default gateway found",
                          data={"gateway": None, "interface": None, "local_ip": None})


def ping_ok(host, count=4, timeout_s=1.0):
    return LatencySample(host, "icmp", count, count, [2.0] * count)


def ping_dead(host, count=4, timeout_s=1.0):
    return LatencySample(host, "icmp", count, 0, [])


def ping_lossy(host, count=4, timeout_s=1.0):
    return LatencySample(host, "icmp", count, count - 1, [2.0] * (count - 1))


def ping_slow(host, count=4, timeout_s=1.0):
    return LatencySample(host, "icmp", count, count, [120.0] * count)


def tcp_dead(host, port, timeout_s=2.0):
    return {"reachable": False, "open": False, "error": "timeout"}


def tcp_refused(host, port, timeout_s=2.0):
    return {"reachable": True, "open": False, "rtt_ms": 1.0}


def dns_ok(host, timeout_s=3.0):
    return {"host": host, "ok": True, "ms": 20.0, "addresses": ["192.0.2.10"], "error": None}


def dns_fail(host, timeout_s=3.0):
    return {"host": host, "ok": False, "ms": None, "addresses": [], "error": "timeout"}


def dns_slow(host, timeout_s=3.0):
    return dict(dns_ok(host), ms=900.0)


def https_ok(url, expect_status=None, timeout_s=5.0):
    return {"url": url, "ok": True, "status": expect_status or 200, "ms": 80.0, "error": None, "captive_portal_suspected": False}


def https_fail(url, expect_status=None, timeout_s=5.0):
    return {"url": url, "ok": False, "status": None, "ms": None, "error": "timeout", "captive_portal_suspected": False}


def https_captive(url, expect_status=None, timeout_s=5.0):
    captive = expect_status is not None
    return {"url": url, "ok": not captive, "status": 302 if captive else 200, "ms": 50.0, "error": None,
            "captive_portal_suspected": captive}


def https_one_fails(url, expect_status=None, timeout_s=5.0):
    return https_fail(url) if "b.test" in url else https_ok(url, expect_status)


def lat(rtts, sent=5):
    def f(host, port=443, count=5, timeout_s=2.0):
        return LatencySample(f"{host}:{port}", "tcp", sent, len(rtts), list(rtts))
    return f


lat_ok = lat([20.0, 22.0, 21.0, 20.0, 23.0])
lat_dead = lat([])
lat_slow = lat([300.0, 310.0, 305.0, 300.0, 302.0])
lat_jittery = lat([20.0, 90.0, 15.0, 100.0, 10.0])
lat_lossy = lat([20.0, 21.0, 22.0])


def run(**overrides):
    base = dict(route=route_ok, ping=ping_ok, tcp_connect=tcp_dead, tcp_latency=lat_ok, resolve=dns_ok, https=https_ok)
    base.update(overrides)
    return run_diagnostics(CFG, Probes(**base))


def titles(report):
    return [f.title for f in report.findings]


def test_healthy():
    r = run()
    assert r.overall == "healthy"
    assert titles(r) == ["No connectivity problems detected"]
    assert r.findings[0].evidence


def test_no_route_and_nothing_works_is_offline():
    r = run(route=route_none, resolve=dns_fail, https=https_fail, tcp_latency=lat_dead)
    assert r.overall == "offline"
    assert titles(r) == ["Not connected to a network"]
    assert "gateway" not in r.evidence  # no gateway → nothing to ping


def test_no_route_but_internet_works_is_not_offline():
    r = run(route=route_none)
    assert r.overall == "healthy"
    assert "Default gateway could not be determined" in titles(r)


def test_router_unreachable_and_no_internet():
    r = run(ping=ping_dead, resolve=dns_fail, https=https_fail, tcp_latency=lat_dead)
    assert r.overall == "offline"
    assert titles(r) == ["Cannot reach the router or the internet"]
    assert r.evidence["gateway"]["tcp"]["port"] == 443  # tried all fallbacks


def test_router_ignores_ping_but_tcp_refused_counts_as_reachable():
    r = run(ping=ping_dead, tcp_connect=tcp_refused, resolve=dns_fail, https=https_fail, tcp_latency=lat_dead)
    assert "No internet access beyond the router" in titles(r)
    assert r.findings[-1].confidence == "high"


def test_router_ignores_ping_internet_fine_is_info_only():
    r = run(ping=ping_dead)
    assert r.overall == "healthy"
    assert "Router does not answer ping" in titles(r)


def test_dns_failure_isolated_by_ip_connectivity():
    r = run(resolve=dns_fail, https=https_fail)
    assert r.overall == "offline"
    f = r.findings[-1]
    assert f.title == "DNS resolution is failing" and f.confidence == "high"
    assert any("TCP" in e for e in f.evidence)


def test_upstream_outage():
    r = run(resolve=dns_fail, https=https_fail, tcp_latency=lat_dead)
    assert titles(r)[-1] == "No internet access beyond the router"


def test_https_blocked_but_tcp_works():
    r = run(https=https_fail)
    assert r.overall == "degraded"
    assert "HTTPS endpoints are failing" in titles(r)


def test_captive_portal():
    r = run(https=https_captive)
    assert "Captive portal or proxy suspected" in titles(r)


def test_single_endpoint_failure_is_not_an_outage():
    r = run(https=https_one_fails)
    assert r.overall == "healthy"
    assert "Some test endpoints failed" in titles(r)


def test_packet_loss_to_router():
    r = run(ping=ping_lossy)
    assert r.overall == "degraded" and "Packet loss to the router" in titles(r)


def test_high_router_latency_blames_local_link():
    r = run(ping=ping_slow, tcp_latency=lat_slow)
    assert "High latency to the router" in titles(r)
    inet = next(f for f in r.findings if f.title == "High internet latency")
    assert "local Wi-Fi link" in inet.likely_cause


def test_high_internet_latency_with_fast_router_blames_upstream():
    r = run(tcp_latency=lat_slow)
    inet = next(f for f in r.findings if f.title == "High internet latency")
    assert "upstream" in inet.likely_cause


def test_jitter_and_intermittent_failures():
    assert "Unstable latency (jitter)" in titles(run(tcp_latency=lat_jittery))
    assert "Intermittent connection failures" in titles(run(tcp_latency=lat_lossy))


def test_slow_dns():
    assert "Slow DNS responses" in titles(run(resolve=dns_slow))


def wifi_with(dbm, mode=ESTIMATED):
    iface = WifiInterface(name="w", connected=True, signal_dbm=Measurement(dbm, "dBm", "t", mode))
    return lambda: ProviderResult(mode="live", source="t", data=[iface])


def test_weak_signal_mentions_estimate():
    r = run(wifi=wifi_with(-82))
    f = next(f for f in r.findings if f.title == "Weak Wi-Fi signal")
    assert "estimated" in f.evidence[0] and f.confidence == "medium"


def test_wifi_unavailable_is_reported_not_hidden():
    r = run(wifi=lambda: ProviderResult(mode="unavailable", source="netsh", error="no Wi-Fi interface found",
                                        hint=None))
    assert r.overall == "healthy"
    assert "Wi-Fi details unavailable" in titles(r)


def test_report_is_json_serialisable():
    import json

    json.dumps(run(ping=ping_lossy).to_dict())
