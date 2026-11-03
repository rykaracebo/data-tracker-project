"""History logic: one row per item per day, built from the raw files alone."""
from __future__ import annotations

import csv

from conftest import full_day, write_raw, make_futures
from tracker import build
from tracker.config import COLUMNS


def history_rows(raw_dir, tmp_path):
    path = tmp_path / "history.csv"
    build.build_history(raw_dir, path)
    with open(path, newline="") as handle:
        return list(csv.DictReader(handle)), path.read_bytes()


def test_one_row_per_item_per_day_with_the_fixed_first_columns(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows, _ = history_rows(raw_dir, tmp_path)
    assert list(rows[0].keys())[:4] == ["date", "item_id", "item", "source"]
    assert list(rows[0].keys()) == COLUMNS
    assert len(rows) == 6  # 2 MVP + 1 ROY + 1 DPOY + 2 COY
    assert len({r["item_id"] for r in rows}) == 6
    assert {r["source"] for r in rows} == {"futures"}


def test_rows_carry_the_stats_that_belong_to_each_award(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    rows, _ = history_rows(raw_dir, tmp_path)
    by_id = {r["item_id"]: r for r in rows}
    mvp = by_id["mvp-10"]
    assert (mvp["item"], mvp["team"], mvp["odds"], mvp["ppg"], mvp["rpg"], mvp["apg"]) == \
        ("Ann Alpha", "LAL", "200", "38.2857", "8.0", "9.1")
    assert mvp["bpg"] == "" and mvp["spg"] == "" and mvp["win_pct"] == ""
    dpoy = by_id["dpoy-30"]
    assert (dpoy["bpg"], dpoy["spg"], dpoy["ppg"]) == ("3.9", "1.2", "")
    coy = by_id["coy-41"]
    assert (coy["item"], coy["team"], coy["win_pct"], coy["gp"]) == ("Coach Zeta", "BOS", "0.875", "")


def test_a_value_the_source_does_not_report_is_left_empty(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")  # MVP 11 has a price but no stats row
    rows, _ = history_rows(raw_dir, tmp_path)
    injured = {r["item_id"]: r for r in rows}["mvp-11"]
    assert injured["odds"] == "-150" and injured["implied_prob"] == "0.6"
    assert injured["team"] == "" and injured["ppg"] == "" and injured["gp"] == ""


def test_rows_are_sorted_by_date_then_item_id(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-05")
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04")
    rows, _ = history_rows(raw_dir, tmp_path)
    keys = [(r["date"], r["item_id"]) for r in rows]
    assert keys == sorted(keys)
    assert [r["date"] for r in rows][0] == "2026-11-03" and [r["date"] for r in rows][-1] == "2026-11-05"


def test_a_day_with_no_futures_file_has_no_rows(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", skip=("futures",))
    rows, _ = history_rows(raw_dir, tmp_path)
    assert {r["date"] for r in rows} == {"2026-11-03"}


def test_a_failed_stats_source_leaves_those_values_empty_but_keeps_the_rows(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03", skip=("stats", "standings"))
    rows, _ = history_rows(raw_dir, tmp_path)
    assert len(rows) == 6
    assert all(r["ppg"] == "" and r["win_pct"] == "" and r["team"] == "" for r in rows)
    assert {r["item_id"]: r for r in rows}["mvp-10"]["odds"] == "200"


def test_names_fall_back_to_an_earlier_day_when_athletes_failed(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", skip=("athletes",))
    rows, _ = history_rows(raw_dir, tmp_path)
    day2 = {r["item_id"]: r["item"] for r in rows if r["date"] == "2026-11-04"}
    assert day2["mvp-10"] == "Ann Alpha"


def test_name_falls_back_to_the_id_when_never_seen(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03", skip=("athletes",))
    rows, _ = history_rows(raw_dir, tmp_path)
    assert {r["item_id"]: r["item"] for r in rows}["mvp-10"] == "10"


def test_building_twice_gives_the_same_file(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04", mvp_odds="+180")
    _, first = history_rows(raw_dir, tmp_path)
    _, second = history_rows(raw_dir, tmp_path)
    assert first == second


def test_history_depends_on_the_raw_files_alone(raw_dir, tmp_path):
    """Deleting the history and rebuilding reproduces it; a stale file is overwritten."""
    full_day(raw_dir, "2026-11-03")
    rows, built = history_rows(raw_dir, tmp_path)
    path = tmp_path / "history.csv"
    path.write_text("garbage,not,the,history\n")
    build.build_history(raw_dir, path)
    assert path.read_bytes() == built


def test_a_changed_raw_file_changes_that_day_only(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    full_day(raw_dir, "2026-11-04")
    before, _ = history_rows(raw_dir, tmp_path)
    write_raw(raw_dir, "2026-11-04", "futures",
              make_futures(mvp=[(10, "+999")], roy=[(20, "+300")], dpoy=[(30, "+500")],
                           coy=[(40, "+650")]))
    after, _ = history_rows(raw_dir, tmp_path)
    assert [r for r in before if r["date"] == "2026-11-03"] == [r for r in after if r["date"] == "2026-11-03"]
    assert {r["item_id"]: r["odds"] for r in after if r["date"] == "2026-11-04"}["mvp-10"] == "999"
    assert "mvp-11" not in {r["item_id"] for r in after if r["date"] == "2026-11-04"}


def test_an_unreadable_raw_file_counts_as_missing(raw_dir, tmp_path):
    full_day(raw_dir, "2026-11-03")
    (raw_dir / "2026-11-03" / "stats.json.gz").write_bytes(b"not gzip at all")
    rows, _ = history_rows(raw_dir, tmp_path)
    assert len(rows) == 6 and all(r["ppg"] == "" for r in rows)


def test_empty_raw_folder_gives_a_header_only_history(raw_dir, tmp_path):
    raw_dir.mkdir()
    rows, content = history_rows(raw_dir, tmp_path)
    assert rows == [] and content.decode().strip() == ",".join(COLUMNS)
