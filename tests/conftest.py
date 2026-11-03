"""Small hand-made samples shaped like the real ESPN responses."""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORE = "http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027"


def athlete_ref(person_id):
    return {"$ref": f"{CORE}/athletes/{person_id}?lang=en&region=us"}


def make_futures(mvp=None, roy=None, dpoy=None, coy=None, extra_market=True):
    """An ESPN futures board. Each award is a list of (person_id, 'odds text')."""
    def market(market_id, name, entries):
        return {
            "id": market_id, "name": name, "displayName": name,
            "futures": [{
                "provider": {"id": "100", "name": "DraftKings", "priority": 1},
                "books": [{"athlete": athlete_ref(pid), "value": odds} for pid, odds in entries],
            }],
        }
    items = []
    if extra_market:
        items.append({"id": 2564, "name": "NBA - Winner", "futures": [
            {"provider": {"id": "100"}, "books": [{"team": {"$ref": f"{CORE}/teams/9"}, "value": "+290"}]}]})
    for market_id, name, entries in (
        (2581, "NBA - Regular Season MVP", mvp),
        (2582, "NBA - Rookie of the Year", roy),
        (2583, "NBA - Defensive Player of the Year", dpoy),
        (2586, "NBA - Coach of the Year", coy),
    ):
        if entries is not None:
            items.append(market(market_id, name, entries))
    return {"count": len(items), "items": items}


def make_athletes(people):
    """people: {id: name} -> the athletes.json.gz layout."""
    return {"athletes": {str(i): {"id": str(i), "fullName": n, "displayName": n}
                         for i, n in people.items()}}


def make_stats(players):
    """players: {id: dict(team, gp, pts, reb, ast, stl, blk)} -> ESPN byathlete layout."""
    categories = [
        {"name": "general", "names": ["gamesPlayed", "avgMinutes", "avgRebounds"]},
        {"name": "offensive", "names": ["avgPoints", "avgAssists"]},
        {"name": "defensive", "names": ["avgSteals", "avgBlocks"]},
    ]
    athletes = []
    for pid, p in players.items():
        athletes.append({
            "athlete": {"id": str(pid), "teamShortName": p["team"]},
            "categories": [
                {"name": "general", "values": [p["gp"], 30.0, p["reb"]]},
                {"name": "offensive", "values": [p["pts"], p["ast"]]},
                {"name": "defensive", "values": [p["stl"], p["blk"]]},
            ],
        })
    return {"pagination": {"count": len(athletes), "pages": 1}, "categories": categories,
            "athletes": athletes}


def make_standings(teams):
    """teams: {team_id: (abbr, win_pct)}."""
    entries = [{"team": {"id": str(tid), "abbreviation": abbr, "displayName": abbr},
                "stats": [{"name": "winPercent", "value": pct}, {"name": "wins", "value": 3}]}
               for tid, (abbr, pct) in teams.items()]
    return {"children": [{"name": "East", "standings": {"entries": entries}}]}


def make_coaches(team_to_coach):
    """team_to_coach: {team_id: coach_id} -> the coaches.json.gz layout."""
    return {"teams": {str(t): {"count": 1, "items": [{"$ref": f"{CORE}/coaches/{c}?lang=en"}]}
                      for t, c in team_to_coach.items()}}


def write_raw(raw_dir: Path, date: str, source: str, payload) -> None:
    folder = raw_dir / date
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"{source}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def full_day(raw_dir: Path, date: str, mvp_odds="+200", skip=()):
    """Write a complete, consistent day of raw files (two MVPs, a ROY, a DPOY, two coaches)."""
    payloads = {
        "futures": make_futures(
            mvp=[(10, mvp_odds), (11, "-150")], roy=[(20, "+300")],
            dpoy=[(30, "+500")], coy=[(40, "+650"), (41, "+900")]),
        "athletes": make_athletes({10: "Ann Alpha", 11: "Bo Beta", 20: "Cy Gamma",
                                   30: "Di Delta", 40: "Coach Eps", 41: "Coach Zeta"}),
        "stats": make_stats({
            10: dict(team="LAL", gp=7, pts=38.285713, reb=8.0, ast=9.1, stl=1.5, blk=0.5),
            20: dict(team="UTA", gp=5, pts=18.0, reb=7.0, ast=2.0, stl=1.0, blk=1.0),
            30: dict(team="SAS", gp=6, pts=22.0, reb=11.0, ast=3.0, stl=1.2, blk=3.9),
        }),
        "standings": make_standings({1: ("ATL", 0.5), 2: ("BOS", 0.875)}),
        "coaches": make_coaches({1: 40, 2: 41}),
    }
    for source, payload in payloads.items():
        if source not in skip:
            write_raw(raw_dir, date, source, payload)


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path / "raw"
