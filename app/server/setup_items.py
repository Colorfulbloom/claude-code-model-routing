"""Small builders the setup collectors share (m4-build.md section 5).

``make_item`` fills the fields every item carries and leaves the part's own ones to the
caller. ``make_problem`` builds one To fix row with the stable id the corpus uses,
``<code>:<subject>[:<line>]``. Nothing here reads a file.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import settings_layers
from models import (
    SETUP_PARTS,
    SETUP_SCOPES,
    Confidence,
    ConfidenceLevel,
    Effective,
    ItemFacts,
    ItemReason,
    MaskedText,
    ModelCheckStatus,
    NotReadCode,
    ProblemFix,
    ProblemGroup,
    ProblemKind,
    ProblemRow,
    ReadOnly,
    ScopeReach,
    SetupItem,
    SetupPart,
    SetupScope,
    SetupSource,
    UnreadableFile,
)

DOCUMENTED = Confidence(level="documented", tested_on=None)
ASSUMED = Confidence(level="assumed", tested_on=None)

PROBLEM_GROUPS: tuple[ProblemGroup, ...] = (
    "couldnt_read",
    "wont_load",
    "not_as_set",
    "cant_tell",
    "notice",
)

# Statuses that make a To fix row, and the row they make: (kind, group, code).
_STATUS_PROBLEM: dict[str, tuple[ProblemKind, ProblemGroup, str]] = {
    "invalid": ("problem", "wont_load", "value_invalid"),
    "ignored": ("problem", "not_as_set", "ignored"),
    "lowered": ("problem", "not_as_set", "lowered"),
    "unknown": ("cant_tell", "cant_tell", "unknown"),
}


@dataclass
class Built:
    """What one part's builder returns: items, problem rows, files it could not read."""

    items: list[SetupItem] = field(default_factory=list[SetupItem])
    problems: list[ProblemRow] = field(default_factory=list[ProblemRow])
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    touched: list[Path] = field(default_factory=list[Path])


def rule_confidence(rule_id: str | None) -> Confidence:
    """Return the confidence of a resolver rule, from rules.json.

    ``tested_on`` is the Claude Code version a test ran on, set only for a tested rule.
    A rule the file doesn't know is ``documented``.
    """
    if rule_id is not None:
        for rule in settings_layers.rules()["rules"]:
            if rule["rule_id"] == rule_id:
                level: ConfidenceLevel = rule.get("confidence", "documented")
                verified: dict[str, str] = rule.get("verified_on") or {}
                version = verified.get("claude_version")
                return Confidence(
                    level=level, tested_on=version if level == "tested" else None
                )
    return DOCUMENTED


def reach(
    visible: Iterable[SetupScope], hidden: Iterable[SetupScope] = ()
) -> list[ScopeReach]:
    """Return the scopes that could set an item, in top-wins order.

    Args:
        visible: Scopes the server can read.
        hidden: Scopes it can't (Shell, Command line), which come back ``visible``
            False.
    """
    seen = set(visible)
    blind = set(hidden)
    return [
        ScopeReach(scope=scope, visible=scope in seen)
        for scope in SETUP_SCOPES
        if scope in seen or scope in blind
    ]


def read_only_for(scope: SetupScope | None) -> ReadOnly | None:
    """Return why an item can't change here, from the scope of its winning value."""
    if scope == "managed":
        return ReadOnly(code="managed", params={}, command=None)
    if scope == "command_line":
        return ReadOnly(code="command_line", params={}, command=None)
    if scope == "shell":
        return ReadOnly(code="not_visible", params={}, command=None)
    return None


def may_change(
    unreadable: Sequence[UnreadableFile], winner_scope: SetupScope | None
) -> bool:
    """True when a file that could not be read could change this item's answer.

    A failed file can change a value only when its scope ranks at or above the scope
    the value comes from (an item with no winning scope counts every failed file).
    A file the scope refused ("not read here") is not a failure.
    """
    rank = (
        SETUP_SCOPES.index(winner_scope)
        if winner_scope is not None
        else len(SETUP_SCOPES)
    )
    return any(
        file.reason not in ("outside_scope", "plugin_outside_plugins")
        and (file.scope is None or SETUP_SCOPES.index(file.scope) <= rank)
        for file in unreadable
    )


def make_item(  # noqa: PLR0913 - the model's own fields
    *,
    part: SetupPart,
    key: str,
    name: str,
    item_id: str | None = None,
    label_known: bool,
    scope: SetupScope | None,
    status: ModelCheckStatus,
    sources: list[SetupSource],
    winner: int | None,
    reach_: list[ScopeReach],
    confidence: Confidence,
    reason: ItemReason | None,
    effective: Effective | None = None,
    group: str | None = None,
    facts: ItemFacts | None = None,
    read_only: ReadOnly | None = None,
    real_path: str | None = None,
    not_read: NotReadCode | None = None,
    changeable: bool = False,
) -> SetupItem:
    """Build one item. ``order`` is 0 until ``number`` sets it."""
    return SetupItem(
        id=item_id if item_id is not None else f"{part}:{key}",
        part=part,
        key=key,
        name=name,
        label_known=label_known,
        order=0,
        group=group,
        scope=scope,
        effective=effective,
        sources=sources,
        winner=winner,
        reach=reach_,
        status=status,
        reason=reason,
        confidence=confidence,
        loads=None,
        applies=None,
        writable=False,
        read_only_reason=read_only,
        risk_tier=None,
        feature="core",
        facts=facts if facts is not None else ItemFacts(),
        usage=None,
        real_path=real_path,
        not_read=not_read,
        may_change=changeable,
    )


def number(items: list[SetupItem]) -> list[SetupItem]:
    """Set each item's ``order`` to its place in the list and return the list."""
    return [item.model_copy(update={"order": at}) for at, item in enumerate(items)]


def problem_id(code: str, subject: str, line: int | None) -> str:
    """Return the stable id of a To fix row: ``code:subject[:line]``."""
    return f"{code}:{subject}" + ("" if line is None else f":{line}")


def make_problem(  # noqa: PLR0913 - the model's own fields
    *,
    code: str,
    group: ProblemGroup,
    kind: ProblemKind,
    part: SetupPart,
    thing: str,
    item: SetupItem | None,
    file: str | None,
    full_path: str | None,
    line: int | None,
    params: dict[str, str],
    confidence: Confidence,
    fix: ProblemFix,
    subject: str | None = None,
) -> ProblemRow:
    """Build one To fix row. The subject is the item id, else the display file."""
    name = subject or (item.id if item is not None else None) or file or thing
    return ProblemRow(
        id=problem_id(code, name, line),
        kind=kind,
        group=group,
        code=code,
        thing=thing,
        part=part,
        item_id=item.id if item is not None else None,
        file=file,
        full_path=full_path,
        line=line,
        params=params,
        confidence=confidence,
        fix=fix,
    )


def status_problem(
    item: SetupItem, source: SetupSource, status: ModelCheckStatus
) -> ProblemRow | None:
    """Return the To fix row a source's status makes, or None for a normal status.

    Invalid is Won't load (``value_invalid``), ignored and lowered are Not as set,
    unknown is Can't tell. Overridden, in effect and default make none.
    """
    row = _STATUS_PROBLEM.get(status)
    if row is None:
        return None
    kind, group, code = row
    params = {"key": source.key}
    if source.value is not None:
        params["value"] = source.value.text
    return make_problem(
        code=code,
        group=group,
        kind=kind,
        part=item.part,
        thing=item.name,
        item=item,
        file=source.file,
        full_path=source.full_path,
        line=source.line,
        params=params,
        confidence=item.confidence,
        fix=ProblemFix(kind="open_item", target=item.id, reason=None),
    )


def file_problem(  # noqa: PLR0913 - the model's own fields
    *,
    code: str,
    part: SetupPart,
    file: str,
    full_path: str,
    line: int | None,
    managed: bool,
    params: dict[str, str] | None = None,
) -> ProblemRow:
    """Return a Won't load row for a whole file.

    A whole file is bad JSON or a top level that isn't an object. A managed file can't
    be fixed here, and any other can be copied to open.
    """
    fix = (
        ProblemFix(kind="cant_fix_here", target=None, reason="managed")
        if managed
        else ProblemFix(kind="copy_path", target=full_path, reason=None)
    )
    return make_problem(
        code=code,
        group="wont_load",
        kind="problem",
        part=part,
        thing=file,
        item=None,
        file=file,
        full_path=full_path,
        line=line,
        params=params or {},
        confidence=DOCUMENTED,
        fix=fix,
    )


def sort_problems(rows: Iterable[ProblemRow]) -> list[ProblemRow]:
    """Sort rows by group, part order, file and line, as the corpus does."""
    return sorted(
        rows,
        key=lambda row: (
            PROBLEM_GROUPS.index(row.group),
            SETUP_PARTS.index(row.part) if row.part is not None else -1,
            row.file or "",
            row.line or 0,
            row.id,
        ),
    )


def source_of(  # noqa: PLR0913 - the model's own fields
    *,
    scope: SetupScope,
    key: str,
    file: str | None,
    full_path: str | None,
    line: int | None,
    value: MaskedText | None,
    status: ModelCheckStatus,
) -> SetupSource:
    """Build a source. ``value`` is a ``MaskedText`` or None."""
    return SetupSource(
        scope=scope,
        key=key,
        file=file,
        full_path=full_path,
        line=line,
        value=value,
        status=status,
        plugin=None,
    )
