// The pure builders of the rail foot's results (round 6 design, boards a-rest and a12-saved): the last-edit line,
// the stale and damaged lines, the result of this page's own press, and the list of them. Nothing here holds state
// or imports it. What the flow knows comes in as the env argument ({ mode, token, strip, stripBusy, history, doUndo,
// dismissStrip, startBack, openOlder }).
//
// Rules this file keeps, the same as edit_card.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.

import { h } from "./h.js";
import { t, fmtTime } from "./format.js";
import { MARKS, basename, button, draw, mark, nt, tokenNt, undoIcon } from "./edit_ui.js";
import { olderRows } from "./edit_backup.js";
import { settingOfEdit } from "./edit_setting.js";
import * as words from "./edit_words.js";

const OK_CLASS = { ok: "s4-ok", warn: "s4-ok s4-ok-warn" };

// A result in the foot: a mark and a line in one status row, then the buttons, then a path line when there is one.
// kind ok is the check, kind warn the triangle, and kind quiet is the plain note of the row at rest. role is null
// for a line that only sits there. below is one node or a list of them, and also is a second line under it. Each is its
// own paragraph, left-aligned. Returns a list of nodes, because the foot is a grid that lays them out itself.
export function strip(kind, line, buttons = [], role = null, below = null, also = null) {
  const lead = kind === "quiet"
    ? h("p", { class: "s4-note" }, line)
    : h("div", { class: OK_CLASS[kind], role },
      h("span", { class: "s4-okm", "aria-hidden": "true" }, MARKS[kind]),
      h("span", null, line));
  return [lead, buttons, below ? h("p", { class: "s4-hint" }, below) : null, also ? h("p", { class: "s4-hint" }, also) : null];
}

// The path of a backup or a restored file, as the line under a result. Null when there is none, so no empty line shows.
const pathLine = (key, path) => (path ? draw(t(key, { path: mark("path") }), { path }) : null);

// ---------------------------------------------------------------- the strip

// The line of a history row, worded for the setting the row changed (the last part of its key path), whatever cell is open.
// A row leaves out the value it never had (a create has no old one, a remove no new one), and only the value a line prints
// is read. The words for each kind are in edit_words.js, one literal t() call for each key.
function lastLine(row) {
  const file = basename(row.file_display);
  const when = fmtTime(row.time);
  const setting = settingOfEdit(row);
  const old = () => words.shown(setting, row.old_value);
  const next = () => words.shown(setting, row.new_value);
  if (row.kind === "restore") return t("ed_last_restored_t", { when, file });
  if (row.kind === "undo" && row.op && row.op !== "replace") return t("ed_last_undone_t", { when, file });
  // A replace row with no old value (effortLevel was null) has no "from" to print, and its undo has no "to".
  const has = (v) => v !== undefined && v !== null && v !== "";
  if (row.kind === "undo" && (!has(row.old_value) || !has(row.new_value))) return t("ed_last_undone_t", { when, file });
  if (row.kind !== "undo" && (!row.op || row.op === "replace") && !has(row.old_value)) {
    return words.lastAdded(setting, { when, file, new: next() });
  }
  switch (row.kind === "undo" ? "replace" : row.op) {
    case "insert": return words.lastAdded(setting, { when, file, new: next() });
    case "create": return words.lastCreated(setting, { when, file, new: next() });
    case "remove": return words.lastRemoved(setting, { when, file, old: old() });
    default: return words.lastReplaced(setting, { when, file, old: old(), new: next() });
  }
}

export function lastStrip(row, env) {
  const line = lastLine(row);
  if (row.kind === "undo" || row.kind === "restore") {
    return strip("quiet", [line, row.restored_from_display ? " " : null,
      row.restored_from_display ? draw(t("ed_undone_path", { path: mark("path") }), { path: row.restored_from_display }) : null]);
  }
  const buttons = row.undoable === true ? [undoButton(row, env)] : [];
  return strip("quiet", [line, row.backup_display ? " " : null,
    row.backup_display ? draw(t("ed_saved_backup", { path: mark("path") }), { path: row.backup_display }) : null], buttons);
}

// The history row with this id as the page holds it now, or null.
const rowNow = (env, id) => {
  const rows = env.history && Array.isArray(env.history.rows) ? env.history.rows : [];
  return rows.find((row) => row && row.id === id) || null;
};

// The offer under a refused Undo: Undo anyway puts the file back from the backup, or deletes a file the save created.
const anywayOffer = (op) => (op === "create" ? t("ed_anyway_offer_created_t") : t("ed_anyway_offer_t"));

// A file the save created has no backup to point at, so the line ends at "delete the file by hand".
export function staleUndoLine(file, path, op = null) {
  if (op === "create") return [t("ed_undo_stale_h", { file }), " ", t("ed_undo_stale_created_t")];
  return [t("ed_undo_stale_h", { file }), path ? " " : null, path ? draw(t("ed_undo_stale_t", { path: mark("path") }), { path }) : null];
}

export function restStrip(row, env) {
  const reason = row.not_undoable_reason;
  if (row.kind !== "undo" && row.undoable !== true) {
    if (reason === "changed_since_save" && row.undo_anyway === true) {
      return strip("warn", [t("ed_undo_stale_h", { file: basename(row.file_display) }), " ", anywayOffer(row.op)],
        [anywayButton(row, env)], "status");
    }
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

// Undo anyway opens the preview of the backup. Nothing is written until the preview's confirm.
export function anywayButton(row, env) {
  return button(t("ed_anyway_btn"), {
    wide: true, focus: "anyway", disabled: env.stripBusy, onClick: () => env.startBack("undo", row, "foot"),
  });
}

const has = (value) => value !== null && value !== undefined;

// The setting a result is worded for: the one the save was made for, else the one its edit changed.
const settingOfResult = (f) => f.setting || settingOfEdit(f.edit);

// A remove tells what runs now. runsAfter comes from the preview the save was made from.
function removedLine(f, file, setting) {
  if (f.noEffect === true) return words.savedRemovedNoEffect(setting, { file });
  if (!has(f.runsAfter)) return words.savedRemovedUnknown(setting, { file });
  return words.savedRemoved(setting, { file, level: words.shown(setting, f.runsAfter) });
}

// The line of a saved result, worded for the setting the edit changed. f is the saved result: the edit, the saved
// preview's warning, and for a remove whether it changed nothing and what runs after. level is the value written.
export function savedLine(f, slots) {
  const warning = f.warning;
  const setting = settingOfResult(f);
  if (f.edit && f.edit.op === "remove") return removedLine(f, slots.file, setting);
  if (!warning && f.edit && f.edit.op === "create") return words.savedCreated(setting, slots);
  if (!warning) return words.savedLine(setting, slots);
  if (warning.status === "unknown") return words.savedUnknown(setting, slots);
  if (warning.in_effect_changes === true) return words.savedPart(setting, slots);
  if (warning.in_effect_changes === false) return words.savedNoEffect(setting, slots);
  return words.savedLine(setting, slots);
}

// The line of an Undo anyway or a restore that was written, worded for the setting of its edit.
function backDoneLine(f) {
  const file = basename(f.edit.file_display);
  const setting = settingOfEdit(f.edit);
  if (f.removedDir) return words.backDoneDeletedBoth(setting, { file });
  if (f.removedFile) return words.backDoneDeleted(setting, { file });
  if (f.replacedFile === false) return words.backDoneCreated(setting, { file });
  return f.back === "undo" ? words.backDoneUndo(setting, { file }) : words.backDoneRestored(setting, { file });
}

// Under it, the backup that holds what the file had before (when the write replaced a file), then the backup the file
// now matches, each in its own line. Either can be missing, and then no empty line shows. A file that didn't parse can't
// be restored from Older backups, so its line names the backup and promises nothing more.
function backDoneBelow(f) {
  let kept = null;
  if (f.replacedFile === true && f.replaced) {
    kept = f.replacedUnparsed === true
      ? draw(t("ed_back_kept_unparsed_t", { path: mark("path") }), { path: f.replaced })
      : draw(t("ed_back_kept", { path: mark("path") }), { path: f.replaced });
  }
  const restored = pathLine("ed_undone_path", f.restored);
  return kept ? [kept, restored] : [restored, null];
}

export function stripResult(f, env) {
  const dismiss = (wide = false) => button(t("ed_dismiss"), { wide, focus: "dismiss-strip", onClick: env.dismissStrip });
  switch (f.kind) {
    case "saved": {
      const file = basename(f.edit.file_display);
      return strip("ok", savedLine(f, { file, level: words.shown(settingOfResult(f), f.edit.new_value) }),
        f.edit.undoable === true ? [undoButton(f.edit, env)] : [], "status", pathLine("ed_saved_backup", f.edit.backup_display));
    }
    case "undone": {
      const file = basename(f.edit.file_display);
      const setting = settingOfEdit(f.edit);
      const line = f.removedDir ? words.undoneRemovedBoth(setting, { file })
        : f.removedFile ? words.undoneRemovedFile(setting, { file }) : words.undone(setting, { file });
      return strip("ok", line, [dismiss(true)], "status", pathLine("ed_undone_path", f.restored));
    }
    case "back_done": return strip("ok", backDoneLine(f), [dismiss(true)], "status", ...backDoneBelow(f));
    case "stale_undo": {
      // The offer follows the history as the page loaded it after the refusal, not the row the press was made from.
      const now = f.row ? rowNow(env, f.row.id) : null;
      if (now && now.undo_anyway === true) {
        return strip("warn", [t("ed_undo_stale_h", { file: f.file }), " ", anywayOffer(f.op)], [anywayButton(now, env), dismiss(true)], "status");
      }
      return strip("warn", staleUndoLine(f.file, f.path, f.op), [dismiss(true)], "status");
    }
    case "backup_damaged":
      return nt("err", f.restore ? t("ed_restore_backup_damaged_h") : t("ed_backup_damaged_h"), [f.path ? draw(t("ed_backup_damaged_t", { path: mark("path") }), { path: f.path }) : null], [dismiss()]);
    case "not_undoable":
      return nt("err", t("ed_not_undoable"), [], [dismiss()]);
    case "write_failed":
      // A write over a missing file can make .claude and fail after it, so the folder stays and the line says so.
      if (f.dirLeft) {
        return nt("err", f.restore ? t("ed_restore_fail_dir_h") : t("ed_undo_fail_dir_h"), [t("ed_back_fail_dir_left_t", { file: f.file })], [dismiss()]);
      }
      if (f.restore) return nt("err", t("ed_restore_fail_h"), [t("ed_restore_fail_t", { file: f.file })], [dismiss()]);
      return nt("err", t("ed_undo_fail_h"), [t("ed_undo_fail_t", { file: f.file })], [dismiss()]);
    case "config_dir_missing":
      if (f.restore) return nt("err", t("ed_restore_fail_h"), [draw(t("ed_restore_fail_config_dir_t", { config_dir: mark("config_dir") }), { config_dir: f.path })], [dismiss()]);
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
    case "back_raced": {
      // An Undo anyway or a restore keeps the bytes it wrote over, so the line names that backup. A file that was
      // absent before the write has none.
      const body = f.path ? draw(t("ed_back_raced_t", { backup: mark("backup") }), { backup: f.path })
        : f.created ? t("ed_back_raced_new_t") : t("ed_raced_new_t");
      return nt("warn", t("ed_raced_h", { file: f.file }), [body], [dismiss()]);
    }
    case "back_unverified": {
      const fsync = f.stage === "fsync";
      const heading = fsync ? t("ed_unverified_fsync_h") : t("ed_unverified_reread_h");
      if (!f.path) return nt("err", heading, [fsync ? t("ed_unverified_fsync_new_t") : t("ed_unverified_new_t")], [dismiss()]);
      const body = fsync ? draw(t("ed_unverified_fsync_t", { path: mark("path") }), { path: f.path })
        : draw(t("ed_back_unverified_t", { backup: mark("backup") }), { backup: f.path });
      return nt("err", heading, [body], [dismiss()]);
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

// The link to the list of older backups. Its focus key is its own, so a draw from new data keeps focus on it.
function olderLink(env) {
  return h("button", {
    type: "button",
    class: "s4-link",
    disabled: env.stripBusy,
    "data-edit-focus": "older",
    on: { click: env.openOlder },
  }, t("ed_older_link"));
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
  if (!env.changing && history && olderRows(history).length > 0) out.push(olderLink(env));
  return out;
}
