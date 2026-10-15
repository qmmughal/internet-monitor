"""In-memory measurement history, statistics, anomaly detection and alerts.

There is deliberately no database: history lives in a bounded ring buffer in
the ``serve`` process and is lost on restart (export it with CSV/JSON).

Anomaly detection is rule-based and explainable. Every anomaly names the rule,
the observed value, the baseline it was compared with, and how many samples
the baseline used. Rules stay silent until enough samples exist.
"""

from __future__ import annotations

import csv
import io
import itertools
import statistics
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional

from .models import SIMULATED

MIN_BASELINE = 6  # samples required before comparing against a baseline


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds")


@dataclass
class Sample:
    ts: float
    mode: str                       # provenance of the Wi-Fi reading
    connected: bool
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    signal_dbm: Optional[int] = None
    signal_mode: Optional[str] = None
    channel: Optional[int] = None
    band: Optional[str] = None
    gateway_ms: Optional[float] = None
    gateway_loss_pct: Optional[float] = None
    internet_ms: Optional[float] = None
    dns_ms: Optional[float] = None
    error: Optional[str] = None
    iface: Optional[str] = None       # primary interface (any type: Wi-Fi, Ethernet, VPN…)
    iface_type: Optional[str] = None
    rx_bps: Optional[float] = None    # bytes/second received on the primary interface
    tx_bps: Optional[float] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = iso(self.ts)
        d["is_simulated"] = self.mode == SIMULATED
        return d


@dataclass
class Event:
    ts: float
    type: str          # roam | network_change | disconnect | reconnect
    detail: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = iso(self.ts)
        return d


@dataclass
class Alert:
    id: int
    ts: float
    type: str
    severity: str      # info | warning | critical
    title: str
    detail: str
    evidence: List[str]
    simulated: bool = False
    acknowledged: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = iso(self.ts)
        return d


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * pct / 100.0
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return round(s[lo] + (s[hi] - s[lo]) * (k - lo), 1)


def summarize(values: List[float]) -> Optional[dict]:
    if not values:
        return None
    return {
        "count": len(values),
        "avg": round(statistics.fmean(values), 1),
        "min": round(min(values), 1),
        "max": round(max(values), 1),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "latest": values[-1],
    }


METRICS = ("signal_dbm", "gateway_ms", "gateway_loss_pct", "internet_ms", "dns_ms", "rx_bps", "tx_bps")


class AlertManager:
    def __init__(self, max_alerts: int = 500, on_alert: Optional[Callable[[Alert], None]] = None) -> None:
        self._alerts: Deque[Alert] = deque(maxlen=max_alerts)
        self._ids = itertools.count(1)
        self._last: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.on_alert = on_alert

    def raise_alert(self, key: str, type_: str, severity: str, title: str, detail: str,
                    evidence: List[str], simulated: bool, now: float, cooldown_s: float = 300) -> Optional[Alert]:
        with self._lock:
            if now - self._last.get(key, -1e18) < cooldown_s:
                return None
            self._last[key] = now
            alert = Alert(next(self._ids), now, type_, severity, title, detail, evidence, simulated)
            self._alerts.append(alert)
        if self.on_alert:
            try:
                self.on_alert(alert)
            except Exception:  # integrations must never break collection
                pass
        return alert

    def list(self, include_acknowledged: bool = True) -> List[Alert]:
        with self._lock:
            return [a for a in self._alerts if include_acknowledged or not a.acknowledged]

    def acknowledge(self, alert_id: int) -> bool:
        with self._lock:
            for a in self._alerts:
                if a.id == alert_id:
                    a.acknowledged = True
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._alerts.clear()
            self._last.clear()


class History:
    """Thread-safe ring buffer of samples plus derived events and alerts."""

    def __init__(self, max_samples: int = 8640, thresholds: Optional[dict] = None,
                 alerts: Optional[AlertManager] = None) -> None:
        from .config import DEFAULTS

        self.samples: Deque[Sample] = deque(maxlen=max(10, max_samples))
        self.events: Deque[Event] = deque(maxlen=1000)
        self.th = dict(DEFAULTS["thresholds"], **(thresholds or {}))
        self.alerts = alerts or AlertManager()
        self._lock = threading.Lock()

    # ── recording ───────────────────────────────────────────────
    def add(self, s: Sample) -> List[dict]:
        """Record a sample; returns the anomalies it triggered (also raised as alerts)."""
        with self._lock:
            prev = self.samples[-1] if self.samples else None
            self.samples.append(s)
            self._track_events(prev, s)
            history = list(self.samples)
            recent_events = [e for e in self.events if s.ts - e.ts <= 3600]
        found = detect_anomalies(history, recent_events, self.th)
        for a in found:
            self.alerts.raise_alert(
                key=a["rule"], type_=a["rule"], severity=a["severity"], title=a["title"],
                detail=a["detail"], evidence=a["evidence"], simulated=s.mode == SIMULATED, now=s.ts,
                cooldown_s=a.get("cooldown_s", 300),
            )
        return found

    def _track_events(self, prev: Optional[Sample], s: Sample) -> None:
        if prev is None:
            return
        if prev.connected and not s.connected:
            self.events.append(Event(s.ts, "disconnect", f"Wi-Fi disconnected ({s.error or 'no connection'})",
                                     {"ssid": prev.ssid, "bssid": prev.bssid}))
        elif not prev.connected and s.connected:
            self.events.append(Event(s.ts, "reconnect", f"Wi-Fi connected to {s.ssid or 'network'}",
                                     {"ssid": s.ssid, "bssid": s.bssid}))
        elif prev.connected and s.connected:
            if prev.ssid != s.ssid and prev.ssid and s.ssid:
                self.events.append(Event(s.ts, "network_change", f"Switched network {prev.ssid} → {s.ssid}",
                                         {"from_ssid": prev.ssid, "to_ssid": s.ssid}))
            elif prev.bssid and s.bssid and prev.bssid != s.bssid:
                self.events.append(Event(
                    s.ts, "roam", f"Roamed to another access point ({prev.bssid} → {s.bssid})",
                    {"ssid": s.ssid, "from_bssid": prev.bssid, "to_bssid": s.bssid,
                     "from_signal": prev.signal_dbm, "to_signal": s.signal_dbm,
                     "from_channel": prev.channel, "to_channel": s.channel}))

    # ── queries ─────────────────────────────────────────────────
    def window(self, seconds: Optional[float] = None, now: Optional[float] = None) -> List[Sample]:
        with self._lock:
            data = list(self.samples)
        if seconds is None:
            return data
        now = now or time.time()
        return [s for s in data if now - s.ts <= seconds]

    def stats(self, seconds: Optional[float] = None, now: Optional[float] = None) -> dict:
        data = self.window(seconds, now)
        out = {"samples": len(data), "window_s": seconds,
               "from": iso(data[0].ts) if data else None, "to": iso(data[-1].ts) if data else None,
               "simulated_samples": sum(1 for s in data if s.mode == SIMULATED),
               "estimated_signal_samples": sum(1 for s in data if s.signal_mode == "estimated"),
               "connected_pct": round(100 * sum(s.connected for s in data) / len(data), 1) if data else None}
        for m in METRICS:
            out[m] = summarize([getattr(s, m) for s in data if getattr(s, m) is not None])
        return out

    def baseline(self, now: Optional[float] = None, recent_s: float = 300, base_s: float = 3600) -> dict:
        """Compare the last ``recent_s`` seconds against the preceding ``base_s`` seconds."""
        now = now or time.time()
        data = self.window(None)
        recent = [s for s in data if now - s.ts <= recent_s]
        base = [s for s in data if recent_s < now - s.ts <= recent_s + base_s]
        out = {}
        for m in METRICS:
            r = [getattr(s, m) for s in recent if getattr(s, m) is not None]
            b = [getattr(s, m) for s in base if getattr(s, m) is not None]
            if len(r) >= 3 and len(b) >= MIN_BASELINE:
                rm, bm = statistics.median(r), statistics.median(b)
                out[m] = {"recent_median": round(rm, 1), "baseline_median": round(bm, 1),
                          "change": round(rm - bm, 1), "recent_samples": len(r), "baseline_samples": len(b)}
            else:
                out[m] = None
        return out

    def event_list(self, seconds: Optional[float] = None, now: Optional[float] = None) -> List[Event]:
        now = now or time.time()
        with self._lock:
            return [e for e in self.events if seconds is None or now - e.ts <= seconds]

    def clear(self) -> None:
        with self._lock:
            self.samples.clear()
            self.events.clear()
        self.alerts.clear()

    def to_csv(self) -> str:
        buf = io.StringIO()
        fields = ["timestamp", "mode", "is_simulated", "connected", "ssid", "bssid", "signal_dbm", "signal_mode",
                  "channel", "band", "gateway_ms", "gateway_loss_pct", "internet_ms", "dns_ms", "iface", "iface_type",
                  "rx_bps", "tx_bps", "error"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for s in self.window(None):
            row = s.to_dict()
            for k, v in row.items():  # spreadsheet formula injection via SSIDs
                if isinstance(v, str) and v[:1] in ("=", "+", "@", "\t", "\r"):
                    row[k] = "'" + v
            w.writerow(row)
        return buf.getvalue()


# ── anomaly rules ───────────────────────────────────────────────

def _prior(history: List[Sample], attr: str, n: int = 30) -> List[float]:
    vals = [getattr(s, attr) for s in history[:-1] if getattr(s, attr) is not None]
    return vals[-n:]


BUSY_BPS = 250_000  # ~2 Mbit/s: enough traffic to plausibly fill an upload link and raise latency


def _busy_evidence(s: Sample) -> List[str]:
    out = []
    if s.tx_bps and s.tx_bps >= BUSY_BPS:
        out.append(f"this computer was uploading {round(s.tx_bps * 8 / 1e6, 1)} Mbit/s (uploads often raise latency)")
    if s.rx_bps and s.rx_bps >= BUSY_BPS:
        out.append(f"this computer was downloading {round(s.rx_bps * 8 / 1e6, 1)} Mbit/s")
    return out


def detect_anomalies(history: List[Sample], events: List[Event], th: dict) -> List[dict]:
    """Pure function: evaluate rules on the latest sample. Returns explained anomalies."""
    if not history:
        return []
    cur = history[-1]
    found: List[dict] = []
    est = " (estimated from OS %)" if cur.signal_mode == "estimated" else ""

    # Sudden signal drop vs rolling median of the same network
    if cur.signal_dbm is not None:
        prior = [s.signal_dbm for s in history[:-1][-30:]
                 if s.signal_dbm is not None and s.bssid == cur.bssid]
        if len(prior) >= MIN_BASELINE:
            med = statistics.median(prior)
            if med - cur.signal_dbm >= th["signal_drop_db"]:
                found.append(dict(
                    rule="signal_drop", severity="warning", title="Sudden signal drop",
                    detail=f"Signal fell to {cur.signal_dbm} dBm{est}, {round(med - cur.signal_dbm)} dB below "
                           f"the recent median.",
                    evidence=[f"current {cur.signal_dbm} dBm", f"median of last {len(prior)} samples on this "
                              f"access point: {round(med)} dBm", f"rule: drop ≥ {th['signal_drop_db']} dB"]))

        # Weak signal sustained for 3 samples (not a single blip)
        last3 = [s.signal_dbm for s in history[-3:]]
        if len(last3) == 3 and all(v is not None and v < th["weak_signal_dbm"] for v in last3):
            found.append(dict(
                rule="weak_signal", severity="warning", title="Weak signal",
                detail=f"Signal has stayed below {th['weak_signal_dbm']} dBm for 3 samples{est}.",
                evidence=[f"last 3 samples: {', '.join(str(v) for v in last3)} dBm"], cooldown_s=900))

    # Latency spikes vs rolling median
    for attr, label in (("gateway_ms", "router"), ("internet_ms", "internet")):
        val = getattr(cur, attr)
        prior = _prior(history, attr)
        if val is not None and len(prior) >= MIN_BASELINE:
            med = statistics.median(prior)
            if val >= max(th["latency_min_ms"], med * th["latency_spike_factor"]):
                evidence = [f"current {val} ms", f"median of last {len(prior)} measurements: {round(med, 1)} ms",
                            f"rule: ≥ {th['latency_spike_factor']}× median and ≥ {th['latency_min_ms']} ms"]
                busy = _busy_evidence(cur)
                found.append(dict(
                    rule=f"{attr}_spike", severity="warning", title=f"Latency spike to the {label}",
                    detail=f"{label.capitalize()} latency {val} ms is {round(val / max(med, 0.1), 1)}× the "
                           f"recent median." + (" Heavy traffic was in progress at the same time." if busy else ""),
                    evidence=evidence + busy))

    if cur.gateway_loss_pct:
        found.append(dict(
            rule="gateway_loss", severity="warning", title="Packet loss to the router",
            detail=f"{cur.gateway_loss_pct}% of pings to the router were lost in the latest check.",
            evidence=[f"loss {cur.gateway_loss_pct}% (small sample; confirm with `internet-monitor diagnose`)"]))

    # Slow DNS sustained
    last3_dns = [s.dns_ms for s in history[-6:] if s.dns_ms is not None][-3:]
    if len(last3_dns) == 3 and all(v > th["dns_slow_ms"] for v in last3_dns):
        found.append(dict(
            rule="dns_slow", severity="warning", title="DNS consistently slow",
            detail=f"The last 3 DNS lookups took over {th['dns_slow_ms']} ms.",
            evidence=[f"DNS times: {', '.join(str(v) for v in last3_dns)} ms"], cooldown_s=900))

    # Repeated disconnects within the last hour
    disconnects = [e for e in events if e.type == "disconnect"]
    if len(disconnects) >= th["disconnects_per_hour"] and not cur.connected:
        found.append(dict(
            rule="repeated_disconnects", severity="critical", title="Repeated disconnections",
            detail=f"Wi-Fi disconnected {len(disconnects)} times in the last hour.",
            evidence=[e.detail + " at " + iso(e.ts) for e in disconnects[-5:]], cooldown_s=1800))

    # Disconnect itself
    if len(history) >= 2 and history[-2].connected and not cur.connected:
        found.append(dict(rule="disconnect", severity="warning", title="Wi-Fi disconnected",
                          detail=cur.error or "The Wi-Fi interface is no longer connected.",
                          evidence=[f"previously connected to {history[-2].ssid or 'a network'}"], cooldown_s=60))
    return found
