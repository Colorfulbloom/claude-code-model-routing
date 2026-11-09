/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The Live page against the real server in flow mode (`--flow <scenario> --test-clock`). Three
 * kinds of check.
 *
 * Matrix. Each scenario (busy, many, unlinked, empty) renders at 320, 375 and 1440, light and dark,
 * with axe and no sideways scroll.
 *
 * Announcements. The data clock steps a minute at a time from 22:11 to 22:40 UTC through
 * POST /api/dev/clock, while the page's own clock is paused and moved by hand. A MutationObserver on
 * the one polite region counts what it says. The count must equal the minutes in which a run
 * started, began a round or finished, or the session ended, worked out here from the raw answers
 * and not from the page's code. A line for a row inside its quiet minute is held and counts in the
 * minute it is let out. Polls that answer `unchanged` must say nothing. The run repeats
 * under reduced motion, because the region is not an animation.
 *
 * Requests. Pause and a hidden tab send no timeline or session request in 5 s of page time, and
 * showing the page again sends one of each at once.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expectUnlocked, linkFor } from "./gate";
import { expect, test } from "./server";
import type { FlowScenario, Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const WIDTHS = [320, 375, 1440] as const;
const THEMES = ["light", "dark"] as const;
const SCENARIOS: FlowScenario[] = ["busy", "many", "unlinked", "empty"];
const FIRST_MINUTE = Date.parse("2026-10-30T22:11:00Z");
const LAST_MINUTE = Date.parse("2026-10-30T22:40:00Z");
const STEP = 60_000;

interface Run {
  run_id: string;
  state: string;
  rounds: unknown[];
}
interface Answer {
  server_time: string;
  session: { state: string };
  runs: Run[];
}

function flowSession(server: Server, scenario: FlowScenario): string {
  const flow = JSON.parse(
    readFileSync(join(server.dataDir, `flow-${scenario}`, "flow.json"), "utf8"),
  ) as { session: string };
  return flow.session;
}

/** Opens Live with no session named. The page picks the project's newest running one. */
async function openLive(page: Page, server: Server): Promise<void> {
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), `/p/${PROJECT}/live`));
  await expectUnlocked(page);
  await expect(page.getByRole("list", { name: "Who is working" })).toBeVisible();
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

/** The full timeline answer at the server's current clock, asked with no etag. */
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

/** Moves the page's paused clock one second, and waits for the poll that second starts. */
async function pollOnce(page: Page): Promise<{ unchanged: boolean }> {
  const answered = page.waitForResponse(
    (response) => response.url().includes("/timeline?") && response.request().method() === "GET",
    { timeout: 10_000 },
  );
  await page.clock.runFor(1000);
  const response = await answered;
  const body = (await response.json()) as { unchanged?: boolean };
  // Let the page draw the answer before the next step.
  await page.waitForTimeout(60);
  return { unchanged: body.unchanged === true };
}

const QUIET_MS = 60_000;

/**
 * What the announcer is meant to do, worked out from raw answers. A row that spoke less than a
 * minute ago (by the answers' own time) keeps its line instead of dropping it, a later line for the
 * row replaces the held one, and the held line speaks on the first answer after the minute if it is
 * still true. Returns true when a minute's change makes the region say something.
 */
function speaker(): (before: Answer, after: Answer) => boolean {
  const last = new Map<string, number>();
  const held = new Map<string, string>();
  return (before, after) => {
    const at = Date.parse(after.server_time);
    const was = new Map(before.runs.map((run) => [run.run_id, run]));
    let said = false;
    const quiet = (row: string): boolean => {
      const when = last.get(row);
      return when !== undefined && at - when < QUIET_MS;
    };
    const offer = (row: string, kind: string): void => {
      if (row === "@session" && held.has(row)) held.delete(row);
      else if (quiet(row)) held.set(row, kind);
      else {
        held.delete(row);
        last.set(row, at);
        said = true;
      }
    };
    for (const run of after.runs) {
      const old = was.get(run.run_id);
      if (old === undefined) offer(run.run_id, run.state === "finished" ? "finish" : "start");
      else if (run.rounds.length > old.rounds.length) offer(run.run_id, "round");
      else if (run.state === "finished" && old.state !== "finished") offer(run.run_id, "finish");
    }
    const ended = after.session.state === "ended";
    if (ended !== (before.session.state === "ended")) offer("@session", ended ? "ended" : "back");
    for (const [row, kind] of [...held]) {
      if (quiet(row)) continue;
      held.delete(row);
      const run = after.runs.find((candidate) => candidate.run_id === row);
      const stands =
        row === "@session"
          ? (kind === "ended") === ended
          : run !== undefined && (kind !== "finish" || run.state === "finished");
      if (stands) {
        last.set(row, at);
        said = true;
      }
    }
    return said;
  };
}

const observe = () => {
  const said: string[] = [];
  (window as unknown as { __said: string[] }).__said = said;
  new MutationObserver((records) => {
    for (const record of records) {
      const node = record.target instanceof Element ? record.target : record.target.parentElement;
      const region = node?.closest('div.sr-only[role="status"]');
      const text = region?.textContent ?? "";
      if (text !== "") said.push(text);
    }
  }).observe(document, { subtree: true, childList: true, characterData: true });
};

async function overflow(page: Page): Promise<number> {
  return page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
}

for (const scenario of SCENARIOS) {
  test.describe(`${scenario} scenario`, () => {
    test.use({ flow: scenario });

    test("renders at 320, 375 and 1440 in light and dark with no axe problems", async ({
      page,
      server,
    }) => {
      test.setTimeout(120_000);
      await openLive(page, server);
      const problems: string[] = [];
      for (const width of WIDTHS) {
        for (const theme of THEMES) {
          await page.setViewportSize({ width, height: 900 });
          await page.emulateMedia({ colorScheme: theme });
          // Colours transition on a theme change, and axe would read them half way.
          await page.waitForTimeout(500);
          const result = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
          for (const v of result.violations) {
            problems.push(
              `${scenario} ${String(width)} ${theme} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
            );
          }
          const sideways = await overflow(page);
          if (sideways > 0)
            problems.push(
              `${scenario} ${String(width)} ${theme} scrolls sideways by ${String(sideways)}`,
            );
        }
      }
      expect(problems).toEqual([]);
    });
  });
}

test.describe("the demo badge", () => {
  test.use({ flow: "busy" });

  test("shows in the sidebar at 1440 and the top bar at 375", async ({ page, server }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openLive(page, server);
    await expect(page.locator(".sidebar .brand").getByText("Demo data")).toBeVisible();
    await page.setViewportSize({ width: 375, height: 800 });
    await expect(page.locator(".top-bar").getByText("Demo data")).toBeVisible();
  });
});

for (const reduced of [false, true]) {
  test.describe(`announcements${reduced ? " under reduced motion" : ""}`, () => {
    test.use({ flow: "busy" });

    test("say one line per changed minute and nothing on unchanged polls", async ({
      page,
      server,
    }) => {
      test.setTimeout(180_000);
      const session = flowSession(server, "busy");
      if (reduced) await page.emulateMedia({ reducedMotion: "reduce" });
      await page.addInitScript(observe);
      await page.clock.install({ time: new Date("2026-11-09T12:00:00Z") });
      await openLive(page, server);
      // Start the run at 22:11 with a fresh page, so the first answer is the baseline.
      await setServerClock(page, FIRST_MINUTE);
      await page.reload();
      await expect(page.getByRole("list", { name: "Who is working" })).toBeVisible();
      await page.clock.pauseAt(new Date("2026-11-09T12:00:30Z"));
      await pollOnce(page);
      const base = await page.evaluate(
        () => (window as unknown as { __said: string[] }).__said.length,
      );

      let before = await fullAnswer(page, session);
      let expected = 0;
      const speaks = speaker();
      for (let at = FIRST_MINUTE + STEP; at <= LAST_MINUTE; at += STEP) {
        await setServerClock(page, at);
        const after = await fullAnswer(page, session);
        if (speaks(before, after)) expected += 1;
        before = after;
        const first = await pollOnce(page);
        expect(
          first.unchanged,
          `the poll at ${new Date(at).toISOString()} brings the new answer`,
        ).toBe(false);
        const said = await page.evaluate(
          () => (window as unknown as { __said: string[] }).__said.length,
        );
        // Three more polls at the same data time answer unchanged and add nothing.
        for (let n = 0; n < 3; n++) {
          const again = await pollOnce(page);
          expect(again.unchanged).toBe(true);
        }
        const settled = await page.evaluate(
          () => (window as unknown as { __said: string[] }).__said.length,
        );
        expect(settled, `unchanged polls after ${new Date(at).toISOString()} said something`).toBe(
          said,
        );
      }
      const lines = await page.evaluate(() =>
        (window as unknown as { __said: string[] }).__said.slice(),
      );
      test.info().annotations.push({
        type: "announced",
        description: `${String(lines.length - base)} of ${String(expected)} changed minutes: ${lines.slice(base).join(" | ")}`,
      });
      expect(lines.length - base).toBe(expected);
      expect(expected).toBeGreaterThan(3);
    });
  });
}

test.describe("requests", () => {
  test.use({ flow: "busy" });

  function counting(page: Page) {
    const seen = { timeline: 0, sessions: 0 };
    page.on("request", (request) => {
      const url = request.url();
      if (/\/api\/sessions\/[^/]+\/timeline/.test(url)) seen.timeline += 1;
      if (url.includes("/api/live/sessions")) seen.sessions += 1;
    });
    return seen;
  }

  async function fiveSeconds(page: Page): Promise<void> {
    for (let second = 0; second < 5; second++) {
      await page.clock.runFor(1000);
      await page.waitForTimeout(40);
    }
  }

  test("Pause sends none in 5 s of page time and Resume sends one of each at once", async ({
    page,
    server,
  }) => {
    await page.clock.install({ time: new Date("2026-11-09T12:00:00Z") });
    await openLive(page, server);
    await page.clock.pauseAt(new Date("2026-11-09T12:00:30Z"));
    const seen = counting(page);
    await page.getByRole("button", { name: "Pause" }).click();
    await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
    await page.waitForTimeout(200);
    seen.timeline = 0;
    seen.sessions = 0;
    await fiveSeconds(page);
    expect(seen).toEqual({ timeline: 0, sessions: 0 });
    await page.getByRole("button", { name: "Resume" }).click();
    await expect.poll(() => seen.timeline).toBe(1);
    await expect.poll(() => seen.sessions).toBe(1);
    // The page time did not move, so nothing else was asked for.
    await page.waitForTimeout(300);
    expect(seen).toEqual({ timeline: 1, sessions: 1 });
  });

  test("a hidden tab sends none in 5 s of page time and showing it sends one of each at once", async ({
    page,
    server,
  }) => {
    await page.clock.install({ time: new Date("2026-11-09T12:00:00Z") });
    await openLive(page, server);
    await page.clock.pauseAt(new Date("2026-11-09T12:00:30Z"));
    const seen = counting(page);
    const visibility = (state: "hidden" | "visible") =>
      page.evaluate((value) => {
        Object.defineProperty(document, "visibilityState", {
          configurable: true,
          get: () => value,
        });
        document.dispatchEvent(new Event("visibilitychange"));
      }, state);
    await visibility("hidden");
    await page.waitForTimeout(200);
    seen.timeline = 0;
    seen.sessions = 0;
    await fiveSeconds(page);
    expect(seen).toEqual({ timeline: 0, sessions: 0 });
    await visibility("visible");
    await expect.poll(() => seen.timeline).toBe(1);
    await expect.poll(() => seen.sessions).toBe(1);
    await page.waitForTimeout(300);
    expect(seen).toEqual({ timeline: 1, sessions: 1 });
  });
});
