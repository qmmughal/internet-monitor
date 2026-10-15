"""Select the Wi-Fi provider for the current operating system."""

from __future__ import annotations

import platform
from typing import Dict, List, Optional

from .base import WifiProvider
from .demo import DemoProvider
from .linux import LinuxProvider
from .macos import MacProvider
from .windows import WindowsProvider

_BY_SYSTEM = {"Windows": WindowsProvider, "Linux": LinuxProvider, "Darwin": MacProvider}


class UnsupportedProvider(WifiProvider):
    name = "unsupported"

    def __init__(self, system: str) -> None:
        super().__init__()
        self.platform = system

    def _none(self):
        from ..models import ProviderResult

        return ProviderResult(mode="unavailable", source="none", error=f"platform '{self.platform}' is not supported")

    def interfaces(self):
        return self._none()

    def access_points(self):
        return self._none()

    def capabilities(self) -> Dict[str, dict]:
        return {}


def get_provider(demo: bool = False, system: Optional[str] = None) -> WifiProvider:
    if demo:
        return DemoProvider()
    system = system or platform.system()
    cls = _BY_SYSTEM.get(system)
    return cls() if cls else UnsupportedProvider(system)


__all__: List[str] = ["WifiProvider", "DemoProvider", "get_provider", "WindowsProvider", "LinuxProvider", "MacProvider"]
