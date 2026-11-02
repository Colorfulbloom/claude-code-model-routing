// The body of an editing cell (Effort, the effort cap, the model, the compact window), its rail and its foot on the
// Settings page (round 6 design, direction A), and the results in the foot. pages/settings.js calls
// begin(ctx, { restRail, selected, editable, onNotSaved }) once per render with a payload and places what comes back.
// The page reads ctx.edit (js/edit_session.js through app.js): the mode, the targets and the history, and
// it sends the preview, the save and the undo. The boards a-rest, a-norm, a-lock and a-shell in the phase 2
// design folder (design-settings-6) are the reference, and app.css holds every class used here (section
// "Settings page, round 6").
//
// This file holds the shell, the pickers, the rows, the rail, the foot, the drawing and the focus. The rest sits
// beside it.
// - edit_pick.js: the pure rules (which radio is checked and off, which rail case, where the picked row lands).
// - edit_flow.js: the state and the actions. It draws through the redraw() registered here.
// - edit_review.js and edit_foot.js: the pure builders of the review (rail) with its Save and Cancel (foot), and of
//   the results (foot).
// - edit_setting.js and edit_words.js: what is particular to each of the four settings (the model options, the window
//   number, the words), pure.
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
//   of a cell that is not edited is its read-only frame. One Save exists in the page, never a copy for a narrow window.
// - One change at a time. A chosen level or a line chosen for removal holds the page: the picker is off, the rows
//   lose their Remove line links, and the review and its Save and Cancel take the rail and the foot. Another cell that
//   edits draws read-only while a change is held (its picker and rows are off), and the Not saved mark stays on the cell
//   the change was made on. The older backups list and the preview of an Undo anyway or a restore (edit_backup.js) hold
//   it the same way, and they take the rail and the foot on every cell, and under the project lock, because Undo stays
//   open there.
// - A level that needs a cap change first has nothing to save: its rail says so and offers Start with the cap.
// - A chosen level that can be saved, or a line to remove that nothing blocks, is Not saved. A choice made with no page render updates the Stat band
//   (onNotSaved) and the project picker (ctx.edit.syncShell) by the callbacks the page and app.js pass in.
// - The checked radio always equals the chosen level, and a row that goes grey takes no focus. A handler never
//   puts a radio back. The model pop-up and the window box draw from the chosen level in the same way.

import { h, clear, frag } from "./h.js";
import { t, tn } from "./format.js";
import { icon } from "./icons.js";
import { MAIN_KEY } from "./router.js";
import { controlsOff, pickerState, railCase } from "./edit_pick.js";
import {
  S, live, setLive, onRedraw, syncFlow, settle, targetsData, changeTargets, historyData, damagedFor, levelFile, isNotSaved,
  notSavedProjects, cancel, pick, pickRow, pickAuto, commitWindow, startWithCap, applyCarry, startRemove, doSave, doUndo,
  dismissStrip, dismissLedger, resetCard, openOlder, closeBack, startBack, confirmBack, openSetting, foreign, changeValue,
  writeSetting,
} from "./edit_flow.js";
import { backFoot, backRail, olderRail, olderRows } from "./edit_backup.js";
import {
  capsOf, limitLine, limitParas, review, reviewFacts, reviewFoot, stopPanel, twoChangesPanel, waitingFoot,
} from "./edit_review.js";
import { stripNodes as footNodes } from "./edit_foot.js";
import {
  basename, button, checkIcon, draw, filesOf, hint, levelRow, levelsOf, lockIcon, lockLine, lockText, mark, nt,
  rowLockText, runningOf, targetById, text, tokenNt, walk,
} from "./edit_ui.js";
import { CAP, COMPACT, EFFORT, MODEL, modelOptions, settingOf } from "./edit_setting.js";
import * as words from "./edit_words.js";
import { valueString, valueText } from "./pages/settings.js";
import { entriesOf, entryRow, rowFor, rowNode, shortFile, whereList } from "./pages/where.js";

export { basename };

const FILE_LAYERS = ["local", "project", "user"];
const NOTE_ID = "p2-levels-note";
const MODEL_ID = "p2-model";
const COMPACT_ID = "p2-compact";
const COMPACT_HINT_ID = "p2-compact-hint";
const COMPACT_NOTE_ID = "p2-compact-note";
const NBSP = " ";

// ---------------------------------------------------------------- builders

// The plain card of the page, with a heading that is plain text. Only a setting with no levels to pick uses it.
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
  return shell(words.cardTitle(settingOf(T)), h("div", { class: "p2-field" },
    hasRuns ? h("div", { class: "p2-head" }, h("span", { class: "p2-big" }, text(T.runs_as))) : null,
    lockLine(t("ed_levels_no_support"))));
}

// What the review and its foot need from the flow, read when they are drawn. lead is a list of nodes that go first in
// the rail. The presses go back through save, cancel and startCap.
function reviewEnv(lead = []) {
  return {
    busy: S.busy, failed: S.failed, failedDir: S.failedDir, failedLeft: S.failedLeft, damaged: damagedFor, save: doSave, cancel, lead,
    model: modelName(changeTargets()),
    level: S.level,
    startCap: () => startWithCap(S.level),
  };
}

// The display name of the model a targets answer is for, by the page's own model lookup (valueString), else null.
function modelName(T) {
  if (!T || !T.model) return null;
  const res = live.ctx.data && live.ctx.data.settings;
  return valueString({ key: "model", value: T.model }, res && res.data ? res.data : null, true);
}

// The word under a level. Off-mode levels are offered, so they carry none. The cap's max sets no cap. A level one cap
// change reaches says to raise the cap, and a level that needs the cap first says it takes two changes.
function levelNote(level, setting) {
  if (setting === CAP && level.level === "max") return t("ed_seg_no_cap");
  if (level.result === "now") return t("ed_seg_now");
  if (level.via === "cap") return t("ed_seg_raise_cap");
  if (level.cap_first === true) return t("ed_seg_two_changes");
  if (level.result === "stopped") {
    if (capsOf(Array.isArray(level.limits) ? level.limits : []).length > 0) return t("ed_seg_over_cap");
    if (level.saveable !== true) return t("ed_seg_stopped");
  }
  return null;
}

// What keeps every control of the open cell from taking a press right now, other than the mode and the project lock: a
// save on its way, a line chosen for removal, an open older backups flow, or a change held on another cell.
const heldOff = () => S.busy || S.remove !== null || S.back !== null || foreign();

// The level radios. The state comes from edit_pick.js, so the checked radio is the chosen level and the running
// level is off once a level is chosen. A level held by a cap is off and says over cap (board a-norm), so it can't be pressed and the arrow keys skip it.
function picker(T, mode, setting) {
  const levels = levelsOf(T);
  const running = runningOf(T);
  const chosen = foreign() ? null : S.level;
  // A line chosen for removal is a change in progress, so every radio is off and the running level stays checked.
  const state = pickerState(levels, running, chosen, mode, { busy: heldOff(), projectLock: T.project_lock, saveable: T.saveable });
  const group = h("div", {
    class: "segs p2-segs s4-segs", role: "radiogroup", "aria-label": words.groupLabel(setting),
    "aria-describedby": T.levels_state === "model_unknown" ? NOTE_ID : null,
  });
  for (const level of levels) {
    const name = level.level;
    const off = state.disabled.includes(name);
    const picked = chosen === name && state.checked === name;
    const now = level.result === "now" || name === running;
    const note = levelNote(level, setting);
    group.appendChild(h("label", { class: ["seg", "p2-seg", now && "s6-now", picked && "s6-on", off && !now && !picked && "is-off"] },
      h("input", {
        class: "sr", type: "radio", name: "p2-level", value: name, checked: state.checked === name, disabled: off,
        "data-edit-focus": "radio:" + name, on: { change: () => pick(name) },
      }),
      h("span", { class: "p2-sv" }, text(name)),
      h("span", { class: "p2-sn" }, note || NBSP)));
  }
  return group;
}

const settingsPayload = () => {
  const res = live.ctx.data && live.ctx.data.settings;
  return res && res.ok && res.data && typeof res.data === "object" ? res.data : null;
};

// The pop-up of the models, labelled. Each option is a model's display name, or for an alias the alias with the model it
// means today. The running option says now, a blocked one says it is not allowed and is grey. The pick is the option
// chosen, and a press on the running model does nothing (it is off once another is chosen).
function modelPicker(T, mode) {
  const payload = settingsPayload();
  const off = controlsOff(mode, { busy: heldOff(), projectLock: T.project_lock, saveable: T.saveable });
  const options = modelOptions(levelsOf(T), payload && payload.models ? payload.models : null,
    { running: runningOf(T), chosen: foreign() ? null : S.level });
  const nodes = [];
  if (!options.some((o) => o.selected)) {
    // No option is the model that runs (none is set, or the dashboard does not list it), so the pop-up names what does.
    const runs = T.runs_as === null || T.runs_as === undefined ? "" : valueString({ key: "model", value: T.runs_as }, payload, true);
    nodes.push(h("option", { value: "", selected: true, disabled: true }, runs || t("where_not_set")));
  }
  for (const o of options) {
    const base = o.alias ? t("ed_model_opt_alias", { alias: o.value, name: o.name }) : o.name;
    const marks = [o.now ? t("ed_model_opt_now") : null, o.blocked ? t("ed_model_opt_blocked") : null].filter(Boolean);
    nodes.push(h("option", { value: o.value, selected: o.selected, disabled: o.disabled },
      marks.length ? base + " (" + marks.join(", ") + ")" : base));
  }
  const select = h("select", {
    id: MODEL_ID, class: "s6-sel", disabled: off, "data-edit-focus": "radio:model",
    on: { change: (ev) => pick(ev && ev.target ? ev.target.value : "") },
  }, nodes);
  return h("div", { class: "s4-run" }, h("label", { class: "s4-lab", for: MODEL_ID }, t("ed_model_label")), select);
}

// The number box and Auto. The box holds what runs now (a number), the number chosen, or what was typed that did not
// count. It commits on change (Enter or blur), never on a keystroke. A word under it says what it takes, and a second
// says why a press picked nothing.
function compactBox(T, mode) {
  const off = controlsOff(mode, { busy: heldOff(), projectLock: T.project_lock, saveable: T.saveable });
  const own = !foreign();
  const field = own && S.field ? S.field : null;
  const bad = field !== null && field.note === "bad";
  const noModel = field !== null && field.note === "nomodel";
  let value = "";
  if (field !== null && field.text !== null) value = field.text;
  else if (own && S.level === "number") value = String(S.number);
  else if (typeof T.runs_as === "number") value = String(T.runs_as);
  const autoOn = (own && S.level === "auto") || T.runs_as === "auto";
  const describedby = [COMPACT_HINT_ID, bad || noModel ? COMPACT_NOTE_ID : null].filter(Boolean).join(" ");
  const input = h("input", {
    id: COMPACT_ID, class: "s6-num", type: "text", inputmode: "numeric", autocomplete: "off", value, disabled: off,
    "aria-describedby": describedby, "aria-invalid": bad ? "true" : null, "data-edit-focus": "radio:compact",
    on: { change: (ev) => commitWindow(ev && ev.target ? ev.target.value : "") },
  });
  const auto = button(t("ed_compact_auto"), { focus: "auto", disabled: off, onClick: pickAuto });
  auto.setAttribute("aria-pressed", autoOn ? "true" : "false");
  return h("div", { class: "s4-run" },
    h("label", { class: "s4-lab", for: COMPACT_ID }, t("ed_compact_label")),
    h("div", { class: "s6-ctl" }, input, auto),
    h("p", { class: "s4-note", id: COMPACT_HINT_ID }, t("ed_compact_hint")),
    bad ? h("p", { class: "s4-note", id: COMPACT_NOTE_ID, role: "status" }, t("ed_compact_bad")) : null,
    noModel ? h("p", { class: "s4-note", id: COMPACT_NOTE_ID, role: "status" }, t("ed_compact_auto_nomodel")) : null);
}

// The first cap limit across the levels, as one line, with the lock line that says why this screen can't change it.
function capNote(T) {
  for (const level of levelsOf(T)) {
    for (const limit of Array.isArray(level.limits) ? level.limits : []) {
      if (!limit || limit.kind !== "cap") continue;
      const line = limitLine(limit, modelName(T));
      if (!line) continue;
      const why = lockText(limit.lock_reason, settingOf(T));
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

// The small line under a file row's name. A locked row with no line shows its file name alone. setting is the setting whose
// lines the rows are about.
function fileLine(file, setting) {
  const shown = file.file_display ? shortFile(file.layer, file.file_display) : "";
  if (file.state === "absent") return t("where_no_file", { file: shown });
  if (file.state === "no_line") return words.whereNoLine(setting, { file: shown });
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
  if (S.level !== null || S.remove !== null || S.back !== null || !file.target) return false;
  const entry = targetById(T, file.target);
  const lock = entry && entry.remove ? entry.remove.lock_reason : undefined;
  return Boolean(entry && entry.remove) && (lock === null || lock === undefined || lock === "repeated_key");
}

// The entries of the main session's row of a setting, top wins. Empty when the payload has no such row.
function mainEntries(payload, setting) {
  if (!payload || !Array.isArray(payload.entries)) return [];
  const row = rowFor(payload, MAIN_KEY, setting);
  return row && Array.isArray(row.entries) ? entriesOf(payload, row) : [];
}

// A file row of a level that one cap change reaches. The file rows of the targets answer are about the effort line, and the
// change goes to the cap line, so the row is drawn from the level's own file (what it would do) and the cap entries of
// the settings payload (the value the file holds now).
function capFile(file, lf, payload) {
  const op = lf ? lf.op : null;
  const entries = mainEntries(payload, CAP);
  const mine = op === "replace"
    ? entries.find((e) => e.layer === file.layer && e.line === lf.line) || entries.find((e) => e.layer === file.layer) || null
    : null;
  const state = op === "create" ? "absent" : op === "insert" ? "no_line" : op === "replace" ? "has_line" : file.state;
  return { ...file, state, line: lf && lf.line !== undefined ? lf.line : file.line, value: mine ? mine.value : null, status: mine ? mine.status : null };
}

// The value of a file row as the page words it: a model by its display name, any other value as text.
function fileValue(file, setting, payload) {
  if (setting === MODEL) return valueString({ key: MODEL, value: file.value }, payload, true);
  return text(file.value);
}

// One file row. lv is the chosen level's row when the rows are live, else null. setting is the open cell's.
function fileRow(T, file, lv, setting) {
  const payload = settingsPayload();
  const lf = lv ? levelFile(lv, file.layer) : null;
  const via = Boolean(lv) && lv.via === "cap";
  const shown = via ? capFile(file, lf, payload) : file;
  const about = via ? CAP : setting;
  const common = { name: placeOf(file.layer), file: fileLine(shown, about) };
  const hasValue = shown.value !== null && shown.value !== undefined && shown.value !== "";
  const cells = hasValue
    ? { value: fileValue(shown, about, payload), status: shown.status || null }
    : { none: t("where_not_set") };
  if (!lv) {
    // In a remove's review the row whose line goes wears the picked style
    const going = S.remove !== null && !foreign() && S.remove.layer === file.layer;
    return rowNode({ ...common, ...cells, act: canRemove(T, file) ? removeLink(file) : null, cls: going ? "is-pick" : null });
  }
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
// a radio, same columns as at rest. Otherwise plain rows from the top-level files. The line about what can beat these
// files is worded for the setting whose lines the rows are.
function rows(T, lv, setting) {
  const payload = settingsPayload();
  const via = Boolean(lv) && lv.via === "cap";
  const about = via ? CAP : setting;
  const entries = mainEntries(payload, about);
  const others = entries
    .filter((e) => !FILE_LAYERS.includes(e.layer) && e.layer !== "default")
    .map((e) => entryRow(e, payload));
  const files = filesOf(T).map((file) => fileRow(T, file, lv, setting));
  const tail = defaultRow(entries, payload);
  return whereList(lv ? t("where_live") : t("where_rest"), others.concat(files), tail, true, Boolean(lv), words.whereBeyond(about));
}

// ---------------------------------------------------------------- the body

// Nothing is saved here because the shell sets the value: the lock line sits over the picker, as the board a-shell
// draws it. There is no change in progress, and the rail is the plain one.
function shellLock(T) {
  if (situation().kase !== "nothing_project" || firstLockReason(T) !== "env_shell") return null;
  return h("p", { class: "s4-lock" }, lockIcon(), h("span", null, lockText("env_shell", settingOf(T))));
}

// The control of a setting: the level radios, the model pop-up or the window box.
function control(T, mode, setting) {
  switch (setting) {
    case MODEL: return modelPicker(T, mode);
    case COMPACT: return compactBox(T, mode);
    default: return h("div", { class: "s4-run" }, h("p", { class: "s4-lab" }, setting === CAP ? t("cap") : t("run_at")), picker(T, mode, setting));
  }
}

function bodyFrame(T, mode, setting) {
  const chosen = S.level !== null && mode === "ready" && !foreign() ? levelRow(T, S.level) : null;
  // A level that needs the cap first has no file to pick, so its rows stay plain.
  const lv = chosen && chosen.saveable === true && chosen.cap_first !== true && T.saveable !== false && !T.project_lock ? chosen : null;
  return [
    shellLock(T),
    control(T, mode, setting),
    T.levels_state === "model_unknown" ? h("p", { class: "s4-note", id: NOTE_ID }, t("ed_levels_model_unknown")) : null,
    capNote(T),
    rows(T, lv, setting),
  ];
}

function bodyNodes() {
  if (!live.editable) return [];
  const T = targetsData();
  if (T === null) return [];
  if (T === false) return [hint(t("ed_err_network"))];
  if (T.levels_state === "no_effort_support") return [noSupportCard(T)];
  return bodyFrame(T, live.ctx.edit.mode, openSetting());
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
      if (limit && lockText(limit.lock_reason, settingOf(T))) return limit.lock_reason;
    }
  }
  return null;
}

// The settings payload's models map (id to display name), or null.
function modelsMap() {
  const payload = settingsPayload();
  return payload && payload.models ? payload.models : null;
}

// The value of the chosen level as the rail words it: the typed number of the compact window, Auto, or the level.
function shownLevel() {
  return words.shown(S.setting, changeValue(), modelsMap());
}

// The headline of the change in the rail: what runs now and the level picked. lead is the notice over it, if any.
// Pick a file adds the note that no file is picked yet. While a preview is on its way, or after it failed, the frame
// is the same with no note. Save and Cancel sit in the foot. A model the dashboard can't tell the allowed models list
// for says so.
function pickFileRail(T, lead, withNote) {
  const was = T.runs_as;
  const hasWas = was !== null && was !== undefined;
  const lv = levelRow(T, S.level);
  return h("div", { class: "s4-rb" },
    lead,
    h("h2", { class: "s4-rh" }, t("review_h")),
    h("div", { class: "s4-chg" },
      hasWas ? h("span", { class: "s4-was" }, words.shown(S.setting, was, modelsMap())) : null,
      hasWas ? h("span", { "aria-hidden": "true" }, "→") : null,
      hasWas ? h("span", { class: "sr" }, t("ed_to")) : null,
      h("span", { class: "s4-to" }, shownLevel())),
    h("p", { class: "s4-runs" }, words.runsWord(writeSetting())),
    lv && lv.allow === "unclear" ? h("p", { class: "s4-note" }, t("ed_allow_unclear_t")) : null,
    withNote ? h("p", { class: "s4-note" }, t("ed_pick_file")) : null);
}

// Nothing can be saved at this level. The winner's own line says what holds it, when there is one.
function nothingLevelRail(lv, T) {
  const setting = S.setting;
  const limits = Array.isArray(lv && lv.limits) ? lv.limits : [];
  const winner = limits.find((l) => l && l.kind === "winner");
  const paras = winner ? limitParas([winner], modelName(T), setting) : [];
  // When every file is locked, the first file's lock says why, under the Can't save line.
  const files = Array.isArray(lv && lv.files) ? lv.files.filter((f) => f && typeof f === "object") : [];
  if (files.length > 0 && files.every((f) => f.lock_reason !== null && f.lock_reason !== undefined)) paras.push(lockText(files[0].lock_reason, setting));
  return h("div", { class: "s4-rb" }, nt("warn", words.nosaveLevel(setting, { level: shownLevel() }), paras,
    [button(t("ed_cancel"), { focus: "cancel", onClick: cancel })]));
}

// The value of the effort line, for the two-change panel: the winner of the effort row, else what runs.
function effortLine(T) {
  const winner = mainEntries(settingsPayload(), EFFORT)[0];
  return winner && typeof winner.value === "string" ? winner.value : T.runs_as;
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

// What the page is showing, and the data it draws from. T is a usable ready or locked answer, or null. A change made on
// another cell reads its own targets answer, so its rail and foot stay whichever cell is open.
function situation() {
  const mode = live.ctx.edit.mode;
  const found = changeTargets();
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

// The cases that hold a chosen level. On a cell that isn't the one the change was made on the rail and the foot keep
// them too, because picking another cell never drops the change.
const CHANGING = ["review", "pick_file", "two_changes", "stop", "nothing_level", "remove", "remove_blocked"];
const changing = ({ mode, T, kase }) => mode === "ready" && T !== null && (S.level !== null || S.remove !== null)
  && CHANGING.includes(kase);
// True when the older backups list, or the preview of an Undo anyway or a restore, is open.
const backOpen = () => live.ctx.edit.mode === "ready" && S.back !== null;
const holding = () => backOpen() || changing(situation());

function railNodes() {
  if (backOpen()) {
    return [S.back.view === "list" ? olderRail(olderRows(historyData()), { startBack }) : backRail(S.back, {})];
  }
  const sit = situation();
  const { mode, T, lv, kase } = sit;
  if (!live.editable && !changing(sit)) return [live.restRail(null)];
  if (mode === "ready" && S.frame && kase !== "project_lock") return [noticeNode(), frameNodes(S.frame)];
  const lead = [noticeNode()];
  switch (kase) {
    case "project_lock": return [live.restRail([lockText(T.project_lock, settingOf(T))].filter(Boolean))];
    case "off": return [live.restRail([tn("ed_off")])];
    case "locked": return [S.token && S.token.where === "card" ? tokenNt() : null, live.restRail([tn("ed_locked")])];
    case "nothing_project":
      if (firstLockReason(T) === "env_shell") return [noticeNode(), live.restRail(null)];
      return [noticeNode(), live.restRail([words.nosaveProject(settingOf(T)), lockText(firstLockReason(T), settingOf(T))].filter(Boolean))];
    case "review": return [S.pv ? review(T, S.pv, reviewEnv(lead)) : pickFileRail(T, lead, false)];
    case "remove": return [S.pv ? review(T, S.pv, reviewEnv(lead)) : removeFrame(lead)];
    case "remove_blocked": return [noticeNode(), removeBlockedRail()];
    case "pick_file": return [pickFileRail(T, lead, true)];
    case "two_changes": return [noticeNode(), twoChangesPanel(lv, S.level, { cancel, startCap: () => startWithCap(S.level), effortLine: effortLine(T) })];
    case "stop": return [noticeNode(), stopPanel(lv, S.level, { cancel, model: modelName(T), setting: S.setting })];
    case "nothing_level": return [noticeNode(), nothingLevelRail(lv, T)];
    default: return [noticeNode(), live.restRail(null)];
  }
}

// ---------------------------------------------------------------- the foot

// Save and Cancel, side by side, whatever cell is open. A review draws its own foot. A preview on its way, a failed
// one and Pick a file keep Save off, as the board a-lock draws it, with Cancel the way back. The stop rows carry
// their own Cancel in the rail, and a result frame its own Dismiss.
function changeFootNodes() {
  if (backOpen()) return backFoot(S.back, { closeBack, confirmBack, rows: olderRows(historyData()) });
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
  // A result stays on every cell, because a Save can be pressed on any of them. The last change at rest is the project's,
  // whichever of the four settings it changed, and it is worded for its own.
  if (!live.editable && !S.strip) return [];
  const mode = live.ctx.edit.mode;
  return footNodes({
    mode,
    token: S.token,
    strip: S.strip,
    changing: holding(), // the foot holds Save and Cancel then, and the last change waits
    stripBusy: S.stripBusy,
    history: mode === "ready" && live.editable ? historyData() : null,
    doUndo,
    dismissStrip,
    startBack,
    openOlder,
    closeBack,
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
// then the checked level radio, then the first enabled one. Searches the slots given. The model pop-up and the window
// box carry a radio key, so they stand in for the level radios.
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
  // The level radios belong to a cell the page edits. On another cell there is none to focus, and the wish does not wait
  // for the day an editing cell comes back.
  if (S.want === "radio" && !live.editable) {
    S.want = null;
    return false;
  }
  const slots = slotsOf();
  let target;
  if (S.want === "radio") target = fallbackFocus(slots, false);
  else {
    // A remove link keeps its own key, "remove:<layer>", a backup row "backup:<id>" and the Older backups link "older".
    // Every other wish names a button.
    const own = S.want.startsWith("remove:") || S.want.startsWith("backup:") || S.want === "older";
    const find = (key) => slots.flatMap((slot) => walk(slot, (n) => keyOf(n) === key && !isOff(n)))[0] || null;
    // Undo anyway and the Older backups link stand in for each other, because the link is not there when the row Undo
    // anyway reaches was the only one. Past both, the level radios take focus.
    if (S.want === "anyway") target = find("btn:anyway") || find("older");
    else if (S.want === "older") target = find("older") || find("btn:anyway");
    else target = find(own ? S.want : "btn:" + S.want);
    if (!target && (S.want === "anyway" || S.want === "older")) target = fallbackFocus(slots, false);
    // A row or a link that is gone will not come back with the next draw, so the wish ends here.
    if (!target && (S.want.startsWith("backup:") || S.want === "anyway" || S.want === "older")) S.want = null;
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

// The Set of setting keys that have a change waiting on Save: the cell the change was made on, while the open project is
// Not saved.
const notSavedSet = () => new Set(isNotSaved() ? [S.setting] : []);

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
// open cell and editable says the page edits it. The body, the notes and the results belong to the editing cells alone, so
// a read-only cell never shows the editing-is-off line. A change in progress is the exception: its review and its Save and
// Cancel stay on every cell. onNotSaved(set) redraws the band alone when a choice changes the Set of Not saved settings.
// It returns the three slots, notSaved (that Set, for the band the page draws) and done(), which the page calls once
// its nodes are in the document. Mode null returns nothing to place.
export function begin(ctx, { restRail, selected, editable, onNotSaved }) {
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
    editable: editable === undefined ? selected === EFFORT : Boolean(editable),
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
  // The level Start with the cap carried is chosen once the targets of the cell it named are in.
  const carried = applyCarry();
  // Once for each targets object the page draws: the picked row stays valid, and a preview matches it.
  const T = targetsData();
  if (T && T !== S.seen && !S.busy) {
    const first = S.seen !== null; // a flow that just loaded has no seen yet, and its preview is asked for once
    S.seen = T;
    if (!carried) settle(first);
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
