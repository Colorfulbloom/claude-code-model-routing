// Which settings get a cell in the Settings band and which go behind More. Pure: no DOM and no storage.
//
// The band is as wide as the page leaves it. Each cell needs minCell pixels, so width / minCell is the number
// of slots, and at least two (a cell and More). When every key has a slot, all of them show and More does not
// appear. Otherwise one slot is More and the rest keep the first keys in the saved order. The cell the person
// has open always shows: if it was in More, it takes the last cell slot and the key it displaced goes first in
// More. No other cell moves, and the saved order itself is never changed.
//
// The saved order is per project and lives in the browser (pages/band.js keeps it). move, merge, sameOrder,
// dropSlot and dropIndex below are the pure part of changing it: the order of keys after a move, the saved order
// reconciled with the keys the page has now, and where a mouse drop lands.
//
// The 1360 window rule: a 1360 pixel window less the sidebar (240) and the page gutters (32 on each side) leaves
// a band 1056 wide, which is eight cells of 132. The rule is the 132 pixel cell, not a window width, so the
// band follows whatever width it is given. Five keys fit from 660.

export const MIN_CELL = 132;

// keys: the saved order. width: the band's width in pixels. selected: the key that is open. Returns
// { cells, more }, two lists of keys. cells and more are new arrays, so the caller may keep them.
export function fit(keys, width, selected, minCell = MIN_CELL) {
  const slots = Math.max(2, Math.floor(width / minCell));
  if (keys.length <= slots) return { cells: keys.slice(), more: [] };
  const n = slots - 1;
  const cells = keys.slice(0, n);
  const more = keys.slice(n);
  const at = more.indexOf(selected);
  if (at >= 0) {
    const displaced = cells[n - 1];
    cells[n - 1] = selected;
    more.splice(at, 1);
    more.unshift(displaced);
  }
  return { cells, more };
}

// ---------------------------------------------------------------- changing the order

// keys with key moved so it sits at index (clamped to the list). A key that is not in keys gives a plain copy.
export function move(keys, key, index) {
  const out = keys.slice();
  const from = out.indexOf(key);
  if (from < 0) return out;
  out.splice(from, 1);
  const wanted = Number.isFinite(index) ? Math.trunc(index) : 0;
  out.splice(Math.max(0, Math.min(out.length, wanted)), 0, key);
  return out;
}

// The saved order reconciled with the keys the page has: saved keys that still exist keep their place, then any key
// the saved order lacks follows in keys order. Anything that is not a list gives the keys as they are, and a repeat or
// a value that is not a string in the saved list is dropped.
export function merge(saved, keys) {
  if (!Array.isArray(saved)) return keys.slice();
  const known = new Set(keys);
  const seen = new Set();
  const out = [];
  for (const key of saved) {
    if (typeof key === "string" && known.has(key) && !seen.has(key)) {
      seen.add(key);
      out.push(key);
    }
  }
  for (const key of keys) if (!seen.has(key)) out.push(key);
  return out;
}

export function sameOrder(a, b) {
  return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((key, i) => key === b[i]);
}

// The slot a mouse at x drops into. edges: { left, right } of each cell on screen, in screen order. Slot i sits
// before cell i and slot edges.length after the last one. A slot is the first one whose cell has its middle right of x.
export function dropSlot(edges, x) {
  for (let i = 0; i < edges.length; i++) {
    if ((edges[i].left + edges[i].right) / 2 > x) return i;
  }
  return edges.length;
}

// The index move() needs for a drop. order: the saved order. cells and more: the keys on screen now, as fit() gave
// them. key: the cell that was dragged. slot: from dropSlot(). onMore: the drop was on the More button.
// It works by keys and not by positions, because the open cell takes the last slot, so the cells are not always the
// first of the order. A drop on a neighbour puts key before it, a drop after the last cell puts key before the first
// key in More (or last, with no More), and a drop on More puts key right after the first key in More, so that key
// is the first one behind More and the one it passed moves up into the band. key itself is never the neighbour.
export function dropIndex(order, cells, more, key, slot, onMore) {
  const at = order.indexOf(key);
  if (at < 0) return order.length;
  const others = order.filter((k) => k !== key);
  const behind = more.find((k) => k !== key && others.includes(k));
  if (onMore) return behind === undefined ? others.length : others.indexOf(behind) + 1;
  if (slot >= cells.length) return behind === undefined ? others.length : others.indexOf(behind);
  const next = cells[Math.max(0, slot)];
  if (next === key) return at;
  return others.indexOf(next) < 0 ? at : others.indexOf(next);
}

// ---------------------------------------------------------------- while arranging (direction A)

// The slot a mouse at (x, y) drops into among cells that may wrap onto several lines (the second row of the band
// editor). edges: { left, right, top, bottom } of each cell, in reading order. The line is the one whose top and
// bottom hold y, else the nearest one. In that line, the slot is the first cell whose middle is right of x, else the
// slot after the line's last cell. One line gives the same answer as dropSlot.
export function dropSlotIn(edges, x, y) {
  if (!edges.length) return 0;
  const lines = [];
  edges.forEach((e, i) => {
    const line = lines.find((l) => Math.abs(l.top - e.top) < 1);
    if (line) line.at.push(i);
    else lines.push({ top: e.top, bottom: e.bottom, at: [i] });
  });
  const gap = (l) => (y < l.top ? l.top - y : y > l.bottom ? y - l.bottom : 0);
  const line = lines.reduce((best, l) => (gap(l) < gap(best) ? l : best), lines[0]);
  for (const i of line.at) {
    if ((edges[i].left + edges[i].right) / 2 > x) return i;
  }
  return line.at[line.at.length - 1] + 1;
}

// The index move() needs for a drop while arranging, when the band shows the saved order exactly: the band row holds
// order[0..foldAt) and the second row order[foldAt..). foldAt equal to order.length means no second row. row is 0 for
// the band and 1 for the second row, slot is from dropSlot or dropSlotIn over that row's cells, and onMore is a drop
// on the More slot of the band, which counts as the second row's first slot.
// It works by keys (before the cell right of the slot), then keeps the setting in the row it was dropped in: a drop
// in the band lands at 0..foldAt-1, so the band's end slot makes it the last cell and the last cell moves under More,
// and a drop in the second row lands at foldAt or later, so the first setting under More moves up into the band.
export function dropIndexArranged(order, foldAt, key, row, slot, onMore) {
  const at = order.indexOf(key);
  if (at < 0) return order.length;
  const fold = Math.max(0, Math.min(order.length, foldAt));
  const inMore = Boolean(onMore) || row === 1;
  const keys = inMore ? order.slice(fold) : order.slice(0, fold);
  const s = onMore ? 0 : Math.max(0, Math.min(keys.length, Math.trunc(slot) || 0));
  const next = keys[s];
  if (next === key) return at;
  const others = order.filter((k) => k !== key);
  let index;
  if (next !== undefined) index = others.indexOf(next);
  else index = inMore ? others.length : fold;
  if (inMore) return Math.max(index, Math.min(fold, others.length));
  return Math.min(index, Math.max(0, fold - 1));
}
