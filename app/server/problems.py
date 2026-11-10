"""The problems feed behind To fix (m4-build.md sections 5 and 16, task 9).

``build_rows`` joins what every collector reported into one list of rows:

- each collector's problem rows (Won't load, Not as set, Can't tell, Notices);
- a Couldn't read row for every file a collector could not read, coded by the reason
  (a file outside the allowed roots is "not read here" and makes no row);
- a Couldn't read row coded ``transcript_unreadable`` for each transcript the ingest
  could not open (leftover 2 of the plan);
- the ``rows_no_usage`` notice when the ingest kept transcript rows that carry no
  usage.

Overridden is never a row: no collector makes one, and a status that is not a
problem is never turned into one here. Rows come sorted by group, part, file and line.

Fix rules, applied to every row (owner decisions 7 and 8):

- Couldn't read gets ``copy_path`` with the file's ``full_path``.
- A row about a user or local MCP server gets ``copy_command`` with the masked
  ``claude mcp remove`` command that sits on the item's ``ReadOnly.command``. Bar Tab
  only offers the text and never runs it. Can't tell rows keep ``open_item``, because
  removing a server does not answer "I can't tell".
- A row whose cause sits in a managed file or in a plugin's files gets
  ``cant_fix_here`` with the reason ``managed`` or ``plugin``. The cause is the file the
  row names; with no file, the owner of the item. A plugin that is enabled but not
  installed names the settings file that enables it, so that row is not a plugin's.
- An agent a cap lowers (``agent_lowered``) gets ``open_item`` for the cap the collector
  names, or ``cant_fix_here`` with the reason ``managed`` when a managed file sets the
  cap. A cap that is no item of the setup leaves the general rules to apply.
- Any other row about an item gets ``open_item``, and any other row about a file keeps
  the collector's ``copy_path``.

Nothing here reads a file. Paths in rows are display paths, except ``full_path``.
"""

import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import setup_codes
import setup_items
from models import (
    ProblemFix,
    ProblemRow,
    SetupItem,
    SetupPart,
    SetupScope,
    UnreadableFile,
)
from setup_contract import Collected

COUNTED_GROUPS = frozenset({"couldnt_read", "wont_load", "not_as_set"})
TRANSCRIPT_CODE = "transcript_unreadable"
NO_USAGE_CODE = "rows_no_usage"
AGENT_LOWERED_CODE = "agent_lowered"

ScopeOf = Callable[[str], SetupScope | None]
Display = Callable[[str], str]


@dataclass(frozen=True)
class Transcripts:
    """What the ingest knows about the project's transcripts.

    Attributes:
        unreadable: Absolute paths of the transcripts the ingest could not open.
        no_usage_rows: How many transcript files hold rows without usage.
    """

    unreadable: tuple[str, ...] = ()
    no_usage_rows: int = 0


def read_failure_id(reason: str, file: str) -> str:
    """Return the stable id of a Couldn't read row: ``<reason>:<display file>``."""
    return setup_items.problem_id(reason, file, None)


def is_read_failure(file: UnreadableFile) -> bool:
    """True when the file was tried and failed, False for "not read here"."""
    return file.reason not in setup_codes.NOT_READ_REASONS


def _copy_path(full_path: str | None) -> ProblemFix:
    if full_path is None:
        return ProblemFix(kind="cant_fix_here", target=None, reason="not_visible")
    return ProblemFix(kind="copy_path", target=full_path, reason=None)


def _read_failure_row(file: UnreadableFile, part: SetupPart | None) -> ProblemRow:
    return setup_items.make_problem(
        code=file.reason,
        group="couldnt_read",
        kind="read_failure",
        part=part,  # pyright: ignore[reportArgumentType]
        thing=file.file,
        item=None,
        file=file.file,
        full_path=file.full_path,
        line=None,
        params={},
        confidence=setup_items.DOCUMENTED,
        fix=_copy_path(file.full_path),
        subject=file.file,
    )


def _transcript_row(path: str, display: Display) -> ProblemRow:
    shown = display(path)
    return setup_items.make_problem(
        code=TRANSCRIPT_CODE,
        group="couldnt_read",
        kind="read_failure",
        part=None,  # pyright: ignore[reportArgumentType]
        thing=os.path.basename(path) or shown,  # noqa: PTH119
        item=None,
        file=shown,
        full_path=path,
        line=None,
        params={},
        confidence=setup_items.DOCUMENTED,
        fix=_copy_path(path),
        subject=shown,
    )


def _no_usage_row(count: int) -> ProblemRow:
    return setup_items.make_problem(
        code=NO_USAGE_CODE,
        group="notice",
        kind="notice",
        part=None,  # pyright: ignore[reportArgumentType]
        thing="transcripts",
        item=None,
        file=None,
        full_path=None,
        line=None,
        params={"count": str(count)},
        confidence=setup_items.DOCUMENTED,
        fix=ProblemFix(kind="cant_fix_here", target=None, reason="not_fixable"),
        subject="transcripts",
    )


def _cap_fix(row: ProblemRow, cap: SetupItem | None) -> ProblemFix | None:
    """Return the fix of an agent a cap lowers, or None for any other row.

    The collector names the cap in ``row.fix.target``. A managed cap can't be changed
    here. A cap that is no item of the setup leaves the general rules to apply.
    """
    if row.code != AGENT_LOWERED_CODE or cap is None or row.fix.kind != "open_item":
        return None
    only = cap.read_only_reason
    owner = only.code if only is not None else cap.scope
    if owner == "managed":
        return ProblemFix(kind="cant_fix_here", target=None, reason="managed")
    return row.fix


def _fixed(row: ProblemRow, item: SetupItem | None, scope_of: ScopeOf) -> ProblemFix:
    """Return the one action a row offers, by the fix rules in the module docstring."""
    if row.group == "couldnt_read":
        return _copy_path(row.full_path)
    if row.group == "notice":
        return row.fix
    only = item.read_only_reason if item is not None else None
    if (
        row.group in ("wont_load", "not_as_set")
        and only is not None
        and only.code == "claude_json_command"
        and only.command is not None
    ):
        return ProblemFix(kind="copy_command", target=only.command.text, reason=None)
    owner: str | None = scope_of(row.full_path) if row.full_path is not None else None
    if owner is None and item is not None:
        owner = only.code if only is not None else item.scope
    if owner in ("managed", "plugin"):
        return ProblemFix(kind="cant_fix_here", target=None, reason=owner)
    if item is not None:
        return ProblemFix(kind="open_item", target=item.id, reason=None)
    return row.fix


def build_rows(
    collected: Sequence[tuple[Collected, Sequence[SetupPart]]],
    items: Mapping[str, SetupItem],
    transcripts: Transcripts,
    *,
    scope_of: ScopeOf,
    display: Display,
) -> list[ProblemRow]:
    """Join every collector's findings and the ingest's into the sorted feed.

    Args:
        collected: Each collector's result with the parts the collector feeds, in run
            order.
        items: Every item the collectors made, by id.
        transcripts: The unreadable transcripts and the no-usage count.
        scope_of: Maps an absolute path to the setup scope it sits in.
        display: Maps an absolute path to its display path.

    Returns:
        The rows, deduplicated by id, with the fix rules applied.
    """
    rows: dict[str, ProblemRow] = {}
    for got, parts in collected:
        for row in got.problems:
            rows.setdefault(row.id, row)
        for file in got.unreadable:
            if not is_read_failure(file):
                continue
            part = file.part if file.part is not None else (parts[0] if parts else None)
            made = _read_failure_row(file, part)
            rows.setdefault(made.id, made)
    for path in transcripts.unreadable:
        made = _transcript_row(path, display)
        rows.setdefault(made.id, made)
    if transcripts.no_usage_rows > 0:
        made = _no_usage_row(transcripts.no_usage_rows)
        rows.setdefault(made.id, made)
    fixed = [
        row.model_copy(
            update={
                "fix": _cap_fix(
                    row, items.get(row.fix.target) if row.fix.target else None
                )
                or _fixed(
                    row,
                    items.get(row.item_id) if row.item_id is not None else None,
                    scope_of,
                )
            }
        )
        for row in rows.values()
    ]
    return setup_items.sort_problems(fixed)


def counted(rows: Iterable[ProblemRow]) -> int:
    """Count the rows that are Couldn't read, Won't load or Not as set."""
    return sum(1 for row in rows if row.group in COUNTED_GROUPS)
