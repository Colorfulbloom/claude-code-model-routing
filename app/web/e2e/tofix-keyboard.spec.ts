/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The M4 keyboard walkthrough "Find one problem on To fix", and the accessibility snapshots of a
 * To fix group and the Agents inspector (m4-build.md section 10 and need 29). The server is the
 * demo build with the setup overlay (`--demo --test-clock`, fact J-b0ae).
 *
 * Walkthrough. At 375 and 1440, with the keyboard only (Tab, Shift+Tab, Enter), from Live to the
 * To fix link in the navigation, which carries the count in its name, and on to a row and its
 * item. Each step asserts which element holds focus by its accessible name, and the visible text.
 * The page loads once and every move after it is a key press.
 *
 * Snapshots. `toMatchAriaSnapshot` on a To fix group with a fix link, on a group with Copy path
 * actions, and on the inspector of an agent beside the Agents table. The words come from the
 * string deck.
 */
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { rmSync } from "node:fs";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const PROJECT = "tidewater-reporting";
const WIDTHS = [375, 1440] as const;

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

async function openAt(page: Page, server: Server, path: string, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

/** The one page load of a walkthrough. It lands on Live, and every move after it is a key press. */
async function loadLive(page: Page, server: Server, width: number): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
  await expectUnlocked(page);
  await expect(page).toHaveURL(new RegExp(`#/p/${PROJECT}/live$`));
}

/** Presses Tab until the locator holds focus, then Shift+Tab, so the walk fails with its step. */
async function reach(page: Page, target: Locator, max = 60): Promise<void> {
  await expect(target).toHaveCount(1);
  const here = (): Promise<boolean> =>
    target.evaluate((el) => el === document.activeElement).catch(() => false);
  for (const key of ["Tab", "Shift+Tab"]) {
    for (let i = 0; i < max; i++) {
      if (await here()) return;
      await page.keyboard.press(key);
    }
  }
  if (await here()) return;
  throw new Error(`the keyboard never reached ${String(target)}`);
}

/** Asserts that the focused element is this one, by its accessible name. */
async function focusIs(target: Locator, name: string | RegExp): Promise<void> {
  await expect(target).toBeFocused();
  await expect(target).toHaveAccessibleName(name);
}

const hash = (page: Page): Promise<string> => page.evaluate(() => window.location.hash);
const groupName = (group: string, n: number): string => fill(en.fx_g_aria, { group, n });

/* ---------- walkthrough ---------- */

for (const width of WIDTHS) {
  test(`keyboard only at ${String(width)} wide: find one problem on To fix and open its item`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(120_000);
    await loadLive(page, demo, width);

    // 1. Live to To fix. The link's name carries the count, so the problem is known before the
    // page opens. The sidebar and the phone's tab bar both name it.
    const main = page.getByRole("navigation", { name: en.nav_aria });
    const toFix = main.getByRole("link", { name: fill(en.tofix_aria_one, { n: 1 }) });
    await reach(page, toFix);
    await focusIs(toFix, fill(en.tofix_aria_one, { n: 1 }));
    await expect(toFix).toContainText("1");
    await page.keyboard.press("Enter");

    // 2. The page. The h1 takes focus, and the line under it counts the problems.
    const h1 = page.getByRole("heading", { level: 1, name: en.fx_h1 });
    await expect(h1).toBeFocused();
    expect(await hash(page)).toBe(`#/p/${PROJECT}/to-fix`);
    await expect(
      page.getByText(fill(en.fx_sub_one, { n: 1, project: "Tidewater reporting" })),
    ).toBeVisible();

    // 3. The group, then its row. The group's heading names its count, the row names its problem.
    const group = page.getByRole("region", { name: groupName(en.fx_g_not_as_set, 1) });
    await expect(group).toBeVisible();
    await expect(group.getByRole("heading", { level: 2 })).toHaveAccessibleName(
      groupName(en.fx_g_not_as_set, 1),
    );
    await expect(group).toContainText(en.fx_q_not_as_set);
    const row = group.getByRole("listitem");
    await expect(row).toHaveCount(1);
    await expect(row.getByRole("heading", { level: 3 })).toHaveText(
      fill(en.pc_lowered_t, { thing: "effortLevel" }),
    );

    // 4. The fix action, by key. It is a link to the item, so Enter opens it.
    const open = row.getByRole("link", { name: fill(en.fx_open, { item: en.sl_effortLevel }) });
    await reach(page, open);
    await focusIs(open, fill(en.fx_open, { item: en.sl_effortLevel }));
    await expect(open).toHaveAttribute("href", `#/p/${PROJECT}/setup/settings/effortLevel`);
    await page.keyboard.press("Enter");

    // 5. The item. Its page names the setting and says why it runs lower.
    await expect.poll(() => hash(page)).toBe(`#/p/${PROJECT}/setup/settings/effortLevel`);
    // Focus lands on the page's h1, or on the item's h2 when the item is the whole phone page.
    await expect(
      width >= 721
        ? page.getByRole("heading", { level: 1, name: en.sf_settings })
        : page.getByRole("heading", { level: 2, name: en.sl_effortLevel }),
    ).toBeFocused();
    const region = page.getByRole("region", { name: en.sl_effortLevel });
    await expect(region).toBeVisible();
    await expect(region.getByRole("heading", { level: 2, name: en.sl_effortLevel })).toBeVisible();
    await expect(region).toContainText(fill(en.in_runs_effort, { value: "high" }));
    await expect(region.getByRole("heading", { level: 3, name: en.in_why_h })).toBeVisible();
    // On a phone the item is its own page, with a back link and no breadcrumb.
    if (width >= 721) {
      const crumb = page.getByRole("navigation", { name: en.bc_label });
      await expect(crumb.locator('[aria-current="page"]')).toHaveText(en.sf_settings);
    } else {
      await expect(region.getByRole("link", { name: en.sf_settings, exact: true })).toBeVisible();
    }
  });
}

/* ---------- snapshots ---------- */

test.describe("accessibility snapshots", () => {
  test("a To fix group with its fix link", async ({ page, demo }) => {
    await openAt(page, demo, `/p/${PROJECT}/to-fix`, 1440);
    await expect(page.getByRole("region", { name: groupName(en.fx_g_not_as_set, 1) }))
      .toMatchAriaSnapshot(`
      - region "${groupName(en.fx_g_not_as_set, 1)}":
        - heading "${groupName(en.fx_g_not_as_set, 1)}" [level=2]
        - list:
          - listitem:
            - heading "${fill(en.pc_lowered_t, { thing: "effortLevel" })}" [level=3]
            - link "${fill(en.fx_open, { item: en.sl_effortLevel })}"
    `);
  });

  test("a To fix group with Copy path actions", async ({ page, demo }) => {
    await openAt(page, demo, "/p/driftwood/to-fix", 1440);
    const group = page.getByRole("region", { name: groupName(en.fx_g_wont_load, 2) });
    await expect(group).toBeVisible();
    await expect(group).toMatchAriaSnapshot(`
      - region "${groupName(en.fx_g_wont_load, 2)}":
        - heading "${groupName(en.fx_g_wont_load, 2)}" [level=2]
        - list:
          - listitem
          - listitem
    `);
    await expect(group.getByRole("button", { name: /^Copy path of / }).first()).toBeVisible();
  });

  test("the Agents inspector beside the table", async ({ page, demo }) => {
    await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d&agent=builder`, 1440);
    await expect(page.getByRole("region", { name: "builder" })).toMatchAriaSnapshot(`
      - region "builder":
        - heading "builder" [level=2]
        - paragraph: ${fill(en.ag_runs, { model: "Fable 5.1", effort: "medium" })} ${fill(en.in_origin_override_file, { key: "effort", file: ".claude/settings.local.json", line: 3 })}
        - paragraph: ${fill(en.in_set_at, { scope: en.sc_user, where: "~/config/agents/builder.md line 2" })}
        - paragraph: ${en.ro_agents_next}
        - button "${en.in_copy}"
        - heading "${en.in_why_h}" [level=3]
        - paragraph: ${fill(en.rs_agent_loads, { file: "~/config/agents/builder.md" })}
        - paragraph: ${en.in_conf_documented}
        - paragraph: ${fill(en.ag_runs_cost, { runs: "82 runs", sessions: "40 sessions", cost: "$241.92", days: 30 })}
        - heading "${en.in_details_h}" [level=3]
        - term: ${en.ag_f_desc}
        - definition: Builds well-specified changes.
        - term: ${en.ag_f_model}
        - definition: Fable 5.1
        - term: ${en.ag_f_effort}
        - definition: xhigh
        - link "${en.ag_open_setup}"
    `);
    await expect(page.getByRole("table", { name: en.ag_h })).toMatchAriaSnapshot(`
      - table "${en.ag_h}":
        - rowgroup:
          - row "${en.ag_col_agent} ${en.ag_col_set} ${en.ag_col_ran} ${en.ag_col_check} ${en.ag_col_runs} ${en.ag_col_cost}"
    `);
  });
});
