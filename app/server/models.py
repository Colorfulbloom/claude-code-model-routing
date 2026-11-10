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


# Review (M3). The contract is docs/rebuild/planning/m3-build.md section 4, with the
# designer's plan review folded in (section 12 there). A Review answer whose asked
# etag still matches is the shared ``Unchanged`` model.
#
# Unpriced rule. A cost sums the priced requests only. Every cost that may miss some
# requests carries an ``Unpriced`` beside it, so the page can say "at least {cost}",
# or "No price for {model}" when ``cost`` is None. A share is None when its own cost
# is None, never 0.

ReviewRange = Literal["today", "7d", "30d", "90d", "12m", "all"]
REVIEW_RANGES: tuple[ReviewRange, ...] = ("today", "7d", "30d", "90d", "12m", "all")
DEFAULT_REVIEW_RANGE: ReviewRange = "30d"
ChartUnit = Literal["hour", "day", "week", "month"]
PagerReason = Literal["no_earlier_data", "newest"]
# ``no_file`` is an agent type that ran with no user or project agent file, such as a
# plugin or built-in agent. The page calls it an unknown source until M4.
AgentScope = Literal["user", "project", "main", "unnamed", "no_file"]
AgentFileScope = Literal["user", "project"]
# Why ``set`` holds no value. ``no_file``: no agent file was found. ``sets_nothing``:
# the file exists and sets neither model nor effort. ``read_failed``: the setup could
# not be read, and the answer's ``errors`` names the card.
SetReason = Literal["no_file", "sets_nothing", "read_failed"]
ReviewCard = Literal["model_check", "agent_setup"]
CardErrorCode = Literal["setup_unreadable", "unexpected"]


class ReviewWindow(_Response):
    """The range's window and the one it compares with, in the answer's zone.

    ``end`` is the clock T. ``prior_start`` and ``prior_end`` are None for ``all``.
    ``oldest`` is the oldest stored request in the project, or None when there is
    none. ``partial`` is True when ``oldest`` falls after ``start``, so the range
    holds less history than its name. ``prior_partial`` is True when ``oldest`` falls
    after ``prior_start``, so a change against the prior would mislead.
    """

    start: datetime
    end: datetime
    prior_start: datetime | None
    prior_end: datetime | None
    tz: str
    oldest: datetime | None
    partial: bool
    prior_partial: bool


class CardError(_Response):
    """A card the server could not build. Its field in the answer is None."""

    card: ReviewCard
    code: CardErrorCode


class _ReviewAnswer(_Response):
    """Fields every full Review answer carries."""

    project: str
    range: ReviewRange
    window: ReviewWindow
    server_time: datetime
    as_of: datetime | None
    etag: str
    unchanged: Literal[False]
    prices: TimelinePrices
    errors: list[CardError]


class CountTile(_Response):
    """A whole-number tile. ``change_pct`` is relative, ``change_abs`` the difference.

    Both changes are None when there is no prior window or ``window.prior_partial``.
    ``change_pct`` is also None when the prior value is 0.
    """

    value: int
    prior: int | None
    change_pct: float | None
    change_abs: int | None


class CostTile(_Response):
    """The cost tile, with the unpriced requests of the range and of the prior."""

    value: float | None
    prior: float | None
    change_pct: float | None
    change_abs: float | None
    unpriced: Unpriced
    prior_unpriced: Unpriced | None


class ShareTile(_Response):
    """A share from 0 to 1, such as the cache share. ``change_abs`` is in shares."""

    value: float | None
    prior: float | None
    change_abs: float | None


class SummaryTiles(_Response):
    """The four Summary tiles."""

    cost: CostTile
    sessions: CountTile
    tokens: CountTile
    cache_share: ShareTile


class AgentMoney(_Response):
    """One agent's part of the range's cost. ``agent`` is an agent key.

    The rows add up to the Cost tile, so a plugin agent with no file still has one.
    """

    agent: str
    model: str | None
    cost: float | None
    share: float | None
    requests: int
    unpriced: Unpriced


class SessionWhole(_Response):
    """A session's whole numbers, for a session that started before the range."""

    tokens: int
    cost: float | None
    unpriced: Unpriced


class ReviewSession(_Response):
    """One session in a Review list. ``agents`` are agent keys, biggest cost first.

    ``tokens``, ``cost`` and ``runs`` count the range only. ``started_before_range``
    marks a session whose first request is before ``window.start``, and ``whole``
    then holds its numbers over its whole life, so the page can show either.
    """

    id: str
    started: datetime
    last_request: datetime
    branch: str | None
    state: SessionState
    agents: list[str]
    runs: int
    tokens: int
    cost: float | None
    unpriced: Unpriced
    started_before_range: bool
    whole: SessionWhole | None


class Summary(_ReviewAnswer):
    """Answer of ``GET /api/summary``. ``model_check`` is None when its card failed."""

    tiles: SummaryTiles
    money: list[AgentMoney]
    model_check: ModelCheck | None
    top_sessions: list[ReviewSession]
    session_count: int
    no_usage_sessions: int


class KindCosts(_Response):
    """Dollars per kind of cost, over priced requests only."""

    input: float
    output: float
    cache_read: float
    cache_write: float


class ModelBarCost(_Response):
    """One model's part of a chart bar. ``cost`` is None when none of it is priced."""

    cost: float | None
    kinds: KindCosts
    requests: int
    unpriced: Unpriced


class ChartBar(_Response):
    """One bar of the cost chart.

    ``start`` and ``end`` are clipped to the chart window and to T, so the first and
    last bars may be shorter than one ``unit``. ``open`` marks the bar that holds T.
    ``holds_oldest`` marks the bar that holds ``window.oldest``. ``no_records`` marks
    a bar that ends before ``oldest``, which the page shows as no records, not $0.
    """

    start: datetime
    end: datetime
    by_model: dict[str, ModelBarCost]
    unpriced: Unpriced
    open: bool
    holds_oldest: bool
    no_records: bool


class ChartWindow(_Response):
    """The chart's own window, and why a pager end is reached.

    On the newest page the window is the range's window, so the legend total equals
    the Cost tile. Earlier pages are whole windows of the same length. ``all`` is one
    page from ``oldest`` to T, with both ends reached, in days, weeks or months by span.
    """

    start: datetime
    end: datetime
    unit: ChartUnit
    has_earlier: bool
    has_later: bool
    earlier_reason: PagerReason | None
    later_reason: PagerReason | None
    newest: bool


class ModelCost(_Response):
    """A legend entry over the chart window. A model with no price keeps its entry."""

    model: str
    cost: float | None
    requests: int
    unpriced: Unpriced


class CostChart(_ReviewAnswer):
    """Answer of ``GET /api/cost-chart``. It never changes the tiles."""

    chart: ChartWindow
    bars: list[ChartBar]
    legend: list[ModelCost]
    kinds: KindCosts
    unpriced: Unpriced
    y_ticks: list[float]


class SessionDay(_Response):
    """The sessions of one local day.

    A session sits under the local day of its first request inside the range, so a
    session that started before the range sits under the range's first day. A day
    can continue on the next page, and the page joins it under one header. The field
    is ``day``, not ``date``, because a field named like its type breaks the
    annotation in a Pydantic class body.
    """

    day: date
    sessions: list[ReviewSession]


class SessionList(_ReviewAnswer):
    """Answer of ``GET /api/sessions``.

    Newest first by (first request in range, id). ``next`` is an opaque cursor that
    anchors on the last row's sort key, so a refetch never repeats or moves loaded
    rows, and None at the end of the list.
    """

    count: int
    days: list[SessionDay]
    next: str | None


class PairRuns(_Response):
    """One model and effort pair the runs used, with its run count."""

    model: str | None
    effort: str | None
    runs: int


class AgentRow(_Response):
    """An agent that ran in the range, with its setup and its model check status.

    ``set_reason`` says why ``set`` holds no value. ``ran_pairs`` lists every pair
    the runs used, most runs first. ``runs_as_set`` and ``runs_not_as_set`` come
    from the model check and are None when nothing is set.
    """

    agent: str
    scope: AgentScope
    set: SetPair | None
    set_reason: SetReason | None
    ran: RanPair
    ran_pairs: list[PairRuns]
    status: ModelCheckStatus | None
    reason_code: str | None
    params: dict[str, str]
    runs: int
    runs_as_set: int | None
    runs_not_as_set: int | None
    sessions: int
    cost: float | None
    share: float | None
    requests: int
    unpriced: Unpriced


class AgentNoRuns(_Response):
    """An agent file with no run in the range."""

    agent: str
    scope: AgentFileScope
    set: SetPair | None
    set_reason: SetReason | None


class AgentList(_ReviewAnswer):
    """Answer of ``GET /api/agents``. ``ran`` adds up to the Cost tile."""

    ran: list[AgentRow]
    never_ran: list[AgentNoRuns]


class ModelRow(_Response):
    """One model over the range. ``used_by`` holds agent keys."""

    model: str
    cost: float | None
    share: float | None
    tokens: int
    requests: int
    cache_share: float | None
    used_by: list[str]
    unpriced: Unpriced


class ModelKinds(_Response):
    """One model's dollars per kind of cost, over its priced requests."""

    model: str
    input: float
    output: float
    cache_read: float
    cache_write: float
    unpriced: Unpriced


class ModelList(_ReviewAnswer):
    """Answer of ``GET /api/models``. ``unpriced`` covers the whole legend."""

    rows: list[ModelRow]
    kinds: list[ModelKinds]
    legend: KindCosts
    unpriced: Unpriced
