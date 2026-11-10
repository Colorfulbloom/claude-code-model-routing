import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { sessionList } from "@/test/review";
import { IDS, NO_UNPRICED, manySessions, sessionAt, sessionsPage } from "@/test/review-fixtures";
import { never, reviewServer } from "@/test/review-server";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

type Server = ReturnType<typeof reviewServer>;

const open = (server: Server, query = "?range=30d", width = 1440) =>
  mount(`#/p/builder/review/sessions${query}`, { server, width });

/** 53 sessions in two pages, 50 then 3. */
const paged = (url: URL) =>
  url.searchParams.get("cursor") === null
    ? sessionsPage(manySessions(0, 50), { count: 53, next: "c1" })
    : sessionsPage(manySessions(50, 3), { count: 53, next: null });

describe("first load", () => {
  it("shows bones with one spoken line and keeps the header", async () => {
    await open(reviewServer({ sessions: () => never() }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sessions" })).toBeInTheDocument();
    expect(screen.getByText("Loading sessions")).toBeInTheDocument();
    expect(document.querySelector("[aria-busy='true']")).not.toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("the list", () => {
  it("groups sessions by day under Today, Yesterday and a date", async () => {
    const server = reviewServer({
      sessions: () =>
        sessionList(
          [
            {
              day: "2026-11-09",
              sessions: [
                sessionAt("run", "2026-11-09T14:10:00Z", {
                  state: "working",
                  branch: "feature/quarter-close",
                  agents: ["deep-reasoner", "@main"],
                  runs: 8,
                  tokens: 5_300_000,
                  cost: 8.28,
                }),
              ],
            },
            {
              day: "2026-11-08",
              sessions: [sessionAt("y", "2026-11-08T21:58:00Z", { cost: 1.81 })],
            },
            {
              day: "2026-11-05",
              sessions: [sessionAt("d", "2026-11-05T17:00:00Z", { cost: 5.55 })],
            },
          ],
          { range: "30d" },
        ),
    });
    await open(server);
    const table = await screen.findByRole("table", { name: "Sessions" });
    const inTable = within(table);
    // The day headers are `scope="colgroup"` cells, so they read as column headers after the five.
    expect(inTable.getAllByRole("columnheader").map((h) => h.textContent)).toEqual([
      "Session",
      "Agents",
      "Runs",
      "Tokens",
      "Cost",
      "Today",
      "Yesterday",
      "November 5",
    ]);
    const link = inTable.getByRole("link", { name: /^9:10\sAM$/ });
    expect(link).toHaveAttribute("href", "#/p/builder/review/sessions/run?range=30d");
    expect(inTable.getByText("Working")).toBeInTheDocument();
    expect(inTable.getByText("feature/quarter-close")).toBeInTheDocument();
    expect(inTable.getAllByText("Main session")).toHaveLength(3);
    expect(inTable.getByText("5.3M")).toBeInTheDocument();
    expect(inTable.getByText("$8.28")).toBeInTheDocument();
    // The count sits in the card header, and the API-rate note once, under the list.
    expect(screen.getByText("3", { selector: ".card-count" })).toBeInTheDocument();
    expect(screen.getAllByText(/^Costs are estimates at API list prices/)).toHaveLength(1);
  });

  it("says No git branch for a session with none", async () => {
    const server = reviewServer({
      sessions: () =>
        sessionList([{ day: "2026-11-09", sessions: [sessionAt("a", "2026-11-09T14:00:00Z")] }]),
    });
    await open(server);
    expect(await screen.findByText("No git branch")).toBeInTheDocument();
  });

  it("flags a session that started before the range, with its description on the link", async () => {
    const server = reviewServer({
      sessions: () =>
        sessionList([
          {
            day: "2026-10-11",
            sessions: [
              sessionAt("early", "2026-10-09T17:00:00Z", {
                started_before_range: true,
                cost: 2.5,
                whole: { tokens: 9_000_000, cost: 20, unpriced: NO_UNPRICED },
              }),
            ],
          },
        ]),
    });
    await open(server);
    const badge = await screen.findByText("Started earlier");
    expect(badge).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /^October 9, 1:00\sPM$/ });
    expect(link).toHaveAccessibleDescription(
      "Started before this range. The cost shown is only the part inside it.",
    );
    // The in-range cost shows, not the whole session's.
    expect(screen.getByText("$2.50")).toBeInTheDocument();
    expect(screen.queryByText("$20.00")).toBeNull();
  });

  it("shows at least for a session with unpriced requests", async () => {
    const server = reviewServer({
      sessions: () =>
        sessionList([
          {
            day: "2026-11-09",
            sessions: [
              sessionAt("u", "2026-11-09T14:00:00Z", {
                cost: 3,
                unpriced: { requests: 2, models: [IDS.fable] },
              }),
            ],
          },
        ]),
    });
    await open(server);
    expect(await screen.findByText("at least $3.00")).toBeInTheDocument();
  });

  it("says what a run is in a visible note, not in a title", async () => {
    await open(
      reviewServer({
        sessions: () =>
          sessionList([{ day: "2026-11-09", sessions: [sessionAt("a", "2026-11-09T14:00:00Z")] }]),
      }),
    );
    const table = await screen.findByRole("table", { name: "Sessions" });
    const note = screen.getByText(
      "Runs counts each agent run, plus one for the main session in each session.",
    );
    expect(note).toBeVisible();
    expect(table.compareDocumentPosition(note) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(within(table).getByRole("columnheader", { name: "Runs" })).not.toHaveAttribute("title");
  });

  it("says the list is complete, in the singular and the plural", async () => {
    const one = reviewServer({
      sessions: () =>
        sessionList([{ day: "2026-11-09", sessions: [sessionAt("a", "2026-11-09T14:00:00Z")] }]),
    });
    await open(one);
    expect(await screen.findByText("That's the only session")).toBeInTheDocument();
    cleanup();
    const many = reviewServer({
      sessions: () => sessionsPage(manySessions(0, 3), { count: 3, next: null }),
    });
    await open(many);
    expect(await screen.findByText("That's all 3 sessions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show/ })).toBeNull();
  });
});

describe("Show more", () => {
  it("says how many are shown, loads the next page and moves focus to its first new row", async () => {
    const server = reviewServer({ sessions: paged });
    const user = userEvent.setup();
    await open(server);
    expect(await screen.findByText("Showing 50 of 53")).toBeInTheDocument();
    expect(document.querySelectorAll("tbody .review-row")).toHaveLength(50);
    await user.click(screen.getByRole("button", { name: "Show 3 more" }));
    await waitFor(() => {
      expect(document.querySelectorAll("tbody .review-row")).toHaveLength(53);
    });
    await waitFor(() => {
      expect(document.querySelector('[data-session="s50"]')).toHaveFocus();
    });
    expect(screen.getByText("That's all 53 sessions")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Show \d+ more/ })).toBeNull();
    const calls = server.calls.filter((path) => path.includes("/api/sessions?"));
    expect(calls.some((path) => path.includes("cursor=c1"))).toBe(true);
  });

  it("offers one page at a time, never more than 50", async () => {
    const server = reviewServer({
      sessions: (url) =>
        url.searchParams.get("cursor") === null
          ? sessionsPage(manySessions(0, 50), { count: 180, next: "c1" })
          : sessionsPage(manySessions(50, 50), { count: 180, next: "c2" }),
    });
    await open(server);
    expect(await screen.findByRole("button", { name: "Show 50 more" })).toBeInTheDocument();
    expect(screen.getByText("Showing 50 of 180")).toBeInTheDocument();
  });

  it("joins a day that runs across the page break under one header", async () => {
    const server = reviewServer({
      sessions: (url) =>
        url.searchParams.get("cursor") === null
          ? sessionList(
              [{ day: "2026-11-09", sessions: [sessionAt("a", "2026-11-09T14:00:00Z")] }],
              {
                count: 2,
                next: "c1",
              },
            )
          : sessionList(
              [{ day: "2026-11-09", sessions: [sessionAt("b", "2026-11-09T13:00:00Z")] }],
              {
                count: 2,
                next: null,
              },
            ),
    });
    const user = userEvent.setup();
    await open(server);
    await user.click(await screen.findByRole("button", { name: "Show 1 more" }));
    await screen.findByText("That's all 2 sessions");
    expect(screen.getAllByRole("columnheader", { name: "Today" })).toHaveLength(1);
    expect(document.querySelectorAll("tbody .review-row")).toHaveLength(2);
  });

  it("keeps the rows and shows the error by the button when a page fails, then retries", async () => {
    let fail = true;
    const server = reviewServer({
      sessions: (url) => (url.searchParams.get("cursor") !== null && fail ? 500 : paged(url)),
    });
    const user = userEvent.setup();
    await open(server);
    await user.click(await screen.findByRole("button", { name: "Show 3 more" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load sessions");
    expect(document.querySelectorAll("tbody .review-row")).toHaveLength(50);
    expect(screen.queryByText("Couldn't load sessions", { selector: "h3" })).toBeNull();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => {
      expect(document.querySelectorAll("tbody .review-row")).toHaveLength(53);
    });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("states", () => {
  it("shows an error card with Try again when the list fails", async () => {
    await open(reviewServer({ sessions: () => 500 }));
    expect(await screen.findByText("Couldn't load sessions")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Sessions" })).toBeInTheDocument();
  });

  it("shows the one page-level card for an empty range, naming the range", async () => {
    const server = reviewServer({
      sessions: (url) =>
        url.searchParams.get("range") === "all"
          ? sessionList([
              { day: "2026-11-03", sessions: [sessionAt("old", "2026-11-03T15:30:00Z")] },
            ])
          : sessionList([], { count: 0 }),
    });
    await open(server, "?range=7d");
    expect(
      await screen.findByRole("heading", { name: "No sessions in Builder in the last 7 days" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/^The last one ran on November 3 at 10:30\sAM\./),
    ).toBeInTheDocument();
    // On 7 days the "Show the last 7 days" action would go nowhere, so it is left out.
    expect(screen.queryByRole("link", { name: "Show the last 7 days" })).toBeNull();
    expect(screen.getByRole("link", { name: "Open Live" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("the range and the pages", () => {
  it("reloads the list for a new range and starts again from the first page", async () => {
    const server = reviewServer({ sessions: paged });
    const user = userEvent.setup();
    await open(server);
    await user.click(await screen.findByRole("button", { name: "Show 3 more" }));
    await screen.findByText("That's all 53 sessions");
    await user.click(screen.getByRole("button", { name: "Range Last 30 days" }));
    await user.click(await screen.findByRole("option", { name: /Last 90 days/ }));
    await waitFor(() => {
      expect(
        server.calls.some((path) => path.includes("/api/sessions?") && path.includes("range=90d")),
      ).toBe(true);
    });
    expect(await screen.findByText("Showing 50 of 53")).toBeInTheDocument();
  });

  it("keeps the range in the segmented pages at phone width", async () => {
    const server = reviewServer({ sessions: paged });
    await open(server, "?range=90d", 375);
    const nav = await screen.findByRole("navigation", { name: "Review" });
    const links = within(nav).getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "#/p/builder/review/summary?range=90d");
    expect(links[1]).toHaveAttribute("aria-current", "page");
  });
});
