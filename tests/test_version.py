"""Tests for dashboard/version.py: parse, compare and read the installed Claude Code version.

read_installed runs against throwaway folders under the helpers' temp base. Each holds a fake claude file
that is never run, and the PATH is built in the test, so the real PATH and the real claude are never used.
"""
import json
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import version  # noqa: E402


def new_dir(case):
    path = os.path.realpath(tempfile.mkdtemp(prefix="version-", dir=helpers._tmp_base()))
    case.addCleanup(helpers.rmtree_force, path)
    return path


def make_file(path, text="#!/bin/sh\nexit 1\n", mode=0o755):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)
    return path


def link_on_path(root, target):
    """Link bin/claude to target and return the PATH text that finds it."""
    bin_dir = os.path.join(root, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    os.symlink(target, os.path.join(bin_dir, "claude"))
    return bin_dir


def tree(root):
    """Every path under root with its size and mtime, to show a read wrote nothing."""
    out = {}
    for base, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(base, name)
            info = os.lstat(path)
            out[path] = (info.st_size, info.st_mtime_ns)
    return out


class Parse(unittest.TestCase):
    def test_leading_dotted_numbers(self):
        self.assertEqual(version.parse("2.1.302"), (2, 1, 302))
        self.assertEqual(version.parse("2.1.302 (Claude Code)"), (2, 1, 302))
        self.assertEqual(version.parse("10"), (10,))
        self.assertEqual(version.parse("2.1.0-beta"), (2, 1, 0))

    def test_text_that_is_not_a_version(self):
        for bad in ("", "v2.1.302", "latest", " 2.1.302", ".1", "x2", None, 2, 2.1, ["2.1"], b"2.1"):
            self.assertIsNone(version.parse(bad), bad)


class Older(unittest.TestCase):
    def test_numbers_not_text(self):
        self.assertTrue(version.older("2.1.302", "2.1.1000"))
        self.assertFalse(version.older("2.1.1000", "2.1.302"))
        self.assertTrue(version.older("2.9.0", "2.10.0"))

    def test_equal_is_not_older(self):
        self.assertFalse(version.older("2.1.302", "2.1.302"))

    def test_unequal_lengths_pad_with_zero(self):
        self.assertFalse(version.older("2.1", "2.1.0"))
        self.assertFalse(version.older("2.1.0", "2.1"))
        self.assertTrue(version.older("2.1", "2.1.1"))
        self.assertFalse(version.older("2.1.1", "2.1"))
        self.assertTrue(version.older("2", "2.0.1"))

    def test_anything_that_does_not_parse_gives_false(self):
        for a, b in (("x", "2.1.0"), ("2.1.0", "x"), (None, "2.1.0"), ("2.1.0", None), ("", ""), (1, 2)):
            self.assertFalse(version.older(a, b), (a, b))


class Oldest(unittest.TestCase):
    def test_the_oldest_comes_back_as_written(self):
        self.assertEqual(version.oldest(["2.1.1000", "2.1.302 (Claude Code)", "2.1.400"]), "2.1.302 (Claude Code)")
        self.assertEqual(version.oldest(["2.10.0", "2.9.0"]), "2.9.0")

    def test_text_that_does_not_parse_is_skipped(self):
        self.assertEqual(version.oldest([None, "latest", "2.1.5", 7]), "2.1.5")

    def test_nothing_to_compare(self):
        self.assertIsNone(version.oldest([]))
        self.assertIsNone(version.oldest([None, "x"]))

    def test_a_generator_works(self):
        self.assertEqual(version.oldest(v for v in ("2.2.0", "2.1.9")), "2.1.9")


class ReadInstalled(unittest.TestCase):
    def setUp(self):
        self.root = new_dir(self)

    def read_without_writes(self, path_env):
        before = tree(self.root)
        got = version.read_installed(path_env)
        self.assertEqual(tree(self.root), before, "read_installed wrote something")
        return got

    def test_native_installer(self):
        real = make_file(os.path.join(self.root, "share", "claude", "versions", "2.1.302"))
        path_env = link_on_path(self.root, real)
        self.assertEqual(self.read_without_writes(path_env), "2.1.302")

    def test_native_folder_with_a_name_that_is_not_a_version(self):
        real = make_file(os.path.join(self.root, "share", "claude", "versions", "latest"))
        self.assertIsNone(self.read_without_writes(link_on_path(self.root, real)))

    def test_homebrew_cask(self):
        real = make_file(os.path.join(self.root, "Caskroom", "claude-code", "2.1.310", "claude"))
        self.assertEqual(self.read_without_writes(link_on_path(self.root, real)), "2.1.310")

    def test_cask_shaped_folder_with_another_grandparent_is_unknown(self):
        real = make_file(os.path.join(self.root, "Caskroom", "other", "2.1.310", "claude"))
        self.assertIsNone(self.read_without_writes(link_on_path(self.root, real)))

    def test_npm_package_beside_the_file(self):
        package = os.path.join(self.root, "lib", "node_modules", "@anthropic-ai", "claude-code")
        make_file(os.path.join(package, "package.json"),
                  json.dumps({"name": "@anthropic-ai/claude-code", "version": "2.1.305"}), 0o644)
        real = make_file(os.path.join(package, "bin", "claude.exe"))
        self.assertEqual(self.read_without_writes(link_on_path(self.root, real)), "2.1.305")

    def test_npm_platform_package_name_with_the_prefix(self):
        package = os.path.join(self.root, "node_modules", "@anthropic-ai", "claude-code-darwin-arm64")
        make_file(os.path.join(package, "package.json"),
                  json.dumps({"name": "@anthropic-ai/claude-code-darwin-arm64", "version": "2.1.306"}), 0o644)
        real = make_file(os.path.join(package, "claude"))
        self.assertEqual(self.read_without_writes(link_on_path(self.root, real)), "2.1.306")

    def test_npm_package_three_folders_up_counts_and_four_does_not(self):
        package = os.path.join(self.root, "pkg")
        make_file(os.path.join(package, "package.json"),
                  json.dumps({"name": "@anthropic-ai/claude-code", "version": "2.1.307"}), 0o644)
        near = make_file(os.path.join(package, "a", "b", "claude.exe"))
        self.assertEqual(self.read_without_writes(link_on_path(self.root, near)), "2.1.307")
        other = os.path.join(self.root, "other")
        os.makedirs(other)
        make_file(os.path.join(other, "package.json"),
                  json.dumps({"name": "@anthropic-ai/claude-code", "version": "2.1.307"}), 0o644)
        far = make_file(os.path.join(other, "a", "b", "c", "claude.exe"))
        self.assertIsNone(self.read_without_writes(link_on_path(os.path.join(self.root, "far"), far)))

    def test_npm_package_with_another_name_or_a_bad_version_is_unknown(self):
        for index, data in enumerate((
                {"name": "something-else", "version": "2.1.305"},
                {"name": "@anthropic-ai/claude-code", "version": "next"},
                {"name": "@anthropic-ai/claude-code", "version": 5},
                {"name": "@anthropic-ai/claude-code"},
                ["not", "an", "object"])):
            folder = os.path.join(self.root, "case%d" % index)
            make_file(os.path.join(folder, "package.json"), json.dumps(data), 0o644)
            real = make_file(os.path.join(folder, "claude.exe"))
            self.assertIsNone(self.read_without_writes(link_on_path(folder, real)), data)

    def test_package_json_that_is_not_json_or_is_huge(self):
        folder = os.path.join(self.root, "bad")
        make_file(os.path.join(folder, "package.json"), "{not json", 0o644)
        real = make_file(os.path.join(folder, "claude.exe"))
        self.assertIsNone(self.read_without_writes(link_on_path(folder, real)))
        big = os.path.join(self.root, "big")
        padding = " " * (version.PACKAGE_READ_CAP + 10)
        make_file(os.path.join(big, "package.json"),
                  padding + json.dumps({"name": "@anthropic-ai/claude-code", "version": "2.1.1"}), 0o644)
        real = make_file(os.path.join(big, "claude.exe"))
        self.assertIsNone(self.read_without_writes(link_on_path(big, real)))

    def test_any_other_layout_is_unknown(self):
        real = make_file(os.path.join(self.root, "somewhere", "claude"))
        self.assertIsNone(self.read_without_writes(link_on_path(self.root, real)))

    def test_no_claude_on_the_path(self):
        os.makedirs(os.path.join(self.root, "bin"))
        self.assertIsNone(self.read_without_writes(os.path.join(self.root, "bin")))

    def test_a_dangling_link_is_unknown(self):
        self.assertIsNone(self.read_without_writes(link_on_path(self.root, os.path.join(self.root, "gone"))))

    def test_no_path_means_none(self):
        for empty in (None, "", 5):
            self.assertIsNone(version.read_installed(empty), empty)

    def test_it_never_reads_the_environment_or_runs_a_program(self):
        real = make_file(os.path.join(self.root, "share", "claude", "versions", "2.1.302"))
        path_env = link_on_path(self.root, real)
        with mock.patch.dict(os.environ, {"PATH": "/nowhere"}), \
                mock.patch("subprocess.run", side_effect=AssertionError("ran a program")), \
                mock.patch("subprocess.Popen", side_effect=AssertionError("ran a program")), \
                mock.patch("os.system", side_effect=AssertionError("ran a program")):
            self.assertEqual(version.read_installed(path_env), "2.1.302")


class Installed(unittest.TestCase):
    def test_a_fixed_version_wins(self):
        ctx = types.SimpleNamespace(claude_version="2.1.310", path_env="/nowhere")
        self.assertEqual(version.installed(ctx), "2.1.310")

    def test_a_fixed_version_that_does_not_parse_is_ignored(self):
        root = new_dir(self)
        real = make_file(os.path.join(root, "share", "claude", "versions", "2.1.302"))
        ctx = types.SimpleNamespace(claude_version="latest", path_env=link_on_path(root, real))
        self.assertEqual(version.installed(ctx), "2.1.302")

    def test_nothing_set_gives_none(self):
        self.assertIsNone(version.installed(types.SimpleNamespace(claude_version=None, path_env=None)))


if __name__ == "__main__":
    unittest.main()
