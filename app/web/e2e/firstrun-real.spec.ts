/// <reference lib="dom" />
/// <reference types="node" />
/*
 * First run on a real ingest. The server reads the demo build (a fresh data folder, so the store
 * is empty), paced at 30 ms a file so the 538 files take about 15 seconds, with the live price
 * fetch off. The page counts files, then the size bar moves forward and never back, the step
 * change is announced once, and the page lands on the launch project's Live with focus on its h1.
 * The footer then shows the freshness, history and price lines (the bundled copy's wording, because
 * the fetch is off), and axe is clean at 375 and 1440.
 *
 * The server binds a port in 47000 to 47999, picked by probing, never 8377.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { mkdtempSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { en } from "../src/strings/en";
import { expectUnlocked, gateHeading, linkFor } from "./gate";
import { expect, startServer, test } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const PACE_MS = "30";

interface Sample {
  at: number;
  now: number | null;
  text: string | null;
}

interface Probes {
  __said: string[];
  __bar: Sample[];
}

function listens(port: number): Promise<boolean> {
  return new Promise((done) => {
    const probe = createServer();
    probe.once("error", () => {
      done(false);
    });
    probe.listen(port, "127.0.0.1", () => {
      probe.close(() => {
        done(true);
      });
    });
  });
}

async function freePort(): Promise<number> {
  for (let tries = 0; tries < 50; tries++) {
    const port = 47500 + Math.floor(Math.random() * 400);
    if (await listens(port)) return port;
  }
  throw new Error("no free port in 47500 to 47899");
}

async function axeProblems(page: Page, width: number, label: string): Promise<string[]> {
  await page.setViewportSize({ width, height: 800 });
  const result = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  return result.violations.map(
    (v) =>
      `${label} ${String(width)} axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

test("first run on the demo build counts, moves forward, then lands on Live", async ({ page }) => {
  test.setTimeout(150_000);
  const dataDir = mkdtempSync(join(tmpdir(), "bartab-e2e-real-"));
  const server = await startServer({
    dataDir,
    port: await freePort(),
    fixture: null,
    args: [
      "--demo",
      "--ingest-pace-ms",
      PACE_MS,
      "--no-price-fetch",
      "--project-dir",
      join(dataDir, "demo", "projects", PROJECT),
    ],
  });
  try {
    expect(server.port).toBeGreaterThanOrEqual(47000);
    expect(server.port).toBeLessThanOrEqual(47999);

    // The live region and the bar are sampled inside the page, so axe runs in between never
    // hide a step. __said holds every distinct text the one polite region spoke.
    await page.addInitScript(() => {
      const said: string[] = [];
      const bar: Sample[] = [];
      Object.assign(window, { __said: said, __bar: bar });
      const region = () => document.querySelector('div.sr-only[role="status"]');
      let last = "";
      new MutationObserver(() => {
        const text = region()?.textContent ?? "";
        if (text !== "" && text !== last) {
          said.push(text);
          last = text;
        }
      }).observe(document, { subtree: true, childList: true, characterData: true });
      setInterval(() => {
        const el = document.querySelector('[role="progressbar"]');
        if (el === null) return;
        const raw = el.getAttribute("aria-valuenow");
        bar.push({
          at: performance.now(),
          now: raw === null ? null : Number(raw),
          text: el.getAttribute("aria-valuetext"),
        });
      }, 100);
    });

    const started = Date.now();
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto(linkFor(server.baseURL, server.code, "/"));
    await expect(gateHeading(page, "firstrun")).toBeVisible();
    await expect(page.getByText(en.fr_counting)).toBeVisible();
    await expect(page.getByRole("progressbar")).toHaveCount(0);

    const bar = page.getByRole("progressbar");
    await expect(bar).toHaveAttribute("aria-valuetext", /^\d+\.\d of \d+\.\d MB$/, {
      timeout: 20_000,
    });
    const problems = await axeProblems(page, 375, "first run");
    problems.push(...(await axeProblems(page, 1440, "first run")));

    await expect(page).toHaveURL(new RegExp(`#/p/${PROJECT}/live$`), { timeout: 90_000 });
    const seconds = (Date.now() - started) / 1000;
    console.log(`first run took ${seconds.toFixed(1)} s from the link to Live`);
    await expectUnlocked(page);
    const h1 = page.locator("main h1");
    await expect(h1).toHaveText(en.nav_live);
    await expect(h1).toBeFocused();

    const { said, samples } = await page.evaluate(() => {
      const probes = window as unknown as Probes;
      return { said: probes.__said, samples: probes.__bar };
    });
    const values = samples.map((s) => s.now).filter((n): n is number => n !== null);
    expect(new Set(values).size).toBeGreaterThanOrEqual(3);
    for (let i = 1; i < values.length; i++) {
      expect(values[i], `bar sample ${String(i)}`).toBeGreaterThanOrEqual(values[i - 1] ?? 0);
    }
    expect(said.filter((text) => text === en.fr_h)).toHaveLength(1);
    expect(said.at(-1)).toBe(en.nav_live);

    await page.setViewportSize({ width: 1440, height: 900 });
    const footer = page.locator(".sidebar-footer");
    await expect(footer).toContainText(/Updated /);
    await expect(footer).toContainText(/History since /);
    await expect(footer).toContainText(/Last backup /);
    // With the fetch off the prices come from the bundled copy, and the line names that source.
    await expect(footer).toContainText(/(Prices as of|Bundled prices,) /);
    problems.push(...(await axeProblems(page, 1440, "live")));
    problems.push(...(await axeProblems(page, 375, "live")));
    expect(problems).toEqual([]);
  } finally {
    await server.stop();
    rmSync(dataDir, { recursive: true, force: true });
  }
});
