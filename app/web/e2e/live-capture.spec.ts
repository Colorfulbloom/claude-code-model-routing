/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Screenshots of the built Live page in the states the designer's M2 boards draw, for a side by
 * side comparison. It does nothing unless BARTAB_CAPTURE_DIR names a folder, so the normal e2e run
 * is unchanged. Each PNG is full page and named `build-<board>-<width>-<theme>.png`. Extra states
 * the boards fold into one picture carry an `x-` name.
 *
 * States come from the four flow scenarios and the server's test clock (POST /api/dev/clock),
 * the same way live.spec.ts moves it. The scenario clocks, UTC on October 30, 2026 (the page
 * shows Eastern time, so 22:10 reads as 6:10 PM)
 *
 *   busy      22:40 session mid-run, 22:50 idle, 23:10 ended and nothing running
 *   many      23:10 session with 25 runs
 *   unlinked  22:40 runs whose starter is not known
 *
 * Boards no fixture can reach are not captured: p1-headers (five header states on one board,
 * see x-idle and x-ended), p1-unpriced (no flow run lacks a price), p2-long (no eight hour
 * session), p3-ended-switch (no second running session starts while the page is open) and
 * p3-nothing-other (no flow runs a session in another project) and p3-no-sessions (every
 * scenario keeps a last ended session at any data time, so the page shows Nothing is running).
 */
import type { Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expectUnlocked, linkFor } from "./gate";
import { expect, test } from "./server";
import type { FlowScenario } from "./server";

const DIR = process.env.BARTAB_CAPTURE_DIR;
const PROJECT = "tidewater-reporting";
const WIDTHS = [1440, 375] as const;
const THEMES = ["light", "dark"] as const;
const DAY = "2026-10-30";

interface Shot {
  /** The board name, or an `x-` name for a state the boards do not draw on its own. */
  name: string;
  /** The data time, UTC on October 30. */
  at: string;
  /** The hash route to open before the shot. The default is the Live route with no query. */
  route?: string;
  /** Opens or changes something once the page has settled, before the size loop and again before each shot. It must be safe to run twice. */
  prepare?: (page: Page) => Promise<void>;
  /** Runs at each size and theme, and its result is undone before the next. */
  during?: (page: Page) => Promise<() => Promise<void>>;
  /** The text the page must show before the shot, so a half drawn page is never saved. */
  expects: string | RegExp;
}

const LIVE = `/p/${PROJECT}/live`;

async function setServerClock(page: Page, at: string): Promise<void> {
  const status = await page.evaluate(async (now) => {
    const key = sessionStorage.getItem("bartab.readKey") ?? "";
    const res = await fetch("/api/dev/clock", {
      method: "POST",
      headers: { "X-Bartab-Key": key, "Content-Type": "application/json" },
      body: JSON.stringify({ now }),
    });
    return res.status;
  }, `${DAY}T${at}:00Z`);
  expect(status).toBe(200);
}

/**
 * Opens a route in a fresh load of the page, so the sessions list the page held at the old data
 * time cannot put its session back into the URL. The key stays in session storage. The stored
 * route holds the last session's query, so it goes first.
 */
async function goTo(page: Page, baseURL: string, route: string): Promise<void> {
  await page.evaluate(() => {
    sessionStorage.removeItem("bartab.route");
  });
  await page.goto("about:blank");
  await page.goto(`${baseURL}/#${route}`);
}

async function openSelect(page: Page): Promise<() => Promise<void>> {
  await page.getByRole("button", { name: /^Session/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  return async () => {
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);
  };
}

/**
 * Opens every fold and checks that each one reads Hide. It runs again before every shot, because
 * the page may redraw between shots and the fold must be open in the picture, not only after the
 * first click. Hide buttons are left alone, so running it twice is safe.
 */
async function showEarlier(page: Page): Promise<void> {
  // The card's title shows while the page is still loading, so wait for the lane rows themselves.
  await expect(page.getByRole("list", { name: "Who is working" })).toBeVisible({ timeout: 20_000 });
  const show = page.getByRole("button", { name: "Show", exact: true });
  while ((await show.count()) > 0) {
    await show.first().click();
  }
  const hide = page.getByRole("button", { name: "Hide", exact: true });
  await expect(hide.first()).toBeVisible();
  await expect(hide.first()).toHaveAttribute("aria-expanded", "true");
}

const PLAN: Record<FlowScenario, Shot[]> = {
  busy: [
    { name: "p1-live", at: "22:40", expects: "Who is working" },
    { name: "x-idle", at: "22:50", expects: "Idle" },
    { name: "x-ended", at: "23:10", route: `${LIVE}?session=BUSY`, expects: "Ended" },
    { name: "p3-select-open", at: "22:40", during: openSelect, expects: "Who is working" },
    {
      name: "p3-gone",
      at: "22:40",
      route: `${LIVE}?session=no-such-session`,
      expects: /isn.t in Tidewater reporting/,
    },
    { name: "p3-nothing-alone", at: "23:10", expects: /Nothing is running/ },
  ],
  many: [
    { name: "p2-many", at: "23:10", expects: "Who is working" },
    { name: "p2-many-open", at: "23:10", prepare: showEarlier, expects: "Who is working" },
  ],
  unlinked: [{ name: "p1-unlinked", at: "22:40", expects: "Who is working" }],
  // The server keeps the last ended session in view at any data time, so the page never says the
  // project has no sessions. p3-no-sessions has no state to capture.
  empty: [],
};

test.describe("live capture", () => {
  test.skip(DIR === undefined, "set BARTAB_CAPTURE_DIR to take the Live page screenshots");

  for (const scenario of (Object.keys(PLAN) as FlowScenario[]).filter(
    (name) => PLAN[name].length > 0,
  )) {
    test.describe(`${scenario} scenario`, () => {
      test.use({ flow: scenario });

      test(`captures ${scenario}`, async ({ page, server }) => {
        test.setTimeout(240_000);
        const out = DIR ?? "";
        mkdirSync(out, { recursive: true });
        await page.clock.install({ time: new Date("2026-11-09T12:00:00Z") });
        await page.setViewportSize({ width: 1440, height: 900 });
        // The first link carries the access code and no query. Wait for the ingest to finish.
        await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), LIVE));
        await expectUnlocked(page);
        await expect(page.getByRole("list", { name: "Who is working" })).toBeVisible({
          timeout: 60_000,
        });
        const session = new URL(page.url().replace("/#/", "/")).searchParams.get("session") ?? "";

        for (const shot of PLAN[scenario]) {
          await setServerClock(page, shot.at);
          await goTo(page, server.baseURL, (shot.route ?? LIVE).replace("BUSY", session));
          await expectUnlocked(page);
          await expect(page.getByText(shot.expects).first()).toBeVisible({ timeout: 20_000 });
          if (shot.prepare !== undefined) await shot.prepare(page);
          for (const width of WIDTHS) {
            for (const theme of THEMES) {
              await page.setViewportSize({ width, height: 900 });
              await page.emulateMedia({ colorScheme: theme });
              // Colours transition on a theme change.
              await page.waitForTimeout(600);
              if (shot.prepare !== undefined) await shot.prepare(page);
              const undo = shot.during === undefined ? null : await shot.during(page);
              await page.waitForTimeout(300);
              await page.screenshot({
                path: join(out, `build-${shot.name}-${String(width)}-${theme}.png`),
                fullPage: true,
              });
              if (undo !== null) await undo();
            }
          }
        }
      });
    });
  }
});
