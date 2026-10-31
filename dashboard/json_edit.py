"""Pure JSON edits for settings files: find a value's bytes, splice one value, mask, diff.

A write must never rebuild a whole file. This module finds the byte span of one
value, replaces only that span, and checks the result with an oracle before it
hands the bytes back. It also masks secret-looking values in text, so a diff
never shows what collect.py hides. Standard library only, Python 3.9.

The module opens no file, writes nothing and keeps no state. Callers pass bytes
or text in and get bytes or text back.
"""
import copy
import difflib
import json
import json.decoder
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from collect import HIDDEN, is_secret_name, is_secret_value  # noqa: E402

_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")
_JSON_SPACE = " \t\n\r"
_CONTEXT = 3


class Refused(ValueError):
    """An edit that must not happen. .code is unparsed, key_missing or oracle_failed."""

    def __init__(self, code, message=None):
        super().__init__(message or code)
        self.code = code


# Parsing

def parse_strict(raw):
    """Return (text, data) for bytes that are strict UTF-8 and a JSON object.

    Anything json.loads rejects is refused, so comments, trailing commas and a
    byte order mark all raise Refused("unparsed"). So does a top level that is
    not an object.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise Refused("unparsed")
    try:
        text = bytes(raw).decode("utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            raise Refused("unparsed")
        for _ in _walk(text):
            pass
    except Refused:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise Refused("unparsed")
    return text, data


# Span walker

def _walk(text):
    """Yield (path, name, start, end) for every value, repeated keys included.

    Offsets are str offsets. A parent comes after its children. The name of an
    array item is the name the array sits under, as collect.mask treats it.
    Call it only on text json.loads accepted.
    """
    decoder = json.JSONDecoder()
    scanstring = json.decoder.scanstring

    def skip(i):
        while i < len(text) and text[i] in _JSON_SPACE:
            i += 1
        return i

    def obj(i, path):
        i = skip(i + 1)
        if text[i] == "}":
            return i + 1
        while True:
            key, i = scanstring(text, i + 1)
            i = skip(skip(i) + 1)  # past the colon
            i = skip((yield from value(i, path + (key,), key)))
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    def arr(i, path, name):
        i = skip(i + 1)
        if text[i] == "]":
            return i + 1
        index = 0
        while True:
            i = skip((yield from value(i, path + (index,), name)))
            index += 1
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    def value(i, path, name):
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


def _spans(raw):
    text, _ = parse_strict(raw)
    try:
        return text, list(_walk(text))
    except RecursionError:
        raise Refused("unparsed")


def value_span(raw, key_path):
    """Return (start, end) byte offsets of the value at key_path in raw.

    key_path is a tuple of str (object key) and int (array index). At each
    level the last occurrence of a repeated key wins, as json.loads does.
    """
    text, events = _spans(raw)
    start, end = events[-1][2], events[-1][3]  # the top level value comes last
    path = ()
    for step in key_path:
        if isinstance(step, bool) or not isinstance(step, (str, int)):
            raise Refused("key_missing")
        opener = "{" if isinstance(step, str) else "["
        if text[start] != opener:
            raise Refused("key_missing")
        path = path + (step,)
        found = [ev for ev in events
                 if ev[0] == path and start < ev[2] and ev[3] <= end]
        if not found:
            raise Refused("key_missing")
        last = max(found, key=lambda ev: ev[2])
        start, end = last[2], last[3]
    return (len(text[:start].encode("utf-8")), len(text[:end].encode("utf-8")))


# Replace

def _same(a, b):
    """Strict equality: same types, and a NaN never equals a NaN."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _oracle(old_raw, new_raw, start, end, key_path, value):
    """Raise Refused("oracle_failed") unless new_raw is old_raw with one value changed."""
    try:
        tail = len(old_raw) - end
        if new_raw[:start] != old_raw[:start]:
            raise Refused("oracle_failed")
        if tail < 0 or len(new_raw) < start + tail:
            raise Refused("oracle_failed")
        if new_raw[len(new_raw) - tail:] != old_raw[end:]:
            raise Refused("oracle_failed")
        expected = copy.deepcopy(json.loads(bytes(old_raw).decode("utf-8")))
        if key_path:
            node = expected
            for step in key_path[:-1]:
                node = node[step]
            node[key_path[-1]] = copy.deepcopy(value)
        else:
            expected = copy.deepcopy(value)
        if not _same(json.loads(bytes(new_raw).decode("utf-8")), expected):
            raise Refused("oracle_failed")
    except Refused:
        raise
    except Exception:
        raise Refused("oracle_failed")


def replace_value(raw, key_path, value):
    """Return raw with only the value at key_path replaced by json.dumps(value)."""
    start, end = value_span(raw, key_path)
    try:
        span = json.dumps(value).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise Refused("oracle_failed")
    new_raw = bytes(raw[:start]) + span + bytes(raw[end:])
    _oracle(bytes(raw), new_raw, start, end, key_path, value)
    return new_raw


# Masking

def mask_text(text):
    """Return text with every secret value's span replaced by "hidden".

    It follows collect.mask: a secret name hides the whole value, whatever its
    type, and a string with a secret prefix hides. Every occurrence of a
    repeated key is masked. Each replacement keeps the line breaks its span
    held, so line numbers stay true. Call it only on text json.loads accepted.
    """
    events = sorted(_walk(text), key=lambda ev: (ev[2], -ev[3]))
    spans = []
    last_end = -1
    for _path, name, start, end in events:
        if start < last_end:
            continue  # inside a span already replaced
        if is_secret_name(name):
            hide = True
        elif text[start] == '"':
            hide = is_secret_value(json.loads(text[start:end]))
        else:
            hide = False
        if hide:
            spans.append((start, end))
            last_end = end
    for start, end in reversed(spans):
        breaks = "".join(_LINE_BREAK_RE.findall(text[start:end]))
        text = text[:start] + '"' + HIDDEN + '"' + breaks + text[end:]
    return text


# Diff

def _lines(text):
    pieces = _LINE_BREAK_RE.split(text)
    if pieces and pieces[-1] == "":
        pieces.pop()
    return pieces


def structured_diff(before_text, after_text, file_display):
    """Return {"file_display", "hunks"} for the masked before and after texts."""
    before = _lines(mask_text(before_text))
    after = _lines(mask_text(after_text))
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    hunks = []
    for group in matcher.get_grouped_opcodes(_CONTEXT):
        lines = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                for k in range(i2 - i1):
                    lines.append({"kind": "context", "old_line": i1 + k + 1,
                                  "new_line": j1 + k + 1, "text": before[i1 + k]})
                continue
            for k in range(i1, i2):
                lines.append({"kind": "del", "old_line": k + 1,
                              "new_line": None, "text": before[k]})
            for k in range(j1, j2):
                lines.append({"kind": "add", "old_line": None,
                              "new_line": k + 1, "text": after[k]})
        hunks.append({"lines": lines})
    return {"file_display": file_display, "hunks": hunks}
