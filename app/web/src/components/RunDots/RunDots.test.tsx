import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RunDots, states } from "./RunDots";

afterEach(cleanup);

function dots(working: number, finished: number) {
  const { container } = render(<RunDots working={working} finished={finished} />);
  return {
    root: container.firstElementChild,
    on: container.querySelectorAll(".run-dot-working").length,
    ok: container.querySelectorAll(".run-dot-finished").length,
  };
}

describe("RunDots", () => {
  it("lists its states", () => {
    expect(states).toEqual(["mixed", "working", "capped"]);
  });

  it("is hidden from assistive tech", () => {
    expect(dots(1, 1).root).toHaveAttribute("aria-hidden", "true");
  });

  it("draws one dot per run, working first", () => {
    expect(dots(4, 4)).toMatchObject({ on: 4, ok: 4 });
    expect(screen.queryByText(/^\+/)).toBeNull();
  });

  it("caps at eight and counts the rest", () => {
    expect(dots(3, 9)).toMatchObject({ on: 3, ok: 5 });
    expect(screen.getByText("+4")).toBeInTheDocument();
  });

  it("caps the working dots too", () => {
    expect(dots(10, 0)).toMatchObject({ on: 8, ok: 0 });
    expect(screen.getByText("+2")).toBeInTheDocument();
  });
});
