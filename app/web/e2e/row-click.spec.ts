/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Whole-row targets on the Agents and Sessions tables, against the real server on the demo build
 * (`--demo --no-price-fetch --test-clock`). A click on an empty part of a row (the Runs or Cost
 * cell) does what the name link does. A Cmd or Ctrl click and a middle click open a new tab and
 * leave this one where it is. Dragging across text to select it never navigates. The row has no
 * role and no tabindex, and the name link is its one Tab stop. The hover shots of an Agents row
 * go to the folder in `ROWCLICK_SHOTS`, when it is set.
 */
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { expectUnlocked, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const PROJECT = "tidewater-reporting";

const test = base.extend<object, { demo: Server }>({
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
});

async function openAt(
  page: Page,
  server: Server,
  path: string,
  size: { width: number; theme?: "light" | "dark" },
): Promise<void> {
  await page.setViewportSize({ width: size.width, height: 900 });
  await page.emulateMedia({ colorScheme: size.theme ?? "light" });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

const agents = `/p/${PROJECT}/review/agents?range=30d`;
const sessions = `/p/${PROJECT}/review/sessions?range=30d`;

/** Where a mouse press should land to be on the cell and clear of its content. */
async function emptySpot(cell: Locator): Promise<{ x: number; y: number }> {
  const box = await cell.boundingBox();
  if (box === null) throw new Error("the cell has no box");
  return { x: box.x + box.width - 3, y: box.y + 3 };
}

for (const kind of ["Agents", "Sessions"] as const) {
  const path = kind === "Agents" ? agents : sessions;
  const rowOf = (page: Page): Locator =>
    kind === "Agents"
      ? page.locator("tr[data-agent='builder']")
      : page.locator("tbody tr.review-row").first();
  const linkOf = (page: Page): Locator => rowOf(page).locator("a[href]").first();
  const opened = (url: string): boolean =>
    kind === "Agents" ? url.includes("agent=") : /\/review\/sessions\/[^/?]+/.test(url);

  test.describe(`${kind} rows`, () => {
    test("a click on an empty cell opens what the name link opens", async ({ page, demo }) => {
      await openAt(page, demo, path, { width: 1440 });
      const cell = rowOf(page).locator("td").last();
      await expect(cell).toBeVisible();
      const spot = await emptySpot(cell);
      expect(opened(page.url())).toBe(false);
      await page.mouse.click(spot.x, spot.y);
      await expect.poll(() => opened(page.url())).toBe(true);
    });

    test("a click on the Runs cell opens it too", async ({ page, demo }) => {
      await openAt(page, demo, path, { width: 1440 });
      const cell = rowOf(page).locator("td.num, td.review-end").first();
      await expect(cell).toBeVisible();
      await cell.click();
      await expect.poll(() => opened(page.url())).toBe(true);
    });

    test("a Cmd or Ctrl click opens a new tab and leaves this one where it is", async ({
      page,
      context,
      demo,
    }) => {
      await openAt(page, demo, path, { width: 1440 });
      const before = page.url();
      const cell = rowOf(page).locator("td").last();
      const popup = context.waitForEvent("page");
      await cell.click({ modifiers: ["ControlOrMeta"], position: { x: 3, y: 3 } });
      const tab = await popup;
      await expect.poll(() => tab.url()).toContain(kind === "Agents" ? "agent=" : "/sessions/");
      expect(page.url()).toBe(before);
      await tab.close();
    });

    test("a middle click opens a new tab and leaves this one where it is", async ({
      page,
      context,
      demo,
    }) => {
      await openAt(page, demo, path, { width: 1440 });
      const before = page.url();
      const spot = await emptySpot(rowOf(page).locator("td").last());
      const popup = context.waitForEvent("page");
      await page.mouse.click(spot.x, spot.y, { button: "middle" });
      const tab = await popup;
      await expect.poll(() => tab.url()).toContain(kind === "Agents" ? "agent=" : "/sessions/");
      expect(page.url()).toBe(before);
      await tab.close();
    });

    test("dragging across text to select it does not navigate", async ({ page, demo }) => {
      await openAt(page, demo, path, { width: 1440 });
      const before = page.url();
      const text = rowOf(page).locator(kind === "Agents" ? ".review-agents-src" : ".review-branch");
      const box = await text.boundingBox();
      if (box === null) throw new Error("no text box");
      const y = box.y + box.height / 2;
      await page.mouse.move(box.x + 1, y);
      await page.mouse.down();
      await page.mouse.move(box.x + Math.min(box.width - 2, 60), y, { steps: 6 });
      await page.mouse.up();
      await page.waitForTimeout(300);
      expect(page.url()).toBe(before);
    });

    test("the name link is the one Tab stop and the row has no role or tabindex", async ({
      page,
      demo,
    }) => {
      await openAt(page, demo, path, { width: 1440 });
      const row = rowOf(page);
      await expect(row).not.toHaveAttribute("role", /.*/);
      await expect(row).not.toHaveAttribute("tabindex", /.*/);
      expect(await row.locator("[tabindex]:not(a)").count()).toBe(0);
      expect(await row.locator("a[href]").count()).toBe(1);
      await expect(linkOf(page)).toBeVisible();
      const cursor = await row
        .locator("td")
        .last()
        .evaluate((el) => getComputedStyle(el).cursor);
      expect(cursor).toBe("pointer");
    });
  });
}

const shots = process.env.ROWCLICK_SHOTS;
if (shots !== undefined && shots !== "") {
  for (const width of [1440, 375] as const) {
    for (const theme of ["light", "dark"] as const) {
      test(`hover shot of an Agents row at ${String(width)}, ${theme}`, async ({ page, demo }) => {
        mkdirSync(shots, { recursive: true });
        await openAt(page, demo, agents, { width, theme });
        const row = page.locator("tr[data-agent='builder']");
        await expect(row).toBeVisible();
        await row
          .locator("td")
          .last()
          .hover({ position: { x: 3, y: 3 } });
        await page.mouse.move(0, 0);
        await row
          .locator("td")
          .last()
          .hover({ position: { x: 3, y: 3 } });
        await page
          .locator(".review-table-well")
          .first()
          .screenshot({
            path: join(shots, `agents-row-hover-${String(width)}-${theme}.png`),
          });
      });
    }
  }
}
