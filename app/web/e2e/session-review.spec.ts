/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Session review (the replay) against the real server on the flow scenarios, which carry the demo
 * history and one session that runs from 6:10 PM to 6:40 PM on October 30. The test clock sets
 * what "now" is: before 6:40 PM the session runs, and after it (11:40 PM here) it has ended.
 *
 * Matrix. Each scenario (busy, many, unlinked, empty) renders after it ends, and busy renders while
 * it runs, at 320, 375 and 1440 in light and dark and in forced colours, with axe and no sideways
 * scroll.
 *
 * Keyboard. A walkthrough at 375 and 1440 uses the keyboard only, from the heading to the Session
 * Select, the button, the line (arrows, Page Up, Home, End) and a fold. "Replay a past session"
 * goes from Live to Sessions to a session by keys, moves the line by keys on an ended session, and
 * on a running one moves it, Tabs to Back to now and presses Enter. No page load after the first,
 * no hash set and no mouse.
 *
 * Exact text. The header and the replay control match their accessibility snapshots. The slider's
 * value text after an arrow and Page Up, the chart's image label at two times and the line said
 * after a settle are asserted word for word, built from the typed strings and the timeline answer.
 *
 * Replay oracle. At three times on the ended busy session the tiles and the lane rows equal the
 * values timeline-at.ts picks from the page's own timeline answer, worked out here from the raw
 * answer and not from the page's code. At five more minutes they equal the old /api/live recorded
 * at that clock time (app/fixtures/oracle/live/busy), outside the allowed differences.
 *
 * Snapshots. The replay control at two minutes and Back to now match accessibility snapshots.
 *
 * Running. The line follows Now until it is moved, then stays, and Back to now returns it.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Locator, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { formatCost, formatTokens } from "../src/lib/format";
import { valuesAt } from "../src/lib/timeline-at";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, test } from "./server";
import type { FlowScenario, Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const PROJECT_NAME = "Tidewater reporting";
const ZONE = "America/New_York";
const SCENARIOS: FlowScenario[] = ["busy", "many", "unlinked", "empty"];
const MINUTE = 60_000;
/** The flow session runs 6:10 PM to 6:40 PM New York time on October 30. */
const RUNNING_CLOCK = Date.parse("2026-10-30T22:25:00Z");
const ENDED_CLOCK = Date.parse("2026-10-30T23:40:00Z");

test.use({ timezoneId: ZONE, locale: "en-US" });

interface Run {
  run_id: string;
  agent: string | null;
  label_n: number | null;
  state: string;
  dispatch_order: number;
  parent: string | null;
  first_request: string;
  model: string | null;
  states: { at: string; state: string }[];
  cum: { tokens: number; cache_read: number; cost: number | null }[];
  [key: string]: unknown;
}
interface Answer {
  server_time: string;
  session: {
    id: string;
    branch: string | null;
    state: string;
    started: string;
    last_request: string;
    running: boolean;
  };
  axis: { start: string; end: string; bucket_seconds: number };
  buckets: { start: string; by_model: Record<string, number> }[];
  models: { model: string; tokens: number }[];
  runs: Run[];
  totals: { tokens: number; cache_read: number; cost: number | null; runs: number };
  [key: string]: unknown;
}

/** The line's last minute on an ended session: the minute of its last request, not the axis edge. */
function endMinute(answer: Answer): number {
  const start = Date.parse(answer.axis.start);
  const last = Date.parse(answer.session.last_request);
  return Math.floor(Math.min(Date.parse(answer.axis.end) - start, last - start) / MINUTE);
}

function flowSession(server: Server, scenario: FlowScenario): string {
  const flow = JSON.parse(
    readFileSync(join(server.dataDir, `flow-${scenario}`, "flow.json"), "utf8"),
  ) as { session: string };
  return flow.session;
}

/** Sets the server's data clock. The read key stays in the page and is never printed. */
async function setServerClock(page: Page, atMs: number): Promise<void> {
  const status = await page.evaluate(async (now) => {
    const key = sessionStorage.getItem("bartab.readKey") ?? "";
    const res = await fetch("/api/dev/clock", {
      method: "POST",
      headers: { "X-Bartab-Key": key, "Content-Type": "application/json" },
      body: JSON.stringify({ now }),
    });
    return res.status;
  }, new Date(atMs).toISOString());
  expect(status).toBe(200);
}

/** The full timeline answer at the server's clock, asked with no etag. */
async function fullAnswer(page: Page, session: string): Promise<Answer> {
  return page.evaluate(
    async ([id, project]) => {
      const key = sessionStorage.getItem("bartab.readKey") ?? "";
      const res = await fetch(`/api/sessions/${id ?? ""}/timeline?project=${project ?? ""}`, {
        headers: { "X-Bartab-Key": key },
      });
      return (await res.json()) as Answer;
    },
    [session, PROJECT],
  );
}

/** Unlocks the page on Live, sets the clock, and leaves the page ready to name a route. */
async function start(page: Page, server: Server, clock: number): Promise<void> {
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
  await expectUnlocked(page);
  await expect(page.getByRole("list", { name: en.tl_h })).toBeVisible();
  await setServerClock(page, clock);
}

async function go(page: Page, session: string, query = ""): Promise<void> {
  const hash = `/p/${PROJECT}/review/sessions/${session}?range=30d${query}`;
  await page.evaluate((h) => {
    window.location.hash = h;
  }, hash);
}

async function openReview(page: Page, session: string, query = ""): Promise<void> {
  await go(page, session, query);
  await expect(page.getByRole("slider", { name: en.sr_label })).toBeVisible();
}

const slider = (page: Page): Locator => page.getByRole("slider", { name: en.sr_label });

/** "6:25 PM" the way the page words it, from the browser's own formatter. */
async function clockText(page: Page, atMs: number): Promise<string> {
  return page.evaluate(
    (at) => new Intl.DateTimeFormat("en-US", { timeStyle: "short" }).format(new Date(at)),
    atMs,
  );
}

const money = (cost: number | null): string => (cost === null ? en.c_none_short : formatCost(cost));
const status = (page: Page): Locator => page.locator('div.sr-only[role="status"]');

async function overflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

async function axeProblems(page: Page, label: string): Promise<string[]> {
  // Colours transition on a theme change, and axe would read them half way.
  await page.waitForTimeout(500);
  const result = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  const problems = result.violations.map(
    (v) => `${label} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
  const sideways = await overflow(page);
  if (sideways > 0) problems.push(`${label} scrolls sideways by ${String(sideways)}`);
  return problems;
}

/** The runs that exist at minute `m`, counted from the raw answer with timeline-at.ts. */
function expectedAt(answer: Answer, minute: number) {
  const at = Date.parse(answer.axis.start) + minute * MINUTE;
  const values = valuesAt(answer as never, at);
  const states = values.runs.map((run) => run.state);
  return {
    values,
    working: states.filter((s) => s === "working").length,
    finished: states.filter((s) => s === "finished").length,
    notStarted: states.filter((s) => s === "not_started").length,
    total: states.length,
  };
}

/** Two minutes on the ended answer where the session still has runs to start and fold. */
const SAMPLE_MINUTES = [6, 15, 24];

/**
 * The "?" buttons a Tab walk meets on the way from the Session Select to the line: the Session
 * totals entry on the Read from cache tile and the Runs tile, then the timeline's own, which sits
 * after the Go to end button in the card header.
 */
const TOTALS_HELP = fill(en.hp_trigger, { title: "Session totals" });
const TIMELINE_HELP = fill(en.hp_trigger, { title: "Who worked when" });

/** Presses Tab, then Shift+Tab, until the locator holds focus, so a walk fails with its step. */
async function reach(page: Page, target: Locator, max = 40): Promise<void> {
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

/**
 * Live to Session review with the keyboard only. At 1440 the sidebar's Sessions link opens the list.
 * At 375 the tab bar's Review link opens Summary and the segmented Sessions link goes on. The row
 * link of the session opens it. Nothing is loaded, set or clicked.
 */
async function keysToSession(page: Page, width: number, session: string): Promise<void> {
  const nav = page.getByRole("navigation", { name: en.nav_aria });
  if (width >= 721) {
    await reach(page, nav.getByRole("link", { name: en.nav_sessions, exact: true }));
    await page.keyboard.press("Enter");
  } else {
    await reach(page, nav.getByRole("link", { name: en.nav_review, exact: true }));
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: en.nav_summary })).toBeFocused();
    await reach(page, page.getByRole("link", { name: en.nav_sessions, exact: true }));
    await page.keyboard.press("Enter");
  }
  await expect(page.getByRole("heading", { level: 1, name: en.nav_sessions })).toBeFocused();
  const row = page.locator(`a.review-link[data-session="${session}"]`);
  await reach(page, row);
  await page.keyboard.press("Enter");
  await expect(slider(page)).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`/review/sessions/${session}`));
}

/** The recorded old `/api/live` at a clock time, as the M2 oracle names its files. */
interface OldLive {
  at: string;
  session: { started: string; last_request: string } | null;
  runs: {
    run_id: string;
    agent: string | null;
    state: string;
    tokens: number;
    cost: number | null;
  }[];
  totals: { tokens: number; cost: number | null; requests: number };
}

function oldLiveAt(scenario: FlowScenario, atMs: number): OldLive {
  const stamp = new Date(atMs)
    .toISOString()
    .replace(/[-:]/g, "")
    .replace(/\.\d+Z$/, "Z");
  const file = join(
    import.meta.dirname,
    "..",
    "..",
    "fixtures",
    "oracle",
    "live",
    scenario,
    `at-${stamp}.json`,
  );
  return JSON.parse(readFileSync(file, "utf8")) as OldLive;
}

for (const scenario of SCENARIOS) {
  test.describe(`${scenario} scenario, ended`, () => {
    test.use({ flow: scenario });

    test("renders at 320, 375 and 1440 in light, dark and forced colours with no axe problems", async ({
      page,
      server,
    }) => {
      test.setTimeout(150_000);
      await start(page, server, ENDED_CLOCK);
      await openReview(page, flowSession(server, scenario), "&at=12");
      const problems: string[] = [];
      for (const width of [320, 375, 1440]) {
        for (const theme of ["light", "dark"] as const) {
          await page.setViewportSize({ width, height: 900 });
          await page.emulateMedia({ colorScheme: theme });
          problems.push(...(await axeProblems(page, `${scenario} ${String(width)} ${theme}`)));
        }
        await page.emulateMedia({ colorScheme: "light", forcedColors: "active" });
        await page.setViewportSize({ width, height: 900 });
        await expect(slider(page)).toBeVisible();
        await expect(page.locator(".replay-handle")).toBeVisible();
        const sideways = await overflow(page);
        if (sideways > 0) {
          problems.push(`${scenario} ${String(width)} forced colours scrolls sideways`);
        }
        await page.emulateMedia({ forcedColors: "none" });
      }
      expect(problems).toEqual([]);
    });
  });
}

test.describe("busy scenario, running", () => {
  test.use({ flow: "busy" });

  test("renders at 320, 375 and 1440 in light and dark with no axe problems", async ({
    page,
    server,
  }) => {
    test.setTimeout(120_000);
    await start(page, server, RUNNING_CLOCK);
    await openReview(page, flowSession(server, "busy"));
    const problems: string[] = [];
    for (const width of [320, 375, 1440]) {
      for (const theme of ["light", "dark"] as const) {
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme: theme });
        problems.push(...(await axeProblems(page, `busy running ${String(width)} ${theme}`)));
      }
    }
    expect(problems).toEqual([]);
  });

  test("follows Now until the line is moved, stays after, and Back to now returns", async ({
    page,
    server,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, RUNNING_CLOCK);
    const id = flowSession(server, "busy");
    await openReview(page, id);
    const line = slider(page);
    const first = await fullAnswer(page, id);
    const max = Math.floor((Date.parse(first.axis.end) - Date.parse(first.axis.start)) / MINUTE);
    await expect(line).toHaveValue(String(max));
    await expect(line).toHaveAttribute(
      "aria-valuetext",
      `${en.sr_at_now}, ${await clockText(page, Date.parse(first.axis.start) + max * MINUTE)}`,
    );
    await expect(page.getByRole("link", { name: en.rv_open_live })).toBeVisible();
    await expect(page.getByRole("button", { name: en.sr_to_now })).toHaveCount(0);

    // Two minutes pass. The 5 second poll brings them and the line goes with them.
    await setServerClock(page, RUNNING_CLOCK + 2 * MINUTE);
    await expect(line).toHaveValue(String(max + 2), { timeout: 15_000 });
    await expect(page).not.toHaveURL(/[?&]at=/);

    // Moved: the URL holds the minute and the line stays put as time passes.
    await line.focus();
    await page.keyboard.press("ArrowLeft");
    await expect(line).toHaveValue(String(max + 1));
    await expect(page).toHaveURL(new RegExp(`[?&]at=${String(max + 1)}(&|$)`));
    await setServerClock(page, RUNNING_CLOCK + 3 * MINUTE);
    await expect(line).toHaveAttribute("max", String(max + 3), { timeout: 15_000 });
    await expect(line).toHaveValue(String(max + 1));

    // Back to now: the minute leaves the URL, the line goes to the end and takes the focus.
    const back = page.getByRole("button", { name: en.sr_to_now });
    await back.click();
    await expect(line).toHaveValue(String(max + 3));
    await expect(line).toBeFocused();
    await expect(page).not.toHaveURL(/[?&]at=/);
    await expect(back).toHaveCount(0);
  });
});

test.describe("a session that is not there", () => {
  test.use({ flow: "busy" });

  test("shows the gone state at 375 and 1440 with no axe problems", async ({ page, server }) => {
    await start(page, server, ENDED_CLOCK);
    await go(page, "no-such-session");
    await expect(page.getByRole("heading", { level: 1, name: en.gone_title })).toBeVisible();
    await expect(page.getByRole("alert")).toContainText(fill(en.gone_h, { project: PROJECT_NAME }));
    await expect(page.getByRole("link", { name: en.gone_all })).toBeVisible();
    await expect(page.getByRole("slider")).toHaveCount(0);
    const problems: string[] = [];
    for (const width of [375, 1440]) {
      await page.setViewportSize({ width, height: 800 });
      problems.push(...(await axeProblems(page, `gone ${String(width)}`)));
    }
    expect(problems).toEqual([]);
    await page.getByRole("link", { name: en.gone_all }).click();
    await expect(page).toHaveURL(/#\/p\/tidewater-reporting\/review\/sessions\?range=30d$/);
  });

  test("clamps a minute past the axis to the end without a message", async ({ page, server }) => {
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "busy");
    await openReview(page, id, "&at=9999");
    const answer = await fullAnswer(page, id);
    const max = endMinute(answer);
    await expect(slider(page)).toHaveValue(String(max));
    await expect(page).not.toHaveURL(/[?&]at=/);
    await expect(page.getByText(en.t_whole).first()).toBeVisible();
  });
});

test.describe("many scenario, ended", () => {
  test.use({ flow: "many" });

  for (const width of [375, 1440]) {
    test(`keyboard walkthrough at ${String(width)}`, async ({ page, server }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 900 });
      await start(page, server, ENDED_CLOCK);
      const id = flowSession(server, "many");
      const answer = await fullAnswer(page, id);
      const max = endMinute(answer);
      // A minute where a crowded parent still has runs that start later, so a fold is on screen.
      let minute = 0;
      for (const candidate of [4, 8, 12, 16, 20]) {
        if (expectedAt(answer, candidate).notStarted >= 3) {
          minute = candidate;
          break;
        }
      }
      expect(minute).toBeGreaterThan(0);
      await openReview(page, id, `&at=${String(minute)}`);

      // The route harness puts focus on the heading.
      const heading = page.locator("main h1");
      await expect(heading).toBeFocused();
      await expect(heading).toHaveText(answer.session.branch ?? en.lv_no_branch);

      await page.keyboard.press("Tab");
      await expect(
        page.getByRole("button", { name: new RegExp(`^${en.rv_session_scope}`) }),
      ).toBeFocused();
      // The one Session totals "?" button on the tiles, then Go to end, then the timeline "?".
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TOTALS_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: en.sr_to_end })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TIMELINE_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      const line = slider(page);
      await expect(line).toBeFocused();
      await expect(line).toHaveValue(String(minute));

      await page.keyboard.press("ArrowRight");
      await expect(line).toHaveValue(String(minute + 1));
      await page.keyboard.press("PageUp");
      await expect(line).toHaveValue(String(minute + 6));
      await page.keyboard.press("PageDown");
      await expect(line).toHaveValue(String(minute + 1));
      await page.keyboard.press("Home");
      await expect(line).toHaveValue("0");
      await page.keyboard.press("End");
      await expect(line).toHaveValue(String(max));
      // At the end the button goes away and the line keeps the focus.
      await expect(page.getByRole("button", { name: en.sr_to_end })).toHaveCount(0);
      await expect(line).toBeFocused();
      await page.keyboard.press("ArrowLeft");
      await expect(line).toHaveValue(String(max - 1));

      // Tab leaves the line for the first fold's button, and Enter opens it.
      await page.keyboard.press("Tab");
      const fold = page.locator(".lane-fold-button").first();
      await expect(fold).toBeFocused();
      const expanded = await fold.getAttribute("aria-expanded");
      await page.keyboard.press("Enter");
      await expect(fold).toHaveAttribute("aria-expanded", expanded === "true" ? "false" : "true");
      await expect(fold).toBeFocused();
    });
  }

  test("header and replay control match their accessibility snapshots", async ({
    page,
    server,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "many");
    const answer = await fullAnswer(page, id);
    await openReview(page, id, "&at=15");
    const start0 = Date.parse(answer.axis.start);
    const at = await clockText(page, start0 + 15 * MINUTE);
    const branch = answer.session.branch ?? en.lv_no_branch;

    const header = page.locator("main header").first();
    await expect(header).toMatchAriaSnapshot(`
      - link /${en.sr_back.replace("{range}", en.rg_p_days.replace("{n}", "30"))}/
      - text: ${en.rs_ended}
      - heading "${branch}" [level=1]
      - paragraph
      - button /^${en.rv_session_scope}/
    `);
    await expect(page.locator(".replay")).toMatchAriaSnapshot(`
      - text: ${en.sr_showing} ${at}
      - slider "${en.sr_label}": "15"
      - text: ${fill(en.sr_keys, { n: 5 })}
    `);
  });

  test("the slider's value text is exact after an arrow and Page Up, and the settle line is said once", async ({
    page,
    server,
  }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "many");
    const answer = await fullAnswer(page, id);
    const start0 = Date.parse(answer.axis.start);
    await openReview(page, id, "&at=10");
    const line = slider(page);
    await line.focus();

    await page.keyboard.press("ArrowRight");
    await expect(line).toHaveAttribute(
      "aria-valuetext",
      await clockText(page, start0 + 11 * MINUTE),
    );
    await expect(line).toHaveValue("11");

    // Watch the one polite region from here on.
    await page.evaluate(() => {
      const said: string[] = [];
      (window as unknown as { __said: string[] }).__said = said;
      new MutationObserver((records) => {
        for (const record of records) {
          const node =
            record.target instanceof Element ? record.target : record.target.parentElement;
          const text = node?.closest('div.sr-only[role="status"]')?.textContent ?? "";
          if (text !== "") said.push(text);
        }
      }).observe(document, { subtree: true, childList: true, characterData: true });
    });
    await page.keyboard.press("PageUp");
    await page.keyboard.press("PageUp");
    await expect(line).toHaveAttribute(
      "aria-valuetext",
      await clockText(page, start0 + 21 * MINUTE),
    );
    const m = expectedAt(answer, 21);
    const line21 = fill(en.sr_sum, {
      time: await clockText(page, start0 + 21 * MINUTE),
      w: m.working,
      f: m.finished,
      s: m.notStarted,
      cost: formatCost(m.values.totals.cost ?? 0),
    });
    await expect(status(page)).toHaveText(line21, { timeout: 5_000 });
    const said = await page.evaluate(() => (window as unknown as { __said: string[] }).__said);
    // Two keys moved the line twice, but the region spoke once.
    expect(said).toEqual([line21]);
  });

  test("the chart's image label follows the line", async ({ page, server }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "many");
    const answer = await fullAnswer(page, id);
    const start0 = Date.parse(answer.axis.start);
    for (const minute of [8, 20]) {
      await openReview(page, id, `&at=${String(minute)}`);
      // Buckets 0 to minute - 1 have ended by the line.
      const sums = new Map<string, number>();
      for (const bucket of answer.buckets.slice(0, minute)) {
        for (const [model, tokens] of Object.entries(bucket.by_model)) {
          const family = /(opus|sonnet|haiku|fable)/.exec(model)?.[1] ?? model;
          sums.set(family, (sums.get(family) ?? 0) + tokens);
        }
      }
      const top = [...sums.entries()].sort((a, b) => b[1] - a[1])[0];
      const total = [...sums.values()].reduce((a, b) => a + b, 0);
      const label = fill(en.sr_img, {
        start: await clockText(page, start0),
        time: await clockText(page, start0 + minute * MINUTE),
        total: formatTokens(total),
        model: await page.evaluate((family) => {
          const entry = Array.from(document.querySelectorAll(".bars-legend li")).find((li) =>
            (li.textContent ?? "").toLowerCase().startsWith(family ?? ""),
          );
          return (entry?.textContent ?? "").replace(/\s*\S+$/, "").trim();
        }, top?.[0]),
      });
      await expect(page.getByRole("img", { name: label })).toBeVisible();
    }
  });
});

test.describe("busy scenario, replay oracle", () => {
  test.use({ flow: "busy" });

  test("at three times the tiles and the rows equal the values timeline-at.ts picks", async ({
    page,
    server,
  }) => {
    test.setTimeout(120_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "busy");
    const answer = await fullAnswer(page, id);
    const start0 = Date.parse(answer.axis.start);
    const stateWord: Record<string, string> = {
      working: en.rs_working,
      idle: en.rs_idle,
      finished: en.rs_finished,
      not_started: en.c_not_started,
    };
    for (const minute of SAMPLE_MINUTES) {
      await openReview(page, id, `&at=${String(minute)}`);
      const time = await clockText(page, start0 + minute * MINUTE);
      const expected = expectedAt(answer, minute);
      const tile = (label: string): Locator => page.locator(".tile").filter({ hasText: label });

      const cost = tile(fill(en.t_at_cost, { time }));
      await expect(cost.locator(".tile-value")).toHaveText(money(expected.values.totals.cost));
      await expect(cost.locator(".tile-delta")).toContainText(
        fill(en.t_of_cost, { v: money(answer.totals.cost) }),
      );
      const tokens = tile(fill(en.t_at_tokens, { time }));
      await expect(tokens.locator(".tile-value")).toHaveText(
        formatTokens(expected.values.totals.tokens + expected.values.totals.cache_read),
      );
      await expect(tokens.locator(".tile-delta")).toContainText(
        fill(en.t_of_tokens, { v: formatTokens(answer.totals.tokens + answer.totals.cache_read) }),
      );
      const runs = tile(fill(en.t_at_runs, { time }));
      await expect(runs.locator(".tile-value")).toHaveText(
        String(expected.total - expected.notStarted),
      );
      await expect(runs.locator(".tile-delta")).toContainText(
        expected.notStarted > 0
          ? fill(en.t_of_runs_other, { w: expected.working, n: expected.notStarted })
          : fill(en.t_of_runs_w_other, { n: expected.working }),
      );

      // Every row the lane shows reads the state timeline-at.ts gives its run.
      const lane = page.getByRole("list", { name: en.sr_tl_h });
      for (const run of expected.values.runs) {
        const source = answer.runs.find((entry) => entry.run_id === run.runId);
        if (source === undefined) continue;
        const name =
          source.agent === null
            ? en.tl_main
            : (source.label_n ?? 1) > 1
              ? `${source.agent} ${String(source.label_n)}`
              : source.agent;
        const row = lane.locator("li.lane-row").filter({
          has: page.locator(".lane-name", { hasText: new RegExp(`^${name}$`) }),
        });
        if ((await row.count()) === 0) continue;
        await expect(row.first().locator(".lane-state")).toContainText(stateWord[run.state] ?? "");
      }
    }
  });

  test("shows the whole session at the end", async ({ page, server }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "busy");
    const answer = await fullAnswer(page, id);
    await openReview(page, id);
    await expect(
      page.locator(".tile").filter({ hasText: en.rv_t_cost }).locator(".tile-value"),
    ).toHaveText(money(answer.totals.cost));
    await expect(page.getByText(en.t_whole)).toHaveCount(3);
    await expect(
      page.locator(".tile").filter({ hasText: en.t_runs }).locator(".tile-value"),
    ).toHaveText(String(answer.totals.runs));
  });
});

// ---- the old /api/live as the oracle -------------------------------------------------------------

/**
 * Five minutes across the busy session, each with a recording of the old /api/live at that exact
 * clock time. The recordings hold every minute of the busy scenario from 6:11 PM to 6:40 PM, so
 * five different minutes check against five different recordings. The minutes are picked where the
 * runs differ: four runs started with four more to come (6:15 and 6:18 PM), then seven started
 * with one more to come (6:23 PM), then all eight (6:31 and 6:36 PM), with scouts and the writer finished by then. The
 * last request is at 6:39 PM, so the line at 6:39 PM is the end and reads the whole session.
 */
const ORACLE_MINUTES = [5, 8, 13, 21, 26];

test.describe("busy scenario, old /api/live oracle", () => {
  test.use({ flow: "busy" });

  test("at five recorded minutes the tiles and the row states equal what the old payload said then", async ({
    page,
    server,
  }) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "busy");
    const answer = await fullAnswer(page, id);
    const start0 = Date.parse(answer.axis.start);
    const stateWord: Record<string, string> = {
      working: en.rs_working,
      idle: en.rs_idle,
      done: en.rs_finished,
    };
    const seen = new Set<string>();
    for (const minute of ORACLE_MINUTES) {
      const old = oldLiveAt("busy", start0 + minute * MINUTE);
      expect(Date.parse(old.at), `recording for minute ${String(minute)}`).toBe(
        start0 + minute * MINUTE,
      );
      expect(old.session).not.toBeNull();
      await openReview(page, id, `&at=${String(minute)}`);
      const time = await clockText(page, start0 + minute * MINUTE);
      const tile = (label: string): Locator => page.locator(".tile").filter({ hasText: label });
      const working = old.runs.filter((run) => run.state === "working").length;
      const notStarted = answer.totals.runs - old.runs.length;

      const cost = tile(fill(en.t_at_cost, { time }));
      await expect(cost.locator(".tile-value")).toHaveText(money(old.totals.cost));
      const tokens = tile(fill(en.t_at_tokens, { time }));
      await expect(tokens.locator(".tile-value")).toHaveText(formatTokens(old.totals.tokens));
      const runs = tile(fill(en.t_at_runs, { time }));
      await expect(runs.locator(".tile-value")).toHaveText(String(old.runs.length));
      await expect(runs.locator(".tile-delta")).toContainText(
        notStarted > 0
          ? fill(en.t_of_runs_other, { w: working, n: notStarted })
          : fill(en.t_of_runs_w_other, { n: working }),
      );

      // Finished runs and runs that start later sit under folds, so open every fold first.
      const lane = page.getByRole("list", { name: en.sr_tl_h });
      const closed = lane.locator('.lane-fold-button[aria-expanded="false"]');
      for (let opened = 0; opened < 10 && (await closed.count()) > 0; opened++) {
        await closed.first().click();
      }
      await expect(closed).toHaveCount(0);
      // The rows that wait to start are the runs the old payload never listed.
      await expect(lane.locator("li.lane-row-future:not(.lane-row-fold)")).toHaveCount(notStarted);

      // Each run the old payload lists reads the state the old payload gave it.
      for (const was of old.runs) {
        const source = answer.runs.find(
          (entry) => entry.run_id === (was.run_id === "@main" ? "main" : was.run_id),
        );
        expect(source, `run ${was.run_id} at minute ${String(minute)}`).toBeDefined();
        const name =
          source?.agent === null || source === undefined
            ? en.tl_main
            : (source.label_n ?? 1) > 1
              ? `${source.agent ?? ""} ${String(source.label_n)}`
              : (source.agent ?? "");
        const row = lane.locator("li.lane-row").filter({
          has: page.locator(".lane-name", { hasText: new RegExp(`^${name}$`) }),
        });
        await expect(row, `row ${name} at minute ${String(minute)}`).toHaveCount(1);
        await expect(row.locator(".lane-state")).toContainText(stateWord[was.state] ?? "?");
        seen.add(`${name} ${was.state}`);
      }
    }
    // The five minutes cover runs that are working and runs that are done.
    expect([...seen].some((entry) => entry.endsWith(" working"))).toBe(true);
    expect([...seen].some((entry) => entry.endsWith(" done"))).toBe(true);
  });
});

// ---- keyboard: replay a past session --------------------------------------------------------------

test.describe("busy scenario, replay with the keyboard only", () => {
  test.use({ flow: "busy" });

  for (const width of [375, 1440]) {
    test(`replay a past session at ${String(width)} wide: Sessions, a session, then the line by keys`, async ({
      page,
      server,
    }) => {
      test.setTimeout(150_000);
      await page.setViewportSize({ width, height: 900 });
      await start(page, server, ENDED_CLOCK);
      const id = flowSession(server, "busy");
      const answer = await fullAnswer(page, id);
      const start0 = Date.parse(answer.axis.start);
      const max = endMinute(answer);
      const valueText = (minute: number): Promise<string> =>
        clockText(page, start0 + minute * MINUTE);

      await keysToSession(page, width, id);
      const heading = page.locator("main h1");
      await expect(heading).toBeFocused();
      await expect(heading).toHaveText(answer.session.branch ?? en.lv_no_branch);
      const step = Number(
        /Page Down move (\d+)/.exec((await page.locator(".replay").textContent()) ?? "")?.[1],
      );
      expect(step).toBeGreaterThan(1);

      // The Session Select, the two Session totals "?" buttons, the timeline "?", then the line.
      // At the end there is no Go to end button.
      await page.keyboard.press("Tab");
      await expect(
        page.getByRole("button", { name: new RegExp(`^${en.rv_session_scope}`) }),
      ).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TOTALS_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TIMELINE_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      const line = slider(page);
      await expect(line).toBeFocused();
      await expect(line).toHaveValue(String(max));
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(max));

      await page.keyboard.press("ArrowLeft");
      await expect(line).toHaveValue(String(max - 1));
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(max - 1));
      await expect(page).toHaveURL(new RegExp(`[?&]at=${String(max - 1)}(&|$)`));

      await page.keyboard.press("Home");
      await expect(line).toHaveValue("0");
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(0));

      await page.keyboard.press("ArrowRight");
      await expect(line).toHaveValue("1");
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(1));

      await page.keyboard.press("PageUp");
      await expect(line).toHaveValue(String(1 + step));
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(1 + step));

      await page.keyboard.press("PageDown");
      await expect(line).toHaveValue("1");
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(1));

      await page.keyboard.press("End");
      await expect(line).toHaveValue(String(max));
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(max));
      await expect(page).not.toHaveURL(/[?&]at=/);
      await expect(line).toBeFocused();
      // The settled line is said, and the tiles read the whole session at the end.
      await expect(page.getByText(en.t_whole)).toHaveCount(3);
    });

    test(`replay a running session at ${String(width)} wide: move the line, Tab to Back to now, press Enter`, async ({
      page,
      server,
    }) => {
      test.setTimeout(150_000);
      await page.setViewportSize({ width, height: 900 });
      await start(page, server, RUNNING_CLOCK);
      const id = flowSession(server, "busy");
      const answer = await fullAnswer(page, id);
      const start0 = Date.parse(answer.axis.start);
      const valueText = (minute: number): Promise<string> =>
        clockText(page, start0 + minute * MINUTE);

      await keysToSession(page, width, id);
      await expect(page.locator("main h1")).toBeFocused();
      const step = Number(
        /Page Down move (\d+)/.exec((await page.locator(".replay").textContent()) ?? "")?.[1],
      );
      // The Session Select and the Open in Live link come before the line on a running session.
      await page.keyboard.press("Tab");
      await expect(
        page.getByRole("button", { name: new RegExp(`^${en.rv_session_scope}`) }),
      ).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link", { name: en.rv_open_live })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TOTALS_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      await expect(page.getByRole("button", { name: TIMELINE_HELP })).toBeFocused();
      await page.keyboard.press("Tab");
      const line = slider(page);
      await expect(line).toBeFocused();
      const max = Number(await line.getAttribute("max"));
      await expect(line).toHaveValue(String(max));
      await expect(line).toHaveAttribute(
        "aria-valuetext",
        `${en.sr_at_now}, ${await valueText(max)}`,
      );
      await expect(page.getByRole("button", { name: en.sr_to_now })).toHaveCount(0);

      // Move the line back. It leaves Now, so the button appears and the words lose "Now".
      await page.keyboard.press("PageDown");
      await expect(line).toHaveValue(String(max - step));
      await expect(line).toHaveAttribute("aria-valuetext", await valueText(max - step));
      await page.keyboard.press("ArrowRight");
      await expect(line).toHaveValue(String(max - step + 1));
      const back = page.getByRole("button", { name: en.sr_to_now });
      await expect(back).toBeVisible();
      await expect(back).toMatchAriaSnapshot(`- button "${en.sr_to_now}"`);

      // The button sits two stops before the line, because the timeline "?" comes between them, so
      // Shift+Tab twice reaches it. Tab alone wraps through the page.
      await page.keyboard.press("Shift+Tab");
      await expect(page.getByRole("button", { name: TIMELINE_HELP })).toBeFocused();
      await page.keyboard.press("Shift+Tab");
      await expect(back).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(line).toHaveValue(String(max));
      await expect(line).toHaveAttribute(
        "aria-valuetext",
        `${en.sr_at_now}, ${await valueText(max)}`,
      );
      await expect(line).toBeFocused();
      await expect(page).not.toHaveURL(/[?&]at=/);
      await expect(back).toHaveCount(0);

      // At the end of a running session the line follows Now: two minutes pass and it goes along.
      await setServerClock(page, RUNNING_CLOCK + 2 * MINUTE);
      await expect(line).toHaveValue(String(max + 2), { timeout: 15_000 });
      await expect(line).toHaveAttribute(
        "aria-valuetext",
        `${en.sr_at_now}, ${await valueText(max + 2)}`,
      );
    });
  }
});

// ---- accessibility snapshots ----------------------------------------------------------------------

test.describe("busy scenario, snapshots", () => {
  test.use({ flow: "busy" });

  test("the replay control matches its snapshot at two different minutes", async ({
    page,
    server,
  }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await start(page, server, ENDED_CLOCK);
    const id = flowSession(server, "busy");
    const answer = await fullAnswer(page, id);
    const start0 = Date.parse(answer.axis.start);
    for (const minute of [8, 21]) {
      await openReview(page, id, `&at=${String(minute)}`);
      const at = await clockText(page, start0 + minute * MINUTE);
      await expect(page.locator(".replay")).toMatchAriaSnapshot(`
        - text: ${en.sr_showing} ${at}
        - slider "${en.sr_label}": "${String(minute)}"
        - text: ${fill(en.sr_keys, { n: 5 })}
      `);
    }
  });
});
