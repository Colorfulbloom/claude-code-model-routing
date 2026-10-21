"""Tests for the install.py picker: state transitions, rendering, the plain
driver and two pty smoke tests. Standard library only, Python 3.9."""
import errno
import fcntl
import io
import os
import pty
import shutil
import select
import signal
import struct
import sys
import tempfile
import termios
import time
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import install as ins  # noqa: E402

AGENTS = ["alpha", "beta", "gamma"]
DEFAULTS = {"alpha": ("opus", "high"), "beta": ("sonnet", "medium"), "gamma": ("haiku", "low")}


def make_state(choices=None, saved=False):
    return ins.PickerState(choices or DEFAULTS, DEFAULTS, saved)


def preview(choices):
    return [ins.Entry("agents/%s.md" % n, 0o644, ("%s %s" % c).encode(), "src")
            for n, c in sorted(choices.items())]


def press(state, *actions):
    for a in actions:
        state.press(a)


def goto_model(state, index):
    """summary -> agents -> model screen of agent number `index`."""
    press(state, ins.DOWN, ins.ENTER)
    for _ in range(index):
        state.press(ins.DOWN)
    state.press(ins.ENTER)


def type_text(state, text):
    for ch in text:
        state.press(("char", ch))


class StateTests(unittest.TestCase):
    def test_fast_path_returns_current_choices(self):
        s = make_state()
        s.press(ins.ENTER)
        self.assertTrue(s.done)
        self.assertFalse(s.cancelled)
        self.assertEqual(s.result, DEFAULTS)

    def test_change_model_and_effort(self):
        s = make_state()
        goto_model(s, 1)
        self.assertEqual(s.screen, "model")
        self.assertEqual(s.agent, "beta")
        self.assertEqual(s.cursor, ins.ALIASES.index("sonnet"))
        press(s, ins.DOWN, ins.ENTER)  # opus
        self.assertEqual(s.screen, "effort")
        self.assertEqual(s.choices["beta"], ("opus", "medium"))
        self.assertEqual(s.cursor, ins.EFFORTS.index("medium"))
        press(s, ins.DOWN, ins.ENTER)  # high
        self.assertEqual(s.screen, "agents")
        self.assertEqual(s.choices["beta"], ("opus", "high"))
        press(s, ins.DOWN, ins.DOWN, ins.ENTER)  # Done -> review
        self.assertEqual(s.screen, "review")
        s.press(ins.ENTER)  # Install
        self.assertEqual(s.result["beta"], ("opus", "high"))
        self.assertEqual(s.result["alpha"], DEFAULTS["alpha"])

    def test_typed_id_valid(self):
        s = make_state()
        goto_model(s, 0)
        for _ in ins.ALIASES:
            s.press(ins.DOWN)
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "typed_id")
        self.assertEqual(s.text, "")
        type_text(s, "claude-opus-5-5x")
        s.press(ins.BACKSPACE)
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "effort")
        self.assertEqual(s.choices["alpha"], ("claude-opus-5-5", "high"))
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "agents")

    def test_typed_id_prefilled_and_invalid(self):
        choices = dict(DEFAULTS, alpha=("claude-x-1", "low"))
        s = make_state(choices)
        goto_model(s, 0)
        self.assertEqual(s.cursor, len(ins.ALIASES))
        s.press(ins.ENTER)
        self.assertEqual(s.text, "claude-x-1")
        for _ in range(len("claude-x-1")):
            s.press(ins.BACKSPACE)
        type_text(s, "inherit")
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "typed_id")
        self.assertTrue(s.error)
        self.assertEqual(s.choices["alpha"], ("claude-x-1", "low"))
        s.press(ins.BACKSPACE)
        self.assertEqual(s.error, "")
        type_text(s, ":")
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "typed_id")
        self.assertTrue(s.error)
        s.press(ins.BACK)
        self.assertEqual(s.screen, "model")

    def test_typed_id_rejects_bad_characters(self):
        for bad in ["a$b", "a\\b", "a{b}", "a|b", "a,b", "x;rm", "a b", "a:b", "a#b", 'a"b']:
            with self.subTest(text=bad):
                s = make_state()
                goto_model(s, 0)
                for _ in ins.ALIASES:
                    s.press(ins.DOWN)
                s.press(ins.ENTER)
                type_text(s, bad)
                s.press(ins.ENTER)
                self.assertEqual(s.screen, "typed_id")
                self.assertTrue(s.error)
                self.assertEqual(s.choices["alpha"], DEFAULTS["alpha"])

    def test_typed_id_accepts_real_ids(self):
        for good in ["claude-opus-5-5", "us.anthropic.claude-opus-5-5", "claude-opus-5-5@20261001", "claude-opus-5-5[1m]"]:
            with self.subTest(text=good):
                s = make_state()
                goto_model(s, 0)
                for _ in ins.ALIASES:
                    s.press(ins.DOWN)
                s.press(ins.ENTER)
                type_text(s, good)
                s.press(ins.ENTER)
                self.assertEqual(s.screen, "effort")
                self.assertEqual(s.error, "")
                self.assertEqual(s.choices["alpha"][0], good)

    def test_typed_id_quit_is_ignored(self):
        s = make_state()
        goto_model(s, 0)
        for _ in ins.ALIASES:
            s.press(ins.DOWN)
        s.press(ins.ENTER)
        s.press(ins.QUIT)
        self.assertFalse(s.done)
        type_text(s, "q")
        self.assertEqual(s.text, "q")

    def test_effort_snapping(self):
        old = ins.EFFORTS_BY_MODEL
        ins.EFFORTS_BY_MODEL = dict(old, haiku=["low", "high", "max"])
        try:
            self.assertEqual(ins.snap_effort("haiku", "medium"), "low")  # tie, lower wins
            self.assertEqual(ins.snap_effort("haiku", "xhigh"), "high")
            self.assertEqual(ins.snap_effort("haiku", "max"), "max")
            s = make_state()
            goto_model(s, 1)  # beta, sonnet/medium
            while s.cursor > 0:
                s.press(ins.UP)
            s.press(ins.ENTER)  # haiku
            self.assertEqual(s.choices["beta"], ("haiku", "low"))
            self.assertEqual([a for _, a in s.options()], ["low", "high", "max"])
            self.assertEqual(s.cursor, 0)
        finally:
            ins.EFFORTS_BY_MODEL = old

    def test_typed_id_uses_all_efforts(self):
        self.assertEqual(ins.snap_effort("some-id", "max"), "max")

    def test_effort_back_keeps_model(self):
        s = make_state()
        goto_model(s, 1)
        press(s, ins.DOWN, ins.ENTER, ins.BACK)
        self.assertEqual(s.screen, "agents")
        self.assertEqual(s.choices["beta"][0], "opus")

    def test_reset_row(self):
        choices = dict(DEFAULTS, beta=("fable", "max"))
        s = make_state(choices)
        press(s, ins.DOWN, ins.ENTER, ins.DOWN, ins.RESET_ROW)
        self.assertEqual(s.choices["beta"], DEFAULTS["beta"])
        s.press(ins.RESET_ROW)  # reset again is harmless
        self.assertEqual(s.choices["beta"], DEFAULTS["beta"])
        s.press(ins.BACK)
        self.assertEqual(s.screen, "summary")

    def test_reset_all(self):
        choices = dict(DEFAULTS, beta=("fable", "max"))
        s = make_state(choices)
        self.assertEqual([k for k, _ in s.options()], ["install", "change", "reset", "cancel"])
        press(s, ins.DOWN, ins.DOWN, ins.ENTER)
        self.assertEqual(s.choices, DEFAULTS)
        self.assertEqual(s.screen, "summary")
        self.assertEqual([k for k, _ in s.options()], ["install", "change", "cancel"])
        self.assertLess(s.cursor, 3)

    def test_cancel_at_each_screen(self):
        def at_summary(s):
            pass

        def at_agents(s):
            press(s, ins.DOWN, ins.ENTER)

        def at_model(s):
            goto_model(s, 0)

        def at_effort(s):
            goto_model(s, 0)
            s.press(ins.ENTER)

        def at_review(s):
            press(s, ins.DOWN, ins.ENTER)
            for _ in AGENTS:
                s.press(ins.DOWN)
            s.press(ins.ENTER)

        for name, setup in (("summary", at_summary), ("agents", at_agents), ("model", at_model),
                            ("effort", at_effort), ("review", at_review)):
            s = make_state()
            setup(s)
            self.assertEqual(s.screen, name)
            s.press(ins.QUIT)
            self.assertTrue(s.done, name)
            self.assertTrue(s.cancelled, name)
            self.assertIsNone(s.result, name)

    def test_cancel_option_on_summary_and_review(self):
        s = make_state()
        press(s, ins.DOWN, ins.DOWN, ins.ENTER)
        self.assertTrue(s.cancelled)
        s = make_state()
        press(s, ins.DOWN, ins.ENTER)
        for _ in AGENTS:
            s.press(ins.DOWN)
        press(s, ins.ENTER, ins.DOWN, ins.DOWN, ins.ENTER)
        self.assertTrue(s.cancelled)

    def test_back_navigation(self):
        s = make_state()
        press(s, ins.BACK)
        self.assertEqual(s.screen, "summary")
        self.assertFalse(s.done)
        goto_model(s, 0)
        s.press(ins.BACK)
        self.assertEqual(s.screen, "agents")
        s.press(ins.BACK)
        self.assertEqual(s.screen, "summary")
        self.assertEqual([k for k, _ in s.options()][s.cursor], "change")

    def test_review_contents_and_back(self):
        s = make_state()
        goto_model(s, 2)  # gamma haiku/low -> sonnet/low
        press(s, ins.DOWN, ins.ENTER, ins.ENTER)
        for _ in AGENTS:
            s.press(ins.DOWN)
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "review")
        lines, sel, footer = ins.render_screen(s, preview)
        self.assertIn("gamma  haiku low  ->  sonnet low", lines)
        self.assertIn("(2 agents unchanged)", lines)
        self.assertTrue(lines[sel].endswith("Install"))
        s.press(ins.DOWN)
        s.press(ins.ENTER)
        self.assertEqual(s.screen, "agents")


class RenderTests(unittest.TestCase):
    def test_summary(self):
        choices = dict(DEFAULTS, beta=("opus", "medium"))
        s = make_state(choices, saved=True)
        lines, sel, footer = ins.render_screen(s, preview)
        self.assertEqual(lines[0], "Model routing installer")
        self.assertEqual(lines[1], "(saved choices loaded)")
        header = [l for l in lines if l.startswith("AGENT")][0]
        self.assertIn("MODEL", header)
        self.assertIn("EFFORT", header)
        beta = [l for l in lines if l.startswith("beta")][0]
        self.assertIn("opus *", beta)
        self.assertNotIn("medium *", beta)
        alpha = [l for l in lines if l.startswith("alpha")][0]
        self.assertNotIn("*", alpha)
        self.assertEqual(lines[sel], "> Install with these settings")
        self.assertIn("  Reset all to defaults", lines)
        self.assertIn("  Cancel", lines)
        self.assertTrue(footer)

    def test_summary_without_saved_or_changes(self):
        lines, _, _ = ins.render_screen(make_state(), preview)
        self.assertNotIn("(saved choices loaded)", lines)
        self.assertNotIn("  Reset all to defaults", lines)

    def test_agents_screen(self):
        choices = dict(DEFAULTS, beta=("opus", "max"))
        s = make_state(choices)
        press(s, ins.DOWN, ins.ENTER)
        lines, sel, _ = ins.render_screen(s, preview)
        alpha = [l for l in lines if "alpha" in l][0]
        beta = [l for l in lines if "beta" in l][0]
        self.assertTrue(alpha.rstrip().endswith("default"))
        self.assertIn("default: sonnet medium", beta)
        self.assertIn("  Done, review", lines)
        self.assertIn("alpha", lines[sel])

    def test_model_screen(self):
        s = make_state()
        goto_model(s, 0)
        lines, sel, _ = ins.render_screen(s, preview)
        self.assertEqual(lines[0], "alpha: model")
        opus = [l for l in lines if " opus" in l][0]
        self.assertIn("(*)", opus)
        self.assertIn("default", opus)
        haiku = [l for l in lines if " haiku" in l][0]
        self.assertIn("( )", haiku)
        fable = [l for l in lines if " fable" in l][0]
        self.assertIn(ins.FABLE_NOTE, fable)
        self.assertTrue(any(l.endswith("Other: type a model id") for l in lines))
        self.assertIn("inherit is not offered: the dispatch hook blocks it.", lines)
        self.assertIn("opus", lines[sel])

    def test_typed_id_screen(self):
        s = make_state()
        goto_model(s, 0)
        for _ in ins.ALIASES:
            s.press(ins.DOWN)
        s.press(ins.ENTER)
        type_text(s, "a b")
        s.press(ins.ENTER)
        lines, sel, _ = ins.render_screen(s, preview)
        self.assertIn("Model id: a b_", lines[sel])
        self.assertTrue(any("Not a valid model id" in l for l in lines))

    def test_effort_screen(self):
        s = make_state()
        goto_model(s, 0)
        s.press(ins.ENTER)
        lines, sel, _ = ins.render_screen(s, preview)
        self.assertEqual(lines[0], "alpha on opus: effort")
        high = [l for l in lines if " high" in l][0]
        self.assertIn("(*)", high)
        self.assertIn("default", high)
        self.assertIn("high", lines[sel])

    def test_review_file_plan(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("MR_TEST_TMP") or None)
        try:
            os.makedirs(tmp + "/agents")
            with open(tmp + "/agents/alpha.md", "wb") as fh:
                fh.write(b"opus high")  # same as the preview
            with open(tmp + "/agents/beta.md", "wb") as fh:
                fh.write(b"different")
            s = make_state()
            press(s, ins.DOWN, ins.ENTER)
            for _ in AGENTS:
                s.press(ins.DOWN)
            s.press(ins.ENTER)
            lines, _, _ = ins.render_screen(s, preview, tmp)
            text = "\n".join(lines)
            self.assertNotIn("agents/alpha.md", text)
            self.assertIn("replace    agents/beta.md", text)
            self.assertIn("add        agents/gamma.md", text)
            self.assertIn("(3 agents unchanged)", text)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_ascii_only(self):
        for setup in ([], [ins.DOWN, ins.ENTER], [ins.DOWN, ins.ENTER, ins.DOWN, ins.ENTER]):
            st = make_state(dict(DEFAULTS, beta=("fable", "max")), saved=True)
            press(st, *setup)
            lines, _, footer = ins.render_screen(st, preview)
            for l in lines + [footer]:
                l.encode("ascii")
        self.assertNotIn("\u2014", ins.PICKER_TOO_SMALL)

    def test_key_mapping(self):
        k = ins.key_to_action
        self.assertEqual(k(ord("j"), "agents"), ins.DOWN)
        self.assertEqual(k(259, "agents"), ins.UP)
        self.assertEqual(k(10, "agents"), ins.ENTER)
        self.assertEqual(k(27, "model"), ins.BACK)
        self.assertEqual(k(263, "model"), ins.BACK)
        self.assertEqual(k(ord("q"), "model"), ins.QUIT)
        self.assertEqual(k(ord("r"), "agents"), ins.RESET_ROW)
        self.assertEqual(k(263, "typed_id"), ins.BACKSPACE)
        self.assertEqual(k(27, "typed_id"), ins.BACK)
        self.assertEqual(k(ord("q"), "typed_id"), ("char", "q"))


class PlainDriverTests(unittest.TestCase):
    def run_plain(self, answers, state=None):
        state = state or make_state()
        it = iter(answers)

        def inp(prompt):
            try:
                return next(it)
            except StopIteration:
                raise EOFError
        out = io.StringIO()
        ins.run_plain_picker(state, preview, None, inp, out)
        return state, out.getvalue()

    def test_install_now(self):
        s, out = self.run_plain(["1"])
        self.assertEqual(s.result, DEFAULTS)
        self.assertIn(" 1) Install with these settings", out)
        out.encode("ascii")

    def test_enter_keeps_current(self):
        s, _ = self.run_plain([""])
        self.assertEqual(s.result, DEFAULTS)

    def test_change_flow(self):
        # Change, agent 2 (beta), model opus (3), effort max (5), Done (4), Install (1)
        s, out = self.run_plain(["2", "2", "3", "5", "4", "1"])
        self.assertEqual(s.result["beta"], ("opus", "max"))
        self.assertIn("beta: model", out)

    def test_typed_id_and_back(self):
        s, _ = self.run_plain(["2", "1", "5", "bad id", "b", "b", "b", "q"])
        self.assertTrue(s.cancelled)
        s, out = self.run_plain(["2", "1", "5", "bad:id", "claude-x-9", "3", "4", "1"])
        self.assertEqual(s.result["alpha"], ("claude-x-9", "high"))
        self.assertIn("Not a valid model id", out)

    def test_reset_row_and_bad_input(self):
        s, out = self.run_plain(["2", "r 1", "r 9", "zzz", "b", "q"],
                                make_state(dict(DEFAULTS, alpha=("haiku", "low"))))
        self.assertTrue(s.cancelled)
        self.assertEqual(s.choices["alpha"], DEFAULTS["alpha"])
        self.assertIn("Enter a number from 1 to", out)

    def test_eof_cancels(self):
        s, _ = self.run_plain([])
        self.assertTrue(s.cancelled)
        s, _ = self.run_plain(["2", "1", "5"])  # EOF inside typed_id
        self.assertTrue(s.cancelled)

    def test_run_picker_plain_flag(self):
        import builtins
        old_input = builtins.input
        answers = iter(["q"])
        builtins.input = lambda prompt="": next(answers)
        try:
            real_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                self.assertIsNone(ins.run_picker(dict(DEFAULTS), preview, plain=True, defaults=DEFAULTS))
            finally:
                sys.stdout = real_stdout
        finally:
            builtins.input = old_input

    def test_run_picker_dumb_term(self):
        import builtins
        old_input = builtins.input
        old_term = os.environ.get("TERM")
        os.environ["TERM"] = "dumb"
        builtins.input = lambda prompt="": "1"
        try:
            real_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                result = ins.run_picker(dict(DEFAULTS), preview, defaults=DEFAULTS)
            finally:
                sys.stdout = real_stdout
        finally:
            builtins.input = old_input
            if old_term is None:
                os.environ.pop("TERM", None)
            else:
                os.environ["TERM"] = old_term
        self.assertEqual(result, DEFAULTS)

    def test_run_picker_curses_error_falls_back_to_plain(self):
        import builtins
        import curses
        old_input, old_wrapper = builtins.input, curses.wrapper
        old_term = os.environ.get("TERM")
        os.environ["TERM"] = "xterm-256color"

        def failing_wrapper(*args, **kwargs):
            raise curses.error("setupterm failed")

        curses.wrapper = failing_wrapper
        builtins.input = lambda prompt="": "1"
        try:
            real_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                result = ins.run_picker(dict(DEFAULTS), preview, defaults=DEFAULTS)
                printed = sys.stdout.getvalue()
            finally:
                sys.stdout = real_stdout
        finally:
            builtins.input, curses.wrapper = old_input, old_wrapper
            if old_term is None:
                os.environ.pop("TERM", None)
            else:
                os.environ["TERM"] = old_term
        self.assertEqual(result, DEFAULTS)
        self.assertIn(" 1) Install with these settings", printed)


class FindOrderTests(unittest.TestCase):
    def test_preorder_unsorted_and_symlinks(self):
        tmp = tempfile.mkdtemp(dir=os.environ.get("MR_TEST_TMP") or None)
        try:
            os.makedirs(tmp + "/sub/deep")
            for rel in ("a.md", "sub/b.md", "sub/deep/c.md", "z.txt"):
                with open(os.path.join(tmp, rel), "w") as fh:
                    fh.write("x")
            os.symlink("a.md", tmp + "/link.md")
            os.symlink("sub", tmp + "/dirlink.md")
            got = ins.find_agent_md_files(tmp)
            self.assertEqual(sorted(got), sorted(
                [tmp + "/a.md", tmp + "/sub/b.md", tmp + "/sub/deep/c.md", tmp + "/link.md", tmp + "/dirlink.md"]))
            names = [e.name for e in os.scandir(tmp)]
            expected = []
            for name in names:
                p = tmp + "/" + name
                if name.endswith(".md") and (os.path.islink(p) or os.path.isfile(p)):
                    expected.append(p)
                if os.path.isdir(p) and not os.path.islink(p):
                    sub = [e.name for e in os.scandir(p)]
                    for n2 in sub:
                        p2 = p + "/" + n2
                        if n2.endswith(".md") and os.path.isfile(p2):
                            expected.append(p2)
                        if os.path.isdir(p2):
                            expected.extend(p2 + "/" + e.name for e in os.scandir(p2) if e.name.endswith(".md"))
            self.assertEqual(got, expected)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PtyTests(unittest.TestCase):
    TIMEOUT = 30

    def setUp(self):
        self.root = tempfile.mkdtemp(dir=os.environ.get("MR_TEST_TMP") or None)
        self.root = os.path.realpath(self.root)
        self.home = self.root + "/home"
        self.config = self.home + "/.claude"
        os.makedirs(self.home)
        os.makedirs(self.root + "/bin")
        stub = self.root + "/bin/claude"
        with open(stub, "w") as fh:
            fh.write("#!/bin/sh\necho '2.1.302 (Claude Code)'\n")
        os.chmod(stub, 0o755)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_pty(self, term, steps, args=("--dry-run",)):
        """Runs install.py --dry-run in a pty. `steps` is a list of (wait_for,
        keys): wait until wait_for appears in the output (or None to just pause),
        then send keys. Returns (exit status, output)."""
        for path in (self.home, self.config):
            self.assertTrue(path.startswith(self.root + os.sep), path)
        env = {"HOME": self.home, "CLAUDE_CONFIG_DIR": self.config, "TERM": term,
               "PATH": self.root + "/bin:/usr/bin:/bin", "LANG": "C"}
        pid, master = pty.fork()
        if pid == 0:
            try:
                os.execve("/usr/bin/python3", ["/usr/bin/python3", REPO + "/install.py"] + list(args), env)
            finally:
                os._exit(127)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        deadline = time.time() + self.TIMEOUT
        buf = b""

        def drain(wait):
            nonlocal buf
            end = time.time() + wait
            while True:
                left = max(0.0, min(end, deadline) - time.time())
                r, _, _ = select.select([master], [], [], left)
                if not r:
                    return True
                try:
                    chunk = os.read(master, 65536)
                except OSError as exc:
                    if exc.errno == errno.EIO:
                        return False
                    raise
                if not chunk:
                    return False
                buf += chunk
        status = None
        try:
            for wait_for, keys in steps:
                if wait_for is None:
                    drain(0.4)
                else:
                    while wait_for.encode() not in buf:
                        if time.time() > deadline:
                            self.fail("timed out waiting for %r; output so far: %r" % (wait_for, buf[-600:]))
                        if not drain(0.2) and wait_for.encode() not in buf:
                            self.fail("process ended before %r: %r" % (wait_for, buf[-600:]))
                os.write(master, keys.encode())
            while time.time() < deadline:
                if not drain(0.2):
                    break
            while time.time() < deadline:
                done, st = os.waitpid(pid, os.WNOHANG)
                if done:
                    status = st
                    break
                time.sleep(0.05)
            if status is None:
                self.fail("install.py did not exit in time; output: %r" % buf[-600:])
        finally:
            if status is None:
                try:
                    os.kill(pid, signal.SIGKILL)
                    os.waitpid(pid, 0)
                except OSError:
                    pass
            os.close(master)
        code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
        return code, buf.decode("utf-8", "replace")

    def test_curses_picker_change_scout(self):
        # Summary: j, Enter (Change). Agents: j x4 to scout, Enter. Model: j (sonnet),
        # Enter. Effort: j (medium), Enter. Agents: j j (Done), Enter. Review: Enter (Install).
        keys = [("Model routing installer", "j"), (None, "\n"), (None, "jjjj"), (None, "\n"),
                (None, "j"), (None, "\n"), (None, "j"), (None, "\n"), (None, "jj"), (None, "\n"),
                (None, "\n")]
        code, out = self.run_pty("xterm-256color", keys)
        self.assertEqual(code, 0, out[-800:])
        self.assertIn("Agent models: picker", out)
        self.assertIn("haiku low  ->  sonnet medium", out)
        self.assertNotIn("replace    agents/scout.md", out)
        self.assertIn("  add        agents/scout.md", out)
        self.assertFalse(os.path.exists(self.config), "dry run must not create the config dir")

    def test_invalid_settings_exits_before_picker(self):
        os.makedirs(self.config)
        with open(self.config + "/settings.json", "w") as fh:
            fh.write("{not json")
        for term in ("xterm-256color", "dumb"):
            with self.subTest(term=term):
                code, out = self.run_pty(term, [])
                self.assertEqual(code, 1, out[-800:])
                self.assertNotIn("Model routing installer", out)
                self.assertNotIn("Choose 1-", out)
                self.assertIn("settings.json", out)
                self.assertFalse(os.path.exists(self.config + "/agents"))

    def test_plain_picker_dumb_term(self):
        code, out = self.run_pty("dumb", [("Choose 1-", "1\n")])
        self.assertEqual(code, 0, out[-800:])
        self.assertIn("Agent models: picker", out)
        self.assertFalse(os.path.exists(self.config))


if __name__ == "__main__":
    unittest.main()
