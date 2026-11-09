import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { StatusChip, states } from "./StatusChip";

afterEach(cleanup);

describe("StatusChip", () => {
  it("lists the seven setting statuses", () => {
    expect(states).toEqual([
      "in_effect",
      "overridden",
      "ignored",
      "lowered",
      "invalid",
      "default",
      "unknown",
    ]);
  });

  it("renders the word and a matching glyph hook for every status", () => {
    for (const status of states) {
      const { unmount } = render(<StatusChip status={status}>Word {status}</StatusChip>);
      const chip = screen.getByText(`Word ${status}`);
      expect(chip).toHaveAttribute("data-glyph", status.replace("_", "-"));
      expect(chip).toHaveClass("status-chip");
      unmount();
    }
  });

  it("has the word as its whole accessible text", () => {
    render(<StatusChip status="lowered">Lowered</StatusChip>);
    expect(screen.getByText("Lowered")).toHaveTextContent(/^Lowered$/);
  });
});
