/// <reference lib="dom" />
/// <reference types="node" />
/*
 * The M6a screenshot set (m6-build.md section 8.3, task a13). Every state is saved at 375 and 1440,
 * light and dark, to test-results/m6a-shots/<state>-<width>-<theme>.png, for the visual review
 * (a14 and a14b). The spec asserts only that each state was reached, so a shot is never a loading or
 * locked screen. The numbers in the comments are the items of section 8.3.
 *
 * Each test builds its own made-up home and project (e2e/fixtures/m6_edit.ts) and starts a real
 * server on it. The ledger of Changes comes from real saves made through the API, never from
 * ledger files. Four answers are made here, as the server would send them: the restart box in both
 * modes (a restart can't be shown any other way, as a11's specs explain), and the `checking`
 * outcome of one Changes row, which a real save holds for only 2 s.
 *
 * The phone's edit sheet is position: fixed, so a full-page capture tears it. At 375 the states that
 * show the sheet take the viewport. Every other state takes the whole page.
 */
import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { mkdirSync, rmSync } from "node:fs";
import { join, resolve } from "node:path";
import { en } from "../src/strings/en";
import { glyphWidth, outlineOf, readAll } from "./contrast";
import { COMMAND, expectUnlocked, linkFor } from "./gate";
import { startServer } from "./server";
import type { Server } from "./server";
import {
  buildM6Fixture,
  linkUserOutside,
  PROJECT_KEY,
  restoreFiles,
  rewriteJson,
  seedHistory,
  startReady,
  waitForSetupRead,
} from "./fixtures/m6_edit";
import type { BuildOptions, M6Fixture } from "./fixtures/m6_edit";

const OUT = join(resolve(import.meta.dirname, ".."), "test-results", "m6a-shots");
const ITEM = `/p/${PROJECT_KEY}/setup/settings/effortLevel`;
const EDIT = `${ITEM}/edit`;
const CHANGES = `/p/${PROJECT_KEY}/setup/changes`;
const OFF_CMD = `${COMMAND} --allow-edits`;

const WIDTHS = [375, 1440] as const;
const THEMES = ["light", "dark"] as const;
type Theme = (typeof THEMES)[number];

test.setTimeout(300_000);

interface World {
  fx: M6Fixture;
  server: Server;
}

/** Builds the fixture, starts the server on it, runs the body, then stops and removes it all. */
async function inWorld(
  options: BuildOptions & { edits?: boolean },
  body: (world: World) => Promise<void>,
): Promise<void> {
  const fx = buildM6Fixture(options);
  let server: Server | null = null;
  try {
    server = await startReady(fx, { edits: options.edits ?? true });
    await body({ fx, server });
  } finally {
    if (server !== null) await server.stop();
    fx.cleanup();
  }
}

/** Opens a route on a blank page, so the same origin with a new hash always loads afresh. */
async function openAt(
  page: Page,
  server: Server,
  route: string,
  width: number,
  theme: Theme,
): Promise<void> {
  await page.goto("about:blank");
  await page.setViewportSize({ width, height: 900 });
  await page.emulateMedia({ colorScheme: theme });
  await page.goto(linkFor(server.baseURL, await server.mint(PROJECT_KEY), "/"));
  await expectUnlocked(page);
  await page.evaluate((hash) => {
    window.location.hash = hash;
  }, route);
}

/** Lets running transitions end, but never waits on an endless one such as a busy spinner. */
async function settle(page: Page): Promise<void> {
  await page.evaluate(() =>
    Promise.race([
      // A cancelled transition rejects its `finished`, and that is as good as done.
      Promise.all(document.getAnimations().map((a) => a.finished.catch(() => undefined))),
      new Promise((done) => setTimeout(done, 500)),
    ]),
  );
}

/** Saves one shot. `viewport` takes the visible window only, for the phone's fixed sheet. */
async function shot(
  page: Page,
  state: string,
  width: number,
  theme: Theme,
  viewport = false,
): Promise<void> {
  mkdirSync(OUT, { recursive: true });
  await settle(page);
  // The sidebar is sticky, so a page scrolled down (a focused message scrolls it) draws the sidebar
  // where the scroll left it, about 100 px low in a full-page capture. Judge F10: that is a capture
  // artefact, not the layout (see the sidebar test below). A full-page shot starts from the top.
  if (!viewport) await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: join(OUT, `${state}-${String(width)}-${theme}.png`),
    fullPage: !viewport,
  });
}

/**
 * Runs one flow for each width and theme, with the settings files put back first. The page leaves
 * and the server finishes any setup read the last variant's page began before the files change,
 * because a read that overlaps a file change answers with the old values (see `waitForSetupRead`).
 */
async function eachVariant(
  world: World,
  page: Page,
  flow: (width: number, theme: Theme) => Promise<void>,
): Promise<void> {
  for (const width of WIDTHS) {
    for (const theme of THEMES) {
      await page.goto("about:blank");
      await waitForSetupRead(world.server);
      restoreFiles(world.fx);
      await flow(width, theme);
    }
  }
}

const saveButton = (page: Page) => page.getByRole("button", { name: /^Save to / });
const scopeRadio = (page: Page, name: RegExp) => page.getByRole("radio", { name });
// An option's name now holds its run line too ("high set now runs at high Lowered"), so the level
// is matched as the first word.
const levelRadio = (page: Page, level: string) =>
  page.getByRole("radio", { name: new RegExp(`^${level}( |$)`) });

async function previewReady(page: Page): Promise<void> {
  await expect(page.getByRole("heading", { level: 3, name: en.ed_this_save_h })).toBeVisible();
}

/** The edit route with the preview drawn and the Project local scope picked. */
async function openEdit(page: Page, world: World, width: number, theme: Theme): Promise<void> {
  await openAt(page, world.server, EDIT, width, theme);
  await previewReady(page);
  await scopeRadio(page, /^Project local/).check({ force: true });
  await expect(page.locator(".this-save")).toContainText("settings.local.json");
}

async function pickLow(page: Page): Promise<void> {
  await levelRadio(page, "low").check({ force: true });
  await expect(page.locator(".this-save")).toContainText("low");
}

// ---------------------------------------------------------------------------------------------
// 1, 2 and 5. The rail and the sheet, This save updating with Save holding, and Save busy.
// ---------------------------------------------------------------------------------------------

test("edit rail, updating with Save held, and Save busy", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      const phone = width === 375;
      // The untouched rail (D2): the picked value and file are what is set now. No error line, no
      // empty diff box and no "xhigh to xhigh" rows. Save is dashed and aria-disabled, stays
      // focusable and is described by the neutral line in This save.
      await openEdit(page, world, width, theme);
      const neutral = page.locator(".this-save-neutral");
      await expect(neutral).toHaveText(en.ed_pick_other);
      await expect(page.locator(".edit-rail-refusal")).toHaveCount(0);
      await expect(page.locator(".this-save .diff")).toHaveCount(0);
      await expect(page.locator(".this-save-dl > div")).toHaveCount(1);
      const idle = saveButton(page);
      await expect(idle).toHaveAttribute("aria-disabled", "true");
      await expect(idle).toHaveAttribute(
        "aria-describedby",
        (await neutral.getAttribute("id")) ?? "",
      );
      await idle.focus();
      await expect(idle).toBeFocused();
      await shot(page, "edit-untouched", width, theme, phone);

      // The Save to rows follow the inspector's order, top wins (D5), and an effort that lands
      // lower says so inside its own option (D6).
      const rows = page.locator(".save-to-row .save-to-scope-name");
      await expect(rows).toHaveText([en.sc_project_local, en.sc_project, en.sc_user]);
      const xhigh = page.getByRole("radio", { name: /^xhigh/ });
      await expect(xhigh).toHaveAccessibleName(
        new RegExp(`${en.ed_now} ${en.ed_opt_runs.replace("{value}", "high")} Lowered`),
      );
      await expect(page.locator(".segmented-choice-hint")).toHaveCount(0);
      // An option that runs as it reads has no run line of its own.
      await expect(page.locator(".segmented-choice-runs")).toHaveCount(1);

      // 1. Effort, Project local picked, This save current (b-edit). At 375 the sheet with its foot.
      await levelRadio(page, "medium").check({ force: true });
      await expect(page.locator(".this-save")).toContainText("medium");
      await expect(page.locator(".this-save-updating")).toHaveCount(0);
      await shot(page, "edit-rail", width, theme, phone);

      // 2. A new pick asks for a new preview. Save pressed meanwhile is held, and reads "Saving".
      let release: () => void = () => undefined;
      const gate = new Promise<void>((done) => {
        release = done;
      });
      await page.route("**/api/edit/preview", async (route) => {
        await gate;
        await route.continue();
      });
      await levelRadio(page, "low").check({ force: true });
      await expect(page.locator(".this-save-updating")).toContainText(en.ed_updating);
      await saveButton(page).click();
      await expect(page.locator(".edit-save-busy:not(.edit-save-hidden)")).toBeVisible();
      await shot(page, "edit-updating", width, theme, phone);
      release();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      await page.unroute("**/api/edit/preview");
    });

    await eachVariant(world, page, async (width, theme) => {
      const phone = width === 375;
      // 5. Save busy: the save is on its way and has no answer yet.
      await openEdit(page, world, width, theme);
      await pickLow(page);
      let release: () => void = () => undefined;
      const gate = new Promise<void>((done) => {
        release = done;
      });
      await page.route("**/api/edit/save", async (route) => {
        await gate;
        await route.continue();
      });
      await saveButton(page).click();
      await expect(page.locator(".edit-save-busy:not(.edit-save-hidden)")).toBeVisible();
      await shot(page, "edit-save-busy", width, theme, phone);
      release();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      await page.unroute("**/api/edit/save");
    });
  });
});

// ---------------------------------------------------------------------------------------------
// 3 and 4. User scope through a link, and a link that leaves the home.
// ---------------------------------------------------------------------------------------------

test("user scope through a link, and link_outside", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      const phone = width === 375;
      // 3. User picked through a link, with the user-scope warning and the projects it reaches
      // (x-symlink).
      await openAt(page, world.server, EDIT, width, theme);
      await previewReady(page);
      await scopeRadio(page, /^User/).check({ force: true });
      await expect(page.locator(".this-save")).toContainText("settings.json");
      await expect(page.getByText(en.ed_links_to).first()).toBeVisible();
      // The link line names the real file with "~" for the home, never a bare file name.
      await expect(page.locator(".save-to-real").first()).toHaveText(
        "~/dotfiles/claude/settings.json",
      );
      // A changed value (judge F3), so the user-scope warning, the diff and the reach line show.
      await levelRadio(page, "medium").check({ force: true });
      await expect(page.locator(".this-save .diff")).toBeVisible();
      await shot(page, "edit-user-link", width, theme, phone);

      // 4. The same link now leaves the home, so its row is refused with link_outside.
      linkUserOutside(world.fx);
      await openAt(page, world.server, EDIT, width, theme);
      await previewReady(page);
      // The refused row can't be picked. It reads "Can't change here", with a lock.
      await expect(scopeRadio(page, /^User/)).toBeDisabled();
      await expect(page.locator(".save-to-blocked")).toContainText(en.ro_h);
      // The row says where the link leads and that the writer won't follow it, and the radio
      // points at that line. The target is outside the home, so the server shows its file name only.
      await expect(page.locator("#save-to-outside-user")).toHaveText(en.ed_link_outside_row);
      await expect(scopeRadio(page, /^User/)).toHaveAttribute(
        "aria-describedby",
        "save-to-outside-user",
      );
      await expect(page.locator(".save-to-real").first()).toHaveText("settings.json");
      await shot(page, "edit-link-outside", width, theme, phone);
    });
  });
});

// ---------------------------------------------------------------------------------------------
// 6. Refused after another program changed the file under the open preview.
// ---------------------------------------------------------------------------------------------

test("refused after a file change, focus on the message", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      await openEdit(page, world, width, theme);
      await pickLow(page);
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      await saveButton(page).click();
      const refusal = page.locator(".refused");
      await expect(refusal).toContainText(en.er_lead);
      await expect(refusal).toBeFocused();
      // x-refused.
      await shot(page, "edit-refused", width, theme, width === 375);
    });
  });
});

// ---------------------------------------------------------------------------------------------
// 7. Saved, with the recheck checking and then confirmed.
// ---------------------------------------------------------------------------------------------

test("saved, checking then confirmed", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      await openEdit(page, world, width, theme);
      await pickLow(page);
      await saveButton(page).click();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      await expect(page.getByText(en.rc_checking)).toBeVisible();
      await shot(page, "saved-checking", width, theme);
      // b-saved.
      await expect(page.getByText(/Checked the file\. It still holds low\./)).toBeVisible({
        timeout: 15_000,
      });
      await shot(page, "saved-confirmed", width, theme);
    });
  });
});

// ---------------------------------------------------------------------------------------------
// 8. Overwritten, with our change kept and with it lost, Review changes open (x-over).
// ---------------------------------------------------------------------------------------------

test("overwritten, our change kept and lost, with Review changes open", async ({ page }) => {
  await inWorld({}, async (world) => {
    for (const kept of [true, false]) {
      await eachVariant(world, page, async (width, theme) => {
        await openEdit(page, world, width, theme);
        await pickLow(page);
        await saveButton(page).click();
        await expect(page.getByText(en.ed_saved)).toBeVisible();
        // Another program writes the file right after the save, before the 2 s recheck.
        // A save of Effort to Project local changes the env twin in that file, so losing our change
        // means the env value goes back.
        rewriteJson(world.fx.localFile, (now) => {
          now.other = true;
          if (!kept) now.env = { CLAUDE_CODE_EFFORT_LEVEL: "xhigh" };
        });
        await expect(page.getByText(en.ed_over)).toBeVisible({ timeout: 15_000 });
        await expect(
          page.getByText(
            kept ? /Your effort change is still in the file/ : /no longer in the file/,
          ),
        ).toBeVisible();
        await page.getByRole("button", { name: en.ed_review_changes }).click();
        await expect(page.getByText(en.ed_drift_h)).toBeVisible();
        await expect(page.locator(".diff").first()).toBeVisible();
        await shot(page, kept ? "over-kept" : "over-lost", width, theme);
      });
    }
  });
});

// ---------------------------------------------------------------------------------------------
// 9. Undo confirm after a change (x-undo).
// ---------------------------------------------------------------------------------------------

test("undo confirm after another program changed the file", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      await openEdit(page, world, width, theme);
      await pickLow(page);
      await saveButton(page).click();
      await expect(page.getByText(en.ed_saved)).toBeVisible();
      rewriteJson(world.fx.localFile, (now) => {
        now.other = true;
      });
      await page.getByRole("button", { name: en.ed_undo }).click();
      const heading = page.getByRole("heading", { name: en.ed_undo_h });
      await expect(heading).toBeVisible();
      await expect(heading).toBeFocused();
      await shot(page, "undo-confirm", width, theme, width === 375);
    });
  });
});

// ---------------------------------------------------------------------------------------------
// 10. Changes with rows in every undo state and recheck outcome (x-history), and a row with its
// undo panel open. Then the same rows with editing off (11, o-changes).
// ---------------------------------------------------------------------------------------------

/**
 * A real save is `checking` for 2 s, so this marks one row `checking` in the history answer the
 * page draws, the way the server would send it in that window. The row is the one that can be
 * undone, whose real outcome is confirmed.
 */
async function markChecking(page: Page): Promise<void> {
  await page.route("**/api/edit/history*", async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as {
      rows: {
        from: unknown;
        to: unknown;
        scope: string;
        recheck: unknown;
        undo_state: string;
      }[];
    };
    for (const row of body.rows) {
      if (row.scope === "user" && row.undo_state === "can_undo") {
        row.recheck = { state: "checking", changed_keys: [], ours_survived: null, seen: false };
      }
    }
    await route.fulfill({ response, json: body });
  });
}

test("Changes with rows in every state, the undo panel, and editing off", async ({ page }) => {
  const fx = buildM6Fixture({ local: false });
  let server: Server | null = null;
  try {
    server = await startReady(fx);
    await seedHistory(server, fx);
    await markChecking(page);
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        // x-history.
        await openAt(page, server, CHANGES, width, theme);
        await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
        await expect(page.locator(".changes-row")).toHaveCount(7);
        await expect(page.getByText(en.cg_deletes_file)).toBeVisible();
        await expect(page.getByText(en.cg_changed_since)).toBeVisible();
        await expect(page.getByText(en.cg_rc_checking)).toBeVisible();
        await expect(page.getByText(en.cg_rc_overwritten).first()).toBeVisible();
        // D8. The overwritten word and its sentence sit on separate lines, a confirmed row says
        // "Still in the file", an undo row reads "Undid ..." with an empty Undo cell, no row says
        // "Can undo", and a save that made the file says so (D9).
        const word = page
          .locator(".changes-recheck-word", { hasText: en.cg_rc_overwritten })
          .first();
        const sentence = page.locator(".changes-recheck-note").first();
        const wordBox = await word.boundingBox();
        const sentenceBox = await sentence.boundingBox();
        expect(sentenceBox?.y ?? 0).toBeGreaterThanOrEqual(
          (wordBox?.y ?? 0) + (wordBox?.height ?? 0) - 1,
        );
        await expect(
          page.locator(".changes-recheck-word", { hasText: en.cg_rc_confirmed }).first(),
        ).toBeVisible();
        await expect(page.getByText("Can undo")).toHaveCount(0);
        const undid = page.locator(".changes-row", { hasText: /^.*Undid / });
        await expect(undid).toHaveCount(1);
        await expect(undid.locator(".changes-undo")).toHaveText(en.cg_col_undo);
        await expect(page.getByText(/set to high in a new file/)).toBeVisible();
        // D14. The column words stay in the page as visually hidden labels (never display:none),
        // and at 375 the header row is gone.
        const label = page.locator(".changes-cell > .sr-only").first();
        expect(await label.evaluate((el) => getComputedStyle(el).display)).not.toBe("none");
        expect(await label.evaluate((el) => el.getBoundingClientRect().width)).toBeLessThanOrEqual(
          1,
        );
        if (width === 375) await expect(page.locator(".changes-head")).toBeHidden();
        // D11. The Checking ring is as big as the check and the triangle and reaches 3:1, and the
        // grey Undo-column text reads AA.
        const read = await readAll(page, {
          ring: ".changes-recheck-word .ring-mark",
          state: ".changes-state",
          note: ".changes-recheck-note",
        });
        expect(read.ring?.ratio, "ring contrast").toBeGreaterThanOrEqual(3);
        expect(read.state?.ratio, "undo state text contrast").toBeGreaterThanOrEqual(4.5);
        expect(read.note?.ratio, "recheck note contrast").toBeGreaterThanOrEqual(4.5);
        const checkWidth = await glyphWidth(
          page,
          '.changes-recheck-word > span[aria-hidden="true"]:not(.ring-mark)',
        );
        expect(Math.abs((read.ring?.width ?? 0) - (checkWidth ?? 0))).toBeLessThanOrEqual(4);
        await shot(page, "changes", width, theme);

        // A row with its undo panel open: the file changed since, so Undo asks first.
        const row = page.locator(".changes-row", { hasText: "high to low" });
        await row.getByRole("button", { name: en.ed_undo }).click();
        await expect(page.getByRole("heading", { name: en.ed_undo_h })).toBeVisible();
        // D1. The panel lists every line Undo removes, including the other program's, in red, and
        // folds the unchanged runs between them into counted rows.
        // The other program removed effortLevel and added includeCoAuthoredBy (the fixture), so
        // the red line is the key it added, and the green line is the effort Undo puts back.
        await expect(
          page.locator(".undo-confirm .diff-del", { hasText: "includeCoAuthoredBy" }),
        ).toHaveCount(1);
        await expect(
          page.locator(".undo-confirm .diff-add", { hasText: "effortLevel" }),
        ).toHaveCount(1);
        // F16. At 375 the panel orders its buttons like the standalone confirm, Undo anyway first.
        const names = await page
          .locator(".undo-confirm .undo-confirm-actions button")
          .allTextContents();
        expect(names).toEqual(
          width === 375
            ? [en.ed_undo_anyway, en.ed_undo_keep]
            : [en.ed_undo_keep, en.ed_undo_anyway],
        );
        await shot(page, "changes-undo-panel", width, theme);

        // D9. "Undo deletes the file" opens the same inline panel, and sends nothing until asked.
        await page.getByRole("button", { name: en.ed_undo_keep }).click();
        const made = page.locator(".changes-row", { hasText: en.cg_deletes_file });
        await made.getByRole("button", { name: en.ed_undo }).click();
        await expect(page.getByRole("heading", { name: en.ed_undo_h })).toBeVisible();
        await expect(page.getByRole("heading", { name: en.ed_undo_h })).toBeFocused();
        // D9b. The panel and its row name the whole path of the file that goes, with "~" for home.
        const whole = "~/work/tidewater-reporting/.claude/settings.local.json";
        await expect(page.locator(".undo-confirm-path .path-text")).toHaveText(whole);
        await expect(made.locator(".changes-file .path-text")).toHaveText(whole);
        await shot(page, "changes-delete-panel", width, theme);
        await page.getByRole("button", { name: en.ed_undo_keep }).click();
      }
    }

    await page.unrouteAll({ behavior: "ignoreErrors" });

    // The same data folder read again with editing off, as after a restart without the flag.
    const port = server.port;
    await server.stop();
    server = await startReady(fx, { edits: false, port });
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        // o-changes.
        await openAt(page, server, CHANGES, width, theme);
        await expect(page.getByRole("heading", { level: 1, name: en.cg_h1 })).toBeVisible();
        await expect(page.getByText(en.eo_hist_note.replace("{cmd}", OFF_CMD))).toHaveCount(1);
        await shot(page, "off-changes", width, theme);
      }
    }
  } finally {
    if (server !== null) await server.stop();
    fx.cleanup();
  }
});

// ---------------------------------------------------------------------------------------------
// 10 (empty Changes), 12 and 13, on a server with editing on and no saves yet.
// ---------------------------------------------------------------------------------------------

test("Changes empty, a field waiting for M7, and the agents pages", async ({ page }) => {
  await inWorld({ userExtra: { alwaysThinkingEnabled: true } }, async (world) => {
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        await openAt(page, world.server, CHANGES, width, theme);
        await expect(page.getByRole("heading", { level: 2, name: en.cg_empty_h })).toBeVisible();
        await shot(page, "changes-empty", width, theme);

        // 12. A Settings item that waits for M7 says so and offers no Edit.
        await openAt(
          page,
          world.server,
          `/p/${PROJECT_KEY}/setup/settings/alwaysThinkingEnabled`,
          width,
          theme,
        );
        await expect(page.getByText(en.ro_field_until_m7)).toBeVisible();
        await expect(page.getByRole("link", { name: /^Edit / })).toHaveCount(0);
        await shot(page, "field-until-m7", width, theme);

        // 13. The agents the setup finds, with the read-only line and no Add an agent or Edit.
        await openAt(page, world.server, `/p/${PROJECT_KEY}/setup/agents/builder`, width, theme);
        await expect(page.getByRole("heading", { level: 2, name: "builder" })).toBeVisible();
        await expect(page.getByRole("button", { name: /Add an agent/ })).toHaveCount(0);
        await expect(page.getByRole("link", { name: /^Edit / })).toHaveCount(0);
        await shot(page, "agents-setup", width, theme);

        // The review page of Agents. The made-up project has no sessions, so it is empty.
        await openAt(page, world.server, `/p/${PROJECT_KEY}/review/agents`, width, theme);
        await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
        await expect(page.getByRole("button", { name: /Add an agent/ })).toHaveCount(0);
        await shot(page, "agents-review", width, theme);

        // An agent edit URL lands on Your setup > Agents with that agent selected, and focus on a
        // one-line note (D7). It never lands on Review > Agents.
        await openAt(
          page,
          world.server,
          `/p/${PROJECT_KEY}/review/agents/builder/edit`,
          width,
          theme,
        );
        await expect(page).toHaveURL(/\/setup\/agents\/builder\/edit$/);
        await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
        const note = page.locator(".edits-off-agent");
        await expect(note).toHaveText(en.eo_route_agent.replace("{name}", "builder"));
        await expect(note).toBeFocused();
        await expect(page.getByRole("heading", { level: 2, name: "builder" })).toBeVisible();
        await shot(page, "agent-edit-url", width, theme);
      }
    }
  });
});

// ---------------------------------------------------------------------------------------------
// 11. Editing off, against the boards o-insp, o-plugin, o-route and the foot lines.
// ---------------------------------------------------------------------------------------------

test("editing off, inspector, plugin agent, route note and foot lines", async ({ page }) => {
  await inWorld({ edits: false }, async (world) => {
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        // o-insp. Edit stays in the foot, aria-disabled, with the reason line.
        await openAt(page, world.server, ITEM, width, theme);
        await expect(page.getByText(en.eo_reason.replace("{cmd}", OFF_CMD))).toBeVisible();
        await shot(page, "off-inspector", width, theme);

        // o-plugin. A plugin agent's inspector, read only.
        await openAt(
          page,
          world.server,
          `/p/${PROJECT_KEY}/setup/agents/linter-kit:linter`,
          width,
          theme,
        );
        await expect(page.getByRole("heading", { level: 2, name: "linter" })).toBeVisible();
        // F11. The reason box has its "Can't change here" title with the help button on its row,
        // and the path with Copy path in one row, as on the board.
        const box = page.locator(".inspector-readonly");
        await expect(box.locator(".inspector-readonly-head")).toContainText(en.ro_h);
        await expect(box.locator(".inspector-readonly-head .help-button")).toBeVisible();
        await expect(box.locator(".inspector-readonly-path")).toContainText("linter.md");
        await expect(
          box.locator(".inspector-readonly-path").getByRole("button", { name: en.in_copy }),
        ).toBeVisible();
        await shot(page, "off-plugin", width, theme);

        // o-route. An edit URL renders the item with focus on the note. The reason line under Edit
        // says the same, so it waits while the note shows (F12).
        await openAt(page, world.server, EDIT, width, theme);
        await expect(page.getByText(/opened without its editor/)).toBeVisible();
        await expect(page.getByText(en.eo_reason.replace("{cmd}", OFF_CMD))).toHaveCount(0);
        // F13. The focused note is not a control, so its ring is the light one, and still 3:1.
        await expect(page.locator(".edits-off-route")).toBeFocused();
        const ring = await outlineOf(page, ".edits-off-route");
        expect(ring?.width).toBe(2);
        expect(ring?.ratio ?? 0).toBeGreaterThanOrEqual(3);
        await shot(page, "off-route", width, theme);

        if (width === 1440) {
          // The sidebar foot line. The phone has no sidebar.
          await openAt(page, world.server, ITEM, width, theme);
          await expect(page.getByRole("button", { name: en.eo_ft_off })).toBeVisible();
          await shot(page, "off-foot", width, theme);
        } else {
          // The More page line. At 721px and up #/more lands on Live, so it has no 1440 shot.
          await openAt(page, world.server, "/more", width, theme);
          await expect(page.getByText(en.eo_more_off, { exact: true })).toBeVisible();
          await shot(page, "off-more", width, theme);
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------------------------
// 11. The restart box in both modes (o-restart). The server's answer is made here, as it would send
// it after a restart, because the page's keys die with a real restart (the M3 gate).
// ---------------------------------------------------------------------------------------------

test("restart box when the new server has editing on, and off", async ({ page }) => {
  await inWorld({}, async (world) => {
    await eachVariant(world, page, async (width, theme) => {
      const phone = width === 375;
      // The new server has editing on, and no longer knows this page's edit key.
      await openEdit(page, world, width, theme);
      await pickLow(page);
      await page.route("**/api/edit/save", (route) =>
        route.fulfill({ status: 403, json: { code: "edit_key_unknown" } }),
      );
      await saveButton(page).click();
      const on = page.locator(".restart-box");
      await expect(on).toContainText(en.eo_restart_on_h);
      await expect(on).toBeFocused();
      // D3. The whole rail is inert: Save is dashed and aria-disabled, described by the box, the
      // value control and the Save to rows are locked, and Reload is the only live primary action.
      await expect(saveButton(page)).toHaveAttribute("aria-disabled", "true");
      await expect(saveButton(page)).toHaveAttribute(
        "aria-describedby",
        (await on.getAttribute("id")) ?? "",
      );
      await expect(levelRadio(page, "low")).toBeDisabled();
      await expect(scopeRadio(page, /^Project local/)).toBeDisabled();
      await expect(
        page.locator('.edit-rail .button-primary:not([aria-disabled="true"])'),
      ).toHaveText(en.eo_reload);
      await shot(page, "restart-on", width, theme, phone);
      await page.unroute("**/api/edit/save");

      // The new server has editing off, so it names the command that turns it on.
      await openEdit(page, world, width, theme);
      await pickLow(page);
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
      await saveButton(page).click();
      const off = page.locator(".restart-box");
      await expect(off).toContainText(en.eo_restart_h);
      await expect(off).toContainText(OFF_CMD);
      await expect(off).toBeFocused();
      await page.waitForTimeout(1500);
      await expect(off).toBeVisible();
      await shot(page, "restart-off", width, theme, phone);
      await page.unrouteAll({ behavior: "ignoreErrors" });
    });
  });
});

// ---------------------------------------------------------------------------------------------
// D12. A demo run. The owner can't turn editing on there, so there is no dashed Edit button at
// all. The inspector shows the lock box with its reason instead.
// ---------------------------------------------------------------------------------------------

test("a demo run shows the lock box and no Edit button", async ({ page }) => {
  // The server reports `unavailable` only for a run whose folders sit inside the Bar Tab checkout,
  // and a test run keeps them outside it. So the demo server's /api/app answer is made here, as the
  // server would send it for a run in the checkout (the restart test does the same).
  const server = await startServer({
    fixture: null,
    args: ["--demo", "--no-price-fetch", "--test-clock"],
  });
  try {
    await page.route(/\/api\/app(\?|$)/, async (route) => {
      const response = await route.fetch();
      const body = (await response.json()) as { edits: { state: string } };
      body.edits.state = "unavailable";
      await route.fulfill({ response, json: body });
    });
    for (const width of WIDTHS) {
      for (const theme of THEMES) {
        await openAt(page, server, ITEM, width, theme);
        const box = page.locator(".inspector-readonly");
        await expect(box).toContainText(en.ro_h);
        await expect(box).toContainText(en.eo_reason_demo);
        await expect(page.getByRole("button", { name: /^Edit / })).toHaveCount(0);
        await expect(page.getByRole("link", { name: /^Edit / })).toHaveCount(0);
        await shot(page, "off-demo", width, theme);
      }
    }
  } finally {
    await server.stop();
    rmSync(server.dataDir, { recursive: true, force: true });
  }
});

// ---------------------------------------------------------------------------------------------
// D10 (judge F10). The sidebar sits at the top of the window whatever the page scroll, so the
// offset in the banner shots was the full-page capture and not the layout.
// ---------------------------------------------------------------------------------------------

test("the sidebar stays at the top of a 900 px window when the page is scrolled", async ({
  page,
}) => {
  await inWorld({}, async (world) => {
    await openEdit(page, world, 1440, "light");
    await pickLow(page);
    await page.route("**/api/edit/save", (route) =>
      route.fulfill({ status: 403, json: { code: "edit_key_unknown" } }),
    );
    await saveButton(page).click();
    await expect(page.locator(".restart-box")).toBeFocused();
    const top = async (): Promise<number> =>
      page.evaluate(() => document.querySelector(".sidebar")?.getBoundingClientRect().top ?? -1);
    expect(await top()).toBe(0);
    await page.evaluate(() => window.scrollTo(0, 120));
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    expect(await top()).toBe(0);
    await page.unrouteAll({ behavior: "ignoreErrors" });
  });
});
