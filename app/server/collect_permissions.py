"""The Permissions part: one item per rule, ``defaultMode`` and extra folder.

Items come from every settings file that parsed, each file read on its own so a rule's
line is the line in its own file. A rule that several files hold is one item with a
source per file (``permissions:<kind>:<rule>`` carries no scope, so the id survives a
rule moving between scopes). Order is deny, ask, allow, ``defaultMode``, folders, then
scope top-wins, then file order, and it never changes between reads.

A rule is a bare tool name or ``Tool(specifier)`` (permissions docs, m4-build.md section
16, "Task 1 results"). Anything else is ``permission_rule_invalid`` (Won't load).
``defaultMode`` ``auto`` and ``bypassPermissions`` are ignored in project and local
settings (settings-reference), so they are Not as set there.

A rule can hold a secret inside a command, so its text goes through ``masking`` before
it reaches an id, a key or a pattern. Two different secret rules that mask alike get a
``#n`` on the later id, so ids stay unique.
"""

import re
from dataclasses import dataclass, field
from typing import cast

import settings_layers
import setup_items
from models import (
    Effective,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    PermissionFacts,
    PermissionKind,
    ProblemFix,
    ProblemRow,
    SetupItem,
    SetupScope,
    SetupSource,
)
from settings_layers import LayerFile, Layers

RULE_KINDS: tuple[PermissionKind, ...] = ("deny", "ask", "allow")
# defaultMode values from settings-reference. ``manual`` is the alias of ``default``.
MODES = frozenset(
    {"default", "manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions"}
)
IGNORED_FROM_PROJECT = frozenset({"auto", "bypassPermissions"})
_FILE_SCOPES: tuple[SetupScope, ...] = ("managed", "project_local", "project", "user")
_RULE = re.compile(r"^(?P<tool>[A-Za-z_][\w.\-:*]*)(?:\((?P<spec>.+)\))?$", re.DOTALL)


def parse_rule(rule: object) -> tuple[bool, str | None, str | None]:
    """Parse a permission rule.

    Args:
        rule: The rule as written.

    Returns:
        (valid, tool, pattern). A bare tool name has no pattern. An invalid rule
        returns (False, None, None).
    """
    if not isinstance(rule, str):
        return False, None, None
    found = _RULE.match(rule.strip())
    if found is None:
        return False, None, None
    return True, found.group("tool"), found.group("spec")


@dataclass
class _Acc:
    """One item being collected: its sources, in top-wins order."""

    kind: PermissionKind
    key: str
    valid: bool
    tool: str | None
    pattern: str | None
    sources: list[SetupSource] = field(default_factory=list[SetupSource])
    files: list[LayerFile] = field(default_factory=list[LayerFile])


def _shown(value: object) -> str:
    return settings_layers.display_value(value).text


def _list_items(
    layers: Layers, kind: PermissionKind, key: str
) -> list[tuple[LayerFile, object, int | None]]:
    """Return (file, entry, line) for every entry of one list, top-wins file order."""
    out: list[tuple[LayerFile, object, int | None]] = []
    for file in layers.readable():
        block = file.data.get("permissions")
        if not isinstance(block, dict):
            continue
        found = cast("dict[str, object]", block).get(key)
        if not isinstance(found, list):
            continue
        entries = cast("list[object]", found)
        for at, entry in enumerate(entries):
            before = sum(1 for earlier in entries[:at] if earlier == entry)
            line = settings_layers.list_item_line(
                file, ("permissions", key), entry, before
            )
            out.append((file, entry, line))
    return out


def _unique(wanted: str, taken: set[str]) -> str:
    key, n = wanted, 1
    while key in taken:
        n += 1
        key = f"{wanted}#{n}"
    return key


def _rules(layers: Layers, kind: PermissionKind, key: str) -> list[_Acc]:
    """Group one list's entries into items, in first-seen order."""
    accs: dict[str, _Acc] = {}
    for file, entry, line in _list_items(layers, kind, key):
        if kind == "directory":
            valid, tool, pattern = isinstance(entry, str) and entry != "", None, None
        else:
            valid, tool, pattern = parse_rule(entry)
        raw = settings_layers.json_text(entry)
        acc = accs.get(raw)
        if acc is None:
            acc = accs[raw] = _Acc(
                kind=kind,
                key=_shown(entry),
                valid=valid,
                tool=_shown(tool) if tool is not None else None,
                pattern=_shown(pattern) if pattern is not None else None,
            )
        acc.files.append(file)
        acc.sources.append(
            setup_items.source_of(
                scope=file.scope,
                key=f"permissions.{key}",
                file=file.display,
                full_path=file.full_path,
                line=line,
                value=None,
                status="in_effect" if valid else "invalid",
            )
        )
    return list(accs.values())


def _item(layers: Layers, acc: _Acc, item_id: str) -> SetupItem:
    status: ModelCheckStatus = "in_effect" if acc.valid else "invalid"
    top = acc.sources[0]
    return setup_items.make_item(
        part="permissions",
        key=acc.key,
        name=acc.key,
        item_id=item_id,
        label_known=True,
        scope=top.scope,
        status=status,
        sources=acc.sources,
        winner=0,
        reach_=setup_items.reach(_FILE_SCOPES),
        confidence=setup_items.DOCUMENTED,
        reason=ItemReason(code=status, params={}, rule_id=None, ref_item=None),
        group=acc.kind,
        facts=ItemFacts(
            permission=PermissionFacts(
                kind=acc.kind, tool=acc.tool, pattern=acc.pattern
            )
        ),
        read_only=setup_items.read_only_for(top.scope),
        real_path=acc.files[0].real_path,
        changeable=setup_items.may_change(layers.unreadable, top.scope),
    )


def _default_mode(layers: Layers) -> tuple[SetupItem | None, list[ProblemRow]]:
    sources: list[SetupSource] = []
    files: list[LayerFile] = []
    for file in layers.readable():
        block = file.data.get("permissions")
        mode: object = (
            cast("dict[str, object]", block).get("defaultMode")
            if isinstance(block, dict)
            else None
        )
        if mode is None:
            continue
        status: ModelCheckStatus = "in_effect"
        if not isinstance(mode, str) or mode not in MODES:
            status = "invalid"
        elif file.layer in ("project", "local") and mode in IGNORED_FROM_PROJECT:
            status = "ignored"
        files.append(file)
        sources.append(
            setup_items.source_of(
                scope=file.scope,
                key="permissions.defaultMode",
                file=file.display,
                full_path=file.full_path,
                line=file.lines.get(("permissions", "defaultMode")),
                value=settings_layers.display_value(mode),
                status=status,
            )
        )
    if not sources:
        return None, []
    live = [at for at, s in enumerate(sources) if s.status == "in_effect"]
    for at in live[1:]:
        sources[at] = sources[at].model_copy(update={"status": "overridden"})
    win = live[0] if live else None
    if win is not None:
        status = "in_effect"
        effective = Effective(value=sources[win].value, origin="set", by_item=None)
    else:
        status = "invalid" if any(s.status == "invalid" for s in sources) else "ignored"
        effective = Effective(
            value=MaskedText(text="default", masked=False),
            origin="default",
            by_item=None,
        )
    scope = sources[win].scope if win is not None else None
    item = setup_items.make_item(
        part="permissions",
        key="defaultMode",
        name="defaultMode",
        label_known=True,
        scope=scope,
        status=status,
        sources=sources,
        winner=win,
        reach_=setup_items.reach(_FILE_SCOPES),
        confidence=setup_items.DOCUMENTED,
        reason=ItemReason(code=status, params={}, rule_id=None, ref_item=None),
        effective=effective,
        group="default_mode",
        facts=ItemFacts(
            permission=PermissionFacts(kind="default_mode", tool=None, pattern=None)
        ),
        read_only=setup_items.read_only_for(scope),
        real_path=files[win].real_path if win is not None else None,
        changeable=setup_items.may_change(layers.unreadable, scope),
    )
    problems = [
        row
        for src in sources
        if src.status in ("invalid", "ignored")
        and (row := setup_items.status_problem(item, src, src.status)) is not None
    ]
    return item, problems


def build(layers: Layers) -> setup_items.Built:
    """Build the Permissions items and their problem rows from the settings files.

    Args:
        layers: One read of the project's settings files.

    Returns:
        The items in order (deny, ask, allow, ``defaultMode``, folders) and the Won't
        load and Not as set rows. A file that failed to parse has no rules here, and
        the Settings part reports it once.
    """
    built = setup_items.Built()
    taken: set[str] = set()
    for kind in RULE_KINDS:
        for acc in _rules(layers, kind, kind):
            item_id = _unique(f"permissions:{kind}:{acc.key}", taken)
            taken.add(item_id)
            item = _item(layers, acc, item_id)
            built.items.append(item)
            if not acc.valid:
                built.problems.extend(_invalid_rule(item))
    mode, mode_problems = _default_mode(layers)
    if mode is not None:
        built.items.append(mode)
        built.problems.extend(mode_problems)
    for acc in _rules(layers, "directory", "additionalDirectories"):
        item_id = _unique(f"permissions:directory:{acc.key}", taken)
        taken.add(item_id)
        built.items.append(_item(layers, acc, item_id))
    return built


def _invalid_rule(item: SetupItem) -> list[ProblemRow]:
    rows: list[ProblemRow] = []
    for src in item.sources:
        rows.append(
            setup_items.make_problem(
                code="permission_rule_invalid",
                group="wont_load",
                kind="problem",
                part="permissions",
                thing=item.name,
                item=item,
                file=src.file,
                full_path=src.full_path,
                line=src.line,
                params={"kind": item.group or "", "rule": item.name},
                confidence=item.confidence,
                fix=ProblemFix(kind="open_item", target=item.id, reason=None),
            )
        )
    return rows
