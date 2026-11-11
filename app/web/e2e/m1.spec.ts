/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The M1 screens on the fixture scenarios. Each one goes through axe at 375 and 1440, light and
 * dark, and carries the checks that prove the page is in the state its scenario names: the
 * sidebar footer at rest and with problems, the updates-stopped notice, the More history card,
 * first run counting, running and retrying, the store_newer gate and the project picker placeholder.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, gateHeading, linkFor } from "./gate";
import { expect, test } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const COMBOS = [
  { width: 375, theme: "light" },
  { width: 375, theme: "dark" },
  { width: 1440, theme: "light" },
  { width: 1440, theme: "dark" },
] as const;
const PROJECT = "tidewater-reporting";

async function axeAllCombos(page: Page, label: string): Promise<string[]> {
  const problems: string[] = [];
  for (const { width, theme } of COMBOS) {
    await page.setViewportSize({ width, height: 800 });
    await page.emulateMedia({ colorScheme: theme });
    // Colours transition on a theme change, and axe would read them half way.
    await page.waitForTimeout(500);
    const result = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
    for (const v of result.violations) {
      problems.push(
        `${label} ${String(width)} ${theme} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
      );
    }
  }
  return problems;
}

/*
 * The footer's date text depends on the clock. A time on the same day as the server's time shows
 * as "7:04 AM", and a time on another day carries the date, "September 30, 12:59 PM". The fixture
 * scenarios count back from the real clock, so a run just after midnight gives other text than a
 * run at noon. These two sets of times pin the clock instead, and the tests below read them in
 * UTC. SHORT keeps every time on the server's day. LONGEST puts every time on the day before,
 * with September, the longest month name, a two-digit day, and a two-digit hour and minute.
 */
const SHORT_TIMES = {
  now: "2026-10-01T09:00:00Z",
  stamp: "2026-10-01T07:04:00Z",
  day: "2026-09-30",
};
const LONGEST_TIMES = {
  now: "2026-10-01T09:00:00Z",
  stamp: "2026-09-30T12:59:00Z",
  day: "2026-09-30",
};

type Json = Record<string, unknown>;

/** Rewrites one answer in flight, so the page reads the times this test chose. */
async function patch(page: Page, url: RegExp, change: (body: Json) => void): Promise<void> {
  await page.route(url, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Json;
    change(body);
    await route.fulfill({ response, json: body });
  });
}

/** Pins every time the footer and the More card print. Call it before the first goto. */
async function pinTimes(page: Page, times: typeof LONGEST_TIMES): Promise<void> {
  await patch(page, /\/api\/app(\?|$)/, (body) => {
    const history = body.history as Json;
    body.server_time = times.now;
    if (body.as_of !== null) body.as_of = times.stamp;
    if (history.oldest !== null) history.oldest = `${times.day}T14:20:00Z`;
    if (history.last_backup !== null) history.last_backup = times.stamp;
    const failed = history.backup_failed as Json | null;
    if (failed !== null) failed.at = times.stamp;
    const passError = history.pass_error as Json | null;
    if (passError !== null) passError.since = times.stamp;
  });
  await patch(page, /\/api\/prices(\?|$)/, (body) => {
    body.as_of = times.day;
  });
}

interface FooterRow {
  text: string;
  rows: number;
  clipped: boolean;
}

/** Each footer line's text, how many text rows it takes, and whether the box cuts any of it off. */
async function footerRows(page: Page): Promise<FooterRow[]> {
  return page.locator(".sidebar-footer-line").evaluateAll((els) =>
    els.map((el) => ({
      text: (el.textContent ?? "").trim(),
      // Every line is at least 32 px tall, so its height no longer counts rows. Count the distinct
      // tops of the line's text instead.
      rows: (() => {
        const tops = new Set<number>();
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node !== null; node = walker.nextNode()) {
          if ((node.textContent ?? "").trim() === "") continue;
          const range = document.createRange();
          range.selectNodeContents(node);
          for (const rect of range.getClientRects()) tops.add(Math.round(rect.top));
        }
        return tops.size;
      })(),
      clipped: el.scrollWidth > el.clientWidth || el.scrollHeight > el.clientHeight,
    })),
  );
}

async function noHorizontalScroll(page: Page): Promise<void> {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

test.describe("footer at rest", () => {
  test.use({ timezoneId: "UTC", locale: "en-US" });

  test("shows six muted lines with no live region and passes axe", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    const lines = page.locator(".sidebar-footer-line");
    await expect(lines).toHaveCount(6);
    await expect(lines.nth(1)).toHaveText(/^History since /);
    await expect(lines.nth(3)).toHaveText(/^Prices as of /);
    await expect(lines.nth(4)).toHaveText(en.eo_ft_off);
    await expect(lines.nth(5)).toHaveText(`Claude Code 2.1.310`);
    await expect(page.locator(".sidebar-footer [role], .sidebar-footer a")).toHaveCount(0);
    await expect(page.locator(".stopped-notice")).toHaveCount(0);
    expect(await axeAllCombos(page, "footer")).toEqual([]);
  });

  test("keeps every line whole with the longest dates", async ({ page, server }) => {
    await pinTimes(page, LONGEST_TIMES);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    await expect(page.locator(".sidebar-footer-line")).toHaveCount(6);
    const rows = await footerRows(page);
    expect(rows.map((r) => r.text)).toEqual([
      "Updated September 30, 12:59 PM",
      "History since September 30",
      "Last backup September 30, 12:59 PM",
      "Prices as of September 30",
      en.eo_ft_off,
      "Claude Code 2.1.310",
    ]);
    expect(rows.filter((r) => r.clipped)).toEqual([]);
    expect(Math.max(...rows.map((r) => r.rows))).toBeLessThanOrEqual(2);
  });
});

test.describe("footer with problems", () => {
  test.use({ fixture: "history_problem", timezoneId: "UTC", locale: "en-US" });

  test("adds the unreadable line, replaces the backup line and keeps the lines on one row", async ({
    page,
    server,
  }) => {
    await pinTimes(page, SHORT_TIMES);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    const lines = page.locator(".sidebar-footer-line");
    await expect(lines).toHaveCount(7);
    await expect(lines.nth(0)).toHaveText(/Couldn't read 3 files$/);
    await expect(lines.nth(3)).toHaveText("Backup failed at 7:04 AM");
    await expect(page.locator(".sidebar-footer")).not.toContainText(/Last backup/);
    const rows = await footerRows(page);
    expect(rows.filter((r) => r.clipped || r.rows !== 1)).toEqual([]);
    expect(await axeAllCombos(page, "footer problem")).toEqual([]);
  });

  test("keeps the backup line whole, on two rows, with the longest date", async ({
    page,
    server,
  }) => {
    await pinTimes(page, LONGEST_TIMES);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    await expect(page.locator(".sidebar-footer-line")).toHaveCount(7);
    const rows = await footerRows(page);
    const backup = rows.find((r) => r.text.startsWith("Backup failed"));
    expect(backup).toEqual({
      text: "Backup failed at September 30, 12:59 PM",
      rows: 2,
      clipped: false,
    });
    expect(rows.filter((r) => r.clipped)).toEqual([]);
    expect(Math.max(...rows.map((r) => r.rows))).toBeLessThanOrEqual(2);
    expect(await axeAllCombos(page, "footer problem longest")).toEqual([]);
  });

  test("More at 375 opens with the history card and the reasons", async ({ page, server }) => {
    await pinTimes(page, LONGEST_TIMES);
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/more"));
    const card = page.getByRole("region", { name: en.more_hist_h });
    await expect(card).toBeVisible();
    await expect(card.getByRole("heading", { level: 3 })).toHaveCount(2);
    await expect(card).toContainText(en.mb_backup_no_space);
    await expect(card).toContainText(en.mb_unread_b);
    await expect(card.locator("dt")).toHaveText([
      en.more_l_updated,
      en.more_l_since,
      en.more_l_backup,
      en.more_l_prices,
      en.more_l_editing,
    ]);
    const first = await page.locator("main section").first().getAttribute("aria-labelledby");
    expect(first).toBe("history-card-title");
    await noHorizontalScroll(page);
    expect(await axeAllCombos(page, "more history problem")).toEqual([]);
  });
});

test.describe("More history card at rest", () => {
  test("lists five rows with no findings", async ({ page, server }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/more"));
    const card = page.getByRole("region", { name: en.more_hist_h });
    await expect(card.locator("dt")).toHaveCount(5);
    await expect(card.getByRole("heading", { level: 3 })).toHaveCount(0);
    expect(await axeAllCombos(page, "more history")).toEqual([]);
  });
});

test.describe("prices from the bundled copy", () => {
  test.use({ fixture: "prices_bundled" });

  test("names the source in the footer", async ({ page, server }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expect(page.locator(".sidebar-footer")).toContainText(
      fill(en.ft_prices_bundled, { d: "October 20" }),
    );
  });
});

test.describe("updates stopped", () => {
  test.use({ fixture: "stopped", timezoneId: "UTC", locale: "en-US" });

  test("the notice shows above the page at both widths, on every page", async ({
    page,
    server,
  }) => {
    await pinTimes(page, LONGEST_TIMES);
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    for (const width of [1440, 375]) {
      await page.setViewportSize({ width, height: 800 });
      const notice = page.locator(".stopped-notice");
      await expect(notice).toHaveCount(1);
      await expect(notice).toContainText(/^Updates stopped at September 30, 12:59 PM /);
      await expect(notice).toContainText("/work/.claude/projects");
      const cut = await notice.evaluate((el) => el.scrollWidth > el.clientWidth);
      expect(cut).toBe(false);
      await noHorizontalScroll(page);
    }
    await page.goto(
      linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/review/agents`),
    );
    await expect(page.locator(".stopped-notice")).toHaveCount(1);
    await page.setViewportSize({ width: 375, height: 800 });
    await page.getByRole("link", { name: en.nav_more }).click();
    await expect(page.locator(".stopped-notice")).toHaveCount(1);
    expect(await axeAllCombos(page, "updates stopped")).toEqual([]);
  });
});

test.describe("first run counting", () => {
  test.use({ fixture: "firstrun_counting" });

  test("says Counting files with no bar", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
    await expect(gateHeading(page, "firstrun")).toBeVisible();
    await expect(page.getByText(en.fr_counting)).toBeVisible();
    await expect(page.getByRole("progressbar")).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText("0 of 0");
    expect(await axeAllCombos(page, "first run counting")).toEqual([]);
  });
});

test.describe("first run running", () => {
  test.use({ fixture: "firstrun" });

  test("counts first, then shows the bar by size", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
    await expect(gateHeading(page, "firstrun")).toBeVisible();
    await expect(page.getByRole("progressbar")).toHaveAttribute(
      "aria-valuetext",
      /^\d+\.\d of 82\.0 MB$/,
      { timeout: 20_000 },
    );
    expect(await axeAllCombos(page, "first run progress")).toEqual([]);
  });
});

test.describe("first run retry", () => {
  test.use({ fixture: "firstrun_retry" });

  test("keeps the error, the size and the next try time", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText("/work/.claude/projects/tidewater-reporting/9f2c.jsonl");
    await expect(alert).toContainText(/Next try at \d{1,2}:\d{2}\s?[AP]M/);
    await expect(alert).toContainText(en.fr_fail_fix2);
    await expect(page.getByText("0.8 of 2.0 GB")).toBeVisible();
    await noHorizontalScroll(page);
    expect(await axeAllCombos(page, "first run retry")).toEqual([]);
  });
});

test.describe("store_newer", () => {
  test.use({ fixture: "store_newer" });

  test("shows the gate sentence, the next step and the command", async ({ page, server }) => {
    await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
    const heading = page.getByRole("heading", { level: 1, name: en.sn_h });
    await expect(heading).toBeFocused();
    await expect(page.getByText(en.sn_next)).toBeVisible();
    await expect(page.getByText("/bartab-preview")).toBeVisible();
    await expect(page.getByRole("button", { name: en.lk_copy })).toBeVisible();
    expect(await axeAllCombos(page, "store newer")).toEqual([]);
  });
});

test.describe("picker placeholder", () => {
  test("shows Pick a project in the Select and Bar Tab in the top bar", async ({
    page,
    server,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(page.getByRole("dialog", { name: en.pk_h })).toBeVisible();
    await expect(page.locator(".sidebar .select-value")).toHaveText(en.pk_placeholder);
    await expect(page.locator(".sidebar .select-value")).toHaveAttribute(
      "data-placeholder",
      "true",
    );
    await page.setViewportSize({ width: 375, height: 812 });
    await expect(page.locator(".top-bar-title")).toHaveText(en.product);
    await expect(page.locator(".top-bar-project")).toHaveText(new RegExp(en.pk_placeholder));
    expect(await axeAllCombos(page, "picker placeholder")).toEqual([]);
  });
});
