"""Find where things sit in a JSON text, without keeping any value.

``collect.json_key_lines`` skips arrays, and the hooks part needs the line of a handler
that is an array element. ``index`` gives the line of every object key and array
element below one key path. ``Cursor`` is the small scanner under it, and the masked
``.claude.json`` reader uses it too, to step over keys it does not keep.

Call both only on text ``json.loads`` already accepted. Neither returns a value from the
text, only lines and positions, so a caller that reads a value does so on its own and
decides what to keep.
"""

import json
import re
from typing import cast

PathKey = str | int
LinePath = tuple[PathKey, ...]

_WHITE = " \t\r\n"
_TOKEN = re.compile(r'["{}\[\]]')
_SCALAR = re.compile(r"[^\s,\]}]+")
MAX_DEPTH = 64


class Cursor:
    """A position-based scanner over validated JSON text."""

    def __init__(self, text: str) -> None:
        """Start at the top of the text. Nothing is parsed yet."""
        self.text = text
        self._decoder = json.JSONDecoder()
        self._mark = 0
        self._line = 1

    def ws(self, i: int) -> int:
        """Return the first position at or after ``i`` that is not white space."""
        text, size = self.text, len(self.text)
        while i < size and text[i] in _WHITE:
            i += 1
        return i

    def line(self, pos: int) -> int:
        """Return the 1-based line of a position.

        Positions that only grow cost one pass over the text in all. A position before
        the last one starts the count again.
        """
        if pos < self._mark:
            self._mark, self._line = 0, 1
        self._line += self.text.count("\n", self._mark, pos)
        self._mark = pos
        return self._line

    def string(self, i: int) -> tuple[str, int]:
        """Decode the string at ``i`` and return it with the position after it."""
        value, end = cast("tuple[str, int]", self._decoder.raw_decode(self.text, i))
        return value, end

    def decode(self, i: int) -> tuple[object, int]:
        """Decode the one value at ``i`` and return it with the position after it."""
        value, end = cast("tuple[object, int]", self._decoder.raw_decode(self.text, i))
        return value, end

    def skip(self, i: int) -> int:
        """Return the position after the value at ``i``. A container is not decoded."""
        text = self.text
        ch = text[i]
        if ch == '"':
            return self.string(i)[1]
        if ch not in "{[":
            found = _SCALAR.match(text, i)
            return found.end() if found else i + 1
        depth, pos = 0, i
        while True:
            token = _TOKEN.search(text, pos)
            if token is None:
                return len(text)
            mark = token.group()
            if mark == '"':
                pos = self.string(token.start())[1]
                continue
            depth += 1 if mark in "{[" else -1
            pos = token.end()
            if depth == 0:
                return pos


class _Indexer:
    def __init__(self, text: str) -> None:
        self.cur = Cursor(text)
        self.text = text
        self.found: dict[LinePath, int] = {}

    def _drop(self, path: LinePath) -> None:
        size = len(path)
        for other in [k for k in self.found if k[:size] == path]:
            del self.found[other]

    def value(self, i: int, path: LinePath, prefix: tuple[str, ...], depth: int) -> int:
        ch = self.text[i]
        if depth > MAX_DEPTH or ch not in "{[":
            return self.cur.skip(i)
        if ch == "{":
            return self.object(i, path, prefix, depth)
        if prefix:  # arrays are not entered on the way to the prefix
            return self.cur.skip(i)
        return self.array(i, path, depth)

    def object(
        self, i: int, path: LinePath, prefix: tuple[str, ...], depth: int
    ) -> int:
        cur, text = self.cur, self.text
        i = cur.ws(i + 1)
        if text[i] == "}":
            return i + 1
        seen: set[str] = set()
        while True:
            at = i
            key, i = cur.string(i)
            i = cur.ws(cur.ws(i) + 1)  # past the colon
            child = (*path, key)
            if not prefix or (key == prefix[0] and len(prefix) == 1):
                if key in seen:
                    self._drop(child)
                self.found[child] = cur.line(at)
            seen.add(key)
            if not prefix:
                i = cur.ws(self.value(i, child, (), depth + 1))
            elif key == prefix[0]:
                i = cur.ws(self.value(i, child, prefix[1:], depth + 1))
            else:
                i = cur.ws(cur.skip(i))
            if text[i] == ",":
                i = cur.ws(i + 1)
                continue
            return i + 1

    def array(self, i: int, path: LinePath, depth: int) -> int:
        cur, text = self.cur, self.text
        i = cur.ws(i + 1)
        if text[i] == "]":
            return i + 1
        index = 0
        while True:
            child = (*path, index)
            self.found[child] = cur.line(i)
            i = cur.ws(self.value(i, child, (), depth + 1))
            index += 1
            if text[i] == ",":
                i = cur.ws(i + 1)
                continue
            return i + 1


def index(text: str, prefix: tuple[str, ...] = ()) -> dict[LinePath, int]:
    """Return the line of every key and array element at or below ``prefix``.

    Args:
        text: JSON text that ``json.loads`` accepted.
        prefix: A key path from the top object. Only objects lead to it. With ``()``
            every key and element of the text is listed.

    Returns:
        ``{path: 1-based line}``. A path is the keys and array indexes from the top
        (``("hooks", "PreToolUse", 0, "hooks", 1)``). The prefix key itself is listed.
        Text the scanner cannot follow gives what it found so far, never an error.
    """
    walker = _Indexer(text)
    try:
        start = walker.cur.ws(0)
        if start < len(text) and text[start] in "{[":
            walker.value(start, (), prefix, 0)
    except (ValueError, IndexError, RecursionError):
        return walker.found
    return walker.found
