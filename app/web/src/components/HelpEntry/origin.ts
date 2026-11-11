/*
 * Where a Glossary link from a help popover came from. The link carries the route it was opened on
 * and the id of the "?" that opened it in its query, #/reference/glossary/<term>?from=<route>&help=<id>.
 * The Glossary reads both to draw "Back to {page}", and following that link focuses the trigger whose
 * data-help-id is the id, so a keyboard user lands back where they were (m5-build.md section 13,
 * need 2).
 */

export const FROM_PARAM = "from";
export const HELP_PARAM = "help";

/**
 * The route the page is on now, without the "#", when it can be an origin. The Reference pages and
 * the picker are not, because a link back to them has nothing to focus.
 */
export function currentOrigin(hash: string = window.location.hash): string | null {
  if (!hash.startsWith("#/")) return null;
  const path = hash.slice(1);
  if (path === "/" || path.startsWith("/reference")) return null;
  return path;
}

/** The hash link to a glossary term, with the origin when the page is one a person can go back to. */
export function glossaryHref(term: string, help: string): string {
  const base = `#/reference/glossary/${encodeURIComponent(term)}`;
  const from = currentOrigin();
  if (from === null) return base;
  return `${base}?${FROM_PARAM}=${encodeURIComponent(from)}&${HELP_PARAM}=${encodeURIComponent(help)}`;
}

/** The selector of the trigger a help id names. Every HelpButton and HelpTerm carries the attribute. */
export function triggerSelector(help: string): string {
  return `[data-help-id="${help.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"]`;
}

let pending: { help: string; path: string } | null = null;

/**
 * Called when Back to {page} starts, with the link's own href. The router focuses the trigger once
 * the page is there. It runs on press start, not on press, because a keyboard Enter follows the
 * link at once and the page unmounts the link before its press ends. The path keeps a press that
 * was dropped from focusing something on a later, unrelated page.
 */
export function setReturnFocus(help: string | null, href: string): void {
  pending = help === null ? null : { help, path: routePath(href) };
}

/** The route a hash link goes to, without the "#" or the query. */
function routePath(href: string): string {
  const route = href.startsWith("#") ? href.slice(1) : href;
  return route.split("?")[0] ?? route;
}

/** Takes the help id waiting for the page at `pathname`, and clears it. Null for any other page. */
export function takeReturnFocus(pathname = ""): string | null {
  const waiting = pending;
  pending = null;
  return waiting !== null && waiting.path === pathname ? waiting.help : null;
}
