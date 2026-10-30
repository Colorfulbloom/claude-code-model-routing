"""Tests for agent_md.py, the agent helpers shared by install.py and the dashboard.

Run from the repo root:
    /usr/bin/python3 -m unittest discover -s tests -p 'test_agent_md.py'
"""
import ast
import importlib.util
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402
from helpers import Sandbox  # noqa: E402

sys.path.insert(0, helpers.REPO)
import agent_md  # noqa: E402

AGENT_MD_PATH = os.path.join(helpers.REPO, "agent_md.py")
INSTALL_PATH = os.path.join(helpers.REPO, "install.py")

MOVED = ["LINE_RE", "split_line", "frontmatter_span", "strip_quotes", "find_field_lines",
         "parse_agent_defaults", "render_agent", "frontmatter_name", "find_agent_md_files",
         "read_bytes_text"]

# Fixed allowlist used when sys.stdlib_module_names is missing (Python before 3.10).
STDLIB_FALLBACK = {"os", "re"}


def load_install():
    spec = importlib.util.spec_from_file_location("install_under_test", INSTALL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class MovedNamesTest(unittest.TestCase):
    def test_install_defines_none_of_the_moved_names(self):
        tree = ast.parse(read(INSTALL_PATH))
        defined = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        defined.add(target.id)
        for name in MOVED + ["MissingFieldsError"]:
            self.assertNotIn(name, defined, name)

    def test_install_names_are_the_agent_md_objects(self):
        ins = load_install()
        for name in MOVED + ["MissingFieldsError"]:
            self.assertIs(getattr(ins, name), getattr(agent_md, name), name)


class SourceShapeTest(unittest.TestCase):
    def test_imports_only_standard_library(self):
        tree = ast.parse(read(AGENT_MD_PATH))
        allowed = getattr(sys, "stdlib_module_names", STDLIB_FALLBACK)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "relative import")
                names = [node.module]
            else:
                continue
            for name in names:
                self.assertIn(name.split(".")[0], allowed, name)

    def test_parses_as_python_39(self):
        ast.parse(read(AGENT_MD_PATH), feature_version=(3, 9))


class ListFilesSortedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="mr-test-", dir=helpers._tmp_base())
        self.addCleanup(helpers.rmtree_force, self.tmp)

    def touch(self, *parts):
        path = os.path.join(self.tmp, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("x\n")
        return path

    def test_sorted_with_subfolders(self):
        b = self.touch("b.md")
        a = self.touch("a.md")
        c = self.touch("sub", "c.md")
        d = self.touch("sub", "deeper", "d.md")
        self.assertEqual(agent_md.list_files_sorted(self.tmp), [a, b, c, d])

    def test_hidden_files_and_folders_skipped(self):
        keep = self.touch("keep.md")
        self.touch(".hidden.md")
        self.touch(".git", "config")
        self.touch("sub", ".secret.md")
        self.touch("sub", ".cache", "x.md")
        self.assertEqual(agent_md.list_files_sorted(self.tmp), [keep])

    def test_missing_folder_gives_empty_list(self):
        self.assertEqual(agent_md.list_files_sorted(os.path.join(self.tmp, "nope")), [])


class MissingFieldsTest(unittest.TestCase):
    def test_error_carries_the_label(self):
        with self.assertRaises(agent_md.MissingFieldsError) as ctx:
            agent_md.parse_agent_defaults("---\nmodel: x\n---\n", "demo.md")
        self.assertEqual(ctx.exception.label, "demo.md")
        with self.assertRaises(agent_md.MissingFieldsError) as ctx:
            agent_md.render_agent("no frontmatter\n", "m", "e", "other.md")
        self.assertEqual(ctx.exception.label, "other.md")

    def test_installer_still_prints_the_old_message(self):
        sb = Sandbox("new")
        self.addCleanup(sb.cleanup)
        path = os.path.join(sb.src, "agents", "scout.md")
        text = read(path)
        kept = [ln for ln in text.split("\n") if not ln.startswith("effort:")]
        self.assertNotEqual(kept, text.split("\n"))
        sb.write(path, "\n".join(kept))
        step = sb.run([])
        self.assertEqual(step.code, 1)
        self.assertEqual(
            step.err,
            "Error: <ROOT>/src/agents/scout.md needs both a model: and an effort: line in its frontmatter.\n")


if __name__ == "__main__":
    unittest.main()
