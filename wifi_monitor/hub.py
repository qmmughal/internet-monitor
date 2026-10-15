"""Distributed monitoring: a hub that receives reports from remote agents.

Security model
* Every hub endpoint requires a bearer token. Agents use *agent* tokens (can
  only submit their own samples); dashboards/Prometheus use *viewer* tokens
  (read-only). Tokens are random 256-bit values shown once at creation and
  stored only as SHA-256 hashes in ``hub_tokens.json``.
* Revocation takes effect on the next request (the token file is re-read when
  it changes).
* The agent identity is the token's registered name — a client-supplied name
  is never trusted.
* Off-loopback the hub requires TLS (``--tls-cert/--tls-key``) unless
  ``--insecure-http`` is passed for a trusted network or a TLS reverse proxy.
* Requests are size-limited, per-agent rate-limited, and agents and samples
  are capped in memory. Agents omit SSIDs/BSSIDs unless configured otherwise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional, Tuple

from . import __version__, config, metrics
from .history import History, Sample

TOKENS_FILE = "hub_tokens.json"
MAX_BODY = 64 * 1024
MAX_AGENTS = 100
MAX_SAMPLES_PER_REPORT = 50
MIN_REPORT_INTERVAL_S = 1.0
_SAMPLE_FIELDS = {
    "ts": (int, float), "mode": str, "connected": bool, "ssid": (str, type(None)), "bssid": (str, type(None)),
    "signal_dbm": (int, type(None)), "signal_mode": (str, type(None)), "channel": (int, type(None)),
    "band": (str, type(None)), "gateway_ms": (int, float, type(None)), "gateway_loss_pct": (int, float, type(None)),
    "internet_ms": (int, float, type(None)), "dns_ms": (int, float, type(None)), "error": (str, type(None)),
    "iface": (str, type(None)), "iface_type": (str, type(None)),
    "rx_bps": (int, float, type(None)), "tx_bps": (int, float, type(None)),
}
_OPTIONAL_FIELDS = {"iface", "iface_type", "rx_bps", "tx_bps"}  # absent in reports from older agents
_NAME_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class TokenStore:
    def __init__(self, filename: str = TOKENS_FILE) -> None:
        self.filename = filename
        self._mtime: Optional[float] = None
        self._data: dict = {"agents": {}, "viewers": {}}
        self._lock = threading.Lock()

    def _path(self):
        return config.home() / self.filename

    def _reload(self) -> None:
        try:
            m = os.path.getmtime(self._path())
        except OSError:
            m = None
        if m != self._mtime:
            data = config.read_json(self.filename, {})
            self._data = {"agents": dict(data.get("agents", {})), "viewers": dict(data.get("viewers", {}))} \
                if isinstance(data, dict) else {"agents": {}, "viewers": {}}
            self._mtime = m

    def create(self, kind: str, name: str) -> str:
        if kind not in ("agents", "viewers"):
            raise ValueError("kind must be 'agents' or 'viewers'")
        if not name or len(name) > 40 or not set(name) <= _NAME_OK:
            raise ValueError("name must be 1–40 characters of letters, digits, '-', '_' or '.'")
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._reload()
            self._data[kind][name] = {"sha256": _hash(token), "created": time.time(), "revoked": False}
            config.write_json(self.filename, self._data)
            self._mtime = None
        return token

    def revoke(self, kind: str, name: str) -> bool:
        with self._lock:
            self._reload()
            rec = self._data.get(kind, {}).get(name)
            if not rec:
                return False
            rec["revoked"] = True
            config.write_json(self.filename, self._data)
            self._mtime = None
            return True

    def list(self) -> dict:
        with self._lock:
            self._reload()
            return {k: {n: {"created": r.get("created"), "revoked": r.get("revoked", False)} for n, r in v.items()}
                    for k, v in self._data.items()}

    def verify(self, kind: str, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        digest = _hash(token)
        with self._lock:
            self._reload()
            match = None
            for name, rec in self._data.get(kind, {}).items():  # compare against all entries, constant time each
                if hmac.compare_digest(rec.get("sha256", ""), digest) and not rec.get("revoked"):
                    match = name
            return match


def parse_sample(raw: dict) -> Sample:
    if not isinstance(raw, dict):
        raise ValueError("sample must be an object")
    clean = {}
    for k, types in _SAMPLE_FIELDS.items():
        v = raw.get(k)
        if k in ("ts", "mode", "connected") and v is None:
            raise ValueError(f"sample.{k} is required")
        if isinstance(v, bool) and k != "connected":
            raise ValueError(f"sample.{k} has the wrong type")
        if v is None and k in _OPTIONAL_FIELDS:
            clean[k] = None
            continue
        if not isinstance(v, types):
            raise ValueError(f"sample.{k} has the wrong type")
        if isinstance(v, str):
            v = "".join(ch for ch in v if ch.isprintable())[:128]
        clean[k] = v
    if clean["mode"] not in ("live", "estimated", "simulated", "unavailable"):
        raise ValueError("sample.mode is invalid")
    if abs(clean["ts"] - time.time()) > 86400:
        raise ValueError("sample.ts is more than a day away from the hub clock")
    return Sample(**clean)


class HubState:
    def __init__(self, tokens: Optional[TokenStore] = None, max_samples: int = 2000) -> None:
        self.tokens = tokens or TokenStore()
        self.agents: Dict[str, dict] = {}
        self.max_samples = max_samples
        self._lock = threading.Lock()

    def report(self, agent: str, body: dict) -> Tuple[int, dict]:
        samples = body.get("samples")
        if not isinstance(samples, list) or not samples or len(samples) > MAX_SAMPLES_PER_REPORT:
            return 400, {"error": f"'samples' must be a list of 1–{MAX_SAMPLES_PER_REPORT} items"}
        try:
            parsed = sorted((parse_sample(s) for s in samples), key=lambda s: s.ts)
        except ValueError as exc:
            return 400, {"error": str(exc)}
        now = time.time()
        with self._lock:
            entry = self.agents.get(agent)
            if entry is None:
                if len(self.agents) >= MAX_AGENTS:
                    return 503, {"error": "hub agent limit reached"}
                entry = self.agents[agent] = {"history": History(max_samples=self.max_samples), "last_report": 0.0}
            if now - entry["last_report"] < MIN_REPORT_INTERVAL_S:
                return 429, {"error": "reporting too fast"}
            entry["last_report"] = now
            entry["platform"] = str(body.get("platform", ""))[:32]
            entry["version"] = str(body.get("version", ""))[:32]
        last_ts = entry["history"].samples[-1].ts if entry["history"].samples else 0
        accepted = 0
        for s in parsed:
            if s.ts > last_ts:  # ignore replays / duplicates
                entry["history"].add(s)
                last_ts = s.ts
                accepted += 1
        return 200, {"accepted": accepted}

    def summary(self) -> List[dict]:
        out = []
        with self._lock:
            items = list(self.agents.items())
        for name, e in items:
            h: History = e["history"]
            data = h.window(None)
            last = data[-1] if data else None
            out.append({
                "agent": name, "platform": e.get("platform"), "version": e.get("version"),
                "last_report": e["last_report"], "stale": time.time() - e["last_report"] > 300,
                "latest": last.to_dict() if last else None,
                "stats_1h": h.stats(3600),
                "alerts": [a.to_dict() for a in h.alerts.list(include_acknowledged=False)][-10:],
            })
        return out

    def metrics(self) -> str:
        with self._lock:
            items = list(self.agents.items())
        parts = []
        for name, e in items:
            parts.append(metrics.render(e["history"], {"agent": name}))
        # merge HELP/TYPE headers: keep the first occurrence of each
        seen, lines = set(), []
        for text in parts:
            for line in text.splitlines():
                if line.startswith("#"):
                    if line in seen:
                        continue
                    seen.add(line)
                lines.append(line)
        return "\n".join(lines) + ("\n" if lines else "")


DRAIN_LIMIT = 1024 * 1024


def read_body(handler, max_body: int):
    """Return (body, None) or (None, (status, error)). Oversized bodies are drained up to DRAIN_LIMIT."""
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError:
        handler.close_connection = True
        return None, (400, {"error": "bad Content-Length"})
    if length < 0:
        handler.close_connection = True
        return None, (400, {"error": "bad Content-Length"})
    if length > max_body:
        remaining = min(length, DRAIN_LIMIT)
        while remaining > 0:
            chunk = handler.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
        handler.close_connection = True
        return None, (413, {"error": f"request body larger than {max_body} bytes"})
    return (handler.rfile.read(length) if length else b""), None


def make_hub_handler(state: HubState):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"wifi-monitor-hub/{__version__}"
        sys_version = ""

        def log_message(self, fmt, *args):
            if os.environ.get("WIFI_MONITOR_HTTP_LOG"):
                super().log_message(fmt, *args)  # never includes the Authorization header

        def _token(self) -> Optional[str]:
            auth = self.headers.get("Authorization", "")
            return auth[7:].strip() if auth.startswith("Bearer ") else None

        def _send(self, status: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, default=str).encode())

        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if state.tokens.verify("viewers", self._token()) is None:
                return self._json(401, {"error": "viewer token required"})
            if path == "/api/v1/agents":
                return self._json(200, {"agents": state.summary()})
            if path == "/metrics":
                return self._send(200, state.metrics().encode(), "text/plain; version=0.0.4; charset=utf-8")
            return self._json(404, {"error": "not found"})

        def do_POST(self):  # noqa: N802
            # Read (bounded) before replying: closing a socket with unread data makes clients see a
            # connection reset instead of the error status.
            raw, err = read_body(self, MAX_BODY)
            if self.path.split("?", 1)[0] != "/api/v1/agents/report":
                return self._json(404, {"error": "not found"})
            agent = state.tokens.verify("agents", self._token())
            if agent is None:
                return self._json(401, {"error": "valid agent token required"})
            if err:
                return self._json(*err)
            if not raw:
                return self._json(400, {"error": "empty body"})
            try:
                body = json.loads(raw)
            except ValueError:
                return self._json(400, {"error": "invalid JSON"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "body must be an object"})
            return self._json(*state.report(agent, body))

    return Handler


def serve_hub(host: str, port: int, tls_cert: Optional[str] = None, tls_key: Optional[str] = None,
              insecure_http: bool = False) -> int:
    from .server import is_loopback

    if not (tls_cert and tls_key) and not is_loopback(host) and not insecure_http:
        print("Refusing to serve the hub over plain HTTP on a network address. Provide --tls-cert and --tls-key, "
              "or pass --insecure-http on a trusted network / behind a TLS reverse proxy.")
        return 2
    state = HubState()
    if not state.tokens.list()["viewers"]:
        print("Note: no viewer tokens yet. Create one with: wifi-monitor hub token add viewers <name>")
    httpd = ThreadingHTTPServer((host, port), make_hub_handler(state))
    httpd.daemon_threads = True
    scheme = "http"
    if tls_cert and tls_key:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(tls_cert, tls_key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    print(f"WiFi Monitor hub {__version__} on {scheme}://{host}:{port}/  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
    return 0


# ── agent side ───────────────────────────────────────────────────

class AgentReporter:
    """Buffers samples and pushes them to a hub with bounded retries."""

    def __init__(self, hub_url: str, token: str, include_identifiers: bool = False, ca_file: Optional[str] = None,
                 opener=None, max_queue: int = 500) -> None:
        from .server import is_loopback

        parsed = urllib.request.urlparse(hub_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("hub URL must start with https:// (or http:// for a local hub)")
        self.insecure = parsed.scheme == "http" and not is_loopback(parsed.hostname or "")
        self.url = hub_url.rstrip("/") + "/api/v1/agents/report"
        self.token = token
        self.include_identifiers = include_identifiers
        self.queue: List[dict] = []
        self.max_queue = max_queue
        ctx = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
        self._opener = opener or urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
        self.last_error: Optional[str] = None

    def enqueue(self, s: Sample) -> None:
        d = {k: getattr(s, k) for k in _SAMPLE_FIELDS}
        if not self.include_identifiers:
            d["ssid"] = d["bssid"] = None
        self.queue.append(d)
        if len(self.queue) > self.max_queue:  # bounded: drop oldest while the hub is unreachable
            del self.queue[: len(self.queue) - self.max_queue]

    def flush(self) -> bool:
        from . import __version__ as ver
        import platform as _platform

        while self.queue:
            batch = self.queue[:MAX_SAMPLES_PER_REPORT]
            body = json.dumps({"samples": batch, "platform": _platform.system(), "version": ver}).encode()
            req = urllib.request.Request(self.url, data=body, method="POST", headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {self.token}"})
            try:
                with self._opener.open(req, timeout=15) as resp:
                    resp.read(4096)
            except urllib.error.HTTPError as exc:
                self.last_error = f"hub returned HTTP {exc.code}"
                if exc.code in (400, 413):  # bad data will never succeed; drop it
                    del self.queue[: len(batch)]
                    continue
                return False
            except (urllib.error.URLError, OSError) as exc:
                self.last_error = f"hub unreachable: {getattr(exc, 'reason', exc)}"
                return False
            del self.queue[: len(batch)]
            self.last_error = None
        return True
