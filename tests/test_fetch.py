"""Fetchers, against a fake network: each league's sources, trimming, and failures."""
from __future__ import annotations

import datetime as dt
import json

from conftest import (LINEBACKER, NBA, NCAAF, NFL, QB, make_athletes, make_coaches,
                      make_football_stats, make_nba_stats, make_standings, make_teams, nba_board,
                      nfl_board, ncaaf_board)
from tracker import convert, fetch

DAY = dt.date(2026, 11, 3)


def router(routes, calls=None):
    """A getter serving canned payloads. routes: [((substring, ...), payload)]; first match wins.
    A payload may be an Exception (raised), or a function of the url."""
    def get(url):
        if calls is not None:
            calls.append(url)
        for needles, payload in routes:
            if all(n in url for n in needles):
                if isinstance(payload, Exception):
                    raise payload
                data = payload(url) if callable(payload) else payload
                return json.dumps(data).encode()
        raise OSError(f"unexpected url {url}")
    return get


def football_record(stats):
    return list(make_football_stats({1: stats})["athletes"].values())[0]


# ------------------------------------------------------------------- futures

def test_futures_url_uses_the_leagues_sport_slug_and_season():
    calls = []
    fetch.fetch_futures(NFL, 2026, router([(("futures",), nfl_board(mvp=[(1, "+200")]))], calls))
    assert calls == ["https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/futures?limit=100"]
    calls.clear()
    fetch.fetch_futures(NCAAF, 2026, router([(("futures",), ncaaf_board([(1, "+1")]))], calls))
    assert "football/leagues/college-football/seasons/2026" in calls[0]


def test_futures_counts_candidates_and_keeps_the_body_as_received():
    result = fetch.fetch_futures(NBA, 2027, router([(("futures",), nba_board(mvp=[(1, "+200"), (2, "+300")]))]))
    assert result.ok and result.name == "nba_futures" and result.count == 2
    assert json.loads(result.body)["items"]


def test_futures_with_no_tracked_markets_counts_as_a_failure():
    result = fetch.fetch_futures(NBA, 2027, router([(("futures",), {"items": []})]))
    assert not result.ok and result.body is None and result.error


def test_futures_http_error_is_a_failure_not_an_exception():
    result = fetch.fetch_futures(NFL, 2026, router([(("futures",), OSError("503"))]))
    assert not result.ok and "503" in result.error


# ------------------------------------------------------------ athletes / stats

def test_athletes_partial_failure_still_ok_but_noted():
    def pick(url):
        if "/athletes/11" in url:
            raise OSError("404")
        return {"id": "10", "fullName": "Ann Alpha"}
    result = fetch.fetch_athletes(NBA, 2027, ["10", "11"], lambda u: json.dumps(pick(u)).encode())
    assert result.ok and result.count == 1 and "1 of 2" in result.error


def test_athletes_and_stats_wait_for_the_futures_board():
    assert not fetch.fetch_athletes(NBA, 2027, [], router([])).ok
    assert not fetch.fetch_stats(NBA, 2027, [], router([])).ok
    assert not fetch.fetch_stats(NFL, 2026, [], router([])).ok


def test_nba_stats_are_filtered_to_the_tracked_athletes():
    stats = make_nba_stats({10: dict(team="LAL", gp=7, pts=30.0, reb=8.0, ast=9.0, stl=1.0, blk=1.0),
                            99: dict(team="BOS", gp=7, pts=10.0, reb=2.0, ast=1.0, stl=1.0, blk=1.0)})
    stats["glossary"] = {"x": "y"}
    result = fetch.fetch_stats(NBA, 2027, ["10"], router([(("byathlete",), stats)]))
    kept = json.loads(result.body)
    assert [a["athlete"]["id"] for a in kept["athletes"]] == ["10"]
    assert "glossary" not in kept and result.count == 1


def test_nba_stats_follow_extra_pages():
    page1 = make_nba_stats({10: dict(team="LAL", gp=1, pts=1.0, reb=1.0, ast=1.0, stl=1.0, blk=1.0)})
    page1["pagination"]["pages"] = 2
    page2 = make_nba_stats({11: dict(team="BOS", gp=1, pts=2.0, reb=2.0, ast=2.0, stl=2.0, blk=2.0)})
    page2["pagination"]["pages"] = 2
    calls = []
    get = router([(("page=1",), page1), (("page=2",), page2)], calls)
    result = fetch.fetch_stats(NBA, 2027, ["10", "11"], get)
    assert result.ok and result.count == 2 and len(calls) == 2


def test_football_stats_are_fetched_one_call_per_player_and_trimmed():
    heavy = football_record({"general": {"gamesPlayed": 8.0}, "passing": {"passingYards": 2400.0},
                             "scoring": {"totalPoints": 99.0}, "punting": {"punts": 5.0}})
    for cat in heavy["splits"]["categories"]:
        for stat in cat["stats"]:
            stat["displayName"] = "long description we do not need"
    calls = []
    result = fetch.fetch_stats(NFL, 2026, ["50", "51"], router([(("types/2/athletes/",), heavy)], calls))
    assert sorted(calls) == [f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/seasons/2026/types/2/athletes/{i}/statistics" for i in ("50", "51")]
    kept = json.loads(result.body)["athletes"]["50"]["splits"]["categories"]
    assert [c["name"] for c in kept] == ["general", "passing"]       # scoring and punting dropped
    assert kept[1]["stats"] == [{"name": "passingYards", "value": 2400.0}]  # only name and value kept
    assert result.ok and result.count == 2


def test_football_player_with_no_stats_page_is_skipped_but_noted():
    def pick(url):
        if "/athletes/51/" in url:
            raise OSError("HTTP Error 404: Not Found")
        return football_record(QB)
    result = fetch.fetch_stats(NFL, 2026, ["50", "51"], router([(("types/2/athletes/",), pick)]))
    assert result.ok and result.count == 1 and "1 of 2" in result.error
    assert set(json.loads(result.body)["athletes"]) == {"50"}


def test_football_stats_with_nothing_usable_is_a_failure():
    result = fetch.fetch_stats(NFL, 2026, ["50"], router([(("types/2/athletes/",), OSError("404"))]))
    assert not result.ok and result.body is None


def test_a_404_is_not_retried_but_other_errors_are(monkeypatch):
    import urllib.error
    attempts = []

    def failing(code):
        def urlopen(request, timeout=None):
            attempts.append(code)
            raise urllib.error.HTTPError("http://x", code, "err", {}, None)
        return urlopen
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)

    monkeypatch.setattr(fetch.urllib.request, "urlopen", failing(404))
    try:
        fetch.http_get("http://x")
    except urllib.error.HTTPError:
        pass
    assert attempts == [404]                      # a missing page will not appear on retry

    attempts.clear()
    monkeypatch.setattr(fetch.urllib.request, "urlopen", failing(503))
    try:
        fetch.http_get("http://x")
    except urllib.error.HTTPError:
        pass
    assert attempts == [503, 503, 503]            # a server hiccup is retried


# ---------------------------------------------------------- standings / teams / coaches

def test_standings_url_per_league_and_count():
    calls = []
    standings = make_standings({1: ("A", "Team A", 0.5, 1, 1, 10, 10)})
    result = fetch.fetch_standings(NFL, 2026, router([(("standings",), standings)], calls))
    assert "football/nfl/standings?season=2026" in calls[0]
    assert result.ok and result.count == 1 and result.name == "nfl_standings"


def test_standings_with_no_teams_is_a_failure():
    assert not fetch.fetch_standings(NBA, 2027, router([(("standings",), {"children": []})])).ok


def test_teams_source_fetches_each_team_once():
    calls = []
    get = router([(("/teams/2390",), {"id": "2390", "abbreviation": "MIA", "displayName": "Miami Hurricanes"})], calls)
    result = fetch.fetch_teams(NCAAF, 2026, ["2390"], get)
    assert result.ok and result.count == 1 and len(calls) == 1
    assert fetch.fetch_teams(NCAAF, 2026, [], get).ok is False


def test_coaches_make_one_call_per_team():
    calls = []
    get = router([(("/coaches",), lambda url: make_coaches({1: 425})["teams"]["1"])], calls)
    result = fetch.fetch_coaches(NBA, 2027, get)
    assert len(calls) == 30 and result.ok and result.count == 1


# ------------------------------------------------------------------ fetch_league

def nba_routes():
    return [
        (("basketball/leagues/nba", "futures"), nba_board(mvp=[(10, "+200")], roy=[(20, "+300")],
                                                           dpoy=[(30, "+500")], coy=[(40, "+650")])),
        (("/coaches",), lambda url: make_coaches({1: 40})["teams"]["1"]),
        (("/athletes/",), lambda url: {"id": url.split("/athletes/")[1].split("?")[0], "fullName": "Somebody"}),
        (("byathlete",), make_nba_stats({10: dict(team="LAL", gp=7, pts=30.0, reb=8.0, ast=9.0, stl=1.0, blk=1.0)})),
        (("basketball/nba/standings",), make_standings({1: ("ATL", "Atlanta Hawks", 0.5, 3, 3, 1, 1)})),
    ]


def test_fetch_league_nba_runs_every_nba_source():
    results = {r.name: r for r in fetch.fetch_league(NBA, 2027, router(nba_routes()))}
    assert list(results) == ["nba_futures", "nba_athletes", "nba_stats", "nba_standings", "nba_coaches"]
    assert all(r.ok for r in results.values())
    assert results["nba_athletes"].count == 4


def test_fetch_league_survives_a_failing_source():
    routes = [((("byathlete",), OSError("503")))] + nba_routes()
    results = {r.name: r for r in fetch.fetch_league(NBA, 2027, router(routes))}
    assert not results["nba_stats"].ok and results["nba_stats"].body is None
    assert results["nba_futures"].ok and results["nba_standings"].ok and results["nba_coaches"].ok


def test_fetch_league_with_failed_futures_still_tries_the_independent_sources():
    routes = [((("futures",), OSError("503")))] + nba_routes()
    results = {r.name: r for r in fetch.fetch_league(NBA, 2027, router(routes))}
    assert not results["nba_futures"].ok and not results["nba_athletes"].ok and not results["nba_stats"].ok
    assert results["nba_standings"].ok and results["nba_coaches"].ok


def test_fetch_league_ncaaf_looks_up_the_teams_of_its_players():
    routes = [
        (("college-football", "futures"), ncaaf_board([(60, "+300")])),
        (("/athletes/60?",), {"id": "60", "fullName": "Colt College",
                               "team": {"$ref": "http://x/teams/2390?lang=en"}}),
        (("/athletes/60/statistics",), football_record(QB)),
        (("/teams/2390",), {"id": "2390", "abbreviation": "MIA", "displayName": "Miami Hurricanes"}),
    ]
    results = {r.name: r for r in fetch.fetch_league(NCAAF, 2026, router(routes))}
    assert list(results) == ["ncaaf_futures", "ncaaf_athletes", "ncaaf_stats", "ncaaf_teams"]
    assert all(r.ok for r in results.values()), {n: r.error for n, r in results.items()}


def test_fetch_all_runs_every_league_and_one_league_failing_does_not_stop_the_rest():
    def get(url):
        if "football/leagues/nfl" in url or "football/nfl" in url:
            raise OSError("nfl is down")
        return router(nba_routes() + [
            (("college-football", "futures"), ncaaf_board([(60, "+300")])),
            (("/athletes/60?",), {"id": "60", "fullName": "Colt College"}),
            (("/athletes/60/statistics",), football_record(QB)),
        ])(url)
    results = {r.name: r for r in fetch.fetch_all(DAY, get)}
    assert set(results) == set(__import__("tracker.build", fromlist=["x"]).source_names())
    assert results["nba_futures"].ok and results["ncaaf_futures"].ok
    assert not results["nfl_futures"].ok and not results["nfl_stats"].ok and not results["nfl_standings"].ok
