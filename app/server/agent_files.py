"""Agent files for the setup read side: find them, read them, parse every field.

``collect_agents`` and ``collect_plugins`` both need the agent files of a folder, so the
finding and the parsing sit here. Files are listed and read through ``read_scope`` only.

Parsing. The statuses of an agent (does it load, which model and effort run) come from
the ported strict reader and the resolver, so Live and Review agree with setup. This
module parses the front matter a second time with ``ruamel.yaml`` in safe mode, for
display only (m4-build.md section 16, "Task 1 results"). The strict reader rejects
hyphenated keys, nesting deeper than one level and an unquoted colon, which Claude Code
accepts. ``AgentFile.gap`` is True when the strict reader rejected a file that YAML
parsed, or that YAML rejected too but Claude Code still loads (an unclosed bracket in
a value). Such a file is read line by line, each value as raw text, so it still has
an item.

A file's body is never kept. Only the front matter fields are, each as ``MaskedText``.
"""

import functools
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

import agent_frontmatter
import agent_md
import collect
import command_mask
import masking
import read_scope
import resolve
from models import AgentField, MaskedText, SetupScope, UnreadableFile
from setup_contract import FILE_CAP_BYTES

# Fields Claude Code ignores on an agent that comes from a plugin (research 26-03,
# docs sub-agents "plugin subagents").
PLUGIN_IGNORED_FIELDS = frozenset({"hooks", "mcpServers", "permissionMode"})
MAX_DEPTH = 8
_MAX_COMMAND_DEPTH = 12

# A top-level key at column 0: bare, "double quoted" or 'single quoted'.
_KEY_LINE = re.compile(
    r"""^(?:"(?P<dq>[^"]+)"|'(?P<sq>[^']+)'|(?P<bare>[^\s#:'"\-?\[\]{},&*!|>%@`][^:]*?))"""
    r"""\s*:(?:\s|$)"""
)


@dataclass
class Strict:
    """What the ported strict reader made of one file, for the strict resolver.

    Attributes:
        fields: The reader's fields, masked with ``collect.mask``.
        errors: The reader's errors, empty when it accepted the file.
        lines: Each field path's 1-based line.
    """

    fields: dict[str, Any] = field(default_factory=dict[str, Any])
    errors: list[str] = field(default_factory=list[str])
    lines: dict[str, int] = field(default_factory=dict[str, int])


@dataclass
class AgentFile:
    """One file in an agents folder, read and parsed.

    Attributes:
        layer: ``managed``, ``project``, ``user`` or ``plugin``.
        plugin: The plugin's name for a plugin agent, else None.
        path: The path as found (not resolved).
        rel: The path below its agents folder, in posix form, for sorting.
        display: The display path.
        full_path: The absolute path.
        real_path: A symlink's target, when the file is a symlink.
        code: ``agent_not_md``, ``frontmatter_invalid`` or ``agent_no_name`` when the
            file has no usable name, else None.
        line: The line of the problem named by ``code``, or None.
        name: The agent's name, or None when ``code`` is set.
        has_description: True when ``description`` is a non-empty string.
        name_line: The line of the ``name`` key.
        fields: Every front matter field, masked.
        gap: True when the strict reader rejected a file that YAML parsed.
        strict_line: The line of the strict reader's first error, when ``gap``.
    """

    layer: SetupScope
    plugin: str | None
    path: str
    rel: str
    display: str
    full_path: str
    real_path: str | None = None
    code: str | None = None
    line: int | None = None
    name: str | None = None
    has_description: bool = False
    name_line: int | None = None
    fields: list[AgentField] = field(default_factory=list[AgentField])
    gap: bool = False
    strict_line: int | None = None

    def ignored_fields(self) -> list[str]:
        """Return the names of the fields set here that Claude Code ignores."""
        return [f.name for f in self.fields if f.ignored]


@dataclass
class Found:
    """What ``find`` saw in one or more agent roots.

    Attributes:
        files: Every file found, sorted by root then by ``rel``.
        unreadable: Files and folders that could not be read.
        touched: Folders listed and files read, for the signature.
        strict: The strict reader's answer for each ``.md`` file that was read, by
            path. It is kept here and not on ``AgentFile``, because its values are
            masked by name only and a record dump must stay clean.
    """

    files: list[AgentFile] = field(default_factory=list[AgentFile])
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    touched: list[Path] = field(default_factory=list[Path])
    strict: dict[str, Strict] = field(default_factory=dict[str, Strict])


def agent_item_id(name: str, plugin: str | None = None) -> str:
    """Return an agent's item id: ``agents:<name>``, or ``agents:<plugin>:<name>``.

    A plugin agent is always its own item, even when a file agent shares its name
    (owner, November 9). Names hold no colon, so the two forms never collide.
    """
    return f"agents:{plugin}:{name}" if plugin else f"agents:{name}"


def _scalar_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, default=str)


def _command_value(key: object, item: object, depth: int) -> object:
    """Return one nested entry: ``command`` and ``url`` text are masked here."""
    if isinstance(item, str):
        if key == "command":
            return command_mask.mask_command(item)
        if key == "url":
            return masking.mask_url(item)
    return _commands(item, depth + 1)


def _commands(value: object, depth: int = 0) -> object:
    """Mask the free text of every ``command`` and ``url`` inside a nested value.

    ``masking.mask_value`` hides a value by its name or shape, and a secret inside a
    shell command (``run.sh --api-key sk-...``) has neither, so hook and MCP commands
    nested in a field go through ``command_mask`` too. A value nested deeper than
    ``_MAX_COMMAND_DEPTH`` is hidden whole, because it can't be checked.
    """
    if depth > _MAX_COMMAND_DEPTH:
        return command_mask.HIDDEN
    if isinstance(value, dict):
        table = cast("dict[object, object]", value)
        return {key: _command_value(key, item, depth) for key, item in table.items()}
    if isinstance(value, list):
        return [_commands(item, depth + 1) for item in cast("list[object]", value)]
    return value


def _field(name: str, value: object, line: int | None, ignored: bool) -> AgentField:
    """Return one front matter field with its value masked."""
    if value is None:
        return AgentField(name=name, value=None, line=line, ignored=ignored)
    raw = _scalar_text(value)
    shown = _scalar_text(_commands(masking.mask_value(value, name)))
    return AgentField(
        name=name,
        value=MaskedText(text=shown, masked=shown != raw),
        line=line,
        ignored=ignored,
    )


def front_matter_field(
    name: str, value: object, line: int | None, *, ignored: bool = False
) -> AgentField:
    """Return one front matter field, masked, for a skill's front matter too."""
    return _field(name, value, line, ignored)


def _key_lines(block: list[str], first_line: int) -> dict[str, int]:
    """Map each top-level key to the first line it sits on (the fence is line 1)."""
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


@functools.cache
def _known_order() -> tuple[str, ...]:
    return tuple(resolve.load_agent_fields())


def _name_of(value: object) -> str | None:
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        text = str(value)
    else:
        return None
    return text or None


def _load_yaml(block_text: str) -> object:
    """Load a front matter block in safe mode. A repeated key keeps its first value."""
    yaml = YAML(typ="safe")
    yaml.allow_duplicate_keys = True
    loaded: object = yaml.load(block_text)  # pyright: ignore[reportUnknownMemberType]
    return loaded


def _error_line(exc: YAMLError, first_line: int) -> int:
    """Return the file line a YAML error names, or the first front matter line."""
    mark: Any = getattr(exc, "problem_mark", None)
    number = getattr(mark, "line", None)
    if isinstance(number, int):
        return first_line + number
    return first_line


def parse_text(text: str, *, plugin: bool, into: AgentFile) -> None:
    """Fill ``into`` from an agent file's text. The body is never kept.

    Args:
        text: The file text.
        plugin: True for a plugin agent, so ignored fields are flagged.
        into: The file record to fill (``code``, ``name``, ``fields`` and the rest).
    """
    lines = agent_md.LINE_RE.findall(text)
    span = agent_md.frontmatter_span(lines)
    if span is None:
        into.code, into.line = "frontmatter_invalid", 1
        return
    first_line = span[0] + 1
    block = lines[span[0] : span[1]]
    positions = _key_lines(block, first_line)
    keyed: dict[str, object]
    try:
        data = _load_yaml("".join(block))
    except (YAMLError, ValueError, RecursionError, TypeError) as exc:
        salvaged = _salvage(text, block) if isinstance(exc, YAMLError) else None
        if salvaged is None:
            line = _error_line(exc, first_line) if isinstance(exc, YAMLError) else 1
            into.code, into.line = "frontmatter_invalid", line
            return
        keyed = salvaged
    else:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            into.code, into.line = "frontmatter_invalid", first_line
            return
        mapping = cast("Mapping[object, object]", data)
        keyed = {str(key): value for key, value in mapping.items()}
    _fill(text, keyed, positions, plugin=plugin, into=into)


# A value that starts with one of these is flow or block syntax, not a plain name.
_NOT_PLAIN = "[{\"'|>&*!"


def _salvage(text: str, block: list[str]) -> dict[str, object] | None:
    """Read the top-level ``key: value`` lines of a block ruamel could not parse.

    Claude Code loads some frontmatter that YAML rejects, such as an unclosed bracket
    in a description (rule ``agent-file-reader-rejected``, tested on 2.1.302). Each
    value is then its raw text, which is all this keeps. A file is salvaged only when
    the strict reader rejected it with no kind that stops the load
    (``resolve.PARSE_ERROR_KINDS``) and it has a plain ``name``, because an item needs
    a name to exist. A key with nothing after it, such as a list, keeps no value.

    Returns:
        The key to raw text map, or None when the file does not load or has no usable
        name, so the caller reports ``frontmatter_invalid``.
    """
    _fields, errors, _lines = agent_frontmatter.read_frontmatter_lines(text)
    if not errors:
        return None
    for error in errors:
        kind = error.split(": ", 1)[1] if ": " in error else error
        if kind in resolve.PARSE_ERROR_KINDS:
            return None
    found: dict[str, object] = {}
    for raw in block:
        content = agent_md.split_line(raw)[0]
        match = _KEY_LINE.match(content)
        if match is None or content[0] in " \t":
            continue
        key = str(match.group("dq") or match.group("sq") or match.group("bare")).strip()
        value = agent_md.strip_quotes(content[match.end() :])
        found.setdefault(key, value or None)
    name = found.get("name")
    if not isinstance(name, str) or name.startswith(tuple(_NOT_PLAIN)):
        return None
    return found


def _fill(
    text: str,
    keyed: dict[str, object],
    positions: dict[str, int],
    *,
    plugin: bool,
    into: AgentFile,
) -> None:
    """Set the fields, name, description flag and gap of ``into`` from parsed keys."""
    known = _known_order()
    order = [key for key in known if key in keyed]
    order += [key for key in keyed if key not in known]
    into.fields = [
        _field(
            key,
            keyed[key],
            positions.get(key),
            ignored=plugin and key in PLUGIN_IGNORED_FIELDS,
        )
        for key in order
    ]
    name = _name_of(keyed.get("name"))
    description = keyed.get("description")
    into.has_description = isinstance(description, str) and description.strip() != ""
    into.name_line = positions.get("name")
    _fields, errors, _lines = agent_frontmatter.read_frontmatter_lines(text)
    if errors:
        into.strict_line = _first_error_line(errors)
    if name is None:
        into.code, into.line = "agent_no_name", 1
        return
    into.name = name
    into.gap = bool(errors)


def _first_error_line(errors: Sequence[str]) -> int:
    match = re.match(r"line (\d+)", errors[0]) if errors else None
    return int(match.group(1)) if match else 1


def _walk(  # noqa: PLR0913, PLR0917 - one recursion state, kept flat
    scope: read_scope.Scope,
    folder: str,
    rel: str,
    plugin: bool,
    seen: set[str],
    out: list[tuple[str, str]],
    found: Found,
    depth: int,
) -> None:
    """List ``folder`` and add each file and each subfolder's files to ``out``."""
    real = os.path.realpath(folder)
    if real in seen or depth > MAX_DEPTH:
        return
    seen.add(real)
    found.touched.append(Path(folder))
    names = read_scope.list_dir(scope, folder, plugin=plugin)
    if isinstance(names, UnreadableFile):
        if names.reason != "vanished":
            found.unreadable.append(names)
        return
    for name in names:
        if name.startswith("."):
            continue
        path = os.path.join(folder, name)  # noqa: PTH118 - paths stay strings here
        if os.path.isdir(path):  # noqa: PTH112
            _walk(scope, path, f"{rel}{name}/", plugin, seen, out, found, depth + 1)
        else:
            out.append((path, f"{rel}{name}"))


def _read_one(  # noqa: PLR0913, PLR0917 - one file and where it sits
    scope: read_scope.Scope,
    path: str,
    rel: str,
    layer: SetupScope,
    plugin_name: str | None,
    found: Found,
) -> None:
    record = AgentFile(
        layer=layer,
        plugin=plugin_name,
        path=path,
        rel=rel,
        display=scope.display(path),
        full_path=os.path.abspath(path),  # noqa: PTH100
    )
    found.files.append(record)
    if not path.endswith(".md"):
        record.code = "agent_not_md"
        return
    found.touched.append(Path(path))
    got = read_scope.read_snapshot(
        scope, path, FILE_CAP_BYTES, plugin=plugin_name is not None
    )
    if isinstance(got, UnreadableFile):
        found.files.pop()
        if got.reason != "vanished":
            found.unreadable.append(got)
        return
    try:
        text = got.data.decode("utf-8")
    except UnicodeDecodeError:
        found.files.pop()
        found.unreadable.append(scope.unreadable(path, "not_utf8"))
        return
    # ``got.real_path`` is absolute (a followed link out of the roots). Show it as a
    # display path, never raw.
    record.real_path = (
        scope.display(got.real_path)
        if got.real_path
        else read_scope.symlink_target(scope, path)
    )
    reader_fields, reader_errors, reader_lines = (
        agent_frontmatter.read_frontmatter_lines(text)
    )
    found.strict[path] = Strict(
        fields=cast("dict[str, Any]", collect.mask(reader_fields)),
        errors=list(reader_errors),
        lines={str(k): v for k, v in reader_lines.items()},
    )
    parse_text(text, plugin=plugin_name is not None, into=record)


def find(
    scope: read_scope.Scope,
    roots: Sequence[str],
    layer: SetupScope,
    *,
    plugin: str | None = None,
) -> Found:
    """Find and read the agent files under some roots.

    Args:
        scope: The project's scope. Every list and read goes through it.
        roots: Agent folders, or single agent files (a plugin manifest may name
            either). A folder that does not exist is no problem.
        layer: The scope of the files.
        plugin: The plugin's name for plugin agents, else None.

    Returns:
        The files in root order, then by path below the root, plus what could not be
        read. A file that vanished between the list and the read is left out.
    """
    found = Found()
    for root in roots:
        listed = list_root(scope, root, found, plugin=plugin is not None)
        for path, rel in sorted(listed, key=lambda pair: pair[1]):
            _read_one(scope, path, rel, layer, plugin, found)
    return found


def list_root(
    scope: read_scope.Scope, root: str, found: Found, *, plugin: bool = False
) -> list[tuple[str, str]]:
    """List the files under one agent root, as ``(path, rel)`` pairs, in walk order.

    This is the one folder walk the agent readers share. Every list goes through
    ``read_scope``, so a folder the scope refuses adds an ``UnreadableFile`` to
    ``found`` and no files. A root may be a single ``.md`` file.

    Args:
        scope: The project's scope.
        root: An agent folder, or a single agent file.
        found: Collects ``unreadable`` and ``touched`` from the walk.
        plugin: True for a plugin root.
    """
    listed: list[tuple[str, str]] = []
    if root.endswith(".md") and os.path.isfile(root):  # noqa: PTH113
        listed.append((root, os.path.basename(root)))  # noqa: PTH119
        found.touched.append(Path(root))
    else:
        _walk(scope, root, "", plugin, set(), listed, found, 0)
    return listed


def _old_order(file: AgentFile) -> tuple[tuple[int, str], ...]:
    """Sort key for the old collector's order: a folder's files, then its subfolders."""
    parts = file.rel.split("/")
    return (*((1, part) for part in parts[:-1]), (0, parts[-1]))


def find_records(
    scope: read_scope.Scope, roots: Sequence[tuple[SetupScope, str]]
) -> list[dict[str, Any]]:
    """Return the strict resolver's agent records for some ``(layer, root)`` pairs.

    One ``{"layer", "path", "fields", "errors", "lines"}`` per file, in the shape and
    order ``collect.collect_agents`` has: the roots in the order given, and in each a
    folder's files before its subfolders. The files are found and read by ``find``,
    so a file the scope refuses, that is over the cap or that is not UTF-8 is left
    out. A file that is not ``.md`` gets empty fields, because the resolver reads only
    its name (``not_md_file``).

    Args:
        scope: The project's scope. Every list and read goes through it.
        roots: ``(layer, agent folder)`` pairs, such as project then user.
    """
    out: list[dict[str, Any]] = []
    for layer, root in roots:
        found = find(scope, [root], layer)
        for f in sorted(found.files, key=_old_order):
            strict = found.strict.get(f.path) or Strict()
            out.append(
                {
                    "layer": layer,
                    "path": f.path,
                    "fields": strict.fields,
                    "errors": strict.errors,
                    "lines": strict.lines,
                }
            )
    return out
