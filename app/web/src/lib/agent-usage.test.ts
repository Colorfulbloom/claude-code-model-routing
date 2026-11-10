/*
 * The Review link in an agent's footer: a plugin or managed agent keeps it only when the Agents
 * answer has a row for it (it ran). Other agents and a loading answer keep it.
 */
import { describe, expect, it } from "vitest";
import type { SetupItem } from "@/api/types";
import { showReviewLink } from "@/lib/agent-usage";
import { agentRow, agentsAnswer } from "@/test/review-tables";

const plugin: Pick<SetupItem, "id" | "scope"> = { id: "agents:lint-kit:linter", scope: "plugin" };
const managed: Pick<SetupItem, "id" | "scope"> = { id: "agents:policy", scope: "managed" };
const project: Pick<SetupItem, "id" | "scope"> = { id: "agents:builder", scope: "project" };

const withRuns = (item: Pick<SetupItem, "id">) =>
  agentsAnswer({ ran: [agentRow({ item_id: item.id, runs: 2 })] });
const noRuns = agentsAnswer({ ran: [agentRow({ item_id: "agents:other" })] });

describe("showReviewLink", () => {
  it("hides the link for a plugin agent with no runs", () => {
    expect(showReviewLink(plugin, noRuns)).toBe(false);
  });

  it("keeps the link for a plugin agent with runs", () => {
    expect(showReviewLink(plugin, withRuns(plugin))).toBe(true);
  });

  it("hides the link for a managed agent with no runs", () => {
    expect(showReviewLink(managed, noRuns)).toBe(false);
  });

  it("keeps the link for a managed agent with runs", () => {
    expect(showReviewLink(managed, withRuns(managed))).toBe(true);
  });

  it("keeps the link for other agents with no runs, and while the answer loads", () => {
    expect(showReviewLink(project, noRuns)).toBe(true);
    expect(showReviewLink(plugin, undefined)).toBe(true);
  });
});
