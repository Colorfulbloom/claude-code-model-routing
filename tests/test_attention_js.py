"""Runs the browser-free checks of Needs attention in tests/js/attention_checks.mjs with Node.

A first step writes real /api/settings answers for a few resolution fixtures into a temp folder, the way
the route builds them, and passes that folder to the checks in MR_PAYLOADS. The checks load the real
modules from dashboard/static/js against the fake DOM. No browser starts. The test skips when node is not
installed, and it tries the --experimental-default-type=module flag like tests/test_settings_js.py does.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
import test_settings_js as settings_js

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "attention_checks.mjs"
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "node is not installed")
class AttentionScripts(unittest.TestCase):
    def test_checks_pass(self):
        folder = os.path.realpath(tempfile.mkdtemp(prefix="attention-js-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, folder)
        settings_js.write_payloads(folder)
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
