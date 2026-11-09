/* Clock times for the shell and the gate pages, in the reader's locale. */
const medium = new Intl.DateTimeFormat("en-US", { timeStyle: "medium" });
const short = new Intl.DateTimeFormat("en-US", { timeStyle: "short" });

/** "6:39:52 PM", for the quiet Updated line. */
export function clockMedium(at: number | string | Date): string {
  return medium.format(new Date(at));
}

/** "3:42 PM", for last-answer and retry lines. */
export function clockShort(at: number | string | Date): string {
  return short.format(new Date(at));
}

const dayOnly = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric" });

/** "September 3", for History since. */
export function dayLong(at: number | string | Date): string {
  return dayOnly.format(new Date(at));
}

/** "October 28" from a calendar date such as "2026-10-28". It is read as a local date, so no zone moves it. */
export function dateWords(isoDate: string): string {
  const [y, m, d] = isoDate.split("-").map(Number);
  if (y === undefined || m === undefined || d === undefined) return isoDate;
  return dayOnly.format(new Date(y, m - 1, d));
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/**
 * A clock time in minutes. Today it is time only, "11:58 PM". On another day it carries the date,
 * "November 7, 11:58 PM", so an old time never reads as a recent one.
 */
export function clockStamp(at: number | string | Date, now: number | string | Date): string {
  const when = new Date(at);
  if (sameDay(when, new Date(now))) return short.format(when);
  return `${dayOnly.format(when)}, ${short.format(when)}`;
}
