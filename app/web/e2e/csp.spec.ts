/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The strict CSP, end to end. The real server's page carries the production policy with a
 * per-request nonce, the page loads with no violation, and React Aria's Select works under the
 * same policy (the sheet server applies the same header).
 */
import type { Page } from "@playwright/test";
import { expectUnlocked, linkFor } from "./gate";
import { expectedCsp } from "./policy";
import { expect, test } from "./server";

interface Violation {
  directive: string;
  blocked: string;
  sample: string;
  source: string;
}

async function watchViolations(page: Page) {
  const violations: Violation[] = [];
  const consoleErrors: string[] = [];
  await page.exposeFunction("__bartabViolation", (v: Violation) => {
    violations.push(v);
  });
  await page.addInitScript(() => {
    document.addEventListener("securitypolicyviolation", (e) => {
      const call = (window as unknown as Record<string, (v: unknown) => void>).__bartabViolation;
      call?.({
        directive: e.effectiveDirective,
        blocked: e.blockedURI,
        sample: e.sample,
        source: `${e.sourceFile}:${String(e.lineNumber)}`,
      });
    });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error" || /content security policy/i.test(msg.text())) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(err.message);
  });
  return { violations, consoleErrors };
}

function nonceOf(header: string): string {
  const found = /script-src 'self' 'nonce-([^']+)'/.exec(header);
  if (found?.[1] === undefined) throw new Error(`no nonce in ${header}`);
  return found[1];
}

test("index.html carries the exact production CSP and a nonce on every script and link", async ({
  server,
}) => {
  const first = await fetch(`${server.baseURL}/`);
  const csp = first.headers.get("content-security-policy");
  expect(csp).not.toBeNull();
  const nonce = nonceOf(csp ?? "");
  expect(csp).toBe(expectedCsp(nonce));
  expect(first.headers.get("x-content-type-options")).toBe("nosniff");
  expect(first.headers.get("referrer-policy")).toBe("no-referrer");
  expect(first.headers.get("cache-control")).toBe("no-store");

  const html = await first.text();
  expect(html).toContain(`<meta name="csp-nonce" content="${nonce}">`);
  expect(html).toContain(`<meta name="bartab-instance" content="${server.instance}">`);
  const tags = html.match(/<(?:script|link)\b[^>]*>/gi) ?? [];
  expect(tags.length).toBeGreaterThan(0);
  for (const tag of tags) expect(tag).toContain(`nonce="${nonce}"`);

  const second = await fetch(`${server.baseURL}/`);
  const secondNonce = nonceOf(second.headers.get("content-security-policy") ?? "");
  expect(secondNonce).not.toBe(nonce);
  expect(await second.text()).toContain(`content="${secondNonce}"`);
});

test("the app loads and unlocks with zero CSP violations", async ({ page, server }) => {
  const seen = await watchViolations(page);
  await page.goto(linkFor(server.baseURL, server.code));
  await expectUnlocked(page);
  await page.waitForLoadState("networkidle");
  expect(seen.violations).toEqual([]);
  expect(seen.consoleErrors).toEqual([]);
});

test("React Aria's Select opens and picks an option under the CSP", async ({ page }) => {
  const sheetUrl = process.env.BARTAB_E2E_SHEET_URL;
  if (sheetUrl === undefined) throw new Error("BARTAB_E2E_SHEET_URL is not set");
  const seen = await watchViolations(page);
  const response = await page.goto(sheetUrl);
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toBe(expectedCsp(nonceOf(csp)));

  const cell = page.locator('[data-component="Select"][data-state="default"]');
  await cell.getByRole("button").click();
  const popover = page.getByRole("dialog");
  const listbox = popover.getByRole("listbox");
  await expect(listbox).toBeVisible();
  await listbox.getByRole("option").first().click();
  await expect(listbox).toHaveCount(0);
  await cell.getByRole("button").press("Enter");
  await expect(listbox).toBeVisible();
  await page.keyboard.press("Escape");

  // Report each violation by directive so a touch-action style case is easy to spot.
  expect(seen.violations.map((v) => `${v.directive} ${v.blocked} ${v.sample}`)).toEqual([]);
  expect(seen.consoleErrors).toEqual([]);
});
