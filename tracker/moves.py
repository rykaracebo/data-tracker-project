"""The move rule: what counts as an item "moving" between two days.

Rule (also stated in the README):
  move = new implied probability - old implied probability, in percentage points.
  An item is compared only if it has a price on both days. The items with the
  biggest absolute move are listed, largest first (ties broken by item_id), up
  to MOVES_LISTED of them. Items with no change are not listed. An item_id that
  is on the board today but was not on the previous day "appeared"; one that was
  on the previous day but is not today "disappeared".
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .config import MOVES_LISTED


def _float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def split_days(rows: Sequence[Dict[str, Any]], date: str) -> Tuple[Optional[str], List[Dict], List[Dict]]:
    """(previous date, previous day's rows, rows of `date`) from the full history."""
    dates = sorted({r["date"] for r in rows})
    earlier = [d for d in dates if d < date]
    previous = earlier[-1] if earlier else None
    prev_rows = [r for r in rows if r["date"] == previous] if previous else []
    today_rows = [r for r in rows if r["date"] == date]
    return previous, prev_rows, today_rows


def compute_moves(prev_rows: Sequence[Dict[str, Any]], today_rows: Sequence[Dict[str, Any]],
                  top_n: int = MOVES_LISTED) -> Dict[str, Any]:
    """Apply the move rule. Returns {'moves': [...], 'appeared': [...], 'disappeared': [...]}."""
    prev = {r["item_id"]: r for r in prev_rows}
    today = {r["item_id"]: r for r in today_rows}

    moves = []
    for item_id, new in today.items():
        old = prev.get(item_id)
        if old is None:
            continue
        old_p, new_p = _float(old.get("implied_prob")), _float(new.get("implied_prob"))
        if old_p is None or new_p is None:
            continue
        change = round((new_p - old_p) * 100.0, 4)
        if change == 0:
            continue
        moves.append({
            "item_id": item_id,
            "item": new.get("item", ""),
            "award": new.get("award", ""),
            "old_odds": old.get("odds", ""),
            "new_odds": new.get("odds", ""),
            "old_prob": old_p,
            "new_prob": new_p,
            "change_pp": change,
        })
    moves.sort(key=lambda m: (-abs(m["change_pp"]), m["item_id"]))

    appeared = [today[i] for i in sorted(today) if i not in prev]
    disappeared = [prev[i] for i in sorted(prev) if i not in today]
    return {"moves": moves[:top_n], "appeared": appeared, "disappeared": disappeared}
