/// <reference lib="dom" />
/// <reference types="node" />
/*
 * How the specs read the gate. The gate pages carry data hooks on their h1 (`data-gate` and
 * `data-reason`), and the shell root carries `data-shell`. Strings come from the string deck.
 */
import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { en } from "../src/strings/en";

export const KEYS = {
  readKey: "bartab.readKey",
  instance: "bartab.instance",
  route: "bartab.route",
} as const;

export type Reason =
  | "no_key"
  | "code_used"
  | "code_expired"
  | "code_unknown"
  | "server_restarted"
  | "wrong_project_key";

export const COMMAND = "/bartab-preview";

/** The locked page's h1, whatever the reason. */
export function lockedHeading(page: Page) {
  return page.locator('h1[data-gate="locked"]');
}

export function gateHeading(page: Page, gate: "locked" | "stopped" | "firstrun") {
  return page.locator(`h1[data-gate="${gate}"]`);
}

export async function expectLocked(page: Page, reason: Reason): Promise<void> {
  await expect(page.locator(`h1[data-gate="locked"][data-reason="${reason}"]`)).toBeVisible();
}

export async function expectUnlocked(page: Page): Promise<void> {
  await expect(page.locator("h1").first()).toBeVisible();
  await expect(page.locator("[data-gate]")).toHaveCount(0);
  await expect(page.locator(".wait-hold")).toHaveCount(0);
}

/** The "other tab is back" line. Its template carries {page} and {project}, so match the rest. */
function tabBackLine(page: Page) {
  const source = en.lk_tab_back
    .split(/\{\w+\}/)
    .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join(".+");
  return page.getByText(new RegExp(`^${source}$`));
}

export async function expectOtherTabBack(page: Page): Promise<void> {
  await expect(tabBackLine(page)).toBeVisible();
}

export async function expectNoOtherTabBack(page: Page): Promise<void> {
  await expect(tabBackLine(page)).toHaveCount(0);
}

export async function storage(page: Page): Promise<Record<string, string>> {
  return page.evaluate(() => Object.fromEntries(Object.entries(window.sessionStorage)));
}

export function linkFor(baseURL: string, code: string, route = "/"): string {
  return `${baseURL}/#${route}?code=${code}`;
}

/** Fills {name} placeholders in a string from the deck. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in values ? String(values[name]) : whole,
  );
}
