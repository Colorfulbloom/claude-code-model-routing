import { describe, expect, it } from "vitest";
import {
  appliesLine,
  confidenceLine,
  contentsList,
  copyPathOf,
  hasMaskedValue,
  notReadView,
  originNote,
  readOnlyView,
  runsLine,
  setLine,
  statusOf,
  usageLine,
  whereRows,
  whyView,
  type OriginKind,
} from "@/lib/setup-inspector";
import { setupItem, source } from "@/test/setup-fixtures";
import { agentItem } from "@/test/tofix";
import type { SetupItem } from "@/api/types";

const effort = setupItem("settings", "effortLevel", {
  effective: {
    value: { text: "high", masked: false },
    origin: "cap",
    by_item: "settings:maxEffortLevel",
  },
  status: "lowered",
  sources: [
    source({
      scope: "project_local",
      key: "env.CLAUDE_CODE_EFFORT_LEVEL",
      file: ".claude/settings.local.json",
      full_path: "/work/b/.claude/settings.local.json",
      line: 3,
      value: { text: "xhigh", masked: false },
      status: "lowered",
    }),
    source({ scope: "project", key: "effortLevel", line: 7, status: "overridden" }),
    source({
      scope: "user",
      key: "effortLevel",
      file: "~/.claude/settings.json",
      line: 3,
      value: { text: "xhigh", masked: false },
      status: "overridden",
    }),
  ],
  reach: [
    { scope: "managed", visible: true },
    { scope: "command_line", visible: false },
    { scope: "project_local", visible: true },
    { scope: "project", visible: true },
    { scope: "user", visible: true },
    { scope: "shell", visible: false },
  ],
});

describe("runsLine", () => {
  it("says what a setting runs at, and the model in its name", () => {
    expect(runsLine(effort)?.text).toBe("Runs at high");
    const model = setupItem("settings", "model", {
      effective: {
        value: { text: "claude-opus-5-5", masked: false },
        origin: "set",
        by_item: null,
      },
    });
    expect(runsLine(model)?.text).toBe("Runs on Opus 5.5");
    const other = setupItem("settings", "maxEffortLevel", {
      effective: { value: { text: "high", masked: false }, origin: "set", by_item: null },
    });
    expect(runsLine(other)?.text).toBe("Runs with high");
  });

  it("says Bar Tab can't tell when the origin is unknown and no value is known", () => {
    const item = setupItem("settings", "model", {
      effective: { value: null, origin: "unknown", by_item: null },
    });
    expect(runsLine(item)?.text).toBe("Bar Tab can't tell what runs.");
  });

  it("splits an agent's model and effort", () => {
    const agent = setupItem("agents", "judge", {
      effective: {
        value: { text: "claude-opus-5-5 / medium", masked: false },
        origin: "cap",
        by_item: null,
      },
    });
    expect(runsLine(agent)?.text).toBe("Runs on Opus 5.5 at medium");
  });

  it("says when an instruction or rules file loads", () => {
    const loads = (kind: "always" | "on_demand" | "when_no_claude_md", globs: string[] = []) =>
      runsLine(setupItem("rules", "r", { loads: { kind, globs } }))?.text;
    expect(loads("always")).toBe("Loads at start");
    expect(loads("on_demand", ["**/*.sql"])).toBe("Loads when Claude works with a matching file");
    expect(loads("when_no_claude_md")).toBe("Loads only when no CLAUDE.md is found");
    expect(
      runsLine(
        setupItem("instructions", "i", { loads: { kind: "on_demand", globs: ["services/api"] } }),
      )?.text,
    ).toBe("Loads when Claude works in services/api");
  });

  it("words a hook by its event, a permission by its kind and an MCP server by its command", () => {
    const hook = setupItem("hooks", "h", {
      facts: {
        ...setupItem("hooks", "h").facts,
        hook: {
          event: "PreToolUse",
          matcher: "Bash",
          handler_type: "command",
          command: null,
          timeout: null,
        },
      },
    });
    expect(runsLine(hook)?.text).toBe("Runs a command before each Bash call");
    const rule = (kind: "allow" | "ask" | "deny") =>
      runsLine(
        setupItem("permissions", "p", {
          facts: {
            ...setupItem("permissions", "p").facts,
            permission: { kind, tool: "Bash", pattern: null },
          },
        }),
      )?.text;
    expect(rule("allow")).toBe("Allowed without asking");
    expect(rule("ask")).toBe("Asks you first");
    expect(rule("deny")).toBe("Blocked");
    const mcp = setupItem("mcp", "notes", {
      facts: {
        ...setupItem("mcp", "notes").facts,
        mcp: {
          transport: "stdio",
          command: { text: "npx notes --key hidden", masked: true },
          url: null,
          args: [],
          env: {},
          headers: {},
          approved: null,
        },
      },
    });
    expect(runsLine(mcp)).toEqual({ text: "Starts with npx notes --key hidden", masked: true });
  });

  it("says what a plugin adds, and that Bar Tab can't tell for one outside the plugins folder", () => {
    const plugin = (contents: string[], notRead: "plugin_outside_plugins" | null = null) =>
      runsLine(
        setupItem("plugins", "p", {
          not_read: notRead,
          facts: {
            ...setupItem("plugins", "p").facts,
            plugin: {
              version: "1",
              marketplace: null,
              enabled: [],
              orphaned_versions: [],
              contents,
            },
          },
        }),
      )?.text;
    expect(plugin(["agents:linter", "skills:check", "skills:other"])).toBe(
      "Adds 1 agent, 2 skills",
    );
    expect(plugin([])).toBe("Adds nothing Bar Tab can see");
    expect(plugin([], "plugin_outside_plugins")).toBe("Bar Tab can't tell what this plugin adds");
  });

  it("says the output style Claude writes in", () => {
    const style = (active: string | null) =>
      runsLine(
        setupItem("output_style", "s", {
          facts: {
            ...setupItem("output_style", "s").facts,
            output_style: { active, builtin: true },
          },
        }),
      )?.text;
    expect(style("Concise")).toBe("Claude writes in the Concise style");
    expect(style(null)).toBe("Claude writes in the default style");
  });
});

describe("setLine", () => {
  it("says the value, scope and place of the winner, and the cap that lowers it", () => {
    expect(setLine(effort)).toBe(
      "Set to xhigh in Project local, .claude/settings.local.json line 3. Effort cap lowers it.",
    );
  });

  it("says a plugin's item comes from the plugin, and a shell value comes from the shell", () => {
    const plugin = setupItem("skills", "s", {
      sources: [
        source({ scope: "plugin", plugin: "lint-kit", file: "skills/x/SKILL.md", line: 2 }),
      ],
    });
    expect(setLine(plugin)).toBe("From the lint-kit plugin, skills/x/SKILL.md line 2.");
    const shell = setupItem("settings", "model", {
      sources: [
        source({ scope: "shell", key: "ANTHROPIC_MODEL", file: null, full_path: null, line: null }),
      ],
    });
    expect(setLine(shell)).toBe(
      "Set by ANTHROPIC_MODEL in your shell, as Bar Tab saw it at start.",
    );
  });

  it("says nothing sets it when the default applies, and nothing for an item with no line", () => {
    const none = setupItem("settings", "model", {
      sources: [],
      winner: null,
      effective: { value: null, origin: "default", by_item: null },
    });
    expect(setLine(none)).toBe("Nothing sets it, so Claude Code's default applies.");
    expect(setLine(setupItem("agents", "a", { sources: [], winner: null }))).toBeNull();
  });
});

/** The status each cause belongs to. A headline whose status is another one is a mismatch. */
const STATUS_OF_CAUSE: Record<OriginKind, SetupItem["status"]> = {
  cap: "lowered",
  override: "overridden",
  unknown: "unknown",
};

const capped = {
  value: { text: "claude-opus-5-5 / medium", masked: false },
  origin: "cap",
  by_item: "settings:maxEffortLevel",
} as const;

/** An agent with a status, the check the server sends for it and what the effective value says. */
function checked(
  status: SetupItem["status"],
  code: string,
  params: Record<string, string>,
  effective: SetupItem["effective"] = capped,
): SetupItem {
  return agentItem({
    status,
    effective,
    check: { code, params: { settings: "effort", ...params } },
  });
}

const WORDS = { lowered: "Lowered", overridden: "Overridden", unknown: "Unknown" } as const;

describe("originNote", () => {
  const pairs: {
    name: string;
    item: SetupItem;
    kind: OriginKind;
    text: string;
  }[] = [
    {
      name: "a cap lowers the effort",
      item: checked("lowered", "lowered_by_cap", { setting: "effort", cap_key: "maxEffortLevel" }),
      kind: "cap",
      text: "Effort cap lowers it.",
    },
    {
      name: "a cap lowers it and the runs used the pin",
      item: checked("lowered", "lowered_ran_at_pin", {
        setting: "effort",
        cap_key: "maxEffortLevel",
      }),
      kind: "cap",
      text: "Effort cap lowers it.",
    },
    {
      name: "a layer with a file wins",
      item: checked("overridden", "pin_overridden", {
        setting: "model",
        by_key: "model",
        by_file: ".claude/settings.json",
        by_line: "2",
        by_layer: "project",
      }),
      kind: "override",
      text: "model on line 2 of .claude/settings.json wins.",
    },
    {
      name: "a variable wins",
      item: checked("overridden", "pin_overridden", {
        setting: "effort",
        by_key: "CLAUDE_CODE_EFFORT_LEVEL",
        by_via: "CLAUDE_CODE_EFFORT_LEVEL",
        by_layer: "env",
      }),
      kind: "override",
      text: "CLAUDE_CODE_EFFORT_LEVEL wins.",
    },
    {
      name: "a layer with no file wins",
      item: checked("overridden", "pin_overridden", {
        setting: "model",
        by_key: "model",
        by_layer: "project",
      }),
      kind: "override",
      text: "model in project wins.",
    },
    {
      // The model is overridden and a cap lowers the effort. The effective value says cap, but
      // the pill says Overridden, so the sentence names the layer that wins and never the cap.
      name: "the model is overridden and a cap also lowers the effort",
      item: checked(
        "overridden",
        "pin_overridden",
        { setting: "model", by_key: "model", by_file: ".claude/settings.json", by_line: "2" },
        capped,
      ),
      kind: "override",
      text: "model on line 2 of .claude/settings.json wins.",
    },
    {
      name: "Bar Tab can't tell",
      item: checked("unknown", "expected_unknown", { setting: "effort" }),
      kind: "unknown",
      text: "Bar Tab can't tell what runs.",
    },
  ];

  it.each(pairs)("ties the headline to the status pill when $name", ({ item, kind, text }) => {
    const note = originNote(item);
    expect(note).toEqual({ kind, text });
    // The pill and the sentence belong to one cause: a mismatched pair fails here.
    expect(item.status).toBe(STATUS_OF_CAUSE[kind]);
    expect(statusOf(item).label).toBe(WORDS[item.status as keyof typeof WORDS]);
    if (kind === "unknown") expect(runsLine(item)?.text).toBe(text);
    else expect(setLine(item)).toContain(text);
  });

  it("never names the cap beside an Overridden pill, or an override beside a Lowered one", () => {
    for (const note of pairs.map((p) => originNote(p.item))) {
      if (note === null) continue;
      expect(note.kind === "cap" ? note.text : "").not.toContain("wins");
      expect(note.kind === "override" ? note.text : "").not.toContain("lowers");
    }
    const mixed = pairs.find((p) => p.name.startsWith("the model is overridden"))?.item;
    if (mixed === undefined) throw new Error("missing the mixed case");
    expect(mixed.effective?.origin).toBe("cap");
    expect(statusOf(mixed).label).toBe("Overridden");
    expect(setLine(mixed)).not.toContain("lowers it");
  });

  it("names no cause when the status and the check's code are another pair", () => {
    // A code of one cause under the status of another.
    expect(
      originNote(checked("overridden", "lowered_by_cap", { cap_key: "maxEffortLevel" })),
    ).toBeNull();
    expect(
      originNote(checked("lowered", "pin_overridden", { by_key: "model", by_layer: "env" })),
    ).toBeNull();
    // A status with no cause of its own.
    for (const status of ["in_effect", "default", "ignored", "invalid"] as const) {
      expect(originNote(checked(status, "in_effect", { cap_key: "maxEffortLevel" }))).toBeNull();
    }
    // An override that names no winner.
    expect(originNote(checked("overridden", "pin_overridden", { setting: "effort" }))).toBeNull();
  });

  it("names the cap of an item with no check only when its status is Lowered", () => {
    expect(originNote(effort)).toEqual({ kind: "cap", text: "Effort cap lowers it." });
    expect(originNote({ ...effort, status: "in_effect" })).toBeNull();
    expect(originNote({ ...effort, status: "overridden" })).toBeNull();
    expect(setLine({ ...effort, status: "in_effect" })).not.toContain("lowers it");
  });

  it("reads Unknown from an effective value that nothing sets, for an item with no check", () => {
    const item = agentItem({
      status: "unknown",
      effective: { value: null, origin: "unknown", by_item: null },
    });
    expect(originNote(item)).toEqual({ kind: "unknown", text: "Bar Tab can't tell what runs." });
    expect(runsLine(item)?.text).toBe("Bar Tab can't tell what runs.");
  });
});

describe("whereRows", () => {
  it("lists every source top first, with its place, and the scopes Bar Tab can't see after Project local", () => {
    const rows = whereRows(effort, "2026-11-10T14:21:00Z");
    expect(rows.map((r) => r.scope.name)).toEqual([
      "Project local",
      "Command line",
      "Your shell",
      "Shared project",
      "User",
    ]);
    expect(rows[0]).toMatchObject({
      key: "env.CLAUDE_CODE_EFFORT_LEVEL",
      value: { text: "xhigh", masked: false },
      location: ".claude/settings.local.json:3",
      status: { label: "Lowered" },
    });
    expect(rows[1]?.note).toBe("Not visible here");
    expect(rows[2]?.note).toBe("Not set when Bar Tab started");
    expect(rows[2]?.scope.meaning).toMatch(/^Seen at .+, when Bar Tab started$/);
  });

  it("names a plugin's scope and shows a parent folder file under Shared project", () => {
    const item = setupItem("instructions", "/work/CLAUDE.md", {
      sources: [
        source({
          scope: "project",
          key: "file",
          file: "/work/CLAUDE.md",
          line: null,
          value: null,
          location: "parent",
        }),
        source({ scope: "plugin", key: "file", plugin: "lint-kit", line: null, value: null }),
      ],
    });
    const rows = whereRows(item, null);
    expect(rows[0]?.scope).toEqual({ name: "Parent folder", meaning: "Everyone in this project" });
    expect(rows[0]?.key).toBeUndefined();
    expect(rows[1]?.scope.name).toBe("Plugin lint-kit");
  });

  it("lists an agent's own files only, and leaves out the layers that cap or override it", () => {
    const item = setupItem("agents", "judge", {
      status: "lowered",
      sources: [
        source({ scope: "project", key: "name", file: ".claude/agents/judge.md", line: 2 }),
        source({
          scope: "user",
          key: "name",
          file: "~/agents/judge.md",
          line: 2,
          status: "overridden",
        }),
        source({ scope: "user", key: "effort", file: ".claude/agents/judge.md", line: 5 }),
        source({ scope: "user", key: "maxEffortLevel", status: "lowered" }),
        source({ scope: "shell", key: "CLAUDE_CODE_EFFORT_LEVEL", file: null, line: null }),
      ],
      reach: [
        { scope: "command_line", visible: false },
        { scope: "shell", visible: false },
      ],
    });
    const rows = whereRows(item, null);
    expect(rows.map((r) => [r.scope.name, r.location, r.status?.label])).toEqual([
      ["Shared project", ".claude/agents/judge.md:2", "In effect"],
      ["User", "~/agents/judge.md:2", "Overridden"],
    ]);
    expect(rows[0]?.key).toBeUndefined();
    // The item keeps every source for anyone who needs the layers.
    expect(item.sources).toHaveLength(5);
  });

  it("masks nothing itself and shows the masked flag of a source value", () => {
    const item = setupItem("settings", "env.TOKEN", {
      sources: [source({ key: "env.TOKEN", value: { text: "hidden", masked: true } })],
    });
    expect(whereRows(item, null)[0]?.value).toEqual({ text: "hidden", masked: true });
    expect(hasMaskedValue(item)).toBe(true);
    expect(hasMaskedValue(effort)).toBe(false);
  });
});

describe("readOnlyView", () => {
  const readOnly = (
    code: "managed" | "plugin" | "claude_json_command" | "command_line" | "not_visible",
    extra: object = {},
  ) =>
    readOnlyView(
      setupItem("agents", "linter", {
        read_only_reason: { code, params: { plugin: "lint-kit" }, command: null, ...extra },
        sources: [source({ full_path: "/work/agents/linter.md" })],
      }),
    );

  it("gives each reason its words, and Copy path with the full path", () => {
    expect(readOnly("managed")?.reason).toBe(
      "Your organization manages this file, so Bar Tab can't change it.",
    );
    expect(readOnly("managed")?.path).toEqual({
      value: "/work/agents/linter.md",
      label: "Copy path",
      copiedLabel: "Copied",
    });
    expect(readOnly("plugin")?.reason).toContain("This comes from the lint-kit plugin.");
    expect(readOnly("plugin")?.reason).toContain("copy the file into your own agents folder");
  });

  it("leaves the copy-the-file advice out for a plugin item that is not an agent", () => {
    const skill = readOnlyView(
      setupItem("skills", "s", {
        read_only_reason: { code: "plugin", params: { plugin: "lint-kit" }, command: null },
      }),
    );
    expect(skill?.reason).not.toContain("agents folder");
  });

  it("gives no Copy path for the command line or a place Bar Tab can't see", () => {
    expect(readOnly("command_line")?.path).toBeUndefined();
    expect(readOnly("not_visible")?.path).toBeUndefined();
  });

  it("offers the claude mcp command for a user or local MCP server", () => {
    const view = readOnly("claude_json_command", {
      command: { text: "claude mcp remove notes -s user", masked: false },
    });
    expect(view?.command).toEqual({
      command: "claude mcp remove notes -s user",
      copyLabel: "Copy command",
      copiedLabel: "Copied",
    });
  });

  it("is null for an item with no read-only reason", () => {
    expect(readOnlyView(effort)).toBeNull();
  });
});

describe("notReadView, whyView and the small lines", () => {
  it("words an item not read, apart from Couldn't read", () => {
    expect(notReadView(setupItem("plugins", "p", { not_read: "outside_scope" }))).toEqual({
      body: "Not read here. It's outside the folders Bar Tab reads.",
    });
    expect(
      notReadView(setupItem("plugins", "p", { not_read: "plugin_outside_plugins" }))?.body,
    ).toContain("outside your Claude plugins folder");
    expect(notReadView(effort)).toBeNull();
  });

  it("builds the Why line from the reason and the kind, with the confidence", () => {
    expect(whyView(effort)).toEqual({
      body: "This is the value that applies.",
      confidence: "Based on Claude Code's docs, not tested yet.",
    });
    const rule = whyView(setupItem("rules", "r"));
    expect(rule?.body).toContain("A rules file with paths in its front matter");
  });

  it("words each confidence level, and the shell as assumed", () => {
    const level = (l: "tested" | "documented" | "assumed", tested_on: string | null = null) =>
      confidenceLine(setupItem("settings", "k", { confidence: { level: l, tested_on } }));
    expect(level("tested", "2.1.302")).toBe("Based on Claude Code's docs and tested on 2.1.302.");
    expect(level("tested")).toBe("Based on Claude Code's docs and tested.");
    expect(level("assumed")).toBe("Assumed, because Claude Code's docs don't cover this case.");
    const shell = setupItem("settings", "model", {
      confidence: { level: "assumed", tested_on: null },
      sources: [source({ scope: "shell" })],
    });
    expect(confidenceLine(shell)).toBe(
      "Assumed, because Bar Tab can't see the shell your session started in.",
    );
  });

  it("words usage for a value and for an agent", () => {
    const usage = (key: string, runs: number, total: number) =>
      usageLine(
        setupItem("settings", key, {
          usage: {
            code: "runs_at_value",
            params: {
              value: key === "model" ? "claude-opus-5-5" : "high",
              runs: String(runs),
              total: String(total),
              days: "30",
            },
          },
        }),
      );
    expect(usage("effortLevel", 53, 53)).toBe(
      "In the last 30 days, all 53 main sessions ran at high.",
    );
    expect(usage("effortLevel", 20, 53)).toBe(
      "In the last 30 days, 20 of 53 main sessions ran at high.",
    );
    expect(usage("model", 5, 9)).toBe("In the last 30 days, 5 of 9 main sessions ran on Opus 5.5.");
    expect(usage("model", 0, 0)).toBe("No main sessions in the last 30 days.");
    const agent = (runs: number) =>
      usageLine(
        setupItem("agents", "a", {
          usage: { code: "agent_runs", params: { runs: String(runs), days: "30" } },
        }),
      );
    expect(agent(1)).toBe("1 run in the last 30 days");
    expect(agent(82)).toBe("82 runs in the last 30 days");
    expect(agent(0)).toBe("No runs in the last 30 days");
    expect(usageLine(effort)).toBeNull();
  });

  it("words when a change applies, picks the path to copy and counts a plugin's contents", () => {
    expect(appliesLine(setupItem("plugins", "p", { applies: "reload_plugins" }))).toBe(
      "Applies after plugins reload",
    );
    expect(appliesLine(effort)).toBeNull();
    expect(copyPathOf(effort)).toBe("/work/b/.claude/settings.local.json");
    expect(copyPathOf(setupItem("settings", "k", { sources: [], winner: null }))).toBeNull();
    expect(contentsList(["hooks:a", "mcp:b", "output_style:c"])).toBe("1 hook, 1 server, 1 style");
  });
});
