"""Download the sources.

Every league (NBA, NFL, college football) has a futures board plus the sources that
enrich it. All are public ESPN JSON endpoints, no login:

  <league>_futures    the DraftKings board: award prices (and Super Bowl winner prices)
  <league>_athletes   one record per candidate, for the name and team (from the futures links)
  <league>_stats      season stats for the tracked candidates only
                        NBA: one call lists every player, filtered to the candidates
                        football: one call per candidate, trimmed to the stat categories used
  <league>_standings  team names, win percentage and points (NBA, NFL)
  <league>_teams      team names for college players (college football has no standings source)
  nba_coaches         which team each NBA coach belongs to (one call per team)

Each fetcher returns a SourceResult and never raises, so one source failing cannot
stop the run. A failed source has no `body`, so no raw file is written for it.
"""
from __future__ import annotations

import concurrent.futures as futures
import datetime as dt
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import convert
from .build import source_name
from .config import LEAGUES, USER_AGENT, League

TIMEOUT = 40
RETRIES = 3
WORKERS = 16

# Football stat categories kept from each per-player record (the rest is not used).
KEEP_CATEGORIES = {"general", "passing", "rushing", "receiving", "defensive", "defensiveInterceptions"}


@dataclass
class SourceResult:
    name: str
    ok: bool = False
    count: int = 0
    body: Optional[bytes] = None   # exactly what gets gzipped into data/raw/<date>/
    ext: str = "json"
    error: str = ""


def http_get(url: str, timeout: int = TIMEOUT, retries: int = RETRIES) -> bytes:
    """GET a URL, retrying a couple of times with a short pause."""
    last: Exception = RuntimeError("no attempt made")
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                           "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as error:  # network, HTTP status, timeout: all retryable
            last = error
            if "404" in str(error):
                break  # a missing page will not appear on retry
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last


def _json(body: bytes) -> Dict[str, Any]:
    return json.loads(body.decode("utf-8"))


def _dump(data: Any) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


Getter = Callable[[str], bytes]


def _lookup_many(urls: Dict[str, str], get: Getter) -> Dict[str, Dict[str, Any]]:
    """Fetch {key: url} in parallel; keys whose call failed are left out."""
    def one(item):
        key, url = item
        try:
            return key, _json(get(url))
        except Exception:
            return key, None
    with futures.ThreadPoolExecutor(WORKERS) as pool:
        return {key: record for key, record in pool.map(one, urls.items()) if record}


# ------------------------------------------------------------------ sources

def fetch_futures(cfg: League, season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult(source_name(cfg.code, "futures"))
    try:
        body = get(f"{cfg.core}/seasons/{season}/futures?limit=100")
        candidates = convert.convert_futures(_json(body), cfg)
        if not candidates:
            raise ValueError("futures board has none of the tracked markets")
        result.ok, result.count, result.body = True, len(candidates), body
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def fetch_athletes(cfg: League, season: int, ids: List[str], get: Getter = http_get) -> SourceResult:
    result = SourceResult(source_name(cfg.code, "athletes"))
    if not ids:
        result.error = "no candidates to look up (futures failed or none are people)"
        return result
    found = _lookup_many({i: f"{cfg.core}/seasons/{season}/athletes/{i}?lang=en&region=us" for i in ids}, get)
    names = convert.convert_athletes({"athletes": found})
    if not names:
        result.error = "no athlete record could be fetched"
        return result
    result.ok, result.count = True, len(names)
    result.body = _dump({"athletes": found})
    if len(found) < len(ids):
        result.error = f"{len(ids) - len(found)} of {len(ids)} athlete lookups failed"
    return result


def _trim_core_stats(record: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the stat categories the build uses, and only each stat's name and value."""
    cats = []
    for cat in ((record.get("splits") or {}).get("categories") or []):
        if cat.get("name") in KEEP_CATEGORIES:
            cats.append({"name": cat["name"],
                         "stats": [{"name": s.get("name"), "value": s.get("value")} for s in cat.get("stats", [])]})
    return {"splits": {"categories": cats}}


def fetch_stats(cfg: League, season: int, ids: List[str], get: Getter = http_get) -> SourceResult:
    """Season stats for the tracked candidates only (see the module docstring)."""
    result = SourceResult(source_name(cfg.code, "stats"))
    if not ids:
        result.error = "no candidates to keep stats for (futures failed or none are people)"
        return result
    try:
        if cfg.bulk_stats:
            return _fetch_bulk_stats(cfg, season, ids, get, result)
        urls = {i: f"{cfg.core}/seasons/{season}/types/2/athletes/{i}/statistics" for i in ids}
        found = {i: _trim_core_stats(rec) for i, rec in _lookup_many(urls, get).items()}
        count = len(convert.convert_football_stats({"athletes": found}))
        if count == 0:
            raise ValueError("no tracked athlete has season stats yet")
        result.ok, result.count, result.body = True, count, _dump({"athletes": found})
        if len(found) < len(ids):
            result.error = f"{len(ids) - len(found)} of {len(ids)} players have no stats record"
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def _fetch_bulk_stats(cfg: League, season: int, ids: List[str], get: Getter,
                      result: SourceResult) -> SourceResult:
    """NBA: the endpoint lists every player (about 300); keep only the tracked ones."""
    wanted = set(ids)
    page, merged = 1, None
    while True:
        data = _json(get(f"{cfg.site_v3}/statistics/byathlete?season={season}&seasontype=2"
                         f"&limit=500&page={page}"))
        if merged is None:
            merged = data
            merged["athletes"] = list(data.get("athletes", []))
        else:
            merged["athletes"].extend(data.get("athletes", []))
        pages = int((data.get("pagination") or {}).get("pages", 1) or 1)
        if page >= pages:
            break
        page += 1
    kept = [a for a in merged["athletes"] if str((a.get("athlete") or {}).get("id")) in wanted]
    merged["athletes"] = kept
    merged.pop("glossary", None)  # explanatory text, not data
    if "pagination" in merged:
        merged["pagination"] = {"count": len(kept), "pages": 1, "note": "filtered to tracked athletes"}
    count = len(convert.convert_stats(merged))
    if count == 0:
        raise ValueError("none of the tracked athletes appear in the stats feed")
    result.ok, result.count, result.body = True, count, _dump(merged)
    return result


def fetch_standings(cfg: League, season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult(source_name(cfg.code, "standings"))
    try:
        body = get(f"{cfg.site_v2}/standings?season={season}")
        count = len(convert.convert_standings(_json(body)))
        if count == 0:
            raise ValueError("standings had no teams")
        result.ok, result.count, result.body = True, count, body
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def fetch_teams(cfg: League, season: int, team_ids: List[str], get: Getter = http_get) -> SourceResult:
    """Team records for the teams of the tracked players (names for college players)."""
    result = SourceResult(source_name(cfg.code, "teams"))
    if not team_ids:
        result.error = "no team ids to look up (athletes failed)"
        return result
    found = _lookup_many({t: f"{cfg.core}/seasons/{season}/teams/{t}" for t in team_ids}, get)
    count = len(convert.convert_teams({"teams": found}))
    if count == 0:
        result.error = "no team record could be fetched"
        return result
    result.ok, result.count, result.body = True, count, _dump({"teams": found})
    if len(found) < len(team_ids):
        result.error = f"{len(team_ids) - len(found)} team lookups failed"
    return result


def fetch_coaches(cfg: League, season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult(source_name(cfg.code, "coaches"))
    teams = _lookup_many({str(t): f"{cfg.core}/seasons/{season}/teams/{t}/coaches" for t in cfg.team_ids}, get)
    count = len(convert.convert_coaches({"teams": teams}))
    if count == 0:
        result.error = "no team returned a coach"
        return result
    result.ok, result.count, result.body = True, count, _dump({"teams": teams})
    if len(teams) < len(cfg.team_ids):
        result.error = f"{len(cfg.team_ids) - len(teams)} team lookups failed"
    return result


# ---------------------------------------------------------------------- all

def fetch_league(cfg: League, season: int, get: Getter = http_get) -> List[SourceResult]:
    """Every source of one league. Athletes, stats and teams need ids from the futures board."""
    results: List[SourceResult] = []
    board = fetch_futures(cfg, season, get)
    results.append(board)
    candidates = convert.convert_futures(_json(board.body), cfg) if board.ok else []
    people = sorted({c["ref_id"] for c in candidates if c["kind"] == "athlete"})
    athletes = fetch_athletes(cfg, season, people, get)
    results.append(athletes)
    results.append(fetch_stats(cfg, season, people, get))
    if cfg.standings:
        results.append(fetch_standings(cfg, season, get))
    if cfg.teams:
        records = _json(athletes.body)["athletes"] if athletes.ok else {}
        team_ids = sorted({t for t in (v["team_id"] for v in convert.convert_athletes({"athletes": records}).values()) if t})
        results.append(fetch_teams(cfg, season, team_ids, get))
    if cfg.coaches:
        results.append(fetch_coaches(cfg, season, get))
    return results


def fetch_all(date: dt.date, get: Getter = http_get) -> List[SourceResult]:
    """Run every league's sources. One league or source failing never stops the others."""
    results: List[SourceResult] = []
    for cfg in LEAGUES.values():
        try:
            results.extend(fetch_league(cfg, cfg.season_for(date), get))
        except Exception as error:  # a bug here must not stop the other leagues
            results.append(SourceResult(source_name(cfg.code, "futures"), error=f"{type(error).__name__}: {error}"))
    return results
