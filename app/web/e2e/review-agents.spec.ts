/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Agents and Models against the real server on the demo build (`--demo --test-clock`, T is
 * October 30, 2026 at 6 PM in New York). Four kinds of check.
 *
 * Matrix. Each state of both pages (the demo's answer, answers changed in flight to cover the
 * cells the demo has no row for, loading, error and an empty range) renders at 375 and 1440,
 * light and dark, with axe and no sideways scroll. A forced-colours pass checks the same pages.
 *
 * Keyboard. With the keyboard only, at 375 and 1440, the person changes the range on Agents, goes
 * to Models by its link, and follows Summary's "Made of" link to the kinds card, which takes focus.
 *
 * Exact text. Each table's header is a `toMatchAriaSnapshot`, the kinds chart's image label is
 * asserted from the string deck, and the Agents total is compared with Summary's money card.
 *
 * Walkthrough. "Read the 30-day cost by agent" at 375 and 1440 uses the keyboard only, from Live
 * to Summary's "Where the money went" and on to Agents. It loads the page once and never sets the
 * hash or uses the mouse. The axe matrix runs at 320, 375 and 1440.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as base } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";
import { rmSync } from "node:fs";
import { formatCost } from "../src/lib/format";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const WIDTHS = [375, 1440] as const;
/** The axe matrix also runs at 320, the narrowest phone the plan names. */
const AXE_WIDTHS = [320, 375, 1440] as const;
const THEMES = ["light", "dark"] as const;
const KINDS_IMAGE = fill(en.md_img, {
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

const agents = (range: string): string => `/p/${PROJECT}/review/agents?range=${range}`;
const models = (range: string): string => `/p/${PROJECT}/review/models?range=${range}`;
const summary = (range: string): string => `/p/${PROJECT}/review/summary?range=${range}`;

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

const status = (page: Page): Locator => page.locator("div.sr-only[role='status']");

type Json = Record<string, unknown> & {
  ran?: Record<string, unknown>[];
  never_ran?: Record<string, unknown>[];
  rows?: Record<string, unknown>[];
  kinds?: Record<string, unknown>[];
  errors?: unknown[];
};

/** Changes one Review answer in flight, so a state the demo has no data for can be drawn. */
async function patch(page: Page, glob: string, change: (body: Json) => void): Promise<void> {
  await page.route(glob, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as Json;
    change(body);
    await route.fulfill({ response, json: body });
  });
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

/** The demo's Agents answer with a row of each kind the demo has no data for. */
function richAgents(body: Json): void {
  const ran = body.ran ?? [];
  const first = ran[0];
  const second = ran[1];
  if (first === undefined || second === undefined) return;
  // A mixed pair, an unpriced cost, a type with no file and a setup that sets nothing.
  first.ran_pairs = [
    { model: "claude-fable-5-1", effort: "medium", runs: 70 },
    { model: "claude-fable-5-1", effort: "xhigh", runs: 12 },
  ];
  first.unpriced = { requests: 3, models: ["claude-fable-5-1"] };
  ran.push(
    {
      ...second,
      agent: "Explore",
      scope: "no_file",
      set: null,
      set_reason: "no_file",
      status: null,
      runs: 2,
      cost: 0.05,
      share: 0.001,
    },
    {
      ...second,
      agent: "@unnamed",
      scope: "unnamed",
      set: null,
      set_reason: "sets_nothing",
      status: null,
      runs: 3,
      cost: 1.07,
      share: 0.003,
    },
  );
  body.never_ran = [
    {
      agent: "migrator",
      scope: "project",
      set: {
        model: { value: "claude-opus-5-5", file: null, line: 3, scope: "agent" },
        effort: { value: "high", file: null, line: 4, scope: "agent" },
      },
      set_reason: null,
    },
    { agent: "release-notes", scope: "user", set: null, set_reason: "sets_nothing" },
  ];
}

function unreadableSetup(body: Json): void {
  for (const row of body.ran ?? []) {
    row.set = null;
    row.set_reason = "read_failed";
    row.status = null;
  }
  body.errors = [{ card: "agent_setup", code: "setup_unreadable" }];
}

/** The demo's Models answer with a model that has no price. */
function unpricedModels(body: Json): void {
  const last = body.rows?.at(-1);
  const kinds = body.kinds?.at(-1);
  if (last === undefined || kinds === undefined) return;
  last.cost = null;
  last.share = null;
  last.cache_share = null;
  last.unpriced = { requests: 4, models: [last.model] };
  Object.assign(kinds, { input: 0, output: 0, cache_read: 0, cache_write: 0 });
  body.unpriced = { requests: 4, models: [last.model] };
}

// ---- matrix ----------------------------------------------------------------------------------

interface State {
  name: string;
  path: string;
  before?: (page: Page) => Promise<void>;
  ready: (page: Page) => Promise<void>;
}

const STATES: State[] = [
  {
    name: "agents 30 days",
    path: agents("30d"),
    ready: async (page) => {
      await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();
    },
  },
  {
    name: "agents today",
    path: agents("today"),
    ready: async (page) => {
      await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();
    },
  },
  {
    name: "agents mixed, no file, unpriced and not run",
    path: agents("30d"),
    before: (page) => patch(page, "**/api/agents*", richAgents),
    ready: async (page) => {
      await expect(page.getByText(en.ag_none_h)).toBeVisible();
      await expect(page.getByText(en.ag_src_unknown)).toBeVisible();
    },
  },
  {
    name: "agents setup unreadable",
    path: agents("30d"),
    before: (page) => patch(page, "**/api/agents*", unreadableSetup),
    ready: async (page) => {
      await expect(page.getByText(fill(en.er_h, { card: en.ag_setup_card }))).toBeVisible();
    },
  },
  {
    name: "agents empty",
    path: agents("30d"),
    before: (page) =>
      patch(page, "**/api/agents*", (body) => {
        body.ran = [];
        body.never_ran = [];
      }),
    ready: async (page) => {
      await expect(page.getByText(en.em_a)).toBeVisible();
    },
  },
  {
    name: "agents loading",
    path: agents("30d"),
    before: (page) => never(page, "**/api/agents*"),
    ready: async (page) => {
      await expect(page.getByText("Loading agents")).toBeAttached();
    },
  },
  {
    name: "agents error",
    path: agents("30d"),
    before: (page) => fail(page, "**/api/agents*"),
    ready: async (page) => {
      await expect(page.getByText("Couldn't load agents")).toBeVisible();
    },
  },
  {
    name: "models 30 days",
    path: models("30d"),
    ready: async (page) => {
      await expect(page.getByRole("img", { name: KINDS_IMAGE })).toBeVisible();
    },
  },
  {
    name: "models today",
    path: models("today"),
    ready: async (page) => {
      await expect(page.getByRole("table", { name: en.md_h })).toBeVisible();
    },
  },
  {
    name: "models landing on the kinds card",
    path: `${models("30d")}&section=kinds`,
    ready: async (page) => {
      await expect(page.getByRole("heading", { level: 2, name: en.md_kind_h })).toBeFocused();
    },
  },
  {
    name: "models with a model that has no price",
    path: models("30d"),
    before: (page) => patch(page, "**/api/models*", unpricedModels),
    ready: async (page) => {
      await expect(page.getByText(en.c_none_short).first()).toBeVisible();
    },
  },
  {
    name: "models empty",
    path: models("30d"),
    before: (page) =>
      patch(page, "**/api/models*", (body) => {
        body.rows = [];
        body.kinds = [];
      }),
    ready: async (page) => {
      await expect(page.getByText(en.em_a)).toBeVisible();
    },
  },
  {
    name: "models loading",
    path: models("30d"),
    before: (page) => never(page, "**/api/models*"),
    ready: async (page) => {
      await expect(page.getByText("Loading models")).toBeAttached();
    },
  },
  {
    name: "models error",
    path: models("30d"),
    before: (page) => fail(page, "**/api/models*"),
    ready: async (page) => {
      await expect(page.getByText("Couldn't load models")).toBeVisible();
    },
  },
];

for (const width of AXE_WIDTHS) {
  for (const theme of THEMES) {
    test(`every Agents and Models state passes axe at ${String(width)} wide, ${theme}`, async ({
      page,
      demo,
    }) => {
      test.setTimeout(180_000);
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

test("forced colours keep the tables and every kind pattern readable", async ({ page, demo }) => {
  await openAt(page, demo, "/", { width: 1440 });
  await page.emulateMedia({ forcedColors: "active", reducedMotion: "reduce" });
  await goTo(page, agents("30d"));
  await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();
  // Every status chip keeps its word, and the cost keeps its number beside the bar.
  await expect(page.getByText(en.status_overridden).first()).toBeVisible();
  const found = await problems(page, "agents forced colours", 1440);
  await goTo(page, models("30d"));
  await expect(page.getByRole("img", { name: KINDS_IMAGE })).toBeVisible();
  // Each pattern piece draws an outline of its own, so a kind never vanishes with its fill.
  const outlines = await page
    .locator(".review-models-stack .review-models-kp")
    .evaluateAll((pieces) => pieces.map((piece) => getComputedStyle(piece).borderTopWidth));
  expect(outlines.length).toBeGreaterThan(0);
  expect(new Set(outlines)).toEqual(new Set(["1px"]));
  found.push(...(await problems(page, "models forced colours", 1440)));
  expect(found).toEqual([]);
});

// ---- exact text ------------------------------------------------------------------------------

test("the Agents header reads as its six columns", async ({ page, demo }) => {
  await openAt(page, demo, agents("30d"), { width: 1440 });
  const table = page.getByRole("table", { name: en.ag_h });
  await expect(table).toBeVisible();
  await expect(table.locator("thead")).toMatchAriaSnapshot(`
    - rowgroup:
      - row "${en.ag_col_agent} ${en.ag_col_set} ${en.ag_col_ran} ${en.ag_col_check} ${en.ag_col_runs} ${en.ag_col_cost}":
        - columnheader "${en.ag_col_agent}"
        - columnheader "${en.ag_col_set}"
        - columnheader "${en.ag_col_ran}"
        - columnheader "${en.ag_col_check}"
        - columnheader "${en.ag_col_runs}"
        - columnheader "${en.ag_col_cost}"
  `);
});

test("the Models header reads as its six columns", async ({ page, demo }) => {
  await openAt(page, demo, models("30d"), { width: 1440 });
  const table = page.getByRole("table", { name: en.md_h });
  await expect(table).toBeVisible();
  await expect(table.locator("thead")).toMatchAriaSnapshot(`
    - rowgroup:
      - row "${en.md_col_model} ${en.md_col_cost} ${en.md_col_share} ${en.md_col_tokens} ${en.md_col_cache} ${en.md_col_used}":
        - columnheader "${en.md_col_model}"
        - columnheader "${en.md_col_cost}"
        - columnheader "${en.md_col_share}"
        - columnheader "${en.md_col_tokens}"
        - columnheader "${en.md_col_cache}"
        - columnheader "${en.md_col_used}"
  `);
});

test("the Agents rows read as the demo's four agents, with the check word beside each", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, agents("30d"), { width: 1440 });
  const table = page.getByRole("table", { name: en.ag_h });
  await expect(table.locator("tbody tr")).toHaveCount(4);
  const builder = table.locator("tr[data-agent='builder']");
  await expect(builder).toContainText("builder");
  await expect(builder).toContainText(en.ag_src_user);
  await expect(builder).toContainText("Fable 5.1 · xhigh");
  await expect(builder).toContainText("Fable 5.1 · medium");
  await expect(builder).toContainText(en.status_overridden);
  const main = table.locator("tr[data-agent='@main']");
  await expect(main).toContainText(en.tl_main);
  await expect(main).toContainText(en.ag_main_src);
  await expect(main).toContainText(en.status_lowered);
  // The foot says the API-rate note once.
  await expect(page.getByText(/^Costs are estimates at API list prices/)).toHaveCount(1);
});

// A picked agent is its own page at 375, so the table is only on screen at 1440.
for (const width of [1440]) {
  test(`the picked Agents row keeps its text where the other rows have it, with the bar in the gutter at ${String(width)} wide`, async ({
    page,
    demo,
  }) => {
    await openAt(page, demo, `${agents("30d")}&agent=builder`, { width });
    const table = page.getByRole("table", { name: en.ag_h });
    const picked = table.locator("tr[data-agent='builder'] .review-agents-src");
    const other = table.locator("tr[data-agent='@main'] .review-agents-src");
    await expect(picked).toBeVisible();
    const pickedBox = await picked.boundingBox();
    const otherBox = await other.boundingBox();
    expect(pickedBox).not.toBeNull();
    expect(otherBox).not.toBeNull();
    expect(pickedBox?.x).toBe(otherBox?.x);
    // The picked fill starts where the dividers start (the first cell's left edge, the same in
    // every row), and the bar is a 3px start border at that edge.
    const pickedCell = await table.locator("tr[data-agent='builder'] th").boundingBox();
    const otherCell = await table.locator("tr[data-agent='@main'] th").boundingBox();
    expect(pickedCell?.x).toBe(otherCell?.x);
    const bar = await table.locator("tr[data-agent='builder'] th").evaluate((el) => {
      const style = getComputedStyle(el, "::before");
      return { left: style.insetInlineStart, border: style.borderInlineStartWidth };
    });
    expect(bar).toEqual({ left: "0px", border: "3px" });
    // The rows run the well's full width, so the fill edge sits on the well's inner edge.
    const well = await page.locator(".review-table-well").boundingBox();
    expect(pickedCell?.x).toBe((well?.x ?? 0) + 1);
  });
}

test("the kinds chart's image carries the exact label, and its legend holds the same total", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, models("30d"), { width: 1440 });
  const image = page.getByRole("img", { name: KINDS_IMAGE });
  await expect(image).toBeVisible();
  await expect(image).toHaveAccessibleName(KINDS_IMAGE);
  const legend = page.locator(".review-models-legend");
  await expect(legend).toContainText(`${en.k_cache_read} $18.29`);
  await expect(legend).toContainText(`${en.k_input} $34.82`);
  await expect(legend).toContainText(`${en.k_cache_write} $160.41`);
  await expect(legend).toContainText(`${en.k_output} $106.09`);
  await expect(page.getByText(en.kind_legend_note)).toBeVisible();
  // The four kinds show four different patterns in every row that has them.
  const fable = image.locator("li").first();
  await expect(fable.locator(".review-models-stack i")).toHaveCount(4);
  await expect(fable).toContainText(
    `${en.k_cache_write} $121.82, ${en.k_output} $83.25, ${en.k_input} $25.53, ${en.k_cache_read} $11.31`,
  );
});

test("the Models table and the kinds chart say the API-rate note once", async ({ page, demo }) => {
  await openAt(page, demo, models("30d"), { width: 1440 });
  await expect(page.getByRole("table", { name: en.md_h })).toBeVisible();
  await expect(page.getByText(/^Costs are estimates at API list prices/)).toHaveCount(1);
});

test("a setup that could not be read shows in each Set to cell, keeps the costs and offers Try again", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, "/", { width: 1440 });
  await patch(page, "**/api/agents*", unreadableSetup);
  await goTo(page, agents("30d"));
  const table = page.getByRole("table", { name: en.ag_h });
  await expect(table.locator("tr[data-agent='builder']")).toContainText(en.ag_set_failed);
  await expect(table.locator("tr[data-agent='builder']")).toContainText("$241.92");
  await expect(table.getByText(en.status_default)).toHaveCount(0);
  await expect(page.getByText(fill(en.er_h, { card: en.ag_setup_card }))).toBeVisible();
  await expect(page.getByRole("button", { name: en.er_try })).toBeVisible();
});

test("the Agents total equals Summary's Where the money went, agent by agent", async ({
  page,
  demo,
}) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await expect(page.getByRole("heading", { name: en.rv_who_h })).toBeVisible();
  const money = page.locator(".review-money > li");
  await expect(money).toHaveCount(4);
  const fromMoney = await money.evaluateAll((rows) =>
    rows.map((row) => [
      row.querySelector(".review-agent-title")?.textContent ?? "",
      row.querySelector(".share-bar-value")?.textContent ?? "",
    ]),
  );
  const tile = await page.locator(".tiles .tile").first().textContent();
  expect(tile).toContain("$319.62");

  await goTo(page, agents("30d"));
  const rows = page.locator("table tbody tr[data-agent]");
  await expect(rows).toHaveCount(4);
  const fromAgents = await rows.evaluateAll((all) =>
    all.map((row) => [
      row.querySelector(".review-agents-name")?.textContent ?? "",
      row.querySelector(".share-bar-value")?.textContent ?? "",
    ]),
  );
  expect(fromAgents).toEqual(fromMoney);

  // The answers behind both pages add up to the same cost, to the cent and beyond.
  const totals = await page.evaluate(async () => {
    const key = sessionStorage.getItem("bartab.readKey") ?? "";
    const get = async (path: string): Promise<unknown> =>
      (await fetch(path, { headers: { "X-Bartab-Key": key } })).json();
    const agents = (await get("/api/agents?project=tidewater-reporting&range=30d")) as {
      ran: { cost: number }[];
    };
    const summary = (await get("/api/summary?project=tidewater-reporting&range=30d")) as {
      tiles: { cost: { value: number } };
    };
    return {
      agents: agents.ran.reduce((sum, row) => sum + row.cost, 0),
      tile: summary.tiles.cost.value,
    };
  });
  expect(Math.abs(totals.agents - totals.tile)).toBeLessThan(1e-9);
});

// ---- keyboard --------------------------------------------------------------------------------

for (const width of WIDTHS) {
  test(`keyboard only at ${String(width)} wide: change the range on Agents, then go to Models by its link`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(90_000);
    await openAt(page, demo, agents("30d"), { width });
    await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: en.nav_agents })).toBeFocused();

    // 1. Range Select: open with Enter, choose 7 days with the arrows, focus returns to the button.
    const select = page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` });
    await reach(page, select);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("listbox")).toBeVisible();
    await page.keyboard.press("ArrowUp");
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_7d}` })).toBeFocused();
    await expect(page).toHaveURL(/range=7d/);
    await expect(status(page)).toHaveText(
      fill(en.rt_range, { range: fill(en.rg_n_days, { n: 7 }) }),
    );
    await expect(page.getByRole("table", { name: en.ag_h })).toBeVisible();

    // 2. The Models link keeps the range, and the page moves focus to its h1. The sidebar has this
    // link at 1440 and the segmented pages have it at 375, never both. Both carry the range.
    const link = page.getByRole("link", { name: en.nav_models, exact: true });
    await expect(link).toHaveCount(1);
    await reach(page, link);
    await expect(link).toHaveAttribute("href", `#/p/${PROJECT}/review/models?range=7d`);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/review\/models\?range=7d$/);
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_7d}` })).toBeVisible();
    await expect(page.getByRole("heading", { level: 1, name: en.nav_models })).toBeFocused();
    await expect(status(page)).toHaveText(en.nav_models);
    await expect(page.getByRole("table", { name: en.md_h })).toBeVisible();
  });

  test(`keyboard only at ${String(width)} wide: Summary's Made of link lands on the kinds card with focus`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(90_000);
    await openAt(page, demo, summary("30d"), { width });
    await expect(page.getByRole("heading", { level: 1, name: en.nav_summary })).toBeFocused();
    const link = page.getByRole("link", { name: en.ch_kinds_link });
    await expect(link).toBeVisible();
    await reach(page, link);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/review\/models\?range=30d&section=kinds/);
    const heading = page.getByRole("heading", { level: 2, name: en.md_kind_h });
    await expect(heading).toBeFocused();
    await expect(heading).toBeInViewport();
    await expect(page.getByRole("img", { name: KINDS_IMAGE })).toBeInViewport();
    // Tab goes on from the kinds card, never back to the top of the page.
    await page.keyboard.press("Tab");
    expect(await page.evaluate(() => document.activeElement?.tagName)).not.toBe("H1");
  });
}

test("the Made of link on a mouse click lands on the same card", async ({ page, demo }) => {
  await openAt(page, demo, summary("30d"), { width: 1440 });
  await page.getByRole("link", { name: en.ch_kinds_link }).click();
  await expect(page.getByRole("heading", { level: 2, name: en.md_kind_h })).toBeFocused();
  await expect(page.getByRole("img", { name: KINDS_IMAGE })).toBeInViewport();
});

// ---- walkthrough: read the 30-day cost by agent --------------------------------------------------

type Place = "before" | "inside" | "after";

/** Where the focused element sits against a card: before it in the page, inside it, or after it. */
async function placeAgainst(card: Locator): Promise<Place> {
  return card.evaluate((el): Place => {
    const active = document.activeElement;
    if (active === null || active === document.body) return "before";
    if (el.contains(active)) return "inside";
    return el.compareDocumentPosition(active) & Node.DOCUMENT_POSITION_FOLLOWING
      ? "after"
      : "before";
  });
}

/** Each row's agent, cost and share, in the order the page lists them. */
async function readRows(rows: Locator, name: string): Promise<[string, string, string][]> {
  return rows.evaluateAll(
    (all, nameSelector) =>
      all.map((row): [string, string, string] => [
        (row.querySelector(nameSelector)?.textContent ?? "").trim(),
        (row.querySelector(".share-bar-value")?.textContent ?? "").trim(),
        (row.querySelector(".share-bar-percent")?.textContent ?? "").trim(),
      ]),
    name,
  );
}

const dollars = (text: string): number => Number(text.replace(/[$,]/g, ""));

for (const width of WIDTHS) {
  test(`keyboard only at ${String(width)} wide: read the 30-day cost by agent, from Live to Summary and on to Agents`, async ({
    page,
    demo,
  }) => {
    test.setTimeout(120_000);
    // The one page load. Everything after it is a key press.
    await page.setViewportSize({ width, height: 900 });
    await page.goto(linkFor(demo.baseURL, await demo.mint(PROJECT), `/p/${PROJECT}/live`));
    await expectUnlocked(page);
    await expect(page).toHaveURL(new RegExp(`#/p/${PROJECT}/live`));
    const main = page.getByRole("navigation", { name: en.nav_aria });

    // 1. Live to Summary. The sidebar has a Summary link at 1440 and the tab bar has Review at 375.
    const toSummary = main.getByRole("link", {
      name: width >= 721 ? en.nav_summary : en.nav_review,
      exact: true,
    });
    await reach(page, toSummary);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/review\/summary/);
    await expect(page.getByRole("heading", { level: 1, name: en.nav_summary })).toBeFocused();
    // The tab bar's link names no range, so the page reads its default, 30 days, from the Select.
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` })).toBeVisible();
    await expect(page.getByRole("img", { name: /^Bar chart of cost per day/ })).toBeVisible();

    // 2. Where the money went. The rows are text, so the card has no stop of its own. Tab goes
    // from the controls before it, over it, to the first control after it.
    const card = page.getByRole("region", { name: en.rv_who_h });
    await expect(card).toBeVisible();
    const items = card.getByRole("listitem");
    await expect(items).toHaveCount(4);
    const fromMoney = await readRows(items, ".review-agent-title");
    await expect(page.locator(".tiles .tile").first()).toContainText("$319.62");
    for (const [agent, cost, share] of fromMoney) {
      expect(agent).not.toBe("");
      expect(cost).toMatch(/^\$\d[\d,]*\.\d\d$/);
      expect(share).toMatch(/^(<1|\d+)%$/);
    }
    // Every row's agent, cost and share are in the card's accessible text, in row order.
    const texts = await items.allInnerTexts();
    fromMoney.forEach(([agent, cost, share], index) => {
      const text = texts[index] ?? "";
      expect(text).toContain(agent);
      expect(text).toContain(cost);
      expect(text).toContain(share);
    });
    // The same rows come from the answer behind the card, in the same words.
    const answer = await page.evaluate(async () => {
      const key = sessionStorage.getItem("bartab.readKey") ?? "";
      const res = await fetch("/api/summary?project=tidewater-reporting&range=30d", {
        headers: { "X-Bartab-Key": key },
      });
      return (await res.json()) as { money: { cost: number; share: number }[] };
    });
    expect(fromMoney.map((row) => row[1])).toEqual(answer.money.map((row) => formatCost(row.cost)));

    const places: Place[] = [];
    const all = page.getByRole("link", { name: /^All \d+ sessions$/ });
    for (let press = 0; press < 40; press++) {
      await page.keyboard.press("Tab");
      places.push(await placeAgainst(card));
      if (await all.evaluate((el) => el === document.activeElement).catch(() => false)) break;
    }
    // Stops before the card, none inside it, then the stops after it, in that order.
    expect(places[0]).toBe("before");
    expect(places).not.toContain("inside");
    expect(places.at(-1)).toBe("after");
    expect(places.lastIndexOf("before")).toBeLessThan(places.indexOf("after"));
    await expect(all).toBeFocused();

    // 3. Summary to Agents. The sidebar link at 1440 and the segmented link at 375 keep the range.
    const toAgents = page.getByRole("link", { name: en.nav_agents, exact: true });
    await reach(page, toAgents);
    await expect(toAgents).toHaveAttribute("href", `#/p/${PROJECT}/review/agents?range=30d`);
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/review\/agents\?range=30d$/);
    await expect(page.getByRole("heading", { level: 1, name: en.nav_agents })).toBeFocused();
    await expect(status(page)).toHaveText(en.nav_agents);
    await expect(page.getByRole("button", { name: `${en.rg_h} ${en.rg_30d}` })).toBeVisible();

    // 4. The Agents rows, then the totals: the same agents, costs and shares, and one total.
    const table = page.getByRole("table", { name: en.ag_h });
    const rows = table.locator("tbody tr[data-agent]");
    await expect(rows).toHaveCount(4);
    const fromAgents = await readRows(rows, ".review-agents-name");
    // The Agents table draws no percent beside its bar, so agent and cost are what both share.
    expect(fromAgents.map((row) => row.slice(0, 2))).toEqual(
      fromMoney.map((row) => row.slice(0, 2)),
    );
    const moneyTotal = fromMoney.reduce((sum, row) => sum + dollars(row[1]), 0);
    const agentsTotal = fromAgents.reduce((sum, row) => sum + dollars(row[1]), 0);
    expect(agentsTotal).toBeCloseTo(moneyTotal, 2);
    // Both match the Cost tile on Summary, to the rounding of four costs.
    expect(Math.abs(agentsTotal - 319.62)).toBeLessThan(0.05);
  });
}
