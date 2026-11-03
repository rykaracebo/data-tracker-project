"""Convert each source's raw JSON into plain Python structures.

Every function here is pure: it takes the parsed JSON a source returned and
gives back what the history build needs. Nothing here touches the network or
the disk, so the same raw file always converts to the same values.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .config import League


def _num(value: Any, digits: int = 4) -> Optional[float]:
    """Round a number to kill float32 noise (38.285713 -> 38.2857); None if not a number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> Optional[int]:
    number = _num(value, 0)
    return None if number is None else int(number)


def id_from_ref(ref: str, segment: str) -> Optional[str]:
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

def convert_futures(data: Dict[str, Any], league: League) -> List[Dict[str, Any]]:
    """ESPN futures board -> one dict per candidate in the league's tracked markets.

    Returns [{award, kind, ref_id, odds}] where kind is 'athlete' (a player or coach
    wins it) or 'team' (a team wins it) and ref_id is that athlete's or team's ESPN id.
    """
    out: List[Dict[str, Any]] = []
    for market in data.get("items", []):
        title = market.get("name") or market.get("displayName") or ""
        award, kind = league.award_for(title)
        if award is None:
            continue
        seen = set()
        for provider in market.get("futures", []):
            for book in provider.get("books", []):
                ref = (book.get("athlete") or book.get("team") or {}).get("$ref", "")
                ref_id = id_from_ref(ref, "athletes" if kind == "athlete" else "teams")
                if ref_id is None or ref_id in seen:
                    continue
                seen.add(ref_id)
                out.append({"award": award, "kind": kind, "ref_id": ref_id,
                            "odds": parse_american_odds(book.get("value"))})
            if seen:
                break  # first provider with prices wins (DraftKings, priority 1)
    return out


# ---------------------------------------------------------------- athletes

def convert_athletes(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """athletes file ({"athletes": {id: record}}) -> {id: {name, team_id}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for key, record in (data.get("athletes") or {}).items():
        name = record.get("fullName") or record.get("displayName")
        if not name:
            continue
        team_ref = (record.get("team") or {}).get("$ref", "")
        out[str(record.get("id", key))] = {"name": name, "team_id": id_from_ref(team_ref, "teams")}
    return out


# ------------------------------------------------------- basketball stats

def convert_stats(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """NBA per-game season stats (bulk feed) -> {athlete_id: {team, gp, ppg, rpg, apg, bpg, spg}}."""
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
            "gp": _int(values.get("gamesPlayed")),
            "ppg": _num(values.get("avgPoints")),
            "rpg": _num(values.get("avgRebounds")),
            "apg": _num(values.get("avgAssists")),
            "bpg": _num(values.get("avgBlocks")),
            "spg": _num(values.get("avgSteals")),
        }
    return out


# --------------------------------------------------------- football stats

def _core_stats(record: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """An ESPN per-athlete statistics record -> {category: {stat name: value}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for cat in ((record.get("splits") or {}).get("categories") or []):
        out[cat.get("name", "")] = {s.get("name"): s.get("value") for s in cat.get("stats", [])}
    return out


def convert_football_stats(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Football per-player season totals ({"athletes": {id: record}}) -> {id: stats}.

    td counts touchdowns passed, rushed or caught (return touchdowns are not included).
    A column is None when the player has no record for it (a lineman has no passing yards).
    """
    out: Dict[str, Dict[str, Any]] = {}
    for athlete_id, record in (data.get("athletes") or {}).items():
        cats = _core_stats(record)
        if not cats:
            continue
        td_parts = [_num(cats.get("passing", {}).get("passingTouchdowns"), 0),
                    _num(cats.get("rushing", {}).get("rushingTouchdowns"), 0),
                    _num(cats.get("receiving", {}).get("receivingTouchdowns"), 0)]
        td_parts = [p for p in td_parts if p is not None]
        out[str(athlete_id)] = {
            "gp": _int(cats.get("general", {}).get("gamesPlayed")),
            "pass_yds": _int(cats.get("passing", {}).get("passingYards")),
            "rush_yds": _int(cats.get("rushing", {}).get("rushingYards")),
            "rec_yds": _int(cats.get("receiving", {}).get("receivingYards")),
            "td": int(sum(td_parts)) if td_parts else None,
            "tackles": _int(cats.get("defensive", {}).get("totalTackles")),
            "sacks": _num(cats.get("defensive", {}).get("sacks"), 1),
            "ints": _int(cats.get("defensiveInterceptions", {}).get("interceptions")),
        }
    return out


# --------------------------------------------------------------- standings

def _entries(node: Dict[str, Any]):
    """Every standings entry under a node, however deeply conferences/divisions nest."""
    for entry in (node.get("standings") or {}).get("entries", []):
        yield entry
    for child in node.get("children", []):
        yield from _entries(child)


def convert_standings(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """ESPN standings -> {team_id: {team, name, win_pct, gp, pts_for, pts_against}}.

    team is the short code (BUF), name the full name. pts_for / pts_against are season totals.
    """
    out: Dict[str, Dict[str, Any]] = {}
    for entry in _entries(data):
        team = entry.get("team") or {}
        team_id = str(team.get("id", ""))
        if not team_id:
            continue
        stats = {s.get("name"): s.get("value") for s in entry.get("stats", [])}
        win_pct = stats.get("winPercent")
        if win_pct is None:
            win_pct = stats.get("leagueWinPercent")
        played = [_num(stats.get(k), 0) for k in ("wins", "losses", "ties")]
        played = [p for p in played if p is not None]
        out[team_id] = {
            "team": team.get("abbreviation") or "",
            "name": team.get("displayName") or team.get("name") or "",
            "win_pct": _num(win_pct),
            "gp": int(sum(played)) if played else None,
            "pts_for": _int(stats.get("pointsFor")),
            "pts_against": _int(stats.get("pointsAgainst")),
        }
    return out


# ------------------------------------------------------------------- teams

def convert_teams(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """teams file ({"teams": {id: record}}) -> {team_id: {team, name}}."""
    out: Dict[str, Dict[str, Any]] = {}
    for key, record in (data.get("teams") or {}).items():
        team_id = str(record.get("id", key))
        out[team_id] = {"team": record.get("abbreviation") or record.get("shortDisplayName") or "",
                        "name": record.get("displayName") or record.get("name") or ""}
    return out


# ----------------------------------------------------------------- coaches

def convert_coaches(data: Dict[str, Any]) -> Dict[str, str]:
    """coaches file ({"teams": {team_id: response}}) -> {coach_id: team_id}."""
    out: Dict[str, str] = {}
    for team_id, response in (data.get("teams") or {}).items():
        for item in (response or {}).get("items", []):
            coach_id = id_from_ref(item.get("$ref", ""), "coaches")
            if coach_id:
                out[coach_id] = str(team_id)
    return out

