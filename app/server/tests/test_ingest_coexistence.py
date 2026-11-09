"""The writer leaves the old app's files alone and stays inside its own folder."""

import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from ingest_helpers import Config

import store_paths
from store_writer import StoreWriter

NOW = datetime(2026, 11, 1, 12, 10, 0, tzinfo=UTC)

OLD_FILES = {
    "routing-dashboard/backups/x/ledger.json": b'{"entries": []}\n',
    "routing-dashboard/.lock": b"4242\n",
    "routing-dashboard/model-routing.settings.bak": b"{}\n",
    "routing-dashboard/.ledger-abc123.tmp": b"partial",
    "routing-dashboard.json": b'{"projects": []}\n',
}


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_ingest_backup_and_a_job_never_touch_an_old_app_file(tmp_path: Path) -> None:
    cfg = Config(tmp_path)
    cfg.write(cfg.main(), [h.assistant(0, "a"), h.link_row(1, "a1")])
    cfg.write(cfg.agent("a1"), [h.assistant(2, "w1")])
    cfg.meta("a1", "scribe")
    for name, data in OLD_FILES.items():
        path = cfg.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        os.utime(path, (1_700_000_000, 1_700_000_000))
    before = _snapshot(cfg.dir)
    folders_before = {p.name for p in (cfg.dir / "routing-dashboard").iterdir()}

    now = [NOW]
    layout = store_paths.StoreLayout(store_paths.shared_store_root(cfg.dir))
    writer = StoreWriter(layout, cfg.dir, clock=lambda: now[0])
    writer.submit(_copy_record)
    writer.tick()
    assert writer.snapshot().state == "done"
    now[0] += timedelta(hours=2)
    writer.stop()

    after = _snapshot(cfg.dir)
    for name, (data, mtime) in before.items():
        assert after[name] == (data, mtime), name
    new = set(after) - set(before)
    assert new
    prefix = str(Path("routing-dashboard") / "bartab") + os.sep
    assert all(name.startswith(prefix) for name in new), sorted(new)
    assert any(name.startswith(prefix + "db-backups") for name in new)
    assert {p.name for p in (cfg.dir / "routing-dashboard").iterdir()} == (
        folders_before | {"bartab"}
    )
    assert {p.name for p in cfg.dir.iterdir()} == {
        "projects",
        "routing-dashboard",
        "routing-dashboard.json",
    }
    conn = sqlite3.connect(layout.db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM price_copies").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0] == 2
    finally:
        conn.close()


def _copy_record(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    conn.execute(
        "INSERT INTO price_copies (fetched_at, source, sha256, bytes, check_ok)"
        " VALUES ('2026-11-01T00:00:00Z', 'litellm', 'abc', 10, 1)"
    )
    conn.execute("COMMIT")
