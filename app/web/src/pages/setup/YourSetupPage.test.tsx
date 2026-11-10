import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { cells, partRow, setupMap } from "@/test/setup-fixtures";
import { setupServer } from "@/test/setup-server";
import { never } from "@/test/review-server";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

const PARTS = [
  "settings",
  "agents",
  "instructions",
  "rules",
  "skills",
  "hooks",
  "permissions",
  "mcp",
  "plugins",
  "output_style",
] as const;

function rows() {
  return PARTS.map((part) =>
    partRow(part, {
      summary:
        part === "settings"
          ? { code: "model_effort", params: { model: "claude-opus-5-5", effort: "high" } }
          : part === "agents"
            ? { code: "agents", params: { count: "6", no_runs: "2" } }
            : { code: part, params: { count: "1", lines: "3", events: "1", enabled: "1" } },
      statuses:
        part === "settings"
          ? [
              { status: "lowered", count: 1 },
              { status: "in_effect", count: 4 },
            ]
          : [{ status: "in_effect", count: 1 }],
      scopes: cells({
        project: { state: "set", summary: { code: "count", params: { n: "3" } } },
        user: { state: "set", summary: { code: "count", params: { n: "2" } } },
      }),
    }),
  );
}

type Server = ReturnType<typeof setupServer>;

const open = (server: Server, query = "", width = 1440) =>
  mount(`#/p/builder/setup${query}`, { server, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

describe("first load", () => {
  it("shows bones with one spoken line and keeps the header and the Switch", async () => {
    await open(setupServer({ map: () => never() }));
    expect(
      await screen.findByRole("heading", { level: 1, name: "Your setup" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Loading your setup")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Show where each comes from" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows one raised error with Try again when the first read fails", async () => {
    const server = setupServer({ map: () => 500 });
    await open(server);
    expect(await screen.findByText("Couldn't load what shapes a session")).toBeInTheDocument();
    server.handlers.map = () => setupMap(rows());
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: "What shapes a session" })).toBeInTheDocument();
  });
});

describe("the map", () => {
  it("has a row for each of the ten parts, each with its summary, statuses and link", async () => {
    await open(setupServer({ map: () => setupMap(rows()) }));
    const table = await screen.findByRole("table", { name: "What shapes a session" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Part", "What applies", "Status"]);
    const body = within(table).getAllByRole("row").slice(1);
    expect(body).toHaveLength(10);
    const settings = need(body[0]);
    expect(within(settings).getByRole("rowheader")).toHaveTextContent("Settings");
    expect(within(settings).getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "#/p/builder/setup/settings",
    );
    expect(settings).toHaveTextContent("Opus 5.5, runs at high effort");
    expect(settings).toHaveTextContent("Lowered");
    expect(settings).toHaveTextContent("In effect");
    expect(need(body[1])).toHaveTextContent("6 agents, 2 with no runs in 30 days");
  });

  it("opens a part's page from its link", async () => {
    await open(setupServer({ map: () => setupMap(rows()) }));
    await userEvent.click(await screen.findByRole("link", { name: "Hooks" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Hooks" })).toBeInTheDocument();
  });

  it("says Couldn't read all its files beside the cause, and keeps an empty or unseen part's row", async () => {
    const list = rows();
    list[1] = partRow("agents", { unreadable: true });
    list[4] = partRow("skills", {
      statuses: [],
      empty: { reason: "none_found", action: "docs", target: "https://x" },
    });
    list[7] = partRow("mcp", {
      statuses: [],
      empty: { reason: "not_visible", action: null, target: null },
    });
    await open(setupServer({ map: () => setupMap(list) }));
    const table = await screen.findByRole("table", { name: "What shapes a session" });
    expect(within(table).getByText("Couldn't read all its files")).toBeInTheDocument();
    expect(within(table).getByText("No skills found")).toBeInTheDocument();
    expect(within(table).getByText("Bar Tab can't see this part")).toBeInTheDocument();
  });

  it("names the project in the sub line", async () => {
    await open(setupServer({ map: () => setupMap(rows()) }));
    expect(
      await screen.findByText("What Claude Code loads when you start a session in Builder"),
    ).toBeInTheDocument();
  });
});

describe("the Switch", () => {
  it("shows scope chips, keeps the state in the URL and fetches nothing", async () => {
    const server = setupServer({ map: () => setupMap(rows()) });
    await open(server);
    await screen.findByRole("table", { name: "What shapes a session" });
    const toggle = screen.getByRole("switch", { name: "Show where each comes from" });
    expect(toggle).not.toBeChecked();
    expect(document.querySelector(".scope-chip")).toBeNull();
    const calls = server.calls.length;
    await userEvent.click(toggle);
    expect(toggle).toBeChecked();
    expect(toggle).toHaveFocus();
    expect(window.location.hash).toBe("#/p/builder/setup?scopes=1");
    const settings = need(document.querySelector<HTMLElement>('tr[data-part="settings"]'));
    expect(within(settings).getByText("Shared project")).toBeInTheDocument();
    expect(within(settings).getByText("Command line")).toBeInTheDocument();
    expect(server.calls.length).toBe(calls);
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(window.location.hash).toBe("#/p/builder/setup");
    expect(document.querySelector(".scope-chip")).toBeNull();
  });

  it("starts on from ?scopes=1 and carries the state into a part's link", async () => {
    await open(setupServer({ map: () => setupMap(rows()) }), "?scopes=1");
    expect(await screen.findByRole("switch", { name: "Show where each comes from" })).toBeChecked();
    expect(await screen.findByRole("link", { name: "Hooks" })).toHaveAttribute(
      "href",
      "#/p/builder/setup/hooks?scopes=1",
    );
  });

  it("dates the shell scope when Bar Tab started", async () => {
    await open(setupServer({ map: () => setupMap(rows()) }), "?scopes=1");
    expect(await screen.findByText(/^Seen at .+, when Bar Tab started$/)).toBeInTheDocument();
  });
});

describe("a project that is not on the list", () => {
  it("says so, links to how to get on it and reads Not read here in the project scopes", async () => {
    const list = rows().map((row) => ({
      ...row,
      scopes: cells({
        project_local: { state: "not_visible" as const },
        project: { state: "not_visible" as const },
        user: { state: "set" as const, summary: { code: "count", params: { n: "1" } } },
      }),
    }));
    await open(setupServer({ map: () => setupMap(list, { listed: false }) }), "?scopes=1");
    expect(await screen.findByText(/^Builder isn't on Bar Tab's project list/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "How a project gets on the list" }),
    ).toBeInTheDocument();
    const settings = need(document.querySelector<HTMLElement>('tr[data-part="settings"]'));
    expect(settings).toHaveTextContent("Project local Not read here");
    expect(settings).toHaveTextContent("Shared project Not read here");
  });
});
