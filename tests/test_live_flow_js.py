"""Runs the browser-free checks of the Live page's dispatch card in tests/js/live_flow_checks.mjs with Node.

The checks load the real modules from dashboard/static/js (pages/live.js and pages/live_flow.js with the shared ones)
against the small fake DOM in fakedom.mjs, with fake timers, a fake tab visibility and a fake phone media query. The
payloads come from the flow_*.json files in tests/fixtures/live, which follow the session.runs[] contract of /api/live.
No browser starts, no socket opens and nothing reads the real ~/.claude. The checks read times in one zone, so the run
sets TZ. The test skips when node is not installed, like tests/test_live_js.py.
"""
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

import test_shell_js as shell_js

TESTS = Path(__file__).resolve().parent
CHECKS = TESTS / "js" / "live_flow_checks.mjs"
FIXTURES = TESTS / "fixtures" / "live"
FLOW = ("flow_busy", "flow_many", "flow_round2", "flow_unlinked")
RUN_KEYS = ["run_id", "route_key", "agent", "label_n", "model", "model_display", "effort", "parent", "parent_known",
            "dispatch_order", "together", "started", "last_request", "active_at", "state", "rounds", "tokens", "cost"]


@unittest.skipUnless(shell_js.NODE, "node is not installed")
class LiveFlowScripts(unittest.TestCase):
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


class FlowFixtures(unittest.TestCase):
    def runs(self, name):
        return json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))["session"]["runs"]

    def test_runs_follow_the_contract(self):
        for name in FLOW:
            runs = self.runs(name)
            ids = [r["run_id"] for r in runs]
            self.assertEqual(ids[0], "@main", name)
            self.assertEqual(len(ids), len(set(ids)), name)
            self.assertEqual([r["dispatch_order"] for r in runs], list(range(len(runs))), name)
            for r in runs:
                self.assertEqual(list(r), RUN_KEYS, "%s %s" % (name, r["run_id"]))
                if r["run_id"] != "@main":
                    self.assertRegex(r["run_id"], r"^[0-9a-f]{12}$", name)
                    self.assertIn(r["parent"], ids, name)
                    self.assertIn(r["state"], ("working", "idle", "done"), name)
                    self.assertRegex(r["started"], r"-04:00$")
                self.assertEqual(r["rounds"][0]["started"], r["started"], name)
                self.assertEqual([x["n"] for x in r["rounds"]], list(range(1, len(r["rounds"]) + 1)), name)
                self.assertGreaterEqual(r["active_at"], r["last_request"], name)

    def test_main_is_never_done_and_has_one_round(self):
        for name in FLOW:
            main = self.runs(name)[0]
            self.assertNotEqual(main["state"], "done", name)
            self.assertEqual(len(main["rounds"]), 1, name)
            self.assertIsNone(main["parent"], name)
            self.assertIsNone(main["label_n"], name)

    def test_no_message_text_in_a_run(self):
        # A run holds usage fields, hashed ids and times. Nothing that reads like a prompt, a path or a raw agent id.
        for name in FLOW:
            text = json.dumps(self.runs(name))
            self.assertNotRegex(text, r"/Users|\.jsonl|agent-[0-9a-f]{8}", name)
            self.assertEqual(re.findall(r'"(?:text|content|prompt|body|origin)"', text), [], name)

    def test_the_fixtures_cover_the_cases_the_checks_rely_on(self):
        busy, many, round2, unlinked = (self.runs(n) for n in FLOW)
        self.assertEqual(len(busy), 8)
        self.assertGreater(len(many), 12)
        self.assertTrue(any(len(r["rounds"]) > 1 for r in busy))
        self.assertTrue(any(len(r["rounds"]) > 2 for r in round2))
        self.assertTrue(any(r["rounds"][-1]["by"] is None and len(r["rounds"]) > 1 for r in round2))
        self.assertEqual(sum(1 for r in unlinked if r["parent_known"] is False), 3)


if __name__ == "__main__":
    unittest.main()
