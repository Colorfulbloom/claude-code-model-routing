"""Runs the browser-free checks of the edit session in tests/js/edit_session_checks.mjs with Node.

The checks cover createEditSession, postJSON and the api cache drop with fakes, and boot the real
dashboard/static/js/app.js on the fake DOM with a fake fetch. Every token and payload is made up. No browser
starts and no socket opens. The test skips when node is not installed, and it tries the
--experimental-default-type=module flag like tests/test_shell_js.py does.
"""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "edit_session_checks.mjs"
NODE = shutil.which("node")
FLAG = "--experimental-default-type=module"


def node_flags():
    probe = subprocess.run([NODE, FLAG, "-e", "0"], capture_output=True, text=True, timeout=60)
    return [FLAG] if probe.returncode == 0 else []


@unittest.skipUnless(NODE, "node is not installed")
class EditSessionScripts(unittest.TestCase):
    def test_checks_pass(self):
        run = subprocess.run([NODE] + node_flags() + [str(CHECKS)], capture_output=True, text=True, timeout=300)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)


if __name__ == "__main__":
    unittest.main()
