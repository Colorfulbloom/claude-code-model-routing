/*
 * Answers for the Agents and Models page tests, built on the task 10 builders. The agents answer
 * holds one row of each kind the cell rules tell apart, and the models answer holds four models,
 * one of them with no price. T is 2026-11-09 10:00 in New York, a 30 day range from October 11.
 */
import type { AgentList, ModelList } from "@/api/types";
import { agentList, modelList } from "@/test/review";
import { IDS, NO_UNPRICED } from "@/test/review-fixtures";

type AgentRow = AgentList["ran"][number];
type NoRuns = AgentList["never_ran"][number];
type ModelRow = ModelList["rows"][number];
type Kinds = ModelList["kinds"][number];

export const SONNET = "claude-sonnet-5-5";

const FILE = ".claude/agents/builder.md";
const value = (text: string, line = 4) => ({ value: text, file: FILE, line, scope: "agent" });

/** A set pair, such as `setPair(IDS.fable, "xhigh")`. */
export const setPair = (
  model: string | null,
  effort: string | null,
): NonNullable<AgentRow["set"]> => ({
  model: model === null ? null : value(model),
  effort: effort === null ? null : value(effort, 5),
});

/** An agent row with a file, a set pair and a run pair, overridden by what a test checks. */
export function agentRow(over: Partial<AgentRow> = {}): AgentRow {
  return {
    agent: "builder",
    scope: "project",
    set: setPair(IDS.fable, "xhigh"),
    set_reason: null,
    ran: { model: IDS.fable, effort: "medium", mixed: false },
    ran_pairs: [{ model: IDS.fable, effort: "medium", runs: 5 }],
    status: "overridden",
    reason_code: "ran_differs",
    params: {},
    runs_as_set: 0,
    runs_not_as_set: 5,
    runs: 5,
    sessions: 3,
    requests: 9,
    cost: 40,
    share: 0.8,
    unpriced: NO_UNPRICED,
    ...over,
  };
}

export function noRuns(over: Partial<NoRuns> = {}): NoRuns {
  return {
    agent: "migrator",
    scope: "project",
    set: setPair(IDS.opus, "high"),
    set_reason: null,
    ...over,
  };
}

/** Six ran rows covering every source and every Set to reason, then two files that did not run. */
export function agentsAnswer(over: Partial<AgentList> = {}): AgentList {
  return agentList({
    ran: [
      agentRow(),
      agentRow({
        agent: "@main",
        scope: "main",
        set: setPair(IDS.opus, "xhigh"),
        ran: { model: IDS.opus, effort: "high", mixed: false },
        ran_pairs: [{ model: IDS.opus, effort: "high", runs: 53 }],
        status: "lowered",
        runs: 53,
        sessions: 53,
        cost: 8,
        share: 0.16,
      }),
      agentRow({
        agent: "reviewer",
        set: setPair(SONNET, "high"),
        ran: { model: SONNET, effort: "xhigh", mixed: true },
        ran_pairs: [
          { model: SONNET, effort: "xhigh", runs: 27 },
          { model: SONNET, effort: "high", runs: 4 },
        ],
        runs: 31,
        cost: 1.5,
        share: 0.03,
      }),
      agentRow({
        agent: "@unnamed",
        scope: "unnamed",
        set: null,
        set_reason: "sets_nothing",
        status: "default",
        ran_pairs: [{ model: IDS.fable, effort: "medium", runs: 3 }],
        runs: 3,
        cost: 0.4,
        share: 0.004,
      }),
      agentRow({
        agent: "Explore",
        scope: "no_file",
        set: null,
        set_reason: "no_file",
        status: null,
        ran: { model: IDS.haiku, effort: "low", mixed: false },
        ran_pairs: [{ model: IDS.haiku, effort: "low", runs: 2 }],
        runs: 2,
        cost: 0.05,
        share: 0.001,
      }),
      agentRow({
        agent: "scribe",
        scope: "user",
        set: setPair("claude-haiku-4-5", "medium"),
        ran: { model: IDS.haiku, effort: "medium", mixed: false },
        ran_pairs: [{ model: IDS.haiku, effort: "medium", runs: 22 }],
        runs: 22,
        cost: 0.33,
        share: 0.001,
      }),
    ],
    never_ran: [
      noRuns(),
      noRuns({ agent: "release-notes", scope: "user", set: setPair(SONNET, "medium") }),
    ],
    ...over,
  });
}

export function modelRow(over: Partial<ModelRow> = {}): ModelRow {
  return {
    model: IDS.fable,
    cost: 40,
    share: 0.8,
    tokens: 58_700_000,
    requests: 12,
    cache_share: 0.79,
    unpriced: NO_UNPRICED,
    used_by: ["builder", "@unnamed"],
    ...over,
  };
}

export function kindRow(over: Partial<Kinds> = {}): Kinds {
  return {
    model: IDS.fable,
    input: 5,
    output: 9,
    cache_read: 1,
    cache_write: 7,
    unpriced: NO_UNPRICED,
    ...over,
  };
}

/** Fable, Opus and Haiku with prices, and a Sonnet with none. */
export function modelsAnswer(over: Partial<ModelList> = {}): ModelList {
  return modelList({
    rows: [
      modelRow({ cost: 241.92, share: 0.76, requests: 40 }),
      modelRow({
        model: IDS.opus,
        cost: 62.61,
        share: 0.19,
        tokens: 37_000_000,
        cache_share: 0.78,
        used_by: ["@main"],
      }),
      modelRow({
        model: IDS.haiku,
        cost: 0.38,
        share: 0.004,
        tokens: 4_600_000,
        cache_share: 0.6,
        used_by: ["scribe", "Explore"],
      }),
      modelRow({
        model: SONNET,
        cost: null,
        share: null,
        tokens: 17_000_000,
        cache_share: null,
        used_by: ["reviewer"],
        unpriced: { requests: 4, models: [SONNET] },
      }),
    ],
    kinds: [
      kindRow({
        model: IDS.fable,
        input: 25.53,
        output: 83.25,
        cache_read: 11.31,
        cache_write: 121.82,
      }),
      kindRow({ model: IDS.opus, input: 7.29, output: 18.17, cache_read: 5.66, cache_write: 31.5 }),
      kindRow({ model: IDS.haiku, input: 0.06, output: 0.15, cache_read: 0.03, cache_write: 0.14 }),
      kindRow({
        model: SONNET,
        input: 0,
        output: 0,
        cache_read: 0,
        cache_write: 0,
        unpriced: { requests: 4, models: [SONNET] },
      }),
    ],
    legend: { input: 33.88, output: 101.57, cache_read: 17, cache_write: 153.46 },
    unpriced: { requests: 4, models: [SONNET] },
    ...over,
  });
}
