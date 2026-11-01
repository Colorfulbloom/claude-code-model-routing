"""End-to-end checks of the owner check path on the Effort cell of Settings (#88, #87). Opt in with MR_E2E=1.

The path is: open the printed link, pick a level, pick the project file, read the review and the diff in the rail,
press Save, read the result in the foot, press Undo, then compare the file with the backup it came from. Built on
test_shell_e2e (its Chrome and Page), test_pages_e2e (add_query, DATA_RENDERED) and test_settings_e2e (its contrast
scripts, not copied).

The world is a small made-up fixture in a temp root. The server runs with --fixture and --allow-edits on it,
with HOME and the config folder inside the same root, and with no CLAUDE_CODE_EFFORT_LEVEL in its environment
(a shell value would beat the file). The project's settings.json holds "effortLevel": "high" at the top level.
That value wins, so a level such as medium is reachable and a preview shows no warning. The line sits in the
project file, which is shared, so no level preselects a file (preselect is the local file or null) and the path
must press the project row before Save. Nothing reads or writes the real ~/.claude.

Importing this module starts nothing. build_world() and the page scripts are pure. EditApi runs on every
suite run, with no browser, so the world is proven valid even where nobody runs Chrome. EditPath and EditLook
need Chrome and skip unless MR_E2E=1.

Selectors, from dashboard/static/js/edit_card.js, edit_review.js, edit_foot.js and pages/where.js:
- nav.s5-a a.s4-stat[data-setting=effortLevel] is the band cell, is-on and aria-current when open. Effort is open on load.
- .s4-run holds the level radios, input[name=p2-level][value=<level>] (class sr, so a script clicks it).
- .s6-rows holds the file rows. At rest they are div.s6-r. Once a level can be saved they are label.s6-r around
  input[name=p2-row][value=<layer>], and the picked one has is-pick.
- aside.s4-rail holds the review: h2.s4-rh, .s4-chg, .s4-note (Pick a file), .s4-dl, figure.p2-df with li.p2-del and
  li.p2-add as its changed lines.
- .s4-rf is the foot. button[data-edit-focus="btn:save"], "btn:undo" and "btn:dismiss-strip" are the buttons,
  .s4-ok is the result line and .s4-hint .pa the backup or restored-from path.
"""
import json
import os
import unittest
import urllib.parse

import helpers
import test_pages_e2e as pages
import test_server as ts
import test_settings_e2e as settings_e2e
import test_shell_e2e as shell

SETTINGS = settings_e2e.SETTINGS
START_LEVEL = "high"
OTHER_LEVELS = ("medium", "low")

PAGE = "[data-page=settings]"
BAND_CELL = PAGE + " nav.s5-a a.s4-stat[data-setting=effortLevel]"
RUN = PAGE + " .s4-run"
RADIO = RUN + " input[name=p2-level]"
ROWS = PAGE + " .s6-rows"
PROJECT_ROW = ROWS + " input[name=p2-row][value=project]"
PICKED_ROWS = ROWS + " label.s6-r.is-pick"
RAIL = PAGE + " aside.s4-rail"
RAIL_HEAD = RAIL + " .s4-rh"
RAIL_NOTE = RAIL + " .s4-note"
RAIL_AFTER = RAIL + " .s4-dl"
DIFF = RAIL + " figure.p2-df"
FOOT = PAGE + " .s4-rf"
SAVE = FOOT + " button[data-edit-focus='btn:save']"
UNDO = FOOT + " button[data-edit-focus='btn:undo']"
STRIP_LINE = FOOT + " .s4-ok"
STRIP_PATH = FOOT + " .s4-hint .pa"
PICK_FILE_LINE = "Pick a file to see the exact change."

# Pure page scripts. Each is an expression with no side effect unless its name says it clicks.
HAS_RADIO = "Boolean(document.querySelector(%s))" % json.dumps(RADIO)
LOCATION_HREF = "location.href"
BODY_OVERFLOW = "document.documentElement.getAttribute('data-ox')"
CLICK_LEVEL = "(() => { const el = document.querySelector(%s + \"[value='\" + %%s + \"']\"); " \
              "if (!el || el.disabled) return false; el.click(); return true; })()" % json.dumps(RADIO)
CLICK_BUTTON = "(() => { const el = document.querySelector(%s); if (!el || el.disabled) return false; " \
               "el.click(); return true; })()"
# The Pick a file line, by its text. Other rail notes (the shared-file line, a still-holds line) stay after a pick.
PICK_NOTE = "[...document.querySelectorAll(%s)].some((el) => el.textContent.trim() === %s)" \
            % (json.dumps(RAIL_NOTE), json.dumps(PICK_FILE_LINE))
IS_ON = "(() => { const el = document.querySelector(%s); return Boolean(el) && !el.disabled; })()"
READ_TEXT = "(() => { const el = document.querySelector(%s); return el ? el.textContent.trim() : null; })()"
DIFF_LINES = "(() => { const read = (sel) => [...document.querySelectorAll(%s + ' ' + sel)]" \
             ".map((el) => el.textContent.replace(/\\s+/g, ' ').trim()); " \
             "return { del: read('li.p2-del'), add: read('li.p2-add') }; })()" % json.dumps(DIFF)
ROW_COUNT = "document.querySelectorAll(%s + ' label.s6-r').length" % json.dumps(ROWS)


def js(template, *values):
    """Fill a page script template with JSON-quoted values."""
    return template % tuple(json.dumps(v) for v in values)


# ---------------------------------------------------------------- the world

class World:
    """A temp root, the fixture in it, and the server on it. close() stops the server and removes the root."""

    def __init__(self, root, folder, settings_path, env, srv):
        self.root = root
        self.folder = folder
        self.settings_path = settings_path
        self.env = env
        self.srv = srv
        self.link = srv.url
        self.token = srv.token
        self.base = "http://127.0.0.1:%d/" % srv.port

    def settings_bytes(self):
        with open(self.settings_path, "rb") as fh:
            return fh.read()

    def real_path(self, display):
        """The file a displayed path names. The fixture shows paths relative to its folder."""
        if os.path.isabs(display) or display.startswith("~"):
            raise AssertionError("expected a path relative to the fixture folder, got %r" % display)
        return os.path.join(self.folder, *display.split("/"))

    def close(self):
        try:
            self.srv.stop()
        finally:
            helpers.rmtree_force(self.root)


def build_fixture(folder):
    """Write the made-up fixture: no shell env, no flags, an empty config folder and one project file."""
    ts.write_json(os.path.join(folder, "session.json"), {"shell_env": {}, "flags": [], "cli_settings": None})
    os.makedirs(os.path.join(folder, "config"))
    ts.write(os.path.join(folder, "project", ".claude", "settings.json"),
             json.dumps({"effortLevel": START_LEVEL}, indent=2) + "\n")
    return os.path.join(folder, "project", ".claude", "settings.json")


def build_world(prefix="mr-e2e-edit-"):
    """Make the root, the fixture and the server with --allow-edits. Returns a World; the caller closes it."""
    root = ts.make_root(prefix)
    try:
        folder = os.path.join(root, "fixture")
        settings_path = build_fixture(folder)
        env = ts.base_env(root)
        env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
        srv = ts.start(root, ["--fixture", folder, "--allow-edits"], env=env)
        return World(root, folder, settings_path, env, srv)
    except BaseException:
        helpers.rmtree_force(root)
        raise


def current_level(world):
    return json.loads(world.settings_bytes().decode("utf-8"))["effortLevel"]


# ---------------------------------------------------------------- no browser

class EditApi(unittest.TestCase):
    """The same path over HTTP, with the headers the page sends. It always runs and starts no browser."""

    @classmethod
    def setUpClass(cls):
        cls.world = build_world("mr-e2e-edit-api-")

    @classmethod
    def tearDownClass(cls):
        cls.world.close()

    def headers(self, write=False, token=None):
        out = {"Origin": self.world.base.rstrip("/"), "Sec-Fetch-Site": "same-origin"}
        if write:
            out["Content-Type"] = "application/json"
            out["X-Dashboard-Token"] = self.world.token if token is None else token
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

    def test_world_is_throwaway(self):
        w = self.world
        self.assertIsNone(w.env.get("CLAUDE_CODE_EFFORT_LEVEL"))
        self.assertTrue(w.env["HOME"].startswith(w.root + os.sep))
        self.assertTrue(w.env["CLAUDE_CONFIG_DIR"].startswith(w.root + os.sep))
        self.assertTrue(w.folder.startswith(w.root + os.sep))
        self.assertTrue(os.path.realpath(w.folder).startswith(os.path.realpath(w.root) + os.sep))
        self.assertFalse(os.path.realpath(w.root).startswith(os.path.realpath(helpers.REPO) + os.sep))
        self.assertRegex(w.link, r"^http://127\.0\.0\.1:\d+/#/settings\?edit=[A-Za-z0-9_-]+$")
        self.assertEqual(json.loads(w.settings_bytes()), {"effortLevel": START_LEVEL})

    def test_preview_save_and_undo_restore_the_bytes(self):
        w = self.world
        before = w.settings_bytes()
        info = self.get("/api/edit")
        self.assertIs(info["enabled"], True)
        found = self.get("/api/edit/targets")
        self.assertIs(found["enabled"], True)
        project = found["project"]
        targets = [t for t in found["targets"] if t["layer"] == "project"]
        self.assertEqual(len(targets), 1, found["targets"])
        target = targets[0]
        self.assertEqual(target["current_value"], START_LEVEL)
        levels = {row["level"]: row for row in found["levels"]}
        self.assertEqual(levels[START_LEVEL]["result"], "now")
        level = OTHER_LEVELS[0]
        self.assertEqual(levels[level]["result"], "reachable", levels[level])
        # The line is in the shared project file, so the level has a project row and preselects nothing.
        self.assertIsNone(levels[level]["preselect"], levels[level])
        rows = {row["layer"]: row for row in levels[level]["files"]}
        self.assertIs(rows["project"]["pickable"], True, rows)
        self.assertEqual(rows["project"]["target"], target["target"])
        self.assertEqual([layer for layer, row in rows.items() if row["pickable"]], ["project"], rows)

        body = {"project": project, "target": target["target"], "value": level}
        preview = self.post("/api/edit/preview", body)
        self.assertIsNone(preview["warning"])
        self.assertIs(preview["no_change"], False)
        self.assertEqual(preview["old_value"], START_LEVEL)
        self.assertEqual(preview["new_value"], level)
        lines = [line["text"] for hunk in preview["diff"]["hunks"] for line in hunk["lines"]]
        self.assertTrue(any('"%s"' % START_LEVEL in text for text in lines), lines)
        self.assertEqual(w.settings_bytes(), before, "a preview wrote the file")

        saved = self.post("/api/edit/save", dict(body, base_file=preview["base_file"],
                                                 base_trail=preview["base_trail"],
                                                 base_others=preview["base_others"]))
        row = saved["edit"]
        self.assertNotEqual(w.settings_bytes(), before)
        self.assertEqual(json.loads(w.settings_bytes()), {"effortLevel": level})
        self.assertIs(row["undoable"], True)
        backup = w.real_path(row["backup_display"])
        with open(backup, "rb") as fh:
            self.assertEqual(fh.read(), before, "the backup holds the bytes from before the save")

        undone = self.post("/api/edit/undo", {"project": project, "edit": row["id"]})
        self.assertIs(undone["matches_backup"], True)
        restored = w.real_path(undone["restored_from_display"])
        with open(restored, "rb") as fh:
            restored_bytes = fh.read()
        self.assertEqual(w.settings_bytes(), restored_bytes)
        self.assertEqual(w.settings_bytes(), before)

        history = self.get("/api/edit/history")
        newest = history["rows"][0]
        self.assertEqual(newest["kind"], "undo")
        self.assertIsNot(newest.get("undoable"), True, "an undo row offers no Undo")

    def test_a_write_without_the_token_is_refused(self):
        status, _heads, _data = self.world.srv.request(
            "POST", "/api/edit/preview", headers=self.headers(write=True, token="wrong"),
            body=b"{}")
        self.assertIn(status, (401, 403))
        self.assertEqual(json.loads(self.world.settings_bytes()), {"effortLevel": START_LEVEL})


# ---------------------------------------------------------------- Chrome

class _ChromeBase(unittest.TestCase):
    """setUpClass builds one world and one Chrome. The subclasses carry the skip decorators."""

    @classmethod
    def setUpClass(cls):
        cls.world = None
        cls.chrome = None
        try:
            cls.world = build_world("mr-e2e-edit-chrome-")
            cls.chrome = shell.Chrome(helpers._tmp_base())
            cls.page = cls.chrome.page
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "chrome", None):
            cls.chrome.close()
        if getattr(cls, "world", None):
            cls.world.close()

    def wait_card(self):
        """Wait until the page has rendered and the Effort cell holds its level radios."""
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.page.wait_for(HAS_RADIO)

    def click(self, selector):
        self.page.wait_for(js(CLICK_BUTTON, selector))

    def text_of(self, selector):
        self.page.wait_for(js(READ_TEXT, selector))
        return self.page.eval(js(READ_TEXT, selector))

    def wait_settings(self):
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps(["settings"]))))

    def open_settings(self, width=1440, theme=None):
        """Open Settings with the token in the address, as the printed link does, and wait for the Effort cell."""
        hash_ = SETTINGS + "?edit=" + urllib.parse.quote(self.world.token, safe="")
        if theme:
            hash_ = pages.add_query(hash_, "theme", theme)
        self.page.open(self.world.base + hash_, width)
        self.wait_card()
        self.wait_settings()
        if theme:
            self.page.wait_for("document.documentElement.getAttribute('data-theme') === %s" % json.dumps(theme))

    def pick(self, level):
        """Choose a level. The rail then holds the review heading and, with no file picked, the Pick a file line."""
        self.page.wait_for(js(CLICK_LEVEL, level))
        self.page.wait_for(js("Boolean(document.querySelector(%s))", RAIL_HEAD))
        self.page.wait_for(PICK_NOTE)

    def pick_project_row(self):
        """Press the project row. The preview then draws the exact change in the rail and Save turns on.

        The project file is shared, so the review keeps a rail note of its own (the shared-file line). Only the
        Pick a file line goes, so the wait is on that line, with the diff, the After list and the picked row as
        the positive signs that the review drew."""
        self.click(PROJECT_ROW)
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& Boolean(document.querySelector(%s))", DIFF, RAIL_AFTER, PICKED_ROWS))
        self.page.wait_for("!(" + PICK_NOTE + ")")
        self.page.wait_for(js(IS_ON, SAVE))


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditPath(_ChromeBase):
    def test_owner_check_path(self):
        w = self.world
        before = w.settings_bytes()
        self.assertEqual(current_level(w), START_LEVEL)

        # The printed link: the address loses edit= once the page has taken the token.
        self.page.open(w.link, 1440)
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.page.wait_for("!location.href.includes('edit=')")
        self.assertNotIn("edit=", self.page.eval(LOCATION_HREF))

        # Settings, with the Effort cell open and its level radios.
        self.wait_settings()
        self.wait_card()
        self.assertNotIn("edit=", self.page.eval(LOCATION_HREF))
        self.assertEqual(self.page.eval("document.querySelector(%s).getAttribute('aria-current')" % json.dumps(BAND_CELL)), "true")
        self.assertEqual(self.text_of(RUN + " .s4-lab"), "Run at")
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_ROWS)), 0)

        # Pick a level. The line is in the shared project file, so no row is picked and Save is off.
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertEqual(self.text_of(RAIL_NOTE), PICK_FILE_LINE)
        self.assertEqual(self.text_of(RAIL + " .s4-chg .s4-to"), level)
        self.assertEqual(self.text_of(RAIL + " .s4-chg .s4-was"), START_LEVEL)
        self.assertGreater(self.page.eval(ROW_COUNT), 0)
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_ROWS)), 0)
        self.assertTrue(self.page.eval("Boolean(document.querySelector(%s)) && document.querySelector(%s).disabled"
                                       % (json.dumps(SAVE), json.dumps(SAVE))), "Save is on before a file is picked")
        self.assertEqual(w.settings_bytes(), before, "picking a level wrote the file")

        # Press the project row: the rail shows what wins after the change and the diff, with the old and the new value.
        self.pick_project_row()
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_ROWS)), 1)
        self.assertTrue(self.page.eval("Boolean(document.querySelector(%s))" % json.dumps(RAIL_AFTER)))
        lines = self.page.eval(DIFF_LINES)
        self.assertTrue(any('"%s"' % START_LEVEL in line for line in lines["del"]), lines)
        self.assertTrue(any('"%s"' % level in line for line in lines["add"]), lines)
        self.assertEqual(w.settings_bytes(), before, "a preview wrote the file")

        # Save: the foot names the backup, and the file holds the new level.
        self.click(SAVE)
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& Boolean(document.querySelector(%s))", STRIP_LINE, STRIP_PATH, UNDO))
        backup_display = self.text_of(STRIP_PATH)
        self.assertEqual(json.loads(w.settings_bytes()), {"effortLevel": level})
        with open(w.real_path(backup_display), "rb") as fh:
            self.assertEqual(fh.read(), before, "the backup holds the bytes from before the save")

        # Undo: the foot names the path it restored from, and no Undo button remains.
        self.click(UNDO)
        self.page.wait_for("!document.querySelector(%s)" % json.dumps(UNDO))
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& document.querySelector(%s).textContent.includes('Undone.')",
                              STRIP_LINE, STRIP_PATH, STRIP_LINE))
        restored_display = self.text_of(STRIP_PATH)
        self.assertFalse(self.page.eval(js("Boolean(document.querySelector(%s))", UNDO)),
                         "an Undo button remains after the undo")
        with open(w.real_path(restored_display), "rb") as fh:
            restored_bytes = fh.read()
        self.assertEqual(w.settings_bytes(), restored_bytes)
        self.assertEqual(w.settings_bytes(), before)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditLook(_ChromeBase):
    """#87's two browser items: no sideways scroll and AA text contrast in the rest, pick-a-file, preview and saved states."""

    def audit(self, where):
        failures = []
        if self.page.eval(BODY_OVERFLOW) != "0":
            failures.append("%s: data-ox is not 0, the page scrolls sideways" % where)
        self.page.eval(settings_e2e.OPEN_DETAILS)
        result = self.page.eval(settings_e2e.TEXT_CONTRAST_BAD)
        if result["checked"] <= 10:
            failures.append("%s: checked only %d elements" % (where, result["checked"]))
        failures += ["%s: %s" % (where, item) for item in result["bad"]]
        return failures

    def test_rest_pick_preview_and_saved_states(self):
        w = self.world
        before = w.settings_bytes()
        failures = []
        for width in (1440, 375):
            for theme in ("light", "dark"):
                tag = "%d %s" % (width, theme)
                self.open_settings(width, theme)
                failures += self.audit(tag + " rest")
                self.pick(OTHER_LEVELS[0])
                failures += self.audit(tag + " pick a file")
                self.pick_project_row()
                failures += self.audit(tag + " preview")
                self.click(SAVE)
                self.page.wait_for(js("Boolean(document.querySelector(%s))", UNDO))
                failures += self.audit(tag + " saved")
                self.click(UNDO)
                self.page.wait_for("!document.querySelector(%s)" % json.dumps(UNDO))
                self.assertEqual(w.settings_bytes(), before, tag + ": the undo left the file changed")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
