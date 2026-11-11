import { describe, expect, it } from "vitest";
import { buildRequests, buildTiles, requestTime, tileHelpValues } from "@/lib/live-tiles";
import { bucket, NOW, run, sessionOf, timeline } from "@/test/timelines";

describe("tileHelpValues", () => {
  it("hands the help entry the text as the tile shows it", () => {
    const { cost, cache } = buildTiles(timeline());
    expect(tileHelpValues(cost)).toEqual({ value: "$8.28", delta: "$0.44 in the last minute" });
    expect(tileHelpValues(cache)).toEqual({ value: "78%", delta: "81% in the last minute" });
  });

  it("adds the note when the tile has one and leaves out an empty or missing part", () => {
    expect(tileHelpValues({ value: "$1.00", delta: "", note: "3 requests have no price" })).toEqual(
      { value: "$1.00", note: "3 requests have no price" },
    );
    expect(tileHelpValues({ value: "5", delta: "Same as 5", note: null })).toEqual({
      value: "5",
      delta: "Same as 5",
    });
  });
});

describe("buildTiles while running", () => {
  const tiles = buildTiles(timeline());

  it("reads Spent so far with the last minute and a spark of bucket costs", () => {
    expect(tiles.cost).toMatchObject({
      label: "Spent so far",
      qualifier: "API-rate estimate",
      value: "$8.28",
      delta: "$0.44 in the last minute",
      note: null,
    });
    expect(tiles.cost.spark).toHaveLength(31);
  });

  it("counts Tokens as new tokens plus cache reads", () => {
    expect(tiles.tokens.value).toBe("151K");
    expect(tiles.tokens.delta).toBe("6K in the last minute");
  });

  it("reads Read from cache as a percent", () => {
    expect(tiles.cache).toEqual({ value: "78%", delta: "81% in the last minute", percent: 78 });
  });

  it("counts the agents working", () => {
    expect(tiles.agents).toEqual({
      label: "Agents working",
      value: "2",
      delta: "0 finished, 2 runs in all",
      working: 2,
      finished: 0,
    });
  });
});

describe("buildTiles with unpriced requests", () => {
  it("adds the unpriced line, and a null bucket cost stays null in the spark", () => {
    const base = timeline();
    const answer = timeline({
      totals: { ...base.totals, unpriced: { requests: 12, models: ["Fable 5.1"] } },
      buckets: [bucket(0, { cost: null }), bucket(1)],
    });
    const tiles = buildTiles(answer);
    expect(tiles.cost.note).toBe("12 requests have no price");
    expect(tiles.cost.spark).toEqual([null, 0.05]);
  });

  it("says the one request has no price", () => {
    const base = timeline();
    const answer = timeline({ totals: { ...base.totals, unpriced: { requests: 1, models: [] } } });
    expect(buildTiles(answer).cost.note).toBe("1 request has no price");
  });

  it("shows No price when no request has one", () => {
    const base = timeline();
    expect(buildTiles(timeline({ totals: { ...base.totals, cost: null } })).cost.value).toBe(
      "No price",
    );
  });

  it("drops the cents from $1,000 up", () => {
    const base = timeline();
    expect(buildTiles(timeline({ totals: { ...base.totals, cost: 1234.56 } })).cost.value).toBe(
      "$1,235",
    );
  });
});

describe("buildTiles once the session has ended", () => {
  const base = timeline();
  const ended = (finished: number) =>
    buildTiles(
      timeline({
        session: sessionOf({ state: "ended", running: false }),
        last_minute: null,
        totals: { ...base.totals, runs: 8, runs_finished: finished, runs_working: 0 },
      }),
    );

  it("uses the ended forms", () => {
    const tiles = ended(8);
    expect(tiles.cost).toMatchObject({ label: "Spent in all", delta: "Whole session" });
    expect(tiles.tokens.delta).toBe("Whole session");
    expect(tiles.cache.delta).toBe("Whole session");
    expect(tiles.agents).toEqual({
      label: "Agent runs",
      value: "8",
      delta: "All finished",
      working: 0,
      finished: 8,
    });
  });

  it("says how many finished when some did not", () => {
    expect(ended(6).agents.delta).toBe("6 finished, 8 runs in all");
  });
});

describe("buildRequests", () => {
  it("shows five of the eight with the agent name, model and effort, tokens and cost", () => {
    const answer = timeline({
      runs: [run("main"), run("deep-reasoner", { agent: "scout", label_n: 2 })],
    });
    const rows = buildRequests(answer);
    expect(rows).toHaveLength(5);
    expect(rows[0]).toMatchObject({
      agent: "Main session",
      model: "opus",
      modelLabel: "Opus 5.5 · high",
      tokens: "48K",
      cost: "$0.05",
    });
    expect(rows[1]?.agent).toBe("scout 2");
  });

  it("names the request with no price", () => {
    const base = timeline();
    const [first, ...rest] = base.requests;
    const answer = timeline({
      requests: first === undefined ? [] : [{ ...first, cost: null }, ...rest],
    });
    expect(buildRequests(answer)[0]?.cost).toBe("No price");
  });

  it("writes the time with seconds and no AM or PM", () => {
    expect(requestTime(Date.parse(NOW))).toMatch(/^\d{1,2}:\d{2}:\d{2}$/);
  });
});
