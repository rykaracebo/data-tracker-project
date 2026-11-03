"""Shared settings for the award odds tracker (NBA, NFL and college football)."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
HISTORY_PATH = ROOT / "data" / "history.csv"
STATUS_PATH = ROOT / "data" / "status.json"
RUN_LOG_PATH = ROOT / "data" / "run_log.jsonl"

USER_AGENT = "award-odds-tracker/1.0 (university course project)"

CORE_HOST = "https://sports.core.api.espn.com/v2/sports"
SITE_V2_HOST = "https://site.api.espn.com/apis/v2/sports"
SITE_V3_HOST = "https://site.web.api.espn.com/apis/common/v3/sports"


@dataclass(frozen=True)
class League:
    code: str                 # short code used in item_id and file names
    name: str                 # display name
    sport: str                # ESPN sport path segment
    slug: str                 # ESPN league path segment
    awards: Dict[str, str]    # futures market title -> award code (a person wins it)
    team_awards: Dict[str, str]  # futures market title -> award code (a team wins it)
    labels: Dict[str, str]    # award code -> short display label
    bulk_stats: bool          # True: one stats call lists all players; False: one call per player
    standings: bool           # has a standings source (team names, win %, points)
    coaches: bool             # has a coaches source (NBA Coach of the Year)
    teams: bool               # has a teams source (team names for players, when no standings)
    team_ids: List[int] = field(default_factory=list)  # ids to ask for coaches

    def season_for(self, date: dt.date) -> int:
        """ESPN's season number. NBA names a season by the year it ends (2026-27 is 2027);
        football names it by the year it starts (2026 season is 2026)."""
        if self.sport == "basketball":
            return date.year + 1 if date.month >= 8 else date.year
        return date.year if date.month >= 3 else date.year - 1

    @property
    def core(self) -> str:
        return f"{CORE_HOST}/{self.sport}/leagues/{self.slug}"

    @property
    def site_v2(self) -> str:
        return f"{SITE_V2_HOST}/{self.sport}/{self.slug}"

    @property
    def site_v3(self) -> str:
        return f"{SITE_V3_HOST}/{self.sport}/{self.slug}"

    def award_for(self, title: str):
        """(award code, 'athlete' | 'team') for a futures market title, or (None, None).
        Titles are matched whole, or after a 'NBA - ' style prefix."""
        for table, kind in ((self.awards, "athlete"), (self.team_awards, "team")):
            for label, code in table.items():
                if title == label or title.endswith(" - " + label):
                    return code, kind
        return None, None


LEAGUES: Dict[str, League] = {
    "nba": League(
        code="nba", name="NBA", sport="basketball", slug="nba",
        awards={"Regular Season MVP": "mvp", "Rookie of the Year": "roy",
                "Defensive Player of the Year": "dpoy", "Coach of the Year": "coy"},
        team_awards={},
        labels={"mvp": "NBA MVP", "roy": "NBA ROY", "dpoy": "NBA DPOY", "coy": "NBA COY"},
        bulk_stats=True, standings=True, coaches=True, teams=False,
        team_ids=list(range(1, 31)),  # ESPN team ids 1..30 are the 30 NBA teams
    ),
    "nfl": League(
        code="nfl", name="NFL", sport="football", slug="nfl",
        awards={"Regular Season MVP": "mvp", "Offensive Player of the Year": "opoy",
                "Defensive Player of the Year": "dpoy", "Offensive Rookie of the Year": "oroy",
                "Defensive Rookie of the Year": "droy"},
        team_awards={"Super Bowl Winner": "sbwin"},
        labels={"mvp": "NFL MVP", "opoy": "NFL OPOY", "dpoy": "NFL DPOY", "oroy": "NFL OROY",
                "droy": "NFL DROY", "sbwin": "Super Bowl"},
        bulk_stats=False, standings=True, coaches=False, teams=False,
    ),
    "ncaaf": League(
        code="ncaaf", name="College football", sport="football", slug="college-football",
        awards={"Heisman Trophy": "heisman"},
        team_awards={},
        labels={"heisman": "Heisman"},
        bulk_stats=False, standings=False, coaches=False, teams=True,
    ),
}

# Columns of data/history.csv, in order. The first four are fixed by the course spec.
COLUMNS = [
    "date", "item_id", "item", "source",
    "league", "award", "team", "odds", "implied_prob", "gp",
    "ppg", "rpg", "apg", "bpg", "spg", "win_pct",
    "pass_yds", "rush_yds", "rec_yds", "td", "tackles", "sacks", "ints",
    "pts_for", "pts_against",
]

BASKETBALL_SCORING = ["ppg", "rpg", "apg"]
FOOTBALL_OFFENSE = ["pass_yds", "rush_yds", "rec_yds", "td"]
FOOTBALL_DEFENSE = ["tackles", "sacks", "ints"]

# Which stat columns each (league, award) carries. Everything else stays empty.
AWARD_STATS = {
    ("nba", "mvp"): BASKETBALL_SCORING,
    ("nba", "roy"): BASKETBALL_SCORING,
    ("nba", "dpoy"): ["bpg", "spg"],
    ("nba", "coy"): ["win_pct"],
    ("nfl", "mvp"): FOOTBALL_OFFENSE,
    ("nfl", "opoy"): FOOTBALL_OFFENSE,
    ("nfl", "oroy"): FOOTBALL_OFFENSE,
    ("nfl", "dpoy"): FOOTBALL_DEFENSE,
    ("nfl", "droy"): FOOTBALL_DEFENSE,
    ("nfl", "sbwin"): ["win_pct", "pts_for", "pts_against"],
    ("ncaaf", "heisman"): FOOTBALL_OFFENSE,
}

MOVES_LISTED = 10  # how many items the daily Issue lists


def award_label(league: str, award: str) -> str:
    cfg = LEAGUES.get(league)
    return cfg.labels.get(award, award.upper()) if cfg else award.upper()
