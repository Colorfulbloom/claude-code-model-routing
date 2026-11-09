"""The real provider, answering from the store behind the ``Provider`` protocol.

The writer thread fills the store and keeps a progress snapshot. This provider reads
that snapshot for ingest progress, and a short read connection for everything else
(history, ``as_of``, running sessions and prices). It also owns the writer and the
price feed, so the server's lifespan starts and stops them with one call each. The
stop runs the writer's clean-stop backup.

``ingest.state`` follows the first-run rule: once ``history.first_ingest`` is set it
stays ``done``, and a later whole-pass failure shows under ``history.pass_error``.
"""

import json
import logging
import sqlite3
import threading
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast, get_args

import history
import ingest
import price_feed
import price_transport
import project_map
import projects
import store
import store_writer
from models import (
    AppInfo,
    BackupFailure,
    BackupReasonCode,
    HistoryInfo,
    Ingest,
    IngestError,
    IngestErrorCode,
    PassError,
    PricesInfo,
    Project,
    ProjectList,
    RunningItem,
)
from store_paths import StoreLayout

logger = logging.getLogger(__name__)

RUNNING_WINDOW = timedelta(minutes=30)
# A paced demo ingest starts this long after the server, so the page can show its
# "Counting files" step before the first totals arrive. Off when there is no pace.
PACED_HOLD_SECONDS = 2.0
MAPPING_TTL_SECONDS = 5.0
DEMO_SESSION_FILE = "session.json"


def _error_code(text: str) -> IngestErrorCode:
    for code in get_args(IngestErrorCode):
        if code == text:
            return code
    return "unexpected"


def _backup_code(text: str) -> BackupReasonCode:
    for code in get_args(BackupReasonCode):
        if code == text:
            return code
    return "copy_failed"


def demo_claude_version(claude_dir: Path) -> str:
    """Read ``claude_version`` from the demo build's ``session.json``.

    The file sits beside the demo's config folder. A missing or odd file gives "".
    """
    try:
        data = cast(
            "object",
            json.loads(
                (claude_dir.parent / DEMO_SESSION_FILE).read_text(encoding="utf-8")
            ),
        )
    except (OSError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    version = cast("dict[str, object]", data).get("claude_version")
    return version if isinstance(version, str) else ""


def open_read(layout: StoreLayout) -> sqlite3.Connection:
    """Open a read connection, or an empty in-memory store before the file exists.

    The writer creates the file a moment after the server starts, and the first
    reads can come before that, or land after the file exists but before the
    migrations finish. An empty store answers them the same way a store with no
    rows does. A store newer than this build is returned as is, for the writer's
    store_newer path to report.
    """
    try:
        conn = store.open_reader(layout)
    except store.StoreError:
        return _empty_store()
    try:
        behind = store.user_version(conn) < store.latest_version()
    except sqlite3.Error:
        conn.close()
        raise
    if behind:
        conn.close()
        return _empty_store()
    return conn


def _empty_store() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", isolation_level=None)
    store.migrate(conn)
    return conn


def tier_policy(settings: price_feed.PriceSettings, now: float) -> ingest.TierPolicy:
    """Build the price-tier policy from the effective price table.

    Before the store exists there are no fetched copies, so the bundled copy answers.
    """
    catalog = settings.models()
    try:
        conn = store.open_reader(settings.layout)
    except store.StoreError:
        document, _as_of = price_feed.load_bundled(settings.bundled_dir, catalog)
        return ingest.tier_policy_from_prices(document, catalog)
    try:
        table = price_feed.price_table(conn, settings, now=now)
    finally:
        conn.close()
    return ingest.tier_policy_from_prices(table.document, catalog)


class StoreProvider:
    """Serve ``/api/app``, ``/api/projects`` and ``/api/prices`` from the store."""

    def __init__(  # noqa: PLR0913 - collaborators, keyword-only
        self,
        *,
        layout: StoreLayout,
        claude_dir: Path,
        writer: store_writer.StoreWriter,
        price_settings: price_feed.PriceSettings,
        feed: price_feed.PriceFeed | None = None,
        clock: Callable[[], float] = time.time,
        claude_version: str = "",
        project_dir: Path | None = None,
        hold_seconds: float = 0.0,
    ) -> None:
        """Wire the provider. Nothing starts until ``start``.

        Args:
            layout: The store folders.
            claude_dir: The Claude config folder (the demo's config folder in M1).
            writer: The store writer this provider reports on and owns.
            price_settings: Where the price sources are.
            feed: The price feed to start and stop, or None.
            clock: Epoch seconds. Running sessions and prices read it.
            claude_version: What ``/api/app`` reports as ``claude_version``.
            project_dir: The launch project's folder, the fallback when no project
                list exists. Defaults to the Claude folder.
            hold_seconds: Wait this long after ``start`` before the writer starts.
        """
        self._layout = layout
        self._claude_dir = claude_dir
        self._writer = writer
        self._prices = price_settings
        self._feed = feed
        self._clock = clock
        self._version = claude_version
        self._project_dir = project_dir if project_dir is not None else claude_dir
        self._hold = hold_seconds
        self._hold_timer: threading.Timer | None = None
        self._feed_lock = threading.Lock()
        self._stopped = False
        self._mapped: tuple[float, list[project_map.MappedProject]] | None = None
        self._price_cache: tuple[tuple[object, ...], PricesInfo] | None = None

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        """Start the writer thread. The price feed starts once the store is migrated.

        The feed reads the store, so it waits for the writer's ``startup`` to create
        its tables. That holds through the hold timer and through a startup that fails
        and retries. A stop before then means the feed never starts.
        """
        if self._feed is not None:
            self._writer.on_ready(self._start_feed)
        if self._hold > 0:
            self._hold_timer = threading.Timer(self._hold, self._writer.start)
            self._hold_timer.daemon = True
            self._hold_timer.start()
        else:
            self._writer.start()

    def _start_feed(self) -> None:
        with self._feed_lock:
            if self._feed is not None and not self._stopped:
                self._feed.start()

    def stop(self) -> None:
        """Stop the feed, then the writer, which makes the clean-stop backup."""
        if self._hold_timer is not None:
            self._hold_timer.cancel()
            self._hold_timer.join()
        with self._feed_lock:
            self._stopped = True
        if self._feed is not None:
            self._feed.stop()
        self._writer.stop()

    def nudge_retry(self) -> None:
        """Ask a failed ingest to retry now."""
        self._writer.nudge_retry()

    # ------------------------------------------------------------ reads

    def now(self) -> datetime:
        """Return the provider's clock as an aware UTC time."""
        return datetime.fromtimestamp(self._clock(), tz=UTC)

    @contextmanager
    def _reader(self) -> Generator[sqlite3.Connection]:
        """Yield a short read connection, closed on exit."""
        conn = open_read(self._layout)
        try:
            yield conn
        finally:
            conn.close()

    def _mapped_projects(
        self, conn: sqlite3.Connection
    ) -> list[project_map.MappedProject]:
        now = self._clock()
        cached = self._mapped
        if cached is not None and now - cached[0] < MAPPING_TTL_SECONDS:
            return cached[1]
        ctx = projects.ProjectsContext(
            config_dir=str(self._claude_dir), project_dir=str(self._project_dir)
        )
        mapped = project_map.map_projects(ctx, conn)
        self._mapped = (now, mapped)
        return mapped

    def _running_sessions(
        self, conn: sqlite3.Connection, mapped: list[project_map.MappedProject]
    ) -> list[RunningItem]:
        cutoff = ingest.ts_text(self.now() - RUNNING_WINDOW)
        rows = conn.execute(
            "SELECT session_id, folder FROM sessions WHERE last_ts >= ?"
            " ORDER BY session_id",
            (cutoff,),
        ).fetchall()
        key_of: dict[str, str] = {}
        for item in mapped:
            for folder in item.folders:
                key_of.setdefault(folder, item.key)
        return [
            RunningItem(project=key_of[str(folder)], session=str(session))
            for session, folder in rows
            if str(folder) in key_of
        ]

    def projects(self) -> ProjectList:
        """Return the mapped projects with each one's running flag."""
        with self._reader() as conn:
            mapped = self._mapped_projects(conn)
            running = {item.project for item in self._running_sessions(conn, mapped)}
        return ProjectList(
            projects=[
                Project(
                    key=item.key,
                    name=item.name,
                    display_path=item.display_path,
                    state=item.state,  # pyright: ignore[reportArgumentType]
                    running=item.key in running,
                )
                for item in mapped
            ]
        )

    def resolve_project(
        self, project_dir: Path | None, *, first_if_none: bool = False
    ) -> str | None:
        """Return the key of the project that matches a folder, or None.

        A project matches when its path is the folder, or when the folder's name as a
        slug is a project key. With ``first_if_none`` a folder that matches nothing
        gets the first listed project, so the demo never opens on the picker.
        """
        if project_dir is None:
            return None
        with self._reader() as conn:
            mapped = self._mapped_projects(conn)
        text = str(project_dir)
        for item in mapped:
            if item.display_path == text:
                return item.key
        slug = projects.slug(project_dir.name)
        if any(item.key == slug for item in mapped):
            return slug
        return mapped[0].key if first_if_none and mapped else None

    def prices(self) -> PricesInfo:
        """Return the price table, rebuilt only when the table or its checks change."""
        with self._reader() as conn:
            answer = price_feed.current_prices(conn, self._prices, now=self._clock())
        key: tuple[object, ...] = (
            answer.etag,
            answer.source,
            answer.as_of,
            answer.cross_check.state,
            answer.cross_check.models,
            tuple(row.source for row in answer.models),
        )
        cached = self._price_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        info = PricesInfo.model_validate(_prices_payload(answer))
        self._price_cache = (key, info)
        return info

    def _history(self, status: history.HistoryStatus) -> HistoryInfo:
        snap = self._writer.snapshot()
        snap_error = snap.pass_error
        pass_error: PassError | None = None
        if status.pass_error is not None:
            pass_error = PassError(
                code=_error_code(status.pass_error.code),
                file=status.pass_error.file,
                since=status.pass_error.since,
            )
        elif snap_error is not None:
            # The first failure's time, kept by the writer. ``now`` only when the
            # snapshot has none, which a failure that just appeared can show.
            snap_since = snap.pass_error_since
            pass_error = PassError(
                code=snap_error.code,
                file=snap_error.file,
                since=snap_since if snap_since is not None else self.now(),
            )
        failed = status.backup_failed
        return HistoryInfo(
            oldest=status.oldest,
            first_ingest=status.first_ingest,
            last_backup=status.last_backup,
            backup_failed=None
            if failed is None
            else BackupFailure(
                at=failed.at, reason_code=_backup_code(failed.reason_code)
            ),
            pass_error=pass_error,
            unreadable_files=status.unreadable_files,
            kept_files=status.kept_files,
            no_usage_rows=status.no_usage_rows,
        )

    def _ingest(self, status: history.HistoryStatus) -> Ingest:
        snap = self._writer.snapshot()
        if status.first_ingest is not None:
            return Ingest(
                state="done",
                files_done=snap.files_done,
                files_total=snap.files_total,
                bytes_done=snap.bytes_done,
                bytes_total=snap.bytes_total,
                error=None,
                retrying=False,
                retry_at=None,
            )
        error = (
            None
            if snap.error is None
            else IngestError(code=snap.error.code, file=snap.error.file)
        )
        return Ingest(
            state=snap.state,
            files_done=snap.files_done,
            files_total=snap.files_total,
            bytes_done=snap.bytes_done,
            bytes_total=snap.bytes_total,
            error=error,
            retrying=snap.retrying,
            retry_at=snap.retry_at,
        )

    def app_info(self, instance: str, project: str | None) -> AppInfo:
        """Return the app-wide facts.

        Args:
            instance: The server instance id.
            project: The project key in the route. ``to_fix_count`` stays None until M4.

        Returns:
            The answer for ``GET /api/app``.
        """
        with self._reader() as conn:
            status = history.read_history(conn)
            running = self._running_sessions(conn, self._mapped_projects(conn))
        as_of = status.as_of
        stamp = "" if as_of is None else history.utc_text(as_of)
        etag = f"{self._writer.generation}-{stamp}"
        return AppInfo(
            server_time=self.now(),
            instance=instance,
            claude_version=self._version,
            as_of=as_of,
            pass_running_since=status.pass_running_since,
            etag=etag,
            ingest=self._ingest(status),
            history=self._history(status),
            running=running,
            to_fix_count=None,
            editable_projects=[],
        )


def _prices_payload(answer: price_feed.PricesAnswer) -> dict[str, object]:
    """Turn a prices answer into the plain dict ``PricesInfo`` validates."""
    return {
        "source": answer.source,
        "as_of": answer.as_of,
        "etag": answer.etag,
        "cross_check": {
            "state": answer.cross_check.state,
            "models": list(answer.cross_check.models),
        },
        "models": [
            {
                "model": row.model,
                "source": row.source,
                "input": row.input,
                "output": row.output,
                "cache_read": row.cache_read,
                "cache_write_5m": row.cache_write_5m,
                "cache_write_1h": row.cache_write_1h,
                "tiers": [
                    {
                        "prompt_tokens_over": tier.prompt_tokens_over,
                        "input": tier.input,
                        "output": tier.output,
                        "cache_read": tier.cache_read,
                        "cache_write_5m": tier.cache_write_5m,
                        "cache_write_1h": tier.cache_write_1h,
                    }
                    for tier in row.tiers
                ],
                "modifiers": _flat_modifiers(row.modifiers),
                "relative": row.relative,
            }
            for row in answer.models
        ],
    }


def _flat_modifiers(modifiers: dict[str, dict[str, float]]) -> dict[str, float]:
    """Flatten ``{"speed": {"fast": 2.0}}`` to ``{"fast": 2.0}`` for the API model."""
    return {
        name: value for values in modifiers.values() for name, value in values.items()
    }


def create(  # noqa: PLR0913 - one server's settings, keyword-only
    *,
    claude_dir: Path,
    store_dir: Path,
    demo: bool,
    pace_ms: int,
    price_fetch: bool,
    transport: price_transport.Transport | None = None,
    clock: Callable[[], float] = time.time,
    log_path: str | None = None,
    project_dir: Path | None = None,
) -> StoreProvider:
    """Build the provider with its writer and price feed. Nothing starts yet.

    Args:
        claude_dir: The Claude config folder.
        store_dir: The store root.
        demo: True for the demo build, which supplies ``claude_version``.
        pace_ms: Sleep after each file. Demo only.
        price_fetch: False turns the live price fetch off.
        transport: The price network, injectable. Defaults to the urllib one.
        clock: Epoch seconds.
        log_path: The log file named in an ``unexpected`` failure.
        project_dir: The launch project's folder, or None.

    Returns:
        A provider that ``start`` brings up.
    """
    layout = StoreLayout(store_dir)
    settings = price_feed.PriceSettings(layout=layout)
    policy = tier_policy(settings, clock())
    writer = store_writer.StoreWriter(
        layout,
        claude_dir,
        clock=lambda: datetime.fromtimestamp(clock(), tz=UTC),
        tier_policy=policy,
        pace_ms=pace_ms,
        log_path=log_path,
    )
    feed = price_feed.PriceFeed(
        transport=transport or price_transport.UrllibTransport(),
        submit=writer.submit,
        settings=settings,
        open_reader=lambda: open_read(layout),
        clock=clock,
        enabled=price_fetch,
    )
    return StoreProvider(
        layout=layout,
        claude_dir=claude_dir,
        writer=writer,
        price_settings=settings,
        feed=feed,
        clock=clock,
        claude_version=demo_claude_version(claude_dir) if demo else "",
        project_dir=project_dir,
        hold_seconds=PACED_HOLD_SECONDS if pace_ms > 0 else 0.0,
    )
