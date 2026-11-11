/// <reference lib="dom" />
/// <reference types="node" />
/*
 * Keyboard walkthroughs 1 to 3 and 6 of M6a (m6-build.md section 11, task a16), at 375 and 1440.
 * Each runs on the screenshot fixture's made-up home with a real server and presses only keys: Tab,
 * Shift+Tab, the arrows, Enter, Space and Escape. Every step asserts where focus is and what the
 * page says.
 *
 *   1. Change effort and undo. List, Effort, Edit, a new level, each Save to row's outcome, Save,
 *      the Saved box and its one recheck line, Undo, and the row on Changes shown as undone.
 *   2. Refusal. The file changes after the preview, Save is refused, focus lands on the message,
 *      the preview shows the new file, and a second Save works.
 *   3. Overwritten and undo after a change. Review changes opens the drift with focus in it, Undo
 *      shows what it removes, "Keep the file as it is" leaves the file, and "Undo anyway" restores it.
 *   6. Edits off. Edit is aria-disabled with the reason naming the command, Changes says so once,
 *      and a row's Undo is aria-disabled and sends nothing.
 *
 * Another program's change to a file is made by writing the file from the test, as it would happen.
 */
import { readFileSync } from "node:fs";
import type { Page } from "@playwright/test";
import { en } from "../src/strings/en";
import { COMMAND } from "./gate";
import { expect, test } from "@playwright/test";
import {
  EDIT,
  LIST,
  inWorld,
  levelRadio,
  openAt,
  previewReady,
  railOf,
  reach,
  saveButton,
  tabStops,
  watchRequests,
} from "./edit-kit";
import type { World } from "./edit-kit";
import { openSession, PROJECT_KEY, rewriteJson, saveField, startReady } from "./fixtures/m6_edit";

test.setTimeout(180_000);

const WIDTHS = [1440, 375] as const;
const OFF_CMD = `${COMMAND} --allow-edits`;

/** Presses a key and checks which element has focus, by role and name. */
async function expectFocus(page: Page, snapshot: string): Promise<void> {
  await expect(page.locator(":focus")).toMatchAriaSnapshot(snapshot);
}

/** Tab to the effort control, then the arrows to the level. Effort starts on xhigh. */
async function pickLevelByKeys(page: Page, arrows: "ArrowLeft" | "ArrowRight", times: number) {
  await reach(page, page.getByRole("radio", { name: /^xhigh/ }));
  for (let i = 0; i < times; i++) await page.keyboard.press(arrows);
}

/** Setup > Changes with the keys: the Setup link in the main navigation, then the Changes link. */
async function changesByKeys(page: Page): Promise<void> {
  const setup = page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Setup" });
  await reach(page, setup);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: en.su_h1 })).toBeVisible();
  await reach(page, page.getByRole("link", { name: en.cg_h1, exact: true }));
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
}

/** Opens the edit route, tabs to low with the arrows and saves with the key. Leaves "Saved." up. */
async function saveLowByKeys(page: Page, world: World, width: number): Promise<void> {
  await openAt(page, world.server, EDIT, width);
  await previewReady(page);
  await pickLevelByKeys(page, "ArrowLeft", 3);
  await expect(levelRadio(page, "low")).toBeFocused();
  await expect(page.locator(".this-save")).toContainText("low");
  await reach(page, saveButton(page));
  await page.keyboard.press("Enter");
  await expect(page.getByText(en.ed_saved)).toBeVisible();
}

for (const width of WIDTHS) {
  const at = `at ${String(width)}`;

  test(`1. change effort and undo with the keyboard ${at}`, async ({ page }) => {
    await inWorld({}, async (world) => {
      const sent = watchRequests(page);
      const before = readFileSync(world.fx.localFile, "utf8");
      await openAt(page, world.server, LIST, width);
      await expect(page.getByRole("heading", { level: 1, name: "Settings" })).toBeVisible();

      // From the setup list: Tab to Effort, Enter. The inspector's title takes focus.
      await reach(page, page.getByRole("link", { name: /^Effort / }).first());
      await page.keyboard.press("Enter");
      await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();
      await expect(page.getByRole("heading", { level: 2, name: "Effort" })).toBeFocused();

      // Edit is a link while editing is on. Enter opens the rail, and focus lands on its heading.
      await reach(page, page.getByRole("link", { name: "Edit effort" }));
      await expectFocus(page, '- link "Edit effort"');
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/setup\/settings\/effortLevel\/edit$/);
      await previewReady(page);
      const rail = railOf(page, width);
      await expect(rail.getByRole("heading", { level: 2, name: "Edit effort" })).toBeFocused();

      // The focus order inside the rail. At 721px and up Cancel comes first, and the rail is not
      // modal. On a phone the sheet traps focus and its Close button closes the loop.
      const stops = await tabStops(page, width > 720 ? 6 : 5);
      if (width > 720) {
        expect(stops.slice(0, 6)).toEqual([
          'button "Cancel"',
          expect.stringMatching(/^radio "xhigh set now runs at high Lowered" \[checked\]$/),
          'button "Save to"',
          expect.stringMatching(/^radio "Project local .*Selected" \[checked\]$/),
          'button "About This save"',
          'button "Save to Project local" [disabled]',
        ]);
      } else {
        expect(stops).toEqual([
          expect.stringMatching(/^radio "xhigh set now runs at high Lowered" \[checked\]$/),
          'button "Save to"',
          expect.stringMatching(/^radio "Project local .*Selected" \[checked\]$/),
          'button "About This save"',
          'button "Save to Project local" [disabled]',
        ]);
      }

      // A new level with the arrows. The group moves the pick with the focus, and This save follows.
      await reach(page, page.getByRole("radio", { name: /^xhigh/ }));
      await page.keyboard.press("ArrowLeft");
      await page.keyboard.press("ArrowLeft");
      await expectFocus(page, "- radio /^medium/ [checked]");
      await expect(page.locator(".this-save")).toContainText("medium");

      // The Save to rows, one arrow each. Each row's name carries its outcome, so a screen reader
      // says it on arrival. The pick lands on the row and the preview follows it.
      await reach(page, page.getByRole("radio", { name: /^Project local/ }));
      await expectFocus(
        page,
        "- radio /^Project local .*(Takes effect|Lowered).*Selected/ [checked]",
      );
      await page.keyboard.press("ArrowDown");
      await expectFocus(
        page,
        '- radio "Shared project Everyone in this project .claude/settings.json Overridden by Project local ✓ Selected" [checked]',
      );
      await expect(page.locator(".this-save-dl")).toContainText("settings.json");
      await page.keyboard.press("ArrowDown");
      await expectFocus(page, "- radio /^User .*Ignored ✓ Selected/ [checked]");
      await expect(page.locator(".this-save-dl")).toContainText("~/.claude/settings.json");
      await page.keyboard.press("ArrowDown");
      await expectFocus(page, "- radio /^Project local/ [checked]");
      await expect(page.locator(".this-save-dl")).toContainText("settings.local.json");
      await expect(page.locator(".this-save")).toContainText("medium");

      // Save to Project local. The key is Enter at 1440 and Space on a phone.
      await reach(page, saveButton(page));
      await expectFocus(page, '- button "Save to Project local"');
      await page.keyboard.press(width > 720 ? "Enter" : "Space");

      // "Saved." says itself once, in its own status line. The rail closes onto the item's title.
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      await expect(railOf(page, width)).toHaveCount(0);
      await expect(page.getByRole("heading", { level: 2, name: "Effort" })).toBeFocused();
      const recheck = page.locator(".saved-box-recheck");
      await expect(recheck).toHaveAttribute("aria-busy", "true");
      await expect(recheck).toHaveText(en.rc_checking);
      // The recheck line settles at about 2 s and is read once, when it does.
      await expect(recheck).toHaveText("✓Checked the file. It still holds medium.", {
        timeout: 15_000,
      });
      await expect(recheck).not.toHaveAttribute("aria-busy", /.*/);
      await expect(page.getByText(/Checked the file/)).toHaveCount(1);
      expect(sent.count("save")).toBe(1);

      // Undo in the Saved box puts the old file back.
      await reach(page, page.getByRole("button", { name: en.ed_undo, exact: true }));
      await page.keyboard.press("Enter");
      await expect(page.getByText(/Undone at /)).toBeVisible();
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(before);
      expect(sent.count("undo")).toBe(1);

      // Changes, by keys, lists the save as undone, and the undo as its own row.
      await changesByKeys(page);
      const rows = page.locator(".changes-row");
      await expect(rows).toHaveCount(2);
      await expect(rows.filter({ hasText: /Undid / })).toHaveCount(1);
      await expect(page.locator(".changes-state", { hasText: /Undone/ })).toHaveCount(1);
      await expect(page.getByRole("button", { name: en.ed_undo, exact: true })).toHaveCount(0);
      sent.stop();
    });
  });

  test(`2. a refused save lands on the message and saves on the second try ${at}`, async ({
    page,
  }) => {
    await inWorld({}, async (world) => {
      await openAt(page, world.server, EDIT, width);
      await previewReady(page);
      await pickLevelByKeys(page, "ArrowLeft", 3);
      await expect(levelRadio(page, "low")).toBeFocused();
      await expect(page.locator(".this-save")).toContainText("low");
      await expect(page.locator(".this-save .diff")).not.toContainText("other");

      // Another program changes the file after the preview.
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      await reach(page, saveButton(page));
      await page.keyboard.press("Enter");

      // Focus lands on the message, which has no alert role, and the sentence names the file.
      const refusal = page.locator(".refused");
      await expect(refusal).toBeFocused();
      await expect(refusal).toContainText(en.er_lead);
      await expect(refusal).toContainText("settings.local.json changed after your preview");
      await expect(refusal).not.toHaveAttribute("role", "alert");
      await expect(railOf(page, width)).toBeVisible();

      // The preview now shows the file as it is, with the other program's line.
      await expect(page.locator(".this-save .diff")).toContainText("other");
      await expect(page.locator(".this-save-updating")).toHaveCount(0);

      // The next Tab goes to the control that follows the message, and the second Save works.
      await page.keyboard.press("Tab");
      await expectFocus(page, "- radio /^low/ [checked]");
      await reach(page, saveButton(page));
      await page.keyboard.press("Enter");
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      expect(JSON.parse(readFileSync(world.fx.localFile, "utf8"))).toEqual({
        env: { CLAUDE_CODE_EFFORT_LEVEL: "low" },
        other: true,
      });
    });
  });

  test(`3. overwritten, review, keep and undo anyway ${at}`, async ({ page }) => {
    await inWorld({}, async (world) => {
      const sent = watchRequests(page);
      const original = readFileSync(world.fx.localFile, "utf8");
      await saveLowByKeys(page, world, width);
      const saved = readFileSync(world.fx.localFile, "utf8");
      // Another program writes the file right after the save, and keeps our value.
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      const changed = readFileSync(world.fx.localFile, "utf8");
      await expect(page.getByText(en.ed_over)).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(/Your effort change is still in the file/)).toBeVisible();
      await expect(page.locator(".overwritten-box code", { hasText: "other" })).toBeVisible();

      // Review changes opens the drift and focus goes into it.
      await reach(page, page.getByRole("button", { name: en.ed_review_changes }));
      await expectFocus(page, '- button "Review changes"');
      await page.keyboard.press("Enter");
      const drift = page.locator(".overwritten-box-drift");
      await expect(drift).toBeFocused();
      await expect(drift.getByRole("heading", { level: 3, name: en.ed_drift_h })).toBeVisible();
      await expect(drift.locator(".diff")).toContainText("other");
      await expect(page.getByRole("button", { name: en.ed_review_changes })).toHaveAttribute(
        "aria-expanded",
        "true",
      );

      // Undo shows what it removes, with focus on the heading, and sends nothing yet.
      await reach(page, page.getByRole("button", { name: en.ed_undo, exact: true }));
      await page.keyboard.press("Enter");
      const heading = page.getByRole("heading", { name: en.ed_undo_h });
      await expect(heading).toBeVisible();
      await expect(heading).toBeFocused();
      await expect(page.locator(".undo-confirm .diff-del", { hasText: "other" })).toHaveCount(1);
      expect(sent.bodies("undo").map((body) => body.anyway === true)).toEqual([false]);

      // "Keep the file as it is" leaves the file alone and closes the panel.
      await reach(page, page.getByRole("button", { name: en.ed_undo_keep }));
      await page.keyboard.press("Enter");
      await expect(heading).toHaveCount(0);
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(changed);
      expect(changed).not.toBe(saved);

      // Undo again, and this time Undo anyway restores the file from before the save.
      await reach(page, page.getByRole("button", { name: en.ed_undo, exact: true }));
      await page.keyboard.press("Enter");
      await expect(heading).toBeFocused();
      await reach(page, page.getByRole("button", { name: en.ed_undo_anyway }));
      await page.keyboard.press("Enter");
      await expect(page.getByText(/Undone at /)).toBeVisible();
      expect(readFileSync(world.fx.localFile, "utf8")).toBe(original);
      // The first press asked, the second asked again, and only Undo anyway sent the confirm.
      expect(sent.bodies("undo").map((body) => body.anyway === true)).toEqual([false, false, true]);
      sent.stop();
    });
  });

  test(`6. editing off: a disabled Edit, one note on Changes, a disabled Undo ${at}`, async ({
    page,
  }) => {
    await inWorld({}, async (world) => {
      // One save with editing on, so Changes has a row, then the same folders with editing off.
      const session = await openSession(world.server);
      await saveField(session, "local", "effortLevel", "low");
      await world.server.stop();
      const off = await startReady(world.fx, { edits: false });
      try {
        const sent = watchRequests(page);
        await openAt(page, off, `/p/${PROJECT_KEY}/setup/settings/effortLevel`, width);
        await expect(page.getByRole("region", { name: "Effort" })).toBeVisible();

        // Tab to Edit. It is a button now, aria-disabled and focusable, and the reason names the
        // command.
        const edit = page.getByRole("button", { name: "Edit effort" });
        await reach(page, edit);
        await expect(edit).toBeFocused();
        await expect(edit).toHaveAttribute("aria-disabled", "true");
        const reason = page.getByText(en.eo_reason.replace("{cmd}", OFF_CMD));
        await expect(reason).toHaveCount(1);
        expect((await edit.getAttribute("aria-describedby"))?.split(" ")).toContain(
          await reason.getAttribute("id"),
        );
        await page.keyboard.press("Enter");
        await page.keyboard.press("Space");
        await expect(page).not.toHaveURL(/\/edit/);
        await expect(edit).toBeFocused();

        // Changes by keys. The note shows once, and says it as a plain line, not an alert.
        await changesByKeys(page);
        const note = page.getByText(en.eo_hist_note.replace("{cmd}", OFF_CMD));
        await expect(note).toHaveCount(1);
        await expect(page.locator('[role="alert"]')).toHaveCount(0);

        // The row's Undo takes focus, is aria-disabled, points at its row, and presses go nowhere.
        const undo = page.getByRole("button", { name: en.ed_undo, exact: true });
        await expect(undo).toHaveCount(1);
        await reach(page, undo);
        await expect(undo).toBeFocused();
        await expect(undo).toHaveAttribute("aria-disabled", "true");
        const described = (await undo.getAttribute("aria-describedby")) ?? "";
        await expect(page.locator(`[id="${described}"]`)).toContainText("low");
        await page.keyboard.press("Enter");
        await page.keyboard.press("Space");
        await expect(page.getByText(/Undone at /)).toHaveCount(0);
        await expect(note).toHaveCount(1);
        expect(sent.count("undo")).toBe(0);
        sent.stop();
      } finally {
        await off.stop();
      }
    });
  });
}
