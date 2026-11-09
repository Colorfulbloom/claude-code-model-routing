/*
 * Values at a time T, picked from one timeline answer. The answer carries everything needed
 * (`states[]`, `parent_at`, `rounds[]`, `cum[]`), so Live asks at T = server time and Session
 * review (M3) will ask at any earlier T from the same payload. Every function is pure and takes T
 * as epoch milliseconds.
 *
 * Cumulative numbers are bucket-granular. `cum[i]` holds the totals at the end of bucket i, so at
 * a T inside a bucket the picker reports the last bucket that has fully ended, and never counts a
 * request that came after T. At or after the answer's own time (Live) it reports the last bucket,
 * open one included. Run states, parents and rounds are exact, because they carry their own times.
 */
import type { StateAt, Timeline, TimelineRound, TimelineRun, TimelineSession } from "@/api/types";

/** Where a run stands at T. A run that has not made a request yet is not started. */
export type RunStateAt = "not_started" | "working" | "idle" | "finished";

export type ParentState = "known" | "waiting" | "unknown";

/** The wait before an unlinked finished run's starter reads as unknown for good (5 minutes). */
export const SETTLE_MS = 5 * 60_000;

export interface CumAt {
  tokens: number;
  cache_read: number;
  cost: number | null;
}

export interface RoundAt {
  n: number;
  at: number;
  /** Clamped to T, because a round still going at T has made requests only up to T. */
  lastRequest: number;
  by: string | null;
  byKind: TimelineRound["by_kind"];
}

export interface RunAt {
  runId: string;
  state: RunStateAt;
  /** `main` for a run whose starter is not known at T, else the starter's run id. Null for main. */
  parent: string | null;
  parentKnown: boolean;
  parentState: ParentState;
  rounds: RoundAt[];
  cum: CumAt;
}

export interface TimelineAt {
  at: number;
  session: SessionStateAt;
  runs: RunAt[];
  totals: CumAt;
}

export type SessionStateAt = "not_started" | TimelineSession["state"];

const ms = (text: string): number => Date.parse(text);

/** The last entry that started at or before T. */
function lastAtOrBefore(states: readonly StateAt[], t: number): StateAt | null {
  let found: StateAt | null = null;
  for (const entry of states) {
    if (ms(entry.at) > t) break;
    found = entry;
  }
  return found;
}

export function runStateAt(run: TimelineRun, t: number): RunStateAt {
  if (t < ms(run.first_request)) return "not_started";
  const entry = lastAtOrBefore(run.states, t);
  if (entry === null) return "idle";
  return entry.state === "working" || entry.state === "finished" ? entry.state : "idle";
}

export function sessionStateAt(session: TimelineSession, t: number): SessionStateAt {
  if (t < ms(session.started)) return "not_started";
  const entry = lastAtOrBefore(session.states, t);
  if (entry === null) return "idle";
  return entry.state === "working" || entry.state === "ended" ? entry.state : "idle";
}

/**
 * The starter of a run at T. It is known only from `parent_at` on. Before that, or with no link,
 * the run hangs under main and the state is waiting while the run still works or finished less
 * than 5 minutes ago, and unknown after that.
 */
export function parentAt(
  run: TimelineRun,
  t: number,
): { parent: string | null; known: boolean; state: ParentState } {
  if (run.parent === null) return { parent: null, known: true, state: "known" };
  if (run.parent_at !== null && t >= ms(run.parent_at)) {
    return { parent: run.parent, known: true, state: "known" };
  }
  const finished = lastAtOrBefore(
    run.states.filter((entry) => entry.state === "finished"),
    t,
  );
  const settled =
    runStateAt(run, t) === "finished" && finished !== null && t - ms(finished.at) >= SETTLE_MS;
  return { parent: "main", known: false, state: settled ? "unknown" : "waiting" };
}

/** The rounds that started at or before T. */
export function roundsAt(run: TimelineRun, t: number): RoundAt[] {
  return run.rounds
    .filter((round) => ms(round.at) <= t)
    .map((round) => ({
      n: round.n,
      at: ms(round.at),
      lastRequest: Math.min(ms(round.last_request), t),
      by: round.by,
      byKind: round.by_kind,
    }));
}

/**
 * The index of the last bucket that counts at T, or -1 when none has ended. At or after the
 * answer's own time it is the last bucket, because Live's open bucket counts up to Now.
 */
export function bucketIndexAt(timeline: Timeline, t: number): number {
  const count = timeline.buckets.length;
  if (count === 0) return -1;
  const start = ms(timeline.axis.start);
  const step = timeline.axis.bucket_seconds * 1000;
  if (t >= ms(timeline.server_time) || t >= start + count * step) return count - 1;
  return Math.max(-1, Math.min(count, Math.floor((t - start) / step)) - 1);
}

const ZERO: CumAt = { tokens: 0, cache_read: 0, cost: 0 };

export function cumAt(run: TimelineRun, index: number): CumAt {
  return run.cum[index] ?? ZERO;
}

/** Totals over every run: new tokens, cache reads, and the cost of the priced requests. */
export function totalsAt(timeline: Timeline, t: number): CumAt {
  const index = bucketIndexAt(timeline, t);
  let tokens = 0;
  let cacheRead = 0;
  let cost: number | null = null;
  for (const run of timeline.runs) {
    const cum = cumAt(run, index);
    tokens += cum.tokens;
    cacheRead += cum.cache_read;
    if (cum.cost !== null) cost = (cost ?? 0) + cum.cost;
  }
  return { tokens, cache_read: cacheRead, cost };
}

/** Every value the Live page and Session review pick from one answer at T. */
export function valuesAt(timeline: Timeline, t: number): TimelineAt {
  const index = bucketIndexAt(timeline, t);
  return {
    at: t,
    session: sessionStateAt(timeline.session, t),
    runs: timeline.runs.map((run) => {
      const parent = parentAt(run, t);
      return {
        runId: run.run_id,
        state: runStateAt(run, t),
        parent: parent.parent,
        parentKnown: parent.known,
        parentState: parent.state,
        rounds: roundsAt(run, t),
        cum: cumAt(run, index),
      };
    }),
    totals: totalsAt(timeline, t),
  };
}
