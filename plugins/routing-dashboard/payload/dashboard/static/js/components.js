// Page components, ported one to one from gen2.py and gen3.py. They keep the old class names, so
// app.css applies unchanged, and they take data arguments and return DOM nodes built with h.js.
// Prose goes through renderText, which keeps command-line flags such as --effort on one line.

import { h, frag } from "./h.js";
import { icon } from "./icons.js";
import { t, renderText, rangeWord, RANGES, fmtClock, fmtDate, fmtTime } from "./format.js";

// ---------------------------------------------------------------- status

// A status word with its mark glyph. Never hue alone. status is one of the seven resolver statuses.
export function chip(status, extraClass = "") {
  return h("span", { class: ["st", "st-" + status, extraClass] },
    h("i", { class: "mk", "aria-hidden": "true" }), t("status_" + status));
}

// The pin check pill. state: match, overridden, differs or unknown. An optional label replaces the
// word, for "Differs in 2 of 5 runs". Can't check pin uses the Unknown pair and mark.
export function pinPill(state, label) {
  if (state === "unknown") {
    return h("span", { class: "st st-unknown" }, h("i", { class: "mk", "aria-hidden": "true" }), label || t("pin_cannot_check"));
  }
  const kinds = {
    match: ["st-match", t("matches_pin")],
    overridden: ["st-overridden", t("pin_overridden")],
    differs: ["st-differs", t("differs_pin")],
  };
  const [cls, word] = kinds[state] || kinds.differs;
  return h("span", { class: "st " + cls }, h("i", { class: "mk", "aria-hidden": "true" }), label || word);
}

// ---------------------------------------------------------------- cards and tiles

// A section card. With summary it is a collapsible <details>, and open decides its state.
export function card({ title, body, icon: iconName = null, sub = null, actions = null, cls = "", summary = null, open = true, heading = "h2" }) {
  const head = (headClass) => h("div", { class: headClass },
    h("div", { class: "cd-t" },
      iconName ? h("span", { class: "cd-ic" }, icon(iconName)) : null,
      h("div", null, h(heading, { class: "cd-h" }, renderText(title)), sub ? h("p", { class: "cd-sub" }, renderText(sub)) : null)),
    actions);
  const bd = h("div", { class: "cd-bd" }, body);
  if (summary === null) return h("section", { class: ["cd", cls] }, head("cd-hd"), bd);
  const label = (isOpen) => (isOpen ? t("hide", { section: title }) : t("show", { section: title }));
  const summaryEl = h("summary", { "aria-label": label(open) },
    head("cd-hd cd-hd-sum"), h("span", { class: "cd-sum" }, summary), icon("chevron", "ic chev"));
  return h("details", {
    class: ["cd", "cd-dis", cls], open,
    on: { toggle: (event) => summaryEl.setAttribute("aria-label", label(event.target.open)) },
  }, summaryEl, bd);
}

export function kpi({ label, value, sub = null, delta: deltaNode = null, icon: iconName = null, cls = "" }) {
  return h("div", { class: ["kpi", cls] },
    h("div", { class: "kpi-top" },
      h("span", { class: "tl-l" }, label),
      iconName ? h("span", { class: "kpi-ic" }, icon(iconName, "ic sm")) : null),
    h("div", { class: "kpi-v" }, value),
    sub ? h("div", { class: "kpi-sub" }, sub) : null,
    deltaNode);
}

const MINUS = String.fromCharCode(0x2212); // a real minus sign, not a hyphen

function vsWord(range) {
  return range === "today" ? t("vs_yesterday") : t("vs_previous", { range: rangeWord(range).toLowerCase() });
}

// The change against the previous period. Relative percent, or percentage points for a rate (points).
// Zero is neutral and has no arrow.
export function delta(current, previous, range, points = false) {
  const none = (text) => h("span", { class: "delta delta-none" }, text);
  if (previous === null || previous === undefined || (!points && !previous)) return none(t("no_previous"));
  let change;
  let number;
  let rest;
  if (points) {
    change = (current - previous) * 100;
    const n = Math.abs(change).toFixed(1);
    if (n === "0.0") return none(t("delta_none"));
    const slots = { sign: change > 0 ? "+" : MINUS, n, vs: vsWord(range) };
    const text = n === "1.0" ? t("delta_point", slots) : t("delta_points", slots);
    const cut = text.indexOf(" ");
    number = text.slice(0, cut);
    rest = text.slice(cut + 1);
  } else {
    change = ((current - previous) / previous) * 100;
    if (Math.round(change) === 0) return none(t("delta_none"));
    number = (change > 0 ? "+" : MINUS) + Math.abs(Math.round(change)) + "%";
    rest = vsWord(range);
  }
  return h("span", { class: ["delta", change < 0 && "delta-down"] }, h("span", { class: "delta-n" }, number), " ", rest);
}

// verifiedOn is the price list's date (payload.prices.verified_on). The tooltip says what "estimated" means
// and when the prices were checked. It says only the first part when the payload has no date.
export function estLine(verifiedOn = null) {
  const tip = verifiedOn ? t("est_tip") + " " + t("prices_checked", { date: fmtTime(verifiedOn) }) : t("est_tip");
  return h("p", { class: "est", title: tip }, renderText(t("est_short")));
}

// "12 sessions" kept together on one line. count and words are text or nodes.
export function inline(count, words) {
  return h("span", { class: "cw" }, count, " ", h("span", { class: "muted" }, words));
}

// cols: the column names. rows: arrays of cells (text or nodes), one per column. Each cell carries its
// column name in data-l, which the narrow layout shows beside the value.
export function table3(cols, rows, cls = "") {
  return h("table", { class: ["dt", cls] },
    h("thead", null, h("tr", null, cols.map((c) => h("th", { scope: "col" }, c)))),
    h("tbody", null, rows.map((row) => h("tr", null, row.map((cell, i) => h("td", { "data-l": cols[i] }, cell))))));
}

// ---------------------------------------------------------------- page head

// crumbs: [{ label, href }]. right: a node, usually the range control.
export function pageHead({ title, intro = null, right = null, crumbs = null }) {
  return h("div", { class: "ph" },
    crumbs ? h("p", { class: "crumbs" }, crumbs.map((c) => frag(h("a", { href: c.href || "#" }, c.label), " ", h("span", { "aria-hidden": "true" }, "/"), " "))) : null,
    h("div", { class: "ph-row" },
      h("div", null, h("h1", null, renderText(title)), intro ? h("p", { class: "intro" }, renderText(intro)) : null),
      right));
}

// The three-way range switch. Switching it fetches nothing: onChange only changes the view.
// It is a radio group, so the arrow keys move between the choices.
export function rangeControl(active, onChange) {
  const group = h("div", { class: "segs segs-range", role: "radiogroup", "aria-label": t("range_label") });
  const buttons = RANGES.map((range) => {
    const on = range === active;
    return h("button", {
      type: "button", role: "radio", class: ["seg", on && "is-active"], "aria-checked": on ? "true" : "false", tabindex: on ? "0" : "-1",
      on: { click: () => onChange(range) },
    }, rangeWord(range));
  });
  group.addEventListener("keydown", (event) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    onChange(RANGES[(RANGES.indexOf(active) + step + RANGES.length) % RANGES.length]);
  });
  buttons.forEach((b) => group.appendChild(b));
  return group;
}

// configDir is the display form of the Claude config folder, such as "~/.claude". generatedAt is the
// payload's ISO time. A plain reload is the refresh, so there is no button.
export function footerLine(configDir, generatedAt = null) {
  const text = renderText(t("footer", { config_dir: configDir }));
  const at = generatedAt ? new Date(generatedAt) : null;
  if (!at || Number.isNaN(at.getTime())) return h("p", { class: "foot" }, text);
  return h("p", { class: "foot" }, text, " ", t("read_at", { time: fmtClock(at), date: fmtDate(at) }));
}

// ---------------------------------------------------------------- empty states

// A heading and a line of text in a card, as the "No usage yet" state is drawn.
export function emptyState(heading, text, iconName = "bars") {
  return card({ title: heading, body: h("p", { class: "es-t" }, renderText(text)), icon: iconName });
}

// Shown on a page that needs one project while All projects is picked (#41 and C-1). The button moves focus
// to the Project select in the top bar, as the "No rule matches" state carries its own control.
export function projectPickerEmpty() {
  const toSelect = () => { const select = document.getElementById("project"); if (select) select.focus(); };
  return card({
    title: t("s_pick_project_h"),
    icon: "overview",
    body: h("div", { class: "es" },
      h("p", { class: "es-t" }, renderText(t("s_pick_project_t"))),
      h("button", { type: "button", class: "btn", on: { click: toSelect } }, t("s_pick_project_btn"))),
  });
}
