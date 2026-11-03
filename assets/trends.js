// Trends page: a report on the history file. Every number here is computed in the browser
// from data/history.csv, so the page changes as the history grows.
import {
  COLUMN, DASH, GROUP, GROUPS, datesOf, el, fmtPP, fmtPct, fmtValue, labelOf, rowsOn, startPage,
} from "./common.js";
import { barChart, chartCard, dataTable, legend, lineChart, scatterChart } from "./charts.js";

const MAX_ITEMS = 8;
const pct1 = (p) => (p * 100).toFixed(1) + "%";

// ------------------------------------------------------------------- statistics

/** Pearson correlation of [{x, y}] (null if fewer than 3 points or no spread). */
function pearson(points) {
  const n = points.length;
  if (n < 3) return null;
  const mx = points.reduce((s, p) => s + p.x, 0) / n, my = points.reduce((s, p) => s + p.y, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (const p of points) { sxy += (p.x - mx) * (p.y - my); sxx += (p.x - mx) ** 2; syy += (p.y - my) ** 2; }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null;
}

const strength = (r) => (Math.abs(r) >= 0.6 ? "closely" : Math.abs(r) >= 0.3 ? "somewhat" : "barely");

/** Items priced on both days: [{row, old, change_pp}] sorted by change, biggest rise first. */
function changesBetween(oldRows, newRows) {
  const old = new Map(oldRows.map((r) => [r.item_id, r]));
  const out = [];
  for (const row of newRows) {
    const before = old.get(row.item_id);
    if (before && before.implied_prob !== null && row.implied_prob !== null) {
      out.push({ row, old: before, change_pp: (row.implied_prob - before.implied_prob) * 100 });
    }
  }
  return out.sort((a, b) => b.change_pp - a.change_pp || (a.row.item_id < b.row.item_id ? -1 : 1));
}

// -------------------------------------------------------------- finding builder

function finding({ heading, text = [], how, chart }) {
  const section = el("section", { class: "finding" }, [el("h2", { text: heading })]);
  for (const paragraph of text) section.append(el("p", { text: paragraph }));
  if (how) section.append(el("p", { class: "how", text: "How it is computed: " + how }));
  if (chart) {
    const { card, host, legendHost } = chartCard(chart.title, chart.sub);
    section.append(card);
    chart.draw(host, legendHost);
    if (chart.table) dataTable(card, chart.table.headers, chart.table.rows);
  }
  return section;
}

const waiting = (title, why) => finding({
  heading: `${title}: waiting for data`,
  text: [why],
  how: "this section fills in by itself as the daily runs add days to the history.",
});

// ---------------------------------------------------------------------- findings

function risers(rows, dates) {
  const title = "Who has risen or fallen the most since the first run";
  if (dates.length < 2) return waiting(title, `The history has one day so far (${dates[0] || "none"}). A rise or fall needs at least two days to compare.`);
  const first = dates[0], last = dates[dates.length - 1];
  const changes = changesBetween(rowsOn(rows, first), rowsOn(rows, last));
  if (!changes.length) return waiting(title, "No item has a price on both the first and the last day.");
  const up = changes[0], down = changes[changes.length - 1];
  const name = (c) => `${c.row.item} (${labelOf(c.row)})`;
  const heading = up.change_pp > 0
    ? `${name(up)} has risen the most since the first run: ${fmtPP(up.change_pp)}`
    : `No item has gained probability since the first run; ${name(down)} fell the most`;
  const bars = [...changes.slice(0, 5), ...changes.slice(-5)].filter((c, i, all) => all.findIndex((d) => d.row.item_id === c.row.item_id) === i);
  return finding({
    heading,
    text: [
      `${name(up)} went from ${pct1(up.old.implied_prob)} (${fmtValue("odds", up.old.odds)}) on ${first} to ${pct1(up.row.implied_prob)} (${fmtValue("odds", up.row.odds)}) on ${last}. `
      + `The biggest fall was ${name(down)}, ${fmtPP(down.change_pp)}, from ${pct1(down.old.implied_prob)} to ${pct1(down.row.implied_prob)}. `
      + `${changes.length} items were priced on both days.`,
    ],
    how: `each item's implied_prob on the last day (${last}) minus its implied_prob on the first day (${first}), in percentage points, for the ${changes.length} items that have a price on both days. The chart shows the five biggest rises and the five biggest falls.`,
    chart: {
      title: "Change in implied probability since the first run", sub: `${first} to ${last}, percentage points`,
      draw: (host) => barChart(host, bars.map((c) => ({ label: name(c), value: Math.round(c.change_pp * 100) / 100, detail: `${pct1(c.old.implied_prob)} to ${pct1(c.row.implied_prob)}` })), {
        signed: true, format: (v) => fmtPP(v), ariaLabel: "Bar chart of the biggest rises and falls in implied probability",
      }),
      table: { headers: ["Item", "Market", "First", "Last", "Change"], rows: changes.map((c) => [c.row.item, labelOf(c.row), pct1(c.old.implied_prob), pct1(c.row.implied_prob), fmtPP(c.change_pp)]) },
    },
  });
}

function busiestDay(rows, dates) {
  const title = "The day the odds moved the most";
  if (dates.length < 2) return waiting(title, `With one day of history (${dates[0] || "none"}) there is no day-to-day movement yet.`);
  const days = [];
  for (let i = 1; i < dates.length; i++) {
    const changes = changesBetween(rowsOn(rows, dates[i - 1]), rowsOn(rows, dates[i]));
    days.push({
      date: dates[i], prev: dates[i - 1], compared: changes.length,
      moved: changes.filter((c) => Math.abs(c.change_pp) > 1e-9).length,
      total: changes.reduce((s, c) => s + Math.abs(c.change_pp), 0),
      top: [...changes].sort((a, b) => Math.abs(b.change_pp) - Math.abs(a.change_pp))[0],
    });
  }
  const best = days.reduce((a, b) => (b.total > a.total ? b : a));
  return finding({
    heading: `${best.date} was the busiest day: the board moved ${best.total.toFixed(1)} points in total`,
    text: [
      `On ${best.date}, ${best.moved} of the ${best.compared} items that were also priced on ${best.prev} changed probability.`
      + (best.top ? ` The biggest single move was ${best.top.row.item} (${labelOf(best.top.row)}), ${fmtPP(best.top.change_pp)}.` : "")
      + ` Across all ${days.length} day-to-day steps the average is ${(days.reduce((s, d) => s + d.total, 0) / days.length).toFixed(1)} points.`,
    ],
    how: "for each day after the first, add up the absolute change in implied_prob (percentage points) of every item priced both on that day and on the day before.",
    chart: {
      title: "Total movement per day", sub: "sum of absolute changes in implied probability, percentage points",
      draw: (host) => lineChart(host, [{ name: "Total movement", color: "var(--s1)", values: days.map((d) => d.total) }], days.map((d) => d.date), {
        yFormat: (v) => v.toFixed(1), ariaLabel: "Line chart of total odds movement per day",
      }),
      table: { headers: ["Day", "Compared with", "Items moved", "Total movement (pp)"], rows: days.map((d) => [d.date, d.prev, `${d.moved} of ${d.compared}`, d.total.toFixed(2)]) },
    },
  });
}

function lopsided(rows, dates) {
  const last = dates[dates.length - 1];
  const today = rowsOn(rows, last);
  const markets = GROUPS.map((group) => {
    const items = today.filter((r) => r.league === group.league && r.award === group.award && r.implied_prob !== null);
    if (!items.length) return null;
    const fav = items.reduce((a, b) => (b.implied_prob > a.implied_prob ? b : a));
    return { group, fav, total: items.reduce((s, r) => s + r.implied_prob, 0), n: items.length };
  }).filter(Boolean).sort((a, b) => b.fav.implied_prob - a.fav.implied_prob);
  if (!markets.length) return waiting("How one-sided each race is", "There are no priced items yet.");
  const top = markets[0], tight = markets[markets.length - 1];
  const totals = markets.map((m) => m.total);
  return finding({
    heading: `${top.group.label} is the most one-sided race: ${top.fav.item} is at ${pct1(top.fav.implied_prob)}`,
    text: [
      `The tightest race is ${tight.group.label}, where the favorite, ${tight.fav.item}, is only at ${pct1(tight.fav.implied_prob)}. `
      + `Each market's prices add up to more than 100%, from ${(Math.min(...totals) * 100).toFixed(0)}% to ${(Math.max(...totals) * 100).toFixed(0)}%, `
      + "and the excess is the sportsbook's margin built into the prices.",
    ],
    how: `on the last day (${last}), for each market take the highest implied_prob among its items (the favorite's share) and the sum of implied_prob over all its items (the total). ${markets.length} markets have prices.`,
    chart: {
      title: "The favorite's share in each market", sub: `implied probability of the favorite, ${last}`,
      draw: (host) => barChart(host, markets.map((m) => ({ label: `${m.group.label}: ${m.fav.item}`, value: m.fav.implied_prob, detail: `${m.n} candidates, prices total ${pct1(m.total)}` })), {
        format: pct1, ariaLabel: "Bar chart of the favorite's implied probability in each market",
      }),
      table: { headers: ["Market", "Favorite", "Share", "All prices total", "Candidates"], rows: markets.map((m) => [m.group.label, m.fav.item, pct1(m.fav.implied_prob), pct1(m.total), String(m.n)]) },
    },
  });
}

/** Do a stat and the price line up? (one market, one stat) */
function statVsPrice(rows, dates, groupId, stat, noun) {
  const group = GROUP[groupId], last = dates[dates.length - 1];
  const all = rowsOn(rows, last).filter((r) => r.league === group.league && r.award === group.award);
  const have = all.filter((r) => r[stat] !== null && r.implied_prob !== null);
  const title = `${group.long}: do ${noun} line up with the price`;
  const r = pearson(have.map((p) => ({ x: p[stat], y: p.implied_prob })));
  if (r === null) return waiting(title, `Only ${have.length} of ${all.length} candidates have ${COLUMN[stat].label} so far, and at least three are needed.`);
  const leader = [...have].sort((a, b) => b[stat] - a[stat])[0];
  const fav = [...have].sort((a, b) => b.implied_prob - a.implied_prob)[0];
  const rankOf = (item) => 1 + have.filter((p) => p.implied_prob > item.implied_prob).length;
  const relation = r >= 0 ? "follow" : "run against";
  return finding({
    heading: `${group.long} prices ${strength(r)} ${relation} ${noun}: correlation ${r.toFixed(2)}`,
    text: [
      `${have.length} of ${all.length} candidates have a ${COLUMN[stat].label} value. `
      + (leader.item_id === fav.item_id
        ? `${leader.item} leads with ${fmtValue(stat, leader[stat])} and is also the favorite, at ${pct1(leader.implied_prob)}.`
        : `${leader.item} leads with ${fmtValue(stat, leader[stat])} and is priced ${pct1(leader.implied_prob)}, number ${rankOf(leader)} of ${have.length} on price. `
          + `The favorite, ${fav.item}, is at ${pct1(fav.implied_prob)} with ${fmtValue(stat, fav[stat])}.`),
    ],
    how: `the Pearson correlation between ${COLUMN[stat].label} (${COLUMN[stat].unit}) and implied_prob over the ${have.length} candidates on the last day (${last}) that have both values. +1 means more of the stat always means a shorter price, 0 means no link, -1 means the opposite.`,
    chart: {
      title: `${COLUMN[stat].label} against implied probability`, sub: `${group.long}, ${last}; each dot is one candidate`,
      draw: (host) => scatterChart(host, have.map((p) => ({ x: p[stat], y: p.implied_prob * 100, label: p.item })), {
        xTitle: COLUMN[stat].label, yTitle: "Implied probability", xFormat: (v) => fmtValue(stat, v), yFormat: (v) => v.toFixed(0) + "%",
        ariaLabel: `Scatter chart of ${COLUMN[stat].label} against implied probability for ${group.long}`,
      }),
      table: { headers: ["Item", COLUMN[stat].label, "Implied prob."], rows: [...have].sort((a, b) => b.implied_prob - a.implied_prob).map((p) => [p.item, fmtValue(stat, p[stat]), pct1(p.implied_prob)]) },
    },
  });
}

function teamRecords(rows, dates) {
  const last = dates[dates.length - 1];
  const results = ["nfl-sbwin", "nba-finals", "ncaaf-cfp"].map((id) => {
    const group = GROUP[id];
    const have = rowsOn(rows, last).filter((r) => r.league === group.league && r.award === group.award && r.win_pct !== null && r.implied_prob !== null);
    return { group, have, r: pearson(have.map((p) => ({ x: p.win_pct, y: p.implied_prob }))) };
  });
  const main = results[0];
  if (main.r === null) return waiting("Do win-loss records predict the title odds", "The Super Bowl market has too few teams with a record yet.");
  const best = [...main.have].sort((a, b) => b.win_pct - a.win_pct || b.implied_prob - a.implied_prob)[0];
  const tied = main.have.filter((p) => p.win_pct === best.win_pct).length;
  const fav = [...main.have].sort((a, b) => b.implied_prob - a.implied_prob)[0];
  const summary = results.filter((x) => x.r !== null).map((x) => `${x.group.label} ${x.r.toFixed(2)} (${x.have.length} teams)`).join(", ");
  return finding({
    heading: `Super Bowl odds ${strength(main.r)} follow win-loss record: correlation ${main.r.toFixed(2)}`,
    text: [
      `Among ${main.have.length} NFL teams, ${tied > 1 ? `${tied} teams share the best record, ${pct1(best.win_pct)}; the highest-priced of them is ${best.item} at ${pct1(best.implied_prob)}` : `${best.item} has the best record (${pct1(best.win_pct)}) and is priced ${pct1(best.implied_prob)}`}. `
      + `The favorite, ${fav.item}, is at ${pct1(fav.implied_prob)} and its record is ${pct1(fav.win_pct)}. `
      + `Correlations of win percentage with title probability: ${summary}.`,
    ],
    how: `the Pearson correlation between win_pct and implied_prob over the teams in each title market on the last day (${last}). Only teams with both values count.`,
    chart: {
      title: "Win percentage against Super Bowl probability", sub: `NFL teams, ${last}; each dot is one team`,
      draw: (host) => scatterChart(host, main.have.map((p) => ({ x: p.win_pct, y: p.implied_prob * 100, label: p.item })), {
        xTitle: "Win %", yTitle: "Implied probability", xFormat: (v) => (v * 100).toFixed(0) + "%", yFormat: (v) => v.toFixed(0) + "%",
        ariaLabel: "Scatter chart of win percentage against Super Bowl probability",
      }),
      table: { headers: ["Market", "Teams", "Correlation"], rows: results.map((x) => [x.group.label, String(x.have.length), x.r === null ? DASH : x.r.toFixed(2)]) },
    },
  });
}

function coachRecords(rows, dates) {
  const last = dates[dates.length - 1];
  const coaches = rowsOn(rows, last).filter((r) => r.league === "nba" && r.award === "coy" && r.win_pct !== null && r.implied_prob !== null);
  if (coaches.length < 2) return waiting("NBA Coach of the Year and team record", "Fewer than two coaches have a team record so far.");
  const byRecord = [...coaches].sort((a, b) => b.win_pct - a.win_pct || b.implied_prob - a.implied_prob || (a.item_id < b.item_id ? -1 : 1));
  const best = byRecord[0];
  const tied = coaches.filter((c) => c.win_pct === best.win_pct).length;
  const favorite = [...coaches].sort((a, b) => b.implied_prob - a.implied_prob)[0];
  const rank = 1 + coaches.filter((c) => c.implied_prob > best.implied_prob).length;
  const recordPhrase = tied > 1 ? `shares the best record (${pct1(best.win_pct)})` : `has the best record (${pct1(best.win_pct)})`;
  return finding({
    heading: rank === 1
      ? `${best.item} ${recordPhrase} and is the Coach of the Year favorite`
      : `${best.item} ${recordPhrase} but is only number ${rank} of ${coaches.length} for Coach of the Year`,
    text: [
      `${best.item} (${best.team}) is priced ${fmtValue("odds", best.odds)}, ${pct1(best.implied_prob)}. `
      + (favorite.item_id === best.item_id ? "" : `The favorite is ${favorite.item}, whose team is ${pct1(favorite.win_pct)}.`)
      + (tied > 1 ? ` ${tied} coaches' teams share that record; the one with the shortest price is shown.` : ""),
    ],
    how: `on the last day (${last}), rank the ${coaches.length} NBA Coach of the Year candidates by win_pct (their team's win percentage) and by implied_prob, and compare the two rankings.`,
    chart: {
      title: "Team win percentage of each Coach of the Year candidate", sub: `${last}; the price is in brackets`,
      draw: (host) => barChart(host, byRecord.map((c) => ({ label: `${c.item} (${fmtValue("odds", c.odds)})`, value: c.win_pct, detail: `${pct1(c.implied_prob)} implied` })), {
        format: pct1, ariaLabel: "Bar chart of team win percentage for each Coach of the Year candidate",
      }),
      table: { headers: ["Coach", "Team", "Win %", "Odds", "Implied prob."], rows: byRecord.map((c) => [c.item, c.team || DASH, pct1(c.win_pct), fmtValue("odds", c.odds), pct1(c.implied_prob)]) },
    },
  });
}

// ------------------------------------------------------------ item picker + charts

function setupPicker(rows, dates) {
  const picker = document.getElementById("picker");
  const chartsHost = document.getElementById("series-charts");
  const last = dates[dates.length - 1];
  const groups = GROUPS.filter((g) => rows.some((r) => r.league === g.league && r.award === g.award));
  const state = { groupId: groups[0] ? groups[0].id : null, selected: [], slots: new Map(), filter: "" };

  const seriesOf = new Map();  // item_id -> {date -> row}
  for (const r of rows) {
    if (!seriesOf.has(r.item_id)) seriesOf.set(r.item_id, new Map());
    seriesOf.get(r.item_id).set(r.date, r);
  }
  const candidates = () => rowsOn(rows, last)
    .filter((r) => state.groupId === `${r.league}-${r.award}`)
    .sort((a, b) => (b.implied_prob ?? -1) - (a.implied_prob ?? -1) || (a.item_id < b.item_id ? -1 : 1));

  const colorOf = (id) => `var(--s${state.slots.get(id)})`;
  function select(id, on) {
    if (on && !state.selected.includes(id) && state.selected.length < MAX_ITEMS) {
      const used = new Set(state.slots.values());
      let slot = 1;
      while (used.has(slot)) slot++;
      state.slots.set(id, slot);
      state.selected.push(id);
    } else if (!on) {
      state.selected = state.selected.filter((x) => x !== id);
      state.slots.delete(id);
    }
  }
  function topFive() {
    state.selected = []; state.slots = new Map();
    candidates().slice(0, 5).forEach((r) => select(r.item_id, true));
  }

  function drawPicker() {
    picker.replaceChildren(
      el("div", { class: "controls", style: "margin-top:0" }, [
        el("div", { class: "field" }, [el("label", { for: "t-market", text: "Market" }),
          el("select", { id: "t-market", onchange: (e) => { state.groupId = e.target.value; state.filter = ""; topFive(); drawPicker(); drawCharts(); } },
            groups.map((g) => el("option", { value: g.id, text: g.label, selected: g.id === state.groupId })))]),
        el("div", { class: "field" }, [el("label", { for: "t-filter", text: "Find an item" }),
          el("input", { id: "t-filter", type: "search", value: state.filter, placeholder: "type a name",
            oninput: (e) => { state.filter = e.target.value.trim().toLowerCase(); drawList(); } })]),
        el("button", { class: "btn", type: "button", text: "Top 5 favorites", onclick: () => { topFive(); drawPicker(); drawCharts(); } }),
        el("button", { class: "btn", type: "button", text: "Clear", onclick: () => { state.selected = []; state.slots = new Map(); drawPicker(); drawCharts(); } }),
      ]),
      el("div", { class: "count-line", id: "t-count", role: "status" }),
      el("div", { class: "picker-list", id: "t-list" }),
    );
    document.getElementById("t-filter").value = state.filter;
    drawList();
  }

  function drawList() {
    const list = candidates().filter((r) => !state.filter || r.item.toLowerCase().includes(state.filter));
    const full = state.selected.length >= MAX_ITEMS;
    document.getElementById("t-count").textContent = `${state.selected.length} of ${MAX_ITEMS} items selected${full ? " (the most you can compare)" : ""}.`;
    document.getElementById("t-list").replaceChildren(...list.map((r) => {
      const on = state.selected.includes(r.item_id);
      return el("label", {}, [
        el("input", { type: "checkbox", checked: on, disabled: !on && full,
          onchange: (e) => { select(r.item_id, e.target.checked); drawList(); drawCharts(); } }),
        on ? el("span", { class: "swatch", style: `background:${colorOf(r.item_id)}` }) : null,
        el("span", { text: `${r.item} ${fmtValue("odds", r.odds)}` }),
      ]);
    }));
  }

  function drawCharts() {
    const group = GROUP[state.groupId];
    chartsHost.replaceChildren();
    if (!group) return;
    if (!state.selected.length) {
      chartsHost.append(el("p", { class: "muted", text: "Select at least one item to see its charts." }));
      return;
    }
    const names = new Map(state.selected.map((id) => [id, (seriesOf.get(id).get(last) || [...seriesOf.get(id).values()][0]).item]));
    for (const key of group.columns) {
      const series = state.selected.map((id) => ({
        name: names.get(id), color: colorOf(id),
        values: dates.map((d) => { const row = seriesOf.get(id).get(d); return row ? row[key] : null; }),
      }));
      const { card, host, legendHost } = chartCard(COLUMN[key].label, `${COLUMN[key].unit}, by day`);
      chartsHost.append(card);
      legend(legendHost, series);
      lineChart(host, series, dates, {
        yFormat: (v) => fmtValue(key, v),
        ariaLabel: `Line chart of ${COLUMN[key].label} by day for ${series.map((s) => s.name).join(", ")}`,
      });
      dataTable(card, ["Day", ...series.map((s) => s.name)], dates.map((d, i) => [d, ...series.map((s) => fmtValue(key, s.values[i]))]));
    }
  }

  if (!state.groupId) { picker.append(el("p", { class: "muted", text: "No data yet." })); return; }
  topFive();
  drawPicker();
  drawCharts();
}

// ------------------------------------------------------------------------ start

startPage("trends.html", ({ rows }) => {
  const dates = datesOf(rows);
  const lede = document.getElementById("trend-lede");
  if (!dates.length) { lede.textContent = "The history is empty. Trends appear after the first run."; return; }
  lede.textContent = `${rows.length.toLocaleString("en-US")} rows over ${dates.length} day${dates.length === 1 ? "" : "s"} (${dates[0]} to ${dates[dates.length - 1]}). `
    + "Every number on this page is computed in your browser from data/history.csv.";
  setupPicker(rows, dates);
  const host = document.getElementById("findings");
  host.replaceChildren(
    risers(rows, dates),
    busiestDay(rows, dates),
    lopsided(rows, dates),
    statVsPrice(rows, dates, "nba-mvp", "ppg", "scoring"),
    statVsPrice(rows, dates, "nfl-mvp", "td", "touchdowns"),
    statVsPrice(rows, dates, "ncaaf-heisman", "td", "touchdowns"),
    teamRecords(rows, dates),
    coachRecords(rows, dates),
  );
});
