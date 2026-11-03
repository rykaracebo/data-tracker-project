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
from .config import AWARD_STATS, COLUMNS, HISTORY_PATH, RAW_DIR

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SOURCES = ("futures", "athletes", "stats", "standings", "coaches")


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

def build_day(date: str, raw: Dict[str, Optional[Dict[str, Any]]],
              names: Dict[str, str]) -> List[Dict[str, Any]]:
    """One day's raw sources -> one row per award candidate.

    `names` is a running id -> name map. It is updated with today's athletes and
    used as a fallback, so a day whose athletes file failed still gets names
    from earlier days (and, failing that, the id itself).
    """
    if raw.get("futures") is None:
        return []  # no futures file, no rows: the futures board is what makes the items

    names.update(convert.convert_athletes(raw["athletes"]) if raw.get("athletes") else {})
    stats = convert.convert_stats(raw["stats"]) if raw.get("stats") else {}
    standings = convert.convert_standings(raw["standings"]) if raw.get("standings") else {}
    coach_team = convert.convert_coaches(raw["coaches"]) if raw.get("coaches") else {}

    rows = []
    for entry in convert.convert_futures(raw["futures"]):
        award, person = entry["award"], entry["person_id"]
        row: Dict[str, Any] = {c: "" for c in COLUMNS}
        row.update({
            "date": date,
            "item_id": f"{award}-{person}",
            "item": names.get(person, person),
            "source": "futures",
            "award": award,
            "odds": entry["odds"],
            "implied_prob": convert.implied_probability(entry["odds"]),
        })
        if award == "coy":
            team = standings.get(coach_team.get(person, ""), {})
            row["team"] = team.get("team", "")
            row["win_pct"] = team.get("win_pct")
        else:
            player = stats.get(person, {})
            row["team"] = player.get("team", "")
            row["gp"] = player.get("gp")
            for column in AWARD_STATS[award]:
                row[column] = player.get(column)
        rows.append(row)
    return rows


# ------------------------------------------------------------------ history

def build_rows(raw_dir: Path = RAW_DIR) -> List[Dict[str, Any]]:
    """Every day's rows, sorted by date then item_id."""
    names: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []
    for date in raw_dates(raw_dir):
        raw = {source: read_raw(raw_dir, date, source) for source in SOURCES}
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
