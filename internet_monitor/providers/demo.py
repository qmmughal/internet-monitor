"""Demo provider: generated data for presentations and UI development.

Every result is marked ``mode="simulated"``. It is only used when the user
asks for it explicitly (``--demo``); it is never a fallback for real data.
"""

from __future__ import annotations

import random
from typing import Dict, Optional

from ..models import SIMULATED, AccessPoint, Measurement, ProviderResult, WifiInterface
from ..signal import dbm_to_percent, resolve_channel
from .base import WifiProvider

SOURCE = "demo"
_NETWORKS = [
    ("DEMO-Home_5G", 36, "5 GHz", "WPA3-Personal"),
    ("DEMO-Office", 11, "2.4 GHz", "WPA2-Personal"),
    ("DEMO-Cafe", 6, "2.4 GHz", "Open"),
    ("DEMO-Neighbour", 6, "2.4 GHz", "WPA2-Personal"),
    ("DEMO-6E", 37, "6 GHz", "WPA3-Personal"),
    ("DEMO-Upstairs", 149, "5 GHz", "WPA2-Personal"),
]


class DemoProvider(WifiProvider):
    name = "demo"
    platform = "demo"

    def __init__(self, seed: Optional[int] = None) -> None:
        super().__init__()
        self._rng = random.Random(seed)
        self._dbm = -58.0

    def interfaces(self) -> ProviderResult:
        self._dbm = max(-90.0, min(-35.0, self._dbm + self._rng.gauss(0, 1.5)))
        dbm = round(self._dbm)
        ch, freq, band = resolve_channel(36, None, "5 GHz")
        iface = WifiInterface(
            name="demo0",
            connected=True,
            state="connected",
            ssid="DEMO-Home_5G",
            bssid="02:00:00:00:00:01",
            channel=ch,
            frequency_mhz=freq,
            band=band,
            radio_type="802.11ax",
            security="WPA3-Personal",
            rx_rate_mbps=866.0,
            tx_rate_mbps=866.0,
            signal_percent=dbm_to_percent(dbm),
            signal_dbm=Measurement(dbm, "dBm", SOURCE, SIMULATED),
        )
        return ProviderResult(mode=SIMULATED, source=SOURCE, data=[iface])

    def access_points(self) -> ProviderResult:
        aps = []
        for i, (ssid, ch, band, sec) in enumerate(_NETWORKS, start=1):
            dbm = self._rng.randint(-88, -45)
            c, f, b = resolve_channel(ch, None, band)
            aps.append(
                AccessPoint(
                    ssid=ssid,
                    bssid=f"02:00:00:00:00:{i:02x}",  # locally administered range: never a real vendor
                    channel=c,
                    frequency_mhz=f,
                    band=b,
                    security=sec,
                    signal_percent=dbm_to_percent(dbm),
                    signal_dbm=dbm,
                    signal_mode=SIMULATED,
                    connected=i == 1,
                )
            )
        return ProviderResult(mode=SIMULATED, source=SOURCE, data=aps)

    def capabilities(self) -> Dict[str, dict]:
        return {"all": {"supported": "simulated", "notes": "demo mode — no real measurements"}}
