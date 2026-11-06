"""Tests for tools/skill_probe/probe.py: its real-home guard, the tree it lays out and the way it reads a run.

Nothing here runs `claude`, starts the fake API or reads the real ~/.claude. The guard tests only compare
paths, and the tests of main() replace subprocess so that any attempt to start a process fails the test.
The fake launcher is run in process, with sys.argv, stdout and os.execv replaced.
"""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
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


class ExitCodeTest(unittest.TestCase):
    """main() with run_variant replaced by canned logs: the shipped variant sets the exit code."""

    bypass_seen = None

    def setUp(self):
        self.bypass_seen = []

    def canned(self, shipped_ok=True, narrow_ok=True):
        def run_variant(harness, claude, name, root, bypass=False):
            self.bypass_seen.append((name, bypass))
            reading = ReadingTest()
            leak = {"edits model": (False, "LAUNCH edits")}
            if name == "shipped":
                rows = reading.rows(**dict(reading.hooked(), **({} if shipped_ok else leak)))
                return rows, reading.launches("reload", "stop")
            rows = reading.rows(**({} if narrow_ok else leak))
            return rows, reading.launches("reload")
        return run_variant

    def run_main(self, argv, **kw):
        out = io.StringIO()
        with tempfile.TemporaryDirectory(prefix="skill-probe-test-") as tmp:
            root = os.path.join(tmp, "root")
            quiet = {name: "" for name in probe.load_harness().CALLER_FORBIDDEN}
            with mock.patch.dict(os.environ, quiet), \
                    mock.patch.object(probe.shutil, "which", return_value="/work/bin/claude"), \
                    mock.patch.object(probe, "claude_version", return_value="9.9.9 (Claude Code)"), \
                    mock.patch.object(probe, "run_variant", side_effect=self.canned(**kw)), \
                    mock.patch.object(probe.subprocess, "Popen", side_effect=no_process), \
                    mock.patch.object(probe.subprocess, "run", side_effect=no_process), \
                    contextlib.redirect_stdout(out):
                code = probe.main(["--root", root] + argv)
        return code, out.getvalue()

    def test_a_passing_shipped_variant_exits_0_and_names_all_three_columns(self):
        code, out = self.run_main([])
        self.assertEqual(code, 0, out)
        self.assertIn("bare", out)
        self.assertIn("narrow", out)
        self.assertIn("shipped", out)
        self.assertIn("back-to-back slash commands", out)
        self.assertNotIn("FAIL: the shipped", out)
        self.assertNotIn("note: the narrow form", out)

    def test_a_failing_shipped_check_exits_1(self):
        code, out = self.run_main([], shipped_ok=False)
        self.assertEqual(code, 1, out)
        self.assertIn("FAIL: the shipped guard hook no longer behaves as recorded", out)

    def test_a_changed_bare_or_narrow_column_prints_a_note_and_exits_0(self):
        code, out = self.run_main([], narrow_ok=False)
        self.assertEqual(code, 0, out)
        self.assertIn("note: the narrow form no longer behaves as recorded. That is informational.", out)
        self.assertIn("note: the bare form no longer behaves as recorded. That is informational.", out)

    def test_variant_picks_one_column(self):
        code, out = self.run_main(["--variant", "shipped"])
        self.assertEqual(code, 0, out)
        header = out.splitlines()[1]
        self.assertIn("shipped", header)
        self.assertNotIn("narrow", header)
        code, out = self.run_main(["--variant", "narrow"], narrow_ok=False)
        self.assertEqual(code, 0, out)

    def test_bypass_is_allowed_only_with_the_shipped_variant(self):
        for argv in (["--bypass"], ["--bypass", "--variant", "all"], ["--bypass", "--variant", "narrow"],
                     ["--bypass", "--variant", "bare"]):
            with self.subTest(argv=argv):
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    code, out = self.run_main(argv)
                self.assertEqual(code, 2, out)
                self.assertIn("--bypass works only with --variant shipped", err.getvalue())
                self.assertEqual(self.bypass_seen, [])

    def test_bypass_with_the_shipped_variant_reaches_run_variant(self):
        code, out = self.run_main(["--bypass", "--variant", "shipped"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.bypass_seen, [("shipped", True)])
        self.assertIn("bypassPermissions", out.splitlines()[0])

    def test_no_bypass_by_default(self):
        code, out = self.run_main([])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.bypass_seen, [("bare", False), ("narrow", False), ("shipped", False)])
        self.assertNotIn("bypassPermissions", out)

    def test_the_claude_command_adds_the_permission_mode_only_with_bypass(self):
        plain = probe.claude_command("/work/bin/claude", "/work/plug")
        self.assertEqual(plain[:2], ["/work/bin/claude", "-p"])
        self.assertIn("/work/plug", plain)
        self.assertNotIn("--permission-mode", plain)
        bypassed = probe.claude_command("/work/bin/claude", "/work/plug", bypass=True)
        self.assertEqual(bypassed[:len(plain)], plain)
        self.assertEqual(bypassed[len(plain):], ["--permission-mode", "bypassPermissions"])

    def test_the_old_both_value_is_gone(self):
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
            probe.main(["--variant", "both"])
        self.assertEqual(caught.exception.code, 2)


class TreeTest(unittest.TestCase):
    """build_tree() and the fake launcher it writes, without starting anything."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="skill-probe-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def tree(self, variant):
        root = os.path.join(self.tmp, variant)
        os.makedirs(root)
        home, cfg, proj, plug = probe.build_tree(root, variant)
        return root, plug

    @staticmethod
    def front(text):
        """The front matter lines that do not name the skill."""
        return [l for l in text.split("\n---\n")[0].splitlines() if not l.startswith(("name:", "description:"))]

    @staticmethod
    def bang(text):
        return [l for l in text.splitlines() if l.startswith("!`")]

    def skill(self, plug, name):
        with open(os.path.join(plug, "skills", name, "SKILL.md")) as fh:
            return fh.read()

    def test_the_old_variants_carry_their_deny_rule_in_both_skills_and_no_hooks(self):
        for variant, rule in (("bare", probe.BARE_DENY), ("narrow", probe.NARROW_DENY)):
            _, plug = self.tree(variant)
            for name in ("dash", "seq"):
                self.assertIn("\ndisallowed-tools: %s\n" % rule, self.skill(plug, name), (variant, name))
            self.assertFalse(os.path.exists(os.path.join(plug, "hooks")), variant)

    def test_the_shipped_variant_has_no_deny_rule_and_the_shipped_hook_list_verbatim(self):
        _, plug = self.tree("shipped")
        for name in ("dash", "seq"):
            self.assertNotIn("disallowed-tools", self.skill(plug, name), name)
        with open(os.path.join(plug, "hooks", "hooks.json")) as fh:
            written = json.load(fh)
        with open(probe.SHIPPED_HOOKS) as fh:
            shipped = json.load(fh)
        self.assertEqual(written, {"hooks": {"PreToolUse": shipped["hooks"]["PreToolUse"]}})

    def test_the_seq_skill_matches_the_dash_skill_but_for_its_name_and_body(self):
        for variant in probe.VARIANTS:
            _, plug = self.tree(variant)
            dash, seq = self.skill(plug, "dash"), self.skill(plug, "seq")
            self.assertIn("SKILLMARK TAG=t2 PLAN=" + probe.SKILL_PLAN, dash)
            self.assertIn("SEQMARK TAG=t4 PLAN=text", seq)
            self.assertIn("name: seq\n", seq)
            self.assertEqual(self.front(dash), self.front(seq), variant)
            self.assertEqual(self.bang(dash), self.bang(seq), variant)

    def test_the_shipped_skill_and_the_probe_skills_share_the_grant_and_the_line(self):
        with open(probe.SHIPPED_SKILL) as fh:
            text = fh.read()
        self.assertNotIn("disallowed-tools", text)
        self.assertIn("\nallowed-tools: " + probe.ALLOW + "\n", text)
        self.assertIn("!`" + probe.BANG + "`", text)
        for variant in probe.VARIANTS:
            _, plug = self.tree(variant)
            self.assertIn("\nallowed-tools: " + probe.ALLOW + "\n", self.skill(plug, "dash"))
            self.assertIn("!`" + probe.BANG + "`", self.skill(plug, "seq"))

    def run_fake(self, plug, argv):
        """Run the fake launcher's source in process. Returns (stdout, what os.execv got)."""
        with open(os.path.join(plug, "bin", "routing-dashboard")) as fh:
            source = fh.read()
        out = io.StringIO()
        execs = []

        class Exec(Exception):
            pass

        def execv(*args):
            execs.append(args)
            raise Exec()   # the real execv never returns

        with mock.patch.object(sys, "argv", ["routing-dashboard"] + argv), \
                mock.patch.object(os, "execv", side_effect=execv), \
                contextlib.redirect_stdout(out):
            try:
                exec(compile(source, "fake-launcher", "exec"), {"__name__": "__main__"})
            except Exec:
                pass
        return out.getvalue(), execs

    def test_the_fake_launcher_logs_one_json_line_and_prints_launch(self):
        root, plug = self.tree("shipped")
        out, execs = self.run_fake(plug, ["--data", "/work/d", "--session", "abc", "reload"])
        self.assertEqual(out, "LAUNCH --data /work/d --session abc reload\n")
        self.assertEqual(execs, [])
        self.run_fake(plug, ["stop"])
        self.assertEqual(probe.read_launches(probe.launch_log(root)),
                         [["--data", "/work/d", "--session", "abc", "reload"], ["stop"]])

    def test_the_fake_launcher_hands_guard_to_the_shipped_launcher_and_logs_nothing(self):
        root, plug = self.tree("shipped")
        out, execs = self.run_fake(plug, ["guard"])
        self.assertEqual(out, "")
        self.assertEqual(execs, [(sys.executable, [sys.executable, probe.SHIPPED_LAUNCHER, "guard"])])
        self.assertTrue(os.path.isfile(probe.SHIPPED_LAUNCHER))
        self.assertEqual(probe.read_launches(probe.launch_log(root)), [])

    def test_read_launches_skips_damaged_lines(self):
        path = os.path.join(self.tmp, "launch.log")
        with open(path, "w") as fh:
            fh.write('["a", "reload"]\nnot json\n{"x": 1}\n["stop"]\n')
        self.assertEqual(probe.read_launches(path), [["a", "reload"], ["stop"]])
        self.assertEqual(probe.read_launches(os.path.join(self.tmp, "missing.log")), [])


class ReadingTest(unittest.TestCase):
    """observe() and judge() on a made-up log, so no run is needed."""

    LAUNCHER_CMDS = ("edits model", "status model", "stop sub", "edits bgin", "edits bgduring", "status bgafter",
                     "status t3")

    @staticmethod
    def hooked():
        """Overrides that make every launcher call the guard hook's refusal."""
        refused = (True, "PreToolUse:Bash hook error: " + probe.guard_reason())
        return {cmd: refused for cmd in ReadingTest.LAUNCHER_CMDS}

    @staticmethod
    def launches(*words):
        """The fake launcher's calls: one per word, each ending with it."""
        return [["--data", "/work/d", "--session", "abc", word] for word in words]

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
        table = probe.judge("narrow", probe.observe(self.rows(), self.launches("reload")))
        self.assertEqual([name for name, _, _ in table], [name for name, _ in probe.CHECKS])
        self.assertEqual(len(table), 7)
        self.assertTrue(all(ok for _, ok, _ in table), table)

    def test_the_recorded_shipped_behaviour_passes_every_check(self):
        seen = probe.observe(self.rows(**self.hooked()), self.launches("reload", "stop"))
        table = probe.judge("shipped", seen)
        self.assertEqual(len(table), 7)
        self.assertTrue(all(ok for _, ok, _ in table), table)
        self.assertEqual(seen["main_edits"], "hook")
        self.assertEqual(seen["main_echo"], "ran")

    def test_a_blanket_deny_fails_the_narrow_checks(self):
        blocked = (True, "Permission to use Bash has been denied.")
        table = probe.judge("narrow", probe.observe(self.rows(**{"echo t2-0": blocked}), self.launches("reload")))
        failed = [name for name, ok, _ in table if not ok]
        self.assertEqual(failed, ["main session later in the turn"])

    def test_a_launcher_that_runs_in_the_turn_fails(self):
        table = probe.judge("narrow", probe.observe(self.rows(**{"edits model": (False, "LAUNCH edits")}),
                                                    self.launches("reload")))
        self.assertFalse(table[1][1])

    def test_a_launcher_that_the_hook_lets_through_fails_the_shipped_checks(self):
        rows = self.rows(**dict(self.hooked(), **{"stop sub": (False, "LAUNCH stop sub")}))
        table = probe.judge("shipped", probe.observe(rows, self.launches("reload", "stop")))
        self.assertEqual([name for name, ok, _ in table if not ok], ["foreground subagent in the turn"])

    def test_an_echo_the_hook_blocks_fails_the_shipped_checks(self):
        blocked = (True, "PreToolUse:Bash hook error: " + probe.guard_reason())
        rows = self.rows(**dict(self.hooked(), **{"echo t2-0": blocked}))
        table = probe.judge("shipped", probe.observe(rows, self.launches("reload", "stop")))
        self.assertEqual([name for name, ok, _ in table if not ok], ["main session later in the turn"])

    def test_a_launch_line_that_never_ran_fails_the_first_check(self):
        rows = self.rows()
        rows[0]["launch"] = False
        table = probe.judge("narrow", probe.observe(rows, self.launches("reload")))
        self.assertFalse(table[0][1])

    def test_a_background_call_after_the_turn_is_accepted_as_denied_or_approval(self):
        for text in ("Permission to use Bash with command x", "This command requires approval"):
            table = probe.judge("narrow", probe.observe(self.rows(**{"status bgafter": (True, text)}),
                                                        self.launches("reload")))
            self.assertTrue(table[4][1], text)

    def test_an_in_turn_call_that_lands_after_the_turn_ended_is_late_and_fails(self):
        rows = self.rows()
        for row in rows:
            if row.get("cmd", "").endswith("echo bgin-0"):
                row["t"] = 50.0
        seen = probe.observe(rows)
        self.assertEqual(seen["bgin_echo"], "late")
        self.assertFalse(probe.judge("narrow", seen)[3][1])

    def test_an_in_turn_call_is_judged_against_the_first_end_of_a_skill_turn(self):
        rows = self.rows()
        rows.append({"ev": "skill_turn_end", "t": 100.0})
        for row in rows:
            if row.get("cmd", "").endswith("echo bgin-0"):
                row["t"] = 50.0
        self.assertEqual(probe.observe(rows)["bgin_echo"], "late")

    def test_a_missing_result_fails(self):
        rows = [r for r in self.rows() if not r.get("cmd", "").endswith("echo fgsame-0")]
        seen = probe.observe(rows)
        self.assertEqual(seen["fg_echo"], "missing")
        self.assertFalse(probe.judge("narrow", seen)[2][1])

    def test_the_back_to_back_check_reads_the_launch_log(self):
        for launches, first, second in (([], "denied", "denied"),
                                        (self.launches("reload"), "ran", "denied"),
                                        (self.launches("stop"), "denied", "ran"),
                                        (self.launches("reload", "stop"), "ran", "ran")):
            seen = probe.observe(self.rows(), launches)
            self.assertEqual((seen["seq_first"], seen["seq_second"]), (first, second), launches)

    def test_the_old_alternation_fails_the_shipped_back_to_back_check(self):
        seen = probe.observe(self.rows(**self.hooked()), self.launches("reload"))
        table = probe.judge("shipped", seen)
        self.assertEqual([name for name, ok, _ in table if not ok], ["back-to-back slash commands"])
        self.assertEqual(table[6][2], [("seq_second", "ran", "denied")])

    def test_only_a_call_that_ends_with_the_word_counts(self):
        seen = probe.observe(self.rows(), [["reload", "--data", "/work/d"], ["--session", "reload-x"]])
        self.assertEqual((seen["seq_first"], seen["seq_second"]), ("denied", "denied"))

    def test_a_hook_refusal_classifies_as_hook_before_denied(self):
        text = "PreToolUse:Bash hook error: Permission to use Bash was denied. " + probe.guard_reason()
        self.assertEqual(probe.classify({"is_error": True, "content": text}), "hook")
        self.assertEqual(probe.classify({"is_error": True, "content": "Permission to use Bash was denied"}),
                         "denied")
        self.assertEqual(probe.classify({"is_error": False, "content": "PreToolUse"}), "ran")

    def test_the_hook_reason_is_the_one_the_shipped_launcher_prints(self):
        loader = importlib.machinery.SourceFileLoader("launcher_for_probe_test", probe.SHIPPED_LAUNCHER)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        launcher = importlib.util.module_from_spec(spec)
        loader.exec_module(launcher)
        self.assertEqual(probe.guard_reason(), launcher.GUARD_REASON)
        self.assertTrue(probe.guard_reason())

    def test_any_other_pretooluse_error_classifies_as_hook_error(self):
        for text in ("PreToolUse:Bash hook error: Traceback (most recent call last):",
                     "PreToolUse:Bash hook error: blocked",
                     "PreToolUse:Bash hook failed"):
            with self.subTest(text=text):
                self.assertEqual(probe.classify({"is_error": True, "content": text}), "hook-error")

    def test_a_crashed_guard_fails_the_shipped_column(self):
        crashed = (True, "PreToolUse:Bash hook error: Traceback (most recent call last): OSError")
        rows = self.rows(**{cmd: crashed for cmd in self.LAUNCHER_CMDS})
        seen = probe.observe(rows, self.launches("reload", "stop"))
        self.assertEqual(seen["main_edits"], "hook-error")
        table = probe.judge("shipped", probe.observe(rows, self.launches("reload", "stop")))
        self.assertFalse(all(ok for _, ok, _ in table))
        self.assertNotIn("hook-error", {o for want in probe.EXPECTED.values() for outs in want.values()
                                        for o in outs})

    def test_every_check_has_an_expectation_for_every_variant(self):
        self.assertEqual(probe.VARIANTS, ("bare", "narrow", "shipped"))
        for variant in probe.VARIANTS:
            wanted = {"launch"} | set(probe.COMMANDS) | set(probe.SEQ_KEYS)
            self.assertEqual(set(probe.EXPECTED[variant]), wanted, variant)
        known = set(probe.COMMANDS) | set(probe.SEQ_KEYS)
        for _, keys in probe.CHECKS:
            for key in keys:
                self.assertIn(key, known)

    def test_the_expectations_are_the_recorded_ones(self):
        shipped = probe.EXPECTED["shipped"]
        for key in ("main_echo", "fg_echo", "bgin_echo", "bgb_echo", "bgb_echo3", "next_echo"):
            self.assertEqual(shipped[key], ("ran",), key)
        for key in ("main_edits", "main_status", "fg_stop", "bgin_edits", "bgb_edits", "bgb_after", "next_launch"):
            self.assertEqual(shipped[key], ("hook",), key)
        self.assertEqual((shipped["launch"], shipped["seq_first"], shipped["seq_second"]),
                         (("yes",), ("ran",), ("ran",)))
        for variant in ("bare", "narrow"):
            self.assertEqual(probe.EXPECTED[variant]["seq_first"], ("ran",), variant)
            self.assertEqual(probe.EXPECTED[variant]["seq_second"], ("denied",), variant)

    def test_the_probed_rule_is_the_one_the_hook_ships(self):
        with open(probe.SHIPPED_HOOKS) as fh:
            groups = json.load(fh)["hooks"]["PreToolUse"]
        self.assertEqual([h["if"] for g in groups for h in g["hooks"]], [probe.SHIPPED_RULE])
        self.assertEqual(probe.SHIPPED_RULE, probe.NARROW_DENY)

    def test_the_shipped_note_reports_a_skill_without_a_deny_rule_and_the_hook_rule(self):
        self.assertEqual(probe.shipped_note().splitlines(), [
            "shipped skill: no disallowed-tools line",
            "shipped hooks.json: its PreToolUse `if` is the probed rule"])

    def test_the_shipped_note_flags_a_skill_that_still_denies_and_a_different_rule(self):
        with tempfile.TemporaryDirectory(prefix="skill-probe-test-") as tmp:
            skill = os.path.join(tmp, "SKILL.md")
            with open(skill, "w") as fh:
                fh.write("---\nname: dash\ndisallowed-tools: Bash\n---\nbody\n")
            hooks = os.path.join(tmp, "hooks.json")
            with open(hooks, "w") as fh:
                json.dump({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"if": "Bash(x*)"}]}]}}, fh)
            with mock.patch.object(probe, "SHIPPED_SKILL", skill), mock.patch.object(probe, "SHIPPED_HOOKS", hooks):
                lines = probe.shipped_note().splitlines()
            self.assertIn("still has disallowed-tools ['Bash']", lines[0])
            self.assertIn("is ['Bash(x*)'], not the probed rule", lines[1])
            with mock.patch.object(probe, "SHIPPED_SKILL", skill), \
                    mock.patch.object(probe, "SHIPPED_HOOKS", os.path.join(tmp, "missing.json")):
                self.assertIn("no readable PreToolUse hook", probe.shipped_note())
            with mock.patch.object(probe, "SHIPPED_SKILL", os.path.join(tmp, "missing.md")):
                self.assertIn("not found", probe.shipped_note())


if __name__ == "__main__":
    unittest.main()
