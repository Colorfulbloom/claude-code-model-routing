import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DiffLine } from "@/api/edit";
import { OverwrittenBox, states, type DriftView } from "./OverwrittenBox";

afterEach(cleanup);

const LINES: DiffLine[] = [
  { kind: "ctx", old_n: 2, new_n: 2, text: '  "permissions": {' },
  { kind: "add", old_n: null, new_n: 3, text: '    "allow": []' },
];

function Harness({
  keys = ["permissions.allow"],
  ours = true as boolean | null,
  drift = { state: "lines", lines: LINES, path: "~/x/settings.local.json" } as DriftView,
  onUndo = () => undefined,
}) {
  const [open, setOpen] = useState(false);
  return (
    <OverwrittenBox
      keys={keys}
      ours={ours}
      field="effort"
      open={open}
      onToggle={() => {
        setOpen((v) => !v);
      }}
      drift={drift}
      onUndo={onUndo}
    />
  );
}

describe("OverwrittenBox", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "kept",
      "lost",
      "drift-open",
      "drift-loading",
      "drift-refused",
      "many-keys",
    ]);
  });

  it("lists several changed keys with commas", () => {
    const { container } = render(<Harness keys={["permissions.allow", "env.FOO"]} />);
    expect(container.querySelector(".overwritten-box-keys")).toHaveTextContent(
      "permissions.allow, env.FOO",
    );
  });

  it("is a polite status with the warning, the changed keys and a glyph", () => {
    const { container } = render(<Harness />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(
      "Saved, but another program changed this file right after. Review it before you go on.",
    );
    expect(within(status).getByText("Changed after your save")).toBeInTheDocument();
    expect(within(status).getByText("permissions.allow")).toBeInTheDocument();
    expect(container.querySelector(".message-mark")).toHaveAttribute("aria-hidden", "true");
  });

  it("says whether the saved value is still in the file", () => {
    const { rerender } = render(
      <OverwrittenBox
        keys={["a"]}
        ours
        field="effort"
        open={false}
        onToggle={() => undefined}
        onUndo={() => undefined}
      />,
    );
    expect(screen.getByText("Your effort change is still in the file.")).toBeInTheDocument();
    rerender(
      <OverwrittenBox
        keys={["a"]}
        ours={false}
        field="effort"
        open={false}
        onToggle={() => undefined}
        onUndo={() => undefined}
      />,
    );
    expect(screen.getByText("Your effort change is no longer in the file.")).toBeInTheDocument();
    rerender(
      <OverwrittenBox
        keys={["a"]}
        ours={null}
        field="effort"
        open={false}
        onToggle={() => undefined}
        onUndo={() => undefined}
      />,
    );
    expect(screen.queryByText(/Your effort change/)).toBeNull();
  });

  it("opens the drift diff under the warning on Review changes, and moves focus to it", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const review = screen.getByRole("button", { name: "Review changes" });
    expect(review).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("heading", { name: "What the other program changed" })).toBeNull();
    await user.click(review);
    expect(review).toHaveAttribute("aria-expanded", "true");
    const drift = screen.getByRole("region", { name: "What the other program changed" });
    expect(drift).toHaveFocus();
    // Two lines, and one fold row for the line the numbers skip over at the top.
    const items = within(drift).getAllByRole("listitem");
    expect(items.filter((li) => !li.classList.contains("diff-fold"))).toHaveLength(2);
    expect(review).toHaveAttribute("aria-controls", drift.id);
  });

  it("closes the drift on a second press", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const review = screen.getByRole("button", { name: "Review changes" });
    await user.click(review);
    await user.click(review);
    expect(screen.queryByRole("region", { name: "What the other program changed" })).toBeNull();
  });

  it("marks the drift busy while it loads", async () => {
    const user = userEvent.setup();
    render(<Harness drift={{ state: "loading" }} />);
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    expect(screen.getByRole("region", { name: "What the other program changed" })).toHaveAttribute(
      "aria-busy",
      "true",
    );
  });

  it("says why when the drift can't be rebuilt", async () => {
    const user = userEvent.setup();
    render(
      <Harness drift={{ state: "refused", code: "cant_rebuild", file: "settings.local.json" }} />,
    );
    await user.click(screen.getByRole("button", { name: "Review changes" }));
    expect(
      screen.getByText(
        "Bar Tab can't show what the other program changed, because it can't rebuild the file it saved.",
      ),
    ).toBeInTheDocument();
  });

  it("calls onUndo from the Undo button", async () => {
    const user = userEvent.setup();
    const onUndo = vi.fn();
    render(<Harness onUndo={onUndo} />);
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(onUndo).toHaveBeenCalledTimes(1);
  });
});
