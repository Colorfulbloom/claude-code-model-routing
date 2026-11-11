"""Masked diffs of settings bytes, and the keys that differ between two files.

Masking is span-aware (m6-build.md section 3.9). Both sides are masked as whole texts
before any line is compared, so the diff never sees a secret. ``json_edit.mask_text``
finds the value span of every secret-looking name or value with the JSON parser. A
secret on a context line, a value that spans lines and a line that holds part of a
secret all come out as ``"hidden"``, and each replacement keeps the line breaks its span
held, so the line numbers stay true.

``mask_text`` needs text the strict parser accepts. A file another program broke, or one
with a byte order mark, doesn't parse, so it takes ``mask_loose`` instead. That mask
hides every line that holds a secret word, prefix or shape, and the lines nested below
it. It hides more than it must, never less.

The diff is line based, with three lines of context and the real line numbers. A long
run of equal lines at either end is skipped before the comparison, so a big file costs
one pass, not a quadratic search.
"""

import difflib
import re
from collections.abc import Sequence
from typing import Any, cast

import json_edit
import masking
from models import DiffLine, EditDiff

CONTEXT = 3
MAX_LINES = 4000
MAX_LINE_CHARS = 4096
MAX_MIDDLE = 6000
_BREAKS = re.compile(r"\r\n|\n|\r")
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_WORDS = re.compile(r"[A-Za-z0-9_\-]+")
_HIDDEN_LINE = '"' + masking.HIDDEN + '"'


def mask_loose(text: str) -> str:
    """Mask text the JSON parser would not accept, by line.

    A line is hidden when it holds a secret name word (``KEY``, ``TOKEN`` and the rest,
    case folded, ``-`` read as ``_``), or a string with a secret prefix or shape. A
    hidden line that opens a bracket hides the lines below it until the bracket
    closes. A hidden line keeps its indent and its line break.
    """
    out: list[str] = []
    depth = 0
    for line in _BREAKS.split(text):
        if depth > 0 or _line_is_secret(line):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + _HIDDEN_LINE)
            depth = max(0, depth + _bracket_balance(line))
        else:
            out.append(line)
    return "\n".join(out)


def _line_is_secret(line: str) -> bool:
    if any(masking.is_secret_name(word) for word in _WORDS.findall(line)):
        return True
    items = [*_STRING.findall(line), line.split(":", 1)[-1].strip().strip('",')]
    return any(masking.is_secret_value(item) for item in items)


def _bracket_balance(line: str) -> int:
    plain = _STRING.sub('""', line)
    return sum(plain.count(o) for o in "{[") - sum(plain.count(c) for c in "}]")


def masked_text(raw: bytes | None) -> str:
    """Return the file's text with every secret hidden. None gives an empty text."""
    if raw is None:
        return ""
    try:
        text, _data = json_edit.parse_strict(raw)
    except json_edit.Refused:
        return mask_loose(raw.decode("utf-8", errors="replace"))
    try:
        return json_edit.mask_text(text)
    except (ValueError, RecursionError):  # pragma: no cover - parse_strict walked it
        return mask_loose(text)


def _lines(text: str) -> list[str]:
    pieces = _BREAKS.split(text)
    if pieces and pieces[-1] == "":
        pieces.pop()
    return pieces


def _clip(text: str) -> str:
    return text if len(text) <= MAX_LINE_CHARS else text[:MAX_LINE_CHARS] + "..."


Opcode = tuple[str, int, int, int, int]


def _grouped(codes: Sequence[Opcode], size: int) -> list[list[Opcode]]:
    """Group opcodes into hunks with ``size`` lines of context, as difflib does."""
    items: list[Opcode] = list(codes) or [("equal", 0, 1, 0, 1)]
    if items[0][0] == "equal":
        tag, i1, i2, j1, j2 = items[0]
        items[0] = (tag, max(i1, i2 - size), i2, max(j1, j2 - size), j2)
    if items[-1][0] == "equal":
        tag, i1, i2, j1, j2 = items[-1]
        items[-1] = (tag, i1, min(i2, i1 + size), j1, min(j2, j1 + size))
    span = size + size
    groups: list[list[Opcode]] = []
    group: list[Opcode] = []
    for tag, i1, i2, j1, j2 in items:
        first, second = i1, j1
        if tag == "equal" and i2 - i1 > span:
            group.append((tag, i1, min(i2, i1 + size), j1, min(j2, j1 + size)))
            groups.append(group)
            group = []
            first, second = max(i1, i2 - size), max(j1, j2 - size)
        group.append((tag, first, i2, second, j2))
    if group and not (len(group) == 1 and group[0][0] == "equal"):
        groups.append(group)
    return groups


def diff_lines(before: bytes | None, after: bytes | None) -> list[DiffLine]:
    """Return the masked diff of two files as lines with real line numbers.

    Args:
        before: The file's bytes, or None when it is not there.
        after: The bytes it would hold, or None for a file that goes.

    Returns:
        Context, removed and added lines, hunks joined in order. At most
        ``MAX_LINES`` lines. A line past ``MAX_LINE_CHARS`` characters is cut after
        masking.
    """
    left = _lines(masked_text(before))
    right = _lines(masked_text(after))
    start = 0
    limit = min(len(left), len(right))
    while start < limit and left[start] == right[start]:
        start += 1
    end = 0
    while (
        end < limit - start and left[len(left) - 1 - end] == right[len(right) - 1 - end]
    ):
        end += 1
    mid_left = left[start : len(left) - end]
    mid_right = right[start : len(right) - end]
    if len(mid_left) + len(mid_right) > MAX_MIDDLE:
        codes: list[Opcode] = [("replace", 0, len(mid_left), 0, len(mid_right))]
    else:
        matcher = difflib.SequenceMatcher(None, mid_left, mid_right, autojunk=False)
        codes = list[Opcode](matcher.get_opcodes())
    full: list[Opcode] = []
    if start:
        full.append(("equal", 0, start, 0, start))
    full.extend(
        (t, i1 + start, i2 + start, j1 + start, j2 + start)
        for t, i1, i2, j1, j2 in codes
    )
    if end:
        full.append(("equal", len(left) - end, len(left), len(right) - end, len(right)))
    out: list[DiffLine] = []
    for group in _grouped(full, CONTEXT):
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out.extend(
                    DiffLine(
                        kind="ctx",
                        old_n=i1 + k + 1,
                        new_n=j1 + k + 1,
                        text=_clip(left[i1 + k]),
                    )
                    for k in range(i2 - i1)
                )
                continue
            out.extend(
                DiffLine(kind="del", old_n=k + 1, new_n=None, text=_clip(left[k]))
                for k in range(i1, i2)
            )
            out.extend(
                DiffLine(kind="add", old_n=None, new_n=k + 1, text=_clip(right[k]))
                for k in range(j1, j2)
            )
        if len(out) >= MAX_LINES:
            return out[:MAX_LINES]
    return out


def edit_diff(before: bytes | None, after: bytes | None) -> EditDiff:
    """Return the masked diff as the answer model (``new_file``: no ``before``)."""
    return EditDiff(lines=diff_lines(before, after), new_file=before is None)


def lines_changed(lines: Sequence[DiffLine]) -> int:
    """Count the lines a diff changes: the larger of the added and removed lines."""
    added = sum(1 for line in lines if line.kind == "add")
    removed = sum(1 for line in lines if line.kind == "del")
    return max(added, removed)


def _dict_of(value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _walk_keys(before: object, after: object, prefix: str) -> list[str]:
    left, right = _dict_of(before), _dict_of(after)
    if left is None or right is None:
        return [] if json_edit.same_value(before, after) else [prefix]
    keys: list[str] = []
    for key in sorted(set(left) | set(right)):
        path = f"{prefix}.{key}" if prefix else key
        if key not in left or key not in right:
            keys.append(path)
        else:
            keys.extend(_walk_keys(left[key], right[key], path))
    return keys


def changed_keys(before: bytes | None, after: bytes | None) -> list[str]:
    """List the dotted key paths whose value differs between two files.

    A file that doesn't parse counts as no keys, so an unparsed side gives an empty
    list. A key name that looks like a secret shows as hidden. An array counts as one
    value.
    """

    def parse(raw: bytes | None) -> dict[str, Any]:
        if raw is None:
            return {}
        try:
            return json_edit.parse_strict(raw)[1]
        except json_edit.Refused:
            raise
        except RecursionError:  # pragma: no cover - parse_strict handles depth
            raise json_edit.Refused("unparsed") from None

    try:
        keys = _walk_keys(parse(before), parse(after), "")
    except json_edit.Refused:
        return []
    return [str(masking.mask_value(key)) for key in keys if key][:50]


def touches(keys: Sequence[str], key_path: Sequence[str]) -> bool:
    """True when any changed key is the edited key, inside it or around it."""
    edited = ".".join(key_path)
    return any(
        key == edited or edited.startswith(key + ".") or key.startswith(edited + ".")
        for key in keys
    )


__all__ = [
    "changed_keys",
    "diff_lines",
    "edit_diff",
    "lines_changed",
    "mask_loose",
    "masked_text",
    "touches",
]
