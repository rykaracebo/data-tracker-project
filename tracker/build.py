"""Build data/history.csv from the raw files in data/raw/.

    python -m tracker.build

The history depends on the raw files alone: nothing else is read. Run it twice
and you get the same bytes; change a rule in tracker/convert.py or here and the
change applies to every day of the history.
"""
from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import convert
from .config import AWARD_STATS, COLUMNS, HISTORY_PATH, LEAGUES, RAW_DIR, League

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KINDS = ("futures", "athletes", "stats", "standings", "teams", "records", "coaches")


def source_name(league: str, kind: str) -> str:
    """Raw file / source name, e.g. nba_futures."""
    return f"{league}_{kind}"


def source_names() -> List[str]:
    """Every source the pipeline calls, in run order."""
    names = []
    for code, cfg in LEAGUES.items():
        names += [source_name(code, "futures"), source_name(code, "athletes"), source_name(code, "stats")]
        if cfg.standings:
            names.append(source_name(code, "standings"))
        if cfg.teams:
            names.append(source_name(code, "teams"))
        if cfg.records:
            names.append(source_name(code, "records"))
        if cfg.coaches:
            names.append(source_name(code, "coaches"))
    return names


# ----------------------------------------------------------------- raw files

def raw_dates(raw_dir: Path = RAW_DIR) -> List[str]:
    """Dates that have at least one raw file, oldest first."""
    if not raw_dir.exists():
        return []
    dates = []
    for child in raw_dir.iterdir():
        if child.is_dir() and DATE_RE.match(child.name) and any(child.glob("*.gz")):
            dates.append(child.name)
    return sorted(dates)


def read_raw(raw_dir: Path, date: str, source: str) -> Optional[Dict[str, Any]]:
    """Parsed JSON of one source on one day, or None if there is no (readable) file."""
    path = raw_dir / date / f"{source}.json.gz"
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, EOFError):
        print(f"warning: could not read {path}", file=sys.stderr)
        return None


# ----------------------------------------------------------------- one day

class Names:
    """Running id -> name maps per league, so a day whose athletes file failed still gets
    names from earlier days (and, failing that, the id itself)."""

    def __init__(self) -> None:
        self.people: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def update(self, league: str, found: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        known = self.people.setdefault(league, {})
        known.update(found)
        return known


def build_league_day(cfg: League, date: str, raw: Dict[str, Optional[Dict[str, Any]]],
                     names: Names) -> List[Dict[str, Any]]:
    """One league's raw sources on one day -> one row per candidate on its futures board.

    `raw` maps kind ('futures', 'athletes', ...) to the parsed file or None.
    """
    if raw.get("futures") is None:
        return []  # no futures file, no rows: the futures board is what makes the items

    people = names.update(cfg.code, convert.convert_athletes(raw["athletes"]) if raw.get("athletes") else {})
    if cfg.bulk_stats:
        stats = convert.convert_stats(raw["stats"]) if raw.get("stats") else {}
    else:
        stats = convert.convert_football_stats(raw["stats"]) if raw.get("stats") else {}
    standings = convert.convert_standings(raw["standings"]) if raw.get("standings") else {}
    teams = dict(standings)
    if raw.get("teams"):
        teams.update(convert.convert_teams(raw["teams"]))
    records = convert.convert_records(raw["records"]) if raw.get("records") else {}
    coach_team = convert.convert_coaches(raw["coaches"]) if raw.get("coaches") else {}

    rows = []
    for entry in convert.convert_futures(raw["futures"], cfg):
        award, ref_id = entry["award"], entry["ref_id"]
        row: Dict[str, Any] = {c: "" for c in COLUMNS}
        row.update({
            "date": date,
            "item_id": f"{cfg.code}-{award}-{ref_id}",
            "item": ref_id,
            "source": source_name(cfg.code, "futures"),
            "league": cfg.code,
            "award": award,
            "odds": entry["odds"],
            "implied_prob": convert.implied_probability(entry["odds"]),
        })
        wanted = AWARD_STATS.get((cfg.code, award), [])
        if entry["kind"] == "team":
            team = teams.get(ref_id, {})
            record = records.get(ref_id) or standings.get(ref_id, {})   # overall record wins
            row["item"] = team.get("name") or ref_id
            row["team"] = team.get("team", "")
            row["gp"] = record.get("gp")
            for column in wanted:
                row[column] = record.get(column)
        elif cfg.coaches and award == "coy":
            person = people.get(ref_id, {})
            row["item"] = person.get("name", ref_id)
            team = standings.get(coach_team.get(ref_id, ""), {})
            row["team"] = team.get("team", "")
            for column in wanted:
                row[column] = team.get(column)
        else:
            person = people.get(ref_id, {})
            row["item"] = person.get("name", ref_id)
            player = stats.get(ref_id, {})
            row["team"] = player.get("team") or teams.get(person.get("team_id") or "", {}).get("team", "")
            row["gp"] = player.get("gp")
            for column in wanted:
                row[column] = player.get(column)
        rows.append(row)
    return rows


def build_day(date: str, raw: Dict[str, Optional[Dict[str, Any]]], names: Names) -> List[Dict[str, Any]]:
    """All leagues' rows for one day. `raw` is keyed by source name (nba_futures, ...)."""
    rows: List[Dict[str, Any]] = []
    for code, cfg in LEAGUES.items():
        league_raw = {kind: raw.get(source_name(code, kind)) for kind in KINDS}
        rows.extend(build_league_day(cfg, date, league_raw, names))
    return rows


# ------------------------------------------------------------------ history

def build_rows(raw_dir: Path = RAW_DIR) -> List[Dict[str, Any]]:
    """Every day's rows, sorted by date then item_id."""
    names = Names()
    rows: List[Dict[str, Any]] = []
    for date in raw_dates(raw_dir):
        raw = {source: read_raw(raw_dir, date, source) for source in source_names()}
        rows.extend(build_day(date, raw, names))
    rows.sort(key=lambda r: (r["date"], r["item_id"]))
    return rows


def _cell(value: Any) -> str:
    """CSV text for a value; a value the source did not report is left empty."""
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def write_history(rows: List[Dict[str, Any]], path: Path = HISTORY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in rows:
            writer.writerow([_cell(row.get(c)) for c in COLUMNS])


def read_history(path: Path = HISTORY_PATH) -> List[Dict[str, str]]:
    """The history file as a list of dicts of strings (empty list if it does not exist)."""
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def build_history(raw_dir: Path = RAW_DIR, path: Path = HISTORY_PATH) -> List[Dict[str, Any]]:
    rows = build_rows(raw_dir)
    write_history(rows, path)
    return rows


if __name__ == "__main__":
    built = build_history()
    days = len({r["date"] for r in built})
    print(f"wrote {HISTORY_PATH}: {len(built)} rows over {days} day(s)")
