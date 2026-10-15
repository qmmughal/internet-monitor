"""Guided signal survey: record signal at named locations and find weak spots.

Walk to a spot, record it with a label ("Kitchen", "Office desk"), repeat,
then read the report. Points are saved as JSON in the config directory.
"""

from __future__ import annotations

import statistics
import time
from typing import Callable, List, Optional

from . import config
from .models import SIMULATED, utc_now
from .signal import quality_label

SURVEY_FILE = "survey.json"
MAX_POINTS = 200
WEAK_DBM = -70
DEAD_DBM = -80


def clean_label(label: str) -> str:
    text = "".join(ch for ch in str(label) if ch.isprintable()).strip()[:64]
    if not text:
        raise ValueError("label must be 1–64 printable characters")
    return text


def load() -> List[dict]:
    data = config.read_json(SURVEY_FILE, [])
    return data if isinstance(data, list) else []


def save(points: List[dict]) -> None:
    config.write_json(SURVEY_FILE, points[-MAX_POINTS:])


def record(label: str, provider, samples: int = 5, interval_s: float = 1.0,
           sleep: Callable[[float], None] = time.sleep, persist: bool = True) -> dict:
    """Take ``samples`` readings at the current location and store their summary."""
    label = clean_label(label)
    samples = max(1, min(int(samples), 30))
    values, modes, ssids, bssids, error = [], set(), set(), set(), None
    for i in range(samples):
        res = provider.connected_interface()
        if res.ok and res.data.signal_dbm and res.data.signal_dbm.value is not None:
            values.append(res.data.signal_dbm.value)
            modes.add(res.data.signal_dbm.mode)
            ssids.add(res.data.ssid)
            bssids.add(res.data.bssid)
        else:
            error = res.error or "signal not reported"
        if i < samples - 1:
            sleep(interval_s)
    if not values:
        return {"ok": False, "label": label, "error": error}
    point = {
        "label": label,
        "timestamp": utc_now(),
        "samples": len(values),
        "median_dbm": round(statistics.median(values)),
        "min_dbm": min(values),
        "max_dbm": max(values),
        "mode": SIMULATED if SIMULATED in modes else ("estimated" if "estimated" in modes else "live"),
        "ssid": next(iter(ssids)) if len(ssids) == 1 else None,
        "bssids": sorted(b for b in bssids if b),
    }
    if persist:
        points = [p for p in load() if p.get("label") != label]  # re-recording a spot replaces it
        points.append(point)
        save(points)
    return {"ok": True, "point": point}


def report(points: Optional[List[dict]] = None) -> dict:
    points = load() if points is None else points
    ordered = sorted(points, key=lambda p: p.get("median_dbm", -999), reverse=True)
    for p in ordered:
        m = p.get("median_dbm")
        p["quality"] = quality_label(m) if m is not None else None
        p["zone"] = "dead" if m is not None and m <= DEAD_DBM else ("weak" if m is not None and m < WEAK_DBM else "ok")
    weak = [p for p in ordered if p["zone"] != "ok"]
    advice = []
    if weak:
        advice.append("Weak spots: " + ", ".join(f"{p['label']} ({p['median_dbm']} dBm)" for p in weak) + ".")
        advice.append("Try moving the router to a more central, elevated spot, or add a mesh node/access point "
                      "between the router and the weak areas.")
    multi_ap = {b for p in ordered for b in p.get("bssids", [])}
    return {
        "points": ordered,
        "weak_spots": [p["label"] for p in weak],
        "access_points_seen": len(multi_ap),
        "thresholds": {"weak_below_dbm": WEAK_DBM, "dead_at_or_below_dbm": DEAD_DBM},
        "simulated": any(p.get("mode") == SIMULATED for p in ordered),
        "advice": advice,
    }


def clear() -> None:
    save([])
