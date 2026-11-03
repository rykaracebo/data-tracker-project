"""One daily run:  python -m tracker.run

  1. call every source, save what it returned to data/raw/<date>/<source>.json.gz
  2. rebuild data/history.csv from the raw files
  3. write data/status.json
  (the Issue and the commit are separate workflow steps)

A second run on the same UTC date replaces that day's raw files and rebuilds the
history, so each day counts once.
"""
from __future__ import annotations

import datetime as dt
import gzip
import json
import shutil
import sys
from pathlib import Path
from typing import Callable, Dict, List, Optional

from . import build, status
from .config import HISTORY_PATH, RAW_DIR, RUN_LOG_PATH, STATUS_PATH, season_for
from .fetch import SourceResult, fetch_all


def write_raw(raw_dir: Path, date: str, results: List[SourceResult]) -> None:
    """Replace the day's raw files with this run's successful sources."""
    folder = raw_dir / date
    if folder.exists():
        shutil.rmtree(folder)  # a second run replaces the day; a failed source leaves no file
    for result in results:
        if result.ok and result.body is not None:
            folder.mkdir(parents=True, exist_ok=True)
            # mtime=0 keeps the gzip bytes identical for identical input
            (folder / f"{result.name}.{result.ext}.gz").write_bytes(gzip.compress(result.body, mtime=0))


def append_log(path: Path, run_time: dt.datetime, date: str, results: List[SourceResult]) -> None:
    """One JSON line per run with every source's outcome, errors included."""
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_time": run_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": date,
        "sources": [{"name": r.name, "ok": r.ok, "count": r.count, "error": r.error} for r in results],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def run(now: Optional[dt.datetime] = None,
        fetcher: Callable[[int], List[SourceResult]] = fetch_all,
        raw_dir: Path = RAW_DIR, history_path: Path = HISTORY_PATH,
        status_path: Path = STATUS_PATH, log_path: Path = RUN_LOG_PATH) -> Dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    date = now.strftime("%Y-%m-%d")

    results = fetcher(season_for(now.date()))            # 1. call every source
    write_raw(raw_dir, date, results)
    rows = build.build_history(raw_dir, history_path)    # 2. build the history from raw files
    summary = status.make_status(now, date, [vars(r) for r in results], rows, raw_dir)
    status.write_status(summary, status_path)            # 3. write the status file
    append_log(log_path, now, date, results)
    return summary


if __name__ == "__main__":
    summary = run()
    for source in summary["sources"]:
        print(f"{'ok  ' if source['ok'] else 'FAIL'} {source['name']:<10} {source['count']}")
    print(f"{summary['items']} items on {summary['run_time']}; "
          f"{summary['days_with_success']} day(s) with data")
    sys.exit(0)
