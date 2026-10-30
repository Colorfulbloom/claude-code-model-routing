"""Runs the browser-free checks of the Settings page in tests/js/settings_checks.mjs with Node.

A first step writes real /api/settings answers for a few resolution fixtures into a temp folder, the way
the route builds them, and passes that folder to the checks in MR_PAYLOADS. The checks load the real
modules from dashboard/static/js against the fake DOM. No browser starts. The test skips when node is not
installed, and it tries the --experimental-default-type=module flag like tests/test_shell_js.py does.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import resolve  # noqa: E402
import server  # noqa: E402

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "settings_checks.mjs"
NODE = shutil.which("node")
FLAG = "--experimental-default-type=module"
FIXTURE_DIR = os.path.join(helpers.FIXTURES, "resolution")
CASES = (
    "effort-user-top-level-xhigh-ignored-opus-5-5",
    "effort-project-top-level-xhigh-opus-5-5",
    "model-main-default-unknown",
    "effort-lowered-by-cap",
    "env-block-over-shell",
)


def node_flags():
    probe = subprocess.run([NODE, FLAG, "-e", "0"], capture_output=True, text=True, timeout=60)
    return [FLAG] if probe.returncode == 0 else []


def write_payloads(folder):
    rules = resolve.load_rules()
    fields = resolve.load_agent_fields()
    for case in CASES:
        ctx = server.fixture_context(os.path.join(FIXTURE_DIR, case), None, None, rules, fields)
        status, payload = server.ROUTES["/api/settings"](ctx, {})
        assert status == 200, case
        with open(os.path.join(folder, case + ".json"), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)


@unittest.skipUnless(NODE, "node is not installed")
class SettingsScripts(unittest.TestCase):
    def test_checks_pass(self):
        folder = os.path.realpath(tempfile.mkdtemp(prefix="settings-js-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, folder)
        write_payloads(folder)
        env = dict(os.environ, MR_PAYLOADS=folder)
        run = subprocess.run([NODE] + node_flags() + [str(CHECKS)], capture_output=True, text=True,
                             timeout=300, env=env)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


if __name__ == "__main__":
    unittest.main()
