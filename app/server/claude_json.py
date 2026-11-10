"""The masked reader of the home Claude settings file (m4-build.md task 8).

That file holds far more than Bar Tab may show: account details, project histories and
the owner's own numbers. The reader keeps three key groups and nothing else, as
m4-build.md section 7 says.

- Top-level ``mcpServers`` (user scope).
- ``projects[<listed project's path>].mcpServers`` (local scope).
- That project entry's approval keys, ``enabledMcpjsonServers``,
  ``disabledMcpjsonServers`` and ``enableAllProjectMcpServers``. The docs make settings
  the source of these (https://code.claude.com/docs/en/mcp.md), but older files may
  still have them. Also its ``disabledMcpServers``, the ``/mcp`` panel's toggle list.

How it holds that line. The text is first checked with ``json.loads`` and an
``object_pairs_hook`` that discards every object, so no value of the file outlives the
check. A scanner (``json_lines.Cursor``) then walks the top level and the listed
project's entry, and steps over every other key without decoding it. Only the wanted
values are decoded, and each server entry goes straight to ``mcp_entry.build``, which
masks it and keeps only the documented server fields. Nothing in the result, in a log
or in an error text is a value from an unwanted key. A parse error is a code and a line
number, never the text.

Which file. ``read_scope.Scope.claude_json_path`` decides. The default config folder
reads ``<home>/.claude.json``. A moved config folder reads only its own copy, because
Claude Code then ignores the home file (research 26-08 line 9).

When it reads. On demand, never in the background. The result is cached by the file's
stat signature (mode, size, mtime and inode), so a matching signature costs one
``lstat`` and no parse. The cap is ``CLAUDE_JSON_CAP_BYTES``. A file over it is
Couldn't read with ``too_large``.
"""

import json
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import json_lines
import mcp_entry
import read_scope
import setup_items
from mcp_entry import McpEntry
from models import ProblemFix, ProblemRow, SetupPart, UnreadableFile
from setup_contract import CLAUDE_JSON_CAP_BYTES, Collected, SetupContext

HANDOFF_KEY = "claude_json"
PART: SetupPart = "mcp"  # rows and unreadable files of this reader belong to MCP
APPROVAL_LISTS = ("enabledMcpjsonServers", "disabledMcpjsonServers")
APPROVAL_ALL = "enableAllProjectMcpServers"
# The /mcp panel's per-project off switch for user, local, plugin and managed servers.
# It is unrelated to the approval keys above (mcp.md, "Disable a server without
# removing it"), but it sits in the same project entry and is read the same way.
TOGGLE_LIST = "disabledMcpServers"
CACHE_MAX = 16

State = Literal["absent", "ok", "json_invalid", "not_object", "unreadable"]
# Called for each key of an object: (key, its line, where its value starts) -> the
# position after the value.
OnKey = Callable[[str, int, int], int]

# How many times a text was scanned, for the cache test. Not part of any answer.
STATS = {"parses": 0}


@dataclass(frozen=True)
class Approvals:
    """The project entry's approval keys and its ``/mcp`` toggle list.

    Attributes:
        enabled: ``enabledMcpjsonServers``.
        disabled: ``disabledMcpjsonServers``.
        enable_all: ``enableAllProjectMcpServers``.
        toggled_off: ``disabledMcpServers``, the servers the ``/mcp`` panel turned off.
    """

    enabled: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()
    enable_all: bool | None = None
    toggled_off: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaudeJson:
    """What the reader kept of the file.

    Attributes:
        state: ``absent`` (no file), ``ok``, ``json_invalid`` (``error_line`` says
            where), ``not_object`` (the top level is not an object) or ``unreadable``.
        display: The display path of the file, or None when absent.
        full_path: The absolute path, or None when absent.
        error_line: The line of a ``json_invalid`` error.
        unreadable: The row for a file that could not be read, with ``part`` set.
        user: Top-level servers, masked, in file order.
        local: The listed project's servers, masked, in file order.
        user_bad_line: The line of a top-level ``mcpServers`` that is not an object.
        local_bad_line: The same for the project entry's ``mcpServers``.
        entry_line: The line of the listed project's key when its value is not an
            object.
        approvals: The project entry's approval keys.
    """

    state: State
    display: str | None = None
    full_path: str | None = None
    error_line: int | None = None
    unreadable: UnreadableFile | None = None
    user: tuple[McpEntry, ...] = ()
    local: tuple[McpEntry, ...] = ()
    user_bad_line: int | None = None
    local_bad_line: int | None = None
    entry_line: int | None = None
    approvals: Approvals = Approvals()


# ---------------------------------------------------------------- the scan


def _drop(_pairs: list[tuple[str, object]]) -> None:
    """Discard an object. The check keeps no value of the file."""
    return None


def validate(text: str) -> None:
    """Raise ``ValueError`` when the text is not JSON."""
    try:
        json.loads(text, object_pairs_hook=_drop)
    except RecursionError as exc:
        msg = "nested too deeply"
        raise ValueError(msg) from exc


class _Scan:
    """One pass over a validated text that keeps the three key groups."""

    def __init__(self, text: str, targets: tuple[str, ...]) -> None:
        self.cur = json_lines.Cursor(text)
        self.text = text
        self.targets = targets
        self.user: list[McpEntry] = []
        self.local: list[McpEntry] = []
        self.user_bad: int | None = None
        self.local_bad: int | None = None
        self.entry_line: int | None = None
        self.approvals = Approvals()

    def _key(self, i: int) -> tuple[str, int, int]:
        """Read a key at ``i``. Return (key, its line, the start of its value)."""
        line = self.cur.line(i)
        key, i = self.cur.string(i)
        return key, line, self.cur.ws(self.cur.ws(i) + 1)

    def _members(self, i: int, on_key: OnKey) -> int:
        """Walk an object at ``i``, calling ``on_key`` for each key. Return its end."""
        cur, text = self.cur, self.text
        i = cur.ws(i + 1)
        if text[i] == "}":
            return i + 1
        while True:
            key, line, i = self._key(i)
            i = cur.ws(on_key(key, line, i))
            if text[i] == ",":
                i = cur.ws(i + 1)
                continue
            return i + 1

    def servers(self, i: int) -> tuple[list[McpEntry] | None, int]:
        """Read an ``mcpServers`` value. None for the list when it is not an object."""
        if self.text[i] != "{":
            return None, self.cur.skip(i)
        found: dict[str, McpEntry] = {}

        def one(name: str, line: int, at: int) -> int:
            raw, end = self.cur.decode(at)
            found.pop(name, None)  # a repeated name: the last one wins
            found[name] = mcp_entry.build(name, raw, line)
            return end

        end = self._members(i, one)
        return list(found.values()), end

    def entry(self, i: int, line: int) -> int:
        """Read the listed project's entry, keeping its servers and approvals."""
        # A repeated project key: the last one wins, so start again.
        self.local, self.local_bad = [], None
        self.approvals = Approvals()
        if self.text[i] != "{":
            self.entry_line = line
            return self.cur.skip(i)
        self.entry_line = None

        def one(key: str, key_line: int, at: int) -> int:
            if key == "mcpServers":
                got, end = self.servers(at)
                self.local, self.local_bad = (
                    got or [],
                    None if got is not None else key_line,
                )
                return end
            if key in APPROVAL_LISTS or key in (APPROVAL_ALL, TOGGLE_LIST):
                value, end = self.cur.decode(at)
                self._approval(key, value)
                return end
            return self.cur.skip(at)

        return self._members(i, one)

    def _approval(self, key: str, value: object) -> None:
        old = self.approvals
        if key == APPROVAL_ALL:
            if isinstance(value, bool):
                self.approvals = Approvals(
                    old.enabled, old.disabled, value, old.toggled_off
                )
            return
        if not isinstance(value, list):
            return
        names = tuple(item for item in value if isinstance(item, str))  # pyright: ignore[reportUnknownVariableType]
        enabled, disabled, off = old.enabled, old.disabled, old.toggled_off
        if key == "enabledMcpjsonServers":
            enabled = names
        elif key == "disabledMcpjsonServers":
            disabled = names
        else:
            off = names
        self.approvals = Approvals(enabled, disabled, old.enable_all, off)

    def projects(self, i: int) -> int:
        """Read the ``projects`` object, keeping only the listed project's entry."""
        if self.text[i] != "{":
            return self.cur.skip(i)

        def one(key: str, line: int, at: int) -> int:
            if key in self.targets:
                return self.entry(at, line)
            return self.cur.skip(at)

        return self._members(i, one)

    def top(self) -> None:
        """Read the top-level object."""

        def one(key: str, line: int, at: int) -> int:
            if key == "mcpServers":
                got, end = self.servers(at)
                self.user, self.user_bad = got or [], None if got is not None else line
                return end
            if key == "projects":
                return self.projects(at)
            return self.cur.skip(at)

        self._members(self.cur.ws(0), one)


def _parse(text: str, targets: tuple[str, ...], shown: str, full: str) -> ClaudeJson:
    """Check the text and keep the three key groups."""
    STATS["parses"] += 1
    try:
        validate(text)
    except json.JSONDecodeError as exc:
        return ClaudeJson("json_invalid", shown, full, error_line=exc.lineno)
    except ValueError:
        return ClaudeJson("json_invalid", shown, full, error_line=1)
    scan = _Scan(text, targets)
    start = scan.cur.ws(0)
    if text[start : start + 1] != "{":
        return ClaudeJson("not_object", shown, full, error_line=1)
    scan.top()
    return ClaudeJson(
        "ok",
        shown,
        full,
        user=tuple(scan.user),
        local=tuple(scan.local),
        user_bad_line=scan.user_bad,
        local_bad_line=scan.local_bad,
        entry_line=scan.entry_line,
        approvals=scan.approvals,
    )


# ---------------------------------------------------------------- the cache

_CACHE: dict[tuple[str, tuple[str, ...]], tuple[str, ClaudeJson]] = {}
_LOCK = threading.Lock()


def _targets(project_dir: Path | None) -> tuple[str, ...]:
    """Return the keys that name the listed project: its path as given and resolved."""
    if project_dir is None:
        return ()
    given = os.path.abspath(project_dir)  # noqa: PTH100
    try:
        real = os.path.realpath(given)
    except (OSError, ValueError):
        real = given
    return tuple(sorted({given, real}))


def _load(
    scope: read_scope.Scope, path: Path, targets: tuple[str, ...], full: str
) -> ClaudeJson:
    shown = scope.display(path)
    text = read_scope.read_text(scope, path, CLAUDE_JSON_CAP_BYTES, parse=validate)
    if isinstance(text, UnreadableFile):
        if text.reason == "vanished":
            return ClaudeJson("absent")
        # The file holds user servers and local ones, so it is shown as the user's.
        bad = text.model_copy(update={"part": PART, "scope": "user"})
        return ClaudeJson("unreadable", shown, full, unreadable=bad)
    return _parse(text, targets, shown, full)


def read(scope: read_scope.Scope) -> ClaudeJson:
    """Return what the Claude settings file holds that Bar Tab may show.

    Args:
        scope: The project's read scope. Its context says which project is listed.

    Returns:
        The three key groups, masked. A file that is missing, unreadable or bad gives
        a result with that ``state`` and nothing else. It never raises, and a result
        whose file signature still matches comes from the cache without a read.
    """
    path = scope.claude_json_path()
    if path is None:
        return ClaudeJson("absent")
    full = os.path.abspath(path)  # noqa: PTH100
    targets = _targets(scope.ctx.project_dir)
    signature = read_scope.stat_signature(scope, [path])
    key = (full, targets)
    with _LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == signature:
        return hit[1]
    got = _load(scope, path, targets, full)
    with _LOCK:
        _CACHE.pop(key, None)
        _CACHE[key] = (signature, got)
        while len(_CACHE) > CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
    return got


def clear_cache() -> None:
    """Forget every cached result."""
    with _LOCK:
        _CACHE.clear()


def cache_size() -> int:
    """Return how many results are cached."""
    with _LOCK:
        return len(_CACHE)


# ---------------------------------------------------------------- the collector


def _entry_problem(got: ClaudeJson, line: int, key: str) -> ProblemRow:
    return setup_items.make_problem(
        code="not_object",
        group="wont_load",
        kind="problem",
        part=PART,
        thing=got.display or "",
        item=None,
        file=got.display,
        full_path=got.full_path,
        line=line,
        params={"key": key},
        confidence=setup_items.DOCUMENTED,
        fix=ProblemFix(kind="copy_path", target=got.full_path, reason=None),
    )


def problems_of(got: ClaudeJson) -> list[ProblemRow]:
    """Return the Won't load rows for a bad file or a bad entry in it."""
    if got.display is None or got.full_path is None:
        return []
    if got.state in ("json_invalid", "not_object"):
        return [
            setup_items.file_problem(
                code=got.state,
                part=PART,
                file=got.display,
                full_path=got.full_path,
                line=got.error_line,
                managed=False,
            )
        ]
    rows: list[ProblemRow] = []
    for line, key in (
        (got.user_bad_line, "mcpServers"),
        (got.local_bad_line, "projects.mcpServers"),
        (got.entry_line, "projects"),
    ):
        if line is not None:
            rows.append(_entry_problem(got, line, key))
    return rows


class ClaudeJsonCollector:
    """The reader as a collector. It has no part: it feeds MCP through the handoff."""

    name = "claude_json"
    parts: Sequence[SetupPart] = ()

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the file once (or take it from the cache). Never raises."""
        scope = read_scope.Scope(ctx)
        got = read(scope)
        path = scope.claude_json_path()
        return Collected(
            problems=setup_items.sort_problems(problems_of(got)),
            unreadable=[got.unreadable] if got.unreadable is not None else [],
            touched=[path] if path is not None else [],
            handoff={HANDOFF_KEY: got},
        )

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of the file."""
        scope = read_scope.Scope(ctx)
        path = scope.claude_json_path()
        return read_scope.stat_signature(scope, [path] if path is not None else [])


COLLECTOR = ClaudeJsonCollector()
