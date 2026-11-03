"""data/status.json: a description of the latest run."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from . import build, moves
from .config import RAW_DIR, STATUS_PATH


def make_status(run_time: dt.datetime, date: str, sources: Sequence[Dict[str, Any]],
                rows: Sequence[Dict[str, Any]], raw_dir: Path = RAW_DIR) -> Dict[str, Any]:
    """Build the status dict.

    items          rows for this run's date (0 if the futures board failed).
    new_today      item_ids on today's board that were not on the previous day's.
    gone_today     item_ids on the previous day's board that are not on today's.
    Both lists are empty on the first day and on a day with no rows, because there
    is nothing to compare (a failed source must not make every item look "gone").
    """
    dates = build.raw_dates(raw_dir)
    _, prev_rows, today_rows = moves.split_days(rows, date)
    new_ids: List[str] = []
    gone_ids: List[str] = []
    if prev_rows and today_rows:
        diff = moves.compute_moves(prev_rows, today_rows)
        new_ids = [r["item_id"] for r in diff["appeared"]]
        gone_ids = [r["item_id"] for r in diff["disappeared"]]
    return {
        "run_time": run_time.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first_run_date": dates[0] if dates else date,
        "days_with_success": len(dates),
        "items": len(today_rows),
        "new_today": new_ids,
        "gone_today": gone_ids,
        "sources": [{"name": s["name"], "ok": bool(s["ok"]), "count": int(s["count"])}
                    for s in sources],
    }


def write_status(status: Dict[str, Any], path: Path = STATUS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(status, handle, indent=2)
        handle.write("\n")
