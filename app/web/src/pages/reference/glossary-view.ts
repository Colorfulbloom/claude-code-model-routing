/*
 * The Glossary's content, read from the shared lists and glossary.ts and nothing else. Its three
 * lists (status words, scopes, confidence words) come from lists.ts, and its Terms are the
 * glossary.ts terms in the "terms" group, A to Z. Every entry has an id a route can name.
 */
import { matches } from "@/components/SearchField/match";
import { en } from "@/strings/en";
import { GLOSSARY, hasTerm } from "@/strings/glossary";
import { CONFIDENCE_WORDS, SCOPES, STATUS_WORDS } from "@/strings/lists";
import { t } from "@/strings/t";

export type SectionId = "status-words" | "scopes" | "confidence-words" | "terms";

export interface GlossaryEntry {
  /** The route segment, such as "status-in_effect", "scope-managed", "confidence-tested" or a term id. */
  id: string;
  kind: "status" | "scope" | "confidence" | "term";
  /** The word. For a status, a scope and a confidence word the page draws its chip, label or badge. */
  name: string;
  /** For a status, the status id the chip needs. */
  status?: (typeof STATUS_WORDS)[number]["id"];
  means: string;
  /** Related terms, by id, that the Glossary has. */
  see: readonly string[];
}

export interface GlossarySection {
  id: SectionId;
  title: string;
  question: string;
  entries: readonly GlossaryEntry[];
}

function listEntries(): Record<"status" | "scopes" | "confidence", GlossaryEntry[]> {
  return {
    status: STATUS_WORDS.map((item) => ({
      id: `status-${item.id}`,
      kind: "status" as const,
      name: en[item.word],
      status: item.id,
      means: en[item.means],
      see: [],
    })),
    scopes: SCOPES.map((item) => ({
      id: `scope-${item.id}`,
      kind: "scope" as const,
      name: en[item.word],
      means: en[item.means],
      see: [],
    })),
    confidence: CONFIDENCE_WORDS.map((item) => ({
      id: `confidence-${item.id}`,
      kind: "confidence" as const,
      name: en[item.word],
      means: en[item.means],
      see: [],
    })),
  };
}

function termEntries(): GlossaryEntry[] {
  const found: GlossaryEntry[] = [];
  for (const [id, term] of Object.entries(GLOSSARY)) {
    if (term.group !== "terms") continue;
    const see: readonly string[] = "see" in term ? term.see : [];
    found.push({
      id,
      kind: "term",
      name: term.term,
      means: term.means,
      see: see.filter((other) => hasTerm(other)),
    });
  }
  return found.sort((a, b) => a.name.localeCompare(b.name, "en"));
}

/** The four sections, in page order. */
export function glossarySections(): GlossarySection[] {
  const lists = listEntries();
  return [
    {
      id: "status-words",
      title: GLOSSARY["status-words"].term,
      question: t("gl_status_q"),
      entries: lists.status,
    },
    {
      id: "scopes",
      title: GLOSSARY.scopes.term,
      question: t("gl_scopes_q"),
      entries: lists.scopes,
    },
    {
      id: "confidence-words",
      title: GLOSSARY["confidence-words"].term,
      question: t("gl_conf_q"),
      entries: lists.confidence,
    },
    { id: "terms", title: t("gl_terms_h"), question: t("gl_terms_q"), entries: termEntries() },
  ];
}

/** The name of a term, for a see link. The id itself when the Glossary has no such term. */
export function termName(id: string): string {
  return hasTerm(id) ? GLOSSARY[id].term : id;
}

export interface Target {
  /** The section the target sits in. */
  section: SectionId;
  /** The entry's id, or null when the target is the section itself. */
  entry: string | null;
}

const SECTION_TERMS: Readonly<Record<string, SectionId>> = {
  "status-words": "status-words",
  scopes: "scopes",
  "confidence-words": "confidence-words",
};

/** Where an id points, or null for an id the Glossary does not have. */
export function resolveTarget(id: string, sections: readonly GlossarySection[]): Target | null {
  const section = SECTION_TERMS[id];
  if (section !== undefined) return { section, entry: null };
  for (const candidate of sections) {
    if (candidate.entries.some((entry) => entry.id === id)) {
      return { section: candidate.id, entry: id };
    }
  }
  return null;
}

/** An entry matches when every word of the query is in its name or its meaning. */
export function entryMatches(entry: GlossaryEntry, q: string): boolean {
  return matches(q, `${entry.name} ${entry.means}`);
}
