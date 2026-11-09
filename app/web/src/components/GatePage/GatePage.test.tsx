import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { GatePage, states } from "./GatePage";

afterEach(cleanup);

describe("GatePage", () => {
  it("lists every state", () => {
    expect(states).toEqual([
      "default",
      "locked-no-key",
      "locked-code-used",
      "locked-code-expired",
      "locked-server-restarted",
      "first-run-failed",
    ]);
  });

  it("shows the brand and one card inside main", () => {
    render(
      <GatePage brand="Bar Tab">
        <h1>This tab can't reach the dashboard</h1>
      </GatePage>,
    );
    expect(screen.getByText("Bar Tab")).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(main).toContainElement(screen.getByRole("heading", { level: 1 }));
  });

  it("shows the brand as a plain wordmark with no mark", () => {
    const { container } = render(
      <GatePage brand="Bar Tab">
        <h1>Title</h1>
      </GatePage>,
    );
    expect(container.querySelector(".brand-logo")).toBeNull();
  });

  it("puts a notice above the card", () => {
    render(
      <GatePage brand="Bar Tab" notice={<p role="status">Back</p>}>
        <h1>Title</h1>
      </GatePage>,
    );
    const notice = screen.getByRole("status");
    const card = screen.getByRole("heading", { level: 1 });
    expect(notice.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
