import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { helpTitle } from "./help-title";
import { HelpPanel, states } from "./HelpPanel";
import { HELP } from "@/strings/help";

afterEach(cleanup);

describe("HelpPanel", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["popover", "tray"]);
  });

  it("draws the popover in place with an h2 title and no Close button", () => {
    render(<HelpPanel help="live.cache" inline />);
    const dialog = screen.getByRole("dialog", { name: "Read from cache" });
    expect(within(dialog).getByRole("heading", { level: 2 })).toHaveTextContent("Read from cache");
    expect(within(dialog).queryByRole("button")).toBeNull();
  });

  it("draws the tray in place with a grip and a Close button", () => {
    const { container } = render(<HelpPanel help="live.cache" tray inline />);
    const dialog = screen.getByRole("dialog", { name: "Read from cache" });
    expect(within(dialog).getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(container.querySelector(".hp-grip")).not.toBeNull();
    expect(container.querySelector(".hp-grip")).toHaveAttribute("aria-hidden", "true");
  });

  it("passes the values, the line and the word to the entry", () => {
    render(
      <HelpPanel
        help="live.cache"
        values={{ value: "78%" }}
        line={HELP["live.cache"].lines[0].label}
        inline
      />,
    );
    expect(screen.getByText("78%")).toBeInTheDocument();
    expect(screen.getByText(en.hp_this_column)).toBeInTheDocument();
  });
});

describe("helpTitle", () => {
  it("is the entry's own title without a unit", () => {
    expect(helpTitle(HELP["summary.costchart"])).toBe(HELP["summary.costchart"].title);
  });

  it("follows the unit when the entry has per-unit titles", () => {
    expect(helpTitle(HELP["summary.costchart"], "week")).toBe(en.ch_h_week);
  });

  it("ignores a unit the entry has no titles for", () => {
    expect(helpTitle(HELP["live.cache"], "week")).toBe(HELP["live.cache"].title);
  });
});
