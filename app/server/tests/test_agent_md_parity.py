"""The two agent_md copies give the same output on the same fixtures.

The repo root ``agent_md.py`` (the old app and ``install.py`` use it) and
``app/server/agent_md.py`` (the new app uses it) must not drift before M6 retires the
old one. The root copy is imported by path and only read. Every ``*.md`` under
``tests/fixtures`` feeds both, plus made-up edge texts.

The three install-parity checks of ``tests/test_agent_md.py`` (install.py defines none
of the moved names, install.py's names are the agent_md objects, the installer prints
the old missing-field message) need ``install.py`` and its Sandbox, and the installer
stays in the old app, so they do not come over. The Python 3.9 parse check of the root
copy does, because ``install.py`` ships that file to machines with the system Python.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import port_helpers as helpers

import agent_md as port

ROOT_PATH = helpers.REPO / "agent_md.py"
FIXTURE_FILES = sorted(helpers.FIXTURES.rglob("*.md"))
FIXTURE_DIRS = sorted({p.parent for p in FIXTURE_FILES})
EDGE_TEXTS = {
    "plain": "---\nname: x\nmodel: opus\neffort: high\n---\nbody\n",
    "crlf": "---\r\nname: x\r\nmodel: opus\r\neffort: high\r\n---\r\nbody\r\n",
    "quoted": '---\nname: "q"\nmodel: "opus"\neffort: \'low\'\n---\n',
    "no_frontmatter": "just text\n",
    "missing_effort": "---\nmodel: opus\n---\n",
    "no_trailing_newline": "---\nmodel: a\neffort: b\n---",
    "duplicate_fields": "---\nmodel: a\nmodel: b\neffort: c\neffort: d\n---\n",
    "field_after_close": "---\nmodel: a\n---\neffort: b\n",
    "empty": "",
}


def load_root() -> ModuleType:
    spec = importlib.util.spec_from_file_location("agent_md_root_copy", ROOT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROOT = load_root()


def outcome(module: ModuleType, name: str, *args: Any) -> tuple[str, Any]:
    """Return ``("ok", value)`` or ``("raised", (type name, label or text))``."""
    try:
        return "ok", getattr(module, name)(*args)
    except Exception as err:  # noqa: BLE001 - the error is part of the output
        return "raised", (type(err).__name__, getattr(err, "label", str(err)))


def both(name: str, *args: Any) -> None:
    assert outcome(ROOT, name, *args) == outcome(port, name, *args), name


def test_the_fixture_set_is_not_empty() -> None:
    assert len(FIXTURE_FILES) > 10


def test_the_same_names_are_public() -> None:
    def names(module: ModuleType) -> set[str]:
        return {n for n in vars(module) if not n.startswith("_")}

    # The port adds imports and typing names only; nothing may be missing.
    assert {
        n for n in names(ROOT) if callable(getattr(ROOT, n)) or n.isupper()
    } <= names(port)


@pytest.mark.parametrize(
    "path", FIXTURE_FILES, ids=lambda p: str(p.relative_to(helpers.FIXTURES))
)
def test_each_fixture_file_gives_equal_output(path: Path) -> None:
    both("read_bytes_text", str(path))
    both("frontmatter_name", str(path))
    text = ROOT.read_bytes_text(str(path))
    _same_on_text(text, path.name)


@pytest.mark.parametrize("name", sorted(EDGE_TEXTS))
def test_each_edge_text_gives_equal_output(name: str) -> None:
    _same_on_text(EDGE_TEXTS[name], name)


def _same_on_text(text: str, label: str) -> None:
    lines = ROOT.LINE_RE.findall(text)
    assert lines == port.LINE_RE.findall(text)
    for line in lines:
        both("split_line", line)
    both("frontmatter_span", lines)
    span = ROOT.frontmatter_span(lines)
    assert span == port.frontmatter_span(lines)
    if span:
        both("find_field_lines", lines, span)
    for value in ("a", '"a"', "'a'", " a ", '"', ""):
        both("strip_quotes", value)
    both("parse_agent_defaults", text, label)
    both("render_agent", text, "m-x", "e-y", label)
    both("render_agent", text, "m-x", "e-y")


@pytest.mark.parametrize(
    "folder", FIXTURE_DIRS, ids=lambda p: str(p.relative_to(helpers.FIXTURES))
)
def test_each_fixture_folder_lists_the_same_files(folder: Path) -> None:
    both("find_agent_md_files", str(folder))
    both("list_files_sorted", str(folder))


def test_a_missing_folder_lists_the_same_nothing(tmp_path: Path) -> None:
    both("find_agent_md_files", str(tmp_path / "nope"))
    both("list_files_sorted", str(tmp_path / "nope"))


def test_the_missing_field_error_has_the_same_shape() -> None:
    a = outcome(ROOT, "parse_agent_defaults", "---\nmodel: x\n---\n", "demo.md")
    b = outcome(port, "parse_agent_defaults", "---\nmodel: x\n---\n", "demo.md")
    assert a == b == ("raised", ("MissingFieldsError", "demo.md"))
    assert str(ROOT.MissingFieldsError("z")) == str(port.MissingFieldsError("z"))


def test_the_root_copy_still_parses_as_python_39() -> None:
    ast.parse(ROOT_PATH.read_text(encoding="utf-8"), feature_version=(3, 9))
