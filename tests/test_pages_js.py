"""Runs the browser-free page checks in tests/js/pages.mjs with Node.

The server starts on the made-up demo set with --fixture, as test_pages_e2e does, and this test saves what the
page would ask it for (/api/projects, /api/usage and /api/settings for every listed project and for "all",
/api/rules and /api/files) into one JSON file keyed by path plus query. Node boots the real app.js on a small
fake DOM and answers every fetch from that file, so no browser starts. The test skips when node is not
installed. It reads the same text files in tests/e2e_checks that the browser sweep uses.
"""
import json
import os
import subprocess
import sys
import unittest
import urllib.parse
from pathlib import Path

import helpers
import test_server as ts
import test_shell_js as shell_js

sys.path.insert(0, os.path.join(helpers.FIXTURES, "demo"))
import build_demo  # noqa: E402

PAGES = Path(__file__).resolve().parent / "js" / "pages.mjs"
ALL = "all"


def project_query(key):
    """The query the page sends for a project, as encodeURIComponent writes it."""
    return "?project=" + urllib.parse.quote(key, safe="!'()*")


@unittest.skipUnless(shell_js.NODE, "node is not installed")
class PageScripts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ts.make_root("mr-pages-js-")
        cls.srv = None
        try:
            folder = os.path.join(cls.root, "set")
            build_demo.build(folder)
            cls.srv = ts.start(cls.root, ["--fixture", folder])
            cls.responses = cls.collect()
            cls.data_path = os.path.join(cls.root, "responses.json")
            with open(cls.data_path, "w", encoding="utf-8") as fh:
                json.dump(cls.responses, fh)
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "srv", None):
            cls.srv.stop()
        if getattr(cls, "root", None):
            helpers.rmtree_force(cls.root)

    @classmethod
    def ask(cls, path):
        status, _heads, body = cls.srv.request("GET", path)
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = None
        return {"status": status, "body": parsed}

    @classmethod
    def collect(cls):
        """Every answer the page asks for, keyed by path plus query."""
        out = {"/api/projects": cls.ask("/api/projects")}
        if out["/api/projects"]["status"] != 200:
            raise AssertionError("/api/projects answered %s" % out["/api/projects"]["status"])
        keys = [p["key"] for p in out["/api/projects"]["body"]["projects"]] + [ALL]
        for key in keys:
            for route in ("/api/usage", "/api/settings"):
                path = route + project_query(key)
                out[path] = cls.ask(path)
        for path in ("/api/rules", "/api/files"):
            out[path] = cls.ask(path)
        return out

    def test_the_saved_answers_hold_the_demo_set(self):
        self.assertEqual(self.responses["/api/usage" + project_query(ALL)]["status"], 200)
        self.assertEqual(self.responses["/api/settings" + project_query(ALL)]["status"], 400)
        names = [p["name"] for p in self.responses["/api/projects"]["body"]["projects"]]
        self.assertIn("Tidewater reporting", names)
        for name in ("Driftwood", "Harbor Light"):
            self.assertIn(name, names)

    def test_checks_pass(self):
        run = subprocess.run([shell_js.NODE] + shell_js.node_flags() + [str(PAGES), self.data_path],
                             capture_output=True, text=True, timeout=300)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


if __name__ == "__main__":
    unittest.main()
