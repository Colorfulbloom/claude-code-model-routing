"""The Bar Tab SQLite store, opened, checked and migrated.

The writer connection runs in autocommit mode (``isolation_level=None``), so the
caller issues ``BEGIN IMMEDIATE`` and ``COMMIT`` itself. Whole-store failures leave
as ``StoreError`` with a first-run code.
"""

import logging
import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import platform_os
import store_paths
from store_paths import StoreLayout

logger = logging.getLogger(__name__)

StoreCode = Literal["store_unwritable", "store_damaged", "store_newer"]

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BUSY_TIMEOUT_MS = 5000

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")
# Primary result codes from sqlite3.h.
_UNWRITABLE = {8, 10, 13, 14}  # READONLY, IOERR, FULL, CANTOPEN
_DAMAGED = {11, 26}  # CORRUPT, NOTADB
_DAMAGED_TEXT = ("file is not a database", "malformed", "corrupt")
_UNWRITABLE_TEXT = ("readonly", "read-only", "disk i/o", "disk is full")


class StoreError(Exception):
    """A whole-store failure with a first-run code and the file it concerns."""

    def __init__(self, code: StoreCode, file: str | None = None) -> None:
        """Keep the code and the file path (None when there is none)."""
        super().__init__(code if file is None else f"{code}: {file}")
        self.code: StoreCode = code
        self.file = file


def map_error(exc: Exception, file: str | None = None) -> StoreError:
    """Map a sqlite3 or OS error to a ``StoreError``, or return it as unwritable."""
    if isinstance(exc, sqlite3.Error):
        primary = (getattr(exc, "sqlite_errorcode", None) or 0) & 0xFF
        text = str(exc).lower()
        if primary in _DAMAGED or any(t in text for t in _DAMAGED_TEXT):
            return StoreError("store_damaged", file)
        if primary in _UNWRITABLE or any(t in text for t in _UNWRITABLE_TEXT):
            return StoreError("store_unwritable", file)
    return StoreError("store_unwritable", file)


def _configure(conn: sqlite3.Connection, *, writer: bool) -> None:
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    if writer:
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
        if mode is None or str(mode[0]).lower() != "wal":
            raise StoreError("store_unwritable")
        conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")


def open_writer(layout: StoreLayout) -> sqlite3.Connection:
    """Create the store folders and file if needed and return the write connection.

    Folders are 0700 and the database file is 0600. WAL, ``synchronous=NORMAL``,
    foreign keys and a busy timeout are set. Raises ``StoreError``.
    """
    db = store_paths.writable(layout, layout.db)
    try:
        platform_os.mkdir_private(layout.root.parent, parents=True)
        for folder in (layout.root, layout.db_backups, layout.prices_dir):
            platform_os.mkdir_private(store_paths.writable(layout, folder))
        platform_os.create_private_file(db)
    except OSError as exc:
        raise map_error(exc, str(layout.root)) from exc
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(db, isolation_level=None)
        _configure(conn, writer=True)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        raise map_error(exc, str(db)) from exc
    except StoreError:
        if conn is not None:
            conn.close()
        raise
    return conn


def open_reader(layout: StoreLayout) -> sqlite3.Connection:
    """Return a connection with ``query_only`` on, for one short read.

    It never creates the file. A missing or unreadable store raises ``StoreError``.
    """
    uri = f"file:{quote(str(layout.db))}?mode=rw"
    try:
        conn = sqlite3.connect(uri, uri=True, isolation_level=None)
        try:
            _configure(conn, writer=False)
            conn.execute("PRAGMA query_only = ON")
            conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchall()
        except sqlite3.Error:
            conn.close()
            raise
    except sqlite3.Error as exc:
        raise map_error(exc, str(layout.db)) from exc
    return conn


def quick_check(conn: sqlite3.Connection) -> bool:
    """Run ``PRAGMA quick_check``. False means the file is damaged."""
    try:
        rows = conn.execute("PRAGMA quick_check").fetchall()
    except sqlite3.Error as exc:
        mapped = map_error(exc)
        if mapped.code == "store_damaged":
            return False
        raise mapped from exc
    return [tuple(r) for r in rows] == [("ok",)]


def user_version(conn: sqlite3.Connection) -> int:
    """Return ``PRAGMA user_version``."""
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def migration_files(migrations_dir: Path = MIGRATIONS_DIR) -> list[tuple[int, Path]]:
    """Return (number, path) for every ``NNNN_name.sql`` file, in order."""
    found: list[tuple[int, Path]] = []
    for path in migrations_dir.iterdir():
        match = _MIGRATION_NAME.match(path.name)
        if match:
            found.append((int(match.group(1)), path))
    found.sort()
    return found


def latest_version(migrations_dir: Path = MIGRATIONS_DIR) -> int:
    """Return the newest migration number the code knows."""
    files = migration_files(migrations_dir)
    return files[-1][0] if files else 0


def _db_file(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    return str(row[2]) if row and row[2] else None


def migrate(
    conn: sqlite3.Connection,
    before_migrate: Callable[[int], None] | None = None,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    target: int | None = None,
) -> int:
    """Apply pending migrations in order and return the new ``user_version``.

    Each file runs in its own transaction and sets ``user_version`` to its number.
    ``before_migrate(old_version)`` runs once first, only when an existing store at
    version 1 or higher is about to change. A store newer than the newest file
    raises ``StoreError("store_newer")`` and is not touched. ``target`` stops at
    that number (tests use it to build older stores).
    """
    files = migration_files(migrations_dir)
    newest = files[-1][0] if files else 0
    current = user_version(conn)
    if current > newest:
        raise StoreError("store_newer", _db_file(conn))
    goal = newest if target is None else min(target, newest)
    pending = [(n, p) for n, p in files if current < n <= goal]
    if not pending:
        return current
    if before_migrate is not None and current >= 1:
        before_migrate(current)
    for number, path in pending:
        script = (
            f"BEGIN IMMEDIATE;\n{path.read_text(encoding='utf-8')}\n"
            f"PRAGMA user_version = {number};\nCOMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            logger.warning("migration %s failed", path.name)
            raise map_error(exc, _db_file(conn)) from exc
    return user_version(conn)
