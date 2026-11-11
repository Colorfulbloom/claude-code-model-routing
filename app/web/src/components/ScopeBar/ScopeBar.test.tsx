import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScopeBar, states } from "./ScopeBar";

afterEach(cleanup);

const options = [
  { id: "today", label: "Today" },
  { id: "7d", label: "Last 7 days" },
  { id: "30d", label: "Last 30 days" },
  { id: "90d", label: "Last 90 days" },
  { id: "12m", label: "Last 12 months" },
  { id: "all", label: "All time" },
];

describe("ScopeBar", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "range",
      "range-hover",
      "range-focus",
      "session",
      "session-hover",
      "session-focus",
      "session-no-live",
      "with-pages",
    ]);
  });

  it("shows the title, the sub and a Range Select with the presets", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ScopeBar
        form="range"
        title="Summary"
        sub="October 10 to November 8"
        range={{ label: "Range", options, value: "30d", onChange }}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Summary" })).toBeInTheDocument();
    expect(screen.getByText("October 10 to November 8")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: /^Range/ });
    expect(button).toHaveTextContent("Last 30 days");
    // The "?" sits beside the Range Select, as its own button.
    expect(screen.getByRole("button", { name: "About Range" })).toHaveAttribute(
      "aria-haspopup",
      "dialog",
    );
    await user.click(button);
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual(
      options.map((option) => option.label),
    );
    await user.click(screen.getByRole("option", { name: "Today" }));
    expect(onChange).toHaveBeenCalledWith("today");
  });

  it("heads the open Range list with Range and gives the popover the board's width class", async () => {
    const user = userEvent.setup();
    render(
      <ScopeBar
        form="range"
        title="Summary"
        range={{ label: "Range", options, value: "30d", onChange: vi.fn() }}
      />,
    );
    expect(document.querySelector(".scope-bar-range")).not.toBeNull();
    await user.click(screen.getByRole("button", { name: /^Range/ }));
    const popover = document.querySelector(".select-popover");
    expect(popover).toHaveClass("select-popover-range");
    expect(popover?.querySelector(".select-heading")).toHaveTextContent("Range");
  });

  it("shows the back link, the Session Select slot and Open in Live in the session form", () => {
    render(
      <ScopeBar
        form="session"
        title="Session at 6:10 PM"
        sub="This session is still running"
        back={{ label: "All sessions", href: "#sessions" }}
        sessionSelect={<span>Session slot</span>}
        openLive={{ label: "Open in Live", href: "#live" }}
      />,
    );
    expect(screen.getByRole("link", { name: "All sessions" })).toHaveAttribute("href", "#sessions");
    expect(screen.getByText("Session slot")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in Live" })).toHaveAttribute("href", "#live");
  });

  it("leaves Open in Live out when the caller does", () => {
    render(
      <ScopeBar
        form="session"
        title="Session at 6:10 PM"
        back={{ label: "All sessions", href: "#sessions" }}
        sessionSelect={<span>Session slot</span>}
      />,
    );
    expect(screen.queryByRole("link", { name: "Open in Live" })).toBeNull();
  });

  it("puts the phone pages under the bar when the caller passes them", () => {
    render(
      <ScopeBar
        form="range"
        title="Summary"
        range={{ label: "Range", options, value: "30d", onChange: () => undefined }}
        pages={<nav aria-label="Review pages">pages</nav>}
      />,
    );
    const pages = screen.getByRole("navigation", { name: "Review pages" });
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading.compareDocumentPosition(pages) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
