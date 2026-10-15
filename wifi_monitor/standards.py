"""Wi-Fi generation / capability reporting from evidence the OS provides.

What can be known: the PHY mode the *current link* negotiated (e.g. 802.11ax),
the band and, on some platforms, the channel width. That describes this
connection, not the maximum the router or adapter supports.

What is never inferred: Wi-Fi 7 from an SSID or a 6 GHz frequency alone, or
Multi-Link Operation (MLO) without an OS field that reports it.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .models import WifiInterface

_GENERATIONS = [
    ("802.11be", "Wi-Fi 7"),
    ("802.11ax", "Wi-Fi 6"),
    ("802.11ac", "Wi-Fi 5"),
    ("802.11n", "Wi-Fi 4"),
    ("802.11g", "legacy (802.11g)"),
    ("802.11a", "legacy (802.11a)"),
    ("802.11b", "legacy (802.11b)"),
]


def phy_from_text(radio_type: Optional[str]) -> Optional[str]:
    if not radio_type:
        return None
    t = radio_type.lower().replace(" ", "")
    m = re.search(r"802\.11(be|ax|ac|n|g|a|b)", t)
    if m:
        return "802.11" + m.group(1)
    return None


def describe(iface: WifiInterface) -> dict:
    """Generation, 6E/7 indicators and MLO status for a connected interface, with evidence."""
    evidence: List[str] = []
    phy = phy_from_text(iface.radio_type)
    generation = None
    if phy:
        generation = dict(_GENERATIONS).get(phy)
        evidence.append(f"OS reports PHY mode {iface.radio_type!s}")
        if phy == "802.11ax" and iface.band == "6 GHz":
            generation = "Wi-Fi 6E"
            evidence.append("connection is in the 6 GHz band")
    if iface.band:
        evidence.append(f"band {iface.band}" + (f", {iface.frequency_mhz} MHz" if iface.frequency_mhz else ""))
    if iface.channel_width_mhz:
        evidence.append(f"channel width {iface.channel_width_mhz} MHz")

    notes = []
    if generation is None:
        notes.append("The OS did not report a PHY mode, so the Wi-Fi generation is unknown.")
    if iface.band == "6 GHz" and phy is None:
        notes.append("6 GHz implies at least Wi-Fi 6E hardware, but the exact generation was not reported.")
    if phy == "802.11be" and not iface.channel_width_mhz:
        notes.append("Wi-Fi 7 link reported; channel width (e.g. 320 MHz) not exposed by this platform.")

    return {
        "generation": generation,
        "phy": phy,
        "band": iface.band,
        "six_ghz": iface.band == "6 GHz",
        "channel_width_mhz": iface.channel_width_mhz,
        "mlo": {
            "status": "unavailable",
            "reason": "No supported OS interface on this platform reports Multi-Link Operation yet.",
        },
        "scope": "current connection (negotiated), not the maximum supported by router or adapter",
        "evidence": evidence,
        "notes": notes,
    }
