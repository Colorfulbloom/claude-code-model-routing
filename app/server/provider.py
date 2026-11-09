"""The contract between the routes and whatever answers them.

``api_app`` asks a provider for every answer. The fixture provider and the real
store provider that replaces it both satisfy this protocol. The models in
``models.py`` are the shape of what they return.
"""

from datetime import datetime
from pathlib import Path
from typing import Protocol

from models import AppInfo, PricesInfo, ProjectList


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
