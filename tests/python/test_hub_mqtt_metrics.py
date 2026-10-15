import http.client
import io
import json
import threading
import time
from http.server import ThreadingHTTPServer

import pytest

from wifi_monitor import hub, metrics, mqtt
from wifi_monitor.history import History, Sample


def sample(ts=None, **kw):
    d = dict(ts=ts or time.time(), mode="live", connected=True, ssid="Home", bssid="02:00:00:00:00:01",
             signal_dbm=-55, signal_mode="live", channel=36, band="5 GHz", gateway_ms=2.0, gateway_loss_pct=0.0,
             internet_ms=20.0, dns_ms=10.0, error=None)
    d.update(kw)
    return d


# ── tokens ───────────────────────────────────────────────────────

def test_tokens_hashed_and_revocable(isolated_home):
    store = hub.TokenStore()
    tok = store.create("agents", "kitchen-pi")
    raw = (isolated_home / hub.TOKENS_FILE).read_text()
    assert tok not in raw and hub._hash(tok) in raw
    assert store.verify("agents", tok) == "kitchen-pi"
    assert store.verify("viewers", tok) is None  # an agent token cannot read
    assert store.verify("agents", "wrong") is None and store.verify("agents", None) is None
    assert store.revoke("agents", "kitchen-pi")
    assert hub.TokenStore().verify("agents", tok) is None


@pytest.mark.parametrize("name", ["", "a b", "x" * 41, "../etc"])
def test_token_name_validation(name):
    with pytest.raises(ValueError):
        hub.TokenStore().create("agents", name)


def test_parse_sample_validation():
    assert hub.parse_sample(sample()).signal_dbm == -55
    for bad in (sample(mode="guessed"), sample(signal_dbm="-55"), sample(ts=1), sample(connected=None),
                sample(signal_dbm=True), "x"):
        with pytest.raises(ValueError):
            hub.parse_sample(bad)
    assert len(hub.parse_sample(sample(ssid="x" * 500)).ssid) == 128


def test_report_rate_limit_and_replay():
    st = hub.HubState(tokens=hub.TokenStore())
    t = time.time()
    assert st.report("a", {"samples": [sample(t - 2), sample(t - 1)]}) == (200, {"accepted": 2})
    assert st.report("a", {"samples": [sample(t)]})[0] == 429
    st.agents["a"]["last_report"] = 0
    assert st.report("a", {"samples": [sample(t - 1)]}) == (200, {"accepted": 0})  # replay ignored
    assert st.report("a", {"samples": []})[0] == 400
    assert st.report("a", {"samples": [sample()] * 51})[0] == 400


def test_agent_limit():
    st = hub.HubState(tokens=hub.TokenStore())
    for i in range(hub.MAX_AGENTS):
        st.agents[f"a{i}"] = {"history": History(), "last_report": 0}
    assert st.report("new", {"samples": [sample()]})[0] == 503


@pytest.fixture
def hub_server():
    st = hub.HubState(tokens=hub.TokenStore())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), hub.make_hub_handler(st))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield st, httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def call(port, method, path, token=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
    r = conn.getresponse()
    data = r.read()
    conn.close()
    return r.status, data


def test_hub_http_auth(hub_server):
    st, port = hub_server
    agent = st.tokens.create("agents", "pi")
    viewer = st.tokens.create("viewers", "grafana")
    assert call(port, "POST", "/api/v1/agents/report", body={"samples": [sample()]})[0] == 401
    assert call(port, "POST", "/api/v1/agents/report", viewer, {"samples": [sample()]})[0] == 401
    assert call(port, "POST", "/api/v1/agents/report", agent, {"samples": [sample()]})[0] == 200
    assert call(port, "GET", "/api/v1/agents", agent)[0] == 401  # agents cannot read others
    status, body = call(port, "GET", "/api/v1/agents", viewer)
    agents = json.loads(body)["agents"]
    assert status == 200 and agents[0]["agent"] == "pi"  # identity from the token, not the request
    status, body = call(port, "GET", "/metrics", viewer)
    assert status == 200 and b'wifi_monitor_signal_dbm{agent="pi",mode="live"} -55' in body
    st.tokens.revoke("agents", "pi")
    st.agents["pi"]["last_report"] = 0
    assert call(port, "POST", "/api/v1/agents/report", agent, {"samples": [sample()]})[0] == 401


def test_hub_rejects_oversized_body(hub_server):
    st, port = hub_server
    agent = st.tokens.create("agents", "pi")
    status, _ = call(port, "POST", "/api/v1/agents/report", agent, {"samples": [], "pad": "x" * 70000})
    assert status == 413


def test_hub_refuses_plain_http_on_network(capsys):
    assert hub.serve_hub("0.0.0.0", 0) == 2
    assert "Refusing" in capsys.readouterr().out


class FakeOpener:
    def __init__(self, fail=None):
        self.requests, self.fail = [], fail

    def open(self, req, timeout=None):
        self.requests.append(req)
        if self.fail:
            raise self.fail
        return io.BytesIO(b'{"accepted": 1}')


def test_agent_reporter_strips_identifiers_and_batches():
    op = FakeOpener()
    rep = hub.AgentReporter("https://hub.example:8766", "tok", opener=op)
    for i in range(60):
        rep.enqueue(Sample(**sample(time.time() + i)))
    assert rep.flush() and not rep.queue
    assert len(op.requests) == 2  # 50 + 10
    body = json.loads(op.requests[0].data)
    assert body["samples"][0]["ssid"] is None and body["samples"][0]["bssid"] is None
    assert op.requests[0].get_header("Authorization") == "Bearer tok"


def test_agent_reporter_queue_bounded_when_hub_down():
    import urllib.error

    rep = hub.AgentReporter("https://hub.example", "tok", opener=FakeOpener(urllib.error.URLError("down")), max_queue=5)
    for i in range(20):
        rep.enqueue(Sample(**sample(time.time() + i)))
    assert not rep.flush() and len(rep.queue) == 5 and "unreachable" in rep.last_error


def test_agent_reporter_flags_insecure_remote_http():
    assert hub.AgentReporter("http://192.168.1.5:8766", "t").insecure
    assert not hub.AgentReporter("http://127.0.0.1:8766", "t").insecure
    with pytest.raises(ValueError):
        hub.AgentReporter("ftp://x", "t")


# ── metrics ──────────────────────────────────────────────────────

def test_metrics_render_and_composite():
    h = History()
    t = time.time()
    h.add(Sample(**sample(t - 10)))
    h.add(Sample(**sample(t, gateway_ms=None, internet_ms=None, dns_ms=None, gateway_loss_pct=None)))
    text = metrics.render(h)
    assert "wifi_monitor_gateway_latency_ms 2" in text  # filled from the recent measurement
    assert "# TYPE wifi_monitor_signal_dbm gauge" in text
    assert "Home" not in text and "02:00" not in text  # no identifiers exported
    assert metrics._escape('a"b\\c\nd') == 'a\\"b\\\\c\\nd'


def test_metrics_empty_history():
    assert "wifi_monitor_samples 0" in metrics.render(History())


# ── MQTT ─────────────────────────────────────────────────────────

class FakeMqtt:
    def __init__(self):
        self.published = []

    def connect(self, host, port, keepalive=60):
        self.connected = (host, port)

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, retain))


def test_mqtt_discovery_and_state():
    c = FakeMqtt()
    pub = mqtt.MqttPublisher({"host": "broker", "port": 1883, "topic_prefix": "wm", "home_assistant_discovery": True},
                             client=c, node="Office PC")
    pub.start()
    assert c.connected == ("broker", 1883)
    topics = [t for t, _, _ in c.published]
    assert "wm/office_pc/availability" in topics
    assert "homeassistant/sensor/wifi_monitor_office_pc/signal_dbm/config" in topics
    assert all(r for t, _, r in c.published if t.startswith("homeassistant/"))  # discovery is retained
    pub.publish(Sample(**sample()))
    topic, payload, _ = c.published[-1]
    state = json.loads(payload)
    assert topic == "wm/office_pc/state" and state["signal_dbm"] == -55 and "ssid" not in state


def test_mqtt_requires_host():
    with pytest.raises(ValueError):
        mqtt.MqttPublisher({"host": None}, client=FakeMqtt())
