// Mouse drag for the cells of the Settings band (ticket 105). A cell follows the mouse, a line shows the slot it
// would drop into, and the More button takes a drop of its own. Round 6 boards d-drag, d-in and d-hov. app.css holds
// every class used here (s6-lift, s6-ins, s6-ghost, s6-mdrop and s6-grip).
//
// What counts as a drag: the mouse only (pointerType "mouse"), the main button, no modifier key, and a press on a
// cell. A touch or a pen does nothing here, so a touch drag still scrolls and the Arrange list (band_arrange.js) is
// the way to move a cell without a mouse. Nothing changes until the pointer is 5 pixels from the press, so a short
// press is a click on the cell's link as it always was. There is no HTML drag. A link drags natively, so the cells
// are draggable="false" and the nav stops dragstart.
//
// This file knows nothing of the order. The band hands it two callbacks (see attachDrag), and band_order.js does the
// maths. Past the threshold the other cells stay where they are until the drop.
//
// Esc puts everything back. It is heard in the capture phase on the document for the length of a drag, and stopped
// there, so shell.js and the More list never see it. A pointer cancel, a lost capture, a window blur and a resize end
// the drag with no message, and so does a mouse move with the main button up (it came up outside the window).
// Whatever ends a drag that had started, the click that follows the mouse button coming up is eaten once, so the drop
// never also selects the cell under the pointer. The eater goes on the next press, the next release plus a tick, or
// the next key other than Esc, so a click that did not come from that mouse button always gets through.

import { h } from "../h.js";
import { t } from "../format.js";
import { dropSlot } from "../band_order.js";

// How far the pointer moves from the press before a drag starts.
export const THRESHOLD = 5;
// How far the lifted cell may leave the nav up or down, so it never leaves the band's own space.
const SPAN_Y = 12;

// The press or the drag in progress, or null. There is one pointer, so there is one.
let drag = null;
// The pending click eater, or null.
let eater = null;

const rectOf = (el) => {
  const r = el.getBoundingClientRect();
  return { left: Number(r.left) || 0, right: Number(r.right) || 0, top: Number(r.top) || 0, bottom: Number(r.bottom) || 0 };
};

const clamp = (n, low, high) => Math.max(low, Math.min(high, n));

// ---------------------------------------------------------------- the click that follows a drag

function disarm() {
  if (!eater) return;
  document.removeEventListener("click", eater.eat, true);
  document.removeEventListener("pointerup", eater.up, true);
  document.removeEventListener("pointerdown", eater.down, true);
  document.removeEventListener("keydown", eater.key, true);
  eater = null;
}

// Eats the next click once, and goes away on the next timer tick. With the mouse button still down (a drag ended by
// Esc or a blur), the click comes when the button comes up, so the tick starts then. A press anywhere else clears it,
// and so does a key, because the button may have come up outside the window and then the next click is a keyboard
// click (Enter on a link) that must get through. Esc does not clear it: the drag's own Esc, held down, repeats.
function eatNextClick(buttonDown) {
  disarm();
  const eat = (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (event.stopImmediatePropagation) event.stopImmediatePropagation();
    disarm();
  };
  const up = () => setTimeout(disarm, 0);
  const key = (event) => { if (event.key !== "Escape") disarm(); };
  eater = { eat, up, down: disarm, key };
  document.addEventListener("click", eat, true);
  if (buttonDown) {
    document.addEventListener("pointerup", up, true);
    document.addEventListener("pointerdown", disarm, true);
    document.addEventListener("keydown", key, true);
  } else {
    setTimeout(disarm, 0);
  }
}

// ---------------------------------------------------------------- the drag

function cellOf(nav, target) {
  for (let node = target; node && node !== nav; node = node.parentNode) {
    if (node.parentNode === nav && node.getAttribute && node.getAttribute("data-setting")) return node;
  }
  return null;
}

// Puts the first span of the More button back to its own words.
function moreWords(d, words) {
  const label = d.more && d.more.childNodes[0];
  if (label) label.textContent = words;
}

function leaveMore(d) {
  if (!d.over) return;
  d.over = false;
  d.more.classList.remove("s6-mdrop");
  moreWords(d, d.moreText);
  d.ins.hidden = false;
}

function enterMore(d) {
  if (d.over) return;
  d.over = true;
  d.more.classList.add("s6-mdrop");
  moreWords(d, t("drop_more"));
  d.ins.hidden = true;
}

// Moves the lifted cell and the line to where the pointer is now.
function follow(d) {
  const nav = d.navRect;
  const room = d.room;
  const left = clamp(d.x - d.grabX, room.left, Math.max(room.left, room.right - d.width));
  const top = clamp(d.y - d.grabY, nav.top - SPAN_Y, Math.max(nav.top - SPAN_Y, nav.bottom - d.height + SPAN_Y));
  d.lift.style.left = (left - nav.left) + "px";
  d.lift.style.top = (top - nav.top) + "px";
  const onMore = Boolean(d.moreRect) && d.x >= d.moreRect.left && d.x <= d.moreRect.right;
  if (onMore) enterMore(d); else leaveMore(d);
  d.slot = dropSlot(d.edges, d.x);
  d.onMore = onMore;
  const at = d.slot < d.edges.length ? d.edges[d.slot].left : d.edges[d.edges.length - 1].right;
  d.ins.style.left = (at - nav.left) + "px";
}

function begin(d) {
  d.started = true;
  const cells = Array.from(d.nav.childNodes).filter((n) => n.getAttribute && n.getAttribute("data-setting"));
  d.edges = cells.map((c) => rectOf(c));
  const cellRect = rectOf(d.cell);
  d.navRect = rectOf(d.nav);
  d.width = cellRect.right - cellRect.left;
  d.height = cellRect.bottom - cellRect.top;
  d.grabX = d.x0 - cellRect.left;
  d.grabY = d.y0 - cellRect.top;
  // The lifted cell stays inside the band's box and the window, so it is never clipped and never makes the page scroll.
  const box = d.nav.parentNode && d.nav.parentNode.getBoundingClientRect ? rectOf(d.nav.parentNode) : d.navRect;
  const wide = document.documentElement && Number(document.documentElement.clientWidth) > 0
    ? Number(document.documentElement.clientWidth) : Infinity;
  d.room = { left: Math.max(0, box.left), right: Math.min(wide, box.right) };
  d.more = Array.from(d.nav.childNodes).find((n) => n.classList && n.classList.contains("s5-more")) || null;
  d.moreRect = d.more ? rectOf(d.more) : null;
  d.moreText = d.more && d.more.childNodes[0] ? d.more.childNodes[0].textContent : "";
  d.over = false;
  try { d.nav.setPointerCapture(d.id); } catch (err) { /* no capture: the document listeners still hear the pointer */ }
  d.cell.classList.add("s6-ghost");
  d.nav.classList.add("is-dragging");
  d.lift = h("div", { class: "s6-lift", "aria-hidden": "true", style: { width: d.width + "px" } }, d.hooks.spans(d.key));
  d.ins = h("i", { class: "s6-ins", "aria-hidden": "true" });
  d.nav.appendChild(d.ins);
  d.nav.appendChild(d.lift);
  document.addEventListener("keydown", onKey, true);
  window.addEventListener("blur", onAway);
  window.addEventListener("resize", onAway);
  d.nav.addEventListener("lostpointercapture", onLost);
}

// Ends the press or the drag. how: "drop", "cancel" (Esc, with a message) or "quiet" (nothing to say).
function end(how) {
  const d = drag;
  if (!d) return;
  drag = null;
  document.removeEventListener("pointermove", onMove);
  document.removeEventListener("pointerup", onUp);
  document.removeEventListener("pointercancel", onCancel);
  if (!d.started) return;
  document.removeEventListener("keydown", onKey, true);
  window.removeEventListener("blur", onAway);
  window.removeEventListener("resize", onAway);
  d.nav.removeEventListener("lostpointercapture", onLost);
  try { d.nav.releasePointerCapture(d.id); } catch (err) { /* it was already gone */ }
  leaveMore(d);
  d.cell.classList.remove("s6-ghost");
  d.nav.classList.remove("is-dragging");
  [d.lift, d.ins].forEach((n) => { if (n.parentNode) n.parentNode.removeChild(n); });
  // Esc, a blur and a resize leave the mouse button down, so the click comes later. A drop and a cancel by the
  // browser end with the button up, and any click is already on its way.
  eatNextClick(how === "cancel" || (how === "quiet" && !d.up));
  if (how === "drop") d.hooks.drop(d.key, d.slot, d.onMore);
  else if (how === "cancel") d.hooks.cancelled(d.key);
}

// Ends a drag at once and says nothing. The band calls it before it draws, so nothing is left on the page.
export function cancelDrag() {
  end("quiet");
}

export function dragging() {
  return Boolean(drag && drag.started);
}

function onMove(event) {
  const d = drag;
  if (!d || (event.pointerId !== undefined && d.id !== undefined && event.pointerId !== d.id)) return;
  if (!(event.buttons & 1)) {
    // The main button is up, so it came up outside the window and this press is over: no drag starts, and a running
    // drag ends with no message. No click is on its way, so the eater does not wait for a button.
    d.up = true;
    end("quiet");
    return;
  }
  d.x = event.clientX;
  d.y = event.clientY;
  if (!d.started) {
    if (Math.hypot(d.x - d.x0, d.y - d.y0) < THRESHOLD) return;
    begin(d);
  }
  follow(d);
}

function onUp(event) {
  const d = drag;
  if (!d || (event.pointerId !== undefined && d.id !== undefined && event.pointerId !== d.id)) return;
  if (!d.started) {
    end("quiet");
    return;
  }
  d.x = event.clientX;
  d.y = event.clientY;
  d.up = true;
  follow(d);
  end("drop");
}

function onCancel() {
  if (drag) drag.up = true;
  end("quiet");
}

function onLost() {
  if (drag) drag.up = true;
  end("quiet");
}

function onAway() {
  end("quiet");
}

function onKey(event) {
  if (event.key !== "Escape") return;
  event.preventDefault();
  event.stopPropagation();
  if (event.stopImmediatePropagation) event.stopImmediatePropagation();
  end("cancel");
}

function onDown(event, nav, hooks) {
  if (drag || event.pointerType !== "mouse" || event.button !== 0) return;
  if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  const cell = cellOf(nav, event.target);
  if (!cell) return;
  drag = {
    nav, hooks, cell, key: cell.getAttribute("data-setting"), id: event.pointerId,
    x0: event.clientX, y0: event.clientY, x: event.clientX, y: event.clientY, started: false, up: false,
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp);
  document.addEventListener("pointercancel", onCancel);
}

// Makes the cells of nav draggable with the mouse. hooks.spans(key) gives the three spans of a cell, drawn new, for the
// lifted copy. hooks.drop(key, slot, onMore) takes a drop: slot is the place among the cells (dropSlot) and onMore is
// true for a drop on the More button. hooks.cancelled(key) takes Esc. Called once for each nav.
export function attachDrag(nav, hooks) {
  nav.addEventListener("pointerdown", (event) => onDown(event, nav, hooks));
  // A link drags natively, and that would start a browser drag over ours.
  nav.addEventListener("dragstart", (event) => event.preventDefault());
}
