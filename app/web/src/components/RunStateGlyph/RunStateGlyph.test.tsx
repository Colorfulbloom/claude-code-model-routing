import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { RunStateGlyph, states } from "./RunStateGlyph";

afterEach(cleanup);

describe("RunStateGlyph", () => {
  it("renders the word for every state", () => {
    for (const state of states) {
      const { unmount } = render(<RunStateGlyph state={state}>Word {state}</RunStateGlyph>);
      expect(screen.getByText(`Word ${state}`)).toHaveClass(`run-state-${state.replace("_", "-")}`);
      unmount();
    }
  });

  it("lists the Live states beside the first run states", () => {
    expect(states).toEqual(expect.arrayContaining(["finished", "not_started", "ended"]));
  });
});
