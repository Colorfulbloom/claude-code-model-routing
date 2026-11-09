import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button, states } from "./Button";

afterEach(cleanup);

describe("Button", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "hover", "focus", "pressed", "disabled", "busy"]);
  });

  it("presses with the mouse and keyboard", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(<Button onPress={onPress}>Copy path</Button>);
    await user.click(screen.getByRole("button", { name: "Copy path" }));
    await user.keyboard("{Enter}");
    expect(onPress).toHaveBeenCalledTimes(2);
  });

  it("is aria-disabled, stays focusable and ties its reason with aria-describedby", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(
      <Button variant="primary" disabled disabledReason="Preview first." onPress={onPress}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled();
    expect(button).toHaveAccessibleDescription("Preview first.");
    await user.tab();
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    await user.click(button);
    expect(onPress).not.toHaveBeenCalled();
  });

  it("swaps the label and sets aria-busy while busy", () => {
    render(
      <Button busy busyLabel="Saving…">
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByText("Save")).toBeNull();
  });

  it("renders a link when it has an href", () => {
    render(<Button href="#/setup">Open Your setup</Button>);
    expect(screen.getByRole("link", { name: "Open Your setup" })).toHaveAttribute(
      "href",
      "#/setup",
    );
  });

  it("names the icon variant by its aria-label", () => {
    render(
      <Button variant="icon" ariaLabel="Close">
        ✕
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
});
