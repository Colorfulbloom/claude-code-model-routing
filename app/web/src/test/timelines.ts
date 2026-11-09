/*
 * Builders for timeline answers in tests. `timeline()` gives a working session at 22:40:00 UTC that
 * started at 22:10:00 with a main run, one lead run and two finished children, and every field a
 * real answer carries. A test overrides what it checks.
 */
import type {
  LiveSession,
  StateAt,
  Timeline,
  TimelineBucket,
  TimelineRun,
  TimelineSession,
} from "@/api/types";

export const START = "2026-10-30T22:10:00Z";
export const NOW = "2026-10-30T22:40:00Z";

const NO_UNPRICED = { requests: 0, models: [] as string[] };

const at = (minutes: number): string =>
  new Date(Date.parse(START) + minutes * 60_000).toISOString();

export function state(minute: number, word: string): StateAt {
  return { at: at(minute), state: word };
}

/** A run that began at `first` minutes into the session. Defaults to a working Opus run. */
export function run(id: string, over: Partial<TimelineRun> = {}): TimelineRun {
  const first = over.first_request ?? at(0);
  return {
    run_id: id,
    agent: id === "main" ? null : id,
    label_n: 1,
    parent: id === "main" ? null : "main",
    parent_known: true,
    parent_at: first,
    parent_state: "known",
    depth: id === "main" ? 0 : 1,
    dispatch_order: 0,
    together: null,
    model: "claude-opus-5-5",
    effort: "high",
    first_request: first,
    last_request: NOW,
    state: "working",
    states: [{ at: first, state: "working" }],
    rounds: [{ n: 1, at: first, last_request: NOW, by: null, by_kind: null }],
    segments: [{ start: first, end: NOW }],
    tokens: 1000,
    cost: 0.5,
    unpriced: NO_UNPRICED,
    cum: [],
    ...over,
  };
}

/** One bucket of 60 seconds with Opus tokens. */
export function bucket(minute: number, over: Partial<TimelineBucket> = {}): TimelineBucket {
  return {
    start: at(minute),
    by_model: { "claude-opus-5-5": 1000 },
    cache_read: 4000,
    cost: 0.05,
    requests: 2,
    unpriced: NO_UNPRICED,
    ...over,
  };
}

export function sessionOf(over: Partial<TimelineSession> = {}): TimelineSession {
  return {
    id: "s1",
    project: "builder",
    branch: "feature/quarter-close",
    started: START,
    last_request: NOW,
    running: true,
    active: true,
    state: "working",
    states: [{ at: START, state: "working" }],
    ended_at: null,
    requests: 40,
    unpriced: NO_UNPRICED,
    ...over,
  };
}

export function timeline(over: Partial<Timeline> = {}): Timeline {
  const buckets = Array.from({ length: 31 }, (_, minute) => bucket(minute));
  const main = run("main", {
    tokens: 5000,
    cost: 3.1,
    cum: buckets.map((_, i) => ({
      tokens: (i + 1) * 100,
      cache_read: (i + 1) * 400,
      cost: (i + 1) * 0.1,
    })),
  });
  const lead = run("deep-reasoner", {
    dispatch_order: 1,
    first_request: at(1),
    tokens: 3000,
    cost: 2.2,
    cum: buckets.map((_, i) => ({ tokens: i * 50, cache_read: i * 200, cost: i * 0.05 })),
  });
  return {
    project: "builder",
    server_time: NOW,
    as_of: NOW,
    etag: "etag-a",
    unchanged: false,
    session: sessionOf(),
    axis: {
      start: START,
      end: NOW,
      bucket_seconds: 60,
      ticks: [at(0), at(5), at(10), at(15), at(20), at(25), at(30)],
      token_ticks: [500, 1000],
    },
    buckets,
    models: [{ model: "claude-opus-5-5", tokens: 31000 }],
    last_minute: {
      tokens: 1200,
      cost: 0.44,
      cache_read: 5000,
      hit_rate: 0.81,
      requests: 3,
      unpriced: NO_UNPRICED,
    },
    totals: {
      tokens: 31000,
      input: 10000,
      output: 12000,
      cache_read: 120000,
      cache_write: 9000,
      cost: 8.28,
      hit_rate: 0.78,
      requests: 40,
      runs: 2,
      runs_working: 2,
      runs_finished: 0,
      unpriced: NO_UNPRICED,
    },
    runs: [main, lead],
    requests: Array.from({ length: 8 }, (_, i) => ({
      id: `r${String(i)}`,
      at: new Date(Date.parse(NOW) - i * 1000).toISOString(),
      run_id: i % 2 === 0 ? "main" : "deep-reasoner",
      model: "claude-opus-5-5",
      effort: "high",
      tokens: 48000,
      new_tokens: 2000,
      cache_read: 46000,
      output: 400,
      cost: 0.05,
    })),
    model_check: { rows: [], in_effect_count: 0 },
    prices: { as_of: "2026-11-08", source: "bundled", cross_check_state: "agree" },
    ...over,
  };
}

export function liveSession(id: string, over: Partial<LiveSession> = {}): LiveSession {
  return {
    id,
    project: "builder",
    project_name: "Builder",
    branch: "feature/quarter-close",
    started: START,
    last_request: NOW,
    active: true,
    runs_working: 2,
    requests: 40,
    state: "working",
    ...over,
  };
}
