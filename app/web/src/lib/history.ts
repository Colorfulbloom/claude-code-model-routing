/*
 * The words for the history facts, shared by the sidebar footer, the updates-stopped notice and
 * the More page card. Every function is pure and takes "now", so a test fixes the day.
 */
import type { AppInfo, BackupFailure, PricesAnswer } from "@/api/types";
import { clockStamp, dateWords, dayLong } from "@/lib/clock";
import { t, tn } from "@/strings/t";

export interface FooterLine {
  id: string;
  text: string;
  /** A ▲ line in the overridden colour. */
  warn?: boolean;
}

/** "Prices as of October 28", or the source word first when the prices are not from LiteLLM. */
export function pricesText(prices: PricesAnswer): string {
  const d = dateWords(prices.as_of);
  switch (prices.source) {
    case "bundled":
      return t("ft_prices_bundled", { d });
    case "last_good":
      return t("ft_prices_saved", { d });
    case "model_pricing":
      return t("ft_prices_custom");
    case "litellm":
      return t("ft_prices", { d });
  }
}

/** The value beside "Prices as of" on More. */
export function pricesValue(prices: PricesAnswer): string {
  const d = dateWords(prices.as_of);
  switch (prices.source) {
    case "bundled":
      return t("more_prices_bundled", { d });
    case "last_good":
      return t("more_prices_saved", { d });
    case "model_pricing":
      return t("more_prices_custom");
    case "litellm":
      return d;
  }
}

/**
 * The footer lines, top to bottom. At rest there are five. Unreadable files add one line on top,
 * and a failed backup takes the place of the backup line, so there are six at most.
 */
export function footerLines(
  app: AppInfo,
  prices: PricesAnswer | undefined,
  now: number | string | Date,
): FooterLine[] {
  const { history } = app;
  const lines: FooterLine[] = [];
  if (history.unreadable_files > 0) {
    lines.push({
      id: "unreadable",
      text: tn("ft_unreadable", history.unreadable_files),
      warn: true,
    });
  }
  if (app.as_of !== null) {
    lines.push({ id: "updated", text: t("ft_updated", { t: clockStamp(app.as_of, now) }) });
  }
  if (history.oldest !== null) {
    lines.push({ id: "since", text: t("ft_since", { d: dayLong(history.oldest) }) });
  }
  if (history.backup_failed !== null) {
    lines.push({
      id: "backup",
      text: t("ft_backup_failed", { t: clockStamp(history.backup_failed.at, now) }),
      warn: true,
    });
  } else if (history.last_backup !== null) {
    lines.push({ id: "backup", text: t("ft_backup", { t: clockStamp(history.last_backup, now) }) });
  }
  if (prices !== undefined) lines.push({ id: "prices", text: pricesText(prices) });
  lines.push({ id: "claude", text: t("more_ver_cc", { version: app.claude_version }) });
  return lines;
}

/** The reason sentence under a failed backup, with the newest good copy when there is one. */
export function backupReason(failure: BackupFailure, lastBackup: string | null): string {
  const why = (() => {
    switch (failure.reason_code) {
      case "no_space":
        return t("mb_backup_no_space");
      case "unwritable":
        return t("mb_backup_unwritable");
      case "check_failed":
        return t("mb_backup_check_failed");
      case "copy_failed":
        return t("mb_backup_copy_failed");
    }
  })();
  return lastBackup === null ? why : `${why} ${t("mb_backup_newest", { d: dayLong(lastBackup) })}`;
}
