/*
 * The More page (phone only). The history card first, then the reference links and the version
 * lines. At 721px and up the Shell redirects #/more to the current project's Live, so this page
 * never shows on a desktop.
 */
import { useAppInfo, usePrices } from "@/api/client";
import type { EditsMode } from "@/api/edit";
import type { AppInfo, PricesAnswer } from "@/api/types";
import { useActiveProject } from "@/app/active-project";
import { HelpTerm } from "@/components/HelpTerm/HelpTerm";
import { HistoryCard } from "@/components/HistoryCard/HistoryCard";
import type { HistoryFinding, HistoryRow } from "@/components/HistoryCard/HistoryCard";
import { MoreCard } from "@/components/MoreCard/MoreCard";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { clockStamp, dayLong } from "@/lib/clock";
import { backupReason, claudeVersionText, editingValue, pricesValue } from "@/lib/history";
import { VERSION } from "@/lib/version";
import { t, tn } from "@/strings/t";
import "./MorePage.css";

/** The card's findings and rows from the history facts. Quiet facts stay out, as in the footer. */
export function historyCardParts(
  app: AppInfo,
  prices: PricesAnswer | undefined,
  now: number | string | Date,
  edits?: EditsMode,
): { findings: HistoryFinding[]; rows: HistoryRow[] } {
  const { history } = app;
  const findings: HistoryFinding[] = [];
  if (history.backup_failed !== null) {
    findings.push({
      id: "backup",
      title: t("ft_backup_failed", { t: clockStamp(history.backup_failed.at, now) }),
      body: backupReason(history.backup_failed, history.last_backup),
    });
  }
  if (history.unreadable_files > 0) {
    findings.push({
      id: "unreadable",
      title: tn("ft_unreadable", history.unreadable_files),
      body: t("mb_unread_b"),
    });
  }
  const rows: HistoryRow[] = [];
  if (app.as_of !== null) {
    rows.push({ id: "updated", label: t("more_l_updated"), value: clockStamp(app.as_of, now) });
  }
  if (history.oldest !== null) {
    rows.push({ id: "since", label: t("more_l_since"), value: dayLong(history.oldest) });
  }
  if (history.backup_failed !== null) {
    rows.push({
      id: "backup",
      label: t("more_l_backup"),
      value: t("ft_backup_failed", { t: clockStamp(history.backup_failed.at, now) }),
      warn: true,
    });
  } else if (history.last_backup !== null) {
    rows.push({
      id: "backup",
      label: t("more_l_backup"),
      value: clockStamp(history.last_backup, now),
    });
  }
  if (prices !== undefined) {
    rows.push({ id: "prices", label: t("more_l_prices"), value: pricesValue(prices) });
  }
  if (edits !== undefined) {
    rows.push({ id: "editing", label: t("more_l_editing"), value: editingValue(edits) });
  }
  return { findings, rows };
}

/** The Prices, Last backup and Editing labels open their help entries. Every other label stays plain. */
function withHelp(row: HistoryRow): HistoryRow {
  if (row.id === "prices") {
    return { ...row, label: <HelpTerm help="shell.prices">{row.label}</HelpTerm> };
  }
  if (row.id === "backup") {
    return { ...row, label: <HelpTerm help="shell.backup">{row.label}</HelpTerm> };
  }
  if (row.id === "editing") {
    return { ...row, label: <HelpTerm help="shell.editing">{row.label}</HelpTerm> };
  }
  return row;
}

export function MorePage() {
  const project = useActiveProject(null);
  const app = useAppInfo(project);
  const prices = usePrices();
  const parts =
    app.data === undefined
      ? null
      : historyCardParts(app.data, prices.data, app.data.server_time, app.data.edits.state);
  const card = parts === null ? null : { ...parts, rows: parts.rows.map(withHelp) };
  return (
    <>
      <PageHeader title={t("more_h1")} />
      <div className="grid">
        {card !== null && (
          <HistoryCard title={t("more_hist_h")} findings={card.findings} rows={card.rows} />
        )}
        <MoreCard
          title={t("nav_ref_h")}
          rows={[
            {
              id: "decides",
              href: "#/reference/decides",
              label: t("nav_decides"),
              icon: "decides",
            },
            {
              id: "glossary",
              href: "#/reference/glossary",
              label: t("nav_glossary"),
              icon: "glossary",
            },
          ]}
        />
        <section className="more-version" aria-labelledby="more-version-title">
          <h2 className="more-version-title" id="more-version-title">
            {t("more_ver_h")}
          </h2>
          {app.data !== undefined && <p>{claudeVersionText(app.data.claude_version)}</p>}
          <p>{t("more_ver_app", { version: VERSION })}</p>
        </section>
      </div>
    </>
  );
}
