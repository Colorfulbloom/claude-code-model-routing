"""Runs the browser-free checks of the dashboard scripts in tests/js with Node.

The checks load the real modules from dashboard/static/js against a small fake DOM and a fake fetch, so no
browser and no server start. The test skips when node is not installed. Node reads the modules as ES modules,
which the .js files need: newer Node versions detect that on their own, and older ones need the
--experimental-default-type=module flag. The test tries the flag and drops it when this Node does not know it.
"""
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "checks.mjs"
NODE = shutil.which("node")
FLAG = "--experimental-default-type=module"


def node_flags():
    probe = subprocess.run([NODE, FLAG, "-e", "0"], capture_output=True, text=True, timeout=60)
    return [FLAG] if probe.returncode == 0 else []


@unittest.skipUnless(NODE, "node is not installed")
class ShellScripts(unittest.TestCase):
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
