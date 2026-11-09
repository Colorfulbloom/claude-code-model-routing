import { describe, expect, it } from "vitest";
import { axisFor, buildChart, clockTicks, frac, niceTicks, tickLabel } from "@/lib/live-chart";
import { bucket, NOW, sessionOf, START, timeline } from "@/test/timelines";

const now = Date.parse(NOW);

describe("axisFor", () => {
  it("ends at Now while running, drawn at the share of the open bucket that has passed", () => {
    const answer = timeline({
      buckets: [bucket(0), bucket(1)],
      axis: { ...timeline().axis, end: new Date(Date.parse(START) + 90_000).toISOString() },
    });
    const axis = axisFor(answer, Date.parse(START) + 90_000);
    expect(axis.endMs).toBe(Date.parse(START) + 90_000);
    expect(axis.openFrac).toBeCloseTo(0.5);
    expect(axis.running).toBe(true);
  });

  it("lets Now run past the answer, but never past the open bucket", () => {
    const answer = timeline({
      buckets: [bucket(0), bucket(1)],
      axis: { ...timeline().axis, end: new Date(Date.parse(START) + 70_000).toISOString() },
    });
    expect(axisFor(answer, Date.parse(START) + 100_000).openFrac).toBeCloseTo(40 / 60);
    expect(axisFor(answer, Date.parse(START) + 10 * 60_000).openFrac).toBe(1);
  });

  it("has no open bucket once the session has ended", () => {
    const answer = timeline({ session: sessionOf({ running: false, state: "ended" }) });
    expect(axisFor(answer, now).openFrac).toBeNull();
    expect(axisFor(answer, now).endMs).toBe(Date.parse(answer.axis.end));
  });
});

describe("frac", () => {
  it("holds times to the axis", () => {
    const axis = axisFor(timeline(), now);
    expect(frac(axis, Date.parse(START))).toBe(0);
    expect(frac(axis, now)).toBe(1);
    expect(frac(axis, now + 1000)).toBe(1);
    expect(frac(axis, Date.parse(START) - 1000)).toBe(0);
    expect(frac(axis, Date.parse(START) + 15 * 60_000)).toBeCloseTo(0.5);
  });
});

describe("clockTicks", () => {
  const start = Date.parse("2026-11-09T18:10:00Z");
  const min = (n: number): number => start + n * 60_000;

  it("labels every 5 minutes on a half hour, leaving the right edge to Now", () => {
    const ticks = clockTicks(start, min(30), 60, []);
    expect(ticks).toEqual([0, 5, 10, 15, 20, 25].map(min));
  });

  it("does not count a mark that sits on the right edge, where Now goes", () => {
    expect(clockTicks(start, min(30) + 1000, 60, [])).toEqual([0, 5, 10, 15, 20, 25].map(min));
    expect(clockTicks(start, min(30), 60, [])).not.toContain(min(30));
  });

  it("widens the step when five minutes would give more than six labels", () => {
    expect(clockTicks(start, min(50), 60, [])).toEqual([0, 10, 20, 30, 40].map(min));
  });

  it("falls back to the server's ticks when no step fits", () => {
    expect(clockTicks(start, start + 400 * 86_400_000, 3600, ["2026-11-10T00:00:00Z"])).toEqual([
      Date.parse("2026-11-10T00:00:00Z"),
    ]);
  });
});

describe("buildChart", () => {
  it("keeps the chart on new tokens and builds the ticks, labels and legend totals", () => {
    const answer = timeline();
    const chart = buildChart(answer, axisFor(answer, now));
    expect(chart.axisLabel).toBe("New tokens per minute");
    expect(chart.bars).toHaveLength(31);
    expect(chart.bars[0]?.byModel).toEqual({ opus: 1000 });
    // two ticks from the tallest bar, which is the open one: 1000 tokens in the first 1% of a minute
    expect(chart.yTicks).toEqual([
      { value: 50000, label: "50K" },
      { value: 100000, label: "100K" },
    ]);
    // six clock labels from 22:10 to 22:35, then Now where the 22:40 tick would be
    expect(chart.xLabels).toHaveLength(7);
    expect(chart.xLabels[1]?.frac).toBeCloseTo(5 / 30);
    expect(chart.xLabels[0]?.label).toMatch(/^\d{1,2}:\d{2}$/);
    expect(chart.xLabels.at(-1)).toEqual({ frac: 1, label: "Now" });
    expect(chart.legend).toEqual([{ model: "opus", label: "Opus 5.5", total: "31K" }]);
  });

  it("draws the last bucket open while the session runs, at its share of the minute", () => {
    const answer = timeline({
      axis: {
        ...timeline().axis,
        end: new Date(Date.parse(START) + 30 * 60_000 + 15_000).toISOString(),
      },
    });
    const axis = axisFor(answer, Date.parse(START) + 30 * 60_000 + 15_000);
    const chart = buildChart(answer, axis);
    const last = chart.bars.at(-1);
    expect(last).toMatchObject({ open: true });
    expect(last?.openFrac).toBeCloseTo(0.25);
    // 1000 new tokens in a quarter of a minute is a rate of 4000 a minute
    expect(last?.byModel.opus).toBeCloseTo(4000);
    expect(chart.bars[0]?.open).toBeUndefined();
  });

  it("draws no open bucket once the session has ended", () => {
    const answer = timeline({ session: sessionOf({ running: false, state: "ended" }) });
    const chart = buildChart(answer, axisFor(answer, now));
    expect(chart.bars.some((bar) => bar.open === true)).toBe(false);
    expect(chart.xLabels.some((l) => l.label === "Now")).toBe(false);
  });

  it("averages per minute past 60 seconds and says so", () => {
    const answer = timeline({
      axis: { ...timeline().axis, bucket_seconds: 600 },
      buckets: [
        bucket(0, { by_model: { "claude-opus-5-5": 6000 } }),
        bucket(10, { by_model: { "claude-opus-5-5": 3000 } }),
      ],
      session: sessionOf({ running: false, state: "ended" }),
    });
    const chart = buildChart(answer, axisFor(answer, now));
    expect(chart.axisLabel).toBe("New tokens per minute, averaged over 10 minutes");
    expect(chart.bars.map((bar) => bar.byModel.opus)).toEqual([600, 300]);
    expect(chart.yTicks.map((tick) => tick.value)).toEqual(niceTicks(600));
  });

  it("averages the open bucket over the time it has run", () => {
    const end = new Date(Date.parse(START) + 15 * 60_000).toISOString();
    const answer = timeline({
      axis: { ...timeline().axis, bucket_seconds: 600, end },
      buckets: [
        bucket(0, { by_model: { "claude-opus-5-5": 6000 } }),
        bucket(10, { by_model: { "claude-opus-5-5": 5000 } }),
      ],
    });
    const chart = buildChart(answer, axisFor(answer, Date.parse(end)));
    expect(chart.bars[1]).toMatchObject({ open: true });
    expect(chart.bars[1]?.openFrac).toBeCloseTo(0.5);
    // 5000 tokens over 5 minutes
    expect(chart.bars[1]?.byModel.opus).toBeCloseTo(1000);
  });

  it("merges two models of one family and names them by family", () => {
    const answer = timeline({
      models: [
        { model: "claude-opus-4-8", tokens: 2000 },
        { model: "claude-opus-5-5", tokens: 3000 },
        { model: "claude-haiku-5-5", tokens: 500 },
      ],
    });
    expect(buildChart(answer, axisFor(answer, now)).legend).toEqual([
      { model: "opus", label: "Opus", total: "5K" },
      { model: "haiku", label: "Haiku 5.5", total: "500" },
    ]);
  });
});

describe("niceTicks and tickLabel", () => {
  it("gives two ticks, 1, 2 or 5 times a power of ten", () => {
    expect(niceTicks(0)).toEqual([]);
    expect(niceTicks(90)).toEqual([50, 100]);
    expect(niceTicks(600)).toEqual([500, 1000]);
    expect(niceTicks(40_000)).toEqual([20_000, 40_000]);
  });

  it("labels short axes with hours and minutes and long ones with hours", () => {
    const at = (h: number, m: number): number => new Date(2026, 9, 30, h, m).getTime();
    expect(tickLabel(at(18, 15), 60, false)).toBe("6:15");
    expect(tickLabel(at(9, 0), 600, true)).toBe("9 AM");
    expect(tickLabel(at(10, 0), 600, false)).toBe("10");
    expect(tickLabel(at(12, 0), 600, false)).toBe("12 PM");
    expect(tickLabel(at(13, 0), 600, false)).toBe("1");
  });
});
