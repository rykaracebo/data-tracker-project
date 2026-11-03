"""A daily run: raw files, history, status; second run on the same day; failed sources."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json

import pytest

from conftest import ITEMS_PER_DAY, NBA, NFL, day_payloads, nba_board
from tracker import build, run as run_mod
from tracker.fetch import SourceResult

ALL_SOURCES = build.source_names()


def utc(day, hour=6):
    return dt.datetime(2026, 11, day, hour, 0, tzinfo=dt.timezone.utc)


def good_results(mvp_odds="+200", fail=()):
    """What fetch_all would return for one day, built from the small samples."""
    out = []
    for name, data in day_payloads(mvp_odds).items():
        if name in fail:
            out.append(SourceResult(name, ok=False, error="boom"))
        else:
            out.append(SourceResult(name, ok=True, count=3, body=json.dumps(data).encode()))
    return out


@pytest.fixture
def paths(tmp_path):
    return dict(raw_dir=tmp_path / "raw", history_path=tmp_path / "history.csv",
                status_path=tmp_path / "status.json", log_path=tmp_path / "run_log.jsonl")


def do_run(paths, day, results):
    return run_mod.run(now=utc(day), fetcher=lambda date: results, **paths)


def history(paths):
    with open(paths["history_path"], newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_writes_raw_files_history_and_status(paths):
    status = do_run(paths, 3, good_results())
    day = paths["raw_dir"] / "2026-11-03"
    assert sorted(p.name for p in day.iterdir()) == sorted(f"{n}.json.gz" for n in ALL_SOURCES)
    with gzip.open(day / "nba_futures.json.gz", "rt") as handle:
        assert json.load(handle)["items"]  # saved in the format it came in, compressed
    assert len(history(paths)) == ITEMS_PER_DAY
    assert status["run_time"] == "2026-11-03T06:00:00Z"
    assert status["first_run_date"] == "2026-11-03" and status["days_with_success"] == 1
    assert status["items"] == ITEMS_PER_DAY
    assert status["new_today"] == [] and status["gone_today"] == []
    assert json.loads(paths["status_path"].read_text()) == status


def test_status_has_exactly_the_specified_keys(paths):
    status = do_run(paths, 3, good_results())
    assert set(status) == {"run_time", "first_run_date", "days_with_success", "items",
                           "new_today", "gone_today", "sources"}
    assert all(set(s) == {"name", "ok", "count"} for s in status["sources"])
    assert [s["name"] for s in status["sources"]] == ALL_SOURCES


def test_a_failed_source_writes_no_raw_file_and_is_recorded(paths):
    status = do_run(paths, 3, good_results(fail=("nba_stats", "nba_coaches")))
    files = {p.name for p in (paths["raw_dir"] / "2026-11-03").iterdir()}
    assert "nba_stats.json.gz" not in files and "nba_coaches.json.gz" not in files
    assert "nba_futures.json.gz" in files and "nfl_stats.json.gz" in files
    by_name = {s["name"]: s for s in status["sources"]}
    assert by_name["nba_stats"] == {"name": "nba_stats", "ok": False, "count": 0}
    assert by_name["nba_futures"]["ok"] is True
    assert len(history(paths)) == ITEMS_PER_DAY  # the run still finishes and builds history
    log = [json.loads(line) for line in paths["log_path"].read_text().splitlines()]
    assert {s["name"]: s["error"] for s in log[-1]["sources"]}["nba_stats"] == "boom"


def test_all_sources_failing_still_finishes(paths):
    status = do_run(paths, 3, good_results(fail=ALL_SOURCES))
    assert status["items"] == 0 and status["days_with_success"] == 0
    assert all(not s["ok"] for s in status["sources"])
    assert history(paths) == []


def test_second_run_on_the_same_day_replaces_that_days_data(paths):
    do_run(paths, 3, good_results(mvp_odds="+200"))
    first = history(paths)
    status = run_mod.run(now=utc(3, hour=18), fetcher=lambda d: good_results(mvp_odds="+250"), **paths)
    rows = history(paths)
    assert len(rows) == len(first) == ITEMS_PER_DAY            # the day is not doubled
    assert {r["item_id"]: r["odds"] for r in rows}["nba-mvp-10"] == "250"   # replaced, not appended
    assert status["days_with_success"] == 1                    # still one day
    assert status["run_time"] == "2026-11-03T18:00:00Z"


def test_second_run_drops_a_source_that_failed_the_second_time(paths):
    do_run(paths, 3, good_results())
    do_run(paths, 3, good_results(fail=("nba_stats",)))
    assert not (paths["raw_dir"] / "2026-11-03" / "nba_stats.json.gz").exists()
    assert {r["item_id"]: r["ppg"] for r in history(paths)}["nba-mvp-10"] == ""


def test_same_day_rerun_with_identical_data_gives_an_identical_history(paths):
    do_run(paths, 3, good_results())
    before = paths["history_path"].read_bytes()
    do_run(paths, 3, good_results())
    assert paths["history_path"].read_bytes() == before


def test_days_with_success_counts_each_date_once(paths):
    for day in (3, 4, 4, 5):
        status = do_run(paths, day, good_results())
    assert status["days_with_success"] == 3 and status["first_run_date"] == "2026-11-03"
    assert [r["date"] for r in history(paths)].count("2026-11-04") == ITEMS_PER_DAY


def test_new_today_and_gone_today_compare_with_the_previous_day(paths):
    do_run(paths, 3, good_results())
    newer = good_results()
    newer[0] = SourceResult("nba_futures", ok=True, count=5, body=json.dumps(nba_board(
        mvp=[(10, "+200"), (12, "+800")], roy=[(20, "+300")], dpoy=[(30, "+500")],
        coy=[(40, "+650"), (41, "+900")])).encode())      # 11 left the MVP board, 12 joined
    status = do_run(paths, 4, newer)
    assert status["new_today"] == ["nba-mvp-12"] and status["gone_today"] == ["nba-mvp-11"]


def test_failed_futures_does_not_make_everything_look_gone(paths):
    do_run(paths, 3, good_results())
    status = do_run(paths, 4, good_results(fail=("nba_futures", "nfl_futures", "ncaaf_futures")))
    assert status["items"] == 0 and status["new_today"] == [] and status["gone_today"] == []
    assert status["days_with_success"] == 2  # day 4 still has raw files from the other sources


def test_one_leagues_futures_failing_only_drops_that_league(paths):
    do_run(paths, 3, good_results())
    status = do_run(paths, 4, good_results(fail=("nfl_futures",)))
    assert status["items"] == ITEMS_PER_DAY - 7
    # the NFL items are not reported "gone" by a failed fetch... they are simply absent today
    assert all(i.startswith("nfl-") for i in status["gone_today"])


def test_fetch_all_gets_the_runs_date(paths):
    seen = []
    run_mod.run(now=utc(3), fetcher=lambda d: seen.append(d) or good_results(), **paths)
    assert seen == [dt.date(2026, 11, 3)]
