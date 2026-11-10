/*
 * The options of Session review's Session Select. They come from the first page of the Sessions
 * list (50 rows) and always include the session on screen, so the value is never missing when a
 * link opens an older session. Newest first, grouped by local day with Today and Yesterday named.
 */
import { dayBefore, localDate } from "@/api/review";
import { clockShort, dateWords } from "@/lib/clock";
import { t } from "@/strings/t";

export interface ChoiceSource {
  id: string;
  started: string;
  branch: string | null;
  state: "working" | "idle" | "ended";
}

export interface SessionChoice extends ChoiceSource {
  /** "Today", "Yesterday" or "October 29". */
  group: string;
  /** "6:10 PM". */
  time: string;
}

/** The group word for a session's start, in the server's zone. */
export function dayGroup(started: string, tz: string, nowMs: number): string {
  const day = localDate(started, tz);
  const today = localDate(nowMs, tz);
  if (day === today) return t("ss_today");
  if (day === dayBefore(today)) return t("ss_yday");
  return dateWords(day);
}

/** How many sessions the Select lists before "See all {n} sessions". */
export const CHOICE_LIMIT = 5;

/**
 * The first `limit` choices, newest first. The open session always stays: when it is older than
 * the first few, it takes the last place and the newest ones fill the rest.
 */
export function limitChoices(
  choices: readonly SessionChoice[],
  currentId: string,
  limit: number = CHOICE_LIMIT,
): SessionChoice[] {
  const head = choices.slice(0, limit);
  if (head.some((choice) => choice.id === currentId)) return head;
  const current = choices.find((choice) => choice.id === currentId);
  return current === undefined ? head : [...head.slice(0, limit - 1), current];
}

/**
 * Rows and the open session, newest first. The open session takes its own state, which is fresher
 * than the list's, and is added when the list has no row for it.
 */
export function sessionChoices(
  rows: readonly ChoiceSource[],
  current: ChoiceSource | null,
  tz: string,
  nowMs: number,
): SessionChoice[] {
  const byId = new Map<string, ChoiceSource>(rows.map((row) => [row.id, row]));
  if (current !== null) byId.set(current.id, current);
  return [...byId.values()]
    .sort((a, b) => Date.parse(b.started) - Date.parse(a.started))
    .map((row) => ({
      ...row,
      group: dayGroup(row.started, tz, nowMs),
      time: clockShort(row.started),
    }));
}

/** The closed button's value, "Today, 6:10 PM" or "October 29, 2:00 PM". */
export function choiceValue(choice: SessionChoice): string {
  return t("sel_value", { day: choice.group, time: choice.time });
}
