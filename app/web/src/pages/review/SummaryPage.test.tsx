import { focusManager } from "@tanstack/react-query";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { reviewWindow, sessionList } from "@/test/review";
import {
  IDS,
  NO_UNPRICED,
  chartAnswer,
  chartEarlier,
  inEffect,
  midnight,
  sessionAt,
  summaryAnswer,
  todayWindow,
} from "@/test/review-fixtures";
import { never, reviewServer } from "@/test/review-server";

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
});

const open = (server: ReturnType<typeof reviewServer>, query = "?range=30d", width = 1440) =>
  mount(`#/p/builder/review/summary${query}`, { server, width });

const asked = (server: ReturnType<typeof reviewServer>, part: string): string[] =>
  server.calls.filter((path) => path.includes(part));

describe("first load", () => {
  it("shows bones on every card with one spoken line each, and the page header", async () => {
    const server = reviewServer({
      summary: () => never(),
      chart: () => never(),
    });
    await open(server);
    expect(await screen.findByRole("heading", { level: 1, name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText("Loading summary")).toBeInTheDocument();
    expect(screen.getByText("Loading cost per day")).toBeInTheDocument();
    expect(screen.getByText("Loading where the money went")).toBeInTheDocument();
    expect(screen.getByText("Loading model check")).toBeInTheDocument();
    expect(screen.getByText("Loading most expensive sessions")).toBeInTheDocument();
    expect(document.querySelectorAll("[aria-busy='true']").length).toBeGreaterThanOrEqual(5);
    // Nothing from an old range or a fake zero is on screen.
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText("$0.00")).toBeNull();
  });
});

describe("a full answer", () => {
  it("shows the title line, four tiles, the chart, money, model check and top sessions", async () => {
    const server = reviewServer({
      summary: () => summaryAnswer(),
      chart: () => chartAnswer(),
    });
    await open(server);
    expect(
      await screen.findByText("October 11 to November 9, compared with the 30 days before"),
    ).toBeInTheDocument();
    const tiles = document.querySelector(".tiles");
    expect(tiles).not.toBeNull();
    const inTiles = within(tiles as HTMLElement);
    expect(inTiles.getByText("API-rate estimate")).toBeInTheDocument();
    expect(inTiles.getByText("$12.50")).toBeInTheDocument();
    expect(inTiles.getByText("Up 25% from $10.00")).toBeInTheDocument();
    expect(inTiles.getByText("53")).toBeInTheDocument();
    expect(inTiles.getByText("Up 33% from 40")).toBeInTheDocument();
    expect(inTiles.getByText("900K")).toBeInTheDocument();
    expect(inTiles.getByText("80%")).toBeInTheDocument();
    expect(inTiles.getByText("Up 10 points from 70%")).toBeInTheDocument();

    expect(
      await screen.findByRole("img", {
        name: "Bar chart of cost per day for October 11 to November 9, $48.00 in all, most of it on Fable 5.1",
      }),
    ).toBeInTheDocument();
    const legend = document.querySelector(".review-legend");
    expect(legend).toHaveTextContent("Opus 5.5 $8.00");
    expect(legend).toHaveTextContent("Fable 5.1 $40.00");
    expect(screen.getByText("Made of")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "See what each model's cost is made of" }),
    ).toHaveAttribute("href", "#/p/builder/review/models?range=30d&section=kinds");
  });

  it("lists where the money went, with the model under each agent", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    await screen.findByText("Unnamed agent");
    const card = screen.getByRole("heading", { name: "Where the money went" }).closest("section");
    const inCard = within(need(card));
    expect(inCard.getByText("builder")).toBeInTheDocument();
    expect(inCard.getByText("Main session")).toBeInTheDocument();
    expect(inCard.getByText("Unnamed agent")).toBeInTheDocument();
    expect(inCard.getByText("$40.00")).toBeInTheDocument();
    expect(inCard.getByText("80%")).toBeInTheDocument();
    expect(inCard.getByText("<1%")).toBeInTheDocument();
  });

  it("shows the model check with its count, the finding and the rest line", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    expect(await screen.findByText("1 of 2 agents didn't run as set")).toBeInTheDocument();
    expect(screen.getByText("builder ran at medium, but it's set to xhigh.")).toBeInTheDocument();
    expect(screen.getByText("Overridden")).toBeInTheDocument();
    expect(screen.getByText("The other agent ran as set.")).toBeInTheDocument();
  });

  it("draws the model check as one-line rows, a chip and one sentence, with no reason text", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    await screen.findByText("1 of 2 agents didn't run as set");
    const rows = document.querySelectorAll<HTMLElement>(".live-mc-row");
    expect(rows).toHaveLength(1);
    expect(within(need(rows[0])).getByText("Overridden")).toBeInTheDocument();
    expect(rows[0]).toHaveTextContent("builder ran at medium, but it's set to xhigh.");
    expect(document.querySelector(".live-mc-body")).toBeNull();
    expect(document.querySelector(".live-mc-title")).toBeNull();
  });

  it("says Default, never None, when a row sets nothing", async () => {
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          model_check: {
            rows: [
              {
                ...inEffect,
                agent: "scout",
                set: { model: null, effort: null },
                status: "default",
                reason_code: "default",
                params: { setting: "model", settings: "model" },
              },
            ],
            in_effect_count: 0,
          },
        }),
      chart: () => chartAnswer(),
    });
    await open(server);
    expect(await screen.findByText("Default")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent("None");
  });

  it("opens each top session with the range kept, and links to every session", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    const link = await screen.findByRole("link", { name: /^November 2, 10:00\sAM$/ });
    expect(link).toHaveAttribute("href", "#/p/builder/review/sessions/s-top?range=30d");
    expect(screen.getByText("feature/quarter-close")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All 53 sessions" })).toHaveAttribute(
      "href",
      "#/p/builder/review/sessions?range=30d",
    );
  });

  it("says the API-rate note once, with the price date", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    await screen.findByRole("img", { name: /Bar chart of cost per day/ });
    expect(
      screen.getAllByText(
        "Costs are estimates at API list prices, not your bill. Prices as of November 8.",
      ),
    ).toHaveLength(1);
  });
});

describe("help", () => {
  it("puts a button on every tile, card and chart, with the unit in the chart's name", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    await screen.findByRole("img", { name: /Bar chart of cost per day/ });
    for (const name of [
      "About Cost",
      "About Sessions",
      "About Tokens",
      "About Read from cache",
      "About Where the money went",
      "About Model check",
      "About Most expensive sessions",
      "About Cost per day",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
  });

  it("hands a tile's popover the numbers on the tile", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    const user = userEvent.setup();
    await open(server);
    await user.click(await screen.findByRole("button", { name: "About Read from cache" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { level: 2, name: "Read from cache" })).toBeTruthy();
    expect(within(dialog).getByText("80%")).toBeInTheDocument();
    expect(within(dialog).getByText("Up 10 points from 70%")).toBeInTheDocument();
  });

  it("hands the cost chart's popover the kind totals from the Made of line", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    const user = userEvent.setup();
    await open(server);
    await screen.findByText("Made of");
    const made = need(document.querySelector(".review-kinds"));
    const totals = [...made.querySelectorAll("b.num")].map((node) => node.textContent);
    expect(totals).toHaveLength(4);
    await user.click(screen.getByRole("button", { name: "About Cost per day" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { level: 2, name: "Cost per day" })).toBeTruthy();
    for (const total of totals) {
      expect(within(dialog).getAllByText(need(total)).length).toBeGreaterThan(0);
    }
  });
});

describe("card errors", () => {
  it("shows an error on the model check alone, with Try again, when its part failed", async () => {
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          model_check: null,
          errors: [{ card: "model_check", code: "setup_unreadable" }],
        }),
      chart: () => chartAnswer(),
    });
    await open(server);
    expect(await screen.findByText("Couldn't load model check")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    // The other cards stay.
    expect(screen.getAllByText("Main session").length).toBeGreaterThan(0);
    expect(screen.getByText("$12.50")).toBeInTheDocument();
  });

  it("shows an error on the chart alone when its route fails", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => 500 });
    await open(server);
    expect(await screen.findByText("Couldn't load cost per day")).toBeInTheDocument();
    expect(screen.getByText("$12.50")).toBeInTheDocument();
    expect(await screen.findAllByText("Main session")).not.toHaveLength(0);
  });

  it("asks again when Try again is pressed", async () => {
    let fail = true;
    const server = reviewServer({
      summary: () => summaryAnswer(),
      chart: () => (fail ? 500 : chartAnswer()),
    });
    const user = userEvent.setup();
    await open(server);
    await screen.findByText("Couldn't load cost per day");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(
      await screen.findByRole("img", { name: /Bar chart of cost per day/ }),
    ).toBeInTheDocument();
  });

  it("shows an error on every summary card when the summary fails", async () => {
    const server = reviewServer({ summary: () => 500, chart: () => chartAnswer() });
    await open(server);
    expect(await screen.findByText("Couldn't load summary")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load where the money went")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load model check")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load most expensive sessions")).toBeInTheDocument();
    expect(
      await screen.findByRole("img", { name: /Bar chart of cost per day/ }),
    ).toBeInTheDocument();
  });
});

describe("a failed refresh", () => {
  it("keeps the last answer and says when it was updated", async () => {
    let fail = false;
    const server = reviewServer({
      summary: () => (fail ? 500 : summaryAnswer()),
      chart: () => (fail ? 500 : chartAnswer()),
    });
    await open(server);
    await screen.findByText("$12.50");
    fail = true;
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => {
      expect(
        screen.getAllByText(/^Updated .+\. The latest refresh failed\.$/).length,
      ).toBeGreaterThan(0);
    });
    expect(screen.getByText("$12.50")).toBeInTheDocument();
    expect(screen.getAllByText("Main session").length).toBeGreaterThan(0);
    expect(screen.queryByText("Couldn't load summary")).toBeNull();
  });
});

describe("an empty range", () => {
  it("shows one page-level card with the last session time, and nothing else", async () => {
    const server = reviewServer({
      summary: () => summaryAnswer({ session_count: 0, top_sessions: [], money: [] }),
      chart: () => chartAnswer(),
      sessions: () =>
        sessionList([{ day: "2026-11-08", sessions: [sessionAt("old", "2026-11-08T19:20:00Z")] }]),
    });
    await open(server);
    expect(
      await screen.findByRole("heading", { name: "No sessions in Builder in the last 30 days" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(/^The last one ran yesterday at 2:20\sPM\. A new session shows here/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Show the last 7 days" })).toHaveAttribute(
      "href",
      "#/p/builder/review/summary?range=7d",
    );
    expect(screen.getByRole("link", { name: "Open Live" })).toHaveAttribute(
      "href",
      "#/p/builder/live",
    );
    // No card of its own says it is empty.
    expect(document.querySelector(".tiles")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(screen.queryByText("Where the money went")).toBeNull();
    // The range still shows, so the person can change it.
    expect(screen.getByRole("button", { name: "Range Last 30 days" })).toBeInTheDocument();
  });

  it("uses the first-run words when All is empty", async () => {
    const server = reviewServer({
      summary: () => summaryAnswer({ range: "all", session_count: 0 }),
      chart: () => chartAnswer({ range: "all" }),
    });
    await open(server, "?range=all");
    expect(
      await screen.findByRole("heading", { name: "No sessions in Builder yet" }),
    ).toBeInTheDocument();
    expect(server.calls.filter((path) => path.includes("/api/sessions?"))).toHaveLength(0);
  });
});

describe("unpriced requests", () => {
  const unpriced = { requests: 12, models: [IDS.fable] };

  it("says at least on the cost tile, the legend and the kinds, and counts the requests", async () => {
    const base = summaryAnswer();
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          tiles: { ...base.tiles, cost: { ...base.tiles.cost, unpriced } },
          money: [
            { agent: "builder", model: IDS.fable, cost: 40, share: 0.8, requests: 9, unpriced },
          ],
        }),
      chart: () =>
        chartAnswer({
          unpriced,
          legend: [
            { model: IDS.opus, cost: 8, requests: 12, unpriced: NO_UNPRICED },
            { model: IDS.fable, cost: 40, requests: 12, unpriced },
          ],
        }),
    });
    await open(server);
    expect(await screen.findByText("at least $12.50")).toBeInTheDocument();
    expect(screen.getByText("12 requests have no price")).toBeInTheDocument();
    await screen.findByText("Made of");
    expect(document.querySelector(".review-legend")).toHaveTextContent("Fable 5.1 at least $40.00");
    expect(
      screen.getByText(
        "12 requests on Fable 5.1 have no price, so they're left out of these bars.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/^at least \$/).length).toBeGreaterThanOrEqual(3);
  });
});

describe("a partial prior", () => {
  it("with no records in it, shows the averages and says where the records start", async () => {
    const base = summaryAnswer();
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          window: reviewWindow({
            prior_partial: true,
            partial: true,
            oldest: "2026-10-20T12:00:00Z",
          }),
          tiles: {
            cost: { ...base.tiles.cost, prior: 0, change_pct: null, change_abs: null },
            sessions: { value: 53, prior: 0, change_pct: null, change_abs: null },
            tokens: { value: 900000, prior: 0, change_pct: null, change_abs: null },
            cache_share: { value: 0.8, prior: 0, change_abs: null },
          },
        }),
      chart: () => chartAnswer(),
    });
    await open(server);
    expect(
      await screen.findByText(
        "October 11 to November 9. Records start on October 20, so there's nothing earlier to compare with.",
      ),
    ).toBeInTheDocument();
    const tiles = need(document.querySelector<HTMLElement>(".tiles"));
    expect(tiles.textContent).not.toMatch(/Up from|Down from/);
    expect(within(tiles).getAllByText(/a day on average$/)).toHaveLength(3);
    expect(within(tiles).getByText("Across the whole range")).toBeInTheDocument();
  });

  it("with records in it, never shows a percent and does not claim there is nothing to compare", async () => {
    const base = summaryAnswer();
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          window: reviewWindow({
            prior_partial: true,
            partial: true,
            oldest: "2026-09-20T12:00:00Z",
          }),
          tiles: {
            cost: { ...base.tiles.cost, prior: 4, change_pct: null, change_abs: null },
            sessions: { value: 53, prior: 0, change_pct: null, change_abs: null },
            tokens: { value: 900000, prior: 100000, change_pct: null, change_abs: null },
            cache_share: { value: 0.8, prior: 0.7, change_abs: null },
          },
        }),
      chart: () => chartAnswer(),
    });
    await open(server);
    expect(
      await screen.findByText("October 11 to November 9, compared with the 30 days before"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/nothing earlier to compare with/)).not.toBeInTheDocument();
    const tiles = within(need(document.querySelector<HTMLElement>(".tiles")));
    expect(tiles.getByText("Up from $4.00")).toBeInTheDocument();
    expect(tiles.getByText("Up from 0")).toBeInTheDocument();
    expect(tiles.getByText("Up from 100K")).toBeInTheDocument();
    expect(tiles.getByText("Up from 70%")).toBeInTheDocument();
    expect(document.querySelector(".tiles")?.textContent).not.toMatch(/\d%\s*from/);
  });
});

describe("Today", () => {
  it("compares with yesterday by the same time and charts the hours", async () => {
    const server = reviewServer({
      summary: () => summaryAnswer({ range: "today", window: todayWindow }),
      chart: () =>
        chartAnswer({
          range: "today",
          window: todayWindow,
          chart: { ...chartAnswer().chart, unit: "hour", start: midnight("2026-11-09") },
        }),
    });
    await open(server, "?range=today");
    expect(
      await screen.findByText(/^Today to 10:00\sAM, compared with yesterday to 10:00\sAM$/),
    ).toBeInTheDocument();
    expect(screen.getByText(/^\$10\.00 yesterday by 10:00\sAM$/)).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 2, name: "Cost per hour" }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/^Today to 10:00\sAM$/)).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /^Bar chart of cost per hour for Today to 10:00\sAM/ }),
    ).toBeInTheDocument();
  });
});

describe("All", () => {
  it("uses the unit the server sends, has no pager and no comparison", async () => {
    const base = summaryAnswer();
    const server = reviewServer({
      summary: () =>
        summaryAnswer({
          range: "all",
          window: reviewWindow({
            start: "2026-09-10T04:00:00Z",
            prior_start: null,
            prior_end: null,
            oldest: "2026-09-10T12:00:00Z",
          }),
          tiles: {
            cost: { ...base.tiles.cost, prior: null, change_pct: null, change_abs: null },
            sessions: { value: 90, prior: null, change_pct: null, change_abs: null },
            tokens: { value: 90_000_000, prior: null, change_pct: null, change_abs: null },
            cache_share: { value: 0.8, prior: null, change_abs: null },
          },
        }),
      chart: () =>
        chartAnswer({
          range: "all",
          chart: {
            ...chartAnswer().chart,
            unit: "week",
            has_earlier: false,
            has_later: false,
            earlier_reason: "no_earlier_data",
          },
        }),
    });
    await open(server, "?range=all");
    expect(await screen.findByText("Everything recorded since September 10")).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { level: 2, name: "Cost per week" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Across the whole range")).toBeInTheDocument();
    expect(screen.getByText("$0.20 a day on average")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Cost per week" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Earlier/ })).toBeNull();
  });
});

describe("the pager", () => {
  it("keeps Later visible and disabled on the newest window, with its reason", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    const later = await screen.findByRole("button", { name: "Later" });
    expect(later).toHaveAttribute("aria-disabled", "true");
    expect(later).toHaveAccessibleDescription("Nothing later yet");
    const earlier = screen.getByRole("button", {
      name: "Show earlier costs, September 11 to October 10",
    });
    expect(earlier).not.toHaveAttribute("aria-disabled");
    const group = screen.getByRole("group", { name: "Cost per day" });
    expect(within(group).getByRole("status")).toHaveTextContent("October 11 to November 9");
  });

  it("moves back one window, never touches the tiles, and says Earlier is at its end", async () => {
    const server = reviewServer({
      summary: () => summaryAnswer(),
      chart: (url) => (url.searchParams.get("end") === null ? chartAnswer() : chartEarlier()),
    });
    const user = userEvent.setup();
    await open(server);
    const summaryCalls = asked(server, "/api/summary").length;
    await user.click(
      await screen.findByRole("button", { name: "Show earlier costs, September 11 to October 10" }),
    );
    expect(await screen.findByRole("button", { name: "Earlier" })).toHaveAccessibleDescription(
      "Nothing earlier. Records start on August 1.",
    );
    expect(screen.getByRole("button", { name: "Earlier" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(asked(server, "/api/cost-chart").some((path) => path.includes("end=2026-10-10"))).toBe(
      true,
    );
    expect(
      screen.getByText("September 11 to October 10", { selector: ".pager-window" }),
    ).toBeInTheDocument();
    // Later is open now, and Back to newest is offered.
    expect(screen.getByRole("button", { name: /^Show later costs, / })).not.toHaveAttribute(
      "aria-disabled",
    );
    expect(asked(server, "/api/summary")).toHaveLength(summaryCalls);
    expect(screen.getByText("$12.50")).toBeInTheDocument();
    // The tiles keep their range, and a note under the pager says so while the chart is paged back.
    expect(screen.getByText("The tiles above still cover the last 30 days.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to newest" }));
    expect(await screen.findByRole("button", { name: "Later" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByRole("button", { name: "Back to newest" })).toBeNull();
    expect(screen.queryByText(/The tiles above still cover/)).toBeNull();
  });

  it("keeps focus on the Earlier button while the next window loads", async () => {
    let release: () => void = () => undefined;
    const server = reviewServer({
      summary: () => summaryAnswer(),
      chart: (url) =>
        url.searchParams.get("end") === null
          ? chartAnswer()
          : new Promise((resolve) => {
              release = () => {
                resolve(chartEarlier());
              };
            }),
    });
    const user = userEvent.setup();
    await open(server);
    const earlier = await screen.findByRole("button", {
      name: "Show earlier costs, September 11 to October 10",
    });
    await user.click(earlier);
    expect(screen.getByText("Loading cost per day")).toBeInTheDocument();
    expect(earlier).toBeInTheDocument();
    release();
    expect(
      await screen.findByRole("img", { name: /Bar chart of cost per day/ }),
    ).toBeInTheDocument();
    // The pager stayed mounted, so the same button holds focus, now at its end.
    expect(earlier).toBeInTheDocument();
    expect(earlier).toHaveFocus();
  });
});

describe("the range", () => {
  it("changes the URL, asks again for the new range and says it through the status", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    const user = userEvent.setup();
    const { router } = await open(server);
    await screen.findByText("$12.50");
    await user.click(screen.getByRole("button", { name: "Range Last 30 days" }));
    await user.click(await screen.findByRole("option", { name: /Last 7 days/ }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?range=7d");
    });
    expect(document.querySelector("div.sr-only[role='status']")).toHaveTextContent(
      "Showing the last 7 days",
    );
    await waitFor(() => {
      expect(asked(server, "/api/summary").some((path) => path.includes("range=7d"))).toBe(true);
    });
    expect(asked(server, "/api/cost-chart").some((path) => path.includes("range=7d"))).toBe(true);
    expect(screen.getByRole("button", { name: "Range Last 7 days" })).toBeInTheDocument();
  });

  it("shows bones, not the old range's numbers, while the new range loads", async () => {
    const server = reviewServer({
      summary: (url) => (url.searchParams.get("range") === "7d" ? never() : summaryAnswer()),
      chart: (url) => (url.searchParams.get("range") === "7d" ? never() : chartAnswer()),
    });
    const user = userEvent.setup();
    await open(server);
    await screen.findByText("$12.50");
    await user.click(screen.getByRole("button", { name: "Range Last 30 days" }));
    await user.click(await screen.findByRole("option", { name: /Last 7 days/ }));
    expect(await screen.findByText("Loading summary")).toBeInTheDocument();
    expect(screen.queryByText("$12.50")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("lists the windows under the options, and says the range in each option", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    const user = userEvent.setup();
    await open(server);
    await screen.findByText("$12.50");
    await user.click(screen.getByRole("button", { name: "Range Last 30 days" }));
    const options = await screen.findAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([
      expect.stringMatching(/^TodayMidnight to 10:00\sAM$/),
      "Last 7 daysNovember 3 to November 9",
      "Last 30 daysOctober 11 to November 9",
      "Last 90 daysAugust 12 to November 9",
      "Last 12 monthsNovember 10, 2025 to November 9, 2026",
      "All timeSince August 1",
    ]);
  });

  it("falls back to 30 days for a bad range, replaces the URL and never asks with it", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    const { router } = await open(server, "?range=bogus");
    await screen.findByText("$12.50");
    await waitFor(() => {
      expect(router.state.location.search).toBe("?range=30d");
    });
    expect(router.state.historyAction).toBe("REPLACE");
    expect(server.calls.some((path) => path.includes("bogus"))).toBe(false);
  });
});

describe("at phone width", () => {
  it("shows the segmented Review pages with the range kept in each link", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server, "?range=7d", 375);
    const nav = await screen.findByRole("navigation", { name: "Review" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual([
      "Summary",
      "Sessions",
      "Agents",
      "Models",
    ]);
    expect(links[1]).toHaveAttribute("href", "#/p/builder/review/sessions?range=7d");
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });

  it("leaves the segmented pages out at desktop width", async () => {
    const server = reviewServer({ summary: () => summaryAnswer(), chart: () => chartAnswer() });
    await open(server);
    await screen.findByText("$12.50");
    expect(screen.queryByRole("navigation", { name: "Review" })).toBeNull();
  });
});
