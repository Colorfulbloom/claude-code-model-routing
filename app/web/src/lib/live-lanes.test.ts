import { describe, expect, it } from "vitest";
import type { Timeline, TimelineRun } from "@/api/types";
import type { LaneFold, LaneRun } from "@/components/TimelineLane/TimelineLane";
import { axisFor } from "@/lib/live-chart";
import {
  buildLane,
  buildLaneItems,
  buildTree,
  DEPTH_CAP_DESKTOP,
  DEPTH_CAP_PHONE,
} from "@/lib/live-lanes";
import type { LaneContext } from "@/lib/live-lanes";
import { NOW, run, sessionOf, state, timeline } from "@/test/timelines";

const now = Date.parse(NOW);
const minutesAgo = (n: number): string => new Date(now - n * 60_000).toISOString();

function context(answer: Timeline, over: Partial<LaneContext> = {}): LaneContext {
  return {
    nowMs: now,
    axis: axisFor(answer, now),
    desktop: true,
    expanded: new Set(),
    moved: new Set(),
    onToggle: () => undefined,
    ...over,
  };
}

const runsOf = (items: (LaneRun | LaneFold)[]): LaneRun[] =>
  items.filter((item): item is LaneRun => item.kind === "run");

/** A finished child that ended `ago` minutes before Now. */
function child(
  id: string,
  parent: string,
  order: number,
  ago: number,
  over: Partial<TimelineRun> = {},
) {
  return run(id, {
    agent: "fast-worker",
    label_n: Number(id.slice(1)) || order,
    parent,
    dispatch_order: order,
    state: "finished",
    first_request: minutesAgo(ago + 3),
    last_request: minutesAgo(ago),
    states: [state(0, "working"), { at: minutesAgo(ago), state: "finished" }],
    segments: [{ start: minutesAgo(ago + 3), end: minutesAgo(ago) }],
    ...over,
  });
}

describe("buildTree", () => {
  it("nests runs under their starters in dispatch order, and an orphan under main", () => {
    const tree = buildTree([
      run("main"),
      run("b", { parent: "a", dispatch_order: 2 }),
      run("a", { parent: "main", dispatch_order: 1 }),
      run("orphan", { parent: "ghost", dispatch_order: 3 }),
    ]);
    expect(tree).toHaveLength(2);
    const [main] = tree;
    expect(main?.children.map((c) => c.run.run_id)).toEqual(["a"]);
    expect(main?.children[0]?.children.map((c) => c.run.run_id)).toEqual(["b"]);
    expect(tree[1]?.run.run_id).toBe("orphan");
  });

  it("breaks a cycle instead of looping", () => {
    const tree = buildTree([run("main"), run("a", { parent: "b" }), run("b", { parent: "a" })]);
    expect(tree.length).toBeGreaterThan(0);
  });
});

describe("rows", () => {
  it("lists runs in dispatch order, nested, with the labels and the main row", () => {
    const answer = timeline({
      runs: [
        run("main"),
        run("lead", { agent: "deep-reasoner", dispatch_order: 1 }),
        run("s1", { agent: "scout", label_n: 1, parent: "lead", dispatch_order: 2, depth: 2 }),
        run("s2", { agent: "scout", label_n: 2, parent: "lead", dispatch_order: 3, depth: 2 }),
      ],
    });
    const rows = runsOf(buildLaneItems(answer, context(answer)));
    expect(rows.map((r) => [r.name, r.depth])).toEqual([
      ["Main session", 0],
      ["deep-reasoner", 1],
      ["scout", 2],
      ["scout 2", 2],
    ]);
    expect(rows[0]).toMatchObject({ model: "opus", modelLabel: "Opus 5.5", effortLabel: "high" });
  });

  it("words the state, the age and the tokens with cache reads", () => {
    const answer = timeline({
      runs: [
        run("main", {
          last_request: new Date(now - 2000).toISOString(),
          tokens: 4000,
          cum: [{ tokens: 4000, cache_read: 6000, cost: 1 }],
        }),
        child("w", "main", 1, 6, {
          cum: [{ tokens: 100, cache_read: 900, cost: 0.1 }],
          tokens: 100,
        }),
      ],
    });
    const [main, worker] = runsOf(buildLaneItems(answer, context(answer)));
    expect(main).toMatchObject({
      stateWord: "Working",
      ageLine: "Last request 2 s ago",
      tokens: "10K",
      reachesNow: true,
    });
    expect(worker).toMatchObject({
      stateWord: "Finished",
      ageLine: "Ran 3 min",
      tokens: "1K",
      reachesNow: false,
    });
  });

  it("fractions segments and round marks of the axis, rounds from the second on", () => {
    const answer = timeline({
      runs: [
        run("main", {
          rounds: [
            { n: 1, at: minutesAgo(30), last_request: minutesAgo(20), by: null, by_kind: null },
            { n: 2, at: minutesAgo(15), last_request: NOW, by: null, by_kind: null },
          ],
          segments: [
            { start: minutesAgo(30), end: minutesAgo(20) },
            { start: minutesAgo(15), end: NOW },
          ],
        }),
      ],
    });
    const [main] = runsOf(buildLaneItems(answer, context(answer)));
    expect(main?.segments[0]?.start).toBeCloseTo(0);
    expect(main?.segments[0]?.end).toBeCloseTo(10 / 30);
    expect(main?.segments[1]?.end).toBeCloseTo(1);
    expect(main?.rounds).toEqual([{ at: expect.closeTo(0.5) as number, label: "Round 2" }]);
  });

  it("marks an unlinked run from parent_state", () => {
    const answer = timeline({
      runs: [
        run("main"),
        run("w", {
          dispatch_order: 1,
          parent_known: false,
          parent_state: "waiting",
          parent_at: null,
        }),
        run("n", {
          dispatch_order: 2,
          parent_known: false,
          parent_state: "unknown",
          parent_at: null,
        }),
        run("k", { dispatch_order: 3 }),
      ],
    });
    const rows = runsOf(buildLaneItems(answer, context(answer)));
    expect(rows.map((r) => r.unlinked)).toEqual([
      null,
      { kind: "may", label: "Finding starter" },
      { kind: "never", label: "No starter found" },
      null,
    ]);
  });

  it("rings a row that moved", () => {
    const answer = timeline({ runs: [run("main"), run("w", { dispatch_order: 1 })] });
    const rows = runsOf(buildLaneItems(answer, context(answer, { moved: new Set(["w"]) })));
    expect(rows.map((r) => r.moved)).toEqual([false, true]);
  });

  it("writes the cost cell for priced, partly priced and unpriced runs", () => {
    const answer = timeline({
      runs: [
        run("main", { cost: 3.1 }),
        run("a", {
          dispatch_order: 1,
          cost: 0.97,
          unpriced: { requests: 2, models: ["Fable 5.1"] },
        }),
        run("b", {
          dispatch_order: 2,
          cost: null,
          unpriced: { requests: 4, models: ["Fable 5.1"] },
        }),
        run("c", { dispatch_order: 3, cost: 1234.5 }),
      ],
    });
    const rows = runsOf(buildLaneItems(answer, context(answer)));
    expect(rows.map((r) => r.cost)).toEqual([
      { kind: "cost", text: "$3.10" },
      { kind: "least", text: "at least $0.97" },
      { kind: "none", text: "No price", full: "No price for Fable 5.1" },
      { kind: "cost", text: "$1,235" },
    ]);
  });
});

describe("the indent cap", () => {
  const chain = timeline({
    runs: [
      run("main"),
      run("a", { agent: "a", parent: "main", dispatch_order: 1 }),
      run("b", { agent: "b", parent: "a", dispatch_order: 2 }),
      run("c", { agent: "c", parent: "b", dispatch_order: 3 }),
      run("d", { agent: "d", parent: "c", dispatch_order: 4 }),
      run("e", { agent: "e", parent: "d", dispatch_order: 5 }),
    ],
  });

  it("caps at 3 at 1440 and says who started a deeper row", () => {
    const rows = runsOf(buildLaneItems(chain, context(chain)));
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2, 3, DEPTH_CAP_DESKTOP, DEPTH_CAP_DESKTOP]);
    expect(rows.map((r) => r.startedBy)).toEqual([
      undefined,
      undefined,
      undefined,
      undefined,
      "Started by c",
      "Started by d",
    ]);
  });

  it("caps at 2 at 375", () => {
    const rows = runsOf(buildLaneItems(chain, context(chain, { desktop: false })));
    expect(rows.map((r) => r.depth)).toEqual([
      0,
      1,
      2,
      DEPTH_CAP_PHONE,
      DEPTH_CAP_PHONE,
      DEPTH_CAP_PHONE,
    ]);
    expect(rows.map((r) => r.startedBy)).toEqual([
      undefined,
      undefined,
      undefined,
      "Started by b",
      "Started by c",
      "Started by d",
    ]);
  });
});

describe("the fold rule", () => {
  /** A lead with six children, four of them finished long ago and two recent or working. */
  function many(): Timeline {
    return timeline({
      runs: [
        run("main"),
        run("lead", { agent: "deep-reasoner", dispatch_order: 1 }),
        child("w1", "lead", 2, 20),
        child("w2", "lead", 3, 18),
        child("w3", "lead", 4, 15, {
          states: [state(0, "working"), { at: minutesAgo(15), state: "finished" }],
        }),
        child("w4", "lead", 5, 12),
        child("w5", "lead", 6, 1),
        run("w6", { agent: "fast-worker", label_n: 6, parent: "lead", dispatch_order: 7 }),
      ],
    });
  }

  it("folds finished subtrees under a parent with more than four children", () => {
    const answer = many();
    const items = buildLaneItems(answer, context(answer));
    const fold = items.find((item): item is LaneFold => item.kind === "fold");
    expect(fold).toMatchObject({
      label: "4 finished earlier",
      expanded: false,
      toggleLabel: "Show",
    });
    expect(runsOf(items).map((r) => r.name)).toEqual([
      "Main session",
      "deep-reasoner",
      "fast-worker 5",
      "fast-worker 6",
    ]);
    expect(fold?.controls.split(" ")).toHaveLength(4);
  });

  it("never folds a working run or one that finished in the last 2 minutes", () => {
    const answer = many();
    const names = runsOf(buildLaneItems(answer, context(answer))).map((r) => r.name);
    expect(names).toContain("fast-worker 5");
    expect(names).toContain("fast-worker 6");
  });

  it("shows the folded rows after the fold row when it is open, and toggles", () => {
    const answer = many();
    const toggled: string[] = [];
    const items = buildLaneItems(
      answer,
      context(answer, {
        expanded: new Set(["lead"]),
        onToggle: (id) => toggled.push(id),
      }),
    );
    const at = items.findIndex((item) => item.kind === "fold");
    expect(
      items.slice(at + 1, at + 5).map((item) => (item.kind === "run" ? item.name : "")),
    ).toEqual(["fast-worker", "fast-worker 2", "fast-worker 3", "fast-worker 4"]);
    const fold = items[at] as LaneFold;
    expect(fold).toMatchObject({ expanded: true, toggleLabel: "Hide" });
    fold.onToggle();
    expect(toggled).toEqual(["lead"]);
  });

  it("does not fold under a parent with four children or fewer", () => {
    const answer = timeline({
      runs: [
        run("main"),
        child("a", "main", 1, 30),
        child("b", "main", 2, 30),
        child("c", "main", 3, 30),
        child("d", "main", 4, 30),
      ],
    });
    expect(buildLaneItems(answer, context(answer)).some((item) => item.kind === "fold")).toBe(
      false,
    );
  });

  it("folds a subtree only when every run in it is finished and quiet", () => {
    const answer = timeline({
      runs: [
        run("main"),
        child("a", "main", 1, 30),
        child("b", "main", 2, 30),
        child("c", "main", 3, 30),
        child("d", "main", 4, 30),
        child("e", "main", 5, 30),
        run("under", { agent: "x", parent: "e", dispatch_order: 6 }),
      ],
    });
    const fold = buildLaneItems(answer, context(answer)).find(
      (item): item is LaneFold => item.kind === "fold",
    );
    expect(fold?.label).toBe("4 finished earlier");
  });
});

describe("the lane axis", () => {
  it("puts Now at the right edge while running, and nowhere once ended", () => {
    const answer = timeline();
    expect(buildLane(answer, context(answer)).axis.nowFrac).toBe(1);
    const ended = timeline({
      session: { ...answer.session, state: "ended", running: false },
    });
    expect(buildLane(ended, context(ended)).axis.nowFrac).toBeNull();
  });
});

describe("the age line and the ended session", () => {
  const timed = (lastSecondsAgo: number): Timeline =>
    timeline({
      runs: [run("main", { last_request: new Date(now - lastSecondsAgo * 1000).toISOString() })],
    });
  const age = (answer: Timeline): string =>
    runsOf(buildLaneItems(answer, context(answer)))[0]?.ageLine ?? "";

  it("reads in seconds under a minute and whole minutes from a minute up", () => {
    expect(age(timed(59))).toBe("Last request 59 s ago");
    expect(age(timed(60))).toBe("Last request 1 min ago");
    expect(age(timed(610))).toBe("Last request 10 min ago");
  });

  it("shows every run as Finished with its run time once the session has ended", () => {
    const answer = timeline({
      session: sessionOf({ running: false, state: "ended" }),
      runs: [
        run("main", { state: "idle", first_request: minutesAgo(12), last_request: minutesAgo(1) }),
      ],
    });
    const [main] = runsOf(buildLaneItems(answer, context(answer)));
    expect(main).toMatchObject({ state: "finished", stateWord: "Finished", ageLine: "Ran 11 min" });
  });
});
