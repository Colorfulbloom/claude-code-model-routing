/*
 * The run line of an agent's inspector, "40 runs in 18 sessions, $9.12, in the last 30 days", from
 * the Agents answer of /api/agents (`ran`, matched by the item's id). Review's inspector reads it
 * over the page's range, and Your setup's inspector reads it over 30 days. An agent with no row
 * did not run in the range.
 */
import type { AgentList, ReviewRange, SetupItem } from "@/api/types";
import { rangePhrase } from "@/lib/range-phrase";
import { costWords } from "@/lib/review-cards";
import { t, tn } from "@/strings/t";

/** All time with no oldest record gives an empty range phrase; drop the stray end. */
function tidy(line: string): string {
  return line.trim().replace(/,$/, "");
}

/** The usage line from an agents answer. Null while the answer loads. */
export function agentUsageLine(
  item: Pick<SetupItem, "id">,
  agents: AgentList | undefined,
  range: ReviewRange,
): string | null {
  if (agents === undefined) return null;
  const row = agents.ran.find((r) => r.item_id === item.id);
  const days = range === "7d" ? 7 : range === "30d" ? 30 : range === "90d" ? 90 : null;
  const phrase = rangePhrase(range, agents.window.oldest);
  if (row === undefined) {
    return days === null
      ? tidy(t("ag_usage_none_range", { range: phrase }))
      : t("ag_usage_none", { days });
  }
  const runs = tn("ag_runs_n", row.runs);
  const sessions = tn("ag_sessions", row.sessions);
  const cost = costWords(row.cost, row.unpriced);
  return days === null
    ? tidy(t("ag_runs_cost_range", { runs, sessions, cost, range: phrase }))
    : t("ag_runs_cost", { runs, sessions, cost, days });
}

/**
 * Whether the footer link to the Agents page in Review shows. A plugin or managed agent with no
 * runs has no review data, so the link would open a page with nothing for it. Other agents keep the
 * link, and so does any agent while the answer loads.
 */
export function showReviewLink(
  item: Pick<SetupItem, "id" | "scope">,
  agents: AgentList | undefined,
): boolean {
  if (item.scope !== "plugin" && item.scope !== "managed") return true;
  if (agents === undefined) return true;
  return agents.ran.some((r) => r.item_id === item.id);
}
