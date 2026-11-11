import { describe, expect, it } from "vitest";
import type { CostChart, ReviewSession } from "@/api/types";
import {
  agentName,
  buildCostChart,
  buildMoney,
  buildSessionGroups,
  buildTopSessions,
  chartWindowLabel,
  earlierWindowLabel,
  kindHelpValues,
  laterWindowLabel,
  rangeUnit,
  sharePercent,
} from "@/lib/review-cards";
import { costChart, reviewWindow, sessionRow, summary } from "@/test/review";

const TZ = "America/New_York";
const NO_UNPRICED = { requests: 0, models: [] as string[] };
const ids = {
  opus: "claude-opus-5-5",
  fable: "claude-fable-5-1",
  haiku: "claude-haiku-5-5",
};

/** Midnight in New York on a date, for November 2026 (EDT until the first, EST after). */
const midnight = (date: string): string => `${date}T0${date <= "2026-11-01" ? 4 : 5}:00:00Z`;

function part(cost: number | null, requests = 3, unpriced = NO_UNPRICED) {
  return {
    cost,
    kinds: { input: 1, output: 2, cache_read: 3, cache_write: 4 },
    requests,
    unpriced,
  };
}

function dayBar(date: string, next: string, parts: Record<string, ReturnType<typeof part>>) {
  return {
    start: midnight(date),
    end: midnight(next),
    by_model: parts,
    unpriced: NO_UNPRICED,
    open: false,
    holds_oldest: false,
    no_records: false,
  };
}

function thirtyDays(over: Partial<CostChart> = {}): CostChart {
  const bars = Array.from({ length: 4 }, (_, i) => {
    const day = String(6 + i).padStart(2, "0");
    const next = String(7 + i).padStart(2, "0");
    return dayBar(`2026-11-${day}`, `2026-11-${next}`, {
      [ids.fable]: part(10),
      [ids.opus]: part(2),
    });
  });
  return costChart({
    bars,
    legend: [
      { model: ids.opus, cost: 8, requests: 12, unpriced: NO_UNPRICED },
      { model: ids.fable, cost: 40, requests: 12, unpriced: NO_UNPRICED },
    ],
    chart: {
      start: midnight("2026-11-06"),
      end: "2026-11-09T15:00:00Z",
      unit: "day",
      has_earlier: true,
      has_later: false,
      earlier_reason: null,
      later_reason: "newest",
      newest: true,
    },
    y_ticks: [10, 20],
    ...over,
  });
}

describe("units", () => {
  it("picks the unit a range starts on", () => {
    expect(["today", "7d", "30d", "90d", "12m", "all"].map((r) => rangeUnit(r as never))).toEqual([
      "hour",
      "day",
      "day",
      "week",
      "month",
      "week",
    ]);
  });
});

describe("the cost chart", () => {
  it("builds bars by model family, the legend in catalog order and the image label", () => {
    const view = buildCostChart(thirtyDays());
    expect(view.heading).toBe("Cost per day");
    expect(view.bars).toHaveLength(4);
    expect(view.bars[0]?.byModel).toEqual({ fable: 10, opus: 2 });
    expect(view.legend).toEqual([
      { model: "opus", label: "Opus 5.5", total: "$8.00" },
      { model: "fable", label: "Fable 5.1", total: "$40.00" },
    ]);
    expect(view.summary).toBe(
      "Bar chart of cost per day for November 6 to November 9, $48.00 in all, most of it on Fable 5.1",
    );
    expect(view.yTicks).toEqual([
      { value: 10, label: "$10" },
      { value: 20, label: "$20" },
    ]);
  });

  it("totals the kinds, biggest first, with no pattern fields on the bars", () => {
    const view = buildCostChart(
      thirtyDays({ kinds: { input: 5, output: 9, cache_read: 1, cache_write: 7 } }),
    );
    expect(view.kinds.map((k) => [k.label, k.total])).toEqual([
      ["Output", "$9.00"],
      ["Cache write", "$7.00"],
      ["Input", "$5.00"],
      ["Cache read", "$1.00"],
    ]);
    expect(view.bars.every((bar) => bar.kinds === undefined)).toBe(true);
  });

  it("hands the help entry each kind total under its ref, as the Made of line shows it", () => {
    const view = buildCostChart(
      thirtyDays({ kinds: { input: 5, output: 9, cache_read: 1, cache_write: 7 } }),
    );
    expect(kindHelpValues(view.kinds)).toEqual({
      k_input: "$5.00",
      k_output: "$9.00",
      k_cread: "$1.00",
      k_cwrite: "$7.00",
    });
  });

  it("labels the x axis at the first and last bars", () => {
    const view = buildCostChart(thirtyDays());
    expect(view.xLabels[0]).toEqual({ frac: 0, label: "Nov 6" });
    expect(view.xLabels.at(-1)).toEqual({ frac: 1, label: "Nov 9" });
  });

  it("describes an empty window", () => {
    const view = buildCostChart(thirtyDays({ bars: [], legend: [], y_ticks: [] }));
    expect(view.hasCost).toBe(false);
    expect(view.summary).toBe("Bar chart for November 6 to November 9 with no cost to show");
  });

  it("says at least for a total with unpriced requests, and a stub for an all-unpriced part", () => {
    const unpriced = { requests: 4, models: [ids.fable] };
    const bar = dayBar("2026-11-09", "2026-11-10", {
      [ids.opus]: part(2),
      [ids.fable]: part(null, 4, unpriced),
    });
    const view = buildCostChart(
      thirtyDays({
        bars: [bar],
        legend: [
          { model: ids.opus, cost: 2, requests: 3, unpriced: NO_UNPRICED },
          { model: ids.fable, cost: 6, requests: 9, unpriced },
          {
            model: ids.haiku,
            cost: null,
            requests: 2,
            unpriced: { requests: 2, models: [ids.haiku] },
          },
        ],
        unpriced: { requests: 6, models: [ids.fable, ids.haiku] },
      }),
    );
    expect(view.bars[0]?.byModel).toEqual({ opus: 2, fable: null });
    expect(view.legend.map((entry) => entry.total)).toEqual([
      "$2.00",
      "No price",
      "at least $6.00",
    ]);
    expect(view.summary).toContain("at least $8.00 in all");
    expect(view.kinds[0]?.total.startsWith("at least ")).toBe(true);
    expect(view.unpricedLines).toEqual([
      "4 requests on Fable 5.1 have no price, so they're left out of these bars.",
      "2 requests on Haiku 5.5 have no price, so they're left out of these bars.",
    ]);
  });

  it("marks the open bucket, a clipped bucket and a bucket before the records", () => {
    const hourStart = "2026-11-09T14:00:00Z";
    const open = {
      ...dayBar("2026-11-09", "2026-11-10", { [ids.opus]: part(1) }),
      start: hourStart,
      end: "2026-11-09T14:30:00Z",
      open: true,
    };
    const clipped = {
      ...dayBar("2026-11-08", "2026-11-09", { [ids.opus]: part(1) }),
      start: "2026-11-08T20:00:00Z",
      end: "2026-11-08T21:00:00Z",
    };
    const none = { ...dayBar("2026-11-07", "2026-11-08", {}), no_records: true };
    const view = buildCostChart(
      thirtyDays({
        bars: [none, clipped, open],
        chart: { ...thirtyDays().chart, unit: "hour", newest: true },
      }),
    );
    expect(view.bars[2]).toMatchObject({ open: true, openFrac: 0.5 });
    expect(view.bars[1]?.partial).toBeUndefined();
    expect(view.bars[0]?.noRecords).toBe("No records before August 1");
  });

  describe("today by hour", () => {
    /** Hourly bars from `from` for `count` hours, the last one open and half through. */
    function hours(from: string, count: number) {
      return Array.from({ length: count }, (_, i) => {
        const start = new Date(Date.parse(from) + i * 3_600_000).toISOString();
        const open = i === count - 1;
        return {
          ...dayBar("2026-11-09", "2026-11-10", { [ids.opus]: part(1) }),
          start,
          end: open
            ? new Date(Date.parse(start) + 1_800_000).toISOString()
            : new Date(Date.parse(start) + 3_600_000).toISOString(),
          open,
        };
      });
    }

    const todayChart = (bars: ReturnType<typeof hours>, start: string, newest = true) =>
      thirtyDays({
        bars,
        legend: [{ model: ids.opus, cost: bars.length, requests: 3, unpriced: NO_UNPRICED }],
        chart: { ...thirtyDays().chart, unit: "hour", start, newest },
      });

    it("draws the whole day, with the hours after now as empty slots", () => {
      // Midnight to 9:30 AM in New York: ten hourly bars, the last open.
      const view = buildCostChart(
        todayChart(hours("2026-11-09T05:00:00Z", 10), midnight("2026-11-09")),
      );
      expect(view.bars).toHaveLength(24);
      expect(view.bars.slice(0, 10).every((bar) => bar.future === undefined)).toBe(true);
      expect(view.bars.slice(10).every((bar) => bar.future === true)).toBe(true);
      expect(view.bars.slice(10).every((bar) => Object.keys(bar.byModel).length === 0)).toBe(true);
      expect(view.bars[9]).toMatchObject({ open: true, openFrac: 0.5 });
      expect(view.nowLabel).toBe("Now");
    });

    it("labels 12 AM, 6 AM, 12 PM, 6 PM and 11 PM", () => {
      const view = buildCostChart(
        todayChart(hours("2026-11-09T05:00:00Z", 10), midnight("2026-11-09")),
      );
      expect(view.xLabels.map((label) => label.label)).toEqual([
        "12 AM",
        "6 AM",
        "12 PM",
        "6 PM",
        "11 PM",
      ]);
      expect(view.xLabels[0]?.frac).toBe(0);
      expect(view.xLabels.at(-1)?.frac).toBe(1);
    });

    it("leaves the legend total as the answer's, so it still equals the Cost tile", () => {
      const view = buildCostChart(
        todayChart(hours("2026-11-09T05:00:00Z", 10), midnight("2026-11-09")),
      );
      expect(view.legend).toEqual([{ model: "opus", label: "Opus 5.5", total: "$10.00" }]);
    });

    it("pads a 25 hour day to 25 slots", () => {
      // November 1, 2026 is the fall-back day. Midnight is 04:00Z, and the day ends at 05:00Z the next day.
      const view = buildCostChart(
        todayChart(hours("2026-11-01T04:00:00Z", 7), midnight("2026-11-01")),
      );
      expect(view.bars).toHaveLength(25);
    });

    it("pads nothing on an earlier day, which the server sends whole, and draws no marker", () => {
      const view = buildCostChart(
        todayChart(hours("2026-11-08T05:00:00Z", 10), midnight("2026-11-08"), false),
      );
      expect(view.bars).toHaveLength(10);
      expect(view.nowLabel).toBeUndefined();
    });

    it("pads nothing when the last hour of the day is open", () => {
      const view = buildCostChart(
        todayChart(hours("2026-11-09T05:00:00Z", 24), midnight("2026-11-09")),
      );
      expect(view.bars).toHaveLength(24);
    });
  });

  it("marks a bar that holds the oldest record as partial", () => {
    const bar = {
      ...dayBar("2026-11-08", "2026-11-09", { [ids.opus]: part(1) }),
      holds_oldest: true,
    };
    const view = buildCostChart(thirtyDays({ bars: [bar] }));
    expect(view.bars[0]?.partial).toBe(true);
  });

  it("keeps the DST day with 25 hours whole", () => {
    const bar = dayBar("2026-11-01", "2026-11-02", { [ids.opus]: part(1) });
    const view = buildCostChart(thirtyDays({ bars: [bar] }));
    expect(view.bars[0]?.partial).toBeUndefined();
  });

  it("labels months with the year on the first bar and January", () => {
    const months = ["2025-12-01", "2026-01-01", "2026-02-01"].map((date) => ({
      ...dayBar(date, date, { [ids.opus]: part(1) }),
      start: `${date}T05:00:00Z`,
      end: `${date}T05:00:00Z`,
    }));
    const view = buildCostChart(
      thirtyDays({ bars: months, chart: { ...thirtyDays().chart, unit: "month" } }),
    );
    expect(view.xLabels.map((label) => label.label)).toEqual(["Dec 2025", "Jan 2026", "Feb"]);
    expect(view.heading).toBe("Cost per month");
  });
});

describe("the pager windows", () => {
  const chart = thirtyDays().chart;

  it("words the newest window and one earlier and later", () => {
    expect(chartWindowLabel(chart, TZ)).toBe("November 6 to November 9");
    expect(earlierWindowLabel(chart, TZ)).toBe("November 2 to November 5");
    const back = {
      ...chart,
      start: midnight("2026-11-02"),
      end: midnight("2026-11-06"),
      newest: false,
    };
    expect(chartWindowLabel(back, TZ)).toBe("November 2 to November 5");
    expect(laterWindowLabel(back, TZ, "2026-11-09")).toBe("November 6 to November 9");
  });

  it("says Today to the time on the newest hourly window and the date on an older one", () => {
    const hourly = { ...chart, unit: "hour" as const, start: midnight("2026-11-09") };
    expect(chartWindowLabel(hourly, TZ)).toMatch(/^Today to 10:00\sAM$/);
    const older = {
      ...hourly,
      newest: false,
      start: midnight("2026-11-08"),
      end: midnight("2026-11-09"),
    };
    expect(chartWindowLabel(older, TZ)).toBe("November 8");
    expect(earlierWindowLabel(older, TZ)).toBe("November 7");
  });

  it("words months by month and year", () => {
    const months = { ...chart, unit: "month" as const, start: "2025-11-10T05:00:00Z" };
    expect(chartWindowLabel(months, TZ)).toBe("November 2025 to November 2026");
  });
});

describe("where the money went", () => {
  it("scales the bar to the biggest row and words the share", () => {
    const answer = summary({
      money: [
        {
          agent: "builder",
          model: ids.fable,
          cost: 75,
          share: 0.75,
          requests: 9,
          unpriced: NO_UNPRICED,
        },
        {
          agent: "@main",
          model: ids.opus,
          cost: 20,
          share: 0.2,
          requests: 4,
          unpriced: NO_UNPRICED,
        },
        {
          agent: "@unnamed",
          model: null,
          cost: 0.4,
          share: 0.004,
          requests: 1,
          unpriced: NO_UNPRICED,
        },
      ],
    });
    const rows = buildMoney(answer);
    expect(rows.map((row) => [row.name, row.value, row.percent])).toEqual([
      ["builder", "$75.00", "75%"],
      ["Main session", "$20.00", "20%"],
      ["Unnamed agent", "$0.40", "<1%"],
    ]);
    expect(rows[0]?.fill).toBe(1);
    expect(rows[1]?.fill).toBeCloseTo(0.2667, 3);
    expect(rows[0]?.modelName).toBe("Fable 5.1");
    expect(rows[2]?.modelName).toBeNull();
  });

  it("shows at least for unpriced requests and no bar or percent for a row with no price", () => {
    const answer = summary({
      money: [
        {
          agent: "builder",
          model: ids.fable,
          cost: 5,
          share: 1,
          requests: 9,
          unpriced: { requests: 2, models: [ids.fable] },
        },
        {
          agent: "scout",
          model: ids.haiku,
          cost: null,
          share: null,
          requests: 2,
          unpriced: { requests: 2, models: [ids.haiku] },
        },
      ],
    });
    const rows = buildMoney(answer);
    expect(rows[0]?.value).toBe("at least $5.00");
    expect(rows[1]).toMatchObject({ value: "No price", fill: null, percent: undefined });
  });

  it("names the special agent keys and words small shares", () => {
    expect(agentName("@main")).toBe("Main session");
    expect(agentName("@unnamed")).toBe("Unnamed agent");
    expect(agentName("reviewer")).toBe("reviewer");
    expect(sharePercent(0.004)).toBe("<1%");
    expect(sharePercent(0.456)).toBe("46%");
  });
});

describe("session rows", () => {
  const end = "2026-11-09T15:00:00Z";
  const at = (iso: string, over: Partial<ReviewSession> = {}) =>
    sessionRow(iso, { started: iso, last_request: iso, ...over });

  it("groups by day as Today, Yesterday and a date, and shows only the time", () => {
    const groups = buildSessionGroups(
      [
        { day: "2026-11-09", sessions: [at("2026-11-09T14:10:00Z", { branch: "feature/x" })] },
        { day: "2026-11-08", sessions: [at("2026-11-08T20:00:00Z")] },
        { day: "2026-11-05", sessions: [at("2026-11-05T17:00:00Z")] },
      ],
      TZ,
      end,
    );
    expect(groups.map((g) => g.label)).toEqual(["Today", "Yesterday", "November 5"]);
    expect(groups[0]?.rows[0]?.when).toMatch(/^9:10\sAM$/);
    expect(groups[0]?.rows[0]?.branch).toBe("feature/x");
    expect(groups[1]?.rows[0]?.branch).toBe("No git branch");
    expect(groups[1]?.rows[0]?.branchMuted).toBe(true);
  });

  it("shows the date of a session that began before the range, under the range's first day", () => {
    const groups = buildSessionGroups(
      [
        {
          day: "2026-11-05",
          sessions: [at("2026-11-03T17:00:00Z", { started_before_range: true, cost: 2.5 })],
        },
      ],
      TZ,
      end,
    );
    expect(groups[0]?.rows[0]).toMatchObject({ startedEarlier: true, cost: "$2.50" });
    expect(groups[0]?.rows[0]?.when).toMatch(/^November 3, 12:00\sPM$/);
  });

  it("scales the cost bars to the biggest and words unpriced and missing costs", () => {
    const groups = buildSessionGroups(
      [
        {
          day: "2026-11-09",
          sessions: [
            at("2026-11-09T14:00:00Z", { cost: 8 }),
            at("2026-11-09T13:00:00Z", { cost: 2, unpriced: { requests: 1, models: [ids.fable] } }),
            at("2026-11-09T12:00:00Z", { cost: null }),
          ],
        },
      ],
      TZ,
      end,
    );
    const rows = groups[0]?.rows ?? [];
    expect(rows.map((row) => row.cost)).toEqual(["$8.00", "at least $2.00", "No price"]);
    expect(rows.map((row) => row.fill)).toEqual([1, 0.25, 0]);
  });

  it("lists the top sessions with a date unless they began today, and names agents", () => {
    const rows = buildTopSessions(
      [at("2026-11-09T14:00:00Z", { agents: ["@main", "scout"] }), at("2026-11-02T14:00:00Z")],
      TZ,
      end,
    );
    expect(rows[0]?.when).toMatch(/^9:00\sAM$/);
    expect(rows[0]?.agents).toEqual(["Main session", "scout"]);
    expect(rows[1]?.when).toMatch(/^November 2, 9:00\sAM$/);
  });
});

describe("the window helper default", () => {
  it("builds with the shared test window", () => {
    expect(reviewWindow().tz).toBe(TZ);
  });
});
