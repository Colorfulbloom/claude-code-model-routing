/// <reference lib="dom" />
/// <reference types="node" />
/*
 * How Claude Code decides and the Glossary against the real server on the demo build (`--demo
 * --test-clock`, where the Claude Code the owner runs is newer than the rules, so the version gap
 * shows). Four kinds of check.
 *
 * Matrix. Each state renders at 320, 375 and 1440, light and dark, with axe and no sideways scroll
 * at phone widths. A forced-colours pass and a reduced-motion pass check the same pages and that the
 * rule's start bar survives forced colours.
 *
 * Layout. The order ladder is a row of pills at 1440 and a vertical well at 375, the setting list is
 * the page on a phone, and the search results show alone there.
 *
 * Walkthroughs from m5-build.md section 10, with the keyboard only. 1 is search, 3 is the Glossary
 * from a help "?" and Back to {page}, and 4 is the version gap from Your setup and the Why line.
 *
 * Set REF_SHOTS to a folder to save a screenshot of each matrix state, for review.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { en } from "../src/strings/en";
import type { Look } from "./a11y";
import {
  PROJECT,
  decides,
  glossary,
  goTo,
  heading2,
  openAt,
  polite,
  settingsNav,
  tabTo,
  test,
} from "./kit";
import { expect } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const WIDTHS = [320, 375, 1440] as const;
const THEMES = ["light", "dark"] as const;
const SHOTS = process.env.REF_SHOTS;

async function problems(page: Page, label: string, width: number): Promise<string[]> {
  const found: string[] = [];
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
  const axe = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  for (const v of axe.violations) {
    found.push(`${label} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  }
  const overflow = await page.evaluate(() => {
    const cw = document.documentElement.clientWidth;
    const wide = [...document.querySelectorAll("main *")]
      .filter((el) => el.getBoundingClientRect().right > cw + 0.5 && el.children.length === 0)
      .slice(0, 4)
      .map((el) => `${el.tagName.toLowerCase()}.${String(el.className)}`);
    return { sw: document.documentElement.scrollWidth, cw, wide };
  });
  if (width <= 375 && overflow.sw > overflow.cw) {
    found.push(
      `${label} scrolls sideways, ${overflow.sw} > ${overflow.cw}: ${overflow.wide.join(", ")}`,
    );
  }
  return found;
}

/** The state of the matrix: where to go, what to wait for, and what to change before it. */
interface Case {
  name: string;
  path: string;
  ready: (page: Page) => Locator;
  before?: (page: Page) => Promise<void>;
  /** What to do once it is ready, such as opening a select. */
  after?: (page: Page) => Promise<void>;
}

const DECIDES_CASES: Case[] = [
  { name: "dc-rest", path: decides(), ready: (page) => settingsNav(page) },
  {
    name: "dc-setting",
    path: decides("/promptCacheTtl"),
    ready: (page) => heading2(page, en.rg_promptCacheTtl),
  },
  {
    name: "dc-deep",
    path: decides("/effortLevel/effort-lowered-by-cap"),
    ready: (page) => page.locator(".ref-rule-on"),
  },
  {
    name: "dc-search",
    path: decides("?q=cache"),
    ready: (page) => heading2(page, /rules in \d+ settings$/),
  },
  {
    name: "dc-due",
    path: decides("?due=1"),
    ready: (page) => page.getByText(/^Showing all 84 rules/),
  },
  {
    name: "dc-duemixed",
    path: decides(),
    ready: (page) => page.getByText(/Bar Tab checked \d+ rules on an older version/),
    before: async (page) => {
      await page.route(/\/api\/rules/, async (route) => {
        const response = await route.fetch();
        const body = (await response.json()) as {
          rules?: { verified_on: { claude_version: string }; due: boolean }[];
        };
        for (const rule of (body.rules ?? []).slice(0, 6)) {
          rule.verified_on.claude_version = "2.1.310";
          rule.due = false;
        }
        await route.fulfill({ response, json: body });
      });
    },
  },
  {
    name: "dc-none",
    path: decides("?q=teleportation"),
    ready: (page) => heading2(page, /^No rules match/),
  },
  {
    name: "dc-selopen",
    path: decides(),
    ready: (page) => page.getByRole("button", { name: new RegExp(en.dc_conf_label) }),
    after: async (page) => {
      await page.getByRole("button", { name: new RegExp(en.dc_conf_label) }).click();
      await expect(page.getByRole("listbox")).toBeVisible();
    },
  },
  {
    name: "dc-loading",
    path: decides("?q=cache"),
    ready: (page) => page.locator(".ref-count-bone"),
    before: async (page) => {
      await page.route(/\/api\/rules/, async () => {
        await new Promise(() => undefined);
      });
    },
  },
  {
    name: "dc-error",
    path: decides(),
    ready: (page) => page.getByRole("heading", { name: en.dc_err_h }),
    before: async (page) => {
      await page.route(/\/api\/rules/, (route) =>
        route.fulfill({ status: 500, json: { code: "unexpected", path: null } }),
      );
    },
  },
  {
    name: "dc-gone",
    path: decides("/noSuchSetting"),
    ready: (page) => page.getByRole("heading", { name: /There's no setting called/ }),
  },
];

const GLOSSARY_CASES: Case[] = [
  { name: "ga-rest", path: glossary(), ready: (page) => heading2(page, en.gl_terms_h) },
  {
    name: "ga-deep",
    path: glossary(`/cache-write?from=${encodeURIComponent(`/p/${PROJECT}/live`)}&help=live.cache`),
    ready: (page) => page.locator(".ref-term-on"),
  },
  {
    name: "ga-item",
    path: glossary("/status-in_effect"),
    ready: (page) => page.locator(".ref-term-on"),
  },
  {
    name: "ga-search",
    path: glossary("?q=cache"),
    ready: (page) => page.getByText(/^\d+ of \d+ entries$/),
  },
  {
    name: "ga-none",
    path: glossary("?q=teleportation"),
    ready: (page) => heading2(page, /^No entries match/),
  },
  {
    name: "ga-long",
    path: glossary("/couldnt-read"),
    ready: (page) => page.locator(".ref-term-on"),
  },
  {
    name: "ga-gone",
    path: glossary("/no-such-term"),
    ready: (page) => page.getByRole("heading", { name: /There's no glossary entry called/ }),
  },
];

const CASES = [...DECIDES_CASES, ...GLOSSARY_CASES];

async function enter(page: Page, server: Server, c: Case, look: Look): Promise<void> {
  await c.before?.(page);
  await openAt(page, server, c.path, look);
  await expect(c.ready(page).first()).toBeVisible({ timeout: 15_000 });
  await c.after?.(page);
}

async function shot(page: Page, name: string, look: Look): Promise<void> {
  if (SHOTS === undefined) return;
  mkdirSync(SHOTS, { recursive: true });
  const mode = look.forced === true ? "forced" : (look.theme ?? "light");
  await page.screenshot({
    path: join(SHOTS, `${name}-${String(look.width)}-${mode}.png`),
    fullPage: true,
  });
}

test.describe("matrix", () => {
  for (const c of CASES) {
    test(`${c.name} at 320, 375 and 1440, light and dark: axe, no sideways scroll`, async ({
      page,
      demo,
    }) => {
      test.setTimeout(180_000);
      const found: string[] = [];
      for (const width of WIDTHS) {
        for (const theme of THEMES) {
          await enter(page, demo, c, { width, theme });
          await shot(page, c.name, { width, theme });
          found.push(...(await problems(page, `${c.name} ${String(width)} ${theme}`, width)));
          // A fresh page per look, so a held route or a set media never leaks into the next.
          await page.unrouteAll({ behavior: "ignoreErrors" });
        }
      }
      expect(found).toEqual([]);
    });
  }

  for (const c of CASES.filter((entry) =>
    ["dc-rest", "dc-deep", "dc-search", "ga-rest", "ga-deep"].includes(entry.name),
  )) {
    test(`${c.name} under forced colours and reduced motion passes axe`, async ({ page, demo }) => {
      test.setTimeout(120_000);
      const found: string[] = [];
      for (const width of [375, 1440]) {
        await enter(page, demo, c, { width, forced: true });
        await shot(page, c.name, { width, forced: true });
        found.push(...(await problems(page, `${c.name} ${String(width)} forced`, width)));
        await enter(page, demo, c, { width, reduced: true });
        found.push(...(await problems(page, `${c.name} ${String(width)} reduced`, width)));
      }
      expect(found).toEqual([]);
    });
  }

  test("the rule's start bar and the term's start bar survive forced colours", async ({
    page,
    demo,
  }) => {
    for (const [path, selector] of [
      [decides("/effortLevel/effort-lowered-by-cap"), ".ref-rule-on"],
      [glossary("/cache-write"), ".ref-term-on"],
    ] as const) {
      await openAt(page, demo, path, { width: 1440, forced: true });
      await expect(page.locator(selector)).toBeVisible();
      const bar = await page.locator(selector).evaluate((el) => {
        const style = getComputedStyle(el, "::before");
        return { width: style.borderInlineStartWidth, style: style.borderInlineStartStyle };
      });
      expect(bar).toEqual({ width: "3px", style: "solid" });
    }
  });
});

test.describe("layout", () => {
  test("the order ladder is a row of pills at 1440 and a vertical well at 375", async ({
    page,
    demo,
  }) => {
    // The setting is in the URL, so it stays the page when the width drops to a phone.
    await openAt(page, demo, decides("/effortLevel"), { width: 1440 });
    const ladder = page.getByRole("list", { name: en.dc_order_h });
    await expect(ladder).toBeVisible();
    await expect(ladder).toHaveCSS("display", "flex");
    const tops = await ladder
      .getByRole("listitem")
      .evaluateAll((items) => items.slice(0, 3).map((item) => item.getBoundingClientRect().top));
    expect(new Set(tops).size).toBe(1);
    await page.setViewportSize({ width: 375, height: 900 });
    await expect(ladder).toHaveCSS("display", "grid");
  });

  test("a phone shows the list as the page, a setting as its own page, and results alone", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, decides(), { width: 375 });
    await expect(settingsNav(page)).toBeVisible();
    await expect(page.locator(".ref-setting")).toHaveCount(0);
    await settingsNav(page)
      .getByRole("link", { name: /Cache lifetime/ })
      .click();
    await expect(page.locator(".ref-setting")).toBeVisible();
    await expect(settingsNav(page)).toHaveCount(0);
    await page.getByRole("link", { name: new RegExp(`Back to ${en.sf_settings}`) }).click();
    await expect(settingsNav(page).getByRole("link", { name: /Cache lifetime/ })).toBeFocused();
    await page.getByRole("searchbox", { name: en.dc_search_label }).fill("cache");
    await expect(heading2(page, /rules in \d+ settings$/)).toBeVisible();
    await expect(settingsNav(page)).toHaveCount(0);
  });

  test("Back leaves the page instead of stepping through keystrokes", async ({ page, demo }) => {
    await openAt(page, demo, decides(), { width: 1440 });
    await goTo(page, decides("/promptCacheTtl"));
    await expect(heading2(page, en.rg_promptCacheTtl)).toBeVisible();
    await page.getByRole("searchbox", { name: en.dc_search_label }).pressSequentially("cache");
    await page.goBack();
    expect(await page.evaluate(() => window.location.hash)).toBe(`#${decides()}`);
  });
});

test.describe("walkthroughs", () => {
  for (const width of [375, 1440]) {
    test(`1 search at ${String(width)}: count, one announcement, Esc, Confidence, Disclosure`, async ({
      page,
      demo,
    }) => {
      await openAt(page, demo, decides(), { width });
      await expect(page.getByRole("searchbox", { name: en.dc_search_label })).toBeVisible();
      const field = page.getByRole("searchbox", { name: en.dc_search_label });
      await tabTo(page, field);
      await expect(polite(page)).toHaveText("");
      await page.keyboard.type("cache");
      // A fast typist keeps every character, so the router never overwrites the field with an echo.
      await expect(field).toHaveValue("cache");
      await expect(page.locator(".search-count")).toHaveText(/^\d+ of 84 rules$/);
      // One announcement after typing settles, not one per key.
      await expect(polite(page)).toHaveText(/^\d+ of 84 rules shown$/, { timeout: 5_000 });
      const said = await polite(page).textContent();
      await page.keyboard.press("Escape");
      await expect(field).toBeFocused();
      await expect(field).toHaveValue("");
      await expect(page.locator(".search-count")).toHaveText("84 rules");
      await expect(polite(page)).toHaveText("84 rules shown", { timeout: 5_000 });
      expect(said).not.toBe("84 rules shown");
      // Tab reaches the Confidence select, which narrows the list.
      const select = page.getByRole("button", { name: new RegExp(en.dc_conf_label) });
      await tabTo(page, select);
      await page.keyboard.press("Enter");
      await page.getByRole("option", { name: new RegExp(`^${en.in_tested}`) }).click();
      await expect(page.locator(".search-count")).toHaveText(/^\d+ of 84 rules$/);
      // Tab reaches a rule's Disclosure, Enter opens the docs line, and its link is next.
      await page.getByRole("searchbox", { name: en.dc_search_label }).fill("");
      // A phone shows the list first, so open the first setting to reach its rules.
      if (width <= 720) await settingsNav(page).getByRole("link").first().click();
      const trigger = page.locator(".ref-docs-trigger").first();
      await tabTo(page, trigger);
      await page.keyboard.press("Enter");
      await expect(trigger).toHaveAttribute("aria-expanded", "true");
      await page.keyboard.press("Tab");
      await expect(page.locator(".ref-doclink").first()).toBeFocused();
    });

    test(`3 glossary from help at ${String(width)}: the link lands on the term, Back returns to the "?"`, async ({
      page,
      demo,
    }) => {
      await openAt(page, demo, `/p/${PROJECT}/setup`, { width });
      const trigger = page.locator('[data-help-id="setup.card"]');
      await expect(trigger).toBeVisible();
      await tabTo(page, trigger);
      await page.keyboard.press("Enter");
      const dialog = page.getByRole("dialog");
      await expect(dialog).toBeVisible();
      const link = dialog.getByRole("link", { name: "Part in the glossary" });
      await tabTo(page, link, 12);
      await page.keyboard.press("Enter");
      await expect(heading2(page, en.gl_terms_h)).toBeVisible();
      await expect(page.locator('dt[data-term-id="part"]')).toBeFocused();
      await expect(page.locator(".ref-term-on")).toBeVisible();
      const back = page.getByRole("link", { name: /Back to Your setup/ });
      await expect(back).toBeVisible();
      await tabTo(page, back);
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeVisible();
      await expect(trigger).toBeFocused();
    });
  }

  test("3 Back falls back to the h1 when the trigger is gone", async ({ page, demo }) => {
    await openAt(
      page,
      demo,
      glossary(`/part?from=${encodeURIComponent(`/p/${PROJECT}/setup`)}&help=no.such.trigger`),
      { width: 1440 },
    );
    await page.getByRole("link", { name: /Back to Your setup/ }).click();
    const h1 = page.getByRole("heading", { level: 1, name: en.su_h1 });
    await expect(h1).toBeFocused();
  });

  for (const width of [375, 1440]) {
    test(`4 version gap at ${String(width)}: the Your setup notice opens the due view, the Why line opens its rule`, async ({
      page,
      demo,
    }) => {
      await openAt(page, demo, `/p/${PROJECT}/setup`, { width });
      const link = page.getByRole("link", { name: /^Show the \d+ rules to re-check$/ });
      await expect(link).toBeVisible();
      await tabTo(page, link);
      await page.keyboard.press("Enter");
      await expect(page.getByText(/^Showing all \d+ rules/)).toBeVisible();
      expect(await page.evaluate(() => window.location.hash)).toBe(`#${decides("?due=1")}`);
      await expect(page.locator(".search-count")).toHaveText(/^\d+( of \d+)? rules$/);
      // From an item's Why line, the rule link lands on the rule, marked and focused.
      await goTo(page, `/p/${PROJECT}/setup/settings/effortLevel`);
      const rule = page.locator(".inspector-rule-link a").first();
      await expect(rule).toBeVisible();
      await expect(page.locator(".inspector-older").first()).toContainText(/Older than your/);
      await tabTo(page, rule, 120);
      await page.keyboard.press("Enter");
      await expect(page.locator(".ref-rule-on")).toBeVisible();
      await expect(page.locator(".ref-rule-on")).toBeFocused();
      await expect(page.locator(".ref-rule-on .ref-docs-trigger")).toHaveAttribute(
        "aria-expanded",
        "true",
      );
    });
  }
});
