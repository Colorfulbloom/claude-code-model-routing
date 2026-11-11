/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The M4 keyboard walkthrough "Explain one agent's model and effort", and the accessibility
 * snapshots of Your setup and the surface pages (m4-build.md section 10 and need 29). The server
 * is the demo build with the setup overlay (`--demo --test-clock`, fact J-b0ae).
 *
 * Walkthrough. At 375 and 1440, with the keyboard only (Tab, Shift+Tab, Enter, Space), from Your
 * setup to the Agents part and an agent's inspector, and from Review's Agents page to the same
 * agent. Each step asserts which element holds focus by its accessible name, and the visible text.
 * The page loads once and every move after it is a key press.
 *
 * Snapshots. `toMatchAriaSnapshot` on the map with the Switch off and on, a surface list with one
 * item picked, the inspector of a read-only item, a masked value, a "not read here" item and the
 * Couldn't read card. The words come from the string deck. The demo has no not-read item and no
 * unreadable file, so those two change one answer in flight, as setup.spec.ts does.
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
const AGENT = "builder";

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

type Json = Record<string, unknown> & { items?: Record<string, unknown>[] };

/** Changes one setup answer in flight, so a state the demo has no data for can be drawn. */
async function patch(page: Page, glob: RegExp, change: (body: Json) => void): Promise<void> {
  await page.route(glob, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Json;
    change(body);
    await route.fulfill({ response, json: body });
  });
}

const path = {
  setup: `/p/${PROJECT}/setup`,
  agents: `/p/${PROJECT}/setup/agents`,
};

/** What the agent's inspector says, from the deck. The demo's builder runs on Fable 5.1 at medium. */
const RUNS = fill(en.ag_runs, { model: "Fable 5.1", effort: "medium" });
// The demo's builder reads Overridden, because settings.local.json sets effort above its file, so
// the sentence names that file and never the cap (the pill and the sentence name one cause).
const CAP = fill(en.in_origin_override_file, {
  key: "effort",
  file: ".claude/settings.local.json",
  line: 3,
});
const WHY = fill(en.rs_agent_loads, { file: "~/config/agents/builder.md" });

/** The inspector's visible words, the same on both routes to the agent. */
async function expectExplained(page: Page): Promise<Locator> {
  const region = page.getByRole("region", { name: AGENT });
  await expect(region).toBeVisible();
  await expect(region.getByRole("heading", { level: 2, name: AGENT })).toBeVisible();
  await expect(region).toContainText(RUNS);
  await expect(region).toContainText(CAP);
  await expect(region.getByRole("heading", { level: 3, name: en.in_why_h })).toBeVisible();
  await expect(region).toContainText(WHY);
  await expect(region).toContainText(en.in_conf_documented);
  return region;
}

/* ---------- walkthroughs ---------- */

for (const width of WIDTHS) {
  test(`keyboard only at ${String(width)} wide: from Your setup to an agent's model, effort and Why`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(120_000);
    await loadLive(page, demo, width);

    // 0. Live to Your setup. The sidebar says Your setup, and the phone's tab bar says Setup.
    const main = page.getByRole("navigation", { name: en.nav_aria });
    const setupName = width >= 721 ? en.nav_setup : en.nav_setup_h;
    const toSetup = main.getByRole("link", { name: setupName, exact: true });
    await reach(page, toSetup);
    await focusIs(toSetup, setupName);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeFocused();
    expect(await hash(page)).toBe(`#${path.setup}`);

    // 1. The Agents row of the map, by its link.
    const map = page.getByRole("table", { name: en.su_card_h });
    const agentsLink = map.getByRole("link", { name: en.sf_agents, exact: true });
    await reach(page, agentsLink);
    await focusIs(agentsLink, en.sf_agents);
    await expect(agentsLink).toHaveAttribute("href", `#${path.agents}`);
    await expect(map.locator('tr[data-part="agents"]')).toContainText(
      fill(en.su_r_agents_other, { n: 3 }),
    );
    await page.keyboard.press("Enter");

    // 2. The Agents part. The page moves focus to its h1, the breadcrumb names where it is.
    const h1 = page.getByRole("heading", { level: 1, name: en.sf_agents });
    await expect(h1).toBeVisible();
    await expect(h1).toBeFocused();
    const crumb = page.getByRole("navigation", { name: en.bc_label });
    await expect(crumb.getByRole("link", { name: en.nav_setup })).toBeVisible();
    await expect(crumb.locator('[aria-current="page"]')).toHaveText(en.sf_agents);
    const list = page.getByRole("navigation", { name: en.sf_agents });
    await expect(list).toBeVisible();
    if (width >= 1440) {
      // The wide page already shows an agent, and it has put that agent in the address.
      await expect(page.getByRole("region", { name: AGENT })).toBeVisible();
      await expect.poll(() => hash(page)).toBe(`#${path.agents}/${AGENT}`);
    } else {
      await expect(page.getByRole("region", { name: AGENT })).toHaveCount(0);
      expect(await hash(page)).toBe(`#${path.agents}`);
    }

    // 3. The builder row, and its inspector. The inspector's h2 takes focus.
    const row = list.getByRole("link", { name: /^builder\b/ });
    await reach(page, row);
    await focusIs(row, /^builder\b/);
    await page.keyboard.press("Enter");
    await expect.poll(() => hash(page)).toBe(`#${path.agents}/${AGENT}`);
    const title = page.getByRole("heading", { level: 2, name: AGENT });
    await expect(title).toBeFocused();

    // 4. Model, effort and Why, in words. The same agent, the same sentences.
    const region = await expectExplained(page);
    await expect(region).toContainText(
      fill(en.in_set_at, { scope: en.sc_user, where: "~/config/agents/builder.md line 2" }),
    );
    await expect(region.getByRole("heading", { level: 3, name: en.in_details_h })).toBeVisible();
    await expect(region.getByText(en.ag_f_model, { exact: true })).toBeVisible();
    await expect(region.getByText(en.ag_f_effort, { exact: true })).toBeVisible();
    // On a phone the list gives way to the inspector, and the back link sits just before the h2.
    if (width < 1440) {
      // The back link reads "← Agents", with the arrow hidden from its name. The footer link to
      // Review's Agents page has the same name, so the back link is the first of the two.
      const back = region.getByRole("link", { name: en.sf_agents, exact: true }).first();
      await page.keyboard.press("Shift+Tab");
      await focusIs(back, en.sf_agents);
    }
  });

  test(`keyboard only at ${String(width)} wide: from Review's Agents page to the same agent`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(120_000);
    await loadLive(page, demo, width);

    // 0. Live to Agents. The sidebar has an Agents link at 1440. The tab bar has Review at 375,
    // and Summary's segmented links lead on to Agents.
    const main = page.getByRole("navigation", { name: en.nav_aria });
    if (width >= 721) {
      const toAgents = main.getByRole("link", { name: en.nav_agents, exact: true });
      await reach(page, toAgents);
      await focusIs(toAgents, en.nav_agents);
      await page.keyboard.press("Enter");
    } else {
      const toReview = main.getByRole("link", { name: en.nav_review, exact: true });
      await reach(page, toReview);
      await focusIs(toReview, en.nav_review);
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { level: 1, name: en.nav_summary })).toBeFocused();
      const toAgents = page.getByRole("link", { name: en.nav_agents, exact: true });
      await reach(page, toAgents);
      await focusIs(toAgents, en.nav_agents);
      await page.keyboard.press("Enter");
    }
    await expect(page.getByRole("heading", { level: 1, name: en.nav_agents })).toBeFocused();
    // The nav's Agents link names no range, and the page reads its default, 30 days.
    await expect(page).toHaveURL(new RegExp(`#/p/${PROJECT}/review/agents(\\?range=30d)?$`));
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` })).toBeVisible();

    // 1. The builder row of the table.
    const table = page.getByRole("table", { name: en.ag_h });
    const link = table.getByRole("link", { name: AGENT, exact: true });
    await reach(page, link);
    await focusIs(link, AGENT);
    await page.keyboard.press("Enter");

    // 2. The inspector. Its h2 takes focus, and the address keeps the agent.
    await expect(page.getByRole("heading", { level: 2, name: AGENT })).toBeFocused();
    expect(await hash(page)).toContain(`agent=${AGENT}`);
    const region = await expectExplained(page);
    await expect(region).toContainText(
      fill(en.ag_runs_cost, {
        runs: "82 runs",
        sessions: "40 sessions",
        cost: "$241.92",
        days: 30,
      }),
    );

    // 3. Open in Your setup, by key, goes to the same agent's page.
    const open = region.getByRole("link", { name: new RegExp(en.ag_open_setup) });
    await reach(page, open);
    await expect(open).toBeFocused();
    await page.keyboard.press("Enter");
    await expect.poll(() => hash(page)).toBe(`#${path.agents}/${AGENT}`);
    await expect(page.getByRole("heading", { level: 2, name: AGENT })).toBeVisible();
    await expectExplained(page);
  });
}

/* ---------- the auto-picked item ---------- */

test("at 1440 the auto-picked item is in the address with no history entry, so Back and reload keep it", async ({
  page,
  demo,
}) => {
  await loadLive(page, demo, 1440);
  const toSetup = page
    .getByRole("navigation", { name: en.nav_aria })
    .getByRole("link", { name: en.nav_setup, exact: true });
  await reach(page, toSetup);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeFocused();
  const agentsLink = page
    .getByRole("table", { name: en.su_card_h })
    .getByRole("link", { name: en.sf_agents, exact: true });
  await reach(page, agentsLink);
  await page.keyboard.press("Enter");
  await expect.poll(() => hash(page)).toBe(`#${path.agents}/${AGENT}`);
  await expect(page.getByRole("region", { name: AGENT })).toBeVisible();
  // One Back goes to the map, not to the bare part address.
  await page.goBack();
  await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeVisible();
  expect(await hash(page)).toBe(`#${path.setup}`);
  await page.goForward();
  await expect.poll(() => hash(page)).toBe(`#${path.agents}/${AGENT}`);
  await page.reload();
  await expect(page.getByRole("region", { name: AGENT })).toBeVisible();
  expect(await hash(page)).toBe(`#${path.agents}/${AGENT}`);
});

/* ---------- snapshots ---------- */

test.describe("accessibility snapshots", () => {
  test("the version gap notice row on Your setup", async ({ page, demo }) => {
    await openAt(page, demo, path.setup, 1440);
    const notice = page.locator(".setup-version-gap");
    await expect(notice).toBeVisible();
    await expect(notice).toMatchAriaSnapshot(`
      - paragraph:
        - text: /^${en.status_unknown} You run Claude Code \\S+, but Bar Tab checked .+ on \\S+\\. /
        - link /^Show the \\d+ rules to re-check$/
    `);
  });

  test("the map, with the Switch off and then on by key", async ({ page, demo }) => {
    await openAt(page, demo, path.setup, 1440);
    const toggle = page.getByRole("switch", { name: en.su_switch });
    await expect(toggle).toMatchAriaSnapshot(`- switch "${en.su_switch}"`);
    const table = page.getByRole("table", { name: en.su_card_h });
    await expect(table).toMatchAriaSnapshot(`
      - table "${en.su_card_h}":
        - rowgroup:
          - row "${en.su_col_what} ${en.su_col_runs} ${en.su_col_status}":
            - columnheader "${en.su_col_what}"
            - columnheader "${en.su_col_runs}"
            - columnheader "${en.su_col_status}"
        - rowgroup:
          - row "${en.sf_settings} Opus 5.5, runs at high effort ${en.status_lowered} ${en.status_in_effect}":
            - rowheader "${en.sf_settings}":
              - link "${en.sf_settings}"
          - row "${en.sf_agents} 3 agents ${en.status_overridden}":
            - rowheader "${en.sf_agents}":
              - link "${en.sf_agents}"
          - row "${en.sf_instructions} 4 files, 9 lines ${en.status_in_effect}"
          - row "${en.sf_rules} 2 files ${en.status_in_effect}"
          - row "${en.sf_skills} 3 skills ${en.status_in_effect}"
          - row "${en.sf_hooks} 3 hooks on 2 events ${en.status_in_effect}"
          - row "${en.sf_permissions} 1 denied, 4 allowed ${en.status_in_effect}"
    `);
    await expect(page.locator(".setup-map-chips")).toHaveCount(0);

    await toggle.focus();
    await page.keyboard.press("Space");
    await expect(toggle).toMatchAriaSnapshot(`- switch "${en.su_switch}" [checked]`);
    await expect(table.locator('tr[data-part="settings"]')).toMatchAriaSnapshot(`
      - row "${en.sf_settings} Opus 5.5, runs at high effort ${en.sc_command_line} ${en.su_nv} ${en.sc_shell} 1 value ${en.sc_project_local} xhigh effort ${en.sc_project} medium effort ${en.sc_user} Opus 5.5 at xhigh ${en.status_lowered} ${en.status_in_effect}":
        - rowheader "${en.sf_settings}"
        - cell:
          - text: Opus 5.5, runs at high effort
          - list:
            - listitem: ${en.sc_command_line} ${en.su_nv}
            - listitem: ${en.sc_shell} 1 value
            - listitem: ${en.sc_project_local} xhigh effort
            - listitem: ${en.sc_project} medium effort
            - listitem: ${en.sc_user} Opus 5.5 at xhigh
    `);
  });

  test("a surface list with one item picked", async ({ page, demo }) => {
    await openAt(page, demo, `${path.setup}/settings/effortLevel`, 1440);
    const list = page.getByRole("navigation", { name: en.sf_settings });
    await expect(list).toMatchAriaSnapshot(`
      - navigation "${en.sf_settings}":
        - heading "${en.sf_settings}" [level=2]
        - heading "${en.sp_g_model} 4" [level=3]
        - list:
          - listitem:
            - link "Effort ${en.status_lowered} high"
          - listitem:
            - link "Effort cap ${en.status_in_effect} high"
          - listitem:
            - link "Model ${en.status_in_effect} Opus 5.5"
          - listitem:
            - link /${en.sl_modelSettings} ${en.status_in_effect} Fable 5.1 \\(Effort cap medium\\).*/
        - heading "${en.sp_g_other} 2" [level=3]
        - list:
          - listitem:
            - link "env.ANTHROPIC_API_KEY ${en.status_in_effect} hidden ${en.in_masked_word}"
          - listitem:
            - link "env.CLAUDE_CODE_EFFORT_LEVEL ${en.status_in_effect} xhigh"
    `);
    await expect(list.locator('a[aria-current="page"]')).toHaveCount(1);
    await expect(list.locator('a[aria-current="page"]')).toContainText("Effort");
    await expect(page.getByRole("region", { name: "Effort" })).toMatchAriaSnapshot(`
      - region "Effort":
        - heading "Effort" [level=2]
        - paragraph: Runs at high
        - paragraph: /Set to xhigh in ${en.sc_project_local}, .claude\\/settings.local.json line 3\\./
        - heading "${en.in_why_h}" [level=3]
    `);
  });

  test("the inspector of a read-only item", async ({ page, demo }) => {
    await openAt(page, demo, `${path.setup}/hooks/PreToolUse:Bash:1`, 1440);
    await expect(page.getByRole("region", { name: "Before Bash" })).toMatchAriaSnapshot(`
      - region "Before Bash":
        - heading "Before Bash" [level=2]
        - paragraph: ${en.in_lock_word}. ${fill(en.ro_plugin, { plugin: "hivemind" })}
        - button "${en.in_copy}"
        - heading "${en.in_details_h}" [level=3]
        - heading "${en.in_why_h}" [level=3]
    `);
  });

  test("a masked value, with no secret in the page", async ({ page, demo }) => {
    await openAt(page, demo, `${path.setup}/settings/env.ANTHROPIC_API_KEY`, 1440);
    const region = page.getByRole("region", { name: "env.ANTHROPIC_API_KEY" });
    await expect(region).toMatchAriaSnapshot(`
      - region "env.ANTHROPIC_API_KEY":
        - heading "env.ANTHROPIC_API_KEY" [level=2]
        - paragraph: Runs with hidden ${en.in_masked_word}
        - paragraph: /Set to hidden in ${en.sc_user}, .*line 8\\./
        - heading "${en.in_why_h}" [level=3]
        - paragraph: ${en.in_masked}
    `);
    await expect(page.locator("body")).not.toContainText("sk-ant");
    expect(await region.ariaSnapshot()).not.toContain("sk-ant");
  });

  test("a not-read-here item", async ({ page, demo }) => {
    await patch(page, /\/api\/setup\/plugins\?/, (body) => {
      for (const it of body.items ?? []) {
        if (it.id === "plugins:hivemind@bartab-demo") {
          // The server sets both together for a plugin installed outside the plugins folder.
          it.not_read = "plugin_outside_plugins";
          it.status = "unknown";
        }
      }
    });
    await openAt(page, demo, `${path.setup}/plugins/hivemind@bartab-demo`, 1440);
    await expect(
      page.getByRole("navigation", { name: en.sf_plugins }).getByRole("listitem").first(),
    ).toMatchAriaSnapshot(`
      - listitem:
        - link "hivemind@bartab-demo ${en.in_lock_word} ${en.status_unknown} ${en.sc_user}"
    `);
    await expect(page.getByRole("region", { name: "hivemind@bartab-demo" })).toMatchAriaSnapshot(`
      - region "hivemind@bartab-demo":
        - heading "hivemind@bartab-demo" [level=2]
        - text: ${en.status_unknown}
        - paragraph: ${en.pl_outside_runs}
        - paragraph: ${en.status_unknown} ${en.pl_outside}
    `);
  });

  test("the Couldn't read card", async ({ page, demo }) => {
    await patch(page, /\/api\/setup\/agents\?/, (body) => {
      body.unreadable = [
        {
          file: "~/config/agents/notes.md",
          full_path: "/work/config/agents/notes.md",
          part: "agents",
          problem: null,
          reason: "permission",
          scope: "user",
        },
      ];
    });
    await openAt(page, demo, path.agents, 1440);
    const card = page.getByRole("alert");
    await expect(card).toMatchAriaSnapshot(`
      - alert:
        - heading "${fill(en.ft_unreadable_one, { n: 1 })}" [level=3]
        - paragraph:
          - text: ${en.cr_r_permission.replace(" {file}.", "")}
          - code: ~/config/agents/notes.md
          - text: . ${en.cr_b}
        - paragraph: ${en.cr_fix}
        - button "${fill(en.fx_copy_path_aria, { file: "~/config/agents/notes.md" })}"
    `);
  });
});
