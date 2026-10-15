"""macOS provider.

Apple removed the ``airport`` utility in macOS 14.4. This provider uses
``system_profiler SPAirPortDataType -json`` (supported, no sudo, but slow:
2–10 s) and falls back to ``airport -I`` only if the binary still exists.

Since macOS 14/15 the SSID may be reported as ``<redacted>`` unless the calling
app has Location permission; that case is reported as unknown, not guessed.
No BSSID is exposed by ``system_profiler``.

Not yet verified on real Apple hardware — parsing is covered by fixtures only.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ..models import LIVE, AccessPoint, Measurement, ProviderResult, WifiInterface
from ..signal import resolve_channel
from .base import WifiProvider, command_failure, to_int

SOURCE = "system_profiler"
AIRPORT = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
REDACTED_HINT = "macOS hides the network name unless the terminal app has Location permission."


def _parse_channel(text: Any):
    """'44 (5GHz, 80MHz)' -> (44, '5 GHz', 80)."""
    s = str(text or "")
    ch = to_int(s.split()[0].split(",")[0]) if s.strip() else None
    band = None
    m = re.search(r"(\d)GHz", s)
    if m:
        band = {"2": "2.4 GHz", "5": "5 GHz", "6": "6 GHz"}.get(m.group(1))
    w = re.search(r"(\d+)MHz", s)
    return ch, band, int(w.group(1)) if w else None


def _parse_signal_noise(text: Any):
    """'-52 dBm / -93 dBm' -> (-52, -93)."""
    nums = re.findall(r"-\d+", str(text or ""))
    sig = int(nums[0]) if nums else None
    noise = int(nums[1]) if len(nums) > 1 else None
    return sig, noise


def _security(val: Any) -> Optional[str]:
    if not val:
        return None
    s = str(val).replace("spairport_security_mode_", "").replace("_", " ").strip()
    return "Open" if s == "none" else s.upper().replace("PERSONAL", "Personal").replace("ENTERPRISE", "Enterprise")


def _ssid(val: Any) -> Optional[str]:
    if not val or val == "<redacted>":
        return None
    return str(val)


def parse_system_profiler(text: str) -> Optional[Dict[str, List]]:
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    ifaces: List[WifiInterface] = []
    aps: List[AccessPoint] = []
    redacted = False
    for section in doc.get("SPAirPortDataType", []):
        for raw in section.get("spairport_airport_interfaces", []):
            name = raw.get("_name", "?")
            if not str(name).startswith("en"):  # skip awdl0 etc.
                continue
            status = str(raw.get("spairport_status_information", ""))
            connected = status.endswith("connected") and "dis" not in status
            iface = WifiInterface(name=name, connected=connected, state=status.replace("spairport_status_", "") or None)
            cur = raw.get("spairport_current_network_information") or {}
            if connected and cur:
                redacted = redacted or cur.get("_name") == "<redacted>"
                ch, band, _width = _parse_channel(cur.get("spairport_network_channel"))
                iface.channel, iface.frequency_mhz, iface.band = resolve_channel(ch, None, band)
                iface.ssid = _ssid(cur.get("_name"))
                iface.radio_type = cur.get("spairport_network_phymode")
                iface.security = _security(cur.get("spairport_security_mode"))
                rate = cur.get("spairport_network_rate")
                iface.tx_rate_mbps = float(rate) if isinstance(rate, (int, float)) else None
                sig, noise = _parse_signal_noise(cur.get("spairport_signal_noise"))
                if sig is not None:
                    iface.signal_dbm = Measurement(sig, "dBm", f"{SOURCE}:signal", LIVE, confidence="high")
                iface.noise_dbm = noise
                aps.append(_ap_from(cur, connected=True))
            ifaces.append(iface)
            for other in raw.get("spairport_airport_other_local_wireless_networks", []) or []:
                aps.append(_ap_from(other, connected=False))
    return {"interfaces": ifaces, "access_points": aps, "redacted": redacted}


def _ap_from(raw: Dict[str, Any], connected: bool) -> AccessPoint:
    ch, band, _ = _parse_channel(raw.get("spairport_network_channel"))
    ch, freq, band = resolve_channel(ch, None, band)
    sig, _noise = _parse_signal_noise(raw.get("spairport_signal_noise"))
    return AccessPoint(
        ssid=_ssid(raw.get("_name")),
        bssid=None,
        channel=ch,
        frequency_mhz=freq,
        band=band,
        security=_security(raw.get("spairport_security_mode")),
        signal_dbm=sig,
        signal_mode=LIVE if sig is not None else "unavailable",
        radio_type=raw.get("spairport_network_phymode"),
        connected=connected,
    )


def parse_airport_info(text: str) -> Optional[WifiInterface]:
    kv = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            kv[k.strip()] = v.strip()
    if "agrCtlRSSI" not in kv:
        return None
    ch, freq, band = resolve_channel(to_int(kv.get("channel", "").split(",")[0]), None, None)
    rssi = to_int(kv.get("agrCtlRSSI"))
    return WifiInterface(
        name="en0",
        connected=kv.get("state") == "running",
        state=kv.get("state"),
        ssid=kv.get("SSID") or None,
        bssid=kv.get("BSSID") or None,
        channel=ch,
        frequency_mhz=freq,
        band=band,
        tx_rate_mbps=float(kv["lastTxRate"]) if kv.get("lastTxRate", "").isdigit() else None,
        signal_dbm=Measurement(rssi, "dBm", "airport:agrCtlRSSI", LIVE, confidence="high") if rssi is not None else None,
        noise_dbm=to_int(kv.get("agrCtlNoise")),
    )


class MacProvider(WifiProvider):
    name = "macos-system_profiler"
    platform = "Darwin"

    def _profile(self) -> ProviderResult:
        cmd = self._run(["system_profiler", "SPAirPortDataType", "-json"], timeout=20)
        fail = command_failure(cmd, SOURCE)
        if fail:
            return fail
        parsed = parse_system_profiler(cmd.stdout)
        if parsed is None:
            return ProviderResult(mode="unavailable", source=SOURCE, error="unrecognised system_profiler output")
        hint = REDACTED_HINT if parsed["redacted"] else None
        return ProviderResult(mode=LIVE, source=SOURCE, data=parsed, hint=hint)

    def interfaces(self) -> ProviderResult:
        legacy = self._run([AIRPORT, "-I"], timeout=3)
        if legacy.ok:
            iface = parse_airport_info(legacy.stdout)
            if iface is not None:
                return ProviderResult(mode=LIVE, source="airport", data=[iface])
        res = self._profile()
        if not res.ok:
            return res
        if not res.data["interfaces"]:
            return ProviderResult(mode="unavailable", source=SOURCE, error="no Wi-Fi interface found")
        return ProviderResult(mode=LIVE, source=SOURCE, data=res.data["interfaces"], hint=res.hint)

    def access_points(self) -> ProviderResult:
        res = self._profile()
        if not res.ok:
            return res
        return ProviderResult(
            mode=LIVE,
            source=SOURCE,
            data=res.data["access_points"],
            hint="macOS does not expose BSSIDs here; the list is the system's cached scan.",
        )

    def capabilities(self) -> Dict[str, dict]:
        return {
            "ssid": {"supported": "partial", "notes": "redacted without Location permission (macOS 14+)"},
            "bssid": {"supported": False, "notes": "only via legacy 'airport' (removed in 14.4)"},
            "signal_dbm": {"supported": True, "notes": "live RSSI"},
            "signal_percent": {"supported": False},
            "channel": {"supported": True},
            "band": {"supported": True},
            "link_rate": {"supported": "partial", "notes": "transmit rate only"},
            "noise": {"supported": True},
            "access_point_scan": {"supported": True, "notes": "cached; slow (2–10 s)"},
            "permissions": {"notes": "Location permission needed for SSIDs; not verified on hardware yet"},
        }
