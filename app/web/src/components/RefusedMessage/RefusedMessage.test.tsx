import { cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { EDIT_REFUSAL_CODES } from "@/api/edit";
import { Mark, MessageFrame } from "./MessageFrame";
import { RefusedMessage, refusalSentence, states } from "./RefusedMessage";

afterEach(cleanup);

describe("RefusedMessage", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "changed",
      "changed-ours",
      "changed-no-keys",
      "link-outside",
      "preview-mismatch",
      "not-undone",
    ]);
  });

  it("leads with Not saved. and then the code's sentence", () => {
    const { container } = render(<RefusedMessage code="link_outside" file="settings.json" />);
    expect(container.querySelector("p")).toHaveTextContent(
      "Not saved. settings.json links to a file outside your home folder and this project, so Bar Tab wrote nothing.",
    );
  });

  it("leads with Not confirmed. when the page got no answer, and names a locked or refused page", () => {
    const { container, rerender } = render(<RefusedMessage code="network" file="settings.json" />);
    expect(container.querySelector("p")).toHaveTextContent("Not confirmed.");
    rerender(<RefusedMessage code="network" file="settings.json" undo />);
    expect(container.querySelector("p")).toHaveTextContent("Undo not confirmed.");
    rerender(<RefusedMessage code="server" file="settings.json" />);
    expect(container.querySelector("p")).toHaveTextContent("Not confirmed.");
    rerender(<RefusedMessage code="locked" file="settings.json" />);
    expect(container.querySelector("p")).toHaveTextContent("Not saved.");
    rerender(<RefusedMessage code="refused" file="settings.json" undo />);
    expect(container.querySelector("p")).toHaveTextContent("Not undone.");
    for (const code of ["network", "server", "locked", "refused"] as const) {
      expect(refusalSentence(code, "settings.json")).not.toBe("");
    }
  });

  it("leads with Not undone. for an undo", () => {
    render(<RefusedMessage code="not_undoable" file="settings.json" undo />);
    expect(screen.getByText("Not undone.")).toBeInTheDocument();
    expect(screen.queryByText("Not saved.")).toBeNull();
  });

  it("names the keys another program changed, and says so when one is the edited setting", () => {
    render(
      <RefusedMessage
        code="changed"
        file="settings.local.json"
        changedKeys={["permissions.allow", "env.LEVEL"]}
        editedKeyChanged
      />,
    );
    expect(
      screen.getByText(
        "Another program changed permissions.allow, env.LEVEL. The preview below now shows the new file, so check it and save again. That includes the setting you're changing.",
      ),
    ).toBeInTheDocument();
  });

  it("falls back to the line with no key names when it has none", () => {
    render(<RefusedMessage code="changed" file="settings.local.json" />);
    expect(
      screen.getByText(
        "The preview below now shows the file as it is, so check it and save again.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the changed-keys line only for a changed file", () => {
    render(
      <RefusedMessage code="preview_mismatch" file="settings.local.json" changedKeys={["a"]} />,
    );
    expect(screen.queryByText(/Another program changed/)).toBeNull();
  });

  it("takes focus from code, with tabindex -1 and no alert role", () => {
    const ref = createRef<HTMLDivElement>();
    render(<RefusedMessage code="changed" file="f.json" messageRef={ref} />);
    expect(ref.current).toHaveAttribute("tabindex", "-1");
    ref.current?.focus();
    expect(document.activeElement).toBe(ref.current);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("hides its glyph from assistive tech", () => {
    const { container } = render(<RefusedMessage code="changed" file="f.json" />);
    expect(container.querySelector(".message-mark")).toHaveAttribute("aria-hidden", "true");
  });
});

describe("refusalSentence", () => {
  it("has a sentence for every refusal code, and fills the file where it has a slot", () => {
    for (const code of EDIT_REFUSAL_CODES) {
      const sentence = refusalSentence(code, "settings.local.json");
      expect(sentence.length, code).toBeGreaterThan(10);
      expect(sentence, code).not.toMatch(/[{}]/);
    }
    expect(refusalSentence("changed", "a.json")).toContain("a.json");
  });
});

describe("MessageFrame", () => {
  it("draws each tone with its own edge class and an optional focus target", () => {
    const { container } = render(
      <>
        <MessageFrame tone="error">
          <p>
            <Mark tone="error" />
            Error
          </p>
        </MessageFrame>
        <MessageFrame tone="warning" role="status">
          <p>Warning</p>
        </MessageFrame>
        <MessageFrame tone="ok" focusable>
          <p>Fine</p>
        </MessageFrame>
      </>,
    );
    expect(container.querySelector(".message-frame-error")).not.toBeNull();
    expect(container.querySelector(".message-frame-warning")).toHaveAttribute("role", "status");
    expect(container.querySelector(".message-frame-ok")).toHaveAttribute("tabindex", "-1");
  });
});
