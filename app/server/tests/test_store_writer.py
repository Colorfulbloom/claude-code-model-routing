"""Tests for the store writer: schedule, first run, failures, followers and jobs."""

import json
import os
import shutil
import sqlite3
import sys
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from ingest_helpers import Config

import backup
import history
import ingest
import store
import store_writer
from store_paths import StoreLayout
from store_writer import Failure, StoreWriter

NOW = datetime(2026, 11, 1, 12, 10, 0, tzinfo=UTC)  # ten minutes after h.T0


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, start: datetime = NOW) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(tmp_path)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def layout(tmp_path: Path) -> StoreLayout:
    return StoreLayout(tmp_path / "bartab")


@pytest.fixture
def writers() -> Iterator[list[StoreWriter]]:
    made: list[StoreWriter] = []
    yield made
    for w in made:
        w.shutdown()


def make(
    writers: list[StoreWriter],
    layout: StoreLayout,
    config: Config,
    clock: Clock,
    **kw: object,
) -> StoreWriter:
    w = StoreWriter(layout, config.dir, clock=clock, **kw)  # pyright: ignore[reportArgumentType]
    writers.append(w)
    return w


def reader(layout: StoreLayout) -> sqlite3.Connection:
    return store.open_reader(layout)


def seed(config: Config) -> None:
    config.write(config.main(h.S1), [h.assistant(0, "a"), h.assistant(30, "b")])
    config.write(config.agent("a1"), [h.assistant(5, "w1")])


# ------------------------------------------------------------------ first run


def test_first_run_walks_waiting_running_and_done_on_the_demo_build(
    demo_build: Path,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[store_writer.WriterSnapshot] = []
    box: list[StoreWriter] = []
    plans: list[store_writer.WriterSnapshot] = []
    real_plan = ingest.Ingestor._plan  # pyright: ignore[reportPrivateUsage]

    def watch_plan(self: ingest.Ingestor, scope: ingest.PassScope) -> object:
        plans.append(box[0].snapshot())
        return real_plan(self, scope)

    monkeypatch.setattr(ingest.Ingestor, "_plan", watch_plan)
    w = StoreWriter(
        layout,
        demo_build / "config",
        clock=clock,
        sleep=lambda _s: sleeps.append(box[0].snapshot()),
        pace_ms=5,
    )
    box.append(w)
    writers.append(w)
    assert w.snapshot().state == "waiting"
    assert w.snapshot().files_total is None
    w.tick()
    # while folders were listed: running, totals unknown
    assert plans[0].state == "running"
    assert (plans[0].files_total, plans[0].bytes_total) == (None, None)
    # while files were read: running, totals fixed and the same every time
    assert len(sleeps) == 538
    assert {(s.files_total, s.bytes_total) for s in sleeps} == {
        (
            538,
            sum(
                p.stat().st_size
                for p in (demo_build / "config" / "projects").rglob("*.jsonl")
            ),
        ),
    }
    assert [s.files_done for s in sleeps] == sorted(s.files_done for s in sleeps)
    assert all(s.state == "running" and s.error is None for s in sleeps)
    final = w.snapshot()
    assert final.state == "done"
    assert (final.files_done, final.files_total) == (538, 538)
    assert final.bytes_done == final.bytes_total
    assert final.generation >= 1
    assert not final.follower
    conn = reader(layout)
    try:
        assert history.read_history(conn).first_ingest is not None
        assert h.store_totals(conn) == h.oracle_totals(demo_build / "config")
    finally:
        conn.close()


def test_an_empty_projects_folder_is_done_at_once(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    w = make(writers, layout, config, clock)
    w.tick()
    snap = w.snapshot()
    assert snap.state == "done"
    assert (snap.files_total, snap.bytes_total) == (0, 0)
    conn = reader(layout)
    try:
        assert history.read_history(conn).first_ingest is not None
    finally:
        conn.close()


def test_a_store_that_has_finished_first_ingest_starts_done(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    first = make(writers, layout, config, clock)
    first.tick()
    first.shutdown()
    again = make(writers, layout, config, clock)
    again.startup()
    assert again.snapshot().state == "done"


# ------------------------------------------------------------------ failures


def _crafted(
    kind: str, tmp_path: Path, config: Config, layout: StoreLayout
) -> tuple[Failure, str | None]:
    if kind == "config_dir_missing":
        shutil.rmtree(config.projects)
        return Failure("config_dir_missing", str(config.projects)), None
    if kind == "config_dir_unreadable":
        config.projects.chmod(0)
        return Failure("config_dir_unreadable", str(config.projects)), None
    if kind == "store_unwritable":
        layout.root.parent.mkdir(parents=True, exist_ok=True)
        layout.root.write_text("not a folder", encoding="utf-8")
        return Failure("store_unwritable", str(layout.root)), None
    if kind == "store_damaged":
        layout.root.mkdir(parents=True)
        layout.db.write_bytes(b"this is not a database" * 500)
        return Failure("store_damaged", str(layout.db)), None
    if kind == "store_newer":
        conn = store.open_writer(layout)
        store.migrate(conn)
        conn.execute("PRAGMA user_version = 99")
        conn.close()
        return Failure("store_newer", str(layout.db)), None
    return Failure("unexpected", str(tmp_path / "bartab.log")), "boom"


@pytest.mark.parametrize(
    "kind",
    [
        "config_dir_missing",
        "config_dir_unreadable",
        "store_unwritable",
        "store_damaged",
        "store_newer",
        "unexpected",
    ],
)
def test_each_failure_code_fires_from_a_crafted_folder(  # noqa: PLR0913, PLR0917
    kind: str,
    tmp_path: Path,
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if kind == "config_dir_unreadable" and os.geteuid() == 0:
        pytest.skip("root can list any folder")
    seed(config)
    expected, boom = _crafted(kind, tmp_path, config, layout)
    if boom:

        def explode(
            self: ingest.Ingestor, scope: ingest.PassScope
        ) -> ingest.PassResult:
            raise RuntimeError(boom)

        monkeypatch.setattr(ingest.Ingestor, "run_pass", explode)
    w = make(writers, layout, config, clock, log_path=str(tmp_path / "bartab.log"))
    try:
        w.tick()
    finally:
        if kind == "config_dir_unreadable":
            config.projects.chmod(0o700)
    snap = w.snapshot()
    assert snap.state == "failed"
    assert snap.error == expected
    assert snap.retry_at == NOW + timedelta(seconds=10)
    assert not snap.retrying
    assert w.tick() == 10.0  # nothing runs before the retry time


def test_store_damaged_also_comes_from_a_failed_quick_check(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def never_ok(_conn: sqlite3.Connection) -> bool:
        return False

    monkeypatch.setattr(store, "quick_check", never_ok)
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().error == Failure("store_damaged", str(layout.db))


def test_retries_follow_10_30_60_then_every_five_minutes(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config.projects.rmdir()
    runs: list[store_writer.WriterSnapshot] = []
    box: list[StoreWriter] = []
    real = ingest.Ingestor._top_folders  # pyright: ignore[reportPrivateUsage]

    def watch(self: ingest.Ingestor, scope: ingest.PassScope) -> object:
        runs.append(box[0].snapshot())
        return real(self, scope)

    monkeypatch.setattr(ingest.Ingestor, "_top_folders", watch)
    w = make(writers, layout, config, clock)
    box.append(w)
    w.tick()
    gaps: list[float] = []
    for _ in range(6):
        snap = w.snapshot()
        assert snap.retry_at is not None
        gaps.append((snap.retry_at - clock.now).total_seconds())
        clock.advance(gaps[-1] - 1)
        w.tick()
        assert len(runs) == len(gaps)  # one second early: no run
        clock.advance(1)
        w.tick()
        assert len(runs) == len(gaps) + 1
    assert gaps == [10, 30, 60, 300, 300, 300]
    # while a retry executes: running, retrying, and the earlier error is still there
    for during in runs[1:]:
        assert during.retrying
        assert during.state == "running"
        assert during.retry_at is None
        assert during.error == Failure("config_dir_missing", str(config.projects))
    assert runs[0].retrying is False


def test_a_successful_retry_clears_the_error_and_the_retry_state(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.projects.rmdir()
    w = make(writers, layout, config, clock)
    w.tick()
    config.projects.mkdir()
    seed(config)
    clock.advance(10)
    w.tick()
    snap = w.snapshot()
    assert snap.state == "done"
    assert snap.error is None
    assert not snap.retrying
    assert snap.retry_at is None
    assert snap.files_total == 2


def test_nudge_retry_starts_a_retry_at_once(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.projects.rmdir()
    w = make(writers, layout, config, clock)
    w.tick()
    clock.advance(10)
    w.tick()  # second failure: next retry is 30 s away
    assert w.snapshot().retry_at == clock.now + timedelta(seconds=30)
    config.projects.mkdir()
    seed(config)
    w.tick()
    assert w.snapshot().state == "failed"  # not yet
    w.nudge_retry()
    w.tick()
    assert w.snapshot().state == "done"


def test_a_nudge_with_nothing_failed_does_nothing(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    generation = w.generation
    w.nudge_retry()
    w.tick()
    assert w.generation == generation
    assert w.snapshot().state == "done"


def test_a_later_failure_leaves_the_state_done_and_sets_pass_error(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().state == "done"
    for path in sorted(config.projects.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    config.projects.rmdir()
    clock.advance(10)
    w.tick()
    snap = w.snapshot()
    assert snap.state == "done"
    assert snap.error is None
    assert snap.pass_error == Failure("config_dir_missing", str(config.projects))
    assert snap.retry_at == clock.now + timedelta(seconds=10)
    conn = reader(layout)
    try:
        status = history.read_history(conn)
        assert status.pass_error is not None
        assert status.pass_error.code == "config_dir_missing"
        assert status.pass_error.file == str(config.projects)
        since = status.pass_error.since
    finally:
        conn.close()
    # the next failure keeps the first failure time
    clock.advance(10)
    w.tick()
    conn = reader(layout)
    try:
        again = history.read_history(conn).pass_error
        assert again is not None
        assert again.since == since
    finally:
        conn.close()
    # a good pass clears it
    config.projects.mkdir()
    config.write(config.main(), [h.assistant(0, "a")])
    clock.advance(30)
    w.tick()
    assert w.snapshot().pass_error is None
    assert w.snapshot().retry_at is None
    conn = reader(layout)
    try:
        assert history.read_history(conn).pass_error is None
    finally:
        conn.close()


# ------------------------------------------------------------------ schedule


def test_hot_passes_run_every_second_over_running_folders_cold_every_ten(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    recent = config.main(h.S1, "-work-live")
    quiet = config.main(h.S2, "-work-quiet")
    config.write(recent, [h.assistant(0, "a")])  # 10 minutes before the clock
    config.write(quiet, [h.assistant(-3 * 3600, "q", sid=h.S2)])  # hours before
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().state == "done"
    config.append(recent, [h.assistant(1, "a2")])
    config.append(quiet, [h.assistant(-3 * 3600 + 1, "q2", sid=h.S2)])

    def keys() -> set[str]:
        conn = reader(layout)
        try:
            return {str(r[0]) for r in conn.execute("SELECT key FROM requests")}
        finally:
            conn.close()

    assert w.tick() == 1.0  # nothing due yet
    clock.advance(1)
    w.tick()  # hot
    assert keys() == {"a", "a2", "q"}  # only the running folder
    clock.advance(9)
    w.tick()  # cold
    assert keys() == {"a", "a2", "q", "q2"}


def test_the_wait_is_the_time_to_the_next_due_pass(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    w = make(writers, layout, config, clock)
    assert w.tick() == 1.0
    clock.advance(0.25)
    assert w.tick() == pytest.approx(0.75)


def test_as_of_is_written_by_cold_passes_and_hot_passes_with_work(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()

    def as_of() -> datetime | None:
        conn = reader(layout)
        try:
            return history.read_history(conn).as_of
        finally:
            conn.close()

    assert as_of() == NOW
    clock.advance(10)
    w.tick()
    assert as_of() == clock.now
    config.append(config.main(), [h.assistant(40, "c")])
    clock.advance(1)
    w.tick()  # a hot pass with work
    assert as_of() == clock.now


def test_pace_sleeps_after_each_file_only_when_set(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    slept: list[float] = []
    w = make(writers, layout, config, clock, pace_ms=250, sleep=slept.append)
    w.tick()
    assert slept == [0.25, 0.25]
    slept.clear()
    config.append(config.main(), [h.assistant(50, "d")])
    clock.advance(10)
    w.tick()
    assert slept == [0.25]
    quiet = make(writers, StoreLayout(layout.root.parent / "other"), config, clock)
    quiet.tick()
    assert slept == [0.25]


def test_generation_changes_only_when_data_changes(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    first = w.generation
    assert first >= 1
    clock.advance(10)
    w.tick()
    assert w.generation == first
    config.append(config.main(), [h.assistant(60, "e")])
    clock.advance(10)
    w.tick()
    assert w.generation == first + 1


# ------------------------------------------------------------------ backups


def test_a_migration_copies_the_old_store_first_and_startup_backs_up(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    conn = store.open_writer(layout)
    store.migrate(conn, target=2)
    conn.execute(
        "INSERT INTO files (path, kind, folder, first_seen, last_seen)"
        " VALUES ('/work/x.jsonl', 'main', 'f', 'x', 'x')"
    )
    conn.close()
    w = make(writers, layout, config, clock)
    w.startup()
    versions: list[int] = []
    for path in sorted(layout.db_backups.iterdir()):
        copy = sqlite3.connect(path)
        try:
            versions.append(copy.execute("PRAGMA user_version").fetchone()[0])
        finally:
            copy.close()
    assert sorted(versions) == [2, store.latest_version()]
    assert w._conn is not None  # pyright: ignore[reportPrivateUsage]
    assert store.user_version(w._conn) == store.latest_version()  # pyright: ignore[reportPrivateUsage]


def test_a_daily_backup_runs_on_a_cold_pass_and_a_failure_waits_an_hour(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = make(writers, layout, config, clock)
    w.tick()
    assert len(list(layout.db_backups.iterdir())) == 1
    clock.advance(23 * 3600)
    w.tick()
    assert len(list(layout.db_backups.iterdir())) == 1
    clock.advance(2 * 3600)
    w.tick()
    assert len(list(layout.db_backups.iterdir())) == 2
    # a failing copy is not retried every pass
    attempts: list[datetime] = []

    def failing(
        conn: sqlite3.Connection, lay: StoreLayout, *, now: datetime, keep: int = 7
    ) -> backup.BackupResult:
        attempts.append(now)
        return backup.BackupResult(False, now, None, 0, "copy_failed")

    monkeypatch.setattr(backup, "make_backup", failing)
    clock.advance(25 * 3600)
    w.tick()
    for _ in range(5):
        clock.advance(10)
        w.tick()
    assert len(attempts) == 1
    clock.advance(3600)
    w.tick()
    assert len(attempts) == 2


def test_stop_runs_the_stop_backup_unless_one_is_fresh(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    clock.advance(1800)  # the start backup is 30 minutes old: skipped
    w.stop()
    assert len(list(layout.db_backups.iterdir())) == 1
    again = make(writers, layout, config, clock)
    again.tick()
    clock.advance(2 * 3600)
    again.stop()
    assert len(list(layout.db_backups.iterdir())) == 2
    conn = reader(layout)
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM backups WHERE ok = 1").fetchone()[0] == 2
        )
        assert history.read_history(conn).last_backup is not None
    finally:
        conn.close()
    assert not again.snapshot().follower
    # the lock is free again
    third = make(writers, layout, config, clock)
    third.tick()
    assert not third.snapshot().follower


# ------------------------------------------------------------------ followers


def _store_bytes(layout: StoreLayout) -> dict[str, tuple[int, int, bytes]]:
    out: dict[str, tuple[int, int, bytes]] = {}
    for path in sorted(layout.root.rglob("*")):
        if (
            path.is_file()
            and path.name != "writer.lock"
            and not path.name.endswith("-shm")
        ):
            st = path.stat()
            out[str(path)] = (st.st_size, st.st_mtime_ns, path.read_bytes())
    return out


def test_a_second_writer_is_a_follower_that_never_writes_and_takes_over(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    first = make(writers, layout, config, clock)
    first.tick()
    second = make(writers, layout, config, clock)
    before = _store_bytes(layout)
    second.tick()
    snap = second.snapshot()
    assert snap.follower
    assert snap.state == "done"  # from the holder's meta
    assert second._conn is None  # pyright: ignore[reportPrivateUsage]
    submitted: list[int] = []
    second.submit(lambda _c: submitted.append(1))
    config.append(config.main(), [h.assistant(70, "late")])
    for _ in range(4):
        clock.advance(2)
        second.tick()
    assert _store_bytes(layout) == before  # it wrote nothing, not even a checkpoint
    assert second.tick() == pytest.approx(
        2.0
    )  # the next lock try is 10 s after the first
    first.stop()
    clock.advance(10)
    second.tick()
    after = second.snapshot()
    assert not after.follower
    assert after.state == "done"
    assert submitted == [1]  # the queued job ran once it was the writer
    conn = reader(layout)
    try:
        assert "late" in {str(r[0]) for r in conn.execute("SELECT key FROM requests")}
    finally:
        conn.close()


def test_a_follower_reports_waiting_running_and_done_from_meta(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    conn = store.open_writer(layout)
    store.migrate(conn)
    handle = store_writer.platform_os.try_lock_exclusive(layout.writer_lock)
    assert handle is not None
    try:
        follower = make(writers, layout, config, clock)
        follower.tick()
        assert follower.snapshot().follower
        assert follower.snapshot().state == "waiting"
        history.write_pass_meta(conn, "start", at=clock.now, full=True)
        clock.advance(10)
        follower.tick()
        assert follower.snapshot().state == "running"
        history.write_pass_meta(conn, "ok", at=clock.now, full=True)
        clock.advance(10)
        follower.tick()
        assert follower.snapshot().state == "done"
        history.write_pass_meta(conn, "failed", at=clock.now, code="store_damaged")
        clock.advance(10)
        follower.tick()
        assert follower.snapshot().pass_error == Failure("store_damaged")
    finally:
        handle.release()
        conn.close()


def test_a_follower_retries_the_lock_every_ten_seconds(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = make(writers, layout, config, clock)
    first.tick()
    second = make(writers, layout, config, clock)
    tries: list[datetime] = []
    real = store_writer.platform_os.try_lock_exclusive

    def counting(path: Path) -> object:
        tries.append(clock.now)
        return real(path)

    monkeypatch.setattr(store_writer.platform_os, "try_lock_exclusive", counting)
    second.tick()
    clock.advance(9)
    second.tick()
    clock.advance(1)
    second.tick()
    assert len(tries) == 2
    assert (tries[1] - tries[0]).total_seconds() == 10


# ------------------------------------------------------------------ thread and jobs


def _threaded(
    layout: StoreLayout, config: Config, clock: Clock, writers: list[StoreWriter]
) -> StoreWriter:
    w = make(writers, layout, config, clock)
    w.start()
    return w


def test_submit_runs_a_job_on_the_writer_thread(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = _threaded(layout, config, clock, writers)
    done = threading.Event()
    seen: dict[str, object] = {}

    def job(conn: sqlite3.Connection) -> None:
        seen["thread"] = threading.current_thread().name
        seen["in_tx"] = conn.in_transaction
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT INTO price_copies (fetched_at, source, sha256, bytes, check_ok)"
            " VALUES ('2026-11-01T00:00:00Z', 'litellm', 'abc', 10, 1)"
        )
        conn.execute("COMMIT")
        done.set()

    before = w.generation
    w.submit(job)
    assert done.wait(5)
    assert seen == {"thread": "store-writer", "in_tx": False}
    w.stop()
    conn = reader(layout)
    try:
        assert conn.execute("SELECT COUNT(*) FROM price_copies").fetchone()[0] == 1
    finally:
        conn.close()
    assert w.generation > before


def test_jobs_run_in_order_and_a_failing_job_does_not_stop_the_writer(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    w = make(writers, layout, config, clock)
    order: list[int] = []

    def bad(conn: sqlite3.Connection) -> None:
        conn.execute("BEGIN IMMEDIATE")
        msg = "job failed"
        raise RuntimeError(msg)

    w.submit(lambda _c: order.append(1))
    w.submit(bad)
    w.submit(lambda _c: order.append(2))
    w.tick()
    assert order == [1, 2]
    assert w.snapshot().state == "done"
    assert w._conn is not None  # pyright: ignore[reportPrivateUsage]
    assert not w._conn.in_transaction  # pyright: ignore[reportPrivateUsage]


def test_a_job_write_error_is_a_store_unwritable_failure_that_retries(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().state == "done"

    def bad(_conn: sqlite3.Connection) -> None:
        raise OSError(28, "no space left on device")

    w.submit(bad)
    w.tick()
    snap = w.snapshot()
    assert snap.state == "done"
    assert snap.pass_error == Failure("store_unwritable", str(layout.root))
    assert snap.retry_at is not None
    clock.advance(11)
    w.tick()
    assert w.snapshot().pass_error is None


def _unwritable(_conn: sqlite3.Connection) -> None:
    raise OSError(28, "no space left on device")


def test_pass_error_since_keeps_the_first_failure_through_store_retries(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().pass_error is None
    assert w.snapshot().pass_error_since is None
    first = clock.now
    w.submit(_unwritable)
    w.tick()  # a store_ failure tears the connection down, so meta never hears of it
    snap = w.snapshot()
    assert snap.pass_error == Failure("store_unwritable", str(layout.root))
    assert snap.pass_error_since == first
    real = store.migrate

    def full_disk(_conn: sqlite3.Connection, **_kw: object) -> int:
        raise store.StoreError("store_unwritable", str(layout.root))

    monkeypatch.setattr(store, "migrate", full_disk)
    for _ in range(3):  # each retry fails again, later, with the same failure
        clock.advance(301)
        w.tick()
        again = w.snapshot()
        assert again.pass_error == snap.pass_error
        assert again.pass_error_since == first
    monkeypatch.setattr(store, "migrate", real)
    clock.advance(301)
    w.tick()  # the retry succeeds
    cleared = w.snapshot()
    assert cleared.pass_error is None
    assert cleared.pass_error_since is None


def test_pass_error_since_stays_when_the_failure_code_changes(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    first = clock.now
    w.submit(_unwritable)
    w.tick()
    assert w.snapshot().pass_error_since == first
    shutil.rmtree(config.projects)  # the retry now hits a different code
    clock.advance(11)
    w.tick()
    snap = w.snapshot()
    assert snap.pass_error == Failure("config_dir_missing", str(config.projects))
    assert snap.pass_error_since == first


def test_a_new_failure_after_a_clear_takes_a_new_since(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    w.tick()
    w.submit(_unwritable)
    w.tick()
    clock.advance(11)
    w.tick()
    assert w.snapshot().pass_error is None
    clock.advance(3600)
    second = clock.now
    w.submit(_unwritable)
    w.tick()
    assert w.snapshot().pass_error_since == second


def test_on_ready_runs_once_after_the_store_is_migrated(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)
    seen: list[bool] = []

    def callback() -> None:
        conn = reader(layout)
        try:
            conn.execute("SELECT COUNT(*) FROM requests").fetchone()
            seen.append(True)
        finally:
            conn.close()

    w.on_ready(callback)
    assert seen == []
    w.tick()
    assert seen == [True]
    w.on_ready(callback)  # already migrated, so it runs at once
    assert seen == [True, True]
    clock.advance(60)
    w.tick()
    assert seen == [True, True]


def test_on_ready_waits_for_a_startup_that_fails_then_retries(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed(config)
    real = store.migrate
    attempts = {"n": 0}

    def flaky(conn: sqlite3.Connection, **kw: object) -> int:
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise OSError(28, "no space left on device")
        return real(conn, **kw)  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(store, "migrate", flaky)
    w = make(writers, layout, config, clock)
    calls: list[int] = []
    w.on_ready(lambda: calls.append(attempts["n"]))
    w.tick()
    assert w.snapshot().error is not None
    assert calls == []
    clock.advance(11)
    w.tick()
    assert calls == [2]
    clock.advance(11)
    w.tick()
    assert calls == [2]


def test_a_failing_on_ready_callback_does_not_fail_the_startup(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make(writers, layout, config, clock)

    def boom() -> None:
        raise RuntimeError("callback")

    w.on_ready(boom)
    w.tick()
    assert w.snapshot().state == "done"
    assert w.snapshot().error is None


def test_stop_ends_the_thread_and_releases_the_lock(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = _threaded(layout, config, clock, writers)
    ready = threading.Event()
    w.submit(lambda _c: ready.set())
    assert ready.wait(5)
    clock.advance(2 * 3600)
    w.stop()
    thread = w._thread  # pyright: ignore[reportPrivateUsage]
    assert thread is not None
    assert not thread.is_alive()
    assert (
        len(list(layout.db_backups.iterdir())) == 2
    )  # the start copy and the stop copy
    handle = store_writer.platform_os.try_lock_exclusive(layout.writer_lock)
    assert handle is not None
    handle.release()


def test_stop_during_a_pass_ends_it_after_the_open_batch(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    for i, sid in enumerate((h.S1, h.S2, h.S3)):
        config.write(config.main(sid), [h.assistant(i, f"m{i}", sid=sid)])
    box: list[StoreWriter] = []
    reached = threading.Event()

    def pace(_seconds: float) -> None:
        reached.set()
        box[0]._wake.wait(5)  # pyright: ignore[reportPrivateUsage]

    w = make(writers, layout, config, clock, pace_ms=1, sleep=pace)
    box.append(w)
    w.start()
    assert reached.wait(5)  # one file is read and committed
    w.stop()
    conn = reader(layout)
    try:
        assert conn.execute("SELECT COUNT(*) FROM files").fetchone()[0] == 1
        assert history.read_history(conn).pass_running_since is None
    finally:
        conn.close()
    assert w.snapshot().state != "done"


def test_a_nudge_runs_one_attempt_and_keeps_the_schedule_when_it_fails(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.rmtree(config.projects)
    runs: list[int] = []
    real = ingest.Ingestor._top_folders  # pyright: ignore[reportPrivateUsage]

    def count(self: ingest.Ingestor, scope: ingest.PassScope) -> object:
        runs.append(1)
        return real(self, scope)

    monkeypatch.setattr(ingest.Ingestor, "_top_folders", count)
    w = make(writers, layout, config, clock)
    w.tick()
    w.nudge_retry()
    w.tick()
    assert len(runs) == 2  # not three
    assert w.snapshot().retry_at == clock.now + timedelta(seconds=30)
    w.nudge_retry()
    w.tick()
    assert len(runs) == 3
    assert w.snapshot().retry_at == clock.now + timedelta(seconds=60)


# ------------------------------------------------------------------ active loop


def _keys(layout: StoreLayout) -> set[str]:
    conn = reader(layout)
    try:
        return {str(r[0]) for r in conn.execute("SELECT key FROM requests")}
    finally:
        conn.close()


def test_active_folders_are_checked_every_half_second_running_ones_every_second(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    live = config.main(h.S1, "-work-live")
    warm = config.main(h.S2, "-work-warm")
    config.write(live, [h.assistant(595, "a")])  # 5 s before the clock: active
    config.write(warm, [h.assistant(300, "w", sid=h.S2)])  # 5 minutes: running only
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.snapshot().state == "done"
    config.append(live, [h.assistant(598, "a2")])
    config.append(warm, [h.assistant(301, "w2", sid=h.S2)])
    assert w.tick() == pytest.approx(0.5)  # an active session shortens the wait
    clock.advance(0.5)
    w.tick()  # active
    assert _keys(layout) == {"a", "a2", "w"}  # the running-only folder waits
    assert w.tick() == pytest.approx(0.5)
    clock.advance(0.5)
    w.tick()  # hot, which covers every running folder
    assert _keys(layout) == {"a", "a2", "w", "w2"}


def test_a_hot_pass_restarts_the_active_timer(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.write(config.main(), [h.assistant(595, "a")])
    w = make(writers, layout, config, clock)
    w.tick()
    clock.advance(1.0)
    w.tick()  # hot
    assert w.tick() == pytest.approx(0.5)  # the active timer began again


def test_the_active_loop_ends_when_the_session_goes_quiet(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.write(config.main(), [h.assistant(595, "a")])
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.tick() == pytest.approx(0.5)
    clock.advance(10)
    w.tick()  # cold, 15 s after the request
    assert w.tick() == pytest.approx(0.5)  # still inside 60 s
    clock.advance(55)  # 70 s after the request
    w.tick()  # a cold pass finds nobody active
    assert w.tick() == pytest.approx(1.0)  # back to the hot interval


def test_a_quiet_store_wakes_once_a_second(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.write(config.main(), [h.assistant(0, "a")])  # ten minutes old
    w = make(writers, layout, config, clock)
    w.tick()
    assert w.tick() == pytest.approx(1.0)


# ------------------------------------------------------------------ health


def health_of(layout: StoreLayout) -> dict[str, object]:
    return json.loads((layout.root / "run" / "health.json").read_text())


def make_health(
    writers: list[StoreWriter], layout: StoreLayout, config: Config, clock: Clock
) -> StoreWriter:
    (layout.root / "run").mkdir(parents=True, exist_ok=True)
    path = layout.root / "run" / "health.json"
    return make(writers, layout, config, clock, health_path=path)


def test_the_first_pass_writes_the_health_file_with_numbers_only(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make_health(writers, layout, config, clock)
    w.tick()
    body = health_of(layout)
    assert set(body) == {"at", "hot_pass_ms", "cold_pass_ms", "lag_ms"}
    assert body["at"] == NOW.isoformat()
    assert isinstance(body["cold_pass_ms"], int)
    assert body["hot_pass_ms"] == 0  # no hot pass has run
    assert body["lag_ms"] is None  # the first full pass measures no lag
    assert str(layout.root) not in json.dumps(body)
    mode = (layout.root / "run" / "health.json").stat().st_mode & 0o777
    assert mode == 0o600
    assert not list((layout.root / "run").glob(".health-*"))  # no temp file is left


def test_the_lag_is_the_pass_end_minus_the_changed_files_mtime(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make_health(writers, layout, config, clock)
    w.tick()
    clock.advance(31)  # past the 30 s health interval
    path = config.main(h.S1)
    config.append(path, [h.assistant(640, "c")])
    stamp = (clock.now - timedelta(seconds=0.4)).timestamp()
    os.utime(path, (stamp, stamp))
    w.tick()  # a cold pass reads the file
    body = health_of(layout)
    assert body["lag_ms"] == pytest.approx(400, abs=2)
    assert body["at"] == clock.now.isoformat()
    assert isinstance(body["cold_pass_ms"], int)


def test_a_hot_pass_sets_the_hot_time(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    config.write(config.main(), [h.assistant(595, "a")])
    w = make_health(writers, layout, config, clock)
    w.tick()
    clock.advance(31)
    w.tick()  # a cold pass, so the file is rewritten
    clock.advance(1)
    config.append(config.main(), [h.assistant(640, "b")])
    w.tick()  # a hot pass: not written yet, under 30 s since the last write
    assert health_of(layout)["at"] == (NOW + timedelta(seconds=31)).isoformat()
    clock.advance(30)
    w.tick()
    assert health_of(layout)["at"] != (NOW + timedelta(seconds=31)).isoformat()


def test_the_health_file_is_written_at_most_every_thirty_seconds(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    w = make_health(writers, layout, config, clock)
    w.tick()
    first = (layout.root / "run" / "health.json").read_bytes()
    for _ in range(5):
        clock.advance(10)
        w.tick()  # a cold pass every ten seconds, 50 s in all
    mid = health_of(layout)["at"]
    assert mid != json.loads(first)["at"]
    assert mid == (NOW + timedelta(seconds=30)).isoformat()  # the 30 s pass only


def test_a_health_path_outside_the_store_is_never_written(
    config: Config,
    layout: StoreLayout,
    clock: Clock,
    writers: list[StoreWriter],
    tmp_path: Path,
) -> None:
    seed(config)
    outside = tmp_path / "outside" / "health.json"
    outside.parent.mkdir()
    w = make(writers, layout, config, clock, health_path=outside)
    w.tick()
    assert w.snapshot().state == "done"
    assert list(outside.parent.iterdir()) == []


def test_a_health_write_that_fails_never_fails_the_pass(
    config: Config, layout: StoreLayout, clock: Clock, writers: list[StoreWriter]
) -> None:
    seed(config)
    path = layout.root / "no-such-folder" / "h.json"
    w = make(writers, layout, config, clock, health_path=path)
    w.tick()  # the run folder is missing, so the write fails and the pass goes on
    assert w.snapshot().state == "done"
    assert w.snapshot().pass_error is None
