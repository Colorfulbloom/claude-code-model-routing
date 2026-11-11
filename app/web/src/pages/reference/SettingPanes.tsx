import { useId } from "react";
import { Link } from "react-aria-components";
import type { RuleRow } from "@/api/types";
import { highlight } from "@/components/SearchField/match";
import { OrderLadder } from "@/components/OrderLadder/OrderLadder";
import { StatusChip } from "@/components/StatusChip/StatusChip";
import { Well } from "@/components/Well/Well";
import { t, tn } from "@/strings/t";
import { RuleItem } from "./RuleItem";
import { decidesHref } from "./reference-routes";
import {
  joinAnd,
  ladderLayers,
  scopeWords,
  settingName,
  slotGroups,
  statusQuestion,
  statusWord,
  type Filters,
  type Matched,
  type RuleRowSlot,
  type RuleStatus,
} from "./rules-view";
import "@/components/Card/Card.css";
import "@/components/ListInspector/ListInspector.css";

interface RuleGroupsProps {
  rules: readonly Matched[];
  groups: readonly (readonly [RuleStatus, readonly RuleRowSlot[]])[];
  query: string;
  /** The rule the route names. Its first row is marked and opens its docs. */
  targetRule: string | undefined;
  showDue: boolean;
}

/**
 * The rules of a setting under each status they lead to, Invalid first, each group with the count
 * of its own rows. A rule that leads to two statuses shows in both, and only its first row has an id.
 */
function RuleGroups({ rules, groups, query, targetRule, showDue }: RuleGroupsProps) {
  const docsOnly = new Map(rules.map((entry) => [entry.rule.rule_id, entry.docsOnly]));
  return (
    <>
      {groups.map(([status, inGroup]) => (
        <div key={status} className="ref-os" data-status={status}>
          <h3 className="ref-os-h">
            <StatusChip status={status}>{statusWord(status)}</StatusChip>
            <span className="ref-osq">{statusQuestion(status)}</span>
            <span className="num muted ref-os-n">{inGroup.length}</span>
          </h3>
          <Well variant="list">
            <ul className="ref-rules">
              {inGroup.map(({ rule, first }) => (
                <RuleItem
                  key={rule.rule_id}
                  rule={rule}
                  query={query}
                  docsOnly={docsOnly.get(rule.rule_id) ?? false}
                  target={rule.rule_id === targetRule}
                  showDue={showDue}
                  first={first}
                />
              ))}
            </ul>
          </Well>
        </div>
      ))}
    </>
  );
}

export interface SettingPageProps {
  setting: string;
  /** Every rule of the setting. The page reads its name, its scopes and its order from them. */
  all: readonly RuleRow[];
  /** The rules to show, after the filters. The rule the route names is always among them. */
  shown: readonly Matched[];
  filters: Filters;
  targetRule: string | undefined;
  showDue: boolean;
  /** The phone page only. A link back to the list. */
  back?: { label: string; href: string };
  headingRef: React.RefObject<HTMLHeadingElement | null>;
}

/**
 * One setting's page: its name and key, how many rules it has and what they apply to, the order
 * Claude Code checks, then its rules under the status each explains. On a phone it is its own page
 * with a back link to the list.
 */
export function SettingPage({
  setting,
  all,
  shown,
  filters,
  targetRule,
  showDue,
  back,
  headingRef,
}: SettingPageProps) {
  const headingId = useId();
  const orderId = useId();
  const scopes = joinAnd(scopeWords(all));
  const layers = ladderLayers(all);
  const { groups, repeats } = slotGroups(shown.map((entry) => entry.rule));
  return (
    <section className="card inspector ref-setting" aria-labelledby={headingId}>
      {back !== undefined && (
        <Link className="inspector-back" href={back.href}>
          <span aria-hidden="true">{"←"}</span> {back.label}
        </Link>
      )}
      <header className="inspector-head">
        <h2 className="inspector-title" id={headingId} ref={headingRef} tabIndex={-1}>
          {highlight(settingName(setting), filters.q)}
        </h2>
        <code className="mono ref-key">{highlight(setting, filters.q)}</code>
      </header>
      <div className="inspector-body">
        <p className="muted ref-sub">{tn("dc_set_sub", shown.length, { scopes })}</p>
        {layers.length > 0 && (
          <div className="ref-order">
            <h3 className="inspector-h3" id={orderId}>
              {t("dc_order_h")}
            </h3>
            <OrderLadder layers={layers} labelledBy={orderId} />
          </div>
        )}
        {repeats > 0 && <p className="muted ref-repeat-note">{t("dc_results_note")}</p>}
        {shown.length === 0 ? (
          <p className="muted ref-none-line">{t("dc_count_ann_none")}</p>
        ) : (
          <RuleGroups
            rules={shown}
            groups={groups}
            query={filters.q}
            targetRule={targetRule}
            showDue={showDue}
          />
        )}
      </div>
    </section>
  );
}

export interface ResultsPaneProps {
  /** The settings with a match, in list order. */
  groups: readonly (readonly [string, readonly Matched[]])[];
  filters: Filters;
  showDue: boolean;
}

/** "{n} rules in {g} settings", with the right singular forms. */
export function resultsLine(n: number, g: number): string {
  if (n === 1 && g === 1) return t("dc_results_one", { n, g });
  if (g === 1) return t("dc_results_other_one_setting", { n, g });
  return t("dc_results_other", { n, g });
}

/**
 * Search results across every setting, grouped by setting, in one pane. Each group names its
 * setting as a link to that setting's page, then lists the matching rules under the status each one
 * explains. On a phone the results are the whole page.
 */
export function ResultsPane({ groups, filters, showDue }: ResultsPaneProps) {
  const headingId = useId();
  const total = groups.reduce((sum, [, inGroup]) => sum + inGroup.length, 0);
  return (
    <section className="card inspector ref-setting ref-results" aria-labelledby={headingId}>
      <header className="inspector-head">
        <h2 className="inspector-title" id={headingId} tabIndex={-1}>
          {resultsLine(total, groups.length)}
        </h2>
      </header>
      <div className="inspector-body">
        {groups.map(([key, inGroup]) => (
          <div key={key} className="ref-os ref-result-group" data-setting-key={key}>
            <h3 className="ref-os-h">
              <Link className="ref-os-link" href={decidesHref({ setting: key }, filters)}>
                {highlight(settingName(key), filters.q)}
              </Link>
              <code className="mono ref-key">{highlight(key, filters.q)}</code>
              <span className="num muted ref-os-n">{inGroup.length}</span>
            </h3>
            <Well variant="list">
              <ul className="ref-rules">
                {inGroup.map((entry) => (
                  <RuleItem
                    key={entry.rule.rule_id}
                    rule={entry.rule}
                    query={filters.q}
                    docsOnly={entry.docsOnly}
                    target={false}
                    showDue={showDue}
                  />
                ))}
              </ul>
            </Well>
          </div>
        ))}
      </div>
    </section>
  );
}
