"""Tests for dashboard/local_root.py: which settings.local.json a project reads and the dashboard writes (#104).

Every case builds folders under the temp root. A repo is a hand-made .git folder, or the files git writes
for a linked worktree, so no test runs git. A fake context carries only what for_project reads (the home
folder, the bound, the Claude Code version), and the last case goes through api_edit with a real World.
"""
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))

import local_root  # noqa: E402
import test_api_edit as edit_tests  # noqa: E402

LOCAL = os.path.join(".claude", "settings.local.json")


class Base(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-local-root-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)
        self.home = self.folder("home")

    def folder(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def repo(self, *parts):
        path = self.folder(*parts)
        os.mkdir(os.path.join(path, ".git"))
        return path

    def write(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def ctx(self, version=None, bound=None):
        return SimpleNamespace(home=self.home, root=bound, claude_version=version, path_env=None)

    def local(self, path, version="2.1.211", bound=None, **extra):
        project = SimpleNamespace(path=path, **extra)
        return local_root.for_project(self.ctx(version, bound), project)


class ForProject(Base):
    def test_no_repo_keeps_the_starting_folder(self):
        plain = self.folder("plain")
        if any(os.path.lexists(os.path.join(d, ".git")) for d in _above(plain)):
            self.skipTest("the temp folder sits inside a repo")
        got = self.local(plain)
        start = os.path.join(plain, LOCAL)
        self.assertEqual((got.place, got.base, got.path, got.start_path), ("no_repo", plain, start, start))
        self.assertEqual((got.leftover, got.locked, got.outside_project), (False, False, False))

    def test_a_repo_root_project_keeps_its_path_as_written(self):
        repo = self.repo("r")
        written = os.path.join(repo, ".", "")  # not the realpath's spelling
        got = self.local(written.rstrip(os.sep))
        self.assertEqual(got.place, "root")
        self.assertEqual(got.path, os.path.join(written.rstrip(os.sep), LOCAL))
        self.assertEqual((got.leftover, got.outside_project, got.locked), (False, False, False))

    def test_a_subfolder_reads_the_real_root_and_keeps_the_start_as_a_leftover(self):
        repo = self.repo("r")
        sub = self.folder("r", "a", "b")
        got = self.local(sub)
        self.assertEqual(got.place, "subfolder")
        self.assertEqual((got.base, got.path), (repo, os.path.join(repo, LOCAL)))
        self.assertEqual((got.start_base, got.start_path), (sub, os.path.join(sub, LOCAL)))
        self.assertEqual((got.leftover, got.outside_project, got.locked), (True, True, False))

    def test_a_worktree_reads_the_main_checkouts_file(self):
        main = self.repo("main")
        git_dir = self.folder("main", ".git", "worktrees", "wt")
        work = self.folder("wt")
        self.write(os.path.join(git_dir, "commondir"), "../..\n")
        self.write(os.path.join(git_dir, "gitdir"), os.path.join(work, ".git") + "\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % git_dir)
        got = self.local(work)
        self.assertEqual((got.place, got.base, got.path), ("worktree", main, os.path.join(main, LOCAL)))
        self.assertEqual((got.leftover, got.outside_project), (True, True))

    def test_the_version_rule(self):
        self.repo("r")
        sub = self.folder("r", "sub")
        old = self.local(sub, version="2.1.210")
        self.assertEqual(old.place, "old_version")
        self.assertEqual((old.path, old.base), (os.path.join(sub, LOCAL), sub))
        self.assertEqual((old.leftover, old.locked, old.outside_project), (False, False, False))
        for version in ("2.1.211", None):
            got = self.local(sub, version=version)
            self.assertEqual((got.place, got.base), ("subfolder", os.path.join(self.root, "r")), version)

    def test_a_root_outside_the_bound_is_unknown_and_locks(self):
        self.repo("r")
        sub = self.folder("r", "sub")
        got = self.local(sub, bound=sub)
        self.assertEqual(got.place, "unknown")
        self.assertIs(got.locked, True)
        self.assertEqual(got.path, os.path.join(sub, LOCAL))
        inside = self.local(sub, bound=self.root)
        self.assertEqual((inside.place, inside.locked), ("subfolder", False))

    def test_a_worktree_of_a_bare_repo_named_dot_git_is_unknown_and_locks(self):
        # The root can't be worked out (owner decision on #104), so the lock stays on and the path stays in the starting folder.
        holder = self.folder("holder")
        git_dir = self.folder("holder", ".git", "worktrees", "wt")
        work = self.folder("wt")
        self.write(os.path.join(holder, ".git", "config"), "[core]\n\tbare = true\n")
        self.write(os.path.join(git_dir, "commondir"), "../..\n")
        self.write(os.path.join(git_dir, "gitdir"), os.path.join(work, ".git") + "\n")
        self.write(os.path.join(work, ".git"), "gitdir: %s\n" % git_dir)
        got = self.local(work)
        self.assertEqual(got.place, "unknown")
        self.assertIs(got.locked, True)
        self.assertEqual((got.path, got.leftover), (os.path.join(work, LOCAL), False))

    def test_an_unexpanded_project_stays_in_its_own_folder(self):
        self.repo("r")
        got = self.local("~/work/app", unexpanded=True)
        start = os.path.join("~/work/app", LOCAL)
        self.assertEqual((got.place, got.path, got.start_path, got.leftover, got.locked),
                         ("no_repo", start, start, False, False))
        self.assertEqual(self.local("").path, os.path.join("", LOCAL))


def _above(path):
    out = []
    here = os.path.dirname(path)
    while True:
        out.append(here)
        parent = os.path.dirname(here)
        if parent == here:
            return out
        here = parent


class SymlinkedAlias(unittest.TestCase):
    """A project listed through a symlink of its folder, like /var for /private/var on macOS."""

    def test_the_root_file_is_under_the_real_root_and_a_save_writes_it(self):
        world = edit_tests.World(self, listed=[{"name": "App", "path": "{root}/repo/app"}],
                                 user={"model": edit_tests.SONNET})
        world.root_patch.stop()  # the real git_check.repo_root answers from here on
        repo = os.path.join(world.root, "repo")
        sub = os.path.join(repo, "app")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(sub)
        root_file = os.path.join(repo, LOCAL)
        world.put(root_file, {"effortLevel": "medium"})
        holder = os.path.realpath(tempfile.mkdtemp(prefix="mr-local-alias-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, holder)
        alias = os.path.join(holder, "alias")
        os.symlink(world.root, alias)
        written = os.path.join(alias, "repo", "app")
        self.assertNotEqual(written, sub)
        world.put(os.path.join(world.cfg, "routing-dashboard.json"),
                  json.dumps({"projects": [{"name": "App", "path": written}]}))
        world.key = "app"

        project = edit_tests.projects.load(world.ctx).find("app")
        self.assertEqual(project.path, written)
        got = local_root.for_project(world.ctx, project)
        self.assertTrue(got.path.startswith(world.root + os.sep), got.path)
        self.assertEqual(got.path, root_file)
        self.assertEqual(got.start_path, os.path.join(written, LOCAL))
        self.assertTrue(got.start_path.startswith(alias + os.sep))
        self.assertEqual((got.leftover, got.outside_project, got.locked), (True, True, False))

        body = world.targets()
        self.assertIsNone(body["project_lock"])
        row = edit_tests.file_of(body["files"], "local")
        self.assertIsNone(row["lock_reason"])
        target = edit_tests.target_of(body, "local")["target"]
        status, pv = world.preview(target, "high")
        self.assertEqual(status, 200, pv)
        status, saved = world.save(pv, target, "high")
        self.assertEqual(status, 200, saved)
        with open(root_file, "rb") as fh:
            self.assertEqual(json.loads(fh.read())["effortLevel"], "high")
        self.assertFalse(os.path.exists(os.path.join(sub, LOCAL)))


if __name__ == "__main__":
    unittest.main()
