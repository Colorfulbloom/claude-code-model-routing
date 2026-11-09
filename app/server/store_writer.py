"""The one thread that writes the Bar Tab store.

``StoreWriter`` takes ``writer.lock``, opens the only write connection, checks and
migrates the store, and then runs ingest passes on a schedule. Every other writer
hands a job to ``submit`` and the job runs on this thread, between passes. A second
server that cannot take the lock runs as a follower. It writes nothing, reads the
holder's progress from ``meta`` through ``history.read_history``, and tries the lock
again every ten seconds.

Schedule. A full pass runs at start. Then a hot pass every second over the folders of
running sessions (a request in the last 30 minutes) and a cold pass every ten seconds
over every folder. A backup runs after the migration when one is due, again about
once a day, and once more at a clean stop unless a good copy is under an hour old.

Failures. A whole-run failure carries one of six codes (``config_dir_missing``,
``config_dir_unreadable``, ``store_unwritable``, ``store_damaged``, ``store_newer``,
``unexpected``). One unreadable transcript is not a failure, it counts in
``files.read_errors``. A failed run retries after 10 s, 30 s and 60 s, then every five
minutes. ``nudge_retry`` starts a retry at once.

First run. ``snapshot().state`` reports the first full ingest only. Once
``meta.first_ingest`` is set the state stays ``done``, and a later whole-pass failure
goes to ``meta.pass_error`` through ``history.write_pass_meta``. The snapshot is read
without the database, behind a lock. The clock and the sleep are injected, so tests
never wait in real time. ``startup`` and ``tick`` are what the thread calls. A test may
call them itself, on one thread, instead of starting the thread.
"""

import logging
import queue
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, get_args

import backup
import history
import ingest
import platform_os
import store
import store_paths
from store_paths import StoreLayout

logger = logging.getLogger(__name__)

IngestState = Literal["waiting", "running", "done", "failed"]
FailureCode = Literal[
    "config_dir_missing",
    "config_dir_unreadable",
    "store_unwritable",
    "store_damaged",
    "store_newer",
    "unexpected",
]
Job = Callable[[sqlite3.Connection], None]

RETRY_DELAYS = (10.0, 30.0, 60.0)
RETRY_STEADY = 300.0
HOT_INTERVAL = 1.0
COLD_INTERVAL = 10.0
FOLLOWER_INTERVAL = 10.0
AS_OF_REFRESH = timedelta(seconds=10)
BACKUP_RETRY = timedelta(hours=1)


@dataclass(frozen=True)
class Failure:
    """A whole-run failure. ``file`` is the folder or file it concerns, or None."""

    code: FailureCode
    file: str | None = None


@dataclass(frozen=True)
class WriterSnapshot:
    """What the page needs about ingest, read without the database.

    ``files_total`` and ``bytes_total`` are None while folders are listed, then fixed
    for the pass. ``error`` is the last whole-run failure of the first ingest and
    stays through automatic retries until a run succeeds. After the first ingest
    ``error`` is None and a failure shows in ``pass_error`` (and in
    ``history.pass_error``). ``retrying`` is True while a retry run executes and
    ``retry_at`` is when the next automatic retry starts. ``generation`` counts the
    changes to store data, for etags. ``follower`` is True when another process holds
    the writer lock. ``pass_error_since`` is when ``pass_error`` first appeared. It
    stays the same while the failure repeats through retries, whatever its code, and
    clears with ``pass_error``.
    """

    state: IngestState = "waiting"
    files_done: int = 0
    bytes_done: int = 0
    files_total: int | None = None
    bytes_total: int | None = None
    error: Failure | None = None
    retrying: bool = False
    retry_at: datetime | None = None
    generation: int = 0
    follower: bool = False
    pass_error: Failure | None = None
    pass_error_since: datetime | None = None


def _as_code(text: str) -> FailureCode:
    """Narrow stored code text to a failure code, ``unexpected`` when unknown."""
    for code in get_args(FailureCode):
        if code == text:
            return code
    return "unexpected"


class _Sink(ingest.ProgressSink):
    """Feeds ingest progress to the writer's snapshot and pass meta."""

    def __init__(self, writer: "StoreWriter", scope: ingest.PassScope) -> None:
        self._writer = writer
        self._scope = scope

    def listing(self) -> None:
        if self._writer.reporting_first_run:
            self._writer.update(
                state="running",
                files_done=0,
                bytes_done=0,
                files_total=None,
                bytes_total=None,
            )

    def totals(self, files: int, bytes_: int) -> None:
        if self._writer.reporting_first_run:
            self._writer.update(files_total=files, bytes_total=bytes_)

    def done(self, files: int, bytes_: int) -> None:
        if self._writer.reporting_first_run:
            self._writer.update(files_done=files, bytes_done=bytes_)

    def has_work(self) -> None:
        if self._scope.kind != "full":
            self._writer.pass_meta("start", full=False)


class StoreWriter:
    """The only writer of one store. See the module docstring."""

    def __init__(  # noqa: PLR0913 - collaborators and intervals, keyword-only
        self,
        layout: StoreLayout,
        claude_dir: Path,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], None] | None = None,
        tier_policy: ingest.TierPolicy | None = None,
        pace_ms: int = 0,
        log_path: str | None = None,
        hot_interval: float = HOT_INTERVAL,
        cold_interval: float = COLD_INTERVAL,
        follower_interval: float = FOLLOWER_INTERVAL,
    ) -> None:
        """Set up a writer. Nothing opens until ``startup`` or ``start``.

        Args:
            layout: The store folders.
            claude_dir: The Claude config folder (transcripts under ``projects/``).
            clock: Returns the current aware time. Every schedule reads it.
            sleep: Waits for a number of seconds. The default wakes early on a job,
                a nudge or a stop.
            tier_policy: Price tiers for ``minute_usage``. Defaults to the old table.
            pace_ms: Sleep this long after each file. For the demo only.
            log_path: The log file named in an ``unexpected`` failure.
            hot_interval: Seconds between hot passes.
            cold_interval: Seconds between cold passes.
            follower_interval: Seconds between lock attempts when a follower.
        """
        self.layout = layout
        self.claude_dir = claude_dir
        self._clock = clock
        self._wake = threading.Event()
        self._sleep = sleep if sleep is not None else self._default_sleep
        self._tier = tier_policy
        self._pace_s = max(pace_ms, 0) / 1000
        self._log_path = log_path
        self._hot = hot_interval
        self._cold = cold_interval
        self._follow = follower_interval

        self._stop = threading.Event()
        self._jobs: queue.SimpleQueue[Job] = queue.SimpleQueue()
        self._thread: threading.Thread | None = None
        self._snap_lock = threading.Lock()
        self._snap = WriterSnapshot()
        self._nudged = False

        self._lock: platform_os.LockHandle | None = None
        self._conn: sqlite3.Connection | None = None
        self._ingestor: ingest.Ingestor | None = None
        self._ready = False
        self._ready_lock = threading.Lock()
        self._migrated = False
        self._ready_callbacks: list[Callable[[], None]] = []
        self._first_done = False
        self._full_done = False
        self._attempt = 0
        self._retry_at: datetime | None = None
        self._next_hot = datetime.min.replace(tzinfo=UTC)
        self._next_cold = datetime.min.replace(tzinfo=UTC)
        self._next_follow = datetime.min.replace(tzinfo=UTC)
        self._next_backup_try = datetime.min.replace(tzinfo=UTC)
        self._last_ok_write = datetime.min.replace(tzinfo=UTC)

    # ------------------------------------------------------------ public

    def snapshot(self) -> WriterSnapshot:
        """Return the progress snapshot. Thread-safe and never touches the database."""
        with self._snap_lock:
            return self._snap

    @property
    def generation(self) -> int:
        """The data generation, for etags."""
        return self.snapshot().generation

    @property
    def reporting_first_run(self) -> bool:
        """True until the first full ingest has finished."""
        return not self._first_done

    def submit(self, job: Job) -> None:
        """Queue a job. It runs on the writer thread with the write connection.

        Jobs run between passes, in the order submitted. A follower keeps them
        queued until it takes the lock.
        """
        self._jobs.put(job)
        self._wake.set()

    def on_ready(self, callback: Callable[[], None]) -> None:
        """Call ``callback`` once, as soon as this writer has migrated the store.

        The callback runs on the writer thread right after ``startup`` migrates the
        store, or at once on the calling thread when that already happened. It runs
        at most once, so a startup that fails and retries calls it on the first try
        that migrates, and never twice. A callback that raises is logged and ignored.
        Nothing runs when the writer never gets that far (a stop during the hold, a
        follower that never takes the lock), so a callback never needs to be waited on.
        """
        with self._ready_lock:
            if not self._migrated:
                self._ready_callbacks.append(callback)
                return
        self._call_ready(callback)

    def _announce_ready(self) -> None:
        with self._ready_lock:
            self._migrated = True
            callbacks, self._ready_callbacks = self._ready_callbacks, []
        for callback in callbacks:
            self._call_ready(callback)

    @staticmethod
    def _call_ready(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            logger.exception("a store writer ready callback failed")

    def nudge_retry(self) -> None:
        """Start a retry now, when a failed run is waiting for its next retry."""
        self._nudged = True
        self._wake.set()

    def start(self) -> None:
        """Start the writer thread. Safe to call once."""
        if self._thread is not None:
            return
        thread = threading.Thread(target=self._run, name="store-writer", daemon=True)
        self._thread = thread
        thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """End the loop and join the thread, which then runs the stop backup.

        With no thread started, the stop backup runs here, on the calling thread.
        """
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is None:
            self.shutdown()
            return
        thread.join(timeout)
        if thread.is_alive():
            logger.warning("the store writer did not stop in %s seconds", timeout)

    # ------------------------------------------------------------ snapshot

    def update(self, **fields: object) -> None:
        """Change snapshot fields. The ingest sink and the passes call this.

        ``pass_error_since`` follows ``pass_error`` unless the caller names it. A new
        ``pass_error`` takes the clock when none was set and keeps the old time
        otherwise, and clearing ``pass_error`` clears it.
        """
        with self._snap_lock:
            if "pass_error" in fields and "pass_error_since" not in fields:
                if fields["pass_error"] is None:
                    fields["pass_error_since"] = None
                elif (
                    self._snap.pass_error is None or self._snap.pass_error_since is None
                ):
                    fields["pass_error_since"] = self._clock()
            self._snap = replace(self._snap, **fields)  # pyright: ignore[reportArgumentType]

    def _bump(self) -> None:
        with self._snap_lock:
            self._snap = replace(self._snap, generation=self._snap.generation + 1)

    # ------------------------------------------------------------ thread

    def _default_sleep(self, seconds: float) -> None:
        self._wake.wait(seconds)

    def _run(self) -> None:
        try:
            while not self._stop.is_set():
                self._wake.clear()
                wait = self.tick()
                if self._stop.is_set():
                    break
                self._sleep(wait)
        finally:
            self.shutdown()

    # ------------------------------------------------------------ steps

    def tick(self) -> float:
        """Do whatever is due, then return the seconds to wait before the next call.

        It never raises. A failure becomes a snapshot error and a retry time.
        """
        now = self._clock()
        try:
            self._tick(now)
        except Exception as exc:  # noqa: BLE001 - the loop must survive anything
            self._fail(exc, now)
        return self._wait_seconds()

    def _tick(self, now: datetime) -> None:
        nudged, self._nudged = self._nudged, False
        if not self._ready:
            if self._retry_at is not None and now < self._retry_at and not nudged:
                return
            if self._lock is None and not self._try_lock(now, nudged=nudged):
                return
            self._attempt_run(now, retry=self._retry_at is not None)
            nudged = False  # the attempt above was the retry
            if not self._ready:
                return
            now = self._clock()
        self._run_jobs()
        if self._retry_at is not None:
            if nudged or now >= self._retry_at:
                self._attempt_run(now, retry=True)
            return
        if not self._full_done:
            self._attempt_run(now, retry=False)
            return
        self._scheduled(now)

    def _wait_seconds(self) -> float:
        now = self._clock()
        if not self._ready:
            due = max(self._retry_at or self._next_follow, self._next_follow)
        elif self._retry_at is not None:
            due = self._retry_at
        elif self._full_done:
            due = min(self._next_hot, self._next_cold)
        else:
            due = now
        return max((due - now).total_seconds(), 0.0)

    # ------------------------------------------------------------ lock and startup

    def _try_lock(self, now: datetime, *, nudged: bool) -> bool:
        """Take the writer lock. False means follower: the lock is held elsewhere."""
        if not nudged and now < self._next_follow:
            return False
        try:
            root = store_paths.writable(self.layout, self.layout.root)
            platform_os.mkdir_private(root, parents=True)
            handle = platform_os.try_lock_exclusive(
                store_paths.writable(self.layout, self.layout.writer_lock)
            )
        except OSError as exc:
            raise store.map_error(exc, str(self.layout.root)) from exc
        if handle is None:
            self._next_follow = now + timedelta(seconds=self._follow)
            self._follower_snapshot()
            return False
        self._lock = handle
        self.update(follower=False)
        return True

    def _follower_snapshot(self) -> None:
        """Report the holder's progress from ``meta``. Reads only."""
        fields: dict[str, object] = {"follower": True}
        try:
            reader = store.open_reader(self.layout)
        except store.StoreError:
            self.update(**fields)
            return
        try:
            status = history.read_history(reader)
        except sqlite3.Error:
            self.update(**fields)
            return
        finally:
            reader.close()
        if status.first_ingest is not None:
            fields["state"] = "done"
        elif status.pass_running_since is not None:
            fields["state"] = "running"
        else:
            fields["state"] = "waiting"
        if status.pass_error is not None:
            fields["pass_error"] = Failure(
                _as_code(status.pass_error.code), status.pass_error.file
            )
            fields["pass_error_since"] = status.pass_error.since
        self.update(**fields)

    def startup(self) -> None:
        """Open the write connection, check it, migrate and make a due backup.

        ``tick`` takes the lock before it calls this. Raises ``StoreError`` or
        ``sqlite3.Error`` on failure.
        """
        conn = store.open_writer(self.layout)
        self._conn = conn
        if not store.quick_check(conn):
            raise store.StoreError("store_damaged", str(self.layout.db))

        def copy_first(_old: int) -> None:
            backup.make_backup(conn, self.layout, now=self._clock())

        store.migrate(conn, before_migrate=copy_first)
        self._ingestor = ingest.Ingestor(
            conn,
            self.claude_dir,
            clock=self._clock,
            tier_policy=self._tier,
            pace=self._pace if self._pace_s > 0 else None,
            cancel=self._stop.is_set,
        )
        self._announce_ready()
        status = history.read_history(conn)
        if status.first_ingest is not None:
            self._first_done = True
            self.update(state="done")
        self._maybe_backup(self._clock(), force_check=True)
        self._ready = True

    def _pace(self) -> None:
        self._sleep(self._pace_s)

    # ------------------------------------------------------------ passes

    def _attempt_run(self, now: datetime, *, retry: bool) -> None:
        """Start up when needed, then run a full pass. Failures schedule a retry."""
        if retry:
            self.update(retrying=True, retry_at=None)
            if not self._first_done:
                self.update(state="running")
        try:
            if not self._ready:
                self.startup()
            self._run_pass(ingest.PassScope("full"))
        except Exception as exc:  # noqa: BLE001 - classified below
            self._fail(exc, now)
            return
        self._attempt = 0
        self._retry_at = None
        self.update(retrying=False, retry_at=None, error=None, pass_error=None)

    def _scheduled(self, now: datetime) -> None:
        conn, runner = self._conn, self._ingestor
        if conn is None or runner is None:
            return
        try:
            if now >= self._next_cold:
                self._run_pass(ingest.PassScope("cold"))
                after = self._clock()
                self._next_cold = after + timedelta(seconds=self._cold)
                self._next_hot = after + timedelta(seconds=self._hot)
                self._maybe_backup(after)
            elif now >= self._next_hot:
                folders = runner.running_folders(now)
                if folders:
                    self._run_pass(ingest.PassScope("hot", folders))
                self._next_hot = self._clock() + timedelta(seconds=self._hot)
        except Exception as exc:  # noqa: BLE001 - classified below
            self._fail(exc, now)
            return
        self.update(pass_error=None)

    def _run_pass(self, scope: ingest.PassScope) -> None:
        conn, runner = self._conn, self._ingestor
        if conn is None or runner is None:
            msg = "the writer is not started"
            raise RuntimeError(msg)
        full = scope.kind == "full"
        runner.progress = _Sink(self, scope)
        if full:
            self.pass_meta("start", full=True)
        result = runner.run_pass(scope)
        if result.cancelled:
            conn.execute("DELETE FROM meta WHERE key = ?", (history.KEY_RUNNING,))
            return
        ended = self._clock()
        if full or result.changed or ended - self._last_ok_write >= AS_OF_REFRESH:
            self.pass_meta("ok", full=full)
            self._last_ok_write = ended
        if result.changed or full:
            self._bump()
        if full:
            self._full_done = True
            self._first_done = True
            self._next_cold = ended + timedelta(seconds=self._cold)
            self._next_hot = ended + timedelta(seconds=self._hot)
            self.update(state="done")

    def pass_meta(self, event: history.PassEvent, *, full: bool) -> None:
        """Write a pass event to ``meta`` on the writer connection."""
        conn = self._conn
        if conn is None:
            return
        history.write_pass_meta(conn, event, at=self._clock(), full=full)

    # ------------------------------------------------------------ failures

    def _failure_for(self, exc: BaseException) -> Failure:
        if isinstance(exc, ingest.IngestError):
            return Failure(exc.code, exc.file)
        if isinstance(exc, store.StoreError):
            return Failure(exc.code, exc.file)
        if isinstance(exc, sqlite3.Error):
            mapped = store.map_error(exc, str(self.layout.db))
            return Failure(mapped.code, mapped.file)
        logger.error("unexpected store writer failure", exc_info=exc)
        return Failure("unexpected", self._log_path)

    def _fail(self, exc: BaseException, now: datetime) -> None:
        """Record a whole-run failure and schedule the next retry."""
        failure = self._failure_for(exc)
        conn = self._conn
        if conn is not None and conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                logger.warning("could not roll back after a failure")
        if failure.code.startswith("store_") or not self._ready:
            self._teardown()
        delay = (
            RETRY_DELAYS[self._attempt]
            if self._attempt < len(RETRY_DELAYS)
            else RETRY_STEADY
        )
        self._attempt += 1
        self._retry_at = now + timedelta(seconds=delay)
        fields: dict[str, object] = {"retrying": False, "retry_at": self._retry_at}
        if self._first_done:
            fields["pass_error"] = failure
        else:
            fields.update(state="failed", error=failure)
        self.update(**fields)
        if self._first_done and self._conn is not None:
            try:
                history.write_pass_meta(
                    self._conn,
                    "failed",
                    at=now,
                    code=failure.code,
                    file=failure.file,
                )
            except sqlite3.Error:
                logger.warning("could not record the pass error")

    def _teardown(self) -> None:
        """Close the connection and drop the lock so the next try starts clean."""
        conn, self._conn = self._conn, None
        self._ingestor = None
        self._ready = False
        self._full_done = False
        if conn is not None:
            try:
                conn.close()
            except sqlite3.Error:
                logger.warning("could not close the store connection")
        lock, self._lock = self._lock, None
        if lock is not None:
            lock.release()

    # ------------------------------------------------------------ jobs and backups

    def _run_jobs(self) -> None:
        conn = self._conn
        if conn is None:
            return
        while True:
            try:
                job = self._jobs.get_nowait()
            except queue.Empty:
                return
            try:
                job(conn)
                self._bump()
            except OSError as exc:
                # A write error is a whole-run failure, so it takes the retry path.
                raise store.map_error(exc, str(self.layout.root)) from exc
            except Exception:
                logger.exception("a store writer job failed")
            finally:
                if conn.in_transaction:
                    logger.warning("a store writer job left a transaction open")
                    conn.execute("ROLLBACK")

    def _maybe_backup(self, now: datetime, *, force_check: bool = False) -> None:
        conn = self._conn
        if conn is None or (now < self._next_backup_try and not force_check):
            return
        if not backup.backup_due(conn, now=now):
            return
        result = backup.make_backup(conn, self.layout, now=now)
        if not result.ok:
            self._next_backup_try = now + BACKUP_RETRY

    def shutdown(self) -> None:
        """Make the stop backup when one is due, then close and release the lock."""
        conn = self._conn
        if conn is not None and self._ready:
            try:
                now = self._clock()
                if backup.stop_backup_due(conn, now=now):
                    backup.make_backup(conn, self.layout, now=now)
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("the stop backup failed")
        self._teardown()
