/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The help walkthroughs from m5-build.md section 10 (walkthrough 2, and the help half of 3), with
 * the keyboard only, at 375 and 1440, and axe on every page that gained help with a popover or the
 * tray open (the loop is in a11y.ts). Live runs on the busy flow, which has a running session and
 * so its tiles and cards. The other pages run on the demo build.
 *
 * Walkthrough 2. Tab to a tile "?", a card "?" and a column-header term. Open each with Enter and
 * with Space. Focus moves into the dialog, Tab walks its links, and at 375 the Close button too.
 * Esc closes it and focus is back on the trigger. In the tray, Tab stays inside and Close returns
 * focus.
 *
 * Walkthrough 3, the help half. From one Live tile and one Your setup inspector field, the
 * glossary link lands on its term, and "Back to {page}" focuses the same "?".
 *
 * Snapshot. One open popover, from a column header, with its marked line. Only headers whose
 * meaning is not obvious carry a term (Agents, Set to, Ran with, Check and Runs), so the walks use
 * Check, which shows at every width, and the snapshot uses Runs at 1440.
 */
import type { Locator, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { en } from "../src/strings/en";
import { scan } from "./a11y";
import type { Look } from "./a11y";
import { PROJECT, glossary, heading2, openAt, tabTo, test } from "./kit";
import { expect } from "./server";
import type { Server } from "./server";

const WIDTHS = [1440, 375] as const;
const KEYS = ["Enter", "Space"] as const;

/** One help trigger, and where it lives. */
interface Spot {
  name: string;
  path: string;
  id: string;
  /** The text of a term trigger. A "?" has none. */
  term?: string;
}

const LIVE_TILE: Spot = { name: "a Live tile", path: `/p/${PROJECT}/live`, id: "live.spent" };
const SUMMARY_CARD: Spot = {
  name: "a Summary card",
  path: `/p/${PROJECT}/review/summary`,
  id: "summary.who",
};
const AGENTS_HEADER: Spot = {
  name: "an Agents column header",
  path: `/p/${PROJECT}/review/agents`,
  id: "agents.check",
  term: "Check",
};
/** Runs is a term only above 720px, and the grouped entry marks its line. */
const AGENTS_RUNS_HEADER: Spot = {
  name: "the Agents Runs header",
  path: `/p/${PROJECT}/review/agents`,
  id: "agents.cols",
  term: "Runs",
};
/** The status pill's "?" on the Your setup inspector. */
const INSPECTOR_STATUS: Spot = {
  name: "the Your setup inspector status pill",
  path: `/p/${PROJECT}/setup/settings/effortLevel`,
  id: "setup.inspector.status",
};
const LIVE_SPOTS: Spot[] = [LIVE_TILE];
const DEMO_SPOTS: Spot[] = [SUMMARY_CARD, AGENTS_HEADER, INSPECTOR_STATUS];

function triggerFor(page: Page, spot: Spot): Locator {
  const all = page.locator(`[data-help-id="${spot.id}"]`);
  return (spot.term === undefined ? all : all.filter({ hasText: spot.term })).first();
}

const dialogOf = (page: Page): Locator => page.getByRole("dialog");

/** Whether the focused element is inside the open dialog. */
const focusInside = (dialog: Locator): Promise<boolean> =>
  dialog.evaluate((el) => el.contains(document.activeElement));

/** Opens a trigger with the keyboard only and waits for its dialog to hold focus. */
async function openByKey(page: Page, spot: Spot, key: string): Promise<Locator> {
  const trigger = triggerFor(page, spot);
  await expect(trigger).toBeVisible();
  await tabTo(page, trigger);
  await page.keyboard.press(key);
  const dialog = dialogOf(page);
  await expect(dialog).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await expect(dialog).toBeFocused();
  return dialog;
}

/** The walk, from a closed trigger to a closed dialog and focus back on the trigger. */
async function walk(
  page: Page,
  server: Server,
  spot: Spot,
  width: number,
  key: string,
): Promise<void> {
  await openAt(page, server, spot.path, width);
  const dialog = await openByKey(page, spot, key);
  // The panel names itself by its h2.
  const title = (await dialog.getByRole("heading", { level: 2 }).first().textContent()) ?? "";
  expect(title).not.toBe("");
  await expect(dialog).toHaveAccessibleName(title);
  // Tab walks every link in the dialog, and at 375 the Close button first, and none leaves it.
  const links = await dialog.getByRole("link").evaluateAll((all) => all.map((a) => a.textContent));
  expect(links.length).toBeGreaterThan(0);
  const stops = links.length + (width <= 720 ? 1 : 0);
  const seen: string[] = [];
  for (let press = 0; press < stops; press++) {
    await page.keyboard.press("Tab");
    expect(await focusInside(dialog)).toBe(true);
    seen.push(
      await page.evaluate(() =>
        (document.activeElement?.textContent ?? "").replace("→", "").trim(),
      ),
    );
  }
  for (const link of links) {
    expect(
      seen.some((text) => link !== null && text.startsWith(link.replace("→", "").trim())),
    ).toBe(true);
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  const trigger = triggerFor(page, spot);
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
}

test.describe("walkthrough 2, help popovers and the tray", () => {
  for (const width of WIDTHS) {
    for (const key of KEYS) {
      for (const spot of LIVE_SPOTS) {
        test(`${spot.name}, ${key}, at ${String(width)}: opens, Tab walks it, Esc returns focus`, async ({
          page,
          busy,
        }) => {
          await walk(page, busy, spot, width, key);
        });
      }
      for (const spot of DEMO_SPOTS) {
        test(`${spot.name}, ${key}, at ${String(width)}: opens, Tab walks it, Esc returns focus`, async ({
          page,
          demo,
        }) => {
          await walk(page, demo, spot, width, key);
        });
      }
    }
  }

  test("the tray at 375 keeps Tab inside it, and Close returns focus to the ?", async ({
    page,
    busy,
  }) => {
    const spot = LIVE_TILE;
    await openAt(page, busy, spot.path, 375);
    const dialog = await openByKey(page, spot, "Enter");
    await expect(page.locator(".hp-tray[data-rac]")).toBeVisible();
    // More presses than the tray has stops, so Tab wraps and never reaches the page behind it.
    for (let press = 0; press < 8; press++) {
      await page.keyboard.press("Tab");
      expect(await focusInside(dialog)).toBe(true);
    }
    for (let press = 0; press < 3; press++) {
      await page.keyboard.press("Shift+Tab");
      expect(await focusInside(dialog)).toBe(true);
    }
    const close = dialog.getByRole("button", { name: en.hp_close });
    await tabTo(page, close, 12);
    await page.keyboard.press("Enter");
    await expect(dialog).toHaveCount(0);
    await expect(triggerFor(page, spot)).toBeFocused();
  });
});

/** A "?" or term, the link it opens, and what the Glossary and Back do. */
interface RoundTrip {
  name: string;
  spot: Spot;
  link: string;
  /** The page the Back link names. */
  back: RegExp;
  /** The term or section the link lands on. */
  target: (page: Page) => Locator;
}

const ROUND_TRIPS: RoundTrip[] = [
  {
    name: "a Live tile",
    spot: LIVE_TILE,
    link: "API-rate estimate in the glossary",
    back: new RegExp(`${en.sp_back.replace("{part}", en.nav_live)}$`),
    target: (page) => page.locator('dt[data-term-id="api-rate-estimate"]'),
  },
  {
    name: "a Your setup inspector field",
    spot: {
      name: "the Why field",
      path: `/p/${PROJECT}/setup/settings/effortLevel`,
      id: "setup.why",
      term: "Why",
    },
    link: "Confidence words in the glossary",
    back: new RegExp(`${en.sp_back.replace("{part}", en.su_h1)}$`),
    target: (page) => heading2(page, "Confidence words"),
  },
];

test.describe("walkthrough 3, the glossary from help", () => {
  for (const width of WIDTHS) {
    for (const trip of ROUND_TRIPS) {
      test(`${trip.name} at ${String(width)}: the link lands on its term, Back focuses the same ?`, async ({
        page,
        demo,
        busy,
      }) => {
        await openAt(page, trip.name === "a Live tile" ? busy : demo, trip.spot.path, width);
        const trigger = triggerFor(page, trip.spot);
        const dialog = await openByKey(page, trip.spot, "Enter");
        const link = dialog.getByRole("link", { name: trip.link });
        await tabTo(page, link, 12);
        await page.keyboard.press("Enter");
        await expect(dialogOf(page)).toHaveCount(0);
        await expect(page).toHaveURL(new RegExp(`#${glossary()}/`));
        await expect(trip.target(page)).toBeFocused();
        const back = page.getByRole("link", { name: trip.back });
        await expect(back).toBeVisible();
        await tabTo(page, back);
        await page.keyboard.press("Enter");
        await expect(page).not.toHaveURL(new RegExp(`#${glossary()}`));
        await expect(trigger).toBeFocused();
      });
    }
  }
});

/** The pages that gained help, each with a trigger that opens a popover or the tray. */
interface AxePage {
  name: string;
  spot: Spot;
  /** Runs on the busy flow, whose session Session review opens. */
  live?: boolean;
  /** The spot's path ends in the busy flow's session id. */
  session?: boolean;
}

/** The busy flow's session, from the flow file the server writes into its data folder. */
function busySession(server: Server): string {
  const flow = JSON.parse(readFileSync(join(server.dataDir, "flow-busy", "flow.json"), "utf8")) as {
    session: string;
  };
  return flow.session;
}

const AXE_PAGES: AxePage[] = [
  { name: "Live", spot: LIVE_TILE, live: true },
  { name: "Summary", spot: SUMMARY_CARD },
  { name: "Agents", spot: AGENTS_HEADER },
  { name: "Your setup", spot: { name: "the card", path: `/p/${PROJECT}/setup`, id: "setup.card" } },
  {
    name: "Session review",
    spot: {
      name: "the state word",
      path: `/p/${PROJECT}/review/sessions/`,
      id: "review.status",
    },
    live: true,
    session: true,
  },
  {
    name: "Sessions",
    spot: { name: "the share card", path: `/p/${PROJECT}/review/sessions`, id: "sessions.share" },
  },
  {
    name: "Models",
    spot: { name: "the kinds card", path: `/p/${PROJECT}/review/models`, id: "models.kinds" },
  },
  {
    name: "To fix",
    spot: { name: "the rows card", path: `/p/${PROJECT}/to-fix`, id: "fix.rows" },
  },
  {
    name: "More",
    spot: { name: "the prices line", path: "/more", id: "shell.prices" },
  },
];

test.describe("axe with help open", () => {
  for (const entry of AXE_PAGES) {
    test(`${entry.name}: a popover at 1440 and the tray at 320 and 375, light and dark, forced colours and reduced motion`, async ({
      page,
      demo,
      busy,
    }) => {
      test.setTimeout(300_000);
      const server = entry.live === true ? busy : demo;
      const spot =
        entry.session === true
          ? { ...entry.spot, path: `${entry.spot.path}${busySession(server)}?range=30d` }
          : entry.spot;
      const options = {
        label: entry.name,
        enter: (p: Page, look: Look) => openAt(p, server, spot.path, look),
        hold: async (p: Page) => {
          await openByKey(p, spot, "Enter");
        },
      };
      const found = [
        ...(await scan(page, { ...options, label: `${entry.name} popover`, widths: [1440] })),
        ...(await scan(page, { ...options, label: `${entry.name} tray`, widths: [320, 375] })),
      ];
      expect(found).toEqual([]);
    });
  }
});

test.describe("accessibility snapshot", () => {
  test("an open popover from a column header, with its marked line", async ({ page, demo }) => {
    const spot = AGENTS_RUNS_HEADER;
    await openAt(page, demo, spot.path, 1440);
    const dialog = await openByKey(page, spot, "Enter");
    await expect(dialog).toMatchAriaSnapshot(`
      - dialog "Agents table":
        - heading "Agents table" [level=2]
        - paragraph: /.+/
        - heading "${en.hp_numbers}" [level=3]
        - term: ${en.ag_col_set}
        - definition: /.+/
        - term: Nothing set
        - definition: /.+/
        - term: ${en.ag_col_ran}
        - definition: /.+/
        - term: Also
        - definition: /.+/
        - term: ${en.ag_col_check}
        - definition: /.+/
        - term: ${en.ag_col_runs}
        - definition: /^.+ ${en.hp_this_column}$/
        - term: ${en.ag_col_cost}
        - definition: /.+/
        - link "${en.ag_col_set} in the glossary"
        - link "${en.ag_col_ran} in the glossary"
    `);
    // Only the Runs line carries the mark.
    await expect(dialog.getByText(en.hp_this_column)).toHaveCount(1);
  });

  test("the help tray open at 375, with its Close button", async ({ page, demo }) => {
    const spot = SUMMARY_CARD;
    await openAt(page, demo, spot.path, 375);
    const dialog = await openByKey(page, spot, "Enter");
    await expect(page.locator(".hp-tray[data-rac]")).toBeVisible();
    await expect(dialog).toMatchAriaSnapshot(`
      - dialog "Where the money went":
        - heading "Where the money went" [level=2]
        - button "${en.hp_close}"
        - paragraph: /.+/
        - heading "${en.hp_numbers}" [level=3]
        - term: /.+/
        - definition: /.+/
        - link /in the glossary$/
    `);
  });
});
