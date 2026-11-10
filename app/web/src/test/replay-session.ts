/*
 * A 60 minute session for the replay tests. It starts at START and ends 60 minutes later. Main and
 * its lead run the whole time. The lead has seven children: three finish early (minutes 3 to 8),
 * one works from 20 to 30, and three start at 40, 42 and 44, so at minute 25 the lead folds three
 * finished runs and three that start later. A verifier under main starts at 55. Every run adds 10
 * new tokens, 40 cache reads and one cent for each minute it works, so any value at T is easy to
 * work out by hand. Buckets are one minute and `cum[i]` holds the totals at the end of bucket i.
 */
import type { Timeline, TimelineRun } from "@/api/types";
import { bucket, run, sessionOf, START, timeline } from "@/test/timelines";

const at = (minutes: number): string =>
  new Date(Date.parse(START) + minutes * 60_000).toISOString();

export const MINUTES = 60;
export const END = at(MINUTES);

interface Spec {
  id: string;
  start: number;
  end: number;
  parent?: string;
  order: number;
  model?: string;
  /** Minutes at which the run's state reads finished. Main never finishes on its own. */
  finished?: boolean;
  agent?: string | null;
}

/** Minutes a run has worked by the end of bucket `i`. */
const worked = (spec: Spec, i: number): number =>
  Math.max(0, Math.min(i + 1, spec.end) - spec.start);

function make(spec: Spec, bucketCount: number): TimelineRun {
  const total = worked(spec, bucketCount - 1);
  return run(spec.id, {
    agent: spec.agent === undefined ? spec.id : spec.agent,
    parent: spec.parent ?? null,
    parent_at: spec.parent === undefined ? null : at(spec.start),
    dispatch_order: spec.order,
    model: spec.model ?? "claude-sonnet-5-5",
    effort: "medium",
    first_request: at(spec.start),
    last_request: at(spec.end),
    state: spec.finished === true ? "finished" : "idle",
    states: [
      { at: at(spec.start), state: "working" },
      ...(spec.finished === true ? [{ at: at(spec.end), state: "finished" }] : []),
    ],
    rounds: [{ n: 1, at: at(spec.start), last_request: at(spec.end), by: null, by_kind: null }],
    segments: [{ start: at(spec.start), end: at(spec.end) }],
    tokens: total * 10,
    cost: total * 0.01,
    cum: Array.from({ length: bucketCount }, (_, i) => ({
      tokens: worked(spec, i) * 10,
      cache_read: worked(spec, i) * 40,
      cost: worked(spec, i) * 0.01,
    })),
  });
}

export const SPECS: Spec[] = [
  {
    id: "main",
    agent: null,
    start: 0,
    end: MINUTES,
    order: 0,
    model: "claude-opus-5-5",
  },
  {
    id: "deep-reasoner",
    start: 1,
    end: MINUTES,
    parent: "main",
    order: 1,
    model: "claude-opus-5-5",
  },
  { id: "c1", start: 3, end: 6, parent: "deep-reasoner", order: 2, finished: true },
  { id: "c2", start: 4, end: 7, parent: "deep-reasoner", order: 3, finished: true },
  { id: "c3", start: 5, end: 8, parent: "deep-reasoner", order: 4, finished: true },
  { id: "c4", start: 20, end: 30, parent: "deep-reasoner", order: 5, finished: true },
  { id: "c5", start: 40, end: 50, parent: "deep-reasoner", order: 6, finished: true },
  { id: "c6", start: 42, end: 52, parent: "deep-reasoner", order: 7, finished: true },
  { id: "c7", start: 44, end: 54, parent: "deep-reasoner", order: 8, finished: true },
  { id: "verifier", start: 55, end: MINUTES, parent: "main", order: 9, model: "claude-opus-5-5" },
];

/** The ended session. `over` replaces any field of the answer. */
export function replaySession(over: Partial<Timeline> = {}): Timeline {
  const base = timeline();
  const buckets = Array.from({ length: MINUTES }, (_, minute) =>
    bucket(minute, { by_model: { "claude-opus-5-5": 600, "claude-sonnet-5-5": 400 } }),
  );
  const runs = SPECS.map((spec) => make(spec, MINUTES));
  const sum = (pick: (entry: TimelineRun) => number): number =>
    runs.reduce((total, entry) => total + pick(entry), 0);
  const tokens = sum((entry) => entry.tokens);
  const cacheRead = sum((entry) => entry.cum.at(-1)?.cache_read ?? 0);
  const input = tokens * 0.3;
  const writes = tokens * 0.2;
  return {
    ...base,
    server_time: END,
    as_of: END,
    session: sessionOf({
      state: "ended",
      running: false,
      active: false,
      ended_at: END,
      last_request: END,
      states: [
        { at: START, state: "working" },
        { at: END, state: "ended" },
      ],
    }),
    axis: {
      start: START,
      end: END,
      bucket_seconds: 60,
      ticks: [0, 10, 20, 30, 40, 50, 60].map(at),
      token_ticks: [500, 1000],
    },
    buckets,
    models: [
      { model: "claude-opus-5-5", tokens: tokens * 0.6 },
      { model: "claude-sonnet-5-5", tokens: tokens * 0.4 },
    ],
    last_minute: null,
    totals: {
      tokens,
      input,
      output: tokens * 0.5,
      cache_read: cacheRead,
      cache_write: writes,
      cost: sum((entry) => entry.cost ?? 0),
      hit_rate: cacheRead / (cacheRead + input + writes),
      requests: 40,
      runs: runs.length,
      runs_working: 0,
      runs_finished: runs.length - 1,
      unpriced: { requests: 0, models: [] },
    },
    runs,
    ...over,
  };
}

export { at as minuteAt };

/**
 * The same session cut to its first `minutes` minutes and still running, as a running session's
 * answer reads at that minute: the axis ends at `minutes` and every cumulative list stops there.
 */
export function runningSession(minutes: number, over: Partial<Timeline> = {}): Timeline {
  const base = replaySession();
  const end = at(minutes);
  return {
    ...base,
    server_time: end,
    as_of: end,
    etag: `etag-${String(minutes)}`,
    session: sessionOf({ state: "working", running: true, active: true, last_request: end }),
    axis: { ...base.axis, end },
    buckets: base.buckets.slice(0, minutes),
    runs: base.runs
      .filter((entry) => Date.parse(entry.first_request) <= Date.parse(end))
      .map((entry) => ({ ...entry, cum: entry.cum.slice(0, minutes) })),
    ...over,
  };
}
