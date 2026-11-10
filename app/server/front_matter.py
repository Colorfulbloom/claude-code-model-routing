"""Read the front matter of a skill, command or rules file (m4-build.md task 7).

Only the block between the two ``---`` fences is parsed. The body is never looked at.
The block goes through ``ruamel.yaml`` in safe mode, because the docs write SKILL.md
fields (``allowed-tools``, ``argument-hint``) that the old strict agent reader rejects
(m4-build.md section 16, "Task 1 results"). A repeated key keeps its first value.

``parse`` never raises. A file with no opening fence has no front matter and is not an
error, since SKILL.md, command and rules front matter is optional. An opening fence with
no closing one, a block YAML rejects and a block that is not a mapping are ``invalid``,
and ``error_line`` says where (the first line of the scalar or flow that failed, else
the line YAML stopped on, in file lines with the opening fence as line 1).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

import agent_md

State = Literal["none", "ok", "invalid"]

# A top-level key at column 0: bare, "double quoted" or 'single quoted'.
_KEY_LINE = re.compile(
    r"""^(?:"(?P<dq>[^"]+)"|'(?P<sq>[^']+)'|(?P<bare>[^\s#:'"\-?\[\]{},&*!|>%@`][^:]*?))"""
    r"""\s*:(?:\s|$)"""
)


@dataclass
class FrontMatter:
    """What one file's front matter says.

    Attributes:
        state: ``none`` with no opening fence, ``ok`` when the block parsed as a
            mapping (or is empty), ``invalid`` otherwise.
        data: The parsed mapping, keys as text. Empty unless ``ok``.
        lines: Top-level key to the file line it starts on (the opening fence is line
            1). Found by scanning the block, so it is also set when the block is
            ``invalid``.
        error_line: For ``invalid``, the file line of the problem.
    """

    state: State = "none"
    data: dict[str, object] = field(default_factory=dict[str, object])
    lines: dict[str, int] = field(default_factory=dict[str, int])
    error_line: int | None = None


def _key_lines(block: list[str], first_line: int) -> dict[str, int]:
    """Map each top-level key to the first line it sits on."""
    found: dict[str, int] = {}
    for offset, raw in enumerate(block):
        text = agent_md.split_line(raw)[0]
        if not text or text[0] in " \t":
            continue
        match = _KEY_LINE.match(text)
        if match is None:
            continue
        key = match.group("dq") or match.group("sq") or match.group("bare")
        found.setdefault(str(key).strip(), first_line + offset)
    return found


def _load(block_text: str) -> object:
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = True
    loaded: object = yaml.load(block_text)  # pyright: ignore[reportUnknownMemberType]
    return loaded


def _error_line(exc: YAMLError, first_line: int) -> int:
    """Return the file line a YAML error names, or the first front matter line."""
    for name in ("context_mark", "problem_mark"):
        mark: Any = getattr(exc, name, None)
        number = getattr(mark, "line", None)
        if isinstance(number, int):
            return first_line + number
    return first_line


def parse(text: str) -> FrontMatter:
    """Parse the front matter of a file's text. The body is never kept."""
    lines = agent_md.LINE_RE.findall(text)
    if not lines or agent_md.split_line(lines[0])[0] != "---":
        return FrontMatter()
    span = agent_md.frontmatter_span(lines)
    if span is None:
        return FrontMatter(state="invalid", error_line=1)
    first_line = span[0] + 1
    block = lines[span[0] : span[1]]
    positions = _key_lines(block, first_line)
    try:
        loaded = _load("".join(block))
    except (YAMLError, ValueError, RecursionError, TypeError) as exc:
        line = (
            _error_line(exc, first_line) if isinstance(exc, YAMLError) else first_line
        )
        return FrontMatter(state="invalid", lines=positions, error_line=line)
    if loaded is None:
        return FrontMatter(state="ok", lines=positions)
    if not isinstance(loaded, dict):
        return FrontMatter(state="invalid", lines=positions, error_line=first_line)
    mapping = cast("Mapping[object, object]", loaded)
    return FrontMatter(
        state="ok",
        data={str(key): value for key, value in mapping.items()},
        lines=positions,
    )
