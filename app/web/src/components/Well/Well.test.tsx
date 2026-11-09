import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Well, states } from "./Well";

afterEach(cleanup);

describe("Well", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "list", "flush"]);
  });

  it("renders children and passes through attributes", () => {
    render(
      <Well variant="list" aria-busy="true" data-testid="well">
        Rows
      </Well>,
    );
    const well = screen.getByTestId("well");
    expect(well).toHaveTextContent("Rows");
    expect(well).toHaveClass("well", "well-list");
    expect(well).toHaveAttribute("aria-busy", "true");
  });
});
