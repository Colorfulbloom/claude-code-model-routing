/*
 * Replay in Session review. The line sits at a whole minute counted from the axis start, kept in
 * the URL as `?at=<minute>` (history replace, so a drag never fills the back stack). No `at`
 * means the end, and at the end the line follows the growing axis of a running session. Once the
 * owner moves it, it stays where it was put until Back to now.
 *
 * Everything the page needs at the line comes from the one timeline answer, through
 * timeline-at.ts, so dragging never asks the server. Run states, parents and rounds are exact at
 * every minute. Tokens and cost are exact only at each bucket's end, so on a long session
 * (buckets above 60 seconds) the numbers hold between bucket ends. `precision` says so.
 *
 * The helpers are pure. `useReplay` is the one hook. The page owns every word.
 */
import { useEffect } from "react";
import { useSearchParams } from "react-router";
import type { Timeline } from "@/api/types";
import { valuesAt } from "@/lib/timeline-at";
import type { SessionStateAt, TimelineAt } from "@/lib/timeline-at";

const MINUTE_MS = 60_000;

/** The page step in minutes, for Page Up and Page Down. */
export const PAGE_STEP_MINUTES = 5;
/** Above this many seconds a bucket is wider than the page step, so the step follows it. */
export const PAGE_STEP_BUCKET_SECONDS = 300;
/** At or below this the numbers are exact at every minute. */
export const EXACT_BUCKET_SECONDS = 60;

/**
 * The last minute of the line, counted from the axis start. Never below 0. A running session ends
 * where the axis ends (Now). An ended session ends in the minute of its last request, because its
 * axis closes on the next bucket edge, which can sit a minute past the session.
 */
export function axisMaxMinute(timeline: Timeline): number {
  const start = Date.parse(timeline.axis.start);
  let span = Date.parse(timeline.axis.end) - start;
  const last = Date.parse(timeline.session.last_request) - start;
  if (!timeline.session.running && Number.isFinite(last) && last < span) span = last;
  return Number.isFinite(span) ? Math.max(0, Math.floor(span / MINUTE_MS)) : 0;
}

/** A minute clamped into [0, max], as a whole number. A value that is not a number gives max. */
export function clampMinute(minute: number, max: number): number {
  if (Number.isNaN(minute)) return max;
  return Math.min(max, Math.max(0, Math.floor(minute)));
}

/**
 * Reads `?at=`. A whole or fractional number is clamped into the axis, so a value past the end
 * gives the end with no message. Anything else (missing, empty, not a number) gives null, which
 * means the line is at the end.
 */
export function parseAt(raw: string | null, max: number): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  return clampMinute(value, max);
}

/** Page Up and Page Down move 5 minutes, or one bucket when the buckets are wider than that. */
export function pageStep(bucketSeconds: number): number {
  return bucketSeconds > PAGE_STEP_BUCKET_SECONDS ? bucketSeconds / 60 : PAGE_STEP_MINUTES;
}

export type ReplayMode = "whole" | "at";

/** At the end the tiles say whole session so far. Before it they say the values at the line. */
export function replayMode(minute: number, max: number): ReplayMode {
  return minute >= max ? "whole" : "at";
}

export interface Precision {
  /** True when numbers hold between bucket ends, so the label says so. */
  held: boolean;
  /** The bucket width in minutes, for the label. */
  bucketMinutes: number;
}

export function precisionOf(timeline: Timeline): Precision {
  const seconds = timeline.axis.bucket_seconds;
  return { held: seconds > EXACT_BUCKET_SECONDS, bucketMinutes: seconds / 60 };
}

/**
 * The instant to ask timeline-at.ts about, in epoch ms. At the end it reaches the answer's own
 * time, so the open last bucket counts too, whatever fraction of a minute the axis ends on.
 */
export function replayTime(timeline: Timeline, minute: number, max: number): number {
  const start = Date.parse(timeline.axis.start);
  const at = start + minute * MINUTE_MS;
  if (replayMode(minute, max) === "at") return at;
  return Math.max(at, Date.parse(timeline.axis.end), Date.parse(timeline.server_time));
}

/** The numbers behind the screen-reader line. The page words them. */
export interface ReplaySummary {
  mode: ReplayMode;
  /** The session's own state at the line. */
  session: SessionStateAt;
  runs: {
    working: number;
    idle: number;
    finished: number;
    notStarted: number;
    total: number;
  };
  /** Cost so far, or null when no cost at the line is priced. */
  cost: number | null;
  tokens: number;
}

/** Counts by run state and the cost so far at the line. */
export function summaryAt(timeline: Timeline, minute: number): ReplaySummary {
  const max = axisMaxMinute(timeline);
  const at = valuesAt(timeline, replayTime(timeline, minute, max));
  return summarize(at, replayMode(minute, max));
}

function summarize(at: TimelineAt, mode: ReplayMode): ReplaySummary {
  const runs = { working: 0, idle: 0, finished: 0, notStarted: 0, total: at.runs.length };
  for (const run of at.runs) {
    if (run.state === "working") runs.working += 1;
    else if (run.state === "idle") runs.idle += 1;
    else if (run.state === "finished") runs.finished += 1;
    else runs.notStarted += 1;
  }
  return { mode, session: at.session, runs, cost: at.totals.cost, tokens: at.totals.tokens };
}

export interface Replay {
  /** The line's minute from the axis start, clamped to [0, max]. */
  minute: number;
  max: number;
  mode: ReplayMode;
  /** True at the end. On a running session the line follows Now there. */
  atEnd: boolean;
  /** Page Up and Page Down, in minutes. */
  step: number;
  /** The line's instant, epoch ms, for the lanes and the chart fade. */
  at: number;
  /** Every value at the line, from timeline-at.ts. */
  values: TimelineAt;
  summary: ReplaySummary;
  precision: Precision;
  /** Puts the line at a minute. At or past the end it goes to the end and follows Now. */
  setMinute: (minute: number) => void;
  /** Moves by a number of minutes (Arrow keys). */
  move: (delta: number) => void;
  /** Moves by one page step, forward or back (Page Down, Page Up). */
  page: (direction: 1 | -1) => void;
  /** Home. */
  toStart: () => void;
  /** End, and Back to now. Removes `at`, so the line follows a running session. */
  toEnd: () => void;
}

/**
 * The replay line over one timeline answer, or null before the answer arrives. A running
 * session's answer grows every 5 seconds. A line with no `at` follows the new end, and a line the
 * owner moved stays at its minute.
 */
export function useReplay(timeline: Timeline | undefined): Replay | null {
  const [params, setParams] = useSearchParams();
  const raw = params.get("at");
  const max = timeline === undefined ? 0 : axisMaxMinute(timeline);
  const parsed = parseAt(raw, max);
  const ready = timeline !== undefined;

  // A value at or past the end, or one that is not a number, goes away without a message.
  const stale = ready && raw !== null && (parsed === null || parsed >= max);
  useEffect(() => {
    if (!stale) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete("at");
        return next;
      },
      { replace: true },
    );
  }, [stale, setParams]);

  if (timeline === undefined) return null;

  const minute = parsed ?? max;
  const mode = replayMode(minute, max);
  const at = replayTime(timeline, minute, max);
  const values = valuesAt(timeline, at);

  function write(next: number | null): void {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current);
        if (next === null) copy.delete("at");
        else copy.set("at", String(next));
        return copy;
      },
      { replace: true },
    );
  }

  function setMinute(target: number): void {
    const clamped = clampMinute(target, max);
    write(clamped >= max ? null : clamped);
  }

  const step = pageStep(timeline.axis.bucket_seconds);
  return {
    minute,
    max,
    mode,
    atEnd: mode === "whole",
    step,
    at,
    values,
    summary: summarize(values, mode),
    precision: precisionOf(timeline),
    setMinute,
    move: (delta) => {
      setMinute(minute + delta);
    },
    page: (direction) => {
      setMinute(minute + direction * step);
    },
    toStart: () => {
      setMinute(0);
    },
    toEnd: () => {
      write(null);
    },
  };
}
