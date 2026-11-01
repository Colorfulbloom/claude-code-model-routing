// Which settings get a cell in the Settings band and which go behind More. Pure: no DOM and no storage.
//
// The band is as wide as the page leaves it. Each cell needs minCell pixels, so width / minCell is the number
// of slots, and at least two (a cell and More). When every key has a slot, all of them show and More does not
// appear. Otherwise one slot is More and the rest keep the first keys in the saved order. The cell the person
// has open always shows: if it was in More, it takes the last cell slot and the key it displaced goes first in
// More. No other cell moves, and the saved order itself is never changed.
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
