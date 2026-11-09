/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The gate pages. Locked for each reachable reason, server stopped, the in-page 401 path, first
 * run and its failure, and the project picker. Timers run on Playwright's clock where a spec
 * waits for the 10 second poll, so no test sleeps for real.
 */
import AxeBuilder from "@axe-core/playwright";
import type { BrowserContext, Page } from "@playwright/test";
import { en } from "../src/strings/en";
import {
  COMMAND,
  expectLocked,
  expectUnlocked,
  fill,
  gateHeading,
  linkFor,
  type Reason,
} from "./gate";
import { expect, startServer, test } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const COMBOS = [
  { width: 375, theme: "light" },
  { width: 375, theme: "dark" },
  { width: 1440, theme: "light" },
  { width: 1440, theme: "dark" },
] as const;

async function axeProblems(page: Page, label: string): Promise<string[]> {
  const result = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  return result.violations.map(
    (v) => `${label} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

/** Runs axe at 375 and 1440, light and dark, on the page as it is. */
async function axeAllCombos(page: Page, label: string): Promise<string[]> {
  const problems: string[] = [];
  for (const { width, theme } of COMBOS) {
    await page.setViewportSize({ width, height: 800 });
    await page.emulateMedia({ colorScheme: theme });
    // Colours transition on a theme change, and axe would read them half way.
    await page.waitForTimeout(500);
    problems.push(...(await axeProblems(page, `${label} ${String(width)} ${theme}`)));
  }
  return problems;
}

const reasons: {
  reason: Reason;
  open: (base: string, instance: string, code: string) => string;
}[] = [
  { reason: "no_key", open: (base) => `${base}/#/p/tidewater-reporting/review/agents` },
  { reason: "code_used", open: (base, _i, code) => linkFor(base, code) },
  { reason: "code_unknown", open: (base, i) => linkFor(base, `${i}.not-a-real-code`) },
  { reason: "server_restarted", open: (base) => linkFor(base, "00000000.not-a-real-code") },
];

test.describe("locked page", () => {
  for (const { reason, open } of reasons) {
    test(`${reason}: title, focus, axe`, async ({ page, browser, server }) => {
      if (reason === "code_used") {
        const first = await browser.newContext();
        const tab = await first.newPage();
        await tab.goto(linkFor(server.baseURL, server.code));
        await expectUnlocked(tab);
        await first.close();
      }
      await page.goto(open(server.baseURL, server.instance, server.code));
      await expectLocked(page, reason);
      await expect(page).toHaveTitle(en.title_locked);
      await expect(gateHeading(page, "locked")).toBeFocused();
      await expect(page.locator('[role="status"]').first()).toBeAttached();
      expect(await axeAllCombos(page, reason)).toEqual([]);
    });
  }

  test("Copy command puts the meta command on the clipboard and says Copied", async ({
    page,
    context,
    server,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin: server.baseURL,
    });
    await page.goto(`${server.baseURL}/#/`);
    await expectLocked(page, "no_key");
    await page.getByRole("button", { name: en.lk_copy }).click();
    await expect(page.getByText(en.cs_copied)).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(COMMAND);
    const live = page.locator('[role="status"]', { hasText: en.cs_copied });
    await expect(live).toHaveCount(1);
  });
});

async function unlockedOnClock(page: Page, base: string, code: string): Promise<void> {
  await page.clock.install();
  await page.goto(linkFor(base, code, "/p/tidewater-reporting/review/agents"));
  await expectUnlocked(page);
}

/** Moves the fake clock in 10 second steps until the stopped page shows. */
async function waitForStopped(page: Page): Promise<void> {
  for (let i = 0; i < 8; i++) {
    if ((await gateHeading(page, "stopped").count()) > 0) return;
    await page.clock.runFor(10_000);
    await page.waitForTimeout(250);
  }
  await expect(gateHeading(page, "stopped")).toBeVisible();
}

test.describe("server stopped", () => {
  test("three failures show the stopped page, Try now shows busy, a restart locks the tab", async ({
    page,
    server,
  }) => {
    await unlockedOnClock(page, server.baseURL, server.code);
    await server.stop();
    await waitForStopped(page);
    await expect(page).toHaveTitle(en.title_stopped);
    await expect(gateHeading(page, "stopped")).toBeFocused();
    await expect(
      page.getByText(new RegExp(`^${fill(en.st_last, { time: "\\d{1,2}:\\d{2}\\s?[AP]M" })}$`)),
    ).toBeVisible();
    expect(await axeAllCombos(page, "stopped")).toEqual([]);

    // Try now: a slow failing request, so the busy state can be seen.
    await page.route("**/api/**", async (route) => {
      await new Promise((done) => setTimeout(done, 600));
      await route.abort();
    });
    const tryNow = page.getByRole("button", { name: en.stopped_try_now });
    await tryNow.click();
    const busy = page.getByRole("button", { name: en.st_trying });
    await expect(busy).toHaveAttribute("aria-busy", "true");
    await expect(page.getByRole("button", { name: en.stopped_try_now })).not.toHaveAttribute(
      "aria-busy",
      "true",
    );
    await page.unroute("**/api/**");

    // A new server on the same port has a new instance, so the tab ends locked.
    const next = await startServer({ dataDir: server.dataDir, port: server.port });
    try {
      await page.getByRole("button", { name: en.stopped_try_now }).click();
      await expectLocked(page, "server_restarted");
    } finally {
      await next.stop();
    }
  });

  test("an old tab hit by a 401 after a restart, with no reload, ends locked server_restarted", async ({
    page,
    server,
  }) => {
    await unlockedOnClock(page, server.baseURL, server.code);
    await server.stop();
    const next = await startServer({ dataDir: server.dataDir, port: server.port });
    try {
      for (let i = 0; i < 4; i++) {
        if ((await gateHeading(page, "locked").count()) > 0) break;
        await page.clock.runFor(10_000);
        await page.waitForTimeout(250);
      }
      await expectLocked(page, "server_restarted");
    } finally {
      await next.stop();
    }
  });
});

async function pageWithFirstRun(
  context: BrowserContext,
  baseURL: string,
  code: string,
): Promise<Page> {
  const page = await context.newPage();
  await page.goto(linkFor(baseURL, code, "/"));
  return page;
}

test.describe("first run", () => {
  test.use({ fixture: "firstrun" });

  test("steps 1 and 2 are done, step 3 is live, then it lands on Live", async ({
    context,
    server,
  }) => {
    const page = await pageWithFirstRun(
      context,
      server.baseURL,
      await server.mint("tidewater-reporting"),
    );
    await expect(gateHeading(page, "firstrun")).toBeVisible();
    await expect(page).toHaveTitle(fill(en.title_bare, { page: en.fr_h }));
    const steps = page.getByRole("list", { name: en.fr_h }).getByRole("listitem");
    await expect(steps).toHaveCount(3);
    await expect(steps.nth(0)).toContainText(en.fr_done);
    await expect(steps.nth(1)).toContainText(en.fr_done);
    await expect(steps.nth(2)).toContainText(en.fr_now);
    await expect(steps.nth(2)).toHaveAttribute("aria-current", "step");
    const bar = page.getByRole("progressbar");
    await expect(bar).toHaveAttribute("aria-valuetext", /^\d+\.\d of 82\.0 MB$/);
    expect(await axeAllCombos(page, "first run")).toEqual([]);
    await expect(page).toHaveURL(/#\/p\/tidewater-reporting\/live$/, { timeout: 30_000 });
    await expectUnlocked(page);
    await expect(page.locator("main h1")).toHaveText(en.nav_live);
  });
});

test.describe("first run failed", () => {
  test.use({ fixture: "firstrun_failed" });

  test("the failure shows as an alert with the store line", async ({ context, server }) => {
    const page = await pageWithFirstRun(
      context,
      server.baseURL,
      await server.mint("tidewater-reporting"),
    );
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible({ timeout: 20_000 });
    await expect(alert).toContainText(en.fr_fail_h);
    await expect(alert).toContainText(
      fill(en.fr_fail_store_unwritable, { file: "/work/data/bartab/store.sqlite" }),
    );
    await expect(alert).toContainText(/Next try at \d{1,2}:\d{2}\s?[AP]M/);
    expect(await axeAllCombos(page, "first run failed")).toEqual([]);
  });

  // While a retry runs, ingest reports state "running" with retrying true and keeps the error.
  test("the finding stays while the retry runs and step 3 goes back to In progress", async ({
    context,
    server,
  }) => {
    const page = await pageWithFirstRun(
      context,
      server.baseURL,
      await server.mint("tidewater-reporting"),
    );
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 20_000 });
    const third = page.getByRole("list", { name: en.fr_h }).getByRole("listitem").nth(2);
    await expect(third).toContainText(en.fr_now, { timeout: 20_000 });
    await expect(page.getByRole("alert")).toContainText(en.fr_fail_h);
  });
});

test.describe("project picker", () => {
  test.use({ fixture: "empty" });

  test("the empty fixture shows the empty state in the picker modal", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: en.pk_h })).toBeVisible();
    await expect(page.getByText(en.pk_empty_h)).toBeVisible();
    await expect(page.getByText(en.pk_empty, { exact: true })).toBeVisible();
    await expect(page).toHaveTitle(fill(en.title_bare, { page: en.pk_h }));
    expect(await axeAllCombos(page, "picker empty")).toEqual([]);
  });
});

test.describe("project picker with projects", () => {
  test("the picker modal, the open 375 tray and the open 1440 Select pass axe", async ({
    page,
    server,
  }) => {
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: en.pk_h })).toBeVisible();
    const problems = await axeAllCombos(page, "picker modal");

    await page.goto("about:blank");
    await page.goto(linkFor(server.baseURL, await server.mint("tidewater-reporting"), "/"));
    await expectUnlocked(page);
    await page.setViewportSize({ width: 375, height: 800 });
    await page.emulateMedia({ colorScheme: "light" });
    // The button's name is the words on it, so a screen reader hears what is on screen.
    await page.getByRole("button", { name: "Tidewater Reporting", exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    for (const theme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: theme });
      await page.waitForTimeout(500);
      problems.push(...(await axeProblems(page, `tray 375 ${theme}`)));
    }
    await page.keyboard.press("Escape");

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.getByRole("button", { name: new RegExp(en.project_label) }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    for (const theme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme: theme });
      await page.waitForTimeout(500);
      problems.push(...(await axeProblems(page, `select 1440 ${theme}`)));
    }
    expect(problems).toEqual([]);
  });
});

test.describe("project picker route", () => {
  test("is a centred sheet at 1440 and a bottom tray at 375, with the h1 in focus", async ({
    page,
    server,
  }) => {
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    const dialog = page.getByRole("dialog", { name: en.pk_h });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading", { level: 1, name: en.pk_h })).toBeFocused();
    await expect(page.locator(".pk-sheet")).toBeVisible();
    await expect(page.locator("[data-shell='desktop']")).toBeVisible();
    await page.setViewportSize({ width: 375, height: 800 });
    await expect(page.locator(".pk-tray")).toBeVisible();
    await expect(page.locator(".pk-sheet")).toHaveCount(0);
  });

  test("Esc with no earlier page keeps it open", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    expect(new URL(page.url()).hash).toBe("#/");
  });

  test("picking a project opens its Live", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await page.getByRole("option", { name: /Tidewater Reporting/ }).click();
    await expect(page).toHaveURL(/#\/p\/tidewater-reporting\/live$/);
    await expect(page.locator("main h1")).toHaveText(en.nav_live);
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });
});
