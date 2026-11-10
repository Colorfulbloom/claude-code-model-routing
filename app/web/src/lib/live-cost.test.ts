import { describe, expect, it } from "vitest";
import { laneCost, sumCosts } from "@/lib/live-cost";
import { formatDuration } from "@/lib/duration";
import { modelFamily, modelLabel } from "@/lib/models";

const none = { requests: 0, models: [] };

describe("laneCost", () => {
  it("is the plain cost when every request is priced", () => {
    expect(laneCost(0.255, none)).toEqual({ kind: "cost", text: "$0.26" });
    expect(laneCost(0.001, none)).toEqual({ kind: "cost", text: "<$0.01" });
  });

  it("reads at least when some requests are unpriced", () => {
    expect(laneCost(0.97, { requests: 3, models: ["Fable 5.1"] })).toEqual({
      kind: "least",
      text: "at least $0.97",
    });
  });

  it("names the model when none is priced, and falls back to No price", () => {
    expect(laneCost(null, { requests: 3, models: ["Fable 5.1"] })).toEqual({
      kind: "none",
      text: "No price",
      full: "No price for Fable 5.1",
    });
    expect(laneCost(null, none)).toEqual({ kind: "none", text: "No price" });
  });
});

describe("sumCosts", () => {
  it("adds priced costs and the unpriced requests, listing each model once", () => {
    expect(
      sumCosts([
        { cost: 1, unpriced: { requests: 1, models: ["A"] } },
        { cost: null, unpriced: { requests: 2, models: ["A", "B"] } },
        { cost: 2, unpriced: none },
      ]),
    ).toEqual({ cost: 3, unpriced: { requests: 3, models: ["A", "B"] } });
    expect(sumCosts([{ cost: null, unpriced: none }]).cost).toBeNull();
  });
});

describe("formatDuration", () => {
  it("reads minutes and hours", () => {
    expect(formatDuration(5_000)).toBe("less than a minute");
    expect(formatDuration(60_000)).toBe("1 minute");
    expect(formatDuration(30 * 60_000)).toBe("30 minutes");
    expect(formatDuration(60 * 60_000)).toBe("1 hour");
    expect(formatDuration((8 * 60 + 2) * 60_000)).toBe("8 hours 2 minutes");
    expect(formatDuration(-1)).toBe("less than a minute");
  });
});

describe("models", () => {
  it("maps ids to families and names", () => {
    expect(modelFamily("claude-opus-5-5")).toBe("opus");
    expect(modelFamily("claude-fable-5-1")).toBe("fable");
    expect(modelFamily("mystery")).toBeNull();
    expect(modelFamily(null)).toBeNull();
    expect(modelLabel("claude-opus-5-5")).toBe("Opus 5.5");
    expect(modelLabel("claude-fable-5")).toBe("Fable 5");
    expect(modelLabel("mystery")).toBe("mystery");
  });
});
