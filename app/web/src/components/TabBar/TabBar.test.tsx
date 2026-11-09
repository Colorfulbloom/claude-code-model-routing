import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TabBar, states, type TabBarItem } from "./TabBar";

afterEach(cleanup);

const items: TabBarItem[] = [
  { id: "live", href: "#/live", label: "Live", icon: "live", current: true },
  { id: "review", href: "#/review", label: "Review", icon: "review" },
  { id: "setup", href: "#/setup", label: "Setup", icon: "setup" },
  { id: "fix", href: "#/fix", label: "To fix", icon: "tofix", count: "4", name: "To fix, 4" },
  { id: "more", href: "#/more", label: "More", icon: "more" },
];

describe("TabBar", () => {
  it("lists every state", () => {
    expect(states).toContain("count");
  });

  it("has five links and the count is in the accessible name", () => {
    render(<TabBar label="Sections" items={items} />);
    expect(screen.getByRole("navigation", { name: "Sections" })).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(5);
    expect(screen.getByRole("link", { name: "To fix, 4" })).toBeInTheDocument();
  });

  it("marks the current link with aria-current", () => {
    render(<TabBar label="Sections" items={items} />);
    expect(screen.getByRole("link", { name: "Live" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "More" })).not.toHaveAttribute("aria-current");
  });
});
