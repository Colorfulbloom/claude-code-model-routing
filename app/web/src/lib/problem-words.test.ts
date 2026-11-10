import { describe, expect, it } from "vitest";
import { countWord, fixPlan, problemWords, word } from "@/lib/problem-words";
import { problemRow } from "@/test/tofix";

describe("word", () => {
  it("fills a known key and drops a placeholder it has no value for", () => {
    expect(word("loc_line", { file: "a.json", line: 3 })).toBe("a.json line 3");
    expect(word("pc_json_invalid_c", {})).toBe("has a JSON syntax error.");
  });

  it("is null for a key the deck does not have", () => {
    expect(word("pc_no_such_code_t")).toBeNull();
  });
});

describe("countWord", () => {
  it("picks the singular and the plural", () => {
    expect(countWord("pc_hooks_disabled_q_all", 1)).toBe("Your 1 hook doesn't run.");
    expect(countWord("pc_hooks_disabled_q_all", 2)).toBe("None of your 2 hooks run.");
  });
});

describe("problemWords", () => {
  it("reads a code with no string as the raw code, never as nothing", () => {
    const words = problemWords(problemRow({ code: "brand_new_code" }));
    expect(words).toEqual({
      title: "brand_new_code",
      cause: "brand_new_code",
      consequence: "brand_new_code",
    });
  });

  it("joins unset variable names with a comma and a space", () => {
    const words = problemWords(
      problemRow({
        group: "cant_tell",
        code: "env_not_visible",
        thing: "docs",
        file: ".mcp.json",
        line: 4,
        params: { name: "docs", vars: "HOME,TOKEN_DIR" },
      }),
    );
    expect(words.cause).toContain("uses HOME, TOKEN_DIR with no default");
  });

  it("chooses the no-file cause for an unknown value with no file", () => {
    const words = problemWords(
      problemRow({
        group: "cant_tell",
        code: "unknown",
        file: null,
        line: null,
        thing: "Cache lifetime",
      }),
    );
    expect(words.cause).toBe("Nothing Bar Tab reads sets it, and something it can't see decides.");
  });

  it("uses the paths causes for an ignored paths key", () => {
    const words = problemWords(
      problemRow({
        group: "not_as_set",
        code: "ignored",
        thing: "rules",
        params: { key: "paths" },
      }),
    );
    expect(words.consequence).toBe("This rule loads at start, not only for matching files.");
  });

  it("says what a lowered agent's file sets, what runs and which cap lowers it", () => {
    const words = problemWords(
      problemRow({
        group: "not_as_set",
        code: "agent_lowered",
        thing: "judge",
        part: "agents",
        item_id: "agents:judge",
        file: ".claude/agents/judge.md",
        line: 5,
        params: { setting: "effort", value: "high", runs: "medium", cap: "maxEffortLevel" },
      }),
    );
    expect(words).toEqual({
      title: "judge runs lower than its file sets",
      cause: ".claude/agents/judge.md line 5 sets effort to high. Effort cap lowers it to medium.",
      consequence: "Its effort is medium, not high.",
    });
  });

  it("words a model by its name in a lowered agent's row", () => {
    const words = problemWords(
      problemRow({
        group: "not_as_set",
        code: "agent_lowered",
        thing: "judge",
        part: "agents",
        params: {
          setting: "model",
          value: "claude-opus-5-5",
          runs: "claude-sonnet-5-5",
          cap: "maxEffortLevel",
        },
      }),
    );
    expect(words.consequence).toBe("Its model is Sonnet 5.5, not Opus 5.5.");
  });
});

describe("fixPlan", () => {
  it("falls back to a reason when copy_path has no path", () => {
    const plan = fixPlan(
      problemRow({ fix: { kind: "copy_path", target: null, reason: null } }),
      "builder",
    );
    expect(plan).toEqual({
      kind: "cant_fix_here",
      reason: "Can't fix here. Bar Tab can't see where this is set.",
    });
  });

  it("uses the reason's own line for cant_fix_here", () => {
    const plan = fixPlan(
      problemRow({ fix: { kind: "cant_fix_here", target: null, reason: "walk_stopped" } }),
      "builder",
    );
    expect(plan).toEqual({
      kind: "cant_fix_here",
      reason: "Can't fix here. It's a limit of how far Bar Tab looks.",
    });
  });

  it("labels a lowered agent's fix by the cap it opens, not by the agent", () => {
    const plan = fixPlan(
      problemRow({
        part: "agents",
        thing: "judge",
        code: "agent_lowered",
        fix: { kind: "open_item", target: "settings:maxEffortLevel", reason: null },
      }),
      "builder",
    );
    expect(plan).toEqual({
      kind: "open_item",
      label: "Open Effort cap",
      href: "#/p/builder/setup/settings/maxEffortLevel",
    });
  });

  it("labels an open_item row for a known settings key by its name", () => {
    const plan = fixPlan(
      problemRow({
        part: "settings",
        thing: "model",
        fix: { kind: "open_item", target: "settings:model", reason: null },
      }),
      "builder",
    );
    expect(plan).toEqual({
      kind: "open_item",
      label: "Open Model",
      href: "#/p/builder/setup/settings/model",
    });
  });
});
