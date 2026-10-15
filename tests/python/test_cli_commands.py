import json

from wifi_monitor import cli, commands, hub


def test_history_without_server_explains(capsys):
    code = cli.main(["history", "--url", "http://127.0.0.1:9"])
    assert code == cli.EXIT_UNAVAILABLE
    assert "wifi-monitor serve" in capsys.readouterr().out


def test_alerts_without_server(capsys):
    assert cli.main(["alerts", "--url", "http://127.0.0.1:9"]) == cli.EXIT_UNAVAILABLE


def test_channels_demo_json(capsys):
    assert cli.main(["channels", "--demo", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "simulated" and data["bands"]["2.4 GHz"]["recommendation"] is None


def test_survey_cli_flow(capsys, monkeypatch):
    monkeypatch.setattr("wifi_monitor.survey.time.sleep", lambda s: None)
    assert cli.main(["survey", "add", "Kitchen", "--demo", "--samples", "2"]) == 0
    assert cli.main(["survey", "report", "--json"]) == 0
    out = capsys.readouterr().out
    report = json.loads(out[out.index("{"):])
    assert report["points"][0]["label"] == "Kitchen" and report["simulated"]
    assert cli.main(["survey", "add"]) == cli.EXIT_USAGE


def test_ask_rule_based_without_ai(capsys):
    assert cli.main(["ask", "why", "slow", "--no-diagnose", "--json"]) == 0
    res = json.loads(capsys.readouterr().out)
    assert res["source"] == "deterministic" and res["question"] == "why slow"


def test_ask_preview(capsys):
    assert cli.main(["ask", "--no-diagnose", "--preview", "--json"]) == 0
    assert "<network_data>" in json.loads(capsys.readouterr().out)["user"]


def test_devices_uses_discover(monkeypatch, capsys):
    monkeypatch.setattr(commands.devices, "discover", lambda probe, known: {
        "result": {"mode": "live", "data": [{"ip": "192.168.1.1", "mac": "aa:aa:aa:00:00:01", "name": None,
                                             "vendor": None, "is_gateway": True, "new": False,
                                             "randomized_mac": False, "first_seen": "t"}]},
        "method": "passive", "sweep": None, "limitations": ["x"], "new_devices": []})
    assert cli.main(["devices"]) == 0
    assert "router" in capsys.readouterr().out


def test_devices_name_validation(capsys):
    assert cli.main(["devices", "--name", "bad", "x"]) == cli.EXIT_USAGE
    assert cli.main(["devices", "--name", "aa:bb:cc:dd:ee:ff", "TV"]) == 0


def test_hub_token_lifecycle(capsys):
    assert cli.main(["hub", "token", "add", "agents", "pi"]) == 0
    token = capsys.readouterr().out.strip().splitlines()[-1]
    assert hub.TokenStore().verify("agents", token) == "pi"
    assert cli.main(["hub", "token", "list"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["agents"]["pi"]["revoked"] is False and token not in json.dumps(listing)
    assert cli.main(["hub", "token", "revoke", "agents", "pi"]) == 0
    assert cli.main(["hub", "token", "add", "agents", "bad name"]) == cli.EXIT_USAGE


def test_agent_requires_token(monkeypatch, capsys):
    monkeypatch.delenv("WIFI_MONITOR_AGENT_TOKEN", raising=False)
    assert cli.main(["agent", "--hub", "https://hub.example"]) == cli.EXIT_USAGE


def test_agent_refuses_remote_http(monkeypatch, capsys):
    monkeypatch.setenv("WIFI_MONITOR_AGENT_TOKEN", "t")
    assert cli.main(["agent", "--hub", "http://192.168.1.5:8766", "--once"]) == cli.EXIT_USAGE
    assert "plain HTTP" in capsys.readouterr().out
