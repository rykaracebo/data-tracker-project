"""The daily Issue: one per day, updated on a re-run, previous day closed."""
from __future__ import annotations

import json

from tracker import issues, moves


class FakeGH:
    """Records `gh` calls and serves a pretend issue list."""
    def __init__(self, existing=()):
        self.existing = list(existing)
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[:2] == ["issue", "list"]:
            return json.dumps(self.existing)
        return ""

    def verbs(self):
        return [c[1] for c in self.calls if c[0] == "issue" and c[1] != "list"]


def row(item_id, prob, odds="+100", item=None):
    return {"item_id": item_id, "item": item or item_id, "award": "mvp", "odds": odds,
            "implied_prob": str(prob)}


def test_first_day_opens_an_issue_and_closes_nothing():
    gh = FakeGH()
    out = issues.sync_issue("2026-11-03", "body", gh)
    assert out == {"action": "created", "closed": []}
    create = next(c for c in gh.calls if c[1] == "create")
    assert create[create.index("--title") + 1] == "2026-11-03 NBA award odds moves"


def test_new_day_closes_the_previous_days_open_issue():
    gh = FakeGH([{"number": 7, "title": "2026-11-03 NBA award odds moves", "state": "OPEN"},
                 {"number": 3, "title": "2026-11-02 NBA award odds moves", "state": "CLOSED"},
                 {"number": 5, "title": "Unrelated bug", "state": "OPEN"}])
    out = issues.sync_issue("2026-11-04", "body", gh)
    assert out == {"action": "created", "closed": [7]}
    closes = [c for c in gh.calls if c[1] == "close"]
    assert [c[2] for c in closes] == ["7"]          # only the open dated issue, not the unrelated one


def test_second_run_the_same_day_updates_instead_of_opening_another():
    gh = FakeGH([{"number": 9, "title": "2026-11-04 NBA award odds moves", "state": "OPEN"}])
    out = issues.sync_issue("2026-11-04", "new body", gh)
    assert out == {"action": "updated", "closed": []}
    assert gh.verbs() == ["edit"]


def test_a_closed_issue_for_today_is_reopened_on_rerun():
    gh = FakeGH([{"number": 9, "title": "2026-11-04 NBA award odds moves", "state": "CLOSED"}])
    issues.sync_issue("2026-11-04", "x", gh)
    assert gh.verbs() == ["edit", "reopen"]


def test_body_lists_moves_with_old_and_new_values():
    prev = [row("mvp-1", 0.25, "+300", "Ann Alpha"), row("mvp-2", 0.5, "-100", "Bo Beta")]
    today = [row("mvp-1", 0.30, "+233", "Ann Alpha"), row("mvp-2", 0.5, "-100", "Bo Beta")]
    body = issues.render_body("2026-11-04", "2026-11-03", moves.compute_moves(prev, today))
    assert "Ann Alpha (MVP)" in body and "+300" in body and "+233" in body
    assert "25.0%" in body and "30.0%" in body and "+5.00 pp" in body
    assert "Bo Beta" not in body                    # unchanged items are not listed


def test_body_lists_items_that_appeared_or_disappeared():
    result = moves.compute_moves([row("old", 0.1, "+900", "Old Guy")], [row("new", 0.1, "+800", "New Guy")])
    body = issues.render_body("2026-11-04", "2026-11-03", result)
    assert "### Appeared" in body and "New Guy" in body
    assert "### Disappeared" in body and "Old Guy" in body


def test_body_on_a_day_with_no_changes_still_says_so():
    rows = [row("a", 0.1)]
    body = issues.render_body("2026-11-04", "2026-11-03", moves.compute_moves(rows, rows))
    assert "No item's implied probability changed" in body
    assert "No item appeared or disappeared" in body


def test_body_on_the_first_day():
    body = issues.render_body("2026-11-03", None, {"moves": [], "appeared": [], "disappeared": []})
    assert "first day with data" in body


def test_body_mentions_failed_sources():
    status = {"items": 4, "sources": [{"name": "stats", "ok": False, "count": 0},
                                      {"name": "futures", "ok": True, "count": 4}]}
    body = issues.render_body("2026-11-03", None, {"moves": [], "appeared": [], "disappeared": []}, status)
    assert "failed sources: stats" in body
