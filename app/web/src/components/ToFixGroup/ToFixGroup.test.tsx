import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ToFixRow } from "../ToFixRow/ToFixRow";
import { ToFixGroup, states, type ToFixKind } from "./ToFixGroup";

afterEach(cleanup);

function group(kind: ToFixKind, extra: { count?: string; note?: string } = {}) {
  return (
    <ToFixGroup kind={kind} title="Couldn't read" {...extra}>
      <ToFixRow
        title="The dashboard couldn't open notes.md"
        cause="File permissions block reading."
        consequence="Problems in this file stay hidden."
        action={{ kind: "cant_fix_here", reason: "Change the file's permissions." }}
      />
      <ToFixRow
        title="Second problem"
        cause="Cause."
        consequence="Consequence."
        action={{ kind: "cant_fix_here", reason: "Reason." }}
      />
    </ToFixGroup>
  );
}

describe("ToFixGroup", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["couldnt-read", "wont-load", "not-as-set", "cant-tell", "notices"]);
  });

  it("is a section named by its h2, with the rows in a list", () => {
    render(group("couldnt_read", { count: "2" }));
    const section = screen.getByRole("region", { name: "Couldn't read" });
    expect(within(section).getByRole("heading", { level: 2, name: "Couldn't read" })).toBeVisible();
    expect(within(section).getAllByRole("listitem")).toHaveLength(2);
    expect(within(section).getAllByRole("heading", { level: 3 })).toHaveLength(2);
  });

  it("keeps the count in its own slot, apart from the heading text", () => {
    const { container } = render(group("couldnt_read", { count: "2" }));
    expect(screen.getByRole("heading", { level: 2 })).toHaveTextContent(/^Couldn't read$/);
    expect(container.querySelector(".card-count")).toHaveTextContent("2");
  });

  it("puts the status glyph in the heading, hidden from assistive tech", () => {
    const { container } = render(group("not_as_set", { count: "2" }));
    expect(container.querySelector("h2 .tofix-mark")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".tofix-group-not-as-set")).not.toBeNull();
  });

  it("has no count for Can't tell, even when one is passed, and shows its note", () => {
    const { container } = render(
      group("cant_tell", {
        count: "1",
        note: "Not counted. The dashboard can't tell which value wins.",
      }),
    );
    expect(container.querySelector(".card-count")).toBeNull();
    expect(screen.getByText(/Not counted/)).toHaveClass("card-question");
    expect(container.querySelector(".tofix-group-cant-tell")).not.toBeNull();
  });

  it("names a counted group's h2 with the count when it has an aria label", () => {
    render(
      <ToFixGroup kind="wont_load" title="Won't load" count="2" ariaLabel="Won't load, 2">
        <li>Row</li>
      </ToFixGroup>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Won't load, 2" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Won't load, 2" })).toBeInTheDocument();
  });

  it("ignores the aria label on Can't tell, which has no count", () => {
    render(
      <ToFixGroup kind="cant_tell" title="Can't tell" ariaLabel="Can't tell, 2">
        <li>Row</li>
      </ToFixGroup>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Can't tell" })).toBeInTheDocument();
  });

  it("has no count and no mark for Notices", () => {
    const { container } = render(group("notices", { count: "3" }));
    expect(container.querySelector(".card-count")).toBeNull();
    expect(container.querySelector(".tofix-mark")).toBeNull();
  });

  it("names every kind in a class, so the glyph styles apply", () => {
    for (const kind of ["couldnt_read", "wont_load", "not_as_set"] as const) {
      const { container, unmount } = render(group(kind, { count: "1" }));
      expect(container.querySelector(`.tofix-group-${kind.replaceAll("_", "-")}`)).not.toBeNull();
      unmount();
    }
  });
});
