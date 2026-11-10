/*
 * Fuller Review answers for the page tests, built on the task 10 builders: a chart with bars, a
 * summary with money, a model check and top sessions, and a sessions list in fifties. All use the
 * builders' window (T is 2026-11-09 10:00 in New York, a 30 day range from October 11).
 */
import type { CostChart, ModelCheckRow, ReviewSession, SessionList, Summary } from "@/api/types";
import { costChart, reviewWindow, sessionList, sessionRow, summary } from "@/test/review";

export const IDS = {
  opus: "claude-opus-5-5",
  fable: "claude-fable-5-1",
  haiku: "claude-haiku-5-5",
};

export const NO_UNPRICED = { requests: 0, models: [] as string[] };

/** Midnight in New York for a November 2026 date (EDT through the first, EST after). */
export const midnight = (date: string): string => `${date}T0${date <= "2026-11-01" ? 4 : 5}:00:00Z`;

function part(cost: number | null, requests = 3, unpriced = NO_UNPRICED) {
  return {
    cost,
    kinds: { input: 1, output: 2, cache_read: 3, cache_write: 4 },
    requests,
    unpriced,
  };
}

function dayBar(day: number, parts: Record<string, ReturnType<typeof part>>) {
  const date = (n: number): string => `2026-11-${String(n).padStart(2, "0")}`;
  return {
    start: midnight(date(day)),
    end: day === 9 ? "2026-11-09T15:00:00Z" : midnight(date(day + 1)),
    by_model: parts,
    unpriced: NO_UNPRICED,
    open: day === 9,
    holds_oldest: false,
    no_records: false,
  };
}

/** The newest 30 day chart with four bars, $48.00 in all, most of it on Fable 5.1. */
export function chartAnswer(over: Partial<CostChart> = {}): CostChart {
  return costChart({
    bars: [6, 7, 8, 9].map((day) => dayBar(day, { [IDS.fable]: part(10), [IDS.opus]: part(2) })),
    legend: [
      { model: IDS.opus, cost: 8, requests: 12, unpriced: NO_UNPRICED },
      { model: IDS.fable, cost: 40, requests: 12, unpriced: NO_UNPRICED },
    ],
    kinds: { input: 5, output: 9, cache_read: 1, cache_write: 7 },
    y_ticks: [10, 20],
    chart: {
      start: midnight("2026-10-11"),
      end: "2026-11-09T15:00:00Z",
      unit: "day",
      has_earlier: true,
      has_later: false,
      earlier_reason: null,
      later_reason: "newest",
      newest: true,
    },
    ...over,
  });
}

/** One page back from the newest, 30 days earlier, with a Later button. */
export function chartEarlier(over: Partial<CostChart> = {}): CostChart {
  return chartAnswer({
    bars: [dayBar(1, { [IDS.opus]: part(3) })],
    legend: [{ model: IDS.opus, cost: 3, requests: 3, unpriced: NO_UNPRICED }],
    chart: {
      start: midnight("2026-09-11"),
      end: midnight("2026-10-11"),
      unit: "day",
      has_earlier: false,
      has_later: true,
      earlier_reason: "no_earlier_data",
      later_reason: null,
      newest: false,
    },
    ...over,
  });
}

const FILE = ".claude/agents/builder.md";
const pair = (value: string, line: number) => ({ value, file: FILE, line, scope: "agent" });

export const overridden: ModelCheckRow = {
  agent: "builder",
  set: { model: pair(IDS.fable, 4), effort: pair("xhigh", 5) },
  ran: { model: IDS.fable, effort: "medium", mixed: false },
  status: "overridden",
  reason_code: "ran_differs",
  params: {
    setting: "effort",
    value: "xhigh",
    expected: "xhigh",
    ran: "medium",
    settings: "effort",
  },
  runs: 5,
  mismatched_runs: 5,
};

export const inEffect: ModelCheckRow = {
  agent: "scribe",
  set: { model: pair(IDS.haiku, 3), effort: null },
  ran: { model: IDS.haiku, effort: "low", mixed: false },
  status: "in_effect",
  reason_code: "in_effect",
  params: { setting: "model", value: IDS.haiku, settings: "model" },
  runs: 3,
  mismatched_runs: 0,
};

export function sessionAt(id: string, startedIso: string, over: Partial<ReviewSession> = {}) {
  return sessionRow(id, { started: startedIso, last_request: startedIso, ...over });
}

/** The Summary for 30 days with money, a model check and one top session. */
export function summaryAnswer(over: Partial<Summary> = {}): Summary {
  return summary({
    money: [
      {
        agent: "builder",
        model: IDS.fable,
        cost: 40,
        share: 0.8,
        requests: 9,
        unpriced: NO_UNPRICED,
      },
      { agent: "@main", model: IDS.opus, cost: 8, share: 0.16, requests: 4, unpriced: NO_UNPRICED },
      {
        agent: "@unnamed",
        model: IDS.fable,
        cost: 0.4,
        share: 0.004,
        requests: 1,
        unpriced: NO_UNPRICED,
      },
    ],
    model_check: { rows: [overridden, inEffect], in_effect_count: 1 },
    top_sessions: [
      sessionAt("s-top", "2026-11-02T15:00:00Z", {
        branch: "feature/quarter-close",
        agents: ["builder", "@main"],
        runs: 5,
        tokens: 4_100_000,
        cost: 14.06,
      }),
    ],
    ...over,
  });
}

/** Today in New York, 24 hours, for the Today tests. */
export const todayWindow = reviewWindow({
  start: midnight("2026-11-09"),
  prior_start: midnight("2026-11-08"),
  prior_end: "2026-11-08T15:00:00Z",
});

/** `count` sessions from the newest, one an hour back from 14:00 UTC on November 9. */
export function manySessions(from: number, count: number): ReviewSession[] {
  return Array.from({ length: count }, (_, i) => {
    const n = from + i;
    const at = new Date(Date.parse("2026-11-09T14:00:00Z") - n * 3_600_000).toISOString();
    return sessionAt(`s${String(n)}`, at, { cost: 1 + (n % 7), branch: `feature/b${String(n)}` });
  });
}

/** One page of the sessions list. `day` groups the rows as one local day. */
export function sessionsPage(
  sessions: ReviewSession[],
  over: Partial<SessionList> = {},
): SessionList {
  const byDay = new Map<string, ReviewSession[]>();
  for (const session of sessions) {
    const day = session.started.slice(0, 10);
    byDay.set(day, [...(byDay.get(day) ?? []), session]);
  }
  return sessionList(
    [...byDay.entries()].map(([day, rows]) => ({ day, sessions: rows })),
    over,
  );
}
