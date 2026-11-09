"""Tests for store: open, migrate, read connections and the schema."""

import hashlib
import sqlite3
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

import platform_os
import store
import store_paths
from store import StoreError
from store_paths import StoreLayout

LATEST = 5
MALFORMED = "database disk image is malformed"

# Rows to insert per table, with the migration that creates the table. Files first,
# because other tables point at them.
ROWS: list[tuple[str, int, str]] = [
    ("meta", 1, "INSERT INTO meta VALUES ('k', 'v')"),
    (
        "files",
        1,
        "INSERT INTO files (id, path, kind, folder, first_seen, last_seen) VALUES "
        "(1, '/work/a.jsonl', 'main', 'f', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z'), "
        "(2, '/work/b.jsonl', 'agent', 'f', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')",
    ),
    (
        "requests",
        1,
        "INSERT INTO requests (file_id, key, ts, model) VALUES "
        "(1, 'k1', '2026-01-01T00:00:00Z', 'm'), "
        "(1, 'k2', '2026-01-01T00:00:01Z', 'm'), "
        "(2, 'k1', '2026-01-01T00:00:02Z', 'm')",
    ),
    ("sessions", 1, "INSERT INTO sessions (session_id, folder) VALUES ('s', 'f')"),
    ("runs", 1, "INSERT INTO runs (session_id, run_id, file_id) VALUES ('s', 'r', 1)"),
    (
        "links",
        1,
        "INSERT INTO links (parent_file_id, child_id, session_id) VALUES (1, 'c', 's')",
    ),
    (
        "run_events",
        2,
        "INSERT INTO run_events (file_id, seq, kind) VALUES (1, 1, 'launch'), "
        "(1, 2, 'stop')",
    ),
    ("file_state", 2, "INSERT INTO file_state (file_id) VALUES (1)"),
    (
        "minute_usage",
        3,
        "INSERT INTO minute_usage (session_id, run_key, minute, model) VALUES "
        "('s', 'r', '2026-01-01T00:00', 'm'), ('s', 'r', '2026-01-01T00:01', 'm')",
    ),
    (
        "passes",
        4,
        "INSERT INTO passes (kind, started) VALUES ('full', '2026-01-01T00:00:00Z')",
    ),
    (
        "backups",
        4,
        "INSERT INTO backups (at, file, ok, reason_code) VALUES "
        "('2026-01-01T00:00:00Z', 'x.db', 0, 'no_space'), "
        "('2026-01-01T00:00:00Z', 'y.db', 1, NULL)",
    ),
    (
        "price_copies",
        5,
        "INSERT INTO price_copies (fetched_at, source, sha256) VALUES "
        "('2026-01-01T00:00:00Z', 'litellm', 'abc')",
    ),
]


@pytest.fixture
def layout(tmp_path: Path) -> StoreLayout:
    return StoreLayout(store_paths.shared_store_root(tmp_path / "cfg"))


@pytest.fixture
def conn(layout: StoreLayout) -> Iterator[sqlite3.Connection]:
    connection = store.open_writer(layout)
    yield connection
    connection.close()


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608


def test_latest_version_matches_files() -> None:
    assert store.latest_version() == LATEST
    assert [n for n, _ in store.migration_files()] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("old", [1, 2, 3, 4, 5])
def test_rows_survive_migration_from_each_version(
    layout: StoreLayout, old: int
) -> None:
    conn = store.open_writer(layout)
    assert store.migrate(conn, target=old) == old
    expected: dict[str, int] = {}
    for table, since, sql in ROWS:
        if since <= old:
            conn.execute(sql)
            expected[table] = _count(conn, table)
    conn.close()
    conn = store.open_writer(layout)
    assert store.migrate(conn) == LATEST
    assert store.user_version(conn) == LATEST
    for table, count in expected.items():
        assert _count(conn, table) == count, table
    # every table exists after the upgrade
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert {t for t, _, _ in ROWS} <= names
    conn.close()


def test_migrate_twice_changes_nothing(conn: sqlite3.Connection) -> None:
    store.migrate(conn)
    calls: list[int] = []
    assert store.migrate(conn, calls.append) == LATEST
    assert calls == []


def test_newer_store_is_refused_and_untouched(layout: StoreLayout) -> None:
    conn = store.open_writer(layout)
    store.migrate(conn)
    conn.execute(f"PRAGMA user_version = {LATEST + 1}")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    before = hashlib.sha256(layout.db.read_bytes()).hexdigest()
    conn = store.open_writer(layout)
    called: list[int] = []
    with pytest.raises(StoreError) as info:
        store.migrate(conn, called.append)
    assert info.value.code == "store_newer"
    assert info.value.file == str(layout.db.resolve()) or info.value.file
    assert called == []
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    assert hashlib.sha256(layout.db.read_bytes()).hexdigest() == before


def test_before_migrate_gets_old_version_on_upgrade(layout: StoreLayout) -> None:
    conn = store.open_writer(layout)
    store.migrate(conn, target=2)
    seen: list[int] = []

    def hook(version: int) -> None:
        seen.append(version)
        assert store.user_version(conn) == version

    assert store.migrate(conn, hook) == LATEST
    assert seen == [2]
    conn.close()


def test_before_migrate_skipped_for_new_store(conn: sqlite3.Connection) -> None:
    seen: list[int] = []
    store.migrate(conn, seen.append)
    assert seen == []
    assert store.user_version(conn) == LATEST


def test_failed_migration_rolls_back(conn: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "m"
    folder.mkdir()
    (folder / "0001_a.sql").write_text("CREATE TABLE a (x INTEGER);")
    (folder / "0002_b.sql").write_text("CREATE TABLE b (x INTEGER); BOGUS SQL;")
    with pytest.raises(StoreError):
        store.migrate(conn, migrations_dir=folder)
    assert store.user_version(conn) == 1
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    assert "a" in names
    assert "b" not in names
    assert not conn.in_transaction


def test_writer_pragmas(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == store.BUSY_TIMEOUT_MS
    assert store.quick_check(conn) is True


def test_foreign_keys_are_enforced(conn: sqlite3.Connection) -> None:
    store.migrate(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO runs (session_id, run_id, file_id) VALUES ('s','r',9)"
        )


def test_check_constraints(conn: sqlite3.Connection) -> None:
    store.migrate(conn)
    conn.execute(ROWS[1][2])
    bad = [
        "INSERT INTO files (path, kind, folder, first_seen, last_seen) "
        "VALUES ('/work/z', 'weird', 'f', 't', 't')",
        "INSERT INTO run_events (file_id, seq, kind) VALUES (1, 9, 'other')",
        "INSERT INTO backups (at, file, reason_code) VALUES ('t', 'f', 'nope')",
        "INSERT INTO price_copies (fetched_at, source, sha256) VALUES ('t','x','h')",
    ]
    for sql in bad:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(sql)


def test_best_requests_ranks_by_output_then_ts_then_path(
    conn: sqlite3.Connection,
) -> None:
    store.migrate(conn)
    conn.execute(ROWS[1][2])
    conn.executemany(
        "INSERT INTO requests (file_id, key, ts, output, model) VALUES (?,?,?,?,'m')",
        [
            (1, "k", "2026-01-01T00:00:00Z", 5),
            (2, "k", "2026-01-01T00:00:00Z", 5),
            (1, "j", "2026-01-01T00:00:00Z", 9),
            (2, "j", "2026-01-02T00:00:00Z", 3),
        ],
    )
    winners = {
        r[0]: (r[1], r[2], r[3], r[4])
        for r in conn.execute(
            "SELECT key, path, session_id, run_id, file_kind FROM best_winners"
        )
    }
    assert winners["k"][0] == "/work/b.jsonl"
    assert winners["j"][0] == "/work/a.jsonl"
    assert winners["k"][3] == "agent"
    assert _count(conn, "best_requests") == 4


def test_without_rowid_and_indexes(conn: sqlite3.Connection) -> None:
    store.migrate(conn)
    sql = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL"
        )
    }
    assert "WITHOUT ROWID" in sql["requests"]
    assert "WITHOUT ROWID" in sql["minute_usage"]
    assert "requests_key" in sql
    assert "links_session_child" in sql
    pk = [
        r[1]
        for r in sorted(
            conn.execute("PRAGMA table_info(minute_usage)"), key=lambda r: r[5]
        )
        if r[5]
    ]
    assert pk == [
        "session_id",
        "run_key",
        "minute",
        "model",
        "effort",
        "speed",
        "service_tier",
        "inference_geo",
        "tier",
    ]


# Every TEXT column must be named here. A new one is a privacy review, because a
# TEXT column is where transcript content could leak into the store.
TEXT_ALLOWLIST = {
    # paths, folders and ids
    "path",
    "folder",
    "session_id",
    "run_id",
    "project_key",
    "key",
    "request_id",
    "child_id",
    "run_key",
    "file",
    "agent_type",
    # request dimensions
    "model",
    "effort",
    "speed",
    "service_tier",
    "inference_geo",
    "tier",
    # timestamps
    "ts",
    "first_ts",
    "last_ts",
    "first_seen",
    "last_seen",
    "minute",
    "at",
    "started",
    "finished",
    "fetched_at",
    # session facts
    "branch",
    "cwd",
    "claude_version",
    # hashes, state, codes
    "head_hash",
    "last_line_hash",
    "sha256",
    "state",
    "source",
    "kind",
    "file_kind",
    "reason_code",
    "error_code",
    "by_kind",
    "by_run",
    # meta rows
    "value",
    # cross check fields
    "cross_check_state",
    "cross_check_models",
}


def test_schema_privacy_text_columns_are_allowlisted(conn: sqlite3.Connection) -> None:
    store.migrate(conn)
    names = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name NOT LIKE 'sqlite_%'"
        )
    ]
    text_columns = {
        (name, col[1])
        for name in names
        for col in conn.execute(f'PRAGMA table_info("{name}")')
        if "TEXT" in str(col[2]).upper()
    }
    unknown = sorted(f"{t}.{c}" for t, c in text_columns if c not in TEXT_ALLOWLIST)
    assert not unknown, f"TEXT columns not on the privacy allowlist: {unknown}"


def test_reader_refuses_writes_and_sees_data(layout: StoreLayout) -> None:
    writer = store.open_writer(layout)
    store.migrate(writer)
    writer.execute(ROWS[0][2])
    reader = store.open_reader(layout)
    assert reader.execute("SELECT value FROM meta").fetchone()[0] == "v"
    with pytest.raises(sqlite3.OperationalError):
        reader.execute("INSERT INTO meta VALUES ('x', 'y')")
    reader.close()
    writer.close()


def test_reader_does_not_create_a_missing_store(layout: StoreLayout) -> None:
    layout.root.mkdir(parents=True)
    with pytest.raises(StoreError) as info:
        store.open_reader(layout)
    assert info.value.code == "store_unwritable"
    assert not layout.db.exists()


def test_modes(layout: StoreLayout) -> None:
    conn = store.open_writer(layout)
    store.migrate(conn)
    conn.execute(ROWS[0][2])
    for folder in (layout.root, layout.db_backups, layout.prices_dir):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700, folder
    assert stat.S_IMODE(layout.root.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(layout.db.stat().st_mode) == 0o600
    for suffix in ("-wal", "-shm"):
        side = Path(f"{layout.db}{suffix}")
        if side.exists():
            assert stat.S_IMODE(side.stat().st_mode) == 0o600, side
    conn.close()


def test_garbage_file_is_damaged(layout: StoreLayout) -> None:
    layout.root.mkdir(parents=True)
    layout.db.write_bytes(b"this is not a database at all, " * 100)
    with pytest.raises(StoreError) as info:
        store.open_writer(layout)
    assert info.value.code == "store_damaged"
    assert info.value.file == str(layout.db)


def test_unwritable_root_maps_to_store_unwritable(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a folder")
    layout = StoreLayout(blocker / "routing-dashboard" / "bartab")
    with pytest.raises(StoreError) as info:
        store.open_writer(layout)
    assert info.value.code == "store_unwritable"


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("attempt to write a readonly database", "store_unwritable"),
        ("disk I/O error", "store_unwritable"),
        ("database or disk is full", "store_unwritable"),
        ("file is not a database", "store_damaged"),
        ("database disk image is malformed", "store_damaged"),
    ],
)
def test_error_mapping(message: str, code: str) -> None:
    assert store.map_error(sqlite3.OperationalError(message)).code == code


def test_quick_check_false_on_damage(conn: sqlite3.Connection) -> None:
    class Broken:
        def execute(self, _sql: str) -> None:
            raise sqlite3.DatabaseError(MALFORMED)

    assert store.quick_check(Broken()) is False  # type: ignore[arg-type]


def test_store_creates_nothing_outside_bartab_and_spares_old_files(
    tmp_path: Path,
) -> None:
    config = tmp_path / "cfg"
    old = config / "routing-dashboard"
    seeded = [
        old / "backups" / "x" / "ledger.json",
        old / "ledger.json",
        old / ".lock",
        old / "settings.json.bak",
        config / "routing-dashboard.json",
    ]
    for i, path in enumerate(seeded):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"old {i}".encode())
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in seeded}
    tree_before = {p for p in config.rglob("*")}

    layout = StoreLayout(store_paths.shared_store_root(config))
    conn = store.open_writer(layout)
    store.migrate(conn)
    conn.execute(ROWS[0][2])
    lock = platform_os.try_lock_exclusive(
        store_paths.writable(layout, layout.writer_lock)
    )
    assert lock is not None
    lock.release()
    conn.close()

    for path, (data, mtime) in before.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == (data, mtime)
    created = {p for p in config.rglob("*")} - tree_before
    assert created
    bartab = layout.root.resolve()
    assert all(bartab in p.resolve().parents or p.resolve() == bartab for p in created)
    assert sorted(p.name for p in old.iterdir()) == sorted(
        ["backups", "ledger.json", ".lock", "settings.json.bak", "bartab"]
    )
