"""Download the five sources.

Sources (all public ESPN JSON, no login):
  futures    the DraftKings award board (MVP, ROY, DPOY, COY prices)
  athletes   one record per candidate, for the name (fetched from the futures links)
  stats      per-game season stats, kept only for the tracked candidates
  standings  team win percentage
  coaches    which team each coach belongs to (one call per team)

Each fetcher returns a SourceResult and never raises, so one source failing
cannot stop the run. A failed source has no `body`, so no raw file is written.
"""
from __future__ import annotations

import concurrent.futures as futures
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import convert
from .config import CORE, NBA_TEAM_IDS, SITE_V2, SITE_V3, USER_AGENT

TIMEOUT = 30
RETRIES = 3
WORKERS = 8


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
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last


def _json(body: bytes) -> Dict[str, Any]:
    return json.loads(body.decode("utf-8"))


def _dump(data: Any) -> bytes:
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


Getter = Callable[[str], bytes]


# ------------------------------------------------------------------ sources

def fetch_futures(season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult("futures")
    try:
        body = get(f"{CORE}/seasons/{season}/futures?limit=100")
        candidates = convert.convert_futures(_json(body))
        if not candidates:
            raise ValueError("futures board has none of the four award markets")
        result.ok, result.count, result.body = True, len(candidates), body
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def fetch_athletes(season: int, person_ids: List[str], get: Getter = http_get) -> SourceResult:
    result = SourceResult("athletes")
    if not person_ids:
        result.error = "no candidates to look up (futures failed)"
        return result

    def one(person_id: str):
        url = f"{CORE}/seasons/{season}/athletes/{person_id}?lang=en&region=us"
        try:
            return person_id, _json(get(url))
        except Exception:
            return person_id, None

    with futures.ThreadPoolExecutor(WORKERS) as pool:
        found = {pid: rec for pid, rec in pool.map(one, person_ids) if rec}
    names = convert.convert_athletes({"athletes": found})
    if not names:
        result.error = "no athlete record could be fetched"
        return result
    result.ok, result.count = True, len(names)
    result.body = _dump({"athletes": found})
    result.error = "" if len(found) == len(person_ids) else \
        f"{len(person_ids) - len(found)} of {len(person_ids)} athlete lookups failed"
    return result


def fetch_stats(season: int, person_ids: List[str], get: Getter = http_get) -> SourceResult:
    """Per-game stats. The endpoint returns every player; only tracked ones are kept."""
    result = SourceResult("stats")
    if not person_ids:
        result.error = "no candidates to keep stats for (futures failed)"
        return result
    wanted = set(person_ids)
    try:
        page, merged = 1, None
        while True:
            body = get(f"{SITE_V3}/statistics/byathlete?season={season}&seasontype=2"
                       f"&limit=500&page={page}")
            data = _json(body)
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
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def fetch_standings(season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult("standings")
    try:
        body = get(f"{SITE_V2}/standings?season={season}")
        count = len(convert.convert_standings(_json(body)))
        if count == 0:
            raise ValueError("standings had no teams")
        result.ok, result.count, result.body = True, count, body
    except Exception as error:
        result.error = f"{type(error).__name__}: {error}"
    return result


def fetch_coaches(season: int, get: Getter = http_get) -> SourceResult:
    result = SourceResult("coaches")

    def one(team_id: int):
        try:
            return str(team_id), _json(get(f"{CORE}/seasons/{season}/teams/{team_id}/coaches"))
        except Exception:
            return str(team_id), None

    with futures.ThreadPoolExecutor(WORKERS) as pool:
        teams = {tid: resp for tid, resp in pool.map(one, NBA_TEAM_IDS) if resp}
    count = len(convert.convert_coaches({"teams": teams}))
    if count == 0:
        result.error = "no team returned a coach"
        return result
    result.ok, result.count, result.body = True, count, _dump({"teams": teams})
    if len(teams) < len(NBA_TEAM_IDS):
        result.error = f"{len(NBA_TEAM_IDS) - len(teams)} team lookups failed"
    return result


# ---------------------------------------------------------------------- all

def fetch_all(season: int, get: Getter = http_get) -> List[SourceResult]:
    """Run every source. Athletes and stats need the candidate ids from the futures board."""
    results: List[SourceResult] = []
    board = fetch_futures(season, get)
    results.append(board)
    person_ids: List[str] = []
    if board.ok:
        person_ids = sorted({c["person_id"] for c in convert.convert_futures(_json(board.body))})
    results.append(fetch_athletes(season, person_ids, get))
    results.append(fetch_stats(season, person_ids, get))
    results.append(fetch_standings(season, get))
    results.append(fetch_coaches(season, get))
    return results
