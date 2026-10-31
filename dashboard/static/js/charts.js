// Chart components, ported one to one from docs/design/usage-stack/tools/gen3.py.
// They keep the old class names, so app.css applies unchanged, and they take plain data.
// Tick steps for daybars come from the server (usage.py); nice_ticks was not ported.

import { h, s } from "./h.js";
import { t, fmtTokens, fmtTick, fmtDay, fmtHour, pct } from "./format.js";

// The first four models get the categorical colors. Any other model draws hatched ("cat-other").
export const MODEL_CLASS = {
  "claude-opus-5-5": "cat-1",
  "claude-sonnet-5-5": "cat-2",
  "claude-haiku-5-5": "cat-3",
  "claude-fable-5-1": "cat-4",
};

function isListed(model) {
  return Object.prototype.hasOwnProperty.call(MODEL_CLASS, model);
}

export function modelClass(model) {
  return isListed(model) ? MODEL_CLASS[model] : "cat-other";
}

// The four token kinds, in price order, with the ramp class each one draws in.
export function kinds() {
  return [
    { key: "cache_read", name: t("k_cache_read"), cls: "rk-1" },
    { key: "input", name: t("k_input"), cls: "rk-2" },
    { key: "cache_write", name: t("k_cache_write"), cls: "rk-3" },
    { key: "output", name: t("k_output"), cls: "rk-4" },
  ];
}

// Pattern ids must be unique in the page. Every page renders at once and hidden sections do not
// resolve a url(#id) that points inside them.
let patternCount = 0;
function patternId(base) {
  patternCount += 1;
  return base + "-" + patternCount;
}

function hatchDefs(id) {
  return s("defs", null,
    s("pattern", { id, patternUnits: "userSpaceOnUse", width: 5, height: 5, patternTransform: "rotate(45)" },
      s("rect", { width: 5, height: 5, class: "pt-bg" }),
      s("rect", { width: 2, height: 5, class: "pt-fg" })));
}

// segments: [{ label, value, cls }]. Unlisted models carry cls "cat-other" and draw hatched.
export function ring(segments, centre, word, kind = "r") {
  const total = segments.reduce((sum, seg) => sum + seg.value, 0) || 1;
  const r = 46;
  const width = 13;
  const circumference = 2 * Math.PI * r;
  const gap = 2.0;
  const id = patternId("oth-" + kind);
  const svg = s("svg", {
    class: "ring", viewBox: "0 0 120 120", width: 160, height: 160, role: "img", "aria-label": centre + " " + word,
  }, hatchDefs(id), s("circle", { cx: 60, cy: 60, r, class: "ring-track", "stroke-width": width }));
  let start = 0;
  for (const seg of segments) {
    if (seg.value <= 0) continue;
    const length = (circumference * seg.value) / total;
    const dash = Math.max(length - gap, 0.6);
    svg.appendChild(s("circle", {
      cx: 60, cy: 60, r, class: "rseg " + seg.cls, "stroke-width": width,
      "stroke-dasharray": dash.toFixed(2) + " " + (circumference - dash).toFixed(2),
      "stroke-dashoffset": (-start).toFixed(2),
      stroke: seg.cls === "cat-other" ? "url(#" + id + ")" : null,
    }, s("title", null, seg.label)));
    start += length;
  }
  svg.appendChild(s("text", { x: 60, y: 58, class: "ring-n", "text-anchor": "middle" }, centre));
  svg.appendChild(s("text", { x: 60, y: 73, class: "ring-w", "text-anchor": "middle" }, word));
  return svg;
}

// rows: [{ swatch, label, cells: [node or text] }]; cols: the column names for screen readers.
export function legendRows(rows, cols) {
  return h("table", { class: "lg" },
    h("thead", { class: "sr" }, h("tr", null, h("th", null, t("lg_name")), cols.map((c) => h("th", null, c)))),
    h("tbody", null, rows.map((row) => h("tr", null,
      h("th", { scope: "row", class: row.swatch === "cat-other" ? "wrap" : null },
        h("span", { class: "swatch " + row.swatch, "aria-hidden": "true" }), row.label),
      row.cells.map((cell) => h("td", null, cell))))));
}

// rows: [{ label, a, sub }] where a holds tokens and the four kinds. Bars share one scale.
export function stackedTokens(rows) {
  const max = rows.reduce((m, row) => Math.max(m, row.a.tokens), 0) || 1;
  const parts = kinds();
  return h("div", { class: "sbars" }, rows.map((row) => h("div", { class: "sb-row" },
    h("div", { class: "sb-l" }, h("span", { class: "sb-n" }, row.label), row.sub ? h("span", { class: "sb-s" }, row.sub) : null),
    h("div", { class: "sb-bar" }, parts.filter((k) => row.a[k.key] > 0).map((k) =>
      h("span", { class: "sb-seg " + k.cls, style: { width: ((100 * row.a[k.key]) / max).toFixed(2) + "%" } },
        h("span", { class: "sr" }, k.name + " " + fmtTokens(row.a[k.key]))))),
    h("div", { class: "sb-v" }, fmtTokens(row.a.tokens)))));
}

// Always with totals: every stacked bar keeps its legend (one anatomy on every page).
export function kindsLegend(a) {
  return h("ul", { class: "klg" }, kinds().map((k) => h("li", null,
    h("span", { class: "swatch " + k.cls, "aria-hidden": "true" }), k.name, " ",
    h("span", { class: "muted" }, fmtTokens(a[k.key])))));
}

// rows: [{ label, value, text }], one series on the track.
export function hbars(rows) {
  const max = rows.reduce((m, row) => Math.max(m, row.value || 0), 0) || 1;
  return h("div", { class: "hbars" }, rows.map((row) => h("div", { class: "hb-row" },
    h("span", { class: "hb-l" }, row.label),
    h("div", { class: "hb-bar" }, h("span", { style: { width: ((100 * (row.value || 0)) / max).toFixed(2) + "%" } })),
    h("span", { class: "hb-v" }, row.text))));
}

// A small ring for one rate. p is 0 to 1.
export function miniRing(p, label, sub) {
  const r = 26;
  const circumference = 2 * Math.PI * r;
  const dash = circumference * (p || 0);
  return h("div", { class: "mini" },
    s("svg", { viewBox: "0 0 64 64", width: 72, height: 72, role: "img", "aria-label": label + " " + pct(p) },
      s("circle", { cx: 32, cy: 32, r, class: "ring-track", "stroke-width": 7 }),
      s("circle", {
        cx: 32, cy: 32, r, class: "rseg mini-arc", "stroke-width": 7,
        "stroke-dasharray": dash.toFixed(2) + " " + (circumference - dash).toFixed(2),
      }),
      s("text", { x: 32, y: 36, "text-anchor": "middle", class: "mini-n" }, pct(p))),
    h("span", { class: "mini-l" }, label),
    sub ? h("span", { class: "mini-s" }, sub) : null);
}

// Columns per bucket. Bars sit in an SVG that stretches to the card, and the axis labels are HTML so
// they never scale. One chart for both bucket units.
//   perDay   models mode: [{ date, by_model: { model: tokens } }]; runs mode: [count, ...]
//   keys     one key per bucket: an ISO date for unit "day", an hour (0 to 23) or timestamp for "hour"
//   options  runs, unit, height, ticks { step, steps } from the server, modelName(model)
export function daybars(perDay, keys, options = {}) {
  const { runs = false, unit = "day", height = 150, ticks = null, modelName = (m) => m } = options;
  const n = perDay.length;
  const W = 600;
  const H = height;
  const values = runs ? perDay : perDay.map((d) => Object.values(d.by_model).reduce((a, b) => a + b, 0));
  const max = values.length ? Math.max(...values) : 0;
  const { step, steps } = ticks || { step: max > 0 ? max : 1, steps: 1 };
  const top = step * steps;
  const bucketWidth = W / Math.max(n, 1);
  const gap = Math.min(3, bucketWidth * 0.25);
  const label = (key) => (unit === "hour" ? fmtHour(typeof key === "number" ? key : new Date(key).getHours()) : fmtDay(key));
  const fmt = runs ? (v) => String(Math.round(v)) : fmtTick; // axis labels only; bars and titles keep fmtTokens
  const id = patternId("oth-day");

  const yLabels = [];
  for (let i = steps; i > 0; i -= 1) yLabels.push(h("span", null, fmt(step * i)));
  yLabels.push(h("span", null, "0"));

  const ariaLabel = runs ? t("c_runs_time") : unit === "hour" ? t("c_per_hour") : t("c_per_day");
  const svg = s("svg", {
    class: "dbars", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img", "aria-label": ariaLabel,
  }, hatchDefs(id));
  for (let i = 1; i <= steps; i += 1) {
    const y = H - (H * i) / steps;
    svg.appendChild(s("line", { x1: 0, y1: y.toFixed(1), x2: W, y2: y.toFixed(1), class: "grid" }));
  }
  svg.appendChild(s("line", { x1: 0, y1: H, x2: W, y2: H, class: "base" }));

  perDay.forEach((d, i) => {
    const x = i * bucketWidth + gap / 2;
    const w = bucketWidth - gap;
    if (runs) {
      const hgt = (H * d) / top;
      if (hgt > 0) {
        svg.appendChild(s("rect", { x: x.toFixed(2), y: (H - hgt).toFixed(2), width: w.toFixed(2), height: hgt.toFixed(2), class: "col cat-acc" }));
      }
      return;
    }
    let y = H;
    const order = Object.keys(MODEL_CLASS).concat(Object.keys(d.by_model).filter((m) => !isListed(m)));
    for (const model of order) {
      const val = d.by_model[model] || 0;
      if (val <= 0) continue;
      const hgt = (H * val) / top;
      svg.appendChild(s("rect", {
        x: x.toFixed(2), y: (y - hgt).toFixed(2), width: w.toFixed(2), height: Math.max(hgt - 1, 0.5).toFixed(2),
        class: "col " + modelClass(model), fill: isListed(model) ? null : "url(#" + id + ")",
      }, s("title", null, label(keys[i]) + " " + modelName(model) + " " + fmtTokens(val))));
      y -= hgt;
    }
  });

  const labelEvery = n > 10 ? 7 : 1;
  const xLabels = [];
  for (let i = 0; i < n; i += labelEvery) {
    xLabels.push(h("span", { style: { left: ((100 * (i + 0.5)) / n).toFixed(2) + "%" } }, label(keys[i])));
  }
  return h("div", { class: "dchart" },
    h("div", { class: "dy", "aria-hidden": "true" }, yLabels),
    svg,
    h("div", { class: "dx", "aria-hidden": "true" }, xLabels));
}
