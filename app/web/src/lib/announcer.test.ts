import { describe, expect, it } from "vitest";
import type { Timeline } from "@/api/types";
import { diffAnnouncements, ROW_LIMIT_MS } from "@/lib/announcer";
import { clockShort } from "@/lib/clock";
import { NOW, run, sessionOf, timeline } from "@/test/timelines";

const at = (seconds: number): string => new Date(Date.parse(NOW) + seconds * 1000).toISOString();

/** The same answer a number of seconds later, with the runs and session changed. */
function later(base: Timeline, seconds: number, over: Partial<Timeline> = {}): Timeline {
  return { ...base, server_time: at(seconds), ...over };
}

const lead = (over = {}) => run("deep-reasoner", { dispatch_order: 1, ...over });
const scout = (n: number, over = {}) =>
  run(`scout-${String(n)}`, { agent: "scout", label_n: n, dispatch_order: 1 + n, ...over });

describe("diffAnnouncements", () => {
  it("says nothing for a baseline", () => {
    const next = timeline();
    expect(diffAnnouncements(null, next, {})).toEqual({ lines: [], spoken: {}, held: {} });
  });

  it("says nothing when nothing changed", () => {
    const base = timeline({ runs: [run("main"), lead()] });
    expect(diffAnnouncements(base, later(base, 1), {}).lines).toEqual([]);
  });

  it("announces a start, with its starter when known", () => {
    const base = timeline({ runs: [run("main"), lead()] });
    const next = later(base, 5, {
      runs: [...base.runs, scout(1, { parent: "deep-reasoner" })],
    });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout started by deep-reasoner"]);
  });

  it("announces a start with no starter when it is unlinked", () => {
    const base = timeline({ runs: [run("main")] });
    const next = later(base, 5, {
      runs: [
        ...base.runs,
        scout(1, { parent_known: false, parent_state: "waiting", parent_at: null }),
      ],
    });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout started"]);
  });

  it("numbers a second run of one type", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const next = later(base, 5, { runs: [...base.runs, scout(2)] });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout 2 started by Main session"]);
  });

  it("announces a finish", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const next = later(base, 5, { runs: [run("main"), scout(1, { state: "finished" })] });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout finished"]);
  });

  it("never announces working to idle, or idle back to working", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const idle = later(base, 5, { runs: [run("main"), scout(1, { state: "idle" })] });
    expect(diffAnnouncements(base, idle, {}).lines).toEqual([]);
    expect(diffAnnouncements(idle, later(base, 70), {}).lines).toEqual([]);
  });

  it("announces a new round", () => {
    const base = timeline({ runs: [run("main"), scout(1, { state: "finished" })] });
    const rounds = [
      ...run("x").rounds,
      { n: 2, at: at(30), last_request: at(31), by: "main", by_kind: "coordinator" as const },
    ];
    const next = later(base, 31, { runs: [run("main"), scout(1, { rounds })] });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout started round 2"]);
  });

  it("batches several finishes in one poll into one line", () => {
    const base = timeline({ runs: [run("main"), scout(1), scout(2), scout(3)] });
    const done = (n: number) => scout(n, { state: "finished" });
    const next = later(base, 5, { runs: [run("main"), done(1), done(2), done(3)] });
    expect(diffAnnouncements(base, next, {}).lines).toEqual([
      "scout, scout 2 and scout 3 finished",
    ]);
  });

  it("folds the move under a starter into the finish line", () => {
    const base = timeline({
      runs: [
        run("main"),
        lead(),
        scout(1, { parent: "main", parent_known: false, parent_state: "waiting", parent_at: null }),
      ],
    });
    const next = later(base, 5, {
      runs: [run("main"), lead(), scout(1, { parent: "deep-reasoner", state: "finished" })],
    });
    expect(diffAnnouncements(base, next, {}).lines).toEqual([
      "scout finished, started by deep-reasoner",
    ]);
  });

  it("says nothing for a move on its own", () => {
    const base = timeline({
      runs: [
        run("main"),
        lead(),
        scout(1, {
          parent: "main",
          parent_known: false,
          parent_state: "waiting",
          parent_at: null,
          state: "finished",
        }),
      ],
    });
    const next = later(base, 5, {
      runs: [run("main"), lead(), scout(1, { parent: "deep-reasoner", state: "finished" })],
    });
    expect(diffAnnouncements(base, next, {}).lines).toEqual([]);
  });

  it("limits a row to one line a minute, by the answers' own time", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const started = later(base, 5, { runs: [run("main"), scout(1), scout(2)] });
    const first = diffAnnouncements(base, started, {});
    expect(first.lines).toEqual(["scout 2 started by Main session"]);
    const finished = later(base, 30, {
      runs: [run("main"), scout(1), scout(2, { state: "finished" })],
    });
    expect(diffAnnouncements(started, finished, first.spoken).lines).toEqual([]);
    const finishedLater = later(base, 5 + ROW_LIMIT_MS / 1000, {
      runs: [run("main"), scout(1), scout(2, { state: "finished" })],
    });
    expect(diffAnnouncements(started, finishedLater, first.spoken).lines).toEqual([
      "scout 2 finished",
    ]);
  });

  it("holds a line inside a row's minute and speaks it on the first poll after", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const started = later(base, 5, { runs: [run("main"), scout(1), scout(2)] });
    const first = diffAnnouncements(base, started, {});
    const done = [run("main"), scout(1), scout(2, { state: "finished" })];
    const finished = later(base, 30, { runs: done });
    const held = diffAnnouncements(started, finished, first.spoken, first.held);
    expect(held.lines).toEqual([]);
    expect(Object.keys(held.held)).toEqual(["scout-2"]);
    // Polls that answer unchanged diff the answer with itself, at the poll's own time.
    const quiet = diffAnnouncements(finished, finished, held.spoken, held.held, Date.parse(at(64)));
    expect(quiet.lines).toEqual([]);
    const out = diffAnnouncements(finished, finished, held.spoken, held.held, Date.parse(at(65)));
    expect(out.lines).toEqual(["scout 2 finished"]);
    expect(out.held).toEqual({});
    const again = diffAnnouncements(finished, finished, out.spoken, out.held, Date.parse(at(90)));
    expect(again.lines).toEqual([]);
  });

  it("keeps only the later of two held lines for one row, because it covers the first", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const started = later(base, 5, { runs: [run("main"), scout(1), scout(2)] });
    const first = diffAnnouncements(base, started, {});
    const rounds = [
      ...run("x").rounds,
      { n: 2, at: at(20), last_request: at(21), by: "main", by_kind: "coordinator" as const },
    ];
    const again = later(base, 21, { runs: [run("main"), scout(1), scout(2, { rounds })] });
    const heldRound = diffAnnouncements(started, again, first.spoken, first.held);
    expect(heldRound.held["scout-2"]?.kind).toBe("round");
    const done = later(base, 30, {
      runs: [run("main"), scout(1), scout(2, { rounds, state: "finished" })],
    });
    const heldFinish = diffAnnouncements(again, done, heldRound.spoken, heldRound.held);
    expect(heldFinish.held["scout-2"]?.kind).toBe("finish");
    const out = diffAnnouncements(
      done,
      later(done, 40),
      heldFinish.spoken,
      heldFinish.held,
      Date.parse(at(70)),
    );
    expect(out.lines).toEqual(["scout 2 finished"]);
  });

  it("drops a held finish that is no longer true when its minute ends", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const started = later(base, 5, { runs: [run("main"), scout(1), scout(2)] });
    const first = diffAnnouncements(base, started, {});
    const done = later(base, 30, {
      runs: [run("main"), scout(1), scout(2, { state: "finished" })],
    });
    const held = diffAnnouncements(started, done, first.spoken, first.held);
    const working = later(base, 66, { runs: [run("main"), scout(1), scout(2)] });
    const out = diffAnnouncements(done, working, held.spoken, held.held);
    expect(out.lines).toEqual([]);
    expect(out.held).toEqual({});
  });

  it("cancels a held ended line when the session comes back inside the minute", () => {
    const base = timeline({ runs: [run("main")] });
    const ended = later(base, 5, {
      session: sessionOf({ state: "ended", running: false, active: false, ended_at: at(0) }),
    });
    const first = diffAnnouncements(base, ended, {});
    expect(first.lines).toHaveLength(1);
    const back = later(base, 20);
    const heldBack = diffAnnouncements(ended, back, first.spoken, first.held);
    expect(heldBack.lines).toEqual([]);
    const gone = later(base, 30, { session: ended.session });
    const cancelled = diffAnnouncements(back, gone, heldBack.spoken, heldBack.held);
    expect(cancelled.held).toEqual({});
    expect(cancelled.lines).toEqual([]);
  });

  it("announces a run that shows up already finished as a finish", () => {
    const base = timeline({ runs: [run("main")] });
    const next = later(base, 5, { runs: [run("main"), scout(1, { state: "finished" })] });
    expect(diffAnnouncements(base, next, {}).lines).toEqual(["scout finished"]);
  });

  it("announces the session ending with its time, and coming back", () => {
    const base = timeline({ runs: [run("main")] });
    const endedAt = at(-5);
    const ended = later(base, 5, {
      session: sessionOf({ state: "ended", running: false, active: false, ended_at: endedAt }),
    });
    expect(diffAnnouncements(base, ended, {}).lines).toEqual([
      `Session ended at ${clockShort(endedAt)}`,
    ]);
    const back = later(base, 90);
    expect(diffAnnouncements(ended, back, {}).lines).toEqual(["Session is working again"]);
  });

  it("orders starts, rounds, finishes and the session line", () => {
    const base = timeline({ runs: [run("main"), scout(1)] });
    const next = later(base, 5, {
      runs: [run("main"), scout(1, { state: "finished" }), scout(2)],
      session: sessionOf({ state: "ended", running: false, ended_at: at(0) }),
    });
    expect(diffAnnouncements(base, next, {}).lines).toEqual([
      "scout 2 started by Main session",
      "scout finished",
      `Session ended at ${clockShort(at(0))}`,
    ]);
  });
});
