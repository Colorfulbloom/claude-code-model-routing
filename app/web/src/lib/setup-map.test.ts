import { describe, expect, it } from "vitest";
import { cells, partRow, setupMap } from "@/test/setup-fixtures";
import { chipsOf, mapRows, summaryText } from "@/lib/setup-map";

describe("summaryText", () => {
  it("says the model and effort of Settings in the model's name", () => {
    const row = partRow("settings", {
      summary: { code: "model_effort", params: { model: "claude-opus-5-5", effort: "high" } },
    });
    expect(summaryText(row)).toBe("Opus 5.5, runs at high effort");
  });

  it("says what is missing when only one of the two is set, and when neither is", () => {
    const only = (params: Record<string, string>) =>
      summaryText(partRow("settings", { summary: { code: "model_effort", params } }));
    expect(only({ model: "claude-opus-5-5" })).toBe("Opus 5.5");
    expect(only({ effort: "low" })).toBe("Runs at low effort");
    expect(only({})).toBe("Not set, so defaults apply");
  });

  it("counts agents and those with no recent runs", () => {
    const sum = (params: Record<string, string>) =>
      summaryText(partRow("agents", { summary: { code: "agents", params } }));
    expect(sum({ count: "1" })).toBe("1 agent");
    expect(sum({ count: "6", no_runs: "2" })).toBe("6 agents, 2 with no runs in 30 days");
  });

  it("counts instruction files and lines, and rules with their on-demand globs", () => {
    expect(
      summaryText(
        partRow("instructions", {
          summary: { code: "instructions", params: { count: "4", lines: "9" } },
        }),
      ),
    ).toBe("4 files, 9 lines");
    expect(
      summaryText(
        partRow("rules", {
          summary: { code: "rules", params: { count: "2", on_demand: "1", globs: "**/*.sql" } },
        }),
      ),
    ).toBe("2 files, 1 loads only for **/*.sql");
  });

  it("joins hooks with their events, and permissions denied, asking first and allowed", () => {
    expect(
      summaryText(
        partRow("hooks", { summary: { code: "hooks", params: { count: "3", events: "2" } } }),
      ),
    ).toBe("3 hooks on 2 events");
    expect(
      summaryText(
        partRow("permissions", {
          summary: { code: "permissions", params: { allow: "9", deny: "2", ask: "1" } },
        }),
      ),
    ).toBe("2 denied, 1 asks first, 9 allowed");
    expect(
      summaryText(
        partRow("permissions", {
          summary: { code: "permissions", params: { allow: "0", deny: "0", ask: "0" } },
        }),
      ),
    ).toBe("No rules");
  });

  it("says servers not approved, and plugins on and off", () => {
    expect(
      summaryText(
        partRow("mcp", { summary: { code: "mcp", params: { count: "4", not_approved: "2" } } }),
      ),
    ).toBe("4 servers, 2 not approved");
    expect(
      summaryText(
        partRow("plugins", { summary: { code: "plugins", params: { count: "3", enabled: "2" } } }),
      ),
    ).toBe("2 plugins on, 1 off");
  });

  it("says the active output style, or the default", () => {
    expect(
      summaryText(
        partRow("output_style", {
          summary: { code: "output_style", params: { active: "Concise" } },
        }),
      ),
    ).toBe("Concise");
    expect(summaryText(partRow("output_style"))).toBe("Default");
  });

  it("says nothing found for an empty part and that Bar Tab can't see a part it can't", () => {
    expect(
      summaryText(
        partRow("skills", { empty: { reason: "none_found", action: "docs", target: "https://x" } }),
      ),
    ).toBe("No skills found");
    expect(
      summaryText(partRow("mcp", { empty: { reason: "not_visible", action: null, target: null } })),
    ).toBe("Bar Tab can't see this part");
  });
});

describe("chipsOf", () => {
  it("gives a chip for each scope that is set, in the board's order, and none for not set", () => {
    const row = partRow("agents", {
      scopes: cells({
        project: { state: "set", summary: { code: "count", params: { n: "3" } } },
        user: { state: "set", summary: { code: "count", params: { n: "2" } } },
        plugin: { state: "set", summary: { code: "count", params: { n: "1" } } },
      }),
    });
    expect(chipsOf(row, true).map((c) => `${c.name} ${c.value}`)).toEqual([
      "Command line Not visible here",
      "Shared project 3 agents",
      "User 2 agents",
      "Plugin 1 agent",
    ]);
  });

  it("says Not visible here for the command line of Settings and Agents only", () => {
    expect(chipsOf(partRow("settings"), true).map((c) => c.name)).toEqual(["Command line"]);
    expect(chipsOf(partRow("skills"), true)).toEqual([]);
  });

  it("words a settings cell by its model and effort", () => {
    const row = partRow("settings", {
      scopes: cells({
        user: {
          state: "set",
          summary: { code: "model_effort", params: { model: "claude-opus-5-5", effort: "xhigh" } },
        },
        project: { state: "set", summary: { code: "model_effort", params: { effort: "medium" } } },
        project_local: { state: "set", summary: { code: "count", params: { n: "2" } } },
      }),
    });
    expect(chipsOf(row, true).map((c) => `${c.name} ${c.value}`)).toEqual([
      "Command line Not visible here",
      "Project local 2 values",
      "Shared project medium effort",
      "User Opus 5.5 at xhigh",
    ]);
  });

  it("says Not read here in the project scopes of a project that is not listed", () => {
    const row = partRow("rules", {
      scopes: cells({
        project_local: { state: "not_visible" },
        project: { state: "not_visible" },
        user: { state: "set", summary: { code: "count", params: { n: "1" } } },
      }),
    });
    expect(chipsOf(row, false).map((c) => `${c.name} ${c.value}`)).toEqual([
      "Project local Not read here",
      "Shared project Not read here",
      "User 1 rule",
    ]);
    // Listed, a project scope that can't be seen says nothing.
    expect(chipsOf(row, true).map((c) => c.name)).toEqual(["User"]);
  });

  it("says Couldn't read for a scope whose file failed", () => {
    const row = partRow("hooks", { scopes: cells({ user: { state: "unreadable" } }) });
    expect(chipsOf(row, true)).toEqual([{ scope: "user", name: "User", value: "Couldn't read" }]);
  });
});

describe("mapRows", () => {
  it("gives chips only with the Switch on, and Nothing set here for a row with none", () => {
    const map = setupMap([partRow("skills"), partRow("hooks")]);
    expect(mapRows(map, false).every((r) => r.chips.length === 0 && !r.noChips)).toBe(true);
    expect(mapRows(map, true).map((r) => r.noChips)).toEqual([true, true]);
  });

  it("marks the unreadable line and shows the statuses in the server's order", () => {
    const row = mapRows(
      setupMap([
        partRow("agents", {
          unreadable: true,
          statuses: [
            { status: "ignored", count: 1 },
            { status: "in_effect", count: 2 },
          ],
        }),
      ]),
      false,
    )[0];
    expect(row?.unread).toBe("Couldn't read all its files");
    expect(row?.statuses.map((s) => s.label)).toEqual(["Ignored", "In effect"]);
  });

  it("shows Default for an output style nothing sets, and no status for another empty part", () => {
    const empty = { reason: "none_found", action: "docs", target: "x" } as const;
    const [style, skills] = mapRows(
      setupMap([
        partRow("output_style", { statuses: [], empty }),
        partRow("skills", { statuses: [], empty }),
      ]),
      false,
    );
    expect(style?.statuses.map((s) => s.label)).toEqual(["Default"]);
    expect(skills?.statuses).toEqual([]);
    expect(skills?.quiet).toBe(true);
  });
});
