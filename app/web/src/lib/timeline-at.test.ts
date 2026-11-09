import { describe, expect, it } from "vitest";
import {
  bucketIndexAt,
  parentAt,
  roundsAt,
  runStateAt,
  sessionStateAt,
  totalsAt,
  valuesAt,
} from "@/lib/timeline-at";
import { NOW, run, sessionOf, START, state, timeline } from "@/test/timelines";

const ms = (text: string): number => Date.parse(text);
const minute = (n: number): number => ms(START) + n * 60_000;

describe("runStateAt", () => {
  const r = run("scout", {
    first_request: new Date(minute(5)).toISOString(),
    states: [state(5, "working"), state(8, "idle"), state(12, "finished")],
  });

  it("is not started before the first request", () => {
    expect(runStateAt(r, minute(4))).toBe("not_started");
  });

  it("follows states[] at each time", () => {
    expect(runStateAt(r, minute(5))).toBe("working");
    expect(runStateAt(r, minute(7))).toBe("working");
    expect(runStateAt(r, minute(8))).toBe("idle");
    expect(runStateAt(r, minute(12))).toBe("finished");
    expect(runStateAt(r, minute(30))).toBe("finished");
  });
});

describe("sessionStateAt", () => {
  const s = sessionOf({ states: [state(0, "working"), state(10, "idle"), state(40, "ended")] });

  it("reads the session history", () => {
    expect(sessionStateAt(s, minute(-1))).toBe("not_started");
    expect(sessionStateAt(s, minute(5))).toBe("working");
    expect(sessionStateAt(s, minute(20))).toBe("idle");
    expect(sessionStateAt(s, minute(41))).toBe("ended");
  });
});

describe("parentAt", () => {
  const linked = run("scout", {
    parent: "deep-reasoner",
    parent_known: true,
    parent_at: new Date(minute(12)).toISOString(),
    first_request: new Date(minute(5)).toISOString(),
    states: [state(5, "working"), state(12, "finished")],
  });

  it("knows the starter only from parent_at on", () => {
    expect(parentAt(linked, minute(11))).toEqual({
      parent: "main",
      known: false,
      state: "waiting",
    });
    expect(parentAt(linked, minute(12))).toEqual({
      parent: "deep-reasoner",
      known: true,
      state: "known",
    });
  });

  it("settles to unknown 5 minutes after an unlinked run finished", () => {
    const never = {
      ...linked,
      parent_at: null,
      parent_known: false,
      parent_state: "unknown" as const,
    };
    expect(parentAt(never, minute(13))).toEqual({ parent: "main", known: false, state: "waiting" });
    expect(parentAt(never, minute(17)).state).toBe("unknown");
    expect(parentAt(never, minute(10)).state).toBe("waiting");
  });

  it("never moves main", () => {
    expect(parentAt(run("main"), minute(0))).toEqual({ parent: null, known: true, state: "known" });
  });
});

describe("roundsAt", () => {
  const r = run("scout", {
    rounds: [
      {
        n: 1,
        at: new Date(minute(0)).toISOString(),
        last_request: new Date(minute(4)).toISOString(),
        by: null,
        by_kind: null,
      },
      {
        n: 2,
        at: new Date(minute(10)).toISOString(),
        last_request: new Date(minute(14)).toISOString(),
        by: "main",
        by_kind: "coordinator",
      },
    ],
  });

  it("lists the rounds that started by T", () => {
    expect(roundsAt(r, minute(9)).map((x) => x.n)).toEqual([1]);
    expect(roundsAt(r, minute(10)).map((x) => x.n)).toEqual([1, 2]);
  });

  it("clamps a round still going to T", () => {
    const [first, second] = roundsAt(r, minute(12));
    expect(first?.lastRequest).toBe(minute(4));
    expect(second?.lastRequest).toBe(minute(12));
  });
});

describe("cumulative values", () => {
  const t = timeline();

  it("picks the last fully ended bucket inside the answer", () => {
    expect(bucketIndexAt(t, minute(-1))).toBe(-1);
    expect(bucketIndexAt(t, minute(0) + 30_000)).toBe(-1);
    expect(bucketIndexAt(t, minute(1))).toBe(0);
    expect(bucketIndexAt(t, minute(10))).toBe(9);
    expect(bucketIndexAt(t, minute(10) + 59_000)).toBe(9);
  });

  it("reports the open bucket at the answer's own time", () => {
    expect(bucketIndexAt(t, ms(NOW))).toBe(30);
    expect(bucketIndexAt(t, ms(NOW) + 5000)).toBe(30);
  });

  it("sums the runs", () => {
    const totals = totalsAt(t, minute(10));
    // main 100 per bucket, the lead 50 per bucket, 9 + 10 buckets ended
    expect(totals.tokens).toBe(10 * 100 + 9 * 50);
    expect(totals.cache_read).toBe(10 * 400 + 9 * 200);
    expect(totalsAt(t, minute(0)).tokens).toBe(0);
  });

  it("keeps a null cost null and adds the priced ones", () => {
    const base = timeline();
    const unpriced = timeline({
      runs: base.runs.map((r, index) => ({
        ...r,
        cum: r.cum.map((c) => ({ ...c, cost: index === 0 ? null : c.cost })),
      })),
    });
    expect(totalsAt(unpriced, minute(10)).cost).toBeCloseTo(9 * 0.05);
    const none = timeline({
      runs: base.runs.map((r) => ({ ...r, cum: r.cum.map((c) => ({ ...c, cost: null })) })),
    });
    expect(totalsAt(none, minute(10)).cost).toBeNull();
  });
});

describe("valuesAt", () => {
  it("gathers states, parents and numbers at one T", () => {
    const t = timeline({
      runs: [
        run("main", { cum: timeline().runs[0]?.cum ?? [] }),
        run("scout", {
          parent: "main",
          first_request: new Date(minute(5)).toISOString(),
          parent_at: new Date(minute(12)).toISOString(),
          states: [state(5, "working"), state(12, "finished")],
        }),
      ],
    });
    const early = valuesAt(t, minute(8));
    expect(early.runs.map((r) => [r.runId, r.state, r.parentKnown])).toEqual([
      ["main", "working", true],
      ["scout", "working", false],
    ]);
    const late = valuesAt(t, minute(20));
    expect(late.runs[1]).toMatchObject({ state: "finished", parent: "main", parentKnown: true });
    expect(late.session).toBe("working");
  });
});
