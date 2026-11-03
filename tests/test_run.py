"""A daily run: raw files, history, status; second run on the same day; failed sources."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json

import pytest

from conftest import (CORE, make_athletes, make_coaches, make_futures, make_standings,
                      make_stats)
from tracker import fetch, run as run_mod
from tracker.fetch import SourceResult


def utc(day, hour=6):
    return dt.datetime(2026, 11, day, hour, 0, tzinfo=dt.timezone.utc)


def good_results(mvp_odds="+200", fail=()):
    """What fetch_all would return, built from the small samples."""
    payloads = {
        "futures": (make_futures(mvp=[(10, mvp_odds), (11, "-150")], roy=[(20, "+300")],
                                 dpoy=[(30, "+500")], coy=[(40, "+650")]), 6),
        "athletes": (make_athletes({10: "Ann Alpha", 11: "Bo Beta", 20: "Cy Gamma",
                                    30: "Di Delta", 40: "Coach Eps"}), 5),
        "stats": (make_stats({10: dict(team="LAL", gp=7, pts=30.0, reb=8.0, ast=9.0, stl=1.0, blk=1.0)}), 1),
        "standings": (make_standings({1: ("ATL", 0.5)}), 1),
        "coaches": (make_coaches({1: 40}), 1),
    }
    out = []
    for name, (data, count) in payloads.items():
        if name in fail:
            out.append(SourceResult(name, ok=False, error="boom"))
        else:
            out.append(SourceResult(name, ok=True, count=count, body=json.dumps(data).encode()))
    return out


@pytest.fixture
def paths(tmp_path):
    return dict(raw_dir=tmp_path / "raw", history_path=tmp_path / "history.csv",
                status_path=tmp_path / "status.json", log_path=tmp_path / "run_log.jsonl")


def do_run(paths, day, results):
    return run_mod.run(now=utc(day), fetcher=lambda season: results, **paths)


def history(paths):
    with open(paths["history_path"], newline="") as handle:
        return list(csv.DictReader(handle))


def test_run_writes_raw_files_history_and_status(paths):
    status = do_run(paths, 3, good_results())
    day = paths["raw_dir"] / "2026-11-03"
    assert sorted(p.name for p in day.iterdir()) == [
        "athletes.json.gz", "coaches.json.gz", "futures.json.gz", "standings.json.gz", "stats.json.gz"]
    with gzip.open(day / "futures.json.gz", "rt") as handle:
        assert json.load(handle)["items"]  # saved in the format it came in, compressed
    assert len(history(paths)) == 5
    assert status["run_time"] == "2026-11-03T06:00:00Z"
    assert status["first_run_date"] == "2026-11-03" and status["days_with_success"] == 1
    assert status["items"] == 5
    assert status["new_today"] == [] and status["gone_today"] == []
    assert json.loads(paths["status_path"].read_text()) == status


def test_status_has_exactly_the_specified_keys(paths):
    status = do_run(paths, 3, good_results())
    assert set(status) == {"run_time", "first_run_date", "days_with_success", "items",
                           "new_today", "gone_today", "sources"}
    assert all(set(s) == {"name", "ok", "count"} for s in status["sources"])
    assert [s["name"] for s in status["sources"]] == ["futures", "athletes", "stats", "standings", "coaches"]


def test_a_failed_source_writes_no_raw_file_and_is_recorded(paths):
    status = do_run(paths, 3, good_results(fail=("stats", "coaches")))
    files = {p.name for p in (paths["raw_dir"] / "2026-11-03").iterdir()}
    assert "stats.json.gz" not in files and "coaches.json.gz" not in files
    assert "futures.json.gz" in files
    by_name = {s["name"]: s for s in status["sources"]}
    assert by_name["stats"] == {"name": "stats", "ok": False, "count": 0}
    assert by_name["futures"]["ok"] is True
    assert len(history(paths)) == 5  # the run still finishes and builds history
    log = [json.loads(line) for line in paths["log_path"].read_text().splitlines()]
    assert {s["name"]: s["error"] for s in log[-1]["sources"]}["stats"] == "boom"


def test_all_sources_failing_still_finishes(paths):
    status = do_run(paths, 3, good_results(fail=("futures", "athletes", "stats", "standings", "coaches")))
    assert status["items"] == 0 and status["days_with_success"] == 0
    assert all(not s["ok"] for s in status["sources"])
    assert history(paths) == []


def test_second_run_on_the_same_day_replaces_that_days_data(paths):
    do_run(paths, 3, good_results(mvp_odds="+200"))
    first = history(paths)
    status = run_mod.run(now=utc(3, hour=18), fetcher=lambda s: good_results(mvp_odds="+250"), **paths)
    rows = history(paths)
    assert len(rows) == len(first) == 5                      # the day is not doubled
    assert {r["item_id"]: r["odds"] for r in rows}["mvp-10"] == "250"   # replaced, not appended
    assert status["days_with_success"] == 1                  # still one day
    assert status["run_time"] == "2026-11-03T18:00:00Z"


def test_second_run_drops_a_source_that_failed_the_second_time(paths):
    do_run(paths, 3, good_results())
    do_run(paths, 3, good_results(fail=("stats",)))
    assert not (paths["raw_dir"] / "2026-11-03" / "stats.json.gz").exists()
    assert {r["item_id"]: r["ppg"] for r in history(paths)}["mvp-10"] == ""


def test_same_day_rerun_with_identical_data_gives_an_identical_history(paths):
    do_run(paths, 3, good_results())
    before = paths["history_path"].read_bytes()
    do_run(paths, 3, good_results())
    assert paths["history_path"].read_bytes() == before


def test_days_with_success_counts_each_date_once(paths):
    for day in (3, 4, 4, 5):
        status = do_run(paths, day, good_results())
    assert status["days_with_success"] == 3 and status["first_run_date"] == "2026-11-03"
    assert [r["date"] for r in history(paths)].count("2026-11-04") == 5


def test_new_today_and_gone_today_compare_with_the_previous_day(paths):
    do_run(paths, 3, good_results())
    newer = good_results()
    newer[0] = SourceResult("futures", ok=True, count=5, body=json.dumps(make_futures(
        mvp=[(10, "+200"), (12, "+800")], roy=[(20, "+300")], dpoy=[(30, "+500")],
        coy=[(40, "+650")])).encode())            # 11 left the MVP board, 12 joined
    status = do_run(paths, 4, newer)
    assert status["new_today"] == ["mvp-12"] and status["gone_today"] == ["mvp-11"]


def test_failed_futures_does_not_make_everything_look_gone(paths):
    do_run(paths, 3, good_results())
    status = do_run(paths, 4, good_results(fail=("futures",)))
    assert status["items"] == 0 and status["new_today"] == [] and status["gone_today"] == []
    assert status["days_with_success"] == 2  # day 4 still has raw files from the other sources


def test_season_for_dates():
    from tracker.config import season_for
    assert season_for(dt.date(2026, 11, 3)) == 2027
    assert season_for(dt.date(2027, 3, 1)) == 2027
    assert season_for(dt.date(2027, 8, 1)) == 2028


# --------------------------------------------------------------- fetchers

def fake_get(responses, calls=None):
    """A getter that serves canned bodies by URL substring and records the calls."""
    def get(url):
        if calls is not None:
            calls.append(url)
        for key, body in responses.items():
            if key in url:
                if isinstance(body, Exception):
                    raise body
                return json.dumps(body).encode()
        raise OSError(f"unexpected url {url}")
    return get


def test_fetch_all_survives_a_failing_source():
    board = make_futures(mvp=[(10, "+200")], roy=[(20, "+300")], dpoy=[(30, "+500")], coy=[(40, "+650")])
    get = fake_get({
        "/futures": board,
        "/athletes/": {"id": "10", "fullName": "Ann Alpha"},
        "byathlete": OSError("503"),
        "/standings": make_standings({1: ("ATL", 0.5)}),
        "/coaches": make_coaches({1: 40})["teams"]["1"],
    })
    results = {r.name: r for r in fetch.fetch_all(2027, get)}
    assert results["futures"].ok and results["futures"].count == 4
    assert results["athletes"].ok
    assert not results["stats"].ok and results["stats"].body is None and "503" in results["stats"].error
    assert results["standings"].ok and results["coaches"].ok


def test_stats_are_filtered_to_the_tracked_athletes():
    stats = make_stats({10: dict(team="LAL", gp=7, pts=30.0, reb=8.0, ast=9.0, stl=1.0, blk=1.0),
                        99: dict(team="BOS", gp=7, pts=10.0, reb=2.0, ast=1.0, stl=1.0, blk=1.0)})
    stats["glossary"] = {"x": "y"}
    result = fetch.fetch_stats(2027, ["10"], fake_get({"byathlete": stats}))
    kept = json.loads(result.body)
    assert [a["athlete"]["id"] for a in kept["athletes"]] == ["10"]
    assert "glossary" not in kept and result.count == 1


def test_stats_follow_extra_pages():
    page1 = make_stats({10: dict(team="LAL", gp=1, pts=1.0, reb=1.0, ast=1.0, stl=1.0, blk=1.0)})
    page1["pagination"]["pages"] = 2
    page2 = make_stats({11: dict(team="BOS", gp=1, pts=2.0, reb=2.0, ast=2.0, stl=2.0, blk=2.0)})
    page2["pagination"]["pages"] = 2
    calls = []

    def get(url):
        calls.append(url)
        return json.dumps(page1 if "page=1" in url else page2).encode()
    result = fetch.fetch_stats(2027, ["10", "11"], get)
    assert result.ok and result.count == 2 and len(calls) == 2


def test_futures_with_no_award_markets_counts_as_a_failure():
    result = fetch.fetch_futures(2027, fake_get({"/futures": {"items": []}}))
    assert not result.ok and result.body is None and result.error


def test_athletes_and_stats_wait_for_the_futures_board():
    assert not fetch.fetch_athletes(2027, [], fake_get({})).ok
    assert not fetch.fetch_stats(2027, [], fake_get({})).ok


def test_athletes_partial_failure_still_ok_but_noted():
    def get(url):
        if "/athletes/11" in url:
            raise OSError("404")
        return json.dumps({"id": "10", "fullName": "Ann Alpha"}).encode()
    result = fetch.fetch_athletes(2027, ["10", "11"], get)
    assert result.ok and result.count == 1 and "1 of 2" in result.error
