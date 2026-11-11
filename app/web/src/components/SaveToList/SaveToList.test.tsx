import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { EditScope } from "@/api/edit";
import { scopeRows } from "@/sheet/edit-samples";
import { en } from "@/strings/en";
import { SaveToList, states } from "./SaveToList";

afterEach(cleanup);

const WARNING = { project: "Tidewater reporting", field: "effort" };

function Harness({ start = "local" as EditScope, onPick = () => undefined }) {
  const [picked, setPicked] = useState<EditScope>(start);
  return (
    <SaveToList
      scopes={scopeRows()}
      picked={picked}
      warning={WARNING}
      onPick={(scope) => {
        setPicked(scope);
        onPick();
      }}
    />
  );
}

describe("SaveToList", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "default",
      "hover",
      "focus",
      "user-link",
      "not-writable",
      "disabled",
      "phone",
    ]);
  });

  it("is a radio group named Save to, with one radio per scope and its path", () => {
    render(<Harness />);
    const group = screen.getByRole("radiogroup", { name: "Save to" });
    const radios = within(group).getAllByRole("radio");
    expect(radios).toHaveLength(3);
    expect(radios[0]).toBeChecked();
    expect(within(group).getByText("Project local")).toBeInTheDocument();
    expect(within(group).getByText("Just you, this project")).toBeInTheDocument();
    expect(within(group).getByText("settings.local.json")).toBeInTheDocument();
  });

  it("has a help term for the legend", () => {
    render(<Harness />);
    expect(screen.getByRole("button", { name: "Save to" })).toHaveAttribute(
      "aria-haspopup",
      "dialog",
    );
  });

  it("gives each outcome a glyph and a word, never a hue alone", () => {
    const { container } = render(<Harness />);
    const chips = [...container.querySelectorAll(".status-chip")];
    expect(chips.map((c) => c.textContent)).toEqual([
      "Takes effect",
      "Overridden by Project local",
      "Overridden by Project local",
    ]);
    expect(chips.map((c) => c.getAttribute("data-glyph"))).toEqual([
      "in-effect",
      "overridden",
      "overridden",
    ]);
  });

  it("shows Selected on the chosen row only", () => {
    const { container } = render(<Harness />);
    const words = [...container.querySelectorAll(".chosen-word")];
    expect(words).toHaveLength(1);
    expect(words[0]).toHaveTextContent("Selected");
    expect(words[0]?.closest(".save-to-row")).toHaveClass("chosen-row");
  });

  it("shows the link target under a linked file", () => {
    render(<Harness />);
    expect(screen.getByText("~/dotfiles/claude/settings.json")).toBeInTheDocument();
    expect(screen.getByText(/links to/)).toBeInTheDocument();
  });

  it("picks a scope on a click and on the arrow keys", async () => {
    const user = userEvent.setup();
    const onPick = vi.fn();
    render(<Harness onPick={onPick} />);
    await user.click(screen.getByRole("radio", { name: /Shared project/ }));
    expect(screen.getAllByRole("radio")[1]).toBeChecked();
    await user.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("radio")[2]).toBeChecked();
    expect(onPick).toHaveBeenCalledTimes(2);
  });

  it("warns that a User save changes nothing here, only while User is picked and loses", () => {
    render(<Harness />);
    expect(screen.queryByText(/This won't change/)).toBeNull();
    cleanup();
    render(<Harness start="user" />);
    expect(
      screen.getByText(
        /This won't change Tidewater reporting, because Project local sets effort there/,
      ),
    ).toBeInTheDocument();
  });

  it("shows a row that can't be saved to before it is picked", () => {
    const rows = scopeRows({
      project: { writable: false, read_only_reason: "managed" },
      user: { writable: false, read_only_reason: "not_writable" },
    });
    render(<SaveToList scopes={rows} picked="local" onPick={() => undefined} />);
    const radios = screen.getAllByRole("radio");
    expect(radios[1]).toBeDisabled();
    expect(radios[2]).toBeDisabled();
    expect(screen.getAllByText("Can't change here")).toHaveLength(2);
    expect(
      screen.getByText("Your organization manages this file, so Bar Tab can't change it."),
    ).toBeInTheDocument();
  });

  it("lists the rows in the inspector's order, top wins, whatever order they arrive in", () => {
    const rows = scopeRows().reverse();
    render(<SaveToList scopes={rows} picked="local" onPick={() => undefined} />);
    expect(
      screen.getAllByRole("radio").map((radio) => radio.closest("label")?.textContent ?? ""),
    ).toEqual([
      expect.stringContaining("Project local"),
      expect.stringContaining("Shared project"),
      expect.stringContaining("User"),
    ]);
  });

  it("explains a link that leaves the home in a plain line the row points to", () => {
    const rows = scopeRows({
      user: {
        writable: false,
        read_only_reason: "link_outside",
        link: true,
        real_path: "/work/dotfiles/settings.json",
      },
    });
    render(<SaveToList scopes={rows} picked="local" onPick={() => undefined} />);
    const user = screen.getAllByRole("radio")[2];
    expect(user).toBeDisabled();
    const line = screen.getByText(en.ed_link_outside_row);
    expect(user).toHaveAttribute("aria-describedby", expect.stringContaining(line.id));
    expect(screen.getByText(/\/work\/dotfiles\/settings\.json/)).toBeInTheDocument();
  });

  it("explains a link to a missing file in a plain line the row points to", () => {
    const rows = scopeRows({
      user: {
        writable: false,
        read_only_reason: "link_dangling",
        link: true,
        real_path: "~/dotfiles/settings.json",
      },
    });
    render(<SaveToList scopes={rows} picked="local" onPick={() => undefined} />);
    const user = screen.getAllByRole("radio")[2];
    expect(user).toBeDisabled();
    const line = screen.getByText(en.ed_link_dangling_row);
    expect(user).toHaveAttribute("aria-describedby", expect.stringContaining(line.id));
    expect(screen.queryByText(en.ed_link_outside_row)).toBeNull();
    expect(screen.getByText("~/dotfiles/settings.json")).toBeInTheDocument();
  });

  it("keys the link-outside line on the server's code, not on a link that can't be saved to", () => {
    // A linked file locked for another reason keeps its link line but gets no outside line.
    const rows = scopeRows({
      user: {
        writable: false,
        read_only_reason: "not_writable",
        link: true,
        real_path: "~/dotfiles/settings.json",
      },
    });
    render(<SaveToList scopes={rows} picked="local" onPick={() => undefined} />);
    expect(screen.queryByText(en.ed_link_outside_row)).toBeNull();
    expect(screen.getAllByRole("radio")[2]).not.toHaveAttribute("aria-describedby");
    expect(screen.getByText("~/dotfiles/settings.json")).toBeInTheDocument();
  });

  it("holds the whole list while a save is in flight", () => {
    render(<SaveToList scopes={scopeRows()} picked="local" onPick={() => undefined} disabled />);
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });
});
