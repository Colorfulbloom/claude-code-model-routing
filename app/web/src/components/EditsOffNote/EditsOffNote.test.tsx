import { cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { Button } from "../Button/Button";
import { EditsOffNote, states } from "./EditsOffNote";

afterEach(cleanup);

const CMD = "/bartab-preview --allow-edits";

describe("EditsOffNote", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "reason",
      "reason-demo",
      "reason-folder",
      "history",
      "route",
      "route-focus",
      "route-agent",
    ]);
  });

  it("names the command in a code span, and is the reason a disabled Edit button points to", () => {
    const { container } = render(
      <>
        <Button variant="primary" disabled describedBy="why">
          Edit
        </Button>
        <EditsOffNote id="why" kind="reason" command={CMD} />
      </>,
    );
    const button = screen.getByRole("button", { name: "Edit" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAttribute("aria-describedby", "why");
    expect(container.querySelector("#why")).toHaveTextContent(
      `Editing is off. Start Bar Tab with ${CMD} to turn it on.`,
    );
    expect(container.querySelector("#why code")).toHaveTextContent(CMD);
  });

  it("names no command when edits can't be turned on here", () => {
    const { container, rerender } = render(<EditsOffNote kind="demo" />);
    expect(container).toHaveTextContent("This run uses sample data, so Bar Tab doesn't edit it.");
    expect(container.querySelector("code")).toBeNull();
    rerender(<EditsOffNote kind="folder" path="~/work/tidewater-reporting" />);
    expect(container).toHaveTextContent(
      "Bar Tab can't find ~/work/tidewater-reporting, so it can't edit this project.",
    );
    expect(container.querySelector("code")).toBeNull();
  });

  it("names the agent in a one-line note that takes focus from code", () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(<EditsOffNote kind="agent" name="builder" noteRef={ref} />);
    expect(container).toHaveTextContent(
      "Bar Tab can't edit agents yet, so builder opened without its editor.",
    );
    expect(ref.current).toHaveAttribute("tabindex", "-1");
    ref.current?.focus();
    expect(document.activeElement).toBe(ref.current);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the Changes note with a lock that screen readers skip", () => {
    const { container } = render(<EditsOffNote kind="history" command={CMD} />);
    expect(container).toHaveTextContent(
      `Undo needs editing on. Start Bar Tab with ${CMD} to turn it on.`,
    );
    expect(container.querySelector(".edits-off-lock")).toHaveAttribute("aria-hidden", "true");
  });

  it("shows the route note with the item and the command, and takes focus from code", () => {
    const ref = createRef<HTMLDivElement>();
    const { container } = render(
      <EditsOffNote kind="route" command={CMD} item="Effort" noteRef={ref} id="route-note" />,
    );
    expect(container).toHaveTextContent(
      `Editing is off, so Effort opened without its editor. Start Bar Tab with ${CMD} to edit it.`,
    );
    expect(ref.current).toHaveAttribute("tabindex", "-1");
    ref.current?.focus();
    expect(document.activeElement).toBe(ref.current);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("uses the command it is given and never a baked-in one", () => {
    const { container } = render(<EditsOffNote kind="reason" command="/other --allow-edits" />);
    expect(container.querySelector("code")).toHaveTextContent("/other --allow-edits");
    expect(container).not.toHaveTextContent("/bartab-preview");
  });
});
