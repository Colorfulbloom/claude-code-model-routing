/*
 * The guards for the help registry, the Glossary and the shared lists (m5-build.md section 4).
 * Each guard is a plain function over data, so the "catches" tests can hand it a planted fault and
 * see it report one. The real-data tests run the same functions over the real files.
 */
import { describe, expect, it } from "vitest";
import { en } from "@/strings/en";
import { GLOSSARY, type GlossaryTerm } from "@/strings/glossary";
import { HELP, type HelpEntry } from "@/strings/help";
import { LISTS, type ListItem } from "@/strings/lists";
import { sourceFiles, type SourceFile } from "@/test/source-files";

type Registry = Readonly<Record<string, HelpEntry>>;
type Terms = Readonly<Record<string, GlossaryTerm>>;
type Deck = Readonly<Record<string, string>>;

const registry: Registry = HELP;
const terms: Terms = GLOSSARY;
const deck: Deck = en;

/** The most glossary links one entry may carry. */
const MAX_GLOSSARY_LINKS = 2;

/**
 * The same bans the en.ts lint holds (lint.test.ts): no colon in prose, no em dash, no
 * exclamation mark, and no bold. That file's rule is not exported, so the pattern is copied here.
 */
const PROSE_BANS: readonly (readonly [string, (value: string) => boolean])[] = [
  ["a colon", (value) => value.includes(":")],
  ["an em dash", (value) => value.includes("—")],
  ["an exclamation mark", (value) => value.includes("!")],
  ["bold", (value) => value.includes("**")],
];

/**
 * A literal help id in a prop. `help="id"` and `helpId="id"` are the plain forms, and
 * `help={{ id: "id" }}` is the form Tile takes. An id built from a variable or a template has no
 * literal text, so it never matches (fact K-819f).
 */
const HELP_PROP = /\b(?:help|helpId)=(?:"([^"]+)"|\{\{\s*id:\s*"([^"]+)")/g;

/** The literal help ids a source text names. */
export function helpIdsIn(text: string): string[] {
  return [...text.matchAll(HELP_PROP)].map((match) => match[1] ?? match[2] ?? "");
}

/** Every `path: id` where a source names an id the registry lacks. */
export function unknownHelpIds(sources: readonly SourceFile[], known: Registry): string[] {
  const problems: string[] = [];
  for (const source of sources) {
    for (const id of helpIdsIn(source.text)) {
      if (!Object.hasOwn(known, id)) problems.push(`${source.path}: ${id}`);
    }
  }
  return problems;
}

/** The registry ids that no source names. */
export function unusedHelpIds(sources: readonly SourceFile[], known: Registry): string[] {
  const named = new Set(sources.flatMap((source) => helpIdsIn(source.text)));
  return Object.keys(known).filter((id) => !named.has(id));
}

/** Dead glossary links in the registry and the Glossary, and entries with too many links. */
export function glossaryProblems(known: Registry, glossary: Terms): string[] {
  const problems: string[] = [];
  for (const [id, entry] of Object.entries(known)) {
    const links = entry.glossary ?? [];
    for (const term of links) {
      if (!Object.hasOwn(glossary, term)) problems.push(`help ${id} links to missing term ${term}`);
    }
    if (links.length > MAX_GLOSSARY_LINKS) {
      problems.push(`help ${id} has ${links.length} glossary links, at most ${MAX_GLOSSARY_LINKS}`);
    }
  }
  for (const [id, term] of Object.entries(glossary)) {
    for (const see of term.see ?? []) {
      if (!Object.hasOwn(glossary, see)) problems.push(`term ${id} sees missing term ${see}`);
    }
  }
  return problems;
}

/** The en.ts keys that a shared list names, with the list item that names each. */
function listKeys(
  lists: Readonly<Record<string, readonly ListItem[]>>,
  fields: readonly ("word" | "means")[] = ["word", "means"],
): Map<string, string> {
  const out = new Map<string, string>();
  for (const [name, items] of Object.entries(lists)) {
    for (const item of items) {
      for (const field of fields) out.set(item[field], `${name}.${item.id}.${field}`);
    }
  }
  return out;
}

/**
 * Every other en.ts key that holds the same text as a `means` a shared list uses. The plan guards
 * definitions, not labels, so a list `word` may repeat as a label elsewhere ("Default", "User").
 */
export function duplicatedListText(
  strings: Deck,
  lists: Readonly<Record<string, readonly ListItem[]>>,
): string[] {
  const problems: string[] = [];
  for (const [key, spot] of listKeys(lists, ["means"])) {
    const text = strings[key];
    if (text === undefined) continue;
    for (const [other, value] of Object.entries(strings)) {
      if (other !== key && value === text) {
        problems.push(`${other} repeats ${key} (${spot}): "${text}"`);
      }
    }
  }
  return problems;
}

/** Every prose field of a help entry, with a name for the failure message. */
function helpTexts(id: string, entry: HelpEntry): [string, string][] {
  const out: [string, string][] = [[`help ${id} title`, entry.title]];
  if (entry.shows !== undefined) out.push([`help ${id} shows`, entry.shows]);
  if (entry.reading !== undefined) out.push([`help ${id} reading`, entry.reading]);
  (entry.lines ?? []).forEach((line, index) => {
    out.push([`help ${id} line ${index + 1} label`, line.label]);
    out.push([`help ${id} line ${index + 1} means`, line.means]);
  });
  return out;
}

/** The registry's and the Glossary's shape and prose problems. */
export function shapeProblems(known: Registry, glossary: Terms, strings: Deck): string[] {
  const problems: string[] = [];
  const texts: [string, string][] = [];
  for (const [id, entry] of Object.entries(known)) {
    if (entry.title.trim() === "") problems.push(`help ${id} has no title`);
    const hasShows = entry.shows !== undefined && entry.shows.trim() !== "";
    const hasLines = entry.lines !== undefined && entry.lines.length > 0;
    const hasList = entry.list !== undefined;
    if (!hasShows && !hasLines && !hasList) {
      problems.push(`help ${id} has none of shows, lines or list`);
    }
    for (const [unit, key] of Object.entries(entry.titleByUnit ?? {})) {
      if (!Object.hasOwn(strings, key))
        problems.push(`help ${id} titleByUnit ${unit}: no key ${key}`);
    }
    texts.push(...helpTexts(id, entry));
  }
  for (const [id, term] of Object.entries(glossary)) {
    if (term.term.trim() === "") problems.push(`term ${id} has no name`);
    if (term.means.trim() === "") problems.push(`term ${id} has no meaning`);
    texts.push([`term ${id} term`, term.term], [`term ${id} means`, term.means]);
  }
  for (const [name, value] of texts) {
    for (const [ban, found] of PROSE_BANS) {
      if (found(value)) problems.push(`${name} has ${ban}: "${value}"`);
    }
  }
  return problems;
}

/** The list words and meanings that are not en.ts keys. A cast can slip one past tsc. */
export function listKeyProblems(
  strings: Deck,
  lists: Readonly<Record<string, readonly ListItem[]>>,
): string[] {
  const problems: string[] = [];
  for (const [key, spot] of listKeys(lists)) {
    if (!Object.hasOwn(strings, key)) problems.push(`${spot} is not an en.ts key: ${key}`);
  }
  return problems;
}

const tsxSources = sourceFiles([".tsx"]);
/** The component sheet draws samples of the real components, so it is not a spot of its own. */
const spotSources = tsxSources.filter((source) => !source.path.startsWith("sheet/"));

describe("help registry guards", () => {
  it("has entries", () => {
    expect(Object.keys(registry).length).toBeGreaterThan(10);
    expect(Object.keys(terms).length).toBeGreaterThan(10);
    expect(tsxSources.length).toBeGreaterThan(10);
  });

  it("names no help id the registry lacks", () => {
    expect(unknownHelpIds(tsxSources, registry)).toEqual([]);
  });

  it("names every registry id in at least one literal prop", () => {
    expect(unusedHelpIds(spotSources, registry)).toEqual([]);
  });

  it("links every glossary id, with at most two links per entry", () => {
    expect(glossaryProblems(registry, terms)).toEqual([]);
  });

  it("types each shared list definition once", () => {
    expect(duplicatedListText(deck, LISTS)).toEqual([]);
  });

  it("gives every entry a title and shows or lines, with the lint's prose rules", () => {
    expect(shapeProblems(registry, terms, deck)).toEqual([]);
  });

  it("points every shared list word and meaning at an en.ts key", () => {
    expect(listKeyProblems(deck, LISTS)).toEqual([]);
  });
});

describe("help guards catch a planted fault", () => {
  const entry: HelpEntry = { title: "Sample", kind: "tile", shows: "What it shows." };
  const base: Registry = { "live.cache": entry, "live.tokens": entry };

  it("reads literal help props in both forms and skips built ones", () => {
    const text = [
      '<HelpButton help="live.cache" />',
      '<HelpTerm helpId="agents.cols">x</HelpTerm>',
      '<Tile help={{ id: "live.spent", values }} />',
      "<HelpButton help={id} />",
      "<HelpButton help={`live.${x}`} />",
    ].join("\n");
    expect(helpIdsIn(text)).toEqual(["live.cache", "agents.cols", "live.spent"]);
  });

  it("fails on an unknown help id in a tsx file", () => {
    const planted: SourceFile = { path: "scratch.tsx", text: '<HelpButton help="live.nope" />' };
    expect(unknownHelpIds([planted], base)).toEqual(["scratch.tsx: live.nope"]);
    const fixed: SourceFile = { path: "scratch.tsx", text: '<HelpButton help="live.cache" />' };
    expect(unknownHelpIds([fixed], base)).toEqual([]);
  });

  it("lists an entry no source names", () => {
    const source: SourceFile = { path: "a.tsx", text: '<HelpButton help="live.cache" />' };
    expect(unusedHelpIds([source], base)).toEqual(["live.tokens"]);
  });

  it("fails on a bad glossary id and on a third link", () => {
    const bad: Registry = { "live.cache": { ...entry, glossary: ["tokens", "nope"] as never } };
    expect(glossaryProblems(bad, terms)).toEqual(["help live.cache links to missing term nope"]);
    const many: Registry = { "live.cache": { ...entry, glossary: ["tokens", "run", "backup"] } };
    expect(glossaryProblems(many, terms)).toEqual([
      "help live.cache has 3 glossary links, at most 2",
    ]);
    const badSee: Terms = { a: { term: "A", means: "x", group: "terms", see: ["b"] } };
    expect(glossaryProblems({}, badSee)).toEqual(["term a sees missing term b"]);
  });

  it("fails on a list definition typed a second time", () => {
    const strings: Deck = {
      w: "Project",
      m: "Shared by the project.",
      other: "Shared by the project.",
    };
    const lists = { scopes: [{ id: "p", word: "w", means: "m" }] } as unknown as Record<
      string,
      readonly ListItem[]
    >;
    expect(duplicatedListText(strings, lists)).toHaveLength(1);
    expect(duplicatedListText({ ...strings, other: "Something else." }, lists)).toEqual([]);
    // A repeated word is a label, not a second definition.
    expect(duplicatedListText({ ...strings, other: "Project" }, lists)).toEqual([]);
  });

  it("fails on a colon, an em dash, an exclamation mark or bold in a value", () => {
    for (const bad of ["Note: x", "a — b", "Wow!", "a **b** c"]) {
      const planted: Registry = { "live.cache": { ...entry, shows: bad } };
      expect(shapeProblems(planted, {}, deck)).toHaveLength(1);
    }
    expect(shapeProblems({ "live.cache": entry }, {}, deck)).toEqual([]);
  });

  it("fails on a missing title, a missing body and a bad titleByUnit key", () => {
    const noTitle: Registry = { a: { ...entry, title: " " } };
    expect(shapeProblems(noTitle, {}, deck)).toEqual(["help a has no title"]);
    const noBody: Registry = { a: { title: "A", kind: "tile" } };
    expect(shapeProblems(noBody, {}, deck)).toEqual(["help a has none of shows, lines or list"]);
    const listOnly: Registry = { a: { title: "A", kind: "pill", list: "status" } };
    expect(shapeProblems(listOnly, {}, deck)).toEqual([]);
    const badUnit: Registry = {
      a: {
        ...entry,
        titleByUnit: {
          hour: "ch_h_hour",
          day: "nope" as never,
          week: "ch_h_week",
          month: "ch_h_month",
        },
      },
    };
    expect(shapeProblems(badUnit, {}, deck)).toEqual(["help a titleByUnit day: no key nope"]);
  });

  it("fails on a list word that is not an en.ts key", () => {
    const lists = { scopes: [{ id: "p", word: "nope", means: "m" }] } as unknown as Record<
      string,
      readonly ListItem[]
    >;
    expect(listKeyProblems({ m: "x" }, lists)).toEqual(["scopes.p.word is not an en.ts key: nope"]);
  });
});
