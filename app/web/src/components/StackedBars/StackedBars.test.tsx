import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StackedBars, states, type StackedBarsProps } from "./StackedBars";
import css from "./StackedBars.css?raw";

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
    expect(states).toEqual([
      "normal",
      "open-bucket",
      "averaged",
      "empty",
      "cost-kinds",
      "cost-open",
      "cost-partial",
      "cost-unpriced",
      "cost-no-records",
    ]);
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

const split = { input: 10, output: 20, cache_read: 60, cache_write: 10 };

const cost: StackedBarsProps = {
  ...base,
  bars: [
    { key: "a", byModel: { opus: 2, sonnet: 1 }, kinds: { opus: split } },
    { key: "b", byModel: { opus: 1 } },
  ],
  yTicks: [{ value: 2, label: "$2" }],
  legend: [
    { model: "opus", label: "Opus 5.5", total: "$3.00" },
    { model: "sonnet", label: "Sonnet 5.5", total: "$1.00" },
  ],
  kindsLine: [
    { kind: "input", label: "Input", total: "$0.30" },
    { kind: "output", label: "Output", total: "$0.60" },
    { kind: "cache_read", label: "Cache read", total: "$1.80" },
    { kind: "cache_write", label: "Cache write", total: "$0.30" },
  ],
  kindsLabel: "Cost by kind",
  axisLabel: "Cost per day",
  summary: "Cost per day, mostly Opus 5.5.",
};

describe("StackedBars as a cost chart", () => {
  it("splits a model segment into four kinds drawn with patterns kp1 to kp4", () => {
    const { container } = render(<StackedBars {...cost} />);
    const slices = Array.from(container.querySelectorAll('[data-bar="a"] [data-kind]'));
    expect(slices.map((slice) => slice.getAttribute("data-kind"))).toEqual([
      "input",
      "output",
      "cache_read",
      "cache_write",
    ]);
    const fills = slices.map((slice) => slice.getAttribute("fill") ?? "");
    expect(fills.map((fill) => /-(kp\d)-opus\)$/.exec(fill)?.[1])).toEqual([
      "kp1",
      "kp2",
      "kp3",
      "kp4",
    ]);
    // The slices fill the segment: their heights add up and they stack from the bottom.
    const heights = slices.map((slice) => Number(slice.getAttribute("height")));
    const segment = container.querySelector('[data-bar="b"] .bars-seg-opus');
    expect(segment).not.toBeNull();
    expect(heights[2]).toBeCloseTo(6 * (heights[0] ?? 0), 5);
    const ys = slices.map((slice) => Number(slice.getAttribute("y")));
    expect(ys[0]).toBeGreaterThan(ys[1] ?? 0);
  });

  it("fills the pattern tiles with currentColor and takes the ink from the model", () => {
    const { container } = render(<StackedBars {...cost} />);
    const tiles = Array.from(container.querySelectorAll("svg.bars-svg pattern[data-pattern]"));
    expect(tiles.map((tile) => tile.getAttribute("data-pattern"))).toEqual([
      "kp1",
      "kp2",
      "kp3",
      "kp4",
    ]);
    for (const tile of tiles) {
      expect(tile).toHaveClass("bars-ink-opus");
      expect(tile.innerHTML).toContain('fill="currentColor"');
      expect(tile.innerHTML).not.toMatch(/#[0-9a-f]{3,6}|--rk/i);
    }
  });

  it("leaves a model with no split solid", () => {
    const { container } = render(<StackedBars {...cost} />);
    expect(container.querySelector('[data-bar="a"] .bars-seg-sonnet')).not.toBeNull();
    expect(container.querySelector('[data-bar="b"] [data-kind]')).toBeNull();
  });

  it("keeps the kinds line as a named list with a pattern swatch for each kind", () => {
    const { container } = render(<StackedBars {...cost} />);
    const list = screen.getByRole("list", { name: "Cost by kind" });
    expect(
      within(list)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["Input $0.30", "Output $0.60", "Cache read $1.80", "Cache write $0.30"]);
    expect(list.querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(4);
    expect(container.querySelectorAll("text")).toHaveLength(0);
  });

  it("draws a part with no price as the dashed stub, never as zero", () => {
    const { container } = render(
      <StackedBars
        {...cost}
        models={["opus", "fable"]}
        bars={[{ key: "u", byModel: { opus: 2, fable: null } }]}
      />,
    );
    const stub = container.querySelector('[data-bar="u"] [data-unpriced="fable"]');
    expect(stub).toHaveClass("bars-stub");
    expect(Number(stub?.getAttribute("height"))).toBeGreaterThan(0);
    expect(container.querySelector('[data-bar="u"] .bars-seg-fable')).toBeNull();
  });

  it("draws no bar for a bucket with no records, and shows the caller's label once", () => {
    const { container } = render(
      <StackedBars
        {...cost}
        bars={[
          { key: "n1", byModel: {}, noRecords: "No records before September 3" },
          { key: "n2", byModel: {}, noRecords: "No records before September 3" },
          { key: "c", byModel: { opus: 1 } },
        ]}
      />,
    );
    expect(container.querySelector('[data-bar="n1"]')).toBeNull();
    expect(container.querySelector('[data-bar="n2"]')).toBeNull();
    expect(container.querySelector('[data-bar="c"]')).not.toBeNull();
    expect(screen.getAllByText("No records before September 3")).toHaveLength(1);
  });

  it("marks an open bucket with kinds as outlined and a partial bucket with a dashed outline", () => {
    const { container } = render(
      <StackedBars
        {...cost}
        bars={[
          { key: "p", byModel: { opus: 1 }, partial: true },
          { key: "o", byModel: { opus: 2 }, kinds: { opus: split }, open: true, openFrac: 0.4 },
        ]}
      />,
    );
    expect(container.querySelector('[data-bar="p"]')).toHaveAttribute("data-partial", "true");
    expect(container.querySelector('[data-bar="p"] .bars-partial')).not.toBeNull();
    expect(container.querySelector('[data-bar="o"]')).toHaveAttribute("data-open", "true");
    expect(container.querySelector('[data-bar="o"] .bars-outline')).not.toBeNull();
    expect(container.querySelectorAll('[data-bar="o"] [data-kind]')).toHaveLength(4);
  });

  it("names the image with the caller's summary", () => {
    render(<StackedBars {...cost} />);
    expect(screen.getByRole("img", { name: "Cost per day, mostly Opus 5.5." })).toBeInTheDocument();
  });

  it("never reads an --rk token, in its styles or in what it draws", () => {
    expect(css).not.toContain("--rk");
    const { container } = render(
      <StackedBars
        {...cost}
        bars={[
          ...cost.bars,
          { key: "o", byModel: { opus: 2 }, kinds: { opus: split }, open: true },
        ]}
      />,
    );
    expect(container.innerHTML).not.toContain("--rk");
  });
});

const cents: StackedBarsProps = {
  ...cost,
  bars: [{ key: "a", byModel: { sonnet: 0.17, opus: null } }],
  models: ["opus", "sonnet"],
  yTicks: [0, 0.05, 0.1, 0.15, 0.2].map((value) => ({ value, label: `$${value.toFixed(2)}` })),
  kindsLine: [],
};

const bottomOf = (label: string): number =>
  Number.parseFloat(/([\d.]+)%/.exec(screen.getByText(label).style.bottom)?.[1] ?? "NaN");

describe("StackedBars scale for a chart of cents", () => {
  it("spreads the ticks over the plot, not into its bottom sixth, with an unpriced stub in it", () => {
    // The scale once had a floor of 1, so $0.20 sat at 18 percent and the labels piled up.
    render(<StackedBars {...cents} />);
    const [low, high] = [bottomOf("$0.05"), bottomOf("$0.20")];
    expect(high).toBeGreaterThan(70);
    expect(low).toBeGreaterThan(15);
    expect(high - low).toBeGreaterThan(50);
  });

  it("keeps a scale of 1 for a chart with nothing to show", () => {
    const { container } = render(<StackedBars {...cents} bars={[]} yTicks={[]} />);
    expect(container.querySelectorAll("rect")).toHaveLength(0);
  });
});

describe("StackedBars slots, marker and gutter", () => {
  const day: StackedBarsProps = {
    ...cost,
    bars: [
      { key: "h0", byModel: { opus: 1 } },
      { key: "h1", byModel: { opus: 1 }, open: true, openFrac: 0.5 },
      { key: "h2", byModel: {}, future: true },
      { key: "h3", byModel: {}, future: true },
    ],
    kindsLine: [],
  };

  it("keeps an empty slot for a future bucket and draws nothing in it", () => {
    const { container } = render(<StackedBars {...day} />);
    expect(container.querySelector('[data-bar="h2"]')).toBeNull();
    expect(container.querySelector('[data-bar="h3"]')).toBeNull();
    // Four equal slots of (600 - 3 gaps of 2) / 4 = 148.5 px, so the first bar is that wide.
    const first = container.querySelector('[data-bar="h0"] rect');
    expect(Number(first?.getAttribute("width"))).toBeCloseTo(148.5, 5);
    const open = container.querySelector('[data-bar="h1"] rect');
    expect(Number(open?.getAttribute("width"))).toBeGreaterThan(100);
  });

  it("puts the Now marker where the open bucket has got to", () => {
    const { container } = render(<StackedBars {...day} nowLabel="Now" />);
    const marker = container.querySelector<HTMLElement>(".bars-now");
    expect(marker).not.toBeNull();
    expect(marker).toHaveAttribute("aria-hidden", "true");
    // The open slot starts at 150.5 and is 148.5 wide, so half of it is 74.25 px in.
    expect(Number.parseFloat(marker?.style.left ?? "")).toBeCloseTo(150.5 + 74.25, 5);
    expect(marker).toHaveTextContent("Now");
  });

  it("draws no marker without a label", () => {
    const { container } = render(<StackedBars {...day} />);
    expect(container.querySelector(".bars-now")).toBeNull();
  });

  it("lets an open bar that nothing follows weigh its fraction", () => {
    const { container } = render(<StackedBars {...base} />);
    const widths = Array.from(container.querySelectorAll("[data-bar] rect")).map((rect) =>
      Number(rect.getAttribute("width")),
    );
    expect(widths.at(-1)).toBeLessThan((widths[0] ?? 0) / 2);
  });

  it("gives the y labels a gutter only when asked", () => {
    const { container, rerender } = render(<StackedBars {...day} />);
    expect(container.firstElementChild).not.toHaveClass("bars-guttered");
    rerender(<StackedBars {...day} guttered />);
    expect(container.firstElementChild).toHaveClass("bars-guttered");
  });

  it("draws the records start as a dashed vertical divider and wraps a wide run's label", () => {
    const { container } = render(
      <StackedBars
        {...day}
        bars={[
          { key: "n1", byModel: {}, noRecords: "No records before August 31" },
          { key: "n2", byModel: {}, noRecords: "No records before August 31" },
          { key: "c", byModel: { opus: 1 } },
        ]}
      />,
    );
    const line = container.querySelector(".bars-none-line");
    expect(line?.getAttribute("x1")).toBe(line?.getAttribute("x2"));
    expect(Number(line?.getAttribute("y2"))).toBeGreaterThan(Number(line?.getAttribute("y1")));
    expect(screen.getByText("No records before August 31").parentElement).toHaveClass(
      "bars-none-wide",
    );
  });

  it("hangs the label of a run too narrow for its words past the divider", () => {
    const bars: StackedBarsProps["bars"] = [
      { key: "n1", byModel: {}, noRecords: "No records before September 3" },
      ...Array.from({ length: 29 }, (_, i) => ({ key: `c${String(i)}`, byModel: { opus: 1 } })),
    ];
    render(<StackedBars {...day} bars={bars} />);
    expect(screen.getByText("No records before September 3").parentElement).toHaveClass(
      "bars-none-edge",
    );
  });
});
