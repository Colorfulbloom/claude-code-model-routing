/*
 * Reads the app's source files as text, for the guard tests that scan call sites (help.test.ts
 * and unused-keys.test.ts). Test files are never returned, so a test that names a key or an id
 * on purpose does not count as a use.
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";

/** The absolute path of app/web/src. */
export const SRC = resolve(import.meta.dirname, "..");

export interface SourceFile {
  /** The path under src, with forward slashes, such as "pages/live/LivePage.tsx". */
  readonly path: string;
  readonly text: string;
}

/** Every non-test file under src with one of the extensions, in path order. */
export function sourceFiles(extensions: readonly string[]): SourceFile[] {
  return readdirSync(SRC, { recursive: true, encoding: "utf8" })
    .map((entry) => entry.split("\\").join("/"))
    .filter((path) => extensions.some((ext) => path.endsWith(ext)))
    .filter((path) => !/\.test\.[tj]sx?$/.test(path))
    .sort()
    .map((path) => ({ path, text: readFileSync(join(SRC, path), "utf8") }));
}
