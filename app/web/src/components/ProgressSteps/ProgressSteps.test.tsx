import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ProgressSteps, states, type ProgressStep } from "./ProgressSteps";

afterEach(cleanup);

const steps: ProgressStep[] = [
  { id: "1", name: "Download Python", state: "done", stateWord: "Done" },
  {
    id: "2",
    name: "Install packages",
    state: "current",
    stateWord: "In progress",
    progress: { percent: 50, text: "41 of 82 MB" },
  },
  { id: "3", name: "Read history", state: "next", stateWord: "Next" },
  { id: "4", name: "Check files", state: "failed", stateWord: "Failed" },
];

describe("ProgressSteps", () => {
  it("lists every state", () => {
    expect(states).toEqual(["done", "in-progress", "next", "failed"]);
  });

  it("is an ordered list with the state word on every step", () => {
    render(<ProgressSteps label="Setup steps" steps={steps} />);
    const list = screen.getByRole("list", { name: "Setup steps" });
    expect(list.tagName).toBe("OL");
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
    for (const word of ["Done", "In progress", "Next", "Failed"]) {
      expect(within(list).getByText(word)).toBeInTheDocument();
    }
  });

  it("gives the current step a labelled progress bar with value text", () => {
    render(<ProgressSteps label="Setup steps" steps={steps} />);
    const bar = screen.getByRole("progressbar", { name: "Install packages" });
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveAttribute("aria-valuetext", "41 of 82 MB");
  });

  it("announces the current step in a polite status region", () => {
    render(<ProgressSteps label="Setup steps" steps={steps} />);
    expect(screen.getByRole("status")).toHaveTextContent("In progress: Install packages");
  });

  it("shows a note on a failed step without a bar", () => {
    render(
      <ProgressSteps
        label="Setup steps"
        steps={[
          {
            id: "1",
            name: "Read",
            state: "failed",
            stateWord: "Failed",
            note: "640 of 1,240 files",
          },
        ]}
      />,
    );
    expect(screen.getByText("640 of 1,240 files")).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("can make the bar's text a polite status of its own", () => {
    render(
      <ProgressSteps
        label="Setup steps"
        steps={[
          {
            id: "1",
            name: "Read",
            state: "current",
            stateWord: "In progress",
            progress: { percent: 0, text: "Trying again since 3:51 PM", live: true },
          },
        ]}
      />,
    );
    const live = screen
      .getAllByRole("status")
      .find((el) => el.textContent === "Trying again since 3:51 PM");
    expect(live).toBeDefined();
  });
});
