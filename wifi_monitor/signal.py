"""Signal and channel helpers (pure functions, no I/O)."""

from __future__ import annotations

from typing import Optional, Tuple

BAND_24 = "2.4 GHz"
BAND_5 = "5 GHz"
BAND_6 = "6 GHz"


def dbm_to_percent(dbm: float) -> int:
    """Map dBm onto 0–100 % using the common linear -100…-50 dBm scale."""
    if dbm >= -50:
        return 100
    if dbm <= -100:
        return 0
    return round((dbm + 100) * 2)


def percent_to_dbm_estimate(pct: int) -> int:
    """Inverse of the linear scale Windows and NetworkManager use for "signal quality".

    The OS percentage is itself derived from RSSI by a vendor-specific mapping,
    so the result is an *estimate* and must be labelled as such.
    """
    pct = max(0, min(100, int(pct)))
    return round(pct / 2 - 100)


def quality_label(dbm: float) -> str:
    if dbm >= -50:
        return "Excellent"
    if dbm >= -60:
        return "Good"
    if dbm >= -70:
        return "Fair"
    return "Poor"


def freq_to_band(mhz: Optional[int]) -> Optional[str]:
    if mhz is None:
        return None
    if 2400 <= mhz <= 2500:
        return BAND_24
    if 4900 <= mhz < 5925:
        return BAND_5
    if 5925 <= mhz <= 7125:
        return BAND_6
    return None


def freq_to_channel(mhz: Optional[int]) -> Optional[int]:
    if mhz is None:
        return None
    if mhz == 2484:
        return 14
    if 2412 <= mhz <= 2472:
        return (mhz - 2407) // 5
    if mhz == 5935:
        return 2
    if 5950 < mhz <= 7125:
        return (mhz - 5950) // 5
    if 5000 <= mhz < 5925:
        return (mhz - 5000) // 5
    return None


def channel_to_freq(channel: Optional[int], band: Optional[str] = None) -> Optional[int]:
    """Centre frequency in MHz. 6 GHz channel numbers overlap 2.4/5 GHz, so a band is required for them."""
    if channel is None:
        return None
    band = normalize_band(band) if band else channel_band(channel)
    if band == BAND_24:
        if channel == 14:
            return 2484
        if 1 <= channel <= 13:
            return 2407 + 5 * channel
    elif band == BAND_5:
        if 32 <= channel <= 177:
            return 5000 + 5 * channel
    elif band == BAND_6:
        if channel == 2:
            return 5935
        if 1 <= channel <= 233:
            return 5950 + 5 * channel
    return None


def channel_band(channel: Optional[int]) -> Optional[str]:
    """Best guess from the channel number alone. Returns None when ambiguous (possible 6 GHz)."""
    if channel is None:
        return None
    if 1 <= channel <= 14:
        return BAND_24
    if 32 <= channel <= 177:
        return BAND_5
    return None


def normalize_band(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    t = text.strip().lower().replace(",", ".")
    if t.startswith("2.4") or t.startswith("2,4"):
        return BAND_24
    if t.startswith("5"):
        return BAND_5
    if t.startswith("6"):
        return BAND_6
    return None


def resolve_channel(
    channel: Optional[int], freq_mhz: Optional[int], band: Optional[str]
) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Fill in whichever of channel / frequency / band can be derived from the others."""
    band = normalize_band(band) if band else None
    if freq_mhz is not None:
        band = band or freq_to_band(freq_mhz)
        channel = channel if channel is not None else freq_to_channel(freq_mhz)
    if band is None:
        band = channel_band(channel)
    if freq_mhz is None:
        freq_mhz = channel_to_freq(channel, band)
    return channel, freq_mhz, band
