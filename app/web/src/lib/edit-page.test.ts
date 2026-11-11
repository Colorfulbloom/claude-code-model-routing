import { describe, expect, it } from "vitest";
import type { SetupItem } from "@/api/types";
import {
  appliesWord,
  asField,
  editPathOf,
  editScopeOf,
  fieldLabel,
  fieldOfItem,
  fieldWord,
  isUntilM7,
  parseWindow,
  requestValue,
  startChoice,
} from "@/lib/edit-page";
import { setupItem, source } from "@/test/setup-fixtures";

const effort = (over: Partial<SetupItem> = {}) => setupItem("settings", "effortLevel", over);

describe("which items have an editor", () => {
  it("gives the four fields an editor and the rest none", () => {
    expect(fieldOfItem(setupItem("settings", "model"))).toBe("model");
    expect(fieldOfItem(setupItem("settings", "effortLevel"))).toBe("effortLevel");
    expect(fieldOfItem(setupItem("settings", "maxEffortLevel"))).toBe("maxEffortLevel");
    expect(fieldOfItem(setupItem("settings", "autoCompactWindow"))).toBe("autoCompactWindow");
    expect(fieldOfItem(setupItem("settings", "env.A"))).toBeNull();
    expect(fieldOfItem(setupItem("agents", "reviewer"))).toBeNull();
  });

  it("gives a read-only item no editor", () => {
    const locked = setupItem("settings", "model", {
      read_only_reason: { code: "managed", command: null, params: {} },
    });
    expect(fieldOfItem(locked)).toBeNull();
  });

  it("names the four items that wait for M7", () => {
    for (const key of [
      "alwaysThinkingEnabled",
      "promptCacheTtl",
      "availableModels",
      "fallbackModel",
    ]) {
      expect(isUntilM7(setupItem("settings", key))).toBe(true);
    }
    expect(isUntilM7(setupItem("settings", "model"))).toBe(false);
    expect(isUntilM7(setupItem("agents", "promptCacheTtl"))).toBe(false);
  });
});

describe("words", () => {
  it("labels each field as the list does", () => {
    expect(fieldLabel("effortLevel")).toBe("Effort");
    expect(fieldLabel("maxEffortLevel")).toBe("Effort cap");
    expect(fieldWord("maxEffortLevel")).toBe("effort cap");
    expect(asField("model")).toBe("model");
    expect(asField("permissions")).toBeNull();
  });

  it("says when a save applies", () => {
    expect(appliesWord("new_session")).toBe("Applies to new sessions");
    expect(appliesWord("new_run")).toBe(appliesWord("picked_up"));
  });
});

describe("where an edit starts", () => {
  it("maps a source scope to an edit scope, and refuses the ones Bar Tab can't write", () => {
    expect(editScopeOf("project_local")).toBe("local");
    expect(editScopeOf("project")).toBe("project");
    expect(editScopeOf("user")).toBe("user");
    for (const scope of ["managed", "command_line", "plugin", "shell"] as const) {
      expect(editScopeOf(scope)).toBeNull();
    }
  });

  it("starts from the winning source's file and value", () => {
    const item = effort({
      winner: 0,
      sources: [source({ scope: "project", value: { text: "high", masked: false } })],
    });
    expect(startChoice(item, "effortLevel")).toEqual({ scope: "project", text: "high" });
  });

  it("starts in Project local with the effective value when the winner can't be written", () => {
    const item = effort({
      winner: 0,
      effective: { value: { text: "max", masked: false }, origin: "set", by_item: null },
      sources: [source({ scope: "shell", value: { text: "max", masked: false } })],
    });
    expect(startChoice(item, "effortLevel")).toEqual({ scope: "local", text: "max" });
  });

  it("falls back to a default by field and never starts from a masked value", () => {
    const masked = effort({
      winner: 0,
      effective: null,
      sources: [source({ scope: "user", value: { text: "hidden", masked: true } })],
    });
    expect(startChoice(masked, "effortLevel").text).toBe("medium");
    expect(startChoice(masked, "maxEffortLevel").text).toBe("max");
    expect(startChoice(masked, "model").text).toBe("");
    expect(startChoice(masked, "autoCompactWindow").text).toBe("1000000");
  });

  it("reads a compact window written as words back to its digits", () => {
    const item = setupItem("settings", "autoCompactWindow", {
      winner: 0,
      sources: [source({ scope: "user", value: { text: "800,000 tokens", masked: false } })],
    });
    expect(startChoice(item, "autoCompactWindow")).toEqual({ scope: "user", text: "800000" });
  });
});

describe("what a request carries", () => {
  it("takes a window only as whole tokens in range", () => {
    expect(parseWindow("100000")).toBe(100_000);
    expect(parseWindow(" 1000000 ")).toBe(1_000_000);
    expect(parseWindow("99999")).toBeNull();
    expect(parseWindow("1000001")).toBeNull();
    expect(parseWindow("1M")).toBeNull();
    expect(parseWindow("")).toBeNull();
  });

  it("sends a number for the window and trimmed text for the rest", () => {
    expect(requestValue("autoCompactWindow", "500000")).toBe(500_000);
    expect(requestValue("autoCompactWindow", "abc")).toBeNull();
    expect(requestValue("effortLevel", " low ")).toBe("low");
    expect(requestValue("model", "   ")).toBeNull();
  });

  it("builds the edit route from an item route and keeps the Switch", () => {
    expect(editPathOf("/p/builder/setup/settings/effortLevel")).toBe(
      "/p/builder/setup/settings/effortLevel/edit",
    );
    expect(editPathOf("/p/builder/setup/settings/effortLevel?scopes=1")).toBe(
      "/p/builder/setup/settings/effortLevel/edit?scopes=1",
    );
  });
});
