// The Change effort card (direction B, Pick the result) and the undo strip, on the trail of the main
// session's effortLevel. pages/trail.js calls begin(ctx) once per render and places what comes back. The card
// reads ctx.edit (js/edit_session.js through app.js): the mode, the targets and the history, and it sends the
// preview, the save and the undo. Boards 01 to 05 in the phase 2 design folder are the reference, and
// app.css holds every class used here (section "Change effort card").
//
// Rules this file keeps.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.
// - The flow state lives in this module, keyed by project. A save or an undo awaits the page's reload, so the
//   page draws again while a press is in flight. The state survives that, and the answer draws into the
//   nodes of the newest render.
// - Picking a radio or pressing a button redraws only the card's own node, or the strip's. A page render
//   rebuilds both, so focusKey() and restoreFocus() carry an edit control's focus across it.

import { h, s, clear, frag } from "./h.js";
import { t, tn, fmtTime } from "./format.js";
import { icon } from "./icons.js";
import { chip } from "./components.js";
import { MAIN_KEY } from "./router.js";
import { editRef } from "./edit_ref.js";
import { layerText, sourceText, valueString } from "./pages/settings.js";

const SETTING = "effortLevel";
const MARKS = { ok: "✓", warn: "▲", err: "✕" };
// A path slot is written into the text as a marker, then drawn as a .pa element. See draw().
const MARK = "\u0001";

// ---------------------------------------------------------------- state

function flow() {
  return {
    scope: null, // the target id a "Change this value" link fixed the picker to
    picked: null, // the level the owner picked
    view: "rest", // rest, or stop for a stopped level
    pv: null, // { target, value, data } the preview on screen
    notice: null, // a note over the picker or the review: { kind, heading, paras, dismiss }
    frame: null, // a result that replaces the review: unverified, raced or ledger
    failed: false, // a write failed and the review stays
    failedDir: null, // the config folder a failed write found missing
    busy: false, // a save is on its way
    strip: null, // a result of this page's own press, shown in the strip slot
    stripBusy: false, // an undo is on its way
    token: null, // { where } a press found no live token
    want: null, // the control that takes focus on the next draw
  };
}

const S = { ...flow(), project: null, mode: undefined, epoch: 0, seq: 0, reloads: 0 };
let live = null; // { ctx, card, strip, misses } the newest render

function resetFlow() {
  const fresh = flow();
  for (const name of Object.keys(fresh)) S[name] = fresh[name];
  S.epoch += 1;
  S.seq += 1; // an answer still on its way drops itself
}

function resetCard() {
  S.seq += 1;
  S.scope = null;
  S.picked = null;
  S.view = "rest";
  S.pv = null;
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
}

// ---------------------------------------------------------------- helpers

export function basename(path) {
  if (path === null || path === undefined) return "";
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || String(path);
}

const text = (value) => (value === null || value === undefined ? "" : String(value));
const isString = (value) => typeof value === "string" && value !== "";

// t() puts a marker where a path goes. draw() splits the text there and puts the path in a .pa element, so a
// long path wraps and a server value is never joined into markup. paths: { name: value }.
const mark = (name) => MARK + name + MARK;

function draw(line, paths = {}) {
  const out = [];
  String(line).split(new RegExp(MARK + "(\\w+)" + MARK)).forEach((piece, i) => {
    if (i % 2 === 0) {
      if (piece !== "") out.push(piece);
    } else {
      out.push(h("span", { class: "pa" }, text(paths[piece])));
    }
  });
  return out;
}

// The text of ed_lock_<reason>, or null. A null or empty reason never builds a key, and a reason with no key shows nothing.
function lockText(reason) {
  if (!isString(reason)) return null;
  const line = t("ed_lock_" + reason);
  return line === "ed_lock_" + reason ? null : line;
}

// The text for an error answer. A status of 0 or an answer with no code is the network line. A 422 with a
// blocked reason is that reason's lock line. Any other code is its ed_err_ line.
function errorText(res) {
  const status = res && typeof res.status === "number" ? res.status : 0;
  const code = res && res.data && typeof res.data === "object" && isString(res.data.error) ? res.data.error : "";
  if (!status || !code) return t("ed_err_network");
  if (status === 422) {
    const lock = lockText(code);
    if (lock) return lock;
  }
  const line = t("ed_err_" + code);
  return line === "ed_err_" + code ? t("ed_err_forbidden") : line;
}

const bodyOf = (out) => (out && out.res && out.res.data && typeof out.res.data === "object" ? out.res.data : {});
const codeOf = (out) => text(bodyOf(out).error);

function walk(node, test, out = []) {
  if (node && node.nodeType === 1 && test(node)) out.push(node);
  for (const child of Array.from((node && node.childNodes) || [])) walk(child, test, out);
  return out;
}

// ---------------------------------------------------------------- builders

function lockIcon() {
  return s("svg", {
    class: "ic sm", viewBox: "0 0 24 24", width: 20, height: 20, fill: "none", stroke: "currentColor",
    "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
  }, s("rect", { x: 5, y: 11, width: 14, height: 9, rx: 2 }), s("path", { d: "M8 11V8a4 4 0 0 1 8 0v3" }));
}

function lockLine(line) {
  return h("p", { class: "p2-lock" }, lockIcon(), h("span", null, line));
}

function hint(line, id) {
  return h("p", { class: "p2-hint", id: id || null }, line);
}

function button(label, { primary = false, focus = null, disabled = false, busy = false, onClick = null } = {}) {
  return h("button", {
    type: "button",
    class: ["btn", primary && "p2-pri"],
    disabled,
    "aria-busy": busy ? "true" : null,
    "data-edit-focus": focus ? "btn:" + focus : null,
    on: onClick ? { click: onClick } : null,
  }, label);
}

const NT_CLASS = { ok: "nt p2-nt p2-nt-ok", warn: "nt p2-nt p2-nt-warn", err: "nt p2-nt p2-nt-err" };

// A notice: the mark and a heading, then paragraphs, then buttons. An error is an alert and the rest are status.
function nt(kind, heading, paras = [], buttons = []) {
  return h("div", { class: NT_CLASS[kind], role: kind === "err" ? "alert" : "status" },
    h("div", { class: "p2-nt-h" }, h("span", { class: "p2-mk", "aria-hidden": "true" }, MARKS[kind]), heading),
    paras.filter(Boolean).map((p) => h("p", null, p)),
    buttons.length ? h("div", { class: "p2-btns" }, buttons) : null);
}

const STRIP_CLASS = {
  ok: "nt nt-banner p2-strip p2-nt-ok",
  warn: "nt nt-banner p2-strip p2-nt-warn",
  quiet: "nt nt-banner p2-strip",
};

// The strip: one line of text and its buttons. kind quiet has no mark. role is null for a strip that only sits there.
function strip(kind, line, buttons = [], role = null) {
  return h("div", { class: STRIP_CLASS[kind], role },
    h("div", { class: "p2-t" },
      kind === "quiet" ? null : h("span", { class: "p2-mk", "aria-hidden": "true" }, MARKS[kind]),
      h("span", null, line)),
    buttons);
}

// The card shell: the plain card of the page, with a heading that is plain text.
function shell(title, body, active) {
  return h("section", { class: ["cd", active && "p2-on"] },
    h("div", { class: "cd-hd" },
      h("div", { class: "cd-t" },
        h("span", { class: "cd-ic" }, icon("sliders")),
        h("div", null, h("h3", { class: "cd-h" }, title)))),
    h("div", { class: "cd-bd" }, body));
}

// ---------------------------------------------------------------- data

// The targets answer when it is usable: the object, null when it has not loaded, false when it failed.
function targetsData() {
  const res = live.ctx.edit.targets;
  if (!res) return null;
  const data = res.data;
  if (!res.ok || !data || typeof data !== "object" || !Array.isArray(data.levels) || !Array.isArray(data.targets)) return false;
  return data;
}

function historyData() {
  const res = live.ctx.edit.history;
  const data = res && res.ok ? res.data : null;
  return data && typeof data === "object" ? data : null;
}

const targetById = (T, id) => T.targets.find((x) => x.target === id) || null;
const levelRow = (T, value) => T.levels.find((l) => l.level === value) || null;

function scopedTarget(T) {
  if (!S.scope) return null;
  const found = targetById(T, S.scope);
  if (!found) S.scope = null; // the file moved, so the fixed target is gone
  return found;
}

// A file whose ledger is damaged takes no save, and the history names it.
function damagedFor(file, layer) {
  const history = historyData();
  const list = history && Array.isArray(history.damaged_ledgers) ? history.damaged_ledgers : [];
  return list.find((d) => d.file_display === file && (d.layer === layer || !layer)) || null;
}

// ---------------------------------------------------------------- limits, the stop panel and the warning

// The line that names a cap or a winner, with its file in a .pa. A model limit has no line of its own.
function limitLine(limit) {
  if (!isString(limit.file_display)) return null;
  const hasLine = limit.line !== null && limit.line !== undefined;
  const slots = { value: text(limit.value), file: mark("file"), line: text(limit.line) };
  const paths = { file: limit.file_display };
  if (limit.kind === "cap") return draw(hasLine ? t("ed_limit_cap", slots) : t("ed_limit_cap_noline", slots), paths);
  if (limit.kind === "winner") return draw(hasLine ? t("ed_limit_winner", slots) : t("ed_limit_winner_noline", slots), paths);
  return null;
}

// Each limit's line, then why it can't be changed here. cap_later is left out, because the panel's own text says it.
function limitParas(limits) {
  const out = [];
  for (const limit of limits) {
    out.push(limitLine(limit));
    if (limit.lock_reason !== "cap_later") out.push(lockText(limit.lock_reason));
  }
  return out.filter(Boolean);
}

const capsOf = (limits) => limits.filter((l) => l.kind === "cap");
const allCapLater = (caps) => caps.length > 0 && caps.every((l) => l.lock_reason === "cap_later");

function stopPanel(level, value) {
  const limits = Array.isArray(level && level.limits) ? level.limits : [];
  const paras = [];
  if (allCapLater(capsOf(limits))) paras.push(t("ed_stop_cap_t", { level: value }));
  if (limits.some((l) => l.kind === "model")) paras.push(t("ed_stop_model_t", { level: value, runs_as: text(level.runs_as) }));
  if (limits.some((l) => l.kind === "winner")) paras.push(t("ed_stop_winner_t", { level: value }));
  const unknown = limits.some((l) => l.kind === "model_unknown");
  if (unknown) paras.push(t("ed_stop_unknown_t", { level: value }));
  const heading = unknown ? t("ed_stop_unknown_h", { level: value }) : t("ed_stop_h", { level: value });
  return nt("warn", heading, paras.concat(limitParas(limits)),
    [button(t("ed_cancel"), { focus: "cancel", onClick: cancel })]);
}

// One literal t() call per status, so the string checks can see every key.
function winnerWarning(status) {
  switch (status) {
    case "overridden": return t("ed_warn_overridden_t");
    case "ignored": return t("ed_warn_ignored_t");
    case "invalid": return t("ed_warn_invalid_t");
    case "unknown": return t("ed_warn_unknown_t");
    default: return null;
  }
}

function warningParas(warning) {
  const limits = Array.isArray(warning.limits) ? warning.limits : [];
  const caps = capsOf(limits);
  const paras = [];
  if (caps.length) {
    if (warning.status === "in_effect") paras.push(t("ed_warn_nomodel_cap_t"));
    else if (allCapLater(caps)) paras.push(t("ed_warn_cap_t"));
  }
  if (limits.some((l) => l.kind === "model")) paras.push(t("ed_warn_model_t"));
  paras.push(winnerWarning(warning.status));
  return paras.filter(Boolean).concat(limitParas(limits));
}

// ---------------------------------------------------------------- the review

function mainEntries(payload) {
  const rows = payload && Array.isArray(payload.rows) ? payload.rows : [];
  const row = rows.find((r) => r.agent === MAIN_KEY && r.setting === SETTING);
  const entries = row && payload.entries ? row.entries.map((i) => payload.entries[i]).filter(Boolean) : [];
  return entries;
}

// A value, its status chip and what it runs as, for one cell of the table.
function cell(value, status, becomes) {
  return h("span", { class: "p2-cell" },
    value === "" ? null : h("span", { class: "val mono" }, value),
    status ? chip(status) : null,
    becomes === null || becomes === undefined || becomes === "" ? null : h("span", { class: "runs" }, t("runs_as_cell", { becomes })));
}

function entryCell(entry, payload) {
  if (!entry) return h("span", { class: "p2-cell" });
  return cell(valueString(entry, payload), entry.status, entry.becomes);
}

function changeCell(side) {
  if (!side) return h("span", { class: "p2-cell" });
  const runs = side.runs_as !== side.value ? side.runs_as : null;
  return cell(text(side.value), side.status, runs);
}

function row(first, nowCell, afterCell, changed) {
  return h("tr", { class: changed ? "p2-tr-on" : "p2-tr-same" },
    h("td", { "data-l": t("ed_th_value") }, h("span", null, first)),
    h("td", { "data-l": t("ed_th_now") }, nowCell),
    h("td", { "data-l": t("ed_th_after") }, afterCell));
}

function trailTable(pv, target) {
  const before = mainEntries(pv.before);
  const after = mainEntries(pv.after);
  const nowBy = new Map(before.map((e) => [editRef(e), e]));
  const afterBy = new Map(after.map((e) => [editRef(e), e]));
  const refs = Array.from(new Set(before.map(editRef).concat(after.map(editRef))));
  const body = refs.map((ref) => {
    const was = nowBy.get(ref) || null;
    const will = afterBy.get(ref) || null;
    const changed = Boolean(target) && ref === target.ref;
    const one = was || will;
    const payload = was ? pv.before : pv.after;
    const label = layerText(one, payload) || sourceText(one, payload, true);
    const first = [h("span", { class: "ly" }, label), changed ? " " : null, changed ? h("span", { class: "p2-tag" }, t("ed_tag_changes")) : null];
    return row(first, entryCell(was, pv.before), entryCell(will, pv.after), changed);
  });
  const also = (Array.isArray(pv.changes) ? pv.changes : []).filter((c) => c.agent !== MAIN_KEY);
  return h("table", { class: "dt p2-tbl" },
    h("caption", { class: "sr" }, t("ed_tbl_cap")),
    h("thead", null, h("tr", null,
      h("th", { scope: "col" }, t("ed_th_value")), h("th", { scope: "col" }, t("ed_th_now")), h("th", { scope: "col" }, t("ed_th_after")))),
    h("tbody", null, body),
    also.length ? h("tbody", null,
      h("tr", { class: "p2-tr-h" }, h("th", { colspan: 3, scope: "colgroup" }, t("ed_also"))),
      also.map((c) => row(h("span", { class: "ly" }, t("ed_also_agent", { agent: text(c.agent) })),
        changeCell(c.before), changeCell(c.after), true))) : null);
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

function diffFigure(diff, target) {
  const name = basename(diff.file_display);
  const layer = target ? layerText({ layer: target.layer }) : "";
  return h("figure", { class: "p2-df" },
    h("figcaption", { class: "p2-df-h" }, layer ? h("span", { class: "ly" }, layer) : null, h("span", { class: "pa" }, text(diff.file_display))),
    (Array.isArray(diff.hunks) ? diff.hunks : []).map((hunk) => {
      const lines = Array.isArray(hunk.lines) ? hunk.lines : [];
      const marks = pairMarks(lines);
      return h("ol", { "aria-label": t("ed_diff_sr", { file: name }) }, lines.map((line, i) => diffLine(line, marks.get(i))));
    }));
}

function runsAfter(pv, T) {
  const change = (Array.isArray(pv.changes) ? pv.changes : []).find((c) => c.agent === MAIN_KEY && c.setting === SETTING);
  if (change) return change.after && change.after.runs_as !== null && change.after.runs_as !== undefined ? change.after.runs_as : null;
  return T.runs_as !== null && T.runs_as !== undefined ? T.runs_as : null;
}

function headline(pv, T, level) {
  const was = T.runs_as;
  const next = runsAfter(pv, T);
  const warning = pv.warning;
  let note = t("ed_runs");
  if (warning && warning.status === "unknown") note = t("ed_nochange_unknown");
  else if (warning && warning.in_effect_changes === false) note = t("ed_nochange");
  else if (level && level.certain === false) note = t("ed_runs_uncertain", { level: text(pv.new_value) });
  const hasWas = was !== null && was !== undefined;
  return h("div", { class: "p2-head" },
    hasWas ? h("span", { class: "p2-big is-was" }, text(was)) : null,
    hasWas ? h("span", { class: "p2-big p2-arrow", "aria-hidden": "true" }, "→") : null,
    hasWas ? h("span", { class: "sr" }, t("ed_to")) : null,
    h("span", { class: "p2-big" }, text(next !== null ? next : pv.new_value)),
    h("span", { class: "runs" }, note));
}

// The buttons under the review. Busy shows Saving, with the buttons off.
function actions(pv, fileName, ledger) {
  const busy = S.busy;
  const save = (label) => button(busy ? t("ed_saving") : label, {
    primary: !pv.warning, focus: "save", disabled: busy, busy, onClick: doSave,
  });
  const cancelButton = button(t("ed_cancel"), { focus: "cancel", disabled: busy, onClick: cancel });
  const saying = busy ? h("span", { class: "sr", role: "status" }, t("ed_saving_sr", { file: fileName })) : null;
  if (S.failed) {
    const why = S.failedDir
      ? draw(t("ed_fail_config_dir_t", { config_dir: mark("config_dir") }), { config_dir: S.failedDir })
      : t("ed_fail_t", { file: fileName });
    return [nt("err", t("ed_fail_h"), [why]),
      h("div", { class: "p2-ctl" }, button(t("ed_try_again"), { primary: true, focus: "try", onClick: doSave }), cancelButton)];
  }
  if (pv.no_change === true) {
    return h("div", { class: "p2-ctl" }, cancelButton, hint(t("ed_no_change_note")));
  }
  const w = pv.warning;
  let warnHeading = null;
  if (w) {
    if (w.status === "unknown") warnHeading = t("ed_warn_unknown_h");
    else warnHeading = w.in_effect_changes === true ? t("ed_warn_part_h") : t("ed_warn_h");
  }
  if (ledger) {
    // The warning still shows, but this file takes no save, so only Cancel is drawn.
    return [w ? nt("warn", warnHeading, warningParas(w)) : null,
      nt("warn", t("ed_ledger_preview_t", { file: fileName }), [], [cancelButton])];
  }
  if (w) return nt("warn", warnHeading, warningParas(w), [save(t("ed_save_anyway")), cancelButton, saying]);
  return h("div", { class: "p2-ctl p2-stick" }, save(t("ed_save_to", { file: fileName })), cancelButton,
    hint(t("ed_nothing_yet")), saying);
}

function review(T, state) {
  const pv = state.data;
  const target = targetById(T, state.target);
  const file = target ? target.file_display : (pv.diff ? pv.diff.file_display : "");
  const fileName = basename(file);
  const level = levelRow(T, state.value);
  const ledger = Boolean(damagedFor(file, target ? target.layer : null));
  const hints = [];
  if (target && target.shared === true) hints.push(hint(t("ed_shared")));
  if (level && level.certain === false) hints.push(hint(t("ed_certain_note")));
  return h("div", { class: "p2-rvw" },
    headline(pv, T, level),
    h("div", null, trailTable(pv, target)),
    h("div", null,
      h("p", { class: "p2-sub" }, t("ed_file_h", { file: fileName, line: target ? text(target.line) : "" })),
      pv.diff ? diffFigure(pv.diff, target) : null),
    hints.length ? h("div", null, hints) : null,
    actions(pv, fileName, ledger));
}

// ---------------------------------------------------------------- the card

function levelNote(level, scoped) {
  if (scoped) return level.level === scoped.current_value ? t("ed_seg_now") : null;
  if (level.result === "now") return t("ed_seg_now");
  if (level.result === "stopped") {
    const limits = Array.isArray(level.limits) ? level.limits : [];
    return allCapLater(capsOf(limits)) ? t("ed_seg_cap") : t("ed_seg_stopped");
  }
  return null;
}

function picker(T, scoped) {
  const group = h("div", {
    class: "segs p2-segs", role: "radiogroup", "aria-label": t("ed_level_group_sr"),
    "aria-describedby": T.levels_state === "model_unknown" ? "p2-levels-note" : null,
  });
  for (const level of T.levels) {
    const on = S.picked === level.level;
    const note = levelNote(level, scoped);
    group.appendChild(h("label", { class: ["seg", "p2-seg", on && "is-active"] },
      h("input", {
        class: "sr", type: "radio", name: "p2-level", value: level.level, checked: on, disabled: S.busy,
        "data-edit-focus": "radio:" + level.level, on: { change: () => pick(level.level) },
      }),
      h("span", { class: "p2-sv" }, text(level.level)),
      note ? h("span", { class: "p2-sn" }, note) : null));
  }
  return group;
}

function mainCard(T) {
  const scoped = scopedTarget(T);
  const inner = [];
  if (S.notice) inner.push(nt(S.notice.kind, S.notice.heading, S.notice.paras || [], S.notice.dismiss ? [dismissButton("card")] : []));
  if (S.frame) inner.push(frameNodes(S.frame));
  else if (S.view === "stop") {
    const level = levelRow(T, S.picked);
    inner.push(stopPanel(level, S.picked));
  } else if (S.pv) inner.push(review(T, S.pv));
  const open = Boolean(S.frame) || S.view === "stop" || Boolean(S.pv); // the hints give way to a review
  const title = scoped ? t("ed_card_line", { file: basename(scoped.file_display), line: text(scoped.line) }) : t("ed_card");
  const label = scoped ? t("ed_field") : t("ed_q");
  const hints = open ? [] : [
    hint(t("ed_hint")),
    T.levels_state === "model_unknown" ? hint(t("ed_levels_model_unknown"), "p2-levels-note") : null,
    hint(t("ed_new_session")),
  ];
  const body = h("div", { class: "p2-rvw" },
    h("div", { class: "p2-field" }, h("span", { class: "p2-lab" }, label), picker(T, scoped), hints),
    inner);
  return shell(title, body, open || inner.length > 0);
}

// A model with no effort levels has nothing to pick. The card says so, and shows what runs.
function noSupportCard(T) {
  const hasRuns = T.runs_as !== null && T.runs_as !== undefined;
  return shell(t("ed_card"), h("div", { class: "p2-field" },
    hasRuns ? h("div", { class: "p2-head" }, h("span", { class: "p2-big" }, text(T.runs_as))) : null,
    lockLine(t("ed_levels_no_support"))), false);
}

function frameNodes(frame) {
  const done = () => { resetCard(); S.want = "radio"; redraw("card"); };
  const ctl = (focus) => h("div", { class: "p2-ctl" }, button(t("ed_dismiss"), { focus, onClick: focus === "dismiss-ledger" ? dismissLedger : done }));
  if (frame.type === "raced") {
    return [nt("warn", t("ed_raced_h", { file: frame.file }), [frame.path ? draw(t("ed_raced_t", { path: mark("path") }), { path: frame.path }) : null]),
      ctl("dismiss-card")];
  }
  if (frame.type === "unverified") {
    const fsync = frame.stage === "fsync";
    const heading = fsync ? t("ed_unverified_fsync_h") : t("ed_unverified_reread_h");
    const slots = { path: mark("path") };
    const body = fsync ? t("ed_unverified_fsync_t", slots) : t("ed_unverified_reread_t", slots);
    return [nt("err", heading, [frame.path ? draw(body, { path: frame.path }) : null]), ctl("dismiss-card")];
  }
  return [nt("err", t("ed_ledger_h", { file: frame.file }),
    [frame.path ? draw(t("ed_ledger_t", { path: mark("path") }), { path: frame.path }) : null]), ctl("dismiss-ledger")];
}

function dismissButton(where) {
  return button(t("ed_dismiss"), {
    focus: "dismiss-" + where,
    onClick: () => {
      if (where === "card") {
        S.notice = null;
        redraw("card");
      } else {
        dismissStrip();
      }
    },
  });
}

function tokenNt() {
  return nt("err", t("ed_token_h"), [t("ed_token_t")]);
}

function cardNodes() {
  const mode = live.ctx.edit.mode;
  if (mode === "off") return [hint(tn("ed_off"))];
  if (mode === "locked") return [S.token && S.token.where === "card" ? tokenNt() : null, hint(tn("ed_locked"))];
  if (mode !== "ready") return [];
  const T = targetsData();
  if (T === null) return [];
  if (T === false) return [hint(t("ed_err_network"))];
  if (T.levels_state === "no_effort_support") return [noSupportCard(T)];
  return [mainCard(T)];
}

// ---------------------------------------------------------------- the strip

function lastStrip(row) {
  const file = basename(row.file_display);
  const line = t("ed_last_t", { when: fmtTime(row.time), old: text(row.old_value), new: text(row.new_value), file });
  if (row.kind === "undo") {
    return strip("quiet", [line, row.restored_from_display ? " " : null,
      row.restored_from_display ? draw(t("ed_undone_path", { path: mark("path") }), { path: row.restored_from_display }) : null]);
  }
  const buttons = row.undoable === true ? [undoButton(row)] : [];
  return strip("quiet", [line, row.backup_display ? " " : null,
    row.backup_display ? draw(t("ed_saved_backup", { path: mark("path") }), { path: row.backup_display }) : null], buttons);
}

function staleUndoLine(file, path) {
  return [t("ed_undo_stale_h", { file }), path ? " " : null, path ? draw(t("ed_undo_stale_t", { path: mark("path") }), { path }) : null];
}

function restStrip(row) {
  const reason = row.not_undoable_reason;
  if (row.kind !== "undo" && row.undoable !== true) {
    if (reason === "changed_since_save") return strip("warn", staleUndoLine(basename(row.file_display), row.backup_display), [], "status");
    if (reason === "backup_damaged") {
      const line = row.backup_display ? draw(t("ed_backup_damaged_rest", { path: mark("path") }), { path: row.backup_display }) : t("ed_backup_damaged_h");
      return strip("warn", line);
    }
    if (reason === "backup_pruned") return strip("quiet", t("ed_backup_pruned_rest"));
  }
  return lastStrip(row);
}

function undoButton(row) {
  return button(t("ed_undo"), { focus: "undo", disabled: S.stripBusy, busy: S.stripBusy, onClick: () => doUndo(row) });
}

// One literal t() call per line, so the string checks can see every key. The warning is the saved preview's.
function savedLine(warning, slots) {
  if (!warning) return t("ed_saved_t", slots);
  if (warning.status === "unknown") return t("ed_saved_unknown_t", slots);
  if (warning.in_effect_changes === true) return t("ed_saved_part_t", slots);
  if (warning.in_effect_changes === false) return t("ed_saved_no_effect_t", slots);
  return t("ed_saved_t", slots);
}

function stripResult(f) {
  const dismiss = () => button(t("ed_dismiss"), { focus: "dismiss-strip", onClick: dismissStrip });
  switch (f.kind) {
    case "saved": {
      const file = basename(f.edit.file_display);
      const line = [savedLine(f.warning, { file, level: text(f.edit.new_value) }),
        f.edit.backup_display ? " " : null,
        f.edit.backup_display ? draw(t("ed_saved_backup", { path: mark("path") }), { path: f.edit.backup_display }) : null];
      return strip("ok", line, f.edit.undoable === true ? [undoButton(f.edit)] : [], "status");
    }
    case "undone": {
      const file = basename(f.edit.file_display);
      const line = [t("ed_undone_t", { file }), f.restored ? " " : null,
        f.restored ? draw(t("ed_undone_path", { path: mark("path") }), { path: f.restored }) : null];
      return strip("ok", line, [dismiss()], "status");
    }
    case "stale_undo":
      return strip("warn", staleUndoLine(f.file, f.path), [dismiss()], "status");
    case "backup_damaged":
      return nt("err", t("ed_backup_damaged_h"), [f.path ? draw(t("ed_backup_damaged_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    case "not_undoable":
      return nt("err", t("ed_not_undoable"), [], [dismiss()]);
    case "write_failed":
      return nt("err", t("ed_fail_h"), [t("ed_fail_t", { file: f.file })], [dismiss()]);
    case "config_dir_missing":
      return nt("err", t("ed_fail_h"), [draw(t("ed_fail_config_dir_t", { config_dir: mark("config_dir") }), { config_dir: f.path })], [dismiss()]);
    case "unverified": {
      const fsync = f.stage === "fsync";
      const slots = { path: mark("path") };
      const body = fsync ? t("ed_unverified_fsync_t", slots) : t("ed_unverified_reread_t", slots);
      return nt("err", fsync ? t("ed_unverified_fsync_h") : t("ed_unverified_reread_h"), [f.path ? draw(body, { path: f.path }) : null], [dismiss()]);
    }
    case "raced":
      return nt("warn", t("ed_raced_h", { file: f.file }), [f.path ? draw(t("ed_raced_undo_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    case "ledger":
      return nt("err", t("ed_ledger_h", { file: f.file }), [f.path ? draw(t("ed_ledger_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    default:
      return nt("err", f.text, [], [dismiss()]);
  }
}

function stripNodes() {
  const mode = live.ctx.edit.mode;
  if (mode === "locked") return [S.token && S.token.where === "strip" ? tokenNt() : null];
  if (mode !== "ready") return [];
  const history = historyData();
  const out = [];
  const ledgers = history && Array.isArray(history.damaged_ledgers) ? history.damaged_ledgers : [];
  for (const d of ledgers) {
    out.push(strip("warn", draw(t("ed_ledger_rest_t", { file: basename(d.file_display), path: mark("path") }), { path: d.ledger_display })));
  }
  if (S.strip) out.push(stripResult(S.strip));
  else if (history && Array.isArray(history.rows) && history.rows.length) out.push(restStrip(history.rows[0]));
  return out;
}

// ---------------------------------------------------------------- drawing and focus

function fill(slot, nodes) {
  if (!slot) return;
  clear(slot);
  slot.appendChild(frag(nodes));
}

function fillCard() {
  fill(live.card, cardNodes());
}

function fillStrip() {
  fill(live.strip, stripNodes());
}

// Gives focus to the control a result asked for. "radio" is the checked level, else the first one. It runs
// only once the nodes are in the page, because a detached node takes no focus.
function applyWant() {
  if (!S.want || !live) return false;
  const slots = [live.card, live.strip].filter(Boolean);
  const find = (test) => slots.flatMap((slot) => walk(slot, test))[0] || null;
  const key = (n) => String(n.getAttribute("data-edit-focus"));
  const target = S.want === "radio"
    ? find((n) => key(n) === "radio:" + S.picked) || find((n) => key(n).startsWith("radio:"))
    : find((n) => key(n) === "btn:" + S.want);
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

// Puts focus back on the control with this key, inside root.
export function restoreFocus(root, key) {
  if (!key || !root) return;
  const found = walk(root, (n) => n.getAttribute("data-edit-focus") === key)[0];
  if (found && found !== document.activeElement) found.focus();
}

// Called by the trail once its panel is in the page: a pending focus first, else the control that held focus.
export function settle(root, key) {
  if (!applyWant()) restoreFocus(root, key);
}

function redraw(which) {
  if (!live) return;
  const key = focusKey();
  if (which !== "strip") fillCard();
  if (which !== "card") fillStrip();
  if (applyWant()) return;
  for (const slot of [live.card, live.strip]) if (slot) restoreFocus(slot, key);
}

// ---------------------------------------------------------------- actions

function tokenOutcome(where) {
  S.token = { where };
  S.busy = false;
  S.stripBusy = false;
  redraw();
}

function cancel() {
  resetCard();
  S.want = "radio";
  redraw("card");
}

function openScope(target) {
  if (S.busy) return;
  resetCard();
  S.strip = S.stripBusy ? S.strip : null;
  S.scope = target.target;
  S.want = "radio";
  redraw();
}

function pick(value) {
  if (S.busy || !live) return;
  const T = targetsData();
  if (!T) return;
  const scoped = scopedTarget(T);
  S.seq += 1; // an older preview answer still on its way is dropped
  S.notice = null;
  S.frame = null;
  S.failed = false;
  S.failedDir = null;
  S.pv = null;
  S.view = "rest";
  S.picked = value;
  const hadResult = Boolean(S.strip) && !S.stripBusy;
  if (hadResult) S.strip = null; // a new edit starts
  const level = levelRow(T, value);
  if (scoped) {
    if (value === scoped.current_value) S.picked = null;
    else startPreview(scoped.target, value);
  } else if (!level || level.result === "now") {
    S.picked = null;
  } else if (level.result === "stopped") {
    S.view = "stop";
  } else {
    startPreview(level.target, value);
  }
  redraw(hadResult ? undefined : "card"); // the card's own node, and the strip's only when its result went
}

async function startPreview(target, value) {
  const mine = S.seq;
  const epoch = S.epoch;
  let out;
  try {
    out = await live.ctx.edit.preview(target, value);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    tokenOutcome("card");
    return;
  }
  if (mine !== S.seq || epoch !== S.epoch) return;
  const data = bodyOf(out);
  if (out && out.kind === "ok" && data.diff) {
    S.pv = { target, value, data };
  } else {
    S.notice = { kind: "err", heading: errorText(out && out.res), paras: [], dismiss: true };
  }
  redraw("card");
}

function staleNotice(data) {
  const files = Array.isArray(data.changed_files) ? data.changed_files : [];
  const names = files.map((f) => basename(f.file_display));
  const fresh = data.preview && typeof data.preview === "object" ? data.preview : null;
  let heading;
  let paras = [];
  if (data.changed === "trail") {
    heading = t("ed_stale_trail_h");
    paras = [names.length ? t("ed_stale_trail_t", { files: names.join(", ") }) : t("ed_stale_trail_general_t")];
  } else {
    heading = t("ed_stale_file_h", { file: names[0] || basename(S.pv && S.pv.data.diff ? S.pv.data.diff.file_display : "") });
    paras = [t("ed_stale_file_t")];
  }
  if (!fresh) paras = [t("ed_stale_gone_t")];
  return { notice: { kind: "warn", heading, paras, dismiss: false }, fresh };
}

async function doSave() {
  if (S.busy || !S.pv || !live) return;
  const epoch = S.epoch;
  const sent = S.pv;
  const fileName = basename(sent.data.diff ? sent.data.diff.file_display : "");
  S.busy = true;
  S.failed = false;
  S.failedDir = null;
  S.notice = null;
  if (!S.stripBusy) S.strip = null;
  redraw();
  let out;
  try {
    out = await live.ctx.edit.save(sent.data, sent.target, sent.value);
  } catch (err) {
    out = { kind: "error", res: null };
  }
  if (out && out.kind === "locked") {
    tokenOutcome("card");
    return;
  }
  S.busy = false;
  if (epoch !== S.epoch) return;
  const data = bodyOf(out);
  const kind = out ? out.kind : "error";
  let staleReload = false;
  if (kind === "ok") {
    resetCard();
    S.strip = { kind: "saved", edit: data.edit || {}, warning: sent.data.warning || null };
    S.want = data.edit && data.edit.undoable === true ? "undo" : "radio";
  } else if (kind === "stale") {
    const stale = staleNotice(data);
    S.notice = stale.notice;
    S.pv = stale.fresh ? { target: sent.target, value: sent.value, data: stale.fresh } : null;
    if (!stale.fresh) S.picked = null;
    staleReload = true;
  } else if (kind === "raced") {
    S.pv = null;
    S.frame = { type: "raced", file: fileName, path: data.backup_display || null };
    S.want = "dismiss-card";
  } else if (kind === "unverified") {
    S.pv = null;
    S.frame = { type: "unverified", stage: data.stage, path: data.backup_display || null };
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
    S.want = "try";
  } else {
    S.notice = { kind: "err", heading: errorText(out && out.res), paras: [], dismiss: true };
  }
  redraw();
  if (staleReload) refreshEdit(); // the page data is old now; this never retries the save
}

async function doUndo(row) {
  if (S.stripBusy || !live) return;
  const epoch = S.epoch;
  const file = basename(row.file_display);
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
  S.stripBusy = false;
  if (epoch !== S.epoch) return;
  const data = bodyOf(out);
  const kind = out ? out.kind : "error";
  const code = codeOf(out);
  let changed = false;
  if (kind === "ok" && data.matches_backup === true) {
    S.strip = { kind: "undone", edit: data.edit || row, restored: data.restored_from_display || null };
    S.want = "dismiss-strip";
  } else if (kind === "ok" || kind === "raced") {
    S.strip = { kind: "raced", file, path: data.restored_from_display || null };
    S.want = "dismiss-strip";
  } else if (kind === "unverified") {
    S.strip = { kind: "unverified", stage: data.stage, path: data.backup_display || null };
    S.want = "dismiss-strip";
  } else if (code === "changed_since_save") {
    S.strip = { kind: "stale_undo", file, path: data.backup_display || null };
    changed = true;
  } else if (code === "backup_damaged") {
    S.strip = { kind: "backup_damaged", path: data.backup_display || null };
    S.want = "dismiss-strip";
  } else if (code === "not_undoable") {
    S.strip = { kind: "not_undoable" };
    S.want = "dismiss-strip";
  } else if (code === "config_dir_missing" && data.config_dir_display) {
    S.strip = { kind: "config_dir_missing", path: data.config_dir_display };
    S.want = "dismiss-strip";
  } else if (code === "write_failed") {
    S.strip = { kind: "write_failed", file };
    S.want = "dismiss-strip";
  } else if (code === "ledger_damaged") {
    S.strip = { kind: "ledger", file, path: data.ledger_display || null };
    S.want = "dismiss-strip";
  } else {
    S.strip = { kind: "error", text: errorText(out && out.res) };
  }
  redraw("strip");
  if (changed) refreshEdit(); // the history still lists an Undo that no longer works, so Dismiss must not bring it back
}

function dismissStrip() {
  const wasLedger = S.strip && S.strip.kind === "ledger";
  S.strip = null;
  redraw("strip");
  if (wasLedger) reloadEdit();
}

function dismissLedger() {
  resetCard();
  redraw("card");
  reloadEdit();
}

function reloadEdit() {
  if (live && live.ctx.edit && typeof live.ctx.edit.reload === "function") live.ctx.edit.reload();
}

// A file changed behind the page's back, so the tiles and the trail are old too, not only the targets and history.
function refreshEdit() {
  if (live && live.ctx.edit && typeof live.ctx.edit.refresh === "function") live.ctx.edit.refresh();
  else reloadEdit();
}

// ---------------------------------------------------------------- entries on the trail

function entryLink(target) {
  const edit = live.ctx;
  const href = edit.hashFor(edit.route.name, edit.route.params);
  return h("span", { class: "p2-act" },
    h("a", {
      class: "lnk", href, "data-edit-focus": "link:" + target.ref,
      on: { click: (event) => { event.preventDefault(); openScope(target); } },
    }, t("ed_this")));
}

// What an entry of the main effort row gets: a Change link when a target matches it, a lock line when a blocked
// row does. No match after the targets loaded means the files moved, so the page loads them again.
function extrasFor(entry) {
  if (!live || live.ctx.edit.mode !== "ready") return {};
  const T = targetsData();
  if (!T || T.levels_state === "no_effort_support") return {};
  const ref = editRef(entry);
  const target = T.targets.find((x) => x.ref === ref);
  if (target) return { act: entryLink(target) };
  const blocked = (Array.isArray(T.blocked) ? T.blocked : []).find((x) => x.ref === ref);
  if (blocked) {
    const line = lockText(blocked.reason);
    return line ? { lock: lockLine(line) } : {};
  }
  live.misses += 1;
  return {};
}

// ---------------------------------------------------------------- entry points

// Called by the trail of the main session's effortLevel, once per render, before the page head is drawn. It
// returns the strip slot and the card, and the helpers the entries use. Mode null returns nothing to place.
export function begin(ctx) {
  const mode = ctx.edit ? ctx.edit.mode : null;
  const key = ctx.project ? ctx.project.key : null;
  if (S.project !== key || S.mode !== mode) {
    resetFlow();
    S.project = key;
    S.mode = mode;
    S.reloads = 0;
  }
  if (mode !== "off" && mode !== "locked" && mode !== "ready") {
    live = null;
    return { strip: null, card: null, extras: () => ({}), done: () => {} };
  }
  live = {
    ctx,
    card: h("div", { "data-edit": "card" }),
    strip: mode === "off" ? null : h("div", { "data-edit": "strip" }),
    misses: 0,
  };
  fillCard();
  fillStrip();
  const mine = live;
  return {
    strip: mine.strip,
    card: mine.card,
    extras: extrasFor,
    // Called when the panel is built. One load per run of misses, so a file that stays missing can't loop.
    done: () => {
      if (mine.misses === 0) {
        S.reloads = 0;
        return;
      }
      if (S.reloads >= 1) return;
      S.reloads += 1;
      Promise.resolve().then(reloadEdit);
    },
  };
}

// Called by every other render of the trail page, so a flow left half done is not there on the way back.
export function leave() {
  if (S.mode !== undefined || live) {
    resetFlow();
    S.mode = undefined;
  }
  live = null;
  return null;
}
