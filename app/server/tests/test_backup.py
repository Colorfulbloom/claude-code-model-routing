"""Tests for backup: copy, check, rotation, failure codes and due rules."""

import errno
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import backup
import store
import store_paths
from store_paths import StoreLayout

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)


def _always_bad(_conn: sqlite3.Connection) -> bool:
    return False


@pytest.fixture
def layout(tmp_path: Path) -> StoreLayout:
    return StoreLayout(tmp_path / "bartab")


@pytest.fixture
def conn(layout: StoreLayout) -> Iterator[sqlite3.Connection]:
    c = store.open_writer(layout)
    store.migrate(c)
    c.execute(
        "INSERT INTO files (id, path, kind, folder, first_seen, last_seen) "
        "VALUES (1, '/work/a.jsonl', 'main', 'f', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')"
    )
    c.executemany(
        "INSERT INTO requests (file_id, key, ts, output, model) "
        "VALUES (1, ?, ?, ?, 'm')",
        [(f"k{i}", f"2026-01-01T00:00:{i:02d}Z", i * 10) for i in range(5)],
    )
    yield c
    c.close()


def _names(layout: StoreLayout) -> list[str]:
    return sorted(p.name for p in layout.db_backups.iterdir())


def _make(
    conn: sqlite3.Connection, layout: StoreLayout, minutes: int
) -> backup.BackupResult:
    return backup.make_backup(conn, layout, now=T0 + timedelta(minutes=minutes))


def _totals(c: sqlite3.Connection) -> tuple[int, int]:
    return c.execute("SELECT COUNT(*), SUM(output) FROM requests").fetchone()


def test_restore_gives_same_totals(
    conn: sqlite3.Connection, layout: StoreLayout, tmp_path: Path
) -> None:
    result = _make(conn, layout, 0)
    assert result.ok
    assert result.file is not None
    assert result.file.stat().st_mode & 0o777 == 0o600
    fresh = tmp_path / "restored.db"
    fresh.write_bytes(result.file.read_bytes())
    restored = sqlite3.connect(fresh)
    try:
        assert store.quick_check(restored)
        assert _totals(restored) == _totals(conn) == (5, 100)
        assert store.user_version(restored) == store.latest_version()
    finally:
        restored.close()
    assert [p.name for p in layout.db_backups.glob("*-wal")] == []


def test_stamp_is_unique_within_one_second(
    conn: sqlite3.Connection, layout: StoreLayout
) -> None:
    for _ in range(3):
        assert _make(conn, layout, 0).ok
    assert _names(layout) == [
        "bartab-20261101T120000Z-2.db",
        "bartab-20261101T120000Z-3.db",
        "bartab-20261101T120000Z.db",
    ]


def test_rotation_keeps_seven_and_drops_oldest(
    conn: sqlite3.Connection, layout: StoreLayout
) -> None:
    for i in range(10):
        assert _make(conn, layout, i * 60).ok
    names = _names(layout)
    assert len(names) == 7
    assert names[0] == "bartab-20261101T150000Z.db"
    assert names[-1] == "bartab-20261101T210000Z.db"


def test_rotation_orders_counter_suffix_after_plain(
    conn: sqlite3.Connection, layout: StoreLayout
) -> None:
    for _ in range(3):
        _make(conn, layout, 0)
    backup.make_backup(conn, layout, now=T0, keep=2)
    assert _names(layout) == [
        "bartab-20261101T120000Z-3.db",
        "bartab-20261101T120000Z-4.db",
    ]


def test_failed_check_deletes_copy_and_keeps_good_ones(
    conn: sqlite3.Connection, layout: StoreLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(7):
        assert _make(conn, layout, i).ok
    before = _names(layout)
    monkeypatch.setattr(store, "quick_check", _always_bad)
    result = _make(conn, layout, 100)
    assert not result.ok
    assert result.reason_code == "check_failed"
    assert result.file is None
    assert _names(layout) == before
    row = conn.execute(
        "SELECT ok, reason_code, bytes FROM backups ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert tuple(row) == (0, "check_failed", 0)


@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (OSError(errno.ENOSPC, "full"), "no_space"),
        (sqlite3.OperationalError("database or disk is full"), "no_space"),
        (PermissionError(errno.EACCES, "denied"), "unwritable"),
        (OSError(errno.EROFS, "read-only"), "unwritable"),
        (
            sqlite3.OperationalError("attempt to write a readonly database"),
            "unwritable",
        ),
        (OSError(errno.EIO, "io"), "copy_failed"),
        (sqlite3.DatabaseError("odd"), "copy_failed"),
    ],
)
def test_failure_codes(
    conn: sqlite3.Connection,
    layout: StoreLayout,
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    code: str,
) -> None:
    assert _make(conn, layout, 0).ok

    def boom(*_a: object, **_k: object) -> None:
        raise exc

    monkeypatch.setattr(backup.platform_os, "fsync_file", boom)
    result = _make(conn, layout, 5)
    assert result.reason_code == code
    assert _names(layout) == ["bartab-20261101T120000Z.db"]
    last = conn.execute(
        "SELECT ok, reason_code FROM backups ORDER BY id DESC"
    ).fetchone()
    assert tuple(last) == (0, code)


def test_unwritable_folder_is_recorded(
    conn: sqlite3.Connection, layout: StoreLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    def deny(_path: Path) -> None:
        raise PermissionError(errno.EACCES, "no")

    monkeypatch.setattr(backup.platform_os, "mkdir_private", deny)
    result = _make(conn, layout, 0)
    assert result.reason_code == "unwritable"
    row = conn.execute("SELECT ok, reason_code FROM backups").fetchone()
    assert tuple(row) == (0, "unwritable")


def test_backup_due_edges(conn: sqlite3.Connection, layout: StoreLayout) -> None:
    assert backup.backup_due(conn, now=T0)
    _make(conn, layout, 0)
    day = timedelta(hours=24)
    assert not backup.backup_due(conn, now=T0 + day - timedelta(seconds=1))
    assert backup.backup_due(conn, now=T0 + day)
    assert backup.backup_due(conn, now=T0 - timedelta(minutes=5))
    assert not backup.backup_due(conn, now=T0 + timedelta(hours=2), max_age=day * 2)


def test_failed_attempt_does_not_defer_the_next_one(
    conn: sqlite3.Connection, layout: StoreLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(store, "quick_check", _always_bad)
    _make(conn, layout, 0)
    assert backup.backup_due(conn, now=T0 + timedelta(minutes=1))
    assert backup.stop_backup_due(conn, now=T0 + timedelta(minutes=1))


def test_stop_backup_due_edges(conn: sqlite3.Connection, layout: StoreLayout) -> None:
    assert backup.stop_backup_due(conn, now=T0)
    _make(conn, layout, 0)
    assert not backup.stop_backup_due(conn, now=T0 + timedelta(minutes=59, seconds=59))
    assert backup.stop_backup_due(conn, now=T0 + timedelta(hours=1))


def test_every_file_written_lies_under_the_store_root(
    conn: sqlite3.Connection, layout: StoreLayout, tmp_path: Path
) -> None:
    for i in range(9):
        _make(conn, layout, i)
    (layout.db_backups / ".bartab-stale.db.tmp").write_bytes(b"x")
    _make(conn, layout, 20)
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert store_paths.writable(layout, path) == path.resolve()
    assert not list(layout.db_backups.glob(".*"))
    assert layout.db_backups.stat().st_mode & 0o777 == 0o700


def test_outside_root_is_refused_and_recorded(
    conn: sqlite3.Connection, layout: StoreLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_layout: StoreLayout, path: Path) -> Path:
        raise store_paths.StorePathError(path, "outside_root")

    monkeypatch.setattr(store_paths, "writable", refuse)
    result = _make(conn, layout, 0)
    assert result.reason_code == "unwritable"


def test_open_transaction_is_refused(
    conn: sqlite3.Connection, layout: StoreLayout
) -> None:
    conn.execute("BEGIN IMMEDIATE")
    with pytest.raises(ValueError, match="open transaction"):
        _make(conn, layout, 0)
    conn.execute("ROLLBACK")
    assert not layout.db_backups.exists() or _names(layout) == []
