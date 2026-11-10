/*
 * Builders for the Review answers in tests. Each gives a full 30-day answer for project builder
 * at 2026-11-09 15:00 UTC, with every field a real answer carries. A test overrides what it checks.
 */
import type {
  AgentList,
  CostChart,
  ModelList,
  ReviewSession,
  ReviewWindow,
  SessionList,
  Summary,
  Unchanged,
} from "@/api/types";

export const SERVER_TIME = "2026-11-09T15:00:00Z";
export const AS_OF = "2026-11-09T14:58:00Z";

const NO_UNPRICED = { requests: 0, models: [] as string[] };

export function reviewWindow(over: Partial<ReviewWindow> = {}): ReviewWindow {
  return {
    start: "2026-10-11T05:00:00Z",
    end: SERVER_TIME,
    prior_start: "2026-09-11T04:00:00Z",
    prior_end: "2026-10-11T05:00:00Z",
    tz: "America/New_York",
    oldest: "2026-08-01T12:00:00Z",
    partial: false,
    prior_partial: false,
    ...over,
  };
}

const shared = (): Pick<
  Summary,
  "project" | "range" | "server_time" | "as_of" | "etag" | "unchanged" | "errors" | "prices"
> => ({
  project: "builder",
  range: "30d",
  server_time: SERVER_TIME,
  as_of: AS_OF,
  etag: "etag-a",
  unchanged: false,
  errors: [],
  prices: { as_of: "2026-11-08", source: "bundled", cross_check_state: "agree" },
});

export function unchanged(etag: string, serverTime = SERVER_TIME): Unchanged {
  return { project: "builder", server_time: serverTime, etag, unchanged: true };
}

export function sessionRow(id: string, over: Partial<ReviewSession> = {}): ReviewSession {
  return {
    id,
    started: "2026-11-09T13:00:00Z",
    last_request: "2026-11-09T13:30:00Z",
    branch: null,
    state: "ended",
    agents: ["@main"],
    runs: 1,
    tokens: 1000,
    cost: 0.5,
    unpriced: NO_UNPRICED,
    started_before_range: false,
    whole: null,
    ...over,
  };
}

export function sessionList(
  days: SessionList["days"],
  over: Partial<SessionList> = {},
): SessionList {
  return {
    ...shared(),
    count: days.reduce((sum, day) => sum + day.sessions.length, 0),
    days,
    next: null,
    window: reviewWindow(),
    ...over,
  };
}

export function summary(over: Partial<Summary> = {}): Summary {
  return {
    ...shared(),
    tiles: {
      cost: {
        value: 12.5,
        prior: 10,
        change_pct: 0.25,
        change_abs: 2.5,
        unpriced: NO_UNPRICED,
        prior_unpriced: NO_UNPRICED,
      },
      sessions: { value: 53, prior: 40, change_pct: 0.325, change_abs: 13 },
      tokens: { value: 900000, prior: 800000, change_pct: 0.125, change_abs: 100000 },
      cache_share: { value: 0.8, prior: 0.7, change_abs: 0.1 },
    },
    money: [],
    model_check: { rows: [], in_effect_count: 0 },
    top_sessions: [],
    session_count: 53,
    no_usage_sessions: 0,
    window: reviewWindow(),
    ...over,
  };
}

export function costChart(over: Partial<CostChart> = {}): CostChart {
  return {
    ...shared(),
    chart: {
      start: "2026-10-11T04:00:00Z",
      end: SERVER_TIME,
      unit: "day",
      has_earlier: true,
      has_later: false,
      earlier_reason: null,
      later_reason: "newest",
      newest: true,
    },
    bars: [],
    legend: [],
    kinds: { input: 1, output: 2, cache_read: 3, cache_write: 4 },
    unpriced: NO_UNPRICED,
    y_ticks: [1, 2],
    window: reviewWindow(),
    ...over,
  };
}

export function agentList(over: Partial<AgentList> = {}): AgentList {
  return { ...shared(), ran: [], never_ran: [], window: reviewWindow(), ...over };
}

export function modelList(over: Partial<ModelList> = {}): ModelList {
  return {
    ...shared(),
    rows: [],
    kinds: [],
    legend: { input: 1, output: 2, cache_read: 3, cache_write: 4 },
    unpriced: NO_UNPRICED,
    window: reviewWindow(),
    ...over,
  };
}
