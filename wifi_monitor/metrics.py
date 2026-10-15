"""Prometheus text exposition (format 0.0.4) for the latest measurements.

No SSIDs, BSSIDs or IP addresses are exported; series carry only an optional
``agent`` label (for the hub) and the measurement ``mode``.
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional

from .history import History, Sample


def _escape(v: str) -> str:
    return v.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(labels: Dict[str, str]) -> str:
    if not labels:
        return ""
    return "{" + ",".join(f'{k}="{_escape(str(v))}"' for k, v in sorted(labels.items())) + "}"


class Exposition:
    def __init__(self) -> None:
        self._meta: Dict[str, tuple] = {}
        self._lines: Dict[str, List[str]] = {}

    def add(self, name: str, kind: str, help_: str, value: Optional[float], labels: Optional[Dict[str, str]] = None):
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return
        self._meta.setdefault(name, (kind, help_))
        self._lines.setdefault(name, []).append(f"{name}{_labels(labels or {})} {float(value):.15g}")

    def render(self) -> str:
        out = []
        for name, (kind, help_) in self._meta.items():
            out.append(f"# HELP {name} {help_}")
            out.append(f"# TYPE {name} {kind}")
            out.extend(self._lines[name])
        return "\n".join(out) + "\n"


def add_sample(ex: Exposition, s: Optional[Sample], labels: Dict[str, str]) -> None:
    if s is None:
        return
    lab = dict(labels, mode=s.mode)
    ex.add("wifi_monitor_connected", "gauge", "1 if Wi-Fi is connected.", 1 if s.connected else 0, lab)
    sig_lab = dict(labels, mode=s.signal_mode or s.mode)
    ex.add("wifi_monitor_signal_dbm", "gauge", "Wi-Fi signal strength in dBm (mode=estimated if derived from %).",
           s.signal_dbm, sig_lab)
    ex.add("wifi_monitor_gateway_latency_ms", "gauge", "Median ICMP round-trip to the default gateway.",
           s.gateway_ms, labels)
    ex.add("wifi_monitor_gateway_loss_ratio", "gauge", "Ping loss to the gateway in the latest check (0-1).",
           None if s.gateway_loss_pct is None else s.gateway_loss_pct / 100.0, labels)
    ex.add("wifi_monitor_internet_latency_ms", "gauge", "TCP handshake time to 1.1.1.1:443.", s.internet_ms, labels)
    ex.add("wifi_monitor_dns_ms", "gauge", "System resolver lookup time.", s.dns_ms, labels)
    ex.add("wifi_monitor_last_sample_timestamp_seconds", "gauge", "Unix time of the latest sample.", s.ts, labels)


FRESH_S = 300  # latency is measured every few samples; export the latest value up to this age


def latest_composite(samples: List[Sample]) -> Optional[Sample]:
    """The newest sample, with latency fields filled from the most recent measurement within FRESH_S."""
    if not samples:
        return None
    last = samples[-1]
    merged = Sample(**{k: getattr(last, k) for k in last.__dataclass_fields__})
    for attr in ("gateway_ms", "gateway_loss_pct", "internet_ms", "dns_ms"):
        if getattr(merged, attr) is None:
            for s in reversed(samples):
                if last.ts - s.ts > FRESH_S:
                    break
                if getattr(s, attr) is not None:
                    setattr(merged, attr, getattr(s, attr))
                    break
    return merged


def render(history: History, labels: Optional[Dict[str, str]] = None, extra: Iterable = ()) -> str:
    labels = labels or {}
    ex = Exposition()
    samples = history.window(None)
    add_sample(ex, latest_composite(samples), labels)
    events = history.event_list(None)
    ex.add("wifi_monitor_samples", "gauge", "Samples held in memory.", len(samples), labels)
    ex.add("wifi_monitor_roams_total", "counter", "Access point changes observed since start.",
           sum(1 for e in events if e.type == "roam"), labels)
    ex.add("wifi_monitor_disconnects_total", "counter", "Wi-Fi disconnections observed since start.",
           sum(1 for e in events if e.type == "disconnect"), labels)
    ex.add("wifi_monitor_alerts_active", "gauge", "Unacknowledged alerts.",
           len(history.alerts.list(include_acknowledged=False)), labels)
    for fn in extra:
        fn(ex)
    return ex.render()
