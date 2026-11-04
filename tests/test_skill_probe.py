"""Tests for tools/skill_probe/probe.py: its real-home guard and the way it reads a run.

Nothing here runs `claude`, starts the fake API or reads the real ~/.claude. The guard tests only compare
paths, and the tests of main() replace subprocess so that any attempt to start a process fails the test.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import helpers

sys.dont_write_bytecode = True

PROBE = os.path.join(helpers.REPO, "tools", "skill_probe", "probe.py")


def load_probe():
    spec = importlib.util.spec_from_file_location("skill_probe_under_test", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


probe = load_probe()


def no_process(*args, **kwargs):
    raise AssertionError("the probe started a process: %r" % (args,))


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="skill-probe-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = probe.real_path(self.tmp)
        self.env = {"HOME": os.path.join(self.home, "fake-real-home"),
                    "CLAUDE_CONFIG_DIR": os.path.join(self.home, "fake-real-config")}

    def refuses(self, home, cfg, env=None):
        with self.assertRaises(probe.Refused):
            probe.check_isolated(home, cfg, env)

    def test_a_throwaway_home_and_config_pass(self):
        probe.check_isolated(os.path.join(self.home, "run", "home"), os.path.join(self.home, "run", "cfg"), self.env)

    def test_the_real_home_is_refused_as_home(self):
        real = sorted(probe.real_homes())[0]
        self.refuses(real, os.path.join(self.home, "cfg"))

    def test_the_real_home_is_refused_as_config_dir(self):
        real = sorted(probe.real_homes())[0]
        self.refuses(os.path.join(self.home, "home"), real)

    def test_the_real_dot_claude_is_refused_as_config_dir(self):
        real = sorted(probe.real_config_dirs())[0]
        self.refuses(os.path.join(self.home, "home"), real)

    def test_a_folder_inside_the_real_dot_claude_is_refused(self):
        real = sorted(probe.real_config_dirs())[0]
        self.refuses(os.path.join(real, "inner"), os.path.join(self.home, "cfg"))
        self.refuses(os.path.join(self.home, "home"), os.path.join(real, "inner"))

    def test_a_home_that_contains_the_real_dot_claude_is_refused(self):
        real = sorted(probe.real_config_dirs())[0]
        self.refuses(os.path.dirname(real), os.path.join(self.home, "cfg"))

    def test_the_callers_home_and_config_dir_variables_count_as_real(self):
        self.refuses(self.env["HOME"], os.path.join(self.home, "cfg"), self.env)
        self.refuses(os.path.join(self.home, "home"), self.env["CLAUDE_CONFIG_DIR"], self.env)

    def test_a_symlink_to_the_real_home_is_refused(self):
        link = os.path.join(self.home, "link")
        os.symlink(sorted(probe.real_homes())[0], link)
        self.refuses(link, os.path.join(self.home, "cfg"))

    def test_root_must_not_be_the_real_home(self):
        with self.assertRaises(probe.Refused):
            probe.check_root(sorted(probe.real_homes())[0])

    def test_root_must_not_sit_inside_the_real_dot_claude(self):
        with self.assertRaises(probe.Refused):
            probe.check_root(os.path.join(sorted(probe.real_config_dirs())[0], "probe"))

    def test_root_must_be_new_or_empty(self):
        probe.check_root(os.path.join(self.home, "new"))
        probe.check_root(self.home)
        with open(os.path.join(self.home, "file"), "w") as fh:
            fh.write("x")
        with self.assertRaises(probe.Refused):
            probe.check_root(self.home)


class MainTest(unittest.TestCase):
    def run_main(self, argv, env=None):
        stderr = mock.MagicMock()
        with mock.patch.dict(os.environ, env or {}), \
                mock.patch.object(probe.subprocess, "Popen", side_effect=no_process), \
                mock.patch.object(probe.subprocess, "run", side_effect=no_process), \
                mock.patch.object(probe.sys, "stderr", stderr):
            code = probe.main(argv)
        return code, "".join(c.args[0] for c in stderr.write.call_args_list)

    def test_an_api_key_in_the_shell_is_refused(self):
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            code, err = self.run_main([], {name: "x"})
            self.assertEqual(code, 2, name)
            self.assertIn(name, err)

    def test_the_real_home_as_root_is_refused_before_anything_starts(self):
        code, err = self.run_main(["--root", sorted(probe.real_homes())[0]])
        self.assertEqual(code, 2)
        self.assertIn("real home", err)

    def test_a_non_empty_root_is_refused_before_anything_starts(self):
        with tempfile.TemporaryDirectory(prefix="skill-probe-test-") as tmp:
            with open(os.path.join(tmp, "file"), "w") as fh:
                fh.write("x")
            code, err = self.run_main(["--root", tmp])
        self.assertEqual(code, 2)
        self.assertIn("not an empty folder", err)

    def test_a_missing_claude_is_refused(self):
        with mock.patch.object(probe.shutil, "which", return_value=None):
            code, err = self.run_main([])
        self.assertEqual(code, 2)
        self.assertIn("claude is not on PATH", err)


class ReadingTest(unittest.TestCase):
    """observe() and judge() on a made-up log, so no run is needed."""

    def rows(self, **override):
        outcome = {
            "echo t2-0": (False, "t2-0"), "edits model": (True, "Permission to use Bash with command x"),
            "status model": (True, "Permission to use Bash with command x"),
            "echo fgsame-0": (False, "fgsame-0"), "stop sub": (True, "Permission to use Bash with command x"),
            "echo bgin-0": (False, "bgin-0"), "edits bgin": (True, "Permission to use Bash with command x"),
            "echo bgb-0": (False, "bgb-0"), "edits bgduring": (True, "Permission to use Bash with command x"),
            "status bgafter": (True, "This command requires approval"), "echo bgb-3": (False, "bgb-3"),
            "echo t3-0": (False, "t3-0"), "status t3": (True, "This command requires approval"),
        }
        outcome.update(override)
        rows = [{"ev": "req", "skill": True, "launch": True, "t": 1.0}]
        for i, (cmd, (is_error, content)) in enumerate(outcome.items()):
            late = cmd in ("status bgafter", "echo bgb-3", "echo t3-0", "status t3")
            rows.append({"ev": "result", "cmd": "x " + cmd, "is_error": is_error, "content": content,
                         "t": 20.0 + i if late else 1.0 + i / 10})
        rows.append({"ev": "skill_turn_end", "t": 10.0})
        return rows

    def test_the_recorded_narrow_behaviour_passes_every_check(self):
        table = probe.judge("narrow", probe.observe(self.rows()))
        self.assertEqual([name for name, _, _ in table], [name for name, _ in probe.CHECKS])
        self.assertTrue(all(ok for _, ok, _ in table), table)

    def test_a_blanket_deny_fails_the_narrow_checks(self):
        blocked = (True, "Permission to use Bash has been denied.")
        table = probe.judge("narrow", probe.observe(self.rows(**{"echo t2-0": blocked})))
        failed = [name for name, ok, _ in table if not ok]
        self.assertEqual(failed, ["main session later in the turn"])

    def test_a_launcher_that_runs_in_the_turn_fails(self):
        table = probe.judge("narrow", probe.observe(self.rows(**{"edits model": (False, "LAUNCH edits")})))
        self.assertFalse(table[1][1])

    def test_a_launch_line_that_never_ran_fails_the_first_check(self):
        rows = self.rows()
        rows[0]["launch"] = False
        table = probe.judge("narrow", probe.observe(rows))
        self.assertFalse(table[0][1])

    def test_a_background_call_after_the_turn_is_accepted_as_denied_or_approval(self):
        for text in ("Permission to use Bash with command x", "This command requires approval"):
            table = probe.judge("narrow", probe.observe(self.rows(**{"status bgafter": (True, text)})))
            self.assertTrue(table[4][1], text)

    def test_an_in_turn_call_that_lands_after_the_turn_ended_is_late_and_fails(self):
        rows = self.rows()
        for row in rows:
            if row.get("cmd", "").endswith("echo bgin-0"):
                row["t"] = 50.0
        seen = probe.observe(rows)
        self.assertEqual(seen["bgin_echo"], "late")
        self.assertFalse(probe.judge("narrow", seen)[3][1])

    def test_a_missing_result_fails(self):
        rows = [r for r in self.rows() if not r.get("cmd", "").endswith("echo fgsame-0")]
        seen = probe.observe(rows)
        self.assertEqual(seen["fg_echo"], "missing")
        self.assertFalse(probe.judge("narrow", seen)[2][1])

    def test_every_check_has_an_expectation_for_both_variants(self):
        for variant in ("bare", "narrow"):
            wanted = {"launch"} | set(probe.COMMANDS)
            self.assertEqual(set(probe.EXPECTED[variant]), wanted, variant)
        for _, keys in probe.CHECKS:
            for key in keys:
                self.assertIn(key, probe.COMMANDS)

    def test_the_narrow_rule_is_the_one_the_skill_ships(self):
        with open(probe.SHIPPED_SKILL) as fh:
            text = fh.read()
        self.assertIn("\ndisallowed-tools: " + probe.NARROW_DENY + "\n", text)
        self.assertIn("\nallowed-tools: " + probe.ALLOW + "\n", text)
        self.assertIn("!`" + probe.BANG + "`", text)


if __name__ == "__main__":
    unittest.main()
