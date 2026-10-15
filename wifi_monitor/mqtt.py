"""Optional MQTT publishing with Home Assistant discovery.

Requires ``pip install "wifi-monitor[mqtt]"`` (paho-mqtt). Publishes a JSON
state message per sample to ``<prefix>/<node>/state`` and, if enabled,
retained Home Assistant discovery configs so the sensors appear automatically.
SSIDs/BSSIDs are not published. The password comes from an environment variable.
"""

from __future__ import annotations

import json
import os
import re
import socket
from typing import Optional

from .history import Sample

SENSORS = [
    # key, name, unit, device_class, state_class
    ("signal_dbm", "Wi-Fi signal", "dBm", "signal_strength", "measurement"),
    ("gateway_ms", "Router latency", "ms", "duration", "measurement"),
    ("internet_ms", "Internet latency", "ms", "duration", "measurement"),
    ("dns_ms", "DNS lookup time", "ms", "duration", "measurement"),
    ("gateway_loss_pct", "Router packet loss", "%", None, "measurement"),
    ("rx_bps", "Download rate", "B/s", "data_rate", "measurement"),
    ("tx_bps", "Upload rate", "B/s", "data_rate", "measurement"),
]


def node_id(name: Optional[str] = None) -> str:
    raw = name or socket.gethostname() or "wifi-monitor"
    return re.sub(r"[^a-z0-9_-]", "_", raw.lower())[:40] or "wifi_monitor"


def state_payload(s: Sample) -> dict:
    return {"connected": s.connected, "mode": s.mode, "signal_mode": s.signal_mode,
            **{k: getattr(s, k) for k, *_ in SENSORS}, "timestamp": s.to_dict()["timestamp"]}


def discovery_messages(prefix: str, node: str):
    """(topic, payload) pairs for Home Assistant MQTT discovery."""
    state_topic = f"{prefix}/{node}/state"
    avail = f"{prefix}/{node}/availability"
    device = {"identifiers": [f"wifi_monitor_{node}"], "name": f"WiFi Monitor ({node})", "manufacturer": "WiFi Monitor"}
    for key, name, unit, dclass, sclass in SENSORS:
        cfg = {"name": name, "unique_id": f"wifi_monitor_{node}_{key}", "state_topic": state_topic,
               "value_template": f"{{{{ value_json.{key} }}}}", "unit_of_measurement": unit,
               "state_class": sclass, "availability_topic": avail, "device": device}
        if dclass:
            cfg["device_class"] = dclass
        yield f"homeassistant/sensor/wifi_monitor_{node}/{key}/config", cfg
    yield (f"homeassistant/binary_sensor/wifi_monitor_{node}/connected/config",
           {"name": "Wi-Fi connected", "unique_id": f"wifi_monitor_{node}_connected", "state_topic": state_topic,
            "value_template": "{{ 'ON' if value_json.connected else 'OFF' }}", "device_class": "connectivity",
            "availability_topic": avail, "device": device})


class MqttPublisher:
    def __init__(self, cfg: dict, client=None, node: Optional[str] = None) -> None:
        if not cfg.get("host"):
            raise ValueError("mqtt.host is not configured in config.json")
        self.cfg = cfg
        self.node = node_id(node)
        self.prefix = re.sub(r"[^A-Za-z0-9_/-]", "_", cfg.get("topic_prefix") or "wifi_monitor").strip("/")
        self.avail = f"{self.prefix}/{self.node}/availability"
        self.client = client or self._make_client()

    def _make_client(self):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:
            raise RuntimeError('MQTT needs paho-mqtt: pip install "wifi-monitor[mqtt]"') from exc
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"wifi-monitor-{self.node}")
        else:  # paho-mqtt 1.x
            client = mqtt.Client(client_id=f"wifi-monitor-{self.node}")
        if self.cfg.get("username"):
            client.username_pw_set(self.cfg["username"], os.environ.get(self.cfg.get("password_env") or "", None))
        if self.cfg.get("tls"):
            client.tls_set()
        client.will_set(self.avail, "offline", retain=True)
        return client

    def start(self) -> None:
        self.client.connect(self.cfg["host"], int(self.cfg.get("port") or 1883), keepalive=60)
        self.client.loop_start()
        self.client.publish(self.avail, "online", retain=True)
        if self.cfg.get("home_assistant_discovery", True):
            for topic, payload in discovery_messages(self.prefix, self.node):
                self.client.publish(topic, json.dumps(payload), retain=True)

    def publish(self, s: Sample) -> None:
        self.client.publish(f"{self.prefix}/{self.node}/state", json.dumps(state_payload(s)))

    def stop(self) -> None:
        try:
            self.client.publish(self.avail, "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass
