import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NoticeLine, states } from "./NoticeLine";

afterEach(cleanup);

describe("NoticeLine", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "with-link"]);
  });

  it("shows the status word with the sentence", () => {
    render(<NoticeLine statusWord="Unknown">Version gap.</NoticeLine>);
    expect(screen.getByText("Unknown")).toHaveAttribute("data-glyph", "unknown");
    expect(screen.getByText("Version gap.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("renders a link and an optional status role", () => {
    render(
      <NoticeLine
        statusWord="Unknown"
        role="status"
        link={{ label: "How it decides", href: "#/rules" }}
      >
        Version gap.
      </NoticeLine>,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "How it decides" })).toHaveAttribute("href", "#/rules");
  });
});
