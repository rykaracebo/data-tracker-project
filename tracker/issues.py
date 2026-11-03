"""The daily GitHub Issue:  python -m tracker.issues

Opens an Issue titled with the date that lists the biggest moves since the
previous run and any item that appeared or disappeared, and closes the previous
day's Issue. It is opened every day, even with no changes. Running again on the
same day updates that day's Issue instead of opening a second one.

Needs the `gh` CLI with a token (GH_TOKEN) that can write Issues; the workflow
provides both.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import build, moves
from .config import MOVES_LISTED, award_label

TITLE_SUFFIX = "award odds moves"
TITLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} " + re.escape(TITLE_SUFFIX) + "$")


def title_for(date: str) -> str:
    return f"{date} {TITLE_SUFFIX}"


def _odds(value: Any) -> str:
    text = str(value) if value not in (None, "") else "n/a"
    return f"+{text}" if text.lstrip("-").isdigit() and not text.startswith("-") else text


def _pct(prob: float) -> str:
    return f"{prob * 100:.1f}%"


def _label(row: Dict[str, Any]) -> str:
    return f"{row.get('item', '')} ({award_label(row.get('league', ''), row.get('award', ''))})"


def render_body(date: str, previous: Optional[str], result: Dict[str, Any],
                status: Optional[Dict[str, Any]] = None) -> str:
    """The Issue text (Markdown)."""
    lines = [f"## Award odds, {date}", ""]
    if previous is None:
        lines += ["This is the first day with data, so there is nothing to compare yet.", ""]
    else:
        lines += [f"Compared with the previous run on **{previous}**. Move = change in implied "
                  f"probability, in percentage points; the top {MOVES_LISTED} moves are listed.", ""]
        if result["moves"]:
            lines += ["### Biggest moves", "",
                      "| Item | Old odds | New odds | Old prob | New prob | Move |",
                      "|---|---|---|---|---|---|"]
            for m in result["moves"]:
                lines.append(f"| {_label(m)} | {_odds(m['old_odds'])} | {_odds(m['new_odds'])} | "
                             f"{_pct(m['old_prob'])} | {_pct(m['new_prob'])} | {m['change_pp']:+.2f} pp |")
            lines.append("")
        else:
            lines += ["No item's implied probability changed since the previous run.", ""]
        if result["appeared"]:
            lines += ["### Appeared", ""] + [f"- {_label(r)}, now {_odds(r.get('odds'))}"
                                             for r in result["appeared"]] + [""]
        if result["disappeared"]:
            lines += ["### Disappeared", ""] + [f"- {_label(r)}, was {_odds(r.get('odds'))}"
                                                for r in result["disappeared"]] + [""]
        if not result["appeared"] and not result["disappeared"]:
            lines += ["No item appeared or disappeared.", ""]
    if status:
        failed = [s["name"] for s in status.get("sources", []) if not s.get("ok")]
        lines += ["---",
                  f"{status.get('items', 0)} items today; failed sources: "
                  f"{', '.join(failed) if failed else 'none'}.", ""]
    return "\n".join(lines)


# --------------------------------------------------------------- gh helpers

GH = Callable[[Sequence[str]], str]


def run_gh(args: Sequence[str]) -> str:
    done = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return done.stdout


def sync_issue(date: str, body: str, gh: GH = run_gh) -> Dict[str, Any]:
    """Create or update today's Issue, then close earlier days' open Issues."""
    title = title_for(date)
    listing = json.loads(gh(["issue", "list", "--state", "all", "--limit", "200",
                             "--json", "number,title,state"]) or "[]")
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
        handle.write(body)
        body_file = handle.name
    try:
        today = next((i for i in listing if i["title"] == title), None)
        if today is None:
            gh(["issue", "create", "--title", title, "--body-file", body_file])
            action = "created"
        else:
            gh(["issue", "edit", str(today["number"]), "--body-file", body_file])
            if today["state"].upper() != "OPEN":
                gh(["issue", "reopen", str(today["number"])])
            action = "updated"
    finally:
        os.unlink(body_file)
    closed: List[int] = []
    for issue in listing:
        if (issue["state"].upper() == "OPEN" and TITLE_RE.match(issue["title"])
                and issue["title"] != title):
            gh(["issue", "close", str(issue["number"]), "--comment", f"Superseded by {title}."])
            closed.append(issue["number"])
    return {"action": action, "closed": closed}


def main(gh: GH = run_gh) -> int:
    status_path = build.HISTORY_PATH.parent / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    date = status["run_time"][:10]
    rows = build.read_history()
    previous, prev_rows, today_rows = moves.split_days(rows, date)
    result = moves.compute_moves(prev_rows, today_rows) if today_rows else \
        {"moves": [], "appeared": [], "disappeared": []}
    outcome = sync_issue(date, render_body(date, previous if prev_rows else None, result, status), gh)
    print(f"issue {title_for(date)!r}: {outcome['action']}; closed {outcome['closed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
