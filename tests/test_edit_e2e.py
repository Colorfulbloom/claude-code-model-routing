"""End-to-end checks of the owner check path on the Change effort card (#88, #87). Opt in with MR_E2E=1.

The path is: open the printed link, pick a level, read the trail table and the diff, press Save, read the
strip, press Undo, then compare the file with the backup it came from. Built on test_shell_e2e (its Chrome and
Page), test_pages_e2e (add_query, DATA_RENDERED) and test_settings_e2e (its contrast scripts, not copied).

The world is a small made-up fixture in a temp root. The server runs with --fixture and --allow-edits on it,
with HOME and the config folder inside the same root, and with no CLAUDE_CODE_EFFORT_LEVEL in its environment
(a shell value would beat the file). The project's settings.json holds "effortLevel": "high" at the top level.
That value wins, so a level such as medium is reachable and a preview shows no warning. Nothing reads or writes
the real ~/.claude.

Importing this module starts nothing. build_world() and the page scripts are pure. EditApi runs on every
suite run, with no browser, so the world is proven valid even where nobody runs Chrome. EditPath and EditLook
need Chrome and skip unless MR_E2E=1.

Selectors, from dashboard/static/js/edit_card.js (the doubtful ones are named in the brief's report):
- [data-edit=card] holds the card and [data-edit=strip] the strip.
- input[name=p2-level][value=<level>] is a level radio (class sr, so a script clicks it).
- table.p2-tbl is the trail table, figure.p2-df the diff, li.p2-del and li.p2-add its changed lines.
- button[data-edit-focus="btn:save"], "btn:undo" and "btn:dismiss-strip" are the buttons.
- .p2-strip is the strip line and .pa inside it the backup or restored-from path.
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

EFFORT_TRAIL = settings_e2e.EFFORT_TRAIL
START_LEVEL = "high"
OTHER_LEVELS = ("medium", "low")

CARD = "[data-edit=card]"
STRIP = "[data-edit=strip]"
RADIO = CARD + " input[name=p2-level]"
TABLE = CARD + " table.p2-tbl"
DIFF = CARD + " figure.p2-df"
SAVE = CARD + " button[data-edit-focus='btn:save']"
UNDO = STRIP + " button[data-edit-focus='btn:undo']"
STRIP_LINE = STRIP + " .p2-strip"
STRIP_PATH = STRIP_LINE + " .pa"

# Pure page scripts. Each is an expression with no side effect unless its name says it clicks.
HAS_RADIO = "Boolean(document.querySelector(%s))" % json.dumps(RADIO)
LOCATION_HREF = "location.href"
BODY_OVERFLOW = "document.documentElement.getAttribute('data-ox')"
CLICK_LEVEL = "(() => { const el = document.querySelector(%s + \"[value='\" + %%s + \"']\"); " \
              "if (!el) return false; el.click(); return true; })()" % json.dumps(RADIO)
CLICK_BUTTON = "(() => { const el = document.querySelector(%s); if (!el || el.disabled) return false; " \
               "el.click(); return true; })()"
READ_TEXT = "(() => { const el = document.querySelector(%s); return el ? el.textContent.trim() : null; })()"
DIFF_LINES = "(() => { const read = (sel) => [...document.querySelectorAll(%s + ' ' + sel)]" \
             ".map((el) => el.textContent.replace(/\\s+/g, ' ').trim()); " \
             "return { del: read('li.p2-del'), add: read('li.p2-add') }; })()" % json.dumps(DIFF)
TABLE_ROWS = "document.querySelectorAll(%s + ' tbody tr').length" % json.dumps(TABLE)


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
        self.assertEqual(levels[level]["target"], target["target"])

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
        """Wait until the page has rendered and the Change effort card holds its level radios."""
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.page.wait_for(HAS_RADIO)

    def click(self, selector):
        self.page.wait_for(js(CLICK_BUTTON, selector))

    def text_of(self, selector):
        self.page.wait_for(js(READ_TEXT, selector))
        return self.page.eval(js(READ_TEXT, selector))

    def open_trail(self, width=1440, theme=None):
        """Open the trail with the token in the address, as the printed link does, and wait for the card."""
        hash_ = EFFORT_TRAIL + "?edit=" + urllib.parse.quote(self.world.token, safe="")
        if theme:
            hash_ = pages.add_query(hash_, "theme", theme)
        self.page.open(self.world.base + hash_, width)
        self.wait_card()
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps(["trail"]))))
        if theme:
            self.page.wait_for("document.documentElement.getAttribute('data-theme') === %s" % json.dumps(theme))

    def pick(self, level):
        self.page.wait_for(js(CLICK_LEVEL, level))
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s))",
                              TABLE, DIFF))


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

        # The effort trail, with the Change effort card.
        self.page.eval("location.hash = %s" % json.dumps(EFFORT_TRAIL))
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps(["trail"]))))
        self.wait_card()
        self.assertNotIn("edit=", self.page.eval(LOCATION_HREF))
        self.assertEqual(self.text_of(CARD + " .cd-h"), "Change effort")

        # Pick a level: the trail table and the diff show, with the old and the new value.
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertGreater(self.page.eval(TABLE_ROWS), 0)
        lines = self.page.eval(DIFF_LINES)
        self.assertTrue(any('"%s"' % START_LEVEL in line for line in lines["del"]), lines)
        self.assertTrue(any('"%s"' % level in line for line in lines["add"]), lines)
        self.assertEqual(w.settings_bytes(), before, "a preview wrote the file")

        # Save: the strip names the backup, and the file holds the new level.
        self.click(SAVE)
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s))",
                              STRIP_PATH, UNDO))
        backup_display = self.text_of(STRIP_PATH)
        self.assertEqual(json.loads(w.settings_bytes()), {"effortLevel": level})
        with open(w.real_path(backup_display), "rb") as fh:
            self.assertEqual(fh.read(), before, "the backup holds the bytes from before the save")

        # Undo: the strip names the path it restored from, and no Undo button remains.
        self.click(UNDO)
        self.page.wait_for("!document.querySelector(%s)" % json.dumps(UNDO))
        self.page.wait_for(js("Boolean(document.querySelector(%s))", STRIP_PATH))
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
    """#87's two browser items: no sideways scroll and AA text contrast in the rest, preview and saved states."""

    def audit(self, where):
        failures = []
        if self.page.eval(BODY_OVERFLOW) != "0":
            failures.append("%s: data-ox is not 0, the page scrolls sideways" % where)
        self.page.eval(settings_e2e.OPEN_DETAILS)
        result = self.page.eval(settings_e2e.TEXT_CONTRAST_BAD)
        if result["checked"] <= 20:
            failures.append("%s: checked only %d elements" % (where, result["checked"]))
        failures += ["%s: %s" % (where, item) for item in result["bad"]]
        return failures

    def test_rest_preview_and_saved_states(self):
        w = self.world
        before = w.settings_bytes()
        failures = []
        for width in (1440, 375):
            for theme in ("light", "dark"):
                tag = "%d %s" % (width, theme)
                self.open_trail(width, theme)
                failures += self.audit(tag + " rest")
                self.pick(OTHER_LEVELS[0])
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
