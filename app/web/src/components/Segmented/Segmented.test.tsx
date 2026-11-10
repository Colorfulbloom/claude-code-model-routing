import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { Segmented, states, type SegmentedItem } from "./Segmented";

afterEach(cleanup);

const items: SegmentedItem[] = [
  { id: "summary", href: "#summary", label: "Summary", current: true },
  { id: "sessions", href: "#sessions", label: "Sessions" },
  { id: "agents", href: "#agents", label: "Agents" },
];

describe("Segmented", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "hover", "focus", "selected", "overflow"]);
  });

  it("is a nav of links, and marks only the current page", () => {
    render(<Segmented label="Review pages" items={items} />);
    expect(screen.getByRole("navigation", { name: "Review pages" })).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Summary", "Sessions", "Agents"]);
    expect(screen.getByRole("link", { name: "Summary" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Sessions" })).not.toHaveAttribute("aria-current");
  });

  it("marks nothing current when no item is", () => {
    render(
      <Segmented
        label="Review pages"
        items={items.map((item) => ({ id: item.id, href: item.href, label: item.label }))}
      />,
    );
    expect(document.querySelector("[aria-current]")).toBeNull();
  });

  it("moves through the links with Tab", async () => {
    const user = userEvent.setup();
    render(<Segmented label="Review pages" items={items} />);
    await user.tab();
    expect(screen.getByRole("link", { name: "Summary" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Sessions" })).toHaveFocus();
  });

  it("carries the forced-state class the sheet passes", () => {
    render(
      <Segmented
        label="Review pages"
        items={[{ id: "a", href: "#a", label: "A", className: "is-hover" }]}
      />,
    );
    expect(screen.getByRole("link", { name: "A" })).toHaveClass("segmented-link", "is-hover");
  });
});
