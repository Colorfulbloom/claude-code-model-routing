/*
 * An agent in Your setup (a-m4-p11-agents): the status pill is the outcome of what runs, the callout
 * sits under the header, the where-set well lists the agent's own files, the run line carries the
 * cost over 30 days, and the footer link goes to the Agents page.
 */
import { cleanup, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { SetupItem } from "@/api/types";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { never } from "@/test/review-server";
import { agentRow, agentsAnswer } from "@/test/review-tables";
import { partAnswer } from "@/test/setup-fixtures";
import { setupServer } from "@/test/setup-server";
import { agentItem, pluginAgentItem } from "@/test/tofix";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

type Source = SetupItem["sources"][number];

const file = (scope: Source["scope"], path: string, status: Source["status"]): Source => ({
  scope,
  key: "name",
  file: path,
  full_path: `/work/${path}`,
  line: 2,
  value: { text: "judge", masked: false },
  status,
  plugin: null,
});

/** A judge whose effort a cap lowers, with the layers that cap it in `sources` as the API sends them. */
function lowered(): SetupItem {
  return agentItem({
    status: "lowered",
    effective: {
      value: { text: "claude-opus-5-5 / medium", masked: false },
      origin: "cap",
      by_item: "settings:maxEffortLevel",
    },
    sources: [
      file("project", ".claude/agents/judge.md", "in_effect"),
      file("user", "~/agents/judge.md", "overridden"),
      {
        ...file("project_local", ".claude/settings.local.json", "in_effect"),
        key: "maxEffortLevel",
      },
      { ...file("shell", "x", "overridden"), key: "CLAUDE_CODE_EFFORT_LEVEL", file: null },
    ],
    reach: [
      { scope: "command_line", visible: false },
      { scope: "shell", visible: false },
    ],
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
}

/** The setup fake with the agents part and an /api/agents answer, which the fake has no route for. */
function agentServer(items: SetupItem[], agents: () => unknown = () => agentsAnswer()) {
  const server = setupServer({ part: (part) => partAnswer(part, items) });
  const base = server.fetch;
  server.fetch = async (input, init) => {
    const path = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (new URL(path, "http://x").pathname !== "/api/agents") return base(input, init);
    server.calls.push(path);
    return new Response(JSON.stringify(await agents()));
  };
  return server;
}

function open(items: SetupItem[], key = "judge", width = 1440, agents = agentsAnswer()) {
  const server = agentServer(items, () => agents);
  return { server, mounted: mount(`#/p/builder/setup/agents/${key}`, { server, width }) };
}

describe("an agent that a cap lowers", () => {
  it("shows Lowered in the header and the list, and the callout under the headline", async () => {
    const { mounted } = open([lowered()]);
    await mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    expect(within(region).getAllByText("Lowered").length).toBeGreaterThanOrEqual(2);
    const list = await screen.findByRole("navigation", { name: /^Agents/ });
    expect(list.querySelector(".status-chip-lowered")).toHaveTextContent("Lowered");
    const callout = need(region.querySelector(".agent-callout"));
    expect(callout).toHaveTextContent("Lowered judge ran at medium, but its file sets high.");
    expect(callout).toHaveTextContent(
      ".claude/agents/judge.md line 5 sets high, but the effort cap in .claude/settings.local.json line 3 lowers it to medium.",
    );
    const text = region.textContent ?? "";
    expect(text.indexOf("Runs on Opus 5.5 at medium")).toBeLessThan(text.indexOf("ran at medium"));
  });

  it("lists the agent's own files in the where-set well and leaves out the cap and the shell", async () => {
    await open([lowered()]).mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    const rows = Array.from(region.querySelectorAll(".where-row"));
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("In effect");
    expect(rows[0]).toHaveTextContent(".claude/agents/judge.md:2");
    expect(rows[1]).toHaveTextContent("Overridden");
    expect(rows[1]).toHaveTextContent("~/agents/judge.md:2");
    expect(region).not.toHaveTextContent("Not visible here");
    expect(region).not.toHaveTextContent("maxEffortLevel");
  });
});

describe("an agent that runs as its file sets it", () => {
  it("has no callout", async () => {
    await open([agentItem()]).mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    expect(region.querySelector(".agent-callout")).toBeNull();
    expect(within(region).getAllByText("In effect").length).toBeGreaterThan(0);
  });
});

describe("the run line and the footer link", () => {
  it("states runs, sessions and cost over 30 days from /api/agents", async () => {
    const answer = agentsAnswer({
      ran: [
        agentRow({ agent: "judge", item_id: "agents:judge", runs: 40, sessions: 18, cost: 9.12 }),
      ],
    });
    const { server, mounted } = open([agentItem()], "judge", 1440, answer);
    await mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    expect(
      await within(region).findByText("40 runs in 18 sessions, $9.12, in the last 30 days"),
    ).toBeInTheDocument();
    expect(server.calls.some((c) => c.startsWith("/api/agents") && c.includes("range=30d"))).toBe(
      true,
    );
  });

  it("says no runs for an agent that did not run in 30 days", async () => {
    await open([agentItem()]).mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    expect(await within(region).findByText("No runs in the last 30 days")).toBeInTheDocument();
  });

  it("keeps the server's runs line while /api/agents loads", async () => {
    const item = agentItem({
      usage: { code: "agent_runs", params: { runs: "3", days: "30" } },
    });
    const server = agentServer([item], () => never());
    await mount("#/p/builder/setup/agents/judge", { server });
    const region = await screen.findByRole("region", { name: "judge" });
    expect(within(region).getByText("3 runs in the last 30 days")).toBeInTheDocument();
  });

  it("ends with a quiet Agents link to the agent's Review page, with a space before its arrow", async () => {
    await open([agentItem()]).mounted;
    const region = await screen.findByRole("region", { name: "judge" });
    const link = within(region).getByRole("link", { name: "Agents" });
    expect(link).toHaveAttribute("href", "#/p/builder/review/agents?range=30d&agent=judge");
    expect(link).toHaveClass("button", "button-quiet");
    expect(link.textContent).toBe("Agents →");
    expect(link.querySelector("span")).toHaveAttribute("aria-hidden", "true");
    // Copy path comes first in the footer, and the link last.
    const actions = need(region.querySelector<HTMLElement>(".inspector-actions"));
    expect(actions.lastElementChild).toBe(link);
    expect(within(actions).getByRole("button", { name: "Copy path" })).toBeInTheDocument();
  });

  it("links a plugin agent by its plugin key, and keeps the read-only box", async () => {
    await open([pluginAgentItem()], "lint-kit:linter").mounted;
    const region = await screen.findByRole("region", { name: "linter" });
    expect(within(region).getByRole("link", { name: "Agents" })).toHaveAttribute(
      "href",
      "#/p/builder/review/agents?range=30d&agent=lint-kit%3Alinter",
    );
    expect(region).toHaveTextContent("This comes from the lint-kit plugin.");
  });
});

describe("a part with no agent", () => {
  it("does not ask /api/agents for another part's item", async () => {
    // The Settings page has no agent, so it never reads the Agents answer.
    const server = agentServer([]);
    await mount("#/p/builder/setup/settings", { server });
    await screen.findByRole("heading", { level: 1 });
    expect(server.calls.some((c) => c.startsWith("/api/agents"))).toBe(false);
  });
});
