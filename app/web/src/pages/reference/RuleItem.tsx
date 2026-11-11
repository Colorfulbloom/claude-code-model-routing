import type { RuleRow } from "@/api/types";
import { Badge } from "@/components/Badge/Badge";
import { highlight } from "@/components/SearchField/match";
import { t } from "@/strings/t";
import { DocsDisclosure } from "./DocsDisclosure";
import { confidenceWord, monthDay, ruleSentence } from "./rules-view";

export interface RuleItemProps {
  rule: RuleRow;
  /** The search text. Matches in the sentence, the id, the word and the version are marked. */
  query: string;
  /** The query was found only in this rule's docs line. */
  docsOnly: boolean;
  /** The route names this rule. It gets the start bar and its docs line opens. */
  target: boolean;
  /** Draws the due mark. The page passes true only when some rules are due, never when all are. */
  showDue: boolean;
  /**
   * A rule that leads to more than one status shows under each. Only its first row carries the
   * rule's id (and, for a route, the mark and focus), so element ids stay unique. Default true.
   */
  first?: boolean;
}

const SEPARATOR = "⁣";

/** The "Checked on {version}, {date}" line, with a match in the version marked. */
function CheckedLine({ rule, query }: { rule: RuleRow; query: string }) {
  const text = t("dc_checked", { version: SEPARATOR, date: monthDay(rule.verified_on.date) });
  const [before = "", after = ""] = text.split(SEPARATOR);
  return (
    <span className="muted">
      {before}
      {highlight(rule.verified_on.claude_version, query)}
      {after}
    </span>
  );
}

/**
 * One rule: its sentence, its id in mono, the confidence word, when it was checked, the due mark
 * and the docs Disclosure. A rule with no docs line says why instead (a tested rule's source is
 * the test, an assumed rule has none). A rule reached by route is marked, and the page moves focus
 * to it, so it takes tabindex -1 and no ring of its own.
 */
export function RuleItem({ rule, query, docsOnly, target, showDue, first = true }: RuleItemProps) {
  const quoted = rule.quotes.length > 0;
  const marked = target && first;
  return (
    <li
      className={marked ? "ref-rule ref-rule-on" : "ref-rule"}
      {...(first ? { "data-rule-id": rule.rule_id } : {})}
      {...(marked ? { tabIndex: -1, "aria-current": "true" as const } : {})}
    >
      <p className="ref-rule-sentence">{highlight(ruleSentence(rule), query)}</p>
      <p className="ref-rule-meta">
        <code className="mono ref-rule-id">{highlight(rule.rule_id, query)}</code>
        <Badge>{highlight(confidenceWord(rule.confidence), query)}</Badge>
        <CheckedLine rule={rule} query={query} />
        {showDue && rule.due && (
          <span className="ref-due">
            <span aria-hidden="true">{"▲"}</span> {t("dc_due_mark")}
          </span>
        )}
      </p>
      {docsOnly && <p className="ref-rule-found muted">{t("dc_found_in_docs")}</p>}
      {quoted ? (
        <DocsDisclosure quotes={rule.quotes} query={query} autoOpen={marked || docsOnly} />
      ) : (
        <p className="ref-nodocs muted">
          {rule.confidence === "assumed" ? t("dc_nodocs_assumed") : t("dc_nodocs_tested")}
        </p>
      )}
    </li>
  );
}
