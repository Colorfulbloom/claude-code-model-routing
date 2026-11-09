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
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast, get_args

import history
import ingest
import live_sessions
import model_catalog
import model_check
import price_feed
import price_transport
import project_map
import projects
import store
import store_writer
import timeline
import usage_query
from data_clock import DataClock
from models import (
    AppInfo,
    AppMode,
    BackupFailure,
    BackupReasonCode,
    HistoryInfo,
    Ingest,
    IngestError,
    IngestErrorCode,
    LiveSessions,
    LiveSessionsUnchanged,
    ModelCheck,
    PassError,
    PricesInfo,
    Project,
    ProjectList,
    RunningItem,
    Timeline,
    TimelinePrices,
    TimelineRun,
    Unchanged,
)
from provider import UnknownProjectError, UnknownSessionError
from store_paths import StoreLayout

logger = logging.getLogger(__name__)

RUNNING_WINDOW = timedelta(minutes=30)
# A paced demo ingest starts this long after the server, so the page can show its
# "Counting files" step before the first totals arrive. Off when there is no pace.
PACED_HOLD_SECONDS = 2.0
MAPPING_TTL_SECONDS = 5.0
# The model check's resolver entries are read from the project's settings files, so
# they are kept per project for this long.
ENTRIES_TTL_SECONDS = 10.0
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


def shell_env_of(claude_dir: Path) -> dict[str, str]:
    """Read ``shell_env`` from the demo or flow build's ``session.json``.

    The file sits beside the build's config folder. A missing or odd file gives an
    empty mapping, and so does any entry that is not a string pair.
    """
    try:
        data = cast(
            "object",
            json.loads(
                (claude_dir.parent / DEMO_SESSION_FILE).read_text(encoding="utf-8")
            ),
        )
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    env = cast("dict[str, object]", data).get("shell_env")
    if not isinstance(env, dict):
        return {}
    return {
        k: v
        for k, v in cast("dict[object, object]", env).items()
        if isinstance(k, str) and isinstance(v, str)
    }


def _newest_claude_version(conn: sqlite3.Connection) -> str:
    """Return ``claude_version`` of the newest session that has one, else "".

    The ingest records the newest top-level ``version`` of a session's transcript rows
    on ``sessions.claude_version``.
    """
    row = conn.execute(
        "SELECT claude_version FROM sessions"
        " WHERE claude_version IS NOT NULL AND claude_version <> ''"
        " ORDER BY last_ts DESC LIMIT 1"
    ).fetchone()
    return "" if row is None else str(row[0])


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


# Where Claude Code keeps file-based managed settings. Ported from
# ``dashboard/server.py`` MANAGED_DIRS (lines 105 to 109) and ``managed_dir_for``
# (lines 233 to 238): macOS, Linux and WSL, Windows, matched by platform prefix.
MANAGED_DIRS = {
    "darwin": "/Library/Application Support/ClaudeCode",
    "linux": "/etc/claude-code",
    "win32": r"C:\Program Files\ClaudeCode",
}


def managed_dir_for(platform: str) -> Path | None:
    """Return the managed settings folder for a platform, or None when unknown."""
    for prefix, folder in MANAGED_DIRS.items():
        if platform.startswith(prefix):
            return Path(folder)
    return None


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
        data_clock: DataClock | None = None,
        mode: AppMode = "real",
        managed_dir: Path | None = None,
        shell_env: dict[str, str] | None = None,
        home: str | None = None,
    ) -> None:
        """Wire the provider. Nothing starts until ``start``.

        Args:
            layout: The store folders.
            claude_dir: The Claude config folder (the demo's config folder in M1).
            writer: The store writer this provider reports on and owns.
            price_settings: Where the price sources are.
            feed: The price feed to start and stop, or None.
            clock: Epoch seconds, the wall clock. Prices and the project mapping cache
                read it.
            claude_version: What ``/api/app`` reports as ``claude_version``.
            project_dir: The launch project's folder, the fallback when no project
                list exists. Defaults to the Claude folder.
            hold_seconds: Wait this long after ``start`` before the writer starts.
            data_clock: The clock data answers read (``now``, running sessions and
                ``as_of``). Defaults to a real clock that follows ``clock``.
            mode: What ``/api/app`` reports as ``mode``.
            managed_dir: The managed settings folder the model check reads, or None.
            shell_env: The shell environment the model check reads. Empty by default.
            home: The home folder that "~" expands to in the project list and that
                project paths shorten against, or None for no expansion.
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
        self._data_clock = (
            data_clock if data_clock is not None else DataClock.real(wall=clock)
        )
        self._mode: AppMode = mode
        self._hold_timer: threading.Timer | None = None
        self._feed_lock = threading.Lock()
        self._stopped = False
        self._mapped: tuple[float, list[project_map.MappedProject]] | None = None
        self._price_cache: tuple[tuple[object, ...], PricesInfo] | None = None
        self._managed_dir = managed_dir
        self._home = home
        self._shell_env = dict(shell_env or {})
        self._pricer: tuple[str, usage_query.Pricer] | None = None
        self._catalog = model_catalog.load_catalog()
        self._entries: dict[str, tuple[float, list[model_check.Row]]] = {}
        self._cache_lock = threading.Lock()

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
        """Return the data clock's time as an aware UTC time."""
        return self._data_clock.now()

    @contextmanager
    def _reader(self) -> Generator[sqlite3.Connection]:
        """Yield a short read connection inside one read transaction, closed on exit.

        The connection is in autocommit mode, so without ``BEGIN`` every statement
        sees its own snapshot, and a commit between two statements could tear one
        answer (``totals.requests`` one ahead of ``requests[]``). One deferred
        transaction gives every statement the same snapshot (m1-build.md section 2,
        "Readers").
        """
        conn = open_read(self._layout)
        try:
            conn.execute("BEGIN")
            yield conn
        finally:
            try:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
            finally:
                conn.close()

    def _mapped_projects(
        self, conn: sqlite3.Connection, *, refresh: bool = False
    ) -> list[project_map.MappedProject]:
        now = self._clock()
        cached = self._mapped
        if not refresh and cached is not None and now - cached[0] < MAPPING_TTL_SECONDS:
            return cached[1]
        ctx = projects.ProjectsContext(
            config_dir=str(self._claude_dir),
            project_dir=str(self._project_dir),
            home=self._home,
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
        key_of = self._folder_keys(mapped)
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
            return self._prices_on(conn)

    def _prices_on(self, conn: sqlite3.Connection) -> PricesInfo:
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

    # ------------------------------------------------------------ Live

    @staticmethod
    def _folder_keys(mapped: list[project_map.MappedProject]) -> dict[str, str]:
        """Return the project key of each store folder, as ``running[]`` maps them."""
        key_of: dict[str, str] = {}
        for item in mapped:
            for folder in item.folders:
                key_of.setdefault(folder, item.key)
        return key_of

    def _pricer_on(self, conn: sqlite3.Connection) -> usage_query.Pricer:
        """Return the pricer for the active price table, rebuilt when it changes."""
        table = price_feed.price_table(conn, self._prices, now=self._clock())
        with self._cache_lock:
            cached = self._pricer
            if cached is not None and cached[0] == table.hash:
                return cached[1]
            pricer = usage_query.Pricer(table.document)
            self._pricer = (table.hash, pricer)
            return pricer

    def _timeline_prices(self, conn: sqlite3.Connection) -> TimelinePrices:
        info = self._prices_on(conn)
        return TimelinePrices(
            as_of=info.as_of,
            source=info.source,
            cross_check_state=info.cross_check.state,
        )

    def _check_dir(self, project: project_map.MappedProject) -> Path | None:
        """Return the folder the model check reads ``.claude`` files under, or None.

        Only a listed project names a folder the owner chose. An unlisted project's
        cwd comes from a transcript, so it is never read: the check sees user scope
        and managed settings only (``resolve_entries`` with no project).
        """
        if not project.listed:
            return None
        return Path(project.path if project.path else str(self._project_dir))

    def _model_check_for(
        self, project: project_map.MappedProject
    ) -> timeline.ModelCheckFn:
        """Return the model check function for one project, entries cached 10 s."""

        def check(_key: str, runs: Sequence[TimelineRun]) -> ModelCheck:
            now = self._clock()
            with self._cache_lock:
                cached = self._entries.get(project.key)
            if cached is not None and now - cached[0] < ENTRIES_TTL_SECONDS:
                entries = cached[1]
            else:
                entries = model_check.resolve_entries(
                    claude_dir=self._claude_dir,
                    project_dir=self._check_dir(project),
                    managed_dir=self._managed_dir,
                    shell_env=self._shell_env,
                )
                with self._cache_lock:
                    self._entries[project.key] = (now, entries)
            return model_check.build_model_check(
                entries=entries, runs=runs, catalog=self._catalog
            )

        return check

    def _build_timeline(
        self,
        conn: sqlite3.Connection,
        mapped: list[project_map.MappedProject],
        project: str,
        session_id: str,
    ) -> Timeline | None:
        item = next((m for m in mapped if m.key == project), None)
        if item is None:
            raise UnknownProjectError
        return timeline.build_timeline(
            conn,
            session_id=session_id,
            project_key=project,
            folder_keys=self._folder_keys(mapped),
            now=self.now(),
            pricer=self._pricer_on(conn),
            catalog=self._catalog,
            model_check_fn=self._model_check_for(item),
            prices=lambda: self._timeline_prices(conn),
        )

    def timeline(
        self, project: str, session_id: str, etag: str | None
    ) -> Timeline | Unchanged:
        """Return one session's timeline, or the short answer when ``etag`` matches.

        The project mapping is cached for 5 s, so a session ingested a moment ago can
        look unknown. A miss refreshes the mapping once before it answers.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
            UnknownSessionError: When the session is not in that project.
        """
        with self._reader() as conn:
            try:
                answer = self._build_timeline(
                    conn, self._mapped_projects(conn), project, session_id
                )
            except UnknownProjectError:
                answer = None
            if answer is None:
                answer = self._build_timeline(
                    conn, self._mapped_projects(conn, refresh=True), project, session_id
                )
        if answer is None:
            raise UnknownSessionError
        if etag is not None and etag == answer.etag:
            return Unchanged(
                project=project,
                server_time=answer.server_time,
                etag=answer.etag,
                unchanged=True,
            )
        return answer

    def live_sessions(
        self, project: str, etag: str | None
    ) -> LiveSessions | LiveSessionsUnchanged:
        """Return the running sessions, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        with self._reader() as conn:
            mapped = self._mapped_projects(conn)
            if all(m.key != project for m in mapped):
                mapped = self._mapped_projects(conn, refresh=True)
                if all(m.key != project for m in mapped):
                    raise UnknownProjectError
            answer = live_sessions.build_live_sessions(
                conn,
                project_key=project,
                now=self.now(),
                project_names={m.key: m.name for m in mapped},
                folder_keys=self._folder_keys(mapped),
            )
        if etag is not None and etag == answer.etag:
            return LiveSessionsUnchanged(
                server_time=answer.server_time, etag=answer.etag, unchanged=True
            )
        return answer

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
            version = self._version or _newest_claude_version(conn)
        as_of = status.as_of
        if as_of is not None and self._data_clock.kind != "real":
            # A fixed, rate or test clock reads a fully ingested build, so the data
            # is as of the clock's T.
            as_of = self.now()
        stamp = "" if as_of is None else history.utc_text(as_of)
        etag = f"{self._writer.generation}-{stamp}"
        return AppInfo(
            server_time=self.now(),
            instance=instance,
            claude_version=version,
            as_of=as_of,
            pass_running_since=status.pass_running_since,
            etag=etag,
            ingest=self._ingest(status),
            history=self._history(status),
            running=running,
            to_fix_count=None,
            editable_projects=[],
            mode=self._mode,
            clock=self._data_clock.info(),
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
    data_clock: DataClock | None = None,
    mode: AppMode | None = None,
    managed_dir: Path | None = None,
    shell_env: Mapping[str, str] | None = None,
    health_path: Path | None = None,
    home: str | None = None,
) -> StoreProvider:
    """Build the provider with its writer and price feed. Nothing starts yet.

    Args:
        claude_dir: The Claude config folder.
        store_dir: The store root.
        demo: True for a demo or flow build, which supplies ``claude_version``.
        pace_ms: Sleep after each file. Demo only.
        price_fetch: False turns the live price fetch off.
        transport: The price network, injectable. Defaults to the urllib one.
        clock: Epoch seconds, the wall clock. The writer, the price feed and the
            project mapping cache keep it.
        log_path: The log file named in an ``unexpected`` failure.
        project_dir: The launch project's folder, or None.
        data_clock: The clock data answers read. Defaults to a real clock on ``clock``.
        mode: What ``/api/app`` reports. Defaults to ``demo`` with ``demo``, else
            ``real``.
        managed_dir: The managed settings folder the model check reads. A demo or
            flow build defaults to its own ``managed`` folder, anything else to None.
        shell_env: The shell environment the model check reads. A demo or flow build
            defaults to the ``shell_env`` of its ``session.json``, anything else to an
            empty mapping.
        health_path: The file the writer reports its pass times and lag in, or None.
        home: The home folder that "~" expands to, or None.

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
        health_path=health_path,
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
        data_clock=data_clock,
        mode=mode if mode is not None else ("demo" if demo else "real"),
        # A demo or flow build carries its own managed folder and shell environment.
        # Real mode names both itself.
        managed_dir=(
            managed_dir
            if managed_dir is not None
            else (claude_dir.parent / "managed" if demo else None)
        ),
        shell_env=(
            dict(shell_env)
            if shell_env is not None
            else (shell_env_of(claude_dir) if demo else {})
        ),
        home=home,
    )
