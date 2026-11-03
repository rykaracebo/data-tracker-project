// Today page: last run, source status, counts, biggest moves, latest values with changes.
import {
  DASH, COLUMN, GROUPS, LEAGUES, computeMoves, el, fmtDelta, fmtPP, fmtPct, fmtRunTime, fmtValue,
  groupOf, labelOf, latestAndPrevious, startPage,
} from "./common.js";

const CHECK = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 4.8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const CROSS = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>';

function icon(markup) {  // the markup is a fixed constant above, never data
  const holder = document.createElement("span");
  holder.innerHTML = markup;
  return holder.firstChild;
}

function tile(label, value, sub) {
  return el("div", { class: "tile" }, [
    el("div", { class: "label", text: label }),
    el("div", { class: "value", text: String(value) }),
    sub ? el("div", { class: "sub", text: sub }) : null,
  ]);
}

function idList(ids) {
  if (!ids.length) return "none";
  const shown = ids.slice(0, 2).join(", ");
  return ids.length > 2 ? `${shown} and ${ids.length - 2} more` : shown;
}

function renderTiles(status, latest) {
  document.getElementById("tiles").replaceChildren(
    tile("Last run", status.run_time.slice(0, 10), status.run_time.slice(11, 16) + " UTC"),
    tile("Items", status.items, "on the latest run"),
    tile("Days with data", status.days_with_success, "since " + status.first_run_date),
    tile("New today", status.new_today.length, idList(status.new_today)),
    tile("Gone today", status.gone_today.length, idList(status.gone_today)),
  );
}

function renderSources(status) {
  document.getElementById("sources").replaceChildren(...status.sources.map((s) =>
    el("li", {}, [
      el("span", { class: "badge " + (s.ok ? "ok" : "fail") }, [
        icon(s.ok ? CHECK : CROSS), el("span", { text: s.ok ? "OK" : "Failed" }),
      ]),
      el("span", { class: "name", text: s.name }),
      el("span", { class: "count", text: s.count + (s.count === 1 ? " item" : " items") }),
    ])));
}

function renderMoves(rows, previous, latestRows, previousRows) {
  const note = document.getElementById("moves-note");
  const host = document.getElementById("moves");
  if (!previous) {
    note.textContent = "This is the first day with data, so there is nothing to compare yet. Moves appear after the next run.";
    host.replaceChildren();
    return;
  }
  const result = computeMoves(previousRows, latestRows, 10);
  note.textContent = `Change in implied probability since ${previous}, in percentage points. The ten biggest moves are shown.`;
  const parts = [];
  if (result.moves.length) {
    const head = el("tr", {}, ["Item", "Market", "Old odds", "New odds", "Old prob.", "New prob.", "Move"].map((h, i) =>
      el("th", { class: i > 1 ? "num" : "", scope: "col", text: h })));
    const body = result.moves.map((m) => el("tr", {}, [
      el("td", { class: "name", text: m.item }),
      el("td", {}, [el("span", { class: "award-tag", text: labelOf(m) })]),
      el("td", { class: "num", text: fmtValue("odds", m.old_odds) }),
      el("td", { class: "num", text: fmtValue("odds", m.new_odds) }),
      el("td", { class: "num", text: fmtPct(m.old_prob) }),
      el("td", { class: "num", text: fmtPct(m.new_prob) }),
      el("td", { class: "num", text: (m.change_pp > 0 ? "▲ " : "▼ ") + fmtPP(m.change_pp) }),
    ]));
    parts.push(el("div", { class: "table-wrap" }, [el("table", {}, [el("thead", {}, [head]), el("tbody", {}, body)])]));
  } else {
    parts.push(el("p", { text: "No item's implied probability changed since the previous run." }));
  }
  if (result.appeared.length) parts.push(el("p", { class: "lede", text: "Appeared: " + result.appeared.map((r) => `${r.item} (${labelOf(r)})`).join(", ") }));
  if (result.disappeared.length) parts.push(el("p", { class: "lede", text: "Disappeared: " + result.disappeared.map((r) => `${r.item} (${labelOf(r)})`).join(", ") }));
  host.replaceChildren(...parts);
}

function groupTable(group, rows, prevById) {
  const sorted = [...rows].sort((a, b) => (b.implied_prob ?? -1) - (a.implied_prob ?? -1) || (a.item_id < b.item_id ? -1 : 1));
  const showTeam = !group.team;
  const head = el("tr", {}, [
    el("th", { scope: "col", text: group.team ? "Team" : "Item" }),
    showTeam ? el("th", { scope: "col", text: "Team" }) : null,
    ...group.columns.map((key) => el("th", { class: "num", scope: "col", title: COLUMN[key].unit, text: COLUMN[key].label })),
  ]);
  const body = sorted.map((row) => {
    const prev = prevById.get(row.item_id);
    return el("tr", {}, [
      el("td", { class: "name", text: row.item }),
      showTeam ? el("td", { text: row.team || DASH }) : null,
      ...group.columns.map((key) => {
        const delta = prev ? fmtDelta(key, row[key], prev[key]) : "";
        return el("td", { class: "num" }, [fmtValue(key, row[key]), delta ? el("span", { class: "delta", text: delta }) : null]);
      }),
    ]);
  });
  return el("div", { class: "table-wrap" }, [el("table", {}, [
    el("caption", { class: "sr-only", text: group.long + ", latest values" }),
    el("thead", {}, [head]), el("tbody", {}, body)])]);
}

function renderLatest(latestRows, previousRows, league) {
  const prevById = new Map(previousRows.map((r) => [r.item_id, r]));
  const host = document.getElementById("latest");
  const sections = [];
  for (const group of GROUPS) {
    if (league !== "all" && group.league !== league) continue;
    const rows = latestRows.filter((r) => r.league === group.league && r.award === group.award);
    if (!rows.length) continue;
    sections.push(el("details", { class: "group", open: true }, [
      el("summary", {}, [el("strong", { text: group.long }), el("span", { class: "muted", text: `  ${rows.length} items` })]),
      groupTable(group, rows, prevById),
    ]));
  }
  host.replaceChildren(...(sections.length ? sections : [el("p", { class: "muted", text: "No items for this league on the latest run." })]));
}

startPage("index.html", ({ rows, status }) => {
  const { latest, previous, latestRows, previousRows } = latestAndPrevious(rows);
  document.getElementById("asof").textContent = latest
    ? `Odds for ${latest}. Last run ${fmtRunTime(status.run_time)}.`
    : "There is no data yet. The first run will fill this page.";
  renderTiles(status, latest);
  renderSources(status);
  renderMoves(rows, previous, latestRows, previousRows);

  const chips = document.getElementById("league-chips");
  const options = [["all", "All leagues"], ...Object.entries(LEAGUES)];
  let current = "all";
  const draw = () => {
    chips.replaceChildren(...options.map(([key, label]) => el("button", {
      class: "btn", type: "button", "aria-pressed": String(key === current), text: label,
      onclick: () => { current = key; draw(); renderLatest(latestRows, previousRows, current); },
    })));
  };
  draw();
  renderLatest(latestRows, previousRows, current);
});
