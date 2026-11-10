import { describe, expect, it } from "vitest";
import {
  addDays,
  buildSummaryTiles,
  dateLabel,
  daysBetween,
  oldestLabel,
  rangeLabel,
  rangeNoun,
  rangePhrase,
  rangeWindow,
  subLine,
  timeIn,
} from "@/lib/review-view";
import { reviewWindow, summary } from "@/test/review";
import type { Summary } from "@/api/types";

// T is 2026-11-09 10:00 in New York. A 30 day window starts at midnight on October 11.
const W30 = reviewWindow({
  start: "2026-10-11T04:00:00Z",
  prior_start: "2026-09-11T04:00:00Z",
  prior_end: "2026-10-11T04:00:00Z",
  oldest: "2026-08-01T12:00:00Z",
});

function withTiles(over: Partial<Summary["tiles"]>, rest: Partial<Summary> = {}): Summary {
  const base = summary();
  return { ...base, tiles: { ...base.tiles, ...over }, ...rest };
}

const labels = (answer: Summary): string[] => buildSummaryTiles(answer).map((tile) => tile.delta);

describe("dates", () => {
  it("does calendar arithmetic with no zone", () => {
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
    expect(daysBetween("2026-10-11", "2026-11-09")).toBe(30);
    expect(dateLabel("2026-10-11")).toBe("October 11");
    expect(dateLabel("2025-10-31", true)).toBe("October 31, 2025");
  });

  it("shows a clock time in the answer's zone", () => {
    expect(timeIn("2026-11-09T15:00:00Z", "America/New_York")).toMatch(/^10:00\sAM$/);
  });

  it("leaves the year off an oldest date in T's year", () => {
    expect(oldestLabel(W30)).toBe("August 1");
    expect(oldestLabel({ ...W30, oldest: "2025-12-01T12:00:00Z" })).toBe("December 1, 2025");
    expect(oldestLabel({ ...W30, oldest: null })).toBeNull();
  });
});

describe("range words", () => {
  it("words every preset and its window", () => {
    expect(rangeLabel("12m")).toBe("Last 12 months");
    expect(rangeWindow("today", W30)).toMatch(/^Midnight to 10:00\sAM$/);
    expect(rangeWindow("7d", W30)).toBe("November 3 to November 9");
    expect(rangeWindow("30d", W30)).toBe("October 11 to November 9");
    expect(rangeWindow("90d", W30)).toBe("August 12 to November 9");
    expect(rangeWindow("12m", W30)).toBe("November 10, 2025 to November 9, 2026");
    expect(rangeWindow("all", W30)).toBe("Since August 1");
  });

  it("gives a noun for the status line and a phrase for the empty card", () => {
    expect(rangeNoun("30d", W30)).toBe("the last 30 days");
    expect(rangeNoun("today", null)).toBe("today");
    expect(rangeNoun("all", W30)).toBe("everything since August 1");
    expect(rangeNoun("all", null)).toBe("All time");
    expect(rangePhrase("7d", W30)).toBe("in the last 7 days");
    expect(rangePhrase("12m", null)).toBe("in the last 12 months");
    expect(rangePhrase("all", W30)).toBe("since August 1");
  });
});

describe("the line under the title", () => {
  it("compares Today with yesterday by the same time", () => {
    expect(subLine("today", W30)).toMatch(
      /^Today to 10:00\sAM, compared with yesterday to 10:00\sAM$/,
    );
  });

  it("says the span and the prior length for a whole prior", () => {
    expect(subLine("30d", W30)).toBe("October 11 to November 9, compared with the 30 days before");
    expect(subLine("7d", { ...W30, start: "2026-11-03T05:00:00Z" })).toBe(
      "November 3 to November 9, compared with the 7 days before",
    );
  });

  it("says where the records start when the prior holds no records", () => {
    expect(subLine("30d", { ...W30, prior_partial: true, oldest: "2026-10-20T12:00:00Z" })).toBe(
      "October 11 to November 9. Records start on October 20, so there's nothing earlier to compare with.",
    );
  });

  it("still compares when the prior is partial but holds records", () => {
    // Records start September 20, inside the prior window, so the tiles compare and the line agrees.
    const line = subLine("30d", { ...W30, prior_partial: true, oldest: "2026-09-20T12:00:00Z" });
    expect(line).toBe("October 11 to November 9, compared with the 30 days before");
    expect(line).not.toMatch(/nothing earlier/);
  });

  it("says Today has nothing earlier when yesterday holds no records", () => {
    expect(subLine("today", { ...W30, oldest: "2026-11-09T12:00:00Z" })).toMatch(
      /^Today to 10:00\sAM\. Records start on November 9, so there's nothing earlier to compare with\.$/,
    );
  });

  it("says everything recorded for All", () => {
    expect(subLine("all", { ...W30, prior_start: null, prior_end: null })).toBe(
      "Everything recorded since August 1",
    );
  });
});

describe("tile deltas", () => {
  it("uses percent for cost, sessions and tokens, and points for the cache share", () => {
    expect(labels(summary())).toEqual([
      "Up 25% from $10.00",
      "Up 33% from 40",
      "Up 13% from 800K",
      "Up 10 points from 70%",
    ]);
  });

  it("says little change under 2 percent and under 1 point", () => {
    const answer = withTiles({
      cost: { ...summary().tiles.cost, change_pct: 0.01 },
      cache_share: { value: 0.8, prior: 0.798, change_abs: 0.002 },
    });
    expect(labels(answer)[0]).toBe("Little change from $10.00");
    expect(labels(answer)[3]).toBe("Little change from 80%");
  });

  it("says down with percent and points", () => {
    const answer = withTiles({
      sessions: { value: 30, prior: 40, change_pct: -0.25, change_abs: -10 },
      cache_share: { value: 0.6, prior: 0.7, change_abs: -0.1 },
    });
    expect(labels(answer)[1]).toBe("Down 25% from 40");
    expect(labels(answer)[3]).toBe("Down 10 points from 70%");
  });

  it("says only up or down from a partial prior that holds records, never a percent", () => {
    // Records start September 20, inside the prior window (September 11 to October 11).
    const answer = withTiles(
      {
        cost: { ...summary().tiles.cost, prior: 4, change_pct: null, change_abs: null },
        sessions: { value: 5, prior: 2, change_pct: null, change_abs: null },
        tokens: { value: 100, prior: 900, change_pct: null, change_abs: null },
        cache_share: { value: 0.8, prior: 0.7, change_abs: null },
      },
      { window: { ...W30, prior_partial: true, oldest: "2026-09-20T12:00:00Z" } },
    );
    expect(labels(answer)).toEqual(["Up from $4.00", "Up from 2", "Down from 900", "Up from 70%"]);
  });

  it("says the daily average, never Up from $0.00, when the prior holds no records", () => {
    // Records start October 20, after the prior window ended. The server sends a prior of 0.
    const answer = withTiles(
      {
        cost: { ...summary().tiles.cost, prior: 0, change_pct: null, change_abs: null },
        sessions: { value: 5, prior: 0, change_pct: null, change_abs: null },
        tokens: { value: 3_000_000, prior: 0, change_pct: null, change_abs: null },
        cache_share: { value: 0.8, prior: null, change_abs: null },
      },
      { window: { ...W30, prior_partial: true, oldest: "2026-10-20T12:00:00Z" } },
    );
    expect(labels(answer)).toEqual([
      "$0.42 a day on average",
      "0.2 a day on average",
      "100K a day on average",
      "Across the whole range",
    ]);
  });

  it("gives the cache tile the same rule as the others when the prior is empty", () => {
    const answer = withTiles(
      { cache_share: { value: 0.8, prior: 0, change_abs: 0.8 } },
      { window: { ...W30, prior_partial: true, oldest: "2026-10-20T12:00:00Z" } },
    );
    expect(labels(answer)[3]).toBe("Across the whole range");
  });

  it("compares Today with yesterday by the same time on all four tiles", () => {
    const answer = summary({ range: "today" });
    expect(labels(answer).every((line) => /yesterday by 10:00\sAM$/.test(line))).toBe(true);
    expect(labels(answer)[0]).toMatch(/^\$10\.00 yesterday by/);
  });

  it("says the daily average and the cache scope for a range with no prior", () => {
    const answer = withTiles(
      {
        cost: { ...summary().tiles.cost, prior: null, change_pct: null, change_abs: null },
        sessions: { value: 90, prior: null, change_pct: null, change_abs: null },
        tokens: { value: 90_000_000, prior: null, change_pct: null, change_abs: null },
        cache_share: { value: 0.8, prior: null, change_abs: null },
      },
      {
        range: "all",
        window: reviewWindow({
          start: "2026-09-10T04:00:00Z",
          prior_start: null,
          prior_end: null,
        }),
      },
    );
    expect(labels(answer)).toEqual([
      "$0.20 a day on average",
      "1.5 a day on average",
      "1.5M a day on average",
      "Across the whole range",
    ]);
  });

  it("reads the cache tile on Today with no yesterday as every request", () => {
    const answer = withTiles(
      { cache_share: { value: 0.8, prior: null, change_abs: null } },
      { range: "today" },
    );
    expect(labels(answer)[3]).toBe("Across every request");
  });

  it("puts at least on a cost with unpriced requests, with the count under it", () => {
    const base = summary();
    const answer = withTiles({
      cost: { ...base.tiles.cost, unpriced: { requests: 12, models: ["claude-fable-5-1"] } },
    });
    const [cost] = buildSummaryTiles(answer);
    expect(cost?.value).toBe("at least $12.50");
    expect(cost?.note).toBe("12 requests have no price");
    expect(cost?.qualifier).toBe("API-rate estimate");
  });

  it("reads a cost with no price as No price", () => {
    const answer = withTiles({
      cost: { ...summary().tiles.cost, value: null, change_pct: null, change_abs: null },
    });
    expect(buildSummaryTiles(answer)[0]?.value).toBe("No price");
  });
});
