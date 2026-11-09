import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StackedBars, states, type StackedBarsProps } from "./StackedBars";

afterEach(cleanup);

const base: StackedBarsProps = {
  bars: [
    { key: "a", byModel: { opus: 40000, sonnet: 10000 } },
    { key: "b", byModel: { opus: 20000 } },
    { key: "c", byModel: { haiku: 5000 }, open: true, openFrac: 0.4 },
  ],
  models: ["opus", "sonnet", "haiku"],
  yTicks: [{ value: 50000, label: "50K" }],
  xLabels: [
    { frac: 0, label: "6:10" },
    { frac: 1, label: "Now" },
  ],
  legend: [
    { model: "opus", label: "Opus 5.5", total: "1.0M" },
    { model: "haiku", label: "Haiku 5.5", total: "29K" },
  ],
  axisLabel: "New tokens per minute",
  summary: "New tokens per minute, mostly Opus 5.5.",
};

describe("StackedBars", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["normal", "open-bucket", "averaged", "empty"]);
  });

  it("draws an image named by the summary, with the labels in HTML", () => {
    render(<StackedBars {...base} />);
    const image = screen.getByRole("img", { name: base.summary });
    expect(image.tagName.toLowerCase()).toBe("svg");
    expect(image.querySelector("text")).toBeNull();
    expect(screen.getByText("New tokens per minute")).toBeInTheDocument();
    expect(screen.getByText("50K")).toBeInTheDocument();
    expect(screen.getByText("6:10")).toBeInTheDocument();
  });

  it("keeps the legend with totals as the text alternative", () => {
    render(<StackedBars {...base} />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual(["Opus 5.5 1.0M", "Haiku 5.5 29K"]);
    // The tick and x labels repeat the picture, so assistive tech skips them.
    expect(screen.getByText("50K")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("6:10").parentElement).toHaveAttribute("aria-hidden", "true");
  });

  it("stacks segments from the first model up and skips models with no value", () => {
    const { container } = render(<StackedBars {...base} />);
    const first = container.querySelector('[data-bar="a"]');
    const rects = Array.from(first?.querySelectorAll("rect") ?? []);
    expect(rects.map((rect) => rect.getAttribute("class"))).toEqual([
      "bars-seg bars-seg-opus",
      "bars-seg bars-seg-sonnet",
    ]);
    const opusY = Number(rects[0]?.getAttribute("y"));
    const sonnetY = Number(rects[1]?.getAttribute("y"));
    expect(sonnetY).toBeLessThan(opusY);
  });

  it("draws the open bucket hatched and outlined, at least 5 px wide", () => {
    const { container } = render(
      <StackedBars
        {...base}
        bars={[
          ...Array.from({ length: 59 }, (_, i) => ({ key: `n${String(i)}`, byModel: { opus: 1 } })),
          { key: "open", byModel: { opus: 30000 }, open: true, openFrac: 0.05 },
        ]}
      />,
    );
    const open = container.querySelector('[data-bar="open"] rect');
    expect(open).toHaveClass("bars-seg-open");
    expect(open?.getAttribute("fill")).toMatch(/^url\(#.+-opus\)$/);
    // The outline is inset by half its width, so the drawn box is 1.5 px narrower than the slot.
    expect(Number(open?.getAttribute("width")) + 1.5).toBeGreaterThanOrEqual(5);
    expect(container.querySelector("pattern")).not.toBeNull();
  });

  it("gives a full-width open bucket the weight of a whole bucket when openFrac is missing", () => {
    const { container } = render(
      <StackedBars
        {...base}
        bars={[
          { key: "x", byModel: { opus: 40000 } },
          { key: "y", byModel: { opus: 40000 }, open: true },
        ]}
      />,
    );
    const widths = Array.from(container.querySelectorAll("[data-bar] rect")).map((rect) =>
      Number(rect.getAttribute("width")),
    );
    expect(widths[0]).toBeCloseTo(widths[1] === undefined ? 0 : widths[1] + 1.5, 1);
  });

  it("drops a clock label that sits too close to Now, and marks every other label minor", () => {
    const { container } = render(
      <StackedBars
        {...base}
        xLabels={[
          { frac: 0, label: "6:10" },
          { frac: 0.5, label: "6:25" },
          { frac: 0.97, label: "6:39" },
          { frac: 1, label: "Now" },
        ]}
      />,
    );
    const labels = Array.from(container.querySelectorAll(".bars-x span"));
    expect(labels.map((label) => label.textContent)).toEqual(["6:10", "6:25", "Now"]);
    expect(labels.map((label) => label.classList.contains("bars-x-minor"))).toEqual([
      false,
      true,
      false,
    ]);
  });

  it("draws no bars when there are none, and still names the image", () => {
    const { container } = render(
      <StackedBars
        {...base}
        bars={[]}
        legend={[]}
        yTicks={[]}
        xLabels={[]}
        summary="No tokens yet."
      />,
    );
    expect(screen.getByRole("img", { name: "No tokens yet." })).toBeInTheDocument();
    expect(container.querySelectorAll("rect")).toHaveLength(0);
    expect(screen.queryByRole("list")).toBeNull();
  });
});
