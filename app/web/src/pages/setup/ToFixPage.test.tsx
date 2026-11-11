import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ProblemRow } from "@/api/types";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { never } from "@/test/review-server";
import { problemList, problemRow, setupServer } from "@/test/tofix";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

const open = (server: ReturnType<typeof setupServer>, width = 1440) =>
  mount("#/p/builder/to-fix", { server, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

/** One row of oneOfEach(), by position. */
const rowAt = (index: number): ProblemRow => need(oneOfEach()[index]);

/** One row of each group, with the actions the page offers. */
function oneOfEach(): ProblemRow[] {
  return [
    problemRow({
      id: "permission:agents/notes.md",
      kind: "read_failure",
      group: "couldnt_read",
      code: "permission",
      thing: "notes.md",
      part: "agents",
      file: "~/.claude/agents/notes.md",
      full_path: "/work/home/.claude/agents/notes.md",
      line: null,
      fix: { kind: "copy_path", target: "/work/home/.claude/agents/notes.md", reason: null },
    }),
    problemRow({
      id: "mcp_bad_entry:mcp:archive",
      group: "wont_load",
      code: "mcp_bad_entry",
      thing: "archive",
      part: "mcp",
      item_id: "mcp:archive",
      file: "~/.claude.json",
      full_path: "/work/home/.claude.json",
      line: null,
      params: { name: "archive", why: "no_command_or_url" },
      fix: { kind: "copy_command", target: "claude mcp remove archive -s user", reason: null },
    }),
    problemRow({
      id: "json_invalid:settings:3",
      group: "wont_load",
      code: "json_invalid",
      thing: "settings.json",
      file: "managed-settings.json",
      line: 6,
      fix: { kind: "cant_fix_here", target: null, reason: "managed" },
    }),
    problemRow({
      id: "lowered:settings:effort",
      group: "not_as_set",
      code: "lowered",
      thing: "effortLevel",
      part: "settings",
      item_id: "settings:effortLevel",
      file: "settings.local.json",
      line: 3,
      params: { key: "effortLevel", value: "xhigh" },
      fix: { kind: "open_item", target: "settings:effortLevel", reason: null },
    }),
    problemRow({
      id: "plugin_field_ignored:linter",
      group: "not_as_set",
      code: "plugin_field_ignored",
      thing: "linter",
      part: "agents",
      item_id: "agents:lint-kit:linter",
      file: "agents/linter.md",
      line: 6,
      params: { field: "permissionMode", plugin: "lint-kit" },
      fix: { kind: "cant_fix_here", target: null, reason: "plugin" },
    }),
    problemRow({
      id: "unknown:settings:cache",
      kind: "cant_tell",
      group: "cant_tell",
      code: "unknown",
      thing: "promptCacheTtl",
      part: "settings",
      item_id: "settings:promptCacheTtl",
      file: null,
      full_path: null,
      line: null,
      fix: { kind: "open_item", target: "settings:promptCacheTtl", reason: null },
    }),
    problemRow({
      id: "rows_no_usage:transcripts",
      kind: "notice",
      group: "notice",
      code: "rows_no_usage",
      thing: "transcripts",
      part: null,
      file: null,
      full_path: null,
      line: null,
      params: { count: "3" },
      fix: { kind: "cant_fix_here", target: null, reason: "not_fixable" },
    }),
  ];
}

describe("first load", () => {
  it("shows the header and bones with one spoken line", async () => {
    await open(setupServer({ problems: () => never() }));
    expect(await screen.findByRole("heading", { level: 1, name: "To fix" })).toBeInTheDocument();
    expect(await screen.findByText("Checking Builder for problems")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
  });
});

describe("the groups", () => {
  it("shows the five groups in order, each with its count and question", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    await screen.findByRole("heading", { name: "Won't load, 2" });
    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings.map((h) => h.getAttribute("aria-label") ?? h.textContent)).toEqual([
      "Couldn't read, 1",
      "Won't load, 2",
      "Not as set, 2",
      "Can't tell",
      "Notices",
    ]);
    const group = need(screen.getByRole("heading", { name: "Won't load, 2" }).closest("section"));
    expect(within(group).getByText("Claude Code skips these")).toBeInTheDocument();
    expect(
      screen.getByText("Not counted, because Bar Tab can't tell what applies"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Not counted, because they aren't problems in your setup"),
    ).toBeInTheDocument();
  });

  it("words the subtitle from the counted total", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    expect(await screen.findByText("5 problems to fix in Builder")).toBeInTheDocument();
  });

  it("uses the singular for one problem", async () => {
    await open(setupServer({ problems: () => problemList([rowAt(0)]) }));
    expect(await screen.findByText("1 problem to fix in Builder")).toBeInTheDocument();
  });

  it("skips a group with no rows", async () => {
    await open(setupServer({ problems: () => problemList([rowAt(3)]) }));
    await screen.findByRole("heading", { name: "Not as set, 1" });
    expect(screen.queryByRole("heading", { name: /^Couldn't read/ })).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
  });
});

describe("a row", () => {
  it("names the thing, says what is wrong with its file and line, and what it means", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const row = need(
      (
        await screen.findByRole("heading", {
          level: 3,
          name: "effortLevel runs lower than it's set",
        })
      ).closest("li"),
    );
    expect(row).toHaveTextContent(
      "settings.local.json line 3 sets effortLevel to xhigh, and a cap lowers it.",
    );
    expect(row).toHaveTextContent("It runs at a lower value than you set.");
  });

  it("builds a hook cause from its why and its title from the event", async () => {
    const rows = [
      problemRow({
        id: "hook_bad_handler:1",
        code: "hook_bad_handler",
        thing: "PreToolUse",
        part: "hooks",
        file: ".claude/settings.json",
        line: 9,
        params: { event: "PreToolUse", why: "no_command" },
      }),
    ];
    await open(setupServer({ problems: () => problemList(rows) }));
    const row = need(
      (
        await screen.findByRole("heading", { level: 3, name: "A PreToolUse hook can't run" })
      ).closest("li"),
    );
    expect(row).toHaveTextContent(
      ".claude/settings.json line 9 has a command hook with no command.",
    );
  });

  it("words the plural consequence of turned-off hooks from the count and the flag", async () => {
    const rows = [
      problemRow({
        id: "hooks_disabled:1",
        group: "not_as_set",
        code: "hooks_disabled",
        thing: "hooks",
        part: "hooks",
        file: ".claude/settings.json",
        line: 2,
        params: { flag: "disableAllHooks", count: "3" },
      }),
    ];
    await open(setupServer({ problems: () => problemList(rows) }));
    const row = need(
      (await screen.findByRole("heading", { level: 3, name: "Hooks are turned off" })).closest(
        "li",
      ),
    );
    expect(row).toHaveTextContent("None of your 3 hooks run.");
    expect(row).toHaveTextContent(".claude/settings.json line 2 sets disableAllHooks.");
  });

  it("shows a Couldn't read row with its cause from the reason", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const row = need(
      (
        await screen.findByRole("heading", { level: 3, name: "Bar Tab can't open notes.md" })
      ).closest("li"),
    );
    expect(row).toHaveTextContent("File permissions block reading ~/.claude/agents/notes.md.");
    expect(row).toHaveTextContent(
      "Any problems in this file stay hidden until Bar Tab can read it.",
    );
  });

  it("shows a notice as one counted sentence with no title and no action", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const group = need(
      (await screen.findByRole("heading", { name: "Notices" })).closest("section"),
    );
    await screen.findByText(/3 transcript files have requests with no usage data/);
    expect(within(group).queryByRole("heading", { level: 3 })).toBeNull();
    expect(within(group).queryByRole("button")).toBeNull();
    expect(within(group).queryByRole("link")).toBeNull();
  });
});

describe("the fix actions", () => {
  it("opens the item with a link for open_item", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const link = await screen.findByRole("link", { name: "Open Effort" });
    expect(link).toHaveAttribute("href", "#/p/builder/setup/settings/effortLevel");
  });

  it("links a plugin agent to its own route", async () => {
    const rows = [
      problemRow({
        id: "x",
        group: "not_as_set",
        code: "plugin_field_ignored",
        thing: "linter",
        part: "agents",
        item_id: "agents:lint-kit:linter",
        params: { field: "hooks", plugin: "lint-kit" },
        fix: { kind: "open_item", target: "agents:lint-kit:linter", reason: null },
      }),
    ];
    await open(setupServer({ problems: () => problemList(rows) }));
    expect(await screen.findByRole("link", { name: "Open linter" })).toHaveAttribute(
      "href",
      "#/p/builder/setup/agents/lint-kit:linter",
    );
  });

  it("copies the full path for copy_path and says Copied once through the live region", async () => {
    const user = userEvent.setup();
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    await user.click(
      await screen.findByRole("button", { name: "Copy path of ~/.claude/agents/notes.md" }),
    );
    expect(await navigator.clipboard.readText()).toBe("/work/home/.claude/agents/notes.md");
    const live = screen.getAllByRole("status").filter((el) => el.textContent === "Copied");
    expect(live).toHaveLength(1);
  });

  it("copies the masked command for copy_command and says Bar Tab never runs it", async () => {
    const user = userEvent.setup();
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const row = need(
      (
        await screen.findByRole("heading", { level: 3, name: "MCP server archive won't load" })
      ).closest("li"),
    );
    expect(within(row).getByText("claude mcp remove archive -s user").tagName).toBe("CODE");
    expect(
      within(row).getByText(/Bar Tab only copies this command and never runs it/),
    ).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Copy command for archive" }));
    expect(await navigator.clipboard.readText()).toBe("claude mcp remove archive -s user");
  });

  it("says why for cant_fix_here, with no link or button", async () => {
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    const managed = need(
      (
        await screen.findByRole("heading", { level: 3, name: "settings.json isn't valid JSON" })
      ).closest("li"),
    );
    expect(managed).toHaveTextContent("Can't fix here. Your organization manages this file.");
    expect(within(managed).queryByRole("button")).toBeNull();
    expect(within(managed).queryByRole("link")).toBeNull();
    const plugin = need(
      screen
        .getByRole("heading", {
          level: 3,
          name: "linter sets a field Claude Code ignores in plugin agents",
        })
        .closest("li"),
    );
    expect(plugin).toHaveTextContent(
      "Can't fix here. It comes from a plugin, and the next update would undo a change.",
    );
  });

  it("says nothing to fix when an open_item row has no item to open", async () => {
    const rows = [
      problemRow({
        id: "y",
        group: "not_as_set",
        code: "ignored",
        fix: { kind: "open_item", target: null, reason: null },
      }),
    ];
    await open(setupServer({ problems: () => problemList(rows) }));
    expect(await screen.findByText("Nothing to fix here.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Open/ })).toBeNull();
  });
});

describe("nothing to fix", () => {
  it("leads with the empty card and keeps Can't tell and Notices below it", async () => {
    const rows = oneOfEach().filter((r) => r.group === "cant_tell" || r.group === "notice");
    await open(setupServer({ problems: () => problemList(rows) }));
    expect(await screen.findByText("Nothing to fix in Builder")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Nothing to fix" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "Everything Bar Tab can check loads and runs as set. New problems show up here.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Your setup" })).toHaveAttribute(
      "href",
      "#/p/builder/setup",
    );
    expect(screen.getByRole("heading", { level: 2, name: "Can't tell" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Notices" })).toBeInTheDocument();
  });

  it("shows only the empty card with no rows at all", async () => {
    await open(setupServer({ problems: () => problemList([]) }));
    expect(
      await screen.findByRole("heading", { level: 2, name: "Nothing to fix" }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
  });
});

describe("errors", () => {
  it("shows one raised error with Try again when the first read fails", async () => {
    await open(setupServer({ problems: () => 500 }));
    expect(await screen.findByText("Couldn't check Builder for problems")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 2 })).toBeNull();
  });

  it("asks again when Try again is pressed", async () => {
    const user = userEvent.setup();
    let calls = 0;
    const server = setupServer({
      problems: () => {
        calls += 1;
        return calls === 1 ? 500 : problemList([rowAt(3)]);
      },
    });
    await open(server);
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Not as set, 1" })).toBeInTheDocument();
  });
});

describe("a long group", () => {
  const many = (n: number): ProblemRow[] =>
    Array.from({ length: n }, (_, i) =>
      problemRow({
        id: `json_invalid:${String(i)}`,
        thing: `file-${String(i)}.json`,
        file: `file-${String(i)}.json`,
        line: 1,
        fix: { kind: "cant_fix_here", target: null, reason: "managed" },
      }),
    );

  it("shows 25 rows and Show 5 more, and the count stays the whole group", async () => {
    await open(setupServer({ problems: () => problemList(many(30)) }));
    const group = need(
      (await screen.findByRole("heading", { name: "Won't load, 30" })).closest("section"),
    );
    expect(within(group).getAllByRole("heading", { level: 3 })).toHaveLength(25);
    expect(within(group).getByRole("button", { name: "Show 5 more" })).toBeInTheDocument();
  });

  it("shows the rest, moves focus to the first new row and drops the button", async () => {
    const user = userEvent.setup();
    const server = setupServer({
      problems: () =>
        problemList(
          many(30).map((row, i) =>
            i === 25
              ? {
                  ...row,
                  fix: { kind: "open_item" as const, target: "settings:model", reason: null },
                }
              : row,
          ),
        ),
    });
    await open(server);
    const group = need(
      (await screen.findByRole("heading", { name: "Won't load, 30" })).closest("section"),
    );
    await user.click(within(group).getByRole("button", { name: "Show 5 more" }));
    expect(within(group).getAllByRole("heading", { level: 3 })).toHaveLength(30);
    expect(within(group).queryByRole("button", { name: /Show/ })).toBeNull();
    expect(within(group).getByRole("link", { name: "Open file-25.json" })).toHaveFocus();
  });
});

describe("the project in the route", () => {
  it("asks /api/problems for the project", async () => {
    const server = setupServer();
    await open(server);
    await screen.findByRole("heading", { level: 2, name: "Nothing to fix" });
    expect(server.calls).toContain("/api/problems?project=builder");
  });
});

describe("help", () => {
  it("puts the groups button in the header and one rows button in each group's header", async () => {
    const user = userEvent.setup();
    await open(setupServer({ problems: () => problemList(oneOfEach()) }));
    await screen.findByRole("heading", { name: "Won't load, 2" });
    const groups = screen.getByRole("button", { name: "About Problem groups" });
    expect(groups).toHaveAttribute("data-help-id", "fix.groups");
    expect(groups.closest(".page-header")).not.toBeNull();
    const rows = screen.getAllByRole("button", { name: "About Problem row" });
    expect(rows.length).toBeGreaterThan(1);
    for (const button of rows) {
      expect(button).toHaveAttribute("data-help-id", "fix.rows");
      expect(button.closest(".card-header")).not.toBeNull();
      expect(button.closest(".page-header")).toBeNull();
    }
    expect(new Set(rows.map((button) => button.closest("section"))).size).toBe(rows.length);
    await user.click(groups);
    const dialog = await screen.findByRole("dialog", { name: "Problem groups" });
    expect(within(dialog).getByText("Notices")).toBeInTheDocument();
  });

  it("leaves both buttons out when there are no rows at all", async () => {
    await open(setupServer({ problems: () => problemList([]) }));
    await screen.findByRole("heading", { level: 1, name: "To fix" });
    expect(screen.queryByRole("button", { name: /^About Problem/ })).toBeNull();
  });
});
