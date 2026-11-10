/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Your setup and the surface pages against the real server on the demo build (`--demo --test-clock`,
 * with the setup overlay, so the demo holds skills, instruction files with imports, hooks, MCP
 * servers, plugins and three extra projects, fact J-b0ae). Four kinds of check.
 *
 * Matrix. Each state renders at 320, 375 and 1440, light and dark, with axe and no sideways scroll
 * at phone widths. The states are the map with the Switch off and on, a surface with an item
 * picked, a masked value, a read-only item, a not-read-here item, the Couldn't read card, an empty
 * part and a long grouped list. A forced-colours pass and a reduced-motion pass check the same
 * pages. States the demo has no data for (not read here, Couldn't read) change one answer in
 * flight, as the Review specs do.
 *
 * Switch. It keeps its state in `?scopes=1`, flips with no request to the server and keeps focus.
 *
 * Phone. The list is the page, an item opens as its own page, and the back link returns focus and
 * scroll to the item.
 *
 * Exact text. The Switch's name and state, the breadcrumb's current page and the inspector's
 * region and h2 come from the string deck.
 *
 * Set SETUP_SHOTS to a folder to save a screenshot of each matrix state, for review.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const LARGE = "setup-large";
/** The matrix runs at 320, the narrowest phone the plan names, 375 and 1440. */
const WIDTHS = [320, 375, 1440] as const;
const THEMES = ["light", "dark"] as const;
const SHOTS = process.env.SETUP_SHOTS;

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

interface Look {
  width: number;
  theme?: "light" | "dark";
  forced?: boolean;
  reduced?: boolean;
}

async function openAt(page: Page, server: Server, path: string, look: Look): Promise<void> {
  await page.setViewportSize({ width: look.width, height: 900 });
  await page.emulateMedia({
    colorScheme: look.theme ?? "light",
    ...(look.forced === true ? { forcedColors: "active" as const } : {}),
    ...(look.reduced === true ? { reducedMotion: "reduce" as const } : {}),
  });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await goTo(page, path);
}

async function goTo(page: Page, path: string): Promise<void> {
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, path);
}

const setup = (project = PROJECT, query = ""): string => `/p/${project}/setup${query}`;
const part = (name: string, project = PROJECT, query = ""): string =>
  `/p/${project}/setup/${name}${query}`;
const item = (name: string, key: string, project = PROJECT): string =>
  `/p/${project}/setup/${name}/${key}`;

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

type Json = Record<string, unknown> & {
  items?: Record<string, unknown>[];
  unreadable?: Record<string, unknown>[];
  parts?: { scopes: { scope: string; state: string }[] }[];
};

/** A project off Bar Tab's list. The server then cannot see its two project scopes. */
function unlist(body: Json): void {
  body.listed = false;
  for (const row of body.parts ?? []) {
    for (const cell of row.scopes) {
      if (cell.scope === "project" || cell.scope === "project_local") cell.state = "not_visible";
    }
  }
}

/** Changes one setup answer in flight, so a state the demo has no data for can be drawn. */
async function patch(
  page: Page,
  glob: string | RegExp,
  change: (body: Json) => void,
): Promise<void> {
  await page.route(glob, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Json;
    change(body);
    await route.fulfill({ response, json: body });
  });
}

/** The state of the matrix: where to go, what to wait for, and what to change in flight. */
interface Case {
  name: string;
  path: string;
  ready: (page: Page) => Locator;
  before?: (page: Page) => Promise<void>;
}

const heading = (page: Page, name: string): Locator =>
  page.getByRole("heading", { level: 2, name, exact: true });

const CASES: Case[] = [
  {
    name: "map-off",
    path: setup(),
    ready: (page) => heading(page, en.su_card_h),
  },
  {
    name: "map-on",
    path: setup(PROJECT, "?scopes=1"),
    ready: (page) => page.locator(".setup-map-chips").first(),
  },
  {
    name: "map-unlisted",
    path: setup(PROJECT, "?scopes=1"),
    ready: (page) => page.locator(".setup-notice"),
    before: (page) => patch(page, /\/api\/setup\?/, unlist),
  },
  {
    name: "surface-picked",
    path: item("settings", "effortLevel"),
    ready: (page) => heading(page, "Effort"),
  },
  {
    name: "masked",
    path: item("settings", "env.ANTHROPIC_API_KEY"),
    ready: (page) => page.getByText(en.in_masked, { exact: true }),
  },
  {
    name: "read-only",
    path: item("hooks", "PreToolUse:Bash:1"),
    ready: (page) => page.locator(".inspector-readonly"),
  },
  {
    name: "instructions",
    path: item("instructions", "CLAUDE.md"),
    ready: (page) => page.locator(".setup-chain"),
  },
  {
    name: "mcp-readonly",
    path: item("mcp", "notes"),
    ready: (page) => page.locator(".command-row"),
  },
  {
    name: "not-read",
    path: item("plugins", "hivemind@bartab-demo"),
    ready: (page) => page.locator(".inspector-not-read"),
    before: (page) =>
      patch(page, /\/api\/setup\/plugins\?/, (body) => {
        for (const it of body.items ?? []) {
          if (it.id === "plugins:hivemind@bartab-demo") it.not_read = "plugin_outside_plugins";
        }
      }),
  },
  {
    name: "couldnt-read",
    path: part("agents"),
    ready: (page) => page.locator(".setup-cr"),
    before: (page) =>
      patch(page, /\/api\/setup\/agents\?/, (body) => {
        body.unreadable = [
          {
            file: "~/config/agents/notes.md",
            full_path: "/work/config/agents/notes.md",
            part: "agents",
            problem: "read_failure:permission:~/config/agents/notes.md",
            reason: "permission",
            scope: "user",
          },
        ];
      }),
  },
  {
    name: "empty",
    path: part("output_style"),
    ready: (page) => page.getByText(en.st_set),
  },
  {
    name: "long-grouped",
    path: part("permissions", LARGE),
    ready: (page) => page.locator(".item-jump"),
  },
];

test.describe("matrix", () => {
  for (const c of CASES) {
    test(`${c.name} passes axe at every width, light and dark`, async ({ page, demo }) => {
      test.setTimeout(180_000);
      const found: string[] = [];
      for (const width of WIDTHS) {
        for (const theme of THEMES) {
          const label = `${c.name} ${String(width)} ${theme}`;
          await page.unrouteAll({ behavior: "ignoreErrors" });
          await c.before?.(page);
          await openAt(page, demo, c.path, { width, theme });
          await expect(c.ready(page)).toBeVisible();
          if (SHOTS !== undefined) {
            mkdirSync(SHOTS, { recursive: true });
            await page.screenshot({
              path: join(SHOTS, `${c.name}-${String(width)}-${theme}.png`),
              fullPage: true,
            });
          }
          found.push(...(await problems(page, label, width)));
        }
      }
      expect(found).toEqual([]);
    });

    test(`${c.name} passes axe in forced colours and with reduced motion`, async ({
      page,
      demo,
    }) => {
      test.setTimeout(120_000);
      const found: string[] = [];
      for (const width of [375, 1440]) {
        for (const look of [{ forced: true }, { reduced: true }]) {
          const label = `${c.name} ${String(width)} ${"forced" in look ? "forced" : "reduced"}`;
          await page.unrouteAll({ behavior: "ignoreErrors" });
          await c.before?.(page);
          await openAt(page, demo, c.path, { width, ...look });
          await expect(c.ready(page)).toBeVisible();
          found.push(...(await problems(page, label, width)));
        }
      }
      expect(found).toEqual([]);
    });
  }
});

test.describe("the Switch", () => {
  test("keeps its state in the URL, fetches nothing and keeps focus", async ({ page, demo }) => {
    await openAt(page, demo, setup(), { width: 1440 });
    const toggle = page.getByRole("switch", { name: en.su_switch });
    await expect(toggle).not.toBeChecked();
    await expect(page.locator(".setup-map-chips")).toHaveCount(0);
    const asked: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/")) asked.push(request.url());
    });
    await toggle.focus();
    await page.keyboard.press("Space");
    await expect(toggle).toBeChecked();
    await expect(toggle).toBeFocused();
    await expect(page.locator(".setup-map-chips").first()).toBeVisible();
    await expect.poll(() => page.evaluate(() => window.location.hash)).toContain("scopes=1");
    expect(asked.filter((url) => url.includes("/api/setup"))).toEqual([]);
    await page.keyboard.press("Space");
    await expect(toggle).not.toBeChecked();
    await expect(page.locator(".setup-map-chips")).toHaveCount(0);
    expect(await page.evaluate(() => window.location.hash)).not.toContain("scopes");
  });

  test("shows scope chips, not columns, and says Not visible here for the command line", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, setup(PROJECT, "?scopes=1"), { width: 1440 });
    const row = page.locator('tr[data-part="settings"]');
    await expect(row.locator(".scope-chip", { hasText: en.sc_command_line })).toContainText(
      en.su_nv,
    );
    await expect(page.getByRole("columnheader")).toHaveCount(3);
    await expect(page.locator(".setup-shell-line")).toBeVisible();
  });

  test("says Not read here in the project scopes of a project off the list", async ({
    page,
    demo,
  }) => {
    await patch(page, /\/api\/setup\?/, unlist);
    await openAt(page, demo, setup(PROJECT, "?scopes=1"), { width: 1440 });
    const row = page.locator('tr[data-part="settings"]');
    await expect(row.locator(".scope-chip", { hasText: en.sc_project })).toContainText(en.su_nr);
    await expect(page.locator(".setup-notice")).toContainText(en.su_unlisted_link);
  });
});

test.describe("a surface", () => {
  test("picks the first item that needs a look at 1440 with no item in the URL", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, part("settings"), { width: 1440 });
    // Effort is Lowered, so it comes before Model, which is in effect.
    await expect(page.locator('.item-list a[aria-current="page"]')).toContainText("Effort");
    await expect(heading(page, "Effort")).toBeVisible();
  });

  test("moves focus to the inspector heading when an item opens", async ({ page, demo }) => {
    await openAt(page, demo, item("settings", "effortLevel"), { width: 1440 });
    await page.getByRole("link", { name: /^Model(?!s)/ }).click();
    await expect(heading(page, "Model")).toBeFocused();
    await expect.poll(() => page.evaluate(() => window.location.hash)).toContain("/settings/model");
  });

  test("copies the full path while the screen shows the short one", async ({
    page,
    demo,
    context,
  }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await openAt(page, demo, item("settings", "effortLevel"), { width: 1440 });
    await expect(page.getByText(".claude/settings.local.json:3")).toBeVisible();
    await page.getByRole("button", { name: en.in_copy }).click();
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    expect(copied.endsWith("/projects/tidewater-reporting/.claude/settings.local.json")).toBe(true);
    expect(copied.startsWith("/")).toBe(true);
    await expect(page.locator("div.sr-only[role='status']")).toHaveText(en.an_copied);
  });

  test("says what a masked value is and never shows the secret", async ({ page, demo }) => {
    await openAt(page, demo, item("settings", "env.ANTHROPIC_API_KEY"), { width: 1440 });
    await expect(page.getByText(en.in_masked, { exact: true })).toBeVisible();
    await expect(page.locator(".value-masked").first()).toContainText(en.in_masked_word);
    await expect(page.locator("body")).not.toContainText("sk-ant");
  });

  test("shows the read-only reason with Copy path for a plugin item", async ({ page, demo }) => {
    await openAt(page, demo, item("hooks", "PreToolUse:Bash:1"), { width: 1440 });
    const box = page.locator(".inspector-readonly");
    await expect(box).toContainText("hivemind");
    await expect(box.getByRole("button", { name: en.in_copy })).toBeVisible();
  });

  test("shows the claude mcp command to copy for a user MCP server", async ({ page, demo }) => {
    await openAt(page, demo, item("mcp", "notes"), { width: 1440 });
    const box = page.locator(".inspector-readonly");
    await expect(box).toContainText(en.ro_claude_json_command);
    await expect(box.getByRole("button", { name: en.lk_copy })).toBeVisible();
  });

  test("shows a plugin that is not read as Unknown, with the box under the headline", async ({
    page,
    demo,
  }) => {
    await patch(page, /\/api\/setup\/plugins\?/, (body) => {
      for (const it of body.items ?? []) {
        if (it.id === "plugins:hivemind@bartab-demo") {
          // The server sets both together for a plugin installed outside the plugins folder.
          it.not_read = "plugin_outside_plugins";
          it.status = "unknown";
        }
      }
    });
    await openAt(page, demo, item("plugins", "hivemind@bartab-demo"), { width: 1440 });
    const box = page.locator(".inspector-not-read");
    await expect(box).toContainText(en.pl_outside);
    await expect(box.locator(".status-chip-unknown")).toHaveText(en.status_unknown);
    await expect(page.locator(".inspector-head .status-chip-unknown")).toHaveText(
      en.status_unknown,
    );
    await expect(page.locator(".item-not-read")).toHaveCount(0);
    await expect(
      page
        .locator(".item-link", { hasText: "hivemind@bartab-demo" })
        .locator(".status-chip-unknown"),
    ).toHaveText(en.status_unknown);
  });

  test("shows an overridden agent's outcome, its callout, its own files and the Agents link", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, item("agents", "builder"), { width: 1440 });
    const inspector = page.locator(".inspector");
    await expect(inspector.locator(".inspector-head .status-chip-overridden")).toHaveText(
      en.status_overridden,
    );
    await expect(inspector.locator(".agent-callout")).toContainText(
      en.mc_l_pin_overridden.replace("{agent}", "builder").split("{ran}")[0] ?? "",
    );
    await expect(inspector.locator(".agent-callout .status-chip-overridden")).toBeVisible();
    // The trail holds the agent's own files only.
    const rows = inspector.locator(".where-row");
    await expect(rows).not.toHaveCount(0);
    await expect(inspector.locator(".where-row .where-key")).toHaveCount(0);
    await expect(inspector.locator(".where-row", { hasText: /CLAUDE_CODE|maxEffort/ })).toHaveCount(
      0,
    );
    await expect(
      inspector.locator(".inspector-small").filter({ hasText: /last 30 days/ }),
    ).toBeVisible();
    const link = inspector.getByRole("link", { name: en.nav_agents, exact: true });
    await expect(link).toHaveAttribute("href", /review\/agents\?range=30d&agent=builder$/);
    await expect(link).toHaveCSS("text-decoration-line", "none");
  });

  test("shows the Couldn't read card over the partial list", async ({ page, demo }) => {
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
    await openAt(page, demo, part("agents"), { width: 1440 });
    const card = page.locator(".setup-cr");
    await expect(card.getByRole("heading", { level: 3 })).toHaveText(
      fill(en.ft_unreadable_one, { n: "1" }),
    );
    await expect(card).toContainText(
      fill(en.cr_r_permission, { file: "~/config/agents/notes.md" }),
    );
    await expect(card).toContainText(en.cr_b);
    await expect(page.getByRole("link", { name: /^builder\b/ })).toBeVisible();
  });

  test("says what would appear in an empty part and offers to copy the folder path", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, part("output_style"), { width: 1440 });
    await expect(page.getByText(en.st_set)).toBeVisible();
    await expect(page.getByRole("button", { name: en.em_a_copy_folder })).toBeVisible();
  });

  test("cuts a long grouped list, with Jump to chips and Show n more", async ({ page, demo }) => {
    await openAt(page, demo, part("permissions", LARGE), { width: 1440 });
    const jump = page.locator(".item-jump");
    await expect(jump).toContainText(en.sp_jump);
    await expect(jump.getByRole("button")).toHaveCount(2);
    const rows = page.locator(".item-row");
    const before = await rows.count();
    expect(before).toBeLessThan(40);
    const more = page.getByRole("button", { name: /^Show \d+ more$/ });
    await more.first().focus();
    await page.keyboard.press("Enter");
    await expect.poll(() => rows.count()).toBeGreaterThan(100);
    // Focus lands on the first row the button revealed.
    await expect(page.locator(".item-link:focus")).toHaveCount(1);
  });

  test("keeps a short list whole, with no chips", async ({ page, demo }) => {
    await openAt(page, demo, part("permissions"), { width: 1440 });
    await expect(page.locator(".item-jump")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Show \d+ more/ })).toHaveCount(0);
  });

  test("says the item is gone and puts focus on the link back (need 27)", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, item("settings", "nope"), { width: 1440 });
    const link = page.getByRole("link", { name: fill(en.sp_back, { part: en.sf_settings }) });
    await expect(
      page.getByRole("heading", { level: 2, name: fill(en.sp_gone_h, { part: en.sf_settings }) }),
    ).toBeVisible();
    await expect(link).toBeFocused();
  });

  test("goes back to Your setup for a part it does not know", async ({ page, demo }) => {
    await openAt(page, demo, part("nope"), { width: 1440 });
    await expect(heading(page, en.su_card_h)).toBeVisible();
  });
});

test.describe("on a phone", () => {
  test("the list is the page, and an item opens as its own page with a back link", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, part("settings"), { width: 375 });
    await expect(page.getByRole("navigation", { name: en.sf_settings })).toBeVisible();
    await expect(page.locator(".inspector")).toHaveCount(0);
    await page.getByRole("link", { name: /^Effort cap\b/ }).click();
    await expect(page.locator(".inspector")).toBeVisible();
    await expect(page.getByRole("navigation", { name: en.sf_settings })).toHaveCount(0);
    await expect(heading(page, "Effort cap")).toBeFocused();
    expect(await page.evaluate(() => window.location.hash)).toContain(
      "/setup/settings/maxEffortLevel",
    );
  });

  test("the back link returns focus and scroll to the item", async ({ page, demo }) => {
    await openAt(page, demo, part("permissions", LARGE), { width: 375 });
    // Show every allow rule, then open one far down the list, so the back link has to scroll.
    await page
      .getByRole("button", { name: /^Show \d+ more$/ })
      .first()
      .click();
    const last = page.locator(".item-link").nth(60);
    const name = (await last.locator(".item-name").innerText()).trim();
    await last.scrollIntoViewIfNeeded();
    await last.click();
    await expect(page.locator(".inspector")).toBeVisible();
    // The back link reads "← Permissions", with the arrow hidden from its name.
    await page.getByRole("link", { name: en.sf_permissions, exact: true }).click();
    const back = page
      .locator(".item-link", { has: page.locator(".item-name", { hasText: name }) })
      .first();
    await expect(back).toBeFocused();
    await expect(back).toBeInViewport();
  });
});

test.describe("exact accessible text", () => {
  test("names the Switch, the breadcrumb's current page and the inspector region", async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, setup(), { width: 1440 });
    await expect(page.getByRole("switch", { name: en.su_switch })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeVisible();

    await goTo(page, item("settings", "effortLevel"));
    const crumb = page.getByRole("navigation", { name: en.bc_label });
    await expect(crumb.getByRole("link", { name: en.nav_setup })).toBeVisible();
    await expect(crumb.locator('[aria-current="page"]')).toHaveText(en.sf_settings);
    await expect(page.getByRole("heading", { level: 1, name: en.sf_settings })).toBeVisible();
    await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: en.sf_settings })).toBeVisible();
  });
});
