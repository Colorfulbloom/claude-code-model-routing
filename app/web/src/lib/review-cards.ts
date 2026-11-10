/*
 * What the Summary and Sessions cards draw, from the answers: the cost chart (bars, legend, labels,
 * pager window and image label), Where the money went, and the session rows. Pure functions.
 * Every t() call keeps a literal key (K-819f).
 */
import { localDate } from "@/api/review";
import type {
  ChartWindow,
  CostChart,
  ReviewRange,
  ReviewSession,
  SessionDay,
  Summary,
  Unpriced,
} from "@/api/types";
import type { Model } from "@/components/ModelSwatch/ModelSwatch";
import type { StackedBar, StackedBarsProps } from "@/components/StackedBars/StackedBars";
import { formatCost, formatCostAtLeast, formatTokens } from "@/lib/format";
import { BAR_MODELS } from "@/lib/live-chart";
import { modelFamily, modelLabel } from "@/lib/models";
import {
  addDays,
  dateLabel,
  daysBetween,
  monthLabel,
  oldestLabel,
  timeIn,
} from "@/lib/review-view";
import { t, tn } from "@/strings/t";

type ChartBar = CostChart["bars"][number];

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;

/** The chart's unit before its answer arrives, from the range. */
export function rangeUnit(range: ReviewRange): ChartWindow["unit"] {
  switch (range) {
    case "today":
      return "hour";
    case "7d":
    case "30d":
      return "day";
    case "90d":
    case "all":
      return "week";
    case "12m":
      return "month";
  }
}

/** The card heading for a unit. */
export function chartHeading(unit: ChartWindow["unit"]): string {
  switch (unit) {
    case "hour":
      return t("ch_h_hour");
    case "day":
      return t("ch_h_day");
    case "week":
      return t("ch_h_week");
    case "month":
      return t("ch_h_month");
  }
}

const shortDate = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  timeZone: "UTC",
});
const shortMonth = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });
const shortMonthYear = new Intl.DateTimeFormat("en-US", {
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});
const atNoon = (date: string): Date => new Date(`${date}T12:00:00Z`);

function hourLabel(at: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    hour12: true,
    timeZone: tz,
  }).format(new Date(at));
  return parts.replace(/\s/g, " ");
}

/** The x label of a bar: "12 AM", "Oct 1", "Aug 2", "Nov 2025" or "Feb". */
function barLabel(
  bar: Pick<ChartBar, "start">,
  unit: ChartWindow["unit"],
  tz: string,
  first: boolean,
): string {
  if (unit === "hour") return hourLabel(bar.start, tz);
  const date = localDate(bar.start, tz);
  if (unit === "month") {
    return first || date.slice(5, 7) === "01"
      ? shortMonthYear.format(atNoon(date))
      : shortMonth.format(atNoon(date));
  }
  return shortDate.format(atNoon(date));
}

/** Labels under some of the bars, the first and last always. The chart drops any that touch. */
function xLabelsFor(
  bars: readonly Pick<ChartBar, "start">[],
  unit: ChartWindow["unit"],
  tz: string,
): StackedBarsProps["xLabels"] {
  const count = bars.length;
  if (count === 0) return [];
  // A day of hours reads 12 AM, 6 AM, 12 PM, 6 PM and the last hour, as the board draws it.
  const step = unit === "hour" ? 6 : Math.max(1, Math.ceil(count / 6));
  const labels: StackedBarsProps["xLabels"] = [];
  bars.forEach((bar, index) => {
    const last = index === count - 1;
    if (index % step !== 0 && !last) return;
    labels.push({
      frac: index === 0 ? 0 : last ? 1 : (index + 0.5) / count,
      label: barLabel(bar, unit, tz, index === 0),
    });
  });
  return labels;
}

/** How long a whole bucket of a unit runs, in ms, for the bar that starts at `start`. */
function fullLength(unit: ChartWindow["unit"], start: string, tz: string): number {
  if (unit === "hour") return HOUR_MS;
  if (unit === "day") return DAY_MS;
  if (unit === "week") return 7 * DAY_MS;
  const date = localDate(start, tz);
  const year = Number(date.slice(0, 4));
  const month = Number(date.slice(5, 7));
  return new Date(Date.UTC(year, month, 0)).getUTCDate() * DAY_MS;
}

const isPriced = (cost: number | null): cost is number => cost !== null;

/** One bar of the picture. Costs per model family, a part with no price as a stub. */
function stackedBar(
  bar: ChartBar,
  unit: ChartWindow["unit"],
  tz: string,
  oldest: string | null,
): StackedBar {
  const byModel: Partial<Record<Model, number | null>> = {};
  const noPrice = new Set<Model>();
  for (const [id, part] of Object.entries(bar.by_model)) {
    const family = modelFamily(id);
    if (family === null) continue;
    if (isPriced(part.cost)) byModel[family] = (byModel[family] ?? 0) + part.cost;
    else if (part.requests > 0) noPrice.add(family);
  }
  for (const family of noPrice) {
    const priced = byModel[family];
    if (priced === undefined || priced === 0) byModel[family] = null;
  }
  const length = Date.parse(bar.end) - Date.parse(bar.start);
  const full = fullLength(unit, bar.start, tz);
  // A bar clipped to the window start or to the records start is a part of its bucket.
  const partial = !bar.open && (bar.holds_oldest || full - length > HOUR_MS);
  return {
    key: bar.start,
    byModel,
    ...(bar.open ? { open: true, openFrac: Math.min(1, Math.max(0.01, length / full)) } : {}),
    ...(partial ? { partial: true } : {}),
    ...(bar.no_records && oldest !== null ? { noRecords: t("ch_norec", { date: oldest }) } : {}),
  };
}

export interface LegendEntry {
  model: Model;
  label: string;
  total: string;
}

/** Costs per family, in the answer's catalog order. A family with two versions reads by family. */
function legendFor(chart: CostChart): { entries: LegendEntry[]; top: string | null } {
  const order: Model[] = [];
  const groups = new Map<
    Model,
    { ids: string[]; cost: number | null; priced: boolean; unpriced: number }
  >();
  for (const entry of chart.legend) {
    const family = modelFamily(entry.model);
    if (family === null) continue;
    let group = groups.get(family);
    if (group === undefined) {
      group = { ids: [], cost: 0, priced: false, unpriced: 0 };
      groups.set(family, group);
      order.push(family);
    }
    group.ids.push(entry.model);
    group.unpriced += entry.unpriced.requests;
    if (entry.cost !== null) {
      group.cost = (group.cost ?? 0) + entry.cost;
      group.priced = true;
    }
  }
  let top: { label: string; cost: number } | null = null;
  const entries: LegendEntry[] = [];
  for (const family of order) {
    const group = groups.get(family);
    if (group === undefined) continue;
    const [only] = group.ids;
    const label =
      group.ids.length === 1 && only !== undefined
        ? modelLabel(only)
        : `${family.charAt(0).toUpperCase()}${family.slice(1)}`;
    const cost = group.priced ? (group.cost ?? 0) : null;
    const total =
      cost === null
        ? t("c_none_short")
        : group.unpriced > 0
          ? t("ch_legend_least", { v: formatCost(cost) })
          : formatCost(cost);
    entries.push({ model: family, label, total });
    if (cost !== null && (top === null || cost > top.cost)) top = { label, cost };
  }
  // The legend reads in the order the bars stack, bottom first, as the board draws it.
  entries.sort((a, b) => BAR_MODELS.indexOf(a.model) - BAR_MODELS.indexOf(b.model));
  return { entries, top: top === null ? null : top.label };
}

/** "October 1 to October 30", "October 29", "Today to 6:41 PM" or "November 2025 to October 2026". */
export function chartWindowLabel(chart: ChartWindow, tz: string): string {
  if (chart.unit === "hour" && chart.newest) {
    return t("ch_win_today", { time: timeIn(chart.end, tz) });
  }
  const start = localDate(chart.start, tz);
  const end = localDate(new Date(Date.parse(chart.end) - 1).toISOString(), tz);
  return spanLabel(start, end, chart.unit);
}

function spanLabel(start: string, end: string, unit: ChartWindow["unit"]): string {
  if (unit === "month") {
    return t("ch_win_span", { start: monthLabel(start), end: monthLabel(end) });
  }
  if (start === end) return t("ch_win_day", { date: dateLabel(start, false) });
  const year = start.slice(0, 4) !== end.slice(0, 4);
  return t("ch_win_span", { start: dateLabel(start, year), end: dateLabel(end, year) });
}

/** The window one page earlier (same length), for the Earlier button's name. */
export function earlierWindowLabel(chart: ChartWindow, tz: string): string {
  const start = localDate(chart.start, tz);
  const end = localDate(new Date(Date.parse(chart.end) - 1).toISOString(), tz);
  const length = daysBetween(start, end);
  return spanLabel(addDays(start, -length), addDays(start, -1), chart.unit);
}

/** The window one page later, held to the newest date, for the Later button's name. */
export function laterWindowLabel(chart: ChartWindow, tz: string, newestEnd: string): string {
  const start = localDate(chart.start, tz);
  const end = localDate(new Date(Date.parse(chart.end) - 1).toISOString(), tz);
  const length = daysBetween(start, end);
  const next = addDays(end, 1);
  const last = addDays(end, length);
  return spanLabel(next, last > newestEnd ? newestEnd : last, chart.unit);
}

export interface KindEntry {
  kind: "input" | "output" | "cache_read" | "cache_write";
  label: string;
  total: string;
}

/** The "Made of" totals, biggest first. A total with unpriced requests behind it reads "at least". */
function kindsFor(chart: CostChart): KindEntry[] {
  const least = chart.unpriced.requests > 0;
  const words = (value: number): string => (least ? formatCostAtLeast(value) : formatCost(value));
  const entries: { kind: KindEntry["kind"]; label: string; value: number }[] = [
    { kind: "input", label: t("k_input"), value: chart.kinds.input },
    { kind: "output", label: t("k_output"), value: chart.kinds.output },
    { kind: "cache_read", label: t("k_cache_read"), value: chart.kinds.cache_read },
    { kind: "cache_write", label: t("k_cache_write"), value: chart.kinds.cache_write },
  ];
  return entries
    .sort((a, b) => b.value - a.value)
    .map((entry) => ({ kind: entry.kind, label: entry.label, total: words(entry.value) }));
}

/** A y tick as dollars: "$20", "$2.50". */
function tickText(value: number): string {
  return Number.isInteger(value) ? `$${value.toLocaleString("en-US")}` : formatCost(value);
}

export interface CostChartView {
  unit: ChartWindow["unit"];
  heading: string;
  bars: StackedBar[];
  models: Model[];
  yTicks: StackedBarsProps["yTicks"];
  xLabels: StackedBarsProps["xLabels"];
  /** The marker word for the open hour ("Now"), on today's chart only. */
  nowLabel?: string;
  legend: LegendEntry[];
  kinds: KindEntry[];
  /** The pager's window as words. */
  window: string;
  /** The chart image's accessible name. */
  summary: string;
  /** One line per model that has requests with no price. */
  unpricedLines: string[];
  hasCost: boolean;
}

/**
 * The hours of today after the open one, as empty slots. The answer ends at now, but the board
 * draws the whole day from 12 AM to 11 PM with the later hours empty. The slots carry no cost, so
 * the legend and the Cost tile still agree. An earlier day is whole already, so it gets none.
 */
function futureHours(chart: CostChart): { start: string }[] {
  const { chart: win, bars } = chart;
  const open = bars.at(-1);
  if (win.unit !== "hour" || !win.newest || open === undefined) return [];
  const day = localDate(win.start, chart.window.tz);
  const slots: { start: string }[] = [];
  for (let at = Date.parse(open.start) + HOUR_MS; slots.length < 24; at += HOUR_MS) {
    const start = new Date(at).toISOString();
    if (localDate(start, chart.window.tz) !== day) break;
    slots.push({ start });
  }
  return slots;
}

export function buildCostChart(chart: CostChart): CostChartView {
  const { window: w } = chart;
  const unit = chart.chart.unit;
  const oldest = oldestLabel(w);
  const future = futureHours(chart);
  const bars = [
    ...chart.bars.map((bar) => stackedBar(bar, unit, w.tz, oldest)),
    ...future.map((slot): StackedBar => ({ key: slot.start, byModel: {}, future: true })),
  ];
  const { entries, top } = legendFor(chart);
  const window = chartWindowLabel(chart.chart, w.tz);
  const priced = chart.legend.reduce((sum, entry) => sum + (entry.cost ?? 0), 0);
  const hasCost = priced > 0;
  const total = chart.unpriced.requests > 0 ? formatCostAtLeast(priced) : formatCost(priced);
  let summary: string;
  if (!hasCost || top === null) {
    summary = t("ch_img_none", { window });
  } else if (unit === "hour") {
    summary = t("ch_img_hour", { window, total, model: top });
  } else if (unit === "day") {
    summary = t("ch_img_day", { window, total, model: top });
  } else if (unit === "week") {
    summary = t("ch_img_week", { window, total, model: top });
  } else {
    summary = t("ch_img_month", { window, total, model: top });
  }
  const unpricedLines = chart.legend
    .filter((entry) => entry.unpriced.requests > 0)
    .map((entry) => tn("ch_unpriced", entry.unpriced.requests, { model: modelLabel(entry.model) }));
  return {
    unit,
    heading: chartHeading(unit),
    bars,
    models: BAR_MODELS,
    yTicks: chart.y_ticks.map((value) => ({ value, label: tickText(value) })),
    xLabels: xLabelsFor([...chart.bars, ...future], unit, w.tz),
    ...(unit === "hour" && chart.chart.newest ? { nowLabel: t("ch_now") } : {}),
    legend: entries,
    kinds: kindsFor(chart),
    window,
    summary,
    unpricedLines,
    hasCost,
  };
}

/** "@main" reads Main session, "@unnamed" Unnamed agent, any other key is the agent type. */
export function agentName(key: string): string {
  if (key === "@main") return t("tl_main");
  if (key === "@unnamed") return t("ag_unnamed");
  return key;
}

/** A cost as words: "$8.28", "at least $8.28" when requests have no price, "No price" with none. */
export function costWords(cost: number | null, unpriced: Unpriced): string {
  if (cost === null) return t("c_none_short");
  return unpriced.requests > 0 ? formatCostAtLeast(cost) : formatCost(cost);
}

/** "75%", "<1%" under one percent. */
export function sharePercent(share: number): string {
  return share < 0.01 ? "<1%" : `${String(Math.round(share * 100))}%`;
}

export interface MoneyRow {
  id: string;
  name: string;
  model: Model | null;
  modelName: string | null;
  value: string;
  /** The bar's fill against the biggest row, or null with no cost. */
  fill: number | null;
  percent: string | undefined;
}

/** Where the money went: one row per agent, the bar scaled to the biggest. */
export function buildMoney(summary: Summary): MoneyRow[] {
  const biggest = Math.max(0, ...summary.money.map((row) => row.share ?? 0));
  return summary.money.map((row) => ({
    id: row.agent,
    name: agentName(row.agent),
    model: modelFamily(row.model),
    modelName: row.model === null ? null : modelLabel(row.model),
    value: costWords(row.cost, row.unpriced),
    fill: row.share === null ? null : biggest > 0 ? row.share / biggest : 0,
    percent: row.share === null ? undefined : sharePercent(row.share),
  }));
}

export interface SessionRowView {
  id: string;
  /** The time, or the date and time for a session that began on another day. */
  when: string;
  branch: string;
  branchMuted: boolean;
  state: ReviewSession["state"];
  agents: string[];
  runs: number;
  tokens: string;
  cost: string;
  /** The cost bar's fill against the biggest cost on the list. */
  fill: number;
  startedEarlier: boolean;
}

export interface SessionGroup {
  key: string;
  /** "Today", "Yesterday" or the date. Empty for the ungrouped Summary list. */
  label: string;
  rows: SessionRowView[];
}

function rowView(
  session: ReviewSession,
  tz: string,
  today: string,
  biggest: number,
  withDate: boolean,
): SessionRowView {
  const date = localDate(session.started, tz);
  const time = timeIn(session.started, tz);
  const year = date.slice(0, 4) !== today.slice(0, 4);
  return {
    id: session.id,
    when: withDate && date !== today ? `${dateLabel(date, year)}, ${time}` : time,
    branch: session.branch ?? t("lv_no_branch"),
    branchMuted: session.branch === null,
    state: session.state,
    agents: session.agents.map(agentName),
    runs: session.runs,
    tokens: formatTokens(session.tokens),
    cost: costWords(session.cost, session.unpriced),
    fill: biggest > 0 ? (session.cost ?? 0) / biggest : 0,
    startedEarlier: session.started_before_range,
  };
}

function dayLabel(day: string, today: string): string {
  if (day === today) return t("ss_today");
  if (day === addDays(today, -1)) return t("ss_yday");
  return dateLabel(day, day.slice(0, 4) !== today.slice(0, 4));
}

const biggestCost = (sessions: readonly ReviewSession[]): number =>
  Math.max(0, ...sessions.map((session) => session.cost ?? 0));

/** The sessions page: rows under their local day. A session that began earlier shows its date. */
export function buildSessionGroups(
  days: readonly SessionDay[],
  tz: string,
  endIso: string,
): SessionGroup[] {
  const today = localDate(endIso, tz);
  const biggest = biggestCost(days.flatMap((day) => day.sessions));
  return days.map((day) => ({
    key: day.day,
    label: dayLabel(day.day, today),
    rows: day.sessions.map((session) =>
      rowView(session, tz, day.day, biggest, session.started_before_range),
    ),
  }));
}

/** The Summary's most expensive sessions: one group, every row with its date unless today. */
export function buildTopSessions(
  sessions: readonly ReviewSession[],
  tz: string,
  endIso: string,
): SessionRowView[] {
  const today = localDate(endIso, tz);
  const biggest = biggestCost(sessions);
  return sessions.map((session) => rowView(session, tz, today, biggest, true));
}
