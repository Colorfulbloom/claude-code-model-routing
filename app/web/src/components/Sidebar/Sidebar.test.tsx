import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Sidebar, states, type SidebarGroup } from "./Sidebar";

afterEach(cleanup);

const groups: SidebarGroup[] = [
  {
    id: "live",
    items: [
      { id: "live", href: "#/live", label: "Live", icon: "live", current: true, end: "Working" },
    ],
  },
  {
    id: "review",
    heading: "Review",
    items: [
      { id: "summary", href: "#/review", label: "Summary", icon: "summary" },
      {
        id: "tofix",
        href: "#/fix",
        label: "To fix",
        icon: "tofix",
        end: "2",
        name: "To fix, 2 items",
      },
    ],
  },
];

function renderSidebar() {
  render(<Sidebar label="Pages" brand="Bar Tab" groups={groups} footer="Version 1.0" />);
}

describe("Sidebar", () => {
  it("lists every state", () => {
    expect(states).toContain("selected");
  });

  it("is a labelled nav with text group headings and links", () => {
    renderSidebar();
    const nav = screen.getByRole("navigation", { name: "Pages" });
    expect(within(nav).getByText("Review").tagName).toBe("P");
    expect(within(nav).getAllByRole("link")).toHaveLength(3);
    expect(within(nav).getByRole("list", { name: "Review" })).toBeInTheDocument();
  });

  it("marks only the current link with aria-current", () => {
    renderSidebar();
    expect(screen.getByRole("link", { name: /Live/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Summary/ })).not.toHaveAttribute("aria-current");
  });

  it("puts the count in the accessible name and shows a plain wordmark", () => {
    const { container } = render(<Sidebar label="Pages" brand="Bar Tab" groups={groups} />);
    expect(screen.getByRole("link", { name: "To fix, 2 items" })).toBeInTheDocument();
    expect(container.querySelector(".brand")).toHaveTextContent("Bar Tab");
    expect(container.querySelector(".brand-logo")).toBeNull();
  });

  it("renders an end slot only on a link that has an end", () => {
    const { container } = render(<Sidebar label="Pages" brand="Bar Tab" groups={groups} />);
    expect(container.querySelectorAll(".sidebar-end")).toHaveLength(2);
  });
});
