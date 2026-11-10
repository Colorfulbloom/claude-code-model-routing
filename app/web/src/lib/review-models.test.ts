import { describe, expect, it } from "vitest";
import { reviewWindow } from "@/test/review";
import { IDS } from "@/test/review-fixtures";
import { kindRow, modelRow, modelsAnswer } from "@/test/review-tables";
import {
  KIND_ORDER,
  buildKindLegend,
  buildKindRows,
  buildModelRows,
  kindsImageLabel,
  phoneLine,
  windowText,
} from "@/lib/review-models";

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

describe("the table rows", () => {
  it("name each model, with its cost, share, tokens, cache share and agents", () => {
    const [fable] = buildModelRows(modelsAnswer());
    expect(fable).toMatchObject({
      name: "Fable 5.1",
      family: "fable",
      cost: "$241.92",
      percent: "76%",
      tokens: "58.7M",
      cache: "79%",
      usedBy: ["builder", "Unnamed agent"],
    });
  });

  it("scales each bar to the biggest cost", () => {
    const rows = buildModelRows(modelsAnswer());
    expect(rows[0]?.fill).toBe(1);
    expect(rows[1]?.fill).toBeCloseTo(62.61 / 241.92);
  });

  it("reads a share under one percent as <1%", () => {
    expect(buildModelRows(modelsAnswer())[2]?.percent).toBe("<1%");
  });

  it("keeps a model with no price, with No price, no share and no bar", () => {
    const sonnet = buildModelRows(modelsAnswer())[3];
    expect(sonnet).toMatchObject({
      name: "Sonnet 5.5",
      cost: "No price",
      percent: null,
      fill: null,
      cache: null,
      tokens: "17.0M",
    });
  });

  it("reads a cost with unpriced requests as at least", () => {
    const rows = buildModelRows(
      modelsAnswer({
        rows: [modelRow({ cost: 8.28, unpriced: { requests: 1, models: [IDS.fable] } })],
      }),
    );
    expect(rows[0]?.cost).toBe("at least $8.28");
  });

  it("says the phone line as share, tokens and cache", () => {
    const [fable, , , sonnet] = buildModelRows(modelsAnswer());
    expect(phoneLine(need(fable))).toBe("76% · 58.7M · 79% from cache");
    expect(phoneLine(need(sonnet))).toBe("17.0M");
  });
});

describe("the kinds", () => {
  it("lists the four kinds in the board's order, each with its pattern and its total", () => {
    const legend = buildKindLegend(modelsAnswer());
    expect(legend.map((entry) => entry.kind)).toEqual([...KIND_ORDER]);
    expect(legend.map((entry) => entry.pattern)).toEqual([1, 2, 3, 4]);
    expect(legend.map((entry) => `${entry.label} ${entry.total}`)).toEqual([
      "Cache read at least $17.00",
      "Input at least $33.88",
      "Cache write at least $153.46",
      "Output at least $101.57",
    ]);
  });

  it("reads a plain total when nothing is unpriced", () => {
    const legend = buildKindLegend(modelsAnswer({ unpriced: { requests: 0, models: [] } }));
    expect(legend[0]?.total).toBe("$17.00");
  });

  it("draws each model as a stack with its kinds left to right, and the text biggest first", () => {
    const [fable] = buildKindRows(modelsAnswer());
    expect(fable?.stack.map((part) => part.kind)).toEqual([
      "cache_read",
      "input",
      "cache_write",
      "output",
    ]);
    expect(fable?.parts.map((part) => `${part.label} ${part.text}`)).toEqual([
      "Cache write $121.82",
      "Output $83.25",
      "Input $25.53",
      "Cache read $11.31",
    ]);
    expect(fable?.total).toBe("$241.91");
    expect(fable?.width).toBe(1);
  });

  it("scales a stack against the biggest model", () => {
    const rows = buildKindRows(modelsAnswer());
    expect(rows[1]?.width).toBeCloseTo(62.62 / 241.91, 2);
  });

  it("leaves out a kind with no cost", () => {
    const rows = buildKindRows(
      modelsAnswer({ kinds: [kindRow({ input: 0, output: 2, cache_read: 0, cache_write: 0 })] }),
    );
    expect(rows[0]?.stack.map((part) => part.kind)).toEqual(["output"]);
  });

  it("gives a model with no price no stack and No price", () => {
    const sonnet = buildKindRows(modelsAnswer())[3];
    expect(sonnet?.stack).toEqual([]);
    expect(sonnet?.total).toBe("No price");
    expect(sonnet?.width).toBe(0);
  });

  it("gives a model with no kinds entry no stack", () => {
    const rows = buildKindRows(modelsAnswer({ kinds: [] }));
    expect(rows.every((row) => row.stack.length === 0)).toBe(true);
  });
});

describe("the chart label", () => {
  it("names the window, the total and the model with the most cost", () => {
    expect(kindsImageLabel(modelsAnswer(), "30d")).toBe(
      "Chart of what each model's cost is made of for October 11 to November 9, at least $305.91 in all, most of it on Fable 5.1",
    );
  });

  it("says there is no priced cost to show when no kind has a price", () => {
    const none = modelsAnswer({
      legend: { input: 0, output: 0, cache_read: 0, cache_write: 0 },
    });
    expect(kindsImageLabel(none, "30d")).toBe(
      "Chart of what each model's cost is made of for October 11 to November 9, with no priced cost to show",
    );
  });

  it("says Today to the time for Today", () => {
    expect(windowText("today", reviewWindow())).toBe("Today to 10:00 AM");
  });

  it("starts All and a partial range where the records start, with the year when it differs", () => {
    expect(windowText("all", reviewWindow({ oldest: "2025-12-01T12:00:00Z" }))).toBe(
      "December 1, 2025 to November 9, 2026",
    );
    expect(windowText("30d", reviewWindow({ partial: true, oldest: "2026-10-20T12:00:00Z" }))).toBe(
      "October 20 to November 9",
    );
  });
});
