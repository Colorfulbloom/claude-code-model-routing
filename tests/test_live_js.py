"""Runs the browser-free checks of the Live page in tests/js/live_checks.mjs with Node.

The checks load the real modules from dashboard/static/js (pages/live.js, live_poll.js, api.js, router.js, shell.js)
against the small fake DOM in fakedom.mjs, with fake timers and a fake tab visibility. The payloads come from the
hand-written files in tests/fixtures/live, named by MR_LIVE_FIXTURES. No browser starts, no socket opens and nothing
reads the real ~/.claude. The checks read times in one zone, so the run sets TZ. The test skips when node is not
installed, and it tries the --experimental-default-type=module flag like tests/test_shell_js.py does.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

import test_shell_js as shell_js

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "live_checks.mjs"
FIXTURES = TESTS / "fixtures" / "live"


@unittest.skipUnless(shell_js.NODE, "node is not installed")
class LiveScripts(unittest.TestCase):
    def test_checks_pass(self):
        env = dict(os.environ, MR_LIVE_FIXTURES=str(FIXTURES), TZ="America/New_York")
        run = subprocess.run([shell_js.NODE] + shell_js.node_flags() + [str(CHECKS)], capture_output=True, text=True,
                             timeout=300, env=env)
        report = run.stdout + run.stderr
        if run.returncode != 0:
            sys.stderr.write(report)
        self.assertEqual(run.returncode, 0, report)
        self.assertIn("checks passed", run.stdout)
        self.assertNotIn("FAIL", run.stdout)

    def test_fixtures_exist(self):
        names = sorted(p.stem for p in FIXTURES.glob("*.json"))
        self.assertEqual(names, ["empty", "idle", "live", "session_gone", "two_running", "unchanged", "unreadable"])


if __name__ == "__main__":
    unittest.main()
