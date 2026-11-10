"""The plugins collector (m4-build.md task 6, part ``plugins``).

It reads ``<config>/plugins/installed_plugins.json`` and ``known_marketplaces.json``,
the ``enabledPlugins`` entries of every settings scope, and each install folder's
``.claude-plugin/plugin.json`` with its components. It makes one item per plugin id
(``plugins:<name>@<marketplace>``) and hands each enabled plugin's component folders
on to the later collectors.

Shapes. The top level of ``installed_plugins.json`` and ``known_marketplaces.json`` is
not in the docs. The corpus assumes ``{"version": <int>, "plugins": {"<id>":
[{"scope", "installPath", "version"}, ...]}}`` for the first and ``{"<marketplace>":
{...}}`` for the second. Any other shape gives a Can't tell row,
``plugin_format_unknown``, and nothing is taken from that file. Every plugin item is
``assumed`` for the same reason.

The ``enabledPlugins`` input, in the order tried.

1. ``handoff["settings"]["enabledPlugins"]``, which the settings collector (task 4)
   makes: one mapping for each settings file that has the key, highest scope first,
   with ``scope``, ``file``, ``full_path``, ``line`` (of the key) and ``value`` (the
   plugin id to Boolean map). The line of each plugin comes from the handed ``layers``
   when they have it, else the key's line.
2. ``handoff["enabledPlugins"]``, a list of ``EnabledEntry`` (or mappings with the same
   keys), highest scope first.
3. Nothing handed: this collector reads the settings files itself through
   ``read_scope``.

One entry for each scope and plugin: the first, which is the highest file, wins.

Handoff out. ``handoff["plugins"]`` is a list of ``PluginComponents``, one for each
plugin that is installed, readable and enabled. A disabled plugin loads nothing, so no
later collector sees it.

Cache folder. When ``CLAUDE_CODE_PLUGIN_CACHE_DIR`` in the shell environment moves the
cache outside ``<config>/plugins/``, nothing under it is read (owner answer 3), so every
plugin is not read here.
"""

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import agent_files
import collect
import git_root
import masking
import read_scope
from models import (
    Effective,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    NotReadCode,
    PluginFacts,
    PluginScopeState,
    ProblemRow,
    ReadOnly,
    ScopeReach,
    SetupItem,
    SetupPart,
    SetupScope,
    SetupSource,
    UnreadableFile,
)
from problem_rows import confidence, make_row
from setup_contract import FILE_CAP_BYTES, Collected, SetupContext

HANDOFF_SETTINGS = "settings"
HANDOFF_ENABLED = "enabledPlugins"
HANDOFF_PLUGINS = "plugins"  # the lead's shape: skills, commands, hooks, mcp lists
HANDOFF_COMPONENTS = "plugin_components"  # list[PluginComponents], for the agents
HANDOFF_STYLES = "plugin_output_styles"  # [{plugin, name, path}] for the Output style
CACHE_ENV = "CLAUDE_CODE_PLUGIN_CACHE_DIR"
PART: SetupPart = "plugins"
# Which install wins when a plugin has several (the narrowest scope first). A guess,
# like the file's shape.
_INSTALL_ORDER: tuple[SetupScope, ...] = ("project_local", "project", "user", "managed")
_INSTALL_SCOPES: dict[str, SetupScope] = {
    "local": "project_local",
    "project": "project",
    "user": "user",
    "managed": "managed",
}
_KEPT_SETTINGS = ("agent", "subagentStatusLine")
_ORPHAN_MARK = ".orphaned_at"
_SCOPE_ORDER: tuple[SetupScope, ...] = ("managed", "project_local", "project", "user")
_ENABLED = "enabled"
_DISABLED = "disabled"
JsonObject = dict[str, Any]


@dataclass(frozen=True)
class EnabledEntry:
    """One ``enabledPlugins`` entry of one settings scope.

    Attributes:
        plugin_id: ``<plugin>@<marketplace>``.
        scope: The settings scope that holds the entry.
        enabled: The entry's Boolean.
        file: The display path of the settings file.
        full_path: The absolute path of the settings file.
        line: The line of the entry.
    """

    plugin_id: str
    scope: SetupScope
    enabled: bool
    file: str | None
    full_path: str | None
    line: int | None


@dataclass
class PluginComponents:
    """What an enabled plugin brings, for the collectors that run after this one.

    Every path is absolute, sits under the plugin's install folder, and exists.

    Attributes:
        item_id: The plugin item's id.
        plugin_id: ``<plugin>@<marketplace>``.
        name: The plugin's name (the manifest's, else the id's first part).
        root: The install folder.
        agents: Agent folders or files (the manifest's ``agents`` replaces ``agents/``).
        skills: Skill folders (``skills`` in the manifest adds to ``skills/``).
        commands: Command folders or files (replaced by the manifest).
        output_styles: Output style folders or files (replaced by the manifest).
        hooks_files: Hook files (``hooks/hooks.json`` unless the manifest names others).
        hooks_inline: A ``hooks`` object written in the manifest, or None.
        mcp_files: MCP files (``.mcp.json`` unless the manifest names others).
        mcp_inline: An ``mcpServers`` object written in the manifest, or None.
        settings: The plugin's ``settings.json``, only ``agent`` and
            ``subagentStatusLine``, masked.
    """

    item_id: str
    plugin_id: str
    name: str
    root: str
    agents: list[str] = field(default_factory=list[str])
    skills: list[str] = field(default_factory=list[str])
    commands: list[str] = field(default_factory=list[str])
    output_styles: list[str] = field(default_factory=list[str])
    hooks_files: list[str] = field(default_factory=list[str])
    hooks_inline: object | None = None
    mcp_files: list[str] = field(default_factory=list[str])
    mcp_inline: object | None = None
    settings: dict[str, object] = field(default_factory=dict[str, object])


def plugin_item_id(plugin_id: str) -> str:
    """Return a plugin's item id."""
    return f"plugins:{plugin_id}"


def _component_row(comp: PluginComponents, path: str) -> dict[str, object]:
    return {"plugin": comp.plugin_id, "name": comp.name, "path": path}


def handoff_lists(components: Sequence[PluginComponents]) -> dict[str, list[object]]:
    """Return the handoff the skills, hooks, MCP and output style collectors read.

    ``{"skills", "commands", "hooks", "mcp"}``, each a list of ``{plugin, name,
    path}``. ``plugin`` is the plugin id (``<name>@<marketplace>``), ``name`` the
    plugin's name and ``path`` an absolute folder (skills, commands) or file (hooks,
    mcp). A manifest object written inline goes in as one more row whose ``path`` is
    the manifest and whose ``inline`` is the object.
    """
    lists: dict[str, list[object]] = {
        "skills": [],
        "commands": [],
        "hooks": [],
        "mcp": [],
    }
    for comp in components:
        for key, paths in (
            ("skills", comp.skills),
            ("commands", comp.commands),
            ("hooks", comp.hooks_files),
            ("mcp", comp.mcp_files),
        ):
            lists[key].extend(_component_row(comp, path) for path in paths)
        manifest = os.path.join(comp.root, ".claude-plugin", "plugin.json")  # noqa: PTH118
        if comp.hooks_inline is not None:
            lists["hooks"].append(
                {**_component_row(comp, manifest), "inline": comp.hooks_inline}
            )
        if comp.mcp_inline is not None:
            lists["mcp"].append(
                {**_component_row(comp, manifest), "inline": comp.mcp_inline}
            )
    return lists


# ---------------------------------------------------------------- reading JSON


@dataclass
class _Json:
    """One JSON file read through the scope."""

    data: object = None
    unreadable: UnreadableFile | None = None
    error_line: int | None = None
    missing: bool = False


def _read_json(scope: read_scope.Scope, path: str, *, plugin: bool) -> _Json:
    got = read_scope.read_text(
        scope, path, FILE_CAP_BYTES, parse=json.loads, plugin=plugin
    )
    if isinstance(got, UnreadableFile):
        if got.reason == "vanished":
            return _Json(missing=True)
        return _Json(unreadable=got)
    try:
        return _Json(data=cast("object", json.loads(got)))
    except json.JSONDecodeError as exc:
        return _Json(error_line=exc.lineno)
    except (ValueError, RecursionError):
        return _Json(error_line=1)


def _is_object(value: object) -> bool:
    return isinstance(value, dict)


def _string_keys(value: object) -> JsonObject:
    return cast("JsonObject", value)


# ---------------------------------------------------------------- file shapes


@dataclass
class _Install:
    scope: SetupScope
    path: str
    version: str | None


def _install_of(raw: object, base: str) -> _Install | None:
    if not _is_object(raw):
        return None
    entry = _string_keys(raw)
    path = entry.get("installPath")
    if not isinstance(path, str) or not path:
        return None
    if not os.path.isabs(path):  # noqa: PTH117
        path = os.path.join(base, path)  # noqa: PTH118
    version = entry.get("version")
    return _Install(
        scope=_INSTALL_SCOPES.get(str(entry.get("scope")), "user"),
        path=path,
        version=version if isinstance(version, str) else None,
    )


def _applicable(raw: object, project: str | None) -> bool:
    """False for an install made for another project (``projectPath`` differs)."""
    if not _is_object(raw):
        return True
    where = _string_keys(raw).get("projectPath")
    if not isinstance(where, str) or project is None:
        return True
    return os.path.realpath(where) == os.path.realpath(project)


def _parse_installed(
    data: object, base: str, project: str | None
) -> dict[str, _Install | None] | None:
    """Return {plugin id: the install that applies, or None} or None for a bad shape."""
    if not _is_object(data):
        return None
    top = _string_keys(data)
    plugins = top.get("plugins")
    if not _is_object(plugins) or not isinstance(top.get("version"), int):
        return None
    out: dict[str, _Install | None] = {}
    for plugin_id, raw in _string_keys(plugins).items():
        items: list[object] = (
            cast("list[object]", raw) if isinstance(raw, list) else [raw]
        )
        installs: list[_Install] = []
        for one in items:
            install = _install_of(one, base)
            if install is None:
                return None
            if _applicable(one, project):
                installs.append(install)
        installs.sort(key=lambda i: _INSTALL_ORDER.index(i.scope))
        out[plugin_id] = installs[0] if installs else None
    return out


def _marketplaces_ok(data: object) -> bool:
    if not _is_object(data):
        return False
    return all(_is_object(v) for v in _string_keys(data).values())


# ---------------------------------------------------------------- enabledPlugins


def _scope_value(value: object) -> SetupScope:
    text = str(value)
    for scope in _SCOPE_ORDER:
        if scope == text:
            return scope
    return "user"


def _entry_of(raw: object) -> EnabledEntry | None:
    """Turn one handoff element (an ``EnabledEntry`` or a mapping) into an entry."""
    if isinstance(raw, EnabledEntry):
        return raw
    if not isinstance(raw, Mapping):
        return None
    row = cast("Mapping[str, object]", raw)
    plugin_id = row.get("plugin_id")
    enabled = row.get("enabled")
    if not isinstance(plugin_id, str) or not isinstance(enabled, bool):
        return None
    line = row.get("line")
    file = row.get("file")
    full = row.get("full_path")
    return EnabledEntry(
        plugin_id=plugin_id,
        scope=_scope_value(row.get("scope")),
        enabled=enabled,
        file=file if isinstance(file, str) else None,
        full_path=full if isinstance(full, str) else None,
        line=line if isinstance(line, int) else None,
    )


def _from_handoff(raw: object) -> list[EnabledEntry] | None:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    entries = [_entry_of(one) for one in cast("Sequence[object]", raw)]
    return [e for e in entries if e is not None]


def _plugin_lines(layers: object) -> dict[str, dict[str, int]]:
    """Map a settings file's full path to {plugin id: line}, from handed layers.

    The layers are the settings collector's own object. Only what is needed is read,
    by name, so a layers object that lacks it gives an empty map.
    """
    readable = getattr(layers, "readable", None)
    if not callable(readable):
        return {}
    found: dict[str, dict[str, int]] = {}
    for one in cast("Iterable[Any]", readable()):
        lines = getattr(one, "lines", None)
        path = getattr(one, "full_path", None)
        if not isinstance(lines, dict) or not isinstance(path, str):
            continue
        found[path] = {
            str(key[1]): value
            for key, value in cast("dict[tuple[str, ...], int]", lines).items()
            if len(key) == 2 and key[0] == "enabledPlugins"  # noqa: PLR2004
        }
    return found


def _from_settings_handoff(settings: object) -> list[EnabledEntry] | None:
    """Turn the settings collector's ``enabledPlugins`` handoff into entries."""
    if not isinstance(settings, Mapping):
        return None
    shared = cast("Mapping[str, object]", settings)
    raw = shared.get(HANDOFF_ENABLED)
    if not isinstance(raw, list):
        return None
    per_plugin = _plugin_lines(shared.get("layers"))
    out: list[EnabledEntry] = []
    seen: set[tuple[SetupScope, str]] = set()
    for one in cast("list[object]", raw):
        if not isinstance(one, Mapping):
            continue
        row = cast("Mapping[str, object]", one)
        value = row.get("value")
        if not isinstance(value, Mapping):
            continue
        scope = _scope_value(row.get("scope"))
        file, full, block = row.get("file"), row.get("full_path"), row.get("line")
        lines = per_plugin.get(full, {}) if isinstance(full, str) else {}
        for plugin_id, enabled in cast("Mapping[str, object]", value).items():
            if not isinstance(enabled, bool) or (scope, plugin_id) in seen:
                continue
            seen.add((scope, plugin_id))
            out.append(
                EnabledEntry(
                    plugin_id=str(plugin_id),
                    scope=scope,
                    enabled=enabled,
                    file=file if isinstance(file, str) else None,
                    full_path=full if isinstance(full, str) else None,
                    line=lines.get(
                        str(plugin_id), block if isinstance(block, int) else None
                    ),
                )
            )
    return out


def _settings_files(
    ctx: SetupContext, scope: read_scope.Scope, touched: list[Path]
) -> list[tuple[SetupScope, str]]:
    """Return the settings files, highest scope first (a standalone read)."""
    files: list[tuple[SetupScope, str]] = []
    if ctx.managed_dir is not None:
        folder = str(ctx.managed_dir / "managed-settings.d")
        touched.append(Path(folder))
        names = read_scope.list_dir(scope, folder)
        if not isinstance(names, UnreadableFile):
            later = [n for n in names if n.endswith(".json") and not n.startswith(".")]
            files.extend(("managed", os.path.join(folder, n)) for n in reversed(later))  # noqa: PTH118
        files.append(("managed", str(ctx.managed_dir / "managed-settings.json")))
    if ctx.project_dir is not None:
        root_local = git_root.local_settings_path(ctx.project_dir, ctx.home)
        if root_local is not None:
            files.append(("project_local", str(root_local)))
        files.append(
            ("project_local", str(ctx.project_dir / ".claude" / "settings.local.json"))
        )
        files.append(("project", str(ctx.project_dir / ".claude" / "settings.json")))
    files.append(("user", str(ctx.config_dir / "settings.json")))
    return files


def _read_enabled(
    ctx: SetupContext, scope: read_scope.Scope, touched: list[Path]
) -> list[EnabledEntry]:
    """Read ``enabledPlugins`` from the settings files, as task 4 would hand it on."""
    out: list[EnabledEntry] = []
    seen: set[tuple[SetupScope, str]] = set()
    for layer, path in _settings_files(ctx, scope, touched):
        touched.append(Path(path))
        text = read_scope.read_text(scope, path, FILE_CAP_BYTES)
        if isinstance(text, UnreadableFile):
            continue
        try:
            data = cast("object", json.loads(text))
            lines = collect.json_key_lines(text)
        except (ValueError, IndexError, RecursionError):
            continue
        if not _is_object(data):
            continue
        block = _string_keys(data).get("enabledPlugins")
        if not _is_object(block):
            continue
        for plugin_id, value in _string_keys(block).items():
            if not isinstance(value, bool) or (layer, plugin_id) in seen:
                continue
            seen.add((layer, plugin_id))
            out.append(
                EnabledEntry(
                    plugin_id=plugin_id,
                    scope=layer,
                    enabled=value,
                    file=scope.display(path),
                    full_path=os.path.abspath(path),  # noqa: PTH100
                    line=lines.get(("enabledPlugins", plugin_id)),
                )
            )
    return out


# ---------------------------------------------------------------- components


def _manifest_paths(root: str, value: object) -> list[str]:
    """Return the paths a manifest component field names, kept under ``root``."""
    raw: Iterable[object]
    if isinstance(value, str):
        raw = [value]
    elif isinstance(value, list):
        raw = cast("list[object]", value)
    else:
        return []
    out: list[str] = []
    base = os.path.realpath(root)
    for one in raw:
        if not isinstance(one, str) or not one:
            continue
        path = os.path.normpath(os.path.join(root, one))  # noqa: PTH118
        real = os.path.realpath(path)
        if real == base or real.startswith(base + os.sep):
            out.append(path)
    return out


def _existing(paths: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for path in paths:
        if os.path.exists(path):  # noqa: PTH110
            seen[path] = None
    return list(seen)


def _files_of(root: str, manifest: JsonObject, key: str, default: str) -> list[str]:
    """Return a file component.

    A manifest value replaces the default, and an inline object leaves no file.
    """
    if key not in manifest:
        return _existing([os.path.join(root, default)])  # noqa: PTH118
    if _is_object(manifest[key]):
        return []
    return _existing(_manifest_paths(root, manifest[key]))


def _components(
    root: str, manifest: JsonObject, item_id: str, plugin_id: str, name: str
) -> PluginComponents:
    """Work out a plugin's component paths. ``skills`` adds, the others replace."""

    def replaced(key: str, default: str) -> list[str]:
        if key in manifest:
            return _existing(_manifest_paths(root, manifest[key]))
        return _existing([os.path.join(root, default)])  # noqa: PTH118

    skills = [
        os.path.join(root, "skills"),  # noqa: PTH118
        *_manifest_paths(root, manifest.get("skills")),
    ]
    hooks, mcp = manifest.get("hooks"), manifest.get("mcpServers")
    return PluginComponents(
        item_id=item_id,
        plugin_id=plugin_id,
        name=name,
        root=root,
        agents=replaced("agents", "agents"),
        skills=_existing(skills),
        commands=replaced("commands", "commands"),
        output_styles=replaced("outputStyles", "output-styles"),
        hooks_files=_files_of(root, manifest, "hooks", "hooks/hooks.json"),
        hooks_inline=hooks if _is_object(hooks) else None,
        mcp_files=_files_of(root, manifest, "mcpServers", ".mcp.json"),
        mcp_inline=mcp if _is_object(mcp) else None,
    )


def _plugin_settings(
    scope: read_scope.Scope, root: str, unreadable: list[UnreadableFile]
) -> dict[str, object]:
    """Read a plugin's ``settings.json``, keeping ``agent`` and ``subagentStatusLine``.

    Values are masked.
    """
    got = _read_json(scope, os.path.join(root, "settings.json"), plugin=True)  # noqa: PTH118
    if got.unreadable is not None:
        unreadable.append(got.unreadable)
        return {}
    if not _is_object(got.data):
        return {}
    data = _string_keys(got.data)
    return {
        key: masking.mask_value(data[key], key) for key in _KEPT_SETTINGS if key in data
    }


def _orphans(install: str, touched: list[Path]) -> list[str]:
    """Return the version folders beside the install that hold ``.orphaned_at``."""
    parent = os.path.dirname(install.rstrip(os.sep))  # noqa: PTH120
    touched.append(Path(parent))
    try:
        names = sorted(os.listdir(parent))  # noqa: PTH208
    except OSError:
        return []
    mine = os.path.basename(install.rstrip(os.sep))  # noqa: PTH119
    return [
        name
        for name in names
        if name != mine and os.path.isfile(os.path.join(parent, name, _ORPHAN_MARK))  # noqa: PTH113, PTH118
    ]


# ---------------------------------------------------------------- one plugin


@dataclass
class _Plan:
    """What one plugin turned out to be, before it becomes an item."""

    plugin_id: str
    entries: list[EnabledEntry]
    install: _Install | None = None
    status: ModelCheckStatus = "in_effect"
    reason_code: str = "plugin_loads"
    not_read: NotReadCode | None = None
    may_change: bool = False
    name: str = ""
    version: str | None = None
    orphans: list[str] = field(default_factory=list[str])
    contents: list[str] = field(default_factory=list[str])
    components: PluginComponents | None = None


def _marketplace(plugin_id: str) -> str | None:
    return plugin_id.partition("@")[2] or None


def _effective(plan: _Plan) -> Effective:
    if not plan.entries:
        return Effective(
            value=MaskedText(text=_DISABLED, masked=False),
            origin="default",
            by_item=None,
        )
    word = _ENABLED if plan.entries[0].enabled else _DISABLED
    origin = "set" if plan.status == "in_effect" else "unknown"
    return Effective(
        value=MaskedText(text=word, masked=False), origin=origin, by_item=None
    )


def _sources(plan: _Plan) -> list[SetupSource]:
    out: list[SetupSource] = []
    for index, entry in enumerate(plan.entries):
        out.append(
            SetupSource(
                scope=entry.scope,
                key=f"enabledPlugins.{plan.plugin_id}",
                file=entry.file,
                full_path=entry.full_path,
                line=entry.line,
                value=MaskedText(
                    text="true" if entry.enabled else "false", masked=False
                ),
                status=plan.status if index == 0 else "overridden",
                plugin=None,
            )
        )
    return out


def _reach(ctx: SetupContext) -> list[ScopeReach]:
    return [
        ScopeReach(scope="managed", visible=ctx.managed_dir is not None),
        ScopeReach(scope="project_local", visible=ctx.project_dir is not None),
        ScopeReach(scope="project", visible=ctx.project_dir is not None),
        ScopeReach(scope="user", visible=True),
    ]


def _build_item(ctx: SetupContext, plan: _Plan, order: int) -> SetupItem:
    item_id = plugin_item_id(plan.plugin_id)
    winner = plan.entries[0] if plan.entries else None
    install_scope = plan.install.scope if plan.install is not None else None
    return SetupItem(
        id=item_id,
        part=PART,
        key=plan.plugin_id,
        name=plan.plugin_id,
        label_known=True,
        order=order,
        group=None,
        scope=winner.scope if winner is not None else install_scope,
        effective=_effective(plan),
        sources=_sources(plan),
        winner=0 if plan.entries else None,
        reach=_reach(ctx),
        status=plan.status,
        reason=ItemReason(
            code=plan.reason_code,
            params={"plugin": plan.name or plan.plugin_id},
            rule_id=None,
            ref_item=None,
        ),
        confidence=confidence("assumed"),
        loads=None,
        applies="reload_plugins",
        writable=False,
        read_only_reason=ReadOnly(
            code="plugin", params={"plugin": plan.name or plan.plugin_id}, command=None
        ),
        risk_tier=None,
        feature="core",
        facts=ItemFacts(
            plugin=PluginFacts(
                version=plan.version,
                marketplace=_marketplace(plan.plugin_id),
                enabled=[
                    PluginScopeState(scope=e.scope, enabled=e.enabled)
                    for e in plan.entries
                ],
                orphaned_versions=plan.orphans,
                contents=plan.contents,
            )
        ),
        usage=None,
        real_path=None,
        not_read=plan.not_read,
        may_change=plan.may_change,
    )


def with_contents(item: SetupItem, extra: Iterable[str]) -> SetupItem:
    """Return a plugin item with more item ids in its ``contents``.

    The plugin collector lists the plugin's agents. Skills, hooks and MCP servers have
    their own collectors, so the answer builder adds their ids with this.
    """
    facts = item.facts.plugin
    if facts is None:
        return item
    merged = list(dict.fromkeys([*facts.contents, *extra]))
    new_facts = facts.model_copy(update={"contents": merged})
    return item.model_copy(
        update={"facts": item.facts.model_copy(update={"plugin": new_facts})}
    )


# ---------------------------------------------------------------- the collector


class _Run:
    """One read of the plugins part."""

    def __init__(
        self, ctx: SetupContext, handoff: Mapping[str, object], scope: read_scope.Scope
    ) -> None:
        self.ctx = ctx
        self.scope = scope
        self.handoff = handoff
        self.out = Collected()
        self.touched = self.out.touched
        self.base = str(ctx.config_dir / "plugins")
        self.plans: list[_Plan] = []
        self.components: list[PluginComponents] = []

    # -- helpers

    def problem(self, row: ProblemRow) -> None:
        self.out.problems.append(row)

    def unreadable(
        self, entry: UnreadableFile, scope: SetupScope | None = None
    ) -> None:
        shown = entry if scope is None else entry.model_copy(update={"scope": scope})
        self.out.unreadable.append(shown)

    def file_problem(self, code: str, path: str) -> None:
        self.problem(
            make_row(
                code=code,
                group="cant_tell",
                thing=os.path.basename(path),  # noqa: PTH119
                part=PART,
                item_id=None,
                file=self.scope.display(path),
                full_path=os.path.abspath(path),  # noqa: PTH100
                line=None,
                level="assumed",
            )
        )

    # -- the files

    def moved_cache(self) -> str | None:
        """Return the cache folder when the environment moves it out of plugins/."""
        raw = self.ctx.shell_env.get(CACHE_ENV)
        if not raw:
            return None
        base = os.path.realpath(self.base)
        real = os.path.realpath(raw)
        return None if real == base or real.startswith(base + os.sep) else raw

    def read_installed(self) -> dict[str, _Install | None] | None:
        path = os.path.join(self.base, "installed_plugins.json")  # noqa: PTH118
        self.touched.append(Path(path))
        got = _read_json(self.scope, path, plugin=True)
        if got.unreadable is not None:
            self.unreadable(got.unreadable)
            return {}
        if got.missing:
            return {}
        project = str(self.ctx.project_dir) if self.ctx.project_dir else None
        parsed = (
            None if got.error_line else _parse_installed(got.data, self.base, project)
        )
        if parsed is None:
            self.file_problem("plugin_format_unknown", path)
            return None
        return parsed

    def read_marketplaces(self) -> None:
        path = os.path.join(self.base, "known_marketplaces.json")  # noqa: PTH118
        self.touched.append(Path(path))
        got = _read_json(self.scope, path, plugin=True)
        if got.unreadable is not None:
            self.unreadable(got.unreadable)
        elif got.missing:
            return
        elif got.error_line or not _marketplaces_ok(got.data):
            self.file_problem("plugin_format_unknown", path)

    def enabled(self) -> list[EnabledEntry]:
        from_settings = _from_settings_handoff(self.handoff.get(HANDOFF_SETTINGS))
        if from_settings is not None:
            return from_settings
        handed = _from_handoff(self.handoff.get(HANDOFF_ENABLED))
        if handed is not None:
            return handed
        return _read_enabled(self.ctx, self.scope, self.touched)

    # -- one plugin

    def plan_for(
        self,
        plugin_id: str,
        entries: list[EnabledEntry],
        installed: dict[str, _Install | None] | None,
    ) -> _Plan:
        plan = _Plan(plugin_id=plugin_id, entries=entries)
        plan.name = plugin_id.partition("@")[0]
        wants = bool(entries) and entries[0].enabled
        if installed is None:
            plan.status, plan.reason_code = "unknown", "plugin_format_unknown"
            return plan
        install = installed.get(plugin_id)
        plan.install = install
        if install is None:
            if wants:
                self.not_installed(plan)
            return plan
        self.read_install(plan, install, wants=wants)
        if not entries and plan.status == "in_effect":
            plan.status, plan.reason_code = "default", "plugin_not_enabled"
        return plan

    def not_installed(self, plan: _Plan) -> None:
        plan.status, plan.reason_code = "invalid", "plugin_not_installed"
        first = plan.entries[0]
        self.problem(
            make_row(
                code="plugin_not_installed",
                group="wont_load",
                thing=plan.plugin_id,
                part=PART,
                item_id=plugin_item_id(plan.plugin_id),
                file=first.file,
                full_path=first.full_path,
                line=first.line,
                level="assumed",
            )
        )

    def outside(self, plan: _Plan, install: _Install, entry: UnreadableFile) -> None:
        plan.status, plan.reason_code = "unknown", "plugin_outside_plugins"
        plan.not_read = "plugin_outside_plugins"
        self.unreadable(entry, install.scope)
        self.problem(
            make_row(
                code="plugin_outside_plugins",
                group="cant_tell",
                thing=plan.plugin_id,
                part=PART,
                item_id=plugin_item_id(plan.plugin_id),
                file=entry.file,
                full_path=entry.full_path,
                line=None,
                level="assumed",
            )
        )

    def read_install(self, plan: _Plan, install: _Install, *, wants: bool) -> None:
        listed = read_scope.list_dir(self.scope, install.path, plugin=True)
        self.touched.append(Path(install.path))
        if isinstance(listed, UnreadableFile):
            if listed.reason == "plugin_outside_plugins":
                self.outside(plan, install, listed)
            elif listed.reason == "vanished":
                if wants:
                    self.not_installed(plan)
                else:
                    plan.status = "unknown"
            else:
                self.unreadable(listed)
                plan.status, plan.may_change = "unknown", True
            return
        plan.version = install.version
        plan.orphans = _orphans(install.path, self.touched)
        if not wants:
            return
        manifest = self.read_manifest(plan, install)
        if manifest is not None:
            self.load_components(plan, install, manifest)

    def read_manifest(self, plan: _Plan, install: _Install) -> JsonObject | None:
        path = os.path.join(install.path, ".claude-plugin", "plugin.json")  # noqa: PTH118
        self.touched.append(Path(path))
        got = _read_json(self.scope, path, plugin=True)
        if got.unreadable is not None:
            self.unreadable(got.unreadable)
            plan.status, plan.may_change = "unknown", True
            return None
        if got.missing:
            return {}
        name = _string_keys(got.data).get("name") if _is_object(got.data) else None
        if got.error_line or not isinstance(name, str) or not name.strip():
            plan.status, plan.reason_code = "invalid", "plugin_manifest_invalid"
            self.problem(
                make_row(
                    code="plugin_manifest_invalid",
                    group="wont_load",
                    thing=plan.plugin_id,
                    part=PART,
                    item_id=plugin_item_id(plan.plugin_id),
                    file=self.scope.display(path),
                    full_path=os.path.abspath(path),  # noqa: PTH100
                    line=got.error_line or 1,
                    level="assumed",
                )
            )
            return None
        manifest = _string_keys(got.data)
        plan.name = name.strip()
        version = manifest.get("version")
        if plan.version is None and isinstance(version, str):
            plan.version = version
        return manifest

    def load_components(
        self, plan: _Plan, install: _Install, manifest: JsonObject
    ) -> None:
        item_id = plugin_item_id(plan.plugin_id)
        parts = _components(install.path, manifest, item_id, plan.plugin_id, plan.name)
        parts.settings = _plugin_settings(self.scope, install.path, self.out.unreadable)
        found = agent_files.find(self.scope, parts.agents, "plugin", plugin=plan.name)
        self.touched.extend(found.touched)
        names = dict.fromkeys(f.name for f in found.files if f.name is not None)
        plan.contents = [agent_files.agent_item_id(n, plan.name) for n in names]
        plan.components = parts
        self.components.append(parts)

    # -- the whole read

    def run(self) -> Collected:
        self.read_marketplaces()
        installed = self.read_installed()
        entries = self.enabled()
        by_id: dict[str, list[EnabledEntry]] = {}
        for entry in entries:
            by_id.setdefault(entry.plugin_id, []).append(entry)
        known: set[str] = {*by_id.keys(), *(installed or {}).keys()}
        ids: list[str] = sorted(known)
        moved = self.moved_cache()
        for plugin_id in ids:
            mine: list[EnabledEntry] = sorted(
                by_id.get(plugin_id, []), key=lambda e: _SCOPE_ORDER.index(e.scope)
            )
            if moved is not None:
                self.plans.append(self.plan_moved(plugin_id, mine, moved))
            else:
                self.plans.append(self.plan_for(plugin_id, mine, installed))
        items = [_build_item(self.ctx, plan, i) for i, plan in enumerate(self.plans)]
        self.out.items[PART] = items
        self.out.unreadable = [
            u.model_copy(update={"part": PART}) for u in self.out.unreadable
        ]
        self.out.handoff[HANDOFF_COMPONENTS] = self.components
        self.out.handoff[HANDOFF_PLUGINS] = handoff_lists(self.components)
        self.out.handoff[HANDOFF_STYLES] = [
            _component_row(c, path) for c in self.components for path in c.output_styles
        ]
        return self.out

    def plan_moved(
        self, plugin_id: str, entries: list[EnabledEntry], cache: str
    ) -> _Plan:
        """A plugin whose cache the environment moved out of ``plugins/``."""
        plan = _Plan(
            plugin_id=plugin_id,
            entries=entries,
            name=plugin_id.split("@", maxsplit=1)[0],
        )
        plan.status, plan.reason_code = "unknown", "plugin_outside_plugins"
        plan.not_read = "plugin_outside_plugins"
        entry = self.scope.unreadable(cache, "outside_scope", plugin=True)
        if all(u.full_path != entry.full_path for u in self.out.unreadable):
            self.unreadable(entry, "plugin")
        self.problem(
            make_row(
                code="plugin_outside_plugins",
                group="cant_tell",
                thing=plugin_id,
                part=PART,
                item_id=plugin_item_id(plugin_id),
                file=entry.file,
                full_path=entry.full_path,
                line=None,
                level="assumed",
            )
        )
        return plan


class PluginsCollector:
    """The ``plugins`` collector. ``COLLECTOR`` is the one instance."""

    name = "plugins"
    parts: Sequence[SetupPart] = (PART,)

    def read(self, ctx: SetupContext, handoff: Mapping[str, object]) -> Collected:
        """Read the plugins of one project. Never raises for a bad file."""
        return _Run(ctx, handoff, read_scope.Scope(ctx)).run()

    def signature(self, ctx: SetupContext, last: Collected | None) -> str:
        """Fingerprint the files and folders the last read touched, with stat only."""
        scope = read_scope.Scope(ctx)
        if last is not None:
            return read_scope.stat_signature(scope, last.touched)
        base = ctx.config_dir / "plugins"
        return read_scope.stat_signature(
            scope, [base / "installed_plugins.json", base / "known_marketplaces.json"]
        )


COLLECTOR = PluginsCollector()

__all__ = [
    "COLLECTOR",
    "HANDOFF_COMPONENTS",
    "HANDOFF_ENABLED",
    "HANDOFF_PLUGINS",
    "HANDOFF_SETTINGS",
    "HANDOFF_STYLES",
    "EnabledEntry",
    "PluginComponents",
    "PluginsCollector",
    "handoff_lists",
    "plugin_item_id",
    "with_contents",
]
