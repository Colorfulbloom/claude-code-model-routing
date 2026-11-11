/// <reference lib="dom" />
/// <reference types="node" />
/*
 * What the a16 specs (edit-keyboard, edit-settings, changes, edits-off) share on the M6a screenshot
 * fixture (e2e/fixtures/m6_edit.ts): a world that builds the made-up home and starts a real server
 * on it, a page opener, the rail's controls, keyboard helpers that press only keys, and a counter
 * for the requests a press sends.
 */
import { expect } from "@playwright/test";
import type { Locator, Page, Request } from "@playwright/test";
import { en } from "../src/strings/en";
import { expectUnlocked, linkFor } from "./gate";
import { buildM6Fixture, PROJECT_KEY, startReady } from "./fixtures/m6_edit";
import type { BuildOptions, M6Fixture, Session } from "./fixtures/m6_edit";
import type { Server } from "./server";

export const ITEM = `/p/${PROJECT_KEY}/setup/settings/effortLevel`;
export const EDIT = `${ITEM}/edit`;
export const LIST = `/p/${PROJECT_KEY}/setup/settings`;
export const SETUP = `/p/${PROJECT_KEY}/setup`;
export const CHANGES = `/p/${PROJECT_KEY}/setup/changes`;

export type Theme = "light" | "dark";

export interface World {
  fx: M6Fixture;
  server: Server;
}

/** Builds the fixture, starts the server on it, runs the body, then stops and removes it all. */
export async function inWorld(
  options: BuildOptions & { edits?: boolean },
  body: (world: World) => Promise<void>,
): Promise<void> {
  const fx = buildM6Fixture(options);
  let server: Server | null = null;
  try {
    server = await startReady(fx, { edits: options.edits ?? true });
    await body({ fx, server });
  } finally {
    if (server !== null) await server.stop();
    fx.cleanup();
  }
}

/** Opens a route on a blank page, so the same origin with a new hash always loads afresh. */
export async function openAt(
  page: Page,
  server: Server,
  route: string,
  width: number,
  theme: Theme = "light",
): Promise<void> {
  await page.goto("about:blank");
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT_KEY), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, route);
}

/**
 * Loads a route fresh with a new code and leaves the look alone, for the axe loop in e2e/a11y.ts,
 * which sets the width, theme and media before it calls `enter`.
 */
export async function loadRoute(page: Page, server: Server, route: string): Promise<void> {
  await page.goto("about:blank");
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT_KEY), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, route);
}

export const saveButton = (page: Page): Locator => page.getByRole("button", { name: /^Save to / });
export const scopeRadio = (page: Page, name: RegExp): Locator => page.getByRole("radio", { name });
// An option's name holds its run line too ("high set now runs at high Lowered"), so the level is
// matched as the first word.
export const levelRadio = (page: Page, level: string): Locator =>
  page.getByRole("radio", { name: new RegExp(`^${level}( |$)`) });

/** The rail at 721px and up is a labelled region, the sheet below that is a dialog. */
export function railOf(page: Page, width: number): Locator {
  return width > 720
    ? page.getByRole("region", { name: "Edit effort" })
    : page.getByRole("dialog", { name: "Edit effort" });
}

export async function previewReady(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 3, name: en.ed_this_save_h })).toBeVisible();
}

/** The edit route with the preview drawn, by hash, as a started session would be. */
export async function openEditRoute(page: Page, world: World, width: number): Promise<void> {
  await openAt(page, world.server, EDIT, width);
  await previewReady(page);
}

/** A mouse pick of Project local and low, then the preview that shows it. */
export async function pickLowByMouse(page: Page): Promise<void> {
  await scopeRadio(page, /^Project local/).check({ force: true });
  await levelRadio(page, "low").check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
}

// ---------------------------------------------------------------------------------------------
// Keyboard helpers. They press keys only.
// ---------------------------------------------------------------------------------------------

async function isFocused(target: Locator): Promise<boolean> {
  return target
    .evaluate((el) => el === document.activeElement, undefined, { timeout: 1_000 })
    .catch(() => false);
}

/** Presses Tab until the target has focus, then Shift+Tab from where the run started if it never did. */
export async function reach(page: Page, target: Locator, max = 60): Promise<void> {
  if (await isFocused(target)) return;
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await isFocused(target)) return;
  }
  for (let i = 0; i < max * 2; i++) {
    await page.keyboard.press("Shift+Tab");
    if (await isFocused(target)) return;
  }
  throw new Error("the keyboard never reached the target");
}

/** Presses Tab `count` times and returns the role and name of each stop, from an aria snapshot. */
export async function tabStops(page: Page, count: number): Promise<string[]> {
  const stops: string[] = [];
  for (let i = 0; i < count; i++) {
    await page.keyboard.press("Tab");
    const snapshot = await page
      .locator(":focus")
      .ariaSnapshot({ timeout: 3_000 })
      .catch(() => "- (nothing in the page has focus)");
    const line = snapshot.split("\n")[0] ?? "";
    stops.push(line.replace(/^- /, "").replace(/:$/, ""));
  }
  return stops;
}

// ---------------------------------------------------------------------------------------------
// History, read as the page reads it.
// ---------------------------------------------------------------------------------------------

/** The rows of the project's history, newest first, as the server answers a read key. */
export async function historyRows(
  session: Session,
): Promise<{ id: string; recheck: { state: string } | null }[]> {
  const res = await fetch(
    `${session.server.baseURL}/api/edit/history?project=${encodeURIComponent(PROJECT_KEY)}`,
    { headers: { "X-Bartab-Key": session.readKey, Origin: session.server.baseURL } },
  );
  if (!res.ok) throw new Error(`history answered ${String(res.status)}`);
  const body = (await res.json()) as { rows: { id: string; recheck: { state: string } | null }[] };
  return body.rows;
}

/**
 * Waits until the newest row's recheck is no longer `checking`, which a real save reaches at about
 * 2 s. A page opened after that shows the settled word. The second recheck at 10 s is not waited for.
 */
export async function waitForFirstRecheck(session: Session): Promise<void> {
  for (let tries = 0; tries < 40; tries++) {
    const rows = await historyRows(session);
    const state = rows[0]?.recheck?.state;
    if (state !== undefined && state !== "checking") return;
    await new Promise((done) => {
      setTimeout(done, 250);
    });
  }
  throw new Error("the first recheck did not settle in 10 s");
}

// ---------------------------------------------------------------------------------------------
// Requests a press sends.
// ---------------------------------------------------------------------------------------------

export interface Sent {
  /** The POSTs to /api/edit/<verb> seen so far, with their JSON bodies. */
  bodies: (verb: string) => Record<string, unknown>[];
  count: (verb: string) => number;
  /** Navigation requests (a document load) seen so far. */
  navigations: () => number;
  stop: () => void;
}

/** Counts the edit POSTs and the document loads a page sends from now on. */
export function watchRequests(page: Page): Sent {
  const seen: Request[] = [];
  const listener = (request: Request): void => {
    seen.push(request);
  };
  page.on("request", listener);
  const posts = (verb: string): Request[] =>
    seen.filter(
      (request) =>
        request.method() === "POST" && new URL(request.url()).pathname === `/api/edit/${verb}`,
    );
  return {
    bodies: (verb) =>
      posts(verb).map((request) => (request.postDataJSON() ?? {}) as Record<string, unknown>),
    count: (verb) => posts(verb).length,
    navigations: () => seen.filter((request) => request.isNavigationRequest()).length,
    stop: () => {
      page.off("request", listener);
    },
  };
}

/** Lets a late second request arrive before a count is read. */
export async function quiet(page: Page, ms = 600): Promise<void> {
  await page.waitForTimeout(ms);
}
