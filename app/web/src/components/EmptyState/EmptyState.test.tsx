import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EmptyState, states } from "./EmptyState";

afterEach(cleanup);

describe("EmptyState", () => {
  it("lists every state", () => {
    expect(states).toEqual(["page", "page-neutral", "inline"]);
  });

  it("renders the page variant with a heading, sentence and link action", () => {
    render(
      <EmptyState
        variant="page"
        title="Nothing to fix"
        action={{ label: "Open Your setup", href: "#/setup" }}
      >
        Everything loads.
      </EmptyState>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Nothing to fix" })).toBeInTheDocument();
    expect(screen.getByText("Everything loads.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Your setup" })).toHaveAttribute(
      "href",
      "#/setup",
    );
  });

  it("draws the check by default and the neutral mark when asked", () => {
    const { container, rerender } = render(<EmptyState variant="page">Done.</EmptyState>);
    const mark = container.querySelector(".empty-page-mark");
    expect(mark).toHaveClass("is-done");
    expect(mark).not.toHaveClass("is-neutral");
    rerender(
      <EmptyState variant="page" mark="neutral">
        Later.
      </EmptyState>,
    );
    expect(container.querySelector(".empty-page-mark")).toHaveClass("is-neutral");
    expect(container.querySelector(".empty-page-mark")).toHaveAttribute("aria-hidden", "true");
  });

  it("renders the inline variant with a button action", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(<EmptyState action={{ label: "Add a hook", onPress }}>No hooks yet.</EmptyState>);
    await user.click(screen.getByRole("button", { name: "Add a hook" }));
    expect(onPress).toHaveBeenCalledOnce();
  });

  it("renders a primary action and a second button beside it on the page variant", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    const onOther = vi.fn();
    const { container } = render(
      <EmptyState
        variant="page"
        title="No sessions"
        action={{ label: "Show 7 days", onPress, primary: true }}
        secondary={{ label: "Open Live", onPress: onOther }}
      >
        Nothing here.
      </EmptyState>,
    );
    expect(screen.getByRole("button", { name: "Show 7 days" })).toHaveClass("button-primary");
    expect(screen.getByRole("button", { name: "Open Live" })).not.toHaveClass("button-primary");
    expect(container.querySelector(".empty-page-actions")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Open Live" }));
    expect(onOther).toHaveBeenCalledOnce();
  });
});
