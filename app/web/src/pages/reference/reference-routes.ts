/*
 * The Reference pages' paths and query. The query lives in the URL, so a link can carry a search or
 * the due view, and it is written with history replace, so Back leaves the page rather than
 * stepping through keystrokes (m5-build.md section 2).
 *
 *   #/reference/decides?q=&confidence=&due=1
 *   #/reference/decides/<key>[/<rule id>]
 *   #/reference/glossary[/<term id or list item id>]?q=&from=&help=
 */
import type { ConfidenceFilter, Filters } from "./rules-view";
import { FROM_PARAM, HELP_PARAM } from "@/components/HelpEntry/origin";

export const DECIDES_PATH = "/reference/decides";
export const GLOSSARY_PATH = "/reference/glossary";

const CONFIDENCES: readonly ConfidenceFilter[] = ["all", "tested", "documented", "assumed"];

/** The filters a query holds. An unknown Confidence word is All, and a missing q is empty. */
export function readFilters(params: URLSearchParams): Filters {
  const confidence = params.get("confidence");
  const known = CONFIDENCES.find((entry) => entry === confidence);
  return {
    q: params.get("q") ?? "",
    confidence: known ?? "all",
    due: params.get("due") === "1",
  };
}

/** True when any filter narrows the rules. */
export function isNarrowed(filters: Filters): boolean {
  return filters.q.trim() !== "" || filters.confidence !== "all" || filters.due;
}

/** The query string for a set of filters, "" when none apply. */
export function filtersQuery(filters: Filters): string {
  const query = new URLSearchParams();
  if (filters.q !== "") query.set("q", filters.q);
  if (filters.confidence !== "all") query.set("confidence", filters.confidence);
  if (filters.due) query.set("due", "1");
  const text = query.toString();
  return text === "" ? "" : `?${text}`;
}

/** The path of a setting page or a rule on it, with the filters, as a hash link. */
export function decidesHref(
  target: { setting?: string; rule?: string },
  filters?: Filters,
): string {
  let path = `#${DECIDES_PATH}`;
  if (target.setting !== undefined) {
    path += `/${encodeURIComponent(target.setting)}`;
    if (target.rule !== undefined) path += `/${encodeURIComponent(target.rule)}`;
  }
  return `${path}${filters === undefined ? "" : filtersQuery(filters)}`;
}

/** Where a Glossary link came from. Both are carried so Back can return focus to the "?". */
export interface Origin {
  from: string;
  help: string | null;
}

/** The origin a Glossary query holds, or null when it has none. */
export function readOrigin(params: URLSearchParams): Origin | null {
  const from = params.get(FROM_PARAM);
  if (from === null || from === "") return null;
  return { from, help: params.get(HELP_PARAM) };
}

/** A hash link to a glossary term or list item. The origin stays on it, so Back to {page} stays. */
export function glossaryLink(
  id?: string,
  extra: { q?: string; origin?: Origin | null } = {},
): string {
  const query = new URLSearchParams();
  if (extra.q !== undefined && extra.q !== "") query.set("q", extra.q);
  if (extra.origin !== undefined && extra.origin !== null) {
    query.set(FROM_PARAM, extra.origin.from);
    if (extra.origin.help !== null) query.set(HELP_PARAM, extra.origin.help);
  }
  const text = query.toString();
  const base =
    id === undefined ? `#${GLOSSARY_PATH}` : `#${GLOSSARY_PATH}/${encodeURIComponent(id)}`;
  return text === "" ? base : `${base}?${text}`;
}
