"""Copies of the live store, rotated to the newest seven.

A copy is made with ``sqlite3.Connection.backup`` into a dot-named temp file, checked
with ``PRAGMA quick_check``, fsynced and renamed. Only a copy that passes may rotate
out an older one. A failed copy is deleted and recorded in ``backups`` with a closed
reason code, and it never displaces a good copy.

Every attempt is recorded through the given writer connection with
``history.transaction``: one short ``BEGIN IMMEDIATE`` and ``COMMIT`` for the row.
The caller must not hold a transaction when it calls ``make_backup``, because
``sqlite3`` would wait forever to read a source that has an open write on the same
connection. ``make_backup`` raises ``ValueError`` in that case.
"""

import errno
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import history
import platform_os
import store
import store_paths
from store_paths import StoreLayout, StorePathError

logger = logging.getLogger(__name__)

ReasonCode = Literal["no_space", "unwritable", "check_failed", "copy_failed"]

DEFAULT_KEEP = 7
DEFAULT_MAX_AGE = timedelta(hours=24)
STOP_MIN_AGE = timedelta(hours=1)

_GOOD_NAME = re.compile(r"^bartab-(\d{8}T\d{6}Z)(?:-(\d+))?\.db$")
_NO_SPACE_ERRNOS = {errno.ENOSPC, errno.EDQUOT}
_UNWRITABLE_ERRNOS = {errno.EACCES, errno.EPERM, errno.EROFS}
_SQLITE_FULL = 13
_SQLITE_READONLY = 8
_SQLITE_CANTOPEN = 14


class _CheckFailedError(Exception):
    """The copy did not pass ``PRAGMA quick_check``."""


@dataclass(frozen=True)
class BackupResult:
    """The outcome of one backup attempt."""

    ok: bool
    at: datetime
    file: Path | None
    bytes: int
    reason_code: ReasonCode | None


def _sqlite_reason(exc: sqlite3.Error) -> ReasonCode:
    primary = (getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF
    text = str(exc).lower()
    if primary == _SQLITE_FULL or "disk is full" in text:
        return "no_space"
    if primary in {_SQLITE_READONLY, _SQLITE_CANTOPEN}:
        return "unwritable"
    if any(t in text for t in ("readonly", "read-only", "unable to open")):
        return "unwritable"
    return "copy_failed"


def _reason(exc: BaseException) -> ReasonCode:
    if isinstance(exc, _CheckFailedError):
        return "check_failed"
    if isinstance(exc, StorePathError | PermissionError):
        return "unwritable"
    if isinstance(exc, sqlite3.Error):
        return _sqlite_reason(exc)
    if isinstance(exc, OSError):
        if exc.errno in _NO_SPACE_ERRNOS:
            return "no_space"
        if exc.errno in _UNWRITABLE_ERRNOS:
            return "unwritable"
    return "copy_failed"


def _good_key(name: str) -> tuple[str, int] | None:
    match = _GOOD_NAME.match(name)
    if match is None:
        return None
    return match.group(1), int(match.group(2) or 1)


def _unique_stamp(folder: Path, base: str) -> str:
    """Return ``base``, or ``base-N`` when a copy or temp file already uses it."""
    stamp, counter = base, 1
    while (folder / f"bartab-{stamp}.db").exists() or (
        folder / f".bartab-{stamp}.db.tmp"
    ).exists():
        counter += 1
        stamp = f"{base}-{counter}"
    return stamp


def _remove(layout: StoreLayout, path: Path) -> None:
    """Delete a temp file and its sqlite side files. Never raises."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            store_paths.writable(layout, path.with_name(path.name + suffix)).unlink(
                missing_ok=True
            )
        except (OSError, StorePathError):
            logger.warning("could not remove %s", path.name + suffix)


def _copy(conn: sqlite3.Connection, layout: StoreLayout, tmp: Path, final: Path) -> int:
    """Copy, check, fsync and rename. Returns the size in bytes."""
    platform_os.create_private_file(tmp)
    dest = sqlite3.connect(tmp, isolation_level=None)
    try:
        conn.backup(dest)
        dest.execute("PRAGMA journal_mode = DELETE")
        if not store.quick_check(dest):
            raise _CheckFailedError
    finally:
        dest.close()
    tmp.chmod(platform_os.FILE_MODE)
    platform_os.fsync_file(tmp)
    size = tmp.stat().st_size
    tmp.replace(final)
    platform_os.fsync_dir(final.parent)
    return size


def _rotate(layout: StoreLayout, folder: Path, keep: int) -> None:
    named = sorted(
        (key, path)
        for path in folder.iterdir()
        if path.is_file() and (key := _good_key(path.name)) is not None
    )
    for _key, path in named[: max(0, len(named) - keep)]:
        try:
            store_paths.writable(layout, path).unlink(missing_ok=True)
        except (OSError, StorePathError):
            logger.warning("could not rotate out %s", path.name)


def _record(
    conn: sqlite3.Connection, at: datetime, name: str, size: int, reason: str | None
) -> None:
    try:
        with history.transaction(conn):
            conn.execute(
                "INSERT INTO backups (at, file, bytes, ok, reason_code)"
                " VALUES (?, ?, ?, ?, ?)",
                (history.utc_text(at), name, size, 1 if reason is None else 0, reason),
            )
    except sqlite3.Error:
        logger.warning("could not record the backup attempt")


def make_backup(
    conn: sqlite3.Connection,
    layout: StoreLayout,
    *,
    now: datetime,
    keep: int = DEFAULT_KEEP,
) -> BackupResult:
    """Copy the live store into ``db-backups/`` and rotate to ``keep`` good copies.

    Never raises for a failed copy. The result carries a closed ``reason_code`` and
    the attempt is recorded in ``backups``. The stamp is UTC to the second, with a
    counter suffix (``-2``, ``-3``) when two copies share a second.

    Raises:
        ValueError: ``conn`` is inside a transaction.
    """
    if conn.in_transaction:
        msg = "make_backup needs a connection with no open transaction"
        raise ValueError(msg)
    at = now.astimezone(UTC)
    base = at.strftime("%Y%m%dT%H%M%SZ")
    name = f"bartab-{base}.db"
    tmp = final = None
    size = 0
    reason: ReasonCode | None = None
    try:
        folder = store_paths.writable(layout, layout.db_backups)
        platform_os.mkdir_private(folder)
        for stale in folder.glob(".bartab-*.db.tmp"):
            _remove(layout, stale)
        stamp = _unique_stamp(folder, base)
        name = f"bartab-{stamp}.db"
        tmp = store_paths.writable(layout, folder / f".bartab-{stamp}.db.tmp")
        final = store_paths.writable(layout, folder / name)
        size = _copy(conn, layout, tmp, final)
    except (OSError, sqlite3.Error, StorePathError, _CheckFailedError) as exc:
        reason = _reason(exc)
        logger.warning("backup failed: %s", reason)
        size = 0
        if tmp is not None:
            _remove(layout, tmp)
    _record(conn, at, name, size, reason)
    if reason is not None or final is None:
        return BackupResult(False, at, None, 0, reason or "copy_failed")
    try:
        _rotate(layout, final.parent, keep)
    except OSError:
        logger.warning("could not list the backup folder to rotate")
    return BackupResult(True, at, final, size, None)


def _newest_ok(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute(
        "SELECT at FROM backups WHERE ok = 1 ORDER BY at DESC, id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else history.parse_utc(row[0])


def _younger_than(conn: sqlite3.Connection, now: datetime, limit: timedelta) -> bool:
    newest = _newest_ok(conn)
    if newest is None or newest > now:
        return False
    return now - newest < limit


def backup_due(
    conn: sqlite3.Connection,
    *,
    now: datetime,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> bool:
    """True when no good copy exists or the newest is ``max_age`` old or older.

    A copy dated after ``now`` (a clock set back) does not count as recent.
    """
    return not _younger_than(conn, now, max_age)


def stop_backup_due(conn: sqlite3.Connection, *, now: datetime) -> bool:
    """True unless the newest good copy is under an hour old (the clean-stop rule)."""
    return not _younger_than(conn, now, STOP_MIN_AGE)
