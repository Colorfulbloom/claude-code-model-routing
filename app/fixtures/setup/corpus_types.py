# ruff: noqa: TRY003, ANN401, PLR0913
"""Shared types and the block format for the setup corpus (m4-build.md task 2).

A case is written as one text of blocks. A line that starts with ``=== `` opens a file,
and everything up to the next marker is its content, so a reader sees the exact lines
that expected.json points at. ``=== path !nonl`` drops the final newline, and
``=== path -> target`` makes a symlink (the target is relative to the link).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

MARKER = "=== "
NO_NEWLINE = "!nonl"
LINK_ARROW = " -> "


@dataclass(frozen=True)
class Link:
    """A symlink in a case. ``target`` is written as given, relative to the link."""

    target: str


@dataclass
class Case:
    """One world of the corpus.

    Attributes:
        name: The folder name under ``corpus/``.
        files: Relative path to text or ``Link``, in write order.
        session: The content of ``session.json`` (``shell_env`` and friends).
        meta: The content of ``case.json`` (project folder, listed, git_root, plan).
        expected: The expected JSON for a generated case, or None when the case's
            expected.json is written by hand and committed beside its files.
    """

    name: str
    files: dict[str, str | Link]
    session: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] | None = None


DEFAULT_META: dict[str, Any] = {
    "project": "proj",
    "listed": True,
    "git_root": False,
    "plan": "subscription",
}


def parse_blocks(text: str) -> dict[str, str | Link]:
    """Split a block text into files and links, in order.

    Args:
        text: Text whose file sections start with ``=== path``.

    Returns:
        Relative path to content or ``Link``.

    Raises:
        ValueError: A path repeats, or text sits before the first marker.
    """
    files: dict[str, str | Link] = {}
    current: str | None = None
    nonl = False
    buf: list[str] = []

    def close() -> None:
        if current is None:
            return
        body = "".join(buf)
        if nonl and body.endswith("\n"):
            body = body[:-1]
        files[current] = body

    for line in text.splitlines(keepends=True):
        if line.startswith(MARKER):
            close()
            head = line[len(MARKER) :].rstrip("\n")
            nonl = head.endswith(" " + NO_NEWLINE)
            if nonl:
                head = head[: -len(NO_NEWLINE) - 1]
            if LINK_ARROW in head:
                path, target = head.split(LINK_ARROW, 1)
                if path in files:
                    raise ValueError(f"repeated path {path}")
                files[path] = Link(target)
                current = None
                buf = []
                continue
            if head in files:
                raise ValueError(f"repeated path {head}")
            current = head
            buf = []
        elif current is not None:
            buf.append(line)
        elif line.strip():
            raise ValueError("text before the first marker")
    close()
    return files


def dump_json(data: Any) -> str:
    """Return the corpus's JSON text: sorted keys, two-space indent, final newline."""
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def make_case(
    name: str,
    blocks: str,
    *,
    meta: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
    extra: dict[str, str | Link] | None = None,
    expected: dict[str, Any] | None = None,
) -> Case:
    """Build a case from a block text, with defaults for session and meta."""
    files = parse_blocks(blocks)
    if extra:
        files.update(extra)
    return Case(
        name=name,
        files=files,
        session=session if session is not None else {"shell_env": {}},
        meta={**DEFAULT_META, **(meta or {})},
        expected=expected,
    )
