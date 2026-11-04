"""End-to-end checks of the hivemind plugin with the real `claude` program. Opt in with MR_E2E=1.

The class installs the plugin from this repo into a throwaway HOME and CLAUDE_CONFIG_DIR, then runs two of its skills
through `claude -p` against a fake API on 127.0.0.1. Nothing reads or writes the real ~/.claude, no real API request
leaves the machine, and the project is a throwaway git repo with its own store. The consolidate skill is not run here,
because it dispatches an agent and writes the store.

Steps, in order, because each one builds on the last:
1. `claude plugin validate` passes on the repo root and on plugins/hivemind. The docs say a marketplace validate does
   not open plugin files in other folders, so both run.
2. `claude plugin marketplace add <source>`, then `claude plugin install hivemind@model-routing`, then
   `claude plugin list` names hivemind. The source is MR_PLUGIN_SOURCE when set, else the local repo path.
3. `/hivemind:status` in the throwaway project reaches the fake API with "HiveMind summary for" in the request body.
4. `/hivemind:inbox` reaches the fake API with the preview line in the request body, and the store tree (every folder
   and every file's bytes) is the same as before the two commands.

The owner runs it with

    MR_E2E=1 /usr/bin/python3 -m unittest discover -s tests -p "test_plugin_hivemind_e2e.py"

To test the copied install a colleague gets, point it at a pushed branch first:

    MR_E2E=1 MR_PLUGIN_SOURCE="Colorfulbloom/claude-code-model-routing#feature/hivemind-plugin" \\
        /usr/bin/python3 -m unittest discover -s tests -p "test_plugin_hivemind_e2e.py"

Importing this module starts nothing. The class skips unless MR_E2E=1, and again when `claude` is not on PATH.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers
import test_plugin_e2e as dash

sys.dont_write_bytecode = True

REPO = helpers.REPO
PLUGIN_DIR = os.path.join(REPO, "plugins", "hivemind")
WRAPPER = os.path.join(PLUGIN_DIR, "bin", "hivemind")
SUMMARY_TEXT = "HiveMind summary for"
PREVIEW_TEXT = "This was a preview, so nothing was written."
TODAY = "2026-10-20"


def tree_hash(folder):
    """Every path under folder (directories and files, relative) with each file's sha256."""
    out = {}
    for dirpath, dirs, files in os.walk(folder):
        for name in dirs:
            out[os.path.relpath(os.path.join(dirpath, name), folder) + "/"] = None
        for name in files:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, folder)] = hashlib.sha256(fh.read()).hexdigest()
    return out


@unittest.skipUnless(os.environ.get("MR_E2E") == "1", "set MR_E2E=1 to run the plugin checks with the real claude")
class HiveMindPluginE2E(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.claude = shutil.which("claude")
        if not cls.claude:
            raise unittest.SkipTest("the claude program is not on PATH")
        cls.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-hivemind-e2e-", dir=helpers._tmp_base()))
        cls.home = os.path.join(cls.root, "home")
        cls.cfg = os.path.join(cls.root, "home-cfg")
        cls.tmp = os.path.join(cls.root, "tmp")
        cls.project = os.path.join(cls.root, "project")
        cls.store = os.path.join(cls.project, ".claude", "hivemind")
        for d in (cls.home, cls.cfg, cls.tmp, cls.project):
            os.makedirs(d, exist_ok=True)
        cls.api = dash.FakeApi()
        cls.make_project()

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "api", None):
            cls.api.close()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    @classmethod
    def env(cls):
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": cls.home,
                "CLAUDE_CONFIG_DIR": cls.cfg, "TMPDIR": cls.tmp, "LANG": "C", "LC_ALL": "C",
                "ANTHROPIC_API_KEY": dash.FAKE_KEY, "ANTHROPIC_BASE_URL": "http://%s:%d" % (dash.HOST, cls.api.port),
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
                "DISABLE_AUTOUPDATER": "1", "BROWSER": "/usr/bin/true",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CEILING_DIRECTORIES": cls.root,
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

    @classmethod
    def make_project(cls):
        """A git project with one commit, a store made by the plugin's own wrapper, and one inbox run file."""
        for args in (["init", "-q", "-b", "main"], ["add", "a.txt"], ["commit", "-q", "-m", "first"]):
            if args[0] == "add":
                with open(os.path.join(cls.project, "a.txt"), "w", encoding="utf-8") as fh:
                    fh.write("x\n")
            proc = subprocess.run(["git", "-c", "commit.gpgsign=false"] + args, cwd=cls.project, env=cls.env(),
                                  stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                raise RuntimeError("git %s failed: %s" % (args[0], proc.stderr))
        made = subprocess.run([sys.executable, "-B", WRAPPER, "--project", cls.project, "init"], cwd=cls.project,
                              env=cls.env(), stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
        if made.returncode != 0 or not os.path.isdir(cls.store):
            raise RuntimeError("the wrapper could not make the store: %s%s" % (made.stdout, made.stderr))
        run = {"version": 1, "date": TODAY, "time": TODAY + "T12:00:00", "agent_type": "scout", "agent_id": "e2e1",
               "used": [], "verified": [], "contradicts": [],
               "new": [{"topic": "testing", "fact": "A proposed fact", "check": "true", "evidence": ["a.txt"]}]}
        with open(os.path.join(cls.store, "inbox", "run0001.json"), "w", encoding="utf-8") as fh:
            json.dump(run, fh)

    def claude_run(self, args, cwd=None):
        return subprocess.run([self.claude] + args, cwd=cwd or self.root, env=self.env(), capture_output=True,
                              text=True, timeout=dash.CLAUDE_TIMEOUT, stdin=subprocess.DEVNULL)

    def assert_ok(self, proc, what):
        self.assertEqual(proc.returncode, 0, "%s failed\nstdout: %s\nstderr: %s" % (what, proc.stdout, proc.stderr))

    def test_1_validate_repo_and_plugin(self):
        for folder in (REPO, PLUGIN_DIR):
            self.assert_ok(self.claude_run(["plugin", "validate", folder]), "claude plugin validate " + folder)

    def test_2_install_from_the_marketplace(self):
        source = os.environ.get("MR_PLUGIN_SOURCE") or REPO
        self.assert_ok(self.claude_run(["plugin", "marketplace", "add", source]),
                       "claude plugin marketplace add " + source)
        self.assert_ok(self.claude_run(["plugin", "install", "hivemind@model-routing"]), "claude plugin install")
        listed = self.claude_run(["plugin", "list"])
        self.assert_ok(listed, "claude plugin list")
        self.assertIn("hivemind", listed.stdout + listed.stderr)

    def test_3_and_4_status_and_inbox_reach_the_request_and_write_nothing(self):
        before = tree_hash(self.store)
        self.api.clear()
        proc = self.claude_run(["-p", "/hivemind:status"], cwd=self.project)
        self.assert_ok(proc, "claude -p status")
        self.assertIn(SUMMARY_TEXT, self.api.text())
        self.api.clear()
        proc = self.claude_run(["-p", "/hivemind:inbox"], cwd=self.project)
        self.assert_ok(proc, "claude -p inbox")
        self.assertIn(PREVIEW_TEXT, self.api.text())
        self.assertEqual(tree_hash(self.store), before, "status and inbox must leave the store as it was")
        for name in ("prep-snapshot.json", "consolidating.lock"):
            self.assertFalse(os.path.lexists(os.path.join(self.store, "inbox", name)), name)


if __name__ == "__main__":
    unittest.main()
