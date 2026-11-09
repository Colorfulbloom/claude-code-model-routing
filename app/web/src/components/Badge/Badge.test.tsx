import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Badge, states } from "./Badge";

afterEach(cleanup);

describe("Badge", () => {
  it("lists its states", () => {
    expect(states).toEqual(["default"]);
  });

  it("renders the text and merges a class", () => {
    render(<Badge className="extra">Finding starter</Badge>);
    expect(screen.getByText("Finding starter")).toHaveClass("badge", "extra");
  });
});
