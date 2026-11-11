import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DiffLine } from "@/api/edit";
import { UndoConfirm, states } from "./UndoConfirm";

afterEach(cleanup);

const LINES: DiffLine[] = [
  { kind: "del", old_n: 3, new_n: null, text: '    "allow": []' },
  { kind: "add", old_n: null, new_n: 6, text: '    "LEVEL": "xhigh"' },
];

function setup(props: Partial<React.ComponentProps<typeof UndoConfirm>> = {}) {
  const onKeep = vi.fn();
  const onAnyway = vi.fn();
  render(
    <UndoConfirm
      file="settings.local.json"
      path="~/work/app/.claude/settings.local.json"
      lines={LINES}
      onKeep={onKeep}
      onAnyway={onAnyway}
      {...props}
    />,
  );
  return { onKeep, onAnyway };
}

describe("UndoConfirm", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "busy", "sheet"]);
  });

  it("warns that the file changed, and shows what Undo changes with its path", () => {
    setup();
    expect(screen.getByRole("heading", { level: 2, name: "Undo this save" })).toBeInTheDocument();
    expect(
      screen.getByText(
        "settings.local.json changed after your save. Undo puts the whole old file back, so it also removes that other change.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 3, name: "What Undo changes" }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "What Undo changes" });
    const items = within(list).getAllByRole("listitem");
    // Two changed lines, with a fold row for each run of unchanged lines the numbers skip over.
    expect(items.filter((li) => !li.classList.contains("diff-fold"))).toHaveLength(2);
    expect(items.filter((li) => li.classList.contains("diff-fold"))).toHaveLength(2);
    expect(screen.getByText("~/work/app/.claude/settings.local.json")).toBeInTheDocument();
  });

  it("asks without a diff when the page has no lines, naming the warning it is given", () => {
    render(
      <UndoConfirm
        file="settings.local.json"
        path=".claude/settings.local.json"
        warning="Undo deletes the file"
        onKeep={() => undefined}
        onAnyway={() => undefined}
      />,
    );
    expect(screen.getByText("Undo deletes the file")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "What Undo changes" })).toBeNull();
    expect(screen.getByText("settings.local.json")).toBeInTheDocument();
  });

  it("puts Undo anyway first when asked, as the phone sheet does", () => {
    render(
      <UndoConfirm
        file="settings.local.json"
        path=".claude/settings.local.json"
        lines={LINES}
        anywayFirst
        onKeep={() => undefined}
        onAnyway={() => undefined}
      />,
    );
    const names = screen.getAllByRole("button").map((b) => b.textContent);
    expect(names.indexOf("Undo anyway")).toBeLessThan(names.indexOf("Keep the file as it is"));
  });

  it("keeps the file from the Keep button and from Cancel", async () => {
    const user = userEvent.setup();
    const { onKeep, onAnyway } = setup();
    await user.click(screen.getByRole("button", { name: "Keep the file as it is" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onKeep).toHaveBeenCalledTimes(2);
    expect(onAnyway).not.toHaveBeenCalled();
  });

  it("undoes anyway from the danger button", async () => {
    const user = userEvent.setup();
    const { onAnyway } = setup();
    const button = screen.getByRole("button", { name: "Undo anyway" });
    expect(button).toHaveClass("button-danger");
    await user.click(button);
    expect(onAnyway).toHaveBeenCalledTimes(1);
  });

  it("holds both buttons while the undo is in flight, with Undo anyway busy", async () => {
    const user = userEvent.setup();
    const { onKeep, onAnyway } = setup({ busy: true });
    const anyway = screen.getByRole("button", { name: "Undo anyway" });
    const keep = screen.getByRole("button", { name: "Keep the file as it is" });
    expect(anyway).toHaveAttribute("aria-busy", "true");
    expect(keep).toHaveAttribute("aria-disabled", "true");
    await user.click(anyway);
    await user.click(keep);
    expect(onAnyway).not.toHaveBeenCalled();
    expect(onKeep).not.toHaveBeenCalled();
  });

  it("shows the link target when the path is a link", () => {
    setup({ linksTo: "~/dotfiles/settings.json" });
    expect(screen.getByText("~/dotfiles/settings.json")).toBeInTheDocument();
  });

  it("puts Undo anyway first in the phone sheet, with an icon Close and no Cancel", () => {
    setup({ layout: "sheet" });
    const buttons = screen.getAllByRole("button").map((b) => b.textContent);
    expect(buttons).toEqual(["✕", "Undo anyway", "Keep the file as it is"]);
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  });

  it("gives the heading a focus target for the page", () => {
    setup();
    expect(screen.getByRole("heading", { level: 2 })).toHaveAttribute("tabindex", "-1");
  });
});
