// The pure builders of the rail foot's results (round 6 design, boards a-rest and a12-saved): the last-edit line,
// the stale and damaged lines, the result of this page's own press, and the list of them. Nothing here holds state
// or imports it. What the flow knows comes in as the env argument ({ mode, token, strip, stripBusy, history, doUndo,
// dismissStrip }).
//
// Rules this file keeps, the same as edit_card.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.

import { h } from "./h.js";
import { t, fmtTime } from "./format.js";
import { MARKS, basename, button, draw, mark, nt, text, tokenNt, undoIcon } from "./edit_ui.js";

const OK_CLASS = { ok: "s4-ok", warn: "s4-ok s4-ok-warn" };

// A result in the foot: a mark and a line in one status row, then the buttons, then a path line when there is one.
// kind ok is the check, kind warn the triangle, and kind quiet is the plain note of the row at rest. role is null
// for a line that only sits there. Returns a list of nodes, because the foot is a grid that lays them out itself.
export function strip(kind, line, buttons = [], role = null, below = null) {
  const lead = kind === "quiet"
    ? h("p", { class: "s4-note" }, line)
    : h("div", { class: OK_CLASS[kind], role },
      h("span", { class: "s4-okm", "aria-hidden": "true" }, MARKS[kind]),
      h("span", null, line));
  return [lead, buttons, below ? h("p", { class: "s4-hint" }, below) : null];
}

// The path of a backup or a restored file, as the line under a result. Null when there is none, so no empty line shows.
const pathLine = (key, path) => (path ? draw(t(key, { path: mark("path") }), { path }) : null);

// ---------------------------------------------------------------- the strip

// The line of a history row. One literal t() call for each kind, so the string checks can see every key. A row leaves
// out the value it never had (a create has no old one, a remove no new one), and only the value a line prints is read.
function lastLine(row) {
  const file = basename(row.file_display);
  const when = fmtTime(row.time);
  if (row.kind === "undo" && row.op && row.op !== "replace") return t("ed_last_undone_t", { when, file });
  // A replace row with no old value (effortLevel was null) has no "from" to print, and its undo has no "to".
  const has = (v) => v !== undefined && v !== null && v !== "";
  if (row.kind === "undo" && (!has(row.old_value) || !has(row.new_value))) return t("ed_last_undone_t", { when, file });
  if (row.kind !== "undo" && (!row.op || row.op === "replace") && !has(row.old_value)) {
    return t("ed_last_added_t", { when, file, new: text(row.new_value) });
  }
  switch (row.kind === "undo" ? "replace" : row.op) {
    case "insert": return t("ed_last_added_t", { when, file, new: text(row.new_value) });
    case "create": return t("ed_last_created_t", { when, file, new: text(row.new_value) });
    case "remove": return t("ed_last_removed_t", { when, file, old: text(row.old_value) });
    default: return t("ed_last_t", { when, file, old: text(row.old_value), new: text(row.new_value) });
  }
}

export function lastStrip(row, env) {
  const line = lastLine(row);
  if (row.kind === "undo") {
    return strip("quiet", [line, row.restored_from_display ? " " : null,
      row.restored_from_display ? draw(t("ed_undone_path", { path: mark("path") }), { path: row.restored_from_display }) : null]);
  }
  const buttons = row.undoable === true ? [undoButton(row, env)] : [];
  return strip("quiet", [line, row.backup_display ? " " : null,
    row.backup_display ? draw(t("ed_saved_backup", { path: mark("path") }), { path: row.backup_display }) : null], buttons);
}

// A file the save created has no backup to point at, so the line ends at "delete the file by hand".
export function staleUndoLine(file, path, op = null) {
  if (op === "create") return [t("ed_undo_stale_h", { file }), " ", t("ed_undo_stale_created_t")];
  return [t("ed_undo_stale_h", { file }), path ? " " : null, path ? draw(t("ed_undo_stale_t", { path: mark("path") }), { path }) : null];
}

export function restStrip(row, env) {
  const reason = row.not_undoable_reason;
  if (row.kind !== "undo" && row.undoable !== true) {
    if (reason === "changed_since_save") return strip("warn", staleUndoLine(basename(row.file_display), row.backup_display, row.op), [], "status");
    if (reason === "backup_damaged") {
      const line = row.backup_display ? draw(t("ed_backup_damaged_rest", { path: mark("path") }), { path: row.backup_display }) : t("ed_backup_damaged_h");
      return strip("warn", line);
    }
    if (reason === "backup_pruned") return strip("quiet", t("ed_backup_pruned_rest"));
  }
  return lastStrip(row, env);
}

export function undoButton(row, env) {
  return button([undoIcon(), t("ed_undo")], {
    wide: true, focus: "undo", disabled: env.stripBusy, busy: env.stripBusy, onClick: () => env.doUndo(row),
  });
}

const has = (value) => value !== null && value !== undefined;

// A remove tells what a new session runs now. runsAfter comes from the preview the save was made from.
function removedLine(f, file) {
  if (f.noEffect === true) return t("ed_saved_removed_no_effect_t", { file });
  if (!has(f.runsAfter)) return t("ed_saved_removed_unknown_t", { file });
  return t("ed_saved_removed_t", { file, level: text(f.runsAfter) });
}

// One literal t() call per line, so the string checks can see every key. f is the saved result: the edit, the saved
// preview's warning, and for a remove whether it changed nothing and what runs after.
export function savedLine(f, slots) {
  const warning = f.warning;
  if (f.edit && f.edit.op === "remove") return removedLine(f, slots.file);
  if (!warning && f.edit && f.edit.op === "create") return t("ed_saved_created_t", slots);
  if (!warning) return t("ed_saved_t", slots);
  if (warning.status === "unknown") return t("ed_saved_unknown_t", slots);
  if (warning.in_effect_changes === true) return t("ed_saved_part_t", slots);
  if (warning.in_effect_changes === false) return t("ed_saved_no_effect_t", slots);
  return t("ed_saved_t", slots);
}

export function stripResult(f, env) {
  const dismiss = (wide = false) => button(t("ed_dismiss"), { wide, focus: "dismiss-strip", onClick: env.dismissStrip });
  switch (f.kind) {
    case "saved": {
      const file = basename(f.edit.file_display);
      return strip("ok", savedLine(f, { file, level: text(f.edit.new_value) }),
        f.edit.undoable === true ? [undoButton(f.edit, env)] : [], "status", pathLine("ed_saved_backup", f.edit.backup_display));
    }
    case "undone": {
      const file = basename(f.edit.file_display);
      const line = f.removedDir ? t("ed_undone_removed_both_t", { file })
        : f.removedFile ? t("ed_undone_removed_file_t", { file }) : t("ed_undone_t", { file });
      return strip("ok", line, [dismiss(true)], "status", pathLine("ed_undone_path", f.restored));
    }
    case "stale_undo":
      return strip("warn", staleUndoLine(f.file, f.path, f.op), [dismiss(true)], "status");
    case "backup_damaged":
      return nt("err", t("ed_backup_damaged_h"), [f.path ? draw(t("ed_backup_damaged_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    case "not_undoable":
      return nt("err", t("ed_not_undoable"), [], [dismiss()]);
    case "write_failed":
      return nt("err", t("ed_undo_fail_h"), [t("ed_undo_fail_t", { file: f.file })], [dismiss()]);
    case "config_dir_missing":
      return nt("err", t("ed_undo_fail_h"), [draw(t("ed_undo_fail_config_dir_t", { config_dir: mark("config_dir") }), { config_dir: f.path })], [dismiss()]);
    case "unverified": {
      const fsync = f.stage === "fsync";
      const slots = { path: mark("path") };
      const heading = fsync ? t("ed_unverified_fsync_h") : t("ed_unverified_reread_h");
      // An undone create has no backup, so the line says to check the file and names no path.
      if (!fsync && f.op === "create") return nt("err", heading, [t("ed_unverified_create_t")], [dismiss()]);
      const body = fsync ? t("ed_unverified_fsync_t", slots) : t("ed_unverified_reread_t", slots);
      return nt("err", heading, [f.path ? draw(body, { path: f.path }) : null], [dismiss()]);
    }
    case "raced": {
      // Undoing a create leaves no backup, so the line says to check the file and names no path.
      const body = f.op === "create" ? t("ed_raced_create_t")
        : f.path ? draw(t("ed_raced_undo_t", { path: mark("path") }), { path: f.path }) : null;
      return nt("warn", t("ed_raced_h", { file: f.file }), [body], [dismiss()]);
    }
    case "ledger":
      return nt("err", t("ed_ledger_h", { file: f.file }), [f.path ? draw(t("ed_ledger_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    default:
      return nt("err", f.text, [], [dismiss()]);
  }
}

export function stripNodes(env) {
  const { mode } = env;
  if (mode === "locked") return [env.token && env.token.where === "strip" ? tokenNt() : null];
  if (mode !== "ready") return [];
  const { history } = env;
  const out = [];
  const ledgers = history && Array.isArray(history.damaged_ledgers) ? history.damaged_ledgers : [];
  for (const d of ledgers) {
    out.push(strip("warn", draw(t("ed_ledger_rest_t", { file: basename(d.file_display), path: mark("path") }), { path: d.ledger_display })));
  }
  if (env.strip) out.push(stripResult(env.strip, env));
  else if (!env.changing && history && Array.isArray(history.rows) && history.rows.length) out.push(restStrip(history.rows[0], env));
  return out;
}
