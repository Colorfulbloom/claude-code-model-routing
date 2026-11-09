/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Spike 1, code swap end to end (m0-build.md section 6). Link swap, reload, single use, second
 * tabs by link and by window.open, unlocking a locked tab in place, and a server restart. Each
 * finding is also written to test-results/spike1/<name>.json for the spike note.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import type { BrowserContext, Page } from "@playwright/test";
import { en } from "../src/strings/en";
import {
  KEYS,
  expectLocked,
  expectOtherTabBack,
  expectUnlocked,
  linkFor,
  lockedHeading,
  storage,
} from "./gate";
import { expect, startServer, test } from "./server";

const ROUTE = "/p/tidewater-reporting/review/agents";
const outDir = resolve(import.meta.dirname, "..", "test-results", "spike1");

function record(name: string, data: unknown): void {
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, `${name}.json`), JSON.stringify(data, null, 2));
}

/** Samples a tab every 4 ms from its first script, so the offer unlock time can be read. */
async function addProbe(context: BrowserContext): Promise<void> {
  await context.addInitScript((lockedHeading: string) => {
    interface Probe {
      initialKey: boolean;
      keyAt: number | null;
      unlockedAt: number | null;
      lockedAt: number | null;
    }
    const probe: Probe = { initialKey: false, keyAt: null, unlockedAt: null, lockedAt: null };
    const read = () => {
      try {
        return window.sessionStorage.getItem("bartab.readKey");
      } catch {
        return null;
      }
    };
    probe.initialKey = read() !== null;
    (window as unknown as { __probe: Probe }).__probe = probe;
    const timer = setInterval(() => {
      const now = performance.now();
      if (probe.keyAt === null && read() !== null) probe.keyAt = now;
      const h1 = document.querySelector("h1");
      const hold = document.querySelector(".hold") !== null;
      if (h1 !== null && !hold) {
        if (h1.textContent === lockedHeading) probe.lockedAt ??= now;
        else probe.unlockedAt ??= now;
      }
      if (now > 4000) clearInterval(timer);
    }, 4);
  }, en.lk_h);
}

async function probeOf(page: Page) {
  return page.evaluate(
    () =>
      (
        window as unknown as {
          __probe: {
            initialKey: boolean;
            keyAt: number | null;
            unlockedAt: number | null;
            lockedAt: number | null;
          };
        }
      ).__probe,
  );
}

test("a link swaps the code, strips it, keeps the keys and survives a reload", async ({
  page,
  server,
}) => {
  await page.goto(linkFor(server.baseURL, server.code, ROUTE));
  await expectUnlocked(page);
  expect(page.url()).not.toContain("code=");
  expect(page.url()).toContain(`#${ROUTE}`);
  const stored = await storage(page);
  expect(stored[KEYS.readKey]).toBeTruthy();
  expect(stored[KEYS.instance]).toBe(server.instance);
  expect(stored[KEYS.route]).toBe(ROUTE);

  await page.reload();
  await expectUnlocked(page);
  expect(page.url()).toContain(`#${ROUTE}`);
  expect((await storage(page))[KEYS.readKey]).toBe(stored[KEYS.readKey]);
});

test("the same link in a fresh context is locked with code_used", async ({
  page,
  browser,
  server,
}) => {
  await page.goto(linkFor(server.baseURL, server.code));
  await expectUnlocked(page);

  const other = await browser.newContext();
  const page2 = await other.newPage();
  await page2.goto(linkFor(server.baseURL, server.code));
  await expectLocked(page2, "code_used");
  expect(page2.url()).not.toContain("code=");
  expect((await storage(page2))[KEYS.readKey]).toBeUndefined();
  await other.close();
});

test("an unknown code is locked with code_unknown, a foreign instance with server_restarted", async ({
  page,
  server,
}) => {
  await page.goto(linkFor(server.baseURL, `${server.instance}.not-a-real-code`));
  await expectLocked(page, "code_unknown");

  await page.goto("about:blank");
  await page.goto(linkFor(server.baseURL, "00000000.not-a-real-code"));
  await expectLocked(page, "server_restarted");
});

const methods = [
  {
    name: "window.open",
    open: (page: Page, url: string) => page.evaluate((u) => window.open(u), url),
  },
  {
    name: "window.open noopener",
    open: (page: Page, url: string) =>
      page.evaluate((u) => window.open(u, "_blank", "noopener"), url),
  },
  {
    name: "link target=_blank",
    open: (page: Page, url: string) => clickLink(page, url, null),
  },
  {
    name: "link target=_blank rel=noopener",
    open: (page: Page, url: string) => clickLink(page, url, "noopener"),
  },
];

async function clickLink(page: Page, url: string, rel: string | null): Promise<void> {
  await page.evaluate(
    ({ href, relValue }) => {
      const a = document.createElement("a");
      a.id = "e2e-link";
      a.href = href;
      a.target = "_blank";
      if (relValue !== null) a.rel = relValue;
      a.textContent = "open";
      document.body.append(a);
    },
    { href: url, relValue: rel },
  );
  await page.locator("#e2e-link").click();
}

for (const method of methods) {
  test(`second tab by ${method.name}: sessionStorage copy and offer unlock`, async ({
    context,
    server,
  }) => {
    await addProbe(context);
    const tabA = await context.newPage();
    await tabA.goto(linkFor(server.baseURL, server.code, ROUTE));
    await expectUnlocked(tabA);

    const popupPromise = context.waitForEvent("page");
    await method.open(tabA, `${server.baseURL}/#${ROUTE}`);
    const tabB = await popupPromise;
    await expectUnlocked(tabB);
    await tabB.waitForTimeout(600);
    const probe = await probeOf(tabB);
    const result = {
      method: method.name,
      sessionStorageCopied: probe.initialKey,
      keyAtMs: probe.keyAt,
      unlockedAtMs: probe.unlockedAt,
      lockedAtMs: probe.lockedAt,
      unlockedWithin400ms: probe.unlockedAt !== null && probe.unlockedAt < 400,
    };
    record(`second-tab-${method.name.replace(/\W+/g, "-")}`, result);
    test.info().annotations.push({ type: "spike1", description: JSON.stringify(result) });
    expect(probe.lockedAt).toBeNull();
    expect(probe.unlockedAt).not.toBeNull();
  });
}

test("a locked tab unlocks in place when a new link opens in another tab", async ({
  context,
  server,
}) => {
  await addProbe(context);
  const tabA = await context.newPage();
  await tabA.goto(`${server.baseURL}/#${ROUTE}`);
  await expectLocked(tabA, "no_key");
  await tabA.evaluate(() => {
    (window as unknown as { __marker: number }).__marker = 7;
  });

  const code = await server.mint("tidewater-reporting");
  const tabB = await context.newPage();
  await tabB.goto(linkFor(server.baseURL, code));
  await expectUnlocked(tabB);

  await expectUnlocked(tabA);
  expect(await tabA.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(7);
  expect(tabA.url()).toContain(`#${ROUTE}`);
  expect((await storage(tabA))[KEYS.readKey]).toBeTruthy();
  expect((await storage(tabA))[KEYS.route]).toBe(ROUTE);
  // B swapped by itself. The shell tells it that the other tab is open again.
  await expectOtherTabBack(tabB);
  record("unlock-in-place", {
    tabAUnlockedWithoutReload: true,
    routeKept: true,
    tabBShowsOtherTabBack: true,
  });
});

test("a restart sends an old tab to server_restarted, never back in from a stale key", async ({
  page,
  server,
}) => {
  await page.goto(linkFor(server.baseURL, server.code, ROUTE));
  await expectUnlocked(page);
  const oldKey = (await storage(page))[KEYS.readKey];

  await server.stop();
  const next = await startServer({ dataDir: server.dataDir, port: server.port });
  try {
    expect(next.instance).not.toBe(server.instance);
    expect(next.port).toBe(server.port);
    await page.reload();
    await expectLocked(page, "server_restarted");
    await expect(lockedHeading(page)).toBeVisible();
    const after = await storage(page);
    record("restart", {
      oldInstance: server.instance,
      newInstance: next.instance,
      reloadResult: "locked server_restarted",
      staleKeyStillInStorage: after[KEYS.readKey] === oldKey,
    });
  } finally {
    await next.stop();
  }
});

test("after a restart a tab on the old page shows that another tab is back", async ({
  context,
  server,
}) => {
  const tabX = await context.newPage();
  await tabX.goto(`${server.baseURL}/#${ROUTE}`);
  await expectLocked(tabX, "no_key");

  await server.stop();
  const next = await startServer({ dataDir: server.dataDir, port: server.port });
  try {
    const tabA = await context.newPage();
    await tabA.goto(`${next.baseURL}/#${ROUTE}`);
    await expectLocked(tabA, "no_key");
    await tabA.evaluate(() => {
      (window as unknown as { __marker: number }).__marker = 9;
    });

    const tabB = await context.newPage();
    await tabB.goto(linkFor(next.baseURL, await next.mint()));
    await expectUnlocked(tabB);

    await expectUnlocked(tabA);
    expect(await tabA.evaluate(() => (window as unknown as { __marker?: number }).__marker)).toBe(
      9,
    );
    // The old page keeps its old instance, so it ignores the offer and only hears "back".
    await expectLocked(tabX, "no_key");
    await expectOtherTabBack(tabX);
    record("restart-other-tab-back", {
      newTabUnlockedInPlace: true,
      oldInstanceTabIgnoredOffer: true,
      oldInstanceTabShowsOtherTabBack: true,
    });
  } finally {
    await next.stop();
  }
});
