import { focusManager } from "@tanstack/react-query";
import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { postStatus } from "@/app/harness";
import { resetViewport } from "@/test/media";
import { mount } from "@/test/mount";
import { modelList, sessionList } from "@/test/review";
import { IDS, sessionAt } from "@/test/review-fixtures";
import { never, reviewServer } from "@/test/review-server";
import { modelRow, modelsAnswer } from "@/test/review-tables";

afterEach(() => {
  cleanup();
  resetViewport();
});

beforeEach(() => {
  postStatus("");
  window.scrollTo = () => undefined;
  Element.prototype.scrollIntoView = () => undefined;
});

type Server = ReturnType<typeof reviewServer>;

const open = (server: Server, query = "?range=30d", width = 1440) =>
  mount(`#/p/builder/review/models${query}`, { server, width });

function need<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error("missing");
  return value;
}

const rowOf = (table: HTMLElement, model: string): HTMLElement =>
  need(table.querySelector<HTMLElement>(`tr[data-model="${model}"]`));

const IMAGE =
  "Chart of what each model's cost is made of for October 11 to November 9, at least $305.91 in all, most of it on Fable 5.1";

describe("first load", () => {
  it("shows bones on both cards with one spoken line each, and keeps the header", async () => {
    await open(reviewServer({ models: () => never() }));
    expect(await screen.findByRole("heading", { level: 1, name: "Models" })).toBeInTheDocument();
    expect(screen.getByText("Loading models")).toBeInTheDocument();
    expect(screen.getByText("Loading what the cost is made of")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("heading", { level: 2, name: "Models" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: "What the cost is made of" }),
    ).toBeInTheDocument();
  });
});

describe("the table", () => {
  it("names its columns in the board's order", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const table = await screen.findByRole("table", { name: "Models" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["Model", "Cost", "Share", "Tokens", "From cache", "Used by"]);
  });

  it("shows each model with its cost, share, tokens, cache share and the agents that used it", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const table = await screen.findByRole("table", { name: "Models" });
    const row = rowOf(table, IDS.fable);
    expect(within(row).getByRole("rowheader")).toHaveTextContent("Fable 5.1");
    const cells = within(row).getAllByRole("cell");
    expect(cells[0]).toHaveTextContent("$241.92");
    expect(cells[1]).toHaveTextContent("76%");
    expect(cells[2]).toHaveTextContent("58.7M");
    expect(cells[3]).toHaveTextContent("79%");
    expect(cells[4]).toHaveTextContent("builderUnnamed agent");
    expect(within(rowOf(table, IDS.opus)).getByText("Main session")).toBeInTheDocument();
    expect(within(rowOf(table, IDS.haiku)).getByText("<1%")).toBeInTheDocument();
  });

  it("keeps a model with no price, with No price and no share", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const table = await screen.findByRole("table", { name: "Models" });
    const row = rowOf(table, "claude-sonnet-5-5");
    const cells = within(row).getAllByRole("cell");
    expect(within(row).getByRole("rowheader")).toHaveTextContent("Sonnet 5.5");
    expect(cells[0]).toHaveTextContent("No price");
    expect(cells[1]).toHaveTextContent("–");
    expect(need(cells[1]).querySelector(".share-bar")).toBeNull();
    expect(cells[2]).toHaveTextContent("17.0M");
  });

  it("says the phone line under each name, hidden from assistive tech", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const table = await screen.findByRole("table", { name: "Models" });
    const line = need(rowOf(table, IDS.fable).querySelector<HTMLElement>(".review-models-phone"));
    expect(line).toHaveTextContent("76% · 58.7M · 79% from cache");
    expect(line).toHaveAttribute("aria-hidden", "true");
  });

  it("shows a cost with unpriced requests as at least", async () => {
    const server = reviewServer({
      models: () =>
        modelsAnswer({
          rows: [modelRow({ cost: 8.28, unpriced: { requests: 2, models: [IDS.fable] } })],
        }),
    });
    await open(server);
    const table = await screen.findByRole("table", { name: "Models" });
    expect(within(table).getByText("at least $8.28")).toBeInTheDocument();
  });

  it("says the API-rate note once, under the table", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    await screen.findByRole("table", { name: "Models" });
    expect(screen.getAllByText(/^Costs are estimates at API list prices/)).toHaveLength(1);
  });
});

describe("what the cost is made of", () => {
  it("lists the four kinds with their totals, then the note about patterns", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    await screen.findByRole("table", { name: "Models" });
    const legend = need(document.querySelector<HTMLElement>(".review-models-legend"));
    expect(Array.from(legend.querySelectorAll("li")).map((li) => li.textContent)).toEqual([
      "Cache read at least $17.00",
      "Input at least $33.88",
      "Cache write at least $153.46",
      "Output at least $101.57",
    ]);
    expect(
      screen.getByText("Patterns show the kind of cost. Colors show the model."),
    ).toBeInTheDocument();
  });

  it("draws the chart as one image with its label", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const image = await screen.findByRole("img", { name: IMAGE });
    expect(image.querySelectorAll("li")).toHaveLength(4);
  });

  it("gives each model a stack of kind patterns in the board's order, and the amounts as text", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const image = await screen.findByRole("img", { name: IMAGE });
    const fable = need(image.querySelector<HTMLElement>(`li[data-model="${IDS.fable}"]`));
    const patterns = Array.from(fable.querySelectorAll(".review-models-stack i")).map(
      (piece) => /review-models-kp(\d)/.exec(piece.className)?.[1],
    );
    expect(patterns).toEqual(["1", "2", "3", "4"]);
    expect(fable).toHaveTextContent("$241.91");
    expect(fable).toHaveTextContent(
      "Cache write $121.82, Output $83.25, Input $25.53, Cache read $11.31",
    );
    expect(fable.querySelector(".review-models-ink-fable")).not.toBeNull();
  });

  it("gives a model with no price no stack, and says No price", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    const image = await screen.findByRole("img", { name: IMAGE });
    const sonnet = need(image.querySelector<HTMLElement>('li[data-model="claude-sonnet-5-5"]'));
    expect(sonnet.querySelectorAll(".review-models-stack i")).toHaveLength(0);
    expect(sonnet).toHaveTextContent("No price");
  });

  it("is the section the Made of link asks for, and takes focus once", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }), "?range=30d&section=kinds");
    const heading = await screen.findByRole("heading", {
      level: 2,
      name: "What the cost is made of",
    });
    await waitFor(() => {
      expect(heading).toHaveFocus();
    });
    expect(document.getElementById("review-models-kinds")).toContainElement(heading);
  });

  it("leaves focus on the page heading when the link asks for no section", async () => {
    await open(reviewServer({ models: () => modelsAnswer() }));
    await screen.findByRole("table", { name: "Models" });
    expect(screen.getByRole("heading", { level: 1, name: "Models" })).toHaveFocus();
  });
});

describe("errors, stale answers and the empty range", () => {
  it("shows the card error on both cards, and loads them on the next try", async () => {
    let fail = true;
    const server = reviewServer({ models: () => (fail ? 500 : modelsAnswer()) });
    await open(server);
    expect(await screen.findByText("Couldn't load models")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load what the cost is made of")).toBeInTheDocument();
    // The kinds section stays on the page, so the Made of link always has somewhere to land.
    expect(document.getElementById("review-models-kinds")).not.toBeNull();
    fail = false;
    await userEvent.setup().click(need(screen.getAllByRole("button", { name: "Try again" })[0]));
    expect(await screen.findByRole("table", { name: "Models" })).toBeInTheDocument();
  });

  it("keeps the last answer and says when it was updated, while a refresh fails", async () => {
    let fail = false;
    const server = reviewServer({ models: () => (fail ? 500 : modelsAnswer()) });
    await open(server);
    await screen.findByRole("table", { name: "Models" });
    fail = true;
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => {
      expect(screen.getAllByText(/^Updated .+\. The latest refresh failed\.$/)).toHaveLength(2);
    });
    expect(screen.getByRole("table", { name: "Models" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: IMAGE })).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load models")).toBeNull();
  });

  it("shows one page-level card and nothing else for a range with no requests", async () => {
    const server = reviewServer({
      models: () => modelList({ rows: [], kinds: [] }),
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
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(document.getElementById("review-models-kinds")).toBeNull();
  });
});

describe("the range", () => {
  it("shows bones, not the old table, after a range change", async () => {
    const server = reviewServer({
      models: (url) => (url.searchParams.get("range") === "30d" ? modelsAnswer() : never()),
    });
    await open(server);
    await screen.findByRole("table", { name: "Models" });
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Range Last 30 days/ }));
    await user.click(await screen.findByRole("option", { name: /^Last 7 days/ }));
    await waitFor(() => {
      expect(screen.queryByRole("table", { name: "Models" })).toBeNull();
    });
    expect(screen.getByText("Loading models")).toBeInTheDocument();
  });
});
