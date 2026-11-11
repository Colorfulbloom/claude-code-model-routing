/*
 * The pure parts of the shell navigation: which link is current on which route, where each
 * link goes and which routes hide the tab bar. The Shell turns these into components.
 */
import type { PageId } from "@/app/routes";

export type SidebarId =
  | "live"
  | "summary"
  | "sessions"
  | "agents"
  | "models"
  | "setup"
  | "tofix"
  | "decides"
  | "glossary";

export type TabId = "live" | "review" | "setup" | "tofix" | "more";

/** The one sidebar link that is current on a page. Detail pages keep their list's link. */
export function sidebarCurrent(page: PageId): SidebarId | null {
  switch (page) {
    case "live":
      return "live";
    case "summary":
      return "summary";
    case "sessions":
    case "session":
      return "sessions";
    case "agents":
    case "agent_new":
    case "agent_edit":
      return "agents";
    case "models":
      return "models";
    case "setup":
    case "surface":
    case "surface_edit":
    case "changes":
      return "setup";
    case "to_fix":
      return "tofix";
    case "decides":
      return "decides";
    case "glossary":
      return "glossary";
    case "picker":
    case "more":
      return null;
  }
}

/**
 * The one tab bar item that is current. Review covers every review route, Setup covers Your
 * setup and its surface pages, and More covers the More page and the Reference routes.
 */
export function tabCurrent(page: PageId): TabId | null {
  switch (page) {
    case "live":
      return "live";
    case "summary":
    case "sessions":
    case "session":
    case "agents":
    case "agent_new":
    case "agent_edit":
    case "models":
      return "review";
    case "setup":
    case "surface":
    case "surface_edit":
    case "changes":
      return "setup";
    case "to_fix":
      return "tofix";
    case "more":
    case "decides":
    case "glossary":
      return "more";
    case "picker":
      return null;
  }
}

/** The agent form routes take the whole screen, so the tab bar is not rendered there. */
export function hidesTabBar(page: PageId): boolean {
  return page === "agent_new" || page === "agent_edit";
}

/** A hash link to a project page, or to the picker when no project is known. */
export function projectHref(project: string | null, rest: string): string {
  return project === null ? "#/" : `#/p/${encodeURIComponent(project)}${rest}`;
}

/** The route path (no hash) of a project's Live page, or "/" with no project. */
export function livePath(project: string | null): string {
  return project === null ? "/" : `/p/${encodeURIComponent(project)}/live`;
}
