import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TimelineLane, type LaneFold, type LaneRun, type TimelineLaneProps } from "./TimelineLane";

afterEach(cleanup);

const run = (over: Partial<LaneRun> = {}): LaneRun => ({
  kind: "run",
  id: "r1",
  name: "fast-worker 5",
  depth: 1,
  model: "sonnet",
  modelLabel: "Sonnet 5.5",
  effortLabel: "medium",
  state: "working",
  stateWord: "Working",
  ageLine: "Since 2:23 PM",
  tokens: "35K",
  cost: { kind: "cost", text: "$0.04" },
  segments: [{ start: 0.3, end: 0.6 }],
  rounds: [],
  unlinked: null,
  moved: false,
  reachesNow: false,
  ...over,
});

const later = (over: Partial<LaneFold> = {}): LaneFold => ({
  kind: "fold",
  id: "f-later",
  depth: 1,
  label: "4 start later",
  expanded: false,
  toggleLabel: "Show",
  onToggle: () => undefined,
  controls: "r1 r2",
  later: true,
  segments: [{ start: 0.7, end: 0.8 }],
  tokens: "–",
  cost: { kind: "cost", text: "–" },
  stateWord: "Not started yet",
  ...over,
});

const lane = (items: TimelineLaneProps["items"], over: Partial<TimelineLaneProps> = {}) =>
  render(
    <TimelineLane
      axis={{ ticks: [{ frac: 0.5, label: "2:30" }], nowFrac: null }}
      items={items}
      note="Hollow bars show work that comes after the line."
      label="Who worked when"
      {...over}
    />,
  );

const segs = (container: HTMLElement) =>
  Array.from(container.querySelectorAll<HTMLElement>(".lane-seg"));

describe("TimelineLane with a cut", () => {
  it("draws nothing extra without a cut", () => {
    const { container } = lane([run()]);
    expect(container.querySelector(".lane-cut")).toBeNull();
    expect(container.querySelector(".lane-seg-after")).toBeNull();
    expect(segs(container)).toHaveLength(1);
  });

  it("splits a bar that crosses the cut into a solid part and a hollow part", () => {
    const { container } = lane([run({ segments: [{ start: 0.3, end: 0.6 }] })], { cut: 0.5 });
    const [solid, hollow] = segs(container);
    expect(segs(container)).toHaveLength(2);
    expect(solid).not.toHaveClass("lane-seg-after");
    expect(solid).toHaveClass("lane-seg-cut");
    expect(solid?.style.left).toBe("30%");
    expect(Number.parseFloat(/, ([\d.]+)%/.exec(solid?.style.width ?? "")?.[1] ?? "")).toBeCloseTo(
      20,
    );
    expect(hollow).toHaveClass("lane-seg-after");
    expect(hollow?.style.left).toBe("50%");
    expect(Number.parseFloat(/, ([\d.]+)%/.exec(hollow?.style.width ?? "")?.[1] ?? "")).toBeCloseTo(
      10,
    );
  });

  it("draws a bar before the cut solid and a bar after it hollow", () => {
    const { container } = lane(
      [
        run({
          segments: [
            { start: 0.1, end: 0.2 },
            { start: 0.7, end: 0.9 },
          ],
        }),
      ],
      { cut: 0.5 },
    );
    const [before, after] = segs(container);
    expect(segs(container)).toHaveLength(2);
    expect(before).not.toHaveClass("lane-seg-after");
    expect(before).not.toHaveClass("lane-seg-cut");
    expect(after).toHaveClass("lane-seg-after");
  });

  it("draws a bar that ends on the cut solid, with no hollow part", () => {
    const { container } = lane([run({ segments: [{ start: 0.3, end: 0.5 }] })], { cut: 0.5 });
    expect(segs(container)).toHaveLength(1);
    expect(segs(container)[0]).not.toHaveClass("lane-seg-after");
  });

  it("puts one cut line in every track, at the cut", () => {
    const { container } = lane([run(), run({ id: "r2" })], { cut: 0.25 });
    const lines = container.querySelectorAll<HTMLElement>(".lane-cut");
    expect(lines).toHaveLength(2);
    expect(lines[0]?.style.left).toBe("25%");
    expect(lines[0]?.closest(".lane-track")).toHaveAttribute("aria-hidden", "true");
  });

  it("does not draw a bar open to Now", () => {
    const { container } = lane([run({ reachesNow: true, segments: [{ start: 0.3, end: 0.9 }] })], {
      cut: 0.5,
    });
    expect(container.querySelector(".lane-seg-open")).toBeNull();
  });

  it("leaves out round marks after the cut", () => {
    lane(
      [
        run({
          rounds: [
            { at: 0.4, label: "Round 2" },
            { at: 0.8, label: "Round 3" },
          ],
        }),
      ],
      { cut: 0.5 },
    );
    expect(screen.getByText("Round 2")).toBeInTheDocument();
    expect(screen.queryByText("Round 3")).toBeNull();
  });

  it("mutes a row that has not started and draws its bar hollow", () => {
    const { container } = lane(
      [
        run({
          state: "not_started",
          stateWord: "Not started yet",
          ageLine: "",
          tokens: "–",
          segments: [{ start: 0.7, end: 0.9 }],
        }),
      ],
      { cut: 0.5 },
    );
    expect(screen.getByRole("listitem")).toHaveClass("lane-row-future");
    expect(screen.getByRole("listitem")).toHaveTextContent("Not started yet");
    expect(segs(container)[0]).toHaveClass("lane-seg-after");
  });

  it("keeps rows plain, not links", () => {
    lane([run(), later()], { cut: 0.5 });
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("TimelineLane starts-later fold", () => {
  it("reads as not started, with the label read by the button", () => {
    lane([later()], { cut: 0.5 });
    const row = screen.getByRole("listitem");
    expect(row).toHaveClass("lane-row-future");
    expect(row).toHaveTextContent("Not started yet");
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(button).toHaveAttribute("aria-controls", "r1 r2");
    expect(button).toHaveAccessibleDescription("4 start later");
    expect(button).toHaveTextContent("Show");
  });

  it("takes its accessible name from toggleAria when the page gives one", () => {
    lane([later({ toggleAria: "Show 4 runs that start later under deep-reasoner" })], {
      cut: 0.5,
    });
    const button = screen.getByRole("button", {
      name: "Show 4 runs that start later under deep-reasoner",
    });
    expect(button).toHaveTextContent("Show");
  });

  it("sets aria-expanded true and says Hide when open", () => {
    lane([later({ expanded: true, toggleLabel: "Hide" })], { cut: 0.5 });
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveTextContent("Hide");
  });

  it("calls onToggle", async () => {
    const onToggle = vi.fn();
    lane([later({ onToggle })], { cut: 0.5 });
    await userEvent.click(screen.getByRole("button"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("draws its bars hollow, in the fold size", () => {
    const { container } = lane([later()], { cut: 0.5 });
    const bar = container.querySelector(".lane-seg-fold");
    expect(bar).toHaveClass("lane-seg-after");
  });

  it("lists the revealed rows after it, each with its id", () => {
    const { container } = lane(
      [
        later({ expanded: true, toggleLabel: "Hide", controls: "r1" }),
        run({
          state: "not_started",
          stateWord: "Not started yet",
          segments: [{ start: 0.7, end: 0.9 }],
        }),
      ],
      { cut: 0.5 },
    );
    const list = screen.getByRole("list", { name: "Who worked when" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(container.querySelector("#r1")).not.toBeNull();
  });

  it("reads as finished when it is an earlier fold, without later", () => {
    lane([later({ later: false, label: "5 finished earlier", stateWord: "Finished" })], {
      cut: 0.5,
    });
    expect(screen.getByRole("listitem")).not.toHaveClass("lane-row-future");
  });
});
