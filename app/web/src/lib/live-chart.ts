/*
 * The "Who is working" chart and its axis, from one timeline answer. The chart stays on new tokens
 * only (the Tokens tile adds cache reads, the chart does not). Past 60 seconds a bucket shows its
 * per-minute average, and the label says so. While the session runs the last bucket is open: it is
 * drawn at the share of its length that has passed, and it ends at Now.
 */
import type { Timeline } from "@/api/types";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import type { StackedBar, StackedBarsProps } from "@/components/StackedBars/StackedBars";
import { formatTokens } from "@/lib/format";
import { modelFamily, modelLabel } from "@/lib/models";
import { t } from "@/strings/t";

/** Stack order, bottom first. */
export const BAR_MODELS: Model[] = ["opus", "sonnet", "haiku", "fable"];

export interface AxisView {
  startMs: number;
  /** The right edge. Now while the session runs, capped at the end of the open bucket. */
  endMs: number;
  bucketMs: number;
  running: boolean;
  /** Share of the open bucket that has passed, 0 to 1. Null once the session has ended. */
  openFrac: number | null;
}

const ms = (text: string): number => Date.parse(text);

export function axisFor(timeline: Timeline, nowMs: number): AxisView {
  const startMs = ms(timeline.axis.start);
  const bucketMs = timeline.axis.bucket_seconds * 1000;
  const count = Math.max(1, timeline.buckets.length);
  const running = timeline.session.running;
  const answerEnd = ms(timeline.axis.end);
  if (!running) return { startMs, endMs: answerEnd, bucketMs, running, openFrac: null };
  const lastStart = startMs + (count - 1) * bucketMs;
  const endMs = Math.min(Math.max(answerEnd, nowMs), lastStart + bucketMs);
  return { startMs, endMs, bucketMs, running, openFrac: (endMs - lastStart) / bucketMs };
}

/** A time as a fraction of the axis, held to 0 and 1. */
export function frac(axis: AxisView, atMs: number): number {
  const span = axis.endMs - axis.startMs;
  if (span <= 0) return 0;
  return Math.min(1, Math.max(0, (atMs - axis.startMs) / span));
}

/** One step from a start that gives at most two ticks, 1, 2 or 5 times a power of ten. */
export function niceTicks(max: number): number[] {
  if (max <= 0) return [];
  const raw = max / 2;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
  return [step, step * 2];
}

/** Label spacing in seconds, from every 5 minutes up to a day. The server uses the same steps. */
const TICK_STEPS = [300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
/** Clock labels at most, not counting Now. */
const MAX_CLOCK_TICKS = 6;
/** The share of the axis at its right edge that carries no clock label. */
const EDGE_SHARE = 0.04;

/**
 * Clock-aligned label times from the start up to the right edge, less its last 4%. The right edge
 * carries Now (or nothing), so the smallest step that fits six labels there wins: 5 minutes on a
 * half hour. Returns the server's ticks when no step fits.
 */
export function clockTicks(
  startMs: number,
  endMs: number,
  bucketSeconds: number,
  fallback: string[],
): number[] {
  for (const step of TICK_STEPS) {
    if (step < bucketSeconds) continue;
    const stepMs = step * 1000;
    const marks: number[] = [];
    // A mark in the last 4% of the axis would sit on top of Now, so it never counts.
    const limit = endMs - (endMs - startMs) * EDGE_SHARE;
    for (let at = Math.ceil(startMs / stepMs) * stepMs; at < limit; at += stepMs) marks.push(at);
    if (marks.length <= MAX_CLOCK_TICKS) return marks;
  }
  return fallback.map(ms);
}

const hourMinute = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });

/** "6:15" while a bucket is under 10 minutes wide, else "9 AM", "10", "12 PM". */
export function tickLabel(atMs: number, bucketSeconds: number, first: boolean): string {
  const at = new Date(atMs);
  if (bucketSeconds < 600) {
    return hourMinute
      .formatToParts(at)
      .filter(
        (part) =>
          part.type !== "dayPeriod" && !(part.type === "literal" && part.value.trim() === ""),
      )
      .map((part) => part.value)
      .join("");
  }
  const hour = at.getHours();
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return first || hour === 12 || hour === 0
    ? `${String(twelve)} ${hour < 12 ? "AM" : "PM"}`
    : String(twelve);
}

export interface ChartView {
  bars: StackedBar[];
  models: Model[];
  yTicks: StackedBarsProps["yTicks"];
  xLabels: StackedBarsProps["xLabels"];
  legend: StackedBarsProps["legend"];
  axisLabel: string;
  summary: string;
}

export function buildChart(timeline: Timeline, axis: AxisView): ChartView {
  const minutes = timeline.axis.bucket_seconds / 60;
  const averaged = minutes > 1;
  const lastIndex = timeline.buckets.length - 1;
  const bars: StackedBar[] = timeline.buckets.map((bucket, index) => {
    const open = axis.openFrac !== null && index === lastIndex;
    // An open bucket has only run for part of its length, so its average divides by that part.
    const span = open && axis.openFrac !== null ? Math.max(axis.openFrac, 0.01) * minutes : minutes;
    const byModel: Partial<Record<Model, number>> = {};
    for (const [id, tokens] of Object.entries(bucket.by_model)) {
      const family = modelFamily(id);
      if (family !== null) byModel[family] = (byModel[family] ?? 0) + tokens / span;
    }
    return {
      key: bucket.start,
      byModel,
      ...(open ? { open: true, openFrac: Math.max(axis.openFrac ?? 1, 0.01) } : {}),
    };
  });
  const peak = Math.max(
    0,
    ...bars.map((bar) => BAR_MODELS.reduce((sum, model) => sum + (bar.byModel[model] ?? 0), 0)),
  );
  // Two ticks, a step and twice the step, as the board draws them.
  const yTicks = niceTicks(peak).map((value) => ({ value, label: formatTokens(value) }));
  const xLabels = clockTicks(
    axis.startMs,
    axis.endMs,
    timeline.axis.bucket_seconds,
    timeline.axis.ticks,
  )
    .map((at, index) => ({
      frac: (at - axis.startMs) / Math.max(1, axis.endMs - axis.startMs),
      label: tickLabel(at, timeline.axis.bucket_seconds, index === 0),
    }))
    .filter((entry) => entry.frac >= 0 && entry.frac < 1);
  if (axis.running) xLabels.push({ frac: 1, label: t("tl_now") });

  const totals = new Map<Model, { tokens: number; ids: string[] }>();
  for (const entry of timeline.models) {
    const family = modelFamily(entry.model);
    if (family === null) continue;
    const found = totals.get(family) ?? { tokens: 0, ids: [] };
    found.tokens += entry.tokens;
    found.ids.push(entry.model);
    totals.set(family, found);
  }
  const legend: StackedBarsProps["legend"] = [];
  const order: Model[] = [];
  for (const entry of timeline.models) {
    const family = modelFamily(entry.model);
    if (family !== null && !order.includes(family)) order.push(family);
  }
  for (const family of order) {
    const found = totals.get(family);
    if (found === undefined) continue;
    const [only] = found.ids;
    legend.push({
      model: family,
      label:
        found.ids.length === 1 && only !== undefined
          ? modelLabel(only)
          : `${family.charAt(0).toUpperCase()}${family.slice(1)}`,
      total: formatTokens(found.tokens),
    });
  }
  const axisLabel = averaged ? t("tl_axis_avg", { n: minutes }) : t("tl_axis_lab");
  return { bars, models: BAR_MODELS, yTicks, xLabels, legend, axisLabel, summary: axisLabel };
}
