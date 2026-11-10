/// <reference lib="dom" />
/// <reference types="node" />
/*
 * To fix, the Agents setup half and Live's See why against the real server on the demo build
 * (`--demo --test-clock`, fact J-b0ae). Four kinds of check.
 *
 * Matrix. Each state renders at 375 and 1440, light and dark, with axe and no sideways scroll.
 * The demo's own rows cover Won't load, Not as set and Can't tell, and its open_item and copy_path
 * fixes. The states the demo has no data for (Couldn't read, a copied command, a managed or plugin
 * cant_fix_here, a Notice, a long group, a plugin agent, a Model check row with an item) are drawn
 * by changing the answer in flight, as the Review specs do. Each is marked "patched" below, and the
 * setup overlay's own rows replace the patch when the demo serves them (task 15).
 *
 * Exact text. Group headings, fix action names, the nav link's name with its count, unchecked and
 * failed, and the inspector's region and h2 are asserted from the string deck.
 *
 * Copy. A Copy path puts the full path on the clipboard and says Copied once through the page's
 * one polite region.
 *
 * Flows. The nav link opens To fix, a row opens its item, an Agents row opens the inspector and
 * back returns, and See why on Live opens the item.
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
const WIDTHS = [375, 1440] as const;
const THEMES = ["light", "dark"] as const;

/** One demo server for each worker, and a flow server for the Live check. */
const test = base.extend<object, { demo: Server; flow: Server }>({
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
  flow: [
    // eslint-disable-next-line no-empty-pattern
    async ({}, run) => {
      const server = await startServer({
        fixture: null,
        args: ["--flow", "busy", "--no-price-fetch", "--test-clock"],
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

type Json = Record<string, unknown> & {
  rows?: Record<string, unknown>[];
  ran?: Record<string, unknown>[];
  items?: Record<string, unknown>[];
  counted?: number;
  unchanged?: boolean;
  to_fix?: unknown;
  model_check?: { rows: Record<string, unknown>[] };
};

async function openAt(
  page: Page,
  server: Server,
  path: string,
  size: { width: number; theme?: "light" | "dark"; forced?: boolean; reduced?: boolean },
): Promise<void> {
  await page.setViewportSize({ width: size.width, height: 900 });
  await page.emulateMedia({
    colorScheme: size.theme ?? "light",
    ...(size.forced === true ? { forcedColors: "active" as const } : {}),
    ...(size.reduced === true ? { reducedMotion: "reduce" as const } : {}),
  });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

/** The errors Playwright throws when the test, page or context ends while a patched call runs. */
const ENDED = /has been disposed|has been closed|Target closed|Test ended|Test timeout/i;

/**
 * Changes one answer in flight, so a state the demo has no data for can be drawn. A call that is
 * still running when the test ends loses its response ("Response has been disposed"). That is the
 * end of the test, not a failure, so the handler lets it go. Any other error still throws.
 */
async function patch(page: Page, glob: string, change: (body: Json) => void): Promise<void> {
  await page.route(glob, async (route) => {
    try {
      const response = await route.fetch();
      const body = (await response.json()) as Json;
      // A short `unchanged` answer carries no rows to change.
      if (body.unchanged !== true) change(body);
      await route.fulfill({ response, json: body });
    } catch (error) {
      if (!(error instanceof Error) || !ENDED.test(error.message)) throw error;
    }
  });
}

async function problems(page: Page, label: string, width: number): Promise<string[]> {
  const found: string[] = [];
  // Let a colour transition finish, or axe reads the mid-fade colour of a row.
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
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

const status = (page: Page): Locator => page.locator("div.sr-only[role='status']");
const hash = (page: Page): Promise<string> => page.evaluate(() => window.location.hash);

/* ---------- rows the demo has no data for (patched) ---------- */

const CONFIDENCE = { level: "documented", tested_on: null };

const base_row = {
  kind: "problem",
  part: null,
  item_id: null,
  file: null,
  full_path: null,
  line: null,
  params: {},
  confidence: CONFIDENCE,
};

const EXTRA_ROWS: Record<string, unknown>[] = [
  {
    ...base_row,
    id: "permission:agents/notes.md",
    kind: "read_failure",
    group: "couldnt_read",
    code: "permission",
    thing: "notes.md",
    part: "agents",
    file: "~/config/agents/notes.md",
    full_path: "/work/home/config/agents/notes.md",
    fix: { kind: "copy_path", target: "/work/home/config/agents/notes.md", reason: null },
  },
  {
    ...base_row,
    id: "mcp_bad_entry:mcp:archive",
    group: "wont_load",
    code: "mcp_bad_entry",
    thing: "archive",
    part: "mcp",
    item_id: "mcp:archive",
    file: "~/.claude.json",
    full_path: "/work/home/.claude.json",
    params: { name: "archive", why: "no_command_or_url" },
    fix: { kind: "copy_command", target: "claude mcp remove archive -s user", reason: null },
  },
  {
    ...base_row,
    id: "json_invalid:managed",
    group: "wont_load",
    code: "json_invalid",
    thing: "managed-settings.json",
    part: "settings",
    file: "managed-settings.json",
    line: 6,
    fix: { kind: "cant_fix_here", target: null, reason: "managed" },
  },
  {
    ...base_row,
    id: "plugin_field_ignored:linter",
    group: "not_as_set",
    code: "plugin_field_ignored",
    thing: "linter",
    part: "agents",
    item_id: "agents:lint-kit:linter",
    file: "agents/linter.md",
    line: 6,
    params: { field: "permissionMode", plugin: "lint-kit" },
    fix: { kind: "cant_fix_here", target: null, reason: "plugin" },
  },
  {
    ...base_row,
    id: "unknown:settings:cache",
    kind: "cant_tell",
    group: "cant_tell",
    code: "unknown",
    thing: "promptCacheTtl",
    part: "settings",
    item_id: "settings:promptCacheTtl",
    fix: { kind: "open_item", target: "settings:promptCacheTtl", reason: null },
  },
  {
    ...base_row,
    id: "rows_no_usage:transcripts",
    kind: "notice",
    group: "notice",
    code: "rows_no_usage",
    thing: "transcripts",
    params: { count: "3" },
    fix: { kind: "cant_fix_here", target: null, reason: "not_fixable" },
  },
];

function allGroups(body: Json): void {
  const rows = body.rows ?? [];
  body.rows = [...rows, ...EXTRA_ROWS];
  body.counted = (body.rows as { group: string }[]).filter(
    (r) => r.group === "couldnt_read" || r.group === "wont_load" || r.group === "not_as_set",
  ).length;
}

function longGroup(body: Json): void {
  const many = Array.from({ length: 30 }, (_, i) => ({
    ...base_row,
    id: `json_invalid:${String(i)}`,
    group: "wont_load",
    code: "json_invalid",
    thing: `file-${String(i)}.json`,
    part: "settings",
    file: `file-${String(i)}.json`,
    line: 1,
    fix: { kind: "cant_fix_here", target: null, reason: "managed" },
  }));
  body.rows = [...(body.rows ?? []), ...many];
  body.counted = (body.rows as { group: string }[]).filter((r) => r.group !== "cant_tell").length;
}

function empty(body: Json): void {
  body.rows = [];
  body.counted = 0;
}

/** A plugin agent beside the file agent of the same name, in both Agents answers. */
async function withPluginAgent(page: Page): Promise<void> {
  await patch(page, "**/api/agents?*", (body) => {
    const ran = body.ran ?? [];
    const scribe = ran.find((r) => r.agent === "scribe");
    if (scribe === undefined) return;
    ran.push({
      ...scribe,
      scope: "plugin",
      plugin: "lint-kit",
      item_id: "agents:lint-kit:scribe",
      set: null,
      set_reason: null,
      status: null,
      reason_code: "agent_source_unchecked",
      runs: 2,
      sessions: 1,
      cost: 0.12,
      share: 0.001,
    });
  });
  await patch(page, "**/api/setup/agents*", (body) => {
    const items = body.items ?? [];
    const scribe = items.find((i) => i.id === "agents:scribe") as
      | (Record<string, unknown> & { facts: { agent: { fields: Record<string, unknown>[] } } })
      | undefined;
    if (scribe === undefined) return;
    const fields = scribe.facts.agent.fields.filter((f) => f.name !== "model");
    items.push({
      ...scribe,
      id: "agents:lint-kit:scribe",
      scope: "plugin",
      status: "ignored",
      effective: { value: null, origin: "unknown", by_item: null },
      read_only_reason: { code: "plugin", params: { plugin: "lint-kit" }, command: null },
      facts: {
        agent: {
          plugin: "lint-kit",
          fields: [
            ...fields,
            {
              name: "permissionMode",
              value: { text: "acceptEdits", masked: false },
              line: 6,
              ignored: true,
            },
            { name: "hooks", value: { text: "1 hook", masked: false }, line: 7, ignored: true },
          ],
        },
      },
    });
  });
}

/* ---------- the matrix ---------- */

interface State {
  name: string;
  path: string;
  /** Sets up the in-flight changes. */
  prepare?: (page: Page) => Promise<void>;
  /** What must be on screen before axe runs. */
  ready: (page: Page) => Locator;
  server?: "demo" | "flow";
}

const groupName = (group: string, n: number): string => fill(en.fx_g_aria, { group, n });

const STATES: State[] = [
  {
    name: "To fix, every group and every fix kind (patched)",
    path: `/p/${PROJECT}/to-fix`,
    prepare: (page) => patch(page, "**/api/problems*", allGroups),
    ready: (page) =>
      page.getByRole("heading", { level: 2, name: groupName(en.fx_g_couldnt_read, 1) }),
  },
  {
    name: "To fix, the demo's own rows (Driftwood)",
    path: "/p/driftwood/to-fix",
    ready: (page) => page.getByRole("heading", { level: 2, name: groupName(en.fx_g_wont_load, 2) }),
  },
  {
    name: "To fix, nothing to fix (patched)",
    path: `/p/${PROJECT}/to-fix`,
    prepare: (page) => patch(page, "**/api/problems*", empty),
    ready: (page) => page.getByRole("heading", { level: 2, name: en.fx_empty_h }),
  },
  {
    name: "To fix, a long group (patched)",
    path: `/p/${PROJECT}/to-fix`,
    prepare: (page) => patch(page, "**/api/problems*", longGroup),
    ready: (page) => page.getByRole("button", { name: /^Show \d+ more$/ }),
  },
  {
    name: "Agents, the inspector beside the table",
    path: `/p/${PROJECT}/review/agents?range=30d&agent=builder`,
    ready: (page) => page.getByRole("heading", { level: 2, name: "builder" }),
  },
  {
    name: "Agents, a plugin row and its inspector (patched)",
    path: `/p/${PROJECT}/review/agents?range=30d&agent=lint-kit%3Ascribe`,
    prepare: withPluginAgent,
    ready: (page) => page.getByText(en.ag_ignored_h),
  },
];

for (const state of STATES) {
  for (const width of WIDTHS) {
    for (const theme of THEMES) {
      test(`${state.name} at ${String(width)}, ${theme}`, async ({ page, demo }) => {
        if (state.prepare !== undefined) await state.prepare(page);
        await openAt(page, demo, state.path, { width, theme });
        await expect(state.ready(page).first()).toBeVisible();
        const found = await problems(page, `${state.name} ${String(width)} ${theme}`, width);
        expect(found).toEqual([]);
      });
    }
  }
}

/* To fix and the setup Agents inspector at 320, in forced colours and with reduced motion. */
const LOOKS = [
  ["forced colours", { forced: true }],
  ["reduced motion", { reduced: true }],
] as const;

const NARROW: { name: string; path: string; ready: (page: Page) => Locator }[] = [
  {
    name: "To fix",
    path: "/p/driftwood/to-fix",
    ready: (page) => page.getByRole("heading", { level: 2, name: groupName(en.fx_g_wont_load, 2) }),
  },
  {
    name: "the Agents inspector in Your setup",
    path: `/p/${PROJECT}/setup/agents/builder`,
    ready: (page) => page.getByRole("heading", { level: 2, name: "builder" }),
  },
];

for (const narrow of NARROW) {
  for (const [look, flag] of LOOKS) {
    test(`${narrow.name} passes axe at 320 in ${look}`, async ({ page, demo }) => {
      await openAt(page, demo, narrow.path, { width: 320, ...flag });
      await expect(narrow.ready(page).first()).toBeVisible();
      const found = await problems(page, `${narrow.name} 320 ${look}`, 320);
      expect(found).toEqual([]);
    });
  }
}

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    test(`Live, See why on a Model check finding (patched) at ${String(width)}, ${theme}`, async ({
      page,
      flow,
    }) => {
      await patch(page, "**/api/sessions/*/timeline*", (body) => {
        const row = body.model_check?.rows.find((r) => r.status === "lowered");
        if (row !== undefined) row.item_id = "settings:effortLevel";
      });
      await openAt(page, flow, `/p/${PROJECT}/live`, { width, theme });
      const link = page.getByRole("link", {
        name: fill(en.mc_see_why_aria, { agent: en.tl_main }),
      });
      await expect(link).toBeVisible();
      const found = await problems(page, `See why ${String(width)} ${theme}`, width);
      expect(found).toEqual([]);
    });
  }
}

/* ---------- exact text ---------- */

test("To fix names each group, row and action from the deck", async ({ page, demo }) => {
  await patch(page, "**/api/problems*", allGroups);
  await openAt(page, demo, `/p/${PROJECT}/to-fix`, { width: 1440, theme: "light" });
  // The demo's own lowered row plus the patched rows make five counted problems, in the order
  // Couldn't read, Won't load, Not as set, Can't tell and Notices.
  const groups = page.getByRole("heading", { level: 2 });
  await expect(groups).toHaveText([
    en.fx_g_couldnt_read,
    en.fx_g_wont_load,
    en.fx_g_not_as_set,
    en.fx_g_cant_tell,
    en.fx_g_notice,
  ]);
  await expect(groups.nth(0)).toHaveAccessibleName(groupName(en.fx_g_couldnt_read, 1));
  await expect(groups.nth(1)).toHaveAccessibleName(groupName(en.fx_g_wont_load, 2));
  await expect(groups.nth(2)).toHaveAccessibleName(groupName(en.fx_g_not_as_set, 2));
  await expect(page.getByText(en.fx_q_couldnt_read)).toBeVisible();
  await expect(page.getByText(en.fx_q_wont_load)).toBeVisible();
  await expect(page.getByText(en.fx_q_not_as_set)).toBeVisible();
  await expect(page.getByText(en.fx_q_cant_tell)).toBeVisible();
  await expect(page.getByText(en.fx_q_notice)).toBeVisible();
  await expect(
    page.getByText(fill(en.fx_sub_other, { n: 5, project: "Tidewater reporting" })),
  ).toBeVisible();

  // Every fix kind, by its accessible name or its text.
  await expect(
    page.getByRole("button", {
      name: fill(en.fx_copy_path_aria, { file: "~/config/agents/notes.md" }),
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: fill(en.fx_copy_cmd_aria, { thing: "archive" }) }),
  ).toBeVisible();
  await expect(page.getByText(en.fx_cmd_note)).toBeVisible();
  await expect(page.getByText(en.fx_cant_managed)).toBeVisible();
  await expect(page.getByText(en.fx_cant_plugin)).toBeVisible();
  await expect(
    page.getByRole("link", { name: fill(en.fx_open, { item: en.sl_effortLevel }) }),
  ).toHaveAttribute("href", `#/p/${PROJECT}/setup/settings/effortLevel`);
  // A notice is one sentence with no action.
  const notices = page.locator("section", {
    has: page.getByRole("heading", { name: en.fx_g_notice }),
  });
  await expect(notices.getByText(fill(en.pc_rows_no_usage_other, { n: 3 }))).toBeVisible();
  await expect(notices.getByRole("button")).toHaveCount(0);
  await expect(notices.getByRole("link")).toHaveCount(0);
});

test("the nav link's name carries the count", async ({ page, demo }) => {
  await openAt(page, demo, `/p/${PROJECT}/live`, { width: 1440, theme: "light" });
  const link = page
    .getByRole("navigation", { name: en.nav_aria })
    .getByRole("link", { name: fill(en.tofix_aria_one, { n: 1 }) });
  await expect(link).toBeVisible();
  await expect(link).toContainText("1");
});

for (const [state, name] of [
  ["unchecked", en.tofix_unchecked_aria],
  ["failed", en.tofix_failed_aria],
] as const) {
  for (const width of WIDTHS) {
    test(`the nav says ${state} with no number at ${String(width)}`, async ({ page, demo }) => {
      await patch(page, "**/api/app?*", (body) => {
        body.to_fix = { state, count: null, etag: null };
        body.to_fix_count = null;
      });
      await openAt(page, demo, `/p/${PROJECT}/live`, { width, theme: "light" });
      const link = page.getByRole("navigation", { name: en.nav_aria }).getByRole("link", { name });
      await expect(link).toBeVisible();
      await expect(link).not.toContainText(/\d/);
    });
  }
}

/* ---------- copy ---------- */

test("Copy path puts the full path on the clipboard and says Copied once", async ({
  page,
  demo,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: demo.baseURL });
  let full = "";
  page.on("response", (res) => {
    if (new URL(res.url()).pathname !== "/api/problems") return;
    void res.json().then((body: Json) => {
      const copy = (body.rows ?? []).find(
        (r) => (r.fix as { kind: string } | undefined)?.kind === "copy_path",
      );
      if (copy !== undefined) full = (copy.fix as { target: string }).target;
    });
  });
  await openAt(page, demo, "/p/driftwood/to-fix", { width: 1440, theme: "light" });
  const button = page.getByRole("button", { name: /^Copy path of / }).first();
  await expect(button).toBeVisible();
  await button.click();
  await expect(status(page)).toHaveText(en.an_copied);
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(full);
  expect(full).toMatch(/^\//);
  // The row's own status is not a second live region.
  await expect(page.locator("[role='status']")).toHaveCount(1);
});

test("Copy command puts the masked command on the clipboard and says Copied once", async ({
  page,
  demo,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: demo.baseURL });
  await patch(page, "**/api/problems*", allGroups);
  await openAt(page, demo, `/p/${PROJECT}/to-fix`, { width: 1440, theme: "light" });
  await page.getByRole("button", { name: fill(en.fx_copy_cmd_aria, { thing: "archive" }) }).click();
  await expect(status(page)).toHaveText(en.an_copied);
  await expect
    .poll(() => page.evaluate(() => navigator.clipboard.readText()))
    .toBe("claude mcp remove archive -s user");
});

test("Show more reveals the rest of a long group and moves focus to the first new row", async ({
  page,
  demo,
}) => {
  await patch(page, "**/api/problems*", longGroup);
  await openAt(page, demo, `/p/${PROJECT}/to-fix`, { width: 1440, theme: "light" });
  const more = page.getByRole("button", { name: /^Show \d+ more$/ });
  await expect(more).toBeVisible();
  const group = page.locator("section", {
    has: page.getByRole("heading", { level: 2, name: /^Won't load, / }),
  });
  await expect(group.getByRole("heading", { level: 3 })).toHaveCount(25);
  await more.focus();
  await page.keyboard.press("Enter");
  await expect(group.getByRole("heading", { level: 3 })).toHaveCount(30);
  await expect(more).toHaveCount(0);
});

/* ---------- flows ---------- */

test("a lowered agent is a Not as set row that says what runs and opens the cap (patched)", async ({
  page,
  demo,
}) => {
  await patch(page, "**/api/problems*", (body) => {
    body.rows = [
      ...(body.rows ?? []),
      {
        ...base_row,
        id: "agent_lowered:agents:judge:5",
        group: "not_as_set",
        code: "agent_lowered",
        thing: "judge",
        part: "agents",
        item_id: "agents:judge",
        file: ".claude/agents/judge.md",
        line: 5,
        params: { setting: "effort", value: "high", runs: "medium", cap: "maxEffortLevel" },
        fix: { kind: "open_item", target: "settings:maxEffortLevel", reason: null },
      },
    ];
  });
  await openAt(page, demo, `/p/${PROJECT}/to-fix`, { width: 1440, theme: "light" });
  await expect(page.getByText(fill(en.pc_agent_lowered_t, { thing: "judge" }))).toBeVisible();
  await expect(
    page.getByText(
      fill(en.pc_agent_lowered_c, {
        where: ".claude/agents/judge.md line 5",
        setting: "effort",
        value: "high",
        cap: en.sl_maxEffortLevel,
        runs: "medium",
      }),
    ),
  ).toBeVisible();
  await expect(
    page.getByText(
      fill(en.pc_agent_lowered_q, { setting: "effort", runs: "medium", value: "high" }),
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: fill(en.fx_open, { item: en.sl_maxEffortLevel }) }),
  ).toHaveAttribute("href", `#/p/${PROJECT}/setup/settings/maxEffortLevel`);
});

test("the nav count opens To fix, and a row opens its item", async ({ page, demo }) => {
  await openAt(page, demo, `/p/${PROJECT}/live`, { width: 1440, theme: "light" });
  await page
    .getByRole("navigation", { name: en.nav_aria })
    .getByRole("link", { name: fill(en.tofix_aria_one, { n: 1 }) })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: en.fx_h1 })).toBeFocused();
  await expect(
    page.getByText(fill(en.fx_sub_one, { n: 1, project: "Tidewater reporting" })),
  ).toBeVisible();
  const open = page.getByRole("link", { name: fill(en.fx_open, { item: en.sl_effortLevel }) });
  await expect(open).toBeVisible();
  await open.click();
  expect(await hash(page)).toBe(`#/p/${PROJECT}/setup/settings/effortLevel`);
});

test("an Agents row opens its inspector and back returns, at 1440", async ({ page, demo }) => {
  await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d`, {
    width: 1440,
    theme: "light",
  });
  const link = page.getByRole("link", { name: "builder", exact: true });
  await link.focus();
  await page.keyboard.press("Enter");
  const heading = page.getByRole("heading", { level: 2, name: "builder" });
  await expect(heading).toBeFocused();
  expect(await hash(page)).toContain("agent=builder");
  await expect(page.getByRole("region", { name: "builder" })).toBeVisible();
  // The table narrows to Agent, Check and Cost.
  const table = page.getByRole("table", { name: en.ag_h });
  // The narrowed columns are clipped to one pixel, which the browser still counts as visible.
  const setColumn = table.getByRole("columnheader", { name: en.ag_col_set });
  const widthOf = async (): Promise<number> => (await setColumn.boundingBox())?.width ?? 0;
  await expect.poll(widthOf).toBeLessThanOrEqual(1);
  await expect(table.getByRole("columnheader", { name: en.ag_col_cost })).toBeVisible();
  await expect(table.getByRole("link", { name: "builder", exact: true })).toHaveAttribute(
    "aria-current",
    "true",
  );
  // Open in Your setup goes to the same item's page.
  await page.getByRole("link", { name: new RegExp(en.ag_open_setup) }).click();
  expect(await hash(page)).toBe(`#/p/${PROJECT}/setup/agents/builder`);
  // Back returns to the Agents page with the inspector still open.
  await page.goBack();
  await expect(page.getByRole("region", { name: "builder" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("region", { name: "builder" })).toHaveCount(0);
  await expect.poll(widthOf).toBeGreaterThan(20);
});

test("at 375 an agent is its own page and the back link returns focus to its row", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d`, { width: 375, theme: "light" });
  const link = page.getByRole("link", { name: "builder", exact: true });
  await link.focus();
  await page.keyboard.press("Enter");
  const region = page.getByRole("region", { name: "builder" });
  await expect(region).toBeVisible();
  await expect(page.getByRole("table", { name: en.ag_h })).toHaveCount(0);
  await region.getByRole("link", { name: fill(en.sp_back, { part: en.sf_agents }) }).click();
  await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();
  await expect(page.getByRole("link", { name: "builder", exact: true })).toBeFocused();
});

test("at 375 a picked agent hides the scope bar title and keeps Range, and at rest shows both", async ({
  page,
  demo,
}) => {
  const title = page.locator(".scope-bar .page-header-title");
  const range = page.locator(".scope-bar-range");
  const widthOf = async (): Promise<number> => (await title.boundingBox())?.width ?? 0;
  await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d`, { width: 375 });
  await expect(title).toBeVisible();
  await expect(title).toHaveText(en.nav_agents);
  await expect(range).toBeVisible();
  await page.getByRole("link", { name: "builder", exact: true }).click();
  await expect(page.getByRole("region", { name: "builder" })).toBeVisible();
  // The title is clipped to one pixel, which the browser still counts as visible, and its text stays
  // in the page for readers.
  await expect.poll(widthOf).toBeLessThanOrEqual(1);
  await expect(page.getByRole("heading", { level: 1, name: en.nav_agents })).toHaveCount(1);
  await expect(range).toBeVisible();
  await expect(range.getByRole("button")).toBeVisible();
  // Back to the list shows the title again.
  await page
    .getByRole("region", { name: "builder" })
    .getByRole("link", { name: fill(en.sp_back, { part: en.sf_agents }) })
    .click();
  await expect.poll(widthOf).toBeGreaterThan(20);
});

test("an agent that is gone says so and the link back takes focus (needs the setup part)", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d&agent=ghost`, {
    width: 1440,
    theme: "light",
  });
  await expect(page.getByText(fill(en.sp_gone_h, { part: en.sf_agents }))).toBeVisible();
  await expect(
    page.getByRole("link", { name: fill(en.sp_back, { part: en.sf_agents }) }),
  ).toBeFocused();
});

test("a plugin row names its plugin, says Not checked, and opens a read-only inspector", async ({
  page,
  demo,
}) => {
  await withPluginAgent(page);
  await openAt(page, demo, `/p/${PROJECT}/review/agents?range=30d`, {
    width: 1440,
    theme: "light",
  });
  const table = page.getByRole("table", { name: en.ag_h });
  const links = table.getByRole("link", { name: "scribe", exact: true });
  // The file agent and the plugin agent of one name are two rows.
  await expect(links).toHaveCount(2);
  const row = table.locator("tr", { hasText: fill(en.ag_src_plugin, { plugin: "lint-kit" }) });
  await expect(row).toHaveCount(1);
  const check = row.getByText(en.ag_chk_unchecked, { exact: true });
  await expect(check).toBeVisible();
  await expect(check).toHaveAccessibleDescription(en.ag_chk_unchecked_aria);
  await row.getByRole("link", { name: "scribe", exact: true }).click();
  expect(await hash(page)).toContain("agent=lint-kit%3Ascribe");
  const region = page.getByRole("region", { name: "scribe" });
  await expect(region).toContainText(fill(en.ro_plugin, { plugin: "lint-kit" }));
  await expect(region.getByText(en.ag_ignored_h)).toBeVisible();
  await expect(region.getByText("permissionMode")).toBeVisible();
  await expect(region.getByRole("button", { name: en.in_copy })).toHaveCount(1);
  await expect(region.getByRole("link", { name: new RegExp(en.ag_open_setup) })).toHaveAttribute(
    "href",
    `#/p/${PROJECT}/setup/agents/lint-kit:scribe`,
  );
});

test("Live shows See why only on a finding with an item, and the link opens it", async ({
  page,
  flow,
}) => {
  // Unpatched, the flow's findings name no item, so Live shows no link.
  await openAt(page, flow, `/p/${PROJECT}/live`, { width: 1440, theme: "light" });
  const card = page.getByRole("region", { name: en.mc_h });
  await expect(card).toBeVisible();
  await expect(card.getByRole("link")).toHaveCount(0);
});

test("Live's See why link opens the item's page (patched)", async ({ page, flow }) => {
  await patch(page, "**/api/sessions/*/timeline*", (body) => {
    const row = body.model_check?.rows.find((r) => r.status === "lowered");
    if (row !== undefined) row.item_id = "settings:effortLevel";
  });
  await openAt(page, flow, `/p/${PROJECT}/live`, { width: 1440, theme: "light" });
  const link = page.getByRole("link", { name: fill(en.mc_see_why_aria, { agent: en.tl_main }) });
  await expect(link).toBeVisible();
  await link.click();
  expect(await hash(page)).toBe(`#/p/${PROJECT}/setup/settings/effortLevel`);
});
