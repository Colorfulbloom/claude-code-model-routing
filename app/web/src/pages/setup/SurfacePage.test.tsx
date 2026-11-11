import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SetupItem } from "@/api/types";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { never } from "@/test/review-server";
import { partAnswer, problemList, setupItem, source } from "@/test/setup-fixtures";
import { setupServer } from "@/test/setup-server";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

type Server = ReturnType<typeof setupServer>;

const open = (server: Server, path: string, width = 1440) =>
  mount(`#/p/builder/setup/${path}`, { server, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

const model = setupItem("settings", "model", {
  effective: { value: { text: "claude-opus-5-5", masked: false }, origin: "set", by_item: null },
  sources: [source({ key: "model", value: { text: "claude-opus-5-5", masked: false } })],
});
const effort = setupItem("settings", "effortLevel", {
  status: "lowered",
  effective: {
    value: { text: "high", masked: false },
    origin: "cap",
    by_item: "settings:maxEffortLevel",
  },
  sources: [
    source({
      scope: "project_local",
      key: "env.CLAUDE_CODE_EFFORT_LEVEL",
      file: ".claude/settings.local.json",
      full_path: "/work/builder/.claude/settings.local.json",
      line: 3,
      value: { text: "xhigh", masked: false },
      status: "lowered",
    }),
  ],
  reason: { code: "lowered", params: {}, rule_id: null, ref_item: "settings:maxEffortLevel" },
});
const secret = setupItem("settings", "env.API_TOKEN", {
  label_known: false,
  effective: { value: { text: "hidden", masked: true }, origin: "set", by_item: null },
  sources: [source({ key: "env.API_TOKEN", value: { text: "hidden", masked: true } })],
});

const settings = () => setupServer({ part: (p) => partAnswer(p, [model, effort, secret]) });

describe("first load and errors", () => {
  it("shows bones with one spoken line and keeps the header", async () => {
    await open(setupServer({ part: () => never() }), "settings");
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(screen.getByText("Loading settings")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: /^Settings/ })).toBeNull();
  });

  it("shows one raised error with Try again", async () => {
    const server = setupServer({ part: () => 500 });
    await open(server, "settings");
    expect(await screen.findByText("Couldn't load settings")).toBeInTheDocument();
    server.handlers.part = (p) => partAnswer(p, [model]);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("navigation", { name: /^Settings/ })).toBeInTheDocument();
  });

  it("goes back to Your setup for a part the server does not know", async () => {
    await open(settings(), "nope");
    expect(await screen.findByRole("table", { name: "What shapes a session" })).toBeInTheDocument();
  });
});

describe("at 1440", () => {
  it("shows the list beside the inspector, named by the part, with the breadcrumb", async () => {
    await open(settings(), "settings/effortLevel");
    expect(await screen.findByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    const crumb = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumb).getByRole("link", { name: "Your setup" })).toHaveAttribute(
      "href",
      "#/p/builder/setup",
    );
    expect(crumb.querySelector('[aria-current="page"]')).toHaveTextContent("Settings");
    const list = await screen.findByRole("navigation", { name: /^Settings/ });
    expect(within(list).getAllByRole("link")).toHaveLength(3);
    expect(within(list).getByRole("link", { current: "page" })).toHaveTextContent("Effort");
    const region = screen.getByRole("region", { name: "Effort" });
    expect(within(region).getByRole("heading", { level: 2, name: "Effort" })).toBeInTheDocument();
    expect(region).toHaveTextContent("Runs at high");
    expect(region).toHaveTextContent(
      "Set to xhigh in Project local, .claude/settings.local.json line 3. Effort cap lowers it.",
    );
  });

  it("picks the first item that needs a look when the URL names none", async () => {
    await open(settings(), "settings");
    // Model is in effect, and Effort is Lowered, so Effort comes first.
    expect(await screen.findByRole("region", { name: "Effort" })).toBeInTheDocument();
    const list = await screen.findByRole("navigation", { name: /^Settings/ });
    expect(within(list).getByRole("link", { current: "page" })).toHaveTextContent("Effort");
  });

  it("writes the auto-picked item to the URL with replace, so no history entry is added", async () => {
    await open(settings(), "settings");
    const before = window.history.length;
    expect(await screen.findByRole("region", { name: "Effort" })).toBeInTheDocument();
    await waitFor(() => {
      expect(window.location.hash).toBe("#/p/builder/setup/settings/effortLevel");
    });
    expect(window.history.length).toBe(before);
  });

  it("picks the first item when every item is quiet, and one a problem names", async () => {
    const quiet = setupServer({ part: (p) => partAnswer(p, [model, secret]) });
    await open(quiet, "settings");
    expect(await screen.findByRole("region", { name: "Model" })).toBeInTheDocument();
    cleanup();
    const flagged = setupServer({
      part: (p) => partAnswer(p, [model, secret]),
      problems: () =>
        problemList({
          rows: [
            {
              id: "x",
              code: "unknown",
              group: "cant_tell",
              kind: "cant_tell",
              part: "settings",
              item_id: "settings:env.API_TOKEN",
              file: null,
              full_path: null,
              line: null,
              params: {},
              thing: "x",
              confidence: { level: "documented", tested_on: null },
              fix: { kind: "open_item", target: "settings:env.API_TOKEN", reason: null },
            },
          ],
        }),
    });
    await open(flagged, "settings");
    expect(await screen.findByRole("region", { name: "env.API_TOKEN" })).toBeInTheDocument();
  });

  it("moves focus to the inspector heading when an item opens, and the URL follows", async () => {
    await open(settings(), "settings/effortLevel");
    await userEvent.click(await screen.findByRole("link", { name: /^Model(?!s)/ }));
    const heading = await screen.findByRole("heading", { level: 2, name: "Model" });
    expect(heading).toHaveFocus();
    expect(window.location.hash).toBe("#/p/builder/setup/settings/model");
    expect(screen.getByRole("region", { name: "Model" })).toHaveTextContent("Runs on Opus 5.5");
  });

  it("keeps the Switch state in the links", async () => {
    await open(settings(), "settings/effortLevel?scopes=1");
    const link = await screen.findByRole("link", { name: /^Model(?!s)/ });
    expect(link).toHaveAttribute("href", "#/p/builder/setup/settings/model?scopes=1");
    expect(
      within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByRole("link", {
        name: "Your setup",
      }),
    ).toHaveAttribute("href", "#/p/builder/setup?scopes=1");
  });

  it("copies the full path while the screen shows the short one, and says Copied", async () => {
    const user = userEvent.setup();
    await open(settings(), "settings/effortLevel");
    const region = await screen.findByRole("region", { name: "Effort" });
    expect(region).toHaveTextContent(".claude/settings.local.json:3");
    await user.click(within(region).getByRole("button", { name: "Copy path" }));
    expect(await navigator.clipboard.readText()).toBe("/work/builder/.claude/settings.local.json");
    await waitFor(() => {
      expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent("Copied");
    });
  });
});

describe("masked, read-only and not-read items", () => {
  it("shows a masked value with the masked mark and says why", async () => {
    await open(settings(), "settings/env.API_TOKEN");
    const region = await screen.findByRole("region", { name: "env.API_TOKEN" });
    expect(within(region).getAllByText("Hidden").length).toBeGreaterThan(0);
    expect(region).toHaveTextContent("Bar Tab hides values that look like secrets.");
  });

  it("shows the read-only box with its reason and Copy path for a managed item", async () => {
    const managed = setupItem("settings", "availableModels", {
      read_only_reason: { code: "managed", params: {}, command: null },
      sources: [
        source({
          scope: "managed",
          key: "availableModels",
          full_path: "/Library/Application Support/ClaudeCode/managed-settings.json",
        }),
      ],
    });
    await open(setupServer({ part: (p) => partAnswer(p, [managed]) }), "settings/availableModels");
    const region = await screen.findByRole("region", { name: "Allowed models" });
    expect(region).toHaveTextContent(
      "Your organization manages this file, so Bar Tab can't change it.",
    );
    expect(within(region).getByRole("button", { name: "Copy path" })).toBeInTheDocument();
    expect(
      within(await screen.findByRole("navigation", { name: /^Settings/ })).getByText("Read only"),
    ).toBeInTheDocument();
  });

  it("shows the claude mcp command to copy for a user MCP server", async () => {
    const server = setupItem("mcp", "notes", {
      scope: "user",
      read_only_reason: {
        code: "claude_json_command",
        params: {},
        command: { text: "claude mcp remove notes -s user", masked: false },
      },
    });
    await open(setupServer({ part: (p) => partAnswer(p, [server]) }), "mcp/notes");
    const region = await screen.findByRole("region", { name: "notes" });
    expect(within(region).getByText("claude mcp remove notes -s user")).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Copy command" })).toBeInTheDocument();
  });

  it("shows a plugin not read here as Unknown, in the header, the list and a box under the headline", async () => {
    const plugin = setupItem("plugins", "hivemind@demo", {
      not_read: "plugin_outside_plugins",
      status: "unknown",
    });
    await open(setupServer({ part: (p) => partAnswer(p, [plugin]) }), "plugins/hivemind@demo");
    const region = await screen.findByRole("region", { name: "hivemind@demo" });
    expect(region.querySelector("header .status-chip-unknown")).toHaveTextContent("Unknown");
    const box = region.querySelector(".inspector-not-read");
    expect(box?.querySelector(".status-chip-unknown")).toHaveTextContent("Unknown");
    expect(box).toHaveTextContent("It's installed outside your Claude plugins folder");
    expect(region.querySelector(".item-not-read-mark")).toBeNull();
    expect(within(region).queryByRole("heading", { name: "Not read here" })).toBeNull();
    const list = await screen.findByRole("navigation", { name: /^Plugins/ });
    expect(list.querySelector(".status-chip-unknown")).toHaveTextContent("Unknown");
    expect(within(list).queryByText("Not read here")).toBeNull();
  });

  it("shows an import chain with each import's state, and a link to an item it reads", async () => {
    const file = setupItem("instructions", "CLAUDE.md", {
      loads: { kind: "always", globs: [] },
      facts: {
        ...setupItem("instructions", "x").facts,
        instruction: {
          lines: 42,
          bytes: 1000,
          imports: [
            {
              target: "docs/a.md",
              target_item: "instructions:docs/a.md",
              depth: 1,
              state: "read",
              line: 3,
            },
            { target: "docs/gone.md", target_item: null, depth: 1, state: "missing", line: 4 },
            { target: "~/notes.md", target_item: null, depth: 1, state: "not_read", line: 5 },
          ],
        },
      },
    });
    await open(setupServer({ part: (p) => partAnswer(p, [file]) }), "instructions/CLAUDE.md");
    const region = await screen.findByRole("region", { name: "CLAUDE.md" });
    expect(region).toHaveTextContent("Loads at start");
    const chain = need(region.querySelector<HTMLElement>(".setup-chain"));
    expect(chain).toHaveTextContent("42 lines");
    expect(within(chain).getByRole("link", { name: "@docs/a.md" })).toHaveAttribute(
      "href",
      "#/p/builder/setup/instructions/docs%2Fa.md",
    );
    expect(chain).toHaveTextContent("File not found");
    expect(chain).toHaveTextContent("Not read here. It's outside the folders Bar Tab reads.");
  });
});

describe("the Couldn't read card, empty parts and a gone item", () => {
  it("shows the card over the partial list, with each cause and Copy path", async () => {
    const agent = setupItem("agents", "builder", { group: "ran" });
    const server = setupServer({
      part: (p) =>
        partAnswer(p, [agent], {
          unreadable: [
            {
              file: "~/agents/notes.md",
              full_path: "/home/me/agents/notes.md",
              part: "agents",
              problem: "p1",
              reason: "permission",
              scope: "user",
            },
            // A file outside the roots is not read here, so the card leaves it out.
            {
              file: "~/elsewhere.md",
              full_path: null,
              part: "agents",
              problem: null,
              reason: "outside_scope",
              scope: null,
            },
          ],
        }),
    });
    await open(server, "agents");
    const card = await screen.findByRole("alert");
    expect(
      within(card).getByRole("heading", { level: 3, name: "Couldn't read 1 file" }),
    ).toBeInTheDocument();
    expect(card).toHaveTextContent("File permissions block reading ~/agents/notes.md.");
    expect(card).toHaveTextContent("The list below has only what Bar Tab could read.");
    expect(
      within(card).getByRole("button", { name: "Copy path of ~/agents/notes.md" }),
    ).toBeInTheDocument();
    expect(card).not.toHaveTextContent("elsewhere");
    // The file reads in code, and the card runs cause, fix line, then Copy path (a-m4 p11 board).
    expect(card.querySelector("code")).toHaveTextContent("~/agents/notes.md");
    const copy = within(card).getByRole("button", { name: "Copy path of ~/agents/notes.md" });
    const fix = within(card).getByText(/Once Bar Tab can open the file/);
    expect(fix.compareDocumentPosition(copy) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // One group of agents gets no heading over the whole list.
    const agents = await screen.findByRole("navigation", { name: /^Agents/ });
    expect(agents.querySelector(".item-group-title")).toBeNull();
    expect(
      within(await screen.findByRole("navigation", { name: /^Agents/ })).getByRole("link", {
        name: /^builder/,
      }),
    ).toBeInTheDocument();
  });

  it("says what would appear in an empty part, with the docs action", async () => {
    const server = setupServer({
      part: (p) =>
        partAnswer(p, [], {
          empty: {
            reason: "none_found",
            action: "docs",
            target: "https://code.claude.com/docs/en/hooks",
          },
        }),
    });
    await open(server, "hooks");
    const list = await screen.findByRole("navigation", { name: /^Hooks/ });
    expect(list).toHaveTextContent("No hooks found.");
    expect(within(list).getByRole("link", { name: "Open the docs" })).toHaveAttribute(
      "href",
      "https://code.claude.com/docs/en/hooks",
    );
  });

  it("offers to copy the folder path for a part with a folder, and says Copied", async () => {
    const user = userEvent.setup();
    const server = setupServer({
      part: (p) =>
        partAnswer(p, [], {
          empty: {
            reason: "none_found",
            action: "copy_path",
            target: "/work/builder/.claude/skills",
          },
        }),
    });
    await open(server, "skills");
    await user.click(await screen.findByRole("button", { name: "Copy folder path" }));
    expect(await navigator.clipboard.readText()).toBe("/work/builder/.claude/skills");
    await waitFor(() => {
      expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent("Copied");
    });
  });

  it("says Bar Tab can't see a part it can't see, with no action", async () => {
    const server = setupServer({
      part: (p) =>
        partAnswer(p, [], { empty: { reason: "not_visible", action: null, target: null } }),
    });
    await open(server, "mcp");
    const list = await screen.findByRole("navigation", { name: /^MCP servers/ });
    expect(list).toHaveTextContent("Bar Tab can't see where this part is set");
    expect(within(list).queryByRole("button")).toBeNull();
    expect(within(list).queryByRole("link")).toBeNull();
  });

  it("says the item is gone and puts focus on its link back to the part (need 27)", async () => {
    await open(settings(), "settings/nope");
    expect(
      await screen.findByRole("heading", { level: 2, name: "This item isn't in Settings anymore" }),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Back to Settings" });
    expect(link).toHaveAttribute("href", "#/p/builder/setup/settings");
    await waitFor(() => {
      expect(link).toHaveFocus();
    });
  });
});

function permissions(): SetupItem[] {
  return Array.from({ length: 40 }, (_, n) =>
    setupItem("permissions", `allow:Bash(run ${String(n)})`, {
      name: `Bash(run ${String(n)})`,
      group: n < 30 ? "allow" : "deny",
      facts: {
        ...setupItem("permissions", "x").facts,
        permission: { kind: n < 30 ? "allow" : "deny", tool: "Bash", pattern: `run ${String(n)}` },
      },
    }),
  );
}

describe("a long grouped list", () => {
  it("shows the first rows of each group with Show n more and Jump to chips", async () => {
    await open(setupServer({ part: (p) => partAnswer(p, permissions()) }), "permissions");
    const list = await screen.findByRole("navigation", { name: /^Permissions/ });
    expect(within(list).getAllByRole("link")).toHaveLength(12);
    expect(within(list).getByText("Jump to")).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Allow 30" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Deny 10" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Show 24 more" })).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Show 4 more" })).toBeInTheDocument();
  });

  it("moves focus to the first row Show n more revealed", async () => {
    await open(setupServer({ part: (p) => partAnswer(p, permissions()) }), "permissions");
    const list = await screen.findByRole("navigation", { name: /^Permissions/ });
    await userEvent.click(within(list).getByRole("button", { name: "Show 4 more" }));
    expect(within(list).getAllByRole("link")).toHaveLength(16);
    await waitFor(() => {
      expect(within(list).getByRole("link", { name: /Bash\(run 36\)/ })).toHaveFocus();
    });
  });

  it("moves focus to a group's heading from its Jump to chip", async () => {
    await open(setupServer({ part: (p) => partAnswer(p, permissions()) }), "permissions");
    const list = await screen.findByRole("navigation", { name: /^Permissions/ });
    await userEvent.click(within(list).getByRole("button", { name: "Deny 10" }));
    expect(within(list).getByRole("heading", { level: 3, name: /^Deny/ })).toHaveFocus();
  });

  it("keeps the picked item on screen though its group is cut", async () => {
    await open(
      setupServer({ part: (p) => partAnswer(p, permissions()) }),
      "permissions/allow:Bash(run 20)",
    );
    const list = await screen.findByRole("navigation", { name: /^Permissions/ });
    expect(within(list).getByRole("link", { current: "page" })).toHaveTextContent("Bash(run 20)");
  });

  it("shows no chips and no Show n more for a short list", async () => {
    await open(
      setupServer({ part: (p) => partAnswer(p, permissions().slice(0, 5)) }),
      "permissions",
    );
    const list = await screen.findByRole("navigation", { name: /^Permissions/ });
    expect(within(list).queryByText("Jump to")).toBeNull();
    expect(within(list).queryByRole("button", { name: /Show/ })).toBeNull();
  });
});

describe("the board's list shapes", () => {
  it("groups settings as Model and effort, then Other settings", async () => {
    await open(settings(), "settings");
    const list = await screen.findByRole("navigation", { name: /^Settings/ });
    const titles = Array.from(list.querySelectorAll(".item-group-title")).map((h) =>
      h.textContent.trim(),
    );
    expect(titles).toEqual(["Model and effort 2", "Other settings 1"]);
    // The unlabelled key keeps its raw name.
    expect(within(list).getByRole("link", { name: /^env\.API_TOKEN/ })).toBeInTheDocument();
  });

  it("shows per-model settings as words in the list", async () => {
    const text = JSON.stringify({ "claude-opus-5-5": { maxEffortLevel: "high" } });
    const perModel = setupItem("settings", "modelSettings", {
      effective: { value: { text, masked: false }, origin: "set", by_item: null },
      sources: [source({ key: "modelSettings", value: { text, masked: false } })],
    });
    await open(setupServer({ part: (p) => partAnswer(p, [perModel]) }), "settings/modelSettings");
    const list = await screen.findByRole("navigation", { name: /^Settings/ });
    expect(list).toHaveTextContent("Opus 5.5 (Effort cap high)");
    expect(list).not.toHaveTextContent("maxEffortLevel");
  });

  it("lists hooks in plain words with no event headings", async () => {
    const base = setupItem("hooks", "PostToolUse:Bash:1", {
      name: "PostToolUse:Bash",
      group: "PostToolUse",
    });
    const hook = {
      ...base,
      facts: {
        ...base.facts,
        hook: {
          event: "PostToolUse",
          matcher: "Bash",
          handler_type: "command",
          command: null,
          timeout: null,
        },
      },
    };
    await open(setupServer({ part: (p) => partAnswer(p, [hook]) }), "hooks");
    const list = await screen.findByRole("navigation", { name: /^Hooks/ });
    expect(within(list).getByRole("link", { name: /^After Bash succeeds/ })).toBeInTheDocument();
    expect(list.querySelector(".item-group-title")).toBeNull();
    const region = await screen.findByRole("region", { name: "After Bash succeeds" });
    expect(region).toHaveTextContent("Runs a command after each Bash call that succeeds");
  });

  it("numbers the instruction files in load order and says what the list leaves out", async () => {
    const files = [
      setupItem("instructions", "CLAUDE.md", { name: "CLAUDE.md" }),
      setupItem("instructions", "docs/close.md", { name: "docs/close.md" }),
    ];
    await open(setupServer({ part: (p) => partAnswer(p, files) }), "instructions");
    const list = await screen.findByRole("navigation", { name: /^Instructions/ });
    expect(Array.from(list.querySelectorAll(".item-order")).map((n) => n.textContent)).toEqual([
      "1",
      "2",
    ]);
    expect(list.querySelector("ol")).not.toBeNull();
    expect(list).toHaveTextContent("Auto memory isn't listed.");
  });
});

describe("on a phone", () => {
  it("shows the list as the page, with no inspector", async () => {
    await open(settings(), "settings", 375);
    expect(await screen.findByRole("navigation", { name: /^Settings/ })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Effort" })).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
  });

  it("opens an item as its own page with a back link, and focuses its heading", async () => {
    await open(settings(), "settings", 375);
    await userEvent.click(await screen.findByRole("link", { name: /^Model(?!s)/ }));
    const heading = await screen.findByRole("heading", { level: 2, name: "Model" });
    expect(heading).toHaveFocus();
    expect(screen.queryByRole("navigation", { name: /^Settings/ })).toBeNull();
    // The link reads "← Settings", with the arrow hidden from the name (a-m4 p11 board).
    const back = screen.getByRole("link", { name: "Settings" });
    expect(back).toHaveAttribute("href", "#/p/builder/setup/settings");
  });

  it("returns focus and scroll to the item from the back link (need 28)", async () => {
    const scrolled: Element[] = [];
    Element.prototype.scrollIntoView = function scroll(this: Element) {
      scrolled.push(this);
    };
    await open(settings(), "settings", 375);
    await userEvent.click(await screen.findByRole("link", { name: /^Effort(?! cap)/ }));
    await screen.findByRole("heading", { level: 2, name: "Effort" });
    await userEvent.click(screen.getByRole("link", { name: "Settings" }));
    const row = await screen.findByRole("link", { name: /^Effort(?! cap)/ });
    await waitFor(() => {
      expect(row).toHaveFocus();
    });
    expect(scrolled.some((el) => el.contains(row))).toBe(true);
  });

  it("shows the unknown-item sentence on the item's page", async () => {
    await open(settings(), "settings/nope", 375);
    expect(
      await screen.findByRole("heading", { level: 2, name: "This item isn't in Settings anymore" }),
    ).toBeInTheDocument();
  });
});

describe("help", () => {
  const facts = setupItem("hooks", "x").facts;
  const text = (value: string) => ({ text: value, masked: false });
  const inspector = () =>
    waitFor(() => need(document.querySelector<HTMLElement>("section.inspector")));

  it("gives the status pill a button that marks its word, and Where and Why a term", async () => {
    const user = userEvent.setup();
    await open(setupServer({ part: (p) => partAnswer(p, [effort]) }), "settings/effortLevel");
    const region = await inspector();
    await user.click(within(region).getByRole("button", { name: "About Status" }));
    const dialog = await screen.findByRole("dialog", { name: "Status" });
    expect(within(dialog).getByText("Shown here").closest(".hp-row")).toHaveTextContent("Lowered");
    // The status words link goes to the Glossary's Status words section (GlossaryPage.test.tsx
    // checks that route lands on it).
    const statusLink = within(dialog).getByRole("link", { name: /Status words/ });
    expect(statusLink.getAttribute("href")).toMatch(/^#\/reference\/glossary\/status-words(\?|$)/);
    await user.keyboard("{Escape}");
    expect(
      within(region).getByRole("button", { name: "Where it's set, top wins" }),
    ).toHaveAttribute("data-help-id", "setup.where");
    expect(within(region).getByRole("button", { name: "Why" })).toHaveAttribute(
      "data-help-id",
      "setup.why",
    );
  });

  it("gives a read-only box a button", async () => {
    const managed = setupItem("settings", "availableModels", {
      read_only_reason: { code: "managed", params: {}, command: null },
      sources: [source({ scope: "managed", key: "availableModels" })],
    });
    await open(setupServer({ part: (p) => partAnswer(p, [managed]) }), "settings/availableModels");
    const region = await screen.findByRole("region", { name: "Allowed models" });
    expect(within(region).getByRole("button", { name: "About Can't change here" })).toHaveAttribute(
      "data-help-id",
      "setup.readonly",
    );
  });

  it("gives the When a change applies line a term", async () => {
    const item = setupItem("settings", "model", { applies: "now" });
    await open(setupServer({ part: (p) => partAnswer(p, [item]) }), "settings/model");
    const region = await inspector();
    expect(within(region).getByRole("button", { name: "Applies right away" })).toHaveAttribute(
      "data-help-id",
      "setup.applies",
    );
  });

  it("gives the Couldn't read card a button", async () => {
    const agent = setupItem("agents", "builder", { group: "ran" });
    const server = setupServer({
      part: (p) =>
        partAnswer(p, [agent], {
          unreadable: [
            {
              file: "~/agents/notes.md",
              full_path: "/home/me/agents/notes.md",
              part: "agents",
              problem: "p1",
              reason: "permission",
              scope: "user",
            },
          ],
        }),
    });
    await open(server, "agents");
    const card = await screen.findByRole("alert");
    expect(within(card).getByRole("button", { name: "About Couldn't read" })).toHaveAttribute(
      "data-help-id",
      "setup.unread",
    );
  });

  it("puts a term on the field labels of hooks, permissions, MCP servers and plugins", async () => {
    const cases = [
      {
        item: setupItem("hooks", "h", {
          facts: {
            ...facts,
            hook: {
              event: "PreToolUse",
              handler_type: "command",
              matcher: "Bash",
              command: text("make check"),
              timeout: 30,
            },
          },
        }),
        part: "hooks/h",
        region: "h",
        label: "Event",
        id: "setup.hooks",
      },
      {
        item: setupItem("permissions", "p", {
          facts: { ...facts, permission: { kind: "allow", tool: "Bash", pattern: null } },
        }),
        part: "permissions/p",
        region: "p",
        label: "Tool",
        id: "setup.permissions",
      },
      {
        item: setupItem("mcp", "m", {
          facts: {
            ...facts,
            mcp: {
              transport: "stdio",
              command: text("node server.js"),
              url: null,
              args: [],
              env: {},
              headers: {},
              approved: true,
            },
          },
        }),
        part: "mcp/m",
        region: "m",
        label: "Approved",
        id: "setup.mcp",
      },
      {
        item: setupItem("plugins", "pl", {
          facts: {
            ...facts,
            plugin: {
              version: "1.0.0",
              marketplace: null,
              contents: [],
              enabled: [{ scope: "user", enabled: true }],
              orphaned_versions: ["0.9.0"],
            },
          },
        }),
        part: "plugins/pl",
        region: "pl",
        label: "Old versions on disk",
        id: "setup.plugins",
      },
    ];
    for (const c of cases) {
      await open(setupServer({ part: (p) => partAnswer(p, [c.item]) }), c.part);
      const region = await inspector();
      expect(within(region).getByRole("button", { name: c.label })).toHaveAttribute(
        "data-help-id",
        c.id,
      );
      cleanup();
    }
  });

  it("gives the Imports heading a term", async () => {
    const file = setupItem("instructions", "CLAUDE.md", {
      loads: { kind: "always", globs: [] },
      facts: {
        ...facts,
        instruction: { lines: 4, bytes: 40, imports: [] },
      },
    });
    await open(setupServer({ part: (p) => partAnswer(p, [file]) }), "instructions/CLAUDE.md");
    const region = await screen.findByRole("region", { name: "CLAUDE.md" });
    expect(within(region).getByRole("button", { name: "Imports, in load order" })).toHaveAttribute(
      "data-help-id",
      "setup.imports",
    );
  });
});
