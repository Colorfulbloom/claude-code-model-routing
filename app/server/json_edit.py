"""Pure JSON edits for settings files: find a value's bytes, splice, mask, diff.

Ported from ``dashboard/json_edit.py`` (m6-build.md section 4.1). A write must never
rebuild a whole file. This module finds the byte span of one value, replaces only that
span (``replace_value``), adds a missing key with any missing parents inside one span
(``insert_value``), or cuts one key out of an object (``remove_key``). Each edit is
prefix, span, suffix, and every byte outside the span stays put. One oracle checks the
result before the bytes go back. ``new_file`` builds the bytes of a brand-new file. The
module also masks secret-looking values in text, so a diff never shows what the read
side hides. ``structured_diff`` accepts None as the before text, for a file that does
not exist yet.

There are no array functions here. Array edits wait for M7.

The module opens no file, writes nothing and keeps no state. Callers pass bytes or text
in and get bytes or text back. The only change from the old module is the masking
rules, which come from ``masking`` (the 26-07 rules) instead of ``collect``.
"""

# ruff: noqa: PLR0912, PLR0913, PLR0915, PLR0917, N818 - ported unchanged, so the old
# tests and the old behaviour carry over. The byte arithmetic keeps its branch and
# argument counts, and ``Refused`` keeps the name the old callers catch.

import copy
import difflib
import json
import json.decoder
import re
from collections.abc import Callable, Generator
from typing import Any, cast

import masking

# typeshed has no ``json.decoder.scanstring``, but the module has one at run time.
_SCANSTRING = cast(
    "Callable[[str, int], tuple[str, int]]", vars(json.decoder)["scanstring"]
)

KeyPath = tuple[str | int, ...]
Event = tuple[KeyPath, str | None, int, int]
_Walker = Generator[Event, None, int]

_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")
_JSON_SPACE = " \t\n\r"
_CONTEXT = 3


class Refused(ValueError):
    """An edit that must not happen.

    ``code`` is ``unparsed``, ``key_missing``, ``oracle_failed``, ``key_present``
    (insert found the key, so the caller should replace), ``parent_not_object`` (a
    parent on the path exists but is not an object) or ``repeated_key`` (remove found
    the key more than once in one object).
    """

    def __init__(self, code: str, message: str | None = None) -> None:
        """Keep the code, and a message that defaults to it."""
        super().__init__(message or code)
        self.code = code


# Parsing


def parse_strict(raw: bytes | bytearray) -> tuple[str, dict[str, Any]]:
    """Return (text, data) for bytes that are strict UTF-8 and a JSON object.

    Anything ``json.loads`` rejects is refused, so comments, trailing commas and a
    byte order mark all raise ``Refused("unparsed")``. So does a top level that is
    not an object.

    Args:
        raw: The file's bytes.

    Returns:
        The decoded text and the parsed object.

    Raises:
        Refused: ``unparsed``.
    """
    if not isinstance(raw, (bytes, bytearray)):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise Refused("unparsed")
    try:
        text = bytes(raw).decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise Refused("unparsed")  # noqa: TRY301
        for _ in _walk(text):
            pass
    except Refused:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refused("unparsed") from None
    return text, cast("dict[str, Any]", data)


# Span walker


def _walk(text: str) -> Generator[Event, None, None]:
    """Yield (path, name, start, end) for every value, repeated keys included.

    Offsets are str offsets. A parent comes after its children. The name of an array
    item is the name the array sits under, as the read side masks it. Call it only on
    text ``json.loads`` accepted.
    """
    decoder = json.JSONDecoder()
    scanstring = _SCANSTRING

    def skip(i: int) -> int:
        while i < len(text) and text[i] in _JSON_SPACE:
            i += 1
        return i

    def obj(i: int, path: KeyPath) -> _Walker:
        i = skip(i + 1)
        if text[i] == "}":
            return i + 1
        while True:
            key, i = scanstring(text, i + 1)
            i = skip(skip(i) + 1)  # past the colon
            i = skip((yield from value(i, (*path, key), key)))
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    def arr(i: int, path: KeyPath, name: str | None) -> _Walker:
        i = skip(i + 1)
        if text[i] == "]":
            return i + 1
        index = 0
        while True:
            i = skip((yield from value(i, (*path, index), name)))
            index += 1
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    def value(i: int, path: KeyPath, name: str | None) -> _Walker:
        ch = text[i]
        if ch == "{":
            end = yield from obj(i, path)
        elif ch == "[":
            end = yield from arr(i, path, name)
        elif ch == '"':
            end = scanstring(text, i + 1)[1]
        else:
            end = decoder.raw_decode(text, i)[1]
        yield (path, name, i, end)
        return end

    yield from value(skip(0), (), None)


def _spans(raw: bytes) -> tuple[str, list[Event]]:
    text, _ = parse_strict(raw)
    try:
        return text, list(_walk(text))
    except RecursionError:
        raise Refused("unparsed") from None


def value_span(raw: bytes, key_path: KeyPath) -> tuple[int, int]:
    """Return (start, end) byte offsets of the value at ``key_path`` in ``raw``.

    ``key_path`` is a tuple of str (object key) and int (array index). At each level
    the last occurrence of a repeated key wins, as ``json.loads`` does.

    Raises:
        Refused: ``unparsed`` or ``key_missing``.
    """
    text, events = _spans(raw)
    start, end = events[-1][2], events[-1][3]  # the top level value comes last
    path: KeyPath = ()
    for step in key_path:
        # a float step (1.0) would match the int 1 in the event paths, so it is refused
        if isinstance(step, bool) or not isinstance(step, (str, int)):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise Refused("key_missing")
        opener = "{" if isinstance(step, str) else "["
        if text[start] != opener:
            raise Refused("key_missing")
        path = (*path, step)
        found = [
            ev for ev in events if ev[0] == path and start < ev[2] and ev[3] <= end
        ]
        if not found:
            raise Refused("key_missing")
        last = max(found, key=lambda ev: ev[2])
        start, end = last[2], last[3]
    return (len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")))


# Replace


def _same(a: object, b: object) -> bool:
    """Strict equality: same types, and a NaN never equals a NaN."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        left = cast("dict[str, object]", a)
        right = cast("dict[str, object]", b)
        return left.keys() == right.keys() and all(
            _same(left[k], right[k]) for k in left
        )
    if isinstance(a, list):
        items = cast("list[object]", a)
        others = cast("list[object]", b)
        return len(items) == len(others) and all(
            _same(x, y) for x, y in zip(items, others, strict=True)
        )
    return a == b


def same_value(a: object, b: object) -> bool:
    """Strict equality of two parsed JSON values (see ``_same``)."""
    return _same(a, b)


def _oracle(
    old_raw: bytes,
    new_raw: bytes,
    start: int,
    end: int,
    key_path: KeyPath,
    value: object,
    edit: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Raise ``Refused("oracle_failed")`` unless new_raw is old_raw, one span changed.

    Without ``edit``, the expected data is the old data with the value at ``key_path``
    replaced (a strict walk). With ``edit``, a function that mutates the expected parsed
    copy, so insert and remove share the same prefix, tail and equality checks.
    """
    try:
        tail = len(old_raw) - end
        if new_raw[:start] != old_raw[:start]:
            raise Refused("oracle_failed")  # noqa: TRY301
        if tail < 0 or len(new_raw) < start + tail:
            raise Refused("oracle_failed")  # noqa: TRY301
        if new_raw[len(new_raw) - tail :] != old_raw[end:]:
            raise Refused("oracle_failed")  # noqa: TRY301
        expected: Any = copy.deepcopy(json.loads(bytes(old_raw).decode("utf-8")))
        if edit is not None:
            edit(expected)
        elif key_path:
            node: Any = expected
            for step in key_path[:-1]:
                node = node[step]
            node[key_path[-1]] = copy.deepcopy(value)
        else:
            expected = copy.deepcopy(value)
        if not _same(json.loads(bytes(new_raw).decode("utf-8")), expected):
            raise Refused("oracle_failed")  # noqa: TRY301
    except Refused:
        raise
    except Exception:  # noqa: BLE001 - any surprise in the check is a failed check
        raise Refused("oracle_failed") from None


def replace_value(raw: bytes, key_path: KeyPath, value: object) -> bytes:
    """Return ``raw`` with only the value at ``key_path`` set to ``json.dumps(value)``.

    Raises:
        Refused: ``unparsed``, ``key_missing`` or ``oracle_failed``.
    """
    start, end = value_span(raw, key_path)
    try:
        span = json.dumps(value).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise Refused("oracle_failed") from None
    new_raw = bytes(raw[:start]) + span + bytes(raw[end:])
    _oracle(bytes(raw), new_raw, start, end, key_path, value)
    return new_raw


# Insert and remove


def _skip(text: str, i: int) -> int:
    while i < len(text) and text[i] in _JSON_SPACE:
        i += 1
    return i


def _bytes_at(text: str, i: int) -> int:
    return len(text[:i].encode("utf-8"))


def _members(text: str, start: int) -> list[tuple[str, int, int, int, int]]:
    """Return (key, key_start, key_end, value_start, value_end) per object member.

    Offsets are str offsets and repeated keys are all listed, in file order. Call it
    only on text ``json.loads`` accepted, with ``text[start] == "{"``.
    """
    decoder = json.JSONDecoder()
    scanstring = _SCANSTRING
    i = _skip(text, start + 1)
    found: list[tuple[str, int, int, int, int]] = []
    if text[i] == "}":
        return found
    while True:
        key_start = i
        key, key_end = scanstring(text, i + 1)
        i = _skip(text, _skip(text, key_end) + 1)  # past the colon
        value_end = decoder.raw_decode(text, i)[1]
        found.append((key, key_start, key_end, i, value_end))
        i = _skip(text, value_end)
        if text[i] == ",":
            i = _skip(text, i + 1)
            continue
        return found


def _render(
    chain: tuple[str, ...],
    value: object,
    multi: bool,
    base: str,
    unit: str,
    nl: str,
    sep: str,
) -> str:
    """Text for value wrapped in one object per key in chain."""
    if not chain:
        return json.dumps(value)
    key = json.dumps(chain[0])
    if not multi:
        return (
            "{"
            + key
            + sep
            + _render(chain[1:], value, False, base, unit, nl, sep)
            + "}"
        )
    inner = base + unit
    return (
        "{"
        + nl
        + inner
        + key
        + sep
        + _render(chain[1:], value, True, inner, unit, nl, sep)
        + nl
        + base
        + "}"
    )


def _check_path(key_path: KeyPath) -> tuple[str, ...]:
    if not isinstance(key_path, tuple) or not key_path:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise Refused("key_missing")
    names: list[str] = []
    for step in key_path:
        if not isinstance(step, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise Refused("key_missing")
        names.append(step)
    return tuple(names)


def insert_value(raw: bytes, key_path: KeyPath, value: object) -> bytes:
    """Return ``raw`` with ``key_path`` added as ``json.dumps(value)``.

    Missing parents are made.

    Refuses ``key_present`` when the final key exists (even as null) and
    ``parent_not_object`` when a parent exists but is not an object. The whole
    addition is one span, so every other byte stays as written.

    Raises:
        Refused: ``unparsed``, ``key_missing``, ``key_present``, ``parent_not_object``
            or ``oracle_failed``.
    """
    names = _check_path(key_path)
    text, _ = parse_strict(raw)
    obj_start = _skip(text, 0)
    missing_from: int | None = None
    for index, step in enumerate(names[:-1]):
        found = [m for m in _members(text, obj_start) if m[0] == step]
        if not found:
            missing_from = index
            break
        value_start = found[-1][3]
        if text[value_start] != "{":
            raise Refused("parent_not_object")
        obj_start = value_start
    members = _members(text, obj_start)
    if missing_from is None:
        if any(m[0] == names[-1] for m in members):
            raise Refused("key_present")
        remaining = names[-1:]
    else:
        remaining = names[missing_from:]
    try:
        key_text = json.dumps(remaining[0])
        if members:
            last = members[-1]
            sep = text[last[2] : last[3]]
            before = members[-2][4] if len(members) > 1 else obj_start + 1
            gap = text[before : last[1]]
            lead = gap[gap.rfind(",") + 1 :]
            multi = bool(_LINE_BREAK_RE.search(lead))
            nl = member_indent = ""
            unit = "  "
            if multi:
                nl = _LINE_BREAK_RE.findall(lead)[-1]
                member_indent = _LINE_BREAK_RE.split(lead)[-1]
                close = _skip(text, last[4])
                tail_gap = text[last[4] : close]
                if _LINE_BREAK_RE.search(tail_gap):
                    close_indent = _LINE_BREAK_RE.split(tail_gap)[-1]
                    if member_indent.startswith(close_indent) and len(
                        member_indent
                    ) > len(close_indent):
                        unit = member_indent[len(close_indent) :]
            body = _render(remaining[1:], value, multi, member_indent, unit, nl, sep)
            add = "," + lead + key_text + sep + body
            start = end = _bytes_at(text, last[4])
        else:
            top = _members(text, _skip(text, 0))
            sep = text[top[0][2] : top[0][3]] if top else ": "
            close = _skip(text, obj_start + 1)
            first_break = _LINE_BREAK_RE.search(text)
            if first_break is None:
                add = (
                    key_text
                    + sep
                    + _render(remaining[1:], value, False, "", "  ", "", sep)
                )
            else:
                nl = first_break.group(0)
                breaks = list(_LINE_BREAK_RE.finditer(text[:obj_start]))
                line_start = breaks[-1].end() if breaks else 0
                line = text[line_start:obj_start]
                base = line[: len(line) - len(line.lstrip(" \t"))]
                indent = base + "  "
                add = (
                    nl
                    + indent
                    + key_text
                    + sep
                    + _render(remaining[1:], value, True, indent, "  ", nl, sep)
                    + nl
                    + base
                )
            start = _bytes_at(text, obj_start + 1)
            end = _bytes_at(text, close)
        span = add.encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise Refused("oracle_failed") from None
    old = bytes(raw)
    new_raw = old[:start] + span + old[end:]

    def edit(expected: dict[str, Any]) -> None:
        node: Any = expected
        for step in names[:-1]:
            if step not in node:
                node[step] = {}
            node = node[step]
        node[names[-1]] = copy.deepcopy(value)

    _oracle(old, new_raw, start, end, key_path, value, edit=edit)
    return new_raw


def remove_key(raw: bytes, key_path: KeyPath) -> bytes:
    """Return ``raw`` with the key at ``key_path`` cut out of its object.

    Parents are strict: a missing or non-object parent is ``key_missing``. A final key
    that appears more than once in its object is ``repeated_key``. Removing the only
    member of a nested object leaves ``{}``, and of the file leaves its braces on their
    own lines.

    Raises:
        Refused: ``unparsed``, ``key_missing``, ``repeated_key`` or ``oracle_failed``.
    """
    names = _check_path(key_path)
    text, _ = parse_strict(raw)
    obj_start = _skip(text, 0)
    for step in names[:-1]:
        found = [m for m in _members(text, obj_start) if m[0] == step]
        if not found or text[found[-1][3]] != "{":
            raise Refused("key_missing")
        obj_start = found[-1][3]
    members = _members(text, obj_start)
    hits = [i for i, m in enumerate(members) if m[0] == names[-1]]
    if not hits:
        raise Refused("key_missing")
    if len(hits) > 1:
        raise Refused("repeated_key")
    i = hits[0]
    if i < len(members) - 1:
        s_off, e_off = members[i][1], members[i + 1][1]
    elif i > 0:
        s_off, e_off = members[i - 1][4], members[i][4]
    elif obj_start == _skip(
        text, 0
    ):  # the file's last key: the brace keeps its own line
        s_off, e_off = obj_start + 1, members[i][4]
    else:
        s_off, e_off = obj_start + 1, _skip(text, members[i][4])
    start, end = _bytes_at(text, s_off), _bytes_at(text, e_off)
    old = bytes(raw)
    new_raw = old[:start] + old[end:]

    def edit(expected: dict[str, Any]) -> None:
        node: Any = expected
        for step in names[:-1]:
            node = node[step]
        del node[names[-1]]

    _oracle(old, new_raw, start, end, key_path, None, edit=edit)
    return new_raw


def new_file(key_path: KeyPath, value: object) -> bytes:
    """Return the bytes of a new file holding only ``key_path``.

    Two-space indent, LF, a final newline.

    Raises:
        Refused: ``key_missing`` for a bad path or ``oracle_failed``.
    """
    names = _check_path(key_path)
    try:
        data: object = value
        for step in reversed(names):
            data = {step: data}
        raw = (json.dumps(data, indent=2) + "\n").encode("ascii")
        if not _same(json.loads(raw.decode("utf-8")), data):
            raise Refused("oracle_failed")  # noqa: TRY301
    except Refused:
        raise
    except (TypeError, ValueError, RecursionError):
        raise Refused("oracle_failed") from None
    return raw


# Masking


def _args_replacements(text: str, events: list[Event]) -> dict[int, str]:
    """Return {span start: replacement text} for the items of every ``args`` list.

    It follows ``masking.mask_args``. A secret-named flag hides the next item, or the
    part after ``=`` in the flag itself. Only a list that sits directly under an
    ``args`` key counts.
    """
    lists: dict[KeyPath, list[Event]] = {}
    for event in events:
        path, name, _start, _end = event
        if (
            len(path) > 1
            and isinstance(path[-1], int)
            and isinstance(path[-2], str)
            and isinstance(name, str)
            and name.lower() == "args"
        ):
            lists.setdefault(path[:-1], []).append(event)
    found: dict[int, str] = {}
    hidden = '"' + masking.HIDDEN + '"'
    for items in lists.values():
        hide_next = False
        for _path, _name, start, end in sorted(items, key=lambda ev: ev[2]):
            if hide_next:
                found[start] = hidden
                hide_next = False
            elif text[start] == '"':
                flag = json.loads(text[start:end])
                if isinstance(flag, str) and flag.startswith("-"):
                    head, equals, _rest = flag.lstrip("-").partition("=")
                    if masking.is_secret_name(head):
                        if equals:
                            kept = f"{flag.partition('=')[0]}={masking.HIDDEN}"
                            found[start] = json.dumps(kept)
                        else:
                            hide_next = True
    return found


def mask_text(text: str) -> str:
    """Return ``text`` with every secret value's span replaced by ``"hidden"``.

    It follows ``masking.mask_value``: a secret name hides the whole value, whatever
    its type, a string with a secret prefix or shape hides, the password of URL
    userinfo hides, and a secret-named flag in an ``args`` list hides its value. Every
    occurrence of a repeated key is masked. Each replacement keeps the line breaks its
    span held, so line numbers stay true. Call it only on text ``json.loads``
    accepted.
    """
    events = sorted(_walk(text), key=lambda ev: (ev[2], -ev[3]))
    arg_spans = _args_replacements(text, events)
    spans: list[tuple[int, int, str]] = []
    last_end = -1
    hidden = '"' + masking.HIDDEN + '"'
    for _path, name, start, end in events:
        if start < last_end:
            continue  # inside a span already replaced
        replacement: str | None = None
        if masking.is_secret_name(name):
            replacement = hidden
        elif start in arg_spans:
            replacement = arg_spans[start]
        elif text[start] == '"':
            value = json.loads(text[start:end])
            if masking.is_secret_value(value):
                replacement = hidden
            else:
                masked = masking.mask_url(value)
                if masked != value:
                    replacement = json.dumps(masked)
        if replacement is not None:
            spans.append((start, end, replacement))
            last_end = end
    for start, end, replacement in reversed(spans):
        breaks = "".join(_LINE_BREAK_RE.findall(text[start:end]))
        text = text[:start] + replacement + breaks + text[end:]
    return text


# Diff


def _lines(text: str) -> list[str]:
    pieces = _LINE_BREAK_RE.split(text)
    if pieces and pieces[-1] == "":
        pieces.pop()
    return pieces


def structured_diff(
    before_text: str | None, after_text: str | None, file_display: str
) -> dict[str, Any]:
    """Return ``{"file_display", "hunks"}`` for the masked before and after texts.

    ``before_text`` may be None for a new file, and ``after_text`` may be None for a
    file that goes. Each counts as no lines, and ``mask_text`` never sees empty text.
    """
    before = [] if before_text is None else _lines(mask_text(before_text))
    after = [] if after_text is None else _lines(mask_text(after_text))
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    hunks: list[dict[str, Any]] = []
    for group in matcher.get_grouped_opcodes(_CONTEXT):
        lines: list[dict[str, Any]] = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                lines.extend(
                    {
                        "kind": "context",
                        "old_line": i1 + k + 1,
                        "new_line": j1 + k + 1,
                        "text": before[i1 + k],
                    }
                    for k in range(i2 - i1)
                )
                continue
            lines.extend(
                {"kind": "del", "old_line": k + 1, "new_line": None, "text": before[k]}
                for k in range(i1, i2)
            )
            lines.extend(
                {"kind": "add", "old_line": None, "new_line": k + 1, "text": after[k]}
                for k in range(j1, j2)
            )
        hunks.append({"lines": lines})
    return {"file_display": file_display, "hunks": hunks}
