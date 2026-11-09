import { describe, expect, it } from "vitest";
import { en } from "@/strings/en";

/** Keys whose values are labels, so a colon is allowed. None yet. */
const COLON_ALLOWED = new Set<string>();

/** Words that keep their capital inside a heading or title. */
const PROPER_NOUNS = [
  "Bar Tab",
  "Claude Code",
  "Live",
  "Review",
  "Setup",
  "To fix",
  "MCP",
  "CLAUDE.md",
  "Opus",
  "Sonnet",
  "Haiku",
  "Fable",
  "VoiceOver",
];

const entries = Object.entries(en) as [string, string][];

function capitalisedAfterFirst(value: string): string[] {
  let rest = value.replace(/\{\w+\}/g, "x");
  for (const noun of PROPER_NOUNS) rest = rest.split(noun).join("x");
  return rest
    .split(/\s+/)
    .filter((w) => w !== "")
    .slice(1)
    .filter((w) => /^[A-Z][a-z]/.test(w));
}

describe("string deck lint", () => {
  it("has entries", () => {
    expect(entries.length).toBeGreaterThan(10);
  });

  it.each(entries)("%s has no em dash", (_key, value) => {
    expect(value).not.toContain("—");
  });

  it.each(entries)("%s has no exclamation mark", (_key, value) => {
    expect(value).not.toContain("!");
  });

  it.each(entries)("%s has no straight colon in prose", (key, value) => {
    if (COLON_ALLOWED.has(key)) return;
    expect(value).not.toContain(":");
  });

  it.each(entries.filter(([key]) => key.endsWith("_h") || key.endsWith("_title")))(
    "%s is sentence case",
    (_key, value) => {
      expect(capitalisedAfterFirst(value).length).toBeLessThanOrEqual(1);
    },
  );

  it("catches Title Case", () => {
    expect(capitalisedAfterFirst("Getting The Dashboard Ready")).toEqual([
      "The",
      "Dashboard",
      "Ready",
    ]);
    expect(capitalisedAfterFirst("Getting the dashboard ready")).toEqual([]);
    expect(capitalisedAfterFirst("Open Claude Code in Review")).toEqual([]);
  });
});
