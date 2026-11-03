"""Small hand-made samples shaped like the real ESPN responses."""
from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tracker.config import LEAGUES  # noqa: E402

NBA, NFL, NCAAF = LEAGUES["nba"], LEAGUES["nfl"], LEAGUES["ncaaf"]

CORE = "http://sports.core.api.espn.com/v2/sports/basketball/leagues/nba/seasons/2027"


def ref(kind, ref_id):
    return {"$ref": f"{CORE}/{kind}/{ref_id}?lang=en&region=us"}


# ------------------------------------------------------------------ futures

def make_futures(markets):
    """An ESPN futures board. markets: [(title, 'athlete'|'team', [(id, 'odds text'), ...])]."""
    items = []
    for n, (title, kind, entries) in enumerate(markets):
        items.append({
            "id": 1000 + n, "name": title, "displayName": title,
            "futures": [{
                "provider": {"id": "100", "name": "DraftKings", "priority": 1},
                "books": [{kind: ref("athletes" if kind == "athlete" else "teams", i), "value": odds}
                          for i, odds in entries],
            }],
        })
    return {"count": len(items), "items": items}


def nba_board(mvp=None, roy=None, dpoy=None, coy=None, team_market=True):
    markets = []
    if team_market:  # NBA has team markets too; they must be ignored
        markets.append(("NBA - Winner", "team", [(9, "+290")]))
    for title, entries in (("NBA - Regular Season MVP", mvp), ("NBA - Rookie of the Year", roy),
                           ("NBA - Defensive Player of the Year", dpoy), ("NBA - Coach of the Year", coy)):
        if entries is not None:
            markets.append((title, "athlete", entries))
    return make_futures(markets)


def nfl_board(mvp=None, opoy=None, dpoy=None, oroy=None, droy=None, superbowl=None):
    markets = []
    for title, entries in (("Regular Season MVP", mvp), ("Offensive Player of the Year", opoy),
                           ("Defensive Player of the Year", dpoy), ("Offensive Rookie of the Year", oroy),
                           ("Defensive Rookie of the Year", droy)):
        if entries is not None:
            markets.append((title, "athlete", entries))
    if superbowl is not None:
        markets.append(("NFL - Super Bowl Winner", "team", superbowl))
    markets.append(("Coach of the Year", "athlete", [(999, "+500")]))  # untracked: must be ignored
    return make_futures(markets)


def ncaaf_board(heisman):
    return make_futures([("NCAA(F) - Heisman Trophy", "athlete", heisman)])


# ----------------------------------------------------------------- athletes

def make_athletes(people):
    """people: {id: name} or {id: (name, team_id)} -> the athletes file layout."""
    out = {}
    for i, value in people.items():
        name, team_id = value if isinstance(value, tuple) else (value, None)
        record = {"id": str(i), "fullName": name, "displayName": name}
        if team_id is not None:
            record["team"] = ref("teams", team_id)
        out[str(i)] = record
    return {"athletes": out}


# -------------------------------------------------------------------- stats

def make_nba_stats(players):
    """players: {id: dict(team, gp, pts, reb, ast, stl, blk)} -> ESPN NBA byathlete layout."""
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


def make_football_stats(players):
    """players: {id: {category: {stat: value}}} -> the football stats file layout."""
    def record(cats):
        return {"splits": {"categories": [
            {"name": name, "stats": [{"name": k, "value": v} for k, v in stats.items()]}
            for name, stats in cats.items()]}}
    return {"athletes": {str(i): record(cats) for i, cats in players.items()}}


QB = {"general": {"gamesPlayed": 8.0}, "passing": {"passingYards": 2400.0, "passingTouchdowns": 20.0},
      "rushing": {"rushingYards": 310.0, "rushingTouchdowns": 4.0}}
LINEBACKER = {"general": {"gamesPlayed": 8.0},
              "defensive": {"totalTackles": 71.0, "sacks": 6.5},
              "defensiveInterceptions": {"interceptions": 2.0}}
RECEIVER = {"general": {"gamesPlayed": 8.0}, "receiving": {"receivingYards": 810.0, "receivingTouchdowns": 6.0},
            "rushing": {"rushingYards": 12.0, "rushingTouchdowns": 0.0}}


# ---------------------------------------------------- standings, teams, coaches

def make_standings(teams):
    """teams: {team_id: (abbr, name, win_pct, wins, losses, pf, pa)} nested under conferences."""
    def entry(tid, v):
        abbr, name, pct, wins, losses, pf, pa = v
        return {"team": {"id": str(tid), "abbreviation": abbr, "displayName": name},
                "stats": [{"name": "winPercent", "value": pct}, {"name": "wins", "value": wins},
                          {"name": "losses", "value": losses}, {"name": "ties", "value": 0},
                          {"name": "pointsFor", "value": pf}, {"name": "pointsAgainst", "value": pa}]}
    entries = [entry(t, v) for t, v in teams.items()]
    # one conference with a division nested inside, like the real NFL feed
    return {"children": [{"name": "East", "children": [{"name": "Atlantic", "standings": {"entries": entries}}]}]}


def make_teams(teams):
    """teams: {team_id: (abbr, name)} -> the teams file layout."""
    return {"teams": {str(t): {"id": str(t), "abbreviation": a, "displayName": n} for t, (a, n) in teams.items()}}


def make_coaches(team_to_coach):
    """team_to_coach: {team_id: coach_id} -> the coaches file layout."""
    return {"teams": {str(t): {"count": 1, "items": [{"$ref": f"{CORE}/coaches/{c}?lang=en"}]}
                      for t, c in team_to_coach.items()}}


# ------------------------------------------------------------ a full raw day

def write_raw(raw_dir: Path, date: str, source: str, payload) -> None:
    folder = raw_dir / date
    folder.mkdir(parents=True, exist_ok=True)
    with gzip.open(folder / f"{source}.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)


def day_payloads(mvp_odds="+200"):
    """A complete, consistent day for all three leagues, keyed by source name."""
    return {
        # NBA: two MVPs (11 has no stats row), a ROY, a DPOY, two coaches
        "nba_futures": nba_board(mvp=[(10, mvp_odds), (11, "-150")], roy=[(20, "+300")],
                                 dpoy=[(30, "+500")], coy=[(40, "+650"), (41, "+900")]),
        "nba_athletes": make_athletes({10: ("Ann Alpha", 1), 11: ("Bo Beta", 2), 20: "Cy Gamma",
                                       30: "Di Delta", 40: "Coach Eps", 41: "Coach Zeta"}),
        "nba_stats": make_nba_stats({
            10: dict(team="LAL", gp=7, pts=38.285713, reb=8.0, ast=9.1, stl=1.5, blk=0.5),
            20: dict(team="UTA", gp=5, pts=18.0, reb=7.0, ast=2.0, stl=1.0, blk=1.0),
            30: dict(team="SAS", gp=6, pts=22.0, reb=11.0, ast=3.0, stl=1.2, blk=3.9)}),
        "nba_standings": make_standings({1: ("ATL", "Atlanta Hawks", 0.5, 3, 3, 600, 590),
                                         2: ("BOS", "Boston Celtics", 0.875, 7, 1, 900, 800)}),
        "nba_coaches": make_coaches({1: 40, 2: 41}),
        # NFL: an MVP quarterback, an OPOY receiver, a DPOY linebacker, a Super Bowl board of 2 teams
        "nfl_futures": nfl_board(mvp=[(50, "+250")], opoy=[(51, "+400")], dpoy=[(52, "+600")],
                                 oroy=[(53, "+900")], droy=[(54, "+700")],
                                 superbowl=[(7, "+450"), (8, "+1200")]),
        "nfl_athletes": make_athletes({50: ("Quinn Back", 7), 51: ("Wes Wide", 8), 52: ("Lee Backer", 7),
                                       53: ("Rook Offense", 8), 54: ("Rook Defense", 7)}),
        "nfl_stats": make_football_stats({50: QB, 51: RECEIVER, 52: LINEBACKER, 54: LINEBACKER}),
        "nfl_standings": make_standings({7: ("BUF", "Buffalo Bills", 0.857, 6, 1, 233, 181),
                                         8: ("MIA", "Miami Dolphins", 0.25, 2, 6, 150, 220)}),
        # College football: a Heisman board of one, with a team record for the team name
        "ncaaf_futures": ncaaf_board([(60, "+300")]),
        "ncaaf_athletes": make_athletes({60: ("Colt College", 2390)}),
        "ncaaf_stats": make_football_stats({60: QB}),
        "ncaaf_teams": make_teams({2390: ("MIA", "Miami Hurricanes")}),
    }


# 6 NBA items + 7 NFL items (5 award players + 2 teams) + 1 Heisman
ITEMS_PER_DAY = 6 + 7 + 1


def full_day(raw_dir: Path, date: str, mvp_odds="+200", skip=()):
    """Write a complete day of raw files, minus the sources named in `skip`."""
    for source, payload in day_payloads(mvp_odds).items():
        if source not in skip:
            write_raw(raw_dir, date, source, payload)


@pytest.fixture
def raw_dir(tmp_path):
    return tmp_path / "raw"
