import { describe, expect, it } from "vitest";
import { backLabel, rangePhrase, selectHeading } from "@/lib/range-phrase";
import { choiceValue, dayGroup, limitChoices, sessionChoices } from "@/lib/session-choices";
import type { ChoiceSource } from "@/lib/session-choices";
import { clockShort } from "@/lib/clock";

const TZ = "America/New_York";
// 2026-10-30 at 6:41 PM in New York.
const NOW = Date.parse("2026-10-30T22:41:00Z");

const row = (id: string, started: string, over: Partial<ChoiceSource> = {}): ChoiceSource => ({
  id,
  started,
  branch: "feature/x",
  state: "ended",
  ...over,
});

describe("dayGroup", () => {
  it("names today and yesterday in the server's zone and dates the rest", () => {
    expect(dayGroup("2026-10-30T14:00:00Z", TZ, NOW)).toBe("Today");
    expect(dayGroup("2026-10-29T18:00:00Z", TZ, NOW)).toBe("Yesterday");
    expect(dayGroup("2026-10-28T18:00:00Z", TZ, NOW)).toBe("October 28");
  });

  it("counts a session after midnight in the zone as today, not as the UTC day", () => {
    // 2026-10-31 02:00 UTC is still October 30 evening in New York.
    expect(dayGroup("2026-10-31T02:00:00Z", TZ, Date.parse("2026-10-31T03:00:00Z"))).toBe("Today");
  });
});

describe("sessionChoices", () => {
  it("lists rows newest first with their group and time", () => {
    const choices = sessionChoices(
      [row("a", "2026-10-29T18:00:00Z"), row("b", "2026-10-30T22:10:00Z", { state: "working" })],
      null,
      TZ,
      NOW,
    );
    expect(choices.map((choice) => choice.id)).toEqual(["b", "a"]);
    expect(choices.map((choice) => choice.group)).toEqual(["Today", "Yesterday"]);
    expect(choices[0]?.time).toBe(clockShort("2026-10-30T22:10:00Z"));
  });

  it("adds the open session when the list leaves it out, in its place by date", () => {
    const choices = sessionChoices(
      [row("a", "2026-10-30T20:00:00Z"), row("c", "2026-10-30T10:00:00Z")],
      row("old", "2026-10-30T15:00:00Z"),
      TZ,
      NOW,
    );
    expect(choices.map((choice) => choice.id)).toEqual(["a", "old", "c"]);
  });

  it("takes the open session's own state over the list's", () => {
    const choices = sessionChoices(
      [row("a", "2026-10-30T20:00:00Z", { state: "working" })],
      row("a", "2026-10-30T20:00:00Z", { state: "ended" }),
      TZ,
      NOW,
    );
    expect(choices).toHaveLength(1);
    expect(choices[0]?.state).toBe("ended");
  });

  it("reads the closed button as the day, a comma and the time", () => {
    const [choice] = sessionChoices([row("a", "2026-10-30T22:10:00Z")], null, TZ, NOW);
    if (choice === undefined) throw new Error("no choice");
    expect(choiceValue(choice)).toBe(`Today, ${clockShort("2026-10-30T22:10:00Z")}`);
  });
});

describe("limitChoices", () => {
  const nine = Array.from({ length: 9 }, (_, i) =>
    row(`s${String(i)}`, `2026-10-30T${String(20 - i).padStart(2, "0")}:00:00Z`),
  );

  it("keeps the 5 newest", () => {
    const all = sessionChoices(nine, null, TZ, NOW);
    expect(limitChoices(all, "s1").map((choice) => choice.id)).toEqual([
      "s0",
      "s1",
      "s2",
      "s3",
      "s4",
    ]);
  });

  it("keeps the open session in the last place when it is older than the first 5", () => {
    const all = sessionChoices(nine, null, TZ, NOW);
    expect(limitChoices(all, "s8").map((choice) => choice.id)).toEqual([
      "s0",
      "s1",
      "s2",
      "s3",
      "s8",
    ]);
  });

  it("lists everything when there are 5 or fewer", () => {
    const all = sessionChoices(nine.slice(0, 3), null, TZ, NOW);
    expect(limitChoices(all, "s0")).toHaveLength(3);
  });
});

describe("range phrases", () => {
  it("finish a sentence for every range", () => {
    expect(rangePhrase("today", null)).toBe("today");
    expect(rangePhrase("7d", null)).toBe("in the last 7 days");
    expect(rangePhrase("90d", null)).toBe("in the last 90 days");
    expect(rangePhrase("12m", null)).toBe("in the last 12 months");
  });

  it("names the first stored day for All time, and is empty without it", () => {
    expect(rangePhrase("all", "2026-09-03T14:20:00")).toBe("since September 3");
    expect(rangePhrase("all", null)).toBe("");
  });

  it("builds the back link and the Select heading with no trailing space", () => {
    expect(backLabel("30d", null)).toBe("Sessions in the last 30 days");
    expect(selectHeading("30d", null)).toBe("Sessions in the last 30 days");
    expect(backLabel("all", null)).toBe("Sessions");
  });
});
