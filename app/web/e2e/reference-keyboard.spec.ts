/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The Reference walkthroughs from m5-build.md section 10 that reference.spec.ts does not cover, with
 * the keyboard only, at 375 and 1440, on the demo build. The helpers come from kit.ts, which
 * reference.spec.ts shares.
 *
 * Decides. Tab to the search field and type, and the count and its one polite announcement follow.
 * The Confidence select narrows the list and announces. A search with no match shows "Clear
 * search", and pressing it announces the whole list again. A setting opens as its own page by key. A
 * rule deep link focuses its first occurrence and gives the other none.
 *
 * Glossary. The Jump to chips move focus to their section by Enter and by Space.
 *
 * Snapshots. `toMatchAriaSnapshot` on the Decides setting page, the Decides search results and the
 * top of the Glossary. Counts and sentences from the rules file are matched by pattern, so a new rule
 * or a reworded sentence does not churn them.
 */
import type { Page } from "@playwright/test";
import { en } from "../src/strings/en";
import { decides, glossary, heading2, openAt, polite, settingsNav, tabTo, test } from "./kit";
import { expect } from "./server";

const WIDTHS = [375, 1440] as const;

const searchbox = (page: Page) => page.getByRole("searchbox", { name: en.dc_search_label });

test.describe("decides by keyboard", () => {
  for (const width of WIDTHS) {
    test(`search, Confidence and Clear announce at ${String(width)}`, async ({ page, demo }) => {
      await openAt(page, demo, decides(), width);
      const field = searchbox(page);
      await expect(field).toBeVisible();
      await tabTo(page, field);
      await page.keyboard.type("teleportation");
      await expect(field).toHaveValue("teleportation");
      // Nothing matches, so the page shows its empty state and says so once typing settles.
      await expect(heading2(page, /^No rules match/)).toBeVisible();
      await expect(polite(page)).toHaveText(en.dc_count_ann_none, { timeout: 5_000 });
      // The empty state's Clear search is a real button, so Tab reaches it.
      const clear = page.getByRole("button", { name: en.sf_clear, exact: true }).last();
      await tabTo(page, clear);
      await page.keyboard.press("Enter");
      await expect(field).toHaveValue("");
      await expect(page.locator(".search-count")).toHaveText("84 rules");
      await expect(polite(page)).toHaveText("84 rules shown", { timeout: 5_000 });
      // The Confidence select narrows the list by key, and the count announces it.
      const select = page.getByRole("button", { name: new RegExp(en.dc_conf_label) });
      await tabTo(page, select);
      await page.keyboard.press("Enter");
      await expect(page.getByRole("listbox")).toBeVisible();
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("Enter");
      await expect(page.getByRole("listbox")).toHaveCount(0);
      await expect(page.locator(".search-count")).toHaveText(/^\d+ of 84 rules$/);
      await expect(polite(page)).toHaveText(/^\d+ of 84 rules shown$/, { timeout: 5_000 });
    });

    test(`a setting opens as its own page by key at ${String(width)}`, async ({ page, demo }) => {
      await openAt(page, demo, decides(), width);
      const link = settingsNav(page).getByRole("link", { name: /^Cache lifetime/ });
      await expect(link).toBeVisible();
      await tabTo(page, link);
      await page.keyboard.press("Enter");
      await expect(heading2(page, en.rg_promptCacheTtl)).toBeVisible();
      expect(await page.evaluate(() => window.location.hash)).toBe(
        `#${decides("/promptCacheTtl")}`,
      );
      // A phone shows the setting alone, with a Back link that returns focus to the list item.
      if (width <= 720) {
        await expect(settingsNav(page)).toHaveCount(0);
        const back = page.getByRole("link", { name: new RegExp(`Back to ${en.sf_settings}`) });
        await tabTo(page, back);
        await page.keyboard.press("Enter");
        await expect(
          settingsNav(page).getByRole("link", { name: /^Cache lifetime/ }),
        ).toBeFocused();
      } else {
        await expect(link).toHaveAttribute("aria-current", "page");
      }
    });

    test(`a rule deep link focuses its first occurrence at ${String(width)}`, async ({
      page,
      demo,
    }) => {
      // This rule leads to two statuses, so the setting shows it twice.
      const id = "prompt-cache-force-5m";
      await openAt(page, demo, decides(`/promptCacheTtl/${id}`), width);
      const rows = page.locator(".ref-rule", { hasText: id });
      await expect(rows).toHaveCount(2);
      await expect(rows.first()).toHaveClass(/ref-rule-on/);
      await expect(rows.first()).toBeFocused();
      await expect(rows.nth(1)).not.toHaveClass(/ref-rule-on/);
      // Only the first row has the id, so element ids stay unique.
      await expect(page.locator(`[data-rule-id="${id}"]`)).toHaveCount(1);
      // The next stop is inside the marked rule, its docs line.
      await page.keyboard.press("Tab");
      await expect(rows.first().locator(".ref-docs-trigger")).toBeFocused();
    });
  }
});

test.describe("glossary by keyboard", () => {
  for (const width of WIDTHS) {
    for (const key of ["Enter", "Space"] as const) {
      test(`Jump to chips, ${key}, at ${String(width)}`, async ({ page, demo }) => {
        await openAt(page, demo, glossary(), width);
        await expect(heading2(page, en.gl_terms_h)).toBeVisible();
        const chip = page.getByRole("button", { name: /^Confidence words \d+$/ });
        await tabTo(page, chip);
        await page.keyboard.press(key);
        const section = heading2(page, "Confidence words");
        await expect(section).toBeFocused();
        await expect(section).toBeInViewport();
        // Tab moves on from the section, not back to the top of the page.
        await page.keyboard.press("Tab");
        await expect(chip).not.toBeFocused();
        await expect(page.getByRole("searchbox", { name: en.gl_search_label })).not.toBeFocused();
      });
    }
  }
});

test.describe("accessibility snapshots", () => {
  test("the Decides setting page", async ({ page, demo }) => {
    await openAt(page, demo, decides("/promptCacheTtl"), 1440);
    const pane = page.getByRole("region", { name: en.rg_promptCacheTtl });
    await expect(pane).toBeVisible();
    await expect(pane).toMatchAriaSnapshot(`
      - region "${en.rg_promptCacheTtl}":
        - heading "${en.rg_promptCacheTtl}" [level=2]
        - code: promptCacheTtl
        - paragraph: /^\\d+ rules\\. Applies to the main session\\.$/
        - heading "${en.dc_order_h}" [level=3]
        - list "${en.dc_order_h}":
          - listitem: ${en.ly_env}
          - listitem: ${en.sc_managed}
          - listitem: ${en.ly_cli}
          - listitem: ${en.sc_project_local}
          - listitem: ${en.sc_project}
          - listitem: ${en.sc_user}
          - listitem: ${en.ly_default}
        - heading /^${en.status_invalid} ${en.dc_q_invalid} \\d+$/ [level=3]
        - list:
          - listitem:
            - paragraph: /.+/
            - paragraph:
              - code: prompt-cache-ttl-order
              - text: /^${en.in_tested} /
            - button /^Show the \\d+ lines from the docs$/
        - heading /^${en.status_overridden} ${en.dc_q_overridden} \\d+$/ [level=3]
        - heading /^${en.status_unknown} ${en.dc_q_unknown} \\d+$/ [level=3]
        - heading /^${en.status_in_effect} ${en.dc_q_in_effect} \\d+$/ [level=3]
        - heading /^${en.status_default} ${en.dc_q_default} \\d+$/ [level=3]
    `);
  });

  test("the Decides search results", async ({ page, demo }) => {
    await openAt(page, demo, decides("?q=promptCacheTtl"), 1440);
    await expect(heading2(page, /rules in \d+ settings$/)).toBeVisible();
    await expect(page.getByRole("main")).toMatchAriaSnapshot(`
      - main:
        - heading "${en.nav_decides}" [level=1]
        - text: ${en.dc_search_label}
        - searchbox "${en.dc_search_label}": promptCacheTtl
        - button "${en.sf_clear}"
        - paragraph: /^\\d+ of 84 rules$/
        - status
        - button /^${en.dc_conf_label} ${en.dc_conf_all}/
        - navigation "${en.sf_settings}":
          - heading "${en.sf_settings}" [level=2]
          - list:
            - listitem:
              - link /^Cache lifetime \\d+ of \\d+ promptCacheTtl$/
            - listitem:
              - link /^Agent cache lifetime \\d+ of \\d+ subagentPromptCacheTtl$/
        - region /^\\d+ rules in 2 settings$/:
          - heading /^\\d+ rules in 2 settings$/ [level=2]
          - heading /^Cache lifetime promptCacheTtl \\d+$/ [level=3]:
            - link "Cache lifetime"
          - list:
            - listitem:
              - paragraph: /.+/
              - paragraph:
                - code
                - text: /^${en.in_tested} /
              - button /^Show the .+ from the docs$/
    `);
  });

  test("a rule reached by route, marked and focused", async ({ page, demo }) => {
    const id = "prompt-cache-force-5m";
    await openAt(page, demo, decides(`/promptCacheTtl/${id}`), 1440);
    const rule = page.locator(".ref-rule-on");
    await expect(rule).toBeFocused();
    await expect(rule).toMatchAriaSnapshot(`
      - listitem:
        - paragraph: /.+/
        - paragraph:
          - code: ${id}
          - text: /^${en.in_tested} /
        - button /^Show the .+ from the docs$/ [expanded=true]
    `);
  });

  test("a Glossary term reached by route, focused", async ({ page, demo }) => {
    await openAt(page, demo, glossary("/part"), 1440);
    const term = page.locator('dt[data-term-id="part"]');
    await expect(term).toBeFocused();
    await expect(page.getByRole("region", { name: en.gl_terms_h })).toMatchAriaSnapshot(`
      - region "${en.gl_terms_h}":
        - heading "${en.gl_terms_h}" [level=2]
        - term: Part
        - definition: /.+/
    `);
  });

  test("the top of the Glossary", async ({ page, demo }) => {
    await openAt(page, demo, glossary(), 1440);
    await expect(heading2(page, en.gl_terms_h)).toBeVisible();
    await expect(page.getByRole("main")).toMatchAriaSnapshot(`
      - main:
        - heading "${en.nav_glossary}" [level=1]
        - paragraph: ${en.gl_sub}
        - text: ${en.gl_search_label}
        - searchbox "${en.gl_search_label}"
        - paragraph: /^\\d+ entries$/
        - status
        - paragraph:
          - text: ${en.sp_jump}
          - button /^Status words \\d+$/
          - button /^Scopes \\d+$/
          - button /^Confidence words \\d+$/
          - button /^Terms \\d+$/
        - region "Status words":
          - heading "Status words" [level=2]
          - text: /^\\d+ ${en.gl_status_q}$/
          - term: ${en.status_in_effect}
          - definition: /.+/
          - term: ${en.status_overridden}
          - definition: /.+/
        - region "Scopes":
          - heading "Scopes" [level=2]
        - region "Confidence words":
          - heading "Confidence words" [level=2]
        - region "${en.gl_terms_h}":
          - heading "${en.gl_terms_h}" [level=2]
    `);
  });
});
