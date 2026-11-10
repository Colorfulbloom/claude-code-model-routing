import { act, cleanup, renderHook } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigationType } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { Timeline } from "@/api/types";
import {
  axisMaxMinute,
  clampMinute,
  pageStep,
  parseAt,
  precisionOf,
  replayMode,
  replayTime,
  summaryAt,
  useReplay,
} from "@/lib/replay";
import { NOW, sessionOf, START, timeline } from "@/test/timelines";

afterEach(cleanup);

const ms = (text: string): number => Date.parse(text);
const iso = (minutes: number): string => new Date(ms(START) + minutes * 60_000).toISOString();

/** The default answer, stretched or squeezed to an axis of `minutes` minutes. */
function axisOf(minutes: number, bucketSeconds = 60, over: Partial<Timeline> = {}): Timeline {
  const base = timeline();
  return {
    ...base,
    axis: { ...base.axis, end: iso(minutes), bucket_seconds: bucketSeconds },
    ...over,
  };
}

describe("axisMaxMinute and clampMinute", () => {
  it("counts whole minutes from the axis start to its end", () => {
    expect(axisMaxMinute(timeline())).toBe(30);
    expect(axisMaxMinute(axisOf(25.5))).toBe(25);
    expect(axisMaxMinute(axisOf(0))).toBe(0);
  });

  it("ends an ended session in the minute of its last request, not the bucket edge after it", () => {
    // The axis closes at minute 31, one bucket past the last request at 30 minutes 20 seconds.
    const ended = axisOf(31, 60, {
      session: sessionOf({ running: false, state: "ended", last_request: iso(30.33) }),
    });
    expect(axisMaxMinute(ended)).toBe(30);
    // A running session still ends where its axis ends.
    expect(axisMaxMinute(axisOf(31))).toBe(31);
  });

  it("clamps into [0, max] and floors", () => {
    expect(clampMinute(-4, 30)).toBe(0);
    expect(clampMinute(12.9, 30)).toBe(12);
    expect(clampMinute(31, 30)).toBe(30);
    expect(clampMinute(Number.NaN, 30)).toBe(30);
  });
});

describe("parseAt", () => {
  it("reads a minute and clamps one past the axis silently", () => {
    expect(parseAt("12", 30)).toBe(12);
    expect(parseAt("12.7", 30)).toBe(12);
    expect(parseAt("999", 30)).toBe(30);
    expect(parseAt("-3", 30)).toBe(0);
  });

  it("gives null for a missing or unusable value, which means the end", () => {
    expect(parseAt(null, 30)).toBeNull();
    expect(parseAt("", 30)).toBeNull();
    expect(parseAt("soon", 30)).toBeNull();
    expect(parseAt("Infinity", 30)).toBeNull();
  });
});

describe("pageStep", () => {
  it("is 5 minutes up to 300 seconds a bucket", () => {
    expect(pageStep(60)).toBe(5);
    expect(pageStep(120)).toBe(5);
    expect(pageStep(300)).toBe(5);
  });

  it("is one bucket once buckets are wider than 5 minutes", () => {
    expect(pageStep(360)).toBe(6);
    expect(pageStep(600)).toBe(10);
    expect(pageStep(900)).toBe(15);
  });
});

describe("replayMode", () => {
  it("is whole at the end and at before it", () => {
    expect(replayMode(30, 30)).toBe("whole");
    expect(replayMode(31, 30)).toBe("whole");
    expect(replayMode(29, 30)).toBe("at");
    expect(replayMode(0, 0)).toBe("whole");
  });
});

describe("precisionOf", () => {
  it("is exact at 60 second buckets", () => {
    expect(precisionOf(axisOf(30, 60))).toEqual({ held: false, bucketMinutes: 1 });
  });

  it("holds between bucket ends above 60 seconds and returns the bucket minutes", () => {
    expect(precisionOf(axisOf(120, 120))).toEqual({ held: true, bucketMinutes: 2 });
    expect(precisionOf(axisOf(300, 600))).toEqual({ held: true, bucketMinutes: 10 });
  });
});

describe("replayTime", () => {
  it("is the minute's instant before the end", () => {
    expect(replayTime(timeline(), 10, 30)).toBe(ms(START) + 10 * 60_000);
  });

  it("reaches the answer's own time at the end", () => {
    expect(replayTime(axisOf(25.5), 25, 25)).toBe(ms(NOW));
  });
});

describe("summaryAt", () => {
  it("counts runs by state and sums the cost so far at a minute", () => {
    const at0 = summaryAt(timeline(), 0);
    expect(at0.mode).toBe("at");
    expect(at0.runs).toEqual({ working: 1, idle: 0, finished: 0, notStarted: 1, total: 2 });
    expect(at0.cost).toBeCloseTo(0);
    const at10 = summaryAt(timeline(), 10);
    expect(at10.runs.working).toBe(2);
    expect(at10.runs.notStarted).toBe(0);
    // Bucket 9 has ended: main 10 x 0.1 plus the lead 9 x 0.05.
    expect(at10.cost).toBeCloseTo(1.45);
    expect(at10.tokens).toBe(1000 + 450);
  });

  it("is whole at the end and counts the open last bucket", () => {
    const whole = summaryAt(timeline(), 30);
    expect(whole.mode).toBe("whole");
    expect(whole.cost).toBeCloseTo(3.1 + 1.5);
  });

  it("counts finished and idle runs from the run states", () => {
    const base = timeline();
    const [main, lead] = base.runs;
    if (main === undefined || lead === undefined) throw new Error("fixture has two runs");
    const answer: Timeline = {
      ...base,
      runs: [
        {
          ...main,
          states: [
            { at: iso(0), state: "working" },
            { at: iso(6), state: "idle" },
          ],
        },
        {
          ...lead,
          states: [
            { at: iso(1), state: "working" },
            { at: iso(4), state: "finished" },
          ],
        },
      ],
    };
    expect(summaryAt(answer, 8).runs).toEqual({
      working: 0,
      idle: 1,
      finished: 1,
      notStarted: 0,
      total: 2,
    });
    expect(summaryAt(answer, 8).session).toBe("working");
  });

  it("is null in cost when nothing is priced", () => {
    const base = timeline();
    const answer: Timeline = {
      ...base,
      runs: base.runs.map((run) => ({
        ...run,
        cum: run.cum.map((cum) => ({ ...cum, cost: null })),
      })),
    };
    expect(summaryAt(answer, 10).cost).toBeNull();
  });
});

function mountReplay(url: string, initial: Timeline | undefined) {
  return renderHook(
    ({ answer }: { answer: Timeline | undefined }) => {
      const replay = useReplay(answer);
      const location = useLocation();
      const navigation = useNavigationType();
      return { replay, search: location.search, navigation };
    },
    {
      initialProps: { answer: initial },
      wrapper: ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={[url]}>{children}</MemoryRouter>
      ),
    },
  );
}

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("expected a value");
  return value;
}

describe("useReplay", () => {
  it("is null until the answer arrives", () => {
    const { result } = mountReplay("/s", undefined);
    expect(result.current.replay).toBeNull();
  });

  it("sits at the end in whole mode when the link has no at", () => {
    const { result } = mountReplay("/s?range=7d", timeline());
    const replay = need(result.current.replay);
    expect(replay.minute).toBe(30);
    expect(replay.max).toBe(30);
    expect(replay.mode).toBe("whole");
    expect(replay.atEnd).toBe(true);
    expect(replay.precision).toEqual({ held: false, bucketMinutes: 1 });
    expect(replay.step).toBe(5);
  });

  it("reads ?at= as a minute from the axis start, in at mode", () => {
    const { result } = mountReplay("/s?at=12", timeline());
    const replay = need(result.current.replay);
    expect(replay.minute).toBe(12);
    expect(replay.mode).toBe("at");
    expect(replay.at).toBe(ms(START) + 12 * 60_000);
    expect(replay.values.at).toBe(replay.at);
    expect(replay.summary.mode).toBe("at");
  });

  it("clamps an at past the axis to the end and drops it from the URL without a message", () => {
    const { result } = mountReplay("/s?range=7d&at=900", timeline());
    const replay = need(result.current.replay);
    expect(replay.minute).toBe(30);
    expect(replay.mode).toBe("whole");
    expect(result.current.search).toBe("?range=7d");
    expect(result.current.navigation).toBe("REPLACE");
  });

  it("drops an at that is not a number", () => {
    const { result } = mountReplay("/s?at=soon", timeline());
    expect(need(result.current.replay).minute).toBe(30);
    expect(result.current.search).toBe("");
  });

  it("writes at with history replace and keeps the other params", () => {
    const { result } = mountReplay("/s?range=90d", timeline());
    act(() => {
      need(result.current.replay).setMinute(7);
    });
    expect(result.current.search).toBe("?range=90d&at=7");
    expect(result.current.navigation).toBe("REPLACE");
    expect(need(result.current.replay).minute).toBe(7);
  });

  it("moves by arrow and by page step, and clamps at both ends", () => {
    const { result } = mountReplay("/s?at=12", timeline());
    act(() => {
      need(result.current.replay).move(1);
    });
    expect(need(result.current.replay).minute).toBe(13);
    act(() => {
      need(result.current.replay).page(-1);
    });
    expect(need(result.current.replay).minute).toBe(8);
    act(() => {
      need(result.current.replay).page(-1);
    });
    act(() => {
      need(result.current.replay).page(-1);
    });
    expect(need(result.current.replay).minute).toBe(0);
    expect(result.current.search).toBe("?at=0");
  });

  it("pages by the bucket on a long session", () => {
    const long = axisOf(120, 600);
    const { result } = mountReplay("/s?at=20", long);
    expect(need(result.current.replay).step).toBe(10);
    act(() => {
      need(result.current.replay).page(1);
    });
    expect(need(result.current.replay).minute).toBe(30);
    expect(need(result.current.replay).precision).toEqual({ held: true, bucketMinutes: 10 });
  });

  it("goes to the start, and to the end by removing at", () => {
    const { result } = mountReplay("/s?at=12", timeline());
    act(() => {
      need(result.current.replay).toStart();
    });
    expect(result.current.search).toBe("?at=0");
    act(() => {
      need(result.current.replay).toEnd();
    });
    expect(result.current.search).toBe("");
    expect(need(result.current.replay).mode).toBe("whole");
  });

  it("removes at when the line is moved to the end", () => {
    const { result } = mountReplay("/s?at=12", timeline());
    act(() => {
      need(result.current.replay).setMinute(30);
    });
    expect(result.current.search).toBe("");
    act(() => {
      need(result.current.replay).setMinute(500);
    });
    expect(result.current.search).toBe("");
  });

  it("follows a growing axis while the line sits at the end", () => {
    const { result, rerender } = mountReplay("/s", timeline());
    expect(need(result.current.replay).minute).toBe(30);
    rerender({ answer: axisOf(35) });
    expect(need(result.current.replay).minute).toBe(35);
    expect(need(result.current.replay).mode).toBe("whole");
  });

  it("stays where the owner put it once moved, and goes back to following on Back to now", () => {
    const { result, rerender } = mountReplay("/s", timeline());
    act(() => {
      need(result.current.replay).setMinute(10);
    });
    rerender({ answer: axisOf(35) });
    expect(need(result.current.replay).minute).toBe(10);
    expect(need(result.current.replay).mode).toBe("at");
    expect(need(result.current.replay).max).toBe(35);
    act(() => {
      need(result.current.replay).toEnd();
    });
    expect(need(result.current.replay).minute).toBe(35);
    rerender({ answer: axisOf(40) });
    expect(need(result.current.replay).minute).toBe(40);
  });
});
