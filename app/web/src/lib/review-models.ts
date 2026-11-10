/*
 * What the Models page draws, from the models answer: the table rows, the kind totals under the
 * chart, one stacked row per model and the chart's image label. Pure functions, so a test can
 * check each rule without a page. Every t() call keeps a literal key (K-819f).
 */
import type { ModelList, ReviewRange, ReviewWindow } from "@/api/types";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import { formatCost, formatCostAtLeast, formatTokens } from "@/lib/format";
import { modelFamily, modelLabel } from "@/lib/models";
import { agentName, costWords, sharePercent } from "@/lib/review-cards";
import { dateLabel, timeIn, windowDates } from "@/lib/review-view";
import { t } from "@/strings/t";

/** The value of `?section=` that asks Models for its kinds card. Summary's "Made of" link sends it. */
export const KINDS_SECTION = "kinds";

export type KindId = "cache_read" | "input" | "cache_write" | "output";

/** Left to right in the legend and in each stack. The pattern number is the kind's own (kp1 to kp4). */
export const KIND_ORDER: readonly KindId[] = ["cache_read", "input", "cache_write", "output"];

export const KIND_PATTERN: Readonly<Record<KindId, 1 | 2 | 3 | 4>> = {
  cache_read: 1,
  input: 2,
  cache_write: 3,
  output: 4,
};

export function kindName(kind: KindId): string {
  switch (kind) {
    case "cache_read":
      return t("k_cache_read");
    case "input":
      return t("k_input");
    case "cache_write":
      return t("k_cache_write");
    case "output":
      return t("k_output");
  }
}

/** "76%", "<1%" under one percent. A share with no price is null, never 0. */
function percentOf(share: number | null): string | null {
  return share === null ? null : sharePercent(share);
}

export interface ModelRowView {
  id: string;
  name: string;
  family: Model | null;
  /** "$241.92", "at least $8.28", or "No price" for a model with no price. */
  cost: string;
  /** The bar's fill against the biggest cost, or null with no price. */
  fill: number | null;
  /** "76%", or null with no price. */
  percent: string | null;
  tokens: string;
  /** "79%", or null when the model has no cache reads to compare. */
  cache: string | null;
  usedBy: string[];
}

export function buildModelRows(answer: ModelList): ModelRowView[] {
  const biggest = Math.max(0, ...answer.rows.map((row) => row.cost ?? 0));
  return answer.rows.map((row) => ({
    id: row.model,
    name: modelLabel(row.model),
    family: modelFamily(row.model),
    cost: costWords(row.cost, row.unpriced),
    fill: row.cost === null ? null : biggest > 0 ? row.cost / biggest : 0,
    percent: percentOf(row.share),
    tokens: formatTokens(row.tokens),
    cache: row.cache_share === null ? null : `${String(Math.round(row.cache_share * 100))}%`,
    usedBy: row.used_by.map(agentName),
  }));
}

/** The phone's one line under the model name: "76% · 58.7M · 79% from cache". */
export function phoneLine(row: ModelRowView): string {
  const parts: string[] = [];
  if (row.percent !== null) parts.push(row.percent);
  parts.push(row.tokens);
  if (row.cache !== null) parts.push(`${row.cache} ${t("md_col_cache").toLowerCase()}`);
  return parts.join(" · ");
}

export interface KindLegendEntry {
  kind: KindId;
  pattern: 1 | 2 | 3 | 4;
  label: string;
  total: string;
}

/** The four kind totals for the whole range. A total that leaves out unpriced requests reads "at least". */
export function buildKindLegend(answer: ModelList): KindLegendEntry[] {
  const least = answer.unpriced.requests > 0;
  return KIND_ORDER.map((kind) => ({
    kind,
    pattern: KIND_PATTERN[kind],
    label: kindName(kind),
    total: least ? formatCostAtLeast(answer.legend[kind]) : formatCost(answer.legend[kind]),
  }));
}

export interface KindPart {
  kind: KindId;
  pattern: 1 | 2 | 3 | 4;
  label: string;
  amount: number;
  /** "$121.82". */
  text: string;
}

export interface KindRowView {
  id: string;
  name: string;
  family: Model | null;
  /** The model's whole cost, "$241.92" or "at least $8.28". "No price" when nothing was priced. */
  total: string;
  /** The stack's width against the biggest model, 0 to 1. Zero when nothing was priced. */
  width: number;
  /** The stack's segments, left to right in KIND_ORDER, kinds with no cost left out. */
  stack: KindPart[];
  /** The same parts, biggest first, for the line under the stack. */
  parts: KindPart[];
}

/** One row per model in the table's order. A model with no kinds entry or no priced cost has no stack. */
export function buildKindRows(answer: ModelList): KindRowView[] {
  const byModel = new Map(answer.kinds.map((entry) => [entry.model, entry]));
  const totals = answer.kinds.map((entry) => KIND_ORDER.reduce((sum, k) => sum + entry[k], 0));
  const biggest = Math.max(0, ...totals);
  return answer.rows.map((row) => {
    const entry = byModel.get(row.model);
    const stack: KindPart[] =
      entry === undefined
        ? []
        : KIND_ORDER.filter((kind) => entry[kind] > 0).map((kind) => ({
            kind,
            pattern: KIND_PATTERN[kind],
            label: kindName(kind),
            amount: entry[kind],
            text: formatCost(entry[kind]),
          }));
    const sum = stack.reduce((total, part) => total + part.amount, 0);
    return {
      id: row.model,
      name: modelLabel(row.model),
      family: modelFamily(row.model),
      total: sum > 0 ? costWords(sum, entry?.unpriced ?? row.unpriced) : t("c_none_short"),
      width: biggest > 0 ? sum / biggest : 0,
      stack,
      parts: [...stack].sort((a, b) => b.amount - a.amount),
    };
  });
}

/** The range as dates for the chart's image label: "October 1 to October 30", "Today to 6:41 PM". */
export function windowText(range: ReviewRange, w: ReviewWindow): string {
  if (range === "today") return t("ch_win_today", { time: timeIn(w.end, w.tz) });
  const { start, end, oldest } = windowDates(w);
  // A range that reaches back past the first record starts where the records do.
  const first = (range === "all" || w.partial) && oldest !== null ? oldest : start;
  const year = first.slice(0, 4) !== end.slice(0, 4);
  return t("ch_win_span", { start: dateLabel(first, year), end: dateLabel(end, year) });
}

/** The chart's accessible name. The model is the one with the most cost. */
export function kindsImageLabel(answer: ModelList, range: ReviewRange): string {
  const priced = KIND_ORDER.reduce((sum, kind) => sum + answer.legend[kind], 0);
  // With nothing priced there is no total or top model to name, so the label says so.
  if (priced <= 0) return t("md_img_none", { window: windowText(range, answer.window) });
  const total = answer.unpriced.requests > 0 ? formatCostAtLeast(priced) : formatCost(priced);
  const top = answer.rows.reduce<ModelList["rows"][number] | null>(
    (best, row) =>
      row.cost !== null && (best === null || row.cost > (best.cost ?? 0)) ? row : best,
    null,
  );
  const first = top ?? answer.rows[0];
  return t("md_img", {
    window: windowText(range, answer.window),
    total,
    model: first === undefined ? "" : modelLabel(first.model),
  });
}
