/*
 * The Changes page as words (M6a task a11). The server sends history rows with codes and masked
 * values, and this module groups them by day and builds the sentences: what changed, the undo state
 * and the recheck outcome. Every key is a literal t() call, so the static key test sees it (K-819f).
 * The page needs no other fact about a row.
 */
import type { HistoryRow, NotUndoableReason, RecheckState, UndoState } from "@/api/edit";
import { clockShort, dayLong } from "@/lib/clock";
import { asField, fieldLabel } from "@/lib/edit-page";
import { t } from "@/strings/t";

export interface DayGroup {
  /** Stable for one calendar day, such as "2026-11-11". */
  key: string;
  /** "Today", "Yesterday", or the date such as "November 9". */
  label: string;
  rows: HistoryRow[];
}

function dayKey(at: Date): string {
  return `${String(at.getFullYear())}-${String(at.getMonth() + 1)}-${String(at.getDate())}`;
}

/** The rows grouped by local calendar day, in the order the server sent them (newest first). */
export function groupByDay(rows: readonly HistoryRow[], now: number | string | Date): DayGroup[] {
  const today = new Date(now);
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  const groups: DayGroup[] = [];
  for (const row of rows) {
    const when = new Date(row.time);
    const key = dayKey(when);
    let group = groups.find((g) => g.key === key);
    if (group === undefined) {
      const label =
        key === dayKey(today)
          ? t("cg_today")
          : key === dayKey(yesterday)
            ? t("cg_yesterday")
            : dayLong(when);
      group = { key, label, rows: [] };
      groups.push(group);
    }
    group.rows.push(row);
  }
  return groups;
}

/** The field as the list names it. A name the page has no label for stays as the file spells it. */
export function rowFieldLabel(field: string): string {
  const known = asField(field);
  return known === null ? field : fieldLabel(known);
}

/** What the row names: "Effort", "Model for builder" or "New agent planner". */
function subjectText(row: HistoryRow): string {
  if (row.subject.kind === "agent") {
    const name = row.subject.name ?? "";
    if (row.op === "create") return t("cg_subj_new_agent", { name });
    return t("cg_subj_agent", { field: rowFieldLabel(row.field), agent: name });
  }
  return t("cg_subj_field", { field: rowFieldLabel(row.field) });
}

function valueText(value: string | number | null): string {
  return value === null ? t("sc_none") : String(value);
}

/** The Change column: the subject and the values, "Effort, xhigh to medium". */
export function changeText(row: HistoryRow): string {
  const subject = subjectText(row);
  let change: string;
  if (row.op === "create" && row.subject.kind === "agent") change = subject;
  else if (row.op === "create") change = t("cg_change_created", { subject, to: valueText(row.to) });
  else if (row.from === null) change = t("cg_change_added", { subject, to: valueText(row.to) });
  else change = t("cg_change", { subject, from: valueText(row.from), to: valueText(row.to) });
  if (row.op === "undo") return t("cg_op_undo", { change });
  if (row.op === "restore") return t("cg_op_restore", { change });
  return change;
}

/** True when the row has an Undo button: the file can go back, or the page asks first. */
export function hasUndo(state: UndoState): boolean {
  return state === "can_undo" || state === "changed_since" || state === "deletes_file";
}

function notUndoableText(reason: NotUndoableReason | null): string {
  switch (reason) {
    case "not_newest":
      return t("cg_nu_not_newest");
    case "undo_row":
      return t("cg_nu_undo_row");
    case "backup_pruned":
      return t("cg_nu_backup_pruned");
    case "backup_damaged":
      return t("cg_nu_backup_damaged");
    case "restore_row":
    case "file_refused":
    case null:
      return t("cg_not_undoable");
  }
}

/**
 * The line under (or beside) the Undo button, by the row's undo state. A row that can simply be
 * undone says nothing, because its Undo button already says so.
 */
export function undoStateText(row: HistoryRow): string | null {
  switch (row.undo_state) {
    case "can_undo":
      return null;
    case "changed_since":
      return t("cg_changed_since");
    case "deletes_file":
      return t("cg_deletes_file");
    case "undone":
      return t("cg_undone_at", { time: clockShort(row.undone_at ?? row.time) });
    case "not_undoable":
      return notUndoableText(row.not_undoable_reason);
  }
}

/** The recheck outcome's word, "Checking the file", "Checked" or "Changed by another program". */
export function recheckWord(state: RecheckState): string {
  switch (state) {
    case "checking":
      return t("cg_rc_checking");
    case "confirmed":
      return t("cg_rc_confirmed");
    case "overwritten":
      return t("cg_rc_overwritten");
  }
}

/**
 * The glyph before a recheck word. Never the only signal, because the word follows. The page draws
 * the hollow circle of "checking" as a CSS ring (`ring-mark`), because the text glyph renders far
 * smaller than the check and the triangle.
 */
export const RECHECK_GLYPH: Record<RecheckState, string> = {
  checking: "◌",
  confirmed: "✓",
  overwritten: "▲",
};
