/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The edits-off states against the real server on the demo build without `--allow-edits`. Task a11.
 * Edit stays in the inspector's foot, aria-disabled and focusable, with one visible reason line tied
 * to it. An edit URL renders the item page with the route note, focused. Changes shows the history
 * note once at the top, with each Undo aria-disabled. The sidebar foot and the More page say
 * "Editing off" and open the help. The restart box names the command when the new server has
 * editing off. Axe runs at 375 and 1440 on each state.
 *
 * Changes needs rows to show Undo, so one test saves on an edits-on server, stops it, and starts
 * the same data folder again with editing off. Set EDIT_SHOTS to a folder to save screenshots.
 *
 * Task a16 adds, at the end and on the screenshot fixture's made-up home (edit-kit.ts), an
 * accessibility snapshot of the off inspector and of the route note, a real double-click on the
 * aria-disabled Edit and Undo (nothing is sent, nothing moves), and the shared axe loop on the off
 * inspector, the off edit route and Changes with a row, at 375 and 1440 in every look.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as base } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import { en } from "../src/strings/en";
import { HELP } from "../src/strings/help";
import { scan } from "./a11y";
import * as kit from "./edit-kit";
import { openSession, saveField, startReady } from "./fixtures/m6_edit";
import { COMMAND, expectUnlocked, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const ITEM = `/p/${PROJECT}/setup/settings/effortLevel`;
const SHOTS = process.env.EDIT_SHOTS;
const OFF_ARGS = ["--demo", "--no-price-fetch", "--test-clock"];
const ON_ARGS = [...OFF_ARGS, "--allow-edits"];
const CMD = `${COMMAND} --allow-edits`;

const test = base.extend<{ off: Server }>({
  // eslint-disable-next-line no-empty-pattern
  off: async ({}, run) => {
    const server = await startServer({ fixture: null, args: OFF_ARGS });
    try {
      await run(server);
    } finally {
      await server.stop();
      rmSync(server.dataDir, { recursive: true, force: true });
    }
  },
});

test.setTimeout(120_000);

async function openAt(
  page: Page,
  server: Server,
  route: string,
  width = 1440,
  theme: "light" | "dark" = "light",
): Promise<void> {
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, route);
}

async function shot(page: Page, name: string, width: number, theme: string): Promise<void> {
  if (SHOTS === undefined) return;
  mkdirSync(SHOTS, { recursive: true });
  await page.screenshot({
    path: join(SHOTS, `${name}-${String(width)}-${theme}.png`),
    fullPage: true,
  });
}

async function axeFound(page: Page, label: string): Promise<string[]> {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
  const axe = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  return axe.violations.map(
    (v) => `${label} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

const reasonText = en.eo_reason.replace("{cmd}", CMD);
const historyNote = en.eo_hist_note.replace("{cmd}", CMD);

test("keeps Edit in the foot, aria-disabled and tied to one reason line", async ({ page, off }) => {
  await openAt(page, off, ITEM);
  const region = page.getByRole("region", { name: "Effort" });
  const edit = region.getByRole("button", { name: en.ed_edit_aria.replace("{field}", "effort") });
  await expect(edit).toBeVisible();
  await expect(edit).toHaveAttribute("aria-disabled", "true");
  // The visible reason names the command, and the button points at it.
  const reason = region.getByText(reasonText);
  await expect(reason).toHaveCount(1);
  const reasonId = await reason.getAttribute("id");
  expect(reasonId).not.toBeNull();
  const describedBy = (await edit.getAttribute("aria-describedby")) ?? "";
  expect(describedBy.split(" ")).toContain(reasonId);
  // It takes focus, and pressing it goes nowhere.
  await edit.focus();
  await expect(edit).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).not.toHaveURL(/\/edit/);
  await shot(page, "off-inspector", 1440, "light");
});

test("renders the item page with a focused route note on an edit URL", async ({ page, off }) => {
  await openAt(page, off, `${ITEM}/edit`);
  await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Edit effort" })).toHaveCount(0);
  // The note names the item and the command, and focus is on it.
  const note = page.locator(":focus");
  await expect(note).toContainText("Editing is off, so Effort opened without its editor.");
  await expect(note).toContainText(CMD);
  await expect(note).not.toHaveAttribute("role", "alert");
  await shot(page, "off-route", 1440, "light");
});

test("says Editing off in the sidebar foot and on More, and opens the help", async ({
  page,
  off,
}) => {
  await openAt(page, off, ITEM);
  const nav = page.getByRole("navigation", { name: "Main" });
  const line = nav.getByRole("button", { name: en.eo_ft_off });
  await expect(line).toBeVisible();
  await line.click();
  await expect(page.getByRole("dialog").getByText(HELP["shell.editing"].title)).toBeVisible();
  await page.keyboard.press("Escape");
  await openAt(page, off, "/more", 375);
  const card = page.getByRole("region", { name: "Your history" });
  await expect(card.getByText(en.eo_more_off, { exact: true })).toBeVisible();
  await card.getByRole("button", { name: en.more_l_editing }).click();
  await expect(page.getByRole("dialog").getByText(HELP["shell.editing"].title)).toBeVisible();
  await shot(page, "off-more", 375, "light");
});

test("shows the history note once on Changes, with each Undo aria-disabled", async ({ page }) => {
  // Save on a server with edits on, then read the same folder with edits off.
  const on = await startServer({ fixture: null, args: ON_ARGS });
  let off: Server | null = null;
  try {
    await openAt(page, on, `${ITEM}/edit`);
    await expect(page.getByRole("heading", { level: 3, name: en.ed_this_save_h })).toBeVisible();
    await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
    await expect(page.locator(".this-save")).toContainText("low");
    await page.getByRole("button", { name: /^Save to / }).click();
    await expect(page.getByText(en.ed_saved)).toBeVisible();
    await on.stop();
    off = await startServer({
      fixture: null,
      args: OFF_ARGS,
      dataDir: on.dataDir,
      port: on.port,
    });
    const found: string[] = [];
    for (const width of [375, 1440]) {
      for (const theme of ["light", "dark"] as const) {
        // The old page still holds the first server's locked state, so start from a blank one.
        await page.goto("about:blank");
        await openAt(page, off, `/p/${PROJECT}/setup/changes`, width, theme);
        await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
        await expect(page.getByText(historyNote)).toHaveCount(1);
        const undo = page.getByRole("button", { name: en.ed_undo });
        await expect(undo).toHaveCount(1);
        await expect(undo).toHaveAttribute("aria-disabled", "true");
        await undo.click({ force: true });
        await expect(page.getByText(/Undone at /)).toHaveCount(0);
        await shot(page, "off-changes", width, theme);
        found.push(...(await axeFound(page, `off changes ${String(width)} ${theme}`)));
      }
    }
    expect(found).toEqual([]);
  } finally {
    await on.stop();
    if (off !== null) await off.stop();
    rmSync(on.dataDir, { recursive: true, force: true });
  }
});

test("names the command in the restart box when the new server has editing off", async ({
  page,
}) => {
  const on = await startServer({ fixture: null, args: ON_ARGS });
  try {
    await openAt(page, on, `${ITEM}/edit`);
    await expect(page.getByRole("heading", { level: 3, name: en.ed_this_save_h })).toBeVisible();
    await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
    await expect(page.locator(".this-save")).toContainText("low");
    // The answers of a server that restarted with editing off, as it would send them.
    await page.route("**/api/edit/save", (route) =>
      route.fulfill({ status: 403, json: { code: "edits_off" } }),
    );
    await page.route(/\/api\/(?!edit\/save)/, async (route) => {
      const response = await route.fetch();
      let body: { edits?: { state: string } } | null = null;
      try {
        body = (await response.json()) as { edits?: { state: string } } | null;
      } catch {
        await route.fulfill({ response });
        return;
      }
      if (body?.edits !== undefined) body.edits.state = "off";

      await route.fulfill({ response, json: body });
    });
    await page.getByRole("button", { name: /^Save to / }).click();
    const box = page.locator(".restart-box");
    await expect(box).toContainText(en.eo_restart_h);
    await expect(box).toContainText(CMD);
    await expect(box).toBeFocused();
    // The new server's mode arrives with the next /api/app read, and the box stays up for it.
    await page.waitForTimeout(1500);
    await expect(box).toBeVisible();
    await expect(page.getByText(/opened without its editor/)).toHaveCount(0);
    await shot(page, "off-restart", 1440, "light");
  } finally {
    await on.stop();
    rmSync(on.dataDir, { recursive: true, force: true });
  }
});

test("axe on the off inspector and the route note at 375 and 1440", async ({ page, off }) => {
  const found: string[] = [];
  for (const width of [375, 1440]) {
    for (const theme of ["light", "dark"] as const) {
      await openAt(page, off, ITEM, width, theme);
      await expect(page.getByText(reasonText)).toBeVisible();
      await shot(page, "off-inspector", width, theme);
      found.push(...(await axeFound(page, `off inspector ${String(width)} ${theme}`)));
      await openAt(page, off, `${ITEM}/edit`, width, theme);
      await expect(page.getByText(/opened without its editor/)).toBeVisible();
      await shot(page, "off-route", width, theme);
      found.push(...(await axeFound(page, `off route ${String(width)} ${theme}`)));
    }
  }
  expect(found).toEqual([]);
});

// ---------------------------------------------------------------------------------------------
// Task a16. Snapshots, double-clicks and the shared axe loop on the screenshot fixture.
// ---------------------------------------------------------------------------------------------

for (const width of [1440, 375] as const) {
  const at = `at ${String(width)}`;

  test(`snapshots: the off inspector and the route note ${at}`, async ({ page }) => {
    await kit.inWorld({ edits: false }, async (world) => {
      await kit.openAt(page, world.server, ITEM, width);
      await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();
      // Edit is a disabled button in the foot, and the one reason line names the command.
      await expect(page.getByRole("region", { name: "Effort" })).toMatchAriaSnapshot(String.raw`
        - heading "Effort" [level=2]
        - text: Lowered
        - paragraph: Runs at high
        - button "Edit effort" [disabled]: Edit
        - button "Copy path"
        - paragraph:
          - text: Editing is off. Start Bar Tab with
          - code: /bartab-preview --allow-edits
          - text: to turn it on.
      `);

      // An edit URL shows the item with a note that takes focus, and the rail does not open.
      await kit.openAt(page, world.server, kit.EDIT, width);
      const note = page.locator(".edits-off-route");
      await expect(note).toBeFocused();
      await expect(note).toMatchAriaSnapshot(String.raw`
        - paragraph:
          - text: Editing is off, so Effort opened without its editor. Start Bar Tab with
          - code: /bartab-preview --allow-edits
          - text: to edit it.
      `);
      await expect(page.getByRole("heading", { level: 2, name: "Edit effort" })).toHaveCount(0);
    });
  });

  test(`double-clicks on the disabled Edit and Undo send nothing ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      // A row to undo, made with editing on, then the same folders with editing off.
      await saveField(await openSession(world.server), "local", "effortLevel", "low");
      await world.server.stop();
      const off = await startReady(world.fx, { edits: false });
      try {
        const sent = kit.watchRequests(page);
        await kit.openAt(page, off, ITEM, width);
        const edit = page.getByRole("button", { name: "Edit effort" });
        await expect(edit).toHaveAttribute("aria-disabled", "true");
        await edit.dblclick({ force: true });
        await kit.quiet(page);
        await expect(page).not.toHaveURL(/\/edit/);
        expect(sent.count("preview")).toBe(0);

        await kit.openAt(page, off, kit.CHANGES, width);
        const undo = page.getByRole("button", { name: en.ed_undo, exact: true });
        await expect(undo).toHaveAttribute("aria-disabled", "true");
        await undo.dblclick({ force: true });
        await kit.quiet(page);
        await expect(page.getByText(/Undone at /)).toHaveCount(0);
        await expect(page.locator(".changes-row")).toHaveCount(1);
        expect(sent.count("undo")).toBe(0);
        sent.stop();
      } finally {
        await off.stop();
      }
    });
  });
}

test("axe on the off inspector, the off edit route and Changes at 375 and 1440 in every look", async ({
  page,
}) => {
  await kit.inWorld({}, async (world) => {
    await saveField(await openSession(world.server), "local", "effortLevel", "low");
    await world.server.stop();
    const off = await startReady(world.fx, { edits: false });
    try {
      const found: string[] = [];
      found.push(
        ...(await scan(page, {
          label: "off inspector",
          widths: [375, 1440],
          enter: async (p) => {
            await kit.loadRoute(p, off, ITEM);
            await expect(p.getByText(reasonText)).toBeVisible();
          },
        })),
        ...(await scan(page, {
          label: "off route",
          widths: [375, 1440],
          enter: async (p) => {
            await kit.loadRoute(p, off, `${ITEM}/edit`);
            await expect(p.getByText(/opened without its editor/)).toBeVisible();
          },
        })),
        ...(await scan(page, {
          label: "off changes",
          widths: [375, 1440],
          enter: async (p) => {
            await kit.loadRoute(p, off, kit.CHANGES);
            await expect(p.locator(".changes-row")).toHaveCount(1);
            await expect(p.getByText(historyNote)).toHaveCount(1);
          },
        })),
      );
      expect(found).toEqual([]);
    } finally {
      await off.stop();
    }
  });
});
