import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { HELP } from "@/strings/help";
import { resetViewport, setViewport } from "@/test/media";
import { HelpButton, states } from "./HelpButton";

afterEach(() => {
  cleanup();
  resetViewport();
});

describe("HelpButton", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "closed",
      "open-popover",
      "open-with-values",
      "line-marked",
      "word-marked",
    ]);
  });

  it("is a button named About and the entry title, with a dialog behind it", () => {
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button", { name: "About Read from cache" });
    expect(button).toHaveAttribute("aria-haspopup", "dialog");
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens a dialog named by its h2 title, and marks itself expanded", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button", { name: "About Read from cache" });
    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Read from cache" });
    expect(
      within(dialog).getByRole("heading", { level: 2, name: "Read from cache" }),
    ).toBeVisible();
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(dialog).toHaveFocus();
  });

  it("draws each passed value beside its line, under the numbers heading", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" values={{ value: "78%", delta: "81%" }} />);
    await user.click(screen.getByRole("button"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("78%")).toBeInTheDocument();
    expect(within(dialog).getByText("81%")).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { level: 3, name: en.hp_numbers })).toBeVisible();
  });

  it("marks the line it was given as This column", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" line={HELP["live.cache"].lines[0].label} />);
    await user.click(screen.getByRole("button"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getAllByText(en.hp_this_column)).toHaveLength(1);
  });

  it("marks the status word it was given as Shown here", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="agents.check" word="lowered" />);
    await user.click(screen.getByRole("button"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getAllByText(en.hp_this_setting)).toHaveLength(1);
    expect(within(dialog).getAllByText(en.status_lowered)).toHaveLength(1);
  });

  it("takes its title from the unit, so it matches the card title", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="summary.costchart" unit="day" />);
    await user.click(screen.getByRole("button", { name: "About Cost per day" }));
    expect(screen.getByRole("dialog", { name: "Cost per day" })).toBeVisible();
  });

  it("closes on Escape and gives focus back to the button", async () => {
    const user = userEvent.setup();
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button");
    await user.click(button);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(button).toHaveFocus();
    });
  });

  it("carries its help id on the trigger, so a page can find it again", () => {
    render(<HelpButton help="live.cache" />);
    expect(screen.getByRole("button")).toHaveAttribute("data-help-id", "live.cache");
  });

  it("stays open, keeps focus and shows the new value when the spot re-renders with new values", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <HelpButton help="live.cache" values={{ value: "78%", delta: "81%" }} />,
    );
    const button = screen.getByRole("button", { name: "About Read from cache" });
    await user.click(button);
    const dialog = screen.getByRole("dialog");
    const title = within(dialog).getByRole("heading", { level: 2 });
    expect(dialog).toHaveFocus();
    expect(within(dialog).getByText("78%")).toBeInTheDocument();
    for (const value of ["79%", "80%"]) {
      rerender(<HelpButton help="live.cache" values={{ value, delta: "81%" }} />);
      // The same elements, not new ones: nothing remounted.
      expect(screen.getByRole("dialog")).toBe(dialog);
      expect(within(dialog).getByRole("heading", { level: 2 })).toBe(title);
      // The page behind an open dialog is aria-hidden, so the trigger is found with hidden on.
      expect(screen.getByRole("button", { name: "About Read from cache", hidden: true })).toBe(
        button,
      );
      expect(dialog).toHaveFocus();
      expect(button).toHaveAttribute("aria-expanded", "true");
      expect(within(dialog).getByText(value)).toBeInTheDocument();
      expect(within(dialog).queryByText("78%")).toBeNull();
    }
  });

  it("keeps focus on a line inside the dialog across a re-render", async () => {
    const user = userEvent.setup();
    const { rerender } = render(
      <HelpButton help="live.cache" values={{ value: "78%", delta: "81%" }} />,
    );
    await user.click(screen.getByRole("button"));
    const link = within(screen.getByRole("dialog")).getAllByRole("link")[0];
    expect(link).toBeDefined();
    link?.focus();
    rerender(<HelpButton help="live.cache" values={{ value: "79%", delta: "81%" }} />);
    expect(link).toHaveFocus();
  });

  it("closes on a click outside", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <HelpButton help="live.cache" />
        <p>Elsewhere</p>
      </div>,
    );
    await user.click(screen.getByRole("button"));
    await user.click(document.body);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("is a popover with no Close button above 720 px", async () => {
    const user = userEvent.setup();
    setViewport(1440);
    render(<HelpButton help="live.cache" />);
    await user.click(screen.getByRole("button"));
    expect(within(screen.getByRole("dialog")).queryByRole("button", { name: "Close" })).toBeNull();
  });

  it("is a tray with a Close button at 720 px and under, and Close closes it", async () => {
    const user = userEvent.setup();
    setViewport(375);
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button", { name: "About Read from cache" });
    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Read from cache" });
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(button).toHaveFocus();
    });
  });

  it("closes when the window crosses 720 px while open, and leaves nothing broken", async () => {
    const user = userEvent.setup();
    setViewport(1440);
    render(<HelpButton help="live.cache" />);
    const button = screen.getByRole("button");
    await user.click(button);
    expect(screen.getByRole("dialog")).toBeVisible();
    setViewport(500);
    await Promise.resolve();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Close" }),
    ).toBeInTheDocument();
  });
});
