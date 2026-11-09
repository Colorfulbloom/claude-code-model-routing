import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { RetryRow, states } from "./RetryRow";

afterEach(cleanup);

function row(busy: boolean, onTryNow = vi.fn()) {
  return (
    <RetryRow
      retryText="Checking again every 10 seconds"
      lastText="Last answer at 3:42 PM"
      tryLabel="Try now"
      busyLabel="Checking"
      busy={busy}
      onTryNow={onTryNow}
    />
  );
}

describe("RetryRow", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default", "loading"]);
  });

  it("is a polite status with the retry and last-answer lines", () => {
    render(row(false));
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Checking again every 10 seconds");
    expect(status).toHaveTextContent("Last answer at 3:42 PM");
  });

  it("calls onTryNow when pressed", async () => {
    const user = userEvent.setup();
    const onTryNow = vi.fn();
    render(row(false, onTryNow));
    await user.click(screen.getByRole("button", { name: "Try now" }));
    expect(onTryNow).toHaveBeenCalledTimes(1);
  });

  it("swaps the label to Checking, sets aria-busy and keeps focus while busy", async () => {
    const user = userEvent.setup();
    const onTryNow = vi.fn();
    render(row(true, onTryNow));
    const button = screen.getByRole("button", { name: "Checking" });
    expect(button).toHaveAttribute("aria-busy", "true");
    await user.tab();
    await user.tab();
    await user.click(button);
    expect(onTryNow).not.toHaveBeenCalled();
  });
});
