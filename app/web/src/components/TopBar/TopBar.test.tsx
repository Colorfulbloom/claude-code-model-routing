import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar, states } from "./TopBar";

afterEach(cleanup);

describe("TopBar", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "with-project", "project-open"]);
  });

  it("shows the page name in a banner", () => {
    render(<TopBar title="Summary" />);
    expect(screen.getByRole("banner")).toHaveTextContent("Summary");
  });

  it("omits the project button when none is given", () => {
    render(<TopBar title="Summary" />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("makes the project a button named by its visible words and opens the tray", async () => {
    const user = userEvent.setup();
    const onPress = vi.fn();
    render(<TopBar title="Summary" project={{ name: "Tidewater reporting", onPress }} />);
    const button = screen.getByRole("button", { name: "Tidewater reporting" });
    expect(button).toHaveAttribute("aria-haspopup", "listbox");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("reports the open tray through aria-expanded", () => {
    render(<TopBar title="Summary" project={{ name: "Builder", open: true, onPress: vi.fn() }} />);
    expect(screen.getByRole("button", { name: "Builder" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });
});
