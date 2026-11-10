/*
 * What Session review shows at the replay line, from one timeline answer and the line's state
 * (lib/replay.ts). Pure functions: the page draws what they return, so every number and word is
 * settled here and Vitest can prove each one.
 *
 * Tiles. Before the end they show the value at the line (t_at_*) with the whole session under it
 * (t_of_*). At the end they read "Whole session so far" on a running session and "Whole session" on
 * an ended one. Tokens and cost are bucket-granular (timeline-at.ts), so on a long session the
 * tile's time is the last bucket end and the precision label says so. Run counts are exact.
 *
 * Cache share at the line. The answer carries cache reads per bucket but not the input and cache
 * write tokens the server's hit rate divides by, so the share at T is an estimate. It takes the
 * session's own mix of input and cache write among new tokens and holds it steady, which makes it
 * exact at the end. This is the one number on the page that is not read straight from the answer.
 *
 * Once an ended session's line is at the end, every run that has started reads Finished, as Live
 * does (the server keeps main idle because main is never done on its own).
 */
import type { Timeline } from "@/api/types";
import { clockShort } from "@/lib/clock";
import { formatCost, formatTokens } from "@/lib/format";
import { buildChart, frac } from "@/lib/live-chart";
import type { AxisView, ChartView } from "@/lib/live-chart";
import { modelFamily, modelLabel } from "@/lib/models";
import type { Replay } from "@/lib/replay";
import type { RunStateAt } from "@/lib/timeline-at";
import { bucketIndexAt } from "@/lib/timeline-at";
import { t, tn } from "@/strings/t";

const MINUTE_MS = 60_000;

const startOf = (timeline: Timeline): number => Date.parse(timeline.axis.start);

/** The line's clock time, in epoch ms: the axis start plus its whole minutes. */
export function lineMs(timeline: Timeline, minute: number): number {
  return startOf(timeline) + minute * MINUTE_MS;
}

/** True when the line sits at the end of a session that is still running. It follows Now there. */
export function followsNow(timeline: Timeline, replay: Replay): boolean {
  return replay.atEnd && timeline.session.running;
}

/**
 * The time the line reads. "2:25 PM", or "Now, 6:40 PM" at the end of a running session. It is the
 * visible words and the slider's `aria-valuetext`.
 */
export function lineLabel(timeline: Timeline, replay: Replay): string {
  const time = clockShort(lineMs(timeline, replay.minute));
  return followsNow(timeline, replay) ? `${t("sr_at_now")}, ${time}` : time;
}

/**
 * The time tokens and cost are as of: the end of the last bucket that counts at the line. On a
 * 1 minute bucket it is the line itself. At the end of the answer it is the line.
 */
export function heldMs(timeline: Timeline, replay: Replay): number {
  if (replay.atEnd) return lineMs(timeline, replay.minute);
  const index = bucketIndexAt(timeline, replay.at);
  return startOf(timeline) + (index + 1) * timeline.axis.bucket_seconds * 1000;
}

/** The long-session label under "Showing", or null when every number is exact at the line. */
export function precisionLabel(replay: Replay): string | null {
  return replay.precision.held ? t("sr_prec_long", { n: replay.precision.bucketMinutes }) : null;
}

/** "Page Up and Page Down move {n}". */
export function keysHint(replay: Replay): string {
  return t("sr_keys", { n: replay.step });
}

/** What the Back button is called: Back to now while running, Go to end once the session ended. */
export function toEndLabel(timeline: Timeline): string {
  return timeline.session.running ? t("sr_to_now") : t("sr_to_end");
}

const percent = (rate: number | null): number => Math.round((rate ?? 0) * 100);

/** Each started run's state at the line, with the end-of-session rule applied. */
export function effectiveStates(timeline: Timeline, replay: Replay): Map<string, RunStateAt> {
  const over = replay.atEnd && !timeline.session.running;
  return new Map(
    replay.values.runs.map((run) => [
      run.runId,
      over && run.state !== "not_started" ? "finished" : run.state,
    ]),
  );
}

export interface RunCounts {
  working: number;
  idle: number;
  finished: number;
  notStarted: number;
  total: number;
}

export function runCounts(timeline: Timeline, replay: Replay): RunCounts {
  const counts: RunCounts = { working: 0, idle: 0, finished: 0, notStarted: 0, total: 0 };
  for (const state of effectiveStates(timeline, replay).values()) {
    counts.total += 1;
    if (state === "working") counts.working += 1;
    else if (state === "idle") counts.idle += 1;
    else if (state === "finished") counts.finished += 1;
    else counts.notStarted += 1;
  }
  return counts;
}

/** The share of reads among reads, writes and input at the line. See the header for the estimate. */
export function cacheShareAt(timeline: Timeline, replay: Replay): number | null {
  const whole = timeline.totals;
  if (replay.atEnd) return whole.hit_rate;
  const here = replay.values.totals;
  const fresh = whole.tokens > 0 ? (whole.input + whole.cache_write) / whole.tokens : 0;
  const denom = here.cache_read + here.tokens * fresh;
  return denom > 0 ? here.cache_read / denom : null;
}

export type TileMode = "at" | "whole" | "sofar";

export interface ReplayTilesView {
  mode: TileMode;
  cost: { label: string; qualifier: string; value: string; delta: string; note: string | null };
  tokens: { label: string; value: string; delta: string };
  cache: { label: string; value: string; delta: string; percent: number };
  runs: {
    label: string;
    value: string;
    delta: string;
    working: number;
    finished: number;
  };
}

const money = (cost: number | null): string =>
  cost === null ? t("c_none_short") : formatCost(cost);

export function buildReplayTiles(timeline: Timeline, replay: Replay): ReplayTilesView {
  const whole = timeline.totals;
  const wholeTokens = whole.tokens + whole.cache_read;
  const wholeCache = percent(whole.hit_rate);
  const counts = runCounts(timeline, replay);
  const note = whole.unpriced.requests > 0 ? tn("t_unpriced", whole.unpriced.requests) : null;
  const qualifier = t("t_cost_kx");

  if (replay.atEnd) {
    const running = timeline.session.running;
    const mode: TileMode = running ? "sofar" : "whole";
    const sub = running ? t("t_sofar") : t("t_whole");
    return {
      mode,
      cost: { label: t("rv_t_cost"), qualifier, value: money(whole.cost), delta: sub, note },
      tokens: { label: t("t_tokens"), value: formatTokens(wholeTokens), delta: sub },
      cache: {
        label: t("t_cache"),
        value: `${String(wholeCache)}%`,
        delta: sub,
        percent: wholeCache,
      },
      runs: {
        label: t("t_runs"),
        value: String(counts.total),
        delta: running ? tn("t_of_runs_w", counts.working) : tn("t_runs_d", counts.finished),
        working: counts.working,
        finished: counts.finished,
      },
    };
  }

  const held = clockShort(heldMs(timeline, replay));
  const line = clockShort(lineMs(timeline, replay.minute));
  const here = replay.values.totals;
  const started = counts.total - counts.notStarted;
  const share = percent(cacheShareAt(timeline, replay));
  return {
    mode: "at",
    cost: {
      label: t("t_at_cost", { time: held }),
      qualifier,
      value: money(here.cost),
      delta: t("t_of_cost", { v: money(whole.cost) }),
      note,
    },
    tokens: {
      label: t("t_at_tokens", { time: held }),
      value: formatTokens(here.tokens + here.cache_read),
      delta: t("t_of_tokens", { v: formatTokens(wholeTokens) }),
    },
    cache: {
      label: t("t_at_cache", { time: held }),
      value: `${String(share)}%`,
      delta: t("t_of_cache", { v: `${String(wholeCache)}%` }),
      percent: share,
    },
    runs: {
      label: t("t_at_runs", { time: line }),
      value: String(started),
      delta:
        counts.notStarted > 0
          ? tn("t_of_runs", counts.notStarted, { w: counts.working })
          : tn("t_of_runs_w", counts.working),
      working: counts.working,
      finished: Math.max(0, started - counts.working),
    },
  };
}

/** The screen-reader line said once after the line settles: counts by run state and the cost so far. */
export function settleLine(timeline: Timeline, replay: Replay): string {
  const counts = runCounts(timeline, replay);
  const cost = replay.atEnd ? timeline.totals.cost : replay.values.totals.cost;
  return t("sr_sum", {
    time: clockShort(lineMs(timeline, replay.minute)),
    w: counts.working,
    f: counts.finished,
    s: counts.notStarted,
    cost: formatCost(cost ?? 0),
  });
}

export interface ReplayChartView extends ChartView {
  /** The line, as a fraction of the plot. */
  cut: number;
  /** Where the faded part starts: the end of the last bucket that counts at the line. */
  fade: number;
}

/** Tokens of one model family in the buckets up to and including `index`. */
function sumsUpTo(timeline: Timeline, index: number): Map<string, number> {
  const sums = new Map<string, number>();
  for (const bucket of timeline.buckets.slice(0, index + 1)) {
    for (const [id, tokens] of Object.entries(bucket.by_model)) {
      const family = modelFamily(id) ?? id;
      sums.set(family, (sums.get(family) ?? 0) + tokens);
    }
  }
  return sums;
}

/**
 * The chart for "Who worked when": the same bars as Live, with the legend totals and the text
 * alternative following the line. Bars after the line fade through the page's CSS, so the model
 * colours and the open bucket stay as the component draws them.
 */
export function buildReplayChart(
  timeline: Timeline,
  replay: Replay,
  axis: AxisView,
): ReplayChartView {
  const base = buildChart(timeline, axis);
  const index = replay.atEnd ? timeline.buckets.length - 1 : bucketIndexAt(timeline, replay.at);
  const sums = sumsUpTo(timeline, index);
  const counted = base.legend
    .map((entry) => ({ entry, tokens: sums.get(entry.model) ?? 0 }))
    .filter((item) => item.tokens > 0);
  const total = [...sums.values()].reduce((sum, tokens) => sum + tokens, 0);
  const top = counted.reduce<(typeof counted)[number] | null>(
    (best, item) => (best === null || item.tokens > best.tokens ? item : best),
    null,
  );
  const first = timeline.models[0];
  const model = top?.entry.label ?? (first === undefined ? "" : modelLabel(first.model));
  const minutes = timeline.axis.bucket_seconds / 60;
  const args = {
    start: clockShort(startOf(timeline)),
    time: clockShort(heldMs(timeline, replay)),
    total: formatTokens(total),
    model,
  };
  const summary = minutes > 1 ? t("sr_img_avg", { ...args, n: minutes }) : t("sr_img", args);
  return {
    ...base,
    legend: counted.map((item) => ({ ...item.entry, total: formatTokens(item.tokens) })),
    summary,
    cut: replay.atEnd ? 1 : frac(axis, replay.at),
    fade: replay.atEnd ? 1 : frac(axis, heldMs(timeline, replay)),
  };
}
