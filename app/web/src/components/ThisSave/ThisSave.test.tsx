import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { samplePreview } from "@/sheet/edit-samples";
import { ThisSave, states, warningSentence } from "./ThisSave";

afterEach(cleanup);

/** The text of a dl row, by its term. */
function rowFor(term: string): HTMLElement {
  const dt = screen.getByText(term, { selector: "dt" });
  const row = dt.closest("div");
  if (row === null) throw new Error(`No row for ${term}`);
  return row;
}

describe("ThisSave", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual([
      "default",
      "user-link",
      "model",
      "updating",
      "warnings",
      "new-value",
      "phone",
    ]);
  });

  it("is a region named This save, with a help button", () => {
    render(<ThisSave preview={samplePreview()} />);
    const region = screen.getByRole("region", { name: "This save" });
    expect(within(region).getByRole("button", { name: "About This save" })).toBeInTheDocument();
  });

  it("shows File, Set to and Runs at from the preview", () => {
    render(<ThisSave preview={samplePreview()} applies="Applies to new sessions" />);
    expect(rowFor("File")).toHaveTextContent("Project local");
    expect(rowFor("File")).toHaveTextContent(
      "~/work/tidewater-reporting/.claude/settings.local.json",
    );
    expect(rowFor("Set to")).toHaveTextContent("xhigh");
    expect(rowFor("Set to")).toHaveTextContent("medium");
    expect(rowFor("Runs at")).toHaveTextContent("high");
    expect(rowFor("Runs at")).toHaveTextContent("Applies to new sessions");
  });

  it("gives every Runs at status a glyph and a word", () => {
    const { container } = render(<ThisSave preview={samplePreview()} />);
    const chips = [...container.querySelectorAll(".status-chip")];
    expect(chips.map((c) => [c.getAttribute("data-glyph"), c.textContent])).toEqual([
      ["lowered", "Lowered"],
      ["in-effect", "In effect"],
    ]);
  });

  it("reads the arrow as the word to for a screen reader", () => {
    const { container } = render(<ThisSave preview={samplePreview()} />);
    const arrows = container.querySelectorAll(".this-save-arrow");
    expect(arrows).toHaveLength(2);
    for (const arrow of arrows) {
      expect(arrow).toHaveAttribute("aria-hidden", "true");
      expect(arrow.nextElementSibling).toHaveTextContent("to");
    }
  });

  it("says Runs on and names the model for the model field", () => {
    render(<ThisSave preview={samplePreview({ model: true })} runsOn />);
    expect(screen.getByText("Runs on", { selector: "dt" })).toBeInTheDocument();
    expect(screen.queryByText("Runs at", { selector: "dt" })).toBeNull();
  });

  it("shows the link note with the real path in the mono face", () => {
    render(<ThisSave preview={samplePreview({ scope: "user" })} />);
    const file = rowFor("File");
    expect(file).toHaveTextContent("This file is a link, so saving changes");
    expect(within(file).getByText("~/dotfiles/claude/settings.json")).toHaveClass("this-save-real");
    expect(file).toHaveTextContent("The link stays as it is.");
  });

  it("shows no link note for a plain file", () => {
    const { container } = render(<ThisSave preview={samplePreview()} />);
    expect(container.querySelector(".this-save-link")).toBeNull();
  });

  it("draws the diff at its real line numbers and says when Bar Tab read the file", () => {
    const { container } = render(<ThisSave preview={samplePreview()} />);
    expect(container.querySelectorAll(".diff-line:not(.diff-fold)")).toHaveLength(4);
    expect(container.querySelector(".diff-del .diff-ln")).toHaveTextContent("3");
    expect(screen.getByText("Bar Tab read this file at 6:41:12 PM.")).toBeInTheDocument();
  });

  it("marks itself busy and says Updating while a preview is pending", () => {
    render(<ThisSave preview={samplePreview()} updating />);
    expect(screen.getByRole("region", { name: "This save" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Updating")).toBeInTheDocument();
  });

  it("is not busy and says nothing about updating when the preview is current", () => {
    render(<ThisSave preview={samplePreview()} />);
    expect(screen.getByRole("region", { name: "This save" })).not.toHaveAttribute("aria-busy");
    expect(screen.queryByText("Updating")).toBeNull();
  });

  it("words each warning and counts the other projects a user save reaches", () => {
    render(
      <ThisSave
        preview={samplePreview({
          reaches: 2,
          warnings: [
            { code: "wont_win", params: { scope: "local" } },
            { code: "config_change_hook", params: {} },
            { code: "shared_repo", params: { file: "settings.json" } },
          ],
        })}
      />,
    );
    expect(
      screen.getByText(
        "Project local sets this too and wins, so this save won't change what runs here.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(/Your setup has a ConfigChange hook/)).toBeInTheDocument();
    expect(screen.getByText(/Git tracks settings.json in this project/)).toBeInTheDocument();
    expect(screen.getByText("2 other projects read this file too.")).toBeInTheDocument();
  });

  it("uses the singular for one other project", () => {
    render(<ThisSave preview={samplePreview({ reaches: 1 })} />);
    expect(screen.getByText("1 other project reads this file too.")).toBeInTheDocument();
  });

  it("reads a key that was not set before as Nothing set here", () => {
    render(<ThisSave preview={samplePreview({ newValue: true })} />);
    expect(rowFor("Set to")).toHaveTextContent("Nothing set here");
  });
});

describe("warningSentence", () => {
  it("keeps a scope word the page sent that is not a scope code", () => {
    expect(warningSentence({ code: "wont_win", params: { scope: "Managed" } })).toBe(
      "Managed sets this too and wins, so this save won't change what runs here.",
    );
  });
});
