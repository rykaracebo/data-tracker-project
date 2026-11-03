"""History logic: one row per item per day, built from the raw files alone."""
from __future__ import annotations

import csv

from conftest import ITEMS_PER_DAY, full_day, make_athletes, write_raw, nba_board
from tracker import build
from tracker.config import COLUMNS


def history_rows(raw_dir, tmp_path):
    path = tmp_path / "history.csv"
    build.build_history(raw_dir, path)
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle)), path.read_bytes()


def by_id(rows, date=None):
    return {r["item_id"]: r for r in rows if date is None or r["date"] == date}


def test_one_row_per_item_per_day_with_the_fixed_first_columns(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows, _ = history_rows(raw_dir, tmp_path)
    assert list(rows[0].keys())[:4] == ["date", "item_id", "item", "source"]
    assert list(rows[0].keys()) == COLUMNS
    assert len(rows) == ITEMS_PER_DAY
    assert len({r["item_id"] for r in rows}) == ITEMS_PER_DAY
    assert {r["source"] for r in rows} == {"nba_futures", "nfl_futures", "ncaaf_futures"}
    assert {r["league"] for r in rows} == {"nba", "nfl", "ncaaf"}


def test_item_ids_carry_league_award_and_the_espn_id(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows, _ = history_rows(raw_dir, tmp_path)
    assert {"nba-mvp-10", "nba-coy-40", "nfl-opoy-51", "nfl-sbwin-7", "ncaaf-heisman-60"} <= set(by_id(rows))


def test_nba_rows_carry_the_stats_that_belong_to_each_award(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    mvp = rows["nba-mvp-10"]
    assert (mvp["item"], mvp["team"], mvp["odds"], mvp["ppg"], mvp["rpg"], mvp["apg"]) == \
        ("Ann Alpha", "LAL", "200", "38.2857", "8.0", "9.1")
    assert mvp["bpg"] == mvp["spg"] == mvp["win_pct"] == mvp["pass_yds"] == ""
    dpoy = rows["nba-dpoy-30"]
    assert (dpoy["bpg"], dpoy["spg"], dpoy["ppg"]) == ("3.9", "1.2", "")
    coy = rows["nba-coy-41"]
    assert (coy["item"], coy["team"], coy["win_pct"], coy["gp"]) == ("Coach Zeta", "BOS", "0.875", "")


def test_nfl_player_rows(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    qb = rows["nfl-mvp-50"]
    assert (qb["item"], qb["team"], qb["odds"], qb["gp"]) == ("Quinn Back", "BUF", "250", "8")
    assert (qb["pass_yds"], qb["rush_yds"], qb["td"], qb["rec_yds"]) == ("2400", "310", "24", "")
    assert qb["ppg"] == qb["tackles"] == ""
    lb = rows["nfl-dpoy-52"]
    assert (lb["tackles"], lb["sacks"], lb["ints"], lb["pass_yds"]) == ("71", "6.5", "2", "")
    assert rows["nfl-droy-54"]["tackles"] == "71"


def test_super_bowl_rows_are_teams_with_team_stats(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    sb = by_id(history_rows(raw_dir, tmp_path)[0])["nfl-sbwin-7"]
    assert (sb["item"], sb["team"], sb["award"], sb["odds"]) == ("Buffalo Bills", "BUF", "sbwin", "450")
    assert (sb["win_pct"], sb["gp"], sb["pts_for"], sb["pts_against"]) == ("0.857", "7", "233", "181")


def test_nba_finals_rows_are_teams_with_standings_stats(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    f = by_id(history_rows(raw_dir, tmp_path)[0])["nba-finals-2"]
    assert (f["item"], f["team"], f["award"], f["odds"]) == ("Boston Celtics", "BOS", "finals", "500")
    assert (f["win_pct"], f["gp"], f["pts_for"], f["pts_against"]) == ("0.875", "8", "900", "800")


def test_cfp_rows_use_the_overall_record_and_team_names_from_the_teams_source(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    c = by_id(history_rows(raw_dir, tmp_path)[0])["ncaaf-cfp-61"]
    assert (c["item"], c["team"], c["league"], c["odds"]) == ("Georgia Bulldogs", "UGA", "ncaaf", "350")
    assert (c["win_pct"], c["gp"], c["pts_for"], c["pts_against"]) == ("0.875", "8", "328", "119")
    assert c["pass_yds"] == "" and c["ppg"] == ""


def test_cfp_without_the_records_source_keeps_names_but_empties_the_stats(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03", skip=("ncaaf_records",))
    c = by_id(history_rows(raw_dir, tmp_path)[0])["ncaaf-cfp-2390"]
    assert c["item"] == "Miami Hurricanes" and c["odds"] == "620"
    assert c["win_pct"] == "" and c["gp"] == "" and c["pts_for"] == ""


def test_heisman_row_gets_its_team_from_the_teams_source(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    h = by_id(history_rows(raw_dir, tmp_path)[0])["ncaaf-heisman-60"]
    assert (h["item"], h["team"], h["league"], h["pass_yds"], h["td"]) == ("Colt College", "MIA", "ncaaf", "2400", "24")


def test_a_value_the_source_does_not_report_is_left_empty(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")    # NBA MVP 11 has a price but no stats row
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    injured = rows["nba-mvp-11"]
    assert injured["odds"] == "-150" and injured["implied_prob"] == "0.6"
    assert injured["ppg"] == "" and injured["gp"] == ""
    assert injured["team"] == "BOS"    # still known from the athlete record
    rookie = rows["nfl-oroy-53"]       # an NFL candidate with no stats record yet
    assert rookie["odds"] == "900" and rookie["td"] == "" and rookie["gp"] == ""


def test_rows_are_sorted_by_date_then_item_id(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-05")
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04")
    rows, _ = history_rows(raw_dir, tmp_path)
    keys = [(r["date"], r["item_id"]) for r in rows]
    assert keys == sorted(keys)
    assert rows[0]["date"] == "2026-11-03" and rows[-1]["date"] == "2026-11-05"


def test_a_league_with_no_futures_file_has_no_rows_that_day(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", skip=("nfl_futures",))
    rows, _ = history_rows(raw_dir, tmp_path)
    day2 = [r for r in rows if r["date"] == "2026-11-04"]
    assert {r["league"] for r in day2} == {"nba", "ncaaf"}
    assert len([r for r in rows if r["date"] == "2026-11-03"]) == ITEMS_PER_DAY


def test_a_day_with_no_futures_at_all_has_no_rows(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", skip=("nba_futures", "nfl_futures", "ncaaf_futures"))
    rows, _ = history_rows(raw_dir, tmp_path)
    assert {r["date"] for r in rows} == {"2026-11-03"}


def test_failed_stats_and_standings_leave_values_empty_but_keep_the_rows(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03", skip=("nba_stats", "nba_standings", "nfl_stats", "nfl_standings", "ncaaf_stats"))
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    assert len(rows) == ITEMS_PER_DAY
    assert rows["nba-mvp-10"]["ppg"] == "" and rows["nba-mvp-10"]["odds"] == "200"
    assert rows["nba-coy-41"]["win_pct"] == "" and rows["nfl-mvp-50"]["pass_yds"] == ""
    assert rows["nfl-sbwin-7"]["item"] == "7"          # no standings, so the team name is unknown


def test_names_fall_back_to_an_earlier_day_when_athletes_failed(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", skip=("nba_athletes", "nfl_athletes"))
    rows = by_id(history_rows(raw_dir, tmp_path)[0], "2026-11-04")
    assert rows["nba-mvp-10"]["item"] == "Ann Alpha" and rows["nfl-mvp-50"]["item"] == "Quinn Back"


def test_name_falls_back_to_the_id_when_never_seen(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03", skip=("nba_athletes",))
    assert by_id(history_rows(raw_dir, tmp_path)[0])["nba-mvp-10"]["item"] == "10"


def test_the_same_espn_id_in_two_leagues_does_not_clash(raw_dir, tmp_path):
    """NBA athlete 10 and NFL athlete 10 are different people with different names."""
    full_day(raw_dir, "2026-11-03")
    write_raw(raw_dir, "2026-11-03", "nfl_futures", {"items": [{
        "name": "Regular Season MVP", "futures": [{"books": [{
            "athlete": {"$ref": "http://x/athletes/10?lang=en"}, "value": "+500"}]}]}]})
    write_raw(raw_dir, "2026-11-03", "nfl_athletes", {"athletes": {"10": {"id": "10", "fullName": "Nate Football"}}})
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    assert rows["nba-mvp-10"]["item"] == "Ann Alpha" and rows["nfl-mvp-10"]["item"] == "Nate Football"


def test_building_twice_gives_the_same_file(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", mvp_odds="+180")
    _, first = history_rows(raw_dir, tmp_path)
    _, second = history_rows(raw_dir, tmp_path)
    assert first == second


def test_history_depends_on_the_raw_files_alone(raw_dir, tmp_path):
    """Deleting the history and rebuilding reproduces it; a stale file is overwritten."""
    full_day(raw_dir, "2026-11-03")
    _, built = history_rows(raw_dir, tmp_path)
    path = tmp_path / "history.csv"
    path.write_text("garbage,not,the,history\n")
    build.build_history(raw_dir, path)
    assert path.read_bytes() == built


def test_a_changed_raw_file_changes_that_day_only(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04")
    before, _ = history_rows(raw_dir, tmp_path)
    write_raw(raw_dir, "2026-11-04", "nba_futures",
              nba_board(mvp=[(10, "+999")], roy=[(20, "+300")], dpoy=[(30, "+500")], coy=[(40, "+650")]))
    after, _ = history_rows(raw_dir, tmp_path)
    assert [r for r in before if r["date"] == "2026-11-03"] == [r for r in after if r["date"] == "2026-11-03"]
    day2 = by_id(after, "2026-11-04")
    assert day2["nba-mvp-10"]["odds"] == "999" and "nba-mvp-11" not in day2


def test_an_unreadable_raw_file_counts_as_missing(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    (raw_dir / "2026-11-03" / "nba_stats.json.gz").write_bytes(b"not gzip at all")
    rows = by_id(history_rows(raw_dir, tmp_path)[0])
    assert len(rows) == ITEMS_PER_DAY and rows["nba-mvp-10"]["ppg"] == ""


def test_empty_raw_folder_gives_a_header_only_history(raw_dir, tmp_path):
    raw_dir.mkdir()
    rows, content = history_rows(raw_dir, tmp_path)
    assert rows == [] and content.decode().strip() == ",".join(COLUMNS)


def test_source_names_cover_every_league():
    names = build.source_names()
    assert names == ["nba_futures", "nba_athletes", "nba_stats", "nba_standings", "nba_coaches",
                     "nfl_futures", "nfl_athletes", "nfl_stats", "nfl_standings",
                     "ncaaf_futures", "ncaaf_athletes", "ncaaf_stats", "ncaaf_teams", "ncaaf_records"]


def test_history_keeps_only_the_top_10_prices_per_market_even_from_a_long_raw_board(raw_dir, tmp_path):
    """Raw files saved before the rule (or by hand) hold the whole board; the build still tracks 10."""
    full_day(raw_dir, "2026-11-03")
    write_raw(raw_dir, "2026-11-03", "nba_futures",
              nba_board(mvp=[(i, f"+{i * 100}") for i in range(1, 41)], coy=[(40, "+650"), (41, "+900")]))
    write_raw(raw_dir, "2026-11-03", "nba_athletes", make_athletes({i: f"Player {i}" for i in range(1, 41)}))
    rows = [r for r in history_rows(raw_dir, tmp_path)[0] if r["league"] == "nba"]
    mvps = sorted(int(r["item_id"].split("-")[-1]) for r in rows if r["award"] == "mvp")
    assert mvps == list(range(1, 11))                        # the 10 shortest of 40
    assert len([r for r in rows if r["award"] == "coy"]) == 2   # a small market keeps everyone


def test_an_item_leaving_the_top_10_is_gone_and_one_entering_has_appeared(raw_dir, tmp_path):
    def board(prices):
        return nba_board(mvp=[(i, f"+{p}") for i, p in prices.items()])
    base = {i: 100 * i for i in range(1, 11)}                 # ids 1..10
    write_raw(raw_dir, "2026-11-03", "nba_futures", board({**base, 11: 1500}))     # 11 is just outside
    write_raw(raw_dir, "2026-11-04", "nba_futures", board({**base, 10: 2000, 11: 950}))   # 11 passes 10
    rows, _ = history_rows(raw_dir, tmp_path)
    day1 = {r["item_id"] for r in rows if r["date"] == "2026-11-03"}
    day2 = {r["item_id"] for r in rows if r["date"] == "2026-11-04"}
    assert "nba-mvp-11" not in day1 and "nba-mvp-11" in day2
    assert "nba-mvp-10" in day1 and "nba-mvp-10" not in day2
