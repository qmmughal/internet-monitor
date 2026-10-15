"""User configuration and small local state files (JSON, no database).

Location: ``$INTERNET_MONITOR_HOME`` if set, else ``%APPDATA%\\internet-monitor`` on
Windows and ``~/.config/internet-monitor`` elsewhere.

Secrets (AI API keys, agent tokens) are never written here in plain text:
API keys come from environment variables, agent tokens are stored as SHA-256.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "collector": {
        "interval_s": 10,          # signal sampling interval for `serve`
        "latency_every": 3,        # gateway/internet latency every N samples
        "retention_samples": 8640,  # ~24 h at 10 s; in memory only
    },
    "thresholds": {
        "weak_signal_dbm": -75,
        "signal_drop_db": 10,       # sudden drop vs rolling median
        "latency_spike_factor": 3.0,
        "latency_min_ms": 50,
        "disconnects_per_hour": 3,
        "dns_slow_ms": 300,
    },
    "ai": {
        "enabled": False,
        "provider": "anthropic",    # "anthropic" | "openai-compatible"
        "model": "claude-opus-5-5",
        "base_url": None,           # for openai-compatible (e.g. http://localhost:11434/v1)
        "api_key_env": None,        # env var holding the key; default per provider
        "send_identifiers": False,  # SSIDs/BSSIDs/IPs are redacted unless True
        "timeout_s": 120,
    },
    "mqtt": {
        "host": None,
        "port": 1883,
        "username": None,
        "password_env": "INTERNET_MONITOR_MQTT_PASSWORD",
        "topic_prefix": "internet_monitor",
        "home_assistant_discovery": True,
        "tls": False,
    },
}


LEGACY_PREFIX = "WIFI_MONITOR_"  # the project was called WiFi Monitor before 1.3


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Read INTERNET_MONITOR_<name>, falling back to the legacy WIFI_MONITOR_<name>."""
    val = os.environ.get(f"INTERNET_MONITOR_{name}")
    if val is None:
        val = os.environ.get(f"{LEGACY_PREFIX}{name}")
    return default if val is None else val


def env_var(full_name: Optional[str]) -> Optional[str]:
    """Read an environment variable named in config/CLI; INTERNET_MONITOR_* names fall back to legacy names."""
    if not full_name:
        return None
    val = os.environ.get(full_name)
    if val is None and full_name.startswith("INTERNET_MONITOR_"):
        val = os.environ.get(LEGACY_PREFIX + full_name[len("INTERNET_MONITOR_"):])
    return val


def home() -> Path:
    override = env("HOME")
    if override:
        return Path(override)
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        base = Path(os.environ["APPDATA"])
    else:
        base = Path.home() / ".config"
    current, legacy = base / "internet-monitor", base / "wifi-monitor"
    if not current.exists() and legacy.exists():  # keep using settings created before the rename
        return legacy
    return current


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        elif k in out and (out[k] is None or v is None or isinstance(v, type(out[k]))
                           or (isinstance(out[k], float) and isinstance(v, int))):
            out[k] = v
        # unknown keys and wrongly-typed values are ignored
    return out


def load() -> dict:
    data = read_json("config.json", {})
    return _merge(DEFAULTS, data if isinstance(data, dict) else {})


def read_json(name: str, default: Any) -> Any:
    path = home() / name
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write_json(name: str, data: Any) -> Path:
    """Atomic write so a crash never leaves a half-written file."""
    if "/" in name or "\\" in name or name.startswith("."):
        raise ValueError("invalid state file name")
    directory = home()
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, directory / name)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return directory / name
