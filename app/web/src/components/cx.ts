/** Joins class names, skipping empty values. */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter((part): part is string => typeof part === "string" && part !== "").join(" ");
}
