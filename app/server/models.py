"""Pydantic models for every request and response body of the Bar Tab API.

Request models forbid extra fields. Every route names one of the response models here
as its ``response_model``, so a field that is not declared never leaves the server.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PROJECT_KEY_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"

IngestState = Literal["waiting", "running", "done", "failed"]
IngestErrorCode = Literal[
    "config_dir_missing",
    "config_dir_unreadable",
    "store_unwritable",
    "store_damaged",
    "store_newer",
    "unexpected",
]
BackupReasonCode = Literal["no_space", "unwritable", "check_failed", "copy_failed"]
PriceSource = Literal["model_pricing", "litellm", "last_good", "bundled"]
CrossCheckState = Literal["agree", "disagree", "not_checked"]
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
    files_total: int | None
    bytes_done: int
    bytes_total: int | None
    error: IngestError | None
    retrying: bool
    retry_at: datetime | None


class RunningItem(_Response):
    """One session that is running now."""

    project: str
    session: str


class BackupFailure(_Response):
    """A daily backup that did not finish. A later good copy clears it."""

    at: datetime
    reason_code: BackupReasonCode


class PassError(_Response):
    """A whole-pass failure after the first ingest. The next good pass clears it."""

    code: IngestErrorCode
    file: str | None
    since: datetime


class HistoryInfo(_Response):
    """What the store holds and how well it is kept."""

    oldest: datetime | None
    first_ingest: datetime | None
    last_backup: datetime | None
    backup_failed: BackupFailure | None
    pass_error: PassError | None
    unreadable_files: int
    kept_files: int
    no_usage_rows: int


class AppInfo(_Response):
    """Answer of ``GET /api/app``."""

    server_time: datetime
    instance: str
    claude_version: str
    as_of: datetime | None
    pass_running_since: datetime | None
    etag: str
    ingest: Ingest
    history: HistoryInfo
    running: list[RunningItem]
    to_fix_count: int | None
    editable_projects: list[str]


class PriceTier(_Response):
    """Rates that apply once a prompt passes a size, in USD per million tokens."""

    prompt_tokens_over: int
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


class ModelPrice(_Response):
    """One model's rates in USD per million tokens."""

    model: str
    source: PriceSource
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    tiers: list[PriceTier]
    modifiers: dict[str, float]
    relative: float | None


class CrossCheck(_Response):
    """Result of comparing the active table with a second public list."""

    state: CrossCheckState
    models: list[str]


class PricesInfo(_Response):
    """Answer of ``GET /api/prices``."""

    source: PriceSource
    as_of: date
    etag: str
    cross_check: CrossCheck
    models: list[ModelPrice]


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
