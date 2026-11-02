// The Stat band of the Settings page: one cell for each setting that fits, then a More button with a list of the
// rest. Round 6, board a-rest, and round 5 for the More list (a12-open). app.css holds every class used here
// (section "Settings and trail", s4-, s5- and s6- classes, named as the boards name them).
//
// Which settings get a cell is band_order.js (pure). This file draws that answer. The band measures its own width,
// so it draws wide first, and pages/settings.js calls refitBand() once the page is in the document. A resize
// then redraws the band alone, and only when the answer changes. One listener per document does that, so
// drawing the page again never stacks listeners.
//
// The order of the cells is the project's own (ticket 105). It is state.order: the default order of TILES, or the
// order saved in the browser for the project (localStorage, keyed by the project's path). A move saves it, Reset
// removes it, and no settings file and no server route is involved. A move comes from a mouse drag (band_drag.js) or
// from the Arrange list (band_arrange.js), and both end in commit() below. If the browser blocks storage the order
// still works in memory until the page is closed.
//
// Every value comes from the server as data, so it goes in as text through h.js, never as markup.

import { h, clear } from "../h.js";
import { t, withCommas } from "../format.js";
import { icon } from "../icons.js";
import { chip } from "../components.js";
import { fit, merge, move, sameOrder, dropIndex } from "../band_order.js";
import { attachDrag, cancelDrag } from "./band_drag.js";
import * as arrange from "./band_arrange.js";
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

// The value of a cell as { plain, node }: the words a screen reader says, and what the cell shows. A setting the
// payload has no entry for, a null value and a value the page hides read as "Not known". An effort cap with no
// value, or one that is only the default, reads as "Not set". A fallback chain reads the same way, and a list of
// models reads as a count: the chain, or for the allowed list the merged list that runs (no list set reads "All
// models", and an entry with no merged list reads "Not known"). Exported so the read-only frame of a setting
// (pages/read_frame.js) words its value the same way as the cell.
export function valueFor(key, entry, payload) {
  const none = () => ({ plain: t("band_not_known"), node: h("span", { class: "s5-sv-none" }, t("band_not_known")) });
  if (!entry) return none();
  if (key === "maxEffortLevel" && (entry.status === "default" || entry.value === null || entry.value === undefined)) {
    return { plain: t("band_not_set"), node: t("band_not_set") };
  }
  if (key === "fallbackModel" && (entry.status === "default" || entry.value === null || entry.value === undefined)) {
    return { plain: t("band_not_set"), node: t("band_not_set") };
  }
  if (key === "availableModels" && entry.status === "default") {
    return { plain: t("band_models_any"), node: t("band_models_any") };
  }
  const node = valueText(entry, payload, true);
  if (node === null) return none();
  if (key === "fallbackModel" || key === "availableModels") {
    // A Lowered chain counts what runs (merged), else the list as written.
    const list = key === "fallbackModel" ? (Array.isArray(entry.merged) ? entry.merged : entry.value) : entry.merged;
    if (Array.isArray(list)) {
      const n = list.length;
      const plain = n === 0 ? t("band_models_none") : n === 1 ? t("band_model_one") : t("band_models", { n });
      return { plain, node: plain };
    }
    if (key === "availableModels") return none();
  }
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

// The three spans of a cell: label, value and status. The lifted copy of a dragged cell is made of new ones.
function cellSpans(model) {
  return [
    h("span", { class: "s4-sl" }, model.label),
    h("span", { class: "s4-sv" }, model.value.node),
    h("span", { class: "s4-sw" }, statusNode(model)),
  ];
}

// draggable="false" because a link drags natively. The grip is for the eye: app.css shows it on hover with a mouse.
function cellFor(model) {
  return h("a", {
    class: ["s4-stat", "s5-stat", model.on && "is-on"],
    href: model.href,
    title: model.becomes ? model.label + ", " + model.becomes : model.label,
    "aria-label": cellName(model),
    "aria-current": model.on ? "true" : null,
    "data-setting": model.key,
    draggable: "false",
  },
  cellSpans(model),
  h("span", { class: "s6-grip", "aria-hidden": "true" }));
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

// ---------------------------------------------------------------- the saved order

const STORE = "band-order:";
// Orders that could not be written to the browser, by project path. A full store still answers a read, with the
// older order, so a path with an order here reads from here first. A write that succeeds and a Reset clear it.
const memory = new Map();

const defaultOrder = () => TILES.map((spec) => spec.key);
const labelOf = (key) => {
  const spec = TILES.find((s) => s.key === key);
  return spec ? spec.label() : String(key);
};

// The order saved for a project, or null for none. Every use of localStorage sits in a try, because a blocked or
// full store throws, even on access. Text that is not JSON counts as none.
function readSaved(path) {
  if (typeof path !== "string" || !path) return null;
  if (memory.has(path)) return memory.get(path);
  let raw;
  try {
    raw = window.localStorage.getItem(STORE + path);
  } catch (err) {
    return null;
  }
  if (raw === null || raw === undefined) return null;
  try {
    return JSON.parse(raw);
  } catch (err) {
    return null;
  }
}

function saveOrder(path, order) {
  if (typeof path !== "string" || !path) return;
  try {
    window.localStorage.setItem(STORE + path, JSON.stringify(order));
    memory.delete(path);
  } catch (err) {
    memory.set(path, order.slice());
  }
}

function clearOrder(path) {
  if (typeof path !== "string" || !path) return;
  memory.delete(path);
  try {
    window.localStorage.removeItem(STORE + path);
  } catch (err) { /* blocked: there is nothing saved to remove */ }
}

// ---------------------------------------------------------------- the status line

// The status line says a move in words, for a screen reader. It is one element in the band's host, so it is there
// before the first move and a redraw of the band never removes it.
function say(state, text) {
  state.status.textContent = "";
  state.status.textContent = text;
}

// The words of a move and of a reset: the setting's name, its place in the order (1 is first) and the number of settings.
const slots = (state, key) => ({ name: labelOf(key), n: state.order.indexOf(key) + 1, total: state.order.length });
const movedText = (state, key) => t("ar_moved", slots(state, key));
const resetText = (state, key) => t("ar_reset_said", slots(state, key));

// ---------------------------------------------------------------- changing the order

// Takes a new order: keeps it in memory, saves it, redraws the band with focus where it was, and says the move.
function commit(state, next, key) {
  state.order = next;
  saveOrder(state.path, next);
  arrange.markMoved(key);
  const focused = focusOf(state);
  paint(state, widthOf(state) || state.width);
  refocus(state, focused);
  say(state, movedText(state, key));
}

// A mouse drop. A drop that leaves the order as it was saves nothing and says nothing.
function dropped(state, key, slot, onMore) {
  const next = move(state.order, key, dropIndex(state.order, state.cells, state.moreKeys, key, slot, onMore));
  if (!sameOrder(next, state.order)) commit(state, next, key);
}

// Up or Down in the Arrange list.
function step(state, key, delta) {
  const to = state.order.indexOf(key) + delta;
  if (to < 0 || to >= state.order.length) return;
  commit(state, move(state.order, key, to), key);
}

// Reset this project: the saved order goes, the default order comes back, and focus goes to Done, because Reset is
// now off.
function reset(state) {
  clearOrder(state.path);
  state.order = defaultOrder();
  arrange.markMoved(null);
  paint(state, widthOf(state) || state.width);
  arrange.restoreAction(state.host, "done");
  say(state, resetText(state, state.order[0]));
}

// ---------------------------------------------------------------- draw

// The More list and the Arrange list, in the slot under the band. They never show together: opening one closes the
// other. The More list is always in the page, hidden until opened. The Arrange list is in the page only while open.
function drawPops(state) {
  clear(state.anc);
  state.pop = null;
  if (state.more) {
    state.pop = h("div", { class: "s5-pop", id: POP_ID, hidden: true },
      h("ul", { class: "s5-pl" }, state.order.map((key) => rowFor(state.models.get(key), state, state.cells.includes(key)))));
    state.anc.appendChild(state.pop);
  }
  if (arrange.isOpen()) {
    state.anc.appendChild(arrange.listFor(arrangeApi(state)));
    state.open = false;
  }
  if (state.more) setOpen(state, state.open);
  else state.open = false;
  if (state.arrBtn) state.arrBtn.setAttribute("aria-expanded", arrange.isOpen() ? "true" : "false");
}

// What band_arrange.js needs to draw the list and to act on it.
function arrangeApi(state) {
  return {
    order: state.order,
    atCell: state.moreKeys.length ? state.cells.length : 0,
    isDefault: sameOrder(state.order, defaultOrder()),
    project: state.ctx.project ? state.ctx.project.name : "",
    label: labelOf,
    value: (key) => valueFor(key, winnerOf(state.payload, key), state.payload).node,
    step: (key, delta) => step(state, key, delta),
    reset: () => reset(state),
    done: () => closeArrange(state, true),
  };
}

function openArrange(state, open) {
  if (arrange.isOpen() === open) return;
  arrange.setOpen(open);
  drawPops(state);
}

// Done and Esc: close the list and give focus back to the Arrange button.
function closeArrange(state, focus) {
  openArrange(state, false);
  if (focus && state.arrBtn) state.arrBtn.focus();
}

// Fills the band for width. The cells and the list come from fit() over state.order, so a width that gives the same
// answer gives the same band. The list holds every setting in the saved order, and the ones with a cell are marked,
// because the narrow layout shows the whole list. A drag in progress ends first, so nothing is left of it.
function paint(state, width) {
  cancelDrag();
  state.width = width;
  const { cells, more } = fit(state.order, width || DEFAULT_WIDTH, state.selected);
  state.cells = cells;
  state.moreKeys = more;
  state.layout = cells.join(",") + "|" + more.join(",");
  state.models = new Map(TILES.map((spec) => [spec.key, modelOf(state.ctx, state.payload, spec, state.selected, state.notSaved)]));
  const hidden = more.map((key) => state.models.get(key));

  clear(state.nav);
  state.more = null;
  cells.forEach((key) => state.nav.appendChild(cellFor(state.models.get(key))));
  state.nav.style.setProperty("--n", String(cells.length + (hidden.length ? 1 : 0)));
  if (hidden.length) {
    state.more = h("button", {
      type: "button",
      class: "s4-stat s5-stat s5-more",
      "aria-expanded": "false",
      "aria-controls": POP_ID,
      "aria-label": moreName(hidden),
      on: { click: () => {
        if (!state.open) openArrange(state, false);
        setOpen(state, !state.open);
      } },
    },
    h("span", { class: "s4-sl" }, t("band_more_l")),
    h("span", { class: "s4-sv" }, t("band_more_v", { n: hidden.length }), icon("chevron", "s5-chev")),
    h("span", { class: "s4-sw" }, moreSummary(hidden)));
    state.nav.appendChild(state.more);
  }
  drawPops(state);
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
  const next = fit(state.order, width, state.selected);
  if (next.cells.join(",") + "|" + next.more.join(",") === state.layout) return;
  // A redraw removes the element that has focus, so focus goes to the same setting, or to More, or to the same
  // button of the Arrange list.
  const focused = focusOf(state);
  paint(state, width);
  refocus(state, focused);
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

// Where focus is in the band: a button of the Arrange list ({ action }), a cell, a row or More ({ key }), or null.
function focusOf(state) {
  const action = arrange.focusedAction(state.host);
  if (action) return { action };
  const key = focusKey(state);
  return key === null ? null : { key };
}

function refocus(state, focused) {
  if (!focused) return;
  if (focused.action) {
    arrange.restoreAction(state.host, focused.action);
    return;
  }
  const target = focused.key === "" ? state.more : findSetting(state.nav, focused.key);
  if (target) target.focus();
}

// Draws the band again for a new Set of Not saved settings, with no page render: a choice on the Effort cell marks
// the cell, or the More button when the cell is in the list. The band keeps its width, its open list and its focus.
export function setNotSaved(notSaved) {
  const state = current;
  if (!state) return;
  state.notSaved = notSaved;
  const focused = focusOf(state);
  paint(state, widthOf(state) || state.width);
  refocus(state, focused);
}

// The Arrange button for the page head, or null when there is no band. Call it after bandFor().
export function arrangeButton() {
  const state = current;
  if (!state) return null;
  state.arrBtn = arrange.buttonFor(() => {
    const opening = !arrange.isOpen();
    openArrange(state, opening);
    // Opening by press moves focus into the list, so Tab does not walk the band first. A redraw never comes here.
    if (opening) arrange.focusFirst(state.host);
  });
  return state.arrBtn;
}

// ---------------------------------------------------------------- keys and clicks

function onKeydown(event) {
  const state = current;
  if (event.key !== "Escape" || event.defaultPrevented || !state) return;
  if (arrange.isOpen()) {
    closeArrange(state, true);
    if (event.preventDefault) event.preventDefault();
    return;
  }
  if (!state.open) return;
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
// The order is the one saved in the browser for payload.path_display, merged with the settings the page has now.
export function bandFor(ctx, payload, selected, notSaved = new Set()) {
  cancelDrag();
  const path = payload ? payload.path_display : null;
  arrange.syncProject(path);
  const nav = h("nav", { class: "s5-a s6-a", "aria-label": t("band_nav_sr") });
  const anc = h("div", { class: "s5-anc" });
  const status = h("div", { class: "sr", role: "status" });
  const host = h("div", { class: "s5-band" }, h("div", { class: "s5-bw" }, nav), anc, status);
  current = {
    ctx, payload, selected, notSaved, host, nav, anc, status, path, open: false, layout: "", more: null, pop: null, width: 0,
    order: merge(readSaved(path), defaultOrder()), cells: [], moreKeys: [], models: new Map(), arrBtn: null,
  };
  const state = current;
  attachDrag(nav, {
    spans: (key) => cellSpans(modelOf(state.ctx, state.payload, TILES.find((spec) => spec.key === key), state.selected, state.notSaved)),
    drop: (key, slot, onMore) => dropped(state, key, slot, onMore),
    cancelled: (key) => say(state, t("ar_drag_cancel", { name: labelOf(key) })),
  });
  bind();
  paint(current, 0);
  return host;
}
