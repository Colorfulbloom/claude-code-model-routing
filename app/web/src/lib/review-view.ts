/*
 * The words and numbers of the Review shell and the Summary tiles, from the answers. Pure
 * functions, so a test can check each rule without a page. Dates are local dates in the answer's
 * zone (`window.tz`). Clock times are shown in that zone too, so the page and the server agree.
 *
 * Every t() call keeps a literal key, because a key passed through a helper reads as unused (K-819f).
 */
import { localDate } from "@/api/review";
import type { ReviewRange, ReviewWindow, Summary } from "@/api/types";
import { formatCost, formatCostAtLeast, formatTokens } from "@/lib/format";
import { t, tn } from "@/strings/t";

const DAY_MS = 86_400_000;

/** The span of each fixed range, in local days. `all` has none. */
export const RANGE_DAYS: Readonly<Record<Exclude<ReviewRange, "today" | "all">, number>> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
  "12m": 365,
};

const clocks = new Map<string, Intl.DateTimeFormat>();

/** "6:41 PM" for an instant, in a zone. */
export function timeIn(at: string | number, tz: string): string {
  let format = clocks.get(tz);
  if (format === undefined) {
    format = new Intl.DateTimeFormat("en-US", { timeStyle: "short", timeZone: tz });
    clocks.set(tz, format);
  }
  return format.format(new Date(at));
}

/** A local date plus or minus days, as YYYY-MM-DD. Calendar arithmetic, so no zone is involved. */
export function addDays(date: string, days: number): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + days * DAY_MS).toISOString().slice(0, 10);
}

/** Whole local days from `from` to `to` (both YYYY-MM-DD), inclusive. */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS) + 1;
}

/** "October 20", or "October 31, 2025" when `year` is set. Read as a calendar date, never a zone. */
export function dateLabel(date: string, year = false): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    day: "numeric",
    ...(year ? { year: "numeric" } : {}),
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}

/** "November 2025" for a calendar date. */
export function monthLabel(date: string): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${date}T12:00:00Z`));
}

/** The local date of the window's end (T) and, with `oldest`, of the oldest stored request. */
export function windowDates(w: ReviewWindow): {
  start: string;
  end: string;
  oldest: string | null;
} {
  return {
    start: localDate(w.start, w.tz),
    end: localDate(w.end, w.tz),
    oldest: w.oldest === null ? null : localDate(w.oldest, w.tz),
  };
}

/** The oldest stored request as a date, with the year only when it is not T's year. Null when none. */
export function oldestLabel(w: ReviewWindow): string | null {
  const { end, oldest } = windowDates(w);
  return oldest === null ? null : dateLabel(oldest, oldest.slice(0, 4) !== end.slice(0, 4));
}

/** The first local date of a fixed range that ends on `end`. */
function spanStart(range: Exclude<ReviewRange, "today" | "all">, end: string): string {
  return addDays(end, 1 - RANGE_DAYS[range]);
}

/** The Range Select's option word. */
export function rangeLabel(range: ReviewRange): string {
  switch (range) {
    case "today":
      return t("rg_today");
    case "7d":
      return t("rg_7d");
    case "30d":
      return t("rg_30d");
    case "90d":
      return t("rg_90d");
    case "12m":
      return t("rg_12m");
    case "all":
      return t("rg_all");
  }
}

/**
 * The line under an option in the Range Select, as dates. Every fixed range ends on the date of T,
 * so the options can all be worded from the one window the page holds.
 */
export function rangeWindow(range: ReviewRange, w: ReviewWindow): string {
  const { end } = windowDates(w);
  switch (range) {
    case "today":
      return t("rg_w_today", { time: timeIn(w.end, w.tz) });
    case "all":
      return t("rg_w_all", { date: oldestLabel(w) ?? dateLabel(end) });
    case "12m":
      return t("rg_w_span", {
        start: dateLabel(spanStart(range, end), true),
        end: dateLabel(end, true),
      });
    default: {
      const start = spanStart(range, end);
      const year = start.slice(0, 4) !== end.slice(0, 4);
      return t("rg_w_span", { start: dateLabel(start, year), end: dateLabel(end, year) });
    }
  }
}

/** The range as a noun, for the route status: "the last 30 days". */
export function rangeNoun(range: ReviewRange, w: ReviewWindow | null): string {
  switch (range) {
    case "today":
      return t("rg_n_today");
    case "7d":
      return t("rg_n_days", { n: 7 });
    case "30d":
      return t("rg_n_days", { n: 30 });
    case "90d":
      return t("rg_n_days", { n: 90 });
    case "12m":
      return t("rg_n_12m");
    case "all": {
      const date = w === null ? null : oldestLabel(w);
      return date === null ? t("rg_all") : t("rg_n_all", { date });
    }
  }
}

/** The range after "in {project}": "in the last 30 days". */
export function rangePhrase(range: ReviewRange, w: ReviewWindow | null): string {
  switch (range) {
    case "today":
      return t("rg_p_today");
    case "7d":
      return t("rg_p_days", { n: 7 });
    case "30d":
      return t("rg_p_days", { n: 30 });
    case "90d":
      return t("rg_p_days", { n: 90 });
    case "12m":
      return t("rg_p_12m");
    case "all": {
      const date = w === null ? null : oldestLabel(w);
      return date === null ? t("rg_all") : t("rg_p_all", { date });
    }
  }
}

/**
 * True when the prior window holds any records, which is when `oldest` falls before the prior
 * window's end. A partial prior with records still compares (the tiles say "Up from {v}"). A prior
 * from before the records began holds nothing, so the tiles say the average and the line under the
 * title says there is nothing earlier to compare with.
 */
export function priorHasRecords(w: ReviewWindow): boolean {
  if (w.prior_end === null || w.oldest === null) return false;
  return Date.parse(w.oldest) < Date.parse(w.prior_end);
}

/** The line under the page title, from the answer's window. */
export function subLine(range: ReviewRange, w: ReviewWindow): string {
  const { start, end } = windowDates(w);
  const since = oldestLabel(w) ?? dateLabel(start);
  if (range === "all") return t("sub_all", { date: since });
  if (range === "today") {
    const time = timeIn(w.end, w.tz);
    return priorHasRecords(w)
      ? t("sub_today", { time })
      : t("sub_short", { start: t("rg_today"), end: time, date: since });
  }
  const year = range === "12m" || start.slice(0, 4) !== end.slice(0, 4);
  const first = dateLabel(range === "12m" ? spanStart(range, end) : start, year);
  if (!priorHasRecords(w)) {
    return t("sub_short", {
      start: first,
      end: dateLabel(end, year),
      date: since,
    });
  }
  return t("sub_span", {
    start: first,
    end: dateLabel(end, year),
    n: RANGE_DAYS[range],
  });
}

/** What a Review tile shows. `note` is a second line under the delta. */
export interface TileView {
  label: string;
  qualifier?: string;
  value: string;
  delta: string;
  note?: string;
}

const percentText = (share: number): string => `${String(Math.round(share * 100))}%`;

function costWords(value: number | null, unpriced: number): string {
  if (value === null) return t("c_none_short");
  return unpriced > 0 ? formatCostAtLeast(value) : formatCost(value);
}

/** Days the window covers, at least one, for "a day on average". */
function windowDays(w: ReviewWindow): number {
  return Math.max(1, Math.ceil((Date.parse(w.end) - Date.parse(w.start)) / DAY_MS));
}

interface CountDelta {
  value: number;
  prior: number | null;
  change_pct: number | null;
}

/**
 * The comparison line for a count or a cost. A fixed range with a whole prior says the change in
 * percent. A prior that is partial or zero gives no percent, so it says only up or down from the
 * prior. Today compares with yesterday by the same time. A prior with no records (All, or a range
 * from before the first request) shows the daily average, never "Up from $0.00".
 */
function deltaFor(
  tile: CountDelta,
  range: ReviewRange,
  w: ReviewWindow,
  show: (n: number) => string,
  average: () => string,
): string {
  const time = timeIn(w.end, w.tz);
  if (tile.prior === null || !priorHasRecords(w)) return average();
  const prior = show(tile.prior);
  if (range === "today") return t("t_yday", { v: prior, time });
  if (tile.change_pct !== null) {
    const p = `${String(Math.round(Math.abs(tile.change_pct) * 100))}%`;
    if (Math.abs(tile.change_pct) < 0.02) return t("t_same", { v: prior });
    return tile.change_pct > 0 ? t("t_up", { p, v: prior }) : t("t_down", { p, v: prior });
  }
  if (tile.value === tile.prior) return t("t_same", { v: prior });
  return tile.value > tile.prior ? t("t_up_n", { v: prior }) : t("t_down_n", { v: prior });
}

/** The four Summary tiles, in order: cost, sessions, tokens, cache. */
export function buildSummaryTiles(summary: Summary): TileView[] {
  const { tiles, window: w, range } = summary;
  const days = windowDays(w);
  const unpriced = tiles.cost.unpriced.requests;
  const cost: TileView = {
    label: t("rv_t_cost"),
    qualifier: t("t_cost_kx"),
    value: costWords(tiles.cost.value, unpriced),
    delta:
      tiles.cost.value === null
        ? ""
        : deltaFor(
            { value: tiles.cost.value, prior: tiles.cost.prior, change_pct: tiles.cost.change_pct },
            range,
            w,
            formatCost,
            () => t("t_avg_cost", { v: formatCost((tiles.cost.value ?? 0) / days) }),
          ),
    ...(unpriced > 0 ? { note: tn("t_unpriced", unpriced) } : {}),
  };
  const sessions: TileView = {
    label: t("rv_t_sessions"),
    value: String(tiles.sessions.value),
    delta: deltaFor(tiles.sessions, range, w, String, () =>
      t("t_avg_sessions", { v: (tiles.sessions.value / days).toFixed(1) }),
    ),
  };
  const tokens: TileView = {
    label: t("rv_t_tokens"),
    value: formatTokens(tiles.tokens.value),
    delta: deltaFor(tiles.tokens, range, w, formatTokens, () =>
      t("t_avg_tokens", { v: formatTokens(tiles.tokens.value / days) }),
    ),
  };
  return [cost, sessions, tokens, cacheTile(summary)];
}

/**
 * The cache tile. A whole prior gives points (a share has no percent change). A partial or zero
 * prior says only up or down. With no prior it says what the share covers.
 */
function cacheTile(summary: Summary): TileView {
  const { cache_share: share } = summary.tiles;
  const { range, window: w } = summary;
  const base = {
    label: t("rv_t_cache"),
    value: share.value === null ? "–" : percentText(share.value),
  };
  if (share.prior === null || !priorHasRecords(w)) {
    return {
      ...base,
      delta: range === "today" ? t("t_avg_cache") : t("t_avg_cache_range"),
    };
  }
  const prior = percentText(share.prior);
  if (range === "today")
    return { ...base, delta: t("t_yday", { v: prior, time: timeIn(w.end, w.tz) }) };
  if (share.change_abs !== null) {
    const points = Math.round(Math.abs(share.change_abs) * 100);
    if (points === 0) return { ...base, delta: t("t_same", { v: prior }) };
    return {
      ...base,
      delta:
        share.change_abs > 0
          ? t("t_up_pt", { p: points, v: prior })
          : t("t_down_pt", { p: points, v: prior }),
    };
  }
  if (share.value === null || share.value === share.prior) {
    return { ...base, delta: t("t_same", { v: prior }) };
  }
  return {
    ...base,
    delta: share.value > share.prior ? t("t_up_n", { v: prior }) : t("t_down_n", { v: prior }),
  };
}
