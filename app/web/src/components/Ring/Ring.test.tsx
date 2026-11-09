import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Ring, states } from "./Ring";

afterEach(cleanup);

function arc(percent: number): Element | null {
  const { container } = render(<Ring percent={percent} />);
  return container.querySelector(".ring-fill");
}

describe("Ring", () => {
  it("lists its states", () => {
    expect(states).toEqual(["partial", "empty", "full"]);
  });

  it("is hidden from assistive tech", () => {
    const { container } = render(<Ring percent={78} />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("draws the share as the arc length", () => {
    expect(arc(78)?.getAttribute("stroke-dasharray")).toBe("78 100");
  });

  it("draws no arc at zero and clamps above 100", () => {
    expect(arc(0)).toBeNull();
    cleanup();
    expect(arc(140)?.getAttribute("stroke-dasharray")).toBe("100 100");
  });
});
