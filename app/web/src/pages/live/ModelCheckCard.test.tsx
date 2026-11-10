import { cleanup, render, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it } from "vitest";
import type { ModelCheckRow } from "@/api/types";
import { buildModelCheck } from "@/lib/model-check";
import { ModelCheckCard } from "./ModelCheckCard";

afterEach(cleanup);

function lowered(over: Partial<ModelCheckRow>): ModelCheckRow {
  return {
    agent: "judge",
    mismatched_runs: 0,
    params: { setting: "effort", value: "high", expected: "medium" },
    ran: { effort: "medium", mixed: false, model: "claude-opus-5-5" },
    reason_code: "lowered_by_cap",
    runs: 1,
    set: {
      effort: { file: ".claude/agents/judge.md", line: 5, scope: "agent", value: "high" },
      model: null,
    },
    status: "lowered",
    ...over,
  };
}

function show(rows: ModelCheckRow[], compact = false) {
  const view = buildModelCheck({ in_effect_count: 0, rows });
  const router = createMemoryRouter(
    [{ path: "/p/:project/live", element: <ModelCheckCard view={view} compact={compact} /> }],
    { initialEntries: ["/p/builder/live"] },
  );
  render(<RouterProvider router={router} />);
}

describe("See why", () => {
  it("links a finding with a setup item to that item's page, named for the agent", () => {
    show([lowered({ item_id: "agents:judge" })]);
    const link = screen.getByRole("link", { name: "See why for judge" });
    expect(link).toHaveAttribute("href", "#/p/builder/setup/agents/judge");
    expect(link).toHaveTextContent("See why");
  });

  it("links a plugin agent to its own route", () => {
    show([lowered({ agent: "linter", item_id: "agents:lint-kit:linter" })]);
    expect(screen.getByRole("link", { name: "See why for linter" })).toHaveAttribute(
      "href",
      "#/p/builder/setup/agents/lint-kit:linter",
    );
  });

  it("shows nothing for a finding with no item", () => {
    show([lowered({ item_id: null })]);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("judge ran at medium")).toBeInTheDocument();
  });

  it("shows a link on the finding that has one and none on the one that has not", () => {
    show([lowered({ item_id: "agents:judge" }), lowered({ agent: "builder", item_id: null })]);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(1);
    const card = screen.getByRole("region", { name: "Model check" });
    expect(within(card).getAllByRole("heading", { level: 3 })).toHaveLength(2);
  });

  it("is not on the compact Review card", () => {
    show([lowered({ item_id: "agents:judge" })], true);
    expect(screen.queryByRole("link")).toBeNull();
  });
});
