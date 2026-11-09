"""The contract between the routes and whatever answers them.

``api_app`` asks a provider for every answer. The fixture provider and the real
store provider that replaces it both satisfy this protocol. The models in
``models.py`` are the shape of what they return.
"""

from datetime import datetime
from pathlib import Path
from typing import Protocol

from models import (
    AppInfo,
    LiveSessions,
    LiveSessionsUnchanged,
    PricesInfo,
    ProjectList,
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
