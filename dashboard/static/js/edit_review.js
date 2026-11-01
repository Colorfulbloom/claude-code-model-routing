// The pure builders of the Change effort review (round 6 design, board a-norm): limits and warnings, the stop
// panel, the review that sits in the rail, the diff figure, and the foot with Save and Cancel. Nothing here holds
// state or imports it. What the flow knows comes in as arguments, and the presses go out through the handlers the
// caller passes ({ save, cancel }).
//
// Rules this file keeps, the same as edit_card.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.

import { h } from "./h.js";
import { t } from "./format.js";
import { chip } from "./components.js";
import { MAIN_KEY } from "./router.js";
import { editRef } from "./edit_ref.js";
import { layerText, valueString, valueText } from "./pages/settings.js";
import { placeName, shortFile } from "./pages/where.js";
import { basename, button, draw, isString, levelRow, lockText, mark, nt, text } from "./edit_ui.js";

const SETTING = "effortLevel";

// ---------------------------------------------------------------- limits, the stop panel and the warning

// Who sets a cap, from the layer of its file. One literal t() call per key, so the string checks can see them.
function capWho(layer) {
  switch (layer) {
    case "project": case "local": return t("ed_cap_who_project");
    case "user": return t("ed_cap_who_user");
    case "managed": return t("ed_cap_who_managed");
    default: return t("ed_cap_who_other");
  }
}

// The line that names a cap or a winner, with its file in a .pa. A model limit has no line of its own. model is the
// display name of the model the cap is for, or null when none is set, and a cap then reads as an effort cap.
export function limitLine(limit, model = null) {
  if (!isString(limit.file_display)) return null;
  const hasLine = limit.line !== null && limit.line !== undefined;
  if (limit.kind === "cap") {
    const slots = { who: capWho(limit.layer), what: model || t("ed_cap_what_effort"), value: text(limit.value), file: mark("file"), line: text(limit.line) };
    const shown = { file: shortFile(limit.layer, limit.file_display) };
    return draw(hasLine ? t("ed_limit_cap", slots) : t("ed_limit_cap_noline", slots), shown);
  }
  const slots = { value: text(limit.value), file: mark("file"), line: text(limit.line) };
  const paths = { file: limit.file_display };
  if (limit.kind === "winner") return draw(hasLine ? t("ed_limit_winner", slots) : t("ed_limit_winner_noline", slots), paths);
  return null;
}

// Each limit's line, then why it can't be changed here. cap_later is left out, because the panel's own text says it.
export function limitParas(limits, model = null) {
  const out = [];
  for (const limit of limits) {
    out.push(limitLine(limit, model));
    if (limit.lock_reason !== "cap_later") out.push(lockText(limit.lock_reason));
  }
  return out.filter(Boolean);
}

export const capsOf = (limits) => limits.filter((l) => l.kind === "cap");
export const allCapLater = (caps) => caps.length > 0 && caps.every((l) => l.lock_reason === "cap_later");

// A level a cap holds is off in the picker (edit_pick.js overCap), so this panel is for the model, the winner and
// the unknown model.
export function stopPanel(level, value, { cancel, model = null }) {
  const limits = Array.isArray(level && level.limits) ? level.limits : [];
  const paras = [];
  if (limits.some((l) => l.kind === "model")) paras.push(t("ed_stop_model_t", { level: value, runs_as: text(level.runs_as) }));
  if (limits.some((l) => l.kind === "winner")) paras.push(t("ed_stop_winner_t", { level: value }));
  const unknown = limits.some((l) => l.kind === "model_unknown");
  if (unknown) paras.push(t("ed_stop_unknown_t", { level: value }));
  const heading = unknown ? t("ed_stop_unknown_h", { level: value }) : t("ed_stop_h", { level: value });
  return h("div", { class: "s4-rb" }, nt("warn", heading, paras.concat(limitParas(limits, model)),
    [button(t("ed_cancel"), { focus: "cancel", onClick: cancel })]));
}

// One literal t() call per status, so the string checks can see every key.
export function winnerWarning(status) {
  switch (status) {
    case "overridden": return t("ed_warn_overridden_t");
    case "ignored": return t("ed_warn_ignored_t");
    case "invalid": return t("ed_warn_invalid_t");
    case "unknown": return t("ed_warn_unknown_t");
    default: return null;
  }
}

export function warningParas(warning, model = null) {
  const limits = Array.isArray(warning.limits) ? warning.limits : [];
  const caps = capsOf(limits);
  const paras = [];
  if (caps.length) {
    if (warning.status === "in_effect") paras.push(warning.model_known === true ? t("ed_warn_cap_t") : t("ed_warn_nomodel_cap_t"));
    else if (allCapLater(caps)) paras.push(t("ed_warn_cap_t"));
  }
  if (limits.some((l) => l.kind === "model")) paras.push(t("ed_warn_model_t"));
  paras.push(winnerWarning(warning.status));
  return paras.filter(Boolean).concat(limitParas(limits, model));
}

// ---------------------------------------------------------------- the review

export function mainEntries(payload) {
  const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
  const row = rows.find((r) => r.agent === MAIN_KEY && r.setting === SETTING);
  const entries = row && payload.entries ? row.entries.map((i) => payload.entries[i]).filter(Boolean) : [];
  return entries;
}

// The changed middle of a pair of lines, by their common start and end. Three text parts, or null when there is no middle.
function middle(a, b) {
  const max = Math.min(a.length, b.length);
  let start = 0;
  while (start < max && a[start] === b[start]) start += 1;
  let end = 0;
  while (end < max - start && a[a.length - 1 - end] === b[b.length - 1 - end]) end += 1;
  if (start === 0 && end === 0) return null; // nothing in common, so a mark would cover the whole line
  const cut = (line) => ({ pre: line.slice(0, start), mid: line.slice(start, line.length - end), suf: line.slice(line.length - end) });
  const left = cut(a);
  const right = cut(b);
  if (left.mid === "" && right.mid === "") return null;
  return [left, right];
}

function codeParts(parts) {
  if (!parts) return null;
  return [parts.pre, parts.mid === "" ? null : h("mark", null, parts.mid), parts.suf].filter((p) => p !== "" && p !== null);
}

// Each del line is paired with the add line at the same place in the run that follows it.
function pairMarks(lines) {
  const marks = new Map();
  let i = 0;
  while (i < lines.length) {
    if (lines[i].kind !== "del") {
      i += 1;
      continue;
    }
    let dels = i;
    while (dels < lines.length && lines[dels].kind === "del") dels += 1;
    let adds = dels;
    while (adds < lines.length && lines[adds].kind === "add") adds += 1;
    for (let k = 0; k < Math.min(dels - i, adds - dels); k += 1) {
      const pair = middle(text(lines[i + k].text), text(lines[dels + k].text));
      if (pair) {
        marks.set(i + k, codeParts(pair[0]));
        marks.set(dels + k, codeParts(pair[1]));
      }
    }
    i = adds;
  }
  return marks;
}

function diffLine(line, parts) {
  const kind = line.kind;
  const cls = kind === "del" ? "p2-del" : kind === "add" ? "p2-add" : null;
  const sign = kind === "del" ? "−" : kind === "add" ? "+" : "";
  const num = kind === "del" ? line.old_line : (line.new_line !== null && line.new_line !== undefined ? line.new_line : line.old_line);
  return h("li", { class: cls },
    kind === "del" ? h("span", { class: "sr" }, t("ed_diff_del_sr") + " ") : null,
    kind === "add" ? h("span", { class: "sr" }, t("ed_diff_add_sr") + " ") : null,
    h("span", { class: "p2-n" }, text(num)),
    h("span", { class: "p2-m", "aria-hidden": "true" }, sign),
    h("code", null, parts || text(line.text)));
}

// newFile adds the New file tag to the caption, as board a-new of design-settings-6 draws it.
function diffFigure(diff, target, newFile = false) {
  const name = basename(diff.file_display);
  const layer = target ? layerText({ layer: target.layer }) : "";
  return h("figure", { class: "p2-df" },
    h("figcaption", { class: "p2-df-h" },
      layer ? h("span", { class: "ly" }, layer) : null,
      h("span", { class: "pa" }, text(diff.file_display)),
      newFile ? h("span", { class: "p2-tag" }, t("ed_diff_new_tag")) : null),
    (Array.isArray(diff.hunks) ? diff.hunks : []).map((hunk) => {
      const lines = Array.isArray(hunk.lines) ? hunk.lines : [];
      const marks = pairMarks(lines);
      return h("ol", { "aria-label": t("ed_diff_sr", { file: name }) }, lines.map((line, i) => diffLine(line, marks.get(i))));
    }));
}

const has = (value) => value !== null && value !== undefined;
const FILE_LAYERS = ["local", "project", "user"];
// The statuses a line in another file keeps after the change, so the review says so.
const STILL = ["overridden", "ignored", "invalid"];

const soleValue = (value) => h("div", { class: "s4-chg" }, h("span", { class: "s4-to" }, text(value)));

// A removal's change line. A line that changes nothing shows the one value that runs. When the value after is not
// known, the value before stands alone. With neither there is no value to show, and no empty one is drawn.
function removeLine(pv) {
  const before = has(pv.runs_before) ? pv.runs_before : null;
  const after = has(pv.runs_after) ? pv.runs_after : null;
  if (pv.no_effect === true || after === null) return before === null ? null : soleValue(before);
  if (before === null || before === after) return soleValue(after);
  return h("div", { class: "s4-chg" },
    h("span", { class: "s4-was" }, text(before)),
    h("span", { "aria-hidden": "true" }, "→"),
    h("span", { class: "sr" }, t("ed_to")),
    h("span", { class: "s4-to" }, text(after)));
}

// The change that runs: what ran before, an arrow, what runs after. A change that leaves what runs as it was, and
// a change with no known before, shows one value.
function changeLine(pv) {
  if (pv.op === "remove") return removeLine(pv);
  const before = has(pv.runs_before) ? pv.runs_before : null;
  const after = has(pv.runs_after) ? pv.runs_after : pv.new_value;
  if (before === null || before === after) return soleValue(after);
  return h("div", { class: "s4-chg" },
    h("span", { class: "s4-was" }, text(before)),
    h("span", { "aria-hidden": "true" }, "→"),
    h("span", { class: "sr" }, t("ed_to")),
    h("span", { class: "s4-to" }, text(after)));
}

// The line under the change. A warning that says nothing moves, or that the dashboard can't tell, comes first.
function runsNote(pv, level) {
  if (pv.op === "remove") {
    if (pv.no_effect === true) return t("ed_nochange");
    return has(pv.runs_after) ? t("ed_runs") : t("ed_nochange_unknown");
  }
  const warning = pv.warning;
  if (warning && warning.status === "unknown") return t("ed_nochange_unknown");
  if (warning && warning.in_effect_changes === false) return t("ed_nochange");
  if (level && level.certain === false) return t("ed_runs_uncertain", { level: text(pv.new_value) });
  return t("ed_runs");
}

// After saving: the value that wins and where it comes from. No winner, no list.
function afterList(pv) {
  const winner = mainEntries(pv.after)[0];
  if (!winner) return null;
  const value = valueText(winner, pv.after, true);
  return h("dl", { class: "s4-dl" },
    h("div", null, h("dt", null, t("review_after")),
      h("dd", null,
        value === null ? h("span", { class: "s4-none" }, t("band_not_known")) : h("span", { class: "s4-v" }, value),
        value === null ? null : h("span", { class: "s4-st" }, chip(winner.status)))),
    h("div", null, h("dt", null, t("review_comes")), h("dd", null, placeName(winner, pv.after))));
}

// One literal t() call for each form. The places of the local and project files hold a comma of their own.
function stillLine(entry, payload) {
  const slots = { value: valueString(entry, payload, true), place: placeName(entry, payload), status: t("status_" + entry.status) };
  return entry.layer === "local" || entry.layer === "project" ? t("still_status_c", slots) : t("still_status", slots);
}

// One line for each other file that still holds a value this change doesn't make win.
function stillNotes(pv, target) {
  return mainEntries(pv.after)
    .filter((e) => FILE_LAYERS.includes(e.layer) && STILL.includes(e.status) && !(target && editRef(e) === target.ref))
    .map((e) => h("p", { class: "s4-note" }, stillLine(e, pv.after)));
}

// One side of a change to another agent: the value and its status, and what it runs as when that differs.
function side(part) {
  if (!part) return h("span", { class: "s4-none" }, t("band_not_known"));
  const runs = part.runs_as !== part.value && has(part.runs_as) && part.runs_as !== "" ? part.runs_as : null;
  return h("span", { class: "s4-lvv" },
    text(part.value),
    part.status ? h("span", { class: "s4-st" }, chip(part.status)) : null,
    runs === null ? null : h("span", { class: "s4-none" }, t("runs_as_cell", { becomes: runs })));
}

// Every row a preview moved besides the main session's: a safety fact, so it stays.
function alsoChanges(pv) {
  const also = (Array.isArray(pv.changes) ? pv.changes : []).filter((c) => c.agent !== MAIN_KEY);
  if (!also.length) return null;
  return [
    h("p", { class: "s4-sub" }, t("ed_also")),
    h("dl", { class: "s4-dl" }, also.map((c) => h("div", null,
      h("dt", null, t("ed_also_agent", { agent: text(c.agent) })),
      h("dd", null, side(c.before), h("span", { "aria-hidden": "true" }, "→"), h("span", { class: "sr" }, t("ed_to")), side(c.after))))),
  ];
}

// The heading of the warning over a preview.
function warningHeading(w) {
  if (w.status === "unknown") return t("ed_warn_unknown_h");
  return w.in_effect_changes === true ? t("ed_warn_part_h") : t("ed_warn_h");
}

// What the review and its foot both need, read from the preview and the targets answer. The preview stands in for the
// target, because an add has no entry in the targets list.
export function reviewFacts(T, state, env) {
  const pv = state.data;
  const target = { layer: pv.layer, ref: pv.ref, line: pv.line, shared: pv.shared };
  const file = pv.diff ? pv.diff.file_display : "";
  return {
    pv,
    target,
    fileName: basename(file),
    level: levelRow(T, state.value),
    ledger: Boolean(env.damaged(file, target.layer)) || pv.ledger_damaged === true,
  };
}

// One literal t() call for each op, so the string checks can see every key.
function subLine(pv, fileName) {
  const slots = { line: text(pv.line), file: fileName };
  switch (pv.op) {
    case "insert": return t("ed_card_add", slots);
    case "create": return t("ed_card_new", slots);
    case "remove": return t("ed_card_remove", slots);
    default: return t("ed_card_line", slots);
  }
}

// The notes under the diff about the file itself: it is new (and its folder with it), or the line is its last.
function fileNotes(pv, fileName, failedLeft) {
  // A failed save that left the .claude folder behind makes the folder note untrue, so it goes.
  const dirNote = failedLeft === true ? null : h("p", { class: "s4-note" }, t("ed_new_dir_note", { file: fileName }));
  return [
    pv.creates_dir === true ? dirNote
      : pv.new_file === true ? h("p", { class: "s4-note" }, t("ed_new_file_note", { file: fileName })) : null,
    pv.last_line === true ? h("p", { class: "s4-note" }, t("ed_remove_last_note", { file: fileName })) : null,
  ];
}

// The folder a file lives in, from its display path.
const parentOf = (path) => {
  const parts = text(path).split(/[\\/]/);
  parts.pop();
  return parts.join("/");
};

// The notices that close a review whose write did not fail: the warning, the damaged record, a removal that changes
// nothing, and what git does with the file. A file in git is a warning, and the dashboard not knowing is a quiet line.
function closingNotes(pv, w, ledger, fileName, model) {
  const out = [];
  if (w) out.push(nt("warn", warningHeading(w), warningParas(w, model)));
  if (ledger) out.push(nt("warn", t("ed_ledger_preview_t", { file: fileName }), []));
  if (pv.op === "remove" && pv.no_effect === true) out.push(nt("warn", t("ed_remove_noeffect_h"), [t("ed_remove_noeffect_t")]));
  if (pv.op !== "remove" && pv.git_ignore === "not_ignored") out.push(nt("warn", t("ed_git_warn_h"), [t("ed_git_warn_t", { file: fileName })]));
  if (pv.git_ignore === "unknown") out.push(h("p", { class: "s4-note" }, t("ed_git_unknown", { file: fileName })));
  return out;
}

// The review in the rail: the change, what runs, the winner after saving, the exact line and the notes. env.lead is
// a list of nodes that go first (a notice over the review). The warning, the failed-write notice and the ledger
// notice close the body, just above the foot.
export function review(T, state, env) {
  const { pv, target, fileName, level, ledger } = reviewFacts(T, state, env);
  const w = pv.warning;
  const closing = [];
  if (env.failed && pv.op === "create" && !env.failedDir) {
    const folder = parentOf(pv.diff ? pv.diff.file_display : "");
    closing.push(nt("err", t("ed_fail_create_h"), [
      draw(t("ed_fail_create_t", { folder: mark("folder") }), { folder }),
      env.failedLeft ? t("ed_fail_dir_left") : null,
    ]));
  } else if (env.failed) {
    const why = env.failedDir
      ? draw(t("ed_fail_config_dir_t", { config_dir: mark("config_dir") }), { config_dir: env.failedDir })
      : t("ed_fail_t", { file: fileName });
    closing.push(nt("err", t("ed_fail_h"), [why]));
  } else if (pv.no_change !== true) {
    closing.push(...closingNotes(pv, w, ledger, fileName, env.model));
  }
  return h("div", { class: "s4-rb" },
    env.lead || [],
    h("h2", { class: "s4-rh" }, t("review_h")),
    changeLine(pv),
    h("p", { class: "s4-runs" }, runsNote(pv, level)),
    afterList(pv),
    h("p", { class: "s4-sub" }, subLine(pv, fileName)),
    pv.diff ? diffFigure(pv.diff, target, pv.new_file === true) : null,
    fileNotes(pv, fileName, env.failedLeft),
    stillNotes(pv, target),
    target.shared === true ? h("p", { class: "s4-note" }, t("ed_shared")) : null,
    level && level.certain === false ? h("p", { class: "s4-note" }, t("ed_certain_note")) : null,
    alsoChanges(pv),
    closing);
}

// The foot while no preview is on screen (one is on its way, or it failed) and while a file is yet to be picked:
// Save is off, Cancel is the way back.
export function waitingFoot({ busy = false, cancel }) {
  return [
    button(t("ed_save_plain"), { primary: true, wide: true, disabled: true, focus: "save" }),
    button(t("ed_cancel"), { wide: true, focus: "cancel", disabled: busy, onClick: cancel }),
    h("p", { class: "s4-hint" }, t("ed_nothing_yet")),
  ];
}

// Save and Cancel, side by side, in the rail's foot. Busy shows Saving with both buttons off.
export function reviewFoot(pv, fileName, ledger, env) {
  const { busy, failed, save: doSave, cancel } = env;
  // A removal that changes nothing is a warned save: Remove anyway, and not the primary button.
  const anyway = pv.op === "remove" && pv.no_effect === true;
  const save = (label) => button(busy ? t("ed_saving") : label, {
    primary: !pv.warning && !anyway, wide: true, focus: "save", disabled: busy, busy, onClick: doSave,
  });
  const cancelButton = button(t("ed_cancel"), { wide: true, focus: "cancel", disabled: busy, onClick: cancel });
  const saying = busy ? h("span", { class: "sr", role: "status" }, t("ed_saving_sr", { file: fileName })) : null;
  if (failed) return [button(t("ed_try_again"), { primary: true, wide: true, focus: "try", onClick: doSave }), cancelButton];
  if (pv.no_change === true) return [cancelButton, h("p", { class: "s4-hint" }, t("ed_no_change_note"))];
  // This file takes no save, so only Cancel is drawn.
  if (ledger) return [cancelButton];
  if (pv.warning) return [save(t("ed_save_anyway")), cancelButton, saying];
  if (anyway) return [save(t("ed_remove_anyway")), cancelButton, saying];
  return [save(saveLabel(pv, fileName)), cancelButton, h("p", { class: "s4-hint" }, t("ed_nothing_yet")), saying];
}

// The words of Save. One literal t() call for each op, so the string checks can see every key.
function saveLabel(pv, fileName) {
  if (pv.op === "create") return t("ed_save_create", { file: fileName });
  if (pv.op === "remove") return t("ed_save_remove", { line: text(pv.line), file: fileName });
  return t("ed_save_to", { file: fileName });
}
