"""The Output style part: the ``outputStyle`` setting and one item per style file.

Style files live in ``<config>/output-styles/`` (user),
``<project>/.claude/output-styles/`` (project) and ``<managed>/.claude/output-styles/``
(managed). A plugin's styles come from the plugin collector's handoff, key
``plugin_output_styles``, a list of mappings with ``name``, ``plugin`` and ``path`` (a
path under ``<config>/plugins/``). The handoff is optional.

Front matter is read with ruamel.yaml in safe mode and only for the ``name`` field. No
file body is read into an item. A file with no ``name`` takes its file name without
``.md``, as Claude Code does (output-styles docs). Clashes between scopes resolve as
managed, then project, then user, then plugin (the first is in effect).

The setting names a style. It is in effect when a style file or a built-in has that
name. The built-ins are ``Proactive``, ``Concise``, ``Explanatory`` and ``Learning``,
case-sensitive (``default`` is Claude Code's default style). A wrong case falls back to
the default style and is Not as set. A name that matches nothing is
``output_style_missing`` (Won't load).
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

import read_scope
import settings_layers
import setup_items
from models import (
    Effective,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    OutputStyleFacts,
    ProblemFix,
    ProblemRow,
    ReadOnly,
    SetupItem,
    SetupScope,
    SetupSource,
    UnreadableFile,
)
from settings_layers import Layers
from setup_contract import FILE_CAP_BYTES, SetupContext

STYLE_DIR = "output-styles"
BUILTINS = ("Proactive", "Concise", "Explanatory", "Learning")
DEFAULT_STYLES = ("default", "Default")
SETTING_ID = "output_style:outputStyle"
PLUGIN_STYLES = "plugin_output_styles"
_RANK: dict[SetupScope, int] = {"managed": 0, "project": 1, "user": 2, "plugin": 3}
_FILE_SCOPES: tuple[SetupScope, ...] = ("managed", "project_local", "project", "user")
_STYLE_SCOPES: tuple[SetupScope, ...] = ("managed", "project", "user", "plugin")
_NAME_LINE = re.compile(r"^name\s*:")


def folders(ctx: SetupContext) -> list[Path]:
    """Return the style folders of a project, top-wins order."""
    found: list[Path] = []
    if ctx.managed_dir is not None:
        found.append(ctx.managed_dir / ".claude" / STYLE_DIR)
    if ctx.project_dir is not None:
        found.append(ctx.project_dir / ".claude" / STYLE_DIR)
    found.append(Path(ctx.config_dir) / STYLE_DIR)
    return found


@dataclass
class _Style:
    """One style file, read."""

    name: str
    scope: SetupScope
    plugin: str | None
    source: SetupSource
    real_path: str | None
    invalid: bool


def _parse_block(block: str) -> tuple[dict[str, object] | None, bool]:
    """Parse front matter YAML in safe mode. Returns (a mapping or None, invalid)."""
    try:
        parsed: object = YAML(typ="safe").load(block)  # pyright: ignore[reportUnknownMemberType]
    except (YAMLError, ValueError, RecursionError):
        return None, True
    if parsed is None:
        return None, False
    if isinstance(parsed, dict):
        return cast("dict[str, object]", parsed), False
    return None, True


def _front_matter(text: str) -> tuple[str | None, int | None, bool]:
    """Return (name, its line, front matter is invalid) for a style file's text."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, None, False
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None, None, True
    table, invalid = _parse_block("\n".join(lines[1:end]))
    name = table.get("name") if table is not None else None
    if invalid or not (isinstance(name, str) and name):
        return None, None, invalid
    at = next((i + 1 for i in range(1, end) if _NAME_LINE.match(lines[i])), None)
    return name, at, False


def _read_style(  # noqa: PLR0913 - one style file's place and owner
    layers: Layers,
    built: setup_items.Built,
    path: Path,
    scope: SetupScope,
    *,
    plugin: str | None = None,
    wanted: str | None = None,
) -> _Style | None:
    got = read_scope.read_text(
        layers.scope, path, FILE_CAP_BYTES, plugin=plugin is not None
    )
    if isinstance(got, UnreadableFile):
        if got.reason != "vanished":
            built.unreadable.append(got)
        return None
    name, line, invalid = _front_matter(got)
    called = name or wanted or path.stem
    shown, full = layers.scope.display(path), str(path.absolute())
    source = setup_items.source_of(
        scope=scope,
        key="name" if name else "file",
        file=shown,
        full_path=full,
        line=line,
        value=None,
        status="invalid" if invalid else "in_effect",
    ).model_copy(update={"plugin": plugin})
    return _Style(
        called,
        scope,
        plugin,
        source,
        read_scope.symlink_target(layers.scope, path),
        invalid,
    )


def _scan(layers: Layers, built: setup_items.Built) -> list[_Style]:
    styles: list[_Style] = []
    ctx = layers.ctx
    pairs: list[tuple[Path, SetupScope]] = []
    if ctx.managed_dir is not None:
        pairs.append((ctx.managed_dir / ".claude" / STYLE_DIR, "managed"))
    if ctx.project_dir is not None:
        pairs.append((ctx.project_dir / ".claude" / STYLE_DIR, "project"))
    pairs.append((Path(ctx.config_dir) / STYLE_DIR, "user"))
    for folder, scope in pairs:
        built.touched.append(folder)
        names = read_scope.list_dir(layers.scope, folder)
        if isinstance(names, UnreadableFile):
            if names.reason != "vanished":
                built.unreadable.append(names)
            continue
        for name in names:
            if name.endswith(".md") and not name.startswith("."):
                path = folder / name
                built.touched.append(path)
                found = _read_style(layers, built, path, scope)
                if found is not None:
                    styles.append(found)
    return styles


def _plugin_styles(
    layers: Layers, built: setup_items.Built, handoff: Mapping[str, object]
) -> list[_Style]:
    raw = handoff.get(PLUGIN_STYLES)
    if not isinstance(raw, list):
        return []
    out: list[_Style] = []
    for row in raw:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(row, Mapping):
            continue
        entry: Mapping[str, object] = row  # pyright: ignore[reportUnknownVariableType]
        plugin, path, wanted = entry.get("plugin"), entry.get("path"), entry.get("name")
        if not (isinstance(plugin, str) and isinstance(path, str)):
            continue
        built.touched.append(Path(path))
        found = _read_style(
            layers,
            built,
            Path(path),
            "plugin",
            plugin=plugin,
            wanted=wanted if isinstance(wanted, str) else None,
        )
        if found is not None:
            out.append(found)
    return out


def _style_items(
    layers: Layers, styles: list[_Style], active: str | None
) -> tuple[list[SetupItem], list[ProblemRow]]:
    by_name: dict[str, list[_Style]] = {}
    for style in sorted(styles, key=lambda s: (_RANK[s.scope], s.source.file or "")):
        by_name.setdefault(style.name, []).append(style)
    items: list[SetupItem] = []
    problems: list[ProblemRow] = []
    for name in sorted(by_name):
        group = by_name[name]
        sources = [
            s.source
            if at == 0
            else s.source.model_copy(update={"status": "overridden"})
            for at, s in enumerate(group)
        ]
        top = group[0]
        status: ModelCheckStatus = "invalid" if top.invalid else "in_effect"
        read_only = (
            ReadOnly(code="plugin", params={"plugin": top.plugin or ""}, command=None)
            if top.scope == "plugin"
            else setup_items.read_only_for(top.scope)
        )
        item = setup_items.make_item(
            part="output_style",
            key=name,
            name=name,
            label_known=True,
            scope=top.scope,
            status=status,
            sources=sources,
            winner=0,
            reach_=setup_items.reach(_STYLE_SCOPES),
            confidence=setup_items.DOCUMENTED,
            reason=ItemReason(code=status, params={}, rule_id=None, ref_item=None),
            facts=ItemFacts(
                output_style=OutputStyleFacts(active=active, builtin=False)
            ),
            read_only=read_only,
            real_path=top.real_path,
            changeable=setup_items.may_change(layers.unreadable, top.scope),
        )
        items.append(item)
        if top.invalid:
            problems.append(
                setup_items.make_problem(
                    code="frontmatter_invalid",
                    group="wont_load",
                    kind="problem",
                    part="output_style",
                    thing=name,
                    item=item,
                    file=top.source.file,
                    full_path=top.source.full_path,
                    line=None,
                    params={},
                    confidence=setup_items.DOCUMENTED,
                    fix=ProblemFix(kind="open_item", target=item.id, reason=None),
                )
            )
    return items, problems


def _setting_item(
    layers: Layers, names: Mapping[str, str]
) -> tuple[SetupItem | None, str | None, list[ProblemRow]]:
    """Return (the setting item, the active style name, its problem rows)."""
    sources: list[SetupSource] = []
    values: list[object] = []
    files: list[settings_layers.LayerFile] = []
    for file in layers.readable():
        value = file.data.get("outputStyle")
        if value is None:
            continue
        files.append(file)
        values.append(value)
        sources.append(
            setup_items.source_of(
                scope=file.scope,
                key="outputStyle",
                file=file.display,
                full_path=file.full_path,
                line=file.lines.get(("outputStyle",)),
                value=settings_layers.display_value(value),
                status="overridden",
            )
        )
    if not sources:
        return None, None, []
    wanted = values[0]
    status: ModelCheckStatus
    ref: str | None = None
    if isinstance(wanted, str) and wanted in names:
        status, ref, active = "in_effect", names[wanted], wanted
    elif isinstance(wanted, str) and (wanted in BUILTINS or wanted in DEFAULT_STYLES):
        status, active = "in_effect", wanted
    elif isinstance(wanted, str) and _falls_back(wanted):
        status, active = "ignored", "default"
    else:
        status, active = "invalid", None
    sources[0] = sources[0].model_copy(update={"status": status})
    shown = sources[0].value
    effective = (
        Effective(
            value=MaskedText(text="default", masked=False),
            origin="default",
            by_item=None,
        )
        if status == "ignored"
        else Effective(
            value=shown,
            origin="unknown" if status == "invalid" else "set",
            by_item=None,
        )
    )
    item = setup_items.make_item(
        part="output_style",
        key="outputStyle",
        name="outputStyle",
        item_id=SETTING_ID,
        label_known=True,
        scope=sources[0].scope,
        status=status,
        sources=sources,
        winner=0,
        reach_=setup_items.reach(_FILE_SCOPES),
        confidence=setup_items.DOCUMENTED,
        reason=ItemReason(code=status, params={}, rule_id=None, ref_item=ref),
        effective=effective,
        facts=ItemFacts(
            output_style=OutputStyleFacts(
                active=active, builtin=isinstance(wanted, str) and wanted in BUILTINS
            )
        ),
        read_only=setup_items.read_only_for(sources[0].scope),
        real_path=files[0].real_path,
        changeable=setup_items.may_change(layers.unreadable, sources[0].scope),
    )
    problems: list[ProblemRow] = []
    if status == "invalid":
        problems.append(
            setup_items.make_problem(
                code="output_style_missing",
                group="wont_load",
                kind="problem",
                part="output_style",
                thing=item.name,
                item=item,
                file=sources[0].file,
                full_path=sources[0].full_path,
                line=sources[0].line,
                params={"style": shown.text if shown is not None else ""},
                confidence=setup_items.DOCUMENTED,
                fix=ProblemFix(kind="open_item", target=item.id, reason=None),
            )
        )
    elif status == "ignored":
        row = setup_items.status_problem(item, sources[0], "ignored")
        if row is not None:
            problems.append(row)
    return item, active, problems


def _falls_back(wanted: str) -> bool:
    """True when only the case differs from a built-in style name."""
    lowered = wanted.lower()
    return any(lowered == b.lower() for b in (*BUILTINS, *DEFAULT_STYLES))


def build(layers: Layers, handoff: Mapping[str, object]) -> setup_items.Built:
    """Build the Output style items and their problem rows.

    Args:
        layers: One read of the project's settings files.
        handoff: What earlier collectors handed on. ``plugin_output_styles`` is read
            when present.

    Returns:
        The setting item first, then one item per style name, sorted. Style files
        that could not be read are in ``unreadable``.
    """
    built = setup_items.Built()
    styles = [*_scan(layers, built), *_plugin_styles(layers, built, handoff)]
    names = {s.name: f"output_style:{s.name}" for s in styles}
    setting, active, setting_problems = _setting_item(layers, names)
    files, file_problems = _style_items(layers, styles, active)
    if setting is not None:
        built.items.append(setting)
    built.items.extend(files)
    built.problems.extend([*setting_problems, *file_problems])
    return built
