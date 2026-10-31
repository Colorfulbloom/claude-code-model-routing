"""Runs the browser-free checks of the Rules reference page in tests/js/rules_checks.mjs with Node.

A first step writes two real /api/rules answers into a temp folder, the way the route builds them (one with no
installed version and one with 2.1.310), and passes that folder to the checks in MR_PAYLOADS. The checks load the
real modules from dashboard/static/js against the fake DOM. No browser starts. The test skips when node is not
installed, and it tries the --experimental-default-type=module flag like tests/test_settings_js.py does.
"""
import dataclasses
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
import test_settings_js as settings_js

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import resolve  # noqa: E402
import server  # noqa: E402

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "rules_checks.mjs"
NODE = shutil.which("node")
CASE = os.path.join(helpers.FIXTURES, "resolution", "effort-lowered-by-cap")


def write_payloads(folder):
    ctx = server.fixture_context(CASE, None, None, resolve.load_rules(), resolve.load_agent_fields())
    for name, installed in (("rules", None), ("rules-due", "2.1.310")):
        status, payload = server.ROUTES["/api/rules"](dataclasses.replace(ctx, claude_version=installed), {})
        assert status == 200, name
        with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)


@unittest.skipUnless(NODE, "node is not installed")
class RulesScripts(unittest.TestCase):
    def test_checks_pass(self):
        folder = os.path.realpath(tempfile.mkdtemp(prefix="rules-js-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, folder)
        write_payloads(folder)
        env = dict(os.environ, MR_PAYLOADS=folder)
        run = subprocess.run([NODE] + settings_js.node_flags() + [str(CHECKS)], capture_output=True, text=True,
                             timeout=300, env=env)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


if __name__ == "__main__":
    unittest.main()
