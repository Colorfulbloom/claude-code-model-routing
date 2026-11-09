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
