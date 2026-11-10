"""The MCP collector (m4-build.md task 8, part ``mcp``).

One item per server name, ``mcp:<name>``. A server is defined in one or more places.

- Managed ``managed-mcp.json`` in the managed folder.
- The listed project's entry in the masked ``.claude.json`` (local scope, setup scope
  ``project_local``), from ``handoff["claude_json"]``.
- The project's ``.mcp.json`` (project scope).
- The top level of ``.claude.json`` (user scope).
- A plugin's ``.mcp.json`` or the ``mcpServers`` written in its manifest
  (``handoff["plugins"]``).

Precedence (https://code.claude.com/docs/en/mcp.md): managed beats local beats project
beats user, with no field merge. A plugin's servers have their own scoped name in
Claude Code (``plugin:<plugin>:<server>``), so they never meet another server of the
same name. An item for a plugin server is always ``mcp:<plugin>:<name>``, as plugin
skills and agents are (owner answer for plugin agents). Inside a name the first server
that can load wins. An
entry that can't load (a bad shape) or isn't approved doesn't shadow the ones below it,
which is our reading, so an item where that matters has confidence ``assumed``.

Approval. A project ``.mcp.json`` server runs only when approved. A name in
``disabledMcpjsonServers`` is rejected, a name in ``enabledMcpjsonServers`` is approved,
and ``enableAllProjectMcpServers`` approves the rest. These keys come from every
settings scope (``handoff["settings"]["approvals"]``) and from the project entry of
``.claude.json``. An unapproved server is ``ignored`` with no problem row (corpus
decision 8). Workspace trust is not visible here.

Toggled off. The project entry of ``.claude.json`` can also hold ``disabledMcpServers``,
the ``/mcp`` panel's off switch for user, local, plugin and managed servers. A server
named there is ``ignored`` and its reason names ``disabledMcpServers`` in ``by``. Like
an unapproved server it makes no problem row and does not shadow the ones below it.

Statuses and rows. A bad entry is ``invalid`` with a Won't load row,
``mcp_bad_entry``. A ``.mcp.json`` that isn't JSON is ``json_invalid``. A server with a
``${VAR}`` that has no default is ``unknown`` with a Can't tell row,
``env_not_visible``, because the session's environment is not visible.

Read-only. A user or local server lives in the home settings file and is changed with
``claude mcp``, so it is read-only with the code ``claude_json_command`` and the masked
command ``claude mcp remove <name> -s user`` (or ``-s local``). Bar Tab only offers to
copy it (owner decision 8). Managed and plugin servers carry their own reasons.
"""

import json
import os
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import claude_json
import collect_settings
import command_mask
import json_lines
import mcp_entry
import plugin_inputs
import read_scope
import setup_items
from claude_json import ClaudeJson
from mcp_entry import McpEntry
from models import (
    SETUP_SCOPES,
    ItemFacts,
    ItemReason,
    ModelCheckStatus,
    ProblemFix,
    ProblemRow,
    ReadOnly,
    SetupItem,
    SetupPart,
    SetupScope,
    UnreadableFile,
)
from setup_contract import FILE_CAP_BYTES, Collected, SetupContext

PART: SetupPart = "mcp"
HANDOFF_SETTINGS = "settings"
MCP_FILE = ".mcp.json"
MANAGED_FILE = "managed-mcp.json"
_RANK = {scope: rank for rank, scope in enumerate(SETUP_SCOPES)}
_VISIBLE: tuple[SetupScope, ...] = (
    "managed",
    "project_local",
    "project",
    "user",
    "plugin",
)
_PROJECT: tuple[SetupScope, ...] = ("project_local", "project")


@dataclass
class _Def:
    """One definition of a server, in one place."""

    scope: SetupScope
    entry: McpEntry
    file: str
    full_path: str
    order: int
    plugin: str | None = None
    real_path: str | None = None
    from_claude_json: bool = False
    approved: bool | None = None
    toggled: bool = False
    by: str | None = None
    status: ModelCheckStatus = "in_effect"

    @property
    def rank(self) -> tuple[int, int]:
        return (_RANK[self.scope], self.order)

    @property
    def group(self) -> tuple[str | None, str]:
        return (self.plugin, self.entry.name)


@dataclass(frozen=True)
class _Where:
    """The file a group of servers came from."""

    scope: SetupScope
    file: str
    full: str
    plugin: str | None = None
    real_path: str | None = None
    from_claude_json: bool = False


@dataclass
class _Approval:
    """The approval keys, merged across every settings scope and the project entry."""

    enabled: set[str] = field(default_factory=set[str])
    disabled: set[str] = field(default_factory=set[str])
    enable_all: bool | None = None
    toggled_off: set[str] = field(default_factory=set[str])

    def is_off(self, one: _Def) -> bool:
        """True when the ``/mcp`` panel turned this definition's server off.

        The list covers user, local, plugin and managed servers, not the servers of a
        project ``.mcp.json``, which the approval keys decide
        (https://code.claude.com/docs/en/mcp.md, "Disable a server without removing
        it"). A plugin server is listed by its scoped name, ``plugin:<plugin>:<name>``,
        which the docs show only for claude.ai connectors, so that match is assumed.
        """
        if one.scope == "project":
            return False
        name = one.entry.name
        if one.plugin is not None:
            name = f"plugin:{one.plugin}:{name}"
        return name in self.toggled_off

    def decide(self, name: str) -> tuple[bool, str | None]:
        """Return (approved, the key that decided it)."""
        if name in self.disabled:
            return False, "disabledMcpjsonServers"
        if name in self.enabled:
            return True, "enabledMcpjsonServers"
        if self.enable_all:
            return True, "enableAllProjectMcpServers"
        return False, None


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast("list[object]", value) if isinstance(item, str)]


def _approvals(settings: Mapping[str, object], cj: ClaudeJson) -> _Approval:
    out = _Approval()
    table = settings.get("approvals")
    if isinstance(table, Mapping):
        by_key = cast("Mapping[str, object]", table)
        for place in _places(by_key.get("enabledMcpjsonServers")):
            out.enabled.update(_strings(place.get("value")))
        for place in _places(by_key.get("disabledMcpjsonServers")):
            out.disabled.update(_strings(place.get("value")))
        for place in _places(by_key.get("enableAllProjectMcpServers")):
            value = place.get("value")
            if isinstance(value, bool):
                out.enable_all = value  # the first place is the top-wins one
                break
    out.enabled.update(cj.approvals.enabled)
    out.disabled.update(cj.approvals.disabled)
    out.toggled_off.update(cj.approvals.toggled_off)
    if out.enable_all is None:
        out.enable_all = cj.approvals.enable_all
    return out


def _places(raw: object) -> list[Mapping[str, object]]:
    if not isinstance(raw, list):
        return []
    return [
        cast("Mapping[str, object]", one)
        for one in cast("list[object]", raw)
        if isinstance(one, Mapping)
    ]


def _settings_handoff(
    ctx: SetupContext, handoff: Mapping[str, object]
) -> Mapping[str, object]:
    """Return the settings handoff, reading the settings if it is missing."""
    got = handoff.get(HANDOFF_SETTINGS)
    if isinstance(got, Mapping) and "approvals" in got:
        return cast("Mapping[str, object]", got)
    made = collect_settings.COLLECTOR.read(ctx, {}).handoff.get(HANDOFF_SETTINGS)
    return cast("Mapping[str, object]", made) if isinstance(made, Mapping) else {}


def _fix_for(scope: SetupScope, full_path: str) -> ProblemFix:
    if scope == "managed":
        return ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    if scope == "plugin":
        return ProblemFix(kind="cant_fix_here", target=None, reason="plugin")
    return ProblemFix(kind="copy_path", target=full_path, reason=None)


def _inline_servers(inline: object) -> tuple[object, tuple[str, ...]]:
    """Return the servers written in a manifest and their key path in it.

    The object is bare (``{name: server}``) or wrapped in its own ``mcpServers`` key.
    """
    if isinstance(inline, dict):
        wrapped: object = cast("dict[str, object]", inline).get("mcpServers")
        if isinstance(wrapped, dict):
            return cast("object", wrapped), ("mcpServers", "mcpServers")
    return cast("object", inline), ("mcpServers",)


def remove_command(name: str, scope: SetupScope) -> str:
    """Return the ``claude mcp remove`` command for a user or local server."""
    flag = "local" if scope == "project_local" else "user"
    return f"claude mcp remove {shlex.quote(name)} -s {flag}"


class _Run:
    """One read of the MCP servers of a project."""

    def __init__(
        self, ctx: SetupContext, handoff: Mapping[str, object], scope: read_scope.Scope
    ) -> None:
        self.ctx = ctx
        self.handoff = handoff
        self.scope = scope
        self.defs: list[_Def] = []
        self.problems: dict[str, ProblemRow] = {}
        self.unreadable: list[UnreadableFile] = []
        self.touched: list[Path] = []
        raw = handoff.get(claude_json.HANDOFF_KEY)
        self.cj = raw if isinstance(raw, ClaudeJson) else claude_json.read(scope)

    # ------------------------------------------------------------ reading

    def _file_problem(
        self, code: str, where: _Where, line: int | None, key: str
    ) -> None:
        row = setup_items.make_problem(
            code=code,
            group="wont_load",
            kind="problem",
            part=PART,
            thing=where.file,
            item=None,
            file=where.file,
            full_path=where.full,
            line=line,
            params={"key": key} if key else {},
            confidence=setup_items.DOCUMENTED,
            fix=_fix_for(where.scope, where.full),
        )
        self.problems.setdefault(row.id, row)

    def _add(self, where: _Where, entry: McpEntry) -> None:
        self.defs.append(
            _Def(
                scope=where.scope,
                entry=entry,
                file=where.file,
                full_path=where.full,
                order=len(self.defs),
                plugin=where.plugin,
                real_path=where.real_path,
                from_claude_json=where.from_claude_json,
            )
        )

    def _servers_of(
        self, table: object, text: str, prefix: tuple[str, ...], where: _Where
    ) -> None:
        """Add the servers of an ``mcpServers`` object read from a file's text."""
        lines = json_lines.index(text, prefix[:1])
        if not isinstance(table, dict):
            self._file_problem("not_object", where, lines.get(prefix), "mcpServers")
            return
        for name, raw in cast("dict[str, object]", table).items():
            entry = mcp_entry.build(
                name, raw, lines.get((*prefix, name)), plugin=where.plugin is not None
            )
            self._add(where, entry)

    def _read(self, path: str, *, plugin: bool) -> str | None:
        """Read one JSON text through the scope. None after noting why not."""
        self.touched.append(Path(path))
        got = read_scope.read_text(
            self.scope, path, FILE_CAP_BYTES, parse=json.loads, plugin=plugin
        )
        if isinstance(got, UnreadableFile):
            if got.reason != "vanished":
                self.unreadable.append(got.model_copy(update={"part": PART}))
            return None
        return got

    def _parsed(self, text: str, where: _Where) -> dict[str, object] | None:
        """Parse a server file's text. A bad file makes its row and gives None."""
        try:
            parsed = cast("object", json.loads(text))
        except json.JSONDecodeError as exc:
            self._file_problem("json_invalid", where, exc.lineno, "")
            return None
        except (ValueError, RecursionError):
            self._file_problem("json_invalid", where, 1, "")
            return None
        if not isinstance(parsed, dict):
            self._file_problem("not_object", where, 1, "")
            return None
        return cast("dict[str, object]", parsed)

    def _where(self, path: str, scope: SetupScope, plugin: str | None = None) -> _Where:
        return _Where(
            scope=scope,
            file=self.scope.display(path),
            full=os.path.abspath(path),  # noqa: PTH100
            plugin=plugin,
            real_path=read_scope.symlink_target(self.scope, path),
        )

    def read_file(self, path: str, scope: SetupScope) -> None:
        """Read a managed or project server file."""
        text = self._read(path, plugin=False)
        if text is None:
            return
        where = self._where(path, scope)
        parsed = self._parsed(text, where)
        if parsed is not None and "mcpServers" in parsed:
            self._servers_of(parsed["mcpServers"], text, ("mcpServers",), where)

    def read_plugins(self) -> None:
        """Read the servers of every enabled plugin."""
        for found in plugin_inputs.rows(self.handoff, "mcp"):
            text = self._read(found.path, plugin=True)
            if text is None:
                continue
            where = self._where(found.path, "plugin", found.name)
            inline = found.inline
            if inline is None:
                parsed = self._parsed(text, where)
                if parsed is not None and "mcpServers" in parsed:
                    self._servers_of(parsed["mcpServers"], text, ("mcpServers",), where)
                continue
            table, prefix = _inline_servers(inline)
            self._servers_of(table, text, prefix, where)

    def read_claude_json(self) -> None:
        """Add the user and local servers the masked reader kept."""
        got = self.cj
        if got.display is None or got.full_path is None:
            return
        places: tuple[tuple[SetupScope, tuple[McpEntry, ...]], ...] = (
            ("project_local", got.local),
            ("user", got.user),
        )
        for scope, entries in places:
            where = _Where(
                scope=scope,
                file=got.display,
                full=got.full_path,
                from_claude_json=True,
            )
            for entry in entries:
                self._add(where, entry)

    # ------------------------------------------------------------ items

    def run(self) -> Collected:
        """Read every place and build the items."""
        ctx = self.ctx
        if ctx.managed_dir is not None:
            self.read_file(str(ctx.managed_dir / MANAGED_FILE), "managed")
        if ctx.project_dir is not None:
            self.read_file(str(ctx.project_dir / MCP_FILE), "project")
        self.read_plugins()
        self.read_claude_json()
        approval = _approvals(_settings_handoff(ctx, self.handoff), self.cj)
        groups: dict[tuple[str | None, str], list[_Def]] = {}
        for one in self.defs:
            if one.scope == "project":
                one.approved, one.by = approval.decide(one.entry.name)
            elif approval.is_off(one):
                one.toggled, one.by = True, claude_json.TOGGLE_LIST
            groups.setdefault(one.group, []).append(one)
        items = [self._item(self._item_id(key), found) for key, found in groups.items()]
        items.sort(key=lambda item: item.id)
        return Collected(
            items={PART: setup_items.number(items)},
            problems=setup_items.sort_problems(self.problems.values()),
            unreadable=self.unreadable,
            touched=self.touched,
        )

    @staticmethod
    def _item_id(key: tuple[str | None, str]) -> str:
        """Return ``mcp:<name>``, or ``mcp:<plugin>:<name>`` for a plugin server.

        A plugin server is always its own item, never the bare name, as agents and
        skills are (owner answer for plugin agents, m4-build.md section 16).
        """
        plugin, name = key
        return f"{PART}:{plugin}:{name}" if plugin else f"{PART}:{name}"

    def _status(self, found: list[_Def]) -> _Def | None:
        """Settle each definition's status and return the one that wins, or None."""
        won: _Def | None = None
        for one in found:
            if one.entry.why_bad is not None:
                one.status = "invalid"
            elif (one.scope == "project" and not one.approved) or one.toggled:
                one.status = "ignored"
            elif won is None:
                one.status = "unknown" if one.entry.unset_vars else "in_effect"
                won = one
            else:
                one.status = "overridden"
        return won

    def _item(self, item_id: str, found: list[_Def]) -> SetupItem:
        ordered = sorted(found, key=lambda d: d.rank)
        won = self._status(ordered)
        lead = won or ordered[0]
        sources = [
            setup_items.source_of(
                scope=d.scope,
                key=f"mcpServers.{d.entry.name}",
                file=d.file,
                full_path=d.full_path,
                line=d.entry.line,
                value=None,
                status=d.status,
            ).model_copy(update={"plugin": d.plugin})
            for d in ordered
        ]
        shadowed = won is not None and any(
            d is not won and d.rank < won.rank for d in ordered
        )
        hidden = list(_PROJECT) if self.ctx.project_dir is None else []
        item = setup_items.make_item(
            part=PART,
            key=lead.entry.name,
            name=lead.entry.name,
            item_id=item_id,
            label_known=True,
            scope=lead.scope,
            status=lead.status,
            sources=sources,
            winner=ordered.index(won) if won is not None else None,
            reach_=setup_items.reach([s for s in _VISIBLE if s not in hidden], hidden),
            confidence=(
                setup_items.ASSUMED
                if shadowed or (lead.toggled and lead.plugin is not None)
                else setup_items.DOCUMENTED
            ),
            reason=_reason(lead),
            facts=ItemFacts(
                mcp=lead.entry.facts.model_copy(update={"approved": lead.approved})
            ),
            read_only=_read_only(lead),
            real_path=lead.real_path,
            changeable=self._may_change(lead.scope),
        )
        for one in ordered:
            self._rows(item, one, won)
        return item

    def _may_change(self, scope: SetupScope) -> bool:
        """True when a file that could not be read could change this item's answer."""
        if setup_items.may_change(self.unreadable, scope):
            return True
        # The home file holds user and local servers, so its failure reaches every
        # scope but managed.
        return self.cj.unreadable is not None and scope != "managed"

    def _rows(self, item: SetupItem, one: _Def, won: _Def | None) -> None:
        """Add the problem row a definition makes, if any."""
        entry = one.entry
        if entry.why_bad is not None:
            code, group, kind = "mcp_bad_entry", "wont_load", "problem"
            params = {"name": entry.name, "why": entry.why_bad}
        elif one is won and entry.unset_vars:
            code, group, kind = "env_not_visible", "cant_tell", "cant_tell"
            params = {"name": entry.name, "vars": ",".join(entry.unset_vars)}
        else:
            return
        subject = item.id
        if f"{code}:{subject}:{entry.line}" in self.problems:
            subject = f"{item.id}@{one.file}"  # the same line in another file
        row = setup_items.make_problem(
            code=code,
            group=group,  # pyright: ignore[reportArgumentType]
            kind=kind,  # pyright: ignore[reportArgumentType]
            part=PART,
            thing=entry.name,
            item=item,
            file=one.file,
            full_path=one.full_path,
            line=entry.line,
            params=params,
            confidence=setup_items.DOCUMENTED,
            fix=_fix(item, one),
            subject=subject,
        )
        self.problems.setdefault(row.id, row)


def _reason(lead: _Def) -> ItemReason:
    params = {"file": lead.file}
    if lead.status == "ignored":
        code = "mcp_not_approved"
        if lead.by is not None:
            params["by"] = lead.by
    elif lead.status == "invalid":
        code = "mcp_bad_entry"
        params["why"] = lead.entry.why_bad or ""
    elif lead.status == "unknown":
        code = "env_not_visible"
    else:
        code = "in_effect"
    return ItemReason(code=code, params=params, rule_id=None, ref_item=None)


def _read_only(lead: _Def) -> ReadOnly | None:
    if lead.from_claude_json:
        text = remove_command(lead.entry.name, lead.scope)
        return ReadOnly(
            code="claude_json_command",
            params={},
            command=command_mask.masked_command(text),
        )
    if lead.scope == "plugin":
        return ReadOnly(
            code="plugin", params={"plugin": lead.plugin or ""}, command=None
        )
    return setup_items.read_only_for(lead.scope)


def _fix(item: SetupItem, one: _Def) -> ProblemFix:
    """Return the one action a row offers, by where the server is defined."""
    if one.from_claude_json:
        text = remove_command(one.entry.name, one.scope)
        return ProblemFix(
            kind="copy_command",
            target=command_mask.mask_command(text),
            reason=None,
        )
    if one.scope in ("managed", "plugin"):
        return _fix_for(one.scope, one.full_path)
    return ProblemFix(kind="open_item", target=item.id, reason=None)


class McpCollector:
    """The collector of part ``mcp``."""

    name = "mcp"
    parts: Sequence[SetupPart] = (PART,)

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the MCP servers of the project. Never raises."""
        return _Run(ctx, handoff, read_scope.Scope(ctx)).run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Return a stat-only fingerprint of the files the last read touched.

        The home settings file is fingerprinted by the ``claude_json`` collector and the
        settings files by theirs.
        """
        scope = read_scope.Scope(ctx)
        paths = last.touched if last is not None else _candidates(ctx)
        return read_scope.stat_signature(scope, paths)


def _candidates(ctx: SetupContext) -> list[Path]:
    found: list[Path] = []
    if ctx.managed_dir is not None:
        found.append(ctx.managed_dir / MANAGED_FILE)
    if ctx.project_dir is not None:
        found.append(ctx.project_dir / MCP_FILE)
    return found


COLLECTOR = McpCollector()

__all__ = ["COLLECTOR", "McpCollector", "remove_command"]
