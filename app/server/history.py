"""The history status the page shows, and the pass bookkeeping in ``meta``.

Times are timezone-aware UTC ``datetime`` values in Python and canonical UTC text
(``2026-01-01T00:00:00Z``) in the store, so text order is time order.

``meta`` keys written here (values are text):

- ``first_ingest``: UTC time the first full pass finished. Set once, never changed.
- ``last_pass``: UTC time the last good pass finished. Read as ``as_of``.
- ``pass_running_since``: UTC time the running pass started. Absent when idle.
- ``pass_error``: JSON ``{"code": str, "file": str | null, "since": UTC time}``.
  ``since`` keeps the first failure time until a good pass clears the key.
"""

import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

logger = logging.getLogger(__name__)

KEY_FIRST_INGEST = "first_ingest"
KEY_AS_OF = "last_pass"
KEY_RUNNING = "pass_running_since"
KEY_FAILURE = "pass_error"

PassEvent = Literal["start", "ok", "failed"]


def utc_text(moment: datetime) -> str:
    """Return the canonical UTC text for an aware ``datetime``.

    Raises:
        ValueError: ``moment`` has no timezone.
    """
    if moment.tzinfo is None:
        msg = "naive datetime"
        raise ValueError(msg)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> datetime:
    """Parse stored UTC text into an aware UTC ``datetime``."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


@contextmanager
def transaction(conn: sqlite3.Connection) -> Generator[None]:
    """Run a block in ``BEGIN IMMEDIATE`` and ``COMMIT`` unless one is open.

    When the caller already holds a transaction it owns the boundary, and this does
    nothing. Otherwise the block commits on success and rolls back on an error.
    """
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@dataclass(frozen=True)
class BackupFailure:
    """The newest backup attempt, when it failed and no good copy followed."""

    at: datetime
    reason_code: str


@dataclass(frozen=True)
class PassError:
    """A whole-pass failure. ``since`` is the first failure of this streak."""

    code: str
    file: str | None
    since: datetime


@dataclass(frozen=True)
class HistoryStatus:
    """What ``/api/app`` reports under ``history``, plus the pass times."""

    oldest: datetime | None
    first_ingest: datetime | None
    last_backup: datetime | None
    backup_failed: BackupFailure | None
    pass_error: PassError | None
    unreadable_files: int
    kept_files: int
    no_usage_rows: int
    as_of: datetime | None
    pass_running_since: datetime | None


def _meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row[0])


def _meta_time(conn: sqlite3.Connection, key: str) -> datetime | None:
    text = _meta(conn, key)
    if text is None:
        return None
    try:
        return parse_utc(text)
    except ValueError:
        logger.warning("meta %s is not a time", key)
        return None


def _pass_error(conn: sqlite3.Connection) -> PassError | None:
    text = _meta(conn, KEY_FAILURE)
    if text is None:
        return None
    try:
        data = json.loads(text)
        file = data.get("file")
        return PassError(
            code=str(data["code"]),
            file=None if file is None else str(file),
            since=parse_utc(str(data["since"])),
        )
    except (ValueError, KeyError, AttributeError, TypeError):
        logger.warning("meta pass_error is malformed")
        return None


def _backup_state(
    conn: sqlite3.Connection,
) -> tuple[datetime | None, BackupFailure | None]:
    ok = conn.execute(
        "SELECT id, at FROM backups WHERE ok = 1 ORDER BY at DESC, id DESC LIMIT 1"
    ).fetchone()
    last = conn.execute(
        "SELECT id, at, ok, reason_code FROM backups ORDER BY at DESC, id DESC LIMIT 1"
    ).fetchone()
    last_ok = None if ok is None else parse_utc(ok[1])
    failed = None
    if last is not None and not last[2] and (ok is None or last[0] > ok[0]):
        failed = BackupFailure(parse_utc(last[1]), str(last[3] or "copy_failed"))
    return last_ok, failed


def read_history(conn: sqlite3.Connection) -> HistoryStatus:
    """Read the history status in one read transaction.

    Opens a deferred transaction and ends it, unless the caller already holds one.
    """
    own = not conn.in_transaction
    if own:
        conn.execute("BEGIN")
    try:
        oldest_row = conn.execute("SELECT MIN(ts) FROM best_winners").fetchone()
        counts = conn.execute(
            "SELECT"
            " COALESCE(SUM(read_errors > 0), 0),"
            " COALESCE(SUM(missing = 1), 0),"
            " COALESCE(SUM(no_usage), 0)"
            " FROM files"
        ).fetchone()
        last_backup, backup_failed = _backup_state(conn)
        return HistoryStatus(
            oldest=parse_utc(oldest_row[0]) if oldest_row[0] else None,
            first_ingest=_meta_time(conn, KEY_FIRST_INGEST),
            last_backup=last_backup,
            backup_failed=backup_failed,
            pass_error=_pass_error(conn),
            unreadable_files=int(counts[0]),
            kept_files=int(counts[1]),
            no_usage_rows=int(counts[2]),
            as_of=_meta_time(conn, KEY_AS_OF),
            pass_running_since=_meta_time(conn, KEY_RUNNING),
        )
    finally:
        if own:
            conn.execute("COMMIT")


def _set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def write_pass_meta(  # noqa: PLR0913 - one event, keyword-only details
    conn: sqlite3.Connection,
    event: PassEvent,
    *,
    at: datetime,
    full: bool = False,
    code: str | None = None,
    file: str | None = None,
) -> None:
    """Record a pass event in ``meta`` on the writer connection.

    Uses ``transaction``, so inside the writer's own ``BEGIN IMMEDIATE`` it only
    adds statements, and on its own it commits at once.

    ``start`` sets ``pass_running_since``. ``ok`` sets ``last_pass``, clears
    ``pass_running_since`` and ``pass_error``, and when ``full`` is true sets
    ``first_ingest`` once. ``failed`` clears ``pass_running_since`` and writes
    ``pass_error`` with ``code`` and ``file``, keeping the ``since`` of an error
    already stored.

    Raises:
        ValueError: ``failed`` without a ``code``.
    """
    stamp = utc_text(at)
    if event == "failed" and not code:
        msg = "a failed pass needs a code"
        raise ValueError(msg)
    with transaction(conn):
        if event == "start":
            _set_meta(conn, KEY_RUNNING, stamp)
            return
        conn.execute("DELETE FROM meta WHERE key = ?", (KEY_RUNNING,))
        if event == "ok":
            _set_meta(conn, KEY_AS_OF, stamp)
            conn.execute("DELETE FROM meta WHERE key = ?", (KEY_FAILURE,))
            if full:
                conn.execute(
                    "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                    (KEY_FIRST_INGEST, stamp),
                )
            return
        previous = _pass_error(conn)
        since = stamp if previous is None else utc_text(previous.since)
        payload = {"code": code, "file": file, "since": since}
        _set_meta(conn, KEY_FAILURE, json.dumps(payload, sort_keys=True))
