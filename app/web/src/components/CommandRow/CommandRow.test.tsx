import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { CommandRow, states } from "./CommandRow";

afterEach(cleanup);

function row(props: { primary?: boolean; copied?: boolean } = {}) {
  return (
    <CommandRow
      command="/bartab"
      copyLabel="Copy command"
      copiedLabel="Copied to clipboard"
      {...props}
    />
  );
}

describe("CommandRow", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "copied"]);
  });

  it("shows the command in code and a Copy button", () => {
    render(row());
    expect(screen.getByText("/bartab").tagName).toBe("CODE");
    expect(screen.getByRole("button", { name: "Copy command" })).toHaveClass("button-secondary");
  });

  it("makes Copy primary on request", () => {
    render(row({ primary: true }));
    expect(screen.getByRole("button", { name: "Copy command" })).toHaveClass("button-primary");
  });

  it("copies the command and says so in a polite status", async () => {
    const user = userEvent.setup();
    render(row());
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    await user.click(screen.getByRole("button", { name: "Copy command" }));
    expect(await screen.findByText("Copied to clipboard")).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe("/bartab");
  });

  it("shows the copied status when forced", () => {
    render(row({ copied: true }));
    expect(screen.getByRole("status")).toHaveTextContent("Copied to clipboard");
  });
});
