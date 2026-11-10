import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ScopeChip, states } from "./ScopeChip";

afterEach(cleanup);

describe("ScopeChip", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "wrap", "truncated"]);
  });

  it("shows the scope in medium weight, then the value", () => {
    const { container } = render(<ScopeChip scope="Project local" value="high" />);
    const parts = container.querySelectorAll(".scope-chip > span");
    expect(parts[0]).toHaveClass("scope-chip-scope");
    expect(parts[0]).toHaveTextContent("Project local");
    expect(parts[1]).toHaveClass("scope-chip-value");
    expect(parts[1]).toHaveTextContent("high");
  });

  it("keeps scope and value together in its text, with a space between", () => {
    const { container } = render(
      <ScopeChip scope="Project local" value="Opus 5.5 and Sonnet 5.5" />,
    );
    expect(container.firstChild).toHaveTextContent("Project local Opus 5.5 and Sonnet 5.5");
  });

  it("does not cut a long value unless asked", () => {
    const { container } = render(<ScopeChip scope="User" value="a-very-long-value-that-wraps" />);
    expect(container.firstChild).not.toHaveClass("scope-chip-truncate");
    expect(container.firstChild).not.toHaveAttribute("title");
  });

  it("truncates visually and keeps the full plugin name in the text and the title", () => {
    const name = "tidewater-reporting-helpers-with-a-very-long-name";
    const { container } = render(<ScopeChip scope="Plugin" value={name} truncate />);
    expect(container.firstChild).toHaveClass("scope-chip-truncate");
    expect(screen.getByText(name)).toBeInTheDocument();
    expect(container.firstChild).toHaveTextContent(`Plugin ${name}`);
    expect(container.firstChild).toHaveAttribute("title", `Plugin ${name}`);
  });
});
