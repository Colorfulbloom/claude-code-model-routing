import { describe, expect, it } from "vitest";
import type { RuleRow } from "@/api/types";
import { en } from "@/strings/en";
import { RULE_GROUP_ORDER } from "@/strings/lists";
import { ruleRows, rulesAnswer } from "@/test/rules-server";
import {
  STATUS_ORDER,
  confidenceCounts,
  filterRules,
  gapOf,
  groupByOutcome,
  joinAnd,
  ladderLayers,
  layerName,
  monthDay,
  orderRule,
  outcomesOf,
  ruleSentence,
  scopeWords,
  settingKeys,
  settingName,
  slotGroups,
} from "./rules-view";

function rule(over: Partial<RuleRow> = {}): RuleRow {
  return {
    combine: "highest_layer",
    confidence: "tested",
    due: false,
    experiment: null,
    key: "effortLevel",
    layer_order: ["env", "user", "default"],
    outcomes: ["in_effect"],
    quotes: [],
    rule_id: "effort-level-main",
    scope: "main",
    verified_on: { claude_version: "2.1.302", date: "2026-10-29" },
    ...over,
  };
}

describe("the words", () => {
  it("has a sentence for every rule and a name for every key", () => {
    for (const row of ruleRows()) {
      expect(ruleSentence(row), row.rule_id).not.toBe(row.rule_id);
      expect(settingName(row.key), row.key).not.toBe(row.key);
    }
  });

  it("turns the dots of a key into underscores for its name", () => {
    expect(settingName("modelSettings.maxEffortLevel")).toBe(en.rg_modelSettings_maxEffortLevel);
  });

  it("reads a date month first", () => {
    expect(monthDay("2026-10-29")).toBe("October 29");
    expect(monthDay("2026-11-02")).toBe("November 2");
    expect(monthDay("later")).toBe("later");
  });

  it("joins with and", () => {
    expect(joinAnd([])).toBe("");
    expect(joinAnd(["a"])).toBe("a");
    expect(joinAnd(["a", "b"])).toBe("a and b");
    expect(joinAnd(["a", "b", "c"])).toBe("a, b and c");
  });

  it("words the scopes in the order main, agent, model", () => {
    const rules = [rule({ scope: "model" }), rule({ scope: "main" }), rule({ scope: "agent" })];
    expect(joinAnd(scopeWords(rules))).toBe(
      `${en.dc_scope_main}, ${en.dc_scope_agent} and ${en.dc_scope_model}`,
    );
  });
});

describe("groups", () => {
  it("orders the setting keys by RULE_GROUP_ORDER, with an unknown key last", () => {
    const rows = [rule({ key: "zzz" }), ...ruleRows()];
    const keys = settingKeys(rows);
    expect(keys.slice(0, -1)).toEqual([...RULE_GROUP_ORDER]);
    expect(keys.at(-1)).toBe("zzz");
  });

  it("groups under every outcome, Invalid first, and leaves an empty status out", () => {
    const rules = [
      rule({ rule_id: "a", outcomes: ["in_effect"] }),
      rule({ rule_id: "b", outcomes: ["lowered", "in_effect"] }),
      rule({ rule_id: "c", outcomes: ["invalid", "default"] }),
      rule({ rule_id: "d", outcomes: [] }),
    ];
    const groups = groupByOutcome(rules);
    expect(groups.map(([status]) => status)).toEqual([
      "invalid",
      "lowered",
      "in_effect",
      "default",
    ]);
    const ids = (status: string): string[] =>
      (groups.find(([s]) => s === status)?.[1] ?? []).map((r) => r.rule_id);
    expect(ids("invalid")).toEqual(["c"]);
    expect(ids("lowered")).toEqual(["b"]);
    expect(ids("in_effect")).toEqual(["a", "b", "d"]);
    expect(ids("default")).toEqual(["c"]);
    expect(outcomesOf(rule({ outcomes: [] }))).toEqual(["in_effect"]);
    expect(STATUS_ORDER[0]).toBe("invalid");
  });

  it("marks only the first row of a rule that shows twice", () => {
    const rules = [
      rule({ rule_id: "a", outcomes: ["in_effect"] }),
      rule({ rule_id: "b", outcomes: ["lowered", "in_effect"] }),
    ];
    const { groups, repeats } = slotGroups(rules);
    expect(repeats).toBe(1);
    expect(
      groups.map(([status, slots]) => [status, slots.map((s) => [s.rule.rule_id, s.first])]),
    ).toEqual([
      ["lowered", [["b", true]]],
      [
        "in_effect",
        [
          ["a", true],
          ["b", false],
        ],
      ],
    ]);
    expect(slotGroups(rules.slice(0, 1)).repeats).toBe(0);
  });

  it("adds a row for each status past the first across the real rules", () => {
    const rows = ruleRows();
    const rowCount = groupByOutcome(rows).reduce((sum, [, inGroup]) => sum + inGroup.length, 0);
    const extra = rows.reduce((sum, row) => sum + Math.max(0, outcomesOf(row).length - 1), 0);
    expect(rowCount).toBe(rows.length + extra);
  });

  it("covers every status once in the order", () => {
    expect(new Set(STATUS_ORDER).size).toBe(7);
  });
});

describe("the order ladder", () => {
  it("names each layer, and the default of an agent's model differently", () => {
    const main = rule();
    expect(layerName("managed", main)).toBe(en.sc_managed);
    expect(layerName("local", main)).toBe(en.sc_project_local);
    expect(layerName("project", main)).toBe(en.sc_project);
    expect(layerName("user", main)).toBe(en.sc_user);
    expect(layerName("plugin", main)).toBe(en.sc_plugin);
    expect(layerName("env", main)).toBe(en.ly_env);
    expect(layerName("flag", main)).toBe(en.ly_flag);
    expect(layerName("cli", main)).toBe(en.ly_cli);
    expect(layerName("agent", main)).toBe(en.ly_agent);
    expect(layerName("default", main)).toBe(en.ly_default);
    expect(layerName("default", rule({ scope: "agent", key: "model" }))).toBe(en.ly_default_agent);
    expect(layerName("default", rule({ scope: "agent", key: "effort" }))).toBe(en.ly_default);
    expect(layerName("odd", main)).toBe("odd");
  });

  it("draws the rule named for its order, else the longest order", () => {
    const named = rule({ rule_id: "x-order", layer_order: ["user"] });
    const long = rule({ rule_id: "y", layer_order: ["env", "user", "default"] });
    expect(orderRule([long, named])).toBe(named);
    expect(orderRule([rule({ rule_id: "a", layer_order: ["user"] }), long])).toBe(long);
    expect(orderRule([])).toBeNull();
    expect(ladderLayers([])).toEqual([]);
  });

  it("gives every real setting a ladder of known layers", () => {
    const rows = ruleRows();
    for (const key of settingKeys(rows)) {
      const layers = ladderLayers(rows.filter((r) => r.key === key));
      expect(layers.length, key).toBeGreaterThan(0);
      for (const layer of layers) expect(layer.label, `${key} ${layer.id}`).not.toBe(layer.id);
    }
  });
});

describe("search", () => {
  it("matches the id, key, group name, sentence, confidence word, version and quotes", () => {
    const rows = [
      rule({
        rule_id: "unique-id-here",
        quotes: [{ doc_url: "https://x", quote: "a zebra line from the docs" }],
      }),
    ];
    const hit = (q: string) => filterRules(rows, { q, confidence: "all", due: false }).length;
    expect(hit("unique-id")).toBe(1);
    expect(hit("effortlevel")).toBe(1);
    expect(hit(en.rg_effortLevel)).toBe(1);
    expect(hit("tested")).toBe(1);
    expect(hit("2.1.302")).toBe(1);
    expect(hit("zebra")).toBe(1);
    expect(hit("zebra nothingelse")).toBe(0);
  });

  it("flags a match found only in the docs line", () => {
    const rows = [
      rule({ quotes: [{ doc_url: "https://x", quote: "a zebra line" }] }),
      rule({ rule_id: "other", quotes: [{ doc_url: "https://x", quote: "tested here too" }] }),
    ];
    const found = filterRules(rows, { q: "zebra", confidence: "all", due: false });
    expect(found.map((m) => m.docsOnly)).toEqual([true]);
    // A word in the rule's own fields as well as its quote is not docs only.
    const both = filterRules(rows, { q: "tested", confidence: "all", due: false });
    expect(both.map((m) => m.docsOnly)).toEqual([false, false]);
    // An empty query matches everything and flags nothing.
    expect(
      filterRules(rows, { q: "", confidence: "all", due: false }).map((m) => m.docsOnly),
    ).toEqual([false, false]);
  });

  it("filters by Confidence and by the due view", () => {
    const rows = [
      rule({ rule_id: "a", confidence: "tested", due: true }),
      rule({ rule_id: "b", confidence: "assumed", due: true }),
      rule({ rule_id: "c", confidence: "assumed", due: false }),
    ];
    const ids = (confidence: "all" | "tested" | "documented" | "assumed", due: boolean) =>
      filterRules(rows, { q: "", confidence, due }).map((m) => m.rule.rule_id);
    expect(ids("all", false)).toEqual(["a", "b", "c"]);
    expect(ids("assumed", false)).toEqual(["b", "c"]);
    expect(ids("all", true)).toEqual(["a", "b"]);
    expect(ids("assumed", true)).toEqual(["b"]);
    expect(confidenceCounts(rows)).toEqual({ all: 3, tested: 1, documented: 0, assumed: 2 });
  });
});

describe("the version gap", () => {
  it("is null with no installed version or with nothing due", () => {
    expect(gapOf(rulesAnswer({ installed: null }))).toBeNull();
    expect(gapOf(rulesAnswer({ installed: "2.1.302" }))).toBeNull();
  });

  it("says all when every rule is due and every one was checked on checked_on", () => {
    const gap = gapOf(rulesAnswer({ installed: "2.1.310" }));
    expect(gap).toMatchObject({ due: 84, total: 84, all: true, marks: false });
    expect(gap?.installed).toBe("2.1.310");
    expect(gap?.checkedOn).toBe("2.1.302");
  });

  it("says some when every rule is due but their versions differ, and draws no due marks", () => {
    const gap = gapOf(
      rulesAnswer({
        installed: "2.1.310",
        mutate: (rules) => {
          const first = rules[0];
          if (first !== undefined)
            first.verified_on = { ...first.verified_on, claude_version: "2.1.305" };
        },
      }),
    );
    expect(gap).toMatchObject({ due: 84, all: false, marks: false });
    expect(gap?.checkedOn).toBe("2.1.302");
  });

  it("says some, and marks rows, when only some are due", () => {
    const gap = gapOf(
      rulesAnswer({
        installed: "2.1.310",
        mutate: (rules) => {
          const first = rules[0];
          if (first !== undefined) {
            first.verified_on = { ...first.verified_on, claude_version: "2.1.310" };
            first.due = false;
          }
        },
      }),
    );
    expect(gap).toMatchObject({ due: 83, all: false, marks: true });
  });
});
