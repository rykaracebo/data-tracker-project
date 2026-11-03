"""The move rule: change in implied probability, biggest first."""
from __future__ import annotations

from tracker import moves


def row(item_id, prob, odds="+100", date="2026-11-03", item=None, award="mvp", league="nba"):
    return {"date": date, "item_id": item_id, "item": item or item_id, "league": league, "award": award,
            "odds": odds, "implied_prob": "" if prob is None else str(prob)}


def test_move_is_change_in_percentage_points():
    prev = [row("mvp-1", 0.25, "+300")]
    today = [row("mvp-1", 0.30, "+233")]
    result = moves.compute_moves(prev, today)
    assert result["moves"][0]["change_pp"] == 5.0
    assert result["moves"][0]["old_odds"] == "+300" and result["moves"][0]["new_odds"] == "+233"


def test_biggest_absolute_move_first_up_or_down():
    prev = [row("a", 0.10), row("b", 0.40), row("c", 0.20)]
    today = [row("a", 0.12), row("b", 0.30), row("c", 0.21)]
    ids = [m["item_id"] for m in moves.compute_moves(prev, today)["moves"]]
    assert ids == ["b", "a", "c"]  # -10pp, +2pp, +1pp


def test_ties_break_by_item_id():
    prev = [row("b", 0.10), row("a", 0.10)]
    today = [row("b", 0.20), row("a", 0.20)]
    assert [m["item_id"] for m in moves.compute_moves(prev, today)["moves"]] == ["a", "b"]


def test_unchanged_items_are_not_listed():
    prev = [row("a", 0.10), row("b", 0.10)]
    today = [row("a", 0.10), row("b", 0.11)]
    assert [m["item_id"] for m in moves.compute_moves(prev, today)["moves"]] == ["b"]


def test_only_top_n_are_listed():
    prev = [row(f"i{n:02d}", 0.10) for n in range(15)]
    today = [row(f"i{n:02d}", 0.10 + (n + 1) / 1000) for n in range(15)]
    assert len(moves.compute_moves(prev, today, top_n=10)["moves"]) == 10
    assert moves.compute_moves(prev, today, top_n=10)["moves"][0]["item_id"] == "i14"


def test_items_without_a_price_on_either_day_are_skipped():
    prev = [row("a", None), row("b", 0.10)]
    today = [row("a", 0.20), row("b", None)]
    assert moves.compute_moves(prev, today)["moves"] == []


def test_appeared_and_disappeared_items():
    prev = [row("old", 0.10), row("same", 0.10)]
    today = [row("same", 0.10), row("new", 0.05)]
    result = moves.compute_moves(prev, today)
    assert [r["item_id"] for r in result["appeared"]] == ["new"]
    assert [r["item_id"] for r in result["disappeared"]] == ["old"]
    assert result["moves"] == []


def test_no_changes_at_all():
    rows = [row("a", 0.10), row("b", 0.20)]
    assert moves.compute_moves(rows, rows) == {"moves": [], "appeared": [], "disappeared": []}


def test_split_days_picks_the_day_before():
    history = [row("a", 0.1, date="2026-11-01"), row("a", 0.1, date="2026-11-03"),
               row("a", 0.1, date="2026-11-05")]
    previous, prev_rows, today_rows = moves.split_days(history, "2026-11-05")
    assert previous == "2026-11-03"
    assert [r["date"] for r in prev_rows] == ["2026-11-03"]
    assert [r["date"] for r in today_rows] == ["2026-11-05"]


def test_split_days_on_the_first_day():
    previous, prev_rows, _ = moves.split_days([row("a", 0.1)], "2026-11-03")
    assert previous is None and prev_rows == []
