"""Each source's raw JSON converts to the values the history needs."""
from __future__ import annotations

import pytest

from conftest import (LINEBACKER, NBA, NCAAF, NFL, QB, RECEIVER, make_athletes, make_coaches,
                      make_football_stats, make_futures, make_nba_stats, make_records, make_standings,
                      make_teams, nba_board, nfl_board, ncaaf_board)
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


# ------------------------------------------------------------ futures: NBA

def test_nba_futures_keeps_only_the_four_awards():
    board = nba_board(mvp=[(1, "+200")], roy=[(2, "+300")], dpoy=[(3, "-450")], coy=[(4, "+650")])
    rows = convert.convert_futures(board, NBA)
    assert [(r["award"], r["kind"], r["ref_id"], r["odds"]) for r in rows] == [
        ("mvp", "athlete", "1", 200), ("roy", "athlete", "2", 300),
        ("dpoy", "athlete", "3", -450), ("coy", "athlete", "4", 650)]


def test_futures_ignores_other_markets_and_duplicates():
    board = nba_board(mvp=[(1, "+200"), (1, "+999"), (2, "+400")])
    rows = convert.convert_futures(board, NBA)   # the conference-winner team market is skipped
    assert [(r["ref_id"], r["odds"]) for r in rows] == [("1", 200), ("2", 400)]


def test_futures_unparseable_price_keeps_the_candidate_with_no_odds():
    rows = convert.convert_futures(nba_board(mvp=[(1, "n/a")]), NBA)
    assert rows == [{"award": "mvp", "kind": "athlete", "ref_id": "1", "odds": None}]


def test_futures_empty_board():
    assert convert.convert_futures({"items": []}, NBA) == []
    assert convert.convert_futures({}, NBA) == []


# ------------------------------------------------------------ futures: NFL

def test_nfl_futures_has_five_player_awards_and_the_super_bowl():
    board = nfl_board(mvp=[(1, "+200")], opoy=[(2, "+300")], dpoy=[(3, "+400")], oroy=[(4, "+500")],
                      droy=[(5, "+600")], superbowl=[(7, "+450"), (8, "+1200")])
    rows = convert.convert_futures(board, NFL)
    assert [(r["award"], r["kind"], r["ref_id"]) for r in rows] == [
        ("mvp", "athlete", "1"), ("opoy", "athlete", "2"), ("dpoy", "athlete", "3"),
        ("oroy", "athlete", "4"), ("droy", "athlete", "5"),
        ("sbwin", "team", "7"), ("sbwin", "team", "8")]   # the NFL Coach of the Year market is not tracked


def test_nfl_offensive_and_defensive_awards_are_not_mixed_up():
    """'Offensive Rookie of the Year' must not match 'Rookie of the Year' style lookups."""
    board = nfl_board(oroy=[(4, "+500")], droy=[(5, "+600")])
    assert [r["award"] for r in convert.convert_futures(board, NFL)] == ["oroy", "droy"]
    nba_view = convert.convert_futures(board, NBA)      # NBA tracks neither of these markets
    assert [r for r in nba_view if r["award"] in ("oroy", "droy")] == []


def test_college_futures_heisman_and_playoff_champion():
    rows = convert.convert_futures(ncaaf_board([(9, "+150")], cfp=[(61, "+350"), (87, "+550")]), NCAAF)
    assert rows == [{"award": "heisman", "kind": "athlete", "ref_id": "9", "odds": 150},
                    {"award": "cfp", "kind": "team", "ref_id": "61", "odds": 350},
                    {"award": "cfp", "kind": "team", "ref_id": "87", "odds": 550}]  # Big Ten market skipped


def test_nba_finals_is_the_plain_winner_market_not_conference_or_division_winners():
    board = nba_board(finals=[(1, "+300"), (2, "+500")])     # also has an Eastern Conference Winner market
    rows = convert.convert_futures(board, NBA)
    assert [(r["award"], r["kind"], r["ref_id"], r["odds"]) for r in rows] == [
        ("finals", "team", "1", 300), ("finals", "team", "2", 500)]


# ----------------------------------------------------------------- athletes

def test_athletes_map_id_to_name_and_team():
    out = convert.convert_athletes(make_athletes({10: ("Ann Alpha", 13), 11: "Bo Beta"}))
    assert out == {"10": {"name": "Ann Alpha", "team_id": "13"}, "11": {"name": "Bo Beta", "team_id": None}}


def test_athletes_fall_back_to_display_name():
    data = {"athletes": {"5": {"id": "5", "displayName": "Only Display"}}}
    assert convert.convert_athletes(data) == {"5": {"name": "Only Display", "team_id": None}}


def test_athletes_without_any_name_are_dropped():
    assert convert.convert_athletes({"athletes": {"5": {"id": "5"}}}) == {}


# ---------------------------------------------------------- NBA player stats

def test_nba_stats_pick_the_per_game_columns_and_round_float_noise():
    stats = convert.convert_stats(make_nba_stats({
        10: dict(team="LAL", gp=7, pts=38.285713, reb=8.0, ast=9.1, stl=1.5, blk=0.5)}))
    assert stats["10"] == {"team": "LAL", "gp": 7, "ppg": 38.2857, "rpg": 8.0,
                           "apg": 9.1, "bpg": 0.5, "spg": 1.5}


def test_nba_stats_missing_values_become_none():
    data = make_nba_stats({10: dict(team="LAL", gp=0, pts=0, reb=0, ast=0, stl=0, blk=0)})
    data["athletes"][0]["categories"] = [{"name": "general", "values": [0.0]}]  # short rows
    out = convert.convert_stats(data)["10"]
    assert out["gp"] == 0 and out["ppg"] is None and out["bpg"] is None


# ------------------------------------------------------ football player stats

def test_football_stats_for_a_quarterback():
    out = convert.convert_football_stats(make_football_stats({50: QB}))["50"]
    assert out["gp"] == 8 and out["pass_yds"] == 2400 and out["rush_yds"] == 310
    assert out["td"] == 24                      # 20 passing + 4 rushing, no receiving record
    assert out["rec_yds"] is None and out["tackles"] is None


def test_football_stats_for_a_receiver_and_a_linebacker():
    stats = convert.convert_football_stats(make_football_stats({51: RECEIVER, 52: LINEBACKER}))
    assert stats["51"]["rec_yds"] == 810 and stats["51"]["td"] == 6 and stats["51"]["pass_yds"] is None
    assert stats["52"]["tackles"] == 71 and stats["52"]["sacks"] == 6.5 and stats["52"]["ints"] == 2
    assert stats["52"]["td"] is None            # no offensive record at all


def test_football_player_with_no_stats_record_is_left_out():
    assert convert.convert_football_stats(make_football_stats({50: {}})) == {}
    assert convert.convert_football_stats({}) == {}


# ---------------------------------------------------------------- standings

def test_standings_map_team_id_to_names_record_and_points():
    out = convert.convert_standings(make_standings({9: ("GSW", "Golden State Warriors", 0.5714286, 4, 3, 788, 902)}))
    assert out == {"9": {"team": "GSW", "name": "Golden State Warriors", "win_pct": 0.5714, "gp": 7,
                         "pts_for": 788, "pts_against": 902}}


def test_standings_find_entries_nested_under_conferences_and_divisions():
    out = convert.convert_standings(make_standings({1: ("A", "Team A", 0.5, 1, 1, 10, 10),
                                                    2: ("B", "Team B", 0.5, 1, 1, 10, 10)}))
    assert set(out) == {"1", "2"}


def test_standings_fall_back_to_league_win_percent():
    data = {"children": [{"standings": {"entries": [
        {"team": {"id": "1", "abbreviation": "ATL", "displayName": "Atlanta"},
         "stats": [{"name": "leagueWinPercent", "value": 0.25}]}]}}]}
    assert convert.convert_standings(data)["1"]["win_pct"] == 0.25


# ------------------------------------------------------------------- records

def test_records_use_the_overall_record_only():
    out = convert.convert_records(make_records({61: (0.875, 8, 328, 119)}))
    assert out == {"61": {"win_pct": 0.875, "gp": 8, "pts_for": 328, "pts_against": 119}}  # not the home record


def test_records_without_an_overall_item_are_skipped():
    assert convert.convert_records({"teams": {"61": {"items": [{"name": "Home", "stats": []}]}}}) == {}
    assert convert.convert_records({}) == {}


# --------------------------------------------------------------------- teams

def test_teams_map_id_to_code_and_name():
    out = convert.convert_teams(make_teams({2390: ("MIA", "Miami Hurricanes")}))
    assert out == {"2390": {"team": "MIA", "name": "Miami Hurricanes"}}


# ------------------------------------------------------------------ coaches

def test_coaches_map_coach_id_to_team_id():
    assert convert.convert_coaches(make_coaches({9: 425, 10: 866})) == {"425": "9", "866": "10"}


# ------------------------------------------------------------------- seasons

def test_season_numbers():
    import datetime as dt
    assert NBA.season_for(dt.date(2026, 11, 3)) == 2027      # 2026-27 NBA season
    assert NBA.season_for(dt.date(2027, 3, 1)) == 2027
    assert NBA.season_for(dt.date(2027, 8, 1)) == 2028
    assert NFL.season_for(dt.date(2026, 11, 3)) == 2026      # 2026 NFL season
    assert NFL.season_for(dt.date(2027, 2, 1)) == 2026       # the playoffs are still the 2026 season
    assert NCAAF.season_for(dt.date(2026, 11, 3)) == 2026


# ------------------------------------------------------------ the top-10 rule

def long_board(n=15):
    """An NBA MVP market with n candidates, listed longest price first (ids 1..n, +1000 down to +100*...)."""
    return nba_board(mvp=[(i, f"+{i * 100}") for i in range(n, 0, -1)])


def test_only_the_shortest_prices_in_each_market_are_kept():
    rows = convert.convert_futures(long_board(15), NBA)
    assert len(rows) == 10
    assert [r["ref_id"] for r in rows] == [str(i) for i in range(1, 11)]   # +100 ... +1000, shortest first
    assert all(r["odds"] <= 1000 for r in rows)


def test_top_n_is_per_market_not_overall():
    board = nba_board(mvp=[(i, f"+{i * 100}") for i in range(1, 16)],
                      roy=[(100 + i, f"+{i * 100}") for i in range(1, 13)], coy=[(200, "+500")])
    rows = convert.convert_futures(board, NBA)
    counts = {a: sum(1 for r in rows if r["award"] == a) for a in ("mvp", "roy", "coy")}
    assert counts == {"mvp": 10, "roy": 10, "coy": 1}      # a small market keeps everyone


def test_minus_odds_are_the_shortest_prices():
    board = nba_board(mvp=[(1, "+500"), (2, "-450"), (3, "+100"), (4, "-120")])
    rows = convert.convert_futures(board, NBA, top_n=2)
    assert [r["ref_id"] for r in rows] == ["2", "4"]       # -450 (81.8%) then -120 (54.5%)


def test_ties_and_missing_prices_are_ranked_the_same_way_every_time():
    board = nba_board(mvp=[(9, "+200"), (3, "+200"), (5, "n/a"), (7, "+200"), (1, "+300")])
    rows = convert.convert_futures(board, NBA, top_n=4)
    assert [r["ref_id"] for r in rows] == ["3", "7", "9", "1"]   # ties by id; the unpriced one is last, so cut
    again = convert.convert_futures(board, NBA, top_n=4)
    assert rows == again


def test_top_n_none_keeps_everyone():
    assert len(convert.convert_futures(long_board(15), NBA, top_n=None)) == 15


def test_trim_futures_keeps_the_shape_but_only_tracked_markets_and_top_prices():
    board = nba_board(mvp=[(i, f"+{i * 100}") for i in range(1, 16)], roy=[(50, "+300")])
    trimmed = convert.trim_futures(board, NBA)
    titles = [m["name"] for m in trimmed["items"]]
    assert titles == ["NBA - Regular Season MVP", "NBA - Rookie of the Year"]   # the conference market is dropped
    books = trimmed["items"][0]["futures"][0]["books"]
    assert len(books) == 10 and trimmed["count"] == 2
    assert trimmed["items"][0]["futures"][0]["provider"]["name"] == "DraftKings"
    assert all("$ref" in b["athlete"] and "value" in b for b in books)           # the original book entries
    # reading the trimmed board gives exactly what reading the full one gave
    assert convert.convert_futures(trimmed, NBA) == convert.convert_futures(board, NBA)


def test_trimming_twice_changes_nothing():
    once = convert.trim_futures(long_board(25), NBA)
    assert convert.trim_futures(once, NBA) == once
