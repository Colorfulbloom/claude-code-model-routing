import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Spark } from "../Spark/Spark";
import { Tile, states } from "./Tile";

afterEach(cleanup);

describe("Tile", () => {
  it("lists its states", () => {
    expect(states).toEqual(["default", "proof", "unpriced", "loading", "link"]);
  });

  it("shows label, qualifier, value, delta and note", () => {
    render(
      <Tile
        label="Spent so far"
        qualifier="API-rate estimate"
        value="$7.05"
        delta="$0.44 in the last minute"
        note="12 requests have no price"
      />,
    );
    expect(screen.getByText("Spent so far")).toBeInTheDocument();
    expect(screen.getByText("API-rate estimate")).toBeInTheDocument();
    expect(screen.getByText("$7.05")).toBeInTheDocument();
    expect(screen.getByText(/\$0\.44 in the last minute/)).toBeInTheDocument();
    expect(screen.getByText("12 requests have no price")).toBeInTheDocument();
  });

  it("keeps the proof out of the accessibility tree", () => {
    const { container } = render(
      <Tile label="Tokens" value="5.3M" delta="334K" proof={<Spark values={[1, 2]} />} />,
    );
    expect(container.querySelector('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("swaps the value and delta for bones and the loading line while loading", () => {
    const { container } = render(
      <Tile label="Tokens" value="5.3M" delta="334K" loading={{ label: "Loading sessions" }} />,
    );
    expect(screen.queryByText("5.3M")).toBeNull();
    expect(screen.queryByText("334K")).toBeNull();
    expect(screen.getByText("Loading sessions")).toBeInTheDocument();
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it("is a link when it opens a page", () => {
    render(<Tile label="Tokens" value="5.3M" delta="334K" href="#summary" />);
    expect(screen.getByRole("link")).toHaveAttribute("href", "#summary");
    expect(screen.getByRole("link")).toHaveTextContent("Tokens");
  });

  it("is plain text without an href", () => {
    render(<Tile label="Tokens" value="5.3M" delta="334K" />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
