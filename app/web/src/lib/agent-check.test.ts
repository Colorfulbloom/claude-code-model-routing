import { describe, expect, it } from "vitest";
import { agentCheckView } from "@/lib/agent-check";
import { agentItem } from "@/test/tofix";

const lowered = agentItem({
  status: "lowered",
  effective: {
    value: { text: "claude-opus-5-5 / medium", masked: false },
    origin: "cap",
    by_item: "settings:maxEffortLevel",
  },
  check: {
    code: "lowered_by_cap",
    params: {
      setting: "effort",
      value: "high",
      expected: "medium",
      cap_key: "maxEffortLevel",
      cap_value: "medium",
      cap_file: ".claude/settings.local.json",
      cap_line: "3",
      settings: "effort",
    },
  },
});

describe("agentCheckView", () => {
  it("says what ran and what the file sets, with the cap as the reason", () => {
    const view = agentCheckView(lowered);
    expect(view?.status).toEqual({ status: "lowered", label: "Lowered" });
    expect(view?.line).toBe("judge ran at medium, but its file sets high.");
    expect(view?.why).toBe(
      ".claude/agents/judge.md line 5 sets high, but the effort cap in .claude/settings.local.json line 3 lowers it to medium.",
    );
  });

  it("says what a higher layer set when it overrides the file", () => {
    const view = agentCheckView(
      agentItem({
        status: "overridden",
        check: {
          code: "pin_overridden",
          params: {
            setting: "effort",
            value: "high",
            expected: "low",
            by_key: "CLAUDE_CODE_EFFORT_LEVEL",
            by_via: "CLAUDE_CODE_EFFORT_LEVEL",
            by_layer: "env",
            settings: "effort",
          },
        },
      }),
    );
    expect(view?.status.label).toBe("Overridden");
    expect(view?.line).toBe("judge ran at low, but its file sets high.");
    expect(view?.why).toBe("Its file sets high, but CLAUDE_CODE_EFFORT_LEVEL wins with low.");
  });

  it("words a model by its name", () => {
    const view = agentCheckView(
      agentItem({
        status: "overridden",
        check: {
          code: "pin_overridden",
          params: {
            setting: "model",
            value: "claude-opus-5-5",
            expected: "claude-haiku-5-5",
            by_key: "model",
            by_file: ".claude/settings.json",
            by_line: "2",
            by_layer: "project",
            settings: "model",
          },
        },
      }),
    );
    expect(view?.line).toBe("judge ran on Haiku 5.5, but its file sets Opus 5.5.");
  });

  it("gives no callout when the agent runs as its file sets it, or when nothing was judged", () => {
    expect(
      agentCheckView(
        agentItem({
          status: "in_effect",
          check: { code: "in_effect", params: { setting: "effort", value: "high" } },
        }),
      ),
    ).toBeNull();
    expect(agentCheckView(agentItem({ status: "lowered" }))).toBeNull();
    expect(agentCheckView(agentItem({ status: "lowered", check: null }))).toBeNull();
  });

  it("gives no callout for an invalid, ignored or unknown outcome", () => {
    for (const status of ["invalid", "ignored", "unknown"] as const) {
      expect(
        agentCheckView(
          agentItem({ status, check: { code: "pin_invalid", params: { setting: "effort" } } }),
        ),
      ).toBeNull();
    }
  });
});
