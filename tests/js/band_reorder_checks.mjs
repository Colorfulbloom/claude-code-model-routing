// Browser-free checks of the per-project band order (ticket 105): the pure moves in band_order.js, the order saved in
// the browser, the Arrange list, and the mouse drag. Run by tests/test_settings_js.py. They load pages/settings.js,
// pages/band.js, pages/band_arrange.js and pages/band_drag.js from dashboard/static/js against the small fake DOM in
// fakedom.mjs. Nothing here opens a browser or a socket.
//
// What this file cannot show, because the fake DOM has no layout, no CSS and no real pointer: where a lifted cell is
// drawn and whether it is clipped, the hover grip, the translucency, native link dragging, a touch drag scrolling, and
// real pointer capture. The rects below are made up by the checks, so they prove the maths, not the pixels. The owner
// checks those by hand in Chrome.
import assert from "node:assert/strict";
import fs from "node:fs";
import { FElement, createPage } from "./fakedom.mjs";

const STATIC = new URL("../../dashboard/static/", import.meta.url);
const JS = new URL("js/", STATIC).href;
const STRINGS = JSON.parse(fs.readFileSync(new URL("strings.json", STATIC), "utf8"));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const format = await import(JS + "format.js");
format.setStrings(STRINGS);
const router = await import(JS + "router.js");
const settings = await import(JS + "pages/settings.js");
const band = await import(JS + "pages/band.js");
const bandOrder = await import(JS + "band_order.js");
const { move, merge, sameOrder, dropSlot, dropIndex, fit } = bandOrder;

const KEYS = ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl", "alwaysThinkingEnabled", "fallbackModel", "availableModels"];
const NAMES = ["Model", "Effort", "Effort cap", "Compact window", "Cache lifetime", "Extended thinking", "Fallback models", "Allowed models"];
const NAME_OF = Object.fromEntries(KEYS.map((k, i) => [k, NAMES[i]]));

// ---------------------------------------------------------------- the pure part

test("move: puts the key at the index, clamps it, and leaves the input and unknown keys alone", () => {
  const keys = ["a", "b", "c", "d"];
  assert.deepEqual(move(keys, "a", 2), ["b", "c", "a", "d"]);
  assert.deepEqual(move(keys, "d", 0), ["d", "a", "b", "c"]);
  assert.deepEqual(move(keys, "b", 1), keys, "the same place is the same order");
  assert.deepEqual(move(keys, "a", 99), ["b", "c", "d", "a"], "past the end clamps to last");
  assert.deepEqual(move(keys, "c", -5), ["c", "a", "b", "d"], "before the start clamps to first");
  assert.deepEqual(move(keys, "c", Number.NaN), ["c", "a", "b", "d"]);
  const copy = move(keys, "zzz", 1);
  assert.deepEqual(copy, keys);
  assert.notEqual(copy, keys, "an unknown key still gives a new array");
  assert.deepEqual(keys, ["a", "b", "c", "d"], "the input is not changed");
  assert.equal(move(keys, "b", 3)[3], "b");
});

test("merge: the saved order wins, a dropped key goes, a new key follows in the page's order, garbage gives the keys", () => {
  const keys = ["a", "b", "c", "d"];
  assert.deepEqual(merge(["c", "a", "b", "d"], keys), ["c", "a", "b", "d"]);
  assert.deepEqual(merge(["d", "x", "a"], keys), ["d", "a", "b", "c"], "x is not a setting any more, b and c are new");
  assert.deepEqual(merge(["c", "a"], keys), ["c", "a", "b", "d"], "keys the saved order lacks follow in keys order");
  assert.deepEqual(merge(["c", "c", "a", "c"], keys), ["c", "a", "b", "d"], "a repeat is dropped");
  assert.deepEqual(merge(["b", 3, null, {}, ["a"], "a"], keys), ["b", "a", "c", "d"], "a value that is not a string is dropped");
  for (const junk of [null, undefined, "abc", 7, { 0: "a" }, true]) {
    const out = merge(junk, keys);
    assert.deepEqual(out, keys);
    assert.notEqual(out, keys, "a new array each time");
  }
  assert.deepEqual(merge([], keys), keys);
  assert.deepEqual(keys, ["a", "b", "c", "d"]);
});

test("sameOrder: equal lists only", () => {
  assert.equal(sameOrder(["a", "b"], ["a", "b"]), true);
  assert.equal(sameOrder(["a", "b"], ["b", "a"]), false);
  assert.equal(sameOrder(["a"], ["a", "b"]), false);
  assert.equal(sameOrder([], []), true);
  assert.equal(sameOrder(null, []), false);
  assert.equal(sameOrder(["a"], undefined), false);
});

test("dropSlot: the first cell whose middle is right of the pointer, else the slot after the last", () => {
  const edges = [{ left: 0, right: 100 }, { left: 100, right: 200 }, { left: 200, right: 300 }];
  assert.equal(dropSlot(edges, -50), 0);
  assert.equal(dropSlot(edges, 0), 0);
  assert.equal(dropSlot(edges, 49), 0);
  assert.equal(dropSlot(edges, 50), 1, "on the middle counts as past it");
  assert.equal(dropSlot(edges, 149), 1);
  assert.equal(dropSlot(edges, 150), 2);
  assert.equal(dropSlot(edges, 250), 3);
  assert.equal(dropSlot(edges, 9999), 3);
  assert.equal(dropSlot([], 10), 0);
});

test("dropIndex: before the neighbour, after the last cell, on More, and never relative to the key itself", () => {
  const order = ["a", "b", "c", "d", "e", "f"];
  // No More: all six are cells.
  const all = order.slice();
  assert.deepEqual(move(order, "d", dropIndex(order, all, [], "d", 1, false)), ["a", "d", "b", "c", "e", "f"], "before b");
  assert.deepEqual(move(order, "b", dropIndex(order, all, [], "b", 4, false)), ["a", "c", "d", "b", "e", "f"], "before e, to the right");
  assert.deepEqual(move(order, "a", dropIndex(order, all, [], "a", 6, false)), ["b", "c", "d", "e", "f", "a"], "slot n with no More is last");
  assert.deepEqual(move(order, "f", dropIndex(order, all, [], "f", 0, false)), ["f", "a", "b", "c", "d", "e"]);
  // Key skipping: its own slot, and the slot just after it, change nothing.
  assert.deepEqual(move(order, "c", dropIndex(order, all, [], "c", 2, false)), order, "before itself");
  assert.deepEqual(move(order, "c", dropIndex(order, all, [], "c", 3, false)), order, "before the cell after it");
  assert.deepEqual(move(order, "f", dropIndex(order, all, [], "f", 6, false)), order, "after itself at the end");
  // More behind four cells.
  const cells = ["a", "b", "c", "d"];
  const more = ["e", "f"];
  assert.deepEqual(move(order, "a", dropIndex(order, cells, more, "a", 4, false)), ["b", "c", "d", "a", "e", "f"], "after the last cell is before the first key in More");
  assert.deepEqual(move(order, "d", dropIndex(order, cells, more, "d", 4, false)), order, "the last cell dropped after itself stays");
  assert.deepEqual(move(order, "a", dropIndex(order, cells, more, "a", 0, true)), ["b", "c", "d", "e", "a", "f"], "on More: first in More, e moves up");
  assert.deepEqual(move(order, "c", dropIndex(order, cells, more, "c", 1, true)), ["a", "b", "d", "e", "c", "f"]);
  // An unknown key goes last.
  assert.equal(dropIndex(order, cells, more, "zzz", 0, false), order.length);
});

test("dropIndex: works by keys when the open cell took the last slot, so the cells are not the front of the order", () => {
  const order = ["a", "b", "c", "d", "e", "f", "g", "h"];
  // 660 wide, f is open: fit gives cells a b c f and More d e g h.
  const { cells, more } = fit(order, 660, "f");
  assert.deepEqual(cells, ["a", "b", "c", "f"]);
  assert.deepEqual(more, ["d", "e", "g", "h"]);
  // Drag f before b: b is the neighbour, wherever f sits in the order.
  assert.deepEqual(move(order, "f", dropIndex(order, cells, more, "f", 1, false)), ["a", "f", "b", "c", "d", "e", "g", "h"]);
  // Drag a after the last cell (f): before d, the first key in More.
  assert.deepEqual(move(order, "a", dropIndex(order, cells, more, "a", 4, false)), ["b", "c", "a", "d", "e", "f", "g", "h"]);
  // Drag b onto More: after d, the key More shows first. f is not that key.
  assert.deepEqual(move(order, "b", dropIndex(order, cells, more, "b", 0, true)), ["a", "c", "d", "b", "e", "f", "g", "h"]);
  // Drag f, the open cell, onto More: after d, and f is first in More. Its slot is skipped as a neighbour.
  assert.deepEqual(move(order, "f", dropIndex(order, cells, more, "f", 0, true)), ["a", "b", "c", "d", "f", "e", "g", "h"]);
});

// ---------------------------------------------------------------- the page

function entry(over) {
  return { key: "effortLevel", value: "high", status: "in_effect", layer: "user", file: "~/.claude/settings.json",
    scope: "main", line: 3, rule_id: "x", rule_ids: ["x"], reason: "because", ...over };
}
const dflt = (key, value = null) => entry({ key, value, file: null, status: "default", layer: "default", line: undefined });
const EIGHT = [
  entry({ key: "model", value: "claude-opus-5-5", line: 2 }),
  entry({ key: "effortLevel", value: "high" }),
  dflt("maxEffortLevel"), dflt("autoCompactWindow", 1000000), dflt("promptCacheTtl", "1h"),
  dflt("alwaysThinkingEnabled", "on"), dflt("fallbackModel"), dflt("availableModels"),
];
let serial = 0;
// A payload for a project path. Every check uses a path of its own, because the Arrange list's open flag and the
// memory kept while storage is blocked live in the module for the length of the run.
function payloadFor(path = "~/work/p" + (++serial)) {
  return {
    project: "app", state: "ok", entries: EIGHT, no_user_settings: false, shell_label: "Shell", path_display: path,
    config_dir_display: "~/.claude", config_file_display: "~/.claude/routing-dashboard.json",
    models: { "claude-opus-5-5": "Opus 5.5", opus: "Opus 5.5" },
  };
}

function show(payload, { page = createPage(), project = { key: "app", name: "App" }, setting = null } = {}) {
  const root = page.sections.settings;
  const ctx = {
    route: { name: "settings", params: {}, query: { setting } },
    project,
    data: { settings: payload ? { ok: true, status: 200, data: payload } : null },
    hashFor: (name, params, patch = {}) => router.hashFor(name, params, { project: project.key, ...patch }),
  };
  settings.render(root, ctx);
  return root;
}

const hasClass = (n, c) => n.classList && n.classList.contains(c);
const byClass = (root, c) => root.find((n) => hasClass(n, c));
const byAttr = (root, name, value) => root.find((n) => n.getAttribute(name) === value)[0];
const text = (n) => n.textContent;
const navOf = (root) => byClass(root, "s5-a")[0];
const cellsOf = (root) => navOf(root).childNodes.filter((n) => n.getAttribute("data-setting"));
const cellKeys = (root) => cellsOf(root).map((n) => n.getAttribute("data-setting"));
const moreOf = (root) => byClass(root, "s5-more")[0];
const statusOf = (root) => root.find((n) => n.getAttribute("role") === "status")[0];
const arrangeBtn = (root) => byClass(root, "s6-arr")[0];
const listOf = (root) => byClass(root, "s6-ap")[0];
const rowsOf = (root) => byClass(root, "s6-ar");
const rowNames = (root) => rowsOf(root).map((r) => text(byClass(r, "n")[0]));
const action = (root, name) => byAttr(root, "data-arrange", name);
const storeOf = (page) => page.win.localStorage.items;
const keyOfPath = (path) => "band-order:" + path;
const names = (keys) => keys.map((k) => NAME_OF[k]);
const swap = (keys, a, b) => keys.map((k) => (k === a ? b : k === b ? a : k));

// The band draws wide when it has no layout. A check sets the width the nav would measure, then a resize redraws it.
function narrow(page, root, width) {
  navOf(root).clientWidth = width;
  (page.listeners.resize || []).forEach((fn) => fn({}));
}

test("page: no band, no Arrange button; a band puts the button in the head with its label, state and target", () => {
  const page = createPage();
  const none = show(null, { page });
  assert.equal(arrangeBtn(none), undefined);
  const root = show(payloadFor(), { page });
  const btn = arrangeBtn(root);
  assert.ok(btn);
  assert.equal(btn.tagName, "button");
  assert.equal(btn.getAttribute("type"), "button");
  assert.equal(text(btn), STRINGS.arrange);
  assert.equal(btn.getAttribute("aria-label"), STRINGS.ar_btn_sr);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  assert.equal(btn.getAttribute("aria-controls"), "settings-arrange");
  const head = byClass(root, "s4-chead")[0];
  assert.ok(head.contains(btn), "the button is in the page head");
  assert.equal(text(root.find((n) => n.tagName === "h1")[0]), "Settings");
  assert.equal(listOf(root), undefined, "the list is closed until it is asked for");
});

test("status line: one role=status element in the band host, outside the nav and the list, empty until a change", () => {
  const root = show(payloadFor());
  const status = statusOf(root);
  assert.ok(status);
  assert.equal(root.find((n) => n.getAttribute("role") === "status").length, 1);
  assert.ok(hasClass(status, "sr"));
  assert.equal(text(status), "");
  const host = byClass(root, "s5-band")[0];
  assert.equal(status.parentNode, host);
  assert.equal(navOf(root).contains(status), false);
  arrangeBtn(root).click();
  assert.equal(listOf(root).contains(status), false);
  action(root, "down:model").click();
  assert.equal(statusOf(root), status, "a redraw of the band keeps the same element");
  assert.equal(text(status), "Model moved to position 2 of 8.");
});

test("arrange: opening shows the heading, the project, a row for each setting in order and Reset off at the default", () => {
  const root = show(payloadFor());
  const btn = arrangeBtn(root);
  btn.click();
  assert.equal(btn.getAttribute("aria-expanded"), "true");
  const list = listOf(root);
  assert.ok(list);
  assert.equal(list.getAttribute("id"), "settings-arrange");
  assert.equal(text(list.find((n) => n.tagName === "h2")[0]), STRINGS.ar_h);
  assert.equal(text(list.find((n) => n.tagName === "p")[0]), "Order for App");
  assert.deepEqual(rowNames(root), NAMES);
  assert.equal(text(byClass(rowsOf(root)[0], "v")[0]), "Opus 5.5");
  assert.equal(text(byClass(rowsOf(root)[1], "v")[0]), "high");
  assert.equal(root.find((n) => hasClass(n, "s6-ag")).length, 0, "a row has no grip, because rows do not drag");
  assert.equal(byClass(list, "s6-grip").length, 0);
  assert.equal(text(list).includes(STRINGS.ar_note), true);
  assert.equal(action(root, "reset").hasAttribute("disabled"), true, "Reset is off at the default order");
  assert.equal(text(action(root, "reset")), STRINGS.ar_reset);
  assert.equal(text(action(root, "done")), STRINGS.ar_done);
  assert.equal(root.find((n) => hasClass(n, "s6-fold")).length, 0, "all eight fit, so More starts nowhere");
});

test("arrange: Up and Down name the setting, and the first Up and the last Down are off", () => {
  const root = show(payloadFor());
  arrangeBtn(root).click();
  assert.equal(action(root, "up:effortLevel").getAttribute("aria-label"), "Move Effort up");
  assert.equal(action(root, "down:effortLevel").getAttribute("aria-label"), "Move Effort down");
  assert.equal(action(root, "up:model").hasAttribute("disabled"), true);
  assert.equal(action(root, "down:model").hasAttribute("disabled"), false);
  assert.equal(action(root, "down:availableModels").hasAttribute("disabled"), true);
  assert.equal(action(root, "up:availableModels").hasAttribute("disabled"), false);
  assert.equal(root.find((n) => n.tagName === "button" && n.hasAttribute("disabled")).length, 3, "Reset, first Up, last Down");
});

test("arrange: opening by press moves focus to the first row's Down; a redraw does not take focus", () => {
  const page = createPage();
  const payload = payloadFor("~/work/focus");
  let root = show(payload, { page });
  const btn = arrangeBtn(root);
  btn.focus();
  btn.click();
  assert.equal(FElement.focused, action(root, "down:" + KEYS[0]), "the first Up is off, so the first Down takes focus");
  assert.equal(FElement.focused.hasAttribute("disabled"), false);
  // Closing with Done returns to the button; opening again moves focus in again.
  action(root, "done").click();
  assert.equal(FElement.focused, btn);
  btn.click();
  assert.equal(FElement.focused, action(root, "down:" + KEYS[0]));
  // A redraw that restores the open list leaves focus where it was.
  btn.focus();
  root = show(payload, { page });
  assert.ok(listOf(root));
  assert.equal(FElement.focused, arrangeBtn(root));
  const other = cellsOf(root)[2];
  other.focus();
  band.setNotSaved(new Set(["model"]));
  assert.notEqual(FElement.focused, action(root, "down:" + KEYS[0]), "a redraw does not pull focus into the list");
});

test("arrange: Down moves the setting in the band and the list, saves it, says it, marks the row, and keeps focus on the button", () => {
  const page = createPage();
  const payload = payloadFor("~/work/down");
  const root = show(payload, { page });
  arrangeBtn(root).click();
  const down = action(root, "down:model");
  down.focus();
  down.click();
  const want = swap(KEYS, "model", "effortLevel");
  assert.deepEqual(cellKeys(root), want);
  assert.deepEqual(rowNames(root), names(want));
  assert.deepEqual(JSON.parse(storeOf(page).get(keyOfPath("~/work/down"))), want);
  assert.equal(text(statusOf(root)), "Model moved to position 2 of 8.");
  const moved = rowsOf(root).filter((r) => hasClass(r, "is-moved"));
  assert.equal(moved.length, 1);
  assert.equal(text(byClass(moved[0], "n")[0]), "Model");
  assert.equal(FElement.focused, action(root, "down:model"), "focus is on the Down button of the moved row");
  assert.equal(FElement.focused.hasAttribute("disabled"), false);
  assert.ok(listOf(root), "the list stays open");
  assert.equal(action(root, "reset").hasAttribute("disabled"), false, "Reset is on once the order differs");
});

test("arrange: when the pressed button turns off, focus goes to the other button of the same row", () => {
  const root = show(payloadFor());
  arrangeBtn(root).click();
  // Up from position 2 reaches the top, so Up is off and Down takes focus.
  action(root, "down:model").click();
  action(root, "up:model").focus();
  action(root, "up:model").click();
  assert.deepEqual(cellKeys(root), KEYS);
  assert.equal(text(statusOf(root)), "Model moved to position 1 of 8.");
  assert.equal(action(root, "up:model").hasAttribute("disabled"), true);
  assert.equal(FElement.focused, action(root, "down:model"));
  // Down to the end of the list: Down is off and Up takes focus.
  let guard = 0;
  while (!action(root, "down:model").hasAttribute("disabled") && guard++ < 20) {
    action(root, "down:model").focus();
    action(root, "down:model").click();
  }
  assert.equal(cellKeys(root)[7], "model");
  assert.equal(text(statusOf(root)), "Model moved to position 8 of 8.");
  assert.equal(FElement.focused, action(root, "up:model"));
});

test("arrange: Reset puts the default order back for this project, says so, turns off, and moves focus to Done", () => {
  const page = createPage();
  const root = show(payloadFor("~/work/reset"), { page });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  action(root, "down:model").click();
  assert.notDeepEqual(cellKeys(root), KEYS);
  assert.equal(storeOf(page).has(keyOfPath("~/work/reset")), true);
  const reset = action(root, "reset");
  reset.focus();
  reset.click();
  assert.deepEqual(cellKeys(root), KEYS);
  assert.deepEqual(rowNames(root), NAMES);
  assert.equal(storeOf(page).has(keyOfPath("~/work/reset")), false, "the item is removed");
  assert.equal(text(statusOf(root)), "Order reset. Model is at position 1 of 8.");
  assert.equal(action(root, "reset").hasAttribute("disabled"), true);
  assert.equal(FElement.focused, action(root, "done"));
  assert.equal(rowsOf(root).filter((r) => hasClass(r, "is-moved")).length, 0);
});

test("arrange: Done closes the list and Esc does too, and both return focus to the Arrange button", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  const btn = arrangeBtn(root);
  btn.click();
  action(root, "done").focus();
  action(root, "done").click();
  assert.equal(listOf(root), undefined);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  assert.equal(FElement.focused, btn);
  btn.click();
  action(root, "down:model").focus();
  const ev = page.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(listOf(root), undefined);
  assert.equal(FElement.focused, btn);
  assert.equal(ev.defaultPrevented, true);
  // A key that was handled already, or another key, leaves the list alone.
  btn.click();
  page.doc.dispatch("keydown", { key: "Escape", defaultPrevented: true });
  assert.ok(listOf(root));
  page.doc.dispatch("keydown", { key: "ArrowDown" });
  assert.ok(listOf(root));
});

test("arrange: an outside click leaves the list open", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  arrangeBtn(root).click();
  page.sections.settings.dispatch("click");
  page.topbar.dispatch("click");
  assert.ok(listOf(root));
});

test("arrange: a band redraw from a Not saved change keeps the list open and focus on the same button", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  arrangeBtn(root).click();
  action(root, "down:effortLevel").focus();
  band.setNotSaved(new Set(["effortLevel"]));
  assert.ok(listOf(root));
  assert.equal(FElement.focused, action(root, "down:effortLevel"));
  assert.equal(text(byClass(cellsOf(root)[1], "s5-pend")[0]), STRINGS.band_not_saved);
  band.setNotSaved(new Set());
  assert.equal(FElement.focused, action(root, "down:effortLevel"));
});

test("arrange: a resize that changes the cells keeps the list open and focus on the same button", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  arrangeBtn(root).click();
  action(root, "up:fallbackModel").focus();
  narrow(page, root, 660);
  assert.equal(cellKeys(root).length, 4);
  assert.ok(listOf(root));
  assert.equal(FElement.focused, action(root, "up:fallbackModel"));
});

test("arrange: a whole page render of the same project keeps it open and focus on the same button; another project closes it", () => {
  const page = createPage();
  const payload = payloadFor("~/work/keep");
  let root = show(payload, { page });
  arrangeBtn(root).click();
  action(root, "down:effortLevel").click();
  action(root, "down:effortLevel").focus();
  root = show(payload, { page });
  assert.ok(listOf(root), "still open");
  assert.equal(arrangeBtn(root).getAttribute("aria-expanded"), "true");
  assert.equal(FElement.focused, action(root, "down:effortLevel"));
  assert.deepEqual(rowNames(root), names(swap(KEYS, "effortLevel", "maxEffortLevel")), "the saved order draws again");
  // The Arrange button keeps focus too.
  arrangeBtn(root).focus();
  root = show(payload, { page });
  assert.equal(FElement.focused, arrangeBtn(root));
  // A different project: the list is closed and the button says so.
  root = show(payloadFor("~/work/other"), { page });
  assert.equal(listOf(root), undefined);
  assert.equal(arrangeBtn(root).getAttribute("aria-expanded"), "false");
});

test("arrange: opening it closes the More list and opening More closes it", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  narrow(page, root, 660);
  moreOf(root).click();
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "true");
  arrangeBtn(root).click();
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "false");
  assert.ok(listOf(root));
  assert.equal(byClass(root, "s5-pop").filter((n) => n.hidden === false && n.getAttribute("id") === "settings-more").length, 0);
  moreOf(root).click();
  assert.equal(listOf(root), undefined, "the Arrange list is gone");
  assert.equal(arrangeBtn(root).getAttribute("aria-expanded"), "false");
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "true");
  assert.equal(byAttr(root, "id", "settings-more").hidden, false);
});

test("arrange: when settings sit in More at this width, a dashed row says where More starts", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  narrow(page, root, 660);
  arrangeBtn(root).click();
  const rows = byClass(root, "s6-al")[0].childNodes;
  const at = rows.findIndex((r) => hasClass(r, "s6-fold"));
  assert.equal(at, 4, "four cells, so the row comes before the fifth setting");
  assert.equal(text(rows[at]), STRINGS.ar_fold);
  assert.equal(text(byClass(rows[at + 1], "n")[0]), "Cache lifetime");
  // Wider again: no More, no row.
  narrow(page, root, 1056);
  assert.equal(root.find((n) => hasClass(n, "s6-fold")).length, 0);
  // A phone: one cell and More. The row sits after the first setting.
  narrow(page, root, 343);
  assert.equal(byClass(root, "s6-al")[0].childNodes.findIndex((r) => hasClass(r, "s6-fold")), 1);
});

test("arrange: a move in the list never changes the address or the open cell, and never calls the network", () => {
  const calls = [];
  const had = Object.getOwnPropertyDescriptor(globalThis, "fetch");
  globalThis.fetch = (...args) => { calls.push(args); throw new Error("a move must not call the network"); };
  try {
    const page = createPage();
    const root = show(payloadFor(), { page, setting: "promptCacheTtl" });
    const before = page.win.location.hash;
    arrangeBtn(root).click();
    action(root, "down:promptCacheTtl").click();
    action(root, "reset").click();
    assert.deepEqual(calls, []);
    assert.equal(page.win.location.hash, before);
    assert.equal(byClass(navOf(root), "is-on").length, 1);
    assert.equal(byClass(navOf(root), "is-on")[0].getAttribute("data-setting"), "promptCacheTtl");
  } finally {
    if (had) Object.defineProperty(globalThis, "fetch", had); else delete globalThis.fetch;
  }
});

// ---------------------------------------------------------------- the saved order

test("storage: two projects keep their own order, and Reset clears one", () => {
  const page = createPage();
  const a = payloadFor("~/work/a");
  const b = payloadFor("~/work/b");
  let root = show(a, { page });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  const aOrder = swap(KEYS, "model", "effortLevel");
  assert.deepEqual(cellKeys(root), aOrder);
  root = show(b, { page });
  assert.deepEqual(cellKeys(root), KEYS, "a project with no item shows the default order");
  arrangeBtn(root).click();
  action(root, "up:availableModels").click();
  const bOrder = swap(KEYS, "availableModels", "fallbackModel");
  assert.deepEqual(cellKeys(root), bOrder);
  assert.deepEqual([...storeOf(page).keys()].sort(), [keyOfPath("~/work/a"), keyOfPath("~/work/b")]);
  root = show(a, { page });
  assert.deepEqual(cellKeys(root), aOrder);
  arrangeBtn(root).click();
  action(root, "reset").click();
  assert.deepEqual([...storeOf(page).keys()], [keyOfPath("~/work/b")], "Reset removes only this project's item");
  root = show(b, { page });
  assert.deepEqual(cellKeys(root), bOrder);
});

test("storage: a saved order with a dropped or a new setting is merged, and the More list follows the order", () => {
  const page = createPage();
  const path = "~/work/merge";
  page.win.localStorage.setItem(keyOfPath(path), JSON.stringify(["availableModels", "gone", "model", "model", 4, "effortLevel"]));
  const root = show(payloadFor(path), { page });
  assert.deepEqual(cellKeys(root), ["availableModels", "model", "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl", "alwaysThinkingEnabled", "fallbackModel"]);
  narrow(page, root, 660);
  moreOf(root).click();
  const rows = byClass(byAttr(root, "id", "settings-more"), "s5-lr").map((n) => n.getAttribute("data-setting"));
  assert.deepEqual(rows, ["availableModels", "model", "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl", "alwaysThinkingEnabled", "fallbackModel"]);
});

test("refit: a resize follows the project's saved order, never the default one, and a width with the same cells draws nothing", () => {
  const page = createPage();
  const path = "~/work/refit";
  const saved = ["availableModels", "fallbackModel", "alwaysThinkingEnabled", "promptCacheTtl", "autoCompactWindow", "maxEffortLevel", "effortLevel", "model"];
  page.win.localStorage.setItem(keyOfPath(path), JSON.stringify(saved));
  // The open setting is the first of the saved order, so it never displaces a cell.
  const root = show(payloadFor(path), { page, setting: "availableModels" });
  assert.deepEqual(cellKeys(root), saved, "no width yet, so the band draws every cell, in the saved order");
  // A width that needs More: four cells and the button, the first four of the saved order.
  narrow(page, root, 660);
  assert.deepEqual(cellKeys(root), saved.slice(0, 4), "the cells follow the saved order");
  assert.notDeepEqual(cellKeys(root), KEYS.slice(0, 4));
  moreOf(root).click();
  const rows = byClass(byAttr(root, "id", "settings-more"), "s5-lr").map((n) => n.getAttribute("data-setting"));
  assert.deepEqual(rows, saved, "the More list follows it too");
  // Another width with the same four cells: nothing is redrawn, so the cell nodes stay.
  const nodes = cellsOf(root);
  narrow(page, root, 700);
  assert.equal(cellsOf(root).length, 4);
  assert.ok(cellsOf(root).every((n, i) => n === nodes[i]), "the same layout is not drawn again");
  // Wider: five cells and More, then all eight, always in the saved order.
  narrow(page, root, 900);
  assert.deepEqual(cellKeys(root), saved.slice(0, 5));
  narrow(page, root, 1056);
  assert.deepEqual(cellKeys(root), saved);
  // And back to a narrow one.
  narrow(page, root, 343);
  assert.deepEqual(cellKeys(root), saved.slice(0, 1));
});

test("storage: text that is not JSON, or not a list, gives the default order", () => {
  for (const [i, raw] of ["{not json", "", "null", "{\"a\":1}", "\"model\"", "42"].entries()) {
    const page = createPage();
    const path = "~/work/corrupt" + i;
    page.win.localStorage.setItem(keyOfPath(path), raw);
    const root = show(payloadFor(path), { page });
    assert.deepEqual(cellKeys(root), KEYS, JSON.stringify(raw));
  }
});

test("storage: blocked localStorage throws on access, the page still draws, and a move still works in memory for this page", () => {
  const page = createPage();
  Object.defineProperty(page.win, "localStorage", { get() { throw new Error("SecurityError: the store is blocked"); } });
  const payload = payloadFor("~/work/blocked");
  let root = show(payload, { page });
  assert.deepEqual(cellKeys(root), KEYS);
  arrangeBtn(root).click();
  action(root, "down:model").click();
  const want = swap(KEYS, "model", "effortLevel");
  assert.deepEqual(cellKeys(root), want, "the move shows");
  assert.equal(text(statusOf(root)), "Model moved to position 2 of 8.");
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), want, "a page render in the same page still has the order");
  assert.ok(listOf(root), "the list is still open");
  action(root, "reset").click();
  assert.deepEqual(cellKeys(root), KEYS);
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), KEYS, "Reset clears the memory too");
});

test("storage: a store that refuses a write keeps the order in memory, and one that refuses reads is not fatal", () => {
  const page = createPage();
  const real = page.win.localStorage;
  page.win.localStorage = { getItem: (k) => real.getItem(k), setItem() { throw new Error("QuotaExceededError"); }, removeItem() { throw new Error("blocked"); } };
  const payload = payloadFor("~/work/full");
  let root = show(payload, { page });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  assert.deepEqual(cellKeys(root), swap(KEYS, "model", "effortLevel"));
  action(root, "reset").click();
  assert.deepEqual(cellKeys(root), KEYS);
  page.win.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); }, removeItem() { throw new Error("blocked"); } };
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), KEYS);
});

test("storage: a full store still answers reads with the old order, but the moved order stays on the next render", () => {
  const page = createPage();
  const real = page.win.localStorage;
  const path = "~/work/quota";
  const old = swap(KEYS, "model", "availableModels");
  real.setItem(keyOfPath(path), JSON.stringify(old));
  // Quota full: reads work and return the old order, writes throw, removes work.
  page.win.localStorage = { getItem: (k) => real.getItem(k), setItem() { throw new Error("QuotaExceededError"); }, removeItem: (k) => real.removeItem(k) };
  const payload = payloadFor(path);
  let root = show(payload, { page });
  assert.deepEqual(cellKeys(root), old, "the old order loads");
  arrangeBtn(root).click();
  action(root, "down:" + old[0]).click();
  const moved = swap(old, old[0], old[1]);
  assert.deepEqual(cellKeys(root), moved, "the move shows");
  assert.deepEqual(JSON.parse(real.getItem(keyOfPath(path))), old, "the store kept the old order");
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), moved, "the next render keeps the moved order, not the stored one");
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), moved, "and so does the one after");
  action(root, "reset").click();
  assert.deepEqual(cellKeys(root), KEYS);
  assert.equal(real.getItem(keyOfPath(path)), null, "Reset removes the stored order");
  root = show(payload, { page });
  assert.deepEqual(cellKeys(root), KEYS, "Reset clears the memory too");
  // A write that works again clears the memory, so the store is the truth once more.
  const second = payloadFor("~/work/quota2");
  page.win.localStorage = { getItem: (k) => real.getItem(k), setItem() { throw new Error("QuotaExceededError"); }, removeItem: (k) => real.removeItem(k) };
  root = show(second, { page });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  page.win.localStorage = real;
  action(root, "down:model").click();
  const twice = move(move(KEYS, "model", 1), "model", 2);
  assert.deepEqual(cellKeys(root), twice);
  assert.deepEqual(JSON.parse(real.getItem(keyOfPath("~/work/quota2"))), twice, "a write that works stores the order");
  real.setItem(keyOfPath("~/work/quota2"), JSON.stringify(KEYS));
  root = show(second, { page });
  assert.deepEqual(cellKeys(root), KEYS, "the store answers again, because the memory was cleared by the good write");
});

test("storage: the key is band-order: plus the project's path, and a payload with no path stays in memory only", () => {
  const page = createPage();
  let root = show(payloadFor("~/work/key"), { page });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  assert.deepEqual([...storeOf(page).keys()], ["band-order:~/work/key"]);
  const nopath = payloadFor();
  delete nopath.path_display;
  const page2 = createPage();
  root = show(nopath, { page: page2 });
  arrangeBtn(root).click();
  action(root, "down:model").click();
  assert.deepEqual(cellKeys(root), swap(KEYS, "model", "effortLevel"));
  assert.equal(storeOf(page2).size, 0);
});

test("order: the last-slot rule for the open cell stays, and the order itself is never changed by it", () => {
  const page = createPage();
  const root = show(payloadFor(), { page, setting: "alwaysThinkingEnabled" });
  narrow(page, root, 660);
  assert.deepEqual(cellKeys(root), ["model", "effortLevel", "maxEffortLevel", "alwaysThinkingEnabled"]);
  arrangeBtn(root).click();
  assert.deepEqual(rowNames(root), NAMES, "the list shows the saved order, not the displaced one");
  assert.equal(storeOf(page).size, 0);
});

// ---------------------------------------------------------------- the mouse drag

// Gives the nav, its wrapper and each cell (and More) a box, left to right, 132 wide.
function place(root, { top = 100, bottom = 170 } = {}) {
  const nav = navOf(root);
  const kids = nav.childNodes.filter((n) => n.getAttribute("data-setting") || hasClass(n, "s5-more"));
  kids.forEach((kid, i) => { kid.rect = { left: i * 132, right: (i + 1) * 132, top, bottom, width: 132, height: bottom - top }; });
  const right = kids.length * 132;
  nav.rect = { left: 0, right, top, bottom, width: right, height: bottom - top };
  nav.parentNode.rect = { left: 0, right, top: top - 20, bottom: bottom + 20, width: right, height: bottom - top + 40 };
  return nav;
}
const center = (i) => i * 132 + 66;
const mouse = { pointerType: "mouse", button: 0, pointerId: 1 };
const press = (target, x, y = 135, extra = {}) => target.dispatch("pointerdown", { ...mouse, clientX: x, clientY: y, ...extra });
const drag = (page, x, y = 135, buttons = 1) => page.doc.dispatch("pointermove", { pointerId: 1, buttons, clientX: x, clientY: y });
const release = (page, x, y = 135) => page.doc.dispatch("pointerup", { pointerId: 1, clientX: x, clientY: y });
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const lifts = (root) => byClass(root, "s6-lift");
const lines = (root) => byClass(root, "s6-ins");
const nothingLeft = (root) => {
  assert.equal(lifts(root).length, 0, "no lifted cell is left");
  assert.equal(lines(root).length, 0, "no insertion line is left");
  assert.equal(byClass(root, "s6-ghost").length, 0, "no gap is left");
  assert.equal(byClass(root, "s6-mdrop").length, 0);
  assert.equal(hasClass(navOf(root), "is-dragging"), false);
};
const listenerCounts = (page) => ["pointermove", "pointerup", "pointercancel", "keydown", "click", "pointerdown"].map((t) => (page.doc.listeners[t] || []).length);

test("drag: every cell is a link that is not draggable, with a grip, and the nav stops the browser's own drag", () => {
  const root = show(payloadFor());
  const nav = navOf(root);
  for (const cell of cellsOf(root)) {
    assert.equal(cell.getAttribute("draggable"), "false");
    const grip = byClass(cell, "s6-grip");
    assert.equal(grip.length, 1);
    assert.equal(grip[0].getAttribute("aria-hidden"), "true");
  }
  assert.equal(nav.dispatch("dragstart").defaultPrevented, true);
});

test("drag: a short press does not start a drag, takes no pointer capture, and leaves the click alone", async () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  const nav = place(root);
  const cell = cellsOf(root)[2];
  const before = listenerCounts(page);
  press(cell, center(2));
  drag(page, center(2) + 3, 138);
  assert.equal(nav.pointerCaptures, undefined, "no capture before the threshold");
  nothingLeft(root);
  release(page, center(2) + 3, 138);
  nothingLeft(root);
  assert.deepEqual(listenerCounts(page), before, "the press leaves no listener behind");
  assert.equal(page.doc.dispatch("click", { target: cell }).defaultPrevented, false, "the click is not eaten");
  assert.equal(text(statusOf(root)), "");
  assert.equal(storeOf(page).size, 0);
  assert.deepEqual(cellKeys(root), KEYS);
  await tick();
});

test("drag: the threshold is 5 pixels from the press, in any direction", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  const nav = place(root);
  press(cellsOf(root)[2], center(2), 135);
  drag(page, center(2) + 3, 138);
  assert.equal(lifts(root).length, 0, "(3, 3) is 4.2 pixels away");
  drag(page, center(2) - 4, 134);
  assert.equal(lifts(root).length, 0, "(-4, -1) is 4.1 pixels away");
  drag(page, center(2) + 3, 139);
  assert.equal(lifts(root).length, 1, "(3, 4) is exactly 5 pixels away, which starts a drag");
  assert.deepEqual(nav.pointerCaptures, [1]);
  release(page, center(2));
});

test("drag: touch, pen, other buttons, modifier keys and the More button start nothing", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  narrow(page, root, 660);
  const nav = place(root);
  const cell = cellsOf(root)[1];
  const attempts = [
    { pointerType: "touch" }, { pointerType: "pen" }, { button: 1 }, { button: 2 },
    { ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true },
  ];
  for (const extra of attempts) {
    press(cell, center(1), 135, extra);
    drag(page, center(1) + 60);
    drag(page, center(1) + 200);
    nothingLeft(root);
    release(page, center(1) + 200);
  }
  press(moreOf(root), center(4));
  drag(page, center(4) - 300);
  nothingLeft(root);
  release(page, center(4) - 300);
  press(nav, center(1));
  drag(page, center(1) + 100);
  nothingLeft(root);
  release(page, center(1) + 100);
  assert.equal(nav.pointerCaptures, undefined);
  assert.deepEqual(cellKeys(root), ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow"]);
  assert.equal(storeOf(page).size, 0);
});

test("drag: a real drop reorders, saves, redraws, says where it went, and eats the click that follows", async () => {
  const page = createPage();
  const path = "~/work/drop";
  const root = show(payloadFor(path), { page });
  const nav = place(root);
  const before = listenerCounts(page);
  const think = cellsOf(root)[5];
  press(think, center(5));
  drag(page, center(5) - 20);
  assert.deepEqual(nav.pointerCaptures, [1], "capture starts when the threshold passes");
  assert.ok(hasClass(think, "s6-ghost"), "the cell leaves a gap");
  assert.ok(hasClass(nav, "is-dragging"));
  assert.equal(lifts(root).length, 1);
  const lift = lifts(root)[0];
  assert.equal(lift.getAttribute("aria-hidden"), "true");
  assert.deepEqual(lift.childNodes.map((n) => [n.tagName, text(n)]), [["span", "Extended thinking"], ["span", "On"], ["span", "Default"]]);
  assert.equal(lift.styleMap.width, "132px");
  assert.equal(lines(root).length, 1);
  assert.equal(lines(root)[0].getAttribute("aria-hidden"), "true");
  assert.deepEqual(cellKeys(root), KEYS, "the other cells stay still until the drop");
  drag(page, 10);
  release(page, 10);
  const want = ["alwaysThinkingEnabled", ...KEYS.filter((k) => k !== "alwaysThinkingEnabled")];
  assert.deepEqual(cellKeys(root), want);
  assert.deepEqual(JSON.parse(storeOf(page).get(keyOfPath(path))), want);
  assert.equal(text(statusOf(root)), "Extended thinking moved to position 1 of 8.");
  nothingLeft(root);
  assert.equal(nav.capturedPointer, null, "the capture is let go");
  assert.deepEqual(listenerCounts(page).slice(0, 4), before.slice(0, 4), "no drag listener stays");
  // The click that follows the button coming up is eaten once.
  const first = page.doc.dispatch("click", { target: cellsOf(root)[0] });
  assert.equal(first.defaultPrevented, true);
  const second = page.doc.dispatch("click", { target: cellsOf(root)[0] });
  assert.equal(second.defaultPrevented, false, "once only");
  assert.deepEqual(listenerCounts(page), before);
  // And if no click comes, the next timer tick takes the eater away, so a later real click works.
  const cell = cellsOf(root)[1];
  press(cell, center(1));
  drag(page, center(1) + 50);
  release(page, center(1) + 50);
  await tick();
  assert.equal(page.doc.dispatch("click", { target: cell }).defaultPrevented, false);
  assert.deepEqual(listenerCounts(page), before);
});

test("drag: the line follows the slot, and a drop to the right of a cell lands before the cell after it", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  press(cellsOf(root)[0], center(0));
  drag(page, center(0) - 20);
  const line = lines(root)[0];
  assert.equal(line.styleMap.left, "0px", "left of its own middle is its own slot");
  drag(page, center(0) + 10);
  assert.equal(line.styleMap.left, "132px", "right of its own middle is the slot after it");
  drag(page, 300);
  assert.equal(line.styleMap.left, "264px", "x 300 is left of the middle of cell 2 (330), so slot 2");
  drag(page, 1100);
  assert.equal(line.styleMap.left, "1056px", "past the last cell is the slot at its right edge");
  drag(page, 300);
  release(page, 300);
  assert.deepEqual(cellKeys(root), ["effortLevel", "model", ...KEYS.slice(2)], "slot 2 is before Effort cap, with Model removed from the front");
  assert.equal(text(statusOf(root)), "Model moved to position 2 of 8.");
});

test("drag: a drop past the last cell puts the setting last", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  press(cellsOf(root)[2], center(2));
  drag(page, center(2) + 400);
  drag(page, 5000);
  release(page, 5000);
  assert.deepEqual(cellKeys(root), [...KEYS.filter((k) => k !== "maxEffortLevel"), "maxEffortLevel"]);
  assert.equal(text(statusOf(root)), "Effort cap moved to position 8 of 8.");
});

test("drag: a drop where the cell already is saves nothing and says nothing, but still eats the click", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  const cell = cellsOf(root)[3];
  press(cell, center(3));
  drag(page, center(3) + 30);
  drag(page, center(3) - 20);
  release(page, center(3) - 20);
  assert.deepEqual(cellKeys(root), KEYS);
  assert.equal(storeOf(page).size, 0);
  assert.equal(text(statusOf(root)), "");
  nothingLeft(root);
  assert.equal(page.doc.dispatch("click", { target: cell }).defaultPrevented, true);
});

test("drag: the lifted cell and the line stay inside the band's box and the window", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  press(cellsOf(root)[3], center(3), 135);
  drag(page, center(3) + 30, 140);
  const lift = lifts(root)[0];
  drag(page, 9000, 9000);
  assert.equal(lift.styleMap.left, "924px", "its right edge ends at the box's right edge, 1056");
  assert.equal(lift.styleMap.top, "12px", "no further than 12 below the cell's own place");
  drag(page, -9000, -9000);
  assert.equal(lift.styleMap.left, "0px");
  assert.equal(lift.styleMap.top, "-12px");
  drag(page, center(3) + 40, 135);
  const left = Number.parseFloat(lift.styleMap.left);
  assert.ok(left >= 0 && left <= 924);
  release(page, center(3));
  // A narrow window: the box is the window, so the lift stops there.
  const narrowDoc = page.doc.documentElement;
  Object.defineProperty(narrowDoc, "clientWidth", { value: 800, configurable: true });
  press(cellsOf(root)[1], center(1));
  drag(page, center(1) + 30);
  drag(page, 5000);
  assert.equal(lifts(root)[0].styleMap.left, "668px", "800 less 132");
  release(page, 5000);
  delete narrowDoc.clientWidth;
});

test("drag: over More the button says Drop into More; leaving it puts the words back; a drop makes the setting first behind More", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  narrow(page, root, 660);
  place(root);
  const more = moreOf(root);
  const label = more.childNodes[0];
  const words = text(label);
  assert.equal(words, STRINGS.band_more_l);
  press(cellsOf(root)[0], center(0));
  drag(page, center(0) + 20);
  assert.equal(hasClass(more, "s6-mdrop"), false);
  assert.equal(lines(root)[0].hidden, false);
  drag(page, 600);
  assert.ok(hasClass(more, "s6-mdrop"));
  assert.equal(text(label), "Drop into More");
  assert.equal(lines(root)[0].hidden, true, "the line gives way to the More outline");
  drag(page, 400);
  assert.equal(hasClass(more, "s6-mdrop"), false);
  assert.equal(text(label), words);
  assert.equal(lines(root)[0].hidden, false);
  drag(page, 600);
  release(page, 600);
  assert.deepEqual(cellKeys(root), ["effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl"], "Cache lifetime moved up into the band");
  assert.equal(text(byClass(moreOf(root), "s4-sl")[0]), words, "the redrawn button has its own words");
  assert.deepEqual(JSON.parse([...storeOf(page).values()][0]), [
    "effortLevel", "maxEffortLevel", "autoCompactWindow", "promptCacheTtl", "model", "alwaysThinkingEnabled", "fallbackModel", "availableModels"]);
  assert.equal(text(statusOf(root)), "Model moved to position 5 of 8.");
  moreOf(root).click();
  const rows = byClass(byAttr(root, "id", "settings-more"), "s5-lr").map((n) => n.getAttribute("data-setting"));
  assert.deepEqual(rows.slice(4, 5), ["model"], "Model is the first setting behind More");
});

test("drag: a drag with the open cell in More follows the last-slot rule, by keys", () => {
  const page = createPage();
  const root = show(payloadFor(), { page, setting: "fallbackModel" });
  narrow(page, root, 660);
  place(root);
  assert.deepEqual(cellKeys(root), ["model", "effortLevel", "maxEffortLevel", "fallbackModel"]);
  press(cellsOf(root)[0], center(0));
  drag(page, center(0) + 20);
  drag(page, 600);
  release(page, 600);
  // Model went behind autoCompactWindow, the first key More showed.
  assert.deepEqual(JSON.parse([...storeOf(page).values()][0]), ["effortLevel", "maxEffortLevel", "autoCompactWindow", "model", "promptCacheTtl", "alwaysThinkingEnabled", "fallbackModel", "availableModels"]);
  assert.equal(byClass(navOf(root), "is-on")[0].getAttribute("data-setting"), "fallbackModel", "the open cell is still open and still shown");
});

test("drag: Esc puts everything back, says so, and stops the key, so the More list does not close", async () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  narrow(page, root, 660);
  place(root);
  moreOf(root).click();
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "true");
  const before = listenerCounts(page);
  press(cellsOf(root)[1], center(1));
  drag(page, center(1) + 80);
  assert.equal(lifts(root).length, 1);
  const esc = page.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(esc.defaultPrevented, true);
  nothingLeft(root);
  assert.deepEqual(cellKeys(root), ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow"]);
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "true", "More did not hear the key");
  assert.equal(text(statusOf(root)), "Move canceled. Effort is back where it was.");
  assert.equal(storeOf(page).size, 0);
  // The mouse is still down. Moving it does nothing, and letting go does not drop.
  drag(page, 10);
  assert.equal(lifts(root).length, 0);
  release(page, 10);
  assert.deepEqual(cellKeys(root), ["model", "effortLevel", "maxEffortLevel", "autoCompactWindow"]);
  assert.equal(storeOf(page).size, 0);
  // The click that follows the release is eaten, then the eater goes.
  assert.equal(page.doc.dispatch("click", { target: cellsOf(root)[1] }).defaultPrevented, true);
  await tick();
  assert.equal(page.doc.dispatch("click", { target: cellsOf(root)[1] }).defaultPrevented, false);
  assert.deepEqual(listenerCounts(page), before);
  // With no drag, Esc closes More as before.
  page.doc.dispatch("keydown", { key: "Escape" });
  assert.equal(moreOf(root).getAttribute("aria-expanded"), "false");
});

test("drag: Esc before the threshold is the page's, and no key listener is added until a drag starts", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  const keys = (page.doc.listeners.keydown || []).length;
  press(cellsOf(root)[1], center(1));
  assert.equal((page.doc.listeners.keydown || []).length, keys);
  drag(page, center(1) + 2);
  assert.equal((page.doc.listeners.keydown || []).length, keys);
  drag(page, center(1) + 40);
  assert.equal((page.doc.listeners.keydown || []).length, keys + 1);
  release(page, center(1) + 40);
  assert.equal((page.doc.listeners.keydown || []).length, keys);
});

test("drag: a pointer cancel, a lost capture, a window blur and a resize each end it with no message and no change", () => {
  const ends = [
    ["pointercancel", (page) => page.doc.dispatch("pointercancel", { pointerId: 1 })],
    ["lostpointercapture", (page, root) => navOf(root).dispatch("lostpointercapture", { pointerId: 1 })],
    ["blur", (page) => (page.listeners.blur || []).slice().forEach((fn) => fn({}))],
    ["resize", (page) => (page.listeners.resize || []).slice().forEach((fn) => fn({}))],
  ];
  for (const [name, end] of ends) {
    const page = createPage();
    const root = show(payloadFor(), { page });
    place(root);
    const before = listenerCounts(page);
    press(cellsOf(root)[4], center(4));
    drag(page, center(4) - 200);
    assert.equal(lifts(root).length, 1, name);
    end(page, root);
    nothingLeft(root);
    assert.equal(text(statusOf(root)), "", name + " says nothing");
    assert.deepEqual(cellKeys(root), KEYS, name);
    assert.equal(storeOf(page).size, 0, name);
    release(page, center(4) - 200);
    assert.deepEqual(cellKeys(root), KEYS, name + " then release drops nothing");
    page.doc.dispatch("click", { target: cellsOf(root)[4] });
    assert.deepEqual(listenerCounts(page), before, name);
  }
});

test("drag: a move with the main button up ends the press with no drag, or a running drag with no message", async () => {
  // Press a cell, leave the window, let go elsewhere, come back and move: no cell lifts.
  let page = createPage();
  let root = show(payloadFor(), { page });
  place(root);
  let before = listenerCounts(page);
  press(cellsOf(root)[2], center(2));
  drag(page, center(2) + 80, 135, 0);
  nothingLeft(root);
  assert.deepEqual(listenerCounts(page), before, "the press is over and leaves no listener");
  drag(page, center(2) + 160, 135, 1);
  nothingLeft(root);
  assert.equal(navOf(root).pointerCaptures, undefined, "no capture");
  assert.deepEqual(cellKeys(root), KEYS);
  assert.equal(storeOf(page).size, 0);
  assert.equal(page.doc.dispatch("click", { target: cellsOf(root)[2] }).defaultPrevented, false, "no click is eaten");
  // A move that carries other buttons but not the main one counts as up.
  press(cellsOf(root)[2], center(2));
  drag(page, center(2) + 80, 135, 2);
  nothingLeft(root);
  // The same for a drag that is running: it ends quietly, changes nothing, and the next move starts nothing.
  page = createPage();
  root = show(payloadFor(), { page });
  place(root);
  before = listenerCounts(page);
  press(cellsOf(root)[4], center(4));
  drag(page, center(4) - 200);
  assert.equal(lifts(root).length, 1);
  drag(page, center(4) - 260, 135, 0);
  nothingLeft(root);
  assert.equal(text(statusOf(root)), "", "no message");
  assert.deepEqual(cellKeys(root), KEYS);
  assert.equal(storeOf(page).size, 0);
  drag(page, center(4) - 300, 135, 1);
  nothingLeft(root);
  release(page, center(4) - 300);
  assert.deepEqual(cellKeys(root), KEYS, "the release after it drops nothing");
  await tick();
  assert.equal(page.doc.dispatch("click", { target: cellsOf(root)[4] }).defaultPrevented, false, "the button was already up, so no click waits past the tick");
  assert.deepEqual(listenerCounts(page), before);
});

test("drag: a real click gets through after each way the click eater goes away", async () => {
  // A drag ended by Esc leaves the eater waiting for the button to come up. Each of these ends the wait.
  const start = (path) => {
    const page = createPage();
    const root = show(payloadFor(path), { page });
    place(root);
    const before = listenerCounts(page);
    press(cellsOf(root)[1], center(1));
    drag(page, center(1) + 80);
    assert.equal(lifts(root).length, 1);
    return { page, root, before };
  };
  const clickOn = (page, root) => page.doc.dispatch("click", { target: cellsOf(root)[1] });
  // 1. The next pointerdown, anywhere.
  {
    const { page, root, before } = start("~/work/eat-down");
    page.doc.dispatch("keydown", { key: "Escape" });
    nothingLeft(root);
    assert.notDeepEqual(listenerCounts(page), before, "the eater waits for the button");
    press(cellsOf(root)[3], center(3));
    assert.equal(clickOn(page, root).defaultPrevented, false, "a click after a new press gets through");
    release(page, center(3));
    await tick();
    assert.deepEqual(listenerCounts(page), before);
  }
  // 2. The next pointerup and a tick. Before the tick the click is the drag's own and is eaten.
  {
    const { page, root, before } = start("~/work/eat-up");
    page.doc.dispatch("keydown", { key: "Escape" });
    release(page, center(1) + 80);
    assert.equal(clickOn(page, root).defaultPrevented, true, "the click that follows the release is eaten");
    const again = start("~/work/eat-up-2");
    again.page.doc.dispatch("keydown", { key: "Escape" });
    release(again.page, center(1) + 80);
    await tick();
    assert.equal(clickOn(again.page, again.root).defaultPrevented, false, "a click after the tick gets through");
    assert.deepEqual(listenerCounts(again.page), again.before);
    assert.ok(before);
  }
  // 3. A key. A drag ended by a blur with the button released outside the window must not eat an Enter click.
  {
    const { page, root, before } = start("~/work/eat-key");
    (page.listeners.blur || []).slice().forEach((fn) => fn({}));
    nothingLeft(root);
    assert.notDeepEqual(listenerCounts(page), before, "the eater waits for a button that may never come");
    page.doc.dispatch("keydown", { key: "Enter" });
    assert.equal(clickOn(page, root).defaultPrevented, false, "the Enter click gets through");
    assert.deepEqual(listenerCounts(page), before);
  }
  // Esc itself does not clear the eater, so a held Esc that repeats keeps the wait.
  {
    const { page, root } = start("~/work/eat-esc");
    page.doc.dispatch("keydown", { key: "Escape" });
    page.doc.dispatch("keydown", { key: "Escape", repeat: true });
    release(page, center(1) + 80);
    assert.equal(clickOn(page, root).defaultPrevented, true, "the click after the release is still eaten");
    await tick();
  }
});

test("drag: a draw of the band during a drag ends the drag first, so nothing is stranded", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  const nav = navOf(root);
  press(cellsOf(root)[1], center(1));
  drag(page, center(1) + 90);
  assert.equal(lifts(root).length, 1);
  band.setNotSaved(new Set(["effortLevel"]));
  nothingLeft(root);
  assert.equal(navOf(root), nav, "the nav stays");
  assert.equal(text(statusOf(root)), "");
  release(page, center(1) + 90);
  assert.deepEqual(cellKeys(root), KEYS, "the release after it drops nothing");
  assert.equal(storeOf(page).size, 0);
  // A refit does the same.
  place(root);
  press(cellsOf(root)[1], center(1));
  drag(page, center(1) + 90);
  narrow(page, root, 660);
  nothingLeft(root);
  assert.equal(cellKeys(root).length, 4);
});

test("drag: a drag never changes the address or the open cell, never moves focus, and never calls the network", () => {
  const calls = [];
  globalThis.fetch = (...args) => { calls.push(args); throw new Error("a drag must not call the network"); };
  try {
    const page = createPage();
    const root = show(payloadFor(), { page, setting: "promptCacheTtl" });
    place(root);
    const hash = page.win.location.hash;
    const open = cellsOf(root)[4];
    open.focus();
    press(cellsOf(root)[2], center(2));
    drag(page, center(2) + 300);
    release(page, center(2) + 300);
    assert.deepEqual(calls, []);
    assert.equal(page.win.location.hash, hash);
    assert.equal(byClass(navOf(root), "is-on")[0].getAttribute("data-setting"), "promptCacheTtl");
    assert.equal(FElement.focused.getAttribute("data-setting"), "promptCacheTtl", "focus stays on the cell it was on");
  } finally {
    delete globalThis.fetch;
  }
});

test("drag: with the Arrange list open, a drop shows in the list and the band, and the list stays open", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  arrangeBtn(root).click();
  place(root);
  press(cellsOf(root)[2], center(2));
  drag(page, 10);
  release(page, 10);
  const want = ["maxEffortLevel", "model", "effortLevel", ...KEYS.slice(3)];
  assert.deepEqual(cellKeys(root), want);
  assert.ok(listOf(root));
  assert.deepEqual(rowNames(root), names(want));
  assert.equal(action(root, "reset").hasAttribute("disabled"), false);
});

test("drag: a status line reaches a screen reader for a mouse drop with the list closed", () => {
  const page = createPage();
  const root = show(payloadFor(), { page });
  place(root);
  assert.equal(listOf(root), undefined);
  press(cellsOf(root)[7], center(7));
  drag(page, center(7) - 400);
  release(page, center(7) - 400);
  assert.equal(statusOf(root).getAttribute("role"), "status");
  assert.equal(text(statusOf(root)), "Allowed models moved to position 5 of 8.");
});

// ---------------------------------------------------------------- the style sheet

test("css: the lifted cell is translucent but readable, nothing sets touch-action none, and the code never lists it", () => {
  const css = fs.readFileSync(new URL("app.css", STATIC), "utf8");
  const rule = /\.s6-lift\{([^}]*)\}/.exec(css)[1];
  const opacity = Number(/opacity:([\d.]+)/.exec(rule)[1]);
  assert.ok(opacity >= 0.7 && opacity <= 0.95, "opacity " + opacity);
  assert.match(rule, /background:var\(--card-bg\)/, "an opaque card under the opacity");
  assert.doesNotMatch(css, /touch-action\s*:\s*none/);
  for (const file of ["pages/band.js", "pages/band_drag.js", "pages/band_arrange.js"]) {
    const source = fs.readFileSync(new URL("js/" + file, STATIC), "utf8");
    assert.doesNotMatch(source, /touch-action|touchstart|touchmove|ondragstart|innerHTML|outerHTML|insertAdjacentHTML/, file);
    assert.doesNotMatch(source, /\bfetch\s*\(|XMLHttpRequest|sendBeacon/, file + " makes no network call");
  }
});

// ---------------------------------------------------------------- run

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log("ok   " + name);
  } catch (err) {
    failed += 1;
    console.log("FAIL " + name + "\n     " + String(err && err.stack ? err.stack : err).split("\n").slice(0, 8).join("\n     "));
  }
}
console.log((tests.length - failed) + " of " + tests.length + " checks passed");
process.exit(failed ? 1 : 0);
