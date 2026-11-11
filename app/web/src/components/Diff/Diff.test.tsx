import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { DiffLine } from "@/api/edit";
import { Diff, states, withFolds } from "./Diff";
import { PathText } from "./PathText";

afterEach(cleanup);

const LINES: DiffLine[] = [
  { kind: "ctx", old_n: 1, new_n: 1, text: '  "env": {' },
  { kind: "del", old_n: 2, new_n: null, text: '    "LEVEL": "xhigh"' },
  { kind: "add", old_n: null, new_n: 2, text: '    "LEVEL": "medium"' },
  { kind: "ctx", old_n: 3, new_n: 3, text: "  }," },
];

describe("Diff", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "link", "new-file", "no-path", "wrap"]);
  });

  it("shows the file's own line numbers, the old one on a removed line", () => {
    render(<Diff lines={LINES} label="This save" />);
    const items = within(screen.getByRole("list", { name: "This save" })).getAllByRole("listitem");
    expect(items).toHaveLength(4);
    expect(items.map((li) => li.querySelector(".diff-ln")?.textContent)).toEqual([
      "1",
      "2",
      "2",
      "3",
    ]);
  });

  it("folds each run of unchanged lines the server left out into one counted row", () => {
    const lines: DiffLine[] = [
      { kind: "ctx", old_n: 3, new_n: 3, text: "a" },
      { kind: "del", old_n: 4, new_n: null, text: "b" },
      { kind: "add", old_n: null, new_n: 4, text: "c" },
      { kind: "ctx", old_n: 5, new_n: 5, text: "d" },
      { kind: "ctx", old_n: 12, new_n: 12, text: "e" },
      { kind: "del", old_n: 13, new_n: null, text: "f" },
    ];
    const { container } = render(<Diff lines={lines} label="Undo" />);
    const folds = [...container.querySelectorAll(".diff-fold")].map((li) => li.textContent);
    // Two lines above the first line shown, six between the hunks.
    expect(folds).toEqual(["⋮2 unchanged lines", "⋮6 unchanged lines"]);
    expect(withFolds(lines).map((row) => row.kind)).toEqual([
      "fold",
      "line",
      "line",
      "line",
      "line",
      "fold",
      "line",
      "line",
    ]);
  });

  it("says one unchanged line in the singular and folds nothing when the numbers run on", () => {
    const one: DiffLine[] = [{ kind: "ctx", old_n: 2, new_n: 2, text: "a" }];
    const { container, rerender } = render(<Diff lines={one} label="Undo" />);
    expect(container.querySelector(".diff-fold")).toHaveTextContent("1 unchanged line");
    expect(container.querySelector(".diff-fold")).not.toHaveTextContent("lines");
    rerender(<Diff lines={LINES} label="Undo" />);
    expect(container.querySelector(".diff-fold")).toBeNull();
  });

  it("shows every removed line of an undo, including another program's change, in red", () => {
    const lines: DiffLine[] = [
      { kind: "ctx", old_n: 1, new_n: 1, text: "{" },
      { kind: "add", old_n: null, new_n: 2, text: '  "effortLevel": "high",' },
      { kind: "ctx", old_n: 2, new_n: 3, text: '  "permissions": {}' },
      { kind: "del", old_n: 3, new_n: null, text: '  "includeCoAuthoredBy": false' },
    ];
    const { container } = render(<Diff lines={lines} label="What Undo changes" />);
    const removed = [...container.querySelectorAll(".diff-del")].map((li) => li.textContent);
    expect(removed).toHaveLength(1);
    expect(removed[0]).toContain("includeCoAuthoredBy");
    expect(container.querySelector(".diff-fold")).toBeNull();
  });

  it("marks added and removed lines with a plus and a minus, and says the word to a screen reader", () => {
    const { container } = render(<Diff lines={LINES} label="This save" />);
    const marks = [...container.querySelectorAll(".diff-gm")];
    expect(marks.map((m) => m.textContent)).toEqual(["", "-", "+", ""]);
    for (const mark of marks) expect(mark).toHaveAttribute("aria-hidden", "true");
    const items = screen.getAllByRole("listitem");
    expect(items[1]).toHaveTextContent("removed");
    expect(items[2]).toHaveTextContent("added");
    expect(items[0]).toHaveTextContent("unchanged");
    expect(items[1]).toHaveClass("diff-del");
    expect(items[2]).toHaveClass("diff-add");
    expect(items[0]).not.toHaveClass("diff-add", "diff-del");
  });

  it("shows the path line, and the link target under it", () => {
    render(
      <Diff
        lines={LINES}
        label="This save"
        path="~/.claude/settings.json"
        linksTo="~/dotfiles/claude/settings.json"
      />,
    );
    expect(screen.getByText("~/.claude/settings.json")).toBeInTheDocument();
    expect(screen.getByText(/links to/)).toBeInTheDocument();
    expect(screen.getByText("~/dotfiles/claude/settings.json")).toBeInTheDocument();
  });

  it("leaves out the path line when it has no path", () => {
    const { container } = render(<Diff lines={LINES} label="This save" />);
    expect(container.querySelector(".diff-path")).toBeNull();
  });

  it("draws a new file as all added lines", () => {
    const lines: DiffLine[] = [
      { kind: "add", old_n: null, new_n: 1, text: "{" },
      { kind: "add", old_n: null, new_n: 2, text: "}" },
    ];
    const { container } = render(<Diff lines={lines} label="This save" />);
    expect(container.querySelectorAll(".diff-add")).toHaveLength(2);
    expect(container.querySelectorAll(".diff-del")).toHaveLength(0);
  });
});

describe("PathText", () => {
  it("sets the folder muted and the file name bold, with a break point after each slash", () => {
    const { container } = render(<PathText path="~/work/app/.claude/settings.local.json" />);
    expect(container.querySelector(".path-text-dir")).toHaveTextContent("~/work/app/.claude/");
    expect(container.querySelector(".path-text-name")).toHaveTextContent("settings.local.json");
    expect(container.querySelectorAll("wbr")).toHaveLength(4);
    expect(container.textContent).toBe("~/work/app/.claude/settings.local.json");
  });

  it("shows a bare file name with no folder", () => {
    const { container } = render(<PathText path="settings.json" />);
    expect(container.querySelector(".path-text-dir")).toHaveTextContent("");
    expect(container.querySelector(".path-text-name")).toHaveTextContent("settings.json");
  });
});
