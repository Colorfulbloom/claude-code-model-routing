/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The replay line's keys, proved in Chromium (m3-build.md section 2 "Replay control" and section 12,
 * task 1 results). No source says whether preventDefault on keydown stops a native range input's
 * own Page Up and Page Down step, so this runs it. Only Chromium is installed, so WebKit and
 * Firefox are not covered here. The M9 pass in Safari covers WebKit.
 *
 * The control test shows the browser's own Page step on a bare input, so the override test is not
 * passing by luck (a native step of 5 would look the same as the override).
 */
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const sheetUrl = (): string => {
  const url = process.env.BARTAB_E2E_SHEET_URL;
  if (url === undefined) throw new Error("BARTAB_E2E_SHEET_URL is not set");
  return url;
};

const cell = (state: string): string => `[data-component="ReplayLine"][data-state="${state}"]`;

async function openLine(page: Page, state: string) {
  await page.goto(sheetUrl());
  await page.waitForSelector(cell(state));
  const input = page.locator(`${cell(state)} input[type="range"]`);
  await input.focus();
  return input;
}

test("a bare native range input steps by more than the page step on Page Up (control)", async ({
  page,
}) => {
  await page.setContent('<input type="range" min="0" max="60" step="1" value="25" id="r">');
  await page.locator("#r").focus();
  await page.keyboard.press("PageUp");
  const native = Number(await page.locator("#r").inputValue());
  test
    .info()
    .annotations.push({ type: "native Page Up from 25 of 60", description: String(native) });
  // Chromium steps a tenth of the range, so the override has something to stop.
  expect(native).not.toBe(30);
  expect(native).toBeGreaterThan(25);
});

test("preventDefault on keydown stops the native Page step, so the handler's step is the only one", async ({
  page,
}) => {
  const input = await openLine(page, "default");
  await expect(input).toHaveValue("25");
  await page.keyboard.press("PageUp");
  await expect(input).toHaveValue("30");
  await page.keyboard.press("PageUp");
  await expect(input).toHaveValue("35");
  await page.keyboard.press("PageDown");
  await expect(input).toHaveValue("30");
  await page.keyboard.press("PageDown");
  await page.keyboard.press("PageDown");
  await expect(input).toHaveValue("20");
});

test("arrow keys move one minute, Home and End go to the start and the end", async ({ page }) => {
  const input = await openLine(page, "default");
  await page.keyboard.press("ArrowRight");
  await expect(input).toHaveValue("26");
  await page.keyboard.press("ArrowUp");
  await expect(input).toHaveValue("27");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowLeft");
  await page.keyboard.press("ArrowDown");
  await expect(input).toHaveValue("24");
  await page.keyboard.press("Home");
  await expect(input).toHaveValue("0");
  await page.keyboard.press("End");
  await expect(input).toHaveValue("60");
});

test("the page keys stop at the start and the end", async ({ page }) => {
  const input = await openLine(page, "at-end");
  await page.keyboard.press("PageUp");
  await expect(input).toHaveValue("60");
  await page.keyboard.press("Home");
  await page.keyboard.press("PageDown");
  await expect(input).toHaveValue("0");
});

test("a long session takes the larger page step", async ({ page }) => {
  const input = await openLine(page, "long");
  await expect(input).toHaveValue("163");
  await page.keyboard.press("PageUp");
  await expect(input).toHaveValue("173");
  await page.keyboard.press("PageDown");
  await page.keyboard.press("PageDown");
  await expect(input).toHaveValue("153");
});

test("the value text follows every key", async ({ page }) => {
  const input = await openLine(page, "default");
  await expect(input).toHaveAttribute("aria-valuetext", "2:25 PM");
  await page.keyboard.press("PageUp");
  await expect(input).toHaveAttribute("aria-valuetext", "2:30 PM");
  await page.keyboard.press("ArrowLeft");
  await expect(input).toHaveAttribute("aria-valuetext", "2:29 PM");
  await expect(page.getByRole("slider", { name: "Replay time" }).first()).toBeVisible();
});

test("a click on the rail moves the value, and the target is at least 24 px", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(sheetUrl());
  const input = page.locator(`${cell("default")} input[type="range"]`);
  await input.scrollIntoViewIfNeeded();
  const box = await input.boundingBox();
  if (box === null) throw new Error("no box");
  expect(box.height).toBeGreaterThanOrEqual(24);
  await page.mouse.click(box.x + box.width * 0.75, box.y + box.height / 2);
  const value = Number(await input.inputValue());
  expect(value).toBeGreaterThan(40);
  expect(value).toBeLessThan(50);
});

test("the focus ring is on the visible handle, not the hidden input", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openLine(page, "default");
  await page.keyboard.press("ArrowRight");
  const ring = await page.evaluate((selector) => {
    const handle = document.querySelector(`${selector} .replay-handle`);
    if (handle === null) return null;
    const style = getComputedStyle(handle);
    return { style: style.outlineStyle, width: style.outlineWidth };
  }, cell("default"));
  expect(ring).toEqual({ style: "solid", width: "2px" });
});
