"""Tests for dashboard/git_check.py: the lstat walk that finds where a project sits in a repo (T23)
and the git check-ignore call that says whether git ignores .claude/settings.local.json (T22).

Every case builds real folders under the temp root. RepoRoot (T104a) covers git_check.repo_root with
hand-made chains, and RepoRootRealGit checks the same places against real git. RepoPlace patches only os.lstat. IgnoreState runs
real git on throwaway repos with a throwaway HOME and GIT_CONFIG_NOSYSTEM=1, and patches
subprocess.run only to prove what the module passes it.
"""
import inspect
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import helpers

DASHBOARD = os.path.join(helpers.REPO, "dashboard")
sys.path.insert(0, DASHBOARD)
import git_check  # noqa: E402

SOURCE = Path(git_check.__file__.replace(".pyc", ".py"))


class RepoPlace(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-git-check-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)

    def folder(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def touch(self, path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("gitdir: elsewhere\n")

    def test_git_folder_at_the_project_is_root(self):
        proj = self.folder("p")
        os.mkdir(os.path.join(proj, ".git"))
        self.assertEqual(git_check.repo_place(proj), "root")

    def test_git_file_at_the_project_is_linked(self):
        proj = self.folder("p")
        self.touch(os.path.join(proj, ".git"))
        self.assertEqual(git_check.repo_place(proj), "linked")

    def test_git_symlink_at_the_project_is_linked(self):
        proj = self.folder("p")
        os.mkdir(os.path.join(self.root, "real-git"))
        os.symlink(os.path.join(self.root, "real-git"), os.path.join(proj, ".git"))
        self.assertEqual(git_check.repo_place(proj), "linked")

    def test_git_folder_at_a_parent_is_subfolder(self):
        parent = self.folder("repo")
        os.mkdir(os.path.join(parent, ".git"))
        self.assertEqual(git_check.repo_place(self.folder("repo", "app")), "subfolder")

    def test_git_folder_at_a_grandparent_is_subfolder(self):
        os.mkdir(os.path.join(self.folder("repo"), ".git"))
        self.assertEqual(git_check.repo_place(self.folder("repo", "a", "b")), "subfolder")

    def test_a_git_file_at_a_parent_is_subfolder(self):
        self.touch(os.path.join(self.folder("repo"), ".git"))
        self.assertEqual(git_check.repo_place(self.folder("repo", "app")), "subfolder")

    def test_no_git_anywhere_is_no_repo(self):
        # The temp base itself could sit inside a repo, so check the walk only up to this root.
        probe = git_check.repo_place(self.folder("plain"))
        if probe == "subfolder" and any(os.path.lexists(os.path.join(d, ".git")) for d in self.above()):
            self.skipTest("the temp folder sits inside a repo")
        self.assertEqual(probe, "no_repo")

    def above(self):
        here = self.root
        while True:
            parent = os.path.dirname(here)
            if parent == here:
                return
            here = parent
            yield here

    def test_a_symlinked_project_resolves_into_its_repo(self):
        os.mkdir(os.path.join(self.folder("repo"), ".git"))
        real = self.folder("repo", "app")
        link = os.path.join(self.root, "link")
        os.symlink(real, link)
        self.assertEqual(git_check.repo_place(link), "subfolder")

    def test_a_missing_path_walks_up(self):
        os.mkdir(os.path.join(self.folder("repo"), ".git"))
        self.assertEqual(git_check.repo_place(os.path.join(self.root, "repo", "gone", "deeper")), "subfolder")

    def test_a_path_under_a_file_keeps_walking(self):
        os.mkdir(os.path.join(self.folder("repo"), ".git"))
        self.touch(os.path.join(self.root, "repo", "afile"))
        self.assertEqual(git_check.repo_place(os.path.join(self.root, "repo", "afile", "x")), "subfolder")

    def test_a_git_entry_that_cannot_be_read_is_never_no_repo(self):
        os.mkdir(os.path.join(self.folder("repo"), ".git"))
        proj = self.folder("repo", "sub")
        real = os.lstat
        denied = os.path.join(proj, ".git")

        def lstat(path, *args, **kwargs):
            if path == denied:
                raise PermissionError(13, "Permission denied", path)
            return real(path, *args, **kwargs)

        with mock.patch.object(git_check.os, "lstat", side_effect=lstat):
            self.assertEqual(git_check.repo_place(proj), "linked")
        self.assertEqual(git_check._git_kind(self.folder("empty")), None)

    def test_none_and_empty_are_no_repo(self):
        self.assertEqual(git_check.repo_place(None), "no_repo")
        self.assertEqual(git_check.repo_place(""), "no_repo")

    def test_the_walk_reads_nothing_and_starts_nothing(self):
        text = inspect.getsource(git_check._git_kind) + inspect.getsource(git_check.repo_place)
        for banned in (r"\bopen\(", r"\bsubprocess\b", r"os\.read\b"):
            self.assertIsNone(re.search(banned, text), banned)

    def test_the_git_call_holds_its_safety_settings(self):
        text = inspect.getsource(git_check.ignore_state)
        for needed in ("--no-lazy-fetch", "core.fsmonitor=false", "GIT_NO_LAZY_FETCH", "timeout=2"):
            self.assertIn(needed, text)
        for banned in (r"shell\s*=\s*True", r"os\.environ"):
            self.assertIsNone(re.search(banned, text), banned)


REAL_GIT = shutil.which("git")
IGNORE_FILE = ".claude/settings.local.json"
MINIMAL_PATH = "/usr/bin:/bin"


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class IgnoreState(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-git-ignore-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)
        self.home = self.folder("home")
        self.bin = self.folder("bin")
        # A wrapper named git sets GIT_CONFIG_NOSYSTEM, because ignore_state builds its own env
        # and can't be handed that variable. The wrapper keeps the system config out of every run.
        wrapper = os.path.join(self.bin, "git")
        self.script(wrapper, 'GIT_CONFIG_NOSYSTEM=1\nexport GIT_CONFIG_NOSYSTEM\nexec "%s" "$@"\n' % REAL_GIT)
        self.git_bin = wrapper

    def folder(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def script(self, path, body):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("#!/bin/sh\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR)
        return path

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def env(self, **extra):
        env = {"PATH": MINIMAL_PATH, "HOME": self.home, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}
        env.update(extra)
        return env

    def git(self, cwd, *args):
        done = subprocess.run([self.git_bin, "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
                              cwd=cwd, env=self.env(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(done.returncode, 0, done.stdout.decode("utf-8", "replace"))
        return done.stdout.decode("utf-8", "replace")

    def repo(self, *parts):
        path = self.folder(*parts)
        self.git(path, "init", "-q", "-b", "main")
        return path

    def commit_file(self, repo, name="README", text="x\n"):
        self.write(os.path.join(repo, name), text)
        self.git(repo, "add", name)
        self.git(repo, "commit", "-q", "-m", "seed")

    def state(self, project, **kw):
        return git_check.ignore_state(project, kw.pop("path_env", self.bin), kw.pop("home", self.home), **kw)

    def fake_repo(self):
        path = self.folder("fake")
        os.makedirs(os.path.join(path, ".git"), exist_ok=True)
        return path

    def raw_check_ignore(self, project, *flags):
        subprocess.run([self.git_bin, *flags, "-C", project, "check-ignore", "-q", "--", IGNORE_FILE],
                       env=self.env(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=10, check=False)

    # exit table with real git

    def test_not_a_repo_is_no_repo_and_git_never_runs(self):
        plain = self.folder("plain")
        if git_check.repo_place(plain) != "no_repo":
            self.skipTest("the temp folder sits inside a repo")
        with mock.patch.object(git_check.subprocess, "run") as run:
            self.assertEqual(self.state(plain), "no_repo")
        run.assert_not_called()

    def test_a_repo_with_nothing_ignoring_the_file_is_not_ignored(self):
        self.assertEqual(self.state(self.repo("r")), "not_ignored")

    def test_a_gitignore_line_is_ignored(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".gitignore"), IGNORE_FILE + "\n")
        self.assertEqual(self.state(repo), "ignored")

    def test_a_pattern_is_ignored(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".gitignore"), "*.local.json\n")
        self.assertEqual(self.state(repo), "ignored")

    def test_info_exclude_is_ignored(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".git", "info", "exclude"), "*.local.json\n")
        self.assertEqual(self.state(repo), "ignored")

    def test_global_excludes_file_in_the_home_gitconfig_is_ignored(self):
        repo = self.repo("r")
        excludes = os.path.join(self.root, "global-excludes")
        self.write(excludes, "settings.local.json\n")
        self.write(os.path.join(self.home, ".gitconfig"), "[core]\n\texcludesFile = %s\n" % excludes)
        self.assertEqual(self.state(repo), "ignored")

    def test_xdg_global_ignore_counts_only_when_xdg_config_home_is_passed(self):
        repo = self.repo("r")
        xdg = self.folder("xdg")
        self.write(os.path.join(xdg, "git", "ignore"), "settings.local.json\n")
        self.assertEqual(self.state(repo), "not_ignored")
        self.assertEqual(self.state(repo, xdg_config_home=xdg), "ignored")

    def test_a_project_in_a_subfolder_is_ignored_by_the_root_gitignore(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".gitignore"), "settings.local.json\n")
        self.assertEqual(self.state(self.folder("r", "app")), "ignored")

    def test_a_tracked_file_is_not_ignored_even_with_a_matching_pattern(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".gitignore"), "*.local.json\n")
        self.write(os.path.join(repo, IGNORE_FILE), "{}\n")
        self.git(repo, "add", "-f", IGNORE_FILE)
        self.assertEqual(self.state(repo), "not_ignored")

    def test_a_tracked_and_deleted_file_is_not_ignored(self):
        repo = self.repo("r")
        self.write(os.path.join(repo, ".gitignore"), "*.local.json\n")
        self.write(os.path.join(repo, IGNORE_FILE), "{}\n")
        self.git(repo, "add", "-f", IGNORE_FILE)
        self.git(repo, "commit", "-q", "-m", "track it")
        os.remove(os.path.join(repo, IGNORE_FILE))
        self.assertEqual(self.state(repo), "not_ignored")

    # git is not found

    def test_no_path_means_unknown_and_git_never_runs(self):
        fake = self.fake_repo()
        empty = self.folder("empty-bin")
        for path_env in (None, "", empty):
            with self.subTest(path_env=path_env), mock.patch.object(git_check.subprocess, "run") as run:
                self.assertEqual(self.state(fake, path_env=path_env), "unknown")
            run.assert_not_called()

    def test_a_relative_git_path_is_unknown(self):
        fake = self.fake_repo()
        with mock.patch.object(git_check.shutil, "which", return_value="git"), \
                mock.patch.object(git_check.subprocess, "run") as run:
            self.assertEqual(self.state(fake), "unknown")
        run.assert_not_called()

    # what reaches subprocess.run

    def run_mocked(self, project=None, returncode=1, **kw):
        project = project or self.fake_repo()
        with mock.patch.object(git_check.subprocess, "run", return_value=SimpleNamespace(returncode=returncode)) as run:
            result = self.state(project, **kw)
        run.assert_called_once()
        return result, run.call_args

    def test_a_missing_home_runs_and_no_none_reaches_the_env(self):
        for xdg in (None, self.folder("xdg")):
            with self.subTest(xdg=xdg):
                result, call = self.run_mocked(home=None, xdg_config_home=xdg)
                self.assertEqual(result, "not_ignored")
                env = call.kwargs["env"]
                self.assertNotIn(None, env.values())
                self.assertNotIn("HOME", env)

    def test_the_env_is_built_from_nothing(self):
        xdg = self.folder("xdg")
        with mock.patch.dict(os.environ, {"MR_SENTINEL": "leak", "GIT_DIR": "/nowhere", "GIT_SSH_COMMAND": "x"}):
            _, call = self.run_mocked(xdg_config_home=xdg)
            env = call.kwargs["env"]
            self.assertEqual(env, {"PATH": self.bin, "HOME": self.home, "GIT_NO_LAZY_FETCH": "1",
                                   "XDG_CONFIG_HOME": xdg})
            _, call = self.run_mocked()
            self.assertEqual(set(call.kwargs["env"]), {"PATH", "HOME", "GIT_NO_LAZY_FETCH"})

    def test_the_call_shape_is_exact(self):
        fake = self.fake_repo()
        _, call = self.run_mocked(fake)
        argv = call.args[0]
        self.assertEqual(argv, [self.git_bin, "--no-lazy-fetch", "-c", "core.fsmonitor=false", "-C", fake,
                                "check-ignore", "-q", "--", IGNORE_FILE])
        self.assertTrue(os.path.isabs(argv[0]))
        self.assertEqual(call.kwargs["timeout"], 2)
        for stream in ("stdin", "stdout", "stderr"):
            self.assertIs(call.kwargs[stream], subprocess.DEVNULL, stream)
        self.assertFalse(call.kwargs.get("shell", False))

    def test_both_safety_flags_reach_the_call(self):
        _, call = self.run_mocked()
        self.assertIn("--no-lazy-fetch", call.args[0])
        self.assertIn("core.fsmonitor=false", call.args[0])
        self.assertEqual(call.kwargs["env"].get("GIT_NO_LAZY_FETCH"), "1")

    def test_exit_codes_and_failures_map_to_a_state(self):
        fake = self.fake_repo()
        for code, want in ((0, "ignored"), (1, "not_ignored"), (128, "unknown"), (2, "unknown"), (-9, "unknown")):
            with self.subTest(code=code):
                self.assertEqual(self.run_mocked(fake, returncode=code)[0], want)
        for error in (subprocess.TimeoutExpired("git", 2), FileNotFoundError(2, "gone"),
                      PermissionError(13, "denied"), ValueError("embedded null byte")):
            with self.subTest(error=type(error).__name__), mock.patch.object(git_check.subprocess, "run",
                                                                              side_effect=error):
                self.assertEqual(self.state(fake), "unknown")

    # a repo must not run a program through this call

    def marker_script(self, name):
        marker = os.path.join(self.root, name + "-marker")
        script = self.script(os.path.join(self.root, name + ".sh"), "/usr/bin/touch '%s'\nexit 1\n" % marker)
        return script, marker

    def fsmonitor_repo(self, via_include):
        repo = self.repo("r")
        self.commit_file(repo)
        script, marker = self.marker_script("fsmonitor")
        if via_include:
            include = os.path.join(self.root, "inc.cfg")
            self.write(include, "[core]\n\tfsmonitor = %s\n" % script)
            self.git(repo, "config", "include.path", include)
        else:
            self.git(repo, "config", "core.fsmonitor", script)
        return repo, marker

    def test_fsmonitor_in_the_repo_config_does_not_run(self):
        repo, marker = self.fsmonitor_repo(via_include=False)
        self.raw_check_ignore(repo)
        self.assertTrue(os.path.exists(marker), "the test cannot see the hook run")
        os.remove(marker)
        self.raw_check_ignore(repo, "-c", "core.fsmonitor=false")
        self.assertFalse(os.path.exists(marker), "core.fsmonitor=false did not stop the hook")
        self.assertEqual(self.state(repo), "not_ignored")
        self.assertFalse(os.path.exists(marker))

    def test_fsmonitor_through_include_path_does_not_run(self):
        repo, marker = self.fsmonitor_repo(via_include=True)
        self.raw_check_ignore(repo)
        self.assertTrue(os.path.exists(marker), "the test cannot see the hook run")
        os.remove(marker)
        self.assertEqual(self.state(repo), "not_ignored")
        self.assertFalse(os.path.exists(marker))

    def test_a_missing_gitignore_blob_in_a_partial_clone_is_not_fetched(self):
        origin = self.repo("origin")
        self.write(os.path.join(origin, ".gitignore"), "*.local.json\n")
        self.git(origin, "add", ".gitignore")
        self.git(origin, "commit", "-q", "-m", "seed")
        server = os.path.join(self.root, "server.git")
        self.git(self.root, "clone", "-q", "--bare", origin, server)
        self.git(server, "config", "uploadpack.allowFilter", "true")
        self.git(server, "config", "uploadpack.allowAnySHA1InWant", "true")
        clone = os.path.join(self.root, "clone")
        self.git(self.root, "clone", "-q", "--filter=blob:none", "--no-checkout", "file://" + server, clone)
        self.git(clone, "read-tree", "HEAD")
        self.git(clone, "update-index", "--skip-worktree", ".gitignore")
        missing = [line for line in self.git(clone, "rev-list", "--objects", "--missing=print", "HEAD").splitlines()
                   if line.startswith("?")]
        if not missing or os.path.exists(os.path.join(clone, ".gitignore")):
            self.skipTest("this git did not leave the .gitignore blob missing in a partial clone")
        script, marker = self.marker_script("ssh")
        self.git(clone, "config", "core.sshCommand", script)
        self.git(clone, "remote", "set-url", "origin", "ssh://example.invalid/x.git")
        self.raw_check_ignore(clone)
        self.assertTrue(os.path.exists(marker), "the test cannot see the lazy fetch run")
        os.remove(marker)
        self.raw_check_ignore(clone, "--no-lazy-fetch")
        self.assertFalse(os.path.exists(marker), "--no-lazy-fetch did not stop the fetch")
        self.assertEqual(self.state(clone), "not_ignored")
        self.assertFalse(os.path.exists(marker))


GIT_TIMEOUT = 60


class RepoRootBase(unittest.TestCase):
    """Folders under a real-path temp root. home is a folder that holds no repo."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-repo-root-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)
        self.home = self.folder("home")

    def folder(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def root_of(self, path):
        return git_check.repo_root(path, home=self.home)

    def handmade(self, work=None):
        """Build the files git writes for a linked worktree. Return (main, work, git_dir)."""
        main = self.folder("main")
        git_dir = self.folder("main", ".git", "worktrees", "wt")
        work = work or self.folder("wt")
        self.write(os.path.join(git_dir, "commondir"), "../..\n")
        self.write(os.path.join(git_dir, "gitdir"), os.path.join(work, ".git") + "\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % git_dir)
        return main, work, git_dir


class RepoRoot(RepoRootBase):
    def test_no_path_and_no_git_are_no_repo(self):
        self.assertEqual(git_check.repo_root(None), ("no_repo", None))
        self.assertEqual(git_check.repo_root(""), ("no_repo", None))
        probe = self.root_of(self.folder("plain"))
        if probe[0] != "no_repo" and any(os.path.lexists(os.path.join(d, ".git"))
                                         for d in RepoPlace.above(self)):
            self.skipTest("the temp folder sits inside a repo")
        self.assertEqual(probe, ("no_repo", None))

    def test_a_git_folder_at_the_path_is_root(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        self.assertEqual(self.root_of(repo), ("root", repo))

    def test_a_git_folder_at_a_parent_is_subfolder(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        self.assertEqual(self.root_of(self.folder("r", "a", "b")), ("subfolder", repo))

    def test_a_missing_path_walks_up(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        self.assertEqual(self.root_of(os.path.join(repo, "gone", "deeper")), ("subfolder", repo))

    def test_a_symlinked_path_gives_the_real_root(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        link = os.path.join(self.root, "link")
        os.symlink(self.folder("r", "app"), link)
        self.assertEqual(self.root_of(link), ("subfolder", repo))

    def test_a_handmade_worktree_is_worktree_with_the_main_root(self):
        main, work, _ = self.handmade()
        self.assertEqual(self.root_of(work), ("worktree", main))
        self.assertEqual(self.root_of(self.folder("wt", "a", "b")), ("worktree", main))

    def test_a_bare_repo_named_dot_git_is_unknown(self):
        main, work, _ = self.handmade()
        self.write(os.path.join(main, ".git", "config"), "[core]\n\trepositoryformatversion = 0\n\tbare = true\n")
        self.assertEqual(self.root_of(work), ("unknown", None))

    def test_a_config_that_is_not_bare_keeps_the_worktree(self):
        main, work, _ = self.handmade()
        self.write(os.path.join(main, ".git", "config"),
                   "[core]\n\tbare = false\n[remote \"o\"]\n\turl = x\n[other]\n\tbare = true\n")
        self.assertEqual(self.root_of(work), ("worktree", main))

    def test_a_config_over_64_kib_is_unknown(self):
        main, work, _ = self.handmade()
        self.write(os.path.join(main, ".git", "config"), "[core]\n" + "# x\n" * 20000)
        self.assertEqual(self.root_of(work), ("unknown", None))

    def test_the_nearest_git_wins_over_a_parent_git_folder(self):
        main, work, _ = self.handmade(work=self.folder("main", "inner"))
        self.assertEqual(self.root_of(work), ("worktree", main))
        self.assertEqual(self.root_of(self.folder("main", "other")), ("subfolder", main))

    def test_crlf_line_ends_are_accepted(self):
        main, work, git_dir = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: %s\r\n" % git_dir)
        self.write(os.path.join(git_dir, "commondir"), "../..\r\n")
        self.write(os.path.join(git_dir, "gitdir"), os.path.join(work, ".git") + "\r\n")
        self.assertEqual(self.root_of(work), ("worktree", main))

    def test_a_missing_final_newline_is_accepted(self):
        main, work, git_dir = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: %s" % git_dir)
        self.assertEqual(self.root_of(work), ("worktree", main))

    def test_a_relative_gitdir_is_relative_to_the_work_folder(self):
        main, work, git_dir = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % os.path.relpath(git_dir, work))
        self.assertEqual(self.root_of(work), ("worktree", main))

    def test_a_git_dir_without_commondir_is_a_submodule(self):
        work = self.folder("w")
        other = self.folder("elsewhere", "modules", "w")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % other)
        self.assertEqual(self.root_of(work), ("submodule", work))
        self.assertEqual(self.root_of(self.folder("w", "deep")), ("submodule", work))

    # every bad chain reads unknown

    def assert_unknown(self, path):
        self.assertEqual(self.root_of(path), ("unknown", None))

    def test_no_back_link_is_unknown(self):
        _, work, git_dir = self.handmade()
        os.remove(os.path.join(git_dir, "gitdir"))
        self.assert_unknown(work)

    def test_a_back_link_to_another_folder_is_unknown(self):
        _, work, git_dir = self.handmade()
        self.write(os.path.join(git_dir, "gitdir"), os.path.join(self.folder("other"), ".git") + "\n")
        self.assert_unknown(work)

    def test_a_git_dir_outside_the_worktrees_folder_is_unknown(self):
        main, work, _ = self.handmade()
        stray = self.folder("stray")
        self.write(os.path.join(stray, "commondir"), os.path.join(main, ".git") + "\n")
        self.write(os.path.join(stray, "gitdir"), os.path.join(work, ".git") + "\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % stray)
        self.assert_unknown(work)

    def test_a_git_dir_deeper_than_worktrees_is_unknown(self):
        main, work, _ = self.handmade()
        deep = self.folder("main", ".git", "worktrees", "a", "b")
        self.write(os.path.join(deep, "commondir"), "../../..\n")
        self.write(os.path.join(deep, "gitdir"), os.path.join(work, ".git") + "\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % deep)
        self.assert_unknown(work)

    def test_a_common_dir_not_named_dot_git_is_unknown(self):
        _, work, git_dir = self.handmade()
        shutil.move(os.path.join(self.root, "main", ".git"), os.path.join(self.root, "main", "store"))
        git_dir = os.path.join(self.root, "main", "store", "worktrees", "wt")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % git_dir)
        self.assert_unknown(work)

    def test_a_missing_git_dir_is_unknown(self):
        work = self.folder("w")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % os.path.join(self.root, "nowhere"))
        self.assert_unknown(work)

    def test_a_git_dir_that_is_a_file_is_unknown(self):
        work = self.folder("w")
        self.write(os.path.join(self.root, "afile"), "x\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % os.path.join(self.root, "afile"))
        self.assert_unknown(work)

    def test_a_fifo_named_dot_git_is_unknown_and_does_not_hang(self):
        work = self.folder("w")
        os.mkfifo(os.path.join(work, ".git"))
        self.assert_unknown(work)
        self.assert_unknown(self.folder("w", "sub"))

    def test_a_git_file_over_4096_bytes_is_unknown(self):
        _, work, git_dir = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: %s\n%s" % (git_dir, "a" * 5120))
        self.assert_unknown(work)
        self.write(os.path.join(work, ".git"), "gitdir: " + "a" * 5120)
        self.assert_unknown(work)

    def test_a_git_file_of_exactly_4096_bytes_is_read(self):
        # The cap is on the read, not on the path: a long but valid line still reaches the chain check.
        _, work, _ = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: " + "a" * (4096 - len("gitdir: ")))
        self.assert_unknown(work)  # unknown because the folder is missing, not because of the cap

    def test_a_symlinked_git_is_unknown(self):
        real = self.folder("real", ".git")
        a = self.folder("a")
        os.symlink(real, os.path.join(a, ".git"))
        self.assert_unknown(a)
        _, work, _ = self.handmade()
        b = self.folder("b")
        os.symlink(os.path.join(work, ".git"), os.path.join(b, ".git"))
        self.assert_unknown(b)

    def test_a_two_line_git_file_is_unknown(self):
        _, work, git_dir = self.handmade()
        self.write(os.path.join(work, ".git"), "gitdir: %s\ngitdir: %s\n" % (git_dir, git_dir))
        self.assert_unknown(work)
        self.write(os.path.join(work, ".git"), "gitdir: %s\n\n" % git_dir)
        self.assert_unknown(work)

    def test_a_git_file_that_is_not_a_gitdir_line_is_unknown(self):
        _, work, git_dir = self.handmade()
        for text in ("", "\n", "gitdir:\n", "gitdir: \n", "%s\n" % git_dir, "GITDIR: %s\n" % git_dir,
                     "gitdir: %s\x00x\n" % git_dir):
            with self.subTest(text=text):
                self.write(os.path.join(work, ".git"), text)
                self.assert_unknown(work)

    def test_a_git_file_that_is_not_utf8_is_unknown(self):
        work = self.folder("w")
        with open(os.path.join(work, ".git"), "wb") as fh:
            fh.write(b"gitdir: \xff\xfe\n")
        self.assert_unknown(work)

    def test_a_git_file_that_cannot_be_read_is_unknown(self):
        _, work, _ = self.handmade()
        os.chmod(os.path.join(work, ".git"), 0)
        self.addCleanup(os.chmod, os.path.join(work, ".git"), 0o644)
        if os.geteuid() == 0:
            self.skipTest("root reads any file")
        self.assert_unknown(work)

    def test_a_nearer_bad_git_hides_a_parent_repo(self):
        os.mkdir(os.path.join(self.folder("r"), ".git"))
        self.write(os.path.join(self.folder("r", "sub"), ".git"), "nonsense\n")
        self.assert_unknown(self.folder("r", "sub", "deep"))

    def test_repo_root_never_raises(self):
        for bad in ("\x00", "a\x00b", 5, b"/x", object()):
            with self.subTest(bad=bad):
                place, root = git_check.repo_root(bad)
                self.assertIn(place, ("unknown", "no_repo"))
                self.assertIsNone(root)

    # the exceptions in the Claude Code docs

    def test_a_root_that_is_home_is_the_start_folder(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        self.assertEqual(git_check.repo_root(repo, home=repo), ("start_folder", None))
        self.assertEqual(git_check.repo_root(self.folder("r", "sub"), home=repo), ("start_folder", None))
        self.assertEqual(git_check.repo_root(repo, home=self.home), ("root", repo))
        self.assertEqual(git_check.repo_root(repo), ("root", repo))

    def test_a_symlinked_home_still_matches(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        link = os.path.join(self.root, "homelink")
        os.symlink(repo, link)
        self.assertEqual(git_check.repo_root(repo, home=link), ("start_folder", None))

    def test_a_home_that_is_the_main_checkout_covers_a_worktree(self):
        main, work, _ = self.handmade()
        self.assertEqual(git_check.repo_root(work, home=main), ("start_folder", None))

    def test_windows_is_the_start_folder(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        with mock.patch.object(git_check, "_WINDOWS", True):
            self.assertEqual(self.root_of(repo), ("start_folder", None))
            self.assertEqual(self.root_of(self.folder("none")), ("no_repo", None))
        self.assertEqual(self.root_of(repo), ("root", repo))

    def test_a_wrong_owner_is_the_start_folder(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        os.mkdir(os.path.join(repo, ".claude"))
        real = os.lstat
        for name in ("", ".git", ".claude"):
            target = os.path.join(repo, name) if name else repo
            with self.subTest(owner_of=name or "root"):
                def lstat(path, *args, **kwargs):
                    info = real(path, *args, **kwargs)
                    if path == target:
                        fields = list(info)
                        fields[4] = info.st_uid + 1
                        return os.stat_result(fields)
                    return info

                with mock.patch.object(git_check.os, "lstat", side_effect=lstat):
                    self.assertEqual(self.root_of(repo), ("start_folder", None))
                    self.assertEqual(self.root_of(self.folder("r", "sub")), ("start_folder", None))
        self.assertEqual(self.root_of(repo), ("root", repo))

    def test_a_missing_claude_folder_is_not_an_exception(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        self.assertFalse(os.path.lexists(os.path.join(repo, ".claude")))
        self.assertEqual(self.root_of(repo), ("root", repo))


class RepoRootGuard(RepoRootBase):
    def run_recorded(self, path, bound=None):
        events, reads = [], []  # reads: one list of (asked, got) per open, because fd numbers get reused
        real_lstat, real_open, real_read = os.lstat, os.open, os.read

        def lstat(p, *args, **kwargs):
            events.append(("lstat", p))
            return real_lstat(p, *args, **kwargs)

        def opener(p, flags, *args, **kwargs):
            events.append(("open", p, flags))
            reads.append([])
            return real_open(p, flags, *args, **kwargs)

        def reader(fd, size):
            data = real_read(fd, size)
            reads[-1].append((size, len(data)))
            return data

        def refuse(*args, **kwargs):
            raise AssertionError("repo_root must not call this")

        with mock.patch.object(git_check.subprocess, "run", side_effect=refuse), \
                mock.patch.object(git_check.subprocess, "Popen", side_effect=refuse), \
                mock.patch("builtins.open", side_effect=refuse), \
                mock.patch.object(os, "lstat", side_effect=lstat), \
                mock.patch.object(os, "open", side_effect=opener), \
                mock.patch.object(os, "read", side_effect=reader):
            result = git_check.repo_root(path, home=self.home, bound=bound)
        return result, events, reads

    def assert_safe_opens(self, events):
        opens = [(i, e) for i, e in enumerate(events) if e[0] == "open"]
        for index, (_, path, flags) in opens:
            self.assertTrue(flags & os.O_NOFOLLOW, path)
            self.assertTrue(flags & os.O_NONBLOCK, path)
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC), path)
            self.assertIn(("lstat", path), events[:index], "no lstat before the open of " + path)
        return [e[1] for _, e in opens]

    def test_a_worktree_read_opens_three_files_safely(self):
        main, work, git_dir = self.handmade()
        result, events, reads = self.run_recorded(work)
        self.assertEqual(result, ("worktree", main))
        opened = self.assert_safe_opens(events)
        self.assertEqual(opened, [os.path.join(work, ".git"), os.path.join(git_dir, "commondir"),
                                  os.path.join(git_dir, "gitdir")])
        self.assertEqual(len(reads), 3)
        for calls in reads:
            self.assertLessEqual(sum(got for _, got in calls), 4097)
            self.assertLessEqual(max(asked for asked, _ in calls), 4097)

    def test_a_5_kib_file_is_never_read_past_4097_bytes(self):
        work = self.folder("big")
        self.write(os.path.join(work, ".git"), "gitdir: " + "a" * 5000)
        result, events, reads = self.run_recorded(work)
        self.assertEqual(result, ("unknown", None))
        self.assertEqual(self.assert_safe_opens(events), [os.path.join(work, ".git")])
        self.assertEqual(len(reads), 1)
        calls = reads[0]
        self.assertEqual(sum(got for _, got in calls), 4097)  # one byte past the cap is enough to refuse
        self.assertLessEqual(max(asked for asked, _ in calls), 4097)

    def test_a_fifo_and_a_symlink_are_never_opened(self):
        work = self.folder("fifo")
        os.mkfifo(os.path.join(work, ".git"))
        link = self.folder("link")
        os.symlink(self.folder("real", ".git"), os.path.join(link, ".git"))
        for path in (work, link):
            result, events, _ = self.run_recorded(path)
            self.assertEqual(result, ("unknown", None))
            self.assertEqual(self.assert_safe_opens(events), [])

    def test_a_bound_below_the_git_file_never_opens_it(self):
        main, work, git_dir = self.handmade()
        inner = self.folder("wt", "deep", "er")
        for bound in (inner, self.folder("wt", "deep")):
            result, events, reads = self.run_recorded(inner, bound=bound)
            self.assertEqual(result, ("unknown", None))
            self.assertEqual(self.assert_safe_opens(events), [])
            self.assertEqual(reads, [])
            # no ownership lstat of the folder, its .git/.claude beyond the walk's own .git probes
            self.assertNotIn(("lstat", os.path.join(work, ".claude")), events)

    def test_a_bound_below_a_git_folder_reads_unknown_without_the_ownership_check(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        result, events, reads = self.run_recorded(self.folder("r", "sub"), bound=self.folder("r", "sub"))
        self.assertEqual(result, ("unknown", None))
        self.assertNotIn(("lstat", os.path.join(repo, ".claude")), events)
        self.assertEqual(reads, [])

    def test_a_bound_that_holds_the_repo_gives_the_normal_answer(self):
        main, work, git_dir = self.handmade()
        for bound in (self.root, work):  # the folder equal to the bound counts as inside
            result, events, _ = self.run_recorded(work, bound=bound)
            self.assertEqual(result, ("worktree", main))
            self.assertEqual(self.assert_safe_opens(events)[0], os.path.join(work, ".git"))

    def test_a_bound_with_no_git_anywhere_is_no_repo(self):
        plain = self.folder("plain", "a")
        probe = git_check.repo_root(plain, home=self.home)
        if probe[0] != "no_repo":
            self.skipTest("the temp folder sits inside a repo")
        self.assertEqual(git_check.repo_root(plain, home=self.home, bound=self.root), ("no_repo", None))
        self.assertEqual(git_check.repo_root(plain, home=self.home, bound=plain), ("no_repo", None))

    def test_a_folder_walk_opens_nothing(self):
        repo = self.folder("r")
        os.mkdir(os.path.join(repo, ".git"))
        result, events, reads = self.run_recorded(self.folder("r", "sub"))
        self.assertEqual(result, ("subfolder", repo))
        self.assertEqual(self.assert_safe_opens(events), [])
        self.assertEqual(reads, [])


@unittest.skipIf(REAL_GIT is None, "git is not installed")
class RepoRootRealGit(RepoRootBase):
    """Real git on throwaway repos, run with a closed environment."""

    def setUp(self):
        super().setUp()
        self.git_home = self.folder("githome")

    def env(self):
        return {"PATH": MINIMAL_PATH, "HOME": self.git_home, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}

    def run_git(self, cwd, *args):
        return subprocess.run([REAL_GIT, *args], cwd=cwd, env=self.env(), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=GIT_TIMEOUT, check=False)

    def git(self, cwd, *args):
        done = self.run_git(cwd, *args)
        self.assertEqual(done.returncode, 0, done.stdout.decode("utf-8", "replace"))

    def repo(self, *parts):
        path = self.folder(*parts)
        self.git(path, "init", "-q", "-b", "main")
        self.write(os.path.join(path, "README"), "x\n")
        self.git(path, "add", "README")
        self.git(path, "commit", "-q", "-m", "seed")
        return path

    def test_a_repo_top_is_root_and_a_subfolder_is_subfolder(self):
        repo = self.repo("r")
        self.assertEqual(self.root_of(repo), ("root", repo))
        self.assertEqual(self.root_of(self.folder("r", "a", "b")), ("subfolder", repo))

    def test_a_linked_worktree_reads_the_main_checkout(self):
        main = self.repo("main")
        work = os.path.join(self.root, "wt")
        self.git(main, "worktree", "add", "-q", "-b", "wt", work)
        self.assertEqual(self.root_of(work), ("worktree", main))
        self.assertEqual(self.root_of(self.folder("wt", "sub")), ("worktree", main))

    def test_a_relative_paths_worktree_reads_the_main_checkout(self):
        main = self.repo("main")
        work = os.path.join(self.root, "wtrel")
        done = self.run_git(main, "worktree", "add", "-q", "--relative-paths", "-b", "wtrel", work)
        if done.returncode != 0:
            self.skipTest("this git has no worktree add --relative-paths")
        self.assertEqual(self.root_of(work), ("worktree", main))
        self.assertEqual(self.root_of(self.folder("wtrel", "sub")), ("worktree", main))

    def test_a_worktree_of_a_bare_repo_named_dot_git_is_unknown(self):
        bare = self.folder("holder", ".git")
        self.git(bare, "init", "-q", "--bare", "-b", "main")
        seed = self.repo("seed")
        self.git(seed, "push", "-q", bare, "main")
        work = os.path.join(self.root, "wtbare")
        self.git(bare, "worktree", "add", "-q", work, "main")
        self.assertTrue(os.path.isfile(os.path.join(work, ".git")))
        self.assertEqual(self.root_of(work), ("unknown", None))

    def test_a_submodule_is_its_own_root(self):
        source = self.repo("source")
        top = self.repo("top")
        self.git(top, "-c", "protocol.file.allow=always", "submodule", "add", "-q", source, "sub")
        sub = os.path.join(top, "sub")
        self.assertTrue(os.path.isfile(os.path.join(sub, ".git")))
        self.assertEqual(self.root_of(sub), ("submodule", sub))
        self.assertEqual(self.root_of(self.folder("top", "sub", "deep")), ("submodule", sub))
        self.assertEqual(self.root_of(self.folder("top", "other")), ("subfolder", top))

    def test_a_separate_git_dir_repo_reads_as_a_submodule(self):
        work = self.folder("sep")
        store = os.path.join(self.root, "store.git")
        self.git(work, "init", "-q", "-b", "main", "--separate-git-dir", store)
        self.assertTrue(os.path.isfile(os.path.join(work, ".git")))
        self.assertEqual(self.root_of(work), ("submodule", work))
        self.assertEqual(self.root_of(self.folder("sep", "sub")), ("submodule", work))


if __name__ == "__main__":
    unittest.main()
