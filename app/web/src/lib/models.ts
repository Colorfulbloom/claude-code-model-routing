/*
 * Model ids from the server ("claude-opus-5-5") to the family the swatch and bar colours use, and
 * to the name on screen ("Opus 5.5"). The page owns every word, so the server sends ids only.
 * An id that follows no known pattern keeps its raw text and draws with no swatch.
 */
import type { Model } from "@/components/ModelSwatch/ModelSwatch";

const FAMILIES = ["opus", "sonnet", "haiku", "fable"] as const;

/** The family a model id belongs to, or null when none of the four matches. */
export function modelFamily(id: string | null): Model | null {
  if (id === null) return null;
  const lower = id.toLowerCase();
  return FAMILIES.find((family) => lower.includes(family)) ?? null;
}

const ID_PATTERN = /^claude-(opus|sonnet|haiku|fable)-(\d+)(?:-(\d+))?$/;

/** "claude-opus-5-5" reads "Opus 5.5", "claude-fable-5" reads "Fable 5". Other names stay as sent. */
export function modelLabel(id: string): string {
  const found = ID_PATTERN.exec(id);
  const family = found?.[1];
  const major = found?.[2];
  if (family === undefined || major === undefined) return id;
  const name = `${family.charAt(0).toUpperCase()}${family.slice(1)}`;
  const minor = found?.[3];
  return minor === undefined ? `${name} ${major}` : `${name} ${major}.${minor}`;
}
