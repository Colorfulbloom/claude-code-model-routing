import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { OrderLadder, states } from "./OrderLadder";

afterEach(cleanup);

const LAYERS = [
  { id: "managed", label: "Managed" },
  { id: "local", label: "Project local" },
  { id: "default", label: "Claude Code's default" },
] as const;

describe("OrderLadder", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["row", "wrapped", "vertical", "single"]);
  });

  it("is an ordered list with one item per layer, highest first", () => {
    render(<OrderLadder layers={LAYERS} />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "1Managed",
      "2Project local",
      "3Claude Code's default",
    ]);
    expect(screen.getByRole("list").tagName).toBe("OL");
  });

  it("hides the place numbers from a screen reader, because the list already counts", () => {
    const { container } = render(<OrderLadder layers={LAYERS} />);
    const numbers = container.querySelectorAll(".order-ladder-n");
    expect(numbers).toHaveLength(3);
    for (const number of numbers) expect(number).toHaveAttribute("aria-hidden", "true");
  });

  it("is named by the heading it points at", () => {
    render(
      <>
        <h3 id="order-h">Where Claude Code looks, top wins</h3>
        <OrderLadder layers={LAYERS} labelledBy="order-h" />
      </>,
    );
    expect(screen.getByRole("list", { name: "Where Claude Code looks, top wins" })).toBeVisible();
  });

  it("draws one layer without a joiner, and the vertical layout on request", () => {
    const { container, rerender } = render(<OrderLadder layers={LAYERS.slice(0, 1)} />);
    expect(container.querySelectorAll("li")).toHaveLength(1);
    expect(container.querySelector(".order-ladder")).not.toHaveClass("is-vertical");
    rerender(<OrderLadder layers={LAYERS} vertical />);
    expect(container.querySelector(".order-ladder")).toHaveClass("is-vertical");
  });

  it("keeps a layer's key stable, so a rerender keeps its element", () => {
    const { container, rerender } = render(<OrderLadder layers={LAYERS} />);
    const first = container.querySelector("li");
    rerender(<OrderLadder layers={[...LAYERS]} />);
    expect(container.querySelector("li")).toBe(first);
  });
});
