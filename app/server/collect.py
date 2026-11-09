"""Collectors for the dashboard: settings files, environment, agent files, rules files.

Each collector reads files the caller names and returns plain data with the
path and line of every value. Secret-looking values are replaced with the word
"hidden" here, before anything else sees them. Standard library only, Python 3.9.

The module never calls os.path.expanduser or Path.home, never reads os.environ
and writes nothing. Every folder and the environment come in as arguments, and
every path in the output is built with os.path.join from those arguments.

It does not return launch flags, --settings content, MDM (mobile device
management) settings or server-managed settings, because the dashboard cannot
see them.
"""

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0917, PTH113, PTH118, PTH123, PTH208
#
# Ported unchanged so the old tests keep passing. The old code builds paths as
# strings with os.path, and its collectors and merge keep their branch and
# argument counts.

import bisect
import copy
import json
import json.decoder
import os
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

import agent_frontmatter
import agent_md

HIDDEN = "hidden"
SECRET_NAME_PARTS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
# Names that hold a secret-looking part but never a secret. MAX_THINKING_TOKENS is
# a token budget, and the resolver reads its value (rule always-thinking-order).
# The match is the whole name, in any case. A value with a secret prefix still hides.
NOT_SECRET_NAMES = ("MAX_THINKING_TOKENS",)
SECRET_VALUE_PREFIXES = ("sk-", "Bearer ")

MANAGED_FILE = "managed-settings.json"
MANAGED_FOLDER = "managed-settings.d"

# Managed settings merge rules, from
# https://code.claude.com/docs/en/managed-settings#split-a-file-based-policy-across-teams
# A later file replaces these top-level values whole.
_REPLACE_WHOLE = (("fallbackModel",), ("modelPicker",))
# A later file replaces these top-level objects entry by entry.
_REPLACE_ENTRY = (("extraKnownMarketplaces",), ("managedMcpServers",))

_LINE_BREAK_RE = re.compile(r"\r\n|\n|\r")
_JSON_SPACE = " \t\n\r"

# One collected record, and the map of key path to {"path", "line"}.
Record = dict[str, Any]
Where = dict[tuple[str, ...], Record]


# Masking


def is_secret_name(name: object) -> bool:
    """True when the name contains any secret part, in any case.

    A name in NOT_SECRET_NAMES is never secret, so its value is read as it is
    (and a value with a secret prefix still hides, see is_secret_value).
    """
    if not isinstance(name, str):
        return False
    upper = name.upper()
    if upper in NOT_SECRET_NAMES:
        return False
    return any(part in upper for part in SECRET_NAME_PARTS)


def is_secret_value(value: object) -> bool:
    """True for a string that starts with a secret prefix, in any case.

    Leading white space is ignored, so " sk-..." hides too.
    """
    if not isinstance(value, str):
        return False
    start = value.lstrip().lower()
    return any(start.startswith(prefix.lower()) for prefix in SECRET_VALUE_PREFIXES)


def mask(value: object, name: object = None) -> object:
    """Return value with every secret-looking part replaced by HIDDEN.

    A secret name hides the whole value, a dict or list included. A dict masks
    each item under its own key, a list masks each item under the list's name,
    and a string with a secret prefix is hidden. Anything else is unchanged.
    """
    if is_secret_name(name):
        return HIDDEN
    if isinstance(value, dict):
        return {
            key: mask(item, key) for key, item in cast("dict[str, Any]", value).items()
        }
    if isinstance(value, list):
        return [mask(item, name) for item in cast("list[Any]", value)]
    if is_secret_value(value):
        return HIDDEN
    return value


# Key lines


def json_key_lines(text: str) -> dict[tuple[str, ...], int]:
    """Return {path tuple: 1-based line} for every object key of valid JSON.

    The path is the tuple of keys from the top, so ("env", "FOO") and
    ("modelSettings", "us.anthropic.x-v1:0", "effortLevel") work even when a key
    holds dots. Arrays are skipped without looking inside. When an object
    repeats a key the last one wins, as json.loads does. Call it only on text
    json.loads accepted.
    """
    starts = [0] + [m.end() for m in _LINE_BREAK_RE.finditer(text)]
    decoder = json.JSONDecoder()
    # typeshed omits json.decoder.scanstring, so it is fetched by name.
    scanstring = cast(
        "Callable[[str, int], tuple[str, int]]",
        getattr(json.decoder, "scanstring"),  # noqa: B009
    )
    found: dict[tuple[str, ...], int] = {}

    def line_of(pos: int) -> int:
        return bisect.bisect_right(starts, pos)

    def skip(i: int) -> int:
        while i < len(text) and text[i] in _JSON_SPACE:
            i += 1
        return i

    def drop(path: tuple[str, ...]) -> None:
        size = len(path)
        for other in [k for k in found if k[:size] == path]:
            del found[other]

    def value(i: int, path: tuple[str, ...]) -> int:
        ch = text[i]
        if ch == "{":
            return obj(i, path)
        if ch == '"':
            return scanstring(text, i + 1)[1]
        return decoder.raw_decode(text, i)[1]

    def obj(i: int, path: tuple[str, ...]) -> int:
        i = skip(i + 1)
        if text[i] == "}":
            return i + 1
        seen: set[Any] = set()
        while True:
            line = line_of(i)
            key, i = scanstring(text, i + 1)
            i = skip(skip(i) + 1)  # past the colon
            child = (*path, key)
            if key in seen:
                drop(child)
            seen.add(key)
            found[child] = line
            i = skip(value(i, child))
            if text[i] == ",":
                i = skip(i + 1)
                continue
            return i + 1

    value(skip(0), ())
    return found


# Settings


def _read_bytes(path: str) -> tuple[bytes | None, str]:
    """Return (bytes, status). Status is "ok", "missing" or "unreadable"."""
    try:
        with open(path, "rb") as fh:
            return fh.read(), "ok"
    except (FileNotFoundError, NotADirectoryError):
        return None, "missing"
    except OSError:
        return None, "unreadable"


def _read_settings_file(
    layer: str, path: str, managed: bool, overlay: dict[str, bytes] | None = None
) -> tuple[Record | None, dict[str, Any] | None, Where | None]:
    """Return (record, data, where). record is None for a missing file.

    data and where are None unless the record's status is "ok". data is not
    masked yet. A path in overlay ({path: bytes}) is read from that map and
    not from the disk, and counts as present even when no such file exists.
    """
    if overlay is not None and path in overlay:
        raw, status = overlay[path], "ok"
    else:
        raw, status = _read_bytes(path)
    if status == "missing":
        return None, None, None
    if status == "unreadable":
        return (
            {"layer": layer, "path": path, "status": "unreadable", "line": None},
            None,
            None,
        )

    def unparsed(line: int) -> tuple[Record, None, None]:
        return (
            {"layer": layer, "path": path, "status": "unparsed", "line": line},
            None,
            None,
        )

    if raw is None:
        return None, None, None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return unparsed(raw[: exc.start].count(b"\n") + 1)
    if managed and text == "":
        return {"layer": layer, "path": path, "status": "ok", "line": None}, {}, {}
    try:
        parsed: Any = json.loads(text)
        if not isinstance(parsed, dict):
            return unparsed(1)
        data = cast("dict[str, Any]", parsed)
        lines = json_key_lines(text)
    except json.JSONDecodeError as exc:
        return unparsed(exc.lineno)
    except (ValueError, IndexError, RecursionError):
        return unparsed(1)
    where: Where = {key: {"path": path, "line": line} for key, line in lines.items()}
    return {"layer": layer, "path": path, "status": "ok", "line": None}, data, where


def _managed_paths(managed_dir: str) -> tuple[list[str], Record | None]:
    """Return (paths in merge order, a record for an unlistable folder or None)."""
    paths = [os.path.join(managed_dir, MANAGED_FILE)]
    folder = os.path.join(managed_dir, MANAGED_FOLDER)
    try:
        names = os.listdir(folder)
    except (FileNotFoundError, NotADirectoryError):
        return paths, None
    except OSError:
        return paths, {
            "layer": "managed",
            "path": folder,
            "status": "unreadable",
            "line": None,
        }
    for name in sorted(names):
        full = os.path.join(folder, name)
        if name.endswith(".json") and not name.startswith(".") and os.path.isfile(full):
            paths.append(full)
    return paths, None


def _drop_where(where: Where, path: tuple[str, ...]) -> None:
    size = len(path)
    for key in [k for k in where if k[:size] == path]:
        del where[key]


def _take_where(where: Where, path: tuple[str, ...], other: Where) -> None:
    """Point path and everything under it at the entries `other` holds."""
    _drop_where(where, path)
    size = len(path)
    for key, entry in other.items():
        if key[:size] == path:
            where[key] = entry


def _combine_lists(old: list[Any], new: list[Any]) -> list[Any]:
    out: list[Any] = []
    seen: set[Any] = set()
    for item in list(old) + list(new):
        marker = json.dumps(item, sort_keys=True)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out


def _merge_into(
    acc: dict[str, Any],
    where: Where,
    new: dict[str, Any],
    new_where: Where,
    path: tuple[str, ...],
) -> None:
    """Merge the dict `new` into `acc`, and keep `where` pointing at the right file."""
    for key, value in new.items():
        child = (*path, key)
        if key not in acc:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)
            continue
        old = acc[key]
        if len(child) == 1 and child in _REPLACE_WHOLE:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)
        elif (
            len(child) == 1
            and child in _REPLACE_ENTRY
            and isinstance(old, dict)
            and isinstance(value, dict)
        ):
            for name, entry in cast("dict[str, Any]", value).items():
                acc[key][name] = copy.deepcopy(entry)
                _take_where(where, (*child, name), new_where)
            where[child] = new_where[child]
        elif isinstance(old, dict) and isinstance(value, dict):
            _merge_into(
                cast("dict[str, Any]", old),
                where,
                cast("dict[str, Any]", value),
                new_where,
                child,
            )
            where[child] = new_where[child]
        elif isinstance(old, list) and isinstance(value, list):
            acc[key] = _combine_lists(cast("list[Any]", old), cast("list[Any]", value))
            _take_where(where, child, new_where)
        else:
            acc[key] = copy.deepcopy(value)
            _take_where(where, child, new_where)


def _merge_local(
    parts: list[tuple[dict[str, Any], Where]],
) -> tuple[dict[str, Any], Where]:
    """Merge the (data, where) of the local files, lowest first, into one pair.

    A list both files set is combined, and its `where` names the root file only
    (_take_where above), a known limit the docs state.
    """
    merged: dict[Any, Any] = {}
    merged_where: dict[Any, Any] = {}
    for data, where in parts:
        _merge_into(merged, merged_where, data, where, ())
    return merged, merged_where


def collect_settings(
    config_dir: str,
    project_dir: str,
    managed_dir: str | None,
    overlay: dict[str, bytes] | None = None,
    local_path: str | None = None,
) -> Record:
    """Read the settings files.

    Returns {"sources": [...], "files": [...]}. "files" has one record per file
    that exists, with its status (ok, unparsed or unreadable) and, for an
    unparsed file, the line of the problem. "sources" has one entry per layer
    that parsed, highest first: the merged managed files, local, project, user.
    Each is {"layer", "data", "where"}, with data masked and where mapping each
    key path to {"path", "line"}.

    overlay is {path: bytes}, keyed by the exact path string joined below. A
    file in it is read from the map, not the disk (see _read_settings_file).

    local_path is the local settings file Claude Code uses (#104), as the exact
    string local_root gives. None, or the project's own .claude/settings.local.json,
    reads that one file. Otherwise the project's file (the leftover) and local_path
    (the root file) are both read, each with its own record in "files", and merge
    into one "local" source with the root file on top.
    """
    start_local = os.path.join(project_dir, ".claude", "settings.local.json")
    two_locals = local_path is not None and local_path != start_local
    files: list[Any] = []
    managed: list[Any] = []  # (data, where) of each ok managed file, in merge order
    if managed_dir is not None:
        paths, folder_record = _managed_paths(managed_dir)
        for path in paths:
            record, data, where = _read_settings_file("managed", path, True, overlay)
            if record is None:
                continue
            files.append(record)
            if data is not None:
                managed.append((mask(data), where))
        if folder_record is not None:
            files.append(folder_record)
    plain: list[Any] = []
    local_parts: list[Any] = []  # (data, where) of each ok local file, leftover first
    local_slot = None
    for layer, path in (
        ("local", start_local),
        ("local", local_path if two_locals else None),
        ("project", os.path.join(project_dir, ".claude", "settings.json")),
        ("user", os.path.join(config_dir, "settings.json")),
    ):
        if path is None:
            continue
        record, data, where = _read_settings_file(layer, path, False, overlay)
        if record is None:
            continue
        files.append(record)
        if data is None:
            continue
        if two_locals and layer == "local":
            local_parts.append((data, where))
            if local_slot is None:
                local_slot = len(plain)
                plain.append(None)
        else:
            plain.append({"layer": layer, "data": mask(data), "where": where})
    if local_slot is not None:
        data, where = _merge_local(local_parts)
        plain[local_slot] = {"layer": "local", "data": mask(data), "where": where}
    sources: list[Any] = []
    if managed:
        merged: dict[Any, Any] = {}
        merged_where: dict[Any, Any] = {}
        for data, where in managed:
            _merge_into(merged, merged_where, data, where, ())
        sources.append({"layer": "managed", "data": merged, "where": merged_where})
    sources.extend(plain)
    return {"sources": sources, "files": files}


# Environment


def collect_env(
    sources: list[Record],
    shell_env: Mapping[str, object],
    variable_names: Iterable[str],
) -> dict[str, list[Record]]:
    """Return {NAME: [record, ...]} with settings records first, then the shell's.

    A settings record comes from an env block in `sources`, in source order,
    and carries its layer, path and line. The shell record carries no path. A
    shell variable is kept only when `variable_names` names it or an env block
    set it, so nothing else of the shell leaves this function. Values are
    masked by variable name and by value.
    """
    out: dict[str, list[Record]] = {}
    for source in sources:
        block: Any = source["data"].get("env")
        if not isinstance(block, dict):
            continue
        for name, value in cast("dict[str, Any]", block).items():
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                continue
            spot = source["where"].get(("env", name), {})
            out.setdefault(name, []).append(
                {
                    "value": mask(str(value), name),
                    "origin": "settings",
                    "layer": source["layer"],
                    "path": spot.get("path"),
                    "line": spot.get("line"),
                }
            )
    named = set(variable_names)
    for name, value in shell_env.items():
        if not isinstance(value, str):
            continue
        if name in named or name in out:
            out.setdefault(name, []).append(
                {"value": mask(value, name), "origin": "shell"}
            )
    return out


# Agents and rules files


def collect_agents(config_dir: str, project_dir: str) -> list[Record]:
    """Read every file under the two agent folders, subfolders included.

    Returns one {"layer", "path", "fields", "errors", "lines"} per file, project
    folder first. fields is masked. A file the reader rejects keeps its errors.
    No file text is returned.
    """
    out: list[Any] = []
    for layer, folder in (
        ("project", os.path.join(project_dir, ".claude", "agents")),
        ("user", os.path.join(config_dir, "agents")),
    ):
        for path in agent_md.list_files_sorted(folder):
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                text = None
            fields, errors, lines = agent_frontmatter.read_frontmatter_lines(text)
            out.append(
                {
                    "layer": layer,
                    "path": path,
                    "fields": mask(fields),
                    "errors": errors,
                    "lines": lines,
                }
            )
    return out


def collect_rules_files(config_dir: str, project_dir: str) -> list[Record]:
    """List every file under the two rules folders as {"layer", "path"}."""
    out: list[Any] = []
    for layer, folder in (
        ("project", os.path.join(project_dir, ".claude", "rules")),
        ("user", os.path.join(config_dir, "rules")),
    ):
        for path in agent_md.list_files_sorted(folder):
            out.append({"layer": layer, "path": path})
    return out


def collect(
    config_dir: str,
    project_dir: str,
    managed_dir: str | None,
    shell_env: Mapping[str, object],
    rules: Mapping[str, Any],
    overlay: dict[str, bytes] | None = None,
    reuse: Record | None = None,
    local_path: str | None = None,
) -> Record:
    """Run every collector. `rules` is the rules.json document.

    overlay is {path: bytes}, passed to collect_settings. reuse is an earlier
    collect() result: its agents and rules_files are taken as they are and those
    two collectors do not run. settings, settings_files and env always run.
    local_path is passed to collect_settings.
    """
    settings = collect_settings(
        config_dir, project_dir, managed_dir, overlay, local_path
    )
    names = [v["name"] for v in rules.get("variables", [])]
    return {
        "settings": settings["sources"],
        "settings_files": settings["files"],
        "env": collect_env(settings["sources"], shell_env, names),
        "agents": reuse["agents"]
        if reuse is not None
        else collect_agents(config_dir, project_dir),
        "rules_files": (
            reuse["rules_files"]
            if reuse is not None
            else collect_rules_files(config_dir, project_dir)
        ),
    }
