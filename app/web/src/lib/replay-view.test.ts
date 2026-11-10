import { describe, expect, it } from "vitest";
import type { Timeline } from "@/api/types";
import { clockShort } from "@/lib/clock";
import { axisFor } from "@/lib/live-chart";
import { buildReplayLane, foldId, laterId } from "@/lib/replay-lanes";
import type { Replay } from "@/lib/replay";
import {
  axisMaxMinute,
  pageStep,
  precisionOf,
  replayMode,
  replayTime,
  summaryAt,
} from "@/lib/replay";
import {
  buildReplayChart,
  buildReplayTiles,
  cacheShareAt,
  effectiveStates,
  heldMs,
  keysHint,
  lineLabel,
  precisionLabel,
  runCounts,
  settleLine,
  toEndLabel,
} from "@/lib/replay-view";
import { valuesAt } from "@/lib/timeline-at";
import { minuteAt, replaySession } from "@/test/replay-session";
import { sessionOf } from "@/test/timelines";

const ms = (text: string): number => Date.parse(text);
const dollars = (cost: number): string => "$" + cost.toFixed(2);

/** A replay at a minute, built the way useReplay builds it but with no router. */
function replayAt(timeline: Timeline, minute: number | null): Replay {
  const max = axisMaxMinute(timeline);
  const at = minute ?? max;
  const time = replayTime(timeline, at, max);
  const values = valuesAt(timeline, time);
  return {
    minute: at,
    max,
    mode: replayMode(at, max),
    atEnd: at >= max,
    step: pageStep(timeline.axis.bucket_seconds),
    at: time,
    values,
    summary: summaryAt(timeline, at),
    precision: precisionOf(timeline),
    setMinute: () => undefined,
    move: () => undefined,
    page: () => undefined,
    toStart: () => undefined,
    toEnd: () => undefined,
  };
}

const running = (timeline: Timeline): Timeline => ({
  ...timeline,
  session: sessionOf({
    state: "working",
    running: true,
    ended_at: null,
    started: timeline.session.started,
  }),
});

/** Minutes worked by bucket 24 (the last one that counts at minute 25). */
const WORKED_AT_25 = 25 + 24 + 3 + 3 + 3 + 5;

describe("the tiles at the line", () => {
  it("show the value at the line with the whole session under it", () => {
    const timeline = replaySession();
    const view = buildReplayTiles(timeline, replayAt(timeline, 25));
    const time = clockShort(ms(minuteAt(25)));
    expect(view.mode).toBe("at");
    expect(view.cost.label).toBe(`Spent by ${time}`);
    expect(view.tokens.label).toBe(`Tokens by ${time}`);
    expect(view.cache.label).toBe(`Read from cache by ${time}`);
    expect(view.runs.label).toBe(`Runs by ${time}`);
    expect(view.cost.value).toBe(dollars(WORKED_AT_25 * 0.01));
    expect(view.tokens.value).toBe("3K");
    expect(view.cost.delta).toMatch(/in the whole session$/);
    expect(view.tokens.delta).toMatch(/in the whole session$/);
    expect(view.cache.delta).toMatch(/for the whole session$/);
  });

  it("counts the runs that started and says how many work and how many start later", () => {
    const timeline = replaySession();
    const view = buildReplayTiles(timeline, replayAt(timeline, 25));
    // Started: main, lead, c1 to c4. Not started: c5 to c7 and the verifier.
    expect(view.runs.value).toBe("6");
    expect(view.runs.delta).toBe("3 working, 4 not started yet");
    expect(view.runs.working).toBe(3);
  });

  it("leaves out the not started count once every run has started", () => {
    const timeline = replaySession();
    const replay = replayAt(timeline, 58);
    const view = buildReplayTiles(timeline, replay);
    expect(view.runs.delta).toBe(`${String(runCounts(timeline, replay).working)} working`);
  });

  it("switches to Whole session so far at the end of a running session", () => {
    const timeline = running(replaySession());
    const view = buildReplayTiles(timeline, replayAt(timeline, null));
    expect(view.mode).toBe("sofar");
    expect(view.cost.label).toBe("Cost");
    expect(view.tokens.label).toBe("Tokens");
    expect(view.cost.delta).toBe("Whole session so far");
    expect(view.tokens.delta).toBe("Whole session so far");
    expect(view.cache.delta).toBe("Whole session so far");
    expect(view.runs.label).toBe("Runs");
    expect(view.runs.value).toBe("10");
  });

  it("switches to Whole session at the end of an ended session, with every run finished", () => {
    const timeline = replaySession();
    const view = buildReplayTiles(timeline, replayAt(timeline, null));
    expect(view.mode).toBe("whole");
    expect(view.cost.delta).toBe("Whole session");
    expect(view.cost.value).toBe(dollars(timeline.totals.cost ?? 0));
    expect(view.runs.value).toBe("10");
    expect(view.runs.delta).toBe("10 finished");
    expect(view.runs.finished).toBe(10);
    expect(view.runs.working).toBe(0);
  });

  it("holds the numbers at the last bucket end on a long session and keeps the line's time for runs", () => {
    const base = replaySession();
    // Ten minute buckets: 6 buckets over the hour, cumulative values at each end.
    const long: Timeline = {
      ...base,
      axis: { ...base.axis, bucket_seconds: 600 },
      buckets: base.buckets.filter((_, i) => i % 10 === 0),
      runs: base.runs.map((r) => ({ ...r, cum: r.cum.filter((_, i) => i % 10 === 9) })),
    };
    const replay = replayAt(long, 43);
    const view = buildReplayTiles(long, replay);
    expect(heldMs(long, replay)).toBe(ms(minuteAt(40)));
    expect(view.cost.label).toBe(`Spent by ${clockShort(ms(minuteAt(40)))}`);
    expect(view.runs.label).toBe(`Runs by ${clockShort(ms(minuteAt(43)))}`);
    expect(replay.step).toBe(10);
    expect(keysHint(replay)).toBe("Arrow keys move 1 minute, Page Up and Page Down move 10");
  });
});

describe("the cache share at the line", () => {
  it("is the answer's own hit rate at the end", () => {
    const timeline = replaySession();
    expect(cacheShareAt(timeline, replayAt(timeline, null))).toBe(timeline.totals.hit_rate);
  });

  it("holds the session's mix of input and writes among new tokens before the end", () => {
    const timeline = replaySession();
    const replay = replayAt(timeline, 25);
    const here = replay.values.totals;
    // Input and writes are half of the new tokens in this answer (0.3 plus 0.2 of 1.0).
    const expected = here.cache_read / (here.cache_read + here.tokens * 0.5);
    expect(cacheShareAt(timeline, replay)).toBeCloseTo(expected, 10);
  });

  it("is null before anything was read", () => {
    const timeline = replaySession();
    expect(cacheShareAt(timeline, replayAt(timeline, 0))).toBeNull();
  });
});

describe("the precision label", () => {
  it("is absent while every number is exact", () => {
    expect(precisionLabel(replayAt(replaySession(), 25))).toBeNull();
  });

  it("names the bucket minutes on a long session", () => {
    const base = replaySession();
    const long: Timeline = { ...base, axis: { ...base.axis, bucket_seconds: 600 } };
    expect(precisionLabel(replayAt(long, 25))).toBe(
      "On long sessions they update every 10 minutes, but runs update every minute.",
    );
  });
});

describe("the line's words", () => {
  it("reads the clock time, and Now at the end of a running session", () => {
    const ended = replaySession();
    expect(lineLabel(ended, replayAt(ended, 25))).toBe(clockShort(ms(minuteAt(25))));
    expect(lineLabel(ended, replayAt(ended, null))).toBe(clockShort(ms(minuteAt(60))));
    const live = running(ended);
    expect(lineLabel(live, replayAt(live, null))).toBe(`Now, ${clockShort(ms(minuteAt(60)))}`);
    expect(lineLabel(live, replayAt(live, 59))).toBe(clockShort(ms(minuteAt(59))));
  });

  it("names the button for the session's state", () => {
    expect(toEndLabel(running(replaySession()))).toBe("Back to now");
    expect(toEndLabel(replaySession())).toBe("Go to end");
  });
});

describe("the settle line", () => {
  it("gives the counts by run state and the cost so far", () => {
    const timeline = replaySession();
    expect(settleLine(timeline, replayAt(timeline, 25))).toBe(
      `At ${clockShort(ms(minuteAt(25)))}, 3 working, 3 finished and 4 not started yet. ${dollars(WORKED_AT_25 * 0.01)} spent so far.`,
    );
  });
});

describe("the chart at the line", () => {
  it("follows the line in its text alternative and its legend", () => {
    const timeline = replaySession();
    const axis = axisFor(timeline, ms(timeline.server_time));
    const early = buildReplayChart(timeline, replayAt(timeline, 10), axis);
    const late = buildReplayChart(timeline, replayAt(timeline, 40), axis);
    expect(early.summary).toBe(
      `Chart of new tokens per minute from ${clockShort(ms(minuteAt(0)))} to ${clockShort(ms(minuteAt(10)))}, 10K in all, most of them on Opus 5.5`,
    );
    expect(late.summary).toContain(`to ${clockShort(ms(minuteAt(40)))}, 40K in all`);
    expect(early.legend.map((entry) => entry.total)).toEqual(["6K", "4K"]);
  });

  it("says averaged over the bucket minutes on a long session", () => {
    const base = replaySession();
    const long: Timeline = {
      ...base,
      axis: { ...base.axis, bucket_seconds: 600 },
      buckets: base.buckets.filter((_, i) => i % 10 === 0),
    };
    const axis = axisFor(long, ms(long.server_time));
    const chart = buildReplayChart(long, replayAt(long, 43), axis);
    expect(chart.summary).toMatch(
      /^Chart of new tokens per minute, averaged over 10 minutes, from /,
    );
    expect(chart.axisLabel).toBe("New tokens per minute, averaged over 10 minutes");
  });

  it("puts the cut at the line and the fade at the end of the last counted bucket", () => {
    const timeline = replaySession();
    const axis = axisFor(timeline, ms(timeline.server_time));
    const chart = buildReplayChart(timeline, replayAt(timeline, 30), axis);
    expect(chart.cut).toBeCloseTo(0.5, 10);
    expect(chart.fade).toBeCloseTo(0.5, 10);
    const end = buildReplayChart(timeline, replayAt(timeline, null), axis);
    expect(end.cut).toBe(1);
    expect(end.fade).toBe(1);
  });
});

describe("effective run states", () => {
  it("reads every started run as finished at the end of an ended session", () => {
    const timeline = replaySession();
    const states = effectiveStates(timeline, replayAt(timeline, null));
    expect([...states.values()].every((state) => state === "finished")).toBe(true);
    const mid = effectiveStates(timeline, replayAt(timeline, 25));
    expect(mid.get("main")).toBe("working");
    expect(mid.get("c5")).toBe("not_started");
  });

  it("keeps the server's states at the end of a running session", () => {
    const timeline = running(replaySession());
    const states = effectiveStates(timeline, replayAt(timeline, null));
    expect(states.get("main")).toBe("working");
  });
});

describe("the lane at the line", () => {
  const context = (expanded: string[] = []) => ({
    axis: axisFor(replaySession(), ms(replaySession().server_time)),
    desktop: true,
    expanded: new Set(expanded),
    onToggle: () => undefined,
  });
  const names = (
    items: readonly { kind: string; name?: string; label?: string }[],
  ): (string | undefined)[] => items.map((item) => (item.kind === "fold" ? item.label : item.name));

  it("folds the runs that finished earlier and the ones that start later under a crowded parent", () => {
    const timeline = replaySession();
    const lane = buildReplayLane(timeline, replayAt(timeline, 25), context());
    expect(names(lane.items)).toEqual([
      "Main session",
      "deep-reasoner",
      "3 finished earlier",
      "c4",
      "3 start later",
      "verifier",
    ]);
    const later = lane.items.find((item) => item.kind === "fold" && item.later === true);
    if (later?.kind !== "fold") throw new Error("no later fold");
    expect(later.stateWord).toBe("Not started yet");
    expect(later.tokens).toBe("–");
    expect(later.toggleLabel).toBe("Show");
    expect(later.toggleAria).toBe("Show 3 runs that start later under deep-reasoner");
    expect(later.id).toBe(laterId("deep-reasoner"));
  });

  it("opens a fold and lists its runs, not started and with no numbers", () => {
    const timeline = replaySession();
    const lane = buildReplayLane(
      timeline,
      replayAt(timeline, 25),
      context([laterId("deep-reasoner"), foldId("deep-reasoner")]),
    );
    expect(names(lane.items)).toEqual([
      "Main session",
      "deep-reasoner",
      "3 finished earlier",
      "c1",
      "c2",
      "c3",
      "c4",
      "3 start later",
      "c5",
      "c6",
      "c7",
      "verifier",
    ]);
    const c5 = lane.items.find((item) => item.kind === "run" && item.name === "c5");
    if (c5?.kind !== "run") throw new Error("no c5");
    expect(c5.state).toBe("not_started");
    expect(c5.tokens).toBe("–");
    expect(c5.cost).toEqual({ kind: "cost", text: "–" });
    const hide = lane.items.find((item) => item.kind === "fold" && item.later === true);
    if (hide?.kind !== "fold") throw new Error("no fold");
    expect(hide.toggleAria).toBe("Hide 3 runs that start later under deep-reasoner");
  });

  it("does not fold a parent with four children or fewer", () => {
    const base = replaySession();
    const few: Timeline = {
      ...base,
      runs: base.runs.filter((r) => !["c5", "c6", "c7"].includes(r.run_id)),
    };
    const lane = buildReplayLane(few, replayAt(few, 25), context());
    expect(lane.items.some((item) => item.kind === "fold")).toBe(false);
  });

  it("gives a working row its start, a finished row its run time and the numbers at the line", () => {
    const timeline = replaySession();
    const lane = buildReplayLane(
      timeline,
      replayAt(timeline, 25),
      context([foldId("deep-reasoner")]),
    );
    const main = lane.items.find((item) => item.kind === "run" && item.name === "Main session");
    if (main?.kind !== "run") throw new Error("no main");
    expect(main.state).toBe("working");
    expect(main.ageLine).toBe(`Since ${clockShort(ms(minuteAt(0)))}`);
    // 25 minutes of work: 250 new tokens and 1,000 cache reads, 1,250 in all.
    expect(main.tokens).toBe("1K");
    expect(main.cost).toEqual({ kind: "cost", text: "$0.25" });
    const c1 = lane.items.find((item) => item.kind === "run" && item.name === "c1");
    if (c1?.kind !== "run") throw new Error("no c1");
    expect(c1.state).toBe("finished");
    expect(c1.ageLine).toBe("Ran 3 min");
  });

  it("hangs a run whose starter is not known yet under main with the unlinked badge", () => {
    const base = replaySession();
    const answer: Timeline = {
      ...base,
      runs: base.runs.map((r) =>
        r.run_id === "c4" ? { ...r, parent_at: minuteAt(29), parent_state: "waiting" as const } : r,
      ),
    };
    const lane = buildReplayLane(answer, replayAt(answer, 25), context());
    const c4 = lane.items.find((item) => item.kind === "run" && item.name === "c4");
    if (c4?.kind !== "run") throw new Error("no c4");
    expect(c4.unlinked?.kind).toBe("may");
    expect(c4.depth).toBe(1);
    const order = names(lane.items);
    expect(order.indexOf("c4")).toBeGreaterThan(order.indexOf("deep-reasoner"));
  });

  it("reads an unlinked run as No starter found once the session has ended", () => {
    const base = replaySession();
    const answer: Timeline = {
      ...base,
      runs: base.runs.map((r) =>
        r.run_id === "c4"
          ? {
              ...r,
              parent_at: null,
              last_request: minuteAt(58),
              states: [
                { at: minuteAt(20), state: "working" as const },
                { at: minuteAt(58), state: "finished" as const },
              ],
            }
          : r,
      ),
    };
    const find = (replay: Replay) => {
      const lane = buildReplayLane(answer, replay, context([foldId("deep-reasoner")]));
      const c4 = lane.items.find((item) => item.kind === "run" && item.name === "c4");
      if (c4?.kind !== "run") throw new Error("no c4");
      return c4.unlinked;
    };
    // At minute 59 the session still runs and c4 finished a minute ago, so its starter may come.
    expect(find(replayAt(answer, 59))?.kind).toBe("may");
    // At the end the session is over, so no starter can still arrive.
    expect(find(replayAt(answer, null))).toEqual({ kind: "never", label: "No starter found" });
  });

  it("counts an idle row's last request from the line, not from the line itself", () => {
    const base = replaySession();
    const answer: Timeline = {
      ...base,
      runs: base.runs.map((r) =>
        r.run_id === "c4"
          ? {
              ...r,
              states: [
                { at: minuteAt(20), state: "working" as const },
                { at: minuteAt(21), state: "idle" as const },
                { at: minuteAt(27), state: "working" as const },
                { at: minuteAt(30), state: "finished" as const },
              ],
            }
          : r,
      ),
    };
    const lane = buildReplayLane(answer, replayAt(answer, 24), context([foldId("deep-reasoner")]));
    const c4 = lane.items.find((item) => item.kind === "run" && item.name === "c4");
    if (c4?.kind !== "run") throw new Error("no c4");
    expect(c4.state).toBe("idle");
    // Idle began at minute 21, so the last request was at minute 20, four minutes before the line.
    expect(c4.ageLine).toBe("Last request 4 min ago");
  });

  it("puts the cut at the line and draws no open bar", () => {
    const timeline = replaySession();
    const lane = buildReplayLane(timeline, replayAt(timeline, 30), context());
    expect(lane.cut).toBeCloseTo(0.5, 10);
    expect(lane.axis.nowFrac).toBeNull();
    expect(buildReplayLane(timeline, replayAt(timeline, null), context()).cut).toBe(1);
  });

  it("reads a run finished at the end of an ended session, with its run time", () => {
    const timeline = replaySession();
    const lane = buildReplayLane(timeline, replayAt(timeline, null), context());
    const main = lane.items.find((item) => item.kind === "run" && item.name === "Main session");
    if (main?.kind !== "run") throw new Error("no main");
    expect(main.state).toBe("finished");
    expect(main.stateWord).toBe("Finished");
    expect(main.ageLine).toBe("Ran 60 min");
  });
});
