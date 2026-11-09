import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Spark, states } from "./Spark";

afterEach(cleanup);

function draw(values: (number | null)[]): SVGElement {
  const { container } = render(<Spark values={values} />);
  const svg = container.querySelector("svg");
  if (svg === null) throw new Error("no svg");
  return svg;
}

describe("Spark", () => {
  it("lists its states", () => {
    expect(states).toEqual(["bars", "unpriced", "dense"]);
  });

  it("is hidden from assistive tech", () => {
    expect(draw([1, 2, 3])).toHaveAttribute("aria-hidden", "true");
  });

  it("draws one bar per value and marks the last", () => {
    const svg = draw([1, 2, 4]);
    expect(svg.querySelectorAll("rect")).toHaveLength(3);
    expect(svg.querySelectorAll(".spark-last")).toHaveLength(1);
    expect(svg.querySelector("rect:last-child")).toHaveClass("spark-last");
  });

  it("scales bars to the largest value with a floor", () => {
    const rects = draw([0, 50, 100]).querySelectorAll("rect");
    expect(rects[2]?.getAttribute("height")).toBe("100");
    expect(rects[1]?.getAttribute("height")).toBe("50");
    expect(rects[0]?.getAttribute("height")).toBe("4");
  });

  it("draws a dashed stub for an unpriced bucket", () => {
    const svg = draw([2, null, 4]);
    expect(svg.querySelectorAll(".spark-stub")).toHaveLength(1);
    expect(svg.querySelectorAll(".spark-bar")).toHaveLength(2);
  });

  it("keeps a 2 px gap up to 32 bars and none above", () => {
    const few = draw(Array.from({ length: 32 }, () => 1)).querySelectorAll("rect");
    const many = draw(Array.from({ length: 33 }, () => 1)).querySelectorAll("rect");
    const width = few[0]?.getAttribute("width") ?? "0";
    expect(Number(width)).toBeCloseTo((96 - 2 * 31) / 32);
    expect(Number(few[1]?.getAttribute("x"))).toBeCloseTo(Number(width) + 2);
    expect(Number(many[0]?.getAttribute("width"))).toBeCloseTo(96 / 33);
    expect(Number(many[1]?.getAttribute("x"))).toBeCloseTo(96 / 33);
  });

  it("survives only unpriced values", () => {
    expect(draw([null, null]).querySelectorAll(".spark-stub")).toHaveLength(2);
  });
});
