import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Select, states, type SelectOption } from "./Select";

afterEach(cleanup);

const items: SelectOption[] = [
  { id: "7", label: "Last 7 days" },
  { id: "30", label: "Last 30 days", description: "Default" },
  { id: "90", label: "Last 90 days" },
];

function Harness({ onChange }: { onChange?: (id: string) => void }) {
  const [value, setValue] = useState<string | null>("30");
  return (
    <Select
      label="Range"
      items={items}
      value={value}
      onChange={(id) => {
        setValue(id);
        onChange?.(id);
      }}
    />
  );
}

describe("Select", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "hover", "focus", "open", "disabled"]);
  });

  it("shows its label and value, and hides the chosen option's description", () => {
    render(<Harness />);
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Range");
    expect(button).toHaveTextContent("Last 30 days");
    expect(within(button).queryByText("Default")).toBeNull();
  });

  it("opens with the keyboard and picks an option", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness onChange={onChange} />);
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    expect(screen.getAllByRole("option")).toHaveLength(3);
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith("90");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button")).toHaveTextContent("Last 90 days");
  });

  it("closes with Escape and keeps the value", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.tab();
    await user.keyboard("{Alt>}{ArrowDown}{/Alt}");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(screen.getByRole("button")).toHaveTextContent("Last 30 days");
  });

  it("keeps a disabled select focusable and ties its reason to it", async () => {
    const user = userEvent.setup();
    render(
      <Select
        label="Range"
        items={items}
        value="30"
        onChange={() => undefined}
        isDisabled
        disabledReason="Only one range is available."
      />,
    );
    const button = screen.getByRole("button");
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled();
    expect(button).toHaveAccessibleDescription("Only one range is available.");
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("shows a heading and an empty state in the popover", async () => {
    const user = userEvent.setup();
    render(
      <Select
        label="Project"
        items={[]}
        value={null}
        onChange={() => undefined}
        heading="Projects"
        emptyState={<p>No projects yet</p>}
      />,
    );
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("Projects")).toBeInTheDocument();
    expect(screen.getByText("No projects yet")).toBeInTheDocument();
  });
});
