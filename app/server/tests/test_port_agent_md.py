"""Tests for the agent file helpers: app/server/agent_md.py.

Ported from tests/test_agent_md.py. The old file also checked that install.py takes
these helpers from agent_md and prints its old missing-field message. The installer
stays in the old app, so those two tests, and the Python 3.9 parse check, did not
come over. Every file here is made up in a throwaway folder.
"""

# ruff: noqa: PT009, PT027, PTH103, PTH118, PTH120, PTH123
#
# Ported unchanged so the old suite stays easy to compare: unittest assertions,
# os.path and open() string handling, % messages and long comment lines.

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import agent_md

AGENT_MD_PATH = Path(agent_md.__file__)

# Fixed allowlist used when sys.stdlib_module_names is missing.
STDLIB_FALLBACK = {"os", "re"}


def read(path: Path) -> str:
    """Return the text of a file."""
    return path.read_text(encoding="utf-8")


class SourceShapeTest(unittest.TestCase):
    def test_imports_only_standard_library(self) -> None:
        tree = ast.parse(read(AGENT_MD_PATH))
        allowed = getattr(sys, "stdlib_module_names", STDLIB_FALLBACK)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "relative import")
                names = [node.module or ""]
            else:
                continue
            for name in names:
                self.assertIn(name.split(".")[0], allowed, name)


class ListFilesSortedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="mr-test-", dir=helpers.tmp_base())
        self.addCleanup(helpers.rmtree_force, self.tmp)

    def touch(self, *parts: str) -> str:
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x\n")
        return path

    def test_sorted_with_subfolders(self) -> None:
        b = self.touch("b.md")
        a = self.touch("a.md")
        c = self.touch("sub", "c.md")
        d = self.touch("sub", "deeper", "d.md")
        self.assertEqual(agent_md.list_files_sorted(self.tmp), [a, b, c, d])

    def test_hidden_files_and_folders_skipped(self) -> None:
        keep = self.touch("keep.md")
        self.touch(".hidden.md")
        self.touch(".git", "config")
        self.touch("sub", ".secret.md")
        self.touch("sub", ".cache", "x.md")
        self.assertEqual(agent_md.list_files_sorted(self.tmp), [keep])

    def test_missing_folder_gives_empty_list(self) -> None:
        self.assertEqual(agent_md.list_files_sorted(os.path.join(self.tmp, "nope")), [])


class MissingFieldsTest(unittest.TestCase):
    def test_error_carries_the_label(self) -> None:
        with self.assertRaises(agent_md.MissingFieldsError) as ctx:
            agent_md.parse_agent_defaults("---\nmodel: x\n---\n", "demo.md")
        self.assertEqual(ctx.exception.label, "demo.md")
        with self.assertRaises(agent_md.MissingFieldsError) as ctx:
            agent_md.render_agent("no frontmatter\n", "m", "e", "other.md")
        self.assertEqual(ctx.exception.label, "other.md")
