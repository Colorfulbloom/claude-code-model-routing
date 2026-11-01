// The Stat band of the Settings page: one cell for each setting that fits, then a More button with a list of the
// rest. Round 6, board a-rest, and round 5 for the More list (a12-open). app.css holds every class used here
// (section "Settings and trail", s4-, s5- and s6- classes, named as the boards name them).
//
// Which settings get a cell is band_order.js (pure). This file draws that answer. The band measures its own width,
// so it draws wide first, and pages/settings.js calls refitBand() once the page is in the document. A resize
// then redraws the band alone, and only when the answer changes. One listener per document does that, so
// drawing the page again never stacks listeners.
//
// Every value comes from the server as data, so it goes in as text through h.js, never as markup.

import { h, clear } from "../h.js";
import { t } from "../format.js";
import { icon } from "../icons.js";
import { chip } from "../components.js";
import { fit } from "../band_order.js";
// settings.js imports this file too: nothing here may use these bindings at the top level, only inside functions.
import { TILES, winnerOf, valueString, valueText } from "./settings.js";

// The width a band is drawn at before it is in the page and has no layout: wide, so every cell shows.
export const DEFAULT_WIDTH = 1600;
// A status that asks to be looked at, so the More summary names it instead of counting settings.
const PROBLEMS = ["overridden", "ignored", "invalid", "unknown"];
const POP_ID = "settings-more";

// The band that is on screen, or null. The listeners below read it.
let current = null;
// The window the listeners are on. The page has one, so they are added once.
let boundTo = null;

// ---------------------------------------------------------------- one cell

const withCommas = (digits) => digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");

// The value of a cell as { plain, node }: the words a screen reader says, and what the cell shows. A setting the
// payload has no entry for, a null value and a value the page hides read as "Not known". An effort cap with no
// value, or one that is only the default, reads as "Not set". Exported so the read-only frame of a setting
// (pages/read_frame.js) words its value the same way as the cell.
export function valueFor(key, entry, payload) {
  const none = () => ({ plain: t("band_not_known"), node: h("span", { class: "s5-sv-none" }, t("band_not_known")) });
  if (!entry) return none();
  if (key === "maxEffortLevel" && (entry.status === "default" || entry.value === null || entry.value === undefined)) {
    return { plain: t("band_not_set"), node: t("band_not_set") };
  }
  const node = valueText(entry, payload, true);
  if (node === null) return none();
  let plain = valueString(entry, payload, true);
  // The compact window is a token count, so it reads with thousands commas.
  if (key === "autoCompactWindow" && /^\d+$/.test(plain)) {
    plain = withCommas(plain);
    return { plain, node: plain };
  }
  return { plain, node };
}

// One setting as the band words it. entry is null when the payload has none.
function modelOf(ctx, payload, spec, selected, notSaved) {
  const entry = winnerOf(payload, spec.key);
  const value = valueFor(spec.key, entry, payload);
  const pending = notSaved.has(spec.key);
  const becomes = entry && entry.becomes !== undefined && entry.becomes !== null
    ? t("runs_as_cell", { becomes: entry.becomes }) : "";
  return {
    key: spec.key,
    label: spec.label(),
    entry,
    value,
    pending,
    becomes,
    on: spec.key === selected,
    href: ctx.hashFor("settings", {}, { setting: spec.key }),
  };
}

// The status part of a cell or a row: the Not saved mark and word for a setting with a change waiting, else the
// status chip, else nothing (no entry, so no status).
function statusNode(model) {
  if (model.pending) return h("span", { class: "s5-pend" }, t("band_not_saved"));
  return model.entry ? h("span", { class: "s4-st" }, chip(model.entry.status)) : null;
}

// What the cell says to a screen reader: label, plain value, status word, what it runs as, then what it does.
function cellName(model) {
  const word = model.pending ? t("band_not_saved") : model.entry ? t("status_" + model.entry.status) : "";
  return [model.label, model.value.plain, word, model.becomes].filter(Boolean).join(", ") + ". " + t("band_cell_desc");
}

function cellFor(model) {
  return h("a", {
    class: ["s4-stat", "s5-stat", model.on && "is-on"],
    href: model.href,
    title: model.becomes ? model.label + ", " + model.becomes : model.label,
    "aria-label": cellName(model),
    "aria-current": model.on ? "true" : null,
    "data-setting": model.key,
  },
  h("span", { class: "s4-sl" }, model.label),
  h("span", { class: "s4-sv" }, model.value.node),
  h("span", { class: "s4-sw" }, statusNode(model)));
}

// ---------------------------------------------------------------- More

// The first line under "N more": a change waiting, else the first hidden status that asks to be looked at, else
// how many hidden settings are set in files, else "All default".
function moreSummary(hidden) {
  if (hidden.some((m) => m.pending)) return h("span", { class: "s5-pend" }, t("band_not_saved"));
  const problem = hidden.find((m) => m.entry && PROBLEMS.includes(m.entry.status));
  if (problem) return h("span", { class: "s4-st" }, chip(problem.entry.status));
  const set = hidden.filter((m) => m.entry && m.entry.status !== "default").length;
  if (set === 0) return t("band_more_none");
  return set === 1 ? t("band_more_set1") : t("band_more_set", { n: set });
}

function moreName(hidden) {
  const n = hidden.length;
  const waiting = hidden.filter((m) => m.pending).map((m) => m.label);
  if (waiting.length) {
    return n === 1 ? t("band_more_sr1_pending", { name: waiting.join(", ") })
      : t("band_more_sr_pending", { n, name: waiting.join(", ") });
  }
  return n === 1 ? t("band_more_sr1") : t("band_more_sr", { n });
}

// One row of the list. A setting that already has a cell is in the list too, and the narrow layout shows it there
// (s5-vc), so a phone shows every setting in one place with the open one marked.
function rowFor(model, state, hasCell) {
  return h("li", { class: hasCell ? "s5-vc" : null },
    h("a", {
      class: ["s5-lr", model.on && "is-on"],
      href: model.href,
      "aria-current": model.on ? "true" : null,
      "data-setting": model.key,
      // Picking a row follows its link. Close first, because the same address does not redraw the page.
      on: { click: () => setOpen(state, false) },
    },
    h("span", { class: "n" }, model.label),
    h("span", { class: "v" }, model.value.node),
    statusNode(model) || h("span")));
}

function setOpen(state, open) {
  state.open = Boolean(open) && state.pop !== null;
  if (state.pop) state.pop.hidden = !state.open;
  if (state.more) state.more.setAttribute("aria-expanded", state.open ? "true" : "false");
}

// ---------------------------------------------------------------- draw

// Fills the band for width. The cells and the list come from fit(), so a width that gives the same answer gives
// the same band. The list holds every setting in the saved order, and the ones with a cell are marked, because the
// narrow layout shows the whole list.
function paint(state, width) {
  state.width = width;
  const keys = TILES.map((spec) => spec.key);
  const { cells, more } = fit(keys, width || DEFAULT_WIDTH, state.selected);
  state.layout = cells.join(",") + "|" + more.join(",");
  const models = new Map(TILES.map((spec) => [spec.key, modelOf(state.ctx, state.payload, spec, state.selected, state.notSaved)]));
  const hidden = more.map((key) => models.get(key));

  clear(state.nav);
  clear(state.anc);
  state.more = null;
  state.pop = null;
  cells.forEach((key) => state.nav.appendChild(cellFor(models.get(key))));
  state.nav.style.setProperty("--n", String(cells.length + (hidden.length ? 1 : 0)));
  if (!hidden.length) {
    state.open = false;
    return;
  }
  state.more = h("button", {
    type: "button",
    class: "s4-stat s5-stat s5-more",
    "aria-expanded": "false",
    "aria-controls": POP_ID,
    "aria-label": moreName(hidden),
    on: { click: () => setOpen(state, !state.open) },
  },
  h("span", { class: "s4-sl" }, t("band_more_l")),
  h("span", { class: "s4-sv" }, t("band_more_v", { n: hidden.length }), icon("chevron", "s5-chev")),
  h("span", { class: "s4-sw" }, moreSummary(hidden)));
  state.nav.appendChild(state.more);
  state.pop = h("div", { class: "s5-pop", id: POP_ID, hidden: true },
    h("ul", { class: "s5-pl" }, keys.map((key) => rowFor(models.get(key), state, cells.includes(key)))));
  state.anc.appendChild(state.pop);
  setOpen(state, state.open);
}

// The width of the band now, or 0 when it has no layout (hidden, not in the page yet, or a test DOM).
function widthOf(state) {
  const width = state.nav.clientWidth;
  return Number.isFinite(width) && width > 0 ? width : 0;
}

// Draws the band again when its width now gives another set of cells. A band with no width yet is left alone.
export function refitBand() {
  const state = current;
  if (!state) return;
  const width = widthOf(state);
  if (!width) return;
  const next = fit(TILES.map((s) => s.key), width, state.selected);
  if (next.cells.join(",") + "|" + next.more.join(",") === state.layout) return;
  // A redraw removes the element that has focus, so focus goes to the same setting, or to More.
  const focused = focusKey(state);
  paint(state, width);
  if (focused === null) return;
  const target = focused === "" ? state.more : findSetting(state.nav, focused);
  if (target) target.focus();
}

// Depth-first search through childNodes, which a real element and the test DOM both have.
function findSetting(node, key) {
  if (node.nodeType === 1 && node.getAttribute("data-setting") === key) return node;
  for (const child of Array.from(node.childNodes || [])) {
    const found = findSetting(child, key);
    if (found) return found;
  }
  return null;
}

// The setting whose cell or row has focus, "" for the More button, null when focus is elsewhere.
function focusKey(state) {
  for (let node = document.activeElement; node && node !== document; node = node.parentNode) {
    if (node === state.more) return "";
    if (node.getAttribute && node.getAttribute("data-setting") && state.host.contains(node)) {
      return node.getAttribute("data-setting");
    }
  }
  return null;
}

// Draws the band again for a new Set of Not saved settings, with no page render: a choice on the Effort cell marks
// the cell, or the More button when the cell is in the list. The band keeps its width, its open list and its focus.
export function setNotSaved(notSaved) {
  const state = current;
  if (!state) return;
  state.notSaved = notSaved;
  const focused = focusKey(state);
  paint(state, widthOf(state) || state.width);
  if (focused === null) return;
  const target = focused === "" ? state.more : findSetting(state.nav, focused);
  if (target) target.focus();
}

// ---------------------------------------------------------------- keys and clicks

function onKeydown(event) {
  const state = current;
  if (event.key !== "Escape" || event.defaultPrevented || !state || !state.open) return;
  setOpen(state, false);
  if (state.more) state.more.focus();
  if (event.preventDefault) event.preventDefault();
}

function onClick(event) {
  const state = current;
  if (!state || !state.open) return;
  if (event.target && state.host.contains(event.target)) return;
  setOpen(state, false);
}

function bind() {
  if (boundTo === window) return;
  boundTo = window;
  window.addEventListener("resize", refitBand);
  document.addEventListener("keydown", onKeydown);
  document.addEventListener("click", onClick);
}

// ---------------------------------------------------------------- the band

// The band for the main session's settings. payload is the /api/settings answer. selected is the key of the open
// cell. notSaved is a Set of setting keys that have a change waiting (setNotSaved changes it later).
// Returns the node to put in the page: the wrapper, the nav and the list. Call refitBand() after it is in the page.
export function bandFor(ctx, payload, selected, notSaved = new Set()) {
  const nav = h("nav", { class: "s5-a", "aria-label": t("band_nav_sr") });
  const anc = h("div", { class: "s5-anc" });
  const host = h("div", { class: "s5-band" }, h("div", { class: "s5-bw" }, nav), anc);
  current = {
    ctx, payload, selected, notSaved, host, nav, anc, open: false, layout: "", more: null, pop: null, width: 0,
  };
  bind();
  paint(current, 0);
  return host;
}
