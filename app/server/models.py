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


# The 422 description is fixed here because FastAPI otherwise reads it from
# ``http.HTTPStatus``, which Python 3.13 renamed from "Unprocessable Entity".
INVALID_REQUEST_RESPONSE: dict[str, object] = {
    "model": ErrorEnvelope,
    "description": "Unprocessable Content",
}


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
    mode: "AppMode"
    clock: "ClockInfo"


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


# ---------------------------------------------------------------------------
# M2 Live. The contract is m2-build.md sections 4 and 12. Times are aware UTC.

AppMode = Literal["demo", "fixture", "flow", "real"]
ClockKind = Literal["real", "fixed", "rate", "test"]
RunState = Literal["working", "idle", "finished"]
SessionState = Literal["working", "idle", "ended"]
ParentState = Literal["known", "waiting", "unknown"]
RoundByKind = Literal["coordinator", "peer", "human"]
ModelCheckStatus = Literal[
    "in_effect", "overridden", "ignored", "lowered", "invalid", "default", "unknown"
]


class ClockInfo(_Response):
    """Which clock the server answers with. ``rate_n`` is set only for ``rate``."""

    kind: ClockKind
    rate_n: float | None


class Unpriced(_Response):
    """Requests with no price, and the models they ran on, in catalog order."""

    requests: int
    models: list[str]


class Unchanged(_Response):
    """The short answer when the asked etag still matches."""

    project: str
    server_time: datetime
    etag: str
    unchanged: Literal[True]


class StateAt(_Response):
    """A state that starts at ``at`` and holds until the next entry."""

    at: datetime
    state: str


class TimelineSession(_Response):
    """The session a timeline describes."""

    id: str
    project: str
    branch: str | None
    started: datetime
    last_request: datetime
    running: bool
    active: bool
    state: SessionState
    states: list[StateAt]
    ended_at: datetime | None
    requests: int
    unpriced: Unpriced


class TimelineAxis(_Response):
    """The x axis over the whole session, and the y ticks for new tokens."""

    start: datetime
    end: datetime
    bucket_seconds: int
    ticks: list[datetime]
    token_ticks: list[int]


class TimelineBucket(_Response):
    """One bar. ``by_model`` holds new tokens and leaves out models with none."""

    start: datetime
    by_model: dict[str, int]
    cache_read: int
    cost: float | None
    requests: int
    unpriced: Unpriced


class ModelTokens(_Response):
    """A legend entry, new tokens over the axis."""

    model: str
    tokens: int


class Window(_Response):
    """Numbers over a stretch of time, such as the 60 s before T."""

    tokens: int
    cost: float | None
    cache_read: int
    hit_rate: float | None
    requests: int
    unpriced: Unpriced


class TimelineTotals(_Response):
    """Session totals at T."""

    tokens: int
    input: int
    output: int
    cache_read: int
    cache_write: int
    cost: float | None
    hit_rate: float | None
    requests: int
    runs: int
    runs_working: int
    runs_finished: int
    unpriced: Unpriced


class Together(_Response):
    """Siblings launched within 5 s of each other share a key."""

    key: str
    n: int


class Round(_Response):
    """One round of a run. ``by`` is ``main``, a run id, or None."""

    n: int
    at: datetime
    last_request: datetime
    by: str | None
    by_kind: RoundByKind | None


class Segment(_Response):
    """A drawn stretch of a lane, one per round."""

    start: datetime
    end: datetime


class Cum(_Response):
    """Cumulative values at the end of one bucket."""

    tokens: int
    cache_read: int
    cost: float | None


class TimelineRun(_Response):
    """One agent run, or the main session (``agent`` None, ``parent`` None)."""

    run_id: str
    agent: str | None
    label_n: int
    parent: str | None
    parent_known: bool
    parent_state: ParentState
    parent_at: datetime | None
    depth: int
    dispatch_order: int
    together: Together | None
    model: str | None
    effort: str | None
    first_request: datetime
    last_request: datetime
    state: RunState
    states: list[StateAt]
    rounds: list[Round]
    segments: list[Segment]
    tokens: int
    cost: float | None
    unpriced: Unpriced
    cum: list[Cum]


class LatestRequest(_Response):
    """One of the eight newest requests at or before T."""

    id: str
    at: datetime
    run_id: str
    model: str | None
    effort: str | None
    tokens: int
    new_tokens: int
    cache_read: int
    output: int
    cost: float | None


class SetValue(_Response):
    """What a file or setting sets, with its display path and line."""

    value: str
    file: str | None
    line: int | None
    scope: str | None


class SetPair(_Response):
    """The model and effort an agent's setup asks for."""

    model: SetValue | None
    effort: SetValue | None


class RanPair(_Response):
    """What the runs used, most common first. ``mixed`` when runs differ."""

    model: str | None
    effort: str | None
    mixed: bool


class ModelCheckRow(_Response):
    """The model check for one agent type in the session."""

    agent: str | None
    set: SetPair
    ran: RanPair
    status: ModelCheckStatus | None
    reason_code: str | None
    params: dict[str, str]
    runs: int
    mismatched_runs: int


class ModelCheck(_Response):
    """Every agent's model check, plus how many are in effect."""

    rows: list[ModelCheckRow]
    in_effect_count: int


class TimelinePrices(_Response):
    """The price facts a cost label needs."""

    as_of: date
    source: PriceSource
    cross_check_state: CrossCheckState


class Timeline(_Response):
    """Answer of ``GET /api/sessions/{id}/timeline``."""

    project: str
    server_time: datetime
    as_of: datetime | None
    etag: str
    unchanged: Literal[False]
    session: TimelineSession
    axis: TimelineAxis
    buckets: list[TimelineBucket]
    models: list[ModelTokens]
    last_minute: Window | None
    totals: TimelineTotals
    runs: list[TimelineRun]
    requests: list[LatestRequest]
    model_check: ModelCheck
    prices: TimelinePrices


class LiveSession(_Response):
    """A running session in the Session Select."""

    id: str
    project: str
    project_name: str
    branch: str | None
    started: datetime
    last_request: datetime
    active: bool
    state: Literal["working", "idle"]
    runs_working: int
    requests: int


class EndedSession(_Response):
    """The newest session in a project that is no longer running."""

    id: str
    branch: str | None
    started: datetime
    last_request: datetime
    requests: int


class LiveSessions(_Response):
    """Answer of ``GET /api/live/sessions``."""

    server_time: datetime
    as_of: datetime | None
    etag: str
    unchanged: Literal[False]
    sessions: list[LiveSession]
    latest_ended: EndedSession | None


class LiveSessionsUnchanged(_Response):
    """The short session-list answer when the asked etag still matches."""

    server_time: datetime
    etag: str
    unchanged: Literal[True]
