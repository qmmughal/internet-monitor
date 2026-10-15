"""Local dashboard server and JSON API (standard library only).

Security model
* Binds to 127.0.0.1 by default. A non-loopback bind needs ``--allow-remote``
  because the API is unauthenticated (use ``wifi-monitor hub`` for
  authenticated multi-machine monitoring).
* The Host header must name a loopback address (blocks DNS-rebinding attacks
  from web pages the user visits).
* No CORS headers are sent, so other origins cannot read responses.
* Every POST requires a custom header that cross-site forms cannot send, an
  absent or loopback Origin, and a JSON body of at most 16 KB. Long-running
  actions (diagnostics, speed test, device sweep) allow one run at a time.
* No request value is ever passed to an OS command; inputs are validated.
* Nothing changes system, router, DNS or firewall settings.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import platform
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, unquote

from . import __version__, ai, apps, channels, config, devices, metrics, netinfo, standards, survey
from .traffic import InterfaceSampler
from . import speedtest as speedtest_mod
from .diagnostics import Probes, run_diagnostics
from .history import History
from .models import SIMULATED, ProviderResult, utc_now
from .providers import get_provider

STATIC_ROOT = Path(__file__).resolve().parent.parent / "src"
API_HEADER = "X-WiFi-Monitor"
MAX_POST_BODY = 16 * 1024
CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self' https://www.cloudflare.com; frame-ancestors 'none'; base-uri 'none'"
)


@dataclass
class Raw:
    """A non-JSON API response (exports, Prometheus)."""

    body: bytes
    content_type: str
    filename: Optional[str] = None


class TTLCache:
    """Avoid running OS commands more often than needed when several tabs poll."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: Dict[str, Tuple[float, object]] = {}

    def get(self, key: str, ttl: float, fn: Callable[[], object]):
        with self._lock:
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < ttl:
                return hit[1]
        value = fn()
        with self._lock:
            self._data[key] = (time.monotonic(), value)
        return value


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _int_param(query: dict, name: str, default: Optional[int], lo: int, hi: int) -> Optional[int]:
    raw = (query.get(name) or [None])[0]
    if raw is None or raw == "":
        return default
    try:
        val = int(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be an integer")
    if not lo <= val <= hi:
        raise ValueError(f"'{name}' must be between {lo} and {hi}")
    return val


class App:
    """HTTP-independent API logic (unit-testable without sockets)."""

    def __init__(self, demo: bool = False, provider=None, route_fn=None, diagnostics_fn=None,
                 history: Optional[History] = None, collector=None, cfg: Optional[dict] = None,
                 speedtest_fn=None, discover_fn=None, ai_provider=None, traffic=None, usage_fn=None,
                 connections_fn=None, rate_tracker=None) -> None:
        self.demo = demo
        self.cfg = cfg or config.load()
        self.provider = provider or get_provider(demo=demo)
        self.route_fn = route_fn or netinfo.default_route
        self.diagnostics_fn = diagnostics_fn or (lambda: run_diagnostics(
            p=Probes(wifi=self.provider.interfaces, activity=apps.activity_snapshot)))
        self.speedtest_fn = speedtest_fn or speedtest_mod.run
        self.discover_fn = discover_fn or devices.discover
        self.ai_provider = ai_provider
        self.history = history or History(max_samples=self.cfg["collector"]["retention_samples"],
                                          thresholds=self.cfg["thresholds"])
        self.collector = collector
        self.cache = TTLCache()
        self.locks = {k: threading.Lock() for k in ("diagnostics", "speedtest", "devices", "survey", "ai")}
        self.last_report: Optional[dict] = None
        self.last_speedtest: Optional[dict] = None
        self.last_devices: Optional[dict] = None
        self.traffic = traffic or InterfaceSampler()
        self.usage_fn = usage_fn or apps.usage
        self.connections_fn = connections_fn or apps.connections
        self.rate_tracker = rate_tracker
        if self.rate_tracker is None and platform.system() == "Windows" and usage_fn is None:
            self.rate_tracker = apps.AppRateTracker()
        self.locks["apps"] = threading.Lock()

    # ── helpers ─────────────────────────────────────────────────
    def _wifi(self) -> ProviderResult:
        return self.cache.get("wifi", 1.0, self.provider.interfaces)

    def _route(self) -> ProviderResult:
        if self.demo:
            return ProviderResult(mode=SIMULATED, source="demo", data={"gateway": None, "local_ip": None})
        return self.cache.get("route", 5.0, self.route_fn)

    def _connected(self):
        res = self._wifi()
        if not res.ok:
            return None
        return next((i for i in res.data or [] if i.connected), None)

    def _standard(self) -> Optional[dict]:
        iface = self._connected()
        return standards.describe(iface) if iface else None

    def _channels(self) -> dict:
        aps = self.cache.get("aps", 10.0, self.provider.access_points)
        if not aps.ok:
            return {"mode": "unavailable", "error": aps.error, "hint": aps.hint}
        iface = self._connected()
        return channels.analyze(aps.data, aps.mode, own_ssid=iface.ssid if iface else None)

    def _security(self) -> dict:
        devs = ((self.last_devices or {}).get("result") or {}).get("data")
        prev = devices.gateway_history(devs, persist=False) if devs and not self.demo else None
        return {"findings": devices.security_posture(self._connected(), devs, prev),
                "devices_scanned": devs is not None,
                "note": "Observations only; a finding is not proof of an attack."}

    def _traffic(self) -> dict:
        if self.demo:
            return {"mode": SIMULATED, "error": "traffic is not simulated in demo mode", "interfaces": []}
        return self.traffic.sample(min_interval=1.0)

    def _app_usage(self, window: int) -> dict:
        if self.demo:
            return {"mode": "unavailable", "error": "per-app usage is not available in demo mode", "apps": []}
        return self.cache.get(f"apps:{window}", 20.0, lambda: self.usage_fn(window))

    def _app_live(self) -> dict:
        if self.demo:
            return {"mode": "unavailable", "error": "per-app usage is not available in demo mode", "apps": []}
        if self.rate_tracker is not None:  # Windows: difference the system usage records
            return self.cache.get("apps:live", 15.0, self.rate_tracker.poll)
        return self.cache.get("apps:live", 3.0, lambda: self.usage_fn(300))  # Linux/macOS sample in real time

    def ai_status(self) -> dict:
        a = self.cfg["ai"]
        external = None
        if a.get("enabled"):
            try:
                external = getattr(ai.provider_from_config(a), "external", True)
            except ai.ProviderError:
                external = None
        return {"enabled": bool(a.get("enabled")), "provider": a.get("provider"), "model": a.get("model"),
                "external": external, "identifiers_redacted": not a.get("send_identifiers")}

    def ai_data(self) -> dict:
        return {
            "diagnostics": self.last_report,
            "wifi": self._wifi().to_dict(),
            "wifi_standard": self._standard(),
            "history_stats_1h": self.history.stats(3600),
            "baseline": self.history.baseline(),
            "events_1h": [e.to_dict() for e in self.history.event_list(3600)][-20:],
            "alerts": [a.to_dict() for a in self.history.alerts.list(include_acknowledged=False)][-10:],
            "speedtest": self.last_speedtest,
            "traffic_now": {k: v for k, v in self._traffic().items() if k != "interfaces"},
            "top_apps_5min": [{k: a.get(k) for k in ("app", "bytes_received", "bytes_sent")}
                              for a in (self._app_usage(300).get("apps") or [])[:5]],
        }

    # ── GET ─────────────────────────────────────────────────────
    def get(self, path: str, query: Optional[dict] = None):
        q = query or {}
        try:
            return self._get(path, q)
        except ValueError as exc:
            return 400, {"error": str(exc)}

    def _get(self, path: str, q: dict):
        if path == "/api/v1/status":
            return 200, {
                "timestamp": utc_now(), "version": __version__, "platform": platform.system(),
                "provider": self.provider.name, "demo": self.demo,
                "wifi": self._wifi().to_dict(), "network": self._route().to_dict(),
                "wifi_standard": self._standard(),
                "traffic": self._traffic(),
                "collector": self.collector.status() if self.collector else {"running": False},
                "features": {"ai": self.ai_status()["enabled"]},
            }
        if path == "/api/v1/wifi/interfaces":
            return 200, self._wifi().to_dict()
        if path == "/api/v1/wifi/signal":
            res = self.cache.get("signal", 1.0, self.provider.connected_interface)
            body = res.to_dict()
            body["data"] = res.data.signal_dbm.to_dict() if res.ok and res.data.signal_dbm else None
            return 200, body
        if path == "/api/v1/wifi/access-points":
            return 200, self.cache.get("aps", 10.0, self.provider.access_points).to_dict()
        if path == "/api/v1/wifi/standard":
            std = self._standard()
            return (200, std) if std else (200, {"mode": "unavailable", "error": "no connected Wi-Fi interface"})
        if path == "/api/v1/channels":
            return 200, self._channels()
        if path == "/api/v1/traffic":
            return 200, self._traffic()
        if path == "/api/v1/apps":
            window = _int_param(q, "window", 300, 60, 30 * 86400)
            return 200, dict(self._app_usage(window), window_s=window)
        if path == "/api/v1/apps/live":
            return 200, self._app_live()
        if path == "/api/v1/connections":
            if self.demo:
                return 200, {"mode": "unavailable", "error": "not available in demo mode", "apps": []}
            return 200, self.cache.get("connections", 3.0, self.connections_fn)
        if path == "/api/v1/network":
            return 200, self._route().to_dict()
        if path == "/api/v1/capabilities":
            return 200, {"platform": platform.system(), "provider": self.provider.name, "demo": self.demo,
                         "capabilities": self.provider.capabilities()}
        if path == "/api/v1/diagnostics":
            if self.last_report is None:
                return 404, {"error": "no diagnostics have been run yet; POST to this endpoint to run them"}
            return 200, self.last_report
        if path == "/api/v1/history":
            window = _int_param(q, "window", None, 10, 7 * 86400)
            limit = _int_param(q, "limit", 1000, 1, 10000)
            data = self.history.window(window)[-limit:]
            return 200, {"samples": [s.to_dict() for s in data], "count": len(data),
                         "storage": "memory (lost when the server stops)"}
        if path == "/api/v1/history/stats":
            window = _int_param(q, "window", 3600, 10, 7 * 86400)
            return 200, {"stats": self.history.stats(window), "baseline": self.history.baseline(),
                         "thresholds": self.history.th,
                         "collector": self.collector.status() if self.collector else {"running": False}}
        if path == "/api/v1/history/export":
            fmt = (q.get("format") or ["csv"])[0]
            stamp = time.strftime("%Y%m%d_%H%M%S")
            if fmt == "csv":
                return 200, Raw(self.history.to_csv().encode(), "text/csv; charset=utf-8", f"wifi_history_{stamp}.csv")
            if fmt == "json":
                body = json.dumps([s.to_dict() for s in self.history.window(None)], indent=2).encode()
                return 200, Raw(body, "application/json", f"wifi_history_{stamp}.json")
            raise ValueError("'format' must be csv or json")
        if path == "/api/v1/events":
            window = _int_param(q, "window", None, 10, 7 * 86400)
            return 200, {"events": [e.to_dict() for e in self.history.event_list(window)]}
        if path == "/api/v1/alerts":
            active = (q.get("active") or ["0"])[0] == "1"
            return 200, {"alerts": [a.to_dict() for a in self.history.alerts.list(include_acknowledged=not active)]}
        if path == "/api/v1/devices":
            if self.last_devices is None:
                return 404, {"error": "no device scan yet; POST /api/v1/devices/scan"}
            return 200, self.last_devices
        if path == "/api/v1/security":
            return 200, self._security()
        if path == "/api/v1/speedtest":
            if self.last_speedtest is None:
                return 404, {"error": "no speed test yet; POST to this endpoint to run one"}
            return 200, self.last_speedtest
        if path == "/api/v1/survey":
            return 200, survey.report()
        if path == "/api/v1/ai/status":
            return 200, self.ai_status()
        if path == "/metrics":
            return 200, Raw(metrics.render(self.history).encode(), "text/plain; version=0.0.4; charset=utf-8")
        return 404, {"error": "not found"}

    # ── POST ────────────────────────────────────────────────────
    def post(self, path: str, body: Optional[dict] = None):
        b = body or {}
        try:
            return self._post(path, b)
        except ValueError as exc:
            return 400, {"error": str(exc)}

    def _exclusive(self, name: str, fn: Callable[[], Tuple[int, dict]]):
        lock = self.locks[name]
        if not lock.acquire(blocking=False):
            return 409, {"error": f"{name} is already running"}
        try:
            return fn()
        finally:
            lock.release()

    def _post(self, path: str, b: dict):
        if path == "/api/v1/diagnostics":
            if self.demo:
                return 400, {"error": "diagnostics always use real measurements and are disabled in demo mode"}

            def run_diag():
                self.last_report = self.diagnostics_fn().to_dict()
                return 200, self.last_report
            return self._exclusive("diagnostics", run_diag)

        if path == "/api/v1/speedtest":
            if self.demo:
                return 400, {"error": "the speed test uses real measurements and is disabled in demo mode"}
            max_mb = b.get("max_mb", 50)
            if not isinstance(max_mb, int) or isinstance(max_mb, bool) or not 5 <= max_mb <= 500:
                raise ValueError("'max_mb' must be an integer between 5 and 500")

            def run_speed():
                self.last_speedtest = self.speedtest_fn(max_mb=max_mb)
                return 200, self.last_speedtest
            return self._exclusive("speedtest", run_speed)

        if path == "/api/v1/devices/scan":
            if self.demo:
                return 400, {"error": "device discovery is disabled in demo mode"}
            probe = b.get("probe", False)
            if not isinstance(probe, bool):
                raise ValueError("'probe' must be true or false")

            def run_devices():
                result = self.discover_fn(probe=probe)
                devs = (result.get("result") or {}).get("data") or []
                previous = devices.gateway_history(devs)
                result["gateway_mac_previous"] = previous
                for mac in result.get("new_devices", []):
                    d = next((x for x in devs if x["mac"] == mac), {})
                    self.history.alerts.raise_alert(
                        key=f"new_device:{mac}", type_="new_device", severity="info", title="New device seen",
                        detail=f"{d.get('vendor') or 'Unknown vendor'} at {d.get('ip')} ({mac}) appeared on the network.",
                        evidence=["not seen in earlier scans", "a new device is not necessarily a threat"]
                        + (["uses a randomized MAC address"] if d.get("randomized_mac") else []),
                        simulated=False, now=time.time(), cooldown_s=0)
                self.last_devices = result
                return 200, result
            return self._exclusive("devices", run_devices)

        if path == "/api/v1/devices/name":
            mac, name = b.get("mac"), b.get("name")
            if not isinstance(mac, str) or (name is not None and not isinstance(name, str)):
                raise ValueError("'mac' must be a string and 'name' a string or null")
            devices.KnownDevices().set_name(mac, name)
            return 200, {"ok": True}

        if path == "/api/v1/alerts/ack":
            alert_id = b.get("id")
            if not isinstance(alert_id, int) or isinstance(alert_id, bool):
                raise ValueError("'id' must be an integer")
            ok = self.history.alerts.acknowledge(alert_id)
            return (200, {"ok": True}) if ok else (404, {"error": "no such alert"})
        if path == "/api/v1/alerts/clear":
            self.history.alerts.clear()
            return 200, {"ok": True}
        if path == "/api/v1/history/clear":
            self.history.clear()
            return 200, {"ok": True}

        if path == "/api/v1/survey/points":
            label = b.get("label")
            samples = b.get("samples", 5)
            if not isinstance(label, str):
                raise ValueError("'label' must be a string")
            if not isinstance(samples, int) or isinstance(samples, bool) or not 1 <= samples <= 30:
                raise ValueError("'samples' must be an integer between 1 and 30")
            return self._exclusive("survey", lambda: (200, survey.record(label, self.provider, samples=samples)))
        if path == "/api/v1/survey/clear":
            survey.clear()
            return 200, {"ok": True}

        if path in ("/api/v1/ai/ask", "/api/v1/ai/preview"):
            question = b.get("question", "")
            if not isinstance(question, str) or len(question) > ai.MAX_QUESTION_CHARS:
                raise ValueError(f"'question' must be a string of at most {ai.MAX_QUESTION_CHARS} characters")
            if path.endswith("preview"):
                return 200, ai.preview(question, self.ai_data(), self.cfg["ai"])

            def run_ask():
                if self.last_report is None and not self.demo:  # explanations need evidence
                    with self.locks["diagnostics"]:
                        self.last_report = self.diagnostics_fn().to_dict()
                return 200, ai.ask(question, self.ai_data(), self.cfg["ai"], provider=self.ai_provider)
            return self._exclusive("ai", run_ask)
        return 404, {"error": "not found"}


def make_handler(app: App, allow_remote: bool, static_root: Path = STATIC_ROOT):
    root = static_root.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = f"wifi-monitor/{__version__}"
        sys_version = ""

        def log_message(self, fmt, *args):  # quieter, and never logs query strings
            if os.environ.get("WIFI_MONITOR_HTTP_LOG"):
                super().log_message(fmt, *args)

        def _host_ok(self) -> bool:
            if allow_remote:
                return True
            host = (self.headers.get("Host") or "").strip()
            name = host.rsplit(":", 1)[0] if not host.startswith("[") else host.split("]")[0] + "]"
            return is_loopback(name)

        def _send(self, status: int, body: bytes, ctype: str, extra: Optional[dict] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _reply(self, status: int, obj) -> None:
            if isinstance(obj, Raw):
                extra = {"Cache-Control": "no-store"}
                if obj.filename:
                    extra["Content-Disposition"] = f'attachment; filename="{obj.filename}"'
                return self._send(status, obj.body, obj.content_type, extra)
            self._send(status, json.dumps(obj, default=str).encode(), "application/json", {"Cache-Control": "no-store"})

        def _split(self) -> Tuple[str, dict]:
            raw = self.path.split("#", 1)[0]
            path, _, qs = raw.partition("?")
            return unquote(path), parse_qs(qs, max_num_fields=20)

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._reply(421, {"error": "invalid Host header"})
            path, query = self._split()
            if path.startswith("/api/") or path == "/metrics":
                return self._reply(*app.get(path, query))
            return self._static(path)

        do_HEAD = do_GET

        def do_POST(self):  # noqa: N802
            from .hub import read_body

            raw, err = read_body(self, MAX_POST_BODY)  # read first so error replies are not reset
            if not self._host_ok():
                return self._reply(421, {"error": "invalid Host header"})
            if self.headers.get(API_HEADER) != "1":
                return self._reply(403, {"error": f"missing {API_HEADER} header"})
            origin = self.headers.get("Origin")
            if origin and not allow_remote:
                host = origin.split("://", 1)[-1].rsplit(":", 1)[0]
                if not is_loopback(host):
                    return self._reply(403, {"error": "cross-origin request refused"})
            if err:
                return self._reply(*err)
            body = {}
            if raw:
                if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                    return self._reply(415, {"error": "Content-Type must be application/json"})
                try:
                    body = json.loads(raw)
                except ValueError:
                    return self._reply(400, {"error": "invalid JSON"})
                if not isinstance(body, dict):
                    return self._reply(400, {"error": "JSON body must be an object"})
            path, _ = self._split()
            return self._reply(*app.post(path, body))

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (root / rel).resolve()
            if root not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            extra = {"Cache-Control": "no-cache"}
            if target.suffix == ".html":
                extra.update({"Content-Security-Policy": CSP, "X-Frame-Options": "DENY"})
            self._send(200, target.read_bytes(), ctype, extra)

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, demo: bool = False, allow_remote: bool = False,
          collect: bool = True, interval_s: Optional[float] = None, mqtt: bool = False) -> int:
    from .collector import Collector

    if not is_loopback(host) and not allow_remote:
        print(f"Refusing to bind to {host}: the API is unauthenticated. Use --allow-remote only on a trusted network.")
        return 2
    mimetypes.add_type("application/javascript", ".js")
    cfg = config.load()
    app = App(demo=demo, cfg=cfg)
    collector = None
    publisher = None
    if collect:
        collector = Collector(app.provider, app.history, interval_s=interval_s or cfg["collector"]["interval_s"],
                              latency_every=cfg["collector"]["latency_every"], demo=demo)
        app.collector = collector
        if mqtt:
            from .mqtt import MqttPublisher

            try:
                publisher = MqttPublisher(cfg["mqtt"])
                publisher.start()
                collector.listeners.append(publisher.publish)
                print(f"MQTT: publishing to {cfg['mqtt']['host']} as {publisher.prefix}/{publisher.node}")
            except Exception as exc:
                print(f"MQTT disabled: {exc}")
                publisher = None
        collector.start()
    httpd = ThreadingHTTPServer((host, port), make_handler(app, allow_remote))
    httpd.daemon_threads = True
    shown = f"[{host}]" if ":" in host else host
    print(f"WiFi Monitor {__version__} — dashboard and API on http://{shown}:{port}/")
    print("Mode: SIMULATED demo data" if demo else f"Mode: live ({app.provider.name})")
    if collector:
        print(f"History: sampling every {collector.interval_s:g} s, kept in memory only (lost on exit)")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if collector:
            collector.stop()
        if publisher:
            publisher.stop()
        httpd.server_close()
    return 0
