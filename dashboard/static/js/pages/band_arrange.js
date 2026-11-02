// The Arrange list of the Settings band (ticket 105): a button at the top right of the page head, and under the band
// a list of the settings in the project's order with Up and Down buttons, a Reset link and Done. It is the way to
// reorder with the keyboard and on a phone. Round 6 boards d-ar0, d-ar1 and d-arm. app.css holds every class used
// here (s6-arr, s6-ap, s6-aph, s6-al, s6-ar, s6-mv, s6-fold and s6-af).
//
// This file draws and keeps the open flag. The order, its storage and the status line belong to pages/band.js,
// which hands in an api (see listFor). It imports nothing from band.js or settings.js, so the import cycle between
// those two stays as it is.
//
// The flag lives in this module and not in the band, because a whole page render draws a new band. The list stays
// open through it for the same project, and a new project closes it. Every button carries data-arrange, so a redraw
// puts focus back on the same one: "button" for the Arrange button, "up:<key>" and "down:<key>" for a row, "reset"
// and "done".

import { h } from "../h.js";
import { t } from "../format.js";
import { icon } from "../icons.js";

export const POP_ID = "settings-arrange";

// The path of the project the flag belongs to, whether the list is open, and the key of the setting that moved last.
const session = { path: null, open: false, moved: null };

// Called when the band is drawn for a project. A different project starts with the list closed.
export function syncProject(path) {
  if (session.path === path) return;
  session.path = path;
  session.open = false;
  session.moved = null;
}

export const isOpen = () => session.open;

// Opening or closing the list clears the mark on the row that moved last.
export function setOpen(open) {
  session.open = Boolean(open);
  session.moved = null;
}

export function markMoved(key) {
  session.moved = key;
}

// ---------------------------------------------------------------- the button

// The Arrange button for the page head. onClick is called with no arguments.
export function buttonFor(onClick) {
  return h("button", {
    type: "button",
    class: "btn s6-arr",
    "aria-expanded": session.open ? "true" : "false",
    "aria-controls": POP_ID,
    "aria-label": t("ar_btn_sr"),
    "data-arrange": "button",
    on: { click: onClick },
  },
  h("span", { class: "s6-grip", "aria-hidden": "true" }),
  t("arrange"));
}

// ---------------------------------------------------------------- the list

// One Up or Down button. The icon is the arrow, and the name says what it moves.
function stepButton(key, dir, name, off, onClick) {
  return h("button", {
    type: "button",
    "aria-label": dir === "up" ? t("ar_up", { name }) : t("ar_down", { name }),
    "data-arrange": dir + ":" + key,
    disabled: off,
    on: { click: onClick },
  }, icon(dir));
}

// The list under the band. api comes from band.js:
//   order: the saved order now (keys)
//   atCell: how many keys have a cell now, so the dashed line sits before the first one behind More (0 for none)
//   isDefault: the order is the default
//   project: the name of the project
//   label(key), value(key): the setting's name, and a new node for its value (a node has one parent)
//   step(key, delta), reset(), done(): the actions
export function listFor(api) {
  const rows = [];
  api.order.forEach((key, i) => {
    if (api.atCell > 0 && i === api.atCell) rows.push(h("li", { class: "s6-fold" }, t("ar_fold")));
    const name = api.label(key);
    rows.push(h("li", { class: ["s6-ar", session.moved === key && "is-moved"], "data-key": key },
      h("span", { class: "n" }, name),
      h("span", { class: "v" }, api.value(key)),
      h("span", { class: "s6-mv" },
        stepButton(key, "up", name, i === 0, () => api.step(key, -1)),
        stepButton(key, "down", name, i === api.order.length - 1, () => api.step(key, 1)))));
  });
  return h("div", { class: "s5-pop s6-ap", id: POP_ID },
    h("div", { class: "s6-aph" }, h("h2", null, t("ar_h")), h("p", null, t("ar_for", { project: api.project }))),
    h("ul", { class: "s6-al" }, rows),
    h("div", { class: "s6-af" },
      h("p", null, t("ar_note")),
      h("button", {
        type: "button", class: "s4-link", "data-arrange": "reset", disabled: api.isDefault, on: { click: () => api.reset() },
      }, t("ar_reset")),
      h("button", { type: "button", class: "btn", "data-arrange": "done", on: { click: () => api.done() } }, t("ar_done"))));
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

// Puts focus on the first enabled control of the open list (the first row's Down, since the first Up is off).
// Returns true when a control took focus.
export function focusFirst(root) {
  const list = find(root, (n) => n.getAttribute("id") === POP_ID);
  if (!list) return false;
  const first = find(list, (n) => n.getAttribute("data-arrange") && !n.hasAttribute("disabled"));
  if (!first) return false;
  first.focus();
  return true;
}

// Puts focus back on the control named by action, inside root. A disabled Up or Down passes focus to the other
// button of the same row, a disabled Reset passes it to Done, and any other control that cannot take focus leaves
// it where it is. Returns true when a
// control took focus.
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
