import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  TimelineLane,
  states,
  type LaneFold,
  type LaneRun,
  type TimelineLaneProps,
} from "./TimelineLane";

afterEach(() => {
  cleanup();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: undefined,
  });
});

const run = (over: Partial<LaneRun> = {}): LaneRun => ({
  kind: "run",
  id: "r1",
  name: "scout",
  depth: 1,
  model: "haiku",
  modelLabel: "Haiku 5.5",
  effortLabel: "medium",
  state: "finished",
  stateWord: "Finished",
  ageLine: "Ran 3 min",
  tokens: "42K",
  cost: { kind: "cost", text: "$0.25" },
  segments: [{ start: 0.1, end: 0.2 }],
  rounds: [],
  unlinked: null,
  moved: false,
  reachesNow: false,
  ...over,
});

const fold = (over: Partial<LaneFold> = {}): LaneFold => ({
  kind: "fold",
  id: "f1",
  depth: 1,
  label: "10 finished earlier",
  expanded: false,
  toggleLabel: "Show",
  onToggle: () => undefined,
  controls: "r1 r2",
  ...over,
});

const lane = (items: TimelineLaneProps["items"], over: Partial<TimelineLaneProps> = {}) =>
  render(
    <TimelineLane
      axis={{ ticks: [{ frac: 0.5, label: "6:25" }], nowFrac: 1 }}
      items={items}
      note="Indented rows were started by the row above them."
      label="Who is working"
      {...over}
    />,
  );

function reduceMotion(reduce: boolean) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
    }),
  });
}

describe("TimelineLane", () => {
  it("lists its sheet states", () => {
    expect(states).toContain("depth-cap");
    expect(states).toContain("moved");
  });

  it("is a named list with one item per row, and the rows are not links", () => {
    lane([run(), run({ id: "r2", name: "judge" })]);
    const list = screen.getByRole("list", { name: "Who is working" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(/Indented rows/)).toBeInTheDocument();
  });

  it("says the row's words, with the model, state, age, tokens and cost", () => {
    lane([run()], { tokensWord: "tokens" });
    const row = screen.getByRole("listitem");
    expect(row).toHaveTextContent("scout");
    expect(row).toHaveTextContent("Haiku 5.5 · medium");
    expect(row).toHaveTextContent("Finished");
    expect(row).toHaveTextContent("Ran 3 min");
    expect(row).toHaveTextContent("42K tokens");
    expect(row).toHaveTextContent("$0.25");
  });

  it("hides the segments and round labels from assistive tech", () => {
    const { container } = lane([
      run({
        segments: [
          { start: 0.1, end: 0.2 },
          { start: 0.9, end: 1 },
        ],
        rounds: [{ at: 0.9, label: "Round 2" }],
      }),
    ]);
    const segments = container.querySelectorAll(".lane-seg");
    expect(segments).toHaveLength(2);
    for (const segment of segments) {
      expect(segment.closest('[aria-hidden="true"]')).not.toBeNull();
    }
    expect(screen.getByText("Round 2").closest('[aria-hidden="true"]')).not.toBeNull();
    // The row text stays readable.
    expect(screen.getByText("Ran 3 min").closest('[aria-hidden="true"]')).toBeNull();
  });

  it("draws the Now edge only on a segment that reaches Now", () => {
    const { container } = lane([
      run({ id: "a", state: "working", reachesNow: true, segments: [{ start: 0.5, end: 1 }] }),
      run({ id: "b", segments: [{ start: 0.5, end: 0.7 }] }),
    ]);
    expect(container.querySelectorAll(".lane-seg-open")).toHaveLength(1);
  });

  it("draws grid lines only at ticks inside the axis", () => {
    const { container } = lane([run()], {
      axis: {
        ticks: [
          { frac: 0, label: "6:10" },
          { frac: 0.5, label: "6:25" },
          { frac: 1, label: "Now" },
        ],
        nowFrac: null,
      },
    });
    expect(container.querySelectorAll(".lane-gridline")).toHaveLength(1);
  });

  it("shows the Started by text the page sets when it caps the indent", () => {
    const { container } = lane([run({ depth: 3, startedBy: "Started by judge" })]);
    expect(screen.getByText("Started by judge")).toBeInTheDocument();
    const row = container.querySelector("li");
    expect(row?.style.getPropertyValue("--lane-ind")).toBe("48px");
    expect(row).toHaveAttribute("aria-level", "4");
  });

  it("shows no Started by text on a row that did not set one", () => {
    lane([run({ depth: 1 })]);
    expect(screen.queryByText(/Started by/)).toBeNull();
  });

  it("marks an unlinked run with its badge and a dashed tree line", () => {
    const { container } = lane([run({ unlinked: { kind: "may", label: "Finding starter" } })]);
    expect(screen.getByText("Finding starter")).toBeInTheDocument();
    expect(container.querySelector(".lane-guide-dashed")).not.toBeNull();
  });

  it("keeps the tree line solid for a linked run", () => {
    const { container } = lane([run()]);
    expect(container.querySelector(".lane-guide")).not.toBeNull();
    expect(container.querySelector(".lane-guide-dashed")).toBeNull();
  });

  it("shows an unpriced cost as its phrase", () => {
    lane([
      run({ id: "a", cost: { kind: "least", text: "at least $0.97" } }),
      run({ id: "b", cost: { kind: "none", text: "No price for Fable 5.1" } }),
    ]);
    expect(screen.getByText("$0.97").tagName).toBe("B");
    expect(screen.getByText("No price for Fable 5.1")).toBeInTheDocument();
  });

  it("shows No price in the cell and keeps the model in the full text for readers", () => {
    lane([
      run({
        id: "b",
        cost: { kind: "none", text: "No price", full: "No price for Fable 5.1" },
      }),
    ]);
    const full = screen.getByText("No price for Fable 5.1");
    expect(full).toHaveClass("sr-only");
    expect(full.parentElement).toHaveAttribute("title", "No price for Fable 5.1");
    expect(screen.getByText("No price")).toHaveAttribute("aria-hidden", "true");
  });

  it("gives a moved row the ring class, and none under reduced motion", () => {
    reduceMotion(false);
    const { container, unmount } = lane([run({ moved: true })]);
    expect(container.querySelector("li")).toHaveClass("lane-row-moved");
    unmount();
    reduceMotion(true);
    const reduced = lane([run({ moved: true })]);
    const row = reduced.container.querySelector("li");
    expect(row).not.toHaveClass("lane-row-moved");
    // The row still says it moved, for the page and the tests.
    expect(row).toHaveAttribute("data-moved", "true");
  });

  it("gives an unmoved row no ring", () => {
    reduceMotion(false);
    const { container } = lane([run()]);
    expect(container.querySelector("li")).not.toHaveClass("lane-row-moved");
  });

  describe("fold row", () => {
    it("has a button with aria-expanded and aria-controls that calls onToggle", async () => {
      const user = userEvent.setup();
      const onToggle = vi.fn();
      lane([fold({ onToggle })]);
      const button = screen.getByRole("button", { name: /Show/ });
      expect(button).toHaveAttribute("aria-expanded", "false");
      expect(button).toHaveAttribute("aria-controls", "r1 r2");
      await user.click(button);
      expect(onToggle).toHaveBeenCalledTimes(1);
    });

    it("reads the fold label with the button, and sets aria-expanded true when open", () => {
      lane([fold({ expanded: true, toggleLabel: "Hide" })]);
      const button = screen.getByRole("button");
      expect(button).toHaveAttribute("aria-expanded", "true");
      expect(button).toHaveAccessibleDescription("10 finished earlier");
      expect(button).toHaveTextContent("Hide");
    });

    it("draws its bars muted and shows its totals", () => {
      const { container } = lane([
        fold({
          segments: [{ start: 0.1, end: 0.2 }],
          tokens: "685K",
          cost: { kind: "cost", text: "$0.67" },
          stateWord: "Finished",
        }),
      ]);
      expect(container.querySelector(".lane-seg-fold")).not.toBeNull();
      expect(screen.getByText("685K")).toBeInTheDocument();
      expect(screen.getByText("$0.67")).toBeInTheDocument();
    });

    it("gives each row its id, so aria-controls has targets", () => {
      const { container } = lane([fold({ expanded: true, controls: "r1" }), run()]);
      expect(container.querySelector("#r1")).not.toBeNull();
    });
  });
});
