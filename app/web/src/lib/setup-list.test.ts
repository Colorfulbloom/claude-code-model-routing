import { describe, expect, it } from "vitest";
import {
  GROUP_SHOWN,
  LONG_LIST,
  itemName,
  itemValue,
  listRow,
  modelSettingsText,
  planList,
  settingValueText,
  shapeGroups,
} from "@/lib/setup-list";
import { setupItem, source } from "@/test/setup-fixtures";

describe("itemName and itemValue", () => {
  it("labels a known setting and shows an unknown key as written", () => {
    expect(itemName(setupItem("settings", "effortLevel"))).toBe("Effort");
    expect(itemName(setupItem("settings", "cleanupPeriodDays", { label_known: false }))).toBe(
      "cleanupPeriodDays",
    );
  });

  it("shows a settings value in the model's name, and a masked value with its flag", () => {
    const model = setupItem("settings", "model", {
      effective: {
        value: { text: "claude-opus-5-5", masked: false },
        origin: "set",
        by_item: null,
      },
    });
    expect(itemValue(model)).toEqual({ text: "Opus 5.5", masked: false });
    const secret = setupItem("settings", "env.TOKEN", {
      effective: { value: { text: "hidden", masked: true }, origin: "set", by_item: null },
    });
    expect(itemValue(secret)).toEqual({ text: "hidden", masked: true });
  });

  it("cuts a long settings value for the list", () => {
    const long = setupItem("settings", "modelSettings", {
      effective: { value: { text: "x".repeat(200), masked: false }, origin: "set", by_item: null },
    });
    expect(itemValue(long)?.text.length).toBe(60);
    expect(itemValue(long)?.text.endsWith("…")).toBe(true);
  });

  it("shows the scope of any other item, with the plugin's name or Parent folder", () => {
    expect(itemValue(setupItem("agents", "builder", { scope: "user" }))?.text).toBe("User");
    expect(
      itemValue(
        setupItem("agents", "linter", {
          scope: "plugin",
          sources: [source({ scope: "plugin", plugin: "lint-kit" })],
        }),
      )?.text,
    ).toBe("Plugin lint-kit");
    expect(
      itemValue(setupItem("instructions", "/work/CLAUDE.md", { location: "parent" }))?.text,
    ).toBe("Parent folder");
  });
});

describe("listRow", () => {
  it("links to the item with the Switch state, and carries its group", () => {
    const row = listRow(
      "builder",
      setupItem("hooks", "PreToolUse:Bash:1", { group: "PreToolUse" }),
      true,
    );
    expect(row.href).toBe("#/p/builder/setup/hooks/PreToolUse:Bash:1?scopes=1");
    expect(row.group).toBe("PreToolUse");
    expect(row.status).toEqual({ status: "in_effect", label: "In effect" });
  });

  it("locks a read-only item and shows an item not read with the Unknown pill", () => {
    const locked = listRow(
      "builder",
      setupItem("skills", "x", { read_only_reason: { code: "plugin", params: {}, command: null } }),
      false,
    );
    expect(locked.locked).toBe(true);
    const unread = listRow(
      "builder",
      setupItem("plugins", "p", { not_read: "plugin_outside_plugins", status: "unknown" }),
      false,
    );
    expect(unread.notRead).toBeUndefined();
    expect(unread.status).toEqual({ status: "unknown", label: "Unknown" });
  });

  it("sets files, rules and unknown keys in the code font", () => {
    expect(listRow("b", setupItem("rules", "sql.md"), false).className).toBe("setup-mono");
    expect(listRow("b", setupItem("settings", "k", { label_known: false }), false).className).toBe(
      "setup-mono",
    );
    expect(listRow("b", setupItem("agents", "a"), false).className).toBeUndefined();
  });
});

function many(total: number, group: (n: number) => string | null) {
  return Array.from({ length: total }, (_, n) =>
    setupItem("permissions", `rule-${String(n)}`, { group: group(n) }),
  );
}

describe("planList", () => {
  it("never cuts a short list", () => {
    const items = many(LONG_LIST, () => "allow");
    const plan = planList(items, ["allow"], new Set(), undefined);
    expect(plan.long).toBe(false);
    expect(plan.shown).toHaveLength(LONG_LIST);
    expect(plan.hidden.size).toBe(0);
  });

  it("never cuts a long list that has no groups", () => {
    const plan = planList(
      many(50, () => null),
      [],
      new Set(),
      undefined,
    );
    expect(plan.long).toBe(true);
    expect(plan.shown).toHaveLength(50);
  });

  it("cuts each group of a long list to its first rows and counts what it left out", () => {
    const items = many(60, (n) => (n < 40 ? "allow" : "deny"));
    const plan = planList(items, ["allow", "deny"], new Set(), undefined);
    expect(plan.long).toBe(true);
    expect(plan.shown).toHaveLength(GROUP_SHOWN * 2);
    expect(plan.hidden.get("allow")).toBe(40 - GROUP_SHOWN);
    expect(plan.hidden.get("deny")).toBe(20 - GROUP_SHOWN);
    expect(plan.firstHidden.get("allow")).toBe(`permissions:rule-${String(GROUP_SHOWN)}`);
  });

  it("shows a whole group once it is expanded, and always the picked item", () => {
    const items = many(60, (n) => (n < 40 ? "allow" : "deny"));
    const open = planList(items, ["allow", "deny"], new Set(["allow"]), undefined);
    expect(open.hidden.has("allow")).toBe(false);
    expect(open.shown.filter((i) => i.group === "allow")).toHaveLength(40);
    const picked = planList(items, ["allow", "deny"], new Set(), "permissions:rule-30");
    expect(picked.shown.map((i) => i.id)).toContain("permissions:rule-30");
    expect(picked.hidden.get("allow")).toBe(40 - GROUP_SHOWN - 1);
  });

  it("keeps the answer's order", () => {
    const items = many(60, (n) => (n % 2 === 0 ? "allow" : "deny"));
    const ids = planList(items, ["allow", "deny"], new Set(), undefined).shown.map((i) => i.id);
    expect(ids).toEqual([...ids].sort((a, b) => Number(a.split("-")[1]) - Number(b.split("-")[1])));
  });
});

function hookItem(event: string, matcher: string | null) {
  const base = setupItem("hooks", `${event}:${matcher ?? ""}:1`, {
    name: `${event}:${matcher ?? ""}`,
  });
  return {
    ...base,
    facts: {
      ...base.facts,
      hook: { event, matcher, handler_type: "command", command: null, timeout: null },
    },
  };
}

describe("hook titles", () => {
  it("says a tool hook in plain words, with its tools", () => {
    expect(itemName(hookItem("PreToolUse", "Edit"))).toBe("Before Edit");
    expect(itemName(hookItem("PostToolUse", "Bash"))).toBe("After Bash succeeds");
    expect(itemName(hookItem("PostToolUseFailure", "Edit|Write"))).toBe(
      "After Edit or Write fails",
    );
    expect(itemName(hookItem("PreToolUse", "Edit|Write|Read"))).toBe("Before Edit, Write or Read");
  });

  it("says the event when there is no matcher, or the matcher is a pattern or not for tools", () => {
    expect(itemName(hookItem("PreToolUse", null))).toBe("Before a tool call runs");
    expect(itemName(hookItem("PreToolUse", ""))).toBe("Before a tool call runs");
    expect(itemName(hookItem("PostToolUse", "mcp__.*"))).toBe("After a tool call succeeds");
    expect(itemName(hookItem("SessionStart", "startup"))).toBe("When a session starts or resumes");
  });
});

describe("per-model settings", () => {
  it("reads as a summary of each model, not as JSON", () => {
    const text = JSON.stringify({
      "claude-opus-5-5": { maxEffortLevel: "high" },
      "claude-haiku-4-5": { effort: "low", autoCompactWindow: 200000 },
    });
    expect(modelSettingsText(text)).toBe(
      "Opus 5.5 (Effort cap high), Haiku 4.5 (Effort low, Compact window 200000)",
    );
    const item = setupItem("settings", "modelSettings", {
      effective: { value: { text, masked: false }, origin: "set", by_item: null },
    });
    expect(itemValue(item)?.text).toContain("Opus 5.5 (Effort cap high)");
    expect(itemValue(item)?.text).not.toContain("{");
  });

  it("keeps text that is not an object of objects as written", () => {
    expect(modelSettingsText("not json")).toBeNull();
    expect(modelSettingsText("[1]")).toBeNull();
    expect(modelSettingsText('{"a":1}')).toBeNull();
    expect(settingValueText("modelSettings", "not json")).toBe("not json");
    expect(settingValueText("model", "claude-opus-5-5")).toBe("Opus 5.5");
    expect(settingValueText("effortLevel", "high")).toBe("high");
  });
});

describe("shapeGroups", () => {
  const server = [{ key: "ran", count: 2 }];

  it("splits settings into Model and effort and Other settings, in the server's order", () => {
    const items = [
      setupItem("settings", "cleanupPeriodDays", { label_known: false }),
      setupItem("settings", "model"),
      setupItem("settings", "effortLevel"),
    ];
    const shaped = shapeGroups("settings", items, []);
    expect(shaped.groups).toEqual([
      { key: "model", count: 2, bare: false },
      { key: "other", count: 1, bare: false },
    ]);
    expect(shaped.items.map((i) => [i.key, i.group])).toEqual([
      ["cleanupPeriodDays", "other"],
      ["model", "model"],
      ["effortLevel", "model"],
    ]);
    const onlyOther = shapeGroups("settings", items.slice(0, 1), []);
    expect(onlyOther.groups.map((g) => g.key)).toEqual(["other"]);
  });

  it("draws hooks as one flat list, with no event headings", () => {
    const items = [hookItem("PreToolUse", "Edit")];
    expect(shapeGroups("hooks", items, [{ key: "PreToolUse", count: 1 }]).groups).toEqual([]);
  });

  it("leaves agents' one group without a heading, and keeps two", () => {
    const items = [setupItem("agents", "a", { group: "ran" })];
    expect(shapeGroups("agents", items, server).groups).toEqual([
      { key: "ran", count: 2, bare: true },
    ]);
    const two = [...server, { key: "no_runs", count: 1 }];
    expect(shapeGroups("agents", items, two).groups.map((g) => g.bare)).toEqual([false, false]);
    expect(shapeGroups("permissions", items, server).groups[0]?.bare).toBe(false);
  });
});
