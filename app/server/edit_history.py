"""Ledger rows as the Changes page and the recheck read show them (m6-build 4.2, 4.3).

History reads straight from the ledger files of the project's settings targets
(``EditStore.read_rows``), newest first, and adds what a scan of the backups folder
finds for this project in files that are no longer one of its targets. Every value goes
through the masker again, because a ledger sits in a folder the owner can edit.

A row's undo state comes from ``EditStore.row_status``, which works it out from hashes
at read time. The writer's words for "not undoable" map onto
``models.NotUndoableReason``. A word outside the six (a new one, or a state the file
can't be read in) reads as ``file_refused``.

Rows found by the scan carry the ledger's own ``project``, so a row of another project
never shows. They can't be undone, because no registry target holds their file.
"""

import json

# ruff: noqa: PLR0917, PTH208 - a row's parts are many, and ``os.listdir`` takes the
# backups folder's descriptor, which ``pathlib`` can't.
import logging
import os
import re
import stat
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast, get_args

import edit_fields
import edit_store
import masking
from edit_seen import SeenMarks
from edit_store import EditStore, Refused, RowStatus, Target
from models import (
    EditScope,
    HistoryOp,
    HistoryRecheck,
    HistoryRow,
    HistorySubject,
    NotUndoableReason,
    RecheckAnswer,
    RecheckState,
    SettingsEditField,
)

logger = logging.getLogger("bartab.edit")

SCOPES: tuple[EditScope, ...] = ("user", "project", "local")
PER_FILE = 20
MAX_FOLDERS = 200
LATE_MARGIN_SECONDS = 5.0
MAX_LATE_RUNS = 5
MAX_TEXT = 1000
_FOLDER = re.compile(r"^[0-9a-f]{16}$")
_ROW_ID = re.compile(r"^[0-9a-f]{16}$")
_REASONS: frozenset[str] = frozenset(get_args(NotUndoableReason))
_STATES: frozenset[str] = frozenset(get_args(RecheckState))
_KINDS = frozenset({"edit", "undo", "restore"})
Scalar = str | int


@dataclass(frozen=True)
class Found:
    """A ledger row with the registry target that holds its file."""

    target: Target
    row: dict[str, Any]
    siblings: Sequence[dict[str, Any]]


def reason_of(status: RowStatus) -> NotUndoableReason | None:
    """Map the writer's word for a row that can't be undone onto the closed set."""
    if status.undo_state != "not_undoable":
        return None
    if status.reason in _REASONS:
        return cast("NotUndoableReason", status.reason)
    return "file_refused"


def _text(value: object) -> str:
    shown = masking.mask_value(value if isinstance(value, str) else "")
    return str(shown)[:MAX_TEXT]


def _scalar(value: object, name: str | None) -> Scalar | None:
    shown = masking.mask_value(value, name)
    if shown is None or isinstance(shown, bool):
        return None if shown is None else str(shown)
    return shown if isinstance(shown, (str, int)) else str(shown)


def _op_of(row: dict[str, Any]) -> HistoryOp:
    kind = row.get("kind")
    if kind == "undo":
        return "undo"
    if kind == "restore":
        return "restore"
    return "create" if row.get("op") == "create" else "set"


def _key_path(row: dict[str, Any]) -> list[str]:
    raw: object = row.get("key_path")
    if not isinstance(raw, list):
        return []
    return [str(step) for step in cast("list[object]", raw)]


def _field_of(row: dict[str, Any]) -> str:
    named: object = row.get("field")
    if isinstance(named, str) and named in edit_fields.FIELDS:
        return named
    path = _key_path(row)
    last = path[-1] if path else ""
    for name, item in edit_fields.FIELDS.items():
        if (
            last == item.top_key
            or last in item.env_twins
            or last in item.model_settings_fields
        ):
            return name
    return _text(last)


def _subject_of(row: dict[str, Any]) -> HistorySubject:
    raw: object = row.get("subject")
    if isinstance(raw, dict):
        item = cast("dict[str, Any]", raw)
        name = item.get("name")
        if item.get("kind") == "agent" and isinstance(name, str):
            return HistorySubject(kind="agent", name=_text(name))
    return HistorySubject(kind="main", name=None)


def as_scope(value: object) -> EditScope | None:
    """Return ``value`` as an ``EditScope`` when it is one of the three, else None."""
    return next((scope for scope in SCOPES if value == scope), None)


def _scope_of(row: dict[str, Any], target: Target | None) -> EditScope:
    for name in ("scope", "layer"):
        found = as_scope(row.get(name))
        if found is not None:
            return found
    return as_scope(target.scope if target is not None else None) or "project"


def _undone_at(row: dict[str, Any], siblings: Sequence[dict[str, Any]]) -> str | None:
    found = [
        str(item.get("time"))
        for item in siblings
        if item.get("kind") == "undo" and item.get("restored_from") == row.get("id")
    ]
    return max(found) if found else None


def recheck_of(
    row: dict[str, Any], seen: SeenMarks, project: str
) -> HistoryRecheck | None:
    """Return the row's stored recheck, or None for a row that has none."""
    raw: object = row.get("recheck")
    if not isinstance(raw, dict):
        return None
    item = cast("dict[str, Any]", raw)
    state = item.get("state")
    if state not in _STATES:
        return None
    keys: object = item.get("changed_keys")
    survived = item.get("ours_survived")
    return HistoryRecheck(
        state=cast("RecheckState", state),
        changed_keys=[
            _text(key) for key in cast("list[object]", keys) if isinstance(key, str)
        ]
        if isinstance(keys, list)
        else [],
        ours_survived=survived if isinstance(survived, bool) else None,
        seen=seen.is_seen(project, str(row.get("id"))),
    )


def recheck_answer(
    row: dict[str, Any], seen: SeenMarks, project: str, server_time: datetime
) -> RecheckAnswer:
    """Build the answer of the recheck read from a row."""
    recheck = recheck_of(row, seen, project)
    raw: object = row.get("recheck")
    at = cast("dict[str, Any]", raw).get("at") if isinstance(raw, dict) else None
    if recheck is None:
        return RecheckAnswer(
            server_time=server_time,
            state="checking",
            changed_keys=[],
            ours_survived=None,
            checked_at=None,
            seen=seen.is_seen(project, str(row.get("id"))),
        )
    return RecheckAnswer(
        server_time=server_time,
        state=recheck.state,
        changed_keys=recheck.changed_keys,
        ours_survived=recheck.ours_survived,
        checked_at=at if isinstance(at, str) else None,
        seen=recheck.seen,
    )


def history_row(  # noqa: PLR0913 - one row's parts
    target: Target | None,
    row: dict[str, Any],
    status: RowStatus | None,
    siblings: Sequence[dict[str, Any]],
    seen: SeenMarks,
    project: str,
    show: Callable[[str], str],
) -> HistoryRow:
    """Build one history row. ``status`` None means the file isn't a registry target."""
    path = _key_path(row)
    name = path[-1] if path else None
    display = row.get("display_path")
    real = row.get("real_path")
    if target is not None:
        display = display if isinstance(display, str) else target.display_path
        real = real if isinstance(real, str) else display
    state = status.undo_state if status is not None else "not_undoable"
    return HistoryRow(
        id=str(row.get("id")),
        time=str(row.get("time") or ""),
        subject=_subject_of(row),
        field=_field_of(row),
        from_=_scalar(row.get("old_value"), name),
        to=_scalar(row.get("new_value"), name),
        scope=_scope_of(row, target),
        display_path=show(display) if isinstance(display, str) else "",
        real_path=show(real) if isinstance(real, str) else "",
        op=_op_of(row),
        undo_state=state,
        undone_at=_undone_at(row, siblings) if state == "undone" else None,
        recheck=recheck_of(row, seen, project),
        not_undoable_reason=reason_of(status) if status is not None else "file_refused",
    )


def _valid(row: object, project: str) -> bool:
    if not isinstance(row, dict):
        return False
    item = cast("dict[str, Any]", row)
    if not (isinstance(item.get("id"), str) and _ROW_ID.match(item["id"])):
        return False
    if item.get("kind") not in _KINDS:
        return False
    owner = item.get("project")
    return owner is None or owner == project


def read_found(
    store: EditStore, targets: Sequence[Target], project: str
) -> list[Found]:
    """Return every visible row of the registry targets, once each.

    A target the writer refuses (a link that now points outside, a damaged ledger)
    adds no rows. A row that names another project is left out.
    """
    out: list[Found] = []
    ids: set[str] = set()
    for target in targets:
        try:
            rows = store.read_rows(target)
        except Refused:
            continue
        for row in rows:
            if not _valid(row, project) or row["id"] in ids:
                continue
            ids.add(row["id"])
            out.append(Found(target, row, rows))
    return out


def find_row(
    store: EditStore, targets: Sequence[Target], project: str, row_id: str
) -> Found | None:
    """Return the row with this id, or None. A row of another project is None."""
    return next(
        (
            item
            for item in read_found(store, targets, project)
            if item.row["id"] == row_id
        ),
        None,
    )


def due(row: dict[str, Any], now: datetime) -> bool:
    """True when a row's last recheck should have run by now."""
    try:
        saved = datetime.fromisoformat(str(row.get("time")))
    except ValueError:
        return False
    if saved.tzinfo is None:
        saved = saved.replace(tzinfo=UTC)
    wait = edit_store.RECHECK_DELAYS[-1] + LATE_MARGIN_SECONDS
    return now - saved > timedelta(seconds=wait)


def is_stuck(row: dict[str, Any], now: datetime) -> bool:
    """True for a row still ``checking`` past its last due time."""
    raw: object = row.get("recheck")
    if not isinstance(raw, dict):
        return False
    return cast("dict[str, Any]", raw).get("state") == "checking" and due(row, now)


def scan_other_rows(
    backups_root: str, skip: set[str], project: str
) -> list[dict[str, Any]]:
    """Read ledgers of other files for rows that carry this project's key.

    Every open is by descriptor with ``O_NOFOLLOW``, a ledger must be a regular file the
    user owns under the size cap, and at most ``MAX_FOLDERS`` folders are read.

    Args:
        backups_root: The backups folder.
        skip: Folder names (target ids) the registry targets already cover.
        project: The project key.

    Returns:
        The newest ``PER_FILE`` rows of each ledger that name the project.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        root = os.open(backups_root, flags)
    except OSError:
        return []
    found: list[dict[str, Any]] = []
    try:
        names = sorted(
            name
            for name in os.listdir(root)
            if _FOLDER.match(name) and name not in skip
        )[:MAX_FOLDERS]
        for name in names:
            found.extend(_scan_one(root, name, project))
    except OSError:
        return found
    finally:
        os.close(root)
    return found


def _scan_one(root: int, name: str, project: str) -> list[dict[str, Any]]:
    try:
        folder = os.open(
            name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root
        )
    except OSError:
        return []
    try:
        leaf = os.open(
            edit_store.LEDGER_FILE,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=folder,
        )
    except OSError:
        os.close(folder)
        return []
    try:
        info = os.fstat(leaf)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_size > edit_store.MAX_LEDGER
        ):
            return []
        data = os.read(leaf, edit_store.MAX_LEDGER + 1)
    except OSError:
        return []
    finally:
        os.close(leaf)
        os.close(folder)
    return _own_rows(data, project)


def _own_rows(data: bytes, project: str) -> list[dict[str, Any]]:
    try:
        doc: object = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        return []
    if not isinstance(doc, dict):
        return []
    table = cast("dict[str, Any]", doc)
    rows: object = table.get("rows")
    if table.get("version") != 1 or not isinstance(rows, list):
        return []
    mine = [
        cast("dict[str, Any]", row)
        for row in cast("list[object]", rows)
        if _valid(row, project)
        and cast("dict[str, Any]", row).get("project") == project
    ]
    return mine[-PER_FILE:]


def newest_first(rows: list[HistoryRow]) -> list[HistoryRow]:
    """Sort rows newest first by time, then id."""
    return sorted(rows, key=lambda item: (item.time, item.id), reverse=True)


def field_of_item(item: str | None) -> SettingsEditField | None:
    """Return the settings field an item id edits, or None."""
    return None if item is None else edit_fields.field_for_item(item)
