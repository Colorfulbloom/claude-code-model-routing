/// <reference lib="dom" />
/*
 * Computed contrast and glyph size for the specs that check what axe skips (an aria-disabled
 * control, a dimmed row, a CSS-drawn glyph). The ratio is WCAG's, from the element's text colour over
 * the colour behind it (the first opaque background up its ancestors, else the page). A glyph's
 * ratio is its own colour, because a ring border and a character both take `currentColor`.
 */
import type { Page } from "@playwright/test";

export interface Reading {
  /** The WCAG contrast ratio of the element's colour over its backdrop. */
  ratio: number;
  /** The element's font size in px. */
  fontSize: number;
  /** The element's box in px, as drawn. */
  width: number;
  height: number;
}

/** Reads the first element each selector matches, or null when none does. */
export async function readAll(
  page: Page,
  selectors: Record<string, string>,
): Promise<Record<string, Reading | null>> {
  return page.evaluate((map) => {
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
    const out: Record<string, Reading | null> = {};
    for (const [name, selector] of Object.entries(map)) {
      const el = document.querySelector(selector);
      if (el === null) {
        out[name] = null;
        continue;
      }
      const style = getComputedStyle(el);
      const bg = backdrop(el);
      // A ring is drawn with a border, so its colour is the border's. Text takes the text colour.
      const ink =
        parseFloat(style.borderTopWidth) > 0 && style.borderTopStyle !== "none"
          ? style.borderTopColor
          : style.color;
      const fg = over(parse(ink), bg);
      const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a) as [number, number];
      const box = el.getBoundingClientRect();
      out[name] = {
        ratio: (hi + 0.05) / (lo + 0.05),
        fontSize: parseFloat(style.fontSize),
        width: box.width,
        height: box.height,
      };
    }
    return out;
  }, selectors);
}

/** The focus outline of an element: its width in px and its contrast against the page behind it. */
export async function outlineOf(
  page: Page,
  selector: string,
): Promise<{ width: number; ratio: number } | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el === null) return null;
    const parse = (value: string): [number, number, number, number] => {
      const found = /rgba?\(([^)]+)\)/.exec(value);
      if (found?.[1] === undefined) throw new Error(`Unreadable colour ${value}`);
      const [r = 0, g = 0, b = 0, a = 1] = found[1]
        .split(/[ ,/]+/)
        .filter(Boolean)
        .map(Number);
      return [r, g, b, a];
    };
    const lin = (v: number): number => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
    };
    const lum = ([r, g, b]: number[]): number =>
      0.2126 * lin(r ?? 0) + 0.7152 * lin(g ?? 0) + 0.0722 * lin(b ?? 0);
    // The outline sits outside the box, so it is drawn over what is behind the box's parent.
    let behind = parse(getComputedStyle(document.body).backgroundColor);
    for (let node: Element | null = el.parentElement; node !== null; node = node.parentElement) {
      const color = parse(getComputedStyle(node).backgroundColor);
      if (color[3] >= 1) {
        behind = color;
        break;
      }
    }
    const style = getComputedStyle(el);
    const [hi, lo] = [lum(parse(style.outlineColor)), lum(behind)].sort((a, b) => b - a) as [
      number,
      number,
    ];
    return { width: parseFloat(style.outlineWidth), ratio: (hi + 0.05) / (lo + 0.05) };
  }, selector);
}

/** The width in px a run of text takes in the element it sits in, such as a "✓" glyph. */
export async function glyphWidth(page: Page, selector: string): Promise<number | null> {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (el === null) return null;
    const range = document.createRange();
    range.selectNodeContents(el);
    return range.getBoundingClientRect().width;
  }, selector);
}
