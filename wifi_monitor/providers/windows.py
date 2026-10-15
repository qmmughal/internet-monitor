"""Windows provider using the built-in ``netsh wlan`` command.

Limitations (documented in docs/CAPABILITIES.md):
* ``netsh`` labels are localised. Only English labels are parsed; other
  locales are reported as unavailable with a hint instead of guessed.
* Windows 11 24H2+ requires Location access for ``netsh wlan``.
* ``show networks`` returns the OS's cached scan list; it does not force a rescan.
* Signal is a 0–100 % quality value. Newer builds also print ``Rssi`` in dBm,
  which is used as a live measurement when present.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..models import ESTIMATED, LIVE, AccessPoint, Measurement, ProviderResult, WifiInterface
from ..signal import percent_to_dbm_estimate, resolve_channel
from .base import WifiProvider, command_failure, to_float, to_int

SOURCE = "netsh"
_LINE = re.compile(r"^(?P<indent>\s*)(?P<key>[^:]+?)\s*:\s?(?P<val>.*)$")

LOCATION_HINT = (
    "Windows requires Location access for Wi-Fi details. Turn on Settings > Privacy & security > "
    "Location (and 'Let desktop apps access your location'), then retry."
)
LOCALE_HINT = (
    "netsh output is not in English, so it could not be parsed reliably. "
    "Run with an English display language, or open an issue with a sample of the output."
)


def _pairs(text: str) -> List[Tuple[int, str, str]]:
    out = []
    for raw in text.splitlines():
        m = _LINE.match(raw)
        if m:
            out.append((len(m.group("indent")), m.group("key").strip(), m.group("val").strip()))
    return out


def classify_error(text: str) -> Optional[ProviderResult]:
    """Recognise the known netsh failure messages."""
    low = text.lower()
    if "location permission" in low or "privacy-location" in low:
        return ProviderResult(mode="unavailable", source=SOURCE, error="location permission denied", hint=LOCATION_HINT)
    if "no wireless interface" in low:
        return ProviderResult(mode="unavailable", source=SOURCE, error="no Wi-Fi interface found on this computer")
    if "wlansvc" in low or "autoconfig service" in low:
        return ProviderResult(
            mode="unavailable",
            source=SOURCE,
            error="the WLAN AutoConfig service is not running",
            hint="Start the 'WLAN AutoConfig' service (services.msc).",
        )
    return None


def parse_interfaces(text: str) -> Optional[List[WifiInterface]]:
    """Parse ``netsh wlan show interfaces``. Returns None if no English labels were found."""
    blocks: List[Dict[str, str]] = []
    for _indent, key, val in _pairs(text):
        k = key.lower()
        if k == "name":
            blocks.append({})
        if blocks:
            blocks[-1].setdefault(k, val)
    if not blocks or not any("state" in b for b in blocks):
        return None  # e.g. German output also uses "Name", but not "State"

    result = []
    for b in blocks:
        state = b.get("state", "")
        connected = state.lower() == "connected"
        pct = to_int(b.get("signal"))
        rssi = to_int(b.get("rssi"))
        if rssi is not None and rssi < 0:
            signal = Measurement(rssi, "dBm", f"{SOURCE}:Rssi", LIVE, confidence="high")
        elif pct is not None:
            signal = Measurement(
                percent_to_dbm_estimate(pct), "dBm", f"{SOURCE}:Signal%", ESTIMATED, confidence="low"
            )
        else:
            signal = None

        channel, freq, band = resolve_channel(to_int(b.get("channel")), None, b.get("band"))
        result.append(
            WifiInterface(
                name=b.get("name", "?"),
                connected=connected,
                state=state or None,
                description=b.get("description"),
                ssid=(b.get("ssid") or None) if connected else None,
                bssid=_mac(b.get("ap bssid") or b.get("bssid")) if connected else None,
                channel=channel if connected else None,
                frequency_mhz=freq if connected else None,
                band=band if connected else None,
                radio_type=b.get("radio type") if connected else None,
                security=b.get("authentication") if connected else None,
                rx_rate_mbps=to_float(b.get("receive rate (mbps)")) if connected else None,
                tx_rate_mbps=to_float(b.get("transmit rate (mbps)")) if connected else None,
                signal_percent=pct if connected else None,
                signal_dbm=signal if connected else None,
            )
        )
    return result


def parse_networks(text: str) -> Optional[List[AccessPoint]]:
    """Parse ``netsh wlan show networks mode=bssid``. Returns None if no English labels were found."""
    aps: List[AccessPoint] = []
    seen_ssid_header = False
    ssid: Optional[str] = None
    auth: Optional[str] = None
    current: Optional[AccessPoint] = None
    pending_band: Optional[str] = None

    def finish() -> None:
        if current is not None:
            ch, freq, band = resolve_channel(current.channel, None, pending_band)
            current.channel, current.frequency_mhz, current.band = ch, freq, band

    for _indent, key, val in _pairs(text):
        k = key.lower()
        if re.fullmatch(r"ssid \d+", k):
            finish()
            current, pending_band = None, None
            seen_ssid_header = True
            ssid, auth = (val or None), None
        elif k == "authentication":
            auth = val
        elif re.fullmatch(r"bssid \d+", k):
            finish()
            pending_band = None
            current = AccessPoint(ssid=ssid, bssid=_mac(val), security=auth)
            aps.append(current)
        elif current is not None:
            if k == "signal":
                pct = to_int(val)
                current.signal_percent = pct
                if pct is not None and current.signal_mode != LIVE:
                    current.signal_dbm = percent_to_dbm_estimate(pct)
                    current.signal_mode = ESTIMATED
            elif k == "rssi":
                rssi = to_int(val)
                if rssi is not None and rssi < 0:
                    current.signal_dbm, current.signal_mode = rssi, LIVE
            elif k == "radio type":
                current.radio_type = val
            elif k == "band":
                pending_band = val
            elif k == "channel":
                current.channel = to_int(val)
    finish()
    return aps if seen_ssid_header or aps else None


def _mac(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    m = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", val)
    return m.group(0).lower().replace("-", ":") if m else None


class WindowsProvider(WifiProvider):
    name = "windows-netsh"
    platform = "Windows"

    def _netsh(self, *args: str) -> Tuple[Optional[str], Optional[ProviderResult]]:
        cmd = self._run(["netsh", "wlan", *args], timeout=8)
        fail = command_failure(cmd, SOURCE)
        if fail:
            return None, fail
        text = cmd.stdout + "\n" + cmd.stderr
        known = classify_error(text)
        if known:
            return None, known
        if cmd.returncode != 0:
            return None, ProviderResult(
                mode="unavailable", source=SOURCE, error=f"netsh exited with code {cmd.returncode}"
            )
        return cmd.stdout, None

    def interfaces(self) -> ProviderResult:
        text, err = self._netsh("show", "interfaces")
        if err:
            return err
        parsed = parse_interfaces(text or "")
        if parsed is None:
            return ProviderResult(mode="unavailable", source=SOURCE, error="unrecognised netsh output", hint=LOCALE_HINT)
        return ProviderResult(mode=LIVE, source=SOURCE, data=parsed)

    def access_points(self) -> ProviderResult:
        text, err = self._netsh("show", "networks", "mode=bssid")
        if err:
            return err
        parsed = parse_networks(text or "")
        if parsed is None:
            return ProviderResult(mode="unavailable", source=SOURCE, error="unrecognised netsh output", hint=LOCALE_HINT)
        conn = self.connected_interface()
        if conn.ok:
            for ap in parsed:
                ap.connected = bool(ap.bssid and ap.bssid == conn.data.bssid)
        return ProviderResult(
            mode=LIVE,
            source=SOURCE,
            data=parsed,
            hint="Results come from Windows' cached scan list and may be up to a minute old.",
        )

    def capabilities(self) -> Dict[str, dict]:
        return {
            "ssid": {"supported": True},
            "bssid": {"supported": True},
            "signal_dbm": {"supported": "partial", "notes": "live from 'Rssi' on newer builds, else estimated from %"},
            "signal_percent": {"supported": True},
            "channel": {"supported": True},
            "band": {"supported": True},
            "link_rate": {"supported": True},
            "noise": {"supported": False},
            "access_point_scan": {"supported": True, "notes": "cached OS scan list"},
            "permissions": {"notes": "Windows 11 24H2+: Location access required"},
        }
