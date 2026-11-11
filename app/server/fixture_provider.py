"""Fixture data standing in for the store provider, behind the ``Provider`` protocol.

Each scenario is one JSON file in ``app/fixtures/m0/``. The ingest steps through the
file's ``ingest_steps`` on an injectable clock. The clock starts at the first
``GET /api/app`` the provider answers, so a page that opens late still sees the
waiting state first. Times that read "ago" or "_s" in the file count from that start, so
they hold still while the clock runs. Price tables are JSON files in ``prices/``.
"""

import importlib.util
import json
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

from pydantic import BaseModel, ConfigDict

import problems
import projects as projects_mod
import rules_reference
import setup_answers
import store_provider
import timeline
from models import (
    AgentList,
    AppInfo,
    BackupFailure,
    BackupReasonCode,
    ClockInfo,
    CostChart,
    EditsState,
    HistoryInfo,
    Ingest,
    IngestError,
    IngestErrorCode,
    IngestState,
    LiveSessions,
    LiveSessionsUnchanged,
    ModelList,
    PassError,
    PricesInfo,
    ProblemList,
    Project,
    ProjectList,
    ProjectState,
    ReviewRange,
    RunningItem,
    SessionList,
    SetupMap,
    SetupPart,
    SetupPartAnswer,
    Summary,
    Timeline,
    ToFix,
    Unchanged,
)
from provider import UnknownProjectError
from setup_contract import SetupContext

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
SETUP_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "setup"


class _ProjectRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    name: str
    display_path: str
    state: ProjectState
    listed: bool = True


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


@dataclass(frozen=True)
class SetupWorld:
    """The folders a fixture provider reads setup from, one context per project key.

    ``contexts`` maps a project key to the ``SetupContext`` its collectors read. A
    project whose context has no ``project_dir`` is not on Bar Tab's list.
    """

    contexts: Mapping[str, SetupContext]


def _corpus_builder() -> ModuleType:
    """Load ``app/fixtures/setup/build_corpus.py`` once (it imports its siblings)."""
    found = sys.modules.get("build_corpus")
    if found is not None:
        return found
    sys.path.insert(0, str(SETUP_FIXTURES_DIR))
    spec = importlib.util.spec_from_file_location(
        "build_corpus", SETUP_FIXTURES_DIR / "build_corpus.py"
    )
    if spec is None or spec.loader is None:
        msg = "the setup corpus builder is missing"
        raise FileNotFoundError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_corpus"] = module
    spec.loader.exec_module(module)
    return module


def corpus_world(
    case: str, dest: Path, *, key: str = "proj", corpus: Path | None = None
) -> SetupWorld:
    """Materialize a setup corpus case and return the world its project reads.

    Args:
        case: A case folder name under ``app/fixtures/setup/corpus``.
        dest: A folder that does not exist yet, outside every repo.
        key: The project key the world serves the case under.
        corpus: The corpus folder to copy from, default the committed one.

    Returns:
        A world with one project. An unlisted case has a context with no project.
    """
    builder: Any = _corpus_builder()
    root: Path = builder.materialize(case, dest, corpus=corpus)
    lay = builder.layout(root)
    meta: dict[str, Any] = json.loads((root / "case.json").read_text("utf-8"))
    session: dict[str, Any] = json.loads(lay.session.read_text("utf-8"))
    env: dict[str, str] = dict(session.get("shell_env") or {})
    ctx = SetupContext(
        project_key=key,
        config_dir=lay.config,
        home=lay.home,
        project_dir=lay.project if meta["listed"] else None,
        managed_dir=lay.managed,
        shell_env=env,
        plan=meta["plan"],
    )
    return SetupWorld({key: ctx})


def apply_demo_setup_overlay(demo_dir: Path) -> None:
    """Apply the setup overlay to a built demo folder, in place.

    ``serve.py --demo`` calls it once per demo build, behind a marker file, so the demo
    shows setup content and its three extra projects. The overlay builder is idempotent,
    but the marker keeps a second start from touching the folder.

    Args:
        demo_dir: A built demo folder (``config/``, ``projects/``, ``managed/``).
    """
    builder: Any = _corpus_builder()
    builder.apply_demo_overlay(demo_dir)


def demo_world(demo_dir: Path) -> SetupWorld:
    """Apply the setup overlay to a demo build and return a world with its projects.

    The overlay (``app/fixtures/setup/demo_overlay.py``) adds skills, instruction
    files, hooks, MCP servers, plugins and three extra listed projects to the folder.
    The folder is changed in place, so pass a copy. Every project the demo lists is a
    project of the world, under the key the app gives it.

    Args:
        demo_dir: A built demo folder (``config/``, ``projects/``, ``managed/``).

    Returns:
        The world.
    """
    builder: Any = _corpus_builder()
    builder.apply_demo_overlay(demo_dir)
    root = demo_dir.resolve()
    config = root / "config"
    listing = projects_mod.load(
        projects_mod.ProjectsContext(config_dir=str(config), project_dir=str(root))
    )
    env = store_provider.shell_env_of(config)
    contexts: dict[str, SetupContext] = {}
    for project in listing.projects:
        key = project.key or projects_mod.slug(project.name)
        contexts[key] = SetupContext(
            project_key=key,
            config_dir=config,
            home=None,
            project_dir=Path(project.path),
            managed_dir=root / "managed",
            shell_env=env,
            plan=listing.plan,
        )
    return SetupWorld(contexts)


class FixtureProvider:
    """Serve the answers of one fixture scenario."""

    def __init__(
        self,
        scenario: str = "demo",
        clock: Callable[[], float] = time.time,
        fixtures_dir: Path | None = None,
        setup: SetupWorld | None = None,
    ) -> None:
        """Load a scenario.

        Args:
            scenario: One of ``SCENARIOS``.
            clock: Seconds source, injectable so tests step the ingest.
            fixtures_dir: Folder of scenario files. Defaults to ``app/fixtures/m0``.
            setup: The folders the Setup routes read (``corpus_world`` or
                ``demo_world``). None answers ``unknown_project`` on those routes, as
                the other data routes do.

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
        self._world = setup
        self._setup = setup_answers.SetupService(started_at=self.now())

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
                Project(
                    **row.model_dump(),
                    running=row.key in running,
                    edit_block=(
                        "folder_not_found" if row.state == "folder_not_found" else None
                    ),
                )
                for row in self._data.projects
            ]
        )

    def claude_version(self) -> str:
        """Return the scenario's Claude Code version."""
        return self._data.claude_version

    def app_info(self, instance: str, project: str | None) -> AppInfo:
        """Return the app-wide facts.

        Args:
            instance: The server instance id.
            project: The project key in the route, or None.

        Returns:
            The answer for ``GET /api/app``. ``to_fix_count`` is None when the project
            is missing or not in the fixture.
        """
        counted = None if project is None else self._data.to_fix_counts.get(project)
        to_fix = ToFix(
            state="unchecked" if counted is None else "ok", count=counted, etag=None
        )
        if project is not None and self._world and project in self._world.contexts:
            to_fix = self._setup.to_fix(self._request(project))
        return AppInfo(
            server_time=self.now(),
            instance=instance,
            claude_version=self._data.claude_version,
            rules_version_gap=rules_reference.version_gap(self._data.claude_version),
            as_of=self._before(self._data.as_of_ago),
            pass_running_since=self._before(self._data.pass_running_since_ago),
            etag=self._data.etag,
            ingest=self.ingest(),
            history=self.history(),
            running=list(self._data.running),
            to_fix_count=to_fix.count,
            to_fix=to_fix,
            editable_projects=list(self._data.editable_projects),
            edits=EditsState(state="off", instance=instance),
            mode="fixture",
            clock=ClockInfo(kind="real", rate_n=None),
        )

    def timeline(
        self, project: str, session_id: str, etag: str | None
    ) -> Timeline | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no sessions.

        Raises:
            UnknownProjectError: Always. The fixture has no Live scenarios.
        """
        del project, session_id, etag
        raise UnknownProjectError

    def live_sessions(
        self, project: str, etag: str | None
    ) -> LiveSessions | LiveSessionsUnchanged:
        """Return an empty session list for a fixture project.

        Raises:
            UnknownProjectError: When ``project`` is not in the scenario.
        """
        if project not in {row.key for row in self._data.projects}:
            raise UnknownProjectError
        now = self.now()
        body: dict[str, object] = {
            "as_of": None,
            "unchanged": False,
            "sessions": [],
            "latest_ended": None,
        }
        tag = timeline.digest(body)
        if etag == tag:
            return LiveSessionsUnchanged(server_time=now, etag=tag, unchanged=True)
        return LiveSessions(
            server_time=now,
            as_of=None,
            etag=tag,
            unchanged=False,
            sessions=[],
            latest_ended=None,
        )

    def summary(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> Summary | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no usage.

        Raises:
            UnknownProjectError: Always. The fixture has no Review data.
        """
        del project, review_range, etag
        raise UnknownProjectError

    def cost_chart(
        self,
        project: str,
        review_range: ReviewRange,
        end: date | None,
        etag: str | None,
    ) -> CostChart | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no usage.

        Raises:
            UnknownProjectError: Always. The fixture has no Review data.
        """
        del project, review_range, end, etag
        raise UnknownProjectError

    def sessions(
        self,
        project: str,
        review_range: ReviewRange,
        cursor: str | None,
        etag: str | None,
    ) -> SessionList | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no usage.

        Raises:
            UnknownProjectError: Always. The fixture has no Review data.
        """
        del project, review_range, cursor, etag
        raise UnknownProjectError

    def agents(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> AgentList | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no usage.

        Raises:
            UnknownProjectError: Always. The fixture has no Review data.
        """
        del project, review_range, etag
        raise UnknownProjectError

    def models(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> ModelList | Unchanged:
        """Answer ``unknown_project``, because the fixture scenarios have no usage.

        Raises:
            UnknownProjectError: Always. The fixture has no Review data.
        """
        del project, review_range, etag
        raise UnknownProjectError

    def _request(self, project: str) -> setup_answers.SetupRequest:
        """Build the setup request for a project of the world.

        Raises:
            UnknownProjectError: When the provider has no setup world, or the world
                has no such project.
        """
        if self._world is None or project not in self._world.contexts:
            raise UnknownProjectError
        ctx = self._world.contexts[project]
        return setup_answers.SetupRequest(
            project=project,
            ctx=ctx,
            listed=ctx.project_dir is not None,
            version="",
            as_of=None,
            claude_version=self._data.claude_version,
            usage=lambda: None,
            transcripts=problems.Transcripts,
        )

    def setup_map(self, project: str, etag: str | None) -> SetupMap | Unchanged:
        """Return the setup map of a project of the setup world.

        Raises:
            UnknownProjectError: When the world has no such project.
        """
        return self._setup.setup_map(self._request(project), etag, self.now())

    def setup_part(
        self, project: str, part: SetupPart, etag: str | None
    ) -> SetupPartAnswer | Unchanged:
        """Return one part of a project of the setup world.

        Raises:
            UnknownProjectError: When the world has no such project.
        """
        return self._setup.setup_part(self._request(project), part, etag, self.now())

    def problems(self, project: str, etag: str | None) -> ProblemList | Unchanged:
        """Return the To fix feed of a project of the setup world.

        Raises:
            UnknownProjectError: When the world has no such project.
        """
        return self._setup.problems(self._request(project), etag, self.now())

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
