"""One MCP server entry, checked and masked (m4-build.md task 8).

The ``.mcp.json`` files, the plugin files and the masked ``.claude.json`` reader all
turn a raw server entry into a ``McpEntry`` here, so the raw entry (which holds
secrets in ``env``, ``headers``, ``args`` and ``url``) never leaves this module's
caller. Only the documented fields are read: ``type``, ``command``, ``args``, ``env``,
``url`` and ``headers``. Any other key of the entry is dropped.

Validity follows the docs facts in m4-build.md section 16 and the MCP page
(https://code.claude.com/docs/en/mcp.md). No ``type`` means stdio. ``http`` (alias
``streamable-http``), ``sse`` and ``ws`` take a ``url``. A ``url`` with no ``type`` is
an error, because Claude Code reads the entry as stdio. A bad entry has a ``why_bad``
word.

``${VAR}`` with no ``:-default`` expands from the session's environment, which the
server can't see, so the entry lists it in ``unset_vars`` and the collector says Can't
tell. A plugin's own entry gets ``CLAUDE_PLUGIN_ROOT``, ``CLAUDE_PLUGIN_DATA`` and
``CLAUDE_PROJECT_DIR`` substituted by Claude Code, so those three are never unset there.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

import command_mask
import masking
from models import MaskedText, McpFacts

REMOTE_TYPES = frozenset({"http", "streamable-http", "sse", "ws"})
KNOWN_TYPES = REMOTE_TYPES | {"stdio"}
PLUGIN_VARS = frozenset(
    {"CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CLAUDE_PROJECT_DIR"}
)
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")


@dataclass(frozen=True)
class McpEntry:
    """A server entry as the collectors use it.

    Attributes:
        name: The server's name.
        line: The line of the name in its file, or None.
        facts: The masked facts. ``approved`` is None here; the collector sets it.
        why_bad: None for a usable entry. Else ``not_object``, ``bad_type``,
            ``unknown_type``, ``bad_field``, ``url_without_type``, ``no_url``,
            ``no_command`` or ``no_command_or_url``.
        unset_vars: Names of ``${VAR}`` references with no default, sorted.
    """

    name: str
    line: int | None
    facts: McpFacts
    why_bad: str | None
    unset_vars: tuple[str, ...]


def _empty(transport: str) -> McpFacts:
    return McpFacts(
        transport=transport,
        command=None,
        url=None,
        args=[],
        env={},
        headers={},
        approved=None,
    )


def _text(value: object) -> str | None:
    """Return a string for a scalar, else None."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _strings(raw: object) -> list[str] | None:
    """Return a list of scalar strings, or None when ``raw`` is not such a list."""
    if not isinstance(raw, list):
        return None
    out: list[str] = []
    for item in cast("list[object]", raw):
        shown = _text(item)
        if shown is None:
            return None
        out.append(shown)
    return out


def _table(raw: object) -> dict[str, str] | None:
    """Return a map of scalar strings, or None when ``raw`` is not such a map."""
    if not isinstance(raw, dict):
        return None
    out: dict[str, str] = {}
    for key, value in cast("dict[object, object]", raw).items():
        shown = _text(value)
        if shown is None:
            return None
        out[str(key)] = shown
    return out


def _masked_table(table: Mapping[str, str]) -> dict[str, MaskedText]:
    return {name: masking.masked_text(value, name) for name, value in table.items()}


def _masked_args(args: list[str]) -> list[MaskedText]:
    shown = masking.mask_args(args)
    return [
        MaskedText(text=str(new), masked=str(new) != old)
        for old, new in zip(args, shown, strict=True)
    ]


def _unset(strings: list[str], *, plugin: bool) -> tuple[str, ...]:
    names: set[str] = set()
    for text in strings:
        for found in _VAR.finditer(text):
            if found[2] is None and not (plugin and found[1] in PLUGIN_VARS):
                names.add(found[1])
    return tuple(sorted(names))


def _transport(kind: object) -> str:
    if kind is None:
        return "stdio"
    if isinstance(kind, str):
        return "http" if kind == "streamable-http" else kind
    return "stdio"


def _why(kind: object, command: str | None, url: str | None) -> str | None:
    """Return why an entry with these fields can't load, or None."""
    if kind is not None and (not isinstance(kind, str)):
        return "bad_type"
    if kind is not None and kind not in KNOWN_TYPES:
        return "unknown_type"
    if kind in REMOTE_TYPES:
        return None if url else "no_url"
    if command:
        return None
    if url:
        return "url_without_type" if kind is None else "no_command"
    return "no_command_or_url" if kind is None else "no_command"


def build(
    name: str, raw: object, line: int | None, *, plugin: bool = False
) -> McpEntry:
    """Check and mask one raw server entry.

    Args:
        name: The server's name.
        raw: The entry as parsed. It is read here and not kept.
        line: The line of the name in its file, or None.
        plugin: True for a plugin's own entry (see the module docstring).

    Returns:
        The entry. Masking has already happened, so nothing in it is a secret value.
    """
    if not isinstance(raw, dict):
        return McpEntry(name, line, _empty("stdio"), "not_object", ())
    entry = cast("dict[str, object]", raw)
    kind = entry.get("type")
    command = entry.get("command")
    url = entry.get("url")
    args = _strings(entry["args"]) if "args" in entry else []
    env = _table(entry["env"]) if "env" in entry else {}
    headers = _table(entry["headers"]) if "headers" in entry else {}
    bad_field = (
        args is None
        or env is None
        or headers is None
        or (command is not None and not isinstance(command, str))
        or (url is not None and not isinstance(url, str))
    )
    command_text = command if isinstance(command, str) else None
    url_text = url if isinstance(url, str) else None
    why = "bad_field" if bad_field else _why(kind, command_text, url_text)
    args = args or []
    env = env or {}
    headers = headers or {}
    facts = McpFacts(
        transport=_transport(kind),
        command=command_mask.masked_command(command_text) if command_text else None,
        url=masking.masked_text(url_text, "url") if url_text else None,
        args=_masked_args(args),
        env=_masked_table(env),
        headers=_masked_table(headers),
        approved=None,
    )
    scanned = [*(s for s in (command_text, url_text) if s), *args]
    scanned += [*env.values(), *headers.values()]
    return McpEntry(name, line, facts, why, _unset(scanned, plugin=plugin))
