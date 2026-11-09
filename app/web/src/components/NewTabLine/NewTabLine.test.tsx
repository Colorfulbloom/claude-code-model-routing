import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { NewTabLine, states } from "./NewTabLine";

afterEach(cleanup);

describe("NewTabLine", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default"]);
  });

  it("is a polite status that reads the sentence and hides the check mark", () => {
    render(<NewTabLine>Your other tab is open again on Agents, builder.</NewTabLine>);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Your other tab is open again on Agents, builder.");
    expect(status.querySelector("[aria-hidden=true]")).toHaveTextContent("✓");
    expect(status).toHaveAccessibleName("");
  });
});
