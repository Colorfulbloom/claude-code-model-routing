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
// from the Earlier and Later buttons (band_arrange.js), and both end in commit() below. If the browser blocks storage
// the order still works in memory until the page is closed.
//
// Arrange (Stage 5 direction A, "the band is the editor"). Over 720px, while Arrange is pressed, the band shows the
// saved order exactly: the first foldAt settings, each with Earlier and Later buttons and a grip, and no cell borrowed
// for the open setting. If settings sit past the fold, the last column is a More slot that only shows them (it is not
// a button), and the tray under the band holds the rest with the same cells. At 720px and under the band stays as it
// is and the Arrange list sits under it. The state keeps two flags for that, narrow and editing, and the layout key
// carries them, so a resize across 720px, or a press of Arrange, draws the band again.
//
// Every value comes from the server as data, so it goes in as text through h.js, never as markup.

import { h, clear } from "../h.js";
import { t, withCommas } from "../format.js";
import { icon } from "../icons.js";
import { chip } from "../components.js";
import { fit, merge, move, sameOrder, dropIndex, dropIndexArranged } from "../band_order.js";
import { attachDrag, cancelDrag } from "./band_drag.js";
import * as arrange from "./band_arrange.js";
// settings.js imports this file too: nothing here may use these bindings at the top level, only inside functions.
import { TILES, winnerOf, valueString, valueText } from "./settings.js";

// The width a band is drawn at before it is in the page and has no layout: wide, so every cell shows.
export const DEFAULT_WIDTH = 1600;
// A status that asks to be looked at, so the More summary names it instead of counting settings.
const PROBLEMS = ["overridden", "ignored", "invalid", "unknown"];
const POP_ID = "settings-more";
// The phone layout of app.css. Over this the band can be the editor, at this and under it the list is.
const NARROW = "(max-width: 720px)";

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

// A cell while the band is the editor: the same three spans, but not a link, so a cell is not a tab stop. The
// open setting keeps its underline. Under the spans sits the control row: Earlier and Later (from band_arrange.js) and
// the grip, always shown, because the cell can be dragged. index is the setting's place in the whole order.
function editCellFor(state, key, index) {
  const model = state.models.get(key);
  return h("div", {
    class: ["s4-stat", "s5-stat", model.on && "is-on"],
    "aria-current": model.on ? "true" : null,
    "data-setting": key,
  },
  cellSpans(model),
  h("span", { class: "s7-ctl" },
    arrange.stepsFor(key, model.label, index, state.order.length, true, (k, delta) => step(state, k, delta)),
    h("span", { class: "s6-grip", "aria-hidden": "true" })));
}

// The last column of the band while it is the editor and settings sit past the fold. It shows that More is there, and
// the tray below holds the settings. It is not a button: it has no tab stop, no pressed look, and a screen reader skips
// it, because the tray says the same in words. Its look is the open More button's. A mouse drop on it is the first
// place under More (band_drag.js finds it by the s5-more class).
function moreSlotFor(count) {
  return h("div", { class: "s4-stat s5-stat s5-more is-open", "aria-hidden": "true" },
    h("span", { class: "s4-sl" }, t("band_more_l")),
    h("span", { class: "s4-sv" }, t("band_more_v", { n: count }), icon("chevron", "s5-chev")));
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

// The other setting that changed side of the fold when key crossed it, or null for none. Taking a setting out of one row
// and putting it in the other shifts the settings between its two places by one, so the one next to the fold goes the
// other way: a setting moved into the band pushes the last band setting under More, and one moved under More lets the
// first setting under More up. That holds for any fold inside the order, so null is only a guard for a fold outside it.
function swappedAcross(before, after, foldAt, key) {
  return after.find((k) => k !== key && (before.indexOf(k) < foldAt) !== (after.indexOf(k) < foldAt)) ?? null;
}

// Takes a new order: keeps it in memory, saves it, redraws the band with focus where it was, and says the move. While
// the band is the editor, a setting that crosses the fold changes row, and the words say which way it went.
function commit(state, next, key) {
  const was = state.order.indexOf(key) < state.foldAt;
  const now = next.indexOf(key) < state.foldAt;
  const crossed = state.editing && was !== now;
  const other = crossed ? swappedAcross(state.order, next, state.foldAt, key) : null;
  state.order = next;
  saveOrder(state.path, next);
  arrange.markMoved(key);
  const focused = focusOf(state);
  paint(state, widthOf(state) || state.width);
  refocus(state, focused);
  if (!crossed) say(state, movedText(state, key));
  else if (now) {
    if (other === null) say(state, t("sr_moved_into_band", slots(state, key)));
    else say(state, t("sr_moved_into_band_dropped", { ...slots(state, key), dropped: labelOf(other) }));
  } else if (other === null) say(state, t("sr_moved_to_more", slots(state, key)));
  else say(state, t("sr_moved_to_more_raised", { ...slots(state, key), raised: labelOf(other) }));
}

// A mouse drop. A drop that leaves the order as it was saves nothing and says nothing. While the band is the editor
// the cells on screen are the saved order, so the drop is placed by the row it landed in (row 0 is the band, 1 is the
// tray, and a drop on the More slot counts as the tray's first slot).
function dropped(state, key, slot, onMore, row = 0) {
  const at = state.editing
    ? dropIndexArranged(state.order, state.foldAt, key, row, slot, onMore)
    : dropIndex(state.order, state.cells, state.moreKeys, key, slot, onMore);
  const next = move(state.order, key, at);
  if (!sameOrder(next, state.order)) commit(state, next, key);
}

// Earlier or Later: one place in the saved order.
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

// The More list and, while arranging, the tray or the list, in the slot under the band. The More list and the phone
// list never show together: opening one closes the other. The More list is always in the page when there is a More
// button, hidden until opened. While the band is the editor there is no More button (the slot is not one), so no
// More list, and the tray is in the page instead. The phone list is in the page only while arranging.
function drawPops(state) {
  clear(state.anc);
  state.pop = null;
  if (state.more) {
    state.pop = h("div", { class: "s5-pop", id: POP_ID, hidden: true },
      h("ul", { class: "s5-pl" }, state.order.map((key) => rowFor(state.models.get(key), state, state.cells.includes(key)))));
    state.anc.appendChild(state.pop);
  }
  if (arrange.isOpen()) {
    state.anc.appendChild(state.editing ? arrange.trayFor(arrangeApi(state)) : arrange.listFor(arrangeApi(state)));
    state.open = false;
  }
  if (state.more) setOpen(state, state.open);
  else state.open = false;
  if (state.arrBtn) state.arrBtn.setAttribute("aria-pressed", arrange.isOpen() ? "true" : "false");
}

// What band_arrange.js needs to draw the tray or the list and to act on it.
function arrangeApi(state) {
  return {
    order: state.order,
    foldAt: state.foldAt,
    columns: state.columns,
    isDefault: sameOrder(state.order, defaultOrder()),
    project: state.ctx.project ? state.ctx.project.name : "",
    label: labelOf,
    value: (key) => valueFor(key, winnerOf(state.payload, key), state.payload).node,
    cell: (key, index) => editCellFor(state, key, index),
    step: (key, delta) => step(state, key, delta),
    reset: () => reset(state),
    done: () => closeArrange(state, true),
  };
}

// Pressing Arrange. Over 720px the band itself changes (editor cells, no borrowed cell), so it is drawn again. On a
// phone the band stays as it is and only the list comes or goes, so the More button, which may be the one being
// pressed, is not replaced.
function openArrange(state, open) {
  if (arrange.isOpen() === open) return;
  arrange.setOpen(open);
  if (isNarrow()) drawPops(state);
  else paint(state, widthOf(state) || state.width);
}

// Done and Esc: close the list and give focus back to the Arrange button.
function closeArrange(state, focus) {
  openArrange(state, false);
  if (focus && state.arrBtn) state.arrBtn.focus();
}

// True in the phone layout (720px and under). A page with no matchMedia reads as wide.
function isNarrow() {
  try {
    return Boolean(window.matchMedia && window.matchMedia(NARROW).matches);
  } catch (err) {
    return false;
  }
}

// The cells and the More list for width, with a key that names the whole drawing. While the band is the editor (Arrange
// pressed, over 720px) no cell is borrowed for the open setting, so the band is the first settings of the saved
// order and the fold is where it ends. Otherwise the open setting takes its cell as always. The key holds both flags
// as well as the cells, so a press of Arrange or a resize across 720px draws again even when the cells are the same,
// and so does a width that moves the fold while the open setting sits behind it.
function layoutFor(state, width, narrow) {
  const editing = arrange.isOpen() && !narrow;
  const { cells, more } = fit(state.order, width || DEFAULT_WIDTH, editing ? null : state.selected);
  const key = cells.join(",") + "|" + more.join(",") + (editing ? "|edit" : "") + (narrow ? "|narrow" : "");
  return { cells, more, editing, key };
}

// Fills the band for width. The cells and the list come from fit() over state.order, so a width that gives the same
// answer gives the same band. The list holds every setting in the saved order, and the ones with a cell are marked,
// because the narrow layout shows the whole list. A drag in progress ends first, so nothing is left of it.
function paint(state, width) {
  cancelDrag();
  state.width = width;
  state.narrow = isNarrow();
  const { cells, more, editing, key } = layoutFor(state, width, state.narrow);
  state.cells = cells;
  state.moreKeys = more;
  state.editing = editing;
  state.foldAt = editing ? cells.length : 0;
  state.layout = key;
  state.models = new Map(TILES.map((spec) => [spec.key, modelOf(state.ctx, state.payload, spec, state.selected, state.notSaved)]));
  const hidden = more.map((k) => state.models.get(k));

  clear(state.nav);
  state.more = null;
  state.nav.classList.toggle("s7-ed", editing);
  state.columns = cells.length + (hidden.length ? 1 : 0);
  state.nav.style.setProperty("--n", String(state.columns));
  if (editing) {
    cells.forEach((k, i) => state.nav.appendChild(editCellFor(state, k, i)));
    if (hidden.length) state.nav.appendChild(moreSlotFor(hidden.length));
  } else {
    cells.forEach((k) => state.nav.appendChild(cellFor(state.models.get(k))));
  }
  if (hidden.length && !editing) {
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
  if (layoutFor(state, width, isNarrow()).key === state.layout) return;
  // A redraw removes the element that has focus, so focus goes to the same setting, or to More, or to the same
  // button of the Arrange list.
  const focused = focusOf(state);
  paint(state, width);
  refocus(state, focused);
}

// Depth-first search through childNodes, which a real element and the test DOM both have.
function findNode(node, test) {
  if (node.nodeType === 1 && test(node)) return node;
  for (const child of Array.from(node.childNodes || [])) {
    const found = findNode(child, test);
    if (found) return found;
  }
  return null;
}

const findSetting = (node, key) => findNode(node, (n) => n.getAttribute("data-setting") === key);

// The rows a mouse drag works in: the band, and while it is the editor the tray's row of cells (when it has any).
function rowsOf(state) {
  const tray = state.editing ? findNode(state.anc, (n) => n.classList && n.classList.contains("s7-trow")) : null;
  return tray ? [state.nav, tray] : [state.nav];
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
    // Over 720px focus stays on the pressed button and Tab walks the band. On a phone Tab from the head would reach the
    // band's link and More first, and More closes arranging, so focus goes into the list. A redraw never comes here.
    if (opening && isNarrow()) arrange.focusFirst(state.host);
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
    narrow: false, editing: false, foldAt: 0, columns: 0,
  };
  const state = current;
  attachDrag(host, {
    rows: () => rowsOf(state),
    spans: (key) => cellSpans(modelOf(state.ctx, state.payload, TILES.find((spec) => spec.key === key), state.selected, state.notSaved)),
    drop: (key, slot, onMore, row) => dropped(state, key, slot, onMore, row),
    cancelled: (key) => say(state, t("ar_drag_cancel", { name: labelOf(key) })),
  });
  bind();
  paint(current, 0);
  return host;
}
