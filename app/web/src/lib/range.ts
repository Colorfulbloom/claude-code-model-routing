/*
 * The Review range. The six presets in the order the Select lists them, a parser for `?range=`
 * that never lets a bad value reach the server, the per-tab last pick, and the helper that builds
 * Review links so the range travels with them.
 *
 * The range lives in the URL. The last pick sits in sessionStorage, so a Review link with no
 * range opens on the range this tab used last. Storage can throw (private windows, blocked site
 * data), so every read and write is wrapped, and the page works without it.
 */
import { useEffect } from "react";
import { useSearchParams } from "react-router";
import type { ReviewRange } from "@/api/types";

/** The presets, in the order the Select shows them. */
export const RANGES: readonly ReviewRange[] = ["today", "7d", "30d", "90d", "12m", "all"];

export const DEFAULT_RANGE: ReviewRange = "30d";

/** The sessionStorage key for the tab's last pick. */
export const RANGE_STORAGE_KEY = "bartab.review.range";

export function isRange(value: unknown): value is ReviewRange {
  return typeof value === "string" && (RANGES as readonly string[]).includes(value);
}

export interface ParsedRange {
  range: ReviewRange;
  /** True when the URL held a value that is not a preset, so the page replaces it. */
  replace: boolean;
}

/**
 * Reads a `?range=` value. A preset passes. No value gives `fallback` (the tab's last pick) and
 * leaves the URL alone. Any other value gives 30 days and asks for the URL to be replaced, so a
 * request is never sent with a bad range.
 */
export function parseRange(raw: string | null, fallback: ReviewRange = DEFAULT_RANGE): ParsedRange {
  if (raw === null) return { range: fallback, replace: false };
  if (isRange(raw)) return { range: raw, replace: false };
  return { range: DEFAULT_RANGE, replace: true };
}

/** The tab's last pick, or null when none was saved or storage is unavailable. */
export function readLastRange(): ReviewRange | null {
  try {
    const value = sessionStorage.getItem(RANGE_STORAGE_KEY);
    return isRange(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastRange(range: ReviewRange): void {
  try {
    sessionStorage.setItem(RANGE_STORAGE_KEY, range);
  } catch {
    // Storage is a convenience. The URL still holds the range.
  }
}

/** A Review page, or one session under Sessions. */
export type ReviewTarget = "summary" | "sessions" | "agents" | "models" | { session: string };

/**
 * A Review link that keeps the range, as a router path (no hash). Extra params follow the range,
 * such as `at` for a replay minute. A null or undefined extra is left out.
 */
export function reviewPath(
  project: string,
  target: ReviewTarget,
  range: ReviewRange,
  extra: Record<string, string | number | null | undefined> = {},
): string {
  const tail =
    typeof target === "string" ? target : `sessions/${encodeURIComponent(target.session)}`;
  const params = new URLSearchParams({ range });
  for (const [name, value] of Object.entries(extra)) {
    if (value !== null && value !== undefined) params.set(name, String(value));
  }
  return `/p/${encodeURIComponent(project)}/review/${tail}?${params.toString()}`;
}

export interface RangeParam {
  range: ReviewRange;
  /** Picks a range and keeps the other params. It adds a history entry, so Back undoes it. */
  setRange: (next: ReviewRange) => void;
}

/**
 * The page's range. It reads `?range=`, falls back to the tab's last pick when the link has none,
 * replaces the URL once when the value is bad, and remembers the pick for the tab.
 */
export function useRangeParam(): RangeParam {
  const [params, setParams] = useSearchParams();
  const raw = params.get("range");
  const parsed = parseRange(raw, readLastRange() ?? DEFAULT_RANGE);

  useEffect(() => {
    writeLastRange(parsed.range);
    if (!parsed.replace) return;
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.set("range", DEFAULT_RANGE);
        return next;
      },
      { replace: true },
    );
  }, [parsed.range, parsed.replace, setParams]);

  return {
    range: parsed.range,
    setRange(next) {
      writeLastRange(next);
      setParams((current) => {
        const copy = new URLSearchParams(current);
        copy.set("range", next);
        return copy;
      });
    },
  };
}
