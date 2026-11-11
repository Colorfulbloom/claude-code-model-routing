/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The help components in a real browser (m5-build.md section 4). jsdom has no layout, so it cannot
 * hit-test the ::after layer that stretches a Tile link over the tile, cannot place a popover and
 * cannot cross a media query. These checks run on the component sheet's closed cells, which are
 * real triggers with real overlays behind them. The sheet also draws open panels in place, so a
 * real overlay is told apart by data-rac, which React Aria sets on its own elements.
 */
import type { Locator, Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const sheetUrl = (): string => {
  const url = process.env.BARTAB_E2E_SHEET_URL;
  if (url === undefined) throw new Error("BARTAB_E2E_SHEET_URL is not set");
  return url;
};

const cell = (component: string, state: string) =>
  `[data-component="${component}"][data-state="${state}"]`;

async function open(page: Page, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(sheetUrl());
  await page.waitForSelector("[data-component]");
}

/** The one real overlay dialog on the page. */
const overlay = (page: Page): Locator => page.locator('[data-rac][role="dialog"]');

const hash = (page: Page): Promise<string> => page.evaluate(() => window.location.hash);

/**
 * A real mouse click at the centre of an element. Playwright's own click refuses an element that
 * another element covers, and the link's ::after layer covers the value on purpose, so the click
 * goes to the point and the browser decides what it hits.
 */
async function clickAt(page: Page, target: Locator): Promise<void> {
  await target.scrollIntoViewIfNeeded();
  const box = await target.boundingBox();
  if (box === null) throw new Error("no box to click");
  await page.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
}

test.describe("Tile link with help", () => {
  const tile = cell("Tile", "link-help");

  test("a click on the value follows the link", async ({ page }) => {
    await open(page, 1440);
    await page.evaluate(() => {
      window.location.hash = "";
    });
    await clickAt(page, page.locator(`${tile} .tile-value`));
    expect(await hash(page)).toBe("#cache");
  });

  test("a click on the delta and on the bare part of the tile follows the link too", async ({
    page,
  }) => {
    await open(page, 1440);
    await clickAt(page, page.locator(`${tile} .tile-delta`));
    expect(await hash(page)).toBe("#cache");
    await page.evaluate(() => {
      window.location.hash = "";
    });
    await page.locator(`${tile} .tile`).scrollIntoViewIfNeeded();
    const box = await page.locator(`${tile} .tile`).boundingBox();
    if (box === null) throw new Error("no tile box");
    await page.mouse.click(box.x + 20, box.y + box.height - 8);
    expect(await hash(page)).toBe("#cache");
  });

  test("a click on the ? opens help and does not navigate", async ({ page }) => {
    await open(page, 1440);
    await page.evaluate(() => {
      window.location.hash = "";
    });
    await page.locator(`${tile} .help-button`).click();
    await expect(overlay(page)).toBeVisible();
    await expect(overlay(page)).toHaveAccessibleName("Read from cache");
    expect(await hash(page)).toBe("");
  });

  test("Tab reaches the link and then the ?, and the ring is on the whole tile", async ({
    page,
  }) => {
    await open(page, 1440);
    await page.keyboard.press("Tab");
    await page.locator(`${tile} .tile-link-label`).focus();
    const ring = await page.locator(`${tile} .tile`).evaluate((el) => {
      const style = getComputedStyle(el);
      return { width: style.outlineWidth, style: style.outlineStyle };
    });
    expect(ring).toEqual({ width: "2px", style: "solid" });
    await page.keyboard.press("Tab");
    await expect(page.locator(`${tile} .help-button`)).toBeFocused();
    await page.keyboard.press("Shift+Tab");
    await expect(page.locator(`${tile} .tile-link-label`)).toBeFocused();
  });

  test("the tile ring shows for the link's focus and not for the ?'s", async ({ page }) => {
    await open(page, 1440);
    const ring = (selector: string) =>
      page.locator(selector).evaluate((el) => {
        const style = getComputedStyle(el);
        return { width: style.outlineWidth, style: style.outlineStyle };
      });
    await page.keyboard.press("Tab");
    await page.locator(`${tile} .tile-link-label`).focus();
    expect(await ring(`${tile} .tile`)).toEqual({ width: "2px", style: "solid" });
    await page.keyboard.press("Tab");
    await expect(page.locator(`${tile} .help-button`)).toBeFocused();
    // The "?" has its own ring, and the tile has none.
    expect((await ring(`${tile} .tile`)).style).toBe("none");
    expect(await ring(`${tile} .help-button`)).toEqual({ width: "2px", style: "solid" });
  });
});

test.describe("help panel", () => {
  const trigger = `${cell("HelpButton", "closed")} .help-button`;

  test("opens a popover under the trigger at 1440, and Esc closes it and returns focus", async ({
    page,
  }) => {
    await open(page, 1440);
    await page.locator(trigger).click();
    const dialog = overlay(page);
    await expect(dialog).toBeVisible();
    await expect(dialog).toBeFocused();
    const box = await dialog.boundingBox();
    const at = await page.locator(trigger).boundingBox();
    expect(box).not.toBeNull();
    expect(at).not.toBeNull();
    if (box === null || at === null) return;
    // Under the trigger, or above it when there is no room below. Never on top of it.
    const below = box.y >= at.y + at.height - 1;
    const above = box.y + box.height <= at.y + 1;
    expect(below || above).toBe(true);
    expect(box.width).toBeLessThanOrEqual(361);
    await expect(dialog.getByRole("button", { name: "Close" })).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(trigger)).toBeFocused();
  });

  test("closes on a click outside", async ({ page }) => {
    await open(page, 1440);
    await page.locator(trigger).click();
    await expect(overlay(page)).toBeVisible();
    await page.mouse.click(1400, 20);
    await expect(overlay(page)).toHaveCount(0);
  });

  test("opens a bottom tray with a grip and a Close button at 375", async ({ page }) => {
    await open(page, 375);
    await page.locator(trigger).click();
    const dialog = overlay(page);
    await expect(dialog).toBeVisible();
    const tray = page.locator(".hp-tray[data-rac]");
    await expect(tray).toBeVisible();
    // Let the 160 ms slide finish before measuring.
    await page.waitForTimeout(400);
    const box = await tray.boundingBox();
    expect(box).not.toBeNull();
    if (box === null) return;
    expect(Math.round(box.x)).toBe(0);
    expect(Math.round(box.width)).toBe(375);
    expect(Math.round(box.y + box.height)).toBe(900);
    await expect(tray.locator(".hp-grip")).toBeVisible();
    await dialog.getByRole("button", { name: "Close" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(trigger)).toBeFocused();
  });

  test("closes when the window crosses 720 px while open, and reopens as the other layout", async ({
    page,
  }) => {
    await open(page, 1440);
    await page.locator(trigger).click();
    await expect(overlay(page)).toBeVisible();
    await page.setViewportSize({ width: 600, height: 900 });
    await expect(overlay(page)).toHaveCount(0);
    await expect(page.locator(trigger)).toHaveAttribute("aria-expanded", "false");
    await page.locator(trigger).click();
    await expect(page.locator(".hp-tray[data-rac]")).toBeVisible();
  });

  test("the tray does not slide when reduced motion is on", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await open(page, 375);
    await page.locator(trigger).click();
    const tray = page.locator(".hp-tray[data-rac]");
    await expect(tray).toBeVisible();
    expect(await tray.evaluate((el) => getComputedStyle(el).animationName)).toBe("none");
  });

  test("the slide is declared only for people who allow motion", async ({ page }) => {
    await open(page, 375);
    const guarded = await page.evaluate(() => {
      const found: string[] = [];
      const visit = (rules: CSSRuleList, inMotion: boolean) => {
        for (const rule of Array.from(rules)) {
          if (rule instanceof CSSMediaRule) {
            visit(rule.cssRules, inMotion || rule.conditionText.includes("no-preference"));
          } else if (rule instanceof CSSStyleRule && rule.cssText.includes("hp-tray-in")) {
            found.push(inMotion ? "guarded" : "bare");
          }
        }
      };
      for (const sheet of Array.from(document.styleSheets)) visit(sheet.cssRules, false);
      return found;
    });
    expect(guarded).toEqual(["guarded"]);
  });
});

test.describe("search field", () => {
  const field = cell("SearchField", "typed");

  test("keeps focus after Escape clears it, and the sample list shows every rule", async ({
    page,
  }) => {
    await open(page, 1440);
    const input = page.locator(`${field} input`);
    await expect(input).toHaveValue("cache");
    await input.focus();
    await page.keyboard.press("Escape");
    await expect(input).toHaveValue("");
    await expect(input).toBeFocused();
    await expect(page.locator(`${field} li`)).toHaveCount(3);
  });

  test("marks matches with mark elements and shows a count that is not live", async ({ page }) => {
    await open(page, 1440);
    await expect(page.locator(`${field} mark`)).toHaveCount(2);
    const count = page.locator(`${field} .search-count`);
    await expect(count).toHaveText("2 of 3 rules");
    expect(await count.evaluate((el) => el.closest("[aria-live], [role='status']") === null)).toBe(
      true,
    );
  });
});
