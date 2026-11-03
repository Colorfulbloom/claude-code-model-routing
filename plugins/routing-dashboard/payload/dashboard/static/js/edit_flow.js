// The flow of the editing body (Effort, the effort cap, the model, the compact window), the rail and the undo strip on
// the Settings page: its state, kept for each project, the data readers over the newest render, and the actions (pick a
// level, pick a row, preview, save, undo, dismiss, reload). Nothing here builds a node. An action that changes what is on screen calls redraw(), which
// edit_card.js registers with onRedraw() when it loads, so this file imports nothing from it.
//
// Rules this file keeps, the same as edit_card.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.
// - The flow state lives in this module, one flow for each project. A project change saves the flow it leaves and
//   loads the one it enters. A route change keeps the flow, a page reload drops it, and a mode change to off or
//   locked clears every flow. A save or an undo awaits the page's reload, so the page draws again while a press
//   is in flight. The state survives that, and the answer draws into the nodes of the newest render.
// - A row is named by its layer, because one file can hold two targets. The target id comes from the chosen
//   level's row each time. Nothing moves to a shared file on its own, and nothing saves until Save.
// - The older backups list, and the preview of an Undo anyway or a restore, are flow state too (back). A change in
//   progress and an open back flow exclude each other. The preview writes nothing, and the confirm sends the hash
//   of the file the preview showed, so a file that changed since is refused and the preview is drawn again.
// - One change at a time. A level (with a row) or a line to remove is chosen, never both. A remove is a set with no
//   value: its preview and save carry action "remove", and its flow field holds the line's target, layer and line.
// - A change belongs to one setting, the cell it was made on (setting), and keeps the targets answer it was made from
//   (heldT). Another cell that edits opens read-only while a change is held (foreign()), and the rail and the foot keep
//   the change's review. A level that one cap change reaches (via "cap") is written through the cap, so its preview and
//   save carry the cap setting. A level that needs the cap first (cap_first) has nothing to save: Start with the cap
//   drops the pick and opens the cap cell with the same level chosen (carry).

import { t } from "./format.js";
import { olderRows, overCap, settleRow } from "./edit_pick.js";
import { basename, bodyOf, codeOf, errorText, levelRow, lockText, runningOf, targetById, walk } from "./edit_ui.js";
import { CAP, EFFORT, parseWindow, settingOf, settingOfEdit } from "./edit_setting.js";

// ---------------------------------------------------------------- state

export function flow() {
  return {
    level: null, // the level the owner picked, or null at rest. For the compact window it is "auto" or "number"
    number: null, // the whole number of a compact window change (level "number"), else null
    setting: null, // the setting of the change in progress (a level or a remove): the cell it was made on, else null
    heldT: null, // the targets answer that change was made from, so another cell can keep drawing its review
    field: null, // the compact window box: { text, note } what was typed and the note under the box, or null
    carry: null, // { setting, level } a level to choose on another cell once its targets load (Start with the cap)
    row: null, // the layer of the file row picked for that level, or null
    remove: null, // { target, layer, line, blocked } a line the owner chose to remove, or null. It excludes level
    pv: null, // { target, value, action, setting, data } the preview on screen. A remove has value null
    pending: null, // { target, value, action, setting } a preview on its way
    notice: null, // a note over the review: { kind, heading, paras, dismiss }
    frame: null, // a result that replaces the review: unverified, raced or ledger
    failed: false, // a write failed and the review stays
    failedDir: null, // the config folder a failed write found missing
    failedLeft: false, // a failed create left the folder it made
    busy: false, // a save is on its way
    strip: null, // a result of this page's own press, shown in the foot
    stripBusy: false, // an undo is on its way
    token: null, // { where } a press found no live token
    back: null, // the older backups flow: { view: "list" }, or { view: "review", kind, row, pv, busy, stale, from, shownAt }, or null
    want: null, // the control that takes focus on the next draw
    reloaded: null, // "target|value" of a preview whose op didn't match its row, so the targets were loaded once for it
  };
}

const FIELDS = Object.keys(flow());

// project and mode say whose flow S holds. seen is the last targets object settle() ran for.
export const S = { ...flow(), project: null, mode: undefined, epoch: 0, seq: 0, seen: null };
// The flows of the other projects, by project key.
const flows = new Map();
// The newest render: { ctx, selected, restRail, body, rail, pickSlot, stripSlot, foot }. Read it through this
// binding, set it through setLive().
export let live = null;

export function setLive(value) {
  live = value;
}

// edit_card.js registers its redraw here, so the actions can draw without importing the card.
let redrawer = () => {};

export function onRedraw(fn) {
  redrawer = fn;
}

function redraw(which) {
  redrawer(which);
}

function load(fields) {
  for (const name of FIELDS) S[name] = fields[name];
}

// Drops an answer on its way: a preview by the sequence, a save or an undo by the epoch.
function bump() {
  S.seq += 1;
  S.pending = null;
}

export function resetFlow() {
  load(flow());
  S.epoch += 1;
  S.seen = null;
  bump();
}

// The change in progress goes away. A result in the foot stays.
export function resetCard() {
  bump();
  S.level = null;
  S.number = null;
  S.setting = null;
  S.heldT = null;
  S.field = null;
  S.row = null;
  S.remove = null;
  S.pv = null;
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
  S.failedLeft = false;
  S.reloaded = null;
  S.back = null;
}

// Called by the page on every render with a payload, before anything is drawn. A mode change to off or locked
// clears every flow. A project change saves the flow in S, loads the new project's or a fresh one, and bumps the
// epoch and the sequence, so an answer on its way for the old project drops itself. The flow it saved no longer
// has a press in flight.
export function syncFlow(key, mode) {
  if (S.mode !== mode) {
    if (mode === "off" || mode === "locked") {
      flows.clear();
      resetFlow();
    }
    S.mode = mode;
  }
  if (S.project === key) return;
  if (S.project !== null) {
    const saved = {};
    for (const name of FIELDS) saved[name] = S[name];
    saved.busy = false;
    saved.stripBusy = false;
    saved.pending = null;
    // A preview on its way is dropped with the sequence bump below, so a review waiting on it would never fill.
    if (saved.back && saved.back.view === "review" && saved.back.pv === null) saved.back = null;
    // Not saved is read from the render that is still on screen, which is the flow's own, before the swap.
    saved.notSaved = isNotSaved();
    flows.set(S.project, saved);
  }
  load(flows.get(key) || flow());
  flows.delete(key);
  S.project = key;
  S.epoch += 1;
  S.seen = null;
  bump();
}

// ---------------------------------------------------------------- not saved

// True when a change waits on Save in the flow S holds: a level is chosen and that level can be saved somewhere, or
// a line to remove is chosen and nothing blocks it. The stop rows (a cap or the model holds the level, or nothing can
// be saved at it) have nothing to save, and neither has a level that needs the cap first. A blocked remove has nothing to
// save either, and a project that takes no save has no change at all. The picker and the rows are not part of it.
export function isNotSaved() {
  if (!live || (S.level === null && S.remove === null) || live.ctx.edit.mode !== "ready") return false;
  if (S.frame && S.frame.type !== "ledger") return false; // a raced or unverified save wrote the file
  const T = changeTargets();
  if (!T || T.enabled === false || T.levels_state === "no_effort_support") return false;
  if (T.project_lock || T.saveable === false) return false;
  if (S.remove !== null) return S.remove.blocked !== true;
  const lv = levelRow(T, S.level);
  return Boolean(lv) && lv.saveable === true && lv.cap_first !== true;
}

// The keys of the projects with a change waiting on Save: the open one, and the ones a switch put away.
export function notSavedProjects() {
  const keys = [];
  if (S.project !== null && isNotSaved()) keys.push(S.project);
  for (const [key, saved] of flows) if (saved.notSaved === true) keys.push(key);
  return keys;
}

// ---------------------------------------------------------------- data

// The setting the targets of the open cell are for: the open cell when the page edits it, else Effort, whose targets the
// page loads for a cell it cannot edit.
export function openSetting() {
  return live && live.editable ? live.selected : EFFORT;
}

// The setting of the change the flow holds: a chosen level or a remove (the cell it was made on), or the preview of an
// older backup (the setting of the row). Null at rest, and for the list of older backups, which belongs to no setting.
export function heldSetting() {
  if (S.level !== null || S.remove !== null) return S.setting;
  if (S.back !== null && S.back.view === "review") return settingOfEdit(S.back.pv || S.back.row);
  return null;
}

// True when a change is held for another setting than the open cell's. That cell draws read-only then: its picker and
// rows are off and its rows have no Remove line links, and the rail keeps the change's review.
export function foreign() {
  const held = heldSetting();
  return held !== null && held !== openSetting();
}

// The targets answer when it is usable: the object, null when it has not loaded (or belongs to another project, or to
// another setting than the open cell's, whose own answer is on its way), false when it failed. The off answer has no
// targets, and a flow draws it read-only.
export function targetsData() {
  const res = live.ctx.edit.targets;
  if (!res) return null;
  const data = res.data;
  const usable = res.ok && data && typeof data === "object" && Array.isArray(data.levels)
    && (Array.isArray(data.targets) || data.enabled === false);
  if (usable && data.project !== live.ctx.project.key) return null;
  if (usable && settingOf(data) !== openSetting()) return null;
  return usable ? data : false;
}

// The targets answer the change in progress reads: the open cell's own, or, when the change was made on another cell, the
// answer it was made from. With no change in progress it is the open cell's.
export function changeTargets() {
  const T = targetsData();
  if (S.setting === null || (S.level === null && S.remove === null)) return T;
  return openSetting() === S.setting ? T : S.heldT;
}

// The value the chosen level writes: the typed number for the compact window's number level, else the level itself.
export const changeValue = () => (S.level === "number" ? S.number : S.level);

// The setting a preview and a save of the change are sent for. A level that one cap change reaches is written through the
// cap, so it is the cap's, whatever cell it was chosen on.
export function writeSetting() {
  const T = changeTargets();
  const lv = T && S.level !== null ? levelRow(T, S.level) : null;
  return lv && lv.via === "cap" ? CAP : S.setting;
}

export function historyData() {
  const res = live.ctx.edit.history;
  const data = res && res.ok ? res.data : null;
  return data && typeof data === "object" ? data : null;
}

// A file whose ledger is damaged takes no save, and the history names it.
export function damagedFor(file, layer) {
  const history = historyData();
  const list = history && Array.isArray(history.damaged_ledgers) ? history.damaged_ledgers : [];
  return list.find((d) => d.file_display === file && (d.layer === layer || !layer)) || null;
}

// The row of the chosen level's file for a layer, or null.
export function levelFile(lv, layer) {
  const files = lv && Array.isArray(lv.files) ? lv.files : [];
  return files.find((f) => f && f.layer === layer) || null;
}

// ---------------------------------------------------------------- actions

export function tokenOutcome(where) {
  S.token = { where };
  S.busy = false;
  S.stripBusy = false;
  redraw();
}

// Cancel puts focus on the level radio. After a remove it goes back to that row's Remove line link, which the
// remove replaced.
export function cancel() {
  const back = S.remove !== null ? "remove:" + S.remove.layer : "radio";
  resetCard();
  S.want = back;
  redraw("card");
}

// Keeps the picked row valid for the chosen level, and the preview matching it. It runs after a level change, a
// pick, a refused save, and once for each new targets object the page draws. The running level chosen after a
// refresh clears the flow. A row that went grey lands on the local file or on nothing, never on another file.
export function settle(fresh = false) {
  if (!live || S.busy || live.ctx.edit.mode !== "ready" || foreign()) return;
  if (S.level === null && S.remove !== null) {
    settleRemove(fresh);
    return;
  }
  if (S.level === null) return;
  const T = targetsData();
  if (!T || T.enabled === false) return;
  if (T.project_lock || T.saveable === false) {
    resetCard(); // a refresh brought a lock: nothing can be saved, so the chosen level goes
    return;
  }
  const lv = levelRow(T, S.level);
  // The running level chosen after a refresh clears the flow. So does a window number that now runs.
  if (!lv || lv.result === "now" || runningOf(T) === S.level || (S.level === "number" && T.runs_as === S.number)) {
    resetCard();
    return;
  }
  S.heldT = T;
  S.row = settleRow(lv, S.row);
  const file = S.row === null ? null : levelFile(lv, S.row);
  if (!file || !file.target) {
    S.row = null;
    if (S.pv !== null || S.pending !== null) bump();
    S.pv = null;
    return;
  }
  if (S.frame) return;
  const same = (x) => x && x.target === file.target && x.value === changeValue();
  // fresh: begin() handed a new targets answer, so a preview made from the old files is asked for again.
  if ((!fresh && same(S.pv)) || same(S.pending)) return;
  S.pv = null;
  startPreview(file.target, changeValue());
}

// The remove path of settle(): the chosen line is still in the targets answer, and the preview matches it. A line that
// is gone, or locked for any reason but a repeated key, ends the remove. A repeated key blocks it and draws no preview.
function settleRemove(fresh) {
  const T = targetsData();
  if (!T || T.enabled === false) return;
  S.heldT = T;
  if (T.project_lock || T.saveable === false) {
    resetCard();
    return;
  }
  const entry = targetById(T, S.remove.target);
  const lock = entry && entry.remove ? entry.remove.lock_reason : undefined;
  if (!entry || !entry.remove || (lock !== null && lock !== undefined && lock !== "repeated_key")) {
    resetCard();
    return;
  }
  S.remove.layer = entry.layer;
  S.remove.line = entry.line;
  if (lock === "repeated_key") {
    if (S.pv !== null || S.pending !== null) bump();
    S.remove.blocked = true;
    S.pv = null;
    return;
  }
  S.remove.blocked = false;
  if (S.frame) return;
  const same = (x) => x && x.target === S.remove.target && x.action === "remove";
  if ((!fresh && same(S.pv)) || same(S.pending)) return;
  S.pv = null;
  startPreview(S.remove.target, null, "remove");
}

// True when the page can take a pick: edits are on, the project takes a save and a level can be saved somewhere.
function pickable(T) {
  return Boolean(T) && T.enabled !== false && live.ctx.edit.mode === "ready" && !T.project_lock && T.saveable !== false;
}

// Chooses a level on the open cell and asks for its preview. Returns null when nothing was chosen (the running level, a
// level held by a cap or the allowed models list, a press while a save is on its way, a cell that is read-only now), else
// { hadResult }, true when the result of the last save left the foot. number is the whole number of the compact window's
// number level. Nothing is written: a preview writes nothing, and only Save does.
function choose(value, number = null) {
  if (S.busy || !live || S.remove !== null || S.back !== null || foreign()) return null;
  const T = targetsData();
  if (!pickable(T)) return null;
  const lv = levelRow(T, value);
  if (!lv || lv.result === "now" || runningOf(T) === value || overCap(lv) || lv.allow === "blocked") return null;
  if (value === "number" && T.runs_as === number) return null; // the window that runs now, typed again
  bump(); // an older preview answer still on its way is dropped
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
  S.failedLeft = false;
  S.pv = null;
  S.reloaded = null;
  S.field = null;
  S.level = value;
  S.number = value === "number" ? number : null;
  S.setting = openSetting();
  S.heldT = T;
  const hadResult = Boolean(S.strip) && !S.stripBusy;
  if (hadResult) S.strip = null; // a new edit starts
  settle();
  return { hadResult };
}

// The owner picked a level. Pressing the running level, or any level while a save is on its way, does nothing.
export function pick(value, number = null) {
  const done = choose(value, number);
  if (done) redraw(done.hadResult ? undefined : "card"); // the body, the rail and the foot's buttons, and the strip only when its result went
}

// The owner committed the compact window box (Enter or blur). Commas and spaces are dropped, then it must be a whole
// number from 100000 to 1000000, else the box keeps what was typed, says so, and nothing is picked. The number that runs
// now, or the one already chosen, picks nothing. The box is drawn again either way, so it shows the state.
export function commitWindow(raw) {
  if (S.busy || !live || S.remove !== null || S.back !== null || foreign()) return;
  if (!pickable(targetsData())) return;
  const parsed = parseWindow(raw);
  if (!parsed.ok) {
    S.field = { text: String(raw === null || raw === undefined ? "" : raw), note: "bad" };
    redraw("card");
    return;
  }
  S.field = null;
  const done = S.level === "number" && S.number === parsed.value ? null : choose("number", parsed.value);
  redraw(done && done.hadResult ? undefined : "card");
}

// The owner pressed Auto. When the dashboard has no model, Auto has no line to go in (it is written under a model only),
// so the box says so and nothing is picked.
export function pickAuto() {
  if (S.busy || !live || S.remove !== null || S.back !== null || foreign()) return;
  const T = targetsData();
  if (!pickable(T)) return;
  const lv = levelRow(T, "auto");
  if (lv && lv.result !== "now" && lv.saveable !== true && (T.model === null || T.model === undefined)) {
    S.field = { text: null, note: "nomodel" };
    redraw("card");
    return;
  }
  S.field = null;
  const done = choose("auto");
  redraw(done && done.hadResult ? undefined : "card");
}

// The owner picked a file row for the chosen level. Only that row's target is previewed.
export function pickRow(layer) {
  if (S.busy || !live || S.level === null || S.remove !== null || S.back !== null || foreign()) return;
  const T = targetsData();
  if (!pickable(T)) return;
  const file = levelFile(levelRow(T, S.level), layer);
  if (!file || file.pickable !== true || !file.target) return;
  bump();
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
  S.failedLeft = false;
  S.pv = null;
  S.reloaded = null;
  S.row = layer;
  startPreview(file.target, changeValue());
  redraw("card");
}

// The owner pressed Remove line on a file row at rest. file is the row of the targets answer's files list. One change
// at a time, so it does nothing while a level or another remove is chosen or a save is on its way. A line with no
// target, or one the server locks for any reason but a repeated key, does nothing. A repeated key opens the blocked
// rail and asks for no preview. Cancel is where focus goes, because the pressed link goes away.
export function startRemove(file) {
  if (S.busy || !live || S.level !== null || S.remove !== null || S.back !== null || foreign()) return;
  const T = targetsData();
  if (!pickable(T) || !file || !file.target) return;
  const entry = targetById(T, file.target);
  if (!entry || !entry.remove) return;
  const lock = entry.remove.lock_reason;
  if (lock !== null && lock !== undefined && lock !== "repeated_key") return;
  bump();
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
  S.failedLeft = false;
  S.pv = null;
  S.reloaded = null;
  S.remove = { target: entry.target, layer: entry.layer, line: entry.line, blocked: lock === "repeated_key" };
  S.setting = openSetting();
  S.heldT = T;
  const hadResult = Boolean(S.strip) && !S.stripBusy;
  if (hadResult) S.strip = null; // a new edit starts
  if (!S.remove.blocked) startPreview(entry.target, null, "remove");
  S.want = "cancel";
  redraw(hadResult ? undefined : "card");
}

// "Start with the cap": the pick on the Effort cell goes, and the Effort cap cell opens with the same level to choose in the
// cap picker once its own targets load. The normal settle then applies that level's preselect (the local file, or none).
// Nothing is written. The cell is opened through ctx.edit.openSetting, the same address the band's cell links to.
export function startWithCap(level) {
  if (S.busy || !live || S.back !== null || typeof level !== "string") return;
  const goTo = live.ctx.edit.openSetting;
  if (typeof goTo !== "function") return;
  const from = S.setting !== null ? S.setting : openSetting();
  resetCard();
  S.carry = { setting: CAP, level, from };
  redraw("card");
  goTo(CAP);
}

// Called by the card on every render. Once the targets of the cell Start with the cap named are in, the level it carried is
// chosen there. A carry waits while those targets load, and goes when the owner has gone to a cell that is neither the one
// it left nor the one it named. Returns true when it chose a level.
export function applyCarry() {
  const carry = S.carry;
  if (carry === null || !live) return false;
  if (live.selected !== carry.setting) {
    if (live.selected !== carry.from) S.carry = null;
    return false;
  }
  const T = targetsData();
  if (T === null) return false;
  S.carry = null;
  return T !== false && choose(carry.level) !== null;
}

// True when the preview's op isn't the op the targets answer gave for the file row of that target.
function opDiffers(target, value, data) {
  const T = changeTargets();
  const lv = T && S.level !== null ? levelRow(T, S.level) : null;
  const file = lv && Array.isArray(lv.files) ? lv.files.find((f) => f && f.target === target) : null;
  return Boolean(file) && file.op !== data.op;
}

// The heading of a refused answer. The project folder going away says so for the two files inside it. Any other
// answer is worded by its code.
function failHeading(out, layer, setting) {
  if (codeOf(out) === "file_missing") {
    if (layer === "local" || layer === "project") return t("ed_fail_project_gone");
    return lockText("file_missing") || errorText(out && out.res, setting);
  }
  return errorText(out && out.res, setting);
}

export async function startPreview(target, value, action = "set") {
  const mine = S.seq;
  const epoch = S.epoch;
  const layer = action === "remove" && S.remove ? S.remove.layer : S.row;
  const setting = writeSetting();
  S.pending = { target, value, action, setting };
  let out;
  try {
    out = await live.ctx.edit.preview(target, value, action, setting);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    tokenOutcome("card");
    return;
  }
  if (mine !== S.seq || epoch !== S.epoch) return;
  S.pending = null;
  const data = bodyOf(out);
  if (out && out.kind === "ok" && data.diff) {
    // A preview whose op isn't its row's op means the targets are old. They load once for this preview, and Save
    // doesn't show until a preview is drawn from the new ones. A second mismatch for the same target and value
    // never shows Save: the owner picks a file again.
    if (opDiffers(target, value, data)) {
      if (S.reloaded !== target + "|" + value) {
        S.reloaded = target + "|" + value;
        redraw("card");
        refreshEdit();
        return;
      }
      S.pv = null;
      S.row = null;
      S.notice = { kind: "err", heading: t("ed_op_mismatch"), paras: [], dismiss: true };
      redraw("card");
      return;
    }
    S.pv = { target, value, action, setting, data };
  } else {
    S.notice = { kind: "err", heading: failHeading(out, layer, setting), paras: [], dismiss: true };
  }
  redraw("card");
}

export function staleNotice(data) {
  const files = Array.isArray(data.changed_files) ? data.changed_files : [];
  const names = files.map((f) => basename(f.file_display));
  const fresh = data.preview && typeof data.preview === "object" ? data.preview : null;
  let heading;
  let paras = [];
  if (data.changed === "trail") {
    heading = t("ed_stale_trail_h");
    paras = [names.length ? t("ed_stale_trail_t", { files: names.join(", ") }) : t("ed_stale_trail_general_t")];
  } else {
    const file = names[0] || basename(S.pv && S.pv.data.diff ? S.pv.data.diff.file_display : "");
    if (data.changed === "file_appeared") {
      heading = t("ed_stale_appeared_h", { file });
      paras = [t("ed_stale_appeared_t")];
    } else if (data.changed === "file_removed") {
      heading = t("ed_stale_removed_h", { file });
      paras = [t("ed_stale_removed_t")];
    } else {
      heading = t("ed_stale_file_h", { file });
      paras = [t("ed_stale_file_t")];
    }
  }
  if (!fresh) paras = [t("ed_stale_gone_t")];
  // With no fresh preview the notice sits alone over the rest rail, so it needs a Dismiss.
  return { notice: { kind: "warn", heading, paras, dismiss: !fresh }, fresh };
}

// A save the server refused for what the file is now: not editable (400) or locked by a reason (422). The review
// is gone, the notice stays, and the page loads the files again so settle() lands on a row that still takes a save.
function refused(out) {
  const status = out && out.res && typeof out.res.status === "number" ? out.res.status : 0;
  return status === 422 || (status === 400 && codeOf(out) === "not_editable");
}

// A save answer that landed after a project switch. The flow it belongs to is the put-away one for that project, or
// S itself when the owner switched back before the answer came. A saved file clears the change and shows the result;
// a stale or refused one only drops the preview and the row, so the owner picks again. Anything else changes nothing.
function landLate(key, out, sent) {
  const holder = key === S.project ? S : flows.get(key);
  if (!holder) return;
  const kind = out ? out.kind : "error";
  if (kind === "ok") {
    const data = bodyOf(out);
    holder.level = null;
    holder.number = null;
    holder.setting = null;
    holder.heldT = null;
    holder.field = null;
    holder.row = null;
    holder.remove = null;
    holder.pv = null;
    holder.notice = null;
    holder.frame = null;
    holder.failed = false;
    holder.failedDir = null;
    holder.failedLeft = false;
    holder.reloaded = null;
    holder.notSaved = false;
    holder.strip = savedStrip(data, sent);
  } else if (kind === "stale" || refused(out)) {
    holder.pv = null;
    holder.row = null;
    if (kind !== "stale") holder.remove = null; // a refused remove is over, a stale one asks for its preview again
  } else {
    return;
  }
  if (holder === S) redraw();
  else syncShellList();
}

// The picker draws Not saved from the put-away flows, so it is told when one of them changes.
function syncShellList() {
  if (live && typeof live.ctx.edit.syncShell === "function") live.ctx.edit.syncShell();
}

// The result a save leaves in the foot. The preview it was made from says what the change did to what runs.
function savedStrip(data, sent) {
  const edit = data.edit || {};
  return {
    kind: "saved",
    setting: Array.isArray(edit.key_path) ? settingOfEdit(edit) : sent.setting || EFFORT,
    edit,
    warning: sent.data.warning || null,
    noEffect: sent.data.no_effect === true,
    runsAfter: sent.data.runs_after,
  };
}

export async function doSave() {
  if (S.busy || !S.pv || !live) return;
  const epoch = S.epoch;
  const key = S.project; // whose flow this save belongs to, read before the await
  const sent = S.pv;
  const fileName = basename(sent.data.diff ? sent.data.diff.file_display : "");
  S.busy = true;
  S.failed = false;
  S.failedDir = null;
  S.failedLeft = false;
  S.notice = null;
  if (!S.stripBusy) S.strip = null;
  redraw();
  let out;
  try {
    out = await live.ctx.edit.save(sent.data, sent.target, sent.value, sent.action, sent.setting);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    tokenOutcome("card");
    return;
  }
  if (epoch !== S.epoch) {
    // Another project's flow, or a cleared one, owns S now, but the file may be written. Its flow hears the outcome.
    landLate(key, out, sent);
    return;
  }
  S.busy = false;
  const data = bodyOf(out);
  const kind = out ? out.kind : "error";
  let reload = false;
  if (kind === "ok") {
    resetCard();
    S.strip = savedStrip(data, sent);
    S.want = data.edit && data.edit.undoable === true ? "undo" : "radio";
  } else if (kind === "stale") {
    const stale = staleNotice(data);
    S.notice = stale.notice;
    S.pv = stale.fresh ? { target: sent.target, value: sent.value, action: sent.action, setting: sent.setting, data: stale.fresh } : null;
    if (!stale.fresh) {
      S.row = null;
      S.remove = null; // the line to remove is gone, so the notice stays over the rest rail
    }
    reload = true;
  } else if (kind === "raced") {
    S.pv = null;
    S.frame = { type: "raced", file: fileName, path: data.backup_display || null, op: sent.data.op };
    S.want = "dismiss-card";
  } else if (kind === "unverified") {
    S.pv = null;
    S.frame = { type: "unverified", stage: data.stage, path: data.backup_display || null, op: sent.data.op };
    S.want = "dismiss-card";
  } else if (codeOf(out) === "ledger_damaged") {
    S.pv = null;
    S.frame = { type: "ledger", file: fileName, path: data.ledger_display || null };
    S.want = "dismiss-ledger";
  } else if (codeOf(out) === "config_dir_missing" && data.config_dir_display) {
    S.failed = true;
    S.failedDir = data.config_dir_display;
    S.want = "try";
  } else if (codeOf(out) === "write_failed") {
    S.failed = true;
    S.failedLeft = data.dir_left === true;
    S.want = "try";
  } else if (refused(out)) {
    S.pv = null;
    S.remove = null;
    S.notice = { kind: "err", heading: failHeading(out, sent.data.layer, sent.setting), paras: [], dismiss: true };
    reload = true;
  } else {
    S.notice = { kind: "err", heading: errorText(out && out.res, sent.setting), paras: [], dismiss: true };
  }
  redraw();
  if (S.failed) showFailure();
  if (reload) refreshEdit(); // the page data is old now; this never retries the save
}

// The failed-write notice closes the review, so on a short rail it can sit below the fold. It scrolls into view and
// focus stays on Try again. A node with no scrollIntoView (an old browser, the test dom) is left alone.
function showFailure() {
  if (!live || !live.rail) return;
  const isNote = (n) => String(n.getAttribute("class") || "").split(/\s+/).includes("p2-nt-err");
  const note = walk(live.rail, isNote)[0];
  if (note && typeof note.scrollIntoView === "function") note.scrollIntoView({ block: "nearest" });
}

// The strip an undo answer leaves, and whether the page must load the history again.
function undoOutcome(out, row) {
  const data = bodyOf(out);
  const kind = out ? out.kind : "error";
  const code = codeOf(out);
  const file = basename(row.file_display);
  if (kind === "ok" && data.matches_backup === true) {
    return {
      strip: {
        kind: "undone",
        edit: data.edit || row,
        restored: data.restored_from_display || null,
        removedFile: data.removed_file === true,
        removedDir: data.removed_dir === true,
      },
      want: "dismiss-strip",
    };
  }
  if (kind === "ok" || kind === "raced") {
    return { strip: { kind: "raced", file, path: data.restored_from_display || null, op: row.op }, want: "dismiss-strip" };
  }
  if (kind === "unverified") {
    return { strip: { kind: "unverified", stage: data.stage, path: data.backup_display || null, op: row.op }, want: "dismiss-strip" };
  }
  if (kind === "stale" || code === "stale") {
    return { strip: { kind: "stale_undo", file, path: data.backup_display || null, op: row.op, row }, changed: true };
  }
  if (code === "unknown_edit") {
    // The history row is gone (a created file deleted by hand trims it), so the page loads the history again.
    return { strip: { kind: "error", text: errorText(out && out.res) }, changed: true };
  }
  if (code === "changed_since_save") {
    return { strip: { kind: "stale_undo", file, path: data.backup_display || null, op: row.op, row }, changed: true };
  }
  if (code === "backup_damaged") return { strip: { kind: "backup_damaged", path: data.backup_display || null }, want: "dismiss-strip", changed: true };
  // A pruned backup is gone for good, so the answer says so and the page loads the history again to grey the row.
  if (code === "not_undoable" && data.reason === "backup_pruned") {
    return { strip: { kind: "error", text: t("ed_older_pruned") }, want: "dismiss-strip", changed: true };
  }
  if (code === "not_undoable") return { strip: { kind: "not_undoable" }, want: "dismiss-strip", changed: true };
  if (code === "config_dir_missing" && data.config_dir_display) {
    return { strip: { kind: "config_dir_missing", path: data.config_dir_display }, want: "dismiss-strip", changed: true };
  }
  if (code === "write_failed") return { strip: { kind: "write_failed", file, dirLeft: data.dir_left === true }, want: "dismiss-strip", changed: true };
  if (code === "ledger_damaged") return { strip: { kind: "ledger", file, path: data.ledger_display || null }, want: "dismiss-strip", changed: true };
  return { strip: { kind: "error", text: errorText(out && out.res) }, changed: true };
}

export async function doUndo(row) {
  if (S.stripBusy || !live || S.back !== null) return;
  const epoch = S.epoch;
  const key = S.project; // whose flow this undo belongs to, read before the await
  S.stripBusy = true;
  redraw("strip");
  let out;
  try {
    out = await live.ctx.edit.undo(row.id);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    tokenOutcome("strip");
    return;
  }
  const result = undoOutcome(out, row);
  if (epoch !== S.epoch) {
    // The file may be restored. The flow it belongs to shows the result in place of an Undo that is spent.
    const holder = key === S.project ? S : flows.get(key);
    if (holder) {
      holder.strip = result.strip;
      holder.stripBusy = false;
      if (holder === S) redraw("strip");
    }
    return;
  }
  S.stripBusy = false;
  S.strip = result.strip;
  if (result.want) S.want = result.want;
  redraw("strip");
  if (result.changed) refreshEdit(); // the history still lists an Undo that no longer works, so Dismiss must not bring it back
}

// ---------------------------------------------------------------- older backups

// The strip an Undo anyway or a restore answer leaves, and whether the page must load the history again. A written
// file that matches its backup is a back_done strip. The refusals only the new routes make are worded here, and every
// other answer is a plain undo's. pv is the preview the write was made from, or null for a refused preview.
function backOutcome(out, row, kind, pv = null) {
  const data = bodyOf(out);
  const code = codeOf(out);
  if (out && out.kind === "ok" && data.matches_backup === true) {
    return {
      strip: {
        kind: "back_done",
        back: kind,
        edit: data.edit || row,
        removedFile: data.removed_file === true,
        removedDir: data.removed_dir === true,
        replacedFile: data.replaced_file !== false,
        replaced: data.replaced_display || null,
        replacedUnparsed: pv !== null && pv.file_unparsed === true,
        restored: data.restored_from_display || null,
      },
      want: "dismiss-strip",
    };
  }
  // A forced write keeps the bytes it wrote over, so op doesn't say whether a backup exists. The backup is named when the
  // answer names one, and a file that was absent before the write (result create) has none.
  const created = pv !== null && pv.result === "create";
  const kept = created ? null : data.backup_display || data.replaced_display || null;
  if (out && (out.kind === "raced" || out.kind === "ok")) {
    return { strip: { kind: "back_raced", file: basename(row.file_display), path: kept, created }, want: "dismiss-strip" };
  }
  if (out && out.kind === "unverified") {
    return { strip: { kind: "back_unverified", stage: data.stage, path: kept }, want: "dismiss-strip" };
  }
  if (code === "backup_unparsed") return { strip: { kind: "error", text: t("ed_backup_unparsed_h") }, changed: true };
  if (code === "no_change") return { strip: { kind: "error", text: t("ed_back_no_change_h") }, changed: true };
  const result = undoOutcome(out, row);
  const restoreKinds = ["write_failed", "backup_damaged", "config_dir_missing"];
  if (kind === "restore" && restoreKinds.includes(result.strip.kind)) result.strip.restore = true;
  return result;
}

// How long after a preview draws the confirm ignores a press. A property, so the browser-free checks can set it to 0.
export const guard = { ms: 500 };

// The list or the review closes the strip, so on a short window its heading can sit below the fold. At 1240 and under,
// where the rail sits under the body, it scrolls into view and focus stays where it is. A notice drawn above the heading
// is what scrolls, so the owner sees it too. A node with no scrollIntoView (an old browser, the test dom) is left alone.
const DOCKED = "(max-width: 1240px)";
function showBackHead() {
  if (!live || !live.rail) return;
  if (typeof window === "undefined" || typeof window.matchMedia !== "function" || !window.matchMedia(DOCKED).matches) return;
  const has = (n, name) => String(n.getAttribute("class") || "").split(/\s+/).includes(name);
  const first = walk(live.rail, (n) => has(n, "s4-rh") || has(n, "nt"))[0];
  if (first && typeof first.scrollIntoView === "function") first.scrollIntoView({ block: "start" });
}

// True when a back flow may not open: a save or an undo is on its way, or a change is in progress.
const backBlocked = () => S.busy || S.stripBusy || !live || S.level !== null || S.remove !== null;

// The key of the first row the list offers, or the Close button when none is.
function firstBackFocus() {
  const first = olderRows(historyData()).find((row) => row.restore_state === null || row.restore_state === undefined);
  return first ? "backup:" + first.id : "older-close";
}

// The owner pressed Older backups. The list takes the rail and the foot, and the last change waits.
export function openOlder() {
  if (backBlocked()) return;
  S.back = { view: "list" };
  S.strip = null;
  S.want = firstBackFocus();
  redraw("card");
  showBackHead();
}

// Close, or Cancel. A review opened from the list goes back to the list, with focus on its row. Any other goes back to
// rest, with focus on the Older backups link. Nothing happens while a write is on its way.
export function closeBack() {
  const back = S.back;
  if (back === null || back.busy === true) return;
  if (back.view === "review" && back.from === "list") {
    const row = olderRows(historyData()).find((r) => r.id === back.row.id && (r.restore_state === null || r.restore_state === undefined));
    S.back = { view: "list" };
    S.want = row ? "backup:" + row.id : "older-close";
  } else {
    S.back = null;
    S.want = back.from === "foot" ? "anyway" : "older"; // the control that opened it, else the other
  }
  redraw("card");
}

// The owner picked a row (kind "restore", from the list) or pressed Undo anyway (kind "undo", from the foot). The review
// opens with no preview, and the preview is asked for. An answer that comes after the review went away is dropped.
export async function startBack(kind, row, from) {
  if (backBlocked()) return;
  S.strip = null;
  bump();
  const mine = S.seq;
  const epoch = S.epoch;
  const review = { view: "review", kind, row, pv: null, busy: false, stale: false, from, shownAt: 0 };
  S.back = review;
  S.want = "cancel";
  redraw("card");
  let out;
  try {
    out = await live.ctx.edit.backupPreview(row.id, kind);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  // A lost token is told even when the review went away, as startPreview does.
  if (out && out.kind === "locked") {
    if (epoch === S.epoch && S.back === review) S.back = null;
    tokenOutcome("strip");
    return;
  }
  if (mine !== S.seq || epoch !== S.epoch || S.back !== review) return;
  if (out && out.kind === "ok") {
    review.pv = bodyOf(out);
    review.shownAt = Date.now();
    S.want = "cancel";
    redraw("card");
    showBackHead();
    return;
  }
  const result = backOutcome(out, row, kind);
  S.back = null;
  S.strip = result.strip;
  S.want = result.want || "dismiss-strip";
  redraw();
  if (result.changed) refreshEdit();
}

// The owner confirmed. The preview's hash goes with the write, so a file that changed since is refused (stale), and
// the answer then carries the preview of the file as it is.
export async function confirmBack() {
  const back = S.back;
  if (!live || back === null || back.view !== "review" || back.pv === null || back.busy) return;
  // A double click on Undo anyway lands on the confirm that replaces it. A press this soon after the preview drew is
  // dropped, with no sign, because the owner can't have read the preview yet.
  if (Date.now() - back.shownAt < guard.ms) return;
  const epoch = S.epoch;
  const key = S.project; // whose flow this write belongs to, read before the await
  const { kind, row } = back;
  const baseFile = back.pv.base_file;
  back.busy = true;
  redraw("card");
  let out;
  try {
    out = kind === "undo" ? await live.ctx.edit.undoAnyway(row.id, baseFile) : await live.ctx.edit.restore(row.id, baseFile);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    if (epoch === S.epoch) S.back = null;
    tokenOutcome("strip");
    return;
  }
  const stale = out && out.kind === "stale";
  const fresh = stale && bodyOf(out).preview && typeof bodyOf(out).preview === "object" ? bodyOf(out).preview : null;
  const result = stale ? { strip: { kind: "error", text: t("ed_back_gone_t") }, changed: true } : backOutcome(out, row, kind, back.pv);
  if (epoch !== S.epoch) {
    // The file may be written. The flow it belongs to shows the result in place of a review that is spent.
    const holder = key === S.project ? S : flows.get(key);
    if (holder) {
      holder.strip = result.strip;
      holder.back = null;
      if (holder === S) redraw();
    }
    if (result.changed) refreshEdit();
    return;
  }
  if (stale && fresh) {
    // Nothing was written. The review shows the file as it is now, and the page loads the files again.
    back.pv = fresh;
    back.stale = true;
    back.busy = false;
    back.shownAt = Date.now();
    S.want = "cancel";
    redraw("card");
    showBackHead();
    refreshEdit();
    return;
  }
  S.back = null;
  S.strip = result.strip;
  S.want = result.want || "dismiss-strip";
  redraw();
  if (result.changed) refreshEdit();
}

export function dismissStrip() {
  const wasLedger = S.strip && S.strip.kind === "ledger";
  S.strip = null;
  S.want = "older"; // the row's own strip is back; focus goes to the Older backups link, else Undo anyway, else the levels
  redraw("strip");
  if (wasLedger) reloadEdit();
}

export function dismissLedger() {
  resetCard();
  redraw("card");
  reloadEdit();
}

export function reloadEdit() {
  if (live && live.ctx.edit && typeof live.ctx.edit.reload === "function") live.ctx.edit.reload();
}

// A file changed behind the page's back, so the tiles and the rows are old too, not only the targets and history.
export function refreshEdit() {
  if (live && live.ctx.edit && typeof live.ctx.edit.refresh === "function") live.ctx.edit.refresh();
  else reloadEdit();
}
