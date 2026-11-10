/*
 * A range as a phrase that finishes a sentence: "in the last 30 days", "today", "since September 3".
 * Session review fills `{range}` in its back link and its Session Select heading with it. `oldest`
 * is the first stored request, which only "All time" names. Without it the phrase is empty, so the
 * sentence stops at "Sessions".
 */
import type { ReviewRange } from "@/api/types";
import { dayLong } from "@/lib/clock";
import { t } from "@/strings/t";

export function rangePhrase(range: ReviewRange, oldest: string | null): string {
  switch (range) {
    case "today":
      return t("rg_p_today");
    case "7d":
      return t("rg_p_days", { n: 7 });
    case "30d":
      return t("rg_p_days", { n: 30 });
    case "90d":
      return t("rg_p_days", { n: 90 });
    case "12m":
      return t("rg_p_12m");
    case "all":
      return oldest === null ? "" : t("rg_p_all", { date: dayLong(oldest) });
  }
}

/** "Sessions in the last 30 days", without a trailing space when the phrase is empty. */
export function backLabel(range: ReviewRange, oldest: string | null): string {
  return t("sr_back", { range: rangePhrase(range, oldest) }).trim();
}

/** The Session Select's heading, "Sessions in the last 30 days". */
export function selectHeading(range: ReviewRange, oldest: string | null): string {
  return t("sel_h", { range: rangePhrase(range, oldest) }).trim();
}
