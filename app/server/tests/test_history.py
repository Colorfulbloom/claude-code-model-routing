"""Tests for history: the status reader and the pass bookkeeping in meta."""

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

import history
import store
from store_paths import StoreLayout

T0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    c = store.open_writer(StoreLayout(tmp_path / "bartab"))
    store.migrate(c)
    yield c
    c.close()


def _backup(conn: sqlite3.Connection, when: datetime, reason: str | None) -> None:
    conn.execute(
        "INSERT INTO backups (at, file, bytes, ok, reason_code) "
        "VALUES (?, 'f', 1, ?, ?)",
        (history.utc_text(when), 1 if reason is None else 0, reason),
    )


def test_empty_store(conn: sqlite3.Connection) -> None:
    status = history.read_history(conn)
    assert status == history.HistoryStatus(
        oldest=None,
        first_ingest=None,
        last_backup=None,
        backup_failed=None,
        pass_error=None,
        unreadable_files=0,
        kept_files=0,
        no_usage_rows=0,
        as_of=None,
        pass_running_since=None,
    )
    assert not conn.in_transaction


def test_counts_and_oldest(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        INSERT INTO files (id, path, kind, folder, read_errors, missing, no_usage,
            first_seen, last_seen) VALUES
          (1, '/work/a', 'main', 'f', 2, 0, 3, 'x', 'x'),
          (2, '/work/b', 'agent', 'f', 0, 1, 4, 'x', 'x'),
          (3, '/work/c', 'agent', 'f', 0, 0, 0, 'x', 'x');
        INSERT INTO requests (file_id, key, ts, output, model) VALUES
          (1, 'k1', '2026-01-05T00:00:00Z', 5, 'm'),
          (2, 'k1', '2026-01-02T00:00:00Z', 1, 'm'),
          (3, 'k2', '2026-01-03T00:00:00Z', 1, 'm');
        """
    )
    status = history.read_history(conn)
    assert status.unreadable_files == 1
    assert status.kept_files == 1
    assert status.no_usage_rows == 7
    # k1's winner is the larger output, at January 5, so the oldest winner is k2.
    assert status.oldest == datetime(2026, 1, 3, tzinfo=UTC)


def test_backup_failed_clears_after_a_good_copy(conn: sqlite3.Connection) -> None:
    _backup(conn, at(0), None)
    _backup(conn, at(10), "no_space")
    status = history.read_history(conn)
    assert status.last_backup == at(0)
    assert status.backup_failed == history.BackupFailure(at(10), "no_space")
    _backup(conn, at(20), None)
    status = history.read_history(conn)
    assert status.last_backup == at(20)
    assert status.backup_failed is None


def test_backup_failed_with_no_good_copy(conn: sqlite3.Connection) -> None:
    _backup(conn, at(0), "check_failed")
    status = history.read_history(conn)
    assert status.last_backup is None
    assert status.backup_failed == history.BackupFailure(at(0), "check_failed")


def test_pass_error_keeps_first_since_and_clears(conn: sqlite3.Connection) -> None:
    history.write_pass_meta(conn, "start", at=at(0))
    assert history.read_history(conn).pass_running_since == at(0)
    history.write_pass_meta(
        conn, "failed", at=at(1), code="store_unwritable", file="/work/s"
    )
    first = history.read_history(conn)
    assert first.pass_running_since is None
    assert first.pass_error == history.PassError("store_unwritable", "/work/s", at(1))
    history.write_pass_meta(conn, "failed", at=at(9), code="unexpected")
    second = history.read_history(conn).pass_error
    assert second == history.PassError("unexpected", None, at(1))
    history.write_pass_meta(conn, "ok", at=at(20))
    done = history.read_history(conn)
    assert done.pass_error is None
    assert done.as_of == at(20)
    history.write_pass_meta(conn, "failed", at=at(30), code="unexpected")
    assert history.read_history(conn).pass_error == history.PassError(
        "unexpected", None, at(30)
    )


def test_pass_error_json_shape(conn: sqlite3.Connection) -> None:
    history.write_pass_meta(conn, "failed", at=at(0), code="unexpected", file=None)
    raw = conn.execute("SELECT value FROM meta WHERE key = 'pass_error'").fetchone()[0]
    assert json.loads(raw) == {
        "code": "unexpected",
        "file": None,
        "since": "2026-11-01T12:00:00Z",
    }


def test_first_ingest_is_set_once(conn: sqlite3.Connection) -> None:
    history.write_pass_meta(conn, "ok", at=at(0), full=False)
    assert history.read_history(conn).first_ingest is None
    history.write_pass_meta(conn, "ok", at=at(5), full=True)
    history.write_pass_meta(conn, "ok", at=at(10), full=True)
    status = history.read_history(conn)
    assert status.first_ingest == at(5)
    assert status.as_of == at(10)


def test_failed_needs_a_code(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="code"):
        history.write_pass_meta(conn, "failed", at=at(0))


def test_write_inside_callers_transaction(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    history.write_pass_meta(conn, "start", at=at(0))
    assert conn.in_transaction
    conn.execute("ROLLBACK")
    assert history.read_history(conn).pass_running_since is None


def test_times_are_aware_utc(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="naive"):
        history.utc_text(datetime(2026, 1, 1))
    eastern = datetime(2026, 11, 1, 8, 0, tzinfo=timezone(timedelta(hours=-4)))
    history.write_pass_meta(conn, "ok", at=eastern)
    assert history.read_history(conn).as_of == at(0)
    raw = conn.execute("SELECT value FROM meta WHERE key = 'last_pass'").fetchone()[0]
    assert raw == "2026-11-01T12:00:00Z"


def test_malformed_meta_reads_as_none(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO meta VALUES ('pass_error', 'not json')")
    conn.execute("INSERT INTO meta VALUES ('last_pass', 'nonsense')")
    status = history.read_history(conn)
    assert status.pass_error is None
    assert status.as_of is None


def test_reader_connection_works(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "bartab")
    w = store.open_writer(layout)
    store.migrate(w)
    history.write_pass_meta(w, "ok", at=at(0), full=True)
    r = store.open_reader(layout)
    try:
        assert history.read_history(r).first_ingest == at(0)
    finally:
        r.close()
        w.close()
