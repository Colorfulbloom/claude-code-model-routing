// Shared small builders and helpers of the Change effort card, the review and the strip: notices, buttons, locks,
// the path marker and the node walker. Nothing here holds state.
//
// Rules this file keeps, the same as edit_card.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.

import { h, s } from "./h.js";
import { t } from "./format.js";

export const MARKS = { ok: "✓", warn: "▲", err: "✕" };
// A path slot is written into the text as a marker, then drawn as a .pa element. See draw().
const MARK = "\u0001";

export function basename(path) {
  if (path === null || path === undefined) return "";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || String(path);
}

export const text = (value) => (value === null || value === undefined ? "" : String(value));
export const isString = (value) => typeof value === "string" && value !== "";

// t() puts a marker where a path goes. draw() splits the text there and puts the path in a .pa element, so a
// long path wraps and a server value is never joined into markup. paths: { name: value }.
export const mark = (name) => MARK + name + MARK;

export function draw(line, paths = {}) {
  const out = [];
  String(line).split(new RegExp(MARK + "(\\w+)" + MARK)).forEach((piece, i) => {
    if (i % 2 === 0) {
      if (piece !== "") out.push(piece);
    } else {
      out.push(h("span", { class: "pa" }, text(paths[piece])));
    }
  });
  return out;
}

// The text of ed_lock_<reason>, or null. A null or empty reason never builds a key, and a reason with no key shows nothing.
export function lockText(reason) {
  if (!isString(reason)) return null;
  const line = t("ed_lock_" + reason);
  return line === "ed_lock_" + reason ? null : line;
}

// The same for the short line of a locked file row: ed_row_lock_<reason>, or null.
export function rowLockText(reason) {
  if (!isString(reason)) return null;
  const line = t("ed_row_lock_" + reason);
  return line === "ed_row_lock_" + reason ? null : line;
}

// The text for an error answer. A status of 0 or an answer with no code is the network line. A 422 with a
// blocked reason is that reason's lock line. Any other code is its ed_err_ line.
export function errorText(res) {
  const status = res && typeof res.status === "number" ? res.status : 0;
  const code = res && res.data && typeof res.data === "object" && isString(res.data.error) ? res.data.error : "";
  if (!status || !code) return t("ed_err_network");
  if (status === 422) {
    const lock = lockText(code);
    if (lock) return lock;
  }
  const line = t("ed_err_" + code);
  return line === "ed_err_" + code ? t("ed_err_forbidden") : line;
}

export const bodyOf = (out) => (out && out.res && out.res.data && typeof out.res.data === "object" ? out.res.data : {});
export const codeOf = (out) => text(bodyOf(out).error);

export function walk(node, test, out = []) {
  if (node && node.nodeType === 1 && test(node)) out.push(node);
  for (const child of Array.from((node && node.childNodes) || [])) walk(child, test, out);
  return out;
}

export function lockIcon() {
  return s("svg", {
    class: "ic sm", viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor",
    "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  }, s("rect", { x: 5, y: 11, width: 14, height: 9, rx: 2 }), s("path", { d: "M8 11V8a4 4 0 0 1 8 0v3" }));
}

// The check mark of the picked file row.
export function checkIcon() {
  return s("svg", {
    class: "ic sm", viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor",
    "stroke-width": 2.5, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  }, s("path", { d: "M5 13l4 4L19 7" }));
}

// The undo arrow of the Undo button.
export function undoIcon() {
  return s("svg", {
    class: "ic sm", viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor",
    "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  }, s("path", { d: "M4 9h11a5 5 0 0 1 0 10H9" }), s("path", { d: "M8 5L4 9l4 4" }));
}

export function lockLine(line) {
  return h("p", { class: "p2-lock" }, lockIcon(), h("span", null, line));
}

export function hint(line, id) {
  return h("p", { class: "p2-hint", id: id || null }, line);
}

export function button(label, { primary = false, wide = false, focus = null, disabled = false, busy = false, onClick = null } = {}) {
  return h("button", {
    type: "button",
    class: ["btn", primary && "p2-pri", wide && "s4-wide"],
    disabled,
    "aria-busy": busy ? "true" : null,
    "data-edit-focus": focus ? "btn:" + focus : null,
    on: onClick ? { click: onClick } : null,
  }, label);
}

const NT_CLASS = { ok: "nt p2-nt p2-nt-ok", warn: "nt p2-nt p2-nt-warn", err: "nt p2-nt p2-nt-err" };

// A notice: the mark and a heading, then paragraphs, then buttons. An error is an alert and the rest are status.
export function nt(kind, heading, paras = [], buttons = []) {
  return h("div", { class: NT_CLASS[kind], role: kind === "err" ? "alert" : "status" },
    h("div", { class: "p2-nt-h" }, h("span", { class: "p2-mk", "aria-hidden": "true" }, MARKS[kind]), heading),
    paras.filter(Boolean).map((p) => h("p", null, p)),
    buttons.length ? h("div", { class: "p2-btns" }, buttons) : null);
}

const isRow = (x) => x !== null && typeof x === "object";

// The rows of the targets answer, read defensively: an item that isn't an object is left out.
export const levelsOf = (T) => (Array.isArray(T && T.levels) ? T.levels.filter((l) => isRow(l) && isString(l.level)) : []);
export const filesOf = (T) => (Array.isArray(T && T.files) ? T.files.filter(isRow) : []);
export const targetById = (T, id) => (Array.isArray(T.targets) ? T.targets : []).find((x) => isRow(x) && x.target === id) || null;
export const levelRow = (T, value) => levelsOf(T).find((l) => l.level === value) || null;
// The level that runs now: the row whose result is now, or null.
export const runningOf = (T) => {
  const row = levelsOf(T).find((l) => l.result === "now");
  return row ? row.level : null;
};

export function tokenNt() {
  return nt("err", t("ed_token_h"), [t("ed_token_t")]);
}
