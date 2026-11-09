/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Every route of the shell, for the demo project, at 320, 375 and 1440 wide, light and dark.
 * Each route checks axe, the title, focus on the h1 after client-side navigation, the polite
 * status, horizontal scroll, the content width cap and the tab bar. Findings carry a label with
 * the route, so one failure names the route. Navigation uses nav links wherever one exists.
 */
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { en } from "../src/strings/en";
import { expectUnlocked, fill, linkFor } from "./gate";
import { expect, readOnlyTest as test } from "./server";

const PROJECT = "tidewater-reporting";
const PROJECT_NAME = "Tidewater Reporting";
const TO_FIX = 4;
const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];

type Tab = "live" | "review" | "setup" | "tofix" | "more";

interface RouteCase {
  path: string;
  /** The page name, which is the h1, the title head and the status line. */
  name: string;
  hasProject: boolean;
  /** The current link in the tab bar (phone) and the sidebar (desktop). */
  tab: Tab;
  side: string;
  hidesTabBar?: boolean;
}

const base = `/p/${PROJECT}`;
const routes: RouteCase[] = [
  { path: `${base}/live`, name: en.nav_live, hasProject: true, tab: "live", side: en.nav_live },
  {
    path: `${base}/review/summary`,
    name: en.nav_summary,
    hasProject: true,
    tab: "review",
    side: en.nav_summary,
  },
  {
    path: `${base}/review/sessions`,
    name: en.nav_sessions,
    hasProject: true,
    tab: "review",
    side: en.nav_sessions,
  },
  {
    path: `${base}/review/sessions/s-1`,
    name: en.pg_session,
    hasProject: true,
    tab: "review",
    side: en.nav_sessions,
  },
  {
    path: `${base}/review/agents`,
    name: en.nav_agents,
    hasProject: true,
    tab: "review",
    side: en.nav_agents,
  },
  {
    path: `${base}/review/agents/new`,
    name: en.pg_agent_new,
    hasProject: true,
    tab: "review",
    side: en.nav_agents,
    hidesTabBar: true,
  },
  {
    path: `${base}/review/agents/scout/edit`,
    name: en.pg_agent_edit,
    hasProject: true,
    tab: "review",
    side: en.nav_agents,
    hidesTabBar: true,
  },
  {
    path: `${base}/review/models`,
    name: en.nav_models,
    hasProject: true,
    tab: "review",
    side: en.nav_models,
  },
  {
    path: `${base}/setup`,
    name: en.nav_setup,
    hasProject: true,
    tab: "setup",
    side: en.nav_setup,
  },
  {
    path: `${base}/setup/agents/scout`,
    name: en.pg_surface,
    hasProject: true,
    tab: "setup",
    side: en.nav_setup,
  },
  {
    path: `${base}/setup/agents/scout/edit`,
    name: en.pg_surface_edit,
    hasProject: true,
    tab: "setup",
    side: en.nav_setup,
  },
  {
    path: `${base}/to-fix`,
    name: en.nav_tofix,
    hasProject: true,
    tab: "tofix",
    side: en.nav_tofix,
  },
  {
    path: "/reference/decides",
    name: en.nav_decides,
    hasProject: false,
    tab: "more",
    side: en.nav_decides,
  },
  {
    path: "/reference/glossary",
    name: en.nav_glossary,
    hasProject: false,
    tab: "more",
    side: en.nav_glossary,
  },
  { path: "/more", name: en.more_h1, hasProject: false, tab: "more", side: "" },
];

const tabLabel: Record<Tab, string> = {
  live: en.nav_live,
  review: en.nav_review,
  setup: en.nav_setup_h,
  tofix: en.nav_tofix,
  more: en.nav_more,
};

const toFixName = fill(en.tofix_aria_other, { n: TO_FIX });

function titleFor(route: RouteCase): string {
  return route.hasProject
    ? fill(en.title_project, { page: route.name, project: PROJECT_NAME })
    : fill(en.title_bare, { page: route.name });
}

async function open(
  page: Page,
  server: { baseURL: string; mint: (project: string) => Promise<string> },
) {
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await expect(page).toHaveURL(new RegExp(`#${base}/live$`));
}

/** Moves to a route the way a person would. Nav link when one exists, else a hash change. */
async function visit(page: Page, path: string, phone: boolean): Promise<void> {
  const link = page.locator(`a[href="#${path}"]:visible`).first();
  if ((await link.count()) > 0) {
    await link.click();
    return;
  }
  if (phone && path.startsWith("/reference")) {
    await visit(page, "/more", phone);
    await page.locator(`a[href="#${path}"]:visible`).first().click();
    return;
  }
  await page.evaluate((p) => {
    window.location.hash = p;
  }, path);
}

async function checkRoute(
  page: Page,
  route: RouteCase,
  width: number,
  phone: boolean,
): Promise<string[]> {
  const problems: string[] = [];
  const bad = (what: string): number => problems.push(`${route.path} ${what}`);
  await visit(page, route.path, phone);
  try {
    await expect(page.locator("main h1").first()).toHaveText(route.name);
  } catch {
    bad(`h1 is not "${route.name}"`);
    return problems;
  }
  try {
    await expect(page).toHaveTitle(titleFor(route));
  } catch {
    bad(`title is "${await page.title()}", wanted "${titleFor(route)}"`);
  }
  const focus = await page.evaluate(() => ({
    tag: document.activeElement?.tagName ?? "",
    text: document.activeElement?.textContent ?? "",
  }));
  if (focus.tag !== "H1" || focus.text !== route.name) {
    bad(`focus is on ${focus.tag} "${focus.text}", wanted the h1`);
  }
  const statuses = await page.locator('[role="status"]').allTextContents();
  if (!statuses.includes(route.name))
    bad(`no polite status "${route.name}", got ${JSON.stringify(statuses)}`);

  const hidden = phone && route.hidesTabBar === true;
  if (!hidden && (phone || route.path !== "/more")) {
    const current = await page
      .locator('nav[aria-label="Main"] [aria-current="page"]')
      .evaluateAll((els) =>
        els.map((el) => el.getAttribute("aria-label") ?? (el.textContent ?? "").trim()),
      );
    const wanted = route.tab === "tofix" ? toFixName : phone ? tabLabel[route.tab] : route.side;
    if (current.length !== 1 || !(current[0] ?? "").startsWith(wanted)) {
      bad(`current nav is ${JSON.stringify(current)}, wanted "${wanted}"`);
    }
  }
  const toFix = await page.getByRole("link", { name: toFixName }).count();
  const tabBarShown = await page.locator(".tab-bar").count();
  if (phone ? route.hidesTabBar !== true && toFix === 0 : false)
    bad(`no link named "${toFixName}"`);
  if (!phone && toFix === 0) bad(`no link named "${toFixName}"`);
  if (phone && route.hidesTabBar === true && tabBarShown > 0) bad("tab bar shows on a form route");

  const overflow = await page.evaluate(() => ({
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth,
  }));
  if (width <= 375 && overflow.sw > overflow.cw)
    bad(`scrolls sideways, ${overflow.sw} > ${overflow.cw}`);
  if (width >= 1440) {
    const box = await page.locator(".shell-content").boundingBox();
    if (box === null || box.width > 1280.5) bad(`content is ${box?.width ?? "missing"} wide`);
  }
  if (phone && route.hidesTabBar !== true) {
    const gap = await page.evaluate(() => {
      window.scrollTo(0, document.documentElement.scrollHeight);
      const main = document.querySelector("main");
      const bar = document.querySelector(".tab-bar");
      if (main === null || bar === null) return null;
      let bottom = 0;
      for (const el of main.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (r.width > 0 && r.height > 0) bottom = Math.max(bottom, r.bottom);
      }
      return bar.getBoundingClientRect().top - bottom;
    });
    if (gap === null || gap < -0.5) bad(`tab bar covers the last element by ${-(gap ?? 0)}px`);
    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
  }
  const axe = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  for (const v of axe.violations) {
    bad(`axe ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`);
  }
  return problems;
}

for (const width of [320, 375, 1440]) {
  for (const theme of ["light", "dark"] as const) {
    test(`routes at ${String(width)} ${theme}`, async ({ page, shared }) => {
      test.setTimeout(120_000);
      await page.setViewportSize({ width, height: 800 });
      await page.emulateMedia({ colorScheme: theme });
      await open(page, shared);
      await page.evaluate((t) => {
        document.documentElement.dataset.theme = t;
      }, theme);
      const phone = width <= 720;
      // One hop away first, so Live is also reached by navigation.
      await visit(page, `${base}/review/summary`, phone);
      const problems: string[] = [];
      for (const route of routes) {
        if (route.path === "/more" && !phone) continue;
        problems.push(...(await checkRoute(page, route, width, phone)));
      }
      expect.soft(problems).toEqual([]);
    });
  }
}

test("more at 1440 goes to Live", async ({ page, shared }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, shared);
  await page.evaluate(() => {
    window.location.hash = "/more";
  });
  await expect(page).toHaveURL(new RegExp(`#${base}/live$`));
});

// Owner decision pending: "How Claude Code decides" needs about 14px more than the 224px sidebar
// gives, and the a-live-1440 boards wrap it too. Un-fixme once a width, spacing or label is picked.
test.fixme("every sidebar label is one line at 1440", async ({ page, shared }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, shared);
  const rows = await page.locator(".sidebar-link").evaluateAll((links) =>
    links.map((link) => {
      const label = link.querySelector(".sidebar-label");
      const style = label === null ? null : getComputedStyle(label);
      return {
        text: label?.textContent ?? "",
        lines:
          label === null
            ? 0
            : Math.round(
                label.getBoundingClientRect().height / parseFloat(style?.lineHeight ?? "1"),
              ),
        link: Math.round(link.getBoundingClientRect().height),
      };
    }),
  );
  expect(rows.length).toBeGreaterThan(0);
  expect(rows.filter((row) => row.lines !== 1 || row.link !== 36)).toEqual([]);
  expect(rows.map((row) => row.text)).toContain(en.nav_decides);
});

test("the sidebar Select swaps the project and keeps the page", async ({ page, shared }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await open(page, shared);
  await page.evaluate((p) => {
    window.location.hash = `${p}/review/agents`;
  }, base);
  await expect(page.locator("main h1")).toHaveText(en.nav_agents);
  await page.getByRole("button", { name: new RegExp(en.project_label) }).click();
  await page
    .getByRole("dialog")
    .getByRole("option", { name: /Saltmarsh/ })
    .click();
  await expect(page).toHaveURL(/#\/p\/saltmarsh\/review\/agents$/);
  await expect(page.locator("main h1")).toHaveText(en.nav_agents);
});

test("the 375 tray swaps the project and keeps the page", async ({ page, shared }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await open(page, shared);
  await page.evaluate((p) => {
    window.location.hash = `${p}/review/models`;
  }, base);
  await expect(page.locator("main h1")).toHaveText(en.nav_models);
  await page.getByRole("button", { name: fill(en.project_aria, { name: PROJECT_NAME }) }).click();
  await page
    .getByRole("dialog")
    .getByRole("option", { name: /Saltmarsh/ })
    .click();
  await expect(page).toHaveURL(/#\/p\/saltmarsh\/review\/models$/);
  await expect(page.locator("main h1")).toHaveText(en.nav_models);
  // The URL changed, so the route harness moves focus to the new page's h1.
  await expect(page.locator("main h1")).toBeFocused();
});
