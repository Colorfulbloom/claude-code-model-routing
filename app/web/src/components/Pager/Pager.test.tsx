import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Pager, states, type PagerProps } from "./Pager";

afterEach(cleanup);

const base: PagerProps = {
  label: "Cost chart window",
  earlierLabel: "Earlier",
  laterLabel: "Later",
  windowLabel: "October 10 to November 8",
  scopeNote: "Moves this chart only.",
};

describe("Pager", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "default",
      "hover",
      "focus",
      "earlier-disabled",
      "later-disabled",
      "both-disabled",
    ]);
  });

  it("is a named group with two buttons and a polite window label", () => {
    render(<Pager {...base} />);
    const group = screen.getByRole("group", { name: "Cost chart window" });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Earlier" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Later" })).toBeInTheDocument();
    const label = screen.getByRole("status");
    expect(label).toHaveTextContent("October 10 to November 8");
    expect(label).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText("Moves this chart only.")).toBeInTheDocument();
  });

  it("draws the arrows hidden from assistive tech, so the names stay Earlier and Later", () => {
    render(<Pager {...base} />);
    const earlier = screen.getByRole("button", { name: "Earlier" });
    const later = screen.getByRole("button", { name: "Later" });
    expect(earlier.querySelector('span[aria-hidden="true"]')).toHaveTextContent("←");
    expect(later.querySelector('span[aria-hidden="true"]')).toHaveTextContent("→");
    expect(earlier.textContent?.startsWith("←")).toBe(true);
    expect(later.textContent?.endsWith("→")).toBe(true);
  });

  it("calls the handlers from the keyboard", async () => {
    const user = userEvent.setup();
    const onEarlier = vi.fn();
    const onLater = vi.fn();
    render(<Pager {...base} onEarlier={onEarlier} onLater={onLater} />);
    await user.tab();
    expect(screen.getByRole("button", { name: "Earlier" })).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.tab();
    await user.keyboard(" ");
    expect(onEarlier).toHaveBeenCalledTimes(1);
    expect(onLater).toHaveBeenCalledTimes(1);
  });

  it("keeps a disabled end focusable, aria-disabled, and tied to its why-line", async () => {
    const user = userEvent.setup();
    const onEarlier = vi.fn();
    render(
      <Pager
        {...base}
        onEarlier={onEarlier}
        earlierDisabled
        earlierReason="No earlier data. Records start on September 3."
      />,
    );
    const button = screen.getByRole("button", { name: "Earlier" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled();
    const why = screen.getByText("No earlier data. Records start on September 3.");
    expect(button).toHaveAttribute("aria-describedby", why.id);
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onEarlier).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Later" })).not.toHaveAttribute("aria-disabled");
  });

  it("shows one why-line per disabled end and none for enabled ends", () => {
    const { rerender } = render(
      <Pager {...base} earlierReason="Hidden" laterReason="Also hidden" />,
    );
    expect(screen.queryByText("Hidden")).toBeNull();
    expect(screen.queryByText("Also hidden")).toBeNull();
    rerender(
      <Pager
        {...base}
        earlierDisabled
        earlierReason="No earlier"
        laterDisabled
        laterReason="Newest"
      />,
    );
    const earlier = screen.getByRole("button", { name: "Earlier" });
    const later = screen.getByRole("button", { name: "Later" });
    expect(earlier).toHaveAccessibleDescription("No earlier");
    expect(later).toHaveAccessibleDescription("Newest");
  });

  it("names a button that can move, and drops that name at an end so the visible word and reason read", () => {
    const { rerender } = render(
      <Pager
        {...base}
        earlierAria="Show earlier costs, September 11 to October 10"
        laterAria="Show later"
      />,
    );
    expect(
      screen.getByRole("button", { name: "Show earlier costs, September 11 to October 10" }),
    ).toBeInTheDocument();
    rerender(
      <Pager
        {...base}
        earlierAria="Show earlier costs, September 11 to October 10"
        earlierDisabled
        earlierReason="No earlier"
      />,
    );
    expect(screen.getByRole("button", { name: "Earlier" })).toHaveAccessibleDescription(
      "No earlier",
    );
  });
});
