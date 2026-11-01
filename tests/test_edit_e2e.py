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
import filecmp
import json
import os
import shutil
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
PICKED_LOCAL = PICKED_ROWS + " input[name=p2-row][value=local]"
PICKED_PROJECT = PICKED_ROWS + " input[name=p2-row][value=project]"
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
NEW_FILE_TAG = RAIL + " .p2-df-h .p2-tag"
CANCEL = FOOT + " button[data-edit-focus='btn:cancel']"
REMOVE_LINK = ROWS + " button[data-edit-focus='remove:%s']"
ANY_REMOVE_LINK = ROWS + " button[data-edit-focus^='remove:']"
MARKED_ROW = ROWS + " .s6-r.is-pick"
DIFF_ADD = DIFF + " li.p2-add"

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
DIFF_DEL = DIFF + " li.p2-del"
DIFF_LINES = "(() => { const read = (sel) => [...document.querySelectorAll(%s + ' ' + sel)]" \
             ".map((el) => el.textContent.replace(/\\s+/g, ' ').trim()); " \
             "return { del: read('li.p2-del'), add: read('li.p2-add') }; })()" % json.dumps(DIFF)
ROW_COUNT = "document.querySelectorAll(%s + ' label.s6-r').length" % json.dumps(ROWS)
ACTIVE_KEY = "(document.activeElement && document.activeElement.getAttribute('data-edit-focus')) || null"
COUNT = "document.querySelectorAll(%s).length"
# True when every level radio is there and off (a remove is open) or every one is on (nothing is chosen).
LEVELS_OFF = "(() => { const r = [...document.querySelectorAll(%s)]; return r.length > 0 && r.every((el) => el.disabled); })()" \
             % json.dumps(RADIO)
LEVELS_ON = "(() => { const r = [...document.querySelectorAll(%s)]; return r.length > 0 && r.every((el) => !el.disabled); })()" \
            % json.dumps(RADIO)
# The box of an element, as a plain object, or null when it is not there.
BOX_OF = "(() => { const el = document.querySelector(%s); if (!el) return null; const b = el.getBoundingClientRect(); " \
         "return { left: b.left, right: b.right, width: b.width, height: b.height }; })()"
# The contrast of every Remove line link at rest, with the helpers the Settings audits share. Returns { count, bad }.
REMOVE_LINK_CONTRAST = "(() => {" + settings_e2e.CONTRAST_HELPERS + r"""
  if (!section) return { count: 0, bad: ['no visible section'] };
  const bad = [];
  const links = [...section.querySelectorAll(%s)];
  links.forEach((el) => report(el, 4.5, bad));
  return { count: links.length, bad };
})()""" % json.dumps(ANY_REMOVE_LINK)


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

    def local_exists(self):
        """True when the project's local settings file is there. The fixture starts without one."""
        return os.path.exists(os.path.join(os.path.dirname(self.settings_path), "settings.local.json"))

    def local_bytes(self):
        with open(os.path.join(os.path.dirname(self.settings_path), "settings.local.json"), "rb") as fh:
            return fh.read()

    def project_state(self):
        """The project folder as it is now: each path under it, with its bytes, or None for a folder."""
        base = os.path.join(self.folder, "project")
        out = {}
        for here, dirs, files in os.walk(base):
            for name in dirs:
                out[os.path.relpath(os.path.join(here, name), base)] = None
            for name in files:
                with open(os.path.join(here, name), "rb") as fh:
                    out[os.path.relpath(os.path.join(here, name), base)] = fh.read()
        return out

    def backups(self):
        """Every backup file the dashboard has written in this world's config folder."""
        found = []
        for here, _dirs, files in os.walk(os.path.join(self.folder, "config")):
            found += [os.path.join(here, name) for name in files if name.endswith(".bak")]
        return found

    def copy_settings(self, name):
        """A copy of the shared file, made before a write, outside the project and the config folder."""
        copies = os.path.join(self.root, "copies")
        os.makedirs(copies, exist_ok=True)
        out = os.path.join(copies, name)
        shutil.copyfile(self.settings_path, out)
        return out

    def same_as_copy(self, copy):
        """True when the shared file equals the copy byte for byte (the cmp of the owner's check)."""
        return filecmp.cmp(copy, self.settings_path, shallow=False)

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


def build_fixture(folder, shared=None, claude_dir=True):
    """Write the made-up fixture: no shell env, no flags, an empty config folder and one project file.

    shared is what the project's settings.json holds (the effort line by default). claude_dir=False leaves the
    project folder empty, with no .claude folder at all. The path of settings.json comes back either way."""
    ts.write_json(os.path.join(folder, "session.json"), {"shell_env": {}, "flags": [], "cli_settings": None})
    os.makedirs(os.path.join(folder, "config"))
    path = os.path.join(folder, "project", ".claude", "settings.json")
    if claude_dir:
        ts.write(path, json.dumps({"effortLevel": START_LEVEL} if shared is None else shared, indent=2) + "\n")
    else:
        os.makedirs(os.path.join(folder, "project"))
    return path


def build_world(prefix="mr-e2e-edit-", shared=None, claude_dir=True):
    """Make the root, the fixture and the server with --allow-edits. Returns a World; the caller closes it."""
    root = ts.make_root(prefix)
    try:
        folder = os.path.join(root, "fixture")
        settings_path = build_fixture(folder, shared, claude_dir)
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
        # The line is in the shared project file. The local file doesn't exist, so the level preselects
        # creating it, never the shared row.
        rows = {row["layer"]: row for row in levels[level]["files"]}
        self.assertEqual(levels[level]["preselect"], rows["local"]["target"], levels[level])
        self.assertEqual(rows["local"]["op"], "create", rows)
        self.assertIs(rows["project"]["pickable"], True, rows)
        self.assertEqual(rows["project"]["target"], target["target"])
        self.assertEqual([layer for layer, row in rows.items() if row["pickable"]], ["local", "project"], rows)

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
        """Choose a level. The local file does not exist, so the page preselects creating it (never the shared file).

        The rail then holds the review heading and the diff of the new file, the local row is the picked one, and
        Save is on. The Pick a file line belongs to a level with no preselect, so it never shows here."""
        self.page.wait_for(js(CLICK_LEVEL, level))
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s))",
                              RAIL_HEAD, DIFF, PICKED_LOCAL, NEW_FILE_TAG))
        self.page.wait_for(js(IS_ON, SAVE))
        self.page.wait_for("!(" + PICK_NOTE + ")")

    def pick_project_row(self):
        """Press the project row, which moves the pick off the local create. The preview then draws the exact
        change in the rail and Save turns on.

        The project file is shared, so the review keeps a rail note of its own (the shared-file line). The waits are
        on positive signs that the project review drew: the project row is the picked one, the diff holds a deleted
        line (the create had none) and no New file tag, and the After list is there."""
        self.click(PROJECT_ROW)
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& Boolean(document.querySelector(%s)) && !document.querySelector(%s)",
                              PICKED_PROJECT, DIFF_DEL, RAIL_AFTER, NEW_FILE_TAG))
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

        # Pick a level. The line is in the shared project file and the local file does not exist, so the page
        # preselects creating the local file. It never picks the shared file on its own, and a preview writes nothing.
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertFalse(self.page.eval(PICK_NOTE), "the Pick a file line shows with a local preselect")
        self.assertEqual(self.text_of(RAIL + " .s4-chg .s4-to"), level)
        self.assertEqual(self.text_of(RAIL + " .s4-chg .s4-was"), START_LEVEL)
        self.assertGreater(self.page.eval(ROW_COUNT), 0)
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_ROWS)), 1)
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_PROJECT)), 0,
                         "the shared project row is picked on its own")
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(DIFF_DEL)), 0,
                         "a new file deletes no line")
        self.assertEqual(w.settings_bytes(), before, "picking a level wrote the file")
        self.assertFalse(w.local_exists(), "picking a level created the local file")

        # Press the project row: the rail shows what wins after the change and the diff, with the old and the new value.
        self.pick_project_row()
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_ROWS)), 1)
        self.assertEqual(self.page.eval("document.querySelectorAll(%s).length" % json.dumps(PICKED_LOCAL)), 0,
                         "the pick stayed on the local create")
        self.assertTrue(self.page.eval("Boolean(document.querySelector(%s))" % json.dumps(RAIL_AFTER)))
        lines = self.page.eval(DIFF_LINES)
        self.assertTrue(any('"%s"' % START_LEVEL in line for line in lines["del"]), lines)
        self.assertTrue(any('"%s"' % level in line for line in lines["add"]), lines)
        self.assertEqual(w.settings_bytes(), before, "a preview wrote the file")
        self.assertFalse(w.local_exists(), "a preview created the local file")

        # Save: the foot names the backup, and the file holds the new level.
        self.click(SAVE)
        self.page.wait_for(js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                              "&& Boolean(document.querySelector(%s))", STRIP_LINE, STRIP_PATH, UNDO))
        backup_display = self.text_of(STRIP_PATH)
        self.assertEqual(json.loads(w.settings_bytes()), {"effortLevel": level})
        self.assertFalse(w.local_exists(), "the save went to the local file")
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
        self.assertFalse(w.local_exists(), "the local file is there after the undo")


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
                failures += self.audit(tag + " local create preview")
                self.pick_project_row()
                failures += self.audit(tag + " project preview")
                self.click(SAVE)
                self.page.wait_for(js("Boolean(document.querySelector(%s))", UNDO))
                failures += self.audit(tag + " saved")
                self.click(UNDO)
                self.page.wait_for("!document.querySelector(%s)" % json.dumps(UNDO))
                self.assertEqual(w.settings_bytes(), before, tag + ": the undo left the file changed")
        self.assertEqual(failures, [], "\n".join(failures))

class _WorldPerTest(_ChromeBase):
    """One Chrome for the class, and a fresh throwaway world for each test (new_world), so a write never leaks."""

    @classmethod
    def setUpClass(cls):
        cls.world = None
        cls.chrome = None
        try:
            cls.chrome = shell.Chrome(helpers._tmp_base())
            cls.page = cls.chrome.page
        except BaseException:
            cls.tearDownClass()
            raise

    def new_world(self, **kwargs):
        self.world = build_world("mr-e2e-edit-write-", **kwargs)
        self.addCleanup(self.world.close)
        return self.world

    def count(self, selector):
        return self.page.eval(js(COUNT, selector))

    def wait_present(self, *selectors):
        """Wait until every selector matches something."""
        self.page.wait_for(" && ".join("Boolean(document.querySelector(%s))" % json.dumps(sel) for sel in selectors))

    def wait_gone(self, selector):
        self.page.wait_for("!document.querySelector(%s)" % json.dumps(selector))

    def wait_saved(self, word="Saved."):
        """The foot holds the result line with the word, and the Undo button."""
        self.wait_present(STRIP_LINE, UNDO)
        self.page.wait_for(js("document.querySelector(%s).textContent.includes(%s)", STRIP_LINE, word))

    def wait_undone(self):
        self.wait_gone(UNDO)
        self.wait_present(STRIP_LINE)
        self.page.wait_for(js("document.querySelector(%s).textContent.includes('Undone.')", STRIP_LINE))

    def wait_focus(self, key):
        self.page.wait_for("(%s) === %s" % (ACTIVE_KEY, json.dumps(key)))

    def start_remove(self, layer="project"):
        """Press Remove line on a row at rest and wait for the remove review: the row marked, Cancel and Save there,
        and a diff that deletes a line."""
        self.click(REMOVE_LINK % layer)
        self.wait_present(MARKED_ROW, CANCEL, DIFF_DEL, RAIL_HEAD)
        self.page.wait_for(js(IS_ON, SAVE))
        self.page.wait_for(LEVELS_OFF)
        self.wait_focus("btn:cancel")


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditWrites(_WorldPerTest):
    """Create, Remove and Add (#92), each in its own world. The shared file and the project folder are compared with
    copies and snapshots made before the write, never with the dashboard's backups."""

    def test_create_local_file_then_undo(self):
        w = self.new_world()
        start = w.project_state()
        shared = w.settings_bytes()
        shared_copy = w.copy_settings("shared-before.json")
        self.open_settings()
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertEqual(self.count(PICKED_LOCAL), 1, "the local row is the preselected one")
        self.assertEqual(self.count(NEW_FILE_TAG), 1, "the review tags the file as new")
        self.assertEqual(w.project_state(), start, "picking a level wrote something")

        self.click(SAVE)
        self.wait_saved("Created")
        self.assertTrue(w.local_exists(), "the save did not create the local file")
        self.assertEqual(w.local_bytes(), (json.dumps({"effortLevel": level}, indent=2) + "\n").encode("utf-8"))
        self.assertEqual(w.settings_bytes(), shared, "the save touched the shared file")
        self.assertTrue(w.same_as_copy(shared_copy))

        self.click(UNDO)
        self.wait_undone()
        self.assertFalse(w.local_exists(), "the undo left the local file")
        self.assertEqual(w.project_state(), start, "the project folder is not as it started")
        self.assertTrue(w.same_as_copy(shared_copy))

    def test_create_with_no_claude_folder_then_undo_removes_both(self):
        w = self.new_world(claude_dir=False)
        start = w.project_state()
        self.assertEqual(start, {}, "the project folder starts empty")
        self.open_settings()
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertEqual(self.count(PICKED_LOCAL), 1)
        self.assertEqual(self.count(NEW_FILE_TAG), 1)
        self.assertEqual(w.project_state(), start, "picking a level wrote something")

        self.click(SAVE)
        self.wait_saved("Created")
        self.assertTrue(w.local_exists(), "the save did not create the local file")
        self.assertEqual(w.local_bytes(), (json.dumps({"effortLevel": level}, indent=2) + "\n").encode("utf-8"))
        self.assertEqual(sorted(w.project_state()), [".claude", ".claude/settings.local.json"])

        self.click(UNDO)
        self.wait_undone()
        self.assertFalse(os.path.exists(os.path.join(w.folder, "project", ".claude")), "the undo left the folder")
        self.assertEqual(w.project_state(), start, "the project folder is not as it started")

    def test_remove_line_then_undo(self):
        w = self.new_world(shared={"effortLevel": START_LEVEL, "language": "en"})
        start = w.project_state()
        before = w.settings_bytes()
        copy = w.copy_settings("shared-before.json")
        self.open_settings()
        self.wait_present(REMOVE_LINK % "project")
        self.assertEqual(self.count(ANY_REMOVE_LINK), 1, "only the project file has a line")

        self.start_remove("project")
        self.assertEqual(self.count(MARKED_ROW), 1, "one row wears the picked style")
        self.assertIn("settings.json", self.text_of(MARKED_ROW))
        self.assertNotIn("settings.local.json", self.text_of(MARKED_ROW))
        self.assertEqual(self.count(PICKED_ROWS), 0, "the marked row is a plain row, not a radio")
        self.assertTrue(self.page.eval(LEVELS_OFF), "a level is still on")
        self.assertEqual(self.page.eval(ACTIVE_KEY), "btn:cancel")
        self.assertEqual(self.count(ANY_REMOVE_LINK), 0, "Remove line stays while a change is open")
        lines = self.page.eval(DIFF_LINES)
        self.assertTrue(any('"effortLevel"' in line for line in lines["del"]), lines)
        self.assertEqual(lines["add"], [])
        self.assertEqual(w.project_state(), start, "the review wrote something")

        self.click(SAVE)
        self.wait_saved()
        self.assertEqual(json.loads(w.settings_bytes().decode("utf-8")), {"language": "en"})
        self.assertNotEqual(w.settings_bytes(), before)
        self.assertFalse(w.local_exists())

        self.click(UNDO)
        self.wait_undone()
        self.assertEqual(w.settings_bytes(), before)
        self.assertTrue(w.same_as_copy(copy), "cmp finds the file changed from the copy made before the write")
        self.assertEqual(w.project_state(), start)

    def test_remove_line_then_cancel_writes_nothing(self):
        w = self.new_world(shared={"effortLevel": START_LEVEL, "language": "en"})
        start = w.project_state()
        copy = w.copy_settings("shared-before.json")
        self.open_settings()
        self.start_remove("project")

        self.click(CANCEL)
        self.wait_present(REMOVE_LINK % "project")
        self.wait_focus("remove:project")
        self.page.wait_for(LEVELS_ON)
        self.wait_gone(DIFF)
        self.wait_gone(MARKED_ROW)
        self.assertEqual(self.count(STRIP_LINE), 0, "Cancel left a result line")
        self.assertEqual(w.project_state(), start, "Cancel wrote something")
        self.assertTrue(w.same_as_copy(copy))
        self.assertEqual(w.backups(), [], "a backup was cut for a change that was never saved")

    def test_add_line_to_a_file_with_another_key_then_undo(self):
        w = self.new_world(shared={"language": "en"})
        start = w.project_state()
        before = w.settings_bytes()
        copy = w.copy_settings("shared-before.json")
        self.open_settings()
        level = OTHER_LEVELS[0]
        self.pick(level)
        self.assertEqual(self.count(PICKED_LOCAL), 1, "a level press preselects the local create first")

        # Press the project row: an add. The review shows no New file tag. The line above the new one gains a comma,
        # so the diff may show it as deleted, but no deleted line holds the setting.
        self.click(PROJECT_ROW)
        self.wait_present(PICKED_PROJECT, DIFF_ADD)
        self.wait_gone(NEW_FILE_TAG)
        self.page.wait_for(js(IS_ON, SAVE))
        lines = self.page.eval(DIFF_LINES)
        self.assertFalse(any("effortLevel" in line for line in lines["del"]), "an add removed an effort line: %r" % lines)
        self.assertTrue(any('"effortLevel"' in line and '"%s"' % level in line for line in lines["add"]), lines)
        self.assertEqual(w.project_state(), start, "the review wrote something")

        self.click(SAVE)
        self.wait_saved()
        self.assertEqual(json.loads(w.settings_bytes().decode("utf-8")), {"language": "en", "effortLevel": level})
        self.assertFalse(w.local_exists(), "the save went to the local file")

        self.click(UNDO)
        self.wait_undone()
        self.assertEqual(w.settings_bytes(), before)
        self.assertTrue(w.same_as_copy(copy), "cmp finds the file changed from the copy made before the write")
        self.assertEqual(w.project_state(), start)


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the headless Chrome checks")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class EditRemoveLook(_WorldPerTest):
    """The Remove line link and its review: AA contrast of the link at rest in both themes (the dark value failed at
    1.83:1 before its fix), and the review at 375 wide."""

    def test_remove_link_contrast_in_light_and_dark(self):
        self.new_world()
        failures = []
        for width in (1440, 375):
            for theme in ("light", "dark"):
                self.open_settings(width, theme)
                self.wait_present(REMOVE_LINK % "project")
                result = self.page.eval(REMOVE_LINK_CONTRAST)
                if result["count"] != 1:
                    failures.append("%d %s: found %d Remove line links, wanted 1" % (width, theme, result["count"]))
                failures += ["%d %s: %s" % (width, theme, item) for item in result["bad"]]
        self.assertEqual(failures, [], "\n".join(failures))

    def test_remove_review_at_375(self):
        w = self.new_world(shared={"effortLevel": START_LEVEL, "language": "en"})
        start = w.project_state()
        failures = []
        for theme in ("light", "dark"):
            tag = "375 %s" % theme
            self.open_settings(375, theme)
            self.wait_present(REMOVE_LINK % "project")
            link = self.page.eval(js(BOX_OF, REMOVE_LINK % "project"))
            if link["height"] < 44:
                failures.append("%s: the Remove line link is %.0f px tall, wanted 44" % (tag, link["height"]))
            self.start_remove("project")
            if self.page.eval(BODY_OVERFLOW) != "0":
                failures.append("%s: data-ox is not 0, the review scrolls sideways" % tag)
            width = self.page.eval("innerWidth")
            for name, selector in (("Save", SAVE), ("Cancel", CANCEL), ("diff", DIFF)):
                box = self.page.eval(js(BOX_OF, selector))
                if box is None or box["left"] < 0 or box["right"] > width:
                    failures.append("%s: %s is outside the %d px window: %r" % (tag, name, width, box))
            self.page.eval(settings_e2e.OPEN_DETAILS)
            result = self.page.eval(settings_e2e.TEXT_CONTRAST_BAD)
            if result["checked"] <= 10:
                failures.append("%s: checked only %d elements" % (tag, result["checked"]))
            failures += ["%s: %s" % (tag, item) for item in result["bad"]]
            self.click(CANCEL)
            self.wait_focus("remove:project")
            self.assertEqual(w.project_state(), start, tag + ": the review wrote something")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
