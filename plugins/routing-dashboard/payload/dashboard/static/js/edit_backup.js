// The pure builders of the older backups list and of the Undo anyway and Restore review (rail), with their foot. The
// list names every history row an Undo or Undo anyway doesn't already reach. A row opens a preview of the restore, and
// nothing is written until the owner confirms. Nothing here holds state or imports it. What the flow knows comes in as
// arguments, and the presses go out through the handlers the caller passes ({ startBack, closeBack, confirmBack }).
//
// Rules this file keeps, the same as edit_foot.js.
// - Every word comes from strings.json through t(). Nothing here holds copy. The marks are glyphs.
// - Every value, path and diff line comes from the server, so it goes in as text through h.js. No markup is
//   parsed anywhere in this file, and tests/test_edit_card_js.py fails on the calls that would parse it.

import { h } from "./h.js";
import { t, fmtTime } from "./format.js";
import { basename, button, draw, mark, nt } from "./edit_ui.js";
import { diffFigure, gitIgnoreNote } from "./edit_review.js";
import { settingOf, settingOfEdit } from "./edit_setting.js";
import * as words from "./edit_words.js";

const has = (value) => value !== null && value !== undefined;

// The rows the list offers are chosen by olderRows in edit_pick.js, a file with no imports, because the flow needs the
// same rule and may not import this file (it would close an import cycle through the card).
export { olderRows } from "./edit_pick.js";

// The line of a row, worded for the setting the row changed (the last part of its key path), whatever cell is open.
function rowLine(row) {
  const file = basename(row.file_display);
  const when = fmtTime(row.time);
  if (row.before_absent === true) return t("ed_older_row_absent_t", { file, when });
  if (has(row.old_value) && row.old_value !== "") {
    const setting = settingOfEdit(row);
    return words.olderRowValue(setting, { file, when, value: words.shown(setting, row.old_value) });
  }
  return t("ed_older_row_t", { file, when });
}

// Why a row can't be restored. One literal t() call for each state.
function reasonLine(state) {
  switch (state) {
    case "same_as_file": return t("ed_older_same");
    case "backup_unparsed": return t("ed_older_unparsed");
    case "backup_damaged": return t("ed_older_damaged");
    case "backup_pruned": return t("ed_older_pruned");
    default: return t("ed_older_file_refused");
  }
}

// The list in the rail. A row that can be restored is a button. Any other is a grey line with its reason.
export function olderRail(rows, env) {
  return h("div", { class: "s4-rb" },
    h("h2", { class: "s4-rh" }, t("ed_older_h")),
    h("p", { class: "s4-sub" }, t("ed_older_intro")),
    h("ul", { class: "s4-bk" }, rows.map((row) => {
      const line = rowLine(row);
      if (row.restore_state === null || row.restore_state === undefined) {
        return h("li", null, h("button", {
          type: "button",
          class: "s4-bkrow",
          "data-edit-focus": "backup:" + row.id,
          on: { click: () => env.startBack("restore", row, "list") },
        }, line));
      }
      return h("li", { class: "s4-bkrow is-off" }, line, h("p", { class: "s4-note" }, reasonLine(row.restore_state)));
    })));
}

// The file name a review speaks of: the preview's, else the row's.
const fileOf = (back) => basename(back.pv && back.pv.file_display ? back.pv.file_display : back.row.file_display);

// One literal t() call for each result, so the string checks can see every key.
function mainLine(pv, file) {
  if (pv.no_change === true) return t("ed_back_no_change_t", { file });
  switch (pv.result) {
    case "delete": return t("ed_back_delete_t", { file });
    case "create": return t("ed_back_create_t", { file });
    default: return t("ed_back_replace_t", { file });
  }
}

// What runs after this, from the preview's two values, worded for the setting the preview carries.
function runsLine(pv) {
  const setting = settingOf(pv);
  if (!has(pv.runs_after)) return words.backRunsUnknown(setting);
  if (pv.runs_after === pv.runs_before) return words.backRunsSame(setting);
  return words.backRuns(setting, { level: words.shown(setting, pv.runs_after) });
}

// True when the preview has a diff and it holds no lines: the file and the backup differ only in line endings, the final
// newline or a value the dashboard hides. An unparsed file has no diff at all, so it is not this case.
const emptyDiff = (pv) => pv.no_change !== true && !!pv.diff && Array.isArray(pv.diff.hunks) && pv.diff.hunks.length === 0;

// The id of the review's heading, which names the rail.
const BACK_HEAD = "s4-back-h";

// The review in the rail: what the click does, the diff when there is one, and the notes about the file.
export function backRail(back, env) {
  const file = fileOf(back);
  const pv = back.pv;
  const head = [
    back.stale === true ? nt("warn", t("ed_back_stale_h", { file }), [t("ed_back_stale_t")]) : null,
    h("h2", { class: "s4-rh", id: BACK_HEAD }, back.kind === "undo" ? t("ed_back_h_undo") : t("ed_back_h_restore")),
  ];
  // The rail scrolls, so it takes focus by keyboard in every browser and is named by its heading.
  const rail = { class: "s4-rb", tabindex: "0", "aria-labelledby": BACK_HEAD };
  if (!pv) return h("div", rail, head);
  const hunks = pv.diff && Array.isArray(pv.diff.hunks) && pv.diff.hunks.length > 0;
  return h("div", rail,
    head,
    h("p", { class: "s4-sub" }, mainLine(pv, file)),
    emptyDiff(pv) ? h("p", { class: "s4-note" }, t("ed_back_no_diff_t")) : null,
    pv.removes_dir === true ? h("p", { class: "s4-note" }, t("ed_back_delete_dir_t")) : null,
    pv.file_unparsed === true ? h("p", { class: "s4-note" }, t("ed_back_unparsed_t", { file })) : null,
    hunks ? diffFigure(pv.diff, { layer: pv.layer }) : null,
    pv.no_change === true || emptyDiff(pv) ? null : h("p", { class: "s4-runs" }, runsLine(pv)),
    pv.shared === true && pv.no_change !== true ? h("p", { class: "s4-note" }, t("ed_shared")) : null,
    pv.creates_dir === true ? h("p", { class: "s4-note" }, t("ed_back_create_dir_t", { file })) : null,
    pv.result === "delete" ? null : gitIgnoreNote(pv.git_ignore, file), // a file that goes can't be committed by mistake
    pv.backup_display ? h("p", { class: "s4-hint" }, draw(t("ed_back_source", { path: mark("path") }), { path: pv.backup_display })) : null);
}

// One literal t() call for each label of the confirm button.
function goLabel(back, file) {
  if (back.pv.result === "delete") return t("ed_back_go_delete", { file });
  return back.kind === "undo" ? t("ed_back_go_undo") : t("ed_back_go_restore");
}

// The foot. The list has Close. A review that is loading or has nothing to do has Cancel alone. Any other has the
// confirm and Cancel, side by side, and Working with both off while the write is on its way. A status line for a screen
// reader says what a loaded preview holds, or Working. With every row of the list grey, focus is on Close, so the status
// line says what the list is for.
export function backFoot(back, env) {
  const say = (line) => h("span", { class: "sr", role: "status" }, line);
  if (back.view === "list") {
    const rows = Array.isArray(env.rows) ? env.rows : [];
    const allGrey = rows.length > 0 && rows.every((row) => has(row.restore_state));
    return [button(t("ed_older_close"), { wide: true, focus: "older-close", onClick: env.closeBack }),
      allGrey ? say(t("ed_older_intro")) : null];
  }
  const pv = back.pv;
  const cancelOnly = !pv || pv.no_change === true;
  const busy = back.busy === true && !cancelOnly;
  const cancel = button(t("ed_cancel"), { wide: true, focus: "cancel", disabled: busy, onClick: env.closeBack });
  const file = fileOf(back);
  const loaded = pv ? say([mainLine(pv, file), emptyDiff(pv) ? " " : null, emptyDiff(pv) ? t("ed_back_no_diff_t") : null,
    pv.no_change === true || emptyDiff(pv) ? null : " ", pv.no_change === true || emptyDiff(pv) ? null : runsLine(pv)]) : null;
  if (cancelOnly) return [cancel, loaded];
  const confirm = button(busy ? t("ed_back_busy") : goLabel(back, file), {
    primary: back.kind === "restore" && pv.result !== "delete",
    wide: true, focus: "save", disabled: busy, busy, onClick: env.confirmBack,
  });
  return [confirm, cancel, busy ? say(t("ed_back_busy_sr", { file })) : loaded];
}
