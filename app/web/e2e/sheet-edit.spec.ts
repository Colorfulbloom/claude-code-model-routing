/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The narrow sheet run for the M6a edit components (task a9). The general sheet spec (sheet.spec.ts)
 * already scans every cell for axe, focus ring and target size, so this file adds only what it does
 * not check, for the eleven edit components:
 *   - every status shows a glyph and a word, never a hue alone;
 *   - nothing draws wider than its cell, at 375 and 1440, light and dark (no sideways scroll);
 *   - the disabled Edit label and its reason line keep AA text contrast in both themes (axe skips
 *     an aria-disabled control, so the ratio is computed here);
 *   - the width of the Save button holds while it reads "Saving".
 * Screenshots land in test-results/sheet-edit as review material, not gates.
 */
import { mkdirSync } from "node:fs";
import { join, resolve } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";
import { glyphWidth, readAll } from "./contrast";

const COMPONENTS = [
  "Diff",
  "SaveToList",
  "ThisSave",
  "EditRail",
  "SavedBox",
  "RefusedMessage",
  "OverwrittenBox",
  "UndoConfirm",
  "EditsOffNote",
  "RestartBox",
  "PhoneActionBar",
] as const;

const outDir = resolve(import.meta.dirname, "..", "test-results", "sheet-edit");
const sheetUrl = (): string => {
  const url = process.env.BARTAB_E2E_SHEET_URL;
  if (url === undefined) throw new Error("BARTAB_E2E_SHEET_URL is not set");
  return url;
};

async function openSheet(page: Page, theme: "light" | "dark"): Promise<void> {
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(sheetUrl());
  await page.evaluate((t) => {
    document.documentElement.dataset.theme = t;
  }, theme);
  await page.waitForSelector('[data-component="EditRail"]');
}

// The edit components, and the choice states of Segmented.
const mine = [
  ...COMPONENTS.map((name) => `[data-component="${name}"]`),
  '[data-component="Segmented"][data-state^="choice"]',
].join(", ");

const widths = [375, 1440] as const;
const themes = ["light", "dark"] as const;

for (const width of widths) {
  for (const theme of themes) {
    test(`edit components at ${String(width)} ${theme}: glyph and word, no overflow, screenshots`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await openSheet(page, theme);
      const shots = join(outDir, `${String(width)}-${theme}`);
      mkdirSync(shots, { recursive: true });

      const problems = await page.evaluate((selector) => {
        const found: string[] = [];
        for (const cell of document.querySelectorAll<HTMLElement>(selector)) {
          const label = `${cell.dataset.component ?? ""}/${cell.dataset.state ?? ""}`;
          const box = cell.getBoundingClientRect();
          // Every status chip and glyph span names itself in words.
          for (const el of cell.querySelectorAll<HTMLElement>(".status-chip, .glyph[data-glyph]")) {
            if (
              (el.textContent ?? "").trim() === "" &&
              el.closest("li, .this-save-notes") === null
            ) {
              found.push(`${label}: a status glyph has no word`);
            }
          }
          for (const li of cell.querySelectorAll<HTMLElement>(".this-save-notes li")) {
            if ((li.textContent ?? "").trim() === "") found.push(`${label}: a note has no words`);
          }
          // Every message mark sits in a line that carries words.
          for (const mark of cell.querySelectorAll<HTMLElement>(".message-mark")) {
            const words = (mark.parentElement?.textContent ?? "").trim();
            if (words === "") found.push(`${label}: a message mark has no words`);
            if (mark.getAttribute("aria-hidden") !== "true") {
              found.push(`${label}: a message mark is not aria-hidden`);
            }
          }
          // Nothing draws past the right edge of its cell. Visually hidden text is exempt.
          for (const el of cell.querySelectorAll<HTMLElement>("*")) {
            if (el.closest(".sr-only") !== null) continue;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            if (r.right > box.right + 1 || r.left < box.left - 1) {
              found.push(
                `${label}: ${el.tagName.toLowerCase()}.${el.className.toString().split(" ")[0] ?? ""} spills ${String(Math.round(r.right - box.right))}px`,
              );
              break;
            }
          }
        }
        // The sheet page itself already scrolls sideways at 375 (the tab bar and top bar cells), so
        // only the edit cells are held to the window.
        for (const cell of document.querySelectorAll<HTMLElement>(selector)) {
          if (cell.getBoundingClientRect().right > window.innerWidth + 1) {
            found.push(
              `${cell.dataset.component ?? ""}/${cell.dataset.state ?? ""}: the cell runs past the window`,
            );
          }
        }
        return found;
      }, mine);
      expect(problems, "glyph and word, overflow").toEqual([]);

      const cells = await page.$$eval(mine, (nodes) =>
        nodes.map(
          (n) => `${n.getAttribute("data-component") ?? ""}-${n.getAttribute("data-state") ?? ""}`,
        ),
      );
      expect(cells.length).toBeGreaterThan(50);
      for (const name of cells) {
        const [component, ...rest] = name.split("-");
        const state = rest.join("-");
        await page
          .locator(`[data-component="${component ?? ""}"][data-state="${state}"]`)
          .screenshot({ path: join(shots, `${name}.png`) });
      }
    });

    test(`disabled Edit and its reason keep AA contrast at ${String(width)} ${theme}`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 });
      await openSheet(page, theme);
      const ratios = await page.evaluate(() => {
        type Rgba = [number, number, number, number];
        const parse = (value: string): Rgba => {
          const found = /rgba?\(([^)]+)\)/.exec(value);
          if (found?.[1] === undefined) throw new Error(`Unreadable colour ${value}`);
          const [r = 0, g = 0, b = 0, a = 1] = found[1]
            .split(/[ ,/]+/)
            .filter(Boolean)
            .map(Number);
          return [r, g, b, a];
        };
        const over = (top: Rgba, base: Rgba): Rgba => {
          const a = top[3] + base[3] * (1 - top[3]);
          const mix = (i: 0 | 1 | 2): number =>
            a === 0 ? 0 : (top[i] * top[3] + base[i] * base[3] * (1 - top[3])) / a;
          return [mix(0), mix(1), mix(2), a];
        };
        const backdrop = (el: Element): Rgba => {
          let color: Rgba = [255, 255, 255, 0];
          for (let node: Element | null = el; node !== null; node = node.parentElement) {
            color = over(color, parse(getComputedStyle(node).backgroundColor));
            if (color[3] >= 1) break;
          }
          return color[3] >= 1
            ? color
            : over(color, parse(getComputedStyle(document.body).backgroundColor));
        };
        const lum = ([r, g, b]: Rgba): number => {
          const lin = (v: number): number => {
            const s = v / 255;
            return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
          };
          return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
        };
        const ratio = (el: Element): number => {
          const fg = over(parse(getComputedStyle(el).color), backdrop(el));
          const bg = backdrop(el);
          const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a) as [number, number];
          return (hi + 0.05) / (lo + 0.05);
        };
        const out: Record<string, number> = {};
        const cell = document.querySelector('[data-component="EditsOffNote"][data-state="reason"]');
        const button = cell?.querySelector('button[aria-disabled="true"]');
        const reason = cell?.querySelector(".edits-off-reason");
        if (button) out["Edit label"] = ratio(button);
        if (reason) out["reason line"] = ratio(reason);
        const route = document.querySelector(
          '[data-component="EditsOffNote"][data-state="history"] .edits-off-note',
        );
        if (route) out["history note"] = ratio(route);
        return out;
      });
      expect(Object.keys(ratios).sort()).toEqual(["Edit label", "history note", "reason line"]);
      for (const [name, ratio] of Object.entries(ratios)) {
        expect(ratio, `${name} contrast`).toBeGreaterThanOrEqual(4.5);
      }
    });
  }
}

// Round a15 (D11). Computed values, because axe skips a CSS-drawn glyph and a dimmed row.
for (const theme of themes) {
  test(`the Checking ring is as big as the check and reaches 3:1, and a dimmed row reads AA in ${theme}`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openSheet(page, theme);
    const read = await readAll(page, {
      ring: '[data-component="SavedBox"][data-state="checking"] .saved-box-ring',
      check: '[data-component="SavedBox"][data-state="confirmed"] .saved-box-ok',
      blockedName:
        '[data-component="SaveToList"][data-state="not-writable"] [data-disabled] .save-to-scope-name',
      blockedMeaning:
        '[data-component="SaveToList"][data-state="not-writable"] [data-disabled] .save-to-scope-meaning',
      blockedPath:
        '[data-component="SaveToList"][data-state="not-writable"] [data-disabled] .save-to-path',
      blockedLock:
        '[data-component="SaveToList"][data-state="not-writable"] [data-disabled] .save-to-blocked',
    });
    const ring = read.ring;
    const check = read.check;
    expect(ring, "the ring").not.toBeNull();
    expect(check, "the check").not.toBeNull();
    // The ring matches the check glyph's size: same font size, and a box as wide as the glyph.
    expect(ring?.fontSize).toBe(check?.fontSize);
    const glyph = await glyphWidth(
      page,
      '[data-component="SavedBox"][data-state="confirmed"] .saved-box-ok',
    );
    expect(glyph).not.toBeNull();
    expect(Math.abs((ring?.width ?? 0) - (glyph ?? 0))).toBeLessThanOrEqual(4);
    expect(Math.abs((ring?.height ?? 0) - (ring?.width ?? 1))).toBeLessThan(1);
    // A hollow circle is non-text, so it needs 3:1 against what it sits on.
    expect(ring?.ratio, "ring contrast").toBeGreaterThanOrEqual(3);
    // The dimmed row that can't be picked keeps AA on all its text.
    for (const name of ["blockedName", "blockedMeaning", "blockedPath", "blockedLock"] as const) {
      const reading = read[name];
      expect(reading, name).not.toBeNull();
      expect(reading?.ratio, `${name} contrast`).toBeGreaterThanOrEqual(4.5);
    }
  });
}

test("Save keeps its width while it reads Saving", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openSheet(page, "light");
  const idle = page.locator('[data-component="EditRail"][data-state="default"] .edit-save');
  const busy = page.locator('[data-component="EditRail"][data-state="saving"] .edit-save');
  const a = await idle.boundingBox();
  const b = await busy.boundingBox();
  expect(a).not.toBeNull();
  expect(b).not.toBeNull();
  expect(Math.abs((a?.width ?? 0) - (b?.width ?? 1))).toBeLessThan(1);
  await expect(busy).toHaveAttribute("aria-busy", "true");
});

test("the sheet draws the phone rail as a dialog with a sticky action bar", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 900 });
  await openSheet(page, "light");
  const cell = page.locator('[data-component="EditRail"][data-state="sheet"]');
  await expect(cell.getByRole("dialog", { name: /Edit effort/ })).toBeVisible();
  await expect(cell.locator(".phone-action-bar")).toBeVisible();
  const bar = await cell.locator(".phone-action-bar button").boundingBox();
  const frame = await cell.locator(".sheet-phone").boundingBox();
  expect(bar?.width ?? 0).toBeGreaterThan((frame?.width ?? 0) - 48);
});
