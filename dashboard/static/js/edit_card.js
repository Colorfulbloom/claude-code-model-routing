// The Effort body, its rail and its foot on the Settings page (round 6 design, direction A), and the results in the
// foot. pages/settings.js calls begin(ctx, { restRail, selected, onNotSaved }) once per render with a payload and
// places what comes back. The page reads ctx.edit (js/edit_session.js through app.js): the mode, the targets and the history, and
// it sends the preview, the save and the undo. The boards a-rest, a-norm, a-lock and a-shell in the phase 2
// design folder (design-settings-6) are the reference, and app.css holds every class used here (section
// "Settings page, round 6").
//
// This file holds the shell, the picker, the rows, the rail, the foot, the drawing and the focus. The rest sits
// beside it.
// - edit_pick.js: the pure rules (which radio is checked and off, which rail case, where the picked row lands).
// - edit_flow.js: the state and the actions. It draws through the redraw() registered here.
// - edit_review.js and edit_foot.js: the pure builders of the review (rail) with its Save and Cancel (foot), and of
//   the results (foot).
// - edit_ui.js: the small shared builders.
//
// Rules this file keeps.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.
// - The flow state lives in edit_flow.js, one flow for each project. A save or an undo awaits the page's reload,
//   so the page draws again while a press is in flight. The state survives that, and the answer draws into the
//   nodes of the newest render.
// - Choosing a level or a row redraws the body, the rail and the foot without a page render. A page render
//   rebuilds all three, so focusKey() and done() carry an edit control's focus across it.
// - A chosen level keeps its review in the rail and its Save and Cancel in the foot on every cell, and the body
//   of any other cell is its read-only frame. One Save exists in the page, never a copy for a narrow window.
// - One change at a time. A chosen level or a line chosen for removal holds the page: the picker is off, the rows
//   lose their Remove line links, and the review and its Save and Cancel take the rail and the foot.
// - A chosen level that can be saved, or a line to remove that nothing blocks, is Not saved. A choice made with no page render updates the Stat band
//   (onNotSaved) and the project picker (ctx.edit.syncShell) by the callbacks the page and app.js pass in.
// - The checked radio always equals the chosen level, and a row that goes grey takes no focus. A handler never
//   puts a radio back.

import { h, clear, frag } from "./h.js";
import { t, tn } from "./format.js";
import { icon } from "./icons.js";
import { MAIN_KEY } from "./router.js";
import { pickerState, railCase } from "./edit_pick.js";
import {
  S, live, setLive, onRedraw, syncFlow, settle, targetsData, historyData, damagedFor, levelFile, isNotSaved, notSavedProjects,
  cancel, pick, pickRow, startRemove, doSave, doUndo, dismissStrip, dismissLedger, resetCard,
} from "./edit_flow.js";
import { capsOf, limitLine, limitParas, review, reviewFacts, reviewFoot, stopPanel, waitingFoot } from "./edit_review.js";
import { stripNodes as footNodes } from "./edit_foot.js";
import {
  basename, button, checkIcon, draw, filesOf, hint, levelRow, levelsOf, lockIcon, lockLine, lockText, mark, nt,
  rowLockText, runningOf, targetById, text, tokenNt, walk,
} from "./edit_ui.js";
import { valueString, valueText } from "./pages/settings.js";
import { entriesOf, entryRow, rowFor, rowNode, shortFile, whereList } from "./pages/where.js";

export { basename };

const SETTING = "effortLevel";
const FILE_LAYERS = ["local", "project", "user"];
const NOTE_ID = "p2-levels-note";
const NBSP = " ";

// ---------------------------------------------------------------- builders

// The plain card of the page, with a heading that is plain text. Only a model with no effort levels uses it.
function shell(title, body) {
  return h("section", { class: "cd" },
    h("div", { class: "cd-hd" },
      h("div", { class: "cd-t" },
        h("span", { class: "cd-ic" }, icon("sliders")),
        h("div", null, h("h3", { class: "cd-h" }, title)))),
    h("div", { class: "cd-bd" }, body));
}

// A model with no effort levels has nothing to pick. The card says so, and shows what runs.
function noSupportCard(T) {
  const hasRuns = T.runs_as !== null && T.runs_as !== undefined;
  return shell(t("ed_card"), h("div", { class: "p2-field" },
    hasRuns ? h("div", { class: "p2-head" }, h("span", { class: "p2-big" }, text(T.runs_as))) : null,
    lockLine(t("ed_levels_no_support"))));
}

// What the review and its foot need from the flow, read when they are drawn. lead is a list of nodes that go first in
// the rail. The presses go back through save and cancel.
function reviewEnv(lead = []) {
  return {
    busy: S.busy, failed: S.failed, failedDir: S.failedDir, failedLeft: S.failedLeft, damaged: damagedFor, save: doSave, cancel, lead,
    model: modelName(),
  };
}

// The display name of the model the targets answer is for, by the page's own model lookup (valueString), else null.
function modelName() {
  const T = targetsData();
  if (!T || !T.model) return null;
  const res = live.ctx.data && live.ctx.data.settings;
  return valueString({ key: "model", value: T.model }, res && res.data ? res.data : null, true);
}

// The word under a level. Off-mode levels are offered, so they carry none.
function levelNote(level) {
  if (level.result === "now") return t("ed_seg_now");
  if (level.result === "stopped") {
    if (capsOf(Array.isArray(level.limits) ? level.limits : []).length > 0) return t("ed_seg_over_cap");
    if (level.saveable !== true) return t("ed_seg_stopped");
  }
  return null;
}

// The level radios. The state comes from edit_pick.js, so the checked radio is the chosen level and the running
// level is off once a level is chosen. A level held by a cap is off and says over cap (board a-norm), so it can't be pressed and the arrow keys skip it.
function picker(T, mode) {
  const levels = levelsOf(T);
  const running = runningOf(T);
  // A line chosen for removal is a change in progress, so every radio is off and the running level stays checked.
  const state = pickerState(levels, running, S.level, mode, { busy: S.busy || S.remove !== null, projectLock: T.project_lock, saveable: T.saveable });
  const group = h("div", {
    class: "segs p2-segs s4-segs", role: "radiogroup", "aria-label": t("ed_level_group_sr"),
    "aria-describedby": T.levels_state === "model_unknown" ? NOTE_ID : null,
  });
  for (const level of levels) {
    const name = level.level;
    const off = state.disabled.includes(name);
    const chosen = S.level === name && state.checked === name;
    const now = level.result === "now" || name === running;
    const note = levelNote(level);
    group.appendChild(h("label", { class: ["seg", "p2-seg", now && "s6-now", chosen && "s6-on", off && !now && !chosen && "is-off"] },
      h("input", {
        class: "sr", type: "radio", name: "p2-level", value: name, checked: state.checked === name, disabled: off,
        "data-edit-focus": "radio:" + name, on: { change: () => pick(name) },
      }),
      h("span", { class: "p2-sv" }, text(name)),
      h("span", { class: "p2-sn" }, note || NBSP)));
  }
  return group;
}

// The first cap limit across the levels, as one line, with the lock line that says why this screen can't change it.
function capNote(T) {
  for (const level of levelsOf(T)) {
    for (const limit of Array.isArray(level.limits) ? level.limits : []) {
      if (!limit || limit.kind !== "cap") continue;
      const line = limitLine(limit, modelName());
      if (!line) continue;
      const why = lockText(limit.lock_reason);
      return [h("p", { class: "s4-note" }, line), why ? h("p", { class: "s4-note" }, why) : null];
    }
  }
  return null;
}

// ---------------------------------------------------------------- the rows

// One literal t() call per layer, so the string checks can see every key.
function placeOf(layer) {
  switch (layer) {
    case "local": return t("place_local");
    case "project": return t("place_project");
    case "user": return t("place_user");
    default: return text(layer);
  }
}

// The small line under a file row's name. A locked row with no line shows its file name alone.
function fileLine(file) {
  const shown = file.file_display ? shortFile(file.layer, file.file_display) : "";
  if (file.state === "absent") return t("where_no_file", { file: shown });
  if (file.state === "no_line") return t("where_no_line", { file: shown });
  if (!shown) return null;
  if (file.line !== null && file.line !== undefined) return t("file_line", { path: shown, line: file.line });
  return shown;
}

// What the file would do with the level: change its line, add a line, or create the file. One literal t() call for
// each op, so the string checks can see every key.
function doesWord(lf) {
  switch (lf.op) {
    case "insert": return t("row_adds");
    case "create": return t("row_creates");
    default: return t("row_edits", { n: text(lf.line) });
  }
}

// The third cell of a live row: the lock, the check, or the word for what the file would do. A resting row has none.
function thirdCell(lf, picked) {
  if (!lf) return null;
  if (lf.lock_reason) {
    const line = rowLockText(lf.lock_reason);
    return line ? [lockIcon(), h("span", null, line)] : null;
  }
  if (picked) return [checkIcon(), h("span", null, doesWord(lf))];
  if (lf.effect === "unknown") return h("span", null, t("ed_unknown_row"));
  if (lf.effect === "wont_apply") return h("span", null, t("row_wont"));
  if (lf.pickable === true) return h("span", null, doesWord(lf));
  return null;
}

// The Remove line link of a row at rest. Its focus key names the layer, so a draw from new data keeps focus on it.
function removeLink(file) {
  return h("button", {
    type: "button",
    class: "s4-link",
    "aria-label": t("row_remove_sr", { line: text(file.line), file: basename(file.file_display) }),
    "data-edit-focus": "remove:" + file.layer,
    on: { click: () => startRemove(file) },
  }, t("row_remove"));
}

// True when a row at rest offers Remove line: edits are on, the project takes a save, nothing else is chosen, the row
// has a line with a target, and the server doesn't lock that removal (a repeated key still opens, to say why not).
function canRemove(T, file) {
  if (live.ctx.edit.mode !== "ready" || T.enabled === false || T.saveable === false || T.project_lock) return false;
  if (S.level !== null || S.remove !== null || !file.target) return false;
  const entry = targetById(T, file.target);
  const lock = entry && entry.remove ? entry.remove.lock_reason : undefined;
  return Boolean(entry && entry.remove) && (lock === null || lock === undefined || lock === "repeated_key");
}

// One file row. lv is the chosen level's row when the rows are live, else null.
function fileRow(T, file, lv) {
  const common = { name: placeOf(file.layer), file: fileLine(file) };
  const hasValue = file.value !== null && file.value !== undefined && file.value !== "";
  const cells = hasValue
    ? { value: text(file.value), status: file.status || null }
    : { none: t("where_not_set") };
  if (!lv) {
    // In a remove's review the row whose line goes wears the picked style
    const going = S.remove !== null && S.remove.layer === file.layer;
    return rowNode({ ...common, ...cells, act: canRemove(T, file) ? removeLink(file) : null, cls: going ? "is-pick" : null });
  }
  const lf = levelFile(lv, file.layer);
  const can = Boolean(lf) && lf.pickable === true;
  const picked = can && S.row === file.layer;
  return rowNode({
    ...common, ...cells, act: thirdCell(lf, picked), pick: picked, no: !can,
    radio: {
      name: "p2-row", value: file.layer, checked: picked, disabled: !can || S.busy,
      focus: "row:" + file.layer, onChange: () => pickRow(file.layer),
    },
  });
}

const settingsPayload = () => {
  const res = live.ctx.data && live.ctx.data.settings;
  return res && res.ok && res.data && typeof res.data === "object" ? res.data : null;
};

// The entries of the main session's effort row, top wins. Empty when the payload has no such row.
function mainEntries(payload) {
  if (!payload || !Array.isArray(payload.entries)) return [];
  const row = rowFor(payload, MAIN_KEY, SETTING);
  return row && Array.isArray(row.entries) ? entriesOf(payload, row) : [];
}

// Claude Code's default, outside the box: the value and its chip when it wins, else the value as not used.
function defaultRow(entries, payload) {
  const def = entries.find((e) => e.layer === "default");
  if (!def) return [];
  const value = valueText(def, payload, true);
  if (value === null) return [rowNode({ name: t("place_default"), none: t("band_not_known"), cls: "s6-def" })];
  if (entries[0] === def) return [rowNode({ name: t("place_default"), value, status: def.status, cls: "s6-def" })];
  return [rowNode({ name: t("place_default"), none: t("where_not_used", { value: valueString(def, payload, true) }), cls: "s6-def" })];
}

// The rows below the picker. Live, when a level is chosen and can be saved: the files of that level, labels around
// a radio, same columns as at rest. Otherwise plain rows from the top-level files.
function rows(T, lv) {
  const payload = settingsPayload();
  const entries = mainEntries(payload);
  const others = entries
    .filter((e) => !FILE_LAYERS.includes(e.layer) && e.layer !== "default")
    .map((e) => entryRow(e, payload));
  const files = filesOf(T).map((file) => fileRow(T, file, lv));
  const tail = defaultRow(entries, payload);
  return whereList(lv ? t("where_live") : t("where_rest"), others.concat(files), tail, true, Boolean(lv));
}

// ---------------------------------------------------------------- the body

// Nothing is saved here because the shell sets the value: the lock line sits over the picker, as the board a-shell
// draws it. There is no change in progress, and the rail is the plain one.
function shellLock(T) {
  if (situation().kase !== "nothing_project" || firstLockReason(T) !== "env_shell") return null;
  return h("p", { class: "s4-lock" }, lockIcon(), h("span", null, lockText("env_shell")));
}

function bodyFrame(T, mode) {
  const chosen = S.level !== null && mode === "ready" ? levelRow(T, S.level) : null;
  const lv = chosen && chosen.saveable === true && T.saveable !== false && !T.project_lock ? chosen : null;
  return [
    shellLock(T),
    h("div", { class: "s4-run" }, h("p", { class: "s4-lab" }, t("run_at")), picker(T, mode)),
    T.levels_state === "model_unknown" ? h("p", { class: "s4-note", id: NOTE_ID }, t("ed_levels_model_unknown")) : null,
    capNote(T),
    rows(T, lv),
  ];
}

function bodyNodes() {
  if (live.selected !== SETTING) return [];
  const T = targetsData();
  if (T === null) return [];
  if (T === false) return [hint(t("ed_err_network"))];
  if (T.levels_state === "no_effort_support") return [noSupportCard(T)];
  return bodyFrame(T, live.ctx.edit.mode);
}

// ---------------------------------------------------------------- the rail

function frameNodes(frame) {
  const done = () => { resetCard(); S.want = "radio"; redraw("card"); };
  const dismiss = (focus) => button(t("ed_dismiss"), { focus, onClick: focus === "dismiss-ledger" ? dismissLedger : done });
  if (frame.type === "raced") {
    // A created file has no backup, so the body says that instead of pointing at one.
    const body = frame.path ? draw(t("ed_raced_t", { path: mark("path") }), { path: frame.path })
      : frame.op === "create" ? t("ed_raced_new_t") : null;
    return [h("div", { class: "s4-rb" }, nt("warn", t("ed_raced_h", { file: frame.file }), [body], [dismiss("dismiss-card")]))];
  }
  if (frame.type === "unverified") {
    const fsync = frame.stage === "fsync";
    const heading = fsync ? t("ed_unverified_fsync_h") : t("ed_unverified_reread_h");
    const slots = { path: mark("path") };
    const body = fsync ? t("ed_unverified_fsync_t", slots) : t("ed_unverified_reread_t", slots);
    // A created file has no backup, so the body says that instead of pointing at one.
    const newBody = fsync ? t("ed_unverified_fsync_new_t") : t("ed_unverified_new_t");
    const note = frame.path ? draw(body, { path: frame.path }) : frame.op === "create" ? newBody : null;
    return [h("div", { class: "s4-rb" }, nt("err", heading, [note], [dismiss("dismiss-card")]))];
  }
  return [h("div", { class: "s4-rb" }, nt("err", t("ed_ledger_h", { file: frame.file }),
    [frame.path ? draw(t("ed_ledger_t", { path: mark("path") }), { path: frame.path }) : null], [dismiss("dismiss-ledger")]))];
}

function dismissButton() {
  return button(t("ed_dismiss"), {
    focus: "dismiss-card",
    onClick: () => {
      S.notice = null;
      redraw("card");
    },
  });
}

function noticeNode() {
  if (!S.notice) return null;
  return nt(S.notice.kind, S.notice.heading, S.notice.paras || [], S.notice.dismiss ? [dismissButton()] : []);
}

// The lock reason of the first limit found across the levels that has a lock text, or null.
function firstLockReason(T) {
  for (const level of levelsOf(T)) {
    for (const limit of Array.isArray(level.limits) ? level.limits : []) {
      if (limit && lockText(limit.lock_reason)) return limit.lock_reason;
    }
  }
  return null;
}

// The headline of the change in the rail: what runs now and the level picked. lead is the notice over it, if any.
// Pick a file adds the note that no file is picked yet. While a preview is on its way, or after it failed, the frame
// is the same with no note. Save and Cancel sit in the foot.
function pickFileRail(T, lead, withNote) {
  const was = T.runs_as;
  const hasWas = was !== null && was !== undefined;
  return h("div", { class: "s4-rb" },
    lead,
    h("h2", { class: "s4-rh" }, t("review_h")),
    h("div", { class: "s4-chg" },
      hasWas ? h("span", { class: "s4-was" }, text(was)) : null,
      hasWas ? h("span", { "aria-hidden": "true" }, "→") : null,
      hasWas ? h("span", { class: "sr" }, t("ed_to")) : null,
      h("span", { class: "s4-to" }, text(S.level))),
    h("p", { class: "s4-runs" }, t("ed_runs")),
    withNote ? h("p", { class: "s4-note" }, t("ed_pick_file")) : null);
}

// Nothing can be saved at this level. The winner's own line says what holds it, when there is one.
function nothingLevelRail(lv) {
  const limits = Array.isArray(lv && lv.limits) ? lv.limits : [];
  const winner = limits.find((l) => l && l.kind === "winner");
  const paras = winner ? limitParas([winner], modelName()) : [];
  // When every file is locked, the first file's lock says why, under the Can't save line.
  const files = Array.isArray(lv && lv.files) ? lv.files.filter((f) => f && typeof f === "object") : [];
  if (files.length > 0 && files.every((f) => f.lock_reason !== null && f.lock_reason !== undefined)) paras.push(lockText(files[0].lock_reason));
  return h("div", { class: "s4-rb" }, nt("warn", t("ed_nosave_level", { level: S.level }), paras,
    [button(t("ed_cancel"), { focus: "cancel", onClick: cancel })]));
}

// The frame of a removal's review while its preview is on its way or failed: the heading alone. Save and Cancel sit in
// the foot, and a failed preview leaves its notice over this.
function removeFrame(lead) {
  return h("div", { class: "s4-rb" }, lead, h("h2", { class: "s4-rh" }, t("review_h")));
}

// The line can't be removed here, because the setting is in the file more than once. Cancel is the way back.
function removeBlockedRail() {
  return h("div", { class: "s4-rb" }, nt("warn", t("ed_remove_blocked_h", { line: text(S.remove.line) }), [t("ed_remove_blocked_t")],
    [button(t("ed_cancel"), { focus: "cancel", onClick: cancel })]));
}

// What the page is showing, and the data it draws from. T is a usable ready or locked answer, or null.
function situation() {
  const mode = live.ctx.edit.mode;
  const found = targetsData();
  const T = found && typeof found === "object" ? found : null;
  if (mode === "ready" && !T) return { mode, T, kase: "rest" };
  const noLevels = T !== null && T.levels_state === "no_effort_support";
  const lv = T !== null && S.level !== null ? levelRow(T, S.level) : null;
  const kase = railCase({
    mode,
    projectLock: T ? T.project_lock : null,
    saveable: T === null || noLevels ? true : T.saveable,
    level: lv ? S.level : null,
    row: S.row,
    levelRow: lv,
    remove: S.remove,
  });
  return { mode, T, lv, kase };
}

// The cases that hold a chosen level. On a cell that isn't Effort the rail and the foot keep them too, because
// picking another cell never drops the change.
const CHANGING = ["review", "pick_file", "stop", "nothing_level", "remove", "remove_blocked"];
const changing = ({ mode, T, kase }) => mode === "ready" && T !== null && (S.level !== null || S.remove !== null)
  && CHANGING.includes(kase);
const holding = () => changing(situation());

function railNodes() {
  const sit = situation();
  const { mode, T, lv, kase } = sit;
  if (live.selected !== SETTING && !changing(sit)) return [live.restRail(null)];
  if (mode === "ready" && S.frame && kase !== "project_lock") return [noticeNode(), frameNodes(S.frame)];
  const lead = [noticeNode()];
  switch (kase) {
    case "project_lock": return [live.restRail([lockText(T.project_lock)].filter(Boolean))];
    case "off": return [live.restRail([tn("ed_off")])];
    case "locked": return [S.token && S.token.where === "card" ? tokenNt() : null, live.restRail([tn("ed_locked")])];
    case "nothing_project":
      if (firstLockReason(T) === "env_shell") return [noticeNode(), live.restRail(null)];
      return [noticeNode(), live.restRail([t("ed_nosave_project"), lockText(firstLockReason(T))].filter(Boolean))];
    case "review": return [S.pv ? review(T, S.pv, reviewEnv(lead)) : pickFileRail(T, lead, false)];
    case "remove": return [S.pv ? review(T, S.pv, reviewEnv(lead)) : removeFrame(lead)];
    case "remove_blocked": return [noticeNode(), removeBlockedRail()];
    case "pick_file": return [pickFileRail(T, lead, true)];
    case "stop": return [noticeNode(), stopPanel(lv, S.level, { cancel, model: modelName() })];
    case "nothing_level": return [noticeNode(), nothingLevelRail(lv)];
    default: return [noticeNode(), live.restRail(null)];
  }
}

// ---------------------------------------------------------------- the foot

// Save and Cancel, side by side, whatever cell is open. A review draws its own foot. A preview on its way, a failed
// one and Pick a file keep Save off, as the board a-lock draws it, with Cancel the way back. The stop rows carry
// their own Cancel in the rail, and a result frame its own Dismiss.
function changeFootNodes() {
  const sit = situation();
  if (!changing(sit) || S.frame) return [];
  if (sit.kase === "pick_file" || ((sit.kase === "review" || sit.kase === "remove") && !S.pv)) return waitingFoot({ busy: S.busy, cancel });
  if (sit.kase !== "review" && sit.kase !== "remove") return [];
  const env = reviewEnv();
  const facts = reviewFacts(sit.T, S.pv, env);
  return reviewFoot(facts.pv, facts.fileName, facts.ledger, env);
}

// What the strip builders need from the flow, read when the strip is drawn.
function stripNodes() {
  // A result stays on every cell, because a Save can be pressed on any of them. The last change at rest is Effort's.
  if (live.selected !== SETTING && !S.strip) return [];
  const mode = live.ctx.edit.mode;
  return footNodes({
    mode,
    token: S.token,
    strip: S.strip,
    changing: holding(), // the foot holds Save and Cancel then, and the last change waits
    stripBusy: S.stripBusy,
    history: mode === "ready" && live.selected === SETTING ? historyData() : null,
    doUndo,
    dismissStrip,
  });
}

// ---------------------------------------------------------------- drawing and focus

function fill(slot, nodes) {
  if (!slot) return;
  clear(slot);
  slot.appendChild(frag(nodes));
}

const slotsOf = () => [live.body, live.rail, live.pickSlot, live.stripSlot].filter(Boolean);
const keyOf = (n) => String(n.getAttribute("data-edit-focus"));
// A disabled radio or button can't take focus, as in a browser.
const isOff = (n) => n.hasAttribute("disabled");

// The control that takes focus when the one that held it is gone or off: the checked row, the first enabled row,
// then the checked level radio, then the first enabled one. Searches the slots given.
function fallbackFocus(slots, rowsFirst) {
  const find = (test) => slots.flatMap((slot) => walk(slot, test))[0] || null;
  const on = (prefix) => (n) => keyOf(n).startsWith(prefix) && !isOff(n);
  const checked = (prefix) => (n) => on(prefix)(n) && n.hasAttribute("checked");
  const rowTarget = rowsFirst ? find(checked("row:")) || find(on("row:")) : null;
  return rowTarget || find(checked("radio:")) || find(on("radio:"));
}

// Gives focus to the control a result asked for. "radio" is the checked level radio. It runs only once the nodes
// are in the page, because a detached node takes no focus.
function applyWant() {
  if (!S.want || !live) return false;
  // The level radios belong to the Effort cell. On another cell there is none to focus, and the wish does not wait
  // for the day Effort comes back.
  if (S.want === "radio" && live.selected !== SETTING) {
    S.want = null;
    return false;
  }
  const slots = slotsOf();
  let target;
  if (S.want === "radio") target = fallbackFocus(slots, false);
  else {
    // A remove link keeps its own key, "remove:<layer>". Every other wish names a button.
    const key = S.want.startsWith("remove:") ? S.want : "btn:" + S.want;
    target = slots.flatMap((slot) => walk(slot, (n) => keyOf(n) === key && !isOff(n)))[0] || null;
  }
  if (!target) return false;
  S.want = null;
  target.focus();
  return true;
}

export function focusKey() {
  const el = typeof document === "undefined" ? null : document.activeElement;
  const key = el && typeof el.getAttribute === "function" ? el.getAttribute("data-edit-focus") : null;
  return key || null;
}

// Puts focus back on the control with this key, inside root. A row that went grey, or a level radio that went off,
// hands focus to the next control of its group, and a key that isn't there does nothing.
export function restoreFocus(root, key) {
  if (!key || !root) return;
  let found = walk(root, (n) => n.getAttribute("data-edit-focus") === key && !isOff(n))[0] || null;
  if (!found && key.startsWith("row:")) found = fallbackFocus([root], true);
  else if (!found && key.startsWith("radio:")) found = fallbackFocus([root], false);
  if (found && found !== document.activeElement) found.focus();
}

// The Set of setting keys that have a change waiting on Save: Effort, while the open project is Not saved.
const notSavedSet = () => new Set(isNotSaved() ? [SETTING] : []);

// A choice made with no page render changes what the band and the project picker say. The band is told when its
// Set changes, and app.js is asked to draw the picker again when the list of projects does.
function syncNotSaved() {
  const set = notSavedSet();
  const band = Array.from(set).join(",");
  if (band !== live.bandSig) {
    live.bandSig = band;
    if (typeof live.onNotSaved === "function") live.onNotSaved(set);
  }
  const projects = notSavedProjects().join(",");
  if (projects !== live.shellSig) {
    live.shellSig = projects;
    if (typeof live.ctx.edit.syncShell === "function") live.ctx.edit.syncShell();
  }
}

function redraw(which) {
  if (!live) return;
  const key = focusKey();
  if (which !== "strip") {
    fill(live.body, bodyNodes());
    fill(live.rail, railNodes());
    fill(live.pickSlot, changeFootNodes());
  }
  // A chosen level hides the last change, so the slot draws when that flips. Otherwise a "card" redraw leaves its node.
  const held = holding();
  if (which !== "card" || live.changing !== held) fill(live.stripSlot, stripNodes());
  live.changing = held;
  syncNotSaved();
  if (applyWant()) return;
  for (const slot of slotsOf()) restoreFocus(slot, key);
}

onRedraw(redraw);

// ---------------------------------------------------------------- entry point

// Called by pages/settings.js once per render with a payload, whichever cell is open. restRail(notes) draws the
// rail at rest for the open cell: notes is a list of lines for under "Why this value", or null. selected is the
// open cell, and the Effort frame, the notes and the results belong to the effortLevel cell alone, so a read-only cell
// never shows the editing-is-off line. A change in progress is the exception: its review and its Save and Cancel
// stay on every cell. onNotSaved(set) redraws the band alone when a choice changes the Set of Not saved settings.
// It returns the three slots, notSaved (that Set, for the band the page draws) and done(), which the page calls once
// its nodes are in the document. Mode null returns nothing to place.
export function begin(ctx, { restRail, selected, onNotSaved }) {
  const shellBefore = live ? live.shellSig : null; // the project list the picker was last drawn with
  const mode = ctx.edit ? ctx.edit.mode : null;
  syncFlow(ctx.project ? ctx.project.key : null, mode);
  if (mode !== "off" && mode !== "locked" && mode !== "ready") {
    setLive(null);
    return { body: null, rail: null, foot: null, notSaved: new Set(), done: () => {} };
  }
  const pickSlot = h("div", { class: "s4-slot", "data-edit": "pick" });
  const stripSlot = h("div", { class: "s4-slot", "data-edit": "strip" });
  const mine = {
    ctx,
    selected,
    restRail: restRail || (() => h("div", { class: "s4-rb" })),
    onNotSaved,
    bandSig: "",
    shellSig: "",
    body: h("div", { class: "s4-slot", "data-edit": "body" }),
    rail: h("div", { class: "s4-slot", "data-edit": "rail" }),
    pickSlot,
    stripSlot,
    foot: h("div", { class: "s4-slot", "data-edit": "foot" }, pickSlot, stripSlot),
  };
  setLive(mine);
  // Once for each targets object the page draws: the picked row stays valid, and a preview matches it.
  const T = targetsData();
  if (T && T !== S.seen && !S.busy) {
    const first = S.seen !== null; // a flow that just loaded has no seen yet, and its preview is asked for once
    S.seen = T;
    settle(first);
  }
  const notSaved = notSavedSet();
  mine.bandSig = Array.from(notSaved).join(",");
  mine.shellSig = notSavedProjects().join(",");
  // settle() above can clear a kept flow, and the picker still says Not saved for it.
  if (shellBefore !== null && shellBefore !== mine.shellSig && typeof ctx.edit.syncShell === "function") ctx.edit.syncShell();
  fill(mine.body, bodyNodes());
  fill(mine.rail, railNodes());
  fill(pickSlot, changeFootNodes());
  mine.changing = holding();
  fill(stripSlot, stripNodes());
  return {
    body: mine.body,
    rail: mine.rail,
    foot: mine.foot,
    notSaved,
    // Called when the nodes are in the page: a pending focus first, else the control that held focus.
    done: (root, key) => {
      if (live === mine && !applyWant()) restoreFocus(root, key);
    },
  };
}
