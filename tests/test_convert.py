"""Each source's raw JSON converts to the values the history needs."""
from __future__ import annotations

import pytest

from conftest import (make_athletes, make_coaches, make_futures, make_standings,
                      make_stats)
from tracker import convert


# ------------------------------------------------------------- odds helpers

@pytest.mark.parametrize("text,expected", [
    ("+200", 200), ("-450", -450), ("+10000", 10000), ("EVEN", 100),
    ("", None), (None, None), ("abc", None), ("+0", None),
])
def test_parse_american_odds(text, expected):
    assert convert.parse_american_odds(text) == expected


@pytest.mark.parametrize("odds,expected", [
    (200, 0.333333), (100, 0.5), (-450, 0.818182), (-100, 0.5), (None, None),
])
def test_implied_probability(odds, expected):
    assert convert.implied_probability(odds) == expected


# ------------------------------------------------------------------ futures

def test_futures_keeps_only_the_four_awards():
    board = make_futures(mvp=[(1, "+200")], roy=[(2, "+300")], dpoy=[(3, "-450")], coy=[(4, "+650")])
    rows = convert.convert_futures(board)
    assert [(r["award"], r["person_id"], r["odds"]) for r in rows] == [
        ("mvp", "1", 200), ("roy", "2", 300), ("dpoy", "3", -450), ("coy", "4", 650),
    ]


def test_futures_ignores_team_markets_and_duplicates():
    board = make_futures(mvp=[(1, "+200"), (1, "+999"), (2, "+400")])
    rows = convert.convert_futures(board)
    assert [(r["person_id"], r["odds"]) for r in rows] == [("1", 200), ("2", 400)]


def test_futures_unparseable_price_keeps_the_candidate_with_no_odds():
    rows = convert.convert_futures(make_futures(mvp=[(1, "n/a")]))
    assert rows == [{"award": "mvp", "person_id": "1", "odds": None}]


def test_futures_empty_board():
    assert convert.convert_futures({"items": []}) == []
    assert convert.convert_futures({}) == []


# ----------------------------------------------------------------- athletes

def test_athletes_map_id_to_full_name():
    names = convert.convert_athletes(make_athletes({10: "Ann Alpha", 11: "Bo Beta"}))
    assert names == {"10": "Ann Alpha", "11": "Bo Beta"}


def test_athletes_fall_back_to_display_name():
    data = {"athletes": {"5": {"id": "5", "displayName": "Only Display"}}}
    assert convert.convert_athletes(data) == {"5": "Only Display"}


# -------------------------------------------------------------------- stats

def test_stats_pick_the_per_game_columns_and_round_float_noise():
    stats = convert.convert_stats(make_stats({
        10: dict(team="LAL", gp=7, pts=38.285713, reb=8.0, ast=9.1, stl=1.5, blk=0.5)}))
    assert stats["10"] == {"team": "LAL", "gp": 7, "ppg": 38.2857, "rpg": 8.0,
                           "apg": 9.1, "bpg": 0.5, "spg": 1.5}


def test_stats_missing_values_become_none():
    data = make_stats({10: dict(team="LAL", gp=0, pts=0, reb=0, ast=0, stl=0, blk=0)})
    data["athletes"][0]["categories"] = [{"name": "general", "values": [0.0]}]  # short rows
    out = convert.convert_stats(data)["10"]
    assert out["gp"] == 0 and out["ppg"] is None and out["bpg"] is None


# ---------------------------------------------------------------- standings

def test_standings_map_team_id_to_code_and_win_pct():
    out = convert.convert_standings(make_standings({9: ("GSW", 0.5714286)}))
    assert out == {"9": {"team": "GSW", "win_pct": 0.5714}}


def test_standings_fall_back_to_league_win_percent():
    data = {"children": [{"standings": {"entries": [
        {"team": {"id": "1", "abbreviation": "ATL"},
         "stats": [{"name": "leagueWinPercent", "value": 0.25}]}]}}]}
    assert convert.convert_standings(data)["1"]["win_pct"] == 0.25


# ------------------------------------------------------------------ coaches

def test_coaches_map_coach_id_to_team_id():
    assert convert.convert_coaches(make_coaches({9: 425, 10: 866})) == {"425": "9", "866": "10"}
