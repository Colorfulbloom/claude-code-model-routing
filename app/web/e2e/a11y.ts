/// <reference lib="dom" />
/// <reference types="node" />
/*
 * One axe loop for the M5 specs (m5-build.md section 12, risk 8). It runs axe at each width, in
 * both themes, under forced colours and under reduced motion, and it can hold a help popover or tray
 * open (or anything else) while it scans. The older specs keep their own loops.
 *
 * Each look starts from a blank page and a fresh load, so a media setting, a held route or an open
 * panel never leaks into the next look. The loop returns the problems as text, so a spec can say
 * `expect(found).toEqual([])` and the failure names the look and the selectors.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { setLook } from "./kit";

export const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
export const WIDTHS = [320, 375, 1440] as const;
export const THEMES = ["light", "dark"] as const;

/** One way to look at the page. Forced colours and reduced motion are their own looks. */
export interface Look {
  width: number;
  theme?: "light" | "dark";
  forced?: boolean;
  reduced?: boolean;
}

export interface ScanOptions {
  /** Names the scan in the problem list. */
  label: string;
  /** Loads the page for a look, after the look's viewport and media are set. */
  enter: (page: Page, look: Look) => Promise<void>;
  /** Opens a popover, a tray or anything else, after the page is ready and before axe runs. */
  hold?: (page: Page, look: Look) => Promise<void>;
  /** The widths to scan. Defaults to 320, 375 and 1440. */
  widths?: readonly number[];
}

/** Every look the loop covers at these widths. */
export function looksFor(widths: readonly number[]): Look[] {
  const found: Look[] = [];
  for (const width of widths) {
    for (const theme of THEMES) found.push({ width, theme });
  }
  for (const width of widths) {
    found.push({ width, forced: true });
    found.push({ width, reduced: true });
  }
  return found;
}

function describe(look: Look): string {
  if (look.forced === true) return `${String(look.width)} forced`;
  if (look.reduced === true) return `${String(look.width)} reduced`;
  return `${String(look.width)} ${look.theme ?? "light"}`;
}

/** Scans one page in every look and returns what axe found, one line for each violation. */
export async function scan(page: Page, options: ScanOptions): Promise<string[]> {
  const found: string[] = [];
  for (const look of looksFor(options.widths ?? WIDTHS)) {
    await setLook(page, look);
    await options.enter(page, look);
    await options.hold?.(page, look);
    // The tray's slide and the popover's fade end before axe reads colours.
    await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
    const result = await new AxeBuilder({ page: page as never }).withTags(AXE_TAGS).analyze();
    for (const violation of result.violations) {
      const nodes = violation.nodes.map((node) => node.target.join(" ")).join(" | ");
      found.push(`${options.label} ${describe(look)} axe ${violation.id}: ${nodes}`);
    }
  }
  return found;
}
