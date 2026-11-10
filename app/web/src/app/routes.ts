/*
 * The route table's pure parts. Page ids, page names from the string deck, a parser for hash
 * paths, and routeForProject for the project swap. Routes follow plan-a section 2.
 */
import { t } from "@/strings/t";

export type PageId =
  | "picker"
  | "live"
  | "summary"
  | "sessions"
  | "session"
  | "agents"
  | "agent_new"
  | "agent_edit"
  | "models"
  | "setup"
  | "surface"
  | "surface_edit"
  | "to_fix"
  | "decides"
  | "glossary"
  | "more";

/** The page name the reader sees, used for the h1, the title and the status line. */
export function pageName(id: PageId): string {
  switch (id) {
    case "picker":
      return t("pk_h");
    case "live":
      return t("nav_live");
    case "summary":
      return t("nav_summary");
    case "sessions":
      return t("nav_sessions");
    case "session":
      return t("pg_session");
    case "agents":
      return t("nav_agents");
    case "agent_new":
      return t("pg_agent_new");
    case "agent_edit":
      return t("pg_agent_edit");
    case "models":
      return t("nav_models");
    case "setup":
      return t("nav_setup");
    case "surface":
      return t("pg_surface");
    case "surface_edit":
      return t("pg_surface_edit");
    case "to_fix":
      return t("nav_tofix");
    case "decides":
      return t("nav_decides");
    case "glossary":
      return t("nav_glossary");
    case "more":
      return t("more_h1");
  }
}

export interface ParsedRoute {
  page: PageId;
  project: string | null;
  /** The route after /p/<project>, with a leading slash. Empty for routes with no project. */
  rest: string;
  /** Route params for detail pages. */
  id?: string;
  name?: string;
  part?: string;
  item?: string;
}

/** Reads a hash path such as /p/builder/review/agents/new. Returns null for an unknown route. */
export function parseRoute(path: string): ParsedRoute | null {
  const segs =
    path
      .split("?")[0]
      ?.split("/")
      .filter((s) => s !== "") ?? [];
  const none = (page: PageId): ParsedRoute => ({ page, project: null, rest: "" });
  if (segs.length === 0) return none("picker");
  if (segs[0] === "more" && segs.length === 1) return none("more");
  if (segs[0] === "reference" && segs.length === 2) {
    if (segs[1] === "decides") return none("decides");
    if (segs[1] === "glossary") return none("glossary");
    return null;
  }
  if (segs[0] !== "p" || segs.length < 3) return null;
  const project = decodeURIComponent(segs[1] ?? "");
  const tail = segs.slice(2);
  const rest = `/${tail.join("/")}`;
  const at = (page: PageId, extra: Partial<ParsedRoute> = {}): ParsedRoute => ({
    page,
    project,
    rest,
    ...extra,
  });
  const [a, b, c, d] = tail;
  if (tail.length === 1) {
    if (a === "live") return at("live");
    if (a === "setup") return at("setup");
    if (a === "to-fix") return at("to_fix");
  }
  if (a === "review") {
    if (tail.length === 2) {
      if (b === "summary") return at("summary");
      if (b === "sessions") return at("sessions");
      if (b === "agents") return at("agents");
      if (b === "models") return at("models");
    }
    if (b === "sessions" && tail.length === 3 && c !== undefined) return at("session", { id: c });
    if (b === "agents" && tail.length === 3 && c === "new") return at("agent_new");
    if (b === "agents" && tail.length === 4 && c !== undefined && d === "edit") {
      return at("agent_edit", { name: c });
    }
  }
  // A part's list, with no item picked.
  if (a === "setup" && b !== undefined && tail.length === 2) return at("surface", { part: b });
  if (a === "setup" && b !== undefined && c !== undefined) {
    if (tail.length === 3) return at("surface", { part: b, item: c });
    if (tail.length === 4 && d === "edit") return at("surface_edit", { part: b, item: c });
  }
  return null;
}

/** A detail page a project swap has to check in the new project. */
export type DetailRoute =
  | { kind: "session"; id: string }
  | { kind: "agent"; name: string }
  | { kind: "surface"; part: string; item: string };

/**
 * The path to go to when the project changes. A list page keeps its place under the new
 * project. A detail page stays only when exists() says the item is in the new project, and
 * otherwise drops to the list level. Routes with no project come back unchanged.
 */
export function routeForProject(
  currentPath: string,
  newProject: string,
  exists: (detail: DetailRoute) => boolean,
): string {
  const parsed = parseRoute(currentPath);
  if (parsed?.project == null) return currentPath;
  const base = `/p/${encodeURIComponent(newProject)}`;
  switch (parsed.page) {
    case "session":
      return exists({ kind: "session", id: parsed.id ?? "" })
        ? `${base}${parsed.rest}`
        : `${base}/review/sessions`;
    case "agent_edit":
      return exists({ kind: "agent", name: parsed.name ?? "" })
        ? `${base}${parsed.rest}`
        : `${base}/review/agents`;
    case "surface":
    case "surface_edit":
      return exists({ kind: "surface", part: parsed.part ?? "", item: parsed.item ?? "" })
        ? `${base}${parsed.rest}`
        : `${base}/setup`;
    default:
      return `${base}${parsed.rest}`;
  }
}
