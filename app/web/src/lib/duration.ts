/** Spans of time in words for the Live sub line, "30 minutes", "8 hours 2 minutes". */
import { t, tn } from "@/strings/t";

/** "less than a minute", "1 minute", "42 minutes", "1 hour", "8 hours 2 minutes". */
export function formatDuration(ms: number): string {
  const minutes = Math.floor(Math.max(0, ms) / 60_000);
  if (minutes < 1) return t("dur_under_min");
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return tn("dur_min", minutes);
  if (rest === 0) return tn("dur_hr", hours);
  return t("dur_hr_min", { hours: tn("dur_hr", hours), minutes: tn("dur_min", rest) });
}
