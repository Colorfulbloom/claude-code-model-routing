"""The contract between the routes and whatever answers them.

``api_app`` asks a provider for every answer. The fixture provider and the real
store provider that replaces it both satisfy this protocol. The models in
``models.py`` are the shape of what they return.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from models import (
    AgentList,
    AppInfo,
    CostChart,
    LiveSessions,
    LiveSessionsUnchanged,
    ModelList,
    PricesInfo,
    ProblemList,
    ProjectList,
    ReviewRange,
    SessionList,
    SetupMap,
    SetupPart,
    SetupPartAnswer,
    Summary,
    Timeline,
    Unchanged,
)


class UnknownProjectError(Exception):
    """The project key names no project the provider knows."""


class UnknownSessionError(Exception):
    """The session id names no session with a request in the project."""


class Provider(Protocol):
    """What ``api_app`` needs from a data source."""

    def now(self) -> datetime:
        """Return the provider's clock as an aware UTC time."""
        ...

    def app_info(self, instance: str, project: str | None) -> AppInfo:
        """Return the answer for ``GET /api/app``."""
        ...

    def projects(self) -> ProjectList:
        """Return the answer for ``GET /api/projects``."""
        ...

    def resolve_project(
        self, project_dir: Path | None, *, first_if_none: bool = False
    ) -> str | None:
        """Return the project key that matches a folder, or None.

        With ``first_if_none`` a folder that matches nothing gets the first project.
        """
        ...

    def prices(self) -> PricesInfo:
        """Return the answer for ``GET /api/prices``."""
        ...

    def timeline(
        self, project: str, session_id: str, etag: str | None
    ) -> Timeline | Unchanged:
        """Return one session's timeline, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
            UnknownSessionError: When the session is not in that project.
        """
        ...

    def live_sessions(
        self, project: str, etag: str | None
    ) -> LiveSessions | LiveSessionsUnchanged:
        """Return the running sessions, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def summary(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> Summary | Unchanged:
        """Return Review's Summary, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def cost_chart(
        self,
        project: str,
        review_range: ReviewRange,
        end: date | None,
        etag: str | None,
    ) -> CostChart | Unchanged:
        """Return the cost chart page that holds the local date ``end``.

        ``end`` None means the newest page. The short answer comes back when ``etag``
        matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def sessions(
        self,
        project: str,
        review_range: ReviewRange,
        cursor: str | None,
        etag: str | None,
    ) -> SessionList | Unchanged:
        """Return one page of the range's sessions, after ``cursor`` when it is set.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
            ValueError: When ``cursor`` is not a cursor this provider made.
        """
        ...

    def agents(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> AgentList | Unchanged:
        """Return the agents that ran in the range and the agent files that did not.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def models(
        self, project: str, review_range: ReviewRange, etag: str | None
    ) -> ModelList | Unchanged:
        """Return the range's models with their kinds of cost.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def setup_map(self, project: str, etag: str | None) -> SetupMap | Unchanged:
        """Return Your setup's map, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def setup_part(
        self, project: str, part: SetupPart, etag: str | None
    ) -> SetupPartAnswer | Unchanged:
        """Return one part's items, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...

    def problems(self, project: str, etag: str | None) -> ProblemList | Unchanged:
        """Return the To fix feed, or the short answer when ``etag`` matches.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        ...
