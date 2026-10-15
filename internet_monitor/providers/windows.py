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
import time
from typing import Dict, List, Optional, Tuple

from ..models import ESTIMATED, LIVE, AccessPoint, Measurement, ProviderResult, WifiInterface
from ..signal import percent_to_dbm_estimate, resolve_channel
from ..runner import run
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


ADAPTER_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$out = @(Get-NetAdapter -IncludeHidden | Where-Object {
    $_.PhysicalMediaType -like '*802.11*' -or $_.InterfaceDescription -match 'Wi-?Fi|Wireless|WLAN|802\.11' } |
  Where-Object { $_.InterfaceDescription -notmatch 'Virtual|Direct' } | ForEach-Object {
    $pnp = Get-PnpDevice -InstanceId $_.PnPDeviceID
    [pscustomobject]@{ name = $_.Name; description = $_.InterfaceDescription; status = "$($_.Status)";
      admin = "$($_.AdminStatus)"; pnp_status = "$($pnp.Status)"; problem = "$($pnp.Problem)" } })
ConvertTo-Json -InputObject $out -Compress
"""

PNP_PROBLEMS = {
    "CM_PROB_FAILED_POST_START": "Windows stopped the device because it reported a problem (Device Manager code 43)",
    "CM_PROB_DISABLED": "the device is disabled in Device Manager (code 22)",
    "CM_PROB_HARDWARE_DISABLED": "the device is disabled by the hardware/firmware (code 29)",
    "CM_PROB_FAILED_START": "the device driver could not start (code 10)",
    "CM_PROB_DRIVER_FAILED_LOAD": "the device driver failed to load (code 39)",
    "CM_PROB_FAILED_INSTALL": "the driver is not installed correctly (code 28)",
    "CM_PROB_PHANTOM": "the device is not currently connected (code 45)",
}


def adapter_health(runner) -> List[dict]:
    from ..pwsh import run_json

    data, err = run_json(ADAPTER_SCRIPT, timeout=20, runner=runner)
    if err or data is None:
        return []
    return data if isinstance(data, list) else [data]


def explain_adapters(adapters: List[dict]) -> Optional[Tuple[str, str]]:
    """(error, hint) when a Wi-Fi adapter exists but is not usable, else None."""
    for a in adapters:
        desc = a.get("description") or a.get("name") or "Wi-Fi adapter"
        problem = a.get("problem") or ""
        if problem and problem not in ("CM_PROB_NONE", "0"):
            reason = PNP_PROBLEMS.get(problem, f"Windows reports a device problem ({problem})")
            return (f"Wi-Fi adapter '{desc}' is not working: {reason}",
                    "Open Device Manager › Network adapters, check the device, and try updating or reinstalling its "
                    "driver, or restart the computer. Internet Monitor does not change device settings.")
        if (a.get("admin") or "").lower() == "down" or (a.get("status") or "").lower() == "disabled":
            return (f"Wi-Fi adapter '{desc}' is disabled",
                    "Enable it in Settings › Network & internet › Advanced network settings.")
    return None


def request_scan() -> bool:
    """Ask Windows to rescan via the Native Wifi API (``WlanScan``, no admin needed).

    Some adapters (e.g. USB dongles) do not scan in the background while
    connected, leaving ``netsh`` with a stale list. Returns True if a scan was
    requested on at least one interface.
    """
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:  # pragma: no cover
        return False

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    class InterfaceInfo(ctypes.Structure):
        _fields_ = [("InterfaceGuid", GUID), ("strInterfaceDescription", ctypes.c_wchar * 256),
                    ("isState", wintypes.DWORD)]

    class InterfaceInfoList(ctypes.Structure):
        _fields_ = [("dwNumberOfItems", wintypes.DWORD), ("dwIndex", wintypes.DWORD),
                    ("InterfaceInfo", InterfaceInfo * 1)]

    try:
        wlan = ctypes.windll.wlanapi
    except (AttributeError, OSError):
        return False
    handle, version = wintypes.HANDLE(), wintypes.DWORD()
    if wlan.WlanOpenHandle(2, None, ctypes.byref(version), ctypes.byref(handle)) != 0:
        return False
    requested = False
    plist = ctypes.POINTER(InterfaceInfoList)()
    try:
        if wlan.WlanEnumInterfaces(handle, None, ctypes.byref(plist)) != 0:
            return False
        n = plist.contents.dwNumberOfItems
        if n:
            items = ctypes.cast(ctypes.byref(plist.contents.InterfaceInfo),
                                ctypes.POINTER(InterfaceInfo * n)).contents
            for info in items:
                if wlan.WlanScan(handle, ctypes.byref(info.InterfaceGuid), None, None, None) == 0:
                    requested = True
        wlan.WlanFreeMemory(plist)
    finally:
        wlan.WlanCloseHandle(handle, None)
    return requested


SCAN_WAIT_S = 2.5  # measured: a USB adapter's list went from 1 to 9 access points within 2 s


def radio_off(text: str) -> bool:
    return bool(re.search(r"\b(Software|Hardware) Off\b", text))


class WindowsProvider(WifiProvider):
    name = "windows-netsh"
    platform = "Windows"

    def __init__(self, runner=run, scanner=None, sleep=time.sleep) -> None:
        super().__init__(runner)
        self._health_cache: Optional[Tuple[float, List[dict]]] = None
        # Only touch the real WLAN API when running real commands (tests inject a fake runner).
        self._scan = scanner if scanner is not None else (request_scan if runner is run else (lambda: False))
        self._sleep = sleep

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

    def _explain_missing(self, err: ProviderResult) -> ProviderResult:
        """When netsh sees no wireless interface, check whether an adapter exists but is not working."""
        if not err.error or "no Wi-Fi interface" not in err.error:
            return err
        now = time.monotonic()
        if self._health_cache is None or now - self._health_cache[0] > 60:
            self._health_cache = (now, adapter_health(self._run))
        adapters = self._health_cache[1]
        explained = explain_adapters(adapters)
        if explained:
            err.error, err.hint = explained
            err.data = None
        return err

    def interfaces(self) -> ProviderResult:
        text, err = self._netsh("show", "interfaces")
        if err:
            return self._explain_missing(err)
        parsed = parse_interfaces(text or "")
        if parsed is None:
            return ProviderResult(mode="unavailable", source=SOURCE, error="unrecognised netsh output", hint=LOCALE_HINT)
        hint = None
        if not any(i.connected for i in parsed) and radio_off(text or ""):
            hint = "Wi-Fi is switched off (airplane mode, the Wi-Fi toggle, or a hardware switch). Turn it on to connect."
        return ProviderResult(mode=LIVE, source=SOURCE, data=parsed, hint=hint)

    def access_points(self) -> ProviderResult:
        fresh = self._scan()
        if fresh:
            self._sleep(SCAN_WAIT_S)
        text, err = self._netsh("show", "networks", "mode=bssid")
        if err:
            return self._explain_missing(err)
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
            hint=("Fresh scan requested from Windows." if fresh else
                  "Results come from Windows' cached scan list and may be up to a minute old."),
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
            "access_point_scan": {"supported": True, "notes": "fresh scan requested via WlanScan, then read with netsh"},
            "permissions": {"notes": "Windows 11 24H2+: Location access required"},
        }
