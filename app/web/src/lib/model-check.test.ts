import { describe, expect, it } from "vitest";
import type { ModelCheck, ModelCheckRow } from "@/api/types";
import { buildModelCheck, checkCounts, findingFor } from "@/lib/model-check";

function row(over: Partial<ModelCheckRow>): ModelCheckRow {
  return {
    agent: "judge",
    mismatched_runs: 0,
    params: { setting: "effort", value: "high", expected: "medium" },
    ran: { effort: "medium", mixed: false, model: "claude-opus-5-5" },
    reason_code: "lowered_by_cap",
    runs: 1,
    set: {
      effort: { file: ".claude/agents/judge.md", line: 5, scope: "agent", value: "high" },
      model: null,
    },
    status: "lowered",
    ...over,
  };
}

const lowered = row({
  params: {
    setting: "effort",
    value: "high",
    expected: "medium",
    cap_file: "Project local",
    cap_line: "3",
    cap_key: "maxEffortLevel",
    cap_value: "medium",
  },
});

describe("findingFor, by reason code and the params present", () => {
  it("reads the lowered effort the board shows", () => {
    expect(findingFor(lowered)).toEqual({
      title: "judge ran at medium",
      body: ".claude/agents/judge.md line 5 sets high, but the effort cap in Project local line 3 lowers it to medium.",
      oneLine: "judge ran at medium, because the effort cap lowers the high it's set to.",
    });
  });

  it("uses the model variants for a model setting", () => {
    const found = findingFor(
      row({
        params: {
          setting: "model",
          value: "opus",
          expected: "claude-sonnet-5-5",
          cap_file: "x.json",
          cap_line: "2",
        },
        ran: { effort: "high", mixed: false, model: "claude-sonnet-5-5" },
        set: { effort: null, model: { file: "a.md", line: 2, scope: "agent", value: "opus" } },
      }),
    );
    expect(found?.title).toBe("judge ran on Sonnet 5.5");
    expect(found?.body).toContain("lowers it to Sonnet 5.5");
  });

  it("picks the no-file and no-cap-file variants", () => {
    const noFile = findingFor(row({ ...lowered, set: { effort: null, model: null } }));
    expect(noFile?.body).toBe(
      "It's set to high, but the effort cap in Project local line 3 lowers it to medium.",
    );
    const noCapFile = findingFor(row({ params: { ...lowered.params, cap_file: "" } }));
    expect(noCapFile?.body).toBe(
      ".claude/agents/judge.md line 5 sets high, but the maxEffortLevel cap of medium lowers it to medium.",
    );
    const neither = findingFor(
      row({ set: { effort: null, model: null }, params: { ...lowered.params, cap_file: "" } }),
    );
    expect(neither?.body).toBe(
      "It's set to high, but the maxEffortLevel cap of medium lowers it to medium.",
    );
  });

  it("reads ran at pin despite the cap", () => {
    const found = findingFor(row({ reason_code: "lowered_ran_at_pin", params: lowered.params }));
    expect(found?.title).toBe("judge ran at medium despite the cap");
    expect(found?.body).toContain("should lower high to medium, but its runs still used medium");
  });

  it("covers the overridden variants", () => {
    const by = {
      setting: "effort",
      value: "high",
      expected: "low",
      by_key: "effortLevel",
      by_layer: "Project local",
    };
    const base = row({ status: "overridden", reason_code: "pin_overridden" });
    expect(findingFor({ ...base, params: { ...by, by_file: "s.json", by_line: "4" } })?.body).toBe(
      "Its file sets high in .claude/agents/judge.md line 5, but effortLevel in s.json line 4 wins with low.",
    );
    expect(findingFor({ ...base, params: by })?.body).toBe(
      "Its file sets high in .claude/agents/judge.md line 5, but effortLevel in Project local wins with low.",
    );
    expect(
      findingFor({
        ...base,
        params: { ...by, by_file: "s.json", by_line: "4" },
        set: { effort: null, model: null },
      })?.body,
    ).toBe("Its file sets high, but effortLevel in s.json line 4 wins with low.");
    expect(
      findingFor({ ...base, params: { ...by, by_via: "an environment variable" } })?.body,
    ).toBe("Its file sets high, but an environment variable wins with low.");
    expect(findingFor({ ...base, params: by })?.title).toBe(
      "judge gets its effort from Project local",
    );
  });

  it("covers ignored, invalid, unknown and the ran variants", () => {
    const p = { setting: "effort", value: "max", expected: "high" };
    expect(
      findingFor(row({ status: "ignored", reason_code: "pin_ignored", params: p }))?.body,
    ).toContain("doesn't read it here, so high applies");
    expect(
      findingFor(
        row({
          status: "ignored",
          reason_code: "pin_ignored",
          params: { setting: "effort", value: "max" },
        }),
      )?.body,
    ).toBe(
      "Its file sets max in .claude/agents/judge.md line 5, but Claude Code doesn't read that setting here.",
    );
    expect(
      findingFor(row({ status: "invalid", reason_code: "pin_invalid", params: p }))?.title,
    ).toBe("judge has an invalid effort");
    expect(
      findingFor(row({ status: "unknown", reason_code: "expected_unknown", params: p }))?.title,
    ).toBe("Bar Tab can't check judge's effort");
    expect(
      findingFor(row({ status: "unknown", reason_code: "unknown_status", params: p }))?.title,
    ).toBe("judge has a result Bar Tab doesn't know");
    const differs = findingFor(
      row({ status: "overridden", reason_code: "ran_differs", params: { ...p, ran: "low" } }),
    );
    expect(differs).toEqual({
      title: "judge ran at low, not high",
      body: "It's set to high, but its runs used low.",
      oneLine: "judge ran at low, but it's set to high.",
    });
    expect(findingFor(row({ status: null, reason_code: "no_pin", params: {} }))?.body).toBe(
      "Its file sets neither model nor effort, so there's nothing to check.",
    );
    expect(
      findingFor({ ...row({ status: null, reason_code: "no_pin", params: {} }), agent: null })
        ?.body,
    ).toBe("Your settings set neither model nor effort, so there's nothing to check.");
    expect(
      findingFor(
        row({
          status: "overridden",
          reason_code: "ran_mixed",
          params: { ...p, ran: "low, medium" },
        }),
      )?.title,
    ).toBe("judge's runs used different effort values");
  });

  it("names a model list with its labels", () => {
    const found = findingFor(
      row({
        status: "overridden",
        reason_code: "ran_differs",
        params: {
          setting: "model",
          expected: "claude-opus-5-5",
          ran: "claude-sonnet-5-5, claude-haiku-5-5",
        },
      }),
    );
    expect(found?.title).toBe("judge ran on Sonnet 5.5, Haiku 5.5, not Opus 5.5");
  });

  it("covers the rows with no status", () => {
    expect(
      findingFor(row({ status: null, reason_code: "unnamed_agent", agent: "unnamed", params: {} }))
        ?.title,
    ).toBe("Runs with no agent type");
    expect(findingFor(row({ status: null, reason_code: "no_pin", params: {} }))?.title).toBe(
      "judge sets no model or effort",
    );
    expect(findingFor(row({ status: null, reason_code: null, params: {} }))).toBeNull();
  });

  it("calls the main session Main session", () => {
    expect(findingFor({ ...lowered, agent: null })?.title).toBe("Main session ran at medium");
  });
});

describe("buildModelCheck", () => {
  it("carries the agent's setup item on a finding, or null when the server named none", () => {
    const view = buildModelCheck({
      in_effect_count: 0,
      rows: [
        row({ ...lowered, item_id: "agents:judge" }),
        row({ ...lowered, agent: "builder", item_id: null }),
        row({ ...lowered, agent: null }),
      ],
    });
    expect(view.findings.map((f) => [f.agent, f.itemId])).toEqual([
      ["judge", "agents:judge"],
      ["builder", null],
      ["Main session", null],
    ]);
  });

  it("lists findings, then counts the agents in effect", () => {
    const check: ModelCheck = {
      in_effect_count: 5,
      rows: [
        lowered,
        ...Array.from({ length: 5 }, (_, i) =>
          row({
            agent: `a${String(i)}`,
            status: "in_effect",
            reason_code: "in_effect",
            params: {},
          }),
        ),
      ],
    };
    const view = buildModelCheck(check);
    expect(view.findings).toHaveLength(1);
    expect(view.findings[0]).toMatchObject({ status: "lowered", statusWord: "Lowered" });
    expect(view.okLine).toBe("The other 5 agents ran as set.");
    expect(view.noFileLine).toBeNull();
  });

  it("uses the singular and the all-in-effect forms", () => {
    const inEffect = (n: number): ModelCheckRow[] =>
      Array.from({ length: n }, (_, i) =>
        row({ agent: `a${String(i)}`, status: "in_effect", reason_code: "in_effect", params: {} }),
      );
    expect(buildModelCheck({ in_effect_count: 1, rows: [lowered, ...inEffect(1)] }).okLine).toBe(
      "The other agent ran as set.",
    );
    expect(buildModelCheck({ in_effect_count: 3, rows: inEffect(3) }).okLine).toBe(
      "All 3 agents ran as set.",
    );
    expect(buildModelCheck({ in_effect_count: 1, rows: inEffect(1) }).okLine).toBe(
      "The agent ran as set.",
    );
  });

  it("groups the agents with no agent file into one line", () => {
    const none = (agent: string): ModelCheckRow =>
      row({ agent, status: null, reason_code: "no_agent_file", params: {} });
    const view = buildModelCheck({
      in_effect_count: 0,
      rows: [none("scout"), none("fast-worker"), none("judge")],
    });
    expect(view.findings).toEqual([]);
    expect(view.noFileLine).toBe(
      "scout, fast-worker and judge have no agent file, so there's nothing to check.",
    );
    expect(view.okLine).toBeNull();
  });

  it("has nothing to say for an empty check", () => {
    expect(buildModelCheck({ in_effect_count: 0, rows: [] })).toEqual({
      findings: [],
      noFileLine: null,
      okLine: null,
    });
  });
});

describe("checkCounts, the k and n of the Summary question", () => {
  const mixed: ModelCheck = {
    in_effect_count: 1,
    rows: [
      row({ agent: "a", status: "in_effect", reason_code: "in_effect", params: {} }),
      row({ agent: "b", status: "default", reason_code: "default", params: {} }),
      row({ agent: "c" }),
      row({ agent: "d", status: "overridden", reason_code: "pin_overridden" }),
      row({ agent: "e", status: null, reason_code: "no_pin", params: {} }),
      row({ agent: "f", status: null, reason_code: "unnamed_agent", params: {} }),
    ],
  };

  it("counts only rows with a status, and k only those not in effect or at default", () => {
    // n is a, b, c and d. k is c (lowered) and d (overridden).
    expect(checkCounts(mixed)).toEqual({ checked: 4, notAsSet: 2 });
  });

  it("never lets k pass n, though the findings list also holds default, no_pin and unnamed rows", () => {
    const { checked, notAsSet } = checkCounts(mixed);
    expect(notAsSet).toBeLessThanOrEqual(checked);
    expect(buildModelCheck(mixed).findings).toHaveLength(5);
  });

  it("gives 0 of 0 when no row has a status", () => {
    const none = row({ status: null, reason_code: "no_pin", params: {} });
    expect(checkCounts({ in_effect_count: 0, rows: [none, none] })).toEqual({
      checked: 0,
      notAsSet: 0,
    });
  });
});
