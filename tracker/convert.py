"""Convert each source's raw JSON into plain Python structures.

Every function here is pure: it takes the parsed JSON a source returned and
gives back what the history build needs. Nothing here touches the network or
the disk, so the same raw file always converts to the same values.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import AWARDS


def _num(value: Any, digits: int = 4) -> Optional[float]:
    """Round a number to kill float32 noise (38.285713 -> 38.2857); None if not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _id_from_ref(ref: str, segment: str) -> Optional[str]:
    """Pull the id out of an ESPN $ref link, e.g. .../athletes/3945274?lang=en -> 3945274."""
    match = re.search(r"/%s/(\d+)" % re.escape(segment), ref or "")
    return match.group(1) if match else None


# ---------------------------------------------------------------- odds math

def parse_american_odds(text: Any) -> Optional[int]:
    """'+200' -> 200, '-450' -> -450, 'EVEN' -> 100. Anything else -> None."""
    if text is None:
        return None
    s = str(text).strip().upper()
    if s in ("EVEN", "EV", "PK"):
        return 100
    if re.fullmatch(r"[+-]\d+", s):
        value = int(s)
        return value if value != 0 else None
    return None


def implied_probability(odds: Optional[int]) -> Optional[float]:
    """Probability (0..1) that American odds imply, before removing the book's margin."""
    if odds is None or odds == 0:
        return None
    if odds > 0:
        return round(100.0 / (odds + 100.0), 6)
    return round(-odds / (-odds + 100.0), 6)


# ------------------------------------------------------------------ futures

def convert_futures(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """ESPN futures board -> one dict per award candidate.

    Returns [{award, person_id, odds}] for the four tracked awards. A market is
    matched by the award name in its title, so a changed market id does not matter.
    """
    out: List[Dict[str, Any]] = []
    for market in data.get("items", []):
        title = market.get("name") or market.get("displayName") or ""
        award = next((code for label, code in AWARDS.items() if label in title), None)
        if award is None:
            continue
        seen = set()
        for provider in market.get("futures", []):
            for book in provider.get("books", []):
                ref = (book.get("athlete") or {}).get("$ref", "")
                person_id = _id_from_ref(ref, "athletes")
                if person_id is None or person_id in seen:
                    continue
                seen.add(person_id)
                out.append({
                    "award": award,
                    "person_id": person_id,
                    "odds": parse_american_odds(book.get("value")),
                })
            if seen:
                break  # first provider with prices wins (DraftKings, priority 1)
    return out


# ---------------------------------------------------------------- athletes

def convert_athletes(data: Dict[str, Any]) -> Dict[str, str]:
    """athletes.json.gz ({"athletes": {id: record}}) -> {id: full name}."""
    names: Dict[str, str] = {}
    for key, record in (data.get("athletes") or {}).items():
        name = record.get("fullName") or record.get("displayName")
        if name:
            names[str(record.get("id", key))] = name
    return names


# ------------------------------------------------------------------- stats

def convert_stats(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """ESPN per-player season stats -> {athlete_id: {team, gp, ppg, rpg, apg, bpg, spg}}."""
    layout = {cat["name"]: cat.get("names", []) for cat in data.get("categories", [])}
    out: Dict[str, Dict[str, Any]] = {}
    for entry in data.get("athletes", []):
        athlete = entry.get("athlete") or {}
        athlete_id = str(athlete.get("id", ""))
        if not athlete_id:
            continue
        values: Dict[str, Any] = {}
        for cat in entry.get("categories", []):
            names = layout.get(cat.get("name"), [])
            for stat_name, value in zip(names, cat.get("values", [])):
                values[stat_name] = value
        out[athlete_id] = {
            "team": athlete.get("teamShortName") or "",
            "gp": _num(values.get("gamesPlayed"), 0),
            "ppg": _num(values.get("avgPoints")),
            "rpg": _num(values.get("avgRebounds")),
            "apg": _num(values.get("avgAssists")),
            "bpg": _num(values.get("avgBlocks")),
            "spg": _num(values.get("avgSteals")),
        }
        if out[athlete_id]["gp"] is not None:
            out[athlete_id]["gp"] = int(out[athlete_id]["gp"])
    return out


# --------------------------------------------------------------- standings

def convert_standings(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """ESPN standings -> {team_id: {team, win_pct}} (team is the 3-letter code)."""
    out: Dict[str, Dict[str, Any]] = {}
    for conference in data.get("children", []):
        for entry in (conference.get("standings") or {}).get("entries", []):
            team = entry.get("team") or {}
            team_id = str(team.get("id", ""))
            if not team_id:
                continue
            stats = {s.get("name"): s.get("value") for s in entry.get("stats", [])}
            win_pct = stats.get("winPercent")
            if win_pct is None:
                win_pct = stats.get("leagueWinPercent")
            out[team_id] = {
                "team": team.get("abbreviation") or "",
                "win_pct": _num(win_pct),
            }
    return out


# ----------------------------------------------------------------- coaches

def convert_coaches(data: Dict[str, Any]) -> Dict[str, str]:
    """coaches.json.gz ({"teams": {team_id: response}}) -> {coach_id: team_id}."""
    out: Dict[str, str] = {}
    for team_id, response in (data.get("teams") or {}).items():
        for item in (response or {}).get("items", []):
            coach_id = _id_from_ref(item.get("$ref", ""), "coaches")
            if coach_id:
                out[coach_id] = str(team_id)
    return out
