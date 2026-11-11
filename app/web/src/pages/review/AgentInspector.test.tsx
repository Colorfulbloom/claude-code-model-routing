import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { never } from "@/test/review-server";
import { agentRow, agentsAnswer, noRuns } from "@/test/review-tables";
import { agentItem, partAnswer, pluginAgentItem, setupServer } from "@/test/tofix";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

/** Rows with setup items, a plugin agent and a file agent that share a name, and Main session. */
function answer() {
  return agentsAnswer({
    ran: [
      agentRow({ agent: "builder", item_id: "agents:builder" }),
      agentRow({ agent: "linter", item_id: "agents:linter", runs: 4, sessions: 2, cost: 2 }),
      agentRow({
        agent: "linter",
        scope: "plugin",
        plugin: "lint-kit",
        item_id: "agents:lint-kit:linter",
        set: null,
        set_reason: null,
        status: null,
        reason_code: "agent_source_unchecked",
        runs: 1,
        sessions: 1,
        cost: 0.1,
      }),
      agentRow({ agent: "@main", scope: "main", runs: 0, sessions: 9, cost: 8, status: "lowered" }),
    ],
    never_ran: [noRuns({ agent: "migrator", item_id: "agents:migrator" })],
  });
}

const items = () => [
  agentItem({ id: "agents:builder", key: "builder", name: "builder" }),
  agentItem({ id: "agents:linter", key: "linter", name: "linter" }),
  pluginAgentItem(),
  agentItem({ id: "agents:migrator", key: "migrator", name: "migrator", status: "overridden" }),
];

function server(over: Parameters<typeof setupServer>[0] = {}) {
  return setupServer(
    { agentsPart: () => partAnswer(items()), ...over },
    { agents: () => answer() },
  );
}

const open = (s: ReturnType<typeof setupServer>, query = "?range=30d", width = 1440) =>
  mount(`#/p/builder/review/agents${query}`, { server: s, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

describe("names as links", () => {
  it("links a row with a setup item to the inspector and keeps the range", async () => {
    await open(server());
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(table).getByRole("link", { name: "builder" })).toHaveAttribute(
      "href",
      "#/p/builder/review/agents?range=30d&agent=builder",
    );
    expect(within(table).getByRole("link", { name: "migrator" })).toHaveAttribute(
      "href",
      "#/p/builder/review/agents?range=30d&agent=migrator",
    );
  });

  it("leaves Main session as plain text", async () => {
    await open(server());
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(table).queryByRole("link", { name: "Main session" })).toBeNull();
    expect(within(table).getByText("Main session")).toBeInTheDocument();
  });

  it("does not ask for the setup part until an agent is picked", async () => {
    const s = server();
    await open(s);
    await screen.findByRole("table", { name: "Agents" });
    expect(s.calls.some((c) => c.startsWith("/api/setup/agents"))).toBe(false);
  });
});

describe("a plugin row", () => {
  it("shows two rows for a plugin agent and a file agent with one name, each with its own link", async () => {
    await open(server());
    const table = await screen.findByRole("table", { name: "Agents" });
    const links = within(table).getAllByRole("link", { name: "linter" });
    expect(links.map((l) => l.getAttribute("href"))).toEqual([
      "#/p/builder/review/agents?range=30d&agent=linter",
      "#/p/builder/review/agents?range=30d&agent=lint-kit%3Alinter",
    ]);
  });

  it("names the plugin under the agent and says Not checked in the Check cell", async () => {
    await open(server());
    const table = await screen.findByRole("table", { name: "Agents" });
    const row = need(within(table).getAllByRole("link", { name: "linter" })[1]?.closest("tr"));
    expect(within(row).getByRole("rowheader")).toHaveTextContent("linterPlugin lint-kit");
    const check = within(row).getByText("Not checked");
    expect(check).toHaveAccessibleDescription(
      "Not checked, because Model check doesn't cover plugin or managed agents. Their setup shows in Your setup.",
    );
    expect(within(row).queryByText("Source unknown")).toBeNull();
  });
});

describe("the inspector", () => {
  it("opens beside a narrowed table, takes focus and marks the row", async () => {
    const user = userEvent.setup();
    await open(server());
    await user.click(await screen.findByRole("link", { name: "builder" }));
    const heading = await screen.findByRole("heading", { level: 2, name: "builder" });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    const table = screen.getByRole("table", { name: "Agents" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .filter((h) => !h.className.includes("review-agents-wide"))
        .map((h) => h.textContent),
    ).toEqual(["Agent", "Check", "Cost", "No runs in this range"]);
    expect(table).toHaveClass("review-agents-narrow");
    expect(within(table).getByRole("link", { name: "builder" })).toHaveAttribute(
      "aria-current",
      "true",
    );
    expect(
      screen.getByText("Every agent in this project, including ones that didn't run"),
    ).toBeInTheDocument();
  });

  it("states the setup from the item and the usage over the range", async () => {
    await open(server(), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    expect(within(region).getByText("Runs on Opus 5.5 at high")).toBeInTheDocument();
    expect(
      within(region).getByText("Set in Shared project, .claude/agents/judge.md line 2."),
    ).toBeInTheDocument();
    expect(
      within(region).getByText("Claude Code loads this agent from .claude/agents/judge.md."),
    ).toBeInTheDocument();
    expect(
      within(region).getByText("Based on Claude Code's docs and tested on 2.1.310."),
    ).toBeInTheDocument();
    expect(
      within(region).getByText("5 runs in 3 sessions, $40.00, in the last 30 days"),
    ).toBeInTheDocument();
    expect(within(region).getByText("Read, Grep")).toBeInTheDocument();
  });

  it("says what runs after a cap and names the cap", async () => {
    const lowered = agentItem({
      id: "agents:builder",
      key: "builder",
      name: "builder",
      status: "lowered",
      effective: {
        value: { text: "claude-opus-5-5 / medium", masked: false },
        origin: "cap",
        by_item: "settings:maxEffortLevel",
      },
      check: {
        code: "lowered_by_cap",
        params: { setting: "effort", value: "high", expected: "medium", cap_key: "maxEffortLevel" },
      },
    });
    await open(server({ agentsPart: () => partAnswer([lowered]) }), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    expect(region).toHaveTextContent("Runs on Opus 5.5 at medium");
    expect(region).toHaveTextContent("Effort cap lowers it.");
  });

  it("names the override, not the cap, when the pill reads Overridden and a cap also lowers the effort", async () => {
    // The model is replaced by a higher layer and a cap lowers the effort. The pill is the worse of
    // the two, so the headline names the layer that wins and the cap stays out of it.
    const mixed = agentItem({
      id: "agents:builder",
      key: "builder",
      name: "builder",
      status: "overridden",
      effective: {
        value: { text: "claude-haiku-5-5 / medium", masked: false },
        origin: "cap",
        by_item: "settings:maxEffortLevel",
      },
      check: {
        code: "pin_overridden",
        params: {
          setting: "model",
          value: "claude-opus-5-5",
          expected: "claude-haiku-5-5",
          by_key: "model",
          by_file: ".claude/settings.json",
          by_line: "2",
          by_layer: "project",
          settings: "model",
        },
      },
    });
    await open(server({ agentsPart: () => partAnswer([mixed]) }), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    const head = need(region.querySelector("header"));
    expect(within(head).getByText("Overridden")).toBeInTheDocument();
    expect(region).toHaveTextContent("Runs on Haiku 5.5 at medium");
    expect(region).toHaveTextContent("model on line 2 of .claude/settings.json wins.");
    expect(region).not.toHaveTextContent("lowers it");
  });

  it("shows the outcome pill and the callout under the header when a cap lowers the agent", async () => {
    const lowered = agentItem({
      id: "agents:builder",
      key: "builder",
      name: "builder",
      status: "lowered",
      effective: {
        value: { text: "claude-opus-5-5 / medium", masked: false },
        origin: "cap",
        by_item: "settings:maxEffortLevel",
      },
      check: {
        code: "lowered_by_cap",
        params: {
          setting: "effort",
          value: "high",
          expected: "medium",
          cap_key: "maxEffortLevel",
          cap_value: "medium",
          cap_file: ".claude/settings.local.json",
          cap_line: "3",
          settings: "effort",
        },
      },
    });
    await open(server({ agentsPart: () => partAnswer([lowered]) }), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    const head = need(region.querySelector("header"));
    expect(within(head).getByText("Lowered")).toBeInTheDocument();
    const callout = need(region.querySelector(".agent-callout"));
    expect(callout).toHaveTextContent("Lowered builder ran at medium, but its file sets high.");
    expect(callout).toHaveTextContent(
      ".claude/agents/judge.md line 5 sets high, but the effort cap in .claude/settings.local.json line 3 lowers it to medium.",
    );
    // The callout sits under the headline and the set line, before the facts.
    const text = region.textContent ?? "";
    expect(text.indexOf("Runs on Opus 5.5 at medium")).toBeLessThan(text.indexOf("ran at medium"));
    expect(text.indexOf("ran at medium")).toBeLessThan(text.indexOf("Description"));
  });

  it("shows no callout for an agent that runs as its file sets it", async () => {
    await open(server(), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    expect(region.querySelector(".agent-callout")).toBeNull();
  });

  it("styles the footer link as a quiet button with a space before its aria-hidden arrow", async () => {
    await open(server(), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    const link = within(region).getByRole("link", { name: "Open in Your setup" });
    expect(link).toHaveClass("button", "button-quiet");
    expect(link.textContent).toBe("Open in Your setup →");
    expect(link.querySelector("span")).toHaveAttribute("aria-hidden", "true");
  });

  it("states the usage for a range that is not a number of days", async () => {
    await open(server(), "?range=today&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    expect(within(region).getByText("5 runs in 3 sessions, $40.00, today")).toBeInTheDocument();
  });

  it("says No runs for an agent with none in the range", async () => {
    await open(server(), "?range=30d&agent=migrator");
    const region = await screen.findByRole("region", { name: "migrator" });
    expect(within(region).getByText("No runs in the last 30 days")).toBeInTheDocument();
  });

  it("offers Copy path and Open in Your setup for a file agent", async () => {
    const user = userEvent.setup();
    await open(server(), "?range=30d&agent=builder");
    const region = await screen.findByRole("region", { name: "builder" });
    expect(within(region).getByRole("link", { name: /Open in Your setup/ })).toHaveAttribute(
      "href",
      "#/p/builder/setup/agents/builder",
    );
    await user.click(within(region).getByRole("button", { name: "Copy path" }));
    expect(await navigator.clipboard.readText()).toBe("/work/builder/.claude/agents/judge.md");
  });

  it("shows a plugin agent's owner, its ignored fields and a Copy path in the read-only box", async () => {
    await open(server(), "?range=30d&agent=lint-kit%3Alinter");
    const region = await screen.findByRole("region", { name: "linter" });
    expect(region).toHaveTextContent("This comes from the lint-kit plugin.");
    expect(region).toHaveTextContent("so Bar Tab leaves them as they are");
    expect(within(region).getByText("Fields Claude Code ignores here")).toBeInTheDocument();
    expect(within(region).getByText("permissionMode")).toBeInTheDocument();
    expect(within(region).getByText("acceptEdits")).toBeInTheDocument();
    expect(within(region).getByText("lint-kit agents/linter.md:6")).toBeInTheDocument();
    expect(within(region).getAllByText("Ignored").length).toBeGreaterThan(1);
    // The effective value is unknown for a plugin agent, and the page says so.
    expect(within(region).getByText("Bar Tab can't tell what runs.")).toBeInTheDocument();
    expect(within(region).getAllByRole("button", { name: "Copy path" })).toHaveLength(1);
    expect(within(region).getByRole("link", { name: /Open in Your setup/ })).toHaveAttribute(
      "href",
      "#/p/builder/setup/agents/lint-kit:linter",
    );
  });

  it("opens the plugin agent and the file agent of one name as two different items", async () => {
    const s = server();
    await open(s, "?range=30d&agent=linter");
    const file = await screen.findByRole("region", { name: "linter" });
    expect(file).not.toHaveTextContent("lint-kit plugin");
    cleanup();
    await open(s, "?range=30d&agent=lint-kit%3Alinter");
    expect(await screen.findByRole("region", { name: "linter" })).toHaveTextContent(
      "This comes from the lint-kit plugin.",
    );
  });

  it("keeps the agent in the URL when the range changes", async () => {
    const s = server();
    const { router } = await open(s, "?range=30d&agent=builder");
    await screen.findByRole("region", { name: "builder" });
    await router.navigate("/p/builder/review/agents?range=7d&agent=builder");
    expect(
      await screen.findByText("5 runs in 3 sessions, $40.00, in the last 7 days"),
    ).toBeInTheDocument();
  });
});

describe("states", () => {
  it("shows bones while the setup loads", async () => {
    await open(server({ agentsPart: () => never() }), "?range=30d&agent=builder");
    expect(await screen.findByText("Loading agents")).toBeInTheDocument();
  });

  it("shows a card error with Try again when the setup fails", async () => {
    await open(server({ agentsPart: () => 500 }), "?range=30d&agent=builder");
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Agents" })).toBeInTheDocument();
  });

  it("says an unknown agent is gone and moves focus to the link back", async () => {
    await open(server(), "?range=30d&agent=ghost");
    const link = await screen.findByRole("link", { name: "Back to Agents" });
    expect(screen.getByText("This item isn't in Agents anymore")).toBeInTheDocument();
    await waitFor(() => {
      expect(link).toHaveFocus();
    });
    expect(link).toHaveAttribute("href", "#/p/builder/review/agents?range=30d");
  });
});

describe("at phone width", () => {
  it("shows the inspector as its own page with a back link that returns focus to the row", async () => {
    const user = userEvent.setup();
    await open(server(), "?range=30d", 375);
    await user.click(await screen.findByRole("link", { name: "builder" }));
    const region = await screen.findByRole("region", { name: "builder" });
    expect(screen.queryByRole("table", { name: "Agents" })).toBeNull();
    await user.click(within(region).getByRole("link", { name: /Back to Agents/ }));
    const table = await screen.findByRole("table", { name: "Agents" });
    await waitFor(() => {
      expect(within(table).getByRole("link", { name: "builder" })).toHaveFocus();
    });
  });
});

describe("help", () => {
  it("gives the status pill a button, and the Details and Why headings a term", async () => {
    const user = userEvent.setup();
    await open(server(), "?range=30d&agent=builder");
    const heading = await screen.findByRole("heading", { level: 2, name: "builder" });
    const region = need(heading.closest("section"));
    expect(within(region).getByRole("button", { name: "About Status" })).toHaveAttribute(
      "data-help-id",
      "setup.inspector.status",
    );
    expect(within(region).getByRole("button", { name: "Why" })).toHaveAttribute(
      "data-help-id",
      "setup.why",
    );
    await user.click(within(region).getByRole("button", { name: "About Status" }));
    expect(await screen.findByRole("dialog", { name: "Status" })).toBeInTheDocument();
  });
});
