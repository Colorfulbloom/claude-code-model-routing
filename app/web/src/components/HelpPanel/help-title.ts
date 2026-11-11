import { en } from "@/strings/en";
import type { ChartUnit, HelpEntry } from "@/strings/help";

/**
 * The title a help spot shows. A chart's entry carries one title per unit, so the popover title
 * matches the card title ("Cost per day") when the spot passes the unit. Without a unit, or for
 * an entry with no per-unit titles, it is the entry's own title.
 */
export function helpTitle(entry: HelpEntry, unit?: ChartUnit): string {
  const key = unit === undefined ? undefined : entry.titleByUnit?.[unit];
  return key === undefined ? entry.title : en[key];
}
