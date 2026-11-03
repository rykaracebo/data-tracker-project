"""Shared settings for the NBA award odds tracker."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
HISTORY_PATH = ROOT / "data" / "history.csv"
STATUS_PATH = ROOT / "data" / "status.json"
RUN_LOG_PATH = ROOT / "data" / "run_log.jsonl"

USER_AGENT = "nba-awards-tracker/1.0 (university course project)"

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"
SITE_V2 = "https://site.api.espn.com/apis/v2/sports/basketball/nba"
SITE_V3 = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"

# ESPN team ids 1..30 are the 30 NBA teams.
NBA_TEAM_IDS = list(range(1, 31))

# Award market name (as ESPN writes it) -> short award code used in item_id.
AWARDS = {
    "Regular Season MVP": "mvp",
    "Rookie of the Year": "roy",
    "Defensive Player of the Year": "dpoy",
    "Coach of the Year": "coy",
}

# Columns of data/history.csv, in order. The first four are fixed by the course spec.
COLUMNS = [
    "date", "item_id", "item", "source",
    "award", "team", "odds", "implied_prob",
    "gp", "ppg", "rpg", "apg", "bpg", "spg", "win_pct",
]

# Which stat columns each award carries.
AWARD_STATS = {
    "mvp": ["ppg", "rpg", "apg"],
    "roy": ["ppg", "rpg", "apg"],
    "dpoy": ["bpg", "spg"],
    "coy": ["win_pct"],
}

MOVES_LISTED = 10  # how many items the daily Issue lists


def season_for(date: dt.date) -> int:
    """ESPN names a season by the year it ends: 2026-27 is season 2027."""
    return date.year + 1 if date.month >= 8 else date.year
