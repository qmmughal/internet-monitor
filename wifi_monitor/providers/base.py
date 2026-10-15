"""Provider interface implemented once per operating system."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from ..models import ProviderResult, WifiInterface
from ..runner import CommandResult, run

Runner = Callable[..., CommandResult]


class WifiProvider:
    """Reads Wi-Fi state from the OS. Subclasses must never fabricate values."""

    name = "base"
    platform = "unknown"

    def __init__(self, runner: Runner = run) -> None:
        self._run = runner

    def interfaces(self) -> ProviderResult:  # data: List[WifiInterface]
        raise NotImplementedError

    def access_points(self) -> ProviderResult:  # data: List[AccessPoint]
        raise NotImplementedError

    def capabilities(self) -> Dict[str, dict]:
        """Static description of what this platform can report; see docs/CAPABILITIES."""
        raise NotImplementedError

    def connected_interface(self) -> ProviderResult:
        """The first connected interface, or an unavailable result explaining why there is none."""
        res = self.interfaces()
        if not res.ok:
            return res
        ifaces: List[WifiInterface] = res.data or []
        for iface in ifaces:
            if iface.connected:
                return ProviderResult(mode=res.mode, source=res.source, data=iface, timestamp=res.timestamp)
        detail = "no Wi-Fi interface is connected" if ifaces else "no Wi-Fi interface found"
        return ProviderResult(mode="unavailable", source=res.source, error=detail, timestamp=res.timestamp)


def command_failure(cmd: CommandResult, tool: str) -> Optional[ProviderResult]:
    """Translate runner-level failures into an unavailable result, or None if the command ran."""
    if cmd.error == "not_found":
        return ProviderResult(mode="unavailable", source=tool, error=f"'{tool}' is not installed or not on PATH")
    if cmd.error == "timeout":
        return ProviderResult(mode="unavailable", source=tool, error=f"'{tool}' timed out")
    if cmd.error:
        return ProviderResult(mode="unavailable", source=tool, error=cmd.error)
    return None


def to_int(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    digits = "".join(ch for ch in text.strip() if ch.isdigit() or ch == "-")
    try:
        return int(digits) if digits not in ("", "-") else None
    except ValueError:
        return None


def to_float(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    token = text.strip().split()[0] if text.strip() else ""
    try:
        return float(token.replace(",", "."))
    except ValueError:
        return None
