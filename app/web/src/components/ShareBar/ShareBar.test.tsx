import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ShareBar, states } from "./ShareBar";

afterEach(cleanup);

describe("ShareBar", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["list", "table", "empty", "unpriced", "table-unpriced"]);
  });

  it("shows the name, value and percent as text and hides the bar", () => {
    const { container } = render(
      <ul>
        <ShareBar model="opus" name="Opus 5.5" share={0.64} value="$1.84" percent="64%" />
      </ul>,
    );
    expect(screen.getByRole("listitem")).toHaveTextContent("Opus 5.5");
    expect(screen.getByText("$1.84")).toBeInTheDocument();
    expect(screen.getByText("64%")).toBeInTheDocument();
    expect(container.querySelector(".share-bar-track")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".model-swatch-opus")).not.toBeNull();
  });

  it("sizes the fill to the share and draws it in the model colour class", () => {
    const { container } = render(
      <ul>
        <ShareBar model="sonnet" name="Sonnet 5.5" share={0.32} value="$0.92" percent="32%" />
      </ul>,
    );
    const fill = container.querySelector(".share-bar-fill");
    expect(fill).toHaveClass("share-bar-fill-sonnet");
    expect(fill).toHaveStyle({ width: "32%" });
  });

  it("clamps a share outside 0 to 1", () => {
    const { container } = render(
      <ul>
        <ShareBar model="opus" name="A" share={1.4} value="$1" percent="140%" />
        <ShareBar model="opus" name="B" share={-0.2} value="$0" percent="0%" />
      </ul>,
    );
    const fills = Array.from(container.querySelectorAll(".share-bar-fill"));
    expect(fills[0]).toHaveStyle({ width: "100%" });
    expect(fills[1]).toHaveStyle({ width: "0%" });
  });

  it("keeps a zero share as an empty fill with its edge, not as no bar", () => {
    const { container } = render(
      <ul>
        <ShareBar model="haiku" name="Haiku 5.5" share={0} value="$0.00" percent="0%" />
      </ul>,
    );
    expect(container.querySelector(".share-bar-fill")).toHaveStyle({ width: "0%" });
    expect(screen.getByText("0%")).toBeInTheDocument();
  });

  it("draws no fill and no percent for a null share, and shows the caller's text", () => {
    const { container } = render(
      <ul>
        <ShareBar
          model="fable"
          name="Fable 5.1"
          share={null}
          value="No price for Fable 5.1"
          percent="0%"
        />
      </ul>,
    );
    expect(container.querySelector(".share-bar-fill")).toBeNull();
    expect(screen.getByText("No price for Fable 5.1")).toBeInTheDocument();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("draws the table variant without a name or a list item", () => {
    const { container } = render(
      <ShareBar variant="table" model="opus" share={0.5} value="$1" percent="50%" />,
    );
    expect(screen.queryByRole("listitem")).toBeNull();
    expect(container.querySelector(".share-bar-table")).not.toBeNull();
    expect(container.querySelector(".share-bar-name")).toBeNull();
    expect(container.querySelector(".share-bar-track")).toHaveAttribute("aria-hidden", "true");
  });

  it("uses a neutral fill and no swatch when there is no model", () => {
    const { container } = render(
      <ul>
        <ShareBar model={null} name="tech-writer" share={0.2} value="$0.40" percent="20%" />
      </ul>,
    );
    expect(container.querySelector(".model-swatch")).toBeNull();
    expect(container.querySelector(".share-bar-fill")?.className).toBe("share-bar-fill");
  });
});
