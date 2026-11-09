import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RaisedFinding, states } from "./RaisedFinding";

afterEach(cleanup);

describe("RaisedFinding", () => {
  it("renders every state with its words", () => {
    for (const variant of states) {
      const { unmount } = render(
        <RaisedFinding variant={variant} title="Heading">
          Body for {variant}
        </RaisedFinding>,
      );
      expect(screen.getByRole("heading", { level: 3, name: "Heading" })).toBeInTheDocument();
      expect(screen.getByText(`Body for ${variant}`)).toBeInTheDocument();
      unmount();
    }
  });

  it("announces Saved and Overwritten politely and Preview failed as an alert", () => {
    render(
      <>
        <RaisedFinding variant="saved">Saved.</RaisedFinding>
        <RaisedFinding variant="overwritten">Changed after save.</RaisedFinding>
        <RaisedFinding variant="error">Preview failed.</RaisedFinding>
      </>,
    );
    expect(screen.getAllByRole("status")).toHaveLength(2);
    expect(screen.getByRole("alert")).toHaveTextContent("Preview failed.");
  });

  it("hides its glyph mark from assistive tech and keeps actions", () => {
    const { container } = render(
      <RaisedFinding variant="warning" actions={<button>Review changes</button>}>
        Check first.
      </RaisedFinding>,
    );
    expect(container.querySelector(".raised-finding-mark")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByRole("button", { name: "Review changes" })).toBeInTheDocument();
  });
});
