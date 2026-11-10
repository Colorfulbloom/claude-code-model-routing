import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ScopeLabel, states } from "./ScopeLabel";

afterEach(cleanup);

describe("ScopeLabel", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "long"]);
  });

  it("puts the scope over its meaning, in that order", () => {
    const { container } = render(
      <ScopeLabel name="Project local" meaning="Just you, this project" />,
    );
    const lines = container.querySelectorAll(".scope-label > span");
    expect(lines).toHaveLength(2);
    expect(lines[0]).toHaveTextContent("Project local");
    expect(lines[1]).toHaveTextContent("Just you, this project");
  });

  it("keeps both lines in the text a screen reader gets", () => {
    render(<ScopeLabel name="Managed" meaning="Your organization" />);
    expect(screen.getByText("Managed")).toBeInTheDocument();
    expect(screen.getByText("Your organization")).toBeInTheDocument();
  });

  it("carries an extra class", () => {
    const { container } = render(
      <ScopeLabel name="User" meaning="You, every project" className="x" />,
    );
    expect(container.firstChild).toHaveClass("scope-label", "x");
  });
});
