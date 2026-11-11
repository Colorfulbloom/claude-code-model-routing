/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The settings edit flow against the real server on the demo build with edits on (`--demo
 * --allow-edits`, whose folders sit in the server's own temp folder, outside every git work tree).
 * Task a11. One flow in order: open Edit from the inspector, see the preview, save, read the Saved
 * box and its recheck line, then undo from the Changes page. A second test changes the file under
 * an open preview and reads the refusal. A third restarts the server between load and save and
 * reads the restart box. Axe runs at 375 and 1440 on the rail and on the Changes page.
 *
 * Set EDIT_SHOTS to a folder to save a screenshot of each state, for review.
 *
 * Task a16 adds three groups at the end, on the screenshot fixture's made-up home (edit-kit.ts):
 * accessibility snapshots of the rail, the refusal, the Saved box, the overwritten box with its
 * drift, the undo panel and the restart box, at 1440 and 375; a real double-click on Edit, Save,
 * Undo, Undo anyway and Reload, each of which must send one request and leave one row in Changes;
 * and axe on the edit route in every look of the shared loop.
 */
import AxeBuilder from "@axe-core/playwright";
import { test as base } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { en } from "../src/strings/en";
import { scan } from "./a11y";
import * as kit from "./edit-kit";
import { rewriteJson } from "./fixtures/m6_edit";
import { expectUnlocked, linkFor } from "./gate";
import { expect, startServer } from "./server";
import type { Server } from "./server";

const TAGS = ["wcag2a", "wcag2aa", "wcag22aa"];
const PROJECT = "tidewater-reporting";
const ITEM = `/p/${PROJECT}/setup/settings/effortLevel`;
const SHOTS = process.env.EDIT_SHOTS;
const ARGS = ["--demo", "--no-price-fetch", "--test-clock", "--allow-edits"];

const test = base.extend<{ edits: Server }>({
  // eslint-disable-next-line no-empty-pattern
  edits: async ({}, run) => {
    const server = await startServer({ fixture: null, args: ARGS });
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
    // The phone sheet is fixed, so a full-page capture would tear it. Its states take the viewport.
    fullPage: !name.includes("rail") && !name.includes("restart") && !name.includes("refused"),
  });
}

async function axeFound(page: Page, label: string): Promise<string[]> {
  await page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished)));
  const axe = await new AxeBuilder({ page: page as never }).withTags(TAGS).analyze();
  return axe.violations.map(
    (v) => `${label} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
  );
}

/** The rail at 721px and up, the sheet below. Either way it names itself "Edit effort". */
function rail(page: Page) {
  return page.getByRole("heading", { level: 2, name: "Edit effort" });
}

/** The demo project's local settings file, which the Effort edit saves to. */
function localFile(server: Server): string {
  const found = readdirSync(server.dataDir, { recursive: true, encoding: "utf8" }).find(
    (path) => path.includes(PROJECT) && path.endsWith(join(".claude", "settings.local.json")),
  );
  if (found === undefined) throw new Error("the demo's local settings file is missing");
  return join(server.dataDir, found);
}

async function previewReady(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 3, name: en.ed_this_save_h })).toBeVisible();
}

test("opens Edit, previews, saves, rechecks and undoes", async ({ page, edits }) => {
  await openAt(page, edits, ITEM);
  await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();
  await page.getByRole("link", { name: "Edit effort" }).click();
  await expect(page).toHaveURL(/\/setup\/settings\/effortLevel\/edit/);
  await expect(rail(page)).toBeFocused();
  await expect(page.getByRole("button", { name: /^Save to / })).toBeVisible();
  await previewReady(page);
  await shot(page, "rail", 1440, "light");

  // A fresh pick changes the preview, and Save sends only that preview.
  await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
  await page.getByRole("button", { name: /^Save to / }).click();

  // Saved: the rail closes back to the inspector, with the Saved box and a link to Changes.
  await expect(page.getByText(en.ed_saved)).toBeVisible();
  await expect(rail(page)).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 2, name: "Effort" })).toBeFocused();
  await expect(page.getByRole("link", { name: en.ed_all_changes })).toHaveAttribute(
    "href",
    `#/p/${PROJECT}/setup/changes`,
  );
  await shot(page, "saved", 1440, "light");
  // The recheck line settles on its own, at about 2 s. A glyph comes first, so match inside it.
  await expect(page.getByText(/Checked the file\. It still holds low\./)).toBeVisible({
    timeout: 15_000,
  });

  // The Changes page lists the save, with its Undo.
  await page.getByRole("link", { name: en.ed_all_changes }).click();
  await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
  await expect(page.getByRole("button", { name: en.ed_undo })).toHaveCount(1);
  await shot(page, "changes", 1440, "light");
  await page.getByRole("button", { name: en.ed_undo }).click();
  await expect(page.getByText(/Undone at /)).toBeVisible();
  await expect(page.getByRole("button", { name: en.ed_undo })).toHaveCount(0);
  await shot(page, "changes-undone", 1440, "light");
});

/** One save to Effort through the UI, so Changes has a row. */
async function saveLow(page: Page, server: Server): Promise<void> {
  await openAt(page, server, `${ITEM}/edit`);
  await previewReady(page);
  await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
  await page.getByRole("button", { name: /^Save to / }).click();
  await expect(page.getByText(en.ed_saved)).toBeVisible();
}

test("axe on Changes with a row at 375 and 1440, light and dark", async ({ page, edits }) => {
  await saveLow(page, edits);
  const found: string[] = [];
  for (const width of [375, 1440]) {
    for (const theme of ["light", "dark"] as const) {
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, `/p/${PROJECT}/setup/changes`);
      await expect(page.getByRole("button", { name: en.ed_undo })).toHaveCount(1);
      // Each cell keeps its column word for a screen reader, and the header row hides from one.
      for (const word of [en.cg_col_when, en.cg_col_change, en.cg_col_file, en.cg_col_undo]) {
        await expect(page.locator(".changes-cell > .sr-only", { hasText: word })).toHaveCount(1);
      }
      const sideways = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(sideways, `Changes scrolls sideways at ${String(width)}`).toBeLessThanOrEqual(0);
      await shot(page, "changes", width, theme);
      found.push(...(await axeFound(page, `changes rows ${String(width)} ${theme}`)));
    }
  }
  expect(found).toEqual([]);
});

test("asks first when Undo would also remove another change", async ({ page, edits }) => {
  await saveLow(page, edits);
  // Another program changes the saved file, so the old copy is no longer the file's last state.
  writeFileSync(localFile(edits), JSON.stringify({ effortLevel: "low", other: true }, null, 2));
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, `/p/${PROJECT}/setup/changes`);
  await page.getByRole("button", { name: en.ed_undo }).click();
  const heading = page.getByRole("heading", { name: en.ed_undo_h });
  await expect(heading).toBeVisible();
  await expect(heading).toBeFocused();
  await shot(page, "undo-confirm", 1440, "light");
  await page.getByRole("button", { name: en.ed_undo_keep }).click();
  await expect(heading).toHaveCount(0);
  await expect(page.getByText(/Undone at /)).toHaveCount(0);
  await page.getByRole("button", { name: en.ed_undo }).click();
  await page.getByRole("button", { name: en.ed_undo_anyway }).click();
  await expect(page.getByText(/Undone at /)).toBeVisible();
});

test("axe on the rail and on Changes at 375 and 1440", async ({ page, edits }) => {
  const found: string[] = [];
  for (const width of [375, 1440]) {
    for (const theme of ["light", "dark"] as const) {
      await openAt(page, edits, `${ITEM}/edit`, width, theme);
      await previewReady(page);
      await shot(page, "rail", width, theme);
      found.push(...(await axeFound(page, `rail ${String(width)} ${theme}`)));
      await openAt(page, edits, `/p/${PROJECT}/setup/changes`, width, theme);
      await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: en.cg_empty_h })).toBeVisible();
      await shot(page, "changes-empty", width, theme);
      found.push(...(await axeFound(page, `changes ${String(width)} ${theme}`)));
    }
  }
  expect(found).toEqual([]);
});

test("refuses a save after another program changed the file", async ({ page, edits }) => {
  await openAt(page, edits, `${ITEM}/edit`);
  await previewReady(page);
  await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
  // Another program changes the picked file under the open page.
  writeFileSync(localFile(edits), JSON.stringify({ effortLevel: "medium", other: true }, null, 2));
  const save = page.getByRole("button", { name: /^Save to / });
  await save.click();
  const refusal = page.locator(".refused");
  await expect(refusal).toContainText(en.er_lead);
  await expect(refusal).toBeFocused();
  await expect(refusal).not.toHaveAttribute("role", "alert");
  // The rail stays open, and Save works again once the fresh preview shows.
  await expect(rail(page)).toBeVisible();
  await shot(page, "refused", 1440, "light");
});

// A restarted server has a new instance, and the page's read key dies with the old one, so a real
// restart shows the locked page before Save can be pressed (the M3 gate). The restart box is for the
// case where the read key still works and the server no longer knows the page's edit key, so the
// server's answer is made here, as it would send it.
test("shows the restart box when the server no longer knows the page's edit key", async ({
  page,
  edits,
}) => {
  await openAt(page, edits, `${ITEM}/edit`);
  await previewReady(page);
  await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
  let sent = 0;
  await page.route("**/api/edit/save", (route) => {
    sent += 1;
    return route.fulfill({ status: 403, json: { code: "edit_key_unknown" } });
  });
  await page.getByRole("button", { name: /^Save to / }).click();
  const box = page.locator(".restart-box");
  await expect(box).toContainText(en.eo_restart_on_h);
  await expect(box).toBeFocused();
  await expect(box).not.toHaveAttribute("role", "alert");
  await shot(page, "restart", 1440, "light");
  // The whole rail is inert: Save is aria-disabled and described by the box, so it waits for a
  // reload, and another press (forced, because the button is aria-disabled) sends nothing.
  const save = page.getByRole("button", { name: /^Save to / });
  await expect(save).toHaveAttribute("aria-disabled", "true");
  await expect(save).toHaveAttribute("aria-describedby", (await box.getAttribute("id")) ?? "");
  await save.click({ force: true });
  await page.waitForTimeout(500);
  expect(sent).toBe(1);
});

test("a real restart between load and save lands on the locked page, never a half save", async ({
  page,
  edits,
}) => {
  await openAt(page, edits, `${ITEM}/edit`);
  await previewReady(page);
  await page.getByRole("radio", { name: "low", exact: true }).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
  // The same data folder and port, so the new server reads the same demo.
  await edits.stop();
  const again = await startServer({
    fixture: null,
    args: ARGS,
    dataDir: edits.dataDir,
    port: edits.port,
  });
  try {
    await page.getByRole("button", { name: /^Save to / }).click();
    await expect(page.locator('h1[data-gate="locked"]')).toBeVisible();
    expect(readFileSync(localFile(again), "utf8")).not.toContain('"effortLevel": "low"');
  } finally {
    await again.stop();
  }
});

// ---------------------------------------------------------------------------------------------
// Task a16. Accessibility snapshots, double-clicks and axe on the screenshot fixture.
// ---------------------------------------------------------------------------------------------

const WIDTHS = [1440, 375] as const;

function indent(text: string, by: number): string {
  const pad = " ".repeat(by);
  return text
    .split("\n")
    .map((line) => pad + line)
    .join("\n");
}

// What a screen reader gets from the rail with Project local and low picked. String.raw keeps the
// backslashes of the quoted code lines.
const RAIL_CONTROLS = String.raw`- radiogroup "Effort":
  - radio "low" [checked]
  - radio "medium"
  - radio "high"
  - radio "xhigh set now runs at high Lowered"
- button "Save to"
- radiogroup "Save to":
  - radio "Project local Just you, this project .claude/settings.local.json Takes effect ✓ Selected" [checked]
  - radio "Shared project Everyone in this project .claude/settings.json Overridden by Project local"
  - radio "User You, every project ~/.claude/settings.json links to ~/dotfiles/claude/settings.json Ignored"
- region "This save":
  - heading "This save" [level=3]
  - button "About This save"
  - term: File
  - definition: Project local .claude/settings.local.json
  - term: Set to
  - definition: xhigh to low
  - term: Runs at
  - definition: high Lowered to low In effect Applies to new sessions
  - list "This save":
    - listitem:
      - text: 1 unchanged
      - code: "{"
    - listitem:
      - text: 2 unchanged
      - code: "\"env\": {"
    - listitem:
      - text: 3 removed
      - code: "\"CLAUDE_CODE_EFFORT_LEVEL\": \"xhigh\""
    - listitem:
      - text: 3 added
      - code: "\"CLAUDE_CODE_EFFORT_LEVEL\": \"low\""
  - paragraph: /Bar Tab read this file at .*/`;

function railSnapshot(width: number): string {
  if (width > 720) {
    return [
      '- region "Edit effort":',
      '  - heading "Edit effort" [level=2]',
      '  - button "Cancel"',
      indent(RAIL_CONTROLS, 2),
      "  - paragraph: Bar Tab keeps a copy of the old file, so Undo can put it back.",
      '  - button "Save to Project local"',
    ].join("\n");
  }
  return [
    '- dialog "Edit effort":',
    "  - banner:",
    '    - button "Close": ✕',
    '    - heading "Edit effort" [level=2]',
    indent(RAIL_CONTROLS, 2),
    "  - paragraph: settings.local.json, xhigh → low",
    '  - button "Save to Project local"',
  ].join("\n");
}

for (const width of WIDTHS) {
  const at = `at ${String(width)}`;

  test(`snapshots: the rail, a refusal and the Saved box ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await expect(kit.railOf(page, width)).toMatchAriaSnapshot(railSnapshot(width));

      // Another program changes the file after the preview. The refusal is two plain paragraphs,
      // with no alert role, and it takes focus.
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      await kit.saveButton(page).click();
      const refusal = page.locator(".refused");
      await expect(refusal).toBeFocused();
      await expect(refusal).toMatchAriaSnapshot(String.raw`
        - paragraph: Not saved. settings.local.json changed after your preview, so Bar Tab wrote nothing.
        - paragraph: Another program changed other. The preview below now shows the new file, so check it and save again.
      `);

      // The Saved box says itself once. Its recheck line is busy, then reads the settled sentence.
      await expect(page.locator(".this-save-updating")).toHaveCount(0);
      await kit.saveButton(page).click();
      const saved = page.locator(".saved-box");
      await expect(saved).toMatchAriaSnapshot(`
        - status: /Saved\\. .+ Undo puts the old file back\\./
        - button "Undo"
        - status: Reading the file again to check the change
        - link "All changes":
          - /url: "#/p/${PROJECT}/setup/changes"
      `);
      await expect(saved).toMatchAriaSnapshot(
        `
        - status: /Saved\\. .+ Undo puts the old file back\\./
        - button "Undo"
        - status: Checked the file. It still holds low.
        - link "All changes"
      `,
        { timeout: 15_000 },
      );
    });
  });

  test(`snapshots: overwritten with its drift, and the undo panel ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await kit.saveButton(page).click();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      // Another program writes the file before the first recheck, and keeps our value.
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      await expect(page.getByText(en.ed_over)).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: en.ed_review_changes }).click();
      await expect(page.locator(".overwritten-box-drift .diff")).toBeVisible();
      await expect(page.locator(".overwritten-box")).toMatchAriaSnapshot(String.raw`
        - status:
          - paragraph: Saved, but another program changed this file right after. Review it before you go on.
          - paragraph: Changed after your save
          - paragraph:
            - code: other
          - paragraph: Your effort change is still in the file.
          - button "Review changes" [expanded]
          - button "Undo"
        - region "What the other program changed":
          - heading "What the other program changed" [level=3]
          - paragraph: .claude/settings.local.json
          - list "What the other program changed":
            - listitem:
              - text: 3 unchanged
              - code: "\"CLAUDE_CODE_EFFORT_LEVEL\": \"low\""
            - listitem:
              - text: 4 removed
              - code: "}"
            - listitem:
              - text: 4 added
              - code: "},"
            - listitem:
              - text: 5 added
              - code: "\"other\": true"
      `);

      // Undo asks first, because the file changed since the save. Its panel is a region in the
      // card at 1440 and a dialog on a phone, and its heading has focus.
      await page.getByRole("button", { name: en.ed_undo, exact: true }).click();
      const heading = page.getByRole("heading", { name: en.ed_undo_h });
      await expect(heading).toBeFocused();
      if (width <= 720)
        await expect(page.getByRole("dialog", { name: en.ed_undo_h })).toBeVisible();
      const head =
        width > 720
          ? '- heading "Undo this save" [level=2]\n- button "Cancel"'
          : '- button "Close": ✕\n- heading "Undo this save" [level=2]';
      const foot =
        width > 720
          ? '- button "Keep the file as it is"\n- button "Undo anyway"'
          : '- button "Undo anyway"\n- button "Keep the file as it is"';
      const body = String.raw`- paragraph: settings.local.json changed after your save. Undo puts the whole old file back, so it also removes that other change.
- heading "What Undo changes" [level=3]
- paragraph: .claude/settings.local.json
- list "What Undo changes":
  - listitem:
    - text: 3 removed
    - code: "\"CLAUDE_CODE_EFFORT_LEVEL\": \"low\""
  - listitem:
    - text: 5 removed
    - code: "\"other\": true"
  - listitem:
    - text: 3 added
    - code: "\"CLAUDE_CODE_EFFORT_LEVEL\": \"xhigh\""`;
      await expect(page.locator(".undo-confirm")).toMatchAriaSnapshot(
        `- region "Undo this save":\n${indent([head, body, foot].join("\n"), 2)}`,
      );
    });
  });

  test(`snapshots: the restart box ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await page.route("**/api/edit/save", (route) =>
        route.fulfill({ status: 403, json: { code: "edit_key_unknown" } }),
      );
      await kit.saveButton(page).click();
      const box = page.locator(".restart-box");
      await expect(box).toBeFocused();
      await expect(box).toMatchAriaSnapshot(`
        - paragraph: Bar Tab restarted after this page loaded, so this page can't save.
        - paragraph: Reload the page to edit again.
        - button "Reload"
      `);
    });
  });

  // ------- A real double-click on each primary button: one request, one row in Changes. -------

  test(`double-click on Edit opens the editor once ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openAt(page, world.server, kit.ITEM, width);
      const edit = page.getByRole("link", { name: "Edit effort" });
      await expect(edit).toBeVisible();
      const sent = kit.watchRequests(page);
      const entries = await page.evaluate(() => window.history.length);
      await edit.dblclick();
      await expect(page).toHaveURL(/\/setup\/settings\/effortLevel\/edit$/);
      await kit.previewReady(page);
      await kit.quiet(page);
      // One preview for the one open, one more history entry, and the second click changed nothing.
      expect(sent.count("preview")).toBe(1);
      expect(await page.evaluate(() => window.history.length)).toBe(entries + 1);
      await expect(kit.levelRadio(page, "xhigh")).toBeChecked();
      await expect(kit.scopeRadio(page, /^Project local/)).toBeChecked();
      await expect(kit.railOf(page, width)).toBeVisible();
      sent.stop();
    });
  });

  test(`double-click on Save sends one save and makes one row ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      const sent = kit.watchRequests(page);
      await kit.saveButton(page).dblclick();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      await kit.quiet(page);
      expect(sent.count("save")).toBe(1);
      // The second click landed on the page behind the closed rail and undid nothing.
      expect(sent.count("undo")).toBe(0);
      sent.stop();
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, kit.CHANGES);
      await expect(page.locator(".changes-row")).toHaveCount(1);
      await expect(page.locator(".changes-row", { hasText: /Undid / })).toHaveCount(0);
    });
  });

  test(`double-click on Undo sends one undo and makes one row ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await kit.saveButton(page).click();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      const sent = kit.watchRequests(page);
      await page.getByRole("button", { name: en.ed_undo, exact: true }).dblclick();
      await expect(page.getByText(/Undone at /)).toBeVisible();
      await kit.quiet(page);
      expect(sent.count("undo")).toBe(1);
      sent.stop();
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, kit.CHANGES);
      // The save and its undo, and no second undo.
      await expect(page.locator(".changes-row")).toHaveCount(2);
      await expect(page.locator(".changes-row", { hasText: /Undid / })).toHaveCount(1);
    });
  });

  test(`double-click on Undo anyway sends one confirmed undo ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await kit.saveButton(page).click();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      const sent = kit.watchRequests(page);
      await page.getByRole("button", { name: en.ed_undo, exact: true }).click();
      await expect(page.getByRole("heading", { name: en.ed_undo_h })).toBeFocused();
      await page.getByRole("button", { name: en.ed_undo_anyway }).dblclick();
      await expect(page.getByText(/Undone at /)).toBeVisible();
      await kit.quiet(page);
      // The ask, then one confirmed undo.
      expect(sent.bodies("undo").map((body) => body.anyway === true)).toEqual([false, true]);
      sent.stop();
      await page.evaluate((hash) => {
        window.location.hash = hash;
      }, kit.CHANGES);
      await expect(page.locator(".changes-row")).toHaveCount(2);
      await expect(page.locator(".changes-row", { hasText: /Undid / })).toHaveCount(1);
    });
  });

  test(`double-click on Reload loads the page once ${at}`, async ({ page }) => {
    await kit.inWorld({}, async (world) => {
      await kit.openEditRoute(page, world, width);
      await kit.pickLowByMouse(page);
      await page.route("**/api/edit/save", (route) =>
        route.fulfill({ status: 403, json: { code: "edit_key_unknown" } }),
      );
      await kit.saveButton(page).click();
      await expect(page.locator(".restart-box")).toBeFocused();
      const sent = kit.watchRequests(page);
      await page.getByRole("button", { name: en.eo_reload }).dblclick();
      await kit.previewReady(page);
      await kit.quiet(page);
      expect(sent.navigations()).toBe(1);
      expect(sent.count("save")).toBe(0);
      sent.stop();
    });
  });
}

test("axe on the edit route at 375 and 1440 in every look", async ({ page }) => {
  await kit.inWorld({}, async (world) => {
    const found = await scan(page, {
      label: "edit route",
      widths: [375, 1440],
      enter: async (p) => {
        await kit.loadRoute(p, world.server, kit.EDIT);
        await kit.previewReady(p);
      },
    });
    expect(found).toEqual([]);
  });
});
