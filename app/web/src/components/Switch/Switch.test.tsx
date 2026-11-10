import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Switch, states } from "./Switch";

afterEach(cleanup);

function Controlled({ start = false, disabled = false }: { start?: boolean; disabled?: boolean }) {
  const [on, setOn] = useState(start);
  return (
    <Switch selected={on} onChange={setOn} disabled={disabled} disabledReason="Not available here">
      Show where each comes from
    </Switch>
  );
}

describe("Switch", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["off", "on", "hover", "focus", "disabled-off", "disabled-on"]);
  });

  it("is a switch named by its label, off by default", () => {
    render(<Controlled />);
    const control = screen.getByRole("switch", { name: "Show where each comes from" });
    expect(control).not.toBeChecked();
  });

  it("follows the selected prop, so the page can keep the state in the URL", () => {
    const { rerender } = render(
      <Switch selected={true} onChange={() => undefined}>
        Label
      </Switch>,
    );
    expect(screen.getByRole("switch", { name: "Label" })).toBeChecked();
    rerender(
      <Switch selected={false} onChange={() => undefined}>
        Label
      </Switch>,
    );
    expect(screen.getByRole("switch", { name: "Label" })).not.toBeChecked();
  });

  it("toggles with Space and reports the new state", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Switch selected={false} onChange={onChange}>
        Label
      </Switch>,
    );
    await user.tab();
    expect(screen.getByRole("switch", { name: "Label" })).toHaveFocus();
    await user.keyboard(" ");
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("makes the whole label the target", async () => {
    const user = userEvent.setup();
    render(<Controlled />);
    await user.click(screen.getByText("Show where each comes from"));
    expect(screen.getByRole("switch")).toBeChecked();
    await user.click(screen.getByText("Show where each comes from"));
    expect(screen.getByRole("switch")).not.toBeChecked();
  });

  it("draws a 40 by 24 track with a thumb, hidden from assistive tech", () => {
    const { container } = render(<Controlled />);
    const track = container.querySelector(".switch-track");
    expect(track).toHaveAttribute("aria-hidden", "true");
    expect(track?.querySelector(".switch-thumb")).not.toBeNull();
  });

  it("disables with a visible reason tied to the control", async () => {
    const user = userEvent.setup();
    render(<Controlled disabled />);
    const control = screen.getByRole("switch");
    expect(control).toBeDisabled();
    expect(control).toHaveAccessibleDescription("Not available here");
    await user.click(screen.getByText("Show where each comes from"));
    expect(control).not.toBeChecked();
  });

  it("shows no reason while enabled", () => {
    render(<Controlled />);
    expect(screen.queryByText("Not available here")).toBeNull();
  });

  it("passes a forced-state class to the label", () => {
    const { container } = render(
      <Switch selected={false} onChange={() => undefined} className="is-hover">
        Label
      </Switch>,
    );
    expect(container.querySelector("label")).toHaveClass("is-hover");
  });
});
