#!/usr/bin/env python3
"""Reads the frontmatter of an agent file, and checks dashboard/agent_fields.json.

Standard library only.

    python3 dashboard/agent_frontmatter.py check
        Validates dashboard/agent_fields.json. Prints ok, or one error per
        line and exits 1.

    python3 dashboard/agent_frontmatter.py read <file>...
        Reads each file's frontmatter. Prints one line per file, "<n>: ok" or
        "<n>: rejected: <error kind>", where n counts the arguments from 1.
        It never prints a file name, a path or any content of a file, so it is
        safe to point at files whose contents must stay private.

The reader takes a strict subset of YAML, with one nested level:

    first line      ---
    last line       --- (a closing fence is required)
    top level       key: value, where key matches [A-Za-z][A-Za-z0-9_]*
    value           plain text, 'single quoted', "double quoted" (with \\", \\\\,
                    \\n and \\t escapes) or a flow list [a, b]
    block list      an empty value, then indented "- item" lines
    block map       an empty value, then indented "key: scalar" lines
    skipped         blank lines and lines that start with #

Anything else is rejected with a line-numbered error that never repeats file
content: any other backslash escape in a double-quoted value, tabs in an
indent, nesting deeper than one level, block scalars (| and >), anchors and
aliases, flow maps, duplicate keys, an unquoted ": " inside a value, unclosed
brackets or quotes, and a missing closing fence. A field the
reader does not know is kept as read, never dropped.

read_frontmatter returns (fields, errors). A value is a string, a list of
strings, a dict of strings, or None for a key with nothing after it. Numbers and
booleans stay strings, because the reader does not interpret them.

read_frontmatter_lines returns (fields, errors, lines), where fields and errors
are what read_frontmatter returns. lines maps a field path to its 1-based line
number, counting the opening fence as line 1, the same count the error messages
use. A top-level field's path is its key ("model"). A key inside a block map
adds a dotted path ("experimental.cacheTtl"). A block list or a flow list gives
only the line of its key. A field the reader dropped because of an error has no
entry.
"""
import json
import os
import re
import sys

FIELDS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_fields.json")

KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
LINE_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*):(?: (.*))?$")

FIELD_TYPES = ("string", "string_or_list", "list", "map", "boolean", "integer", "enum")
DISPLAYS = ("column", "disclosure")
TOP_LEVEL = {"schema_version", "verified_on", "doc_url", "fields"}
ITEM_REQUIRED = {"field", "type", "required", "display", "quote"}
ITEM_OPTIONAL = {"values", "known_keys"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class _Reject(Exception):
    """A rejection of one value, with a content-free kind."""


def _scan_quoted(s, quote):
    """Return (text, rest) for a quoted scalar at the start of s."""
    out = []
    i = 1
    while i < len(s):
        c = s[i]
        if quote == '"' and c == "\\":
            if i + 1 >= len(s):
                break
            nxt = s[i + 1]
            if nxt not in 'nt"\\':
                raise _Reject("unsupported escape")
            out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
            i += 2
            continue
        if c == quote:
            if quote == "'" and s[i + 1:i + 2] == "'":
                out.append("'")
                i += 2
                continue
            return "".join(out), s[i + 1:]
        out.append(c)
        i += 1
    raise _Reject("unclosed quote")


def _after_scalar(rest):
    rest = rest.strip()
    if rest and not rest.startswith("#"):
        raise _Reject("text after a closing quote")


def _parse_scalar(s, inside_flow=False):
    """Parse one scalar, plain or quoted. s is stripped."""
    if s == "":
        return ""
    if s[0] in "\"'":
        text, rest = _scan_quoted(s, s[0])
        if inside_flow:
            if rest.strip():
                raise _Reject("text after a closing quote")
        else:
            _after_scalar(rest)
        return text
    if s[0] in "|>":
        raise _Reject("block scalar")
    if s[0] in "&*":
        raise _Reject("anchor or alias")
    if s[0] == "{":
        raise _Reject("flow map")
    if s[0] == "[":
        raise _Reject("nesting deeper than one level")
    if s[0] == "!":
        raise _Reject("tag")
    if not inside_flow:
        cut = s.find(" #")
        if cut >= 0:
            s = s[:cut].rstrip()
    if ": " in s or s.endswith(":"):
        raise _Reject("unquoted colon in a value")
    if inside_flow and any(ch in s for ch in "[]{}"):
        raise _Reject("nesting deeper than one level")
    return s


def _split_flow(inner):
    """Split the inside of [..] on commas that sit outside quotes."""
    items = []
    cur = []
    quote = None
    # True once the current item holds a character other than whitespace, so a quote
    # opens a quoted item only at its start. Tracked, not re-joined, to stay linear.
    seen = False
    i = 0
    while i < len(inner):
        c = inner[i]
        if quote:
            cur.append(c)
            if quote == '"' and c == "\\" and i + 1 < len(inner):
                cur.append(inner[i + 1])
                i += 2
                continue
            if c == quote:
                if quote == "'" and inner[i + 1:i + 2] == "'":
                    cur.append("'")
                    i += 2
                    continue
                quote = None
        elif c in "\"'" and not seen:
            quote = c
            seen = True
            cur.append(c)
        elif c == ",":
            items.append("".join(cur))
            cur = []
            seen = False
        else:
            cur.append(c)
            if not c.isspace():
                seen = True
        i += 1
    if quote:
        raise _Reject("unclosed quote")
    items.append("".join(cur))
    return items


def _parse_value(s):
    """Parse the text after `key:` or `- `: a scalar or a flow list."""
    if s.startswith("["):
        body = s
        cut = body.rfind("]")
        if cut < 0:
            raise _Reject("unclosed bracket")
        tail = body[cut + 1:].strip()
        if tail and not tail.startswith("#"):
            raise _Reject("text after a closing bracket")
        inner = body[1:cut]
        if inner.strip() == "":
            return []
        parts = _split_flow(inner)
        out = []
        for part in parts:
            part = part.strip()
            if part == "":
                raise _Reject("empty list item")
            out.append(_parse_scalar(part, inside_flow=True))
        return out
    return _parse_scalar(s)


def _indent_of(line):
    body = line.lstrip(" ")
    return len(line) - len(body), body


def read_frontmatter(text):
    """Return (fields, errors). Errors read "line N: <kind>"."""
    fields, errors, _ = read_frontmatter_lines(text)
    return fields, errors


def read_frontmatter_lines(text):
    """Return (fields, errors, lines). lines maps a field path to its 1-based line.

    A nested key has a dotted path, such as "experimental.cacheTtl". A list gives
    the line of its key only. Only a path present in fields has an entry.
    """
    fields = {}
    errors = []
    field_lines = {}
    if not isinstance(text, str):
        return fields, ["line 1: not text"], field_lines
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0].rstrip() != "---":
        return fields, ["line 1: missing opening fence"], field_lines
    close = None
    for n in range(1, len(lines)):
        if lines[n].rstrip() == "---":
            close = n
            break
    if close is None:
        return fields, ["line 1: missing closing fence"], field_lines

    def err(n, kind):
        errors.append("line %d: %s" % (n + 1, kind))

    body = lines[1:close]
    base = 1  # index in `lines` of body[0]
    i = 0

    def skippable(line):
        stripped = line.strip(" ")
        return stripped == "" or stripped.startswith("#")

    while i < len(body):
        line = body[i]
        n = base + i
        if skippable(line):
            i += 1
            continue
        indent, rest = _indent_of(line)
        if "\t" in line[:len(line) - len(line.lstrip(" \t"))]:
            err(n, "tab in an indent")
            i += 1
            continue
        if indent > 0:
            err(n, "unexpected indent")
            i += 1
            continue
        m = LINE_KEY_RE.match(rest.rstrip())
        if not m:
            err(n, "not a key: value line")
            i += 1
            continue
        key = m.group(1)
        raw = (m.group(2) or "").strip()
        has_dup = key in fields
        if has_dup:
            err(n, "duplicate key")
        i += 1
        if raw != "":
            try:
                value = _parse_value(raw)
            except _Reject as exc:
                err(n, str(exc))
                value = None
                failed = True
            else:
                failed = False
            # A continuation line below a non-empty value is not supported.
            while i < len(body) and skippable(body[i]) and body[i].strip(" ") == "":
                i += 1
            if i < len(body) and not skippable(body[i]) and _indent_of(body[i])[0] > 0:
                err(base + i, "unexpected indent")
                while i < len(body) and (skippable(body[i]) or _indent_of(body[i])[0] > 0):
                    i += 1
            if not failed and not has_dup:
                fields[key] = value
                field_lines[key] = n + 1
            continue
        # Empty value: a block list, a block map, or nothing.
        block = []
        while i < len(body):
            nxt = body[i]
            if skippable(nxt):
                i += 1
                continue
            if _indent_of(nxt)[0] == 0 and "\t" not in nxt[:1]:
                break
            block.append((base + i, nxt))
            i += 1
        if not block:
            if not has_dup:
                fields[key] = None
                field_lines[key] = n + 1
            continue
        sub_lines = {}
        value, bad = _parse_block(block, err, sub_lines)
        if not bad and not has_dup:
            fields[key] = value
            field_lines[key] = n + 1
            for sub, sub_n in sub_lines.items():
                field_lines["%s.%s" % (key, sub)] = sub_n
    return fields, errors, field_lines


def _parse_block(block, err, sub_lines=None):
    """Parse the indented lines under an empty value. Returns (value, bad).

    For a block map, sub_lines (when given) gets each nested key's 1-based line.
    """
    first_n, first = block[0]
    if "\t" in first[:len(first) - len(first.lstrip(" \t"))]:
        err(first_n, "tab in an indent")
        return None, True
    width, _ = _indent_of(first)
    is_list = first[width:] == "-" or first[width:].startswith("- ")
    bad = False
    items = []
    mapping = {}
    for n, line in block:
        lead = line[:len(line) - len(line.lstrip(" \t"))]
        if "\t" in lead:
            err(n, "tab in an indent")
            bad = True
            continue
        indent, rest = _indent_of(line)
        rest = rest.rstrip()
        if indent > width:
            err(n, "nesting deeper than one level")
            bad = True
            continue
        if indent < width:
            err(n, "inconsistent indent")
            bad = True
            continue
        if is_list:
            if not (rest == "-" or rest.startswith("- ")):
                err(n, "mixed list and map")
                bad = True
                continue
            item = rest[1:].strip()
            if item == "":
                err(n, "empty list item")
                bad = True
                continue
            try:
                parsed = _parse_scalar(item)
            except _Reject as exc:
                err(n, str(exc))
                bad = True
                continue
            items.append(parsed)
        else:
            if rest == "-" or rest.startswith("- "):
                err(n, "mixed list and map")
                bad = True
                continue
            m = LINE_KEY_RE.match(rest)
            if not m:
                err(n, "not a key: value line")
                bad = True
                continue
            sub, raw = m.group(1), (m.group(2) or "").strip()
            if sub in mapping:
                err(n, "duplicate key")
                bad = True
                continue
            if raw == "":
                mapping[sub] = None
                if sub_lines is not None:
                    sub_lines[sub] = n + 1
                continue
            try:
                mapping[sub] = _parse_scalar(raw)
            except _Reject as exc:
                err(n, str(exc))
                bad = True
            else:
                if sub_lines is not None:
                    sub_lines[sub] = n + 1
    return (items if is_list else mapping), bad


def _nonempty(value):
    return isinstance(value, str) and value.strip() != ""


def _unique_strings(value):
    return (isinstance(value, list) and value and all(_nonempty(v) for v in value)
            and len(set(value)) == len(value))


def check_fields(data):
    """Strict check of the agent_fields.json document. Returns a list of errors."""
    errors = []
    if not isinstance(data, dict):
        return ["top level must be an object"]
    for key in sorted(TOP_LEVEL - set(data)):
        errors.append("missing field %s" % key)
    for key in sorted(set(data) - TOP_LEVEL):
        errors.append("unknown field %s" % key)
    if "schema_version" in data:
        version = data["schema_version"]
        if not (isinstance(version, int) and not isinstance(version, bool) and version == 1):
            errors.append("schema_version must be the integer 1")
    if "verified_on" in data:
        ver = data["verified_on"]
        if not isinstance(ver, dict) or set(ver) != {"claude_version", "date"}:
            errors.append("verified_on must be an object with claude_version and date")
        else:
            if not _nonempty(ver["claude_version"]):
                errors.append("verified_on claude_version must be a non-empty string")
            if not (isinstance(ver["date"], str) and DATE_RE.match(ver["date"])):
                errors.append("verified_on date must look like 2026-10-29")
    if "doc_url" in data:
        url = data["doc_url"]
        if not (isinstance(url, str) and url.startswith("https://") and len(url) > 8):
            errors.append("doc_url must be an https link")
    if "fields" in data:
        fields = data["fields"]
        if not (isinstance(fields, list) and fields):
            errors.append("fields must be a non-empty list")
        else:
            seen = set()
            for idx, item in enumerate(fields):
                errors.extend("fields[%d]: %s" % (idx, e) for e in _check_item(item, seen))
    return errors


def _check_item(item, seen):
    errors = []
    if not isinstance(item, dict):
        return ["must be an object"]
    for key in sorted(ITEM_REQUIRED - set(item)):
        errors.append("missing field %s" % key)
    for key in sorted(set(item) - ITEM_REQUIRED - ITEM_OPTIONAL):
        errors.append("unknown field %s" % key)
    name = item.get("field")
    if "field" in item:
        if not (isinstance(name, str) and KEY_RE.match(name)):
            errors.append("field must match [A-Za-z][A-Za-z0-9_]*")
        elif name in seen:
            errors.append("field %s repeats" % name)
        else:
            seen.add(name)
    ftype = item.get("type")
    if "type" in item and not (isinstance(ftype, str) and ftype in FIELD_TYPES):
        errors.append("type must be one of %s" % ", ".join(FIELD_TYPES))
    if "required" in item and not isinstance(item["required"], bool):
        errors.append("required must be true or false")
    if "display" in item and not (isinstance(item["display"], str)
                                  and item["display"] in DISPLAYS):
        errors.append("display must be one of %s" % ", ".join(DISPLAYS))
    if "quote" in item and not _nonempty(item["quote"]):
        errors.append("quote must be a non-empty string")
    if "values" in item:
        if ftype != "enum":
            errors.append("values is only for type enum")
        elif not _unique_strings(item["values"]):
            errors.append("values must be a non-empty list of unique non-empty strings")
    elif ftype == "enum":
        errors.append("type enum needs values")
    if "known_keys" in item:
        if ftype != "map":
            errors.append("known_keys is only for type map")
        elif not _unique_strings(item["known_keys"]):
            errors.append("known_keys must be a non-empty list of unique non-empty strings")
    return errors


def _kind(error):
    return error.split(": ", 1)[1] if ": " in error else error


def _cmd_check():
    try:
        with open(FIELDS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        print("cannot read %s: %s" % (FIELDS_PATH, exc.__class__.__name__))
        return 1
    errors = check_fields(data)
    if errors:
        for e in errors:
            print(e)
        return 1
    print("ok")
    return 0


def _cmd_read(paths):
    for n, path in enumerate(paths, 1):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except UnicodeDecodeError:
            print("%d: rejected: not utf-8" % n)
            continue
        except OSError:
            print("%d: rejected: unreadable" % n)
            continue
        _, errors = read_frontmatter(text)
        if errors:
            kinds = []
            for e in errors:
                if _kind(e) not in kinds:
                    kinds.append(_kind(e))
            print("%d: rejected: %s" % (n, ", ".join(kinds)))
        else:
            print("%d: ok" % n)
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] == "check":
        return _cmd_check()
    if len(argv) >= 3 and argv[1] == "read":
        return _cmd_read(argv[2:])
    print("usage: agent_frontmatter.py check | read <file>...")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
