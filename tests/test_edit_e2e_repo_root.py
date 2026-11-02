"""End-to-end checks that the dashboard writes the repo root's settings.local.json for a worktree project (#104).

Run the whole file, with the browser and the harness parts, with the owner's one command from the repo root:

    MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_edit_e2e_repo_root.py"

Without MR_E2E=1 the file still runs the HTTP parts and skips the other two.

The world is built under helpers._tmp_base() and never touches the real ~/.claude or this repo's own
.claude/settings.local.json. Its folders, all inside one throwaway root:
- main            a real git repo with one commit. main/app is a listed project with a .claude folder.
- wt              a real linked worktree of main (git worktree add), listed as a second project.
- wt/.claude      settings.json with "model": "claude-opus-5-5" (so an effort line applies) and a leftover
                  settings.local.json with an unrelated key. Claude Code 2.1.211 and later read the leftover under
                  the root file, so the dashboard must never write to it.
- config          routing-dashboard.json listing both projects, written the way the other tests write it.
- home, home-cfg  the server's HOME and config folder.
Git runs with the closed environment of tests/test_git_check.py: a throwaway HOME, GIT_CONFIG_NOSYSTEM=1,
GIT_CONFIG_GLOBAL=/dev/null, an identity in the environment, stdin on /dev/null and a timeout.

Three groups of tests:
- RepoRootApi (every suite run, needs git). The real server process starts with --fixture and --allow-edits, as
  test_edit_e2e does, on that world. Over HTTP with the edit key: the wt project's local row names the main
  checkout's file (outside_project true, no project lock), a preview and a save of an effort line write that file with
  the bytes the preview showed and leave the leftover alone, the history of both projects shows the row, and an undo
  puts the main file back (or removes it, when the save created it). The harness case for the same files is also
  checked against the runcase.py guard here, without running claude.
- RepoRootPage (MR_E2E=1 and Chrome). The same save, driven through the page in headless Chrome: the review shows
  the ed_shared_local note from strings.json, Save writes the main checkout's file and the foot's Undo restores it.
- RepoRootHarness (MR_E2E=1 and claude on PATH). One harness case in runcase.py's worktree layout, with the files the
  save produced. Its `/effort status` answer must be the level the preview's runs_after promised. runcase.py builds its
  own repo and cannot point at the one above, so the case copies the same file contents into the layout it builds.
  `/effort status` sends no request (T-07ef), and the caller's environment is closed down to PATH, TMPDIR and LANG.

Importing this module starts nothing.
"""
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import unittest
import urllib.parse

import helpers
import test_edit_e2e as e2e
import test_pages_e2e as pages
import test_server as ts
import test_shell_e2e as shell

GIT = shutil.which("git")
CLAUDE = shutil.which("claude")
RUNCASE = os.path.join(helpers.REPO, "dashboard", "experiments", "harness", "runcase.py")
HARNESS_PYTHON = "/usr/bin/python3"
MINIMAL_PATH = "/usr/bin:/bin"
GIT_TIMEOUT = 60
HARNESS_TIMEOUT = 150

MODEL = "claude-opus-5-5"
LEVEL = "low"
LEFTOVER = {"cleanupPeriodDays": 30}
ROOT_LOCAL = {"language": "en"}
MAIN_LOCAL_DISPLAY = "main/.claude/settings.local.json"
EFFORT_REF_END = '"effortLevel"]'

E2E_ON = os.environ.get("MR_E2E") == "1"
SKIP_E2E = unittest.skipUnless(E2E_ON, "set MR_E2E=1 to run the headless Chrome and harness checks")

with open(os.path.join(helpers.REPO, "dashboard", "static", "strings.json"), encoding="utf-8") as _fh:
    STRINGS = json.load(_fh)
SHARED_NOTE = STRINGS["ed_shared_local"]


def dumps(data):
    return json.dumps(data, indent=2) + "\n"


def raw(path):
    with open(path, "rb") as fh:
        return fh.read()


def tree(folder):
    """Every file under folder except .git, as {relative path: bytes}."""
    found = {}
    for here, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            found[os.path.relpath(os.path.join(here, name), folder)] = raw(os.path.join(here, name))
    return found


def load_runcase():
    spec = importlib.util.spec_from_file_location("runcase_repo_root_e2e", RUNCASE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class World:
    """A temp root with the repo, the worktree, the fixture folder and the server on it. close() stops and removes."""

    def __init__(self, root_local=None, serve=True):
        self.root = ts.make_root("mr-e2e-rr-")
        self.srv = None
        try:
            self._build(root_local)
            if serve:
                self.srv = ts.start(self.root, ["--fixture", self.folder, "--allow-edits"], env=self.env)
                self.token = self.srv.token
                self.base = "http://127.0.0.1:%d/" % self.srv.port
        except BaseException:
            self.close()
            raise

    # ------------------------------------------------------------ building

    def _build(self, root_local):
        self.folder = os.path.join(self.root, "fixture")
        self.main = os.path.join(self.folder, "main")
        self.app = os.path.join(self.main, "app")
        self.wt = os.path.join(self.folder, "wt")
        self.githome = os.path.join(self.root, "githome")
        os.makedirs(self.githome)
        self.env = ts.base_env(self.root)
        self.env.pop("CLAUDE_CODE_EFFORT_LEVEL", None)
        self.assert_throwaway()
        ts.write_json(os.path.join(self.folder, "session.json"),
                      {"shell_env": {}, "flags": [], "cli_settings": None, "claude_version": "2.1.302"})
        os.makedirs(os.path.join(self.app, ".claude"))
        self.git(self.main, "init", "-q", "-b", "main")
        self.git(self.main, "commit", "-q", "--allow-empty", "-m", "seed")
        self.git(self.main, "worktree", "add", "-q", "-b", "branch-wt", self.wt)
        ts.write(os.path.join(self.wt, ".claude", "settings.json"), dumps({"model": MODEL}))
        ts.write(self.leftover_path, dumps(LEFTOVER))
        if root_local is not None:
            ts.write(self.main_local, dumps(root_local))
        ts.write_json(os.path.join(self.folder, "config", "routing-dashboard.json"), {"projects": [
            {"name": "App", "path": self.app}, {"name": "Wt", "path": self.wt}]})

    def assert_throwaway(self):
        """Every folder the world uses sits under the temp root, and the root is not inside this repo."""
        real_root = os.path.realpath(self.root)
        assert self.root == real_root, (self.root, real_root)
        assert not (real_root + os.sep).startswith(os.path.realpath(helpers.REPO) + os.sep), real_root
        for key in ("HOME", "CLAUDE_CONFIG_DIR", "TMPDIR"):
            assert self.env[key].startswith(self.root + os.sep), (key, self.env[key])
        for path in (self.folder, self.main, self.app, self.wt, self.githome):
            assert path.startswith(self.root + os.sep), path

    def git_env(self):
        return {"PATH": MINIMAL_PATH, "HOME": self.githome, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def git(self, cwd, *args):
        os.makedirs(cwd, exist_ok=True)
        done = subprocess.run([GIT, "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *args],
                              cwd=cwd, env=self.git_env(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=GIT_TIMEOUT, check=False)
        if done.returncode != 0:
            raise AssertionError("git %s failed: %s" % (" ".join(args), done.stdout.decode("utf-8", "replace")))

    # ------------------------------------------------------------ the files

    @property
    def main_local(self):
        return os.path.join(self.main, ".claude", "settings.local.json")

    @property
    def leftover_path(self):
        return os.path.join(self.wt, ".claude", "settings.local.json")

    def worktree_files(self):
        return tree(self.wt)

    def app_files(self):
        return tree(self.app)

    # ------------------------------------------------------------ HTTP

    def headers(self, write=False):
        out = {"Origin": self.base.rstrip("/"), "Sec-Fetch-Site": "same-origin"}
        if write:
            out["Content-Type"] = "application/json"
            out["X-Dashboard-Token"] = self.token
        return out

    def get(self, path):
        status, _heads, data = self.srv.request("GET", path, headers=self.headers())
        assert status == 200, (path, status, data[:300])
        return json.loads(data)

    def post(self, path, body):
        status, _heads, data = self.srv.request("POST", path, headers=self.headers(write=True),
                                                body=json.dumps(body).encode("utf-8"))
        assert status == 200, (path, status, data[:300])
        return json.loads(data)

    def targets(self, project):
        return self.get("/api/edit/targets?project=" + urllib.parse.quote(project, safe=""))

    def history(self, project):
        return self.get("/api/edit/history?project=" + urllib.parse.quote(project, safe=""))

    def effort_add(self, found, level=LEVEL):
        """The request body for adding the top-level effort line in the local row of a targets answer."""
        adds = [a for a in found["adds"] if a["layer"] == "local" and a["ref"].endswith(EFFORT_REF_END)]
        assert len(adds) == 1, found["adds"]
        return {"project": found["project"], "target": adds[0]["target"], "value": level}

    def close(self):
        try:
            if self.srv is not None:
                self.srv.stop()
        finally:
            helpers.rmtree_force(self.root)


# ---------------------------------------------------------------- HTTP, every run

@unittest.skipIf(GIT is None, "git was not found")
class RepoRootApi(unittest.TestCase):
    """The worktree project's effort save over HTTP with the headers the page sends. It starts no browser."""

    def world(self, root_local=None):
        w = World(root_local)
        self.addCleanup(w.close)
        return w

    def local_row(self, found):
        rows = [f for f in found["files"] if f["layer"] == "local"]
        self.assertEqual(len(rows), 1, found["files"])
        return rows[0]

    def test_world_is_throwaway_and_the_projects_are_listed(self):
        w = self.world()
        self.assertTrue(w.env["HOME"].startswith(w.root + os.sep))
        self.assertTrue(w.env["CLAUDE_CONFIG_DIR"].startswith(w.root + os.sep))
        self.assertFalse(os.path.realpath(w.root).startswith(os.path.realpath(helpers.REPO) + os.sep))
        self.assertTrue(os.path.isfile(os.path.join(w.wt, ".git")), "wt is a linked worktree: its .git is a file")
        self.assertTrue(os.path.isdir(os.path.join(w.main, ".git")))
        self.assertFalse(os.path.exists(w.main_local))
        self.assertEqual(json.loads(raw(w.leftover_path)), LEFTOVER)
        listed = {p["key"]: p["path_display"] for p in w.get("/api/projects")["projects"]}
        self.assertEqual(listed, {"app": "main/app", "wt": "wt"})

    def test_the_local_row_names_the_main_checkouts_file(self):
        w = self.world()
        found = w.targets("wt")
        row = self.local_row(found)
        self.assertEqual(row["file_display"], MAIN_LOCAL_DISPLAY)
        self.assertIs(row["outside_project"], True, row)
        self.assertIsNone(found["project_lock"])
        self.assertEqual(found["runs_as"], "medium", "the model line in wt makes effort apply, at the default")
        app = self.local_row(w.targets("app"))
        self.assertEqual(app["file_display"], MAIN_LOCAL_DISPLAY)
        self.assertIs(app["outside_project"], True, app)

    def check_save_and_undo(self, root_local):
        w = self.world(root_local)
        before_main = raw(w.main_local) if root_local is not None else None
        before_wt = w.worktree_files()
        before_app = w.app_files()
        found = w.targets("wt")
        body = w.effort_add(found)
        add = [a for a in found["adds"] if a["target"] == body["target"]][0]
        self.assertEqual(add["file_display"], MAIN_LOCAL_DISPLAY)
        self.assertEqual(add["op"], "create" if root_local is None else "insert")

        preview = w.post("/api/edit/preview", body)
        self.assertIs(preview["outside_project"], True)
        self.assertEqual(preview["diff"]["file_display"], MAIN_LOCAL_DISPLAY)
        self.assertEqual((preview["runs_before"], preview["runs_after"]), ("medium", LEVEL))
        self.assertIsNone(preview["warning"])
        # A preview writes nothing.
        self.assertEqual(os.path.exists(w.main_local), root_local is not None)
        self.assertEqual(w.worktree_files(), before_wt)

        saved = w.post("/api/edit/save", dict(body, base_file=preview["base_file"], base_trail=preview["base_trail"],
                                              base_others=preview["base_others"]))
        row = saved["edit"]
        self.assertEqual(row["file_display"], MAIN_LOCAL_DISPLAY)
        self.assertIs(row["undoable"], True)
        # The bytes on disk are the preview diff's context and added lines, and nothing else.
        rebuilt = "".join(line["text"] + "\n" for hunk in preview["diff"]["hunks"] for line in hunk["lines"]
                          if line["kind"] != "del")
        after = raw(w.main_local)
        self.assertEqual(after.decode("utf-8"), rebuilt)
        expected = dict(root_local or {}, effortLevel=LEVEL)
        self.assertEqual(json.loads(after), expected)
        # The worktree and the subfolder project hold exactly what they held, the leftover included.
        self.assertEqual(w.worktree_files(), before_wt)
        self.assertEqual(raw(w.leftover_path), dumps(LEFTOVER).encode("utf-8"))
        self.assertEqual(w.app_files(), before_app)
        self.assertFalse(os.path.exists(os.path.join(w.app, ".claude", "settings.local.json")))

        # The file is shared, so both projects' history shows the row.
        for project in ("wt", "app"):
            ids = [r["id"] for r in w.history(project)["rows"]]
            self.assertIn(row["id"], ids, project)
        newest = w.history("app")["rows"][0]
        self.assertEqual(newest["file_display"], MAIN_LOCAL_DISPLAY)

        # And the target now reads the saved level back.
        again = w.targets("wt")
        self.assertEqual(again["runs_as"], LEVEL)
        self.assertEqual(self.local_row(again)["file_display"], MAIN_LOCAL_DISPLAY)

        undone = w.post("/api/edit/undo", {"project": "wt", "edit": row["id"]})
        if root_local is None:
            self.assertFalse(os.path.exists(w.main_local), "the undo of a create leaves the file")
            self.assertFalse(os.path.exists(os.path.join(w.main, ".claude")), "the undo left the folder it created")
        else:
            self.assertIs(undone["matches_backup"], True)
            self.assertEqual(raw(w.main_local), before_main)
        self.assertEqual(w.worktree_files(), before_wt)
        self.assertEqual(w.app_files(), before_app)

    def test_a_save_creates_the_main_checkouts_file_and_an_undo_removes_it(self):
        self.check_save_and_undo(None)

    def test_a_save_inserts_into_the_main_checkouts_file_and_an_undo_restores_the_bytes(self):
        self.check_save_and_undo(ROOT_LOCAL)

    def test_a_write_without_the_token_is_refused_and_writes_nothing(self):
        w = self.world(ROOT_LOCAL)
        body = w.effort_add(w.targets("wt"))
        headers = w.headers(write=True)
        headers["X-Dashboard-Token"] = "wrong"
        status, _heads, _data = w.srv.request("POST", "/api/edit/preview", headers=headers,
                                              body=json.dumps(body).encode("utf-8"))
        self.assertIn(status, (401, 403))
        self.assertEqual(json.loads(raw(w.main_local)), ROOT_LOCAL)


# ---------------------------------------------------------------- the harness case

def harness_case(root_local, start_local):
    """The runcase.py case for the world's files: <project> is the main checkout, claude runs in the worktree.

    root_local is the main checkout's settings.local.json after the save, start_local the worktree's leftover."""
    return {"name": "rr-e2e-worktree", "cwd": "worktree", "prompt": "/effort status",
            "start_project": {"model": MODEL}, "local": root_local, "start_local": start_local}


class HarnessCaseShape(unittest.TestCase):
    """The case is one runcase.py accepts. It runs every suite and starts no process."""

    def test_the_guard_accepts_the_case(self):
        runcase = load_runcase()
        case = harness_case({"effortLevel": LEVEL}, LEFTOVER)
        runcase.check_case(case)
        self.assertEqual(case["cwd"], "worktree")
        self.assertIn("worktree", runcase.GIT_LAYOUTS)
        self.assertIn(case["prompt"], runcase.PROMPT_ALLOWLIST)


# ---------------------------------------------------------------- Chrome, MR_E2E=1

@SKIP_E2E
@unittest.skipIf(GIT is None, "git was not found")
@unittest.skipIf(shell.CHROME is None, "Chrome was not found (set MR_CHROME to its path)")
class RepoRootPage(unittest.TestCase):
    """The wt project's effort line, added through the page. One Chrome for the class, one world per test."""

    @classmethod
    def setUpClass(cls):
        cls.chrome = shell.Chrome(helpers._tmp_base())
        cls.page = cls.chrome.page

    @classmethod
    def tearDownClass(cls):
        cls.chrome.close()

    def open_settings(self, w, width=1440):
        hash_ = pages.add_query(e2e.SETTINGS, "project", "wt") + "&edit=" + urllib.parse.quote(w.token, safe="")
        self.page.open(w.base + hash_, width)
        self.page.wait_for(pages.DATA_RENDERED + " === '1'")
        self.page.wait_for(e2e.HAS_RADIO)
        self.page.wait_for("JSON.stringify(%s) === %s" % (shell.VISIBLE, json.dumps(json.dumps(["settings"]))))

    def click(self, selector):
        self.page.wait_for(e2e.js(e2e.CLICK_BUTTON, selector))

    def test_adding_an_effort_line_writes_the_main_checkouts_file(self):
        w = World(None)
        self.addCleanup(w.close)
        before_wt = w.worktree_files()
        self.open_settings(w)
        # Pick a level. The root file does not exist, so the page preselects creating it.
        self.page.wait_for(e2e.js(e2e.CLICK_LEVEL, LEVEL))
        self.page.wait_for(e2e.js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s)) "
                                  "&& Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s))",
                                  e2e.RAIL_HEAD, e2e.DIFF, e2e.PICKED_LOCAL, e2e.NEW_FILE_TAG))
        self.page.wait_for(e2e.js(e2e.IS_ON, e2e.SAVE))
        # The review says the file is outside this folder and shared, in the words of strings.json.
        notes = self.page.eval("[...document.querySelectorAll(%s)].map((el) => el.textContent.trim())"
                               % json.dumps(e2e.RAIL_NOTE))
        self.assertIn(SHARED_NOTE, notes)
        lines = self.page.eval(e2e.DIFF_LINES)
        self.assertTrue(any('"%s"' % LEVEL in line for line in lines["add"]), lines)
        self.assertFalse(os.path.exists(w.main_local), "a preview created the file")

        self.click(e2e.SAVE)
        self.page.wait_for(e2e.js("Boolean(document.querySelector(%s)) && Boolean(document.querySelector(%s))",
                                  e2e.STRIP_LINE, e2e.UNDO))
        self.page.wait_for(e2e.js("document.querySelector(%s).textContent.includes('Created')", e2e.STRIP_LINE))
        # A create keeps only an .absent marker, not a backup, so the saved strip names no backup path.
        self.assertFalse(self.page.eval("Boolean(document.querySelector(%s))" % json.dumps(e2e.STRIP_PATH)),
                         "a create has no backup, so the strip should name none")
        self.assertEqual(json.loads(raw(w.main_local)), {"effortLevel": LEVEL})
        self.assertEqual(w.worktree_files(), before_wt)
        self.assertEqual(raw(w.leftover_path), dumps(LEFTOVER).encode("utf-8"))
        # The shared file shows in the history of the subfolder project too.
        rows = w.history("app")["rows"]
        self.assertEqual(rows[0]["file_display"], MAIN_LOCAL_DISPLAY)

        self.click(e2e.UNDO)
        self.page.wait_for("!document.querySelector(%s)" % json.dumps(e2e.UNDO))
        self.page.wait_for(e2e.js("document.querySelector(%s).textContent.includes('Undone.')", e2e.STRIP_LINE))
        self.assertFalse(os.path.exists(w.main_local), "the undo of a create leaves the file")
        self.assertFalse(os.path.exists(os.path.join(w.main, ".claude")), "the undo left the folder it created")
        self.assertEqual(w.worktree_files(), before_wt)


# ---------------------------------------------------------------- the harness, MR_E2E=1

@SKIP_E2E
@unittest.skipIf(GIT is None, "git was not found")
@unittest.skipIf(CLAUDE is None, "claude was not found on PATH")
class RepoRootHarness(unittest.TestCase):
    """One harness case in the worktree layout. `/effort status` must answer the level the preview promised."""

    def test_effort_status_matches_the_previews_runs_after(self):
        w = World(None)
        self.addCleanup(w.close)
        found = w.targets("wt")
        body = w.effort_add(found)
        preview = w.post("/api/edit/preview", body)
        promised = preview["runs_after"]
        w.post("/api/edit/save", dict(body, base_file=preview["base_file"], base_trail=preview["base_trail"],
                                      base_others=preview["base_others"]))
        case = harness_case(json.loads(raw(w.main_local)), json.loads(raw(w.leftover_path)))
        scratch = os.path.join(w.root, "harness")
        os.makedirs(os.path.join(scratch, "tmp"))
        case_path = os.path.join(scratch, "case.json")
        with open(case_path, "w", encoding="utf-8") as fh:
            json.dump(case, fh)
        # Nothing from the caller's environment but PATH (for claude), a throwaway TMPDIR and LANG.
        env = {"PATH": os.path.dirname(CLAUDE) + ":" + MINIMAL_PATH, "TMPDIR": os.path.join(scratch, "tmp"),
               "LANG": "C"}
        done = subprocess.run([HARNESS_PYTHON, RUNCASE, case_path, str(self.free_port())], env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=HARNESS_TIMEOUT, check=False)
        self.assertEqual(done.returncode, 0, done.stderr.decode("utf-8", "replace"))
        out = json.loads(done.stdout.decode("utf-8").strip().splitlines()[-1])
        self.assertEqual(out["sent"], [], "`/effort status` sent a request")
        answers = [re.search(r"effort level: (\w+)", text) for text in out["result"]]
        levels = [m.group(1) for m in answers if m]
        self.assertEqual(levels, [promised], out["result"])

    @staticmethod
    def free_port():
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]


if __name__ == "__main__":
    unittest.main()
