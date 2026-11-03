// Small SVG chart library (no dependencies, so it works offline).
// Line, horizontal bar (plain or signed) and scatter charts, each with a hover and
// keyboard tooltip, plus a table view of the numbers behind every chart.
//
// Marks follow one spec: 2px lines, bars <= 24px thick with a 4px rounded data end and a
// square baseline end, dots >= 8px with a 2px surface ring, hairline recessive grid.
// Series colors are CSS variables (--s1 ... --s8) so light and dark mode both work.

import { el } from "./common.js";

const NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, children = []) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") node.textContent = value;
    else node.setAttribute(key, String(value));
  }
  for (const child of [].concat(children)) if (child) node.append(child);
  return node;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function shortDate(iso) {
  const [, m, d] = String(iso).split("-");
  return m ? `${MONTHS[Number(m) - 1]} ${Number(d)}` : String(iso);
}

function niceTicks(lo, hi, target = 5) {
  if (!(hi > lo)) { const pad = Math.abs(lo) * 0.05 || 1; lo -= pad; hi += pad; }
  const raw = (hi - lo) / target;
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const norm = raw / mag;
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + step / 1e6; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

const truncate = (text, n) => (text.length > n ? text.slice(0, n - 1) + "…" : text);

/** Redraw `draw(width)` now and whenever the host changes width. */
function responsive(host, draw) {
  let last = -1;
  const run = () => {
    const width = Math.max(260, Math.floor(host.clientWidth));
    if (width === last) return;
    last = width;
    draw(width);
  };
  run();
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(run).observe(host);
  else window.addEventListener("resize", run);
}

// ---------------------------------------------------------------------- tooltip

function tooltipFor(host) {
  const box = el("div", { class: "tooltip", role: "status", hidden: true });
  host.append(box);
  return {
    show(head, rows, x, y) {
      box.replaceChildren(el("div", { class: "t-head", text: head }),
        ...rows.map((r) => el("div", { class: "t-row" }, [
          r.color ? el("span", { class: "t-key", style: `background:${r.color}` }) : null,
          el("span", { class: "t-name", text: r.name }),
          el("span", { class: "t-val", text: r.value }),
        ])));
      box.hidden = false;
      const w = box.offsetWidth, h = box.offsetHeight, hw = host.clientWidth;
      let left = x + 14;
      if (left + w > hw) left = Math.max(0, x - 14 - w);
      box.style.left = left + "px";
      box.style.top = Math.max(0, Math.min(y - 10, host.clientHeight - h)) + "px";
    },
    hide() { box.hidden = true; },
  };
}

const pointerX = (host, event) => event.clientX - host.getBoundingClientRect().left;
const pointerY = (host, event) => event.clientY - host.getBoundingClientRect().top;

// ------------------------------------------------------------------ card helpers

/** A titled card with a chart host inside. Returns {card, host, legendHost}. */
export function chartCard(title, subtitle) {
  const host = el("div", { class: "chart" });
  const legendHost = el("div");
  const card = el("div", { class: "chart-card" }, [
    el("h3", { text: title }),
    subtitle ? el("div", { class: "chart-sub", text: subtitle }) : null,
    legendHost, host,
  ]);
  return { card, host, legendHost };
}

export function emptyChart(host, message) {
  host.replaceChildren(el("div", { class: "empty-chart", text: message }));
}

/** A "show the numbers" table under a chart, so no value is only reachable by hovering. */
export function dataTable(parent, headers, rows) {
  const table = el("table", {}, [
    el("thead", {}, [el("tr", {}, headers.map((h, i) => el("th", { class: i ? "num" : "", scope: "col", text: h })))]),
    el("tbody", {}, rows.map((row) => el("tr", {}, row.map((cell, i) => el("td", { class: i ? "num" : "name", text: cell }))))),
  ]);
  parent.append(el("details", { class: "data-table" }, [
    el("summary", { text: "Show the numbers" }),
    el("div", { class: "table-wrap" }, [table]),
  ]));
}

export function legend(parent, items) {
  parent.replaceChildren();
  if (items.length < 2) return;
  parent.append(el("div", { class: "legend" }, items.map((item) =>
    el("span", {}, [el("i", { style: `background:${item.color}` }), item.name]))));
}

// -------------------------------------------------------------------- line chart

/**
 * series: [{name, color, values: [number|null per x]}]   xLabels: ["2026-11-03", ...]
 * options: {yFormat, ariaLabel, height}
 */
export function lineChart(host, series, xLabels, options = {}) {
  const yFormat = options.yFormat || ((v) => String(v));
  const height = options.height || 260;
  host.replaceChildren();
  const tip = tooltipFor(host);
  const all = series.flatMap((s) => s.values).filter((v) => v !== null && v !== undefined);
  if (!all.length || !xLabels.length) { emptyChart(host, "No values for the selected items."); return; }

  responsive(host, (width) => {
    host.querySelectorAll("svg").forEach((n) => n.remove());
    const directLabels = series.length <= 4 && width >= 560;
    const m = { top: 14, right: directLabels ? 116 : 20, bottom: 30, left: 52 };
    const iw = width - m.left - m.right, ih = height - m.top - m.bottom;
    const ticks = niceTicks(Math.min(...all), Math.max(...all), 4);
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const n = xLabels.length;
    const xAt = (i) => (n > 1 ? m.left + (i * iw) / (n - 1) : m.left + iw / 2);
    const yAt = (v) => m.top + ih - ((v - lo) / (hi - lo || 1)) * ih;

    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, tabindex: 0, role: "img",
      "aria-label": options.ariaLabel || "Line chart. Use the left and right arrow keys to read values by day." });

    for (const t of ticks) {
      root.append(svg("line", { class: "grid", x1: m.left, x2: m.left + iw, y1: yAt(t), y2: yAt(t) }),
        svg("text", { class: "tick", x: m.left - 8, y: yAt(t) + 4, "text-anchor": "end", text: yFormat(t) }));
    }
    root.append(svg("line", { class: "axis", x1: m.left, x2: m.left + iw, y1: m.top + ih, y2: m.top + ih }));
    const maxLabels = Math.max(2, Math.floor(iw / 80));
    const every = Math.max(1, Math.ceil(n / maxLabels));
    for (let i = 0; i < n; i++) {
      if (i % every !== 0 && i !== n - 1) continue;
      if (i !== n - 1 && n - 1 - i < every) continue;   // keep clear of the last label
      root.append(svg("text", { class: "tick", x: xAt(i), y: height - 8, "text-anchor": n > 1 && i === 0 ? "start" : n > 1 && i === n - 1 ? "end" : "middle", text: shortDate(xLabels[i]) }));
    }

    const ends = [];
    for (const s of series) {
      const color = s.color;
      let path = "", open = false;
      s.values.forEach((v, i) => {
        if (v === null || v === undefined) { open = false; return; }
        path += `${open ? "L" : "M"}${xAt(i).toFixed(1)} ${yAt(v).toFixed(1)}`;
        open = true;
      });
      root.append(svg("path", { d: path, fill: "none", style: `stroke:${color}`, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
      s.values.forEach((v, i) => {  // dots on isolated points (a line has no segment to show them)
        if (v === null || v === undefined) return;
        const lonely = (s.values[i - 1] ?? null) === null && (s.values[i + 1] ?? null) === null;
        if (lonely) root.append(svg("circle", { cx: xAt(i), cy: yAt(v), r: 4, style: `fill:${color};stroke:var(--surface)`, "stroke-width": 2 }));
      });
      let lastIdx = -1;
      s.values.forEach((v, i) => { if (v !== null && v !== undefined) lastIdx = i; });
      if (lastIdx >= 0) {
        const v = s.values[lastIdx];
        root.append(svg("circle", { cx: xAt(lastIdx), cy: yAt(v), r: 4, style: `fill:${color};stroke:var(--surface)`, "stroke-width": 2 }));
        ends.push({ y: yAt(v), name: s.name, x: xAt(lastIdx) });
      }
    }
    if (directLabels) {  // label line ends only where labels do not collide
      ends.sort((a, b) => a.y - b.y);
      let prev = -99;
      for (const e of ends) {
        if (e.y - prev < 14) continue;
        prev = e.y;
        root.append(svg("text", { class: "label", x: e.x + 10, y: e.y + 4, text: truncate(e.name, 16) }));
      }
    }

    const cross = svg("line", { class: "cross", y1: m.top, y2: m.top + ih, visibility: "hidden" });
    const hoverDots = svg("g");
    root.append(cross, hoverDots);
    const focusAt = (i, px, py) => {
      cross.setAttribute("x1", xAt(i)); cross.setAttribute("x2", xAt(i)); cross.setAttribute("visibility", "visible");
      hoverDots.replaceChildren();
      const rows = [];
      for (const s of series) {
        const v = s.values[i];
        if (v === null || v === undefined) continue;
        hoverDots.append(svg("circle", { cx: xAt(i), cy: yAt(v), r: 4, style: `fill:${s.color};stroke:var(--surface)`, "stroke-width": 2 }));
        rows.push({ color: s.color, name: s.name, value: yFormat(v) });
      }
      tip.show(shortDate(xLabels[i]) + " (" + xLabels[i] + ")", rows.length ? rows : [{ name: "No values", value: "" }], px ?? xAt(i), py ?? m.top + 20);
    };
    const clear = () => { cross.setAttribute("visibility", "hidden"); hoverDots.replaceChildren(); tip.hide(); };
    const nearest = (px) => { let best = 0; for (let i = 1; i < n; i++) if (Math.abs(xAt(i) - px) < Math.abs(xAt(best) - px)) best = i; return best; };
    root.addEventListener("pointermove", (e) => focusAt(nearest(pointerX(host, e)), pointerX(host, e), pointerY(host, e)));
    root.addEventListener("pointerleave", clear);
    let kbd = n - 1;
    root.addEventListener("focus", () => focusAt(kbd));
    root.addEventListener("blur", clear);
    root.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") kbd = Math.max(0, kbd - 1);
      else if (e.key === "ArrowRight") kbd = Math.min(n - 1, kbd + 1);
      else return;
      e.preventDefault(); focusAt(kbd);
    });
    host.prepend(root);
  });
}

// --------------------------------------------------------------------- bar chart

function barPath(x0, x1, y, h, r) {
  const dir = x1 >= x0 ? 1 : -1;
  const len = Math.abs(x1 - x0);
  const rr = Math.min(r, len, h / 2);
  // square at the baseline end (x0), rounded at the data end (x1)
  return `M${x0} ${y} L${x1 - dir * rr} ${y} Q${x1} ${y} ${x1} ${y + rr} L${x1} ${y + h - rr} Q${x1} ${y + h} ${x1 - dir * rr} ${y + h} L${x0} ${y + h} Z`;
}

/**
 * bars: [{label, value, detail?}]   options: {format, signed, color, ariaLabel}
 * Plain bars grow right from a baseline at 0; signed bars grow right (blue) or left (red).
 */
export function barChart(host, bars, options = {}) {
  const format = options.format || String;
  const signed = !!options.signed;
  const color = options.color || "var(--s1)";
  host.replaceChildren();
  const tip = tooltipFor(host);
  if (!bars.length) { emptyChart(host, "Nothing to show yet."); return; }

  responsive(host, (width) => {
    host.querySelectorAll("svg").forEach((n) => n.remove());
    const rowH = 30, barH = 18;
    const labelChars = width < 480 ? 16 : width < 760 ? 26 : 38;
    const labelW = Math.min(width * 0.46, labelChars * 6.4 + 8);
    const reserve = 74;  // room for the value written at the bar tip
    const m = { top: 4, bottom: 4, left: labelW + 8, right: signed ? reserve : reserve };
    const innerLeft = m.left + (signed ? reserve : 0);
    const iw = width - innerLeft - m.right;
    const height = m.top + m.bottom + bars.length * rowH;
    const maxAbs = Math.max(...bars.map((b) => Math.abs(b.value)), 1e-9);
    const x0 = signed ? innerLeft + iw / 2 : innerLeft;
    const scale = (signed ? iw / 2 : iw) / maxAbs;

    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, role: "img", "aria-label": options.ariaLabel || "Bar chart" });
    bars.forEach((b, i) => {
      const y = m.top + i * rowH, by = y + (rowH - barH) / 2;
      const x1 = x0 + b.value * scale;
      const fill = signed ? (b.value >= 0 ? "var(--up)" : "var(--down)") : color;
      root.append(svg("text", { class: "label", x: m.left - 10 + (signed ? 0 : 0), y: y + rowH / 2 + 4, "text-anchor": "end", text: truncate(b.label, labelChars) }));
      if (Math.abs(b.value) * scale >= 1) root.append(svg("path", { d: barPath(x0, x1, by, barH, 4), style: `fill:${fill}` }));
      const labelRight = b.value >= 0;
      root.append(svg("text", { class: "value", x: x1 + (labelRight ? 8 : -8), y: y + rowH / 2 + 4, "text-anchor": labelRight ? "start" : "end", text: format(b.value) }));
      const hit = svg("rect", { class: "mark", x: 0, y, width, height: rowH, fill: "transparent", tabindex: 0,
        role: "img", "aria-label": `${b.label}: ${format(b.value)}${b.detail ? ", " + b.detail : ""}` });
      const show = (px, py) => tip.show(b.label, [{ name: b.detail || "Value", value: format(b.value) }], px, py);
      hit.addEventListener("pointermove", (e) => show(pointerX(host, e), pointerY(host, e)));
      hit.addEventListener("pointerleave", () => tip.hide());
      hit.addEventListener("focus", () => show(x1, y + rowH / 2));
      hit.addEventListener("blur", () => tip.hide());
      root.append(hit);
    });
    root.append(svg("line", { class: "axis", x1: x0, x2: x0, y1: m.top, y2: height - m.bottom }));
    host.prepend(root);
  });
}

// ------------------------------------------------------------------ scatter chart

/**
 * points: [{x, y, label}]   options: {xFormat, yFormat, xTitle, yTitle, ariaLabel}
 * The pointer finds the nearest dot, so the hit target is far larger than the 10px dot.
 */
export function scatterChart(host, points, options = {}) {
  const xFormat = options.xFormat || String, yFormat = options.yFormat || String;
  host.replaceChildren();
  const tip = tooltipFor(host);
  if (!points.length) { emptyChart(host, "Not enough values to plot yet."); return; }

  responsive(host, (width) => {
    host.querySelectorAll("svg").forEach((n) => n.remove());
    const height = 300;
    const m = { top: 14, right: 24, bottom: 46, left: 56 };
    const iw = width - m.left - m.right, ih = height - m.top - m.bottom;
    const xt = niceTicks(Math.min(...points.map((p) => p.x)), Math.max(...points.map((p) => p.x)), 5);
    const yt = niceTicks(Math.min(...points.map((p) => p.y)), Math.max(...points.map((p) => p.y)), 4);
    const xAt = (v) => m.left + ((v - xt[0]) / (xt[xt.length - 1] - xt[0] || 1)) * iw;
    const yAt = (v) => m.top + ih - ((v - yt[0]) / (yt[yt.length - 1] - yt[0] || 1)) * ih;

    const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, width, height, tabindex: 0, role: "img",
      "aria-label": options.ariaLabel || "Scatter chart. Use the arrow keys to move between points." });
    for (const t of yt) root.append(svg("line", { class: "grid", x1: m.left, x2: m.left + iw, y1: yAt(t), y2: yAt(t) }),
      svg("text", { class: "tick", x: m.left - 8, y: yAt(t) + 4, "text-anchor": "end", text: yFormat(t) }));
    for (const t of xt) root.append(svg("text", { class: "tick", x: xAt(t), y: m.top + ih + 16, "text-anchor": "middle", text: xFormat(t) }));
    root.append(svg("line", { class: "axis", x1: m.left, x2: m.left + iw, y1: m.top + ih, y2: m.top + ih }));
    if (options.xTitle) root.append(svg("text", { class: "axis-title", x: m.left + iw / 2, y: height - 6, "text-anchor": "middle", text: options.xTitle }));
    if (options.yTitle) root.append(svg("text", { class: "axis-title", x: 12, y: m.top + ih / 2, "text-anchor": "middle", transform: `rotate(-90 12 ${m.top + ih / 2})`, text: options.yTitle }));

    for (const p of points) root.append(svg("circle", { cx: xAt(p.x), cy: yAt(p.y), r: 5, style: "fill:var(--s1);stroke:var(--surface)", "stroke-width": 2 }));
    // name only the few extremes, so labels never pile up
    const named = [...points].sort((a, b) => b.y - a.y).slice(0, 3);
    const taken = [];
    for (const p of named) {
      const lx = xAt(p.x) + 9, ly = yAt(p.y) + 4;
      if (taken.some((t) => Math.abs(t.x - lx) < 90 && Math.abs(t.y - ly) < 13)) continue;
      taken.push({ x: lx, y: ly });
      const flip = lx + 100 > width;
      root.append(svg("text", { class: "label", x: flip ? xAt(p.x) - 9 : lx, y: ly, "text-anchor": flip ? "end" : "start", text: truncate(p.label, 28) }));
    }
    const ring = svg("circle", { r: 8, fill: "none", style: "stroke:var(--ink)", "stroke-width": 2, visibility: "hidden" });
    root.append(ring);
    const focusPoint = (p, px, py) => {
      ring.setAttribute("cx", xAt(p.x)); ring.setAttribute("cy", yAt(p.y)); ring.setAttribute("visibility", "visible");
      tip.show(p.label, [{ name: options.xTitle || "x", value: xFormat(p.x) }, { name: options.yTitle || "y", value: yFormat(p.y) }], px ?? xAt(p.x), py ?? yAt(p.y));
    };
    const clear = () => { ring.setAttribute("visibility", "hidden"); tip.hide(); };
    root.addEventListener("pointermove", (e) => {
      const px = pointerX(host, e), py = pointerY(host, e);
      let best = null, bestD = Infinity;
      for (const p of points) { const d = Math.hypot(xAt(p.x) - px, yAt(p.y) - py); if (d < bestD) { bestD = d; best = p; } }
      if (best && bestD <= 48) focusPoint(best, px, py); else clear();
    });
    root.addEventListener("pointerleave", clear);
    const order = [...points].sort((a, b) => a.x - b.x);
    let k = 0;
    root.addEventListener("focus", () => focusPoint(order[k]));
    root.addEventListener("blur", clear);
    root.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowUp") k = Math.min(order.length - 1, k + 1);
      else if (e.key === "ArrowLeft" || e.key === "ArrowDown") k = Math.max(0, k - 1);
      else return;
      e.preventDefault(); focusPoint(order[k]);
    });
    host.prepend(root);
  });
}
