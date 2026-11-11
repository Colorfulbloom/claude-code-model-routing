/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The Changes page of M6a (m6-build.md section 5.4, task a16) on the screenshot fixture's made-up
 * home, with rows made by real saves through the server's API (never by writing ledger files).
 *
 *   - Rows and empty, as accessibility snapshots, and the shared axe loop on both.
 *   - Undo of an unchanged file, at once, and the row shown as undone with an undo row of its own.
 *   - Undo anyway after another program changed the file. The panel opens under the row with focus,
 *     lists the other program's lines, Keep leaves the file, and Undo anyway restores it.
 *   - Undo of a save that made the file. The panel names the whole path with "~", sends nothing
 *     until asked, and a real double-click on Undo anyway sends one request and deletes the file.
 *   - Older backups, a disclosure under the last day with the count of earlier saves, and the
 *     backup folder line with Copy path. The clipboard is a stub that records what it is given.
 *
 * Every test runs at 1440 and 375.
 */
import { existsSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page } from "@playwright/test";
import { expect, test } from "@playwright/test";
import { en } from "../src/strings/en";
import { scan } from "./a11y";
import * as kit from "./edit-kit";
import {
  openSession,
  PROJECT_KEY,
  PROJECT_NAME,
  rewriteJson,
  saveField,
  startReady,
} from "./fixtures/m6_edit";
import type { Server } from "./server";

test.setTimeout(180_000);

const WIDTHS = [1440, 375] as const;
const BACKUPS = ".claude/routing-dashboard/backups";

/** One save of Effort to Project local, made through the API as the page makes it. */
async function saveOnce(world: kit.World, value = "low"): Promise<void> {
  const session = await openSession(world.server);
  await saveField(session, "local", "effortLevel", value);
  // The first recheck is at 2 s, so a page opened after it shows the settled word.
  await kit.waitForFirstRecheck(session);
}

/** Opens Changes after the first recheck, so the row shows its settled word. */
async function openSettled(page: Page, world: kit.World, width: number): Promise<void> {
  await kit.openAt(page, world.server, kit.CHANGES, width);
  await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
  await expect(page.locator(".changes-row")).toHaveCount(1);
}

const undoButton = (page: Page) => page.getByRole("button", { name: en.ed_undo, exact: true });

for (const width of WIDTHS) {
  const at = `at ${String(width)}`;

  test(`rows, Undo at once, and the row shown as undone ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      const original = readFileSync(world.fx.localFile, "utf8");
      await saveOnce(world);
      await openSettled(page, world, width);
      await expect(page.locator("main")).toMatchAriaSnapshot(String.raw`
        - heading "Changes" [level=1]
        - paragraph: Every file Bar Tab changed for Tidewater reporting, newest first.
        - region "Today":
          - heading "Today" [level=2]
          - text: "1"
          - button "About Changes"
          - list:
            - listitem:
              - text: /^When .+ Change Effort, xhigh to low File Project local .claude.settings.local.json Undo$/
              - button "Undo"
              - text: Still in the file
          - paragraph:
            - text: Bar Tab keeps copies of the old files in
            - code: ~/.claude/routing-dashboard/backups
            - button "Copy path"
      `);

      // Nothing changed since the save, so Undo goes through at once and asks nothing.
      const sent = kit.watchRequests(page);
      await undoButton(page).click();
      await expect(page.locator(".changes-row")).toHaveCount(2);
      expect(sent.bodies("undo").map((body) => body.anyway === true)).toEqual([false]);
      sent.stop();
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(original);
      await expect(page.locator("main")).toMatchAriaSnapshot(String.raw`
        - region "Today":
          - list:
            - listitem: /^When .+ Change Undid Effort, low to xhigh File Project local .claude.settings.local.json Undo$/
            - listitem: /^When .+ Change Effort, xhigh to low File Project local .claude.settings.local.json Undo Undone at .+/
      `);
      await expect(undoButton(page)).toHaveCount(0);
    });
  });

  test(`Undo anyway restores a file another program changed ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      const original = readFileSync(world.fx.localFile, "utf8");
      await saveOnce(world);
      await openSettled(page, world, width);
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      const changed = readFileSync(world.fx.localFile, "utf8");
      await page.reload();
      await expect(page.locator(".changes-row")).toHaveCount(1);

      // Undo asks first. The panel sits inside the row's list item, and its heading has focus.
      const row = page.locator(".changes-row");
      await undoButton(page).click();
      const heading = page.getByRole("heading", { name: en.ed_undo_h });
      await expect(heading).toBeFocused();
      await expect(row.locator(".changes-confirm .undo-confirm")).toBeVisible();
      // The other program's line is in the list of what Undo removes.
      await expect(page.locator(".undo-confirm .diff-del", { hasText: "other" })).toHaveCount(1);
      await expect(page.locator(".undo-confirm .diff-add", { hasText: "xhigh" })).toHaveCount(1);
      const names = await page.locator(".undo-confirm-actions button").allTextContents();
      expect(names).toEqual(
        width > 720 ? [en.ed_undo_keep, en.ed_undo_anyway] : [en.ed_undo_anyway, en.ed_undo_keep],
      );

      // Keep leaves the file as it is, and the row keeps its Undo.
      await page.getByRole("button", { name: en.ed_undo_keep }).click();
      await expect(heading).toHaveCount(0);
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(changed);
      await expect(undoButton(page)).toHaveCount(1);

      // Undo anyway puts the whole old file back, the other program's line with it.
      await undoButton(page).click();
      await page.getByRole("button", { name: en.ed_undo_anyway }).click();
      await expect(page.locator(".changes-row")).toHaveCount(2);
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(original);
      await expect(page.locator(".changes-state", { hasText: /Undone/ })).toHaveCount(1);
      await expect(page.locator(".changes-row", { hasText: /Undid / })).toHaveCount(1);
    });
  });

  test(`Undo of a file Bar Tab made names the whole path and deletes it once ${at}`, async ({
    page,
  }) => {
    await kit.inWorld({ local: false }, async (world) => {
      await saveOnce(world, "high");
      expect(existsSync(world.fx.localFile)).toBe(true);
      await openSettled(page, world, width);
      const row = page.locator(".changes-row", { hasText: en.cg_deletes_file });
      await expect(row).toHaveCount(1);
      const whole = "~/work/tidewater-reporting/.claude/settings.local.json";
      await expect(row.locator(".changes-file .path-text")).toHaveText(whole);

      // The panel asks first and sends nothing, and its heading has focus.
      const sent = kit.watchRequests(page);
      await undoButton(page).click();
      const heading = page.getByRole("heading", { name: en.ed_undo_h });
      await expect(heading).toBeFocused();
      await expect(page.locator(".undo-confirm-path .path-text")).toHaveText(whole);
      await expect(page.locator(".undo-confirm")).toContainText(en.cg_deletes_file);
      await kit.quiet(page);
      expect(sent.count("undo")).toBe(0);
      expect(existsSync(world.fx.localFile)).toBe(true);

      // Keep closes it with nothing sent.
      await page.getByRole("button", { name: en.ed_undo_keep }).click();
      await expect(heading).toHaveCount(0);
      expect(sent.count("undo")).toBe(0);

      // Undo anyway, pressed twice quickly, deletes the file with one request and one new row.
      await undoButton(page).click();
      await expect(heading).toBeFocused();
      await page.getByRole("button", { name: en.ed_undo_anyway }).dblclick();
      await expect(page.locator(".changes-row")).toHaveCount(2);
      await kit.quiet(page);
      expect(sent.count("undo")).toBe(1);
      sent.stop();
      expect(existsSync(world.fx.localFile)).toBe(false);
      await expect(page.locator(".changes-row", { hasText: /Undid / })).toHaveCount(1);
    });
  });

  test(`Changes empty, as a snapshot and under axe ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openAt(page, world.server, kit.CHANGES, width);
      await expect(page.locator("main")).toMatchAriaSnapshot(String.raw`
        - heading "Changes" [level=1]
        - paragraph: Every file Bar Tab changed for Tidewater reporting, newest first.
        - heading "No changes yet" [level=2]
        - paragraph: When you save a change from Your setup, it shows here with Undo.
        - link "Go to Your setup":
          - /url: "#/p/${PROJECT_KEY}/setup"
      `);
    });
  });
}

test("Changes empty is clean under axe at 375 and 1440 in every look", async ({ page }) => {
  await kit.inWorld({}, async (world) => {
    const found = await scan(page, {
      label: "changes empty",
      widths: [375, 1440],
      enter: async (p) => {
        await kit.loadRoute(p, world.server, kit.CHANGES);
        await expect(p.getByRole("heading", { level: 2, name: en.cg_empty_h })).toBeVisible();
      },
    });
    expect(found).toEqual([]);
  });
});

/**
 * Older backups hold the saves of files the project no longer has as targets. A ledger keeps its 20
 * newest rows per file, so more saves never reach it. What does is a project whose folder moved: two
 * saves are made in the old folder, the folder is renamed, the project list points at the new one,
 * and the server starts again on the same data. The two rows are now "earlier saves", and one new
 * save in the moved folder is the one row of Today. The body gets the second server.
 */
async function withMovedProject(
  world: kit.World,
  body: (server: Server) => Promise<void>,
): Promise<void> {
  const first = await openSession(world.server);
  await saveField(first, "local", "effortLevel", "low");
  await saveField(first, "local", "effortLevel", "high");
  await world.server.stop();
  const moved = join(world.fx.home, "work", "tidewater-moved");
  renameSync(world.fx.project, moved);
  writeFileSync(
    join(world.fx.claudeDir, "routing-dashboard.json"),
    JSON.stringify({ projects: [{ name: PROJECT_NAME, path: moved }], plan: "subscription" }),
  );
  const fx = {
    ...world.fx,
    project: moved,
    projectFile: join(moved, ".claude", "settings.json"),
    localFile: join(moved, ".claude", "settings.local.json"),
  };
  const server = await startReady(fx);
  try {
    await saveField(await openSession(server), "local", "effortLevel", "low");
    await body(server);
  } finally {
    await server.stop();
  }
}

for (const width of WIDTHS) {
  test(`Older backups opens with the keys, and Copy path copies the backup folder at ${String(width)}`, async ({
    page,
  }) => {
    await kit.inWorld({}, async (world) => {
      await withMovedProject(world, async (server) => {
        // A stub clipboard that records what the page copies. The real one is never touched.
        await page.addInitScript(() => {
          const copied: string[] = [];
          Object.defineProperty(window, "__copied", { value: copied });
          Object.defineProperty(navigator, "clipboard", {
            configurable: true,
            value: {
              writeText: (text: string): Promise<void> => {
                copied.push(text);
                return Promise.resolve();
              },
            },
          });
        });
        await kit.openAt(page, server, kit.CHANGES, width);
        await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
        await expect(page.locator(".changes-row:visible")).toHaveCount(1);

        // The disclosure is closed, names the count, and holds its two rows until it opens.
        const trigger = page.locator(".changes-older-trigger");
        await expect(trigger).toContainText(en.cg_older_h);
        await expect(trigger).toContainText("2 earlier saves");
        await expect(trigger).toHaveAttribute("aria-expanded", "false");
        await expect(page.locator(".changes-older-panel .changes-row:visible")).toHaveCount(0);
        await kit.reach(page, trigger);
        await page.keyboard.press("Enter");
        await expect(trigger).toHaveAttribute("aria-expanded", "true");
        await expect(page.locator(".changes-older-panel .changes-row:visible")).toHaveCount(2);
        await page.keyboard.press("Space");
        await expect(trigger).toHaveAttribute("aria-expanded", "false");
        await expect(page.locator(".changes-older-panel .changes-row:visible")).toHaveCount(0);
        await page.keyboard.press("Enter");
        await expect(page.locator(".changes-older-panel .changes-row:visible")).toHaveCount(2);

        // The line under it names the backup folder, with "~" for home, and Copy path copies the
        // real folder. The status says Copied.
        await expect(page.locator(".changes-folder")).toHaveText(`~/${BACKUPS}`);
        const copy = page.getByRole("button", { name: en.in_copy });
        await expect(copy).toHaveCount(1);
        await kit.reach(page, copy);
        await page.keyboard.press("Enter");
        await expect(page.locator(".copy-path-status")).toHaveText(en.an_copied);
        const copied = await page.evaluate(
          () => (window as unknown as { __copied: string[] }).__copied,
        );
        expect(copied).toEqual([join(world.fx.home, BACKUPS)]);
      });
    });
  });
}

test("Changes with rows and Older backups open is clean under axe at 375 and 1440", async ({
  page,
}) => {
  await kit.inWorld({}, async (world) => {
    await withMovedProject(world, async (server) => {
      const found = await scan(page, {
        label: "changes rows",
        widths: [375, 1440],
        enter: async (p) => {
          await kit.loadRoute(p, server, kit.CHANGES);
          await expect(p.locator(".changes-row:visible")).toHaveCount(1);
        },
        hold: async (p) => {
          await p.locator(".changes-older-trigger").click();
          await expect(p.locator(".changes-older-panel .changes-row:visible")).toHaveCount(2);
        },
      });
      expect(found).toEqual([]);
    });
  });
});
