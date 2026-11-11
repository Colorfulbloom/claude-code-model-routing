import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { HELP } from "@/strings/help";
import { resetViewport } from "@/test/media";
import { HelpTerm, states } from "./HelpTerm";

afterEach(() => {
  cleanup();
  resetViewport();
});

describe("HelpTerm", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["closed", "open", "in-header"]);
  });

  it("is a button named by its text alone, with a dialog behind it", () => {
    render(<HelpTerm help="agents.check">Check</HelpTerm>);
    const button = screen.getByRole("button", { name: "Check" });
    expect(button).toHaveAttribute("aria-haspopup", "dialog");
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("carries its help id on the trigger, so a page can find it again", () => {
    render(<HelpTerm help="agents.check">Check</HelpTerm>);
    expect(screen.getByRole("button", { name: "Check" })).toHaveAttribute(
      "data-help-id",
      "agents.check",
    );
  });

  it("takes a note that describes the spot, so the button keeps it", () => {
    render(
      <>
        <HelpTerm help="agents.unchecked" describedBy="note">
          Not checked
        </HelpTerm>
        <span id="note" className="sr-only">
          Not checked, because a plugin agent is out of scope.
        </span>
      </>,
    );
    expect(screen.getByRole("button", { name: "Not checked" })).toHaveAccessibleDescription(
      "Not checked, because a plugin agent is out of scope.",
    );
  });

  it("stays open when the spot re-renders", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<HelpTerm help="agents.check">Check</HelpTerm>);
    await user.click(screen.getByRole("button", { name: "Check" }));
    const dialog = screen.getByRole("dialog");
    rerender(<HelpTerm help="agents.check">Check</HelpTerm>);
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(dialog).toHaveFocus();
  });

  it("keeps a column header's name as its label when it is the header's only content", () => {
    render(
      <table>
        <thead>
          <tr>
            <th scope="col">Agent</th>
            <th scope="col">
              <HelpTerm help="agents.check">Check</HelpTerm>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>builder</td>
            <td>Overridden</td>
          </tr>
        </tbody>
      </table>,
    );
    const header = screen.getByRole("columnheader", { name: "Check" });
    expect(within(header).getAllByRole("button")).toHaveLength(1);
    expect(header.textContent).toBe("Check");
  });

  it("opens the entry, marks its own line and returns focus on Escape", async () => {
    const user = userEvent.setup();
    render(
      <HelpTerm help="live.cache" line={HELP["live.cache"].lines[0].label}>
        Read from cache
      </HelpTerm>,
    );
    const button = screen.getByRole("button", { name: "Read from cache" });
    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Read from cache" });
    expect(within(dialog).getAllByText(en.hp_this_column)).toHaveLength(1);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => {
      expect(button).toHaveFocus();
    });
  });

  it("opens from the keyboard with Enter", async () => {
    const user = userEvent.setup();
    render(<HelpTerm help="agents.check">Check</HelpTerm>);
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("dialog", { name: "Check" })).toBeVisible();
  });
});
