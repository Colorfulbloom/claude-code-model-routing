// The words of the flow that change with the setting. Effort, the effort cap, the model and the compact window each have
// their own variant of a string where the effort one would be wrong, and a setting with no variant of a key uses
// Effort's. The cap and the compact window have no "new session" in their undo and backup lines, so they use the
// neutral ones. Pure: nothing here holds state or builds a node.
//
// Every key sits in a literal t() call, one for each key, so tests/test_static_strings.py can see it has a caller.
// A table maps a setting to a function of the slots. A setting missing from a table reads Effort's entry.

import { t, withCommas } from "./format.js";
import { CAP, COMPACT, EFFORT, MODEL } from "./edit_setting.js";

const by = (table) => (setting, slots) => (table[setting] || table[EFFORT])(slots);

// ---------------------------------------------------------------- the card and the picker

export const cardTitle = by({
  [EFFORT]: () => t("ed_card"),
  [CAP]: () => t("ed_card_cap"),
  [MODEL]: () => t("ed_card_model"),
  [COMPACT]: () => t("ed_card_compact"),
});

export const groupLabel = by({
  [EFFORT]: () => t("ed_level_group_sr"),
  [CAP]: () => t("ed_level_group_sr_cap"),
});

// The line under the change in the rail: when it takes effect.
export const runsWord = by({
  [EFFORT]: () => t("ed_runs"),
  [CAP]: () => t("ed_runs_cap"),
  [COMPACT]: () => t("ed_runs_compact"),
});

// The line about what can beat the files, for a setting that has its own. Effort's stays with the list (pages/where.js), so
// this gives null for it and the list draws its own.
const beyondTable = {
  [CAP]: () => t("where_beyond_cap"),
  [MODEL]: () => t("where_beyond_model"),
  [COMPACT]: () => t("where_beyond_compact"),
};
export const whereBeyond = (setting) => (beyondTable[setting] ? beyondTable[setting]() : null);

export const whereNoLine = by({
  [EFFORT]: (s) => t("where_no_line", s),
  [CAP]: (s) => t("where_no_line_cap", s),
  [MODEL]: (s) => t("where_no_line_model", s),
  [COMPACT]: (s) => t("where_no_line_compact", s),
});

// ---------------------------------------------------------------- the rail's stops

export const stopHeading = by({
  [EFFORT]: (s) => t("ed_stop_h", s),
  [CAP]: (s) => t("ed_stop_h_cap", s),
  [MODEL]: (s) => t("ed_stop_h_model", s),
  [COMPACT]: (s) => t("ed_stop_h_compact", s),
});

export const stopWinner = by({
  [EFFORT]: (s) => t("ed_stop_winner_t", s),
  [CAP]: (s) => t("ed_stop_winner_t_cap", s),
  [MODEL]: (s) => t("ed_stop_winner_t_model", s),
  [COMPACT]: (s) => t("ed_stop_winner_t_compact", s),
});

export const nosaveLevel = by({
  [EFFORT]: (s) => t("ed_nosave_level", s),
  [CAP]: (s) => t("ed_nosave_level_cap", s),
  [MODEL]: (s) => t("ed_nosave_level_model", s),
  [COMPACT]: (s) => t("ed_nosave_level_compact", s),
});

export const nosaveProject = by({
  [EFFORT]: () => t("ed_nosave_project"),
  [CAP]: () => t("ed_nosave_project_cap"),
  [MODEL]: () => t("ed_nosave_project_model"),
  [COMPACT]: () => t("ed_nosave_project_compact"),
});

export const warnUnknown = by({
  [EFFORT]: () => t("ed_warn_unknown_t"),
  [CAP]: () => t("ed_warn_unknown_t_cap"),
  [COMPACT]: () => t("ed_warn_unknown_t_compact"),
});

// ---------------------------------------------------------------- the results in the foot

export const savedLine = by({
  [EFFORT]: (s) => t("ed_saved_t", s),
  [CAP]: (s) => t("ed_saved_t_cap", s),
  [MODEL]: (s) => t("ed_saved_t_model", s),
  [COMPACT]: (s) => t("ed_saved_t_compact", s),
});

export const savedCreated = by({
  [EFFORT]: (s) => t("ed_saved_created_t", s),
  [CAP]: (s) => t("ed_saved_created_t_cap", s),
  [MODEL]: (s) => t("ed_saved_created_t_model", s),
  [COMPACT]: (s) => t("ed_saved_created_t_compact", s),
});

export const savedNoEffect = by({
  [EFFORT]: (s) => t("ed_saved_no_effect_t", s),
  [CAP]: (s) => t("ed_saved_no_effect_t_cap", s),
  [COMPACT]: (s) => t("ed_saved_no_effect_t_compact", s),
});

export const savedPart = by({
  [EFFORT]: (s) => t("ed_saved_part_t", s),
  [CAP]: (s) => t("ed_saved_part_t_cap", s),
  [MODEL]: (s) => t("ed_saved_part_t_model", s),
  [COMPACT]: (s) => t("ed_saved_part_t_compact", s),
});

export const savedUnknown = by({
  [EFFORT]: (s) => t("ed_saved_unknown_t", s),
  [CAP]: (s) => t("ed_saved_unknown_t_cap", s),
  [COMPACT]: (s) => t("ed_saved_unknown_t_compact", s),
});

export const savedRemoved = by({
  [EFFORT]: (s) => t("ed_saved_removed_t", s),
  [CAP]: (s) => t("ed_saved_removed_t_cap", s),
  [MODEL]: (s) => t("ed_saved_removed_t_model", s),
  [COMPACT]: (s) => t("ed_saved_removed_t_compact", s),
});

export const savedRemovedNoEffect = by({
  [EFFORT]: (s) => t("ed_saved_removed_no_effect_t", s),
  [CAP]: (s) => t("ed_saved_removed_no_effect_t_cap", s),
  [COMPACT]: (s) => t("ed_saved_removed_no_effect_t_compact", s),
});

export const savedRemovedUnknown = by({
  [EFFORT]: (s) => t("ed_saved_removed_unknown_t", s),
  [CAP]: (s) => t("ed_saved_removed_unknown_t_cap", s),
  [COMPACT]: (s) => t("ed_saved_removed_unknown_t_compact", s),
});

export const lastReplaced = by({
  [EFFORT]: (s) => t("ed_last_t", s),
  [CAP]: (s) => t("ed_last_t_cap", s),
  [MODEL]: (s) => t("ed_last_t_model", s),
  [COMPACT]: (s) => t("ed_last_t_compact", s),
});

export const lastAdded = by({
  [EFFORT]: (s) => t("ed_last_added_t", s),
  [CAP]: (s) => t("ed_last_added_t_cap", s),
  [MODEL]: (s) => t("ed_last_added_t_model", s),
  [COMPACT]: (s) => t("ed_last_added_t_compact", s),
});

export const lastCreated = by({
  [EFFORT]: (s) => t("ed_last_created_t", s),
  [CAP]: (s) => t("ed_last_created_t_cap", s),
  [MODEL]: (s) => t("ed_last_created_t_model", s),
  [COMPACT]: (s) => t("ed_last_created_t_compact", s),
});

export const lastRemoved = by({
  [EFFORT]: (s) => t("ed_last_removed_t", s),
  [CAP]: (s) => t("ed_last_removed_t_cap", s),
  [MODEL]: (s) => t("ed_last_removed_t_model", s),
  [COMPACT]: (s) => t("ed_last_removed_t_compact", s),
});

export const olderRowValue = by({
  [EFFORT]: (s) => t("ed_older_row_value_t", s),
  [CAP]: (s) => t("ed_older_row_value_t_cap", s),
  [MODEL]: (s) => t("ed_older_row_value_t_model", s),
  [COMPACT]: (s) => t("ed_older_row_value_t_compact", s),
});

// Undo and the older backups. Effort and the model apply in a new session, so they keep the lines that say so. The cap
// and the compact window use the neutral ones.
export const undone = by({
  [EFFORT]: (s) => t("ed_undone_t", s),
  [CAP]: (s) => t("ed_undone_t_neutral", s),
  [COMPACT]: (s) => t("ed_undone_t_neutral", s),
});

export const undoneRemovedFile = by({
  [EFFORT]: (s) => t("ed_undone_removed_file_t", s),
  [CAP]: (s) => t("ed_undone_removed_file_t_neutral", s),
  [COMPACT]: (s) => t("ed_undone_removed_file_t_neutral", s),
});

export const undoneRemovedBoth = by({
  [EFFORT]: (s) => t("ed_undone_removed_both_t", s),
  [CAP]: (s) => t("ed_undone_removed_both_t_neutral", s),
  [COMPACT]: (s) => t("ed_undone_removed_both_t_neutral", s),
});

export const backDoneCreated = by({
  [EFFORT]: (s) => t("ed_back_done_created_t", s),
  [CAP]: (s) => t("ed_back_done_created_t_neutral", s),
  [COMPACT]: (s) => t("ed_back_done_created_t_neutral", s),
});

export const backDoneDeletedBoth = by({
  [EFFORT]: (s) => t("ed_back_done_deleted_both_t", s),
  [CAP]: (s) => t("ed_back_done_deleted_both_t_neutral", s),
  [COMPACT]: (s) => t("ed_back_done_deleted_both_t_neutral", s),
});

export const backDoneDeleted = by({
  [EFFORT]: (s) => t("ed_back_done_deleted_t", s),
  [CAP]: (s) => t("ed_back_done_deleted_t_neutral", s),
  [COMPACT]: (s) => t("ed_back_done_deleted_t_neutral", s),
});

export const backDoneRestored = by({
  [EFFORT]: (s) => t("ed_back_done_restored_t", s),
  [CAP]: (s) => t("ed_back_done_restored_t_neutral", s),
  [COMPACT]: (s) => t("ed_back_done_restored_t_neutral", s),
});

export const backDoneUndo = by({
  [EFFORT]: (s) => t("ed_back_done_undo_t", s),
  [CAP]: (s) => t("ed_back_done_undo_t_neutral", s),
  [COMPACT]: (s) => t("ed_back_done_undo_t_neutral", s),
});

// What runs after an Undo anyway or a restore.
export const backRuns = by({
  [EFFORT]: (s) => t("ed_back_runs_t", s),
  [CAP]: (s) => t("ed_back_runs_t_cap", s),
  [MODEL]: (s) => t("ed_back_runs_t_model", s),
  [COMPACT]: (s) => t("ed_back_runs_t_compact", s),
});

export const backRunsSame = by({
  [EFFORT]: () => t("ed_back_runs_same_t"),
  [CAP]: () => t("ed_back_runs_same_t_cap"),
  [COMPACT]: () => t("ed_back_runs_same_t_compact"),
});

export const backRunsUnknown = by({
  [EFFORT]: () => t("ed_back_runs_unknown_t"),
  [CAP]: () => t("ed_back_runs_unknown_t_cap"),
  [COMPACT]: () => t("ed_back_runs_unknown_t_compact"),
});

// ---------------------------------------------------------------- errors and locks

// The line for a write the server refused as a bad value: one for each setting.
export const badValue = by({
  [EFFORT]: () => t("ed_err_bad_value"),
  [CAP]: () => t("ed_err_bad_value_cap"),
  [MODEL]: () => t("ed_err_bad_value_model"),
  [COMPACT]: () => t("ed_err_bad_value_compact"),
});

// The suffix a lock line or an error line takes for a setting, when that setting has its own variant of it. The keys
// themselves are built at run time (ed_lock_, ed_row_lock_ and ed_err_ are run-time prefixes in the string checks).
export const SUFFIX = { [CAP]: "_cap", [MODEL]: "_model", [COMPACT]: "_compact" };

// A value as the page words it: the compact window's "auto" is the Auto button's word, a model in the models map
// (the settings payload's, id to display name) is its display name, and any other value is its text.
export function shown(setting, value, models = null) {
  if (value === null || value === undefined) return "";
  if (setting === MODEL && models && typeof value === "string" && Object.prototype.hasOwnProperty.call(models, value)) return String(models[value]);
  if (setting === COMPACT && value === "auto") return t("ed_compact_auto");
  if (setting === COMPACT && /^\d+$/.test(String(value))) return withCommas(String(value));
  return String(value);
}
