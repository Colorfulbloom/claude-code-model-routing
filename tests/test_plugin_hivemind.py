"""Checks of the hivemind plugin's wrapper, plugins/hivemind/bin/hivemind, run as a subprocess.

The wrapper loads the plugin's own copy of the HiveMind library and prints one text per situation. These tests run it
against throwaway git projects with throwaway stores, a throwaway HOME and a throwaway CLAUDE_CONFIG_DIR. Nothing here
reads the real ~/.claude, runs `claude` or touches the repo's own .claude/hivemind. Every run must exit 0 and print
nothing on stderr, because a non-zero exit from a skill's ! line aborts the skill.
"""
import contextlib
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import helpers

sys.dont_write_bytecode = True

REPO = helpers.REPO
PLUGIN = os.path.join(REPO, "plugins", "hivemind")
WRAPPER = os.path.join(PLUGIN, "bin", "hivemind")
PAYLOAD_LIB = os.path.join(PLUGIN, "payload", "hooks", "hivemind_lib.py")
TODAY = "2026-10-20"

USAGE_ALL = ("error: wrong arguments. Use /hivemind:status | /hivemind:check | /hivemind:inbox | /hivemind:init | "
             "/hivemind:consolidate | /hivemind:link [<id> <sha or base..head>] | "
             "/hivemind:related <path>... (1 to 20 paths, none starting with -)")
USAGE_ONE = {
    "status": "/hivemind:status",
    "check": "/hivemind:check",
    "inbox": "/hivemind:inbox",
    "init": "/hivemind:init",
    "consolidate": "/hivemind:consolidate",
    "link": "/hivemind:link [<id> <sha or base..head>]",
    "related": "/hivemind:related <path>... (1 to 20 paths, none starting with -)",
}
NO_PROJECT = "error: no project found. Start Claude Code from inside a git repository."
LINK_NONE = "No history entries are waiting for a commit."
LINK_HEADING = ("These history entries are waiting for a commit. "
                "Link each one with /hivemind:link <id> <sha>.")
HOOKS_DIFFER = ("note: the installed HiveMind library differs from this plugin's copy. "
                "Rerun ./install.sh from an up-to-date clone of the repo.")


def load_lib():
    spec = importlib.util.spec_from_file_location("hivemind_lib_for_plugin_tests", PAYLOAD_LIB)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LIB = load_lib()


def usage(action=None):
    return "error: wrong arguments. Use " + USAGE_ONE[action] if action else USAGE_ALL


def off_message(root):
    return "HiveMind is off in %s. Run /hivemind:init to turn it on." % root


def hooks_missing(cfg):
    return ("note: the HiveMind hooks aren't installed at %s, so nothing captures new facts. "
            "Run ./install.sh from the model routing repo." % os.path.join(cfg, "hooks", "hivemind_lib.py"))


def tree_hash(folder):
    """Every path under folder (directories and files, relative) with each file's sha256."""
    out = {}
    for dirpath, dirs, files in os.walk(folder):
        for name in dirs:
            out[os.path.relpath(os.path.join(dirpath, name), folder) + "/"] = None
        for name in files:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, folder)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class Result:
    def __init__(self, proc):
        self.code = proc.returncode
        self.out = proc.stdout
        self.err = proc.stderr
        self.lines = proc.stdout.rstrip("\n").split("\n") if proc.stdout.strip() else []


class WrapperCase(unittest.TestCase):
    """A throwaway HOME, config dir and git project with one commit on main."""

    def setUp(self):
        self.base = os.path.realpath(tempfile.mkdtemp(prefix="mr-hivemind-plugin-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.base)
        self.home = os.path.join(self.base, "user")
        self.cfg = os.path.join(self.base, "user-cfg")
        self.plain = os.path.join(self.base, "plain")
        self.proj = os.path.join(self.base, "proj")
        for folder in (self.home, self.cfg, self.plain, self.proj):
            os.makedirs(folder)
        self.store = LIB.store_path(self.proj)
        self.git("init", "-q", "-b", "main")
        self.commit("a.txt")

    # ---- building blocks

    def base_env(self):
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": self.home, "CLAUDE_CONFIG_DIR": self.cfg,
                "TMPDIR": self.base, "LANG": "C", "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CEILING_DIRECTORIES": self.base,
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

    def git(self, *args, cwd=None):
        proc = subprocess.run(["git", "-c", "commit.gpgsign=false"] + list(args), cwd=cwd or self.proj,
                              env=self.base_env(), stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc.stdout.strip()

    def commit(self, name, text="x\n"):
        """Commit a new file in the project; returns the full SHA."""
        with open(os.path.join(self.proj, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        self.git("add", name)
        self.git("commit", "-q", "-m", "add " + name)
        return self.git("rev-parse", "HEAD")

    def run_wrapper(self, *args, project=None, cwd=None, env=None, wrapper=WRAPPER, bare=False, stdin=None):
        """Run the wrapper as the skills do. Every run must exit 0 and leave stderr empty.

        stdin is text for the child, or None for an empty stdin."""
        argv = [sys.executable, "-B", wrapper]
        argv += list(args) if bare else ["--project", self.proj if project is None else project] + list(args)
        child = self.base_env()
        child.update(env or {})
        proc = subprocess.run(argv, cwd=cwd or self.proj, env=child, input=stdin,
                              stdin=subprocess.DEVNULL if stdin is None else None,
                              capture_output=True, text=True, timeout=120)
        self.assertEqual(proc.returncode, 0, "the wrapper must always exit 0\n" + proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, "", "the wrapper prints on stdout only")
        return Result(proc)

    def init_store(self):
        res = self.run_wrapper("init")
        self.assertTrue(os.path.isdir(self.store), res.out)
        return res

    def write(self, rel, text, base=None):
        path = os.path.join(base or self.proj, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def add_run(self, n=1, new=None):
        data = {"version": 1, "date": TODAY, "time": TODAY + "T12:00:00", "agent_type": "scout",
                "agent_id": "agent%d" % n, "used": [], "verified": [], "contradicts": []}
        if new:
            data["new"] = new
        return self.write("inbox/run%04d.json" % n, json.dumps(data), self.store)

    def add_fact(self, rid="T-0001", evidence="src/a.py"):
        self.write("src/a.py", "print(1)\n")
        fp = LIB.fingerprint(self.proj, LIB.split_evidence(evidence))[0]
        rec = {"id": rid, "title": "a fact", "fact": "Fact text.", "check": "true", "evidence": evidence, "fp": fp,
               "as_of": "nogit " + TODAY, "author": "deep-reasoner", "created": TODAY, "last_used": TODAY,
               "uses": "1"}
        LIB.write_topic(os.path.join(self.store, "topics", "testing.md"), "testing", [rec])

    def add_pending(self, eid="F-0001", date="2026-10-10", title="Pending feature"):
        entry = {"id": eid, "title": title,
                 "fields": {"status": "in-progress", "kind": "code", "dates": "%s .. %s" % (date, date),
                            "refs": [("commit", "pending (branch b1)")], "summary": "One line."}}
        self.write("history/%s-%s.md" % (date, LIB.history_slug(title)), LIB.serialize_entry(entry), self.store)
        LIB.write_history_index(self.store)

    def install_lib(self, same=True):
        hooks = os.path.join(self.cfg, "hooks")
        os.makedirs(hooks, exist_ok=True)
        target = os.path.join(hooks, "hivemind_lib.py")
        if same:
            shutil.copy2(PAYLOAD_LIB, target)
        else:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write("# an older installed copy\n")
        return target


class ProjectTest(WrapperCase):
    def setUp(self):
        super().setUp()
        self.install_lib(same=True)   # no note, so the summary is the first line

    def test_off_project_message_for_every_action_but_init(self):
        for args in (("status",), ("consolidate",), ("check",), ("inbox",), ("related", "src/a.py"), ("link",),
                     ("link", "F-0001", "abcdef1")):
            res = self.run_wrapper(*args)
            self.assertEqual(res.lines, [off_message(self.proj)], args)
        self.assertFalse(os.path.exists(os.path.join(self.proj, ".claude")))

    def test_no_project_message_outside_git(self):
        res = self.run_wrapper("status", project="", cwd=self.plain)
        self.assertEqual(res.lines, [NO_PROJECT])
        res = self.run_wrapper("init", project="", cwd=self.plain)
        self.assertEqual(res.lines, [NO_PROJECT])
        self.assertEqual(os.listdir(self.plain), [])

    def test_unexpanded_literal_project_falls_back_to_the_working_folder(self):
        self.init_store()
        sub = os.path.join(self.proj, "sub")
        os.makedirs(sub)
        res = self.run_wrapper("status", project="${CLAUDE_PROJECT_DIR}", cwd=sub)
        self.assertEqual(res.lines[0], "HiveMind summary for " + self.store)

    def test_empty_project_uses_the_inherited_variable(self):
        other = os.path.join(self.base, "other")
        os.makedirs(other)
        self.git("init", "-q", "-b", "main", cwd=other)
        self.run_wrapper("init", project=other, cwd=self.plain)
        res = self.run_wrapper("status", project="", cwd=self.plain, env={"CLAUDE_PROJECT_DIR": other})
        self.assertEqual(res.lines[0], "HiveMind summary for " + LIB.store_path(other))

    def test_project_argument_wins_over_the_inherited_variable(self):
        other = os.path.join(self.base, "other")
        os.makedirs(other)
        self.git("init", "-q", "-b", "main", cwd=other)
        self.run_wrapper("init", project=other, cwd=self.plain)
        self.init_store()
        res = self.run_wrapper("status", cwd=self.plain, env={"CLAUDE_PROJECT_DIR": other})
        self.assertEqual(res.lines[0], "HiveMind summary for " + self.store)

    def test_linked_worktree_without_project_uses_the_main_checkout_store(self):
        self.init_store()
        wt = os.path.join(self.base, "wt")
        self.git("worktree", "add", "-q", wt, "-b", "wtbranch")
        res = self.run_wrapper("status", project="", cwd=wt)
        self.assertEqual(res.lines[0], "HiveMind summary for " + self.store)
        self.assertFalse(os.path.exists(os.path.join(wt, ".claude", "hivemind")))


class StatusTest(WrapperCase):
    def test_status_and_consolidate_print_the_same_text_ending_in_the_verdict(self):
        self.init_store()
        self.install_lib(same=True)
        status = self.run_wrapper("status")
        self.assertEqual(status.lines[0], "HiveMind summary for " + self.store)
        self.assertEqual(status.lines[-1], "consolidate: nothing to do")
        self.assertEqual(self.run_wrapper("consolidate").out, status.out)
        self.add_run()
        status = self.run_wrapper("status")
        self.assertEqual(status.lines[-1], "consolidate: work waiting (1 inbox files)")
        self.assertEqual(self.run_wrapper("consolidate").out, status.out)

    def test_the_note_comes_before_the_summary_and_the_verdict_stays_last(self):
        self.init_store()
        status = self.run_wrapper("status")
        self.assertEqual(status.lines[0], hooks_missing(self.cfg))
        self.assertTrue(status.lines[1].startswith("HiveMind summary for "))
        self.assertTrue(status.lines[-1].startswith("consolidate:"))
        self.assertEqual(self.run_wrapper("consolidate").out, status.out)

    def test_note_cases(self):
        self.init_store()
        self.assertEqual(self.run_wrapper("status").lines[0], hooks_missing(self.cfg))
        self.install_lib(same=False)
        self.assertEqual(self.run_wrapper("status").lines[0], HOOKS_DIFFER)
        self.install_lib(same=True)
        self.assertEqual(self.run_wrapper("status").lines[0], "HiveMind summary for " + self.store)
        # No CLAUDE_CONFIG_DIR means ~/.claude under the throwaway HOME.
        env = {"CLAUDE_CONFIG_DIR": ""}
        default_cfg = os.path.join(self.home, ".claude")
        self.assertEqual(self.run_wrapper("status", env=env).lines[0], hooks_missing(default_cfg))

    def test_a_tally_topic_over_its_limit_is_not_work(self):
        self.init_store()
        self.install_lib(same=True)
        big = "x" * (LIB.DEFAULT_CONFIG["tally_topic_max_bytes"] + 100)
        self.write("topics/%s.md" % LIB.TALLY_TOPIC, big, self.store)
        lines = self.run_wrapper("status").lines
        self.assertIn("topics/%s.md" % LIB.TALLY_TOPIC, [ln for ln in lines if ln.startswith("Over limit:")][0])
        self.assertEqual(lines[-1], "consolidate: nothing to do")


class CheckInboxTest(WrapperCase):
    def test_check_passes_on_a_fresh_store(self):
        self.init_store()
        self.assertEqual(self.run_wrapper("check").lines[-1], "check passed")

    def test_check_reports_a_broken_topic(self):
        self.init_store()
        self.write("topics/testing.md", "# testing\n\n### T-0001 half a record\nnot a field line\n", self.store)
        res = self.run_wrapper("check")
        self.assertNotEqual(res.lines[-1], "check passed", res.out)
        # check's exit 1 means "problems listed", so the wrapper adds no error line after them.
        self.assertFalse(any(ln.startswith("error:") for ln in res.lines), res.out)
        self.assertTrue(any("testing" in ln for ln in res.lines), res.out)

    def test_inbox_previews_and_leaves_the_store_alone(self):
        self.init_store()
        self.add_run(new=[{"topic": "testing", "fact": "A proposed fact", "check": "true", "evidence": ["src/a.py"]}])
        self.add_fact()
        before = tree_hash(self.store)
        res = self.run_wrapper("inbox")
        self.assertIn("HiveMind prep report for " + self.store, res.out)
        self.assertIn("A proposed fact", res.out)
        self.assertEqual(res.lines[-1], LIB.PREVIEW_LINE)
        self.assertEqual(tree_hash(self.store), before)
        for name in (LIB.PREP_SNAPSHOT, LIB.LOCK_NAME):
            self.assertFalse(os.path.lexists(os.path.join(self.store, "inbox", name)), name)

    def test_inbox_on_a_store_with_no_inbox_folder_creates_none(self):
        self.init_store()
        shutil.rmtree(os.path.join(self.store, "inbox"))
        before = tree_hash(self.store)
        self.run_wrapper("inbox")
        self.run_wrapper("status")
        self.run_wrapper("check")
        self.assertEqual(tree_hash(self.store), before)


class RelatedTest(WrapperCase):
    def test_related_lists_the_fact_that_cites_the_path(self):
        self.init_store()
        self.add_fact()
        before = tree_hash(self.store)
        res = self.run_wrapper("related", "src/a.py")
        self.assertEqual(res.lines[0], "facts:")
        self.assertIn("T-0001 [testing] a fact (evidence: src/a.py)", res.lines[1])
        self.assertEqual(self.run_wrapper("related", "src/none.py").lines, ["related: nothing cites these paths"])
        self.assertEqual(tree_hash(self.store), before)

    def test_related_takes_a_quoted_path_with_a_space(self):
        self.init_store()
        res = self.run_wrapper("related", "docs/my notes.md")
        self.assertEqual(res.lines, ["related: nothing cites these paths"])

    def test_related_refuses_option_looking_paths_and_too_many(self):
        self.init_store()
        for args in (("related", "--store", self.store), ("related", "-x"), ("related", "src/a.py", "--store=x"),
                     ("related",), ("related",) + tuple("p%d.py" % i for i in range(21))):
            self.assertEqual(self.run_wrapper(*args).lines, [usage("related")], args)
        twenty = ("related",) + tuple("p%d.py" % i for i in range(20))
        self.assertEqual(self.run_wrapper(*twenty).lines, ["related: nothing cites these paths"])


class LinkTest(WrapperCase):
    def setUp(self):
        super().setUp()
        self.init_store()
        self.install_lib(same=True)

    def entry_text(self):
        folder = os.path.join(self.store, "history")
        name = [n for n in os.listdir(folder) if n != "INDEX.md"][0]
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            return fh.read()

    def test_link_with_no_arguments_lists_pending_ids_or_says_none(self):
        self.assertEqual(self.run_wrapper("link").lines, [LINK_NONE])
        self.add_pending("F-0001", "2026-10-10", "One")
        self.add_pending("F-0002", "2026-10-11", "Two")
        res = self.run_wrapper("link")
        self.assertEqual(res.lines[0], LINK_HEADING)
        self.assertEqual(len(res.lines), 3)
        self.assertEqual(res.lines[1], "- 2026-10-11 F-0002 in-progress code: Two (commit pending)")
        self.assertEqual(res.lines[2], "- 2026-10-10 F-0001 in-progress code: One (commit pending)")

    def test_link_refuses_a_bad_id_a_bad_rev_and_an_unknown_commit_and_writes_nothing(self):
        self.add_pending()
        sha = self.git("rev-parse", "HEAD")
        before = tree_hash(self.store)
        res = self.run_wrapper("link", "F-12", sha[:8])
        self.assertEqual(res.lines, ["error: F-12 isn't a history entry id. Ids look like F-1a2b."])
        for rev in ("main", "ABCDEF1", "abc12", sha[:8] + "..", sha + "0" * 5):
            res = self.run_wrapper("link", "F-0001", rev)
            self.assertEqual(res.lines, ["error: %s isn't a commit. Give a SHA of 7 to 40 hex characters, "
                                         "or base..head." % rev], rev)
        res = self.run_wrapper("link", "F-0001", "deadbee")
        self.assertEqual(res.lines, ["error: commit deadbee isn't in %s. Nothing changed." % self.proj])
        res = self.run_wrapper("link", "F-0001", sha[:8] + "..deadbee")
        self.assertEqual(res.lines, ["error: commit %s..deadbee isn't in %s. Nothing changed."
                                     % (sha[:8], self.proj)])
        self.assertEqual(tree_hash(self.store), before)

    def test_link_for_an_id_the_store_does_not_hold_reports_the_library_refusal(self):
        sha = self.git("rev-parse", "HEAD")
        before = tree_hash(self.store)
        res = self.run_wrapper("link", "F-00ff", sha[:8])
        self.assertIn("history link: F-00ff not found", res.lines)
        self.assertEqual(res.lines[-1], "error: the HiveMind library stopped with exit 1.")
        self.assertEqual(tree_hash(self.store), before)

    def test_link_without_a_development_branch_gives_no_warning(self):
        self.add_pending()
        sha = self.commit("b.txt")
        res = self.run_wrapper("link", "F-0001", sha[:8])
        self.assertEqual(res.lines, ["linked F-0001 to " + sha[:7]])
        self.assertIn(sha, self.entry_text())
        self.assertEqual(self.run_wrapper("link").lines, [LINK_NONE])

    def test_link_warns_when_a_local_development_branch_lacks_the_commit_and_still_links(self):
        self.add_pending()
        self.git("branch", "development")
        sha = self.commit("b.txt")
        res = self.run_wrapper("link", "F-0001", sha[:8])
        self.assertEqual(res.lines, ["warning: commit %s isn't on development. Linking it anyway." % sha[:7],
                                     "linked F-0001 to " + sha[:7]])
        self.assertIn(sha, self.entry_text())

    def test_link_gives_no_warning_when_development_holds_the_commit(self):
        self.add_pending()
        sha = self.commit("b.txt")
        self.git("branch", "development")
        res = self.run_wrapper("link", "F-0001", sha[:8])
        self.assertEqual(res.lines, ["linked F-0001 to " + sha[:7]])

    def test_link_checks_the_origin_development_branch_too(self):
        self.add_pending("F-0001", "2026-10-10", "One")
        self.add_pending("F-0002", "2026-10-11", "Two")
        self.git("branch", "development")
        sha = self.commit("b.txt")
        self.git("update-ref", "refs/remotes/origin/development", sha)
        res = self.run_wrapper("link", "F-0001", sha[:8])
        self.assertEqual(res.lines, ["linked F-0001 to " + sha[:7]], "origin/development holds it")
        newer = self.commit("c.txt")
        res = self.run_wrapper("link", "F-0002", newer[:8])
        self.assertEqual(res.lines[0], "warning: commit %s isn't on development. Linking it anyway." % newer[:7])

    def test_link_takes_base_dot_dot_head(self):
        self.add_pending()
        base = self.git("rev-parse", "HEAD")
        head = self.commit("b.txt")
        res = self.run_wrapper("link", "F-0001", "%s..%s" % (base[:8], head[:8]))
        self.assertEqual(res.lines, ["linked F-0001 to " + head[:7]])
        self.assertIn("%s..%s" % (base, head), self.entry_text())


class InitTest(WrapperCase):
    def test_init_creates_the_store_and_a_second_init_changes_nothing(self):
        first = self.run_wrapper("init")
        self.assertTrue(os.path.isfile(os.path.join(self.store, "config.json")), first.out)
        self.assertTrue(os.path.isfile(os.path.join(self.proj, ".claude", "rules", "project-facts.md")))
        self.assertTrue(first.lines)
        before = tree_hash(self.store)
        second = self.run_wrapper("init")
        self.assertEqual(second.lines, ["HiveMind is already on in %s. Nothing changed." % self.store])
        self.assertEqual(tree_hash(self.store), before)

    def test_init_works_from_a_folder_inside_the_project(self):
        sub = os.path.join(self.proj, "deep", "er")
        os.makedirs(sub)
        self.run_wrapper("init", project="", cwd=sub)
        self.assertTrue(os.path.isdir(self.store))
        self.assertFalse(os.path.exists(os.path.join(sub, ".claude")))


class PayloadTest(WrapperCase):
    def test_a_missing_payload_copy_gives_the_error_line(self):
        plugin = os.path.join(self.base, "plug")
        shutil.copytree(os.path.join(PLUGIN, "bin"), os.path.join(plugin, "bin"))
        wrapper = os.path.join(plugin, "bin", "hivemind")
        res = self.run_wrapper("status", wrapper=wrapper)
        missing = os.path.join(plugin, "payload", "hooks", "hivemind_lib.py")
        self.assertEqual(res.lines, ["error: the plugin's copy of the HiveMind library is missing at %s. "
                                     "Reinstall the plugin." % missing])

    def test_the_wrapper_leaves_no_bytecode_behind(self):
        self.init_store()
        self.run_wrapper("status")
        for dirpath, dirs, files in os.walk(PLUGIN):
            self.assertNotIn("__pycache__", dirs, dirpath)
            self.assertEqual([f for f in files if f.endswith(".pyc")], [], dirpath)

    def test_child_git_settings_are_hardened(self):
        # The wrapper appends core.fsmonitor=false after any GIT_CONFIG_COUNT entries and sets two switches.
        # A project git hook cannot show them, so load the wrapper's function and read the environment it builds.
        loader = importlib.machinery.SourceFileLoader("hivemind_wrapper_under_test", WRAPPER)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        saved = dict(os.environ)
        try:
            for key in list(os.environ):
                if key.startswith("GIT_"):
                    del os.environ[key]
            os.environ["GIT_CONFIG_COUNT"] = "2"
            os.environ["GIT_CONFIG_KEY_0"] = "a.b"
            os.environ["GIT_CONFIG_VALUE_0"] = "1"
            os.environ["GIT_CONFIG_KEY_1"] = "c.d"
            os.environ["GIT_CONFIG_VALUE_1"] = "2"
            mod.harden_git_env()
            self.assertEqual(os.environ["GIT_CONFIG_COUNT"], "3")
            self.assertEqual((os.environ["GIT_CONFIG_KEY_2"], os.environ["GIT_CONFIG_VALUE_2"]),
                             ("core.fsmonitor", "false"))
            self.assertEqual((os.environ["GIT_CONFIG_KEY_0"], os.environ["GIT_CONFIG_VALUE_1"]), ("a.b", "2"))
            self.assertEqual((os.environ["GIT_OPTIONAL_LOCKS"], os.environ["GIT_NO_LAZY_FETCH"]), ("0", "1"))
            for key in list(os.environ):
                if key.startswith("GIT_"):
                    del os.environ[key]
            mod.harden_git_env()
            self.assertEqual((os.environ["GIT_CONFIG_COUNT"], os.environ["GIT_CONFIG_KEY_0"]),
                             ("1", "core.fsmonitor"))
        finally:
            os.environ.clear()
            os.environ.update(saved)


class UsageTest(WrapperCase):
    def test_wrong_arguments_get_that_actions_usage(self):
        self.init_store()
        cases = [("status", "x"), ("consolidate", "x"), ("check", "x"), ("inbox", "x"), ("init", "x"),
                 ("link", "F-0001"), ("link", "F-0001", "abcdef1", "extra"), ("related",)]
        for args in cases:
            self.assertEqual(self.run_wrapper(*args).lines, [usage(args[0])], args)

    def test_an_unknown_or_missing_action_lists_all_seven(self):
        self.init_store()
        for args in (("frobnicate",), ("--help",), ("",)):
            self.assertEqual(self.run_wrapper(*args).lines, [usage()], args)
        for args in ((), ("status",), ("--project",), ("--project", self.proj)):
            self.assertEqual(self.run_wrapper(*args, bare=True).lines, [usage()], args)

    def test_usage_needs_no_project_and_no_store(self):
        self.assertEqual(self.run_wrapper("status", "x", project="", cwd=self.plain).lines, [usage("status")])


# (command with NAME for the wrapper's file name, denied?). The same list sits in test_plugin_launcher.py.
GUARD_CASES = [
    ('python3 "/work/cache/NAME/0.1.7/bin/NAME" --data "/work/d" --session abc status', True),
    ('python3 "${CLAUDE_PLUGIN_ROOT}/bin/NAME" status', True),
    ("cd /work && python3 /work/bin/NAME status", True),
    ("FOO=1 python3 /work/bin/NAME stop", True),
    ("env python3 /work/bin/NAME stop", True),
    ("env FOO=1 nohup python3 /work/bin/NAME stop", True),
    ("exec python3 /work/bin/NAME stop", True),
    ("/usr/bin/python3 /work/bin/NAME status", True),
    ('"/usr/bin/python3" /work/bin/NAME status', True),
    ("python3.12 /work/bin/NAME status", True),
    ("echo $(python3 /work/bin/NAME edits)", True),
    ("echo `python3 /work/bin/NAME edits`", True),
    ("true; python3 /work/bin/NAME log", True),
    ("true || python3 /work/bin/NAME log", True),
    ("echo hi | python3 /work/bin/NAME log", True),
    ("python3 /work/bin/NAME log &", True),
    ("echo hi\npython3 /work/bin/NAME log", True),
    ("(python3 /work/bin/NAME status)", True),
    ("{ python3 /work/bin/NAME status; }", True),
    ('python3 "$(dirname "$0")/bin/NAME" status', True),
    ("grep -n python3 plugins/NAME/bin/NAME | head -$N", False),
    ("cat /work/repo/plugins/NAME/bin/NAME", False),
    ("sed -n 1,80p plugins/NAME/bin/NAME", False),
    ("git log -- plugins/NAME/bin/NAME", False),
    ("echo python3; ls bin/NAME", False),
    ("echo hi", False),
    ("git status", False),
    ("python3 tools/build_plugins.py", False),
    ("python3 -m unittest discover -s tests", False),
]


class DeadOut:
    """A stdout whose every write and flush fails."""

    def write(self, _text):
        raise OSError("closed")

    def flush(self):
        raise OSError("closed")


class GuardTest(WrapperCase):
    """The hidden guard call, run as the PreToolUse hook runs it: JSON on stdin, one line out, exit 0.

    It checks each command segment against the hook's `if` rule, which Claude Code skips for a command it
    cannot parse."""

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("hivemind_wrapper_for_guard_test", WRAPPER)
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.module = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.module)
        cls.deny = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": cls.module.GUARD_REASON}}

    def guard(self, stdin):
        return self.run_wrapper("guard", bare=True, stdin=stdin)

    @staticmethod
    def bash(command):
        return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})

    def assert_denied(self, stdin):
        res = self.guard(stdin)
        self.assertEqual(res.out.count("\n"), 1, res.out)
        self.assertEqual(json.loads(res.out), self.deny, stdin)

    def assert_silent(self, stdin):
        self.assertEqual(self.guard(stdin).out, "", stdin)

    def test_every_rendered_skill_line_is_denied(self):
        wrapper = '"/work/cache/hivemind/0.1.3/bin/hivemind"'
        for tail in ("status", "check", "inbox", "init", "consolidate", "link", "link F-0001 abcdef1",
                     "related src/a.py", 'related "docs/my notes.md"'):
            command = 'python3 %s --project "/work/proj" %s' % (wrapper, tail)
            with self.subTest(command=command):
                self.assert_denied(self.bash(command))

    def test_a_model_call_to_the_wrapper_is_denied_however_it_is_spelled(self):
        for template, denied in GUARD_CASES:
            if not denied:
                continue
            command = template.replace("NAME", "hivemind")
            with self.subTest(command=command):
                self.assert_denied(self.bash(command))

    def test_other_bash_commands_pass_in_silence(self):
        for template, denied in GUARD_CASES:
            if denied:
                continue
            command = template.replace("NAME", "hivemind")
            with self.subTest(command=command):
                self.assert_silent(self.bash(command))

    def test_the_library_calls_of_deep_reasoner_pass_in_silence(self):
        for command in ('python3 "/work/cfg/hooks/hivemind_lib.py" prep /work/proj/.claude/hivemind',
                        "python3 /work/cfg/hooks/hivemind_lib.py apply /work/proj/.claude/hivemind",
                        "cd /work/proj && python3 hooks/hivemind_lib.py summary .claude/hivemind"):
            with self.subTest(command=command):
                self.assert_silent(self.bash(command))

    def test_a_python3_call_that_never_names_the_wrapper_passes(self):
        for command in ("python3 /work/bin/other-tool status", "FOO=1 python3 -c 'print(1)'",
                        "python2 /work/bin/hivemind status", "ls -l /work/bin/hivemind"):
            with self.subTest(command=command):
                self.assert_silent(self.bash(command))

    def test_the_library_path_never_holds_the_wrapper_substring(self):
        self.assertNotIn("bin/hivemind", "/work/cfg/hooks/hivemind_lib.py")
        self.assertNotIn("bin/hivemind", os.path.join("hooks", "hivemind_lib.py"))
        self.assertNotIn("bin/hivemind", self.module.LIB_REL)

    def test_unreadable_input_is_denied(self):
        for stdin in ("not json", "", "[]", "null", '"Bash"', "5",
                      json.dumps({"tool_name": "Bash", "tool_input": {"command": 5}}),
                      json.dumps({"tool_name": "Bash", "tool_input": {}}),
                      json.dumps({"tool_name": "Bash", "tool_input": "echo hi"}),
                      json.dumps({"tool_name": "Bash"})):
            with self.subTest(stdin=stdin):
                self.assert_denied(stdin)

    def test_a_tool_other_than_bash_passes_in_silence(self):
        self.assert_silent(json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/work/a.py"}}))
        self.assert_silent(json.dumps({"tool_name": "Read", "tool_input": {
            "command": "python3 /work/bin/hivemind"}}))
        self.assert_silent(json.dumps({"tool_name": "Read"}))

    def test_an_input_over_the_cap_is_denied(self):
        padding = "x" * (self.module.GUARD_STDIN_LIMIT + 10)
        self.assert_denied(json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo " + padding}}))

    def test_a_broken_stream_is_denied(self):
        class Broken:
            def read(self, _limit):
                raise OSError("closed")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.module.guard(Broken())
        self.assertEqual(json.loads(out.getvalue()), self.deny)

    def test_a_guard_whose_deny_line_cannot_be_written_exits_1(self):
        stdin = io.StringIO(self.bash("python3 /work/bin/hivemind status"))
        with contextlib.redirect_stdout(DeadOut()):
            self.assertEqual(self.module.guard(stdin), 1)
        real_stdin = sys.stdin
        sys.stdin = io.StringIO(self.bash("python3 /work/bin/hivemind status"))
        try:
            with contextlib.redirect_stdout(DeadOut()):
                self.assertEqual(self.module.main(["guard"]), 1)
        finally:
            sys.stdin = real_stdin

    def test_the_wrapper_still_exits_0_for_every_other_action(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.module.main(["--project", self.proj, "status", "x"]), 0)
            self.assertEqual(self.module.main(["frobnicate"]), 0)
        self.assertEqual(out.getvalue().splitlines(), [usage("status"), usage()])
        with contextlib.redirect_stdout(DeadOut()):
            self.assertEqual(self.module.guard(io.StringIO(self.bash("echo hi"))), 0)

    def test_guard_is_not_a_skill_action(self):
        self.assertEqual(self.run_wrapper("guard").lines, [usage()])
        self.assertEqual(self.run_wrapper("guard", bare=True, stdin="").lines, [json.dumps(self.deny)])
        self.assertEqual(self.run_wrapper("guard", "x", bare=True).lines, [usage()])
        self.assertNotIn("guard", self.module.USAGE)
        self.assertNotIn("guard", self.module.ORDER)
        self.assertEqual(self.module.GUARD_RULE, "Bash(python3 *bin/hivemind*)")


if __name__ == "__main__":
    unittest.main()
