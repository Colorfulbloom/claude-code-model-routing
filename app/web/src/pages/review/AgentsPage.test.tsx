import { focusManager } from "@tanstack/react-query";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { agentList, sessionList } from "@/test/review";
import { IDS, sessionAt } from "@/test/review-fixtures";
import { never, reviewServer } from "@/test/review-server";
import { agentRow, agentsAnswer } from "@/test/review-tables";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

type Server = ReturnType<typeof reviewServer>;

const open = (server: Server, query = "?range=30d", width = 1440) =>
  mount(`#/p/builder/review/agents${query}`, { server, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

/** The table's row for an agent, by its data attribute. */
function rowOf(table: HTMLElement, agent: string): HTMLElement {
  return need(table.querySelector<HTMLElement>(`tr[data-agent="${agent}"]`));
}

describe("first load", () => {
  it("shows bones with one spoken line and keeps the header", async () => {
    await open(reviewServer({ agents: () => never() }));
    expect(await screen.findByRole("heading", { level: 1, name: "Agents" })).toBeInTheDocument();
    expect(screen.getByText("Loading agents")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "Agents" })).toBeInTheDocument();
  });
});

describe("the table", () => {
  it("names its columns in the board's order", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Agent", "Set to", "Ran with", "Check", "Runs", "Cost", "No runs in this range"]);
  });

  it("shows an agent with a project file, what is set, what it ran with and the check", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const row = rowOf(table, "builder");
    const cells = within(row).getAllByRole("cell");
    expect(within(row).getByRole("rowheader")).toHaveTextContent("builderShared project");
    expect(cells[0]).toHaveTextContent("Fable 5.1 · xhigh");
    expect(cells[1]).toHaveTextContent("Fable 5.1 · medium");
    expect(cells[2]).toHaveTextContent("Overridden");
    expect(cells[3]).toHaveTextContent("5");
    expect(cells[4]).toHaveTextContent("$40.00");
  });

  it("shows Main session with its settings source and Unnamed agent with its own", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(rowOf(table, "@main")).getByRole("rowheader")).toHaveTextContent(
      "Main sessionSettings",
    );
    expect(within(rowOf(table, "@unnamed")).getByRole("rowheader")).toHaveTextContent(
      "Unnamed agentRuns with no agent type",
    );
  });

  it("says Nothing set and shows the Default status for an agent with a file that sets nothing", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const cells = within(rowOf(table, "@unnamed")).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Nothing set");
    expect(cells[2]).toHaveTextContent("Default");
  });

  it("says No agent file, Source unknown and Default for a type with no file", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const row = rowOf(table, "Explore");
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("No agent file");
    expect(cells[2]).toHaveTextContent("Default");
    const header = within(row).getByRole("rowheader");
    expect(header).toHaveTextContent("ExploreSource unknown");
    expect(header).toHaveAccessibleDescription(
      "Bar Tab found no user or project file for this agent type.",
    );
  });

  it("never shows the text None in any cell", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    for (const cell of within(table).getAllByRole("cell")) {
      expect(cell.textContent?.trim()).not.toBe("None");
    }
    expect(within(table).queryByText(/^none$/i)).toBeNull();
  });

  it("adds an Also line under Ran with for another pair the runs used", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const cells = within(rowOf(table, "reviewer")).getAllByRole("cell");
    expect(cells[1]).toHaveTextContent("Sonnet 5.5 · xhigh");
    expect(cells[1]).toHaveTextContent("Also Sonnet 5.5 · high on 4 runs");
    // An agent whose runs all used one pair has no Also line.
    expect(within(rowOf(table, "builder")).queryByText(/^Also /)).toBeNull();
  });

  it("lists the agent files that did not run under No runs in this range", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const group = within(table).getByRole("columnheader", { name: "No runs in this range" });
    expect(group).toHaveAttribute("scope", "colgroup");
    const migrator = rowOf(table, "migrator");
    expect(migrator).toHaveTextContent("migratorShared project");
    expect(migrator).toHaveTextContent("Opus 5.5 · high");
    expect(migrator).toHaveTextContent("$0.00");
    expect(rowOf(table, "release-notes")).toHaveTextContent("Sonnet 5.5 · medium");
    // The group comes after every row that ran.
    const rows = Array.from(table.querySelectorAll("tbody tr"));
    expect(rows.indexOf(migrator)).toBeGreaterThan(rows.indexOf(rowOf(table, "scribe")));
  });

  it("leaves out the group when every agent file ran", async () => {
    await open(reviewServer({ agents: () => agentsAnswer({ never_ran: [] }) }));
    await screen.findByRole("table", { name: "Agents" });
    expect(screen.queryByText("No runs in this range")).toBeNull();
  });

  it("shows a cost with unpriced requests as at least, as Summary does", async () => {
    const server = reviewServer({
      agents: () =>
        agentsAnswer({
          ran: [agentRow({ cost: 8.28, unpriced: { requests: 2, models: [IDS.fable] } })],
          never_ran: [],
        }),
    });
    await open(server);
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(rowOf(table, "builder")).getByText("at least $8.28")).toBeInTheDocument();
  });

  it("shows No price for an agent whose requests have no price", async () => {
    const server = reviewServer({
      agents: () => agentsAnswer({ ran: [agentRow({ cost: null, share: null })], never_ran: [] }),
    });
    await open(server);
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(rowOf(table, "builder")).getByText("No price")).toBeInTheDocument();
  });

  it("does not link a row anywhere new", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    expect(within(table).queryAllByRole("link")).toEqual([]);
  });

  it("says the API-rate note once, under the card", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    await screen.findByRole("table", { name: "Agents" });
    expect(screen.getAllByText(/^Costs are estimates at API list prices/)).toHaveLength(1);
    expect(screen.getByText(/Prices as of November 8/)).toBeInTheDocument();
  });

  it("says what a run is in a visible note, not in a title", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    const table = await screen.findByRole("table", { name: "Agents" });
    const note = screen.getByText(
      "Runs counts each agent run, plus one for the main session in each session.",
    );
    expect(note).toBeVisible();
    expect(table.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(table).getByRole("columnheader", { name: "Runs" })).not.toHaveAttribute("title");
  });

  it("says a price disagreement under the note", async () => {
    const server = reviewServer({
      agents: () =>
        agentsAnswer({
          prices: { as_of: "2026-11-08", source: "bundled", cross_check_state: "disagree" },
        }),
    });
    server.prices = {
      ...server.prices,
      cross_check: { state: "disagree", models: [IDS.opus] },
    };
    await open(server);
    expect(await screen.findByText(/Two price sources disagree on Opus 5\.5/)).toBeInTheDocument();
  });
});

describe("the setup half", () => {
  it("says it could not read the setup in each Set to cell, with no verdict, and keeps the rows", async () => {
    const server = reviewServer({
      agents: () =>
        agentsAnswer({
          ran: [
            agentRow({ set: null, set_reason: "read_failed", status: null }),
            agentRow({ agent: "scribe", set: null, set_reason: "read_failed", status: null }),
          ],
          never_ran: [],
          errors: [{ card: "agent_setup", code: "setup_unreadable" }],
        }),
    });
    await open(server);
    const table = await screen.findByRole("table", { name: "Agents" });
    const cells = within(rowOf(table, "builder")).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("Couldn't read its setup");
    expect(cells[2]).toHaveTextContent("–");
    expect(within(table).queryByText("Default")).toBeNull();
    expect(cells[4]).toHaveTextContent("$40.00");
    // One card error with Try again sits above the table, and it asks for the answer again.
    expect(screen.getByText("Couldn't load agent setup")).toBeInTheDocument();
    const before = server.calls.filter((path) => path.startsWith("/api/agents")).length;
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(server.calls.filter((path) => path.startsWith("/api/agents")).length).toBe(before + 1);
    });
  });

  it("shows no card error when the setup read worked", async () => {
    await open(reviewServer({ agents: () => agentsAnswer() }));
    await screen.findByRole("table", { name: "Agents" });
    expect(screen.queryByText("Couldn't load agent setup")).toBeNull();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("errors, stale answers and the empty range", () => {
  it("shows the card error with Try again, and loads the table on the next try", async () => {
    let fail = true;
    const server = reviewServer({ agents: () => (fail ? 500 : agentsAnswer()) });
    await open(server);
    expect(await screen.findByText("Couldn't load agents")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Agents" })).toBeInTheDocument();
    fail = false;
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table", { name: "Agents" })).toBeInTheDocument();
  });

  it("keeps the last answer and says when it was updated, while a refresh fails", async () => {
    let fail = false;
    const server = reviewServer({ agents: () => (fail ? 500 : agentsAnswer()) });
    await open(server);
    await screen.findByRole("table", { name: "Agents" });
    fail = true;
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    expect(
      await screen.findByText(/^Updated .+\. The latest refresh failed\.$/),
    ).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Agents" })).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load agents")).toBeNull();
  });

  it("shows one page-level card and no table for a range with no runs", async () => {
    const server = reviewServer({
      agents: () => agentList({ ran: [], never_ran: [] }),
      sessions: () =>
        sessionList([{ day: "2026-11-08", sessions: [sessionAt("old", "2026-11-08T19:20:00Z")] }]),
    });
    await open(server, "?range=7d");
    expect(
      await screen.findByRole("heading", {
        level: 2,
        name: "No sessions in Builder in the last 7 days",
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/^The last one ran yesterday at 2:20/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(1);
  });
});

describe("the range", () => {
  it("asks for the range in the link and keeps it in the page links", async () => {
    const server = reviewServer({ agents: () => agentsAnswer() });
    await open(server, "?range=90d");
    await screen.findByRole("table", { name: "Agents" });
    expect(
      server.calls.some((path) => path.startsWith("/api/agents?") && path.includes("range=90d")),
    ).toBe(true);
    expect(await screen.findByRole("button", { name: /Range Last 90 days/ })).toBeInTheDocument();
  });

  it("shows bones, not the old table, after a range change", async () => {
    const server = reviewServer({
      agents: (url) => (url.searchParams.get("range") === "30d" ? agentsAnswer() : never()),
    });
    await open(server);
    await screen.findByRole("table", { name: "Agents" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Range Last 30 days/ }));
    await user.click(await screen.findByRole("option", { name: /^Last 7 days/ }));
    await waitFor(() => {
      expect(screen.queryByRole("table", { name: "Agents" })).toBeNull();
    });
    expect(screen.getByText("Loading agents")).toBeInTheDocument();
  });
});
