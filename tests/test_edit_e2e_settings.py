"""End-to-end checks of the effort cap, the model and the compact window on Settings (#120, #122). Opt in with MR_E2E=1.

Built on tests/test_edit_e2e.py (its world, selectors and helpers, not copied). Each case changes one setting from the
page, saves, then presses Undo and compares the shared file with a copy made before the write, byte for byte. Two cases
pick and then press Cancel, and prove that nothing was written. One case presses Start with the cap on the Effort cell
and follows it to the cap's review.

The world is a small made-up fixture in a temp root, with the server on it (--fixture and --allow-edits). The project's
shared settings.json holds a model line, an effort line (low), a cap line (medium) and a compact window line (200000).
No local file exists, so a first pick of a model or a window preselects creating it, and the cases then press the
project row to write the shared file. A cap pick preselects nothing: the lowest cap applies, so a cap above the shared
one only takes effect in the shared file, and the rail asks for a file until the case presses the project row
(EditSettingsApi.test_first_picks_preselect_what_the_browser_cases_expect). Nothing reads or writes the real ~/.claude.

Importing this module starts nothing. EditSettingsApi runs on every suite run with no browser, so the world is proven
valid even where nobody runs Chrome. The browser classes need Chrome and skip unless MR_E2E=1. The owner runs them with

    MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_edit_e2e_settings.py"

Selectors, from dashboard/static/js/edit_card.js, edit_review.js and pages/where.js, on top of those in test_edit_e2e.py:
- nav.s5-a a.s4-stat[data-setting=maxEffortLevel|model|autoCompactWindow|effortLevel] is the band cell of each setting. The
  page opens one with ?setting=<key> in the address.
- The effort cap cell has the level radios of the Effort cell (input[name=p2-level]), under the label "Effort cap".
- select#p2-model is the model pop-up. A script sets its value and fires change.
- input#p2-compact is the compact window box (inputmode numeric), committed on change. button[data-edit-focus="btn:auto"] is Auto.
- button[data-edit-focus="btn:startcap"] is Start with the cap, in the rail of a level that takes two changes.
"""
import json
import os
import unittest
import urllib.parse

import helpers
import test_edit_e2e as e2e
import test_pages_e2e as pages
import test_shell_e2e as shell

SETTINGS = e2e.SETTINGS
STRINGS = e2e.STRINGS
js = e2e.js

CAP = "maxEffortLevel"
MODEL = "model"
WINDOW = "autoCompactWindow"
EFFORT = "effortLevel"

START_MODEL = "claude-sonnet-5-5"
OTHER_MODEL = "claude-opus-5-5"
START_EFFORT = "low"
START_CAP = "medium"
START_WINDOW = 200000

# The shared project file. The model makes the effort levels known, so the cap panel has levels to pick.
SHARED = {"model": START_MODEL, "effortLevel": START_EFFORT, "maxEffortLevel": START_CAP, "autoCompactWindow": START_WINDOW}

PAGE = e2e.PAGE
MODEL_SELECT = PAGE + " select#p2-model"
COMPACT_BOX = PAGE + " input#p2-compact"
AUTO = PAGE + " button[data-edit-focus='btn:auto']"
START_CAP_BUTTON = e2e.RAIL + " button[data-edit-focus='btn:startcap']"
CHECKED_RADIO = e2e.RADIO + ":checked"


def band_cell(key):
    return PAGE + " nav.s5-a a.s4-stat[data-setting=" + key + "]"


# Pure page scripts. Each is an expression, and the two that change a control say so in their names.
SET_AND_CHANGE = "(() => { const el = document.querySelector(%s); if (!el || el.disabled) return false; " \
                 "el.value = %s; el.dispatchEvent(new Event('change', { bubbles: true })); return true; })()"
CHECKED_VALUE = "(() => { const el = document.querySelector(%s); return el ? el.value : null; })()"


def shared_with(**changes):
    out = dict(SHARED)
    out.update(changes)
    return out


def level_in_file(world, key):
    return json.loads(world.settings_bytes().decode("utf-8")).get(key)


# ---------------------------------------------------------------- no browser

class EditSettingsApi(unittest.TestCase):
    """The same world over HTTP, with the headers the page sends. It always runs and starts no browser."""

    @classmethod
    def setUpClass(cls):
        cls.world = e2e.build_world("mr-e2e-edit-settings-api-", shared=SHARED)

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def headers(self, write=False):
        out = {"Origin": self.world.base.rstrip("/"), "Sec-Fetch-Site": "same-origin"}
        if write:
            out["Content-Type"] = "application/json"
            out["X-Dashboard-Token"] = self.world.token
        return out

    def get(self, path):
        status, _heads, data = self.world.srv.request("GET", path, headers=self.headers())
        self.assertEqual(status, 200, (path, data[:300]))
        return json.loads(data)

    def post(self, path, body, expect=200):
        status, _heads, data = self.world.srv.request(
            "POST", path, headers=self.headers(write=True), body=json.dumps(body).encode("utf-8"))
        self.assertEqual(status, expect, (path, data[:300]))
        return json.loads(data)

    def targets(self, setting):
        return self.get("/api/edit/targets?setting=" + setting)

    def project_target(self, setting):
        rows = [t for t in self.targets(setting)["targets"] if t["layer"] == "project"]
        self.assertEqual(len(rows), 1, (setting, rows))
        return rows[0]

    def round_trip(self, setting, value):
        """Preview, save and undo at the project file, and prove the bytes are back."""
        w = self.world
        before = w.settings_bytes()
        found = self.targets(setting)
        target = self.project_target(setting)
        body = {"project": found["project"], "target": target["target"], "value": value, "setting": setting}
        preview = self.post("/api/edit/preview", body)
        self.assertEqual(preview["setting"], setting)
        self.assertIs(preview["no_change"], False)
        self.assertEqual(w.settings_bytes(), before, "a preview wrote the file")
        saved = self.post("/api/edit/save", dict(body, base_file=preview["base_file"], base_trail=preview["base_trail"],
                                                 base_others=preview["base_others"]))
        self.assertNotEqual(w.settings_bytes(), before)
        self.assertEqual(level_in_file(w, setting), value)
        self.assertEqual(saved["edit"]["key_path"][-1], setting)
        undone = self.post("/api/edit/undo", {"project": found["project"], "edit": saved["edit"]["id"]})
        self.assertIs(undone["matches_backup"], True)
        self.assertEqual(w.settings_bytes(), before, "the undo did not restore the bytes")

    def test_world_is_throwaway_and_holds_the_four_lines(self):
        w = self.world
        self.assertTrue(w.folder.startswith(w.root + os.sep))
        self.assertFalse(os.path.realpath(w.root).startswith(os.path.realpath(helpers.REPO) + os.sep))
        self.assertEqual(json.loads(w.settings_bytes()), SHARED)
        self.assertFalse(w.local_exists())

    def test_the_cap_changes_and_undoes(self):
        self.round_trip(CAP, "high")

    def test_the_model_changes_and_undoes(self):
        self.round_trip(MODEL, OTHER_MODEL)

    def test_the_compact_window_changes_and_undoes(self):
        self.round_trip(WINDOW, 300000)

    def test_an_effort_level_above_the_cap_takes_two_changes(self):
        found = self.targets(EFFORT)
        levels = {row["level"]: row for row in found["levels"]}
        self.assertEqual(levels[START_EFFORT]["result"], "now")
        high = levels["high"]
        self.assertIs(high["cap_first"], True, high)
        self.assertIs(high["saveable"], True)
        self.assertEqual([(l["kind"], l["editable"], l["via"]) for l in high["limits"]], [("cap", True, "cap")])
        cap_target = self.project_target(CAP)["target"]
        self.assertEqual(high["limits"][0]["target"], cap_target, "Start with the cap changes the cap's own line")

    def test_first_picks_preselect_what_the_browser_cases_expect(self):
        """The browser cases wait on a rail that follows from these rows. A model or a window pick preselects the local
        create (preview_at_project_row). A cap pick above the shared cap preselects nothing, because the lowest cap
        applies and only the shared file can raise it (cap_preview_at_project_row). Start with the cap lands on the same
        cap row, so it follows the cap's rule."""
        local = {}
        for setting, level in ((MODEL, OTHER_MODEL), (WINDOW, "number")):
            found = self.targets(setting)
            row = next(r for r in found["levels"] if r["level"] == level)
            local[setting] = next(f["target"] for f in row["files"] if f["layer"] == "local")
            self.assertEqual(row["preselect"], local[setting], (setting, row))
        cap_rows = {r["level"]: r for r in self.targets(CAP)["levels"]}
        for level in ("high", "xhigh"):
            row = cap_rows[level]
            self.assertIs(row["saveable"], True, row)
            self.assertIsNone(row["preselect"], row)
            files = {f["layer"]: (f["effect"], f["pickable"]) for f in row["files"]}
            self.assertEqual(files["project"], ("applies", True), row)
            self.assertEqual(files["local"], ("wont_apply", False), row)

    def test_each_cell_answers_its_own_levels(self):
        self.assertEqual([r["level"] for r in self.targets(CAP)["levels"]], ["low", "medium", "high", "xhigh", "max"])
        self.assertEqual([r["level"] for r in self.targets(WINDOW)["levels"]], ["auto", "number"])
        model = self.targets(MODEL)
        self.assertIn(OTHER_MODEL, [r["level"] for r in model["levels"]])
        self.assertEqual(model["runs_as"], START_MODEL)

    def test_a_cap_preview_writes_nothing(self):
        w = self.world
        before = w.settings_bytes()
        found = self.targets(CAP)
        target = self.project_target(CAP)
        preview = self.post("/api/edit/preview", {"project": found["project"], "target": target["target"], "value": "xhigh",
                                                   "setting": CAP})
        self.assertEqual((preview["old_value"], preview["new_value"]), (START_CAP, "xhigh"))
        self.assertEqual(w.settings_bytes(), before)
        self.assertFalse(w.local_exists())


# ---------------------------------------------------------------- Chrome

class _SettingsBase(e2e._WorldPerTest):
    """A fresh world for each test, with the four lines in the shared file and no local file."""

    def new_settings_world(self, **changes):
        return self.new_world(shared=shared_with(**changes))

    def open_cell(self, key, width=1440):
        """Open Settings on a cell with the token in the address, as the printed link does."""
        hash_ = SETTINGS + "?setting=" + urllib.parse.quote(key, safe="") + "&edit=" + urllib.parse.quote(self.world.token, safe="")
        self.page.open(self.world.base + hash_, width)
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.wait_settings()
        self.page.wait_for(js("document.querySelector(%s).getAttribute('aria-current') === 'true'", band_cell(key)))

    def wait_levels(self):
        self.page.wait_for(e2e.HAS_RADIO)

    def wait_checked(self, level):
        """The level radio that is checked is this one."""
        self.page.wait_for("(%s) === %s" % (js(CHECKED_VALUE, CHECKED_RADIO), json.dumps(level)))

    def wait_model_select(self):
        self.wait_present(MODEL_SELECT)

    def wait_compact_box(self):
        self.wait_present(COMPACT_BOX)

    def set_value(self, selector, value):
        self.page.wait_for(js(SET_AND_CHANGE, selector, value))

    def wait_review(self):
        """The review is up: the rail heading, a diff, and Save on."""
        self.wait_present(e2e.RAIL_HEAD, e2e.DIFF)
        self.page.wait_for(js(e2e.IS_ON, e2e.SAVE))

    def preview_at_project_row(self):
        """The first pick preselects creating the local file. Press the project row so the shared file is the one written."""
        self.wait_review()
        self.pick_project_row()

    def wait_pick_file(self):
        """The rail of a level with no preselect: its heading and the Pick a file line, no diff, and Save off."""
        self.wait_present(e2e.RAIL_HEAD)
        self.page.wait_for(e2e.PICK_NOTE)
        self.assertEqual(self.count(e2e.DIFF), 0, "a diff before a file was picked")
        self.assertFalse(self.page.eval(js(e2e.IS_ON, e2e.SAVE)), "Save is on before a file was picked")

    def cap_preview_at_project_row(self):
        """A cap pick preselects nothing, because only the shared file can raise the cap. Press the project row, then
        the review is up."""
        self.wait_pick_file()
        self.pick_project_row()
        self.wait_review()

    def save_and_undo(self, copy, expect_key, expect_value):
        """Save, check what the file holds, press Undo, and compare the shared file with the copy made before."""
        w = self.world
        self.click(e2e.SAVE)
        self.wait_saved()
        self.assertEqual(level_in_file(w, expect_key), expect_value)
        self.assertFalse(w.local_exists(), "the save went to the local file")
        self.click(e2e.UNDO)
        self.wait_undone()
        self.assertTrue(w.same_as_copy(copy), "the undo did not bring back the bytes")
        self.assertFalse(w.local_exists())


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditSettingsWrites(_SettingsBase):
    def test_cap_change_then_undo(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-cap.json")
        self.open_cell(CAP)
        self.wait_levels()
        self.wait_checked(START_CAP)
        self.page.wait_for(js(e2e.CLICK_LEVEL, "high"))
        self.cap_preview_at_project_row()
        self.assertEqual(self.text_of(e2e.RAIL + " .s4-chg .s4-to"), "high")
        self.assertEqual(self.text_of(e2e.RAIL + " .s4-chg .s4-was"), START_CAP)
        self.assertTrue(w.same_as_copy(copy), "a preview wrote the file")
        self.save_and_undo(copy, CAP, "high")

    def test_model_change_then_undo(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-model.json")
        self.open_cell(MODEL)
        self.wait_model_select()
        self.set_value(MODEL_SELECT, OTHER_MODEL)
        self.preview_at_project_row()
        self.assertTrue(w.same_as_copy(copy), "a preview wrote the file")
        self.save_and_undo(copy, MODEL, OTHER_MODEL)

    def test_compact_change_then_undo(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-compact.json")
        self.open_cell(WINDOW)
        self.wait_compact_box()
        self.set_value(COMPACT_BOX, "300,000")
        self.preview_at_project_row()
        self.assertTrue(w.same_as_copy(copy), "a preview wrote the file")
        self.save_and_undo(copy, WINDOW, 300000)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditSettingsCancel(_SettingsBase):
    def cancelled(self, start_state, copy):
        w = self.world
        self.click(e2e.CANCEL)
        self.wait_gone(e2e.CANCEL)
        self.assertTrue(w.same_as_copy(copy), "Cancel left the file changed")
        self.assertFalse(w.local_exists(), "the pick created the local file")
        self.assertEqual(w.project_state(), start_state)
        self.assertEqual(w.backups(), [], "a backup was written")

    def test_cap_pick_then_cancel_writes_nothing(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-cap-cancel.json")
        start = w.project_state()
        self.open_cell(CAP)
        self.wait_levels()
        self.page.wait_for(js(e2e.CLICK_LEVEL, "xhigh"))
        self.cap_preview_at_project_row()
        self.assertEqual(w.project_state(), start, "picking a level wrote something")
        self.cancelled(start, copy)

    def test_model_pick_then_cancel_writes_nothing(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-model-cancel.json")
        start = w.project_state()
        self.open_cell(MODEL)
        self.wait_model_select()
        self.set_value(MODEL_SELECT, OTHER_MODEL)
        self.wait_review()
        self.assertEqual(w.project_state(), start, "picking a model wrote something")
        self.cancelled(start, copy)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditStartWithCap(_SettingsBase):
    def test_start_with_the_cap_reaches_the_cap_review(self):
        w = self.new_settings_world()
        copy = w.copy_settings("shared-before-start-cap.json")
        start = w.project_state()
        self.open_cell(EFFORT)
        self.wait_levels()
        # high is above both the effort line (low) and the cap (medium), so it takes two changes. The rail says so, has
        # no file rows to pick and no Save, and offers Start with the cap.
        self.page.wait_for(js(e2e.CLICK_LEVEL, "high"))
        self.wait_present(START_CAP_BUTTON)
        self.assertEqual(self.count(e2e.DIFF), 0, "no diff for a level that needs the cap first")
        self.assertEqual(self.count(e2e.SAVE), 0, "there is no Save in a two-change stop")
        self.assertEqual(w.project_state(), start, "picking a level wrote something")

        self.click(START_CAP_BUTTON)
        # The Effort cap cell opens with the same level chosen, and its review is of the cap line.
        self.page.wait_for("location.href.includes('setting=maxEffortLevel')")
        self.page.wait_for(js("document.querySelector(%s).getAttribute('aria-current') === 'true'", band_cell(CAP)))
        self.wait_levels()
        self.wait_checked("high")
        self.cap_preview_at_project_row()
        self.assertEqual(self.text_of(e2e.RAIL + " .s4-chg .s4-to"), "high")
        self.assertEqual(self.text_of(e2e.RAIL + " .s4-chg .s4-was"), START_CAP)
        self.assertTrue(w.same_as_copy(copy), "Start with the cap wrote the file")
        self.assertFalse(w.local_exists())


if __name__ == "__main__":
    unittest.main()
