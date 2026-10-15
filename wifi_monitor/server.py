"""Local dashboard server and read-only JSON API (standard library only).

Security model
* Binds to 127.0.0.1 by default. A non-loopback bind needs ``--allow-remote``
  because the API is unauthenticated.
* The Host header must name a loopback address (blocks DNS-rebinding attacks
  from web pages the user visits).
* No CORS headers are sent, so other origins cannot read responses.
* The only state-changing endpoint (POST /api/v1/diagnostics, which makes
  outbound requests) requires a custom header that cross-site forms cannot
  send, and only one run may be in flight.
* No request parameter is ever passed to an OS command.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import platform
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import unquote

from . import __version__, netinfo
from .diagnostics import Probes, run_diagnostics
from .models import ProviderResult, utc_now
from .providers import get_provider

STATIC_ROOT = Path(__file__).resolve().parent.parent / "src"
API_HEADER = "X-WiFi-Monitor"
CSP = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; connect-src 'self' https://www.cloudflare.com; frame-ancestors 'none'; base-uri 'none'"
)


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


class App:
    """HTTP-independent API logic (unit-testable without sockets)."""

    def __init__(self, demo: bool = False, provider=None, route_fn=None, diagnostics_fn=None) -> None:
        self.demo = demo
        self.provider = provider or get_provider(demo=demo)
        self.route_fn = route_fn or netinfo.default_route
        self.diagnostics_fn = diagnostics_fn or (lambda: run_diagnostics(p=Probes(wifi=self.provider.interfaces)))
        self.cache = TTLCache()
        self.diag_lock = threading.Lock()
        self.last_report: Optional[dict] = None

    def _wifi(self) -> ProviderResult:
        return self.cache.get("wifi", 1.0, self.provider.interfaces)

    def _route(self) -> ProviderResult:
        if self.demo:
            return ProviderResult(mode="simulated", source="demo", data={"gateway": None, "local_ip": None})
        return self.cache.get("route", 5.0, self.route_fn)

    def get(self, path: str) -> Tuple[int, dict]:
        if path == "/api/v1/status":
            return 200, {
                "timestamp": utc_now(),
                "version": __version__,
                "platform": platform.system(),
                "provider": self.provider.name,
                "demo": self.demo,
                "wifi": self._wifi().to_dict(),
                "network": self._route().to_dict(),
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
        if path == "/api/v1/network":
            return 200, self._route().to_dict()
        if path == "/api/v1/capabilities":
            return 200, {"platform": platform.system(), "provider": self.provider.name, "demo": self.demo,
                         "capabilities": self.provider.capabilities()}
        if path == "/api/v1/diagnostics":
            if self.last_report is None:
                return 404, {"error": "no diagnostics have been run yet; POST to this endpoint to run them"}
            return 200, self.last_report
        return 404, {"error": "not found"}

    def post(self, path: str) -> Tuple[int, dict]:
        if path != "/api/v1/diagnostics":
            return 404, {"error": "not found"}
        if self.demo:
            return 400, {"error": "diagnostics always use real measurements and are disabled in demo mode"}
        if not self.diag_lock.acquire(blocking=False):
            return 409, {"error": "diagnostics are already running"}
        try:
            self.last_report = self.diagnostics_fn().to_dict()
            return 200, self.last_report
        finally:
            self.diag_lock.release()


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

        def _json(self, status: int, obj: dict) -> None:
            self._send(status, json.dumps(obj, default=str).encode(), "application/json", {"Cache-Control": "no-store"})

        def _path(self) -> str:
            return unquote(self.path.split("?", 1)[0].split("#", 1)[0])

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._json(421, {"error": "invalid Host header"})
            path = self._path()
            if path.startswith("/api/"):
                return self._json(*app.get(path))
            return self._static(path)

        do_HEAD = do_GET

        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                return self._json(421, {"error": "invalid Host header"})
            if self.headers.get(API_HEADER) != "1":
                return self._json(403, {"error": f"missing {API_HEADER} header"})
            origin = self.headers.get("Origin")
            if origin and not allow_remote:
                host = origin.split("://", 1)[-1].rsplit(":", 1)[0]
                if not is_loopback(host):
                    return self._json(403, {"error": "cross-origin request refused"})
            return self._json(*app.post(self._path()))

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


def serve(host: str = "127.0.0.1", port: int = 8765, demo: bool = False, allow_remote: bool = False) -> int:
    if not is_loopback(host) and not allow_remote:
        print(f"Refusing to bind to {host}: the API is unauthenticated. Use --allow-remote only on a trusted network.")
        return 2
    mimetypes.add_type("application/javascript", ".js")
    app = App(demo=demo)
    httpd = ThreadingHTTPServer((host, port), make_handler(app, allow_remote))
    httpd.daemon_threads = True
    shown = f"[{host}]" if ":" in host else host
    print(f"WiFi Monitor {__version__} — dashboard and API on http://{shown}:{port}/")
    print("Mode: SIMULATED demo data" if demo else f"Mode: live ({app.provider.name})")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0
