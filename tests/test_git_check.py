"""Tests for dashboard/git_check.py, the lstat walk that finds where a project sits in a repo (T23).

Every case builds real folders under the temp root. Only the unreadable-entry case patches os.lstat.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
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

    def test_the_source_reads_nothing_and_starts_nothing(self):
        text = SOURCE.read_text(encoding="utf-8")
        for banned in (r"\bopen\(", r"\bsubprocess\b", r"os\.read\b"):
            self.assertIsNone(re.search(banned, text), banned)


if __name__ == "__main__":
    unittest.main()
