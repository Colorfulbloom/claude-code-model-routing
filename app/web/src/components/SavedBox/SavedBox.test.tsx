import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SavedBox, states } from "./SavedBox";

afterEach(cleanup);

const SAVED_AT = new Date(2026, 10, 11, 18, 41, 0).toISOString();

describe("SavedBox", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["checking", "confirmed", "undo-busy", "phone"]);
  });

  it("says Saved. with the time and what Undo does, and links to all changes", () => {
    render(
      <SavedBox
        savedAt={SAVED_AT}
        recheck={{ state: "confirmed", value: "medium" }}
        onUndo={() => undefined}
        changesHref="#changes"
      />,
    );
    expect(screen.getByText("Saved.")).toBeInTheDocument();
    expect(screen.getByText("6:41 PM. Undo puts the old file back.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All changes" })).toHaveAttribute("href", "#changes");
  });

  it("shows the checking line with a glyph, and holds its announcement while busy", () => {
    const { container } = render(
      <SavedBox
        savedAt={SAVED_AT}
        recheck={{ state: "checking" }}
        onUndo={() => undefined}
        changesHref="#changes"
      />,
    );
    const line = screen.getByText("Reading the file again to check the change").closest("p");
    expect(line).toHaveAttribute("role", "status");
    expect(line).toHaveAttribute("aria-busy", "true");
    expect(container.querySelector(".saved-box-ring")).toHaveAttribute("aria-hidden", "true");
  });

  it("settles to the confirmed line with the value, and is no longer busy", () => {
    render(
      <SavedBox
        savedAt={SAVED_AT}
        recheck={{ state: "confirmed", value: "medium" }}
        onUndo={() => undefined}
        changesHref="#changes"
      />,
    );
    const line = screen.getByText("Checked the file. It still holds medium.").closest("p");
    expect(line).toHaveAttribute("role", "status");
    expect(line).not.toHaveAttribute("aria-busy");
  });

  it("calls onUndo from the Undo button", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    render(
      <SavedBox
        savedAt={SAVED_AT}
        recheck={{ state: "checking" }}
        onUndo={onUndo}
        changesHref="#changes"
      />,
    );
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });

  it("keeps Undo in place and busy while an undo is in flight, and ignores a press", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    render(
      <SavedBox
        savedAt={SAVED_AT}
        recheck={{ state: "checking" }}
        onUndo={onUndo}
        undoBusy
        changesHref="#changes"
      />,
    );
    const button = screen.getByRole("button", { name: "Undo" });
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.click(button);
    expect(onUndo).not.toHaveBeenCalled();
  });
});
