// Browse page: filters, name search, sort on every numeric column, stars saved in the browser.
import {
  COLUMN, DASH, GROUPS, LEAGUES, el, fmtValue, getStars, labelOf, latestAndPrevious, startPage, toggleStar,
} from "./common.js";

const ALL = "all";

startPage("browse.html", ({ rows }) => {
  const { latest, latestRows } = latestAndPrevious(rows);
  const els = {
    q: document.getElementById("q"), league: document.getElementById("f-league"),
    award: document.getElementById("f-award"), team: document.getElementById("f-team"),
    sortCol: document.getElementById("sort-col"), sortDir: document.getElementById("sort-dir"),
    stars: document.getElementById("only-stars"), starCount: document.getElementById("star-count"),
    reset: document.getElementById("reset"), count: document.getElementById("count"),
    table: document.getElementById("table"),
  };
  const state = { sort: "implied_prob", dir: "desc" };
  let stars = getStars();

  const option = (value, text) => el("option", { value, text });
  els.league.replaceChildren(option(ALL, "All leagues"), ...Object.entries(LEAGUES).map(([k, v]) => option(k, v)));
  const teams = [...new Set(latestRows.map((r) => r.team).filter(Boolean))].sort();
  els.team.replaceChildren(option(ALL, "All teams"), ...teams.map((t) => option(t, t)));

  function fillAwards() {
    const keep = els.award.value || ALL;
    const groups = GROUPS.filter((g) => els.league.value === ALL || g.league === els.league.value);
    els.award.replaceChildren(option(ALL, "All markets"), ...groups.map((g) => option(g.id, g.label)));
    els.award.value = groups.some((g) => g.id === keep) ? keep : ALL;
  }

  function filtered() {
    const needle = els.q.value.trim().toLowerCase();
    return latestRows.filter((r) =>
      (els.league.value === ALL || r.league === els.league.value)
      && (els.award.value === ALL || `${r.league}-${r.award}` === els.award.value)
      && (els.team.value === ALL || r.team === els.team.value)
      && (!needle || r.item.toLowerCase().includes(needle))
      && (!els.stars.checked || stars.has(r.item_id)));
  }

  function sorted(list) {
    const sign = state.dir === "asc" ? 1 : -1;
    return [...list].sort((a, b) => {
      const x = a[state.sort], y = b[state.sort];
      if (x === null && y === null) return a.item_id < b.item_id ? -1 : 1;
      if (x === null) return 1;      // empty values always sort last, up or down
      if (y === null) return -1;
      return (x - y) * sign || (a.item_id < b.item_id ? -1 : 1);
    });
  }

  function render() {
    const list = sorted(filtered());
    // only the numeric columns that have a value somewhere in the current view
    const cols = Object.keys(COLUMN).filter((k) => list.some((r) => r[k] !== null));
    if (!cols.includes(state.sort) && cols.length) state.sort = cols.includes("implied_prob") ? "implied_prob" : cols[0];

    els.sortCol.replaceChildren(...cols.map((k) => option(k, COLUMN[k].label)));
    els.sortCol.value = state.sort;
    els.sortDir.textContent = state.dir === "asc" ? "▲ Low to high" : "▼ High to low";
    els.starCount.textContent = stars.size ? `(${stars.size})` : "";

    const head = el("tr", {}, [
      el("th", { scope: "col" }, [el("span", { class: "sr-only", text: "Shortlist" })]),
      el("th", { scope: "col", text: "Item" }), el("th", { scope: "col", text: "Market" }), el("th", { scope: "col", text: "Team" }),
      ...cols.map((k) => el("th", {
        class: "num", scope: "col", title: COLUMN[k].unit,
        "aria-sort": state.sort === k ? (state.dir === "asc" ? "ascending" : "descending") : null,
      }, [el("button", {
        class: "sort", type: "button", title: `Sort by ${COLUMN[k].label} (${COLUMN[k].unit})`,
        onclick: () => {
          if (state.sort === k) state.dir = state.dir === "asc" ? "desc" : "asc";
          else { state.sort = k; state.dir = "desc"; }
          render();
        },
      }, [COLUMN[k].label, el("span", { class: "arrow", "aria-hidden": "true", text: state.sort === k ? (state.dir === "asc" ? "▲" : "▼") : "↕" })])])),
    ]);

    const body = list.map((r) => {
      const starred = stars.has(r.item_id);
      const star = el("button", {
        class: "star", type: "button", "aria-pressed": String(starred),
        "aria-label": `${starred ? "Remove" : "Add"} ${r.item} ${starred ? "from" : "to"} shortlist`,
        text: starred ? "★" : "☆",
        onclick: () => { toggleStar(r.item_id); stars = getStars(); render(); },
      });
      return el("tr", {}, [
        el("td", {}, [star]),
        el("td", { class: "name", text: r.item }),
        el("td", {}, [el("span", { class: "award-tag", text: labelOf(r) })]),
        el("td", { text: r.team || DASH }),
        ...cols.map((k) => el("td", { class: "num", text: fmtValue(k, r[k]) })),
      ]);
    });
    els.table.tHead.replaceChildren(head);
    els.table.tBodies[0].replaceChildren(...(body.length ? body : [
      el("tr", {}, [el("td", { colspan: String(4 + cols.length), class: "muted", text: "No items match these filters." })])]));
    els.count.textContent = `Showing ${list.length} of ${latestRows.length} items from ${latest || "no run yet"}.`;
  }

  els.league.addEventListener("change", () => { fillAwards(); render(); });
  for (const key of ["award", "team", "stars"]) els[key].addEventListener("change", render);
  els.q.addEventListener("input", render);
  els.sortCol.addEventListener("change", () => { state.sort = els.sortCol.value; render(); });
  els.sortDir.addEventListener("click", () => { state.dir = state.dir === "asc" ? "desc" : "asc"; render(); });
  els.reset.addEventListener("click", () => {
    els.q.value = ""; els.league.value = ALL; els.team.value = ALL; els.stars.checked = false;
    fillAwards(); state.sort = "implied_prob"; state.dir = "desc"; render();
  });
  fillAwards();
  render();
});
