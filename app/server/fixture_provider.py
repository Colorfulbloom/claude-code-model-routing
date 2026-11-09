"""Fixture data standing in for the store provider, behind the ``Provider`` protocol.

Each scenario is one JSON file in ``app/fixtures/m0/``. The ingest steps through the
file's ``ingest_steps`` on an injectable clock. The clock starts at the first
``GET /api/app`` the provider answers, so a page that opens late still sees the
waiting state first. Times that read "ago" or "_s" in the file count from that start, so
they hold still while the clock runs. Price tables are JSON files in ``prices/``.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from models import (
    AppInfo,
    BackupFailure,
    BackupReasonCode,
    HistoryInfo,
    Ingest,
    IngestError,
    IngestErrorCode,
    IngestState,
    PassError,
    PricesInfo,
    Project,
    ProjectList,
    ProjectState,
    RunningItem,
)

SCENARIOS = (
    "demo",
    "empty",
    "firstrun",
    "firstrun_failed",
    "firstrun_counting",
    "firstrun_retry",
    "store_newer",
    "stopped",
    "history_problem",
    "prices_bundled",
)
DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "m0"


class _ProjectRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    display_path: str
    state: ProjectState


class _Step(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: float
    state: IngestState
    files_done: int
    files_total: int | None
    bytes_done: int
    bytes_total: int | None
    error: IngestError | None
    retrying: bool
    retry_at_s: float | None = None


class _BackupFailed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at_ago: float
    reason_code: BackupReasonCode


class _PassError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: IngestErrorCode
    file: str | None
    since_ago: float


class _History(BaseModel):
    model_config = ConfigDict(extra="forbid")

    oldest: datetime | None
    first_ingest: datetime | None
    last_backup_ago: float | None
    backup_failed: _BackupFailed | None
    pass_error: _PassError | None
    unreadable_files: int
    kept_files: int
    no_usage_rows: int


class _Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claude_version: str
    as_of_ago: float | None
    pass_running_since_ago: float | None
    etag: str
    prices: str
    history: _History
    projects: list[_ProjectRow]
    running: list[RunningItem]
    to_fix_counts: dict[str, int]
    editable_projects: list[str]
    ingest_steps: list[_Step]


class FixtureProvider:
    """Serve the answers of one fixture scenario."""

    def __init__(
        self,
        scenario: str = "demo",
        clock: Callable[[], float] = time.time,
        fixtures_dir: Path | None = None,
    ) -> None:
        """Load a scenario.

        Args:
            scenario: One of ``SCENARIOS``.
            clock: Seconds source, injectable so tests step the ingest.
            fixtures_dir: Folder of scenario files. Defaults to ``app/fixtures/m0``.

        Raises:
            ValueError: When the scenario name is unknown.
        """
        if scenario not in SCENARIOS:
            msg = "unknown fixture scenario"
            raise ValueError(msg)
        folder = fixtures_dir or DEFAULT_FIXTURES_DIR
        text = (folder / f"{scenario}.json").read_text(encoding="utf-8")
        self._data = _Scenario.model_validate_json(text)
        self._steps = sorted(self._data.ingest_steps, key=lambda step: step.at)
        self.scenario = scenario
        self._clock = clock
        self._folder = folder
        self._started: float | None = None

    def now(self) -> datetime:
        """Return the provider's clock as an aware UTC time."""
        return datetime.fromtimestamp(self._clock(), tz=UTC)

    def _anchor(self) -> float:
        """Return the clock reading at the first call, which starts the scenario."""
        if self._started is None:
            self._started = self._clock()
        return self._started

    def _before(self, seconds: float | None) -> datetime | None:
        """Return the time ``seconds`` before the scenario start, or None."""
        if seconds is None:
            return None
        return datetime.fromtimestamp(self._anchor() - seconds, tz=UTC)

    def ingest(self) -> Ingest:
        """Return the ingest step for the time since the first call."""
        start = self._anchor()
        elapsed = self._clock() - start
        current = self._steps[0]
        for step in self._steps:
            if step.at <= elapsed:
                current = step
        retry_at = (
            None
            if current.retry_at_s is None
            else datetime.fromtimestamp(start + current.retry_at_s, tz=UTC)
        )
        return Ingest(
            **current.model_dump(exclude={"at", "retry_at_s"}),
            retry_at=retry_at,
        )

    def history(self) -> HistoryInfo:
        """Return the history facts of the scenario."""
        h = self._data.history
        failed = (
            None
            if h.backup_failed is None
            else BackupFailure(
                at=self._before(h.backup_failed.at_ago) or self.now(),
                reason_code=h.backup_failed.reason_code,
            )
        )
        pass_error = (
            None
            if h.pass_error is None
            else PassError(
                code=h.pass_error.code,
                file=h.pass_error.file,
                since=self._before(h.pass_error.since_ago) or self.now(),
            )
        )
        return HistoryInfo(
            oldest=h.oldest,
            first_ingest=h.first_ingest,
            last_backup=self._before(h.last_backup_ago),
            backup_failed=failed,
            pass_error=pass_error,
            unreadable_files=h.unreadable_files,
            kept_files=h.kept_files,
            no_usage_rows=h.no_usage_rows,
        )

    def prices(self) -> PricesInfo:
        """Return the price table the scenario names, from ``prices/<name>.json``."""
        text = (self._folder / "prices" / f"{self._data.prices}.json").read_text(
            encoding="utf-8"
        )
        return PricesInfo.model_validate_json(text)

    def projects(self) -> ProjectList:
        """Return the project list with each project's running flag."""
        running = {item.project for item in self._data.running}
        return ProjectList(
            projects=[
                Project(**row.model_dump(), running=row.key in running)
                for row in self._data.projects
            ]
        )

    def app_info(self, instance: str, project: str | None) -> AppInfo:
        """Return the app-wide facts.

        Args:
            instance: The server instance id.
            project: The project key in the route, or None.

        Returns:
            The answer for ``GET /api/app``. ``to_fix_count`` is None when the project
            is missing or not in the fixture.
        """
        to_fix = None if project is None else self._data.to_fix_counts.get(project)
        return AppInfo(
            server_time=self.now(),
            instance=instance,
            claude_version=self._data.claude_version,
            as_of=self._before(self._data.as_of_ago),
            pass_running_since=self._before(self._data.pass_running_since_ago),
            etag=self._data.etag,
            ingest=self.ingest(),
            history=self.history(),
            running=list(self._data.running),
            to_fix_count=to_fix,
            editable_projects=list(self._data.editable_projects),
        )

    def resolve_project(
        self, project_dir: Path | None, *, first_if_none: bool = False
    ) -> str | None:
        """Return the project key that matches a folder, or None.

        The key is the folder name as a slug, kept only when a fixture project has it.
        """
        if project_dir is None:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", project_dir.name.lower()).strip("-")
        keys = {row.key for row in self._data.projects}
        if slug in keys:
            return slug
        if first_if_none and self._data.projects:
            return self._data.projects[0].key
        return None
