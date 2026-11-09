/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The component sheet run (plan-a section 4, "Component sheet test"). Every rendered state at 375
 * and 1440, light and dark, goes through axe, a focus ring check and a target size check. Forced
 * colors and reduced motion run once each. Screenshots land in test-results/sheet and are review
 * material, not gates. Each cell reports on its own, so a failure names the component and state.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const outDir = resolve(import.meta.dirname, "..", "test-results", "sheet");
const sheetUrl = (): string => {
  const url = process.env.BARTAB_E2E_SHEET_URL;
  if (url === undefined) throw new Error("BARTAB_E2E_SHEET_URL is not set");
  return url;
};

interface Cell {
  component: string;
  state: string;
}

type Finding = Record<string, unknown>;

type AxePage = ConstructorParameters<typeof AxeBuilder>[0]["page"];

/** @axe-core/playwright ships its own copy of the Playwright types, so the page needs a cast. */
function newAxe(page: Page): AxeBuilder {
  return new AxeBuilder({ page: page as unknown as AxePage });
}

async function openSheet(page: Page, theme: "light" | "dark"): Promise<Cell[]> {
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(sheetUrl());
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForSelector("[data-component]");
  return page.$$eval("[data-component]", (nodes) =>
    nodes.map((n) => ({
      component: n.getAttribute("data-component") ?? "",
      state: n.getAttribute("data-state") ?? "",
    })),
  );
}

const cellSelector = (c: Cell): string =>
  `[data-component="${c.component}"][data-state="${c.state}"]`;

async function axeCell(page: Page, cell: Cell): Promise<Finding[]> {
  const result = await newAxe(page).withTags(TAGS).include(cellSelector(cell)).analyze();
  return result.violations.map((v) => ({
    kind: "axe",
    cell: `${cell.component}/${cell.state}`,
    rule: v.id,
    impact: v.impact,
    nodes: v.nodes.map((n) => n.target.join(" ")),
  }));
}

/** Focus ring and target size for the focusable parts of one cell. */
async function measureCell(page: Page, cell: Cell): Promise<Finding[]> {
  return page.evaluate(
    async ({ selector, label }) => {
      const found: Finding[] = [];
      const root = document.querySelector(selector);
      if (root === null) return found;
      const probe = document.createElement("div");
      probe.style.width = "var(--focus-width)";
      probe.style.position = "absolute";
      document.body.append(probe);
      const focusWidth = parseFloat(getComputedStyle(probe).width);
      probe.remove();
      const items = root.querySelectorAll<HTMLElement>(
        'a[href], button, input, select, textarea, [role="button"], [role="option"], [tabindex]:not([tabindex="-1"])',
      );
      for (const el of items) {
        // React Aria's hidden native select is clipped to 1 px and is not a target.
        if (el.closest('[aria-hidden="true"]') !== null) continue;
        const disabled = el.matches(":disabled") || el.getAttribute("aria-disabled") === "true";
        const rect = el.getBoundingClientRect();
        const name = `${el.tagName.toLowerCase()}.${el.className.toString().split(" ")[0] ?? ""}`;
        if (rect.width === 0 || rect.height === 0) continue;
        const inTabBar = el.closest(".tab-bar") !== null;
        const isButton = el.tagName === "BUTTON" || el.getAttribute("role") === "button";
        const inline =
          el.tagName === "A" && el.closest("p, li") !== null && el.closest("nav") === null;
        const min = inTabBar ? 52 : isButton ? 32 : 24;
        if (!inline && (rect.width < min || rect.height < min)) {
          found.push({
            kind: "target-size",
            cell: label,
            el: name,
            width: Math.round(rect.width * 10) / 10,
            height: Math.round(rect.height * 10) / 10,
            min,
          });
        }
        if (disabled) continue;
        el.focus({ focusVisible: true });
        if (document.activeElement !== el) continue;
        // React Aria sets its focus attributes after a state update, so give it a moment.
        await new Promise((done) => setTimeout(done, 25));
        const style = getComputedStyle(el);
        const width = parseFloat(style.outlineWidth);
        const visible = el.matches(":focus-visible");
        const drawn = style.outlineStyle !== "none" && width > 0;
        // A chosen option draws its focus edge as a 2 px inset shadow, by design (Select.css).
        const insetEdge = style.boxShadow.includes("inset") && style.boxShadow.includes("2px");
        if (visible && !insetEdge && (!drawn || Math.abs(width - focusWidth) > 0.01)) {
          found.push({
            kind: "focus-ring",
            cell: label,
            el: name,
            outlineWidth: style.outlineWidth,
            outlineStyle: style.outlineStyle,
            boxShadow: style.boxShadow === "none" ? null : "set",
            expected: focusWidth,
          });
        }
        if (!visible) found.push({ kind: "focus-visible-false", cell: label, el: name });
        el.blur();
      }
      return found;
    },
    { selector: cellSelector(cell), label: `${cell.component}/${cell.state}` },
  );
}

function summarise(findings: Finding[]): string[] {
  return findings.map((f) => JSON.stringify(f));
}

function save(name: string, data: unknown): void {
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, `${name}.json`), JSON.stringify(data, null, 2));
}

const widths = [375, 1440] as const;
const themes = ["light", "dark"] as const;

for (const width of widths) {
  for (const theme of themes) {
    test(`sheet at ${String(width)} ${theme}: axe, focus ring and target size`, async ({
      page,
    }) => {
      // The per-cell loop (axe, Tab, measure, screenshot) runs past 60 s on the 2-vCPU Linux
      // runner, as the hover tests below do, so it gets the same longer limit.
      test.setTimeout(240_000);
      await page.setViewportSize({ width, height: 900 });
      const cells = await openSheet(page, theme);
      expect(cells.length).toBeGreaterThan(40);
      const shots = join(outDir, `${String(width)}-${theme}`);
      mkdirSync(shots, { recursive: true });

      const axe: Finding[] = [];
      const measured: Finding[] = [];
      for (const cell of cells) {
        axe.push(...(await axeCell(page, cell)));
        // A key press first, so React Aria's focus tracking is in keyboard mode and sets its
        // data-focus-visible attribute when the check moves focus by script.
        await page.keyboard.press("Tab");
        measured.push(...(await measureCell(page, cell)));
        await page
          .locator(cellSelector(cell))
          .screenshot({ path: join(shots, `${cell.component}-${cell.state}.png`) });
      }
      const wholePage = await newAxe(page).withTags(TAGS).analyze();
      const pageLevel = wholePage.violations.map((v) => ({
        kind: "axe-page",
        rule: v.id,
        impact: v.impact,
        nodes: v.nodes.map((n) => n.target.join(" ")),
      }));
      await page.screenshot({
        path: join(outDir, `page-${String(width)}-${theme}.png`),
        fullPage: true,
      });
      save(`findings-${String(width)}-${theme}`, { axe, pageLevel, measured });
      expect.soft(summarise(axe), "axe violations per cell").toEqual([]);
      expect.soft(summarise(pageLevel), "axe violations on the whole page").toEqual([]);
      expect.soft(summarise(measured), "focus ring and target size").toEqual([]);
    });
  }
}

test("sheet under forced colors keeps passing axe", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ forcedColors: "active" });
  const cells = await openSheet(page, "light");
  await page.emulateMedia({ forcedColors: "active" });
  const found: Finding[] = [];
  for (const cell of cells) found.push(...(await axeCell(page, cell)));
  await page.screenshot({ path: join(outDir, "page-forced-colors.png"), fullPage: true });
  save("findings-forced-colors", found);
  expect.soft(summarise(found)).toEqual([]);
});

test("sheet under reduced motion keeps passing axe", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const cells = await openSheet(page, "light");
  await page.emulateMedia({ reducedMotion: "reduce" });
  const found: Finding[] = [];
  for (const cell of cells) found.push(...(await axeCell(page, cell)));
  save("findings-reduced-motion", found);
  expect.soft(summarise(found)).toEqual([]);
});

for (const width of widths) {
  test(`hover does not move anything at ${String(width)}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width, height: 900 });
    const cells = await openSheet(page, "light");
    const interactive = [
      "a[href]",
      "button:not([disabled])",
      "input",
      "select",
      "textarea",
      '[role="option"]',
      '[role="button"]',
    ];
    const snapshot = (selector: string) =>
      page.evaluate((sel) => {
        // The cell's own elements, plus every cell box on the sheet as the neighbours.
        const rects: Record<string, string> = {};
        const put = (key: string, el: Element) => {
          const r = el.getBoundingClientRect();
          // React Aria's hidden select is fixed and clipped, so scrolling moves it. Zero boxes too.
          if (el.closest("[data-testid='hidden-select-container']") !== null) return;
          if (r.width === 0 && r.height === 0) return;
          rects[key] =
            `${el.tagName.toLowerCase()}.${String(el.getAttribute("class") ?? "").split(" ")[0] ?? ""} ` +
            [r.x + window.scrollX, r.y + window.scrollY, r.width, r.height]
              .map((n) => n.toFixed(1))
              .join(",");
        };
        document
          .querySelector(sel)
          ?.querySelectorAll("*")
          .forEach((el, i) => {
            put(`in${String(i)}`, el);
          });
        document.querySelectorAll(".sheet-cell").forEach((el, i) => {
          put(`cell${String(i)}`, el);
        });
        return rects;
      }, selector);
    const moved: Finding[] = [];
    for (const cell of cells) {
      const sel = cellSelector(cell);
      const targets = page.locator(interactive.map((part) => `${sel} ${part}`).join(", "));
      const count = await targets.count();
      // Up to five elements per cell, spread from first to last, to keep the run short.
      const picks = new Set(
        Array.from({ length: Math.min(count, 5) }, (_, k) =>
          Math.round((k * (count - 1)) / Math.max(1, Math.min(count, 5) - 1)),
        ),
      );
      await page.mouse.move(0, 0);
      const before = await snapshot(sel);
      for (const i of picks) {
        const target = targets.nth(i);
        if (!(await target.isVisible())) continue;
        if ((await target.evaluate((el) => el.closest('[aria-hidden="true"]'))) !== null) continue;
        await target.scrollIntoViewIfNeeded();
        const box = await target.boundingBox();
        if (box === null) continue;
        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        const after = await snapshot(sel);
        const changed = Object.keys(before).filter((k) => before[k] !== after[k]);
        if (changed.length > 0) {
          moved.push({
            kind: "hover-shift",
            cell: `${cell.component}/${cell.state}`,
            target: i,
            elements: changed.length,
            sample: changed.slice(0, 3).map((k) => `${before[k] ?? ""} -> ${after[k] ?? ""}`),
          });
        }
      }
    }
    save(`findings-hover-${String(width)}`, moved);
    expect.soft(summarise(moved), "hover moves layout").toEqual([]);
  });
}
