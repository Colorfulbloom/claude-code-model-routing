/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Summary and Sessions against the real server on the demo build (`--demo --test-clock`, T is
 * October 30, 2026 at 6 PM in New York). Four kinds of check.
 *
 * Matrix. Each state (Summary on 30 days, Today, All and 12 months, Sessions, and the loading and
 * error forms of both) renders at 320, 375 and 1440, light and dark, with axe and no sideways
 * scroll. A forced-colours and a reduced-motion pass check the same two pages.
 *
 * Keyboard. With the keyboard only, at 375 and 1440, the person changes the range, pages the
 * cost chart back, opens All sessions and shows more. Each step asserts focus and the visible text.
 *
 * Exact text. The scope bar, the chart image's name, each pager end's description and the route
 * status after a range change are asserted from the string deck, since VoiceOver waits for M9.
 *
 * Empty range. The data clock moves past the last session, so Today and 7 days are empty.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { rmSync } from "node:fs";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const PROJECT_NAME = "Tidewater reporting";
const WIDTHS = [320, 375, 1440] as const;
const THEMES = ["light", "dark"] as const;
const THIRTY_DAY_IMAGE = fill(en.ch_img_day, {
  window: fill(en.ch_win_span, { start: "October 1", end: "October 30" }),
  total: "$319.62",
  model: "Fable 5.1",
});

/** One demo server for each worker. Every test mints its own code, so tabs never share keys. */
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

/** Opens the app unlocked, then moves to a Review route by hash, the way a link does. */
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
  await goTo(page, path);
}

async function goTo(page: Page, path: string): Promise<void> {
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

const summary = (range: string): string => `/p/${PROJECT}/review/summary?range=${range}`;
const sessions = (range: string): string => `/p/${PROJECT}/review/sessions?range=${range}`;

async function problems(page: Page, label: string, width: number): Promise<string[]> {
  const found: string[] = [];
  const axe = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  for (const v of axe.violations) {
    found.push(`${label} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  }
  const overflow = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth,
  }));
  if (width <= 375 && overflow.sw > overflow.cw) {
    found.push(`${label} scrolls sideways, ${overflow.sw} > ${overflow.cw}`);
  }
  return found;
}

/** Presses Tab until the locator holds focus, so a walk fails with its step and not a timeout. */
async function tabTo(page: Page, target: Locator, max = 60): Promise<void> {
  for (let i = 0; i < max; i++) {
    await page.keyboard.press("Tab");
    if (await target.evaluate((el) => el === document.activeElement).catch(() => false)) return;
  }
  throw new Error(`Tab never reached ${String(target)} in ${String(max)} presses`);
}

const status = (page: Page): Locator => page.locator("div.sr-only[role='status']");

// ---- matrix ----------------------------------------------------------------------------------

interface State {
  name: string;
  path: string;
  /** Sets up routes before the page moves, for the loading and error forms. */
  before?: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
}

const never = async (page: Page, glob: string): Promise<void> => {
  await page.route(glob, () => {
    // Never answers, so the cards stay on their bones.
  });
};

const fail = async (page: Page, glob: string): Promise<void> => {
  await page.route(glob, (route) =>
    route.fulfill({ status: 500, body: JSON.stringify({ code: "unexpected", path: null }) }),
  );
};

const STATES: State[] = [
  {
    name: "summary 30 days",
    path: summary("30d"),
    ready: async (page) => {
      await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
      await expect(page.getByRole("heading", { name: en.mc_h })).toBeVisible();
    },
  },
  {
    name: "summary today",
    path: summary("today"),
    ready: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: en.ch_h_hour })).toBeVisible();
      await expect(page.getByRole("img", { name: /^Bar chart of cost per hour/ })).toBeVisible();
    },
  },
  {
    name: "summary all",
    path: summary("all"),
    ready: async (page) => {
      await expect(page.getByRole("img", { name: /^Bar chart of cost per/ })).toBeVisible();
      await expect(page.getByRole("button", { name: en.pager_prev })).toHaveCount(0);
    },
  },
  {
    name: "summary 12 months",
    path: summary("12m"),
    ready: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: en.ch_h_month })).toBeVisible();
      await expect(page.getByText(en.ch_none_later)).toBeVisible();
    },
  },
  {
    name: "sessions",
    path: sessions("30d"),
    ready: async (page) => {
      await expect(page.getByRole("table", { name: en.ss_h })).toBeVisible();
      await expect(page.getByRole("button", { name: "Show 3 more" })).toBeVisible();
    },
  },
  {
    name: "summary loading",
    path: summary("30d"),
    before: async (page) => {
      await never(page, "**/api/summary*");
      await never(page, "**/api/cost-chart*");
    },
    ready: async (page) => {
      await expect(page.getByText("Loading cost per day")).toBeAttached();
    },
  },
  {
    name: "summary error",
    path: summary("30d"),
    before: async (page) => {
      await fail(page, "**/api/summary*");
      await fail(page, "**/api/cost-chart*");
    },
    ready: async (page) => {
      await expect(page.getByText("Couldn't load cost per day")).toBeVisible();
      await expect(page.getByText("Couldn't load model check")).toBeVisible();
    },
  },
  {
    name: "sessions loading",
    path: sessions("30d"),
    before: (page) => never(page, "**/api/sessions?*"),
    ready: async (page) => {
      await expect(page.getByText("Loading sessions")).toBeAttached();
    },
  },
  {
    name: "sessions error",
    path: sessions("30d"),
    before: (page) => fail(page, "**/api/sessions?*"),
    ready: async (page) => {
      await expect(page.getByText("Couldn't load sessions")).toBeVisible();
    },
  },
];

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    test(`every Review state passes axe at ${String(width)} wide, ${theme}`, async ({
      page,
      demo,
    }) => {
      test.setTimeout(120_000);
      await openAt(page, demo, "/", { width, theme });
      const found: string[] = [];
      for (const state of STATES) {
        await page.unrouteAll();
        await state.before?.(page);
        await goTo(page, `/p/${PROJECT}/live`);
        await goTo(page, state.path);
        await state.ready(page);
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        found.push(...(await problems(page, `${state.name} ${String(width)} ${theme}`, width)));
      }
      expect(found).toEqual([]);
    });
  }
}

test("forced colours keep the chart, the legend and the table readable", async ({ page, demo }) => {
  await openAt(page, demo, "/", { width: 1440 });
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await goTo(page, summary("30d"));
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  const wellBorder = await page
    .locator(".review-costwell")
    .evaluate((el) => getComputedStyle(el).borderTopColor);
  expect(wellBorder).not.toBe("rgba(0, 0, 0, 0)");
  // Every status chip and the share bars keep a word or a number beside them.
  await expect(page.getByText(en.status_overridden).first()).toBeVisible();
  const found = await problems(page, "summary forced colours", 1440);
  await goTo(page, sessions("30d"));
  await expect(page.getByRole("table", { name: en.ss_h })).toBeVisible();
  found.push(...(await problems(page, "sessions forced colours", 1440)));
  expect(found).toEqual([]);
});

test("reduced motion shows the same two pages with nothing that moves", async ({ page, demo }) => {
  await openAt(page, demo, "/", { width: 375 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await goTo(page, summary("30d"));
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  const found = await problems(page, "summary reduced motion", 375);
  expect(found).toEqual([]);
  const moving = await page.evaluate(() => document.getAnimations().length);
  expect(moving).toBe(0);
});

// ---- exact text ------------------------------------------------------------------------------

test("the scope bar reads as its title, its window line and the Range Select", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  await expect(page.locator(".scope-bar")).toMatchAriaSnapshot(`
    - heading "${en.nav_summary}" [level=1]
    - paragraph: "October 1 to October 30, compared with the 30 days before"
    - button "${en.rg_h} ${en.rg_30d}"
  `);
});

test("the chart's image carries the exact text, and the legend and kinds line agree with it", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  const image = page.getByRole("img", { name: THIRTY_DAY_IMAGE });
  await expect(image).toBeVisible();
  await expect(image).toHaveAccessibleName(THIRTY_DAY_IMAGE);
  const legend = page.locator(".review-legend");
  await expect(legend).toContainText("Opus 5.5 $62.61");
  await expect(legend).toContainText("Fable 5.1 $241.92");
  await expect(page.locator(".review-kinds")).toContainText(`${en.ch_kinds}`);
  await expect(page.getByRole("link", { name: en.ch_kinds_link })).toHaveAttribute(
    "href",
    `#/p/${PROJECT}/review/models?range=30d&section=kinds`,
  );
  // The legend and the Cost tile hold the same total.
  await expect(page.locator(".tiles")).toContainText("$319.62");
});

test("the pager walks back to the records start and says why each end stops", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  const tile = page.locator(".tiles .tile").first();
  await expect(tile).toContainText("$319.62");
  const later = page.getByRole("button", { name: en.pager_next, exact: true });
  await expect(later).toHaveAttribute("aria-disabled", "true");
  await expect(later).toHaveAccessibleDescription(en.ch_none_later);
  const earlierName = fill(en.ch_prev_aria, {
    window: fill(en.ch_win_span, { start: "September 1", end: "September 30" }),
  });
  const earlier = page.getByRole("button", { name: earlierName });
  await expect(earlier).toBeVisible();
  await earlier.click();
  await expect(page.locator(".pager-window")).toHaveText(
    fill(en.ch_win_span, { start: "September 1", end: "September 30" }),
  );
  await expect(page.getByRole("button", { name: en.pager_newest })).toBeVisible();
  // The tiles keep their range while the chart pages.
  await expect(tile).toContainText("$319.62");
  // One more page reaches the records start.
  await page.getByRole("button", { name: /^Show earlier costs, / }).click();
  const end = page.getByRole("button", { name: en.pager_prev, exact: true });
  await expect(end).toHaveAttribute("aria-disabled", "true");
  await expect(end).toHaveAccessibleDescription(fill(en.ch_none_earlier, { date: "August 31" }));
  await expect(page.locator(".pager-window")).toHaveText(
    fill(en.ch_win_span, { start: "August 2", end: "August 31" }),
  );
  await expect(page.getByRole("button", { name: /^Show later costs, / })).not.toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await expect(tile).toContainText("$319.62");
  await page.getByRole("button", { name: en.pager_newest }).click();
  await expect(page.getByRole("button", { name: en.pager_next, exact: true })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
});

test("a range change is said through the route status and keeps the focus on the Select", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  const select = page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` });
  await select.click();
  await page.getByRole("option", { name: new RegExp(`^${en.rg_7d}`) }).click();
  await expect(page).toHaveURL(/range=7d/);
  await expect(status(page)).toMatchAriaSnapshot(
    `- status: "${fill(en.rt_range, { range: fill(en.rg_n_days, { n: 7 }) })}"`,
  );
  await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_7d}` })).toBeFocused();
  await expect(
    page.getByText("October 24 to October 30, compared with the 7 days before"),
  ).toBeVisible();
});

test("the Summary tiles match their accessibility snapshot", async ({ page, demo }) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  // The four tiles read as text: each label, value and change against the period before. Each
  // label is followed by its "?" button, named About and the label.
  await expect(page.locator(".tiles")).toMatchAriaSnapshot(`
    - text: CostAPI-rate estimate
    - button "About Cost"
    - text: $319.62 Up 36% from $234.52 Sessions
    - button "About Sessions"
    - text: 53 Up 39% from 38 Tokens
    - button "About Tokens"
    - text: 117M Up 34% from 87.7M Read from cache
    - button "About Read from cache"
    - text: 78% Little change from 78%
  `);
});

test("the Cost per day popover stays inside the window and its dialog scrolls", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  await page.getByRole("button", { name: "About Cost per day" }).click();
  const popover = page.locator('[data-rac][role="dialog"]');
  await expect(popover).toBeVisible();
  const box = await page.locator(".hp-pop").boundingBox();
  if (box === null) throw new Error("the popover has no box");
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThanOrEqual(900);
  // The inner dialog is the part that scrolls, so a tall entry never pushes the card past the edge.
  const overflow = await popover.evaluate((el) => getComputedStyle(el).overflowY);
  expect(["auto", "scroll"]).toContain(overflow);
});

test("the Range Select lists six presets with their windows", async ({ page, demo }) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  await page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` }).click();
  await expect(page.getByRole("listbox")).toMatchAriaSnapshot(`
    - listbox:
      - option /Today/
      - option /Last 7 days/
      - option /Last 30 days/
      - option /Last 90 days/
      - option /Last 12 months/
      - option /All time/
  `);
  await expect(page.getByRole("option", { name: /^All time/ })).toContainText(
    fill(en.rg_w_all, { date: "August 31" }),
  );
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` })).toBeFocused();
});

test("a bad range in the link falls back to 30 days and replaces the URL", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("bogus"), { width: 1440 });
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
  await expect(page).toHaveURL(/range=30d/);
});

// ---- keyboard --------------------------------------------------------------------------------

for (const width of [375, 1440]) {
  test(`keyboard only at ${String(width)} wide: change the range, page the chart, open all sessions and show more`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(90_000);
    await openAt(page, demo, summary("30d"), { width });
    await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
    // The page is open, so the h1 holds focus after the route change.
    await expect(page.getByRole("heading", { level: 1, name: en.nav_summary })).toBeFocused();

    // 1. Range Select: open with Enter, choose 7 days with the arrows, focus returns to the button.
    const select = page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` });
    await tabTo(page, select);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_7d}` })).toBeFocused();
    await expect(page).toHaveURL(/range=7d/);
    await expect(status(page)).toHaveText(
      fill(en.rt_range, { range: fill(en.rg_n_days, { n: 7 }) }),
    );

    // 2. The pager: Earlier moves the chart back and keeps focus on the same button.
    const earlier = page.getByRole("button", { name: /^Show earlier costs, / });
    await tabTo(page, earlier);
    await page.keyboard.press("Enter");
    await expect(page.locator(".pager-window")).toHaveText(
      fill(en.ch_win_span, { start: "October 17", end: "October 23" }),
    );
    await expect(page.getByRole("button", { name: /^Show earlier costs, / })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator(".pager-window")).toHaveText(
      fill(en.ch_win_span, { start: "October 10", end: "October 16" }),
    );

    // 3. All sessions link on the top card opens Sessions with the range kept.
    const all = page.getByRole("link", { name: /^All \d+ sessions$/ });
    await tabTo(page, all);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/review/sessions\\?range=7d`));
    await expect(page.getByRole("heading", { level: 1, name: en.nav_sessions })).toBeFocused();
    await expect(page.getByRole("table", { name: en.ss_h })).toBeVisible();

    // 4. Over 30 days, Show more loads the last page and focus lands on its first new row.
    await goTo(page, sessions("30d"));
    const more = page.getByRole("button", { name: "Show 3 more" });
    await expect(more).toBeVisible();
    await expect(page.getByText("Showing 50 of 53")).toBeVisible();
    await tabTo(page, more);
    await page.keyboard.press("Enter");
    await expect(page.getByText(fill(en.ss_end_other, { n: 53 }))).toBeVisible();
    const rows = page.locator("tbody .review-row");
    await expect(rows).toHaveCount(53);
    // Every day header is a row of its own, so the first new row is the 51st session row.
    const index = await rows.evaluateAll((all) =>
      all.findIndex((row) => row.contains(document.activeElement)),
    );
    expect(index).toBe(50);
  });
}

test("a session row opens Session review with the range kept", async ({ page, demo }) => {
  await openAt(page, demo, sessions("7d"), { width: 1440 });
  const link = page.locator("tbody .review-link").first();
  await expect(link).toBeVisible();
  await expect(link).toHaveAttribute(
    "href",
    /#\/p\/tidewater-reporting\/review\/sessions\/[^?]+\?range=7d$/,
  );
});

test("Review links keep the range at phone width", async ({ page, demo }) => {
  await openAt(page, demo, summary("90d"), { width: 375 });
  const nav = page.getByRole("navigation", { name: en.nav_review });
  await expect(nav.getByRole("link", { name: en.nav_summary })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(nav.getByRole("link", { name: en.nav_sessions })).toHaveAttribute(
    "href",
    `#/p/${PROJECT}/review/sessions?range=90d`,
  );
  await nav.getByRole("link", { name: en.nav_sessions }).click();
  await expect(page).toHaveURL(/review\/sessions\?range=90d/);
  await expect(page.getByRole("heading", { level: 1, name: en.nav_sessions })).toBeVisible();
});

// ---- failure and empty states ------------------------------------------------------------------

test("a failed chart keeps the other cards, and Try again loads it", async ({ page, demo }) => {
  await openAt(page, demo, "/", { width: 1440 });
  let failing = true;
  await page.route("**/api/cost-chart*", (route) =>
    failing
      ? route.fulfill({ status: 500, body: JSON.stringify({ code: "unexpected", path: null }) })
      : route.continue(),
  );
  await goTo(page, summary("30d"));
  await expect(page.getByText("Couldn't load cost per day")).toBeVisible();
  await expect(page.locator(".tiles")).toContainText("$319.62");
  await expect(page.getByRole("heading", { name: en.rv_who_h })).toBeVisible();
  failing = false;
  await page.getByRole("button", { name: en.er_try }).click();
  await expect(page.getByRole("img", { name: THIRTY_DAY_IMAGE })).toBeVisible();
});

test("an empty range shows one page-level card, on Summary and on Sessions", async ({ page }) => {
  test.setTimeout(120_000);
  const server = await startServer({
    fixture: null,
    args: ["--demo", "--no-price-fetch", "--test-clock"],
  });
  try {
    await openAt(page, server, "/", { width: 1440 });
    // Move the data clock two months past the last session.
    const code = await page.evaluate(async (at) => {
      const key = sessionStorage.getItem("bartab.readKey") ?? "";
      const res = await fetch("/api/dev/clock", {
        method: "POST",
        headers: { "X-Bartab-Key": key, "Content-Type": "application/json" },
        body: JSON.stringify({ now: at }),
      });
      return res.status;
    }, "2026-12-30T22:00:00Z");
    expect(code).toBe(200);
    for (const [path, page_] of [
      [summary("7d"), "summary"],
      [sessions("7d"), "sessions"],
    ] as const) {
      await goTo(page, path);
      await expect(
        page.getByRole("heading", {
          level: 2,
          name: fill(en.em_h, { project: PROJECT_NAME, range: fill(en.rg_p_days, { n: 7 }) }),
        }),
      ).toBeVisible();
      await expect(page.getByText(/^The last one ran on October 30 at 4:48/)).toBeVisible();
      // On 7 days the "Show the last 7 days" action goes nowhere, so Open Live is the one way out.
      await expect(page.getByRole("link", { name: en.em_live })).toHaveAttribute(
        "href",
        `#/p/${PROJECT}/live`,
      );
      await expect(page.locator(".tiles")).toHaveCount(0);
      await expect(page.getByRole("table")).toHaveCount(0);
      expect(await problems(page, `empty ${page_}`, 1440)).toEqual([]);
    }
    await goTo(page, summary("today"));
    const action = page.getByRole("link", { name: en.em_a });
    await expect(action).toHaveAttribute("href", `#/p/${PROJECT}/review/summary?range=7d`);
  } finally {
    await server.stop();
    rmSync(server.dataDir, { recursive: true, force: true });
  }
});
