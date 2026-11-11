import { describe, expect, it } from "vitest";
import type { SetupItem } from "@/api/types";
import {
  SETUP_PARTS,
  autoPickItem,
  buildSetupRoute,
  hasItem,
  itemId,
  itemKey,
  itemState,
  parseSetupRoute,
  setupItemPath,
  setupItemPathFromId,
  setupPartPath,
  setupPath,
  toFixPath,
  withScopes,
} from "@/lib/setup-routes";
import type { SetupRoute } from "@/lib/setup-routes";

describe("paths", () => {
  it("builds the map, part, item and To fix paths", () => {
    expect(setupPath("builder")).toBe("/p/builder/setup");
    expect(setupPartPath("builder", "agents")).toBe("/p/builder/setup/agents");
    expect(setupItemPath("builder", "agents", "reviewer")).toBe("/p/builder/setup/agents/reviewer");
    expect(toFixPath("builder")).toBe("/p/builder/to-fix");
  });

  it("adds the Switch state as ?scopes=1", () => {
    expect(setupPath("builder", true)).toBe("/p/builder/setup?scopes=1");
    expect(setupPartPath("builder", "mcp", true)).toBe("/p/builder/setup/mcp?scopes=1");
    expect(setupItemPath("builder", "skills", "x", true)).toBe(
      "/p/builder/setup/skills/x?scopes=1",
    );
  });

  it("keeps the colon of a plugin item literal and encodes the rest", () => {
    expect(setupItemPath("builder", "agents", "design:critic")).toBe(
      "/p/builder/setup/agents/design:critic",
    );
    expect(setupItemPath("my proj", "settings", "env.A/B")).toBe(
      "/p/my%20proj/setup/settings/env.A%2FB",
    );
  });

  it("builds an item path from an id", () => {
    expect(setupItemPathFromId("builder", "agents:design:critic")).toBe(
      "/p/builder/setup/agents/design:critic",
    );
    expect(setupItemPathFromId("builder", "nope:x")).toBeNull();
    expect(setupItemPathFromId("builder", "agents:")).toBeNull();
    expect(setupItemPathFromId("builder", "agents")).toBeNull();
  });

  it("splits an id into part and key", () => {
    expect(itemId("agents", "design:critic")).toBe("agents:design:critic");
    expect(itemKey("agents", "agents:design:critic")).toBe("design:critic");
    expect(itemKey("agents", "skills:x")).toBeNull();
  });
});

describe("parse and build round trip", () => {
  const routes: SetupRoute[] = [
    { kind: "map", scopes: false },
    { kind: "map", scopes: true },
    { kind: "part", part: "hooks", scopes: false },
    { kind: "part", part: "output_style", scopes: true },
    { kind: "item", part: "agents", key: "reviewer", scopes: false },
    { kind: "item", part: "agents", key: "design:critic", scopes: true },
    { kind: "item", part: "settings", key: "env.A/B", scopes: false },
    { kind: "item", part: "permissions", key: "allow:Bash(git *)", scopes: false },
    { kind: "edit", part: "settings", key: "effortLevel", scopes: false },
    { kind: "edit", part: "settings", key: "env.A/B", scopes: true },
    { kind: "changes" },
    { kind: "to_fix" },
    { kind: "unknown_part", part: "widgets" },
  ];
  it.each(routes)("round trips %j", (route) => {
    expect(parseSetupRoute(buildSetupRoute("builder", route))).toEqual(route);
  });

  it("round trips every part", () => {
    for (const part of SETUP_PARTS) {
      const route: SetupRoute = { kind: "part", part, scopes: false };
      expect(parseSetupRoute(buildSetupRoute("p", route))).toEqual(route);
    }
  });

  it("reads a relative path and a path with a query", () => {
    expect(parseSetupRoute("setup/agents/design:critic")).toEqual({
      kind: "item",
      part: "agents",
      key: "design:critic",
      scopes: false,
    });
    expect(parseSetupRoute("/p/builder/setup?scopes=1")).toEqual({ kind: "map", scopes: true });
    expect(parseSetupRoute("/p/builder/setup?scopes=0")).toEqual({ kind: "map", scopes: false });
    expect(parseSetupRoute("/p/builder/setup/")).toEqual({ kind: "map", scopes: false });
  });

  it("returns null for paths that are not Setup routes", () => {
    expect(parseSetupRoute("/p/builder/live")).toBeNull();
    expect(parseSetupRoute("/p/builder/setup/agents/a/b")).toBeNull();
    expect(parseSetupRoute("/p/builder/setup/widgets/a/b")).toBeNull();
    expect(parseSetupRoute("/p/builder/to-fix/x")).toBeNull();
    expect(parseSetupRoute("/p/builder/setup/agents/%E0%A4%A")).toBeNull();
    expect(parseSetupRoute("/p/builder/setup/%E0%A4%A")).toBeNull();
  });

  it("detects an unknown part, with or without an item", () => {
    expect(parseSetupRoute("/p/builder/setup/widgets")).toEqual({
      kind: "unknown_part",
      part: "widgets",
    });
    expect(parseSetupRoute("/p/builder/setup/widgets/x")).toEqual({
      kind: "unknown_part",
      part: "widgets",
    });
  });

  it("turns the Switch on and off without touching To fix", () => {
    expect(withScopes({ kind: "part", part: "mcp", scopes: false }, true)).toEqual({
      kind: "part",
      part: "mcp",
      scopes: true,
    });
    expect(withScopes({ kind: "to_fix" }, true)).toEqual({ kind: "to_fix" });
  });
});

describe("vanished items", () => {
  const items = [{ id: "agents:reviewer" }, { id: "agents:design:critic" }];
  it("finds a file item and a plugin item", () => {
    expect(hasItem(items, "agents", "reviewer")).toBe(true);
    expect(hasItem(items, "agents", "design:critic")).toBe(true);
  });
  it("misses an item that is gone or sits under another part", () => {
    expect(hasItem(items, "agents", "gone")).toBe(false);
    expect(hasItem(items, "skills", "reviewer")).toBe(false);
  });
  it("names the state of a route", () => {
    expect(itemState({ kind: "item", part: "agents", key: "reviewer", scopes: false }, items)).toBe(
      "found",
    );
    expect(itemState({ kind: "item", part: "agents", key: "gone", scopes: false }, items)).toBe(
      "vanished",
    );
    expect(itemState({ kind: "part", part: "agents", scopes: false }, items)).toBe("none");
    expect(itemState({ kind: "map", scopes: false }, items)).toBe("none");
    expect(itemState({ kind: "unknown_part", part: "widgets" }, items)).toBe("unknown_part");
  });
});

describe("autoPickItem", () => {
  const item = (id: string, status: SetupItem["status"]) => ({ id, status });

  it("picks the first item that needs a look", () => {
    const items = [item("a", "in_effect"), item("b", "invalid"), item("c", "ignored")];
    expect(autoPickItem(items)?.id).toBe("b");
  });

  it("treats each of the other statuses as needing a look", () => {
    for (const status of ["ignored", "lowered", "invalid", "unknown"] as const) {
      expect(autoPickItem([item("a", "in_effect"), item("b", status)])?.id).toBe("b");
    }
  });

  it("skips in effect, overridden and default", () => {
    const items = [item("a", "in_effect"), item("b", "overridden"), item("c", "default")];
    expect(autoPickItem(items)?.id).toBe("a");
  });

  it("picks an item that has a problem row, even when its status is quiet", () => {
    const items = [item("a", "in_effect"), item("b", "in_effect"), item("c", "default")];
    expect(autoPickItem(items, [{ item_id: "b" }])?.id).toBe("b");
  });

  it("takes the earlier of a status flag and a problem row", () => {
    const items = [item("a", "in_effect"), item("b", "lowered"), item("c", "in_effect")];
    expect(autoPickItem(items, [{ item_id: "c" }])?.id).toBe("b");
    expect(autoPickItem(items, [{ item_id: "a" }])?.id).toBe("a");
  });

  it("ignores problem rows with no item", () => {
    const items = [item("a", "in_effect"), item("b", "default")];
    expect(autoPickItem(items, [{ item_id: null }])?.id).toBe("a");
  });

  it("falls back to the first item when none needs a look", () => {
    const items = [item("a", "overridden"), item("b", "in_effect")];
    expect(autoPickItem(items, [])?.id).toBe("a");
  });

  it("is null for an empty list", () => {
    expect(autoPickItem([])).toBeNull();
    expect(autoPickItem([], [{ item_id: "x" }])).toBeNull();
  });
});
