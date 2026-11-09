/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Screens for the design review. Every M0 screen is captured full page as a PNG at 1440x900 and
 * 375x812, in light and dark, into test-results/screens/<name>-<width>-<theme>.png. The captures
 * are review material, not gates. The only asserts are the ones that prove the page was in the
 * state its file name claims.
 */
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import type { BrowserContext, Page } from "@playwright/test";
import { en } from "../src/strings/en";
import {
  expectLocked,
  expectOtherTabBack,
  expectUnlocked,
  fill,
  gateHeading,
  linkFor,
} from "./gate";
import { expect, test } from "./server";

const OUT = resolve(import.meta.dirname, "..", "test-results", "screens");
const PROJECT = "tidewater-reporting";
const PROJECT_NAME = "Tidewater Reporting";
const SIZES = [
  { width: 1440, height: 900 },
  { width: 375, height: 812 },
] as const;
const THEMES = ["light", "dark"] as const;
type Size = (typeof SIZES)[number];
type Theme = (typeof THEMES)[number];

mkdirSync(OUT, { recursive: true });

async function look(page: Page, size: Size, theme: Theme): Promise<void> {
  await page.setViewportSize(size);
  await page.emulateMedia({ colorScheme: theme });
  // Colours transition on a theme change.
  await page.waitForTimeout(500);
}

async function snap(page: Page, name: string, size: Size, theme: Theme): Promise<void> {
  await page.screenshot({
    path: join(OUT, `${name}-${String(size.width)}-${theme}.png`),
    fullPage: true,
  });
}

/** Captures the page as it is in all four size and theme combinations. */
async function shootAll(
  page: Page,
  name: string,
  sizes: readonly Size[] = SIZES,
  stillThere?: () => Promise<void>,
): Promise<void> {
  for (const size of sizes) {
    for (const theme of THEMES) {
      await look(page, size, theme);
      if (stillThere !== undefined) await stillThere();
      await snap(page, name, size, theme);
    }
  }
}

async function openLive(
  page: Page,
  server: { baseURL: string; mint: (project: string) => Promise<string> },
  route = "/",
): Promise<void> {
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), route));
  await expectUnlocked(page);
}

function sizeOf(width: number): Size {
  const found = SIZES.find((s) => s.width === width);
  if (found === undefined) throw new Error(`no size ${String(width)}`);
  return found;
}

test.describe("shell", () => {
  test("shell-live", async ({ page, server }) => {
    await openLive(page, server);
    await expect(page).toHaveURL(new RegExp(`#/p/${PROJECT}/live$`));
    await expect(page.locator("main h1")).toHaveText(en.nav_live);
    await shootAll(page, "shell-live");
  });

  test("shell-tofix", async ({ page, server }) => {
    await openLive(page, server, `/p/${PROJECT}/to-fix`);
    await expect(page.locator("main h1")).toHaveText(en.nav_tofix);
    await shootAll(page, "shell-tofix");
  });

  test("more, 375 only", async ({ page, server }) => {
    await page.setViewportSize(sizeOf(375));
    await openLive(page, server);
    await page.evaluate(() => {
      window.location.hash = "/more";
    });
    await expect(page.locator("main h1")).toHaveText(en.more_h1);
    await shootAll(page, "more", [sizeOf(375)]);
  });
});

test.describe("picker", () => {
  test("picker-open", async ({ page, server }) => {
    await openLive(page, server);
    for (const size of SIZES) {
      await page.setViewportSize(size);
      const opener =
        size.width === 375
          ? page.getByRole("button", { name: fill(en.project_aria, { name: PROJECT_NAME }) })
          : page.getByRole("button", { name: new RegExp(en.project_label) });
      await opener.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      for (const theme of THEMES) {
        await look(page, size, theme);
        await snap(page, "picker-open", size, theme);
      }
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
    }
  });

  test("picker-root", async ({ page, server }) => {
    // #/ with no launch project, on the demo fixture: the picker the owner lands on.
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    await expect(page.getByRole("option", { name: new RegExp(PROJECT_NAME) })).toBeVisible();
    await shootAll(page, "picker-root");
  });

  test.describe("empty", () => {
    test.use({ fixture: "empty" });
    test("picker-empty", async ({ page, server }) => {
      await page.goto(linkFor(server.baseURL, server.code, "/"));
      await expect(page.getByText(en.pk_empty_h)).toBeVisible();
      await shootAll(page, "picker-empty");
    });
  });
});

test.describe("gates", () => {
  test("locked-no-key", async ({ page, server }) => {
    await page.goto(`${server.baseURL}/#/p/${PROJECT}/review/agents`);
    await expectLocked(page, "no_key");
    await shootAll(page, "locked-no-key");
  });

  test("locked-code-used", async ({ page, browser, server }) => {
    const first = await browser.newContext();
    const tab = await first.newPage();
    await tab.goto(linkFor(server.baseURL, server.code));
    await expectUnlocked(tab);
    await first.close();
    await page.goto(linkFor(server.baseURL, server.code));
    await expectLocked(page, "code_used");
    await shootAll(page, "locked-code-used");
  });

  // The hold lasts 400 ms. An init script drops the page's timers and keeps the other tabs'
  // answer from arriving, so the hold stays up while the four captures run.
  test("locked-wait", async ({ page, server }) => {
    await page.addInitScript(() => {
      const w = window as unknown as { setTimeout: typeof setTimeout };
      const real = w.setTimeout.bind(window);
      w.setTimeout = ((fn: TimerHandler, ms?: number, ...rest: unknown[]) =>
        ms !== undefined && ms >= 300 && ms <= 500
          ? 0
          : real(fn, ms, ...rest)) as unknown as typeof setTimeout;
      window.BroadcastChannel = class {
        onmessage: unknown = null;
        postMessage(): void {
          // A stub channel that never answers keeps the hold on screen.
        }
        close(): void {
          // A stub channel that never answers keeps the hold on screen.
        }
        addEventListener(): void {
          // A stub channel that never answers keeps the hold on screen.
        }
        removeEventListener(): void {
          // A stub channel that never answers keeps the hold on screen.
        }
      } as unknown as typeof BroadcastChannel;
    });
    await page.goto(`${server.baseURL}/#/p/${PROJECT}/review/agents`);
    await expect(page.locator(".wait-hold")).toBeVisible();
    await shootAll(page, "locked-wait", SIZES, async () => {
      await expect(page.locator(".wait-hold")).toBeVisible();
    });
  });

  test("tab-back", async ({ context, server }) => {
    const tabA: Page = await context.newPage();
    await tabA.goto(`${server.baseURL}/#/p/${PROJECT}/live`);
    await expectLocked(tabA, "no_key");
    const tabB: Page = await context.newPage();
    await tabB.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(tabB);
    await expectOtherTabBack(tabB);
    await shootAll(tabB, "tab-back");
  });

  test("stopped", async ({ page, server }) => {
    test.setTimeout(120_000);
    await page.clock.install();
    await page.goto(linkFor(server.baseURL, server.code, `/p/${PROJECT}/review/agents`));
    await expectUnlocked(page);
    await server.stop();
    for (let i = 0; i < 8; i++) {
      if ((await gateHeading(page, "stopped").count()) > 0) break;
      await page.clock.runFor(10_000);
      await page.waitForTimeout(250);
    }
    await expect(gateHeading(page, "stopped")).toBeVisible();
    await expect(page.getByRole("button", { name: en.stopped_try_now })).toBeVisible();
    await shootAll(page, "stopped");
  });
});

async function firstRunPage(context: BrowserContext, baseURL: string, code: string) {
  const page = await context.newPage();
  await page.goto(linkFor(baseURL, code, "/"));
  return page;
}

test.describe("first run", () => {
  test.use({ fixture: "firstrun" });
  test("firstrun", async ({ context, server }) => {
    const page = await firstRunPage(context, server.baseURL, await server.mint(PROJECT));
    await expect(gateHeading(page, "firstrun")).toBeVisible();
    await shootAll(page, "firstrun", SIZES, async () => {
      await expect(gateHeading(page, "firstrun")).toBeVisible({ timeout: 1000 });
    });
  });
});

test.describe("first run failed", () => {
  test.use({ fixture: "firstrun_failed" });

  test("firstrun-failed", async ({ context, server }) => {
    const page = await firstRunPage(context, server.baseURL, await server.mint(PROJECT));
    await expect(page.getByRole("alert")).toContainText(en.fr_fail_h, { timeout: 20_000 });
    await shootAll(page, "firstrun-failed");
  });

  test("firstrun-retry", async ({ context, server }) => {
    const page = await firstRunPage(context, server.baseURL, await server.mint(PROJECT));
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 20_000 });
    const third = page.getByRole("list", { name: en.fr_h }).getByRole("listitem").nth(2);
    await expect(third).toContainText(en.fr_now, { timeout: 20_000 });
    await shootAll(page, "firstrun-retry");
  });
});
