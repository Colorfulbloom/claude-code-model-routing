/*
 * The four tiles and the Latest requests rows, from one timeline answer. On screen "Tokens" means
 * new tokens plus cache reads, which is what the old page and the board show. The chart stays on
 * new tokens only. Costs are API list-price estimates and sum the priced requests only.
 */
import type { Timeline } from "@/api/types";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import { formatCost, formatTokens } from "@/lib/format";
import { modelFamily, modelLabel } from "@/lib/models";
import { runLabel } from "@/lib/run-label";
import { t, tn } from "@/strings/t";

export interface TilesView {
  cost: {
    label: string;
    qualifier: string;
    value: string;
    delta: string;
    note: string | null;
    /** One value per bucket. Null is a bucket with no price. */
    spark: (number | null)[];
  };
  tokens: { value: string; delta: string };
  cache: { value: string; delta: string; percent: number };
  agents: { label: string; value: string; delta: string; working: number; finished: number };
}

const percent = (rate: number | null): number => Math.round((rate ?? 0) * 100);

export function buildTiles(timeline: Timeline): TilesView {
  const { totals, last_minute: minute } = timeline;
  const ended = timeline.session.state === "ended";
  const whole = t("t_ended_d");
  const spent = totals.cost === null ? t("c_none_short") : formatCost(totals.cost);
  const agentsAllFinished = totals.runs_finished === totals.runs;
  return {
    cost: {
      label: ended ? t("t_cost_ended") : t("t_cost"),
      qualifier: t("t_cost_kx"),
      value: spent,
      delta:
        ended || minute === null ? whole : t("t_cost_d", { cost: formatCost(minute.cost ?? 0) }),
      note: totals.unpriced.requests > 0 ? tn("t_unpriced", totals.unpriced.requests) : null,
      spark: timeline.buckets.map((bucket) => bucket.cost),
    },
    tokens: {
      value: formatTokens(totals.tokens + totals.cache_read),
      delta:
        ended || minute === null
          ? whole
          : t("t_tokens_d", { tokens: formatTokens(minute.tokens + minute.cache_read) }),
    },
    cache: {
      value: `${String(percent(totals.hit_rate))}%`,
      delta:
        ended || minute === null
          ? whole
          : t("t_cache_d", { pct: `${String(percent(minute.hit_rate))}%` }),
      percent: percent(totals.hit_rate),
    },
    agents: ended
      ? {
          label: t("t_agents_ended"),
          value: String(totals.runs),
          delta: agentsAllFinished
            ? t("t_agents_ended_d")
            : t("t_agents_d", { finished: totals.runs_finished, runs: totals.runs }),
          working: 0,
          finished: totals.runs_finished,
        }
      : {
          label: t("t_agents"),
          value: String(totals.runs_working),
          delta: t("t_agents_d", { finished: totals.runs_finished, runs: totals.runs }),
          working: totals.runs_working,
          finished: totals.runs_finished,
        },
  };
}

export interface RequestRow {
  id: string;
  time: string;
  agent: string;
  model: Model | null;
  modelLabel: string;
  tokens: string;
  cost: string;
}

/** The newest five of the eight the server sends. */
export const REQUEST_ROWS = 5;

const seconds = new Intl.DateTimeFormat("en-US", {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
});

/** "6:39:50", the clock time with seconds and no AM or PM. */
export function requestTime(atMs: number): string {
  return seconds
    .formatToParts(new Date(atMs))
    .filter(
      (part) => part.type !== "dayPeriod" && !(part.type === "literal" && part.value.trim() === ""),
    )
    .map((part) => part.value)
    .join("");
}

export function buildRequests(timeline: Timeline): RequestRow[] {
  const byId = new Map(timeline.runs.map((run) => [run.run_id, run]));
  return timeline.requests.slice(0, REQUEST_ROWS).map((request) => {
    const run = byId.get(request.run_id);
    const label = request.model === null ? "" : modelLabel(request.model);
    return {
      id: request.id,
      time: requestTime(Date.parse(request.at)),
      agent: run === undefined ? t("tl_main") : runLabel(run),
      model: modelFamily(request.model),
      modelLabel: request.effort === null ? label : `${label} · ${request.effort}`,
      tokens: formatTokens(request.tokens),
      cost: request.cost === null ? t("c_none_short") : formatCost(request.cost),
    };
  });
}
