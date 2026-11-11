import { describe, expect, it, vi } from "vitest";
import { pageName, parentPageName, parseRoute, routeForProject } from "@/app/routes";

describe("parseRoute", () => {
  it.each([
    ["/", "picker", null],
    ["/more", "more", null],
    ["/reference/decides", "decides", null],
    ["/reference/glossary", "glossary", null],
    ["/p/a/live", "live", "a"],
    ["/p/a/review/summary", "summary", "a"],
    ["/p/a/review/sessions", "sessions", "a"],
    ["/p/a/review/sessions/s1", "session", "a"],
    ["/p/a/review/agents", "agents", "a"],
    ["/p/a/review/agents/new", "agent_new", "a"],
    ["/p/a/review/agents/builder/edit", "agent_edit", "a"],
    ["/p/a/review/models", "models", "a"],
    ["/p/a/setup", "setup", "a"],
    ["/p/a/setup/settings", "surface", "a"],
    ["/p/a/setup/settings/effort", "surface", "a"],
    ["/p/a/setup/settings/effort/edit", "surface_edit", "a"],
    ["/p/a/setup/changes", "changes", "a"],
    ["/p/a/to-fix", "to_fix", "a"],
  ])("%s", (path, page, project) => {
    const parsed = parseRoute(path);
    expect(parsed?.page).toBe(page);
    expect(parsed?.project).toBe(project);
  });

  it("returns null for unknown routes", () => {
    expect(parseRoute("/nope")).toBeNull();
    expect(parseRoute("/p/a")).toBeNull();
    expect(parseRoute("/reference/other")).toBeNull();
    expect(parseRoute("/reference")).toBeNull();
  });

  it("reads the setting and rule segments of How Claude Code decides, with no project", () => {
    expect(parseRoute("/reference/decides/effortLevel")).toEqual({
      page: "decides",
      project: null,
      rest: "",
      setting: "effortLevel",
    });
    expect(
      parseRoute(
        "/reference/decides/modelSettings.maxEffortLevel/model-settings-max-effort-values",
      ),
    ).toEqual({
      page: "decides",
      project: null,
      rest: "",
      setting: "modelSettings.maxEffortLevel",
      rule: "model-settings-max-effort-values",
    });
    expect(parseRoute("/reference/decides/a/b?q=cache&due=1")?.rule).toBe("b");
    expect(parseRoute("/reference/decides/a/b/c")).toBeNull();
  });

  it("reads the term id of the Glossary, including list item targets", () => {
    expect(parseRoute("/reference/glossary/cache-write")?.id).toBe("cache-write");
    expect(parseRoute("/reference/glossary/status-in_effect")?.id).toBe("status-in_effect");
    expect(
      parseRoute("/reference/glossary/scope-managed?from=%2Fp%2Fa%2Flive&help=live.cache")?.id,
    ).toBe("scope-managed");
    expect(parseRoute("/reference/glossary/a/b")).toBeNull();
  });

  it("keeps the text of a malformed escape", () => {
    expect(parseRoute("/reference/glossary/%E0%A4%A")?.id).toBe("%E0%A4%A");
  });

  it("names a detail page by its parent's nav name", () => {
    expect(parentPageName("session")).toBe("Sessions");
    expect(parentPageName("agent_edit")).toBe("Agents");
    expect(parentPageName("agent_new")).toBe("Agents");
    expect(parentPageName("surface")).toBe("Your setup");
    expect(parentPageName("surface_edit")).toBe("Your setup");
    expect(parentPageName("live")).toBe("Live");
    expect(parentPageName("to_fix")).toBe("To fix");
  });

  it("keeps a Reference route as it is when the project changes", () => {
    const no = vi.fn(() => false);
    expect(routeForProject("/reference/decides/effortLevel/x", "b", no)).toBe(
      "/reference/decides/effortLevel/x",
    );
  });

  it("ignores the query", () => {
    expect(parseRoute("/p/a/review/summary?range=30d")?.page).toBe("summary");
  });
});

describe("pageName", () => {
  it("names a page from the string deck", () => {
    expect(pageName("live")).toBe("Live");
    expect(pageName("setup")).toBe("Your setup");
  });
});

describe("routeForProject", () => {
  const yes = vi.fn(() => true);
  const no = vi.fn(() => false);

  it("keeps a list page under the new project", () => {
    expect(routeForProject("/p/a/review/agents", "b", no)).toBe("/p/b/review/agents");
    expect(routeForProject("/p/a/live", "b", no)).toBe("/p/b/live");
    expect(routeForProject("/p/a/to-fix", "b", no)).toBe("/p/b/to-fix");
  });

  it("keeps a new-agent form", () => {
    expect(routeForProject("/p/a/review/agents/new", "b", no)).toBe("/p/b/review/agents/new");
  });

  it("keeps a detail page when the item exists in the new project", () => {
    expect(routeForProject("/p/a/review/sessions/s1", "b", yes)).toBe("/p/b/review/sessions/s1");
    expect(yes).toHaveBeenCalledWith({ kind: "session", id: "s1" });
  });

  it("drops a session to the sessions list when it is missing", () => {
    expect(routeForProject("/p/a/review/sessions/s1", "b", no)).toBe("/p/b/review/sessions");
  });

  it("drops an agent edit to the agents list when it is missing", () => {
    expect(routeForProject("/p/a/review/agents/builder/edit", "b", no)).toBe("/p/b/review/agents");
    expect(routeForProject("/p/a/review/agents/builder/edit", "b", yes)).toBe(
      "/p/b/review/agents/builder/edit",
    );
  });

  it("drops a surface page and its edit rail to Your setup when missing", () => {
    expect(routeForProject("/p/a/setup/settings/effort", "b", no)).toBe("/p/b/setup");
    expect(routeForProject("/p/a/setup/settings/effort/edit", "b", no)).toBe("/p/b/setup");
    expect(routeForProject("/p/a/setup/settings/effort/edit", "b", yes)).toBe(
      "/p/b/setup/settings/effort/edit",
    );
  });

  it("leaves routes with no project alone", () => {
    expect(routeForProject("/more", "b", no)).toBe("/more");
    expect(routeForProject("/reference/glossary", "b", no)).toBe("/reference/glossary");
    expect(routeForProject("/", "b", no)).toBe("/");
  });

  it("encodes the project key", () => {
    expect(routeForProject("/p/a/live", "my proj", no)).toBe("/p/my%20proj/live");
  });
});
