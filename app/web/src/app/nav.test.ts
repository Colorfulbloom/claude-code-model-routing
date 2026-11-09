import { describe, expect, it } from "vitest";
import { hidesTabBar, livePath, projectHref, sidebarCurrent, tabCurrent } from "@/app/nav";

describe("nav", () => {
  it("keeps a detail page under its list in the sidebar", () => {
    expect(sidebarCurrent("session")).toBe("sessions");
    expect(sidebarCurrent("agent_edit")).toBe("agents");
    expect(sidebarCurrent("surface_edit")).toBe("setup");
    expect(sidebarCurrent("more")).toBeNull();
    expect(sidebarCurrent("picker")).toBeNull();
  });

  it("makes Review current on every review route and More on Reference", () => {
    for (const page of [
      "summary",
      "sessions",
      "session",
      "agents",
      "agent_new",
      "models",
    ] as const) {
      expect(tabCurrent(page)).toBe("review");
    }
    expect(tabCurrent("decides")).toBe("more");
    expect(tabCurrent("glossary")).toBe("more");
    expect(tabCurrent("more")).toBe("more");
    expect(tabCurrent("surface")).toBe("setup");
    expect(tabCurrent("to_fix")).toBe("tofix");
  });

  it("hides the tab bar on the agent form routes only", () => {
    expect(hidesTabBar("agent_new")).toBe(true);
    expect(hidesTabBar("agent_edit")).toBe(true);
    expect(hidesTabBar("agents")).toBe(false);
  });

  it("builds links, and falls back to the picker with no project", () => {
    expect(projectHref("a b", "/live")).toBe("#/p/a%20b/live");
    expect(projectHref(null, "/live")).toBe("#/");
    expect(livePath("builder")).toBe("/p/builder/live");
    expect(livePath(null)).toBe("/");
  });
});
