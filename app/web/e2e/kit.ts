/// <reference lib="dom" />
/// <reference types="node" />
/*
 * What the M5 specs share against the demo build (`--demo --test-clock`, where the Claude Code the
 * owner runs is newer than the rules, so the version gap shows). One server for each worker, a page
 * opener that sets the look before it loads, and the keyboard helpers the walkthroughs use.
 */
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { rmSync } from "node:fs";
import { en } from "../src/strings/en";
import { expectUnlocked, linkFor } from "./gate";
import { startServer } from "./server";
import type { Server } from "./server";
import type { Look } from "./a11y";

export const PROJECT = "tidewater-reporting";

/** One demo server for each worker. Every opener mints its own code, so tabs never share keys. */
export const test = base.extend<object, { demo: Server; busy: Server }>({
  demo: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, run) => {
      const server = await startServer({
        fixture: null,
        args: ["--demo", "--no-price-fetch", "--test-clock"],
      });
      try {
        await run(server);
      } finally {
        await server.stop();
        rmSync(server.dataDir, { recursive: true, force: true });
      }
    },
    { scope: "worker", timeout: 90_000 },
  ],
  // The Live flow with a running session, so Live shows its tiles and cards. A spec that does not
  // ask for it never starts it.
  busy: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, run) => {
      const server = await startServer({
        fixture: null,
        args: ["--flow", "busy", "--test-clock", "--no-price-fetch"],
      });
      try {
        await run(server);
      } finally {
        await server.stop();
        rmSync(server.dataDir, { recursive: true, force: true });
      }
    },
    { scope: "worker", timeout: 90_000 },
  ],
});

/** The media a look asks for, set before the page loads. */
export async function setLook(page: Page, look: Look): Promise<void> {
  await page.setViewportSize({ width: look.width, height: 900 });
  await page.emulateMedia({
    colorScheme: look.theme ?? "light",
    ...(look.forced === true ? { forcedColors: "active" as const } : {}),
    ...(look.reduced === true ? { reducedMotion: "reduce" as const } : {}),
  });
}

export async function goTo(page: Page, path: string): Promise<void> {
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

/** Sets the look, loads the app fresh with a new code, and goes to the route. */
export async function openAt(
  page: Page,
  server: Server,
  path: string,
  look: Look | number,
): Promise<void> {
  await setLook(page, typeof look === "number" ? { width: look } : look);
  // A blank page first, so the next load is a real one with its own requests and a cold cache.
  await page.goto("about:blank");
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await goTo(page, path);
}

/** Presses Tab until the locator has focus, so a walkthrough uses only the keyboard. */
export async function tabTo(page: Page, target: Locator, max = 80): Promise<void> {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    const there = await target
      .evaluate((el) => el === document.activeElement, undefined, { timeout: 1_000 })
      .catch(() => false);
    if (there) return;
  }
  throw new Error("the keyboard never reached the target");
}

export const decides = (rest = ""): string => `/reference/decides${rest}`;
export const glossary = (rest = ""): string => `/reference/glossary${rest}`;

export const heading2 = (page: Page, name: string | RegExp): Locator =>
  page.getByRole("heading", { level: 2, name });

/** The list of settings on How Claude Code decides. */
export const settingsNav = (page: Page): Locator =>
  page.getByRole("navigation", { name: en.sf_settings });

/** The polite region beside a Reference search field. */
export const polite = (page: Page): Locator => page.locator(".search [role='status']");
