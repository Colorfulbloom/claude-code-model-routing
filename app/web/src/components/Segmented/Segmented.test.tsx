import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Segmented, SegmentedChoice, states, type SegmentedItem } from "./Segmented";

afterEach(cleanup);

const items: SegmentedItem[] = [
  { id: "summary", href: "#summary", label: "Summary", current: true },
  { id: "sessions", href: "#sessions", label: "Sessions" },
  { id: "agents", href: "#agents", label: "Agents" },
];

describe("Segmented", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "default",
      "hover",
      "focus",
      "selected",
      "overflow",
      "choice",
      "choice-now",
      "choice-hover",
      "choice-focus",
      "choice-disabled",
      "choice-phone",
    ]);
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

const LEVELS = ["low", "medium", "high", "xhigh", "max"].map((id) => ({ id, label: id }));

interface ChoiceProps {
  onChange?: (id: string) => void;
  options?: { id: string; label: string; now?: boolean }[];
  disabled?: boolean;
}

function Choice({ onChange, options = LEVELS, disabled = false }: ChoiceProps) {
  const [value, setValue] = useState("medium");
  return (
    <SegmentedChoice
      label="Effort"
      hint="The effort cap is high."
      value={value}
      options={options}
      disabled={disabled}
      {...(disabled ? { disabledReason: "Pick a file first." } : {})}
      onChange={(id) => {
        setValue(id);
        onChange?.(id);
      }}
    />
  );
}

describe("SegmentedChoice", () => {
  it("is a radio group named by its visible label, with the hint as its description", () => {
    render(<Choice />);
    const group = screen.getByRole("radiogroup", { name: "Effort" });
    expect(group).toHaveAccessibleDescription("The effort cap is high.");
    expect(screen.getAllByRole("radio").map((r) => r.closest("label")?.textContent)).toEqual(
      LEVELS.map((l) => l.label),
    );
  });

  it("shows the chosen option with the chosen look and a check, and no other", () => {
    const { container } = render(<Choice />);
    expect(screen.getByRole("radio", { name: "medium" })).toBeChecked();
    const chosen = container.querySelectorAll(".chosen");
    expect(chosen).toHaveLength(1);
    expect(chosen[0]).toHaveTextContent("medium");
    expect(chosen[0]?.querySelector(".chosen-mark")).not.toBeNull();
  });

  it("carries set now on a second line, for the option that is set", () => {
    render(<Choice options={LEVELS.map((l) => (l.id === "xhigh" ? { ...l, now: true } : l))} />);
    expect(screen.getAllByText("set now")).toHaveLength(1);
    expect(screen.getByText("set now").closest("label")).toHaveTextContent("xhigh");
  });

  it("picks on a click, and moves and selects with the arrow keys", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Choice onChange={onChange} />);
    await user.click(screen.getByRole("radio", { name: "max" }));
    expect(onChange).toHaveBeenLastCalledWith("max");
    await user.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenLastCalledWith("xhigh");
    expect(screen.getByRole("radio", { name: "xhigh" })).toBeChecked();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "high" })).toBeChecked();
  });

  it("enters the group once on Tab, at the chosen option", async () => {
    const user = userEvent.setup();
    render(<Choice />);
    await user.tab();
    expect(screen.getByRole("radio", { name: "medium" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("radio", { name: "medium" })).not.toHaveFocus();
  });

  it("holds every option when disabled, with the reason in words", () => {
    render(<Choice disabled />);
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
    expect(screen.getByText("Pick a file first.")).toBeInTheDocument();
  });

  it("carries the forced-state class the sheet passes", () => {
    render(
      <SegmentedChoice
        label="Effort"
        value="low"
        onChange={() => undefined}
        options={[
          { id: "low", label: "low" },
          { id: "high", label: "high", className: "is-hover" },
        ]}
      />,
    );
    expect(screen.getByRole("radio", { name: "high" }).closest("label")).toHaveClass("is-hover");
  });
});
