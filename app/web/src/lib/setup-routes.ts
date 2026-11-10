/*
 * The Setup routes, as pure functions. A route is the map, one part, one item, or To fix, plus the
 * Switch state in `?scopes=1`.
 *
 *   /p/<project>/setup                    the map
 *   /p/<project>/setup/<part>             one part, with its list
 *   /p/<project>/setup/<part>/<item key>  one item in its inspector
 *   /p/<project>/to-fix                   the To fix page
 *
 * An item id is `<part>:<key>`, and the route carries the key alone, because the part is already
 * in the path. A plugin item is `<part>:<plugin>:<name>`, so its route is
 * `setup/agents/<plugin>:<name>`. The colon stays literal in the path, and every other reserved
 * character is encoded.
 */
import type { ProblemRow, SetupItem, SetupPart } from "@/api/types";

/** The ten parts, in the map's order. */
export const SETUP_PARTS: readonly SetupPart[] = [
  "settings",
  "agents",
  "instructions",
  "rules",
  "skills",
  "hooks",
  "permissions",
  "mcp",
  "plugins",
  "output_style",
];

export function isSetupPart(value: string): value is SetupPart {
  return (SETUP_PARTS as readonly string[]).includes(value);
}

export type SetupRoute =
  | { kind: "map"; scopes: boolean }
  | { kind: "part"; part: SetupPart; scopes: boolean }
  | { kind: "item"; part: SetupPart; key: string; scopes: boolean }
  | { kind: "to_fix" }
  /** A part name the server does not know, kept so the page can say so. */
  | { kind: "unknown_part"; part: string };

const SCOPES_QUERY = "?scopes=1";

function projectBase(project: string): string {
  return `/p/${encodeURIComponent(project)}`;
}

/** One path segment, with the colon kept literal so a plugin item reads `<plugin>:<name>`. */
function segment(value: string): string {
  return encodeURIComponent(value).replaceAll("%3A", ":");
}

/** The id of an item from its part and route key. */
export function itemId(part: SetupPart, key: string): string {
  return `${part}:${key}`;
}

/** The route key of an item id, or null when the id belongs to another part. */
export function itemKey(part: SetupPart, id: string): string | null {
  const prefix = `${part}:`;
  return id.startsWith(prefix) && id.length > prefix.length ? id.slice(prefix.length) : null;
}

/** `/p/<project>/setup`, with the Switch state when it is on. */
export function setupPath(project: string, scopes = false): string {
  return `${projectBase(project)}/setup${scopes ? SCOPES_QUERY : ""}`;
}

/** `/p/<project>/setup/<part>`. */
export function setupPartPath(project: string, part: SetupPart, scopes = false): string {
  return `${projectBase(project)}/setup/${part}${scopes ? SCOPES_QUERY : ""}`;
}

/** `/p/<project>/setup/<part>/<key>`. The key is the item id without its `<part>:` prefix. */
export function setupItemPath(
  project: string,
  part: SetupPart,
  key: string,
  scopes = false,
): string {
  return `${projectBase(project)}/setup/${part}/${segment(key)}${scopes ? SCOPES_QUERY : ""}`;
}

/** The path of an item from its id, or null when the id names no known part. */
export function setupItemPathFromId(project: string, id: string, scopes = false): string | null {
  const colon = id.indexOf(":");
  if (colon < 1) return null;
  const part = id.slice(0, colon);
  if (!isSetupPart(part)) return null;
  const key = itemKey(part, id);
  return key === null ? null : setupItemPath(project, part, key, scopes);
}

/** `/p/<project>/to-fix`. */
export function toFixPath(project: string): string {
  return `${projectBase(project)}/to-fix`;
}

/** The path for a parsed route. */
export function buildSetupRoute(project: string, route: SetupRoute): string {
  switch (route.kind) {
    case "map":
      return setupPath(project, route.scopes);
    case "part":
      return setupPartPath(project, route.part, route.scopes);
    case "item":
      return setupItemPath(project, route.part, route.key, route.scopes);
    case "to_fix":
      return toFixPath(project);
    case "unknown_part":
      return `${projectBase(project)}/setup/${segment(route.part)}`;
  }
}

/**
 * Reads a Setup path, with or without its `/p/<project>` prefix and its query. Returns null for
 * a path that is not a Setup route. A part name the server does not know comes back as
 * `unknown_part`. The Switch is on only for exactly `scopes=1`.
 */
export function parseSetupRoute(path: string): SetupRoute | null {
  const [pathname = "", query = ""] = path.split("?", 2);
  const segs = pathname.split("/").filter((s) => s !== "");
  const tail = segs[0] === "p" && segs.length >= 3 ? segs.slice(2) : segs;
  const scopes = new URLSearchParams(query).get("scopes") === "1";
  const [head, part, ...rest] = tail;
  if (head === "to-fix" && tail.length === 1) return { kind: "to_fix" };
  if (head !== "setup") return null;
  if (part === undefined) return { kind: "map", scopes };
  const name = safeDecode(part);
  if (name === null) return null;
  if (!isSetupPart(name)) return rest.length <= 1 ? { kind: "unknown_part", part: name } : null;
  if (rest.length === 0) return { kind: "part", part: name, scopes };
  if (rest.length > 1) return null;
  const key = safeDecode(rest[0] ?? "");
  if (key === null || key === "") return null;
  return { kind: "item", part: name, key, scopes };
}

function safeDecode(value: string): string | null {
  try {
    return decodeURIComponent(value);
  } catch {
    return null;
  }
}

/** The same route with the Switch turned on or off. To fix has no Switch and comes back as is. */
export function withScopes(route: SetupRoute, scopes: boolean): SetupRoute {
  if (route.kind === "to_fix" || route.kind === "unknown_part") return route;
  return { ...route, scopes };
}

/** True when the part's answer holds the item. The vanished-item check (need 27). */
export function hasItem(
  items: readonly Pick<SetupItem, "id">[],
  part: SetupPart,
  key: string,
): boolean {
  const id = itemId(part, key);
  return items.some((item) => item.id === id);
}

/**
 * Whether a route's item is still on the page: `found`, or `vanished` when the part's answer
 * has no item with that key. A route with no item is `none`, and an unknown part is
 * `unknown_part`. Call it only with a good answer for the route's part, not while loading or
 * after an error, or a slow answer reads as a vanished item.
 */
export function itemState(
  route: SetupRoute,
  items: readonly Pick<SetupItem, "id">[],
): "none" | "found" | "vanished" | "unknown_part" {
  if (route.kind === "unknown_part") return "unknown_part";
  if (route.kind !== "item") return "none";
  return hasItem(items, route.part, route.key) ? "found" : "vanished";
}

/** The statuses that need no look: nothing is wrong and nothing is hidden. */
const QUIET_STATUSES: ReadonlySet<SetupItem["status"]> = new Set([
  "in_effect",
  "overridden",
  "default",
]);

/**
 * The first item that needs a look: a status that is not in effect, overridden or default, or any
 * problem row naming it. Else the first item, else null for an empty list. The page calls it at
 * 1440 with no item in the URL (owner decision 3).
 */
export function autoPickItem<T extends Pick<SetupItem, "id" | "status">>(
  items: readonly T[],
  problems: readonly Pick<ProblemRow, "item_id">[] = [],
): T | null {
  const flagged = new Set<string>();
  for (const row of problems) if (row.item_id !== null) flagged.add(row.item_id);
  const needsLook = items.find((item) => !QUIET_STATUSES.has(item.status) || flagged.has(item.id));
  return needsLook ?? items[0] ?? null;
}
