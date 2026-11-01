"""Tests for dashboard/git_check.py: the lstat walk that finds where a project sits in a repo (T23)
and the git check-ignore call that says whether git ignores .claude/settings.local.json (T22).

Every case builds real folders under the temp root. RepoPlace patches only os.lstat. IgnoreState runs
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


if __name__ == "__main__":
    unittest.main()
