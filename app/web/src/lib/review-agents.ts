/*
 * What the Agents table draws, from the agents answer: one view per row with its source line, its
 * Set to and Ran with cells, its Check status and its cost. Pure functions, so a test can check
 * each cell rule without a page. Every t() call keeps a literal key (K-819f).
 */
import type { AgentList } from "@/api/types";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import type { SettingStatus } from "@/components/StatusChip/StatusChip";
import { modelFamily, modelLabel } from "@/lib/models";
import { agentName, costWords } from "@/lib/review-cards";
import { t, tn } from "@/strings/t";

type AgentRow = AgentList["ran"][number];
type NoRuns = AgentList["never_ran"][number];
type SetPair = AgentRow["set"];

/** "Fable 5.1 · xhigh", a model alone, an effort alone, or null when the pair has neither. */
function pairWords(
  model: string | null | undefined,
  effort: string | null | undefined,
): string | null {
  const parts = [model == null ? null : modelLabel(model), effort ?? null].filter(
    (part): part is string => part !== null,
  );
  return parts.length === 0 ? null : parts.join(" · ");
}

export type SetWhy = "sets_nothing" | "no_file" | "read_failed";

/** The Set to cell. `text` is what a set pair reads. `why` is the reason there is none. */
export interface SetCell {
  text: string | null;
  why: SetWhy | null;
}

/**
 * A pair that sets a model or an effort reads as words. A null pair reads by its reason, and a
 * null pair with no reason is treated as sets nothing, so the cell never shows the text "None".
 */
export function setCell(set: SetPair, reason: AgentRow["set_reason"]): SetCell {
  const text = set === null ? null : pairWords(set.model?.value, set.effort?.value);
  if (text !== null) return { text, why: null };
  return { text: null, why: reason ?? "sets_nothing" };
}

/** The words for a Set to cell with no pair. Each reason has its own key. */
export function setWhyWords(why: SetWhy): string {
  switch (why) {
    case "sets_nothing":
      return t("ag_nothing");
    case "no_file":
      return t("ag_src_none");
    case "read_failed":
      return t("ag_set_failed");
  }
}

export interface RanCell {
  model: Model | null;
  /** "Sonnet 5.5 · xhigh", or null when the runs name neither a model nor an effort. */
  text: string | null;
  /** One line per other pair the runs used, "Also Sonnet 5.5 · high on 4 runs". */
  also: string[];
}

/** The Ran with cell: the most common pair, and a line for each other pair. */
export function ranCell(row: AgentRow): RanCell {
  const text = pairWords(row.ran.model, row.ran.effort);
  const also = row.ran_pairs
    .filter((pair) => pair.model !== row.ran.model || pair.effort !== row.ran.effort)
    .flatMap((pair) => {
      const setup = pairWords(pair.model, pair.effort);
      return setup === null ? [] : [tn("ag_also", pair.runs, { setup })];
    });
  return { model: modelFamily(row.ran.model), text, also };
}

export interface SourceLine {
  text: string;
  /** The sentence that explains the source, for a row whose source Bar Tab could not find. */
  description: string | null;
}

/** The muted line under the agent's name. */
export function sourceLine(scope: AgentRow["scope"] | NoRuns["scope"]): SourceLine {
  switch (scope) {
    case "user":
      return { text: t("ag_src_user"), description: null };
    case "project":
      return { text: t("ag_src_project"), description: null };
    case "main":
      return { text: t("ag_main_src"), description: null };
    case "unnamed":
      return { text: t("ag_src_unnamed"), description: null };
    case "no_file":
      return { text: t("ag_src_unknown"), description: t("ag_src_unknown_aria") };
  }
}

/**
 * The Check cell. A status the server sent stands. With none, a row whose setup could not be read
 * has no verdict, and every other row sets nothing, so it shows Default.
 */
export function checkStatus(row: AgentRow): SettingStatus | null {
  if (row.status !== null) return row.status;
  return row.set_reason === "read_failed" ? null : "default";
}

export interface AgentRowView {
  key: string;
  name: string;
  source: SourceLine;
  set: SetCell;
  ran: RanCell;
  check: SettingStatus | null;
  runs: number;
  cost: string;
  /** The model whose colour fills the cost bar. */
  model: Model | null;
  /** The bar's fill against the biggest cost, or null with no price. */
  fill: number | null;
}

export interface NoRunsView {
  key: string;
  name: string;
  source: SourceLine;
  set: SetCell;
}

export interface AgentsView {
  rows: AgentRowView[];
  neverRan: NoRunsView[];
}

/**
 * The Runs cell. The server counts a subagent's runs and gives the Main session none, because it
 * is not a run of its own. The board counts the Main session once for each session, as the model
 * check does, so a Main session row reads its session count.
 */
export function runsOf(row: AgentRow): number {
  return row.scope === "main" ? row.sessions : row.runs;
}

export function buildAgents(answer: AgentList): AgentsView {
  const biggest = Math.max(0, ...answer.ran.map((row) => row.cost ?? 0));
  return {
    rows: answer.ran.map((row) => ({
      key: row.agent,
      name: agentName(row.agent),
      source: sourceLine(row.scope),
      set: setCell(row.set, row.set_reason),
      ran: ranCell(row),
      check: checkStatus(row),
      runs: runsOf(row),
      cost: costWords(row.cost, row.unpriced),
      model: modelFamily(row.ran.model),
      fill: row.cost === null ? null : biggest > 0 ? row.cost / biggest : 0,
    })),
    neverRan: answer.never_ran.map((row) => ({
      key: row.agent,
      name: row.agent,
      source: sourceLine(row.scope),
      set: setCell(row.set, row.set_reason),
    })),
  };
}
