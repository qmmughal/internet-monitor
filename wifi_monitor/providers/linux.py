"""Linux provider using NetworkManager (``nmcli``) and, when available, ``iw``.

``nmcli`` reports signal as a percentage (dBm is then *estimated*); ``iw dev
<if> link`` reports the driver's RSSI in dBm, which is used as a live value.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..models import ESTIMATED, LIVE, AccessPoint, Measurement, ProviderResult, WifiInterface
from ..signal import percent_to_dbm_estimate, resolve_channel
from .base import WifiProvider, command_failure, to_int

SOURCE = "nmcli"
AP_FIELDS = ["IN-USE", "SSID", "BSSID", "CHAN", "FREQ", "RATE", "SIGNAL", "SECURITY", "DEVICE"]
DEV_FIELDS = ["DEVICE", "TYPE", "STATE", "CONNECTION"]


def split_terse(line: str) -> List[str]:
    """Split one ``nmcli -t -e yes`` line on unescaped colons."""
    fields, buf, esc = [], [], False
    for ch in line:
        if esc:
            buf.append(ch)
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == ":":
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    fields.append("".join(buf))
    return fields


def parse_ap_list(text: str) -> List[AccessPoint]:
    aps = []
    for line in text.splitlines():
        if not line.strip():
            continue
        f = split_terse(line)
        if len(f) != len(AP_FIELDS):
            continue
        row = dict(zip(AP_FIELDS, f))
        pct = to_int(row["SIGNAL"])
        ch, freq, band = resolve_channel(to_int(row["CHAN"]), to_int(row["FREQ"]), None)
        sec = row["SECURITY"].strip()
        aps.append(
            AccessPoint(
                ssid=row["SSID"] or None,
                bssid=row["BSSID"].lower() or None,
                channel=ch,
                frequency_mhz=freq,
                band=band,
                security=sec if sec and sec != "--" else "Open",
                signal_percent=pct,
                signal_dbm=percent_to_dbm_estimate(pct) if pct is not None else None,
                signal_mode=ESTIMATED if pct is not None else "unavailable",
                connected=row["IN-USE"].strip() == "*",
            )
        )
    return aps


def parse_device_status(text: str) -> List[Dict[str, str]]:
    rows = []
    for line in text.splitlines():
        f = split_terse(line)
        if len(f) == len(DEV_FIELDS):
            rows.append(dict(zip(DEV_FIELDS, f)))
    return [r for r in rows if r["TYPE"] == "wifi"]


def parse_iw_link(text: str) -> Dict[str, Optional[float]]:
    """Parse ``iw dev <if> link``. Returns {} when not connected."""
    if "Not connected" in text or "Connected to" not in text:
        return {}
    out: Dict[str, Optional[float]] = {}
    m = re.search(r"signal:\s*(-?\d+)\s*dBm", text)
    out["signal_dbm"] = int(m.group(1)) if m else None
    m = re.search(r"freq:\s*(\d+)", text)
    out["freq"] = int(m.group(1)) if m else None
    m = re.search(r"rx bitrate:\s*([\d.]+)", text)
    out["rx"] = float(m.group(1)) if m else None
    m = re.search(r"tx bitrate:\s*([\d.]+)", text)
    out["tx"] = float(m.group(1)) if m else None
    bitrate_lines = " ".join(l for l in text.splitlines() if "bitrate" in l)
    m = re.search(r"\b(\d{2,3})MHz\b", bitrate_lines)
    out["width"] = int(m.group(1)) if m else None
    phy = None
    for token, name in (("EHT-", "802.11be"), ("HE-", "802.11ax"), ("VHT-", "802.11ac"), ("MCS", "802.11n")):
        if token in bitrate_lines:
            phy = name
            break
    out["phy"] = phy
    return out


class LinuxProvider(WifiProvider):
    name = "linux-nmcli"
    platform = "Linux"

    def _ap_list(self, rescan: str) -> ProviderResult:
        cmd = self._run(
            ["nmcli", "-t", "-e", "yes", "-f", ",".join(AP_FIELDS), "device", "wifi", "list", "--rescan", rescan],
            timeout=15 if rescan != "no" else 5,
        )
        fail = command_failure(cmd, SOURCE)
        if fail:
            fail.hint = "Install NetworkManager (nmcli), or use a distribution that ships it."
            return fail
        if cmd.returncode != 0:
            msg = (cmd.stderr or cmd.stdout).strip().splitlines()
            return ProviderResult(mode="unavailable", source=SOURCE, error=msg[0] if msg else "nmcli failed")
        return ProviderResult(mode=LIVE, source=SOURCE, data=parse_ap_list(cmd.stdout))

    def interfaces(self) -> ProviderResult:
        cmd = self._run(["nmcli", "-t", "-e", "yes", "-f", ",".join(DEV_FIELDS), "device", "status"], timeout=5)
        fail = command_failure(cmd, SOURCE)
        if fail:
            fail.hint = "Install NetworkManager (nmcli), or use a distribution that ships it."
            return fail
        devices = parse_device_status(cmd.stdout)
        if not devices:
            return ProviderResult(mode="unavailable", source=SOURCE, error="no Wi-Fi interface found")

        aps = self._ap_list("no")
        active = next((ap for ap in (aps.data or []) if ap.connected), None)

        result = []
        for dev in devices:
            connected = dev["STATE"] == "connected"
            iface = WifiInterface(name=dev["DEVICE"], connected=connected, state=dev["STATE"])
            if connected and active is not None:
                iface.ssid = active.ssid
                iface.bssid = active.bssid
                iface.channel, iface.frequency_mhz, iface.band = active.channel, active.frequency_mhz, active.band
                iface.security = active.security
                iface.signal_percent = active.signal_percent
                if active.signal_percent is not None:
                    iface.signal_dbm = Measurement(
                        active.signal_dbm, "dBm", f"{SOURCE}:SIGNAL%", ESTIMATED, confidence="low"
                    )
            if connected:
                self._enrich_with_iw(iface)
            result.append(iface)
        return ProviderResult(mode=LIVE, source=SOURCE, data=result)

    def _enrich_with_iw(self, iface: WifiInterface) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_.\-]{1,15}", iface.name):  # Linux IFNAMSIZ; never pass odd names on
            return
        cmd = self._run(["iw", "dev", iface.name, "link"], timeout=3)
        if not cmd.ok:
            return
        link = parse_iw_link(cmd.stdout)
        if link.get("signal_dbm") is not None:
            iface.signal_dbm = Measurement(int(link["signal_dbm"]), "dBm", "iw:signal", LIVE, confidence="high")
        if link.get("freq") and iface.frequency_mhz is None:
            iface.channel, iface.frequency_mhz, iface.band = resolve_channel(None, int(link["freq"]), None)
        iface.channel_width_mhz = link.get("width") or iface.channel_width_mhz
        iface.radio_type = link.get("phy") or iface.radio_type
        iface.rx_rate_mbps = link.get("rx") or iface.rx_rate_mbps
        iface.tx_rate_mbps = link.get("tx") or iface.tx_rate_mbps

    def access_points(self) -> ProviderResult:
        return self._ap_list("auto")

    def capabilities(self) -> Dict[str, dict]:
        return {
            "ssid": {"supported": True},
            "bssid": {"supported": True},
            "signal_dbm": {"supported": "partial", "notes": "live via 'iw' when installed, else estimated from %"},
            "signal_percent": {"supported": True},
            "channel": {"supported": True},
            "band": {"supported": True},
            "link_rate": {"supported": "partial", "notes": "requires 'iw'"},
            "noise": {"supported": False},
            "access_point_scan": {"supported": True, "notes": "may trigger a rescan (up to ~15 s)"},
            "permissions": {"notes": "requires NetworkManager; no root needed"},
        }

