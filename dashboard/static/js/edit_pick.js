// The pure rules of the Effort picker and its rail: which level radio is checked and which are off, which of the
// eleven rail cases the page is in, and where the picked row lands after a refresh. No DOM, no state, no copy. What
// the flow knows comes in as arguments, and the answers are plain values.
//
// Owner rules these functions keep.
// - Nothing moves to a shared file on its own. preselect is the local file or null, and settleRow never lands on
//   another file when the picked row goes away.
// - A level a cap holds is off and says over cap, so a press and the arrow keys skip it.
// - Pressing the running level does nothing. It stays checked at rest, and once a level is chosen it is off, so
//   arrows and presses both skip it. Only Cancel goes back.
// - The checked radio always equals the chosen level, so a handler never has to put it back.

const name = (level) => (level !== null && typeof level === "object" ? level.level : level);

// True for a level row that a cap holds and nothing can be saved at (a level a cap only lowers can be saved, so it
// stays pressable and opens the review with its warning): the picker shows it as over cap and turns it
// off (board a-norm), so it can't be pressed and the arrow keys skip it. The model and the winner still open the stop.
export const overCap = (level) => Boolean(level) && typeof level === "object" && level.result === "stopped"
  && level.saveable !== true && Array.isArray(level.limits) && level.limits.some((limit) => limit && limit.kind === "cap");

// { checked, disabled } for the level radios. levels is the list of level rows (or names), running the level that
// runs now, chosen the level the owner picked (or null). mode is the edit mode. busy, projectLock and saveable come
// from the flow and the targets answer.
export function pickerState(levels, running, chosen, mode, { busy = false, projectLock = null, saveable = true } = {}) {
  const names = (Array.isArray(levels) ? levels : []).map(name);
  const now = running === undefined ? null : running;
  if (mode !== "ready" || projectLock || saveable === false) return { checked: now, disabled: names.slice() };
  const picked = chosen !== undefined && chosen !== null && chosen !== now ? chosen : null;
  const checked = picked !== null ? picked : now;
  if (busy) return { checked, disabled: names.slice() };
  const off = (Array.isArray(levels) ? levels : []).filter(overCap).map(name);
  if (picked !== null && now !== null && !off.includes(now)) off.push(now);
  return { checked, disabled: off };
}

const limitsOf = (levelRow) => (levelRow && Array.isArray(levelRow.limits) ? levelRow.limits : []);

// The case the rail is in. The first match wins, in this order. remove is the flow's chosen line, { blocked }, or null.
//   project_lock    the project can't take a save at all (any mode)
//   off, locked     editing is off, or locked behind the token
//   remove          a line to remove is chosen and its review is on screen or on its way
//   remove_blocked  the chosen line can't be removed here (the setting is in the file more than once)
//   nothing_project nothing can be saved at project level
//   rest            no level is chosen
//   review          the chosen level has a row to save to
//   pick_file       the chosen level can be saved, but no row is picked yet
//   stop            the chosen level is stopped by a cap or by the model
//   nothing_level   nothing can be saved at this level
export function railCase({ mode, projectLock, saveable, level, row, levelRow, remove = null }) {
  if (projectLock) return "project_lock";
  if (mode === "off") return "off";
  if (mode === "locked") return "locked";
  if (mode !== "ready") return "rest";
  if (remove !== null && remove !== undefined) return remove.blocked === true ? "remove_blocked" : "remove";
  if (saveable === false) return "nothing_project";
  if (level === null || level === undefined || level === "") return "rest";
  const can = Boolean(levelRow && levelRow.saveable === true);
  if (can && row !== null && row !== undefined && row !== "") return "review";
  if (can) return "pick_file";
  if (limitsOf(levelRow).some((limit) => limit && (limit.kind === "cap" || limit.kind === "model"))) return "stop";
  return "nothing_level";
}

const pickable = (levelRow, layer) => Boolean(layer && levelRow && Array.isArray(levelRow.files)
  && levelRow.files.some((file) => file && file.layer === layer && file.pickable === true));

// The layer of the row to keep after the files changed: the current one while that level's row is still pickable,
// else the row of the level's preselect (the local file, by the server's rule), else null.
export function settleRow(levelRow, currentLayer) {
  if (!levelRow || !Array.isArray(levelRow.files)) return null;
  if (pickable(levelRow, currentLayer)) return currentLayer;
  const target = levelRow.preselect;
  if (target === null || target === undefined) return null;
  const file = levelRow.files.find((f) => f && f.target === target && f.pickable === true);
  return file ? file.layer : null;
}
