"""Fixture data for the M0 reads, standing in for the real ingest until M1.

Each scenario is one JSON file in ``app/fixtures/m0/``. The ingest steps through the
file's ``ingest_steps`` on an injectable clock. The clock starts at the first
``GET /api/app`` the provider answers, so a page that opens late still sees the
waiting state first.
"""

import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from models import (
    AppInfo,
    Ingest,
    IngestError,
    IngestState,
    Project,
    ProjectList,
    ProjectState,
    RunningItem,
)

SCENARIOS = ("demo", "empty", "firstrun", "firstrun_failed")
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
    files_total: int
    bytes_done: int
    bytes_total: int
    error: IngestError | None
    retrying: bool


class _Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claude_version: str
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
        self._started: float | None = None

    def now(self) -> datetime:
        """Return the provider's clock as an aware UTC time."""
        return datetime.fromtimestamp(self._clock(), tz=UTC)

    def ingest(self) -> Ingest:
        """Return the ingest step for the time since the first call."""
        now = self._clock()
        if self._started is None:
            self._started = now
        elapsed = now - self._started
        current = self._steps[0]
        for step in self._steps:
            if step.at <= elapsed:
                current = step
        return Ingest(
            **current.model_dump(exclude={"at"}, exclude_none=False),
        )

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
            ingest=self.ingest(),
            running=list(self._data.running),
            to_fix_count=to_fix,
            editable_projects=list(self._data.editable_projects),
        )

    def resolve_project(self, project_dir: Path | None) -> str | None:
        """Return the project key that matches a folder, or None.

        The key is the folder name as a slug, kept only when a fixture project has it.
        """
        if project_dir is None:
            return None
        slug = re.sub(r"[^a-z0-9]+", "-", project_dir.name.lower()).strip("-")
        keys = {row.key for row in self._data.projects}
        return slug if slug in keys else None
