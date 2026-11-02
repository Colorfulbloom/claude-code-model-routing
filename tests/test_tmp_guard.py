"""Tests for helpers._tmp_base: a test temp base never sits inside a git work tree (#104).

After #104 a project path inside a git work tree resolves to that repo's real
.claude/settings.local.json, so a base inside one could let a test write to it.
Every case builds its repo-like folders under a temp root that passed the guard.
"""
import os
import tempfile
import unittest
from unittest import mock

import helpers


class TmpBaseGuard(unittest.TestCase):
    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="mr-tmp-guard-", dir=helpers._tmp_base()))
        self.addCleanup(helpers.rmtree_force, self.root)

    def folder(self, *parts):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def test_the_normal_call_passes(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("MR_TEST_TMP", None)
            self.assertIsNone(helpers._tmp_base())

    def test_a_set_base_outside_any_repo_is_returned_and_created(self):
        base = os.path.join(self.root, "base", "deeper")
        with mock.patch.dict(os.environ, {"MR_TEST_TMP": base}):
            self.assertEqual(helpers._tmp_base(), base)
        self.assertTrue(os.path.isdir(base))

    def test_a_base_inside_a_repo_is_refused(self):
        repo = self.folder("repo")
        os.mkdir(os.path.join(repo, ".git"))
        for base in (repo, os.path.join(repo, "tmp"), os.path.join(repo, "a", "b")):
            with self.subTest(base=base), mock.patch.dict(os.environ, {"MR_TEST_TMP": base}):
                with self.assertRaises(RuntimeError) as caught:
                    helpers._tmp_base()
                self.assertIn(repo, str(caught.exception))
        self.assertFalse(os.path.exists(os.path.join(repo, "a")), "the refused base must not be created")
        self.assertFalse(os.path.exists(os.path.join(repo, "tmp")), "the refused base must not be created")

    def test_a_git_file_or_other_entry_counts_too(self):
        worktree = self.folder("wt")
        with open(os.path.join(worktree, ".git"), "w", encoding="utf-8") as fh:
            fh.write("gitdir: elsewhere\n")
        linked = self.folder("linked")
        os.symlink(self.folder("real"), os.path.join(linked, ".git"))
        for repo in (worktree, linked):
            with self.subTest(repo=repo), mock.patch.dict(os.environ, {"MR_TEST_TMP": os.path.join(repo, "t")}):
                with self.assertRaises(RuntimeError) as caught:
                    helpers._tmp_base()
                self.assertIn(repo, str(caught.exception))

    def test_a_symlinked_base_is_judged_by_its_real_path(self):
        repo = self.folder("repo")
        os.mkdir(os.path.join(repo, ".git"))
        link = os.path.join(self.root, "link")
        os.symlink(self.folder("repo", "inner"), link)
        with mock.patch.dict(os.environ, {"MR_TEST_TMP": link}):
            with self.assertRaises(RuntimeError):
                helpers._tmp_base()

    def test_an_unset_base_checks_the_system_temp_folder(self):
        repo = self.folder("repo")
        os.mkdir(os.path.join(repo, ".git"))
        with mock.patch.dict(os.environ), mock.patch.object(helpers.tempfile, "gettempdir", return_value=repo):
            os.environ.pop("MR_TEST_TMP", None)
            with self.assertRaises(RuntimeError):
                helpers._tmp_base()

    def test_an_empty_setting_counts_as_unset(self):
        with mock.patch.dict(os.environ, {"MR_TEST_TMP": ""}):
            self.assertIsNone(helpers._tmp_base())


if __name__ == "__main__":
    unittest.main()
