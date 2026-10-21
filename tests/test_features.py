"""Tests for the model and effort flags, rendering, saved choices and the shim.

Everything runs in throwaway sandboxes (see helpers.py). Run from the repo root:
    /usr/bin/python3 -m unittest tests.test_features -v
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from helpers import CHOICES, MANIFEST, REPO, Sandbox  # noqa: E402

AGENTS = ["deep-reasoner", "designer", "fast-worker", "judge", "scout", "verifier"]


def load_install():
    spec = importlib.util.spec_from_file_location("install_under_test", os.path.join(REPO, "install.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    with open(path, "rb") as fh:
        return fh.read()


def repo_agent(name):
    return read(os.path.join(REPO, "agents", name + ".md"))


def repo_defaults():
    inst = load_install()
    return {n: inst.parse_agent_defaults(repo_agent(n).decode("utf-8"), n) for n in AGENTS}


class SandboxCase(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox("new")
        self.addCleanup(self.sb.cleanup)
        self.cfg = self.sb.cfg

    def run_install(self, *args, **kw):
        return self.sb.run(list(args), **kw)

    def cpath(self, *parts):
        return os.path.join(self.cfg, *parts)

    def expected_choices(self, overrides=None):
        d = {n: {"model": m, "effort": e} for n, (m, e) in repo_defaults().items()}
        for n, (m, e) in (overrides or {}).items():
            d[n] = {"model": m, "effort": e}
        return json.dumps({"format": 1, "agents": {k: d[k] for k in sorted(d)}}, indent=2) + "\n"

    def backups_with(self, rel):
        out = []
        bdir = self.cpath("backups")
        if os.path.isdir(bdir):
            for d in os.listdir(bdir):
                if os.path.exists(os.path.join(bdir, d, rel)):
                    out.append(d)
        return out

    def assert_usage_error(self, *args):
        step = self.run_install(*args)
        self.assertEqual(step.code, 2, (args, step.out, step.err))
        self.assertIn("Usage: install.sh", step.err, args)
        self.assertFalse(os.path.exists(self.cfg), "config dir created for %r" % (args,))
        return step


class CustomizedInstall(SandboxCase):
    def test_01_agent_flag_fresh_install(self):
        step = self.run_install("--yes", "--agent", "scout=sonnet:medium")
        self.assertEqual(step.code, 0, step.err)
        self.assertIn("Agent models: defaults with --agent", step.out)
        repo = repo_agent("scout").decode().splitlines(True)
        got = read(self.cpath("agents", "scout.md")).decode().splitlines(True)
        self.assertEqual(len(repo), len(got))
        diff = [(a, b) for a, b in zip(repo, got) if a != b]
        self.assertTrue(all(b.startswith(("model:", "effort:")) for _, b in diff), diff)
        self.assertIn("model: sonnet\n", got)
        self.assertIn("effort: medium\n", got)
        self.assertEqual(len(diff), 2)
        self.assertEqual(read(self.cpath(CHOICES)).decode(),
                         self.expected_choices({"scout": ("sonnet", "medium")}))
        self.assertEqual(os.stat(self.cpath(CHOICES)).st_mode & 0o777, 0o644)
        self.assertIn(CHOICES, read(self.cpath(MANIFEST)).decode().split("\n"))

    def test_02_rerun_uses_saved_choices(self):
        self.run_install("--yes", "--agent", "scout=sonnet:medium")
        step = self.run_install()
        self.assertEqual(step.code, 0, step.err)
        self.assertIn("Agent models: saved choices (%s)" % self.sb.normalize(self.cpath(CHOICES)), step.out)
        files = [l for l in step.out.split("\n") if l.startswith("  ") and ("agents/" in l or CHOICES in l or "rules/" in l)]
        self.assertTrue(files)
        for l in files:
            self.assertTrue(l.startswith("  unchanged"), l)
        self.assertFalse(os.path.isdir(self.cpath("backups")))

    def test_03_reset(self):
        self.run_install("--yes", "--agent", "scout=sonnet:medium")
        step = self.run_install("--reset")
        self.assertEqual(step.code, 0, step.err)
        self.assertIn("Agent models: defaults\n", step.out)
        self.assertEqual(read(self.cpath("agents", "scout.md")), repo_agent("scout"))
        self.assertRegex(step.out, r"(?m)^  replace\s+agents/scout\.md")
        self.assertRegex(step.out, r"(?m)^  replace\s+%s" % CHOICES.replace(".", r"\."))
        self.assertTrue(self.backups_with(os.path.join("agents", "scout.md")))
        self.assertTrue(self.backups_with(CHOICES))
        self.assertEqual(read(self.cpath(CHOICES)).decode(), self.expected_choices())

    def test_04_second_agent_flag_keeps_effort_and_saved(self):
        self.run_install("--yes", "--agent", "scout=sonnet:medium")
        # first give judge a known effort, then change only the model
        self.run_install("--yes", "--agent", "judge=sonnet:medium")
        step = self.run_install("--yes", "--agent", "judge=opus")
        self.assertEqual(step.code, 0, step.err)
        self.assertIn("Agent models: saved choices with --agent", step.out)
        data = json.loads(read(self.cpath(CHOICES)))
        self.assertEqual(data["agents"]["judge"], {"model": "opus", "effort": "medium"})
        self.assertEqual(data["agents"]["scout"], {"model": "sonnet", "effort": "medium"})

    def test_05_uninstall_after_customized_install(self):
        self.run_install("--yes", "--agent", "scout=sonnet:medium")
        step = self.run_install("--uninstall")
        self.assertEqual(step.code, 0, step.err)
        self.assertRegex(step.out, r"(?m)^  remove\s+agents/scout\.md")
        self.assertRegex(step.out, r"(?m)^  remove\s+%s" % CHOICES.replace(".", r"\."))
        self.assertNotRegex(step.out, r"(?m)^  edited")
        self.assertFalse(os.path.exists(self.cpath("agents", "scout.md")))
        self.assertFalse(os.path.exists(self.cpath(CHOICES)))
        self.assertEqual(self.backups_with(os.path.join("agents", "scout.md")), [])
        settings = read(self.cpath("settings.json")).decode()
        self.assertNotIn("require-agent-model", settings)
        self.assertNotIn("check-agent-models", settings)


class UpgradeFromOld(SandboxCase):
    def run_old(self, *args):
        proc = helpers.run("old", list(args), self.sb.home, self.cfg, None, subprocess.DEVNULL, sandbox=self.sb)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")

    def ours(self):
        data = json.loads(read(self.cpath("settings.json")))
        found = {}
        for event, needle in (("PreToolUse", "require-agent-model"), ("SessionStart", "check-agent-models")):
            found[event] = [h for g in data.get("hooks", {}).get(event, []) for h in g.get("hooks", [])
                            if needle in h.get("command", "")]
        return found

    def agent_bytes(self):
        return {n: read(self.cpath("agents", n + ".md")) for n in AGENTS}

    def test_12_upgrade_then_uninstall(self):
        code, _out, err = self.run_old()
        self.assertEqual(code, 0, err)
        agents_before = self.agent_bytes()
        self.assertFalse(os.path.exists(self.cpath(CHOICES)))
        step = self.run_install("--yes")
        self.assertEqual(step.code, 0, step.err)
        found = self.ours()
        self.assertEqual(len(found["PreToolUse"]), 1, found)
        self.assertEqual(len(found["SessionStart"]), 1, found)
        manifest = read(self.cpath(MANIFEST)).decode().split("\n")
        self.assertEqual(manifest.count(CHOICES), 1)
        self.assertTrue(os.path.isfile(self.cpath(CHOICES)))
        self.assertEqual(self.agent_bytes(), agents_before)
        paths = [l for l in manifest if l and not l.startswith("#")]
        self.assertTrue(paths)
        step = self.run_install("--uninstall")
        self.assertEqual(step.code, 0, step.err)
        for rel in paths:
            self.assertFalse(os.path.exists(self.cpath(rel)), rel)
        self.assertFalse(os.path.exists(self.cpath(CHOICES)))
        found = self.ours()
        self.assertEqual(found, {"PreToolUse": [], "SessionStart": []})


class UsageErrors(SandboxCase):
    CASES = [
        ["--agent"],
        ["--agent="],
        ["--agent", "scout"],
        ["--agent", "nosuch=haiku"],
        ["--agent", "scout=inherit"],
        ["--agent", "scout=sonnet:extreme"],
        ["--agent", "scout=bad id"],
        ["--uninstall", "--agent", "scout=haiku"],
        ["--uninstall", "--reset"],
    ]

    def test_06_usage_errors(self):
        for case in self.CASES:
            with self.subTest(args=case):
                self.assert_usage_error(*case)


class TypedIds(SandboxCase):
    def test_07_typed_ids_verbatim(self):
        for model, effort in (("claude-opus-5-5[1m]", "max"), ("us.anthropic.claude-sonnet-5-5", "low"),
                              ("claude-opus-5-5@20260101", "high")):
            with self.subTest(model=model):
                step = self.run_install("--yes", "--agent", "scout=%s:%s" % (model, effort))
                self.assertEqual(step.code, 0, step.err)
                text = read(self.cpath("agents", "scout.md")).decode()
                self.assertIn("\nmodel: %s\n" % model, text)
                self.assertIn("\neffort: %s\n" % effort, text)


BAD_IDS = ["a$b", "a\\b", "a{b}", "a|b", "a,b", "x;rm", "a b", "a:b", "a#b", 'a"b']
GOOD_IDS = ["claude-opus-5-5", "us.anthropic.claude-opus-5-5", "claude-opus-5-5@20261001", "claude-opus-5-5[1m]"]


class ModelIdCharset(SandboxCase):
    def test_07b_bad_ids_rejected_by_agent_flag(self):
        for bad in BAD_IDS:
            with self.subTest(model=bad):
                self.assert_usage_error("--agent", "scout=" + bad)

    def test_07c_good_ids_accepted_by_agent_flag(self):
        for good in GOOD_IDS:
            with self.subTest(model=good):
                step = self.run_install("--yes", "--agent", "scout=" + good)
                self.assertEqual(step.code, 0, step.err)
                self.assertIn("\nmodel: %s\n" % good, read(self.cpath("agents", "scout.md")).decode())


class FakeStream(object):
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class Units(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst = load_install()

    def test_08a_import_has_no_side_effects(self):
        self.assertTrue(callable(self.inst.main))

    def test_08b_validate_model_accepts(self):
        for v in ["haiku", "sonnet", "opus", "fable", "claude-opus-5-5[1m]", "us.anthropic.claude-sonnet-5-5",
                  "claude-opus-5-5@20260101", "a" * 100, "9abc"]:
            self.assertTrue(self.inst.validate_model(v), v)

    def test_08c_validate_model_rejects(self):
        for v in ["inherit", "", "a" * 101, "a b", "a\tb", 'a"b', "a'b", "a:b", "a#b", "a`b", "-abc", ".abc"]:
            self.assertFalse(self.inst.validate_model(v), repr(v))

    def test_08c2_validate_model_charset(self):
        for v in BAD_IDS:
            self.assertFalse(self.inst.validate_model(v), repr(v))
        for v in GOOD_IDS:
            self.assertTrue(self.inst.validate_model(v), repr(v))

    def test_08d_valid_effort(self):
        for model in ["haiku", "sonnet", "opus", "fable", "claude-opus-5-5"]:
            for e in ["low", "medium", "high", "xhigh", "max"]:
                self.assertTrue(self.inst.valid_effort(model, e), (model, e))
            self.assertFalse(self.inst.valid_effort(model, "extreme"), model)

    def test_08e_render_defaults_is_identity(self):
        for name in AGENTS:
            text = repo_agent(name).decode("utf-8")
            model, effort = self.inst.parse_agent_defaults(text, name)
            self.assertEqual(self.inst.render_agent(text, model, effort, name), text, name)

    def test_08f_render_changes_two_lines_keeps_crlf(self):
        text = "---\r\nname: x\r\nmodel: haiku\r\neffort: low\r\nnote: model: keep\r\n---\r\nbody\r\nmodel: body\r\n"
        out = self.inst.render_agent(text, "opus", "max")
        self.assertEqual(out, "---\r\nname: x\r\nmodel: opus\r\neffort: max\r\nnote: model: keep\r\n---\r\nbody\r\nmodel: body\r\n")

    def test_08g_is_interactive(self):
        tty, no = FakeStream(True), FakeStream(False)
        f = self.inst.is_interactive
        self.assertFalse(f(tty, tty, {"CI": "1"}))
        self.assertFalse(f(no, tty, {}))
        self.assertFalse(f(tty, no, {}))
        self.assertTrue(f(tty, tty, {}))
        self.assertTrue(f(tty, tty, {"CI": ""}))

    def test_08h_ci_values(self):
        tty = FakeStream(True)
        for ci in ("false", "0", "", "False", "NO", "off"):
            self.assertTrue(self.inst.is_interactive(tty, tty, {"CI": ci}), repr(ci))
        for ci in ("true", "1", "yes", "True"):
            self.assertFalse(self.inst.is_interactive(tty, tty, {"CI": ci}), repr(ci))

    def test_08i_manifest_paths_raw(self):
        text = "# c\n\n  \nagents/a.md \n a/b\n../x\n"
        self.assertEqual(self.inst.manifest_paths(text), ["agents/a.md ", " a/b", "../x"])


class SavedChoicesRobustness(SandboxCase):
    def run_with_choices(self, content):
        self.sb.write(self.cpath(CHOICES), content)
        return self.run_install("--yes")

    def test_09a_not_json(self):
        step = self.run_with_choices("this is not json")
        self.assertEqual(step.code, 0, step.err)
        warn = [l for l in (step.out + step.err).split("\n") if l.startswith("Warning")]
        self.assertEqual(len(warn), 1, warn)
        for n in AGENTS:
            self.assertEqual(read(self.cpath("agents", n + ".md")), repo_agent(n), n)

    def test_09b_one_bad_entry(self):
        agents = {n: {"model": m, "effort": e} for n, (m, e) in repo_defaults().items()}
        agents["scout"] = {"model": "inherit", "effort": "low"}
        agents["judge"] = {"model": "opus", "effort": "max"}
        step = self.run_with_choices(json.dumps({"format": 1, "agents": agents}))
        self.assertEqual(step.code, 0, step.err)
        warn = [l for l in (step.out + step.err).split("\n") if l.startswith("Warning")]
        self.assertEqual(len(warn), 1, warn)
        self.assertIn("scout", warn[0])
        self.assertEqual(read(self.cpath("agents", "scout.md")), repo_agent("scout"))
        judge = read(self.cpath("agents", "judge.md")).decode()
        self.assertIn("\nmodel: opus\n", judge)
        self.assertIn("\neffort: max\n", judge)

    def test_09c_unknown_agent_key_ignored(self):
        agents = {"ghost": {"model": "opus", "effort": "low"}}
        step = self.run_with_choices(json.dumps({"format": 1, "agents": agents}))
        self.assertEqual(step.code, 0, step.err)
        self.assertNotIn("Warning", step.out + step.err)
        self.assertNotIn("ghost", step.out + step.err.replace(self.cfg, ""))


class Shim(SandboxCase):
    def run_shim(self, path_dirs):
        env = {"HOME": self.sb.home, "CLAUDE_CONFIG_DIR": self.cfg, "PATH": ":".join(path_dirs),
               "LANG": "C", "LC_ALL": "C"}
        self.sb.check_env(env, self.sb.root)
        return subprocess.run(["/bin/bash", os.path.join(self.sb.src, "install.sh"), "--yes"], env=env,
                              cwd=self.sb.root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=60)

    def mkbin(self, name):
        d = self.sb.p(name)
        os.makedirs(d)
        os.symlink("/bin/bash", os.path.join(d, "bash"))
        return d

    def test_10a_old_python(self):
        d = self.mkbin("oldpy")
        self.sb.write(os.path.join(d, "python3"),
                      '#!/bin/sh\ncase "$1" in --version) echo "Python 3.8.10";; *) exit 1;; esac\n', 0o755)
        proc = self.run_shim([d])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stderr.decode(),
                         "Error: python3 is older than 3.9 (Python 3.8.10). Install a newer one and run this again.\n")
        self.assertFalse(os.path.exists(self.cfg))

    def test_10b_no_python(self):
        d = self.mkbin("nopy")
        proc = self.run_shim([d])
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(proc.stderr.decode(), "Error: python3 is not on PATH. Install it and run this again.\n")
        self.assertFalse(os.path.exists(self.cfg))


class DryRun(SandboxCase):
    def test_11_dry_run_with_agent(self):
        step = self.run_install("--dry-run", "--agent", "scout=sonnet:medium")
        self.assertEqual(step.code, 0, step.err)
        self.assertFalse(os.path.exists(self.cfg))
        self.assertRegex(step.out, r"(?m)^  add\s+agents/scout\.md")
        self.assertRegex(step.out, r"(?m)^  add\s+%s" % CHOICES.replace(".", r"\."))
        self.assertIn("Agent models: defaults with --agent", step.out)


if __name__ == "__main__":
    unittest.main()
