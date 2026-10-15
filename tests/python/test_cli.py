import csv
import json

import pytest

from internet_monitor import cli
from internet_monitor.models import ProviderResult
from internet_monitor.providers.base import WifiProvider


class NoWifi(WifiProvider):
    name = "nowifi"

    def interfaces(self):
        return ProviderResult(mode="unavailable", source="test", error="no Wi-Fi interface found", hint="plug it in")

    def access_points(self):
        return self.interfaces()

    def capabilities(self):
        return {"ssid": {"supported": False}}


@pytest.fixture
def no_wifi(monkeypatch):
    monkeypatch.setattr(cli, "get_provider", lambda demo=False: NoWifi())
    monkeypatch.setattr(cli.netinfo, "default_route",
                        lambda: ProviderResult(mode="live", source="t", data={"gateway": "192.168.1.1", "local_ip": "192.168.1.5"}))


def test_status_json_unavailable_never_fabricates(no_wifi, capsys):
    code = cli.main(["status", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == cli.EXIT_OK  # online through another connection (default route present)
    assert data["wifi"]["mode"] == "unavailable" and data["wifi"]["data"] is None
    assert data["network"]["data"]["gateway"] == "192.168.1.1"


def test_status_text_shows_reason_and_hint(no_wifi, capsys):
    cli.main(["status"])
    text = capsys.readouterr().out
    assert "no Wi-Fi interface found" in text and "plug it in" in text
    assert "dBm" not in text


def test_scan_unavailable(no_wifi, capsys):
    assert cli.main(["scan"]) == cli.EXIT_UNAVAILABLE


def test_monitor_unavailable_writes_honest_rows(no_wifi, tmp_path, capsys):
    out = tmp_path / "log.csv"
    code = cli.main(["monitor", "-n", "1", "-i", "1", "-o", str(out), "--json"])
    assert code == cli.EXIT_UNAVAILABLE
    [row] = list(csv.DictReader(out.open(encoding="utf-8")))
    assert row["mode"] == "unavailable" and row["signal_dbm"] == "" and row["error"]


def test_demo_json_is_labelled(capsys):
    assert cli.main(["scan", "--demo", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "simulated" and data["is_simulated"] is True


def test_demo_text_has_banner(capsys):
    cli.main(["status", "--demo"])
    assert "SIMULATED" in capsys.readouterr().out


def test_monitor_json_export(tmp_path, capsys):
    out = tmp_path / "log.json"
    assert cli.main(["monitor", "--demo", "-n", "2", "-i", "1", "-o", str(out), "--json"]) == 0
    rows = json.loads(out.read_text(encoding="utf-8"))
    assert len(rows) == 2 and all(r["mode"] == "simulated" for r in rows)


def test_legacy_scan_flag(capsys):
    assert cli.main(["--scan", "--demo"]) == 0
    assert "DEMO" in capsys.readouterr().out


def test_diagnose_rejects_demo(capsys):
    assert cli.main(["diagnose", "--demo"]) == cli.EXIT_USAGE


def test_capabilities_json(no_wifi, capsys):
    cli.main(["capabilities", "--json"])
    assert json.loads(capsys.readouterr().out)["capabilities"]["ssid"]["supported"] is False


def test_untrusted_ssid_is_escaped():
    assert "\x1b" not in cli.safe("evil\x1b[31m")  # no terminal escape injection
    if cli._console is not None:
        assert cli.safe("[bold]x") == "\\[bold]x"  # no Rich markup injection


def test_csv_quotes_commas(tmp_path):
    p = tmp_path / "x.csv"
    cli.write_log([{"timestamp": "t", "mode": "live", "ssid": 'a,"b"'}], str(p))
    [row] = list(csv.DictReader(p.open(encoding="utf-8")))
    assert row["ssid"] == 'a,"b"'
