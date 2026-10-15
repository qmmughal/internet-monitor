"""Channel congestion analysis and transparent channel recommendations.

Inputs are access points from a *real* OS scan. The score is a count of
neighbouring access points weighted by their signal strength and spectral
overlap. It is not a measurement of RF interference or airtime, and the
recommendation is a suggestion for your router's settings, never applied.

Assumptions (stated in every result):
* Access points with the same SSID as your connection are treated as yours
  and excluded from the competition score.
* 20 MHz channel widths are assumed when the OS does not report widths.
* Regulatory rules differ by country; 2.4 GHz channels 12–13, 5 GHz DFS
  channels and some 6 GHz channels may not be allowed or supported.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .models import SIMULATED, AccessPoint

CANDIDATES = {
    "2.4 GHz": [1, 6, 11],
    "5 GHz": [36, 40, 44, 48, 149, 153, 157, 161, 165],
    "6 GHz": [5 + 16 * i for i in range(15)],  # preferred scanning channels (PSC)
}
DFS_5GHZ = set(range(52, 145))


def _weight(dbm: Optional[int]) -> float:
    """0 for very weak neighbours (−95 dBm or below), 1 for strong ones (−50 dBm or above)."""
    if dbm is None:
        return 0.3  # seen but strength unknown
    return max(0.0, min(1.0, (dbm + 95) / 45.0))


def _overlap(band: str, a: int, b: int) -> float:
    if band == "2.4 GHz":
        d = abs(a - b)
        return max(0.0, (5 - d) / 5.0) if d < 5 else 0.0
    return 1.0 if a == b else 0.0  # 20 MHz assumption for 5/6 GHz


def analyze(aps: List[AccessPoint], mode: str, own_ssid: Optional[str] = None) -> dict:
    bands: Dict[str, dict] = {}
    for band in CANDIDATES:
        in_band = [ap for ap in aps if ap.band == band and ap.channel is not None]
        neighbours = [ap for ap in in_band if not (own_ssid and ap.ssid == own_ssid)]
        own = [ap for ap in in_band if own_ssid and ap.ssid == own_ssid]

        per_channel: Dict[int, dict] = {}
        for ap in in_band:
            c = per_channel.setdefault(ap.channel, {"channel": ap.channel, "access_points": 0, "strongest_dbm": None,
                                                    "own": 0})
            c["access_points"] += 1
            if own_ssid and ap.ssid == own_ssid:
                c["own"] += 1
            if ap.signal_dbm is not None and (c["strongest_dbm"] is None or ap.signal_dbm > c["strongest_dbm"]):
                c["strongest_dbm"] = ap.signal_dbm

        scores = []
        for cand in CANDIDATES[band]:
            score = 0.0
            contributors = 0
            for ap in neighbours:
                ov = _overlap(band, cand, ap.channel)
                if ov:
                    score += ov * _weight(ap.signal_dbm)
                    contributors += 1
            scores.append({"channel": cand, "score": round(score, 2), "overlapping_networks": contributors,
                           "dfs": band == "5 GHz" and cand in DFS_5GHZ})
        scores.sort(key=lambda s: (s["score"], s["channel"]))

        current = sorted({ap.channel for ap in own})
        maybe_own = possibly_own(neighbours, own)
        entry = {
            "access_points": len(in_band),
            "neighbour_access_points": len(neighbours),
            "channels": sorted(per_channel.values(), key=lambda c: c["channel"]),
            "your_channels": current,
            "possibly_yours": [{"ssid": ap.ssid, "channel": ap.channel, "bssid": ap.bssid} for ap in maybe_own],
            "candidates": scores,
            "recommendation": None,
        }
        if mode == SIMULATED:
            entry["recommendation_withheld"] = "Recommendations are only made from real scans, not demo data."
        elif in_band or own_ssid:
            entry["recommendation"] = _recommend_with_own(band, scores, current, len(neighbours), maybe_own)
        bands[band] = entry

    return {
        "mode": mode,
        "own_ssid_excluded": own_ssid,
        "bands": bands,
        "method": "Score = Σ (spectral overlap × signal weight) of neighbouring access points. "
                  "Lower is better. A count-based estimate, not measured interference.",
        "assumptions": [
            "Access points sharing your SSID are treated as your own and excluded.",
            "20 MHz channel widths assumed where widths are not reported.",
            "Allowed channels depend on your country and router; DFS channels may be unavailable or "
            "vacated when radar is detected.",
            "The scan is a snapshot; neighbours change channels and some may be hidden.",
            "This is a suggestion only. Internet Monitor never changes router settings.",
        ],
    }


def _oui(bssid: Optional[str]) -> Optional[str]:
    """Vendor prefix of a BSSID, or None for locally administered (randomised/virtual) addresses."""
    if not bssid or len(bssid) < 8:
        return None
    try:
        if int(bssid[:2], 16) & 0x02:
            return None
    except ValueError:
        return None
    return bssid[:8].lower()


def possibly_own(neighbours: List[AccessPoint], own: List[AccessPoint]) -> List[AccessPoint]:
    """Neighbours from the same router vendor as your network — often your own extra SSIDs or mesh nodes.

    This is a hint, not proof: an ISP may give neighbours the same router model.
    """
    own_ouis = {o for o in (_oui(ap.bssid) for ap in own) if o}
    return [ap for ap in neighbours if _oui(ap.bssid) in own_ouis]


def _names(aps: List[AccessPoint]) -> str:
    return ", ".join(f"{ap.ssid or '<hidden>'} (ch {ap.channel})" for ap in aps)


def _recommend_with_own(band: str, scores: List[dict], current: List[int], neighbours: int,
                        maybe_own: List[AccessPoint]) -> dict:
    """Never suggest moving onto a channel used by an access point that is probably yours."""
    taken = {ap.channel for ap in maybe_own}
    if not taken:
        return _recommend(band, scores, current, neighbours)
    free = [s for s in scores if s["channel"] not in taken]
    note = (f" {_names(maybe_own)} use the same router brand as your network and are probably your own access "
            "points; their channels are not suggested.")
    if not free or all(s["channel"] in current for s in free):
        layout = sorted(taken | set(current))
        return {"channel": current[0] if current else None, "change_recommended": False,
                "reason": f"Your network and access points that are probably yours already use channels "
                          f"{', '.join(map(str, layout))}" + (" — the standard non-overlapping layout. Keep it."
                                                              if band == "2.4 GHz" and set(layout) >= {1, 6, 11}
                                                              else ". Keep your access points on different channels.")
                          + note, "confidence": "medium"}
    rec = _recommend(band, free, current, neighbours)
    rec["reason"] += note
    return rec


def _recommend(band: str, scores: List[dict], current: List[int], neighbours: int) -> dict:
    best = scores[0]
    cur_score = next((s for s in scores if s["channel"] in current), None)
    if neighbours == 0:
        return {"channel": None, "reason": f"No neighbouring networks seen on {band}; any allowed channel is fine.",
                "confidence": "medium"}
    if cur_score and cur_score["score"] - best["score"] < 0.5:
        return {"channel": cur_score["channel"], "change_recommended": False,
                "reason": f"Your channel {cur_score['channel']} is already among the least crowded "
                          f"(score {cur_score['score']} vs best {best['score']}).",
                "confidence": "medium"}
    reason = (f"Channel {best['channel']} has the lowest weighted neighbour score ({best['score']}) "
              f"with {best['overlapping_networks']} overlapping network(s)")
    if cur_score:
        reason += f"; your current channel {cur_score['channel']} scores {cur_score['score']}"
    if best["dfs"]:
        reason += ". It is a DFS channel: the router must support DFS and may move off it if radar is detected"
    return {"channel": best["channel"], "change_recommended": bool(current), "reason": reason + ".",
            "confidence": "low" if neighbours < 3 else "medium"}
