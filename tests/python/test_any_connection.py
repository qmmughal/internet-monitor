"""Monitoring that works for any connection type, Wi-Fi adapter health, and activity in diagnostics."""

import json
import time

import fixtures as fx

from internet_monitor import cli, commands, hub, server
from internet_monitor.diagnostics import DiagnosticsConfig, Finding, Probes, run_diagnostics, _activity_findings
from internet_monitor.history import History, Sample, detect_anomalies
from internet_monitor.config import DEFAULTS
from internet_monitor.models import ProviderResult
from internet_monitor.probes import LatencySample
from internet_monitor.providers import DemoProvider, windows
from internet_monitor.runner import CommandResult

BROKEN = [{"name": "Wi-Fi", "description": "Intel(R) Wi-Fi 6E AX211 160MHz", "status": "", "admin": "Up",
           "pnp_status": "Error", "problem": "CM_PROB_FAILED_POST_START"}]


def test_explain_broken_adapter():
    err, hint = windows.explain_adapters(BROKEN)
    assert "AX211" in err and "code 43" in err and "Device Manager" in hint
    disabled = [dict(BROKEN[0], problem="", admin="Down")]
    assert "disabled" in windows.explain_adapters(disabled)[0]
    assert windows.explain_adapters([dict(BROKEN[0], problem="CM_PROB_NONE")]) is None
    assert windows.explain_adapters([]) is None


def test_provider_enriches_missing_interface():
    calls = []

    def runner(args, timeout=5):
        calls.append(args[0])
        if args[0] == "netsh":
            return CommandResult(args, 1, stdout=fx.NETSH_NO_WIRELESS)
        return CommandResult(args, 0, stdout=json.dumps(BROKEN))

    p = windows.WindowsProvider(runner=runner)
    res = p.interfaces()
    assert not res.ok and "not working" in res.error and "Device Manager" in res.hint
    p.interfaces()
    assert calls.count("powershell") == 1  # adapter health is cached


def test_radio_off_hint():
    text = fx.NETSH_IFACE_TWO.replace("Software On", "Software Off").replace("State                  : connected",
                                                                               "State                  : disconnected")
    p = windows.WindowsProvider(runner=lambda a, timeout=5: CommandResult(a, 0, stdout=text))
    res = p.connected_interface()
    assert not res.ok and "switched off" in res.hint
    assert windows.radio_off("Radio status : Hardware On\n   Software Off")


# ── activity in diagnostics ─────────────────────────────────────

def test_activity_busy_links_to_latency():
    f = [Finding("warning", "High internet latency", ["x"], "upstream", None, "medium")]
    _activity_findings({"traffic": {"primary": "Ethernet", "primary_type": "ethernet", "rx_bps": 10, "tx_bps": 1_000_000},
                        "top_apps": [{"app": "OneDrive", "bytes_received": 1e5, "bytes_sent": 8e7}]}, f)
    assert f[-1].title == "Heavy network use during the check" and "OneDrive" in " ".join(f[-1].evidence)
    assert "8.0 Mbps" in f[0].evidence[-1] and "Heavy traffic" in f[0].likely_cause


def test_activity_idle_is_info_and_errors_ignored():
    f = []
    _activity_findings({"traffic": {"primary": "Wi-Fi", "rx_bps": 100, "tx_bps": 100}, "top_apps": []}, f)
    assert f[0].severity == "info" and f[0].title == "Network activity during the check"
    g = []
    _activity_findings({"error": "boom"}, g)
    _activity_findings(None, g)
    assert g == []


def test_run_diagnostics_calls_activity():
    def route():
        return ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1"})
    p = Probes(route=route, ping=lambda h, count=4, timeout_s=1: LatencySample(h, "icmp", 4, 4, [1.0] * 4),
               tcp_latency=lambda h, port, count=5, timeout_s=2: LatencySample(h, "tcp", 5, 5, [20.0] * 5),
               resolve=lambda h, timeout_s=3: {"host": h, "ok": True, "ms": 5.0},
               https=lambda u, expect_status=None, timeout_s=5: {"url": u, "ok": True, "status": 204},
               activity=lambda: {"traffic": {"primary": "Ethernet", "rx_bps": 0, "tx_bps": 0}, "top_apps": []})
    r = run_diagnostics(DiagnosticsConfig(dns_hosts=("a",), https_endpoints=(("https://a/", None),),
                                          tcp_targets=(("1.1.1.1", 443),)), p)
    assert "activity" in r.evidence and r.overall == "healthy"


def test_activity_failure_does_not_break_diagnostics():
    def boom():
        raise RuntimeError("psutil exploded")
    p = Probes(route=lambda: ProviderResult(mode="unavailable", source="t", error="x", data={}),
               resolve=lambda h, timeout_s=3: {"host": h, "ok": False}, https=lambda u, expect_status=None, timeout_s=5: {"url": u, "ok": False},
               tcp_latency=lambda h, port, count=5, timeout_s=2: LatencySample(h, "tcp", 1, 0), activity=boom)
    r = run_diagnostics(DiagnosticsConfig(dns_hosts=("a",), https_endpoints=(("https://a/", None),),
                                          tcp_targets=(("1.1.1.1", 443),)), p)
    assert r.evidence["activity"]["error"] == "psutil exploded"


# ── history / hub with throughput ───────────────────────────────

def test_latency_spike_mentions_upload():
    hist = [Sample(ts=i, mode="live", connected=False, internet_ms=20.0) for i in range(8)]
    hist.append(Sample(ts=9, mode="live", connected=False, internet_ms=200.0, tx_bps=2_000_000))
    spike = next(a for a in detect_anomalies(hist, [], DEFAULTS["thresholds"]) if a["rule"] == "internet_ms_spike")
    assert "Heavy traffic" in spike["detail"] and any("uploading 16.0 Mbit/s" in e for e in spike["evidence"])


def test_history_stats_include_throughput():
    h = History()
    for i in range(3):
        h.add(Sample(ts=time.time() - 10 + i, mode="unavailable", connected=False, iface="Ethernet",
                     iface_type="ethernet", rx_bps=1000.0 * (i + 1), tx_bps=10.0))
    st = h.stats(3600)
    assert st["rx_bps"]["max"] == 3000.0 and "rx_bps" in h.to_csv().splitlines()[0]


def test_hub_accepts_old_and_new_agents():
    base = dict(ts=time.time(), mode="live", connected=True, ssid=None, bssid=None, signal_dbm=None, signal_mode=None,
                channel=None, band=None, gateway_ms=None, gateway_loss_pct=None, internet_ms=None, dns_ms=None, error=None)
    assert hub.parse_sample(base).rx_bps is None  # agent from before throughput existed
    s = hub.parse_sample(dict(base, iface="Ethernet", iface_type="ethernet", rx_bps=1000, tx_bps=20.5))
    assert s.iface_type == "ethernet" and s.tx_bps == 20.5


# ── API ─────────────────────────────────────────────────────────

class FakeSampler:
    def sample(self, min_interval=0.0):
        return {"mode": "live", "primary": "Ethernet", "primary_type": "ethernet", "rx_bps": 1000, "tx_bps": 50,
                "interfaces": [{"name": "Ethernet", "type": "ethernet", "primary": True}]}


class FakeTracker:
    def poll(self):
        return {"mode": "live", "source": "t", "apps": [{"app": "A", "rx_bps": 5}], "realtime": False}


def make_app(**kw):
    defaults = dict(provider=DemoProvider(seed=1), route_fn=lambda: ProviderResult(mode="live", source="t", data={}),
                    traffic=FakeSampler(), rate_tracker=FakeTracker(),
                    usage_fn=lambda w: {"mode": "live", "source": "t", "apps": [{"app": "Chrome", "bytes_received": 9,
                                                                                    "bytes_sent": 1}]},
                    connections_fn=lambda: {"mode": "live", "apps": [{"app": "Chrome"}]})
    defaults.update(kw)
    return server.App(**defaults)


def test_api_traffic_apps_connections():
    a = make_app()
    assert a.get("/api/v1/traffic")[1]["primary_type"] == "ethernet"
    assert a.get("/api/v1/status")[1]["traffic"]["rx_bps"] == 1000
    body = a.get("/api/v1/apps", {"window": ["3600"]})[1]
    assert body["window_s"] == 3600 and body["apps"][0]["app"] == "Chrome"
    assert a.get("/api/v1/apps", {"window": ["5"]})[0] == 400
    assert a.get("/api/v1/apps/live")[1]["apps"][0]["rx_bps"] == 5
    assert a.get("/api/v1/connections")[1]["apps"][0]["app"] == "Chrome"
    ai_data = a.ai_data()
    assert ai_data["traffic_now"]["primary"] == "Ethernet" and ai_data["top_apps_5min"][0]["app"] == "Chrome"


def test_api_demo_never_simulates_apps():
    a = make_app(demo=True)
    assert a.get("/api/v1/apps")[1]["mode"] == "unavailable"
    assert a.get("/api/v1/connections")[1]["mode"] == "unavailable"
    assert a.get("/api/v1/traffic")[1]["mode"] == "simulated" and a.get("/api/v1/traffic")[1]["interfaces"] == []


# ── CLI ─────────────────────────────────────────────────────────

def test_cli_apps(monkeypatch, capsys):
    import internet_monitor.apps as apps_mod
    monkeypatch.setattr(apps_mod, "usage", lambda w: {"mode": "live", "source": "t", "note": "n", "apps": [
        {"app": "Chrome", "bytes_received": 2_000_000, "bytes_sent": 1_000, "running": True}]})
    assert cli.main(["apps", "--window", "2h"]) == 0
    assert "Chrome" in capsys.readouterr().out
    assert cli.main(["apps", "--window", "soon"]) == cli.EXIT_USAGE


def test_cli_connections_filter(monkeypatch, capsys):
    import internet_monitor.apps as apps_mod
    monkeypatch.setattr(apps_mod, "connections", lambda: {"mode": "live", "note": "n", "apps": [
        {"app": "Google Chrome", "process": "chrome.exe", "pids": [1], "established": 1, "listening": [],
         "remotes": [{"ip": "1.2.3.4", "port": 443, "service": "https", "protocol": "tcp", "state": "ESTABLISHED",
                      "count": 1}]},
        {"app": "Other", "process": "o.exe", "pids": [2], "established": 0, "listening": [], "remotes": []}]})
    assert cli.main(["connections", "--app", "chrome", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [a["app"] for a in data["apps"]] == ["Google Chrome"]


def test_window_parsing():
    assert commands._window_seconds("5m") == 300 and commands._window_seconds("2h") == 7200
    assert commands._window_seconds("1d") == 86400 and commands._window_seconds("90") == 90


# ── rename compatibility (WiFi Monitor → Internet Monitor) ───────

def test_env_prefers_new_name_and_falls_back(monkeypatch):
    from internet_monitor import config
    monkeypatch.delenv("INTERNET_MONITOR_AGENT_TOKEN", raising=False)
    monkeypatch.setenv("WIFI_MONITOR_AGENT_TOKEN", "old")
    assert config.env("AGENT_TOKEN") == "old"
    assert config.env_var("INTERNET_MONITOR_AGENT_TOKEN") == "old"
    monkeypatch.setenv("INTERNET_MONITOR_AGENT_TOKEN", "new")
    assert config.env("AGENT_TOKEN") == "new" and config.env_var("INTERNET_MONITOR_AGENT_TOKEN") == "new"
    assert config.env_var("SOME_OTHER_VAR_XYZ") is None and config.env_var(None) is None


def test_legacy_config_folder_is_reused(monkeypatch, tmp_path):
    from internet_monitor import config
    monkeypatch.delenv("INTERNET_MONITOR_HOME", raising=False)
    monkeypatch.delenv("WIFI_MONITOR_HOME", raising=False)
    monkeypatch.setattr(config.sys, "platform", "linux")
    monkeypatch.setattr(config.Path, "home", staticmethod(lambda: tmp_path))
    assert config.home() == tmp_path / ".config" / "internet-monitor"
    (tmp_path / ".config" / "wifi-monitor").mkdir(parents=True)
    assert config.home() == tmp_path / ".config" / "wifi-monitor"
    (tmp_path / ".config" / "internet-monitor").mkdir()
    assert config.home() == tmp_path / ".config" / "internet-monitor"
