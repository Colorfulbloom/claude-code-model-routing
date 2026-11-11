/*
 * How Claude Code decides, #/reference/decides (direction C, picked on November 10). A settings list
 * leads to one page per setting, and each setting page shows the order Claude Code checks and then
 * its rules under the status each one explains. Searching shows one results pane across every
 * setting. At 720px and under the list is the page, a setting is its own page with a back link, and
 * the results show alone.
 *
 * Routes. #/reference/decides, #/reference/decides/<key> and #/reference/decides/<key>/<rule id>,
 * with ?q=, ?confidence= and ?due=1 kept in the URL by history replace. A route with a target
 * focuses it (the setting's heading, or the rule when there is one), and a plain load leaves focus
 * on the h1. A target the filters hide still shows. A stale key or rule id shows a line that says so
 * and links to the whole list.
 *
 * Search runs here, over the words on screen (matchFields), so it needs no server and behaves the
 * same on every build. The rules come once from GET /api/rules.
 */
import { useEffect, useRef } from "react";
import { Navigate, useLocation } from "react-router";
import { useRules } from "@/api/rules";
import { parseRoute } from "@/app/routes";
import { Button } from "@/components/Button/Button";
import { EmptyState } from "@/components/EmptyState/EmptyState";
import { NoticeLine } from "@/components/NoticeLine/NoticeLine";
import { PageHeader } from "@/components/PageHeader/PageHeader";
import { RaisedFinding } from "@/components/RaisedFinding/RaisedFinding";
import { useIsDesktop } from "@/lib/media";
import { t, tn } from "@/strings/t";
import { GoneCard, RuleBones } from "./ReferenceStates";
import { RulesTools, countWords } from "./RulesTools";
import { ResultsPane, SettingPage } from "./SettingPanes";
import { SettingsList, type SettingsListRow } from "./SettingsList";
import { DECIDES_PATH, decidesHref, glossaryLink, isNarrowed } from "./reference-routes";
import { confidenceCounts, filterRules, gapOf, settingKeys, type Matched } from "./rules-view";
import { useFilters } from "./useFilters";
import "./Reference.css";
import "@/components/ListInspector/ListInspector.css";

export function DecidesPage() {
  const { pathname } = useLocation();
  const parsed = parseRoute(pathname);
  if (parsed?.page !== "decides") return <Navigate to="/" replace />;
  return <DecidesView setting={parsed.setting} rule={parsed.rule} />;
}

interface ViewProps {
  setting: string | undefined;
  rule: string | undefined;
}

/** The row of a rule on the page, by id. Ids can hold hyphens only, but no selector is built. */
function ruleEl(root: HTMLElement | null, id: string): HTMLElement | undefined {
  if (root === null) return undefined;
  return Array.from(root.querySelectorAll<HTMLElement>("[data-rule-id]")).find(
    (el) => el.dataset.ruleId === id,
  );
}

function settingRow(root: HTMLElement | null, key: string): HTMLElement | undefined {
  if (root === null) return undefined;
  return Array.from(root.querySelectorAll<HTMLElement>("[data-setting-key]")).find(
    (el) => el.dataset.settingKey === key && el.closest(".ref-list") !== null,
  );
}

function DecidesView({ setting, rule }: ViewProps) {
  const card = useRules();
  const { filters, setQ, setConfidence, showAll, clear } = useFilters();
  const desktop = useIsDesktop();
  const root = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLHeadingElement | null>(null);
  const answer = card.answer;

  const all = answer?.rules ?? [];
  const keys = settingKeys(all);
  const matched = filterRules(all, filters);
  const narrowed = isNarrowed(filters);
  // The due view with every rule due shows all of them, so its count reads "84 rules", not "84 of 84".
  const allDue =
    filters.due &&
    filters.q.trim() === "" &&
    filters.confidence === "all" &&
    matched.length === all.length;
  const gap = answer === undefined ? null : gapOf(answer);
  const settingKnown = setting === undefined || keys.includes(setting);
  const ruleRow = rule === undefined ? undefined : all.find((entry) => entry.rule_id === rule);
  const ruleKnown = rule === undefined || (ruleRow !== undefined && ruleRow.key === setting);
  const matchedKeys = new Set(matched.map((entry) => entry.rule.key));
  // The setting the route names always stays in the list, even when the filters hide all its rules.
  const listKeys = keys.filter((key) => matchedKeys.has(key) || key === setting);
  const listRows: SettingsListRow[] = listKeys.map((key) => ({
    key,
    shown: matched.filter((entry) => entry.rule.key === key).length,
    total: all.filter((entry) => entry.key === key).length,
  }));
  const results = filters.q.trim() !== "" && setting === undefined;
  const current = setting ?? (desktop && !results ? (listKeys[0] ?? null) : null);
  const mode = desktop ? "split" : setting !== undefined ? "setting" : results ? "results" : "list";

  // A due view with no due rule left, with or without a Confidence word, says so and offers Show all.
  const dueLeft = filterRules(all, { ...filters, q: "" });
  const dueNone = answer !== undefined && filters.due && dueLeft.length === 0;
  const noMatch = answer !== undefined && matched.length === 0 && setting === undefined;

  // Focus follows the route's target. A plain load keeps the h1, which the route harness focuses.
  const target = `${setting ?? ""}/${rule ?? ""}`;
  const ready = answer !== undefined && settingKnown && ruleKnown;
  useEffect(() => {
    if (!ready || target === "/") return;
    queueMicrotask(() => {
      const row = rule === undefined ? undefined : ruleEl(root.current, rule);
      if (row !== undefined) row.focus();
      else headingRef.current?.focus();
    });
  }, [ready, target, rule]);

  // On a phone, Back to Settings returns focus and scroll to the setting's row (need 28).
  const lastSetting = useRef<string | null>(null);
  const listed = answer !== undefined;
  useEffect(() => {
    if (setting !== undefined) {
      lastSetting.current = setting;
      return;
    }
    if (desktop || !listed) {
      if (desktop) lastSetting.current = null;
      return;
    }
    const key = lastSetting.current;
    if (key === null) return;
    lastSetting.current = null;
    const row = settingRow(root.current, key);
    if (row === undefined) return;
    row.querySelector("a")?.focus();
    row.scrollIntoView({ block: "center" });
  }, [setting, desktop, listed]);

  const header = <PageHeader title={t("nav_decides")} sub={t("dc_sub")} />;

  if (answer === undefined) {
    return (
      <div className="ref-page" ref={root}>
        {header}
        <RulesTools
          key="tools"
          q={filters.q}
          onQ={setQ}
          confidence={filters.confidence}
          onConfidence={setConfidence}
          counts={null}
          count={null}
          loading={card.error === null}
        />
        {card.error === null ? (
          <div className="list-inspector ref-split" aria-busy="true">
            <section className="card ref-list">
              <RuleBones rows={8} />
            </section>
            {desktop && (
              <section className="card ref-setting">
                <RuleBones rows={6} />
              </section>
            )}
          </div>
        ) : (
          <section className="card ref-error">
            <RaisedFinding
              variant="error"
              title={t("dc_err_h")}
              actions={<Button onPress={card.retry}>{t("er_try")}</Button>}
            >
              <p>{t("dc_err_b")}</p>
            </RaisedFinding>
          </section>
        )}
      </div>
    );
  }

  let notice: React.ReactNode = null;
  if (gap !== null && !dueNone) {
    if (filters.due) {
      notice = (
        <NoticeLine
          statusWord={t("status_unknown")}
          link={{ label: t("dc_due_show_all"), href: decidesHref({}, { ...filters, due: false }) }}
        >
          {gap.all
            ? tn("dc_due_all", gap.due, {
                due: gap.due,
                checked_on: gap.checkedOn,
                installed: gap.installed,
              })
            : tn("dc_due_some", gap.due, { due: gap.due, installed: gap.installed })}
        </NoticeLine>
      );
    } else {
      notice = (
        <NoticeLine
          statusWord={t("status_unknown")}
          link={{
            label: tn("dc_gap_link", gap.due),
            href: decidesHref({}, { ...filters, due: true }),
          }}
        >
          {gap.all
            ? tn("dc_gap_all", gap.due, {
                installed: gap.installed,
                due: gap.due,
                checked_on: gap.checkedOn,
              })
            : tn("dc_gap_some", gap.due, { installed: gap.installed, due: gap.due })}
        </NoticeLine>
      );
    }
  }

  const tools = (
    <RulesTools
      key="tools"
      q={filters.q}
      onQ={setQ}
      confidence={filters.confidence}
      onConfidence={setConfidence}
      counts={confidenceCounts(all)}
      count={countWords(matched.length, all.length, narrowed && !allDue)}
    />
  );

  const showDue = gap !== null && gap.marks && !filters.due;
  const listHref = `#${DECIDES_PATH}`;

  // What fills the right-hand slot.
  let right: React.ReactNode = null;
  if (!settingKnown && setting !== undefined) {
    right = (
      <GoneCard
        title={t("dc_gone_setting_h", { key: setting })}
        link={{ label: t("dc_gone_link"), href: listHref }}
      />
    );
  } else if (!ruleKnown && rule !== undefined) {
    right = (
      <GoneCard
        title={t("dc_gone_rule_h", { id: rule })}
        link={{ label: t("dc_gone_link"), href: listHref }}
      />
    );
  } else if (results) {
    const groups = listKeys.map(
      (key) => [key, matched.filter((entry) => entry.rule.key === key)] as const,
    );
    right = <ResultsPane groups={groups} filters={filters} showDue={showDue} />;
  } else if (current !== null) {
    const ofSetting = all.filter((entry) => entry.key === current);
    const byId = new Map(matched.map((entry) => [entry.rule.rule_id, entry]));
    // The rule the route names stays, even when the filters would hide it.
    const shown: Matched[] = ofSetting.flatMap((entry) => {
      const found = byId.get(entry.rule_id);
      if (found !== undefined) return [found];
      return entry.rule_id === rule ? [{ rule: entry, docsOnly: false }] : [];
    });
    right = (
      <SettingPage
        setting={current}
        all={ofSetting}
        shown={shown}
        filters={filters}
        targetRule={rule}
        showDue={showDue}
        headingRef={headingRef}
        {...(mode === "setting"
          ? {
              back: {
                label: t("sp_back", { part: t("sf_settings") }),
                href: decidesHref({}, filters),
              },
            }
          : {})}
      />
    );
  }

  let body: React.ReactNode;
  if (dueNone) {
    body = (
      <EmptyState
        variant="page"
        mark="neutral"
        title={t("dc_due_none_h")}
        action={{ label: t("dc_due_show_all"), onPress: showAll }}
      >
        {t("dc_due_none_b", { installed: answer.installed ?? "" })}
      </EmptyState>
    );
  } else if (noMatch) {
    body = (
      <EmptyState
        variant="page"
        mark="neutral"
        title={t("dc_none_h", { query: filters.q.trim() === "" ? filters.confidence : filters.q })}
        action={{ label: t("sf_clear"), onPress: clear }}
        secondary={{
          label: t("dc_none_glossary"),
          href: glossaryLink(undefined, { q: filters.q }),
        }}
      >
        {t("dc_none_b")}
      </EmptyState>
    );
  } else {
    const list = (
      <SettingsList
        rows={listRows}
        settings={keys.length}
        current={results ? null : current}
        filters={filters}
        onOpen={() => undefined}
      />
    );
    body = (
      <div
        className={
          mode === "split" ? "list-inspector ref-split" : "list-inspector list-inspector-single"
        }
        data-mode={mode}
      >
        {mode === "split" && (
          <>
            {list}
            {right}
          </>
        )}
        {mode === "list" && list}
        {(mode === "setting" || mode === "results") && right}
      </div>
    );
  }

  return (
    <div className="ref-page" ref={root}>
      {header}
      {notice}
      {mode === "setting" && !dueNone ? null : tools}
      {body}
    </div>
  );
}
