// Shared by all three pages: data loading, number formatting, the move rule,
// the shortlist (stars), the navigation bar and the service worker.

export const LEAGUES = { nba: "NBA", nfl: "NFL", ncaaf: "College football" };

// Every numeric column of data/history.csv, in file order. `fmt` says how to show it.
export const COLUMNS = [
  { key: "odds", label: "Odds", unit: "American odds", fmt: "odds" },
  { key: "implied_prob", label: "Implied prob.", unit: "share of 100%", fmt: "pct" },
  { key: "gp", label: "GP", unit: "games played", fmt: "int" },
  { key: "ppg", label: "PPG", unit: "points per game", fmt: "dec" },
  { key: "rpg", label: "RPG", unit: "rebounds per game", fmt: "dec" },
  { key: "apg", label: "APG", unit: "assists per game", fmt: "dec" },
  { key: "bpg", label: "BPG", unit: "blocks per game", fmt: "dec" },
  { key: "spg", label: "SPG", unit: "steals per game", fmt: "dec" },
  { key: "win_pct", label: "Win %", unit: "share of games won", fmt: "pct" },
  { key: "pass_yds", label: "Pass yds", unit: "passing yards, season", fmt: "int" },
  { key: "rush_yds", label: "Rush yds", unit: "rushing yards, season", fmt: "int" },
  { key: "rec_yds", label: "Rec yds", unit: "receiving yards, season", fmt: "int" },
  { key: "td", label: "TD", unit: "touchdowns passed, rushed or caught", fmt: "int" },
  { key: "tackles", label: "Tackles", unit: "total tackles, season", fmt: "int" },
  { key: "sacks", label: "Sacks", unit: "sacks, season", fmt: "dec" },
  { key: "ints", label: "INT", unit: "interceptions caught, season", fmt: "int" },
  { key: "pts_for", label: "Pts for", unit: "points scored, season", fmt: "int" },
  { key: "pts_against", label: "Pts against", unit: "points allowed, season", fmt: "int" },
];
export const NUMERIC = COLUMNS.map((c) => c.key);
export const COLUMN = Object.fromEntries(COLUMNS.map((c) => [c.key, c]));

const BASKETBALL = ["ppg", "rpg", "apg"];
const OFFENSE = ["pass_yds", "rush_yds", "rec_yds", "td"];
const DEFENSE = ["tackles", "sacks", "ints"];
const TEAM = ["win_pct", "pts_for", "pts_against"];

// The 13 award markets, in display order. `stats` are the columns that market carries
// besides odds and implied probability (same table as AWARD_STATS in tracker/config.py).
export const GROUPS = [
  { league: "nba", award: "mvp", label: "NBA MVP", long: "NBA Most Valuable Player", stats: BASKETBALL, gp: true },
  { league: "nba", award: "roy", label: "NBA ROY", long: "NBA Rookie of the Year", stats: BASKETBALL, gp: true },
  { league: "nba", award: "dpoy", label: "NBA DPOY", long: "NBA Defensive Player of the Year", stats: ["bpg", "spg"], gp: true },
  { league: "nba", award: "coy", label: "NBA COY", long: "NBA Coach of the Year", stats: ["win_pct"], gp: false },
  { league: "nba", award: "finals", label: "NBA Finals", long: "NBA Finals winner", stats: TEAM, gp: true, team: true },
  { league: "nfl", award: "mvp", label: "NFL MVP", long: "NFL Most Valuable Player", stats: OFFENSE, gp: true },
  { league: "nfl", award: "opoy", label: "NFL OPOY", long: "NFL Offensive Player of the Year", stats: OFFENSE, gp: true },
  { league: "nfl", award: "dpoy", label: "NFL DPOY", long: "NFL Defensive Player of the Year", stats: DEFENSE, gp: true },
  { league: "nfl", award: "oroy", label: "NFL OROY", long: "NFL Offensive Rookie of the Year", stats: OFFENSE, gp: true },
  { league: "nfl", award: "droy", label: "NFL DROY", long: "NFL Defensive Rookie of the Year", stats: DEFENSE, gp: true },
  { league: "nfl", award: "sbwin", label: "Super Bowl", long: "Super Bowl winner", stats: TEAM, gp: true, team: true },
  { league: "ncaaf", award: "heisman", label: "Heisman", long: "Heisman Trophy", stats: OFFENSE, gp: true },
  { league: "ncaaf", award: "cfp", label: "CFP champion", long: "College Football Playoff champion", stats: TEAM, gp: true, team: true },
];
for (const g of GROUPS) {
  g.id = `${g.league}-${g.award}`;
  g.columns = ["odds", "implied_prob", ...(g.gp ? ["gp"] : []), ...g.stats];
}
export const GROUP = Object.fromEntries(GROUPS.map((g) => [g.id, g]));
export const groupOf = (row) => GROUP[`${row.league}-${row.award}`];
export const labelOf = (row) => (groupOf(row) ? groupOf(row).label : `${row.league} ${row.award}`);

// ------------------------------------------------------------------ DOM helper

/** el("div", {class: "x", text: "hi"}, [child, ...]). Text always goes in via textContent. */
export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// ------------------------------------------------------------------- CSV / data

/** Parse CSV text (quotes and embedded commas handled) into an array of arrays. */
export function parseCSV(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else quoted = false;
      } else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ",") { row.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.length > 1 || row[0] !== "") rows.push(row);
      row = [];
    } else field += ch;
  }
  if (field !== "" || row.length) { row.push(field); rows.push(row); }
  return rows;
}

/** CSV text -> array of row objects; numeric columns become numbers (null if empty). */
export function parseHistory(text) {
  const [header, ...body] = parseCSV(text);
  if (!header) return [];
  return body.map((cells) => {
    const row = {};
    header.forEach((name, i) => {
      const raw = cells[i] === undefined ? "" : cells[i];
      row[name] = NUMERIC.includes(name) ? (raw === "" ? null : Number(raw)) : raw;
    });
    return row;
  });
}

async function fetchText(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return { text: await response.text(), fromCache: response.headers.get("x-from-cache") === "1" };
}

/** Load both data files. `fromCache` is true when the service worker served saved copies (offline). */
export async function loadData() {
  const [history, status] = await Promise.all([fetchText("data/history.csv"), fetchText("data/status.json")]);
  return {
    rows: parseHistory(history.text),
    status: JSON.parse(status.text),
    fromCache: history.fromCache || status.fromCache,
  };
}

export const datesOf = (rows) => [...new Set(rows.map((r) => r.date))].sort();
export const rowsOn = (rows, date) => rows.filter((r) => r.date === date);

/** The latest day in the history, the day before it, and their rows. */
export function latestAndPrevious(rows) {
  const dates = datesOf(rows);
  const latest = dates[dates.length - 1] || null;
  const previous = dates.length > 1 ? dates[dates.length - 2] : null;
  return { dates, latest, previous, latestRows: latest ? rowsOn(rows, latest) : [], previousRows: previous ? rowsOn(rows, previous) : [] };
}

// --------------------------------------------------------------- the move rule

/**
 * Same rule as tracker/moves.py: move = new implied probability - old, in percentage
 * points, for items priced on both days. Biggest absolute move first (ties by item_id),
 * unchanged items left out, top `n` kept. Also returns items that appeared / disappeared.
 */
export function computeMoves(prevRows, todayRows, n = 10) {
  const prev = new Map(prevRows.map((r) => [r.item_id, r]));
  const today = new Map(todayRows.map((r) => [r.item_id, r]));
  const moves = [];
  for (const [id, now] of today) {
    const old = prev.get(id);
    if (!old || old.implied_prob === null || now.implied_prob === null) continue;
    const change = Math.round((now.implied_prob - old.implied_prob) * 100 * 10000) / 10000;
    if (change === 0) continue;
    moves.push({ item_id: id, item: now.item, award: now.award, old_odds: old.odds, new_odds: now.odds,
      old_prob: old.implied_prob, new_prob: now.implied_prob, change_pp: change, league: now.league });
  }
  moves.sort((a, b) => Math.abs(b.change_pp) - Math.abs(a.change_pp) || (a.item_id < b.item_id ? -1 : 1));
  const byId = (a, b) => (a.item_id < b.item_id ? -1 : 1);
  return {
    moves: moves.slice(0, n),
    appeared: [...today.values()].filter((r) => !prev.has(r.item_id)).sort(byId),
    disappeared: [...prev.values()].filter((r) => !today.has(r.item_id)).sort(byId),
  };
}

// ------------------------------------------------------------------- formatting

export const DASH = "–";

export function fmtValue(key, value) {
  if (value === null || value === undefined || Number.isNaN(value)) return DASH;
  switch (COLUMN[key] ? COLUMN[key].fmt : "dec") {
    case "odds": return (value > 0 ? "+" : "") + value;
    case "pct": return (value * 100).toFixed(1) + "%";
    case "int": return Math.round(value).toLocaleString("en-US");
    default: return value.toFixed(1);
  }
}

/** Change since the previous run, as text with an arrow ("" if nothing to show). */
export function fmtDelta(key, current, previous) {
  if (current === null || previous === null || current === undefined || previous === undefined) return "";
  let diff = current - previous;
  if (Math.abs(diff) < 1e-9) return "";
  let text;
  const fmt = COLUMN[key] ? COLUMN[key].fmt : "dec";
  if (fmt === "pct") {
    diff *= 100;
    text = Math.abs(diff).toFixed(Math.abs(diff) < 0.05 ? 2 : 1) + " pp";
  } else if (fmt === "odds" || fmt === "int") text = Math.abs(Math.round(diff)).toLocaleString("en-US");
  else text = Math.abs(diff).toFixed(Math.abs(diff) < 0.05 ? 2 : 1);
  return (diff > 0 ? "▲" : "▼") + text;
}

export const fmtPP = (pp) => (pp > 0 ? "+" : pp < 0 ? "−" : "") + Math.abs(pp).toFixed(1) + " pp";
export const fmtPct = (p) => (p * 100).toFixed(1) + "%";

export function fmtRunTime(iso) {
  const when = new Date(iso);
  if (Number.isNaN(when.getTime())) return String(iso);
  return when.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) + " (" + iso.replace("T", " ").replace("Z", " UTC") + ")";
}

// ----------------------------------------------------------- shortlist (stars)

const STAR_KEY = "nba-awards:shortlist";

export function getStars() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STAR_KEY) || "[]");
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch (error) {
    return new Set();
  }
}

/** Star or unstar an item; returns true if it is now starred. Survives a reload. */
export function toggleStar(itemId) {
  const stars = getStars();
  const now = !stars.has(itemId);
  if (now) stars.add(itemId); else stars.delete(itemId);
  try { localStorage.setItem(STAR_KEY, JSON.stringify([...stars])); } catch (error) { /* private mode */ }
  return now;
}

// --------------------------------------------------------------------- page chrome

const PAGES = [["index.html", "Today"], ["browse.html", "Browse"], ["trends.html", "Trends"]];

/** The one navigation bar all three pages share. */
export function renderNav(current) {
  const host = document.getElementById("site-nav");
  if (!host) return;
  host.className = "site-nav";
  host.append(el("div", { class: "wrap" }, [
    el("a", { class: "brand", href: "index.html" }, [
      el("img", { src: "assets/icon-192.png", alt: "", width: "28", height: "28" }),
      el("span", { text: "Award Odds" }),
    ]),
    el("nav", { class: "nav-links", "aria-label": "Main" },
      PAGES.map(([href, label]) => el("a", { href, text: label, "aria-current": href === current ? "page" : null }))),
  ]));
}

export function showNotice(message, kind = "info") {
  const main = document.querySelector("main");
  const box = el("div", { class: "notice" + (kind === "error" ? " error" : ""), role: kind === "error" ? "alert" : "status", text: message });
  main.prepend(box);
  return box;
}

export function registerServiceWorker() {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch(() => { /* the site works without it */ });
    });
  }
}

/** Standard start-up for a page: nav, service worker, data, offline notice. */
export async function startPage(current, render) {
  renderNav(current);
  registerServiceWorker();
  try {
    const data = await loadData();
    if (data.fromCache) showNotice("You are offline. Showing the last data this device loaded.");
    render(data);
  } catch (error) {
    showNotice("Could not load the data files (" + error.message + "). Check your connection and reload.", "error");
  }
}
