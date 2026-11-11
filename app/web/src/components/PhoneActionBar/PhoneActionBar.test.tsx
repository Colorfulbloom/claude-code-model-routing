import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Button } from "../Button/Button";
import { PhoneActionBar, states } from "./PhoneActionBar";

afterEach(cleanup);

describe("PhoneActionBar", () => {
  it("lists its sheet states", () => {
    expect(states).toEqual(["default", "with-link", "button-only"]);
  });

  it("shows the summary above the primary button", () => {
    const { container } = render(
      <PhoneActionBar summary="settings.local.json, xhigh to medium">
        <Button variant="primary">Save to Project local</Button>
      </PhoneActionBar>,
    );
    expect(container.querySelector(".phone-action-bar-summary")).toHaveTextContent(
      "settings.local.json, xhigh to medium",
    );
    expect(screen.getByRole("button", { name: "Save to Project local" })).toBeInTheDocument();
  });

  it("shows a link beside the summary", () => {
    render(
      <PhoneActionBar summary="planner.md" aside={<a href="#file">Show the file</a>}>
        <Button variant="primary">Create planner.md</Button>
      </PhoneActionBar>,
    );
    expect(screen.getByRole("link", { name: "Show the file" })).toHaveAttribute("href", "#file");
  });

  it("holds just the button when it has no note", () => {
    const { container } = render(
      <PhoneActionBar>
        <Button variant="primary">Save</Button>
      </PhoneActionBar>,
    );
    expect(container.querySelector(".phone-action-bar-note")).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
  });
});
