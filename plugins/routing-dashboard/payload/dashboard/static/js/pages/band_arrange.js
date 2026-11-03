// The Arrange side of the Settings band (ticket 105, and Stage 5 direction A: the band is the editor).
//
// Over 720px the band itself is the editor. Arrange is a toggle button at the top right of the page head
// (aria-pressed). While it is pressed, each cell of the band carries Earlier and Later buttons and a grip, the
// settings that did not fit sit in a tray under the band below a "More starts here" line, and Reset and Done close
// the tray. This file draws the Earlier and Later buttons (stepsFor), the tray (trayFor) and, for a phone, the list.
// The cells themselves come from pages/band.js, because a cell is the band's own. At 720px and under the band is a
// sticky strip with one cell and More, so there the editor is a list under it (listFor): one row for each setting,
// Earlier and Later as up and down arrows, 44px wide. Round 6 boards d-ar0, d-ar1 and d-arm for the list, Stage 5
// board A for the band. app.css holds every class used here (s6-ap, s6-ar, s6-mv, s6-fold and s6-af for the list,
// s7- for the tray).
//
// This file draws and keeps the open flag. The order, its storage and the status line belong to pages/band.js,
// which hands in an api (see trayFor and listFor). It imports nothing from band.js or settings.js, so the import
// cycle between those two stays as it is.
//
// The flag lives in this module and not in the band, because a whole page render draws a new band. Arranging stays
// on through it for the same project, and a new project turns it off. Every button carries data-arrange, so a redraw
// puts focus back on the same one: "button" for the Arrange button, "up:<key>" (Earlier) and "down:<key>" (Later) for
// a setting, "reset" and "done". The names stay up and down because the phone list shows them as arrows up and down.

import { h } from "../h.js";
import { t } from "../format.js";
import { icon } from "../icons.js";

export const POP_ID = "settings-arrange";

// The path of the project the flag belongs to, whether arranging is on, and the key of the setting that moved last
// (the phone list marks its row).
const session = { path: null, open: false, moved: null };

// Called when the band is drawn for a project. A different project starts with arranging off.
export function syncProject(path) {
  if (session.path === path) return;
  session.path = path;
  session.open = false;
  session.moved = null;
}

export const isOpen = () => session.open;

// Turning arranging on or off clears the mark on the row that moved last.
export function setOpen(open) {
  session.open = Boolean(open);
  session.moved = null;
}

export function markMoved(key) {
  session.moved = key;
}

// ---------------------------------------------------------------- the button

// The Arrange button for the page head. onClick is called with no arguments. It is a toggle, so it says pressed.
export function buttonFor(onClick) {
  return h("button", {
    type: "button",
    class: "btn s6-arr",
    "aria-pressed": session.open ? "true" : "false",
    "aria-controls": POP_ID,
    "aria-label": t("ar_btn_sr"),
    "data-arrange": "button",
    on: { click: onClick },
  },
  h("span", { class: "s6-grip", "aria-hidden": "true" }),
  t("arrange"));
}

// ---------------------------------------------------------------- the editor

// One Earlier or Later button. The icon is the arrow, and the name says what it moves. Over 720px the arrows point
// left and right, because the band reads across. On a phone the list reads down, so they point up and down.
function stepButton(key, dir, name, off, across, onClick) {
  const earlier = dir === "up";
  return h("button", {
    type: "button",
    "aria-label": earlier ? t("step_earlier", { name }) : t("step_later", { name }),
    "data-arrange": dir + ":" + key,
    disabled: off,
    on: { click: onClick },
  }, icon(across ? (earlier ? "left" : "right") : dir));
}

// The pair of buttons of one setting: Earlier, then Later. The first setting's Earlier and the last one's Later are
// off. index is the setting's place in the whole order. across is true in the band editor and false in the phone
// list. step(key, delta) is called with -1 for Earlier and 1 for Later.
export function stepsFor(key, name, index, total, across, step) {
  return h("span", { class: "s6-mv" },
    stepButton(key, "up", name, index === 0, across, () => step(key, -1)),
    stepButton(key, "down", name, index === total - 1, across, () => step(key, 1)));
}

// The foot of the tray and of the list: the note, Reset (off at the default order) and Done.
function footFor(api, extra) {
  return h("div", { class: ["s6-af", extra] },
    h("p", null, t("ar_note")),
    h("button", {
      type: "button", class: "s4-link", "data-arrange": "reset", disabled: api.isDefault, on: { click: () => api.reset() },
    }, t("ar_reset")),
    h("button", { type: "button", class: "btn", "data-arrange": "done", on: { click: () => api.done() } }, t("ar_done")));
}

// The tray under the band while the band is the editor (over 720px). api comes from band.js:
//   order: the saved order now (keys)
//   foldAt: how many settings the band shows, so the tray holds order[foldAt..]
//   columns: the band's column count, so the tray's cells sit under the band's columns
//   isDefault: the order is the default
//   cell(key, index): a new editor cell for the setting, drawn by band.js with its buttons from stepsFor
//   reset(), done(): the actions
// With nothing past the fold the tray says every setting fits. It is in the flow, so it pushes the page down and
// never covers it.
export function trayFor(api) {
  const rest = api.order.slice(api.foldAt);
  return h("div", { class: "s7-tray", id: POP_ID, style: { "--n": api.columns } },
    rest.length
      ? [h("div", { class: "s6-fold" }, t("fold_line")),
        h("div", { class: "s7-trow" }, rest.map((key, i) => {
          const cell = api.cell(key, api.foldAt + i);
          // A cell that starts a line of the tray's grid sits flush left, like the band's first cell.
          if (i % api.columns === 0) cell.classList.add("s7-lead");
          return cell;
        }))]
      : h("p", { class: "s7-empty" }, t("tray_empty")),
    footFor(api, "s7-af"));
}

// ---------------------------------------------------------------- the phone list

// The list under the band on a phone (720px and under). api comes from band.js:
//   order: the saved order now (keys)
//   isDefault: the order is the default
//   project: the name of the project
//   label(key), value(key): the setting's name, and a new node for its value (a node has one parent)
//   step(key, delta), reset(), done(): the actions
// There is no fold line, because the band here is one cell and More. The note says the order sets the More list.
export function listFor(api) {
  const rows = api.order.map((key, i) => {
    const name = api.label(key);
    return h("li", { class: ["s6-ar", session.moved === key && "is-moved"], "data-key": key },
      h("span", { class: "n" }, name),
      h("span", { class: "v" }, api.value(key)),
      stepsFor(key, name, i, api.order.length, false, api.step));
  });
  return h("div", { class: "s5-pop s6-ap", id: POP_ID },
    h("div", { class: "s6-aph" }, h("h2", null, t("ar_h")), h("p", null, t("ar_for", { project: api.project }))),
    h("p", { class: "s7-note" }, t("phone_note")),
    h("ul", { class: "s6-al" }, rows),
    footFor(api));
}

// ---------------------------------------------------------------- focus

// Depth-first search through childNodes, which a real element and the test DOM both have.
function find(node, test) {
  if (node.nodeType === 1 && test(node)) return node;
  for (const child of Array.from(node.childNodes || [])) {
    const found = find(child, test);
    if (found) return found;
  }
  return null;
}

export const withAction = (root, action) => find(root, (n) => n.getAttribute("data-arrange") === action);

// The data-arrange value of the control inside root that has focus, or null.
export function focusedAction(root) {
  for (let node = document.activeElement; node && node !== document; node = node.parentNode) {
    if (node.getAttribute && node.getAttribute("data-arrange") && root.contains(node)) return node.getAttribute("data-arrange");
  }
  return null;
}

// Puts focus on the first enabled control of the open list (the first setting's Later, since its Earlier is off).
// Only a phone uses it: over 720px focus stays on the Arrange button and Tab walks the band. Returns true when a
// control took focus.
export function focusFirst(root) {
  const list = find(root, (n) => n.getAttribute("id") === POP_ID);
  if (!list) return false;
  const first = find(list, (n) => n.getAttribute("data-arrange") && !n.hasAttribute("disabled"));
  if (!first) return false;
  first.focus();
  return true;
}

// Puts focus back on the control named by action, inside root. A disabled Earlier or Later passes focus to the other
// button of the same setting, a disabled Reset passes it to Done, and any other control that cannot take focus leaves
// it where it is. Returns true when a control took focus.
export function restoreAction(root, action) {
  const target = withAction(root, action);
  if (!target) return false;
  if (!target.hasAttribute("disabled")) {
    target.focus();
    return true;
  }
  const [dir, key] = action.split(":");
  if (action === "reset") return restoreAction(root, "done");
  if (key === undefined) return false;
  const other = withAction(root, (dir === "up" ? "down:" : "up:") + key);
  if (!other || other.hasAttribute("disabled")) return false;
  other.focus();
  return true;
}
