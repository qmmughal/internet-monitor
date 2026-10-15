"""Data model shared by the CLI, the local API and the diagnostics engine.

Every value that reaches a user carries its provenance:

* ``live``        – read directly from an OS interface in native units.
* ``estimated``   – derived from a real observation (e.g. dBm from a percentage).
* ``simulated``   – generated for demos/tests. Never mixed into live output.
* ``unavailable`` – could not be obtained; ``error`` says why.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

LIVE = "live"
ESTIMATED = "estimated"
SIMULATED = "simulated"
UNAVAILABLE = "unavailable"
MODES = (LIVE, ESTIMATED, SIMULATED, UNAVAILABLE)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Measurement:
    value: Any
    unit: Optional[str]
    source: str
    mode: str
    timestamp: str = field(default_factory=utc_now)
    confidence: Optional[str] = None  # "high" | "medium" | "low"
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"invalid mode: {self.mode!r}")

    @property
    def is_simulated(self) -> bool:
        return self.mode == SIMULATED

    @property
    def ok(self) -> bool:
        return self.mode != UNAVAILABLE and self.value is not None

    @classmethod
    def unavailable(cls, source: str, error: str, unit: Optional[str] = None) -> "Measurement":
        return cls(value=None, unit=unit, source=source, mode=UNAVAILABLE, error=error)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["is_simulated"] = self.is_simulated
        return d


@dataclass
class WifiInterface:
    """State of one wireless interface. Fields are ``None`` when the OS does not expose them."""

    name: str
    connected: bool
    state: Optional[str] = None
    description: Optional[str] = None
    ssid: Optional[str] = None
    bssid: Optional[str] = None
    channel: Optional[int] = None
    frequency_mhz: Optional[int] = None
    band: Optional[str] = None
    radio_type: Optional[str] = None
    channel_width_mhz: Optional[int] = None
    security: Optional[str] = None
    rx_rate_mbps: Optional[float] = None
    tx_rate_mbps: Optional[float] = None
    signal_percent: Optional[int] = None
    signal_dbm: Optional[Measurement] = None
    noise_dbm: Optional[int] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["signal_dbm"] = self.signal_dbm.to_dict() if self.signal_dbm else None
        return d


@dataclass
class AccessPoint:
    ssid: Optional[str]  # None for hidden networks
    bssid: Optional[str]
    channel: Optional[int] = None
    frequency_mhz: Optional[int] = None
    band: Optional[str] = None
    security: Optional[str] = None
    signal_percent: Optional[int] = None
    signal_dbm: Optional[int] = None
    signal_mode: str = UNAVAILABLE  # provenance of signal_dbm
    radio_type: Optional[str] = None
    channel_width_mhz: Optional[int] = None
    connected: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderResult:
    """Result envelope returned by every provider call."""

    mode: str
    source: str
    data: Any = None
    error: Optional[str] = None
    hint: Optional[str] = None  # remediation the user can act on
    timestamp: str = field(default_factory=utc_now)

    @property
    def ok(self) -> bool:
        return self.mode != UNAVAILABLE

    def to_dict(self) -> dict:
        data = self.data
        if isinstance(data, list):
            data = [x.to_dict() if hasattr(x, "to_dict") else x for x in data]
        elif hasattr(data, "to_dict"):
            data = data.to_dict()
        return {
            "mode": self.mode,
            "source": self.source,
            "is_simulated": self.mode == SIMULATED,
            "timestamp": self.timestamp,
            "error": self.error,
            "hint": self.hint,
            "data": data,
        }
