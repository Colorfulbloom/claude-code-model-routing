"""Pydantic models for every request and response body of the Bar Tab API.

Request models forbid extra fields. Every route names one of the response models here
as its ``response_model``, so a field that is not declared never leaves the server.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROJECT_KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"

IngestState = Literal["waiting", "running", "done", "failed"]
IngestErrorCode = Literal[
    "config_dir_missing",
    "config_dir_unreadable",
    "store_unwritable",
    "store_damaged",
    "unexpected",
]
ProjectState = Literal["ok", "no_claude_folder", "folder_not_found"]


class _Response(BaseModel):
    """Base for response bodies."""

    model_config = ConfigDict(extra="forbid")


class _Request(BaseModel):
    """Base for request bodies. Unknown fields are refused."""

    model_config = ConfigDict(extra="forbid", strict=True)


class ErrorEnvelope(_Response):
    """The one error body. It never carries input or file paths."""

    code: str
    path: list[str | int] | None


class IngestError(_Response):
    """Why a first-run ingest failed. ``file`` is None when the contract names none."""

    code: IngestErrorCode
    file: str | None


class Ingest(_Response):
    """Progress of the first read of the usage history."""

    state: IngestState
    files_done: int
    files_total: int
    bytes_done: int
    bytes_total: int
    error: IngestError | None
    retrying: bool


class RunningItem(_Response):
    """One session that is running now."""

    project: str
    session: str


class AppInfo(_Response):
    """Answer of ``GET /api/app``."""

    server_time: datetime
    instance: str
    claude_version: str
    ingest: Ingest
    running: list[RunningItem]
    to_fix_count: int | None
    editable_projects: list[str]


class Project(_Response):
    """One project in the picker."""

    key: str
    name: str
    display_path: str
    state: ProjectState
    running: bool


class ProjectList(_Response):
    """Answer of ``GET /api/projects``."""

    projects: list[Project]


class SwapRequest(_Request):
    """Body of ``POST /api/access/swap``."""

    code: str = Field(min_length=1, max_length=200)


class SwapResponse(_Response):
    """Keys handed out after a code swap."""

    read_key: str
    edit_keys: dict[str, str]
    instance: str
    project: str | None


class MintRequest(_Request):
    """Body of ``POST /api/access/mint``."""

    project: str | None = Field(default=None, pattern=PROJECT_KEY_PATTERN)


class MintResponse(_Response):
    """A fresh single-use code."""

    code: str
