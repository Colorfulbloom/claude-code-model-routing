import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { WaitHold, states } from "./WaitHold";

afterEach(cleanup);

describe("WaitHold", () => {
  it("lists every state", () => {
    expect(states).toEqual(["default"]);
  });

  it("shows only the wordmark and a polite status for screen readers", () => {
    render(<WaitHold brand="Bar Tab" status="Checking for another dashboard tab" />);
    expect(screen.getByText("Bar Tab")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Checking for another dashboard tab");
    expect(screen.queryByRole("heading")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("has no status when none is given", () => {
    render(<WaitHold brand="Bar Tab" />);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
