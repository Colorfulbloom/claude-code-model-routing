/*
 * The search match, held in one pure module. A query is split on whitespace and every word must
 * be found in the text, in any order. Both sides fold the same way, lower case then NFKD with the
 * combining marks removed, so "cafe" finds "Café". An empty query matches everything.
 * `highlight` splits the original text into strings and <mark> elements, never into HTML.
 */
import { createElement, type ReactNode } from "react";

const MARKS = /\p{M}/u;

function foldChar(char: string): string {
  return char.toLowerCase().normalize("NFKD").replace(/\p{M}/gu, "");
}

/**
 * Folds a whole string the way both sides of a match are folded. It folds one character at a
 * time, so it agrees with the index table `highlight` builds (a lone final sigma would otherwise
 * lower-case differently inside a word than on its own).
 */
export function fold(text: string): string {
  let out = "";
  for (const char of text) out += foldChar(char);
  return out;
}

function words(query: string): string[] {
  return fold(query)
    .split(/\s+/)
    .filter((word) => word !== "");
}

/** True when every word of the query is in the text. An empty query matches everything. */
export function matches(query: string, text: string): boolean {
  const needed = words(query);
  if (needed.length === 0) return true;
  const hay = fold(text);
  return needed.every((word) => hay.includes(word));
}

/**
 * Matches a query against named fields and says where it was found. Every query word must be
 * found somewhere across the fields, so "effort docs" can match a word in one field and a word in
 * another. The answer is null for no match, or the set of field names in which any query word was
 * found. An empty query matches with an empty set. A row whose set holds only its quote field is
 * a match found in the docs line, and the page can say so and open that line.
 */
export function matchFields(
  query: string,
  fields: Readonly<Record<string, string>>,
): ReadonlySet<string> | null {
  const needed = words(query);
  const found = new Set<string>();
  if (needed.length === 0) return found;
  const folded = Object.entries(fields).map(([name, text]) => [name, fold(text)] as const);
  for (const word of needed) {
    const where = folded.filter(([, hay]) => hay.includes(word));
    if (where.length === 0) return null;
    for (const [name] of where) found.add(name);
  }
  return found;
}

/**
 * The text with each match wrapped in a <mark>. Folding can change a character's length ("ﬁ"
 * becomes "fi"), so the match is found in the folded text and mapped back to the original by an
 * index table. Overlapping and touching matches merge into one mark.
 */
export function highlight(text: string, query: string): ReactNode[] {
  const needed = words(query);
  if (needed.length === 0 || text === "") return [text];
  let folded = "";
  const starts: number[] = [];
  const ends: number[] = [];
  let at = 0;
  for (const char of text) {
    const part = foldChar(char);
    // One entry per folded character, each pointing at the original character it came from.
    starts.push(...Array.from({ length: part.length }, () => at));
    ends.push(...Array.from({ length: part.length }, () => at + char.length));
    folded += part;
    at += char.length;
  }
  const ranges: [number, number][] = [];
  for (const word of needed) {
    let from = folded.indexOf(word);
    while (from !== -1) {
      const start = starts[from];
      let end = ends[from + word.length - 1];
      if (start !== undefined && end !== undefined) {
        // A mark that follows the last letter belongs to it.
        while (end < text.length && MARKS.test(text.charAt(end))) end += 1;
        ranges.push([start, end]);
      }
      from = folded.indexOf(word, from + word.length);
    }
  }
  if (ranges.length === 0) return [text];
  ranges.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const merged: [number, number][] = [];
  for (const range of ranges) {
    const last = merged[merged.length - 1];
    if (last !== undefined && range[0] <= last[1]) last[1] = Math.max(last[1], range[1]);
    else merged.push([range[0], range[1]]);
  }
  const nodes: ReactNode[] = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (start > cursor) nodes.push(text.slice(cursor, start));
    nodes.push(
      createElement(
        "mark",
        { key: `m${String(start)}`, className: "search-mark" },
        text.slice(start, end),
      ),
    );
    cursor = end;
  }
  if (cursor < text.length) nodes.push(text.slice(cursor));
  return nodes;
}
