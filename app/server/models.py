"""Pydantic models for every request and response body of the Bar Tab API.

Request models forbid extra fields. Every route names one of the response models here
as its ``response_model``, so a field that is not declared never leaves the server.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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
    to_fix: "ToFix" = Field(
        default_factory=lambda: _unchecked_to_fix()  # noqa: PLW0108 - ToFix is defined below
    )
    editable_projects: list[str]
    edits: "EditsState"
    mode: "AppMode"
    clock: "ClockInfo"
    rules_version_gap: "VersionGap | None" = None


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
    listed: bool
    edit_block: Literal["folder_not_found"] | None = None


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
    item_id: str | None = None


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
# ``no_file`` is an agent type that ran with no agent file anywhere, such as a built-in
# agent. ``plugin`` is an agent that a plugin adds and ``managed`` one from the managed
# folder (M4): both are items of the setup, so their rows carry an ``item_id``.
AgentScope = Literal[
    "user", "project", "managed", "plugin", "main", "unnamed", "no_file"
]
AgentFileScope = Literal["user", "project", "managed", "plugin"]
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
    item_id: str | None = None
    plugin: str | None = None


class AgentNoRuns(_Response):
    """An agent file with no run in the range.

    ``item_id`` is the setup item of the agent (``agents:<name>``, or
    ``agents:<plugin>:<name>`` for a plugin agent), and ``plugin`` the plugin's name.
    """

    agent: str
    scope: AgentFileScope
    set: SetPair | None
    set_reason: SetReason | None
    item_id: str | None = None
    plugin: str | None = None


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


# Setup (M4). The contract is docs/rebuild/planning/m4-build.md section 5, with the
# owner's answers in section 15 and the designer's plan review in section 16 there.
# A Setup answer whose asked etag still matches is the shared ``Unchanged`` model.
#
# Paths. ``file`` is always a display path (``~/...`` under HOME, project-relative
# inside a project, or the managed folder's name). ``full_path`` is the absolute path.
# The page shows ``file`` and Copy path copies ``full_path`` (owner, November 9).
#
# Masking. Every value that can hold a secret is a ``MaskedText``, masked on the
# server before it reaches these models, and says whether masking hid anything. No
# model here carries a file body.
#
# Ids. An item id is readable and stable: ``<part>:<key path>`` with no scope in it,
# so a value that moves between scopes keeps its id (``settings:effortLevel``,
# ``agents:scout``, ``hooks:PreToolUse:Bash:0``). The page puts it in the URL with
# ``encodeURIComponent``. ``agents:<name>`` is the id Review, Live and setup share.
# A plugin agent is always its own item, ``agents:<plugin>:<name>``, even when a
# user or project agent has the same name (owner, November 9), so the two never
# share an id or a route. Names hold no colon, so the forms can't collide.
#
# Order. ``items`` come in the part's own order (load order for instructions,
# top-wins order inside a name, hook event order, then name) and ``order`` repeats it,
# so a refetch never reorders rows. ``group`` and ``groups`` split long parts.
#
# Task 9 widened ``AgentScope`` with ``plugin`` and ``managed``, gave the Agents rows
# and the Model check rows an ``item_id``, and added ``to_fix`` to ``AppInfo`` and
# ``listed`` to ``Project``, so the OpenAPI file changed once.

SetupPart = Literal[
    "settings",
    "agents",
    "instructions",
    "rules",
    "skills",
    "hooks",
    "permissions",
    "mcp",
    "plugins",
    "output_style",
]
SETUP_PARTS: tuple[SetupPart, ...] = (
    "settings",
    "agents",
    "instructions",
    "rules",
    "skills",
    "hooks",
    "permissions",
    "mcp",
    "plugins",
    "output_style",
)
# Scopes in top-wins order. ``command_line`` is never visible to the server, and
# ``shell`` is the server's own environment from when it started (owner answer 9).
SetupScope = Literal[
    "managed", "command_line", "project_local", "project", "user", "plugin", "shell"
]
# Where inside a scope a file sits. ``parent`` marks a CLAUDE.md or CLAUDE.local.md
# in a folder above the project, read up to the filesystem root as Claude Code does;
# the page shows it as "Parent folder" under Shared project (owner, November 9).
SetupLocation = Literal["parent"]
SETUP_SCOPES: tuple[SetupScope, ...] = (
    "managed",
    "command_line",
    "project_local",
    "project",
    "user",
    "plugin",
    "shell",
)
ScopeState = Literal["set", "not_set", "not_visible", "unreadable"]
ConfidenceLevel = Literal["tested", "documented", "assumed"]
# Why a file was not read. ``outside_scope`` and ``plugin_outside_plugins`` are not
# read failures: the file lies outside what the owner allowed (m4-build.md section 7),
# and the page says "not read here".
UnreadableReason = Literal[
    "permission",
    "not_utf8",
    "too_large",
    "vanished",
    "folder_unlistable",
    "outside_scope",
    "plugin_outside_plugins",
]
NotReadCode = Literal["outside_scope", "plugin_outside_plugins"]
EmptyReason = Literal["none_found", "not_visible"]
EmptyAction = Literal["docs", "copy_path"]
LoadsKind = Literal["always", "on_demand", "when_no_claude_md"]
AppliesWhen = Literal["now", "new_session", "restart", "reload_plugins"]
# Where the value that runs comes from. ``set``: a source wins as written. ``cap``:
# a cap or limit changed it (see ``by_item``). ``default``: nothing sets it.
# ``unknown``: the dashboard can't tell.
EffectiveOrigin = Literal["set", "cap", "default", "unknown"]
ReadOnlyCode = Literal[
    "managed", "plugin", "claude_json_command", "command_line", "not_visible"
]
RiskTier = Literal["safe", "risky"]
ProblemKind = Literal["read_failure", "problem", "cant_tell", "notice"]
ProblemGroup = Literal["couldnt_read", "wont_load", "not_as_set", "cant_tell", "notice"]
FixKind = Literal["open_item", "copy_command", "copy_path", "cant_fix_here"]
ImportState = Literal["read", "missing", "cycle", "too_deep", "not_read"]
PermissionKind = Literal["allow", "ask", "deny", "default_mode", "directory"]
ToFixState = Literal["ok", "unchecked", "failed"]


class Coded(_Response):
    """A code the page turns into words, with its string parameters."""

    code: str
    params: dict[str, str]


class MaskedText(_Response):
    """A value that may hold a secret. ``masked`` is True when masking hid any part."""

    text: str
    masked: bool


class Confidence(_Response):
    """How sure the dashboard is, and the Claude Code version a test ran on."""

    level: ConfidenceLevel
    tested_on: str | None


class ItemReason(_Response):
    """Why the item resolves as it does.

    Why the item resolves as it does. ``ref_item`` names another item the reason is
    about (the cap that lowers it, the file that overrides it), or None.
    """

    code: str
    params: dict[str, str]
    rule_id: str | None
    ref_item: str | None


class ItemCheck(_Response):
    """What the Model check says about an agent's own file, judged over no runs.

    ``code`` and ``params`` are the Model check's reason code and params for the agent
    (``model_check.judge_agent`` with an empty run list), so the Agents inspector says
    what the Model check says. Set only for a project or user agent whose file loads
    and sets a model or an effort.
    """

    code: str
    params: dict[str, str]


class Effective(_Response):
    """The value that runs and where it comes from.

    The value that runs and where it comes from, so the page never parses a reason.
    ``value`` is None for a union part or when nothing runs.
    """

    value: MaskedText | None
    origin: EffectiveOrigin
    by_item: str | None


class SetupSource(_Response):
    """One place an item is set, in top-wins order.

    ``key`` is what sets it there: a settings key path (``effortLevel``), an env
    name (``env.CLAUDE_CODE_EFFORT_LEVEL``), a flag (``--effort``) or a front matter
    key. ``value`` is None for a union part.
    """

    scope: SetupScope
    key: str
    file: str | None
    full_path: str | None
    line: int | None
    value: MaskedText | None
    status: ModelCheckStatus
    plugin: str | None
    location: SetupLocation | None = None


class ScopeReach(_Response):
    """A scope that could set this item.

    A scope that could set this item, and whether the server can see it. A Command line
    entry appears only for an item that has a flag.
    """

    scope: SetupScope
    visible: bool


class SetupLoads(_Response):
    """When an instruction or rules file loads. ``globs`` only for ``on_demand``."""

    kind: LoadsKind
    globs: list[str]


class ReadOnly(_Response):
    """Why an item can't change here and who owns it.

    ``command`` is the ``claude mcp`` command for a user or local MCP server, masked.
    For a plugin item ``params`` names the plugin and the page words how to change
    it (update or disable the plugin).
    """

    code: ReadOnlyCode
    params: dict[str, str]
    command: MaskedText | None


class AgentField(_Response):
    """One front matter field of an agent file.

    One front matter field. ``ignored`` for fields Claude Code ignores on a plugin
    agent, which still carry their value and line.
    """

    name: str
    value: MaskedText | None
    line: int | None
    ignored: bool


class AgentFacts(_Response):
    """Inspector facts for an agent file."""

    plugin: str | None
    fields: list[AgentField]


class ImportRef(_Response):
    """One ``@import`` in an instruction file.

    One ``@import`` in an instruction file. ``target_item`` is the target's item id when
    the target is itself an item.
    """

    target: str
    target_item: str | None
    depth: int
    state: ImportState
    line: int | None


class InstructionFacts(_Response):
    """Inspector facts for a CLAUDE.md or rules file."""

    lines: int
    bytes: int
    imports: list[ImportRef]


class SkillFacts(_Response):
    """Inspector facts for a skill or legacy command.

    Inspector facts for a skill or legacy command. ``invoke`` is the slash form, with
    the plugin namespace when there is one.
    """

    description: MaskedText | None
    invoke: str
    namespace: str | None
    legacy_command: bool


class HookFacts(_Response):
    """Inspector facts for one hook handler."""

    event: str
    matcher: str | None
    handler_type: str
    command: MaskedText | None
    timeout: int | None


class McpFacts(_Response):
    """Inspector facts for one MCP server.

    Inspector facts for one MCP server. Env and headers show names and masked values.
    ``approved`` is None when no approval applies.
    """

    transport: str
    command: MaskedText | None
    url: MaskedText | None
    args: list[MaskedText]
    env: dict[str, MaskedText]
    headers: dict[str, MaskedText]
    approved: bool | None


class PermissionFacts(_Response):
    """Inspector facts for one permission rule, ``defaultMode`` or an extra folder."""

    kind: PermissionKind
    tool: str | None
    pattern: str | None


class PluginScopeState(_Response):
    """Whether one scope's ``enabledPlugins`` turns the plugin on or off."""

    scope: SetupScope
    enabled: bool


class PluginFacts(_Response):
    """Inspector facts for one plugin. ``contents`` lists the item ids it adds."""

    version: str | None
    marketplace: str | None
    enabled: list[PluginScopeState]
    orphaned_versions: list[str]
    contents: list[str]


class OutputStyleFacts(_Response):
    """Inspector facts for the output style setting or one style file."""

    active: str | None
    builtin: bool


class ItemFacts(_Response):
    """The part's extra inspector lines.

    The part's extra inspector lines. Exactly one field is set, for the item's kind, or
    none for a plain setting.
    """

    agent: AgentFacts | None = None
    instruction: InstructionFacts | None = None
    skill: SkillFacts | None = None
    hook: HookFacts | None = None
    mcp: McpFacts | None = None
    permission: PermissionFacts | None = None
    plugin: PluginFacts | None = None
    output_style: OutputStyleFacts | None = None


class SetupItem(_Response):
    """One item on a surface page. The inspector reads every field.

    ``key`` is the raw key or name, and ``label_known`` says whether the page has a
    label for it; when not, the page shows ``key`` (open-ended settings keys never
    fail the closed-enum test). ``not_read`` is set when the item's file lies outside
    the allowed roots, a state apart from Couldn't read and Unknown. ``may_change``
    is True when a file the part couldn't read could change this item's answer.
    ``usage`` is set for agents and model and effort settings, over the last 30 days.
    ``real_path`` is the target's display path when the file is a symlink. For an
    agent, ``status`` is the outcome of what runs (the Model check's word for the file's
    model and effort over no runs), and the load status stays in ``reason``; ``check``
    carries the Model check's code and params when that outcome was judged.
    """

    id: str
    part: SetupPart
    key: str
    name: str
    label_known: bool
    order: int
    group: str | None
    scope: SetupScope | None
    effective: Effective | None
    sources: list[SetupSource]
    winner: int | None
    reach: list[ScopeReach]
    status: ModelCheckStatus
    reason: ItemReason | None
    confidence: Confidence
    loads: SetupLoads | None
    applies: AppliesWhen | None
    writable: bool
    read_only_reason: ReadOnly | None
    risk_tier: RiskTier | None
    feature: Literal["core"]
    facts: ItemFacts
    usage: Coded | None
    real_path: str | None
    not_read: NotReadCode | None
    may_change: bool
    location: SetupLocation | None = None
    check: ItemCheck | None = None


class UnreadableFile(_Response):
    """A file a collector could not read, or was not allowed to.

    ``problem`` is the id of its To fix row, or None for a "not read here" file.
    ``part`` is the setup part the file feeds; a collector that serves several parts
    sets it so the setup map can split one ``Collected.unreadable`` list.
    """

    file: str
    full_path: str | None
    scope: SetupScope | None
    reason: UnreadableReason
    problem: str | None
    part: SetupPart | None = None


class EmptyInfo(_Response):
    """Why a part is empty, and the target of its empty state's action.

    Why a part is empty, and the target of the empty state's action: a docs anchor URL
    for ``docs``, or a full folder path for ``copy_path``.
    """

    reason: EmptyReason
    action: EmptyAction | None
    target: str | None


class GroupCount(_Response):
    """One group of a long part, in order, with its item count."""

    key: str
    count: int


class StatusCount(_Response):
    """How many items of a part carry one status."""

    status: ModelCheckStatus
    count: int


class SetupScopeCell(_Response):
    """One part in one scope, for "Show where each comes from"."""

    scope: SetupScope
    state: ScopeState
    summary: Coded | None


class SetupPartRow(_Response):
    """One row of the setup map.

    One row of the setup map. ``summary`` carries the facts the drawn summary uses in
    ``params`` (effective model and effort, agents with no recent runs, on-demand
    globs). ``scopes`` is always present, so the Switch flips with no fetch.
    """

    part: SetupPart
    summary: Coded
    statuses: list[StatusCount]
    counted_problems: int
    unreadable: bool
    empty: EmptyInfo | None
    scopes: list[SetupScopeCell]


class _SetupAnswer(_Response):
    """Fields every full Setup answer carries."""

    project: str
    server_time: datetime
    as_of: datetime | None
    etag: str
    unchanged: Literal[False]


class SetupMap(_SetupAnswer):
    """Answer of ``GET /api/setup``.

    ``server_started_at`` dates the shell scope. ``listed`` is False for a project
    that is not on Bar Tab's list; its project scopes then read "Not read here" with
    a notice (owner, November 9).
    """

    parts: list[SetupPartRow]
    notices: list[Coded]
    server_started_at: datetime
    listed: bool = True


class SetupPartAnswer(_SetupAnswer):
    """Answer of ``GET /api/setup/{part}``."""

    part: SetupPart
    items: list[SetupItem]
    groups: list[GroupCount]
    unreadable: list[UnreadableFile]
    empty: EmptyInfo | None


class ProblemFix(_Response):
    """The one action a To fix row offers.

    The one action a To fix row offers. ``target`` is an item id, a masked command or a
    full path, by ``kind``.
    """

    kind: FixKind
    target: str | None
    reason: str | None


class ProblemRow(_Response):
    """One row of the problems feed.

    One row of the problems feed. ``id`` is stable across refetches. ``thing`` is the
    display name the title names.
    """

    id: str
    kind: ProblemKind
    group: ProblemGroup
    code: str
    thing: str
    part: SetupPart | None
    item_id: str | None
    file: str | None
    full_path: str | None
    line: int | None
    params: dict[str, str]
    confidence: Confidence
    fix: ProblemFix


class ToFix(_Response):
    """The nav's To fix count.

    The nav's To fix count. ``state`` is ``unchecked`` before the first problems pass
    and ``failed`` when it couldn't run; ``count`` is None then. ``etag`` is the
    problems answer's etag, so the nav and the To fix page agree.
    """

    state: ToFixState
    count: int | None
    etag: str | None


def _unchecked_to_fix() -> ToFix:
    """Return the To fix state before any problems pass (``AppInfo.to_fix`` default)."""
    return ToFix(state="unchecked", count=None, etag=None)


class ProblemList(_SetupAnswer):
    """Answer of ``GET /api/problems``. ``counted`` equals ``to_fix.count``."""

    rows: list[ProblemRow]
    counted: int


# --------------------------------------------------------------------- Rules (M5)
# Rules are global, so these answers carry no project. The page owns every word:
# a rule's sentence and group name are keyed in en.ts by ``rule_id`` and ``key``.

RuleScope = Literal["main", "agent", "model"]


class VersionGap(_Response):
    """The Claude Code that ran last is newer than the rules' checked version.

    ``installed`` is the newest session's version (demo: ``session.json``).
    ``checked_on`` is the oldest ``verified_on.claude_version`` across ``rules.json``
    and ``agent_fields.json``. ``due`` counts the rules checked on a version older
    than ``installed``, for "Show the {n} rules to re-check".
    """

    installed: str
    checked_on: str
    due: int


class RuleQuote(_Response):
    """Verbatim docs text that backs a rule, and the docs section it comes from."""

    doc_url: str
    quote: str


class RuleVerified(_Response):
    """The Claude Code version and the date a rule was checked on."""

    claude_version: str
    date: str


class RuleRow(_Response):
    """One rule from ``rules.json``. ``due`` is True when ``installed`` is newer.

    ``outcomes`` are the distinct ``conditions[].status`` values, in the order they
    first appear in the file, so a setting page can say what each rule can lead to.
    """

    rule_id: str
    key: str
    scope: RuleScope
    combine: str
    layer_order: list[str]
    confidence: ConfidenceLevel
    verified_on: RuleVerified
    due: bool
    outcomes: list[ModelCheckStatus]
    quotes: list[RuleQuote]
    experiment: str | None


class RulesAnswer(_Response):
    """Answer of ``GET /api/rules``. ``rules`` are sorted by ``rule_id``."""

    server_time: datetime
    etag: str
    unchanged: Literal[False]
    installed: str | None
    checked_on: str
    rules: list[RuleRow]


class RulesUnchanged(_Response):
    """The short answer of ``GET /api/rules`` when the asked etag still matches."""

    server_time: datetime
    etag: str
    unchanged: Literal[True]


# ---------------------------------------------------------------------------
# Edit contract (M6a, docs/rebuild/planning/m6-build.md sections 2, 4.2 and 4.3).
# Types and bodies only. The routes, the writer and the preview builder come later.
# ---------------------------------------------------------------------------

EditsMode = Literal["on", "off", "unavailable"]
EditRefusalCode = Literal[
    "changed",
    "preview_mismatch",
    "bad_version",
    "changed_since_save",
    "raced",
    "link_outside",
    "link_dangling",
    "not_regular",
    "hard_link",
    "not_owner",
    "too_large",
    "managed",
    "forbidden_path",
    "folder_not_found",
    "unknown_project",
    "not_editable",
    "bad_value",
    "no_change",
    "unparsed",
    "key_missing",
    "key_present",
    "parent_not_object",
    "repeated_key",
    "oracle_failed",
    "lock_busy",
    "write_failed",
    "ledger_damaged",
    "backup_damaged",
    "not_undoable",
    "unknown_edit",
    "forged_row",
    "request_reused",
    "cant_rebuild",
    "edits_off",
    "edit_key_unknown",
]
EditWarningCode = Literal["wont_win", "config_change_hook", "shared_repo"]
EditReadOnlyCode = Literal[
    "field_until_m7",
    "risky_until_m8",
    "managed",
    "plugin",
    "not_writable",
    "link_outside",
    "link_dangling",
]
RecheckState = Literal["checking", "confirmed", "overwritten"]
UndoState = Literal[
    "can_undo", "changed_since", "undone", "deletes_file", "not_undoable"
]
EditOp = Literal["set"]  # M6a. M6b adds create_agent and agent_set.
EditScope = Literal["user", "project", "local"]
SettingsEditField = Literal[
    "model", "effortLevel", "maxEffortLevel", "autoCompactWindow"
]
EditApplies = Literal["new_session", "new_run", "picked_up"]
DiffKind = Literal["ctx", "add", "del"]
HistoryOp = Literal["set", "create", "undo", "restore"]
# Why a ledger row can't be undone. The writer's own words, closed to these six.
NotUndoableReason = Literal[
    "not_newest",
    "undo_row",
    "restore_row",
    "backup_pruned",
    "backup_damaged",
    "file_refused",
]

# The page makes one request id per press of Save or Undo.
REQUEST_ID_PATTERN = r"^[A-Za-z0-9_-]{8,64}$"


class _AliasedResponse(_Response):
    """Base for response bodies with a field named like a Python keyword.

    ``from`` is a keyword, so the field is ``from_``. Code builds it as ``from_=``,
    a parsed body may use either name, and ``from`` is what leaves the server, through
    ``response_model`` and through a plain ``model_dump``.
    """

    model_config = ConfigDict(extra="forbid", serialize_by_alias=True)


class EditsState(_Response):
    """Whether this server can write. ``instance`` is the server instance id.

    ``unavailable`` is a demo or fixture run whose folders sit in the checkout.
    """

    state: EditsMode
    instance: str


class EditPreviewRequest(_Request):
    """Body of ``POST /api/edit/preview``, settings edits only (``op`` is ``set``).

    ``seq`` is echoed in the answer so the page drops answers older than its latest
    request. The server builds every path from ``project``, ``scope`` and ``field``.
    """

    project: str = Field(min_length=1, max_length=200)
    op: EditOp
    scope: EditScope
    field: SettingsEditField
    value: str | int
    seq: int


class EditSaveRequest(EditPreviewRequest):
    """Body of ``POST /api/edit/save``: the preview body plus its token and an id.

    ``version`` is the token the preview returned. ``request_id`` makes a repeat press
    of Save return the first result instead of a stale-token refusal.
    """

    version: str = Field(min_length=1, max_length=2048)
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)


class EditUndoRequest(_Request):
    """Body of ``POST /api/edit/undo``.

    ``version`` and ``anyway`` come back from a ``changed_since_save`` answer to
    confirm "Undo anyway".
    """

    project: str = Field(min_length=1, max_length=200)
    row_id: str = Field(min_length=1, max_length=200)
    request_id: str = Field(pattern=REQUEST_ID_PATTERN)
    version: str | None = Field(default=None, min_length=1, max_length=2048)
    anyway: bool = False


class MarkSeenRequest(_Request):
    """Body of ``POST /api/edit/rows/<id>/seen``. The read key is enough."""

    project: str = Field(min_length=1, max_length=200)


class DiffLine(_Response):
    """One line of a masked diff. ``old_n`` and ``new_n`` are real file line numbers.

    A context line has both, an added line only ``new_n`` and a removed line only
    ``old_n``.
    """

    kind: DiffKind
    old_n: int | None
    new_n: int | None
    text: str


class EditDiff(_Response):
    """A masked diff of one file. ``new_file`` is True when the save creates it."""

    lines: list[DiffLine]
    new_file: bool


class EditTarget(_Response):
    """The file a save would write. For a link, ``real_path`` is the target file."""

    scope: EditScope
    display_path: str
    real_path: str
    link: bool
    exists: bool
    git_tracked: bool
    new_file: bool


class RunsAt(_Response):
    """What the setting runs at, and the Model check status of that value."""

    value: str | None
    status: ModelCheckStatus


class EditSetChange(_AliasedResponse):
    """The key's value before and after. ``from`` is None when the file has no key."""

    from_: str | int | None = Field(
        validation_alias=AliasChoices("from_", "from"), serialization_alias="from"
    )
    to: str | int


class EditRuns(_Response):
    """What runs now, and what would run after the save."""

    now: RunsAt
    after: RunsAt


class EditEffect(_Response):
    """What a save does. ``applies`` says when a running session picks it up."""

    set: EditSetChange
    runs: EditRuns
    applies: EditApplies


class OptionRunsAt(_Response):
    """One option of an effort or effort cap field, with where it would run."""

    value: str
    runs_at: RunsAt


class ScopeOutcome(_Response):
    """What a value saved in one scope would do. ``beaten_by`` names the scope above."""

    status: ModelCheckStatus
    beaten_by: EditScope | None


class EditScopeRow(_Response):
    """One writable scope of a field: its file, its current value and its outcome."""

    scope: EditScope
    display_path: str
    real_path: str
    link: bool
    git_tracked: bool
    writable: bool
    read_only_reason: EditReadOnlyCode | None
    current_value: str | None
    outcome: ScopeOutcome


class EditReach(_Response):
    """A project a user-scope save changes, with that project's outcome."""

    project: str
    name: str
    outcome: ScopeOutcome


class EditWarning(_Response):
    """A warning the preview shows before Save. ``params`` fill the page's string."""

    code: EditWarningCode
    params: dict[str, str]


class EditSummary(_Response):
    """The phone bar's line: what the save does to which file."""

    verb: Literal["creates", "changes"]
    lines_changed: int
    display_path: str


class EditRefusal(_Response):
    """Why a save to the picked scope would be refused. ``params`` fill the string."""

    code: EditRefusalCode
    params: dict[str, str]


class EditPreview(_Response):
    """Answer of ``POST /api/edit/preview``.

    ``choice_key`` is the sha256 of the canonical body without ``seq``, and ``version``
    is the token Save sends back. ``refusal`` is None unless a save to the picked scope
    would be refused.
    """

    server_time: datetime
    seq: int
    choice_key: str
    target: EditTarget
    effect: EditEffect
    options: list[OptionRunsAt]
    scopes: list[EditScopeRow]
    reaches: list[EditReach]
    warnings: list[EditWarning]
    diff: EditDiff
    summary: EditSummary
    read_at: str
    version: str
    refusal: EditRefusal | None


class EditSaved(_Response):
    """Answer of a good ``POST /api/edit/save``."""

    server_time: datetime
    row_id: str
    saved_at: str
    recheck_after_ms: int


class EditConflict(_Response):
    """The 409 body of a save: the file or the body changed since the preview.

    ``code`` is ``changed`` or ``preview_mismatch``. ``preview`` is a fresh one, and
    ``changed_keys`` lists the keys that changed on disk (empty when the writer can't
    tell, such as after a restart).
    """

    server_time: datetime
    code: EditRefusalCode
    preview: EditPreview | None
    changed_keys: list[str]
    edited_key_changed: bool


class EditError(_Response):
    """The 422 body of an edit route: a refusal with no write."""

    server_time: datetime
    code: EditRefusalCode
    params: dict[str, str]


class UndoDone(_Response):
    """Answer of a good ``POST /api/edit/undo``."""

    server_time: datetime
    row_id: str


class UndoPreview(_Response):
    """What "Undo anyway" would do to a file that changed since the save."""

    diff: EditDiff
    version: str


class UndoConflict(_Response):
    """The 409 body of an undo: the file changed since the save."""

    server_time: datetime
    code: EditRefusalCode
    undo_preview: UndoPreview


class RecheckAnswer(_Response):
    """Answer of ``GET /api/edit/rows/<id>``: the read-only checks after a save.

    ``ours_survived`` is None while the state is ``checking``.
    """

    server_time: datetime
    state: RecheckState
    changed_keys: list[str]
    ours_survived: bool | None
    checked_at: str | None
    seen: bool


class DriftAnswer(_Response):
    """Answer of ``GET /api/edit/rows/<id>/drift``.

    ``lines`` is the masked diff from the bytes Bar Tab wrote to the file now. It is
    None, with ``code`` ``cant_rebuild``, when the bytes can't be rebuilt.
    """

    server_time: datetime
    lines: list[DiffLine] | None
    code: EditRefusalCode | None


class HistorySubject(_Response):
    """What a ledger row edited. ``name`` is None for the main session."""

    kind: Literal["main", "agent"]
    name: str | None


class HistoryRecheck(_Response):
    """The recheck result a ledger row carries, and whether the owner saw it."""

    state: RecheckState
    changed_keys: list[str]
    ours_survived: bool | None
    seen: bool


class HistoryRow(_AliasedResponse):
    """One edit in the Changes page. Values are masked.

    ``from`` and ``to`` are None for a create or a removed key.
    """

    id: str
    time: str
    subject: HistorySubject
    field: str
    from_: str | int | None = Field(
        validation_alias=AliasChoices("from_", "from"), serialization_alias="from"
    )
    to: str | int | None
    scope: EditScope
    display_path: str
    real_path: str
    op: HistoryOp
    undo_state: UndoState
    undone_at: str | None
    recheck: HistoryRecheck | None
    not_undoable_reason: NotUndoableReason | None


class HistoryOlder(_Response):
    """Older rows, with their count.

    Rows past the newest 20 of one file, and rows a scan of the backups folder found
    for this project in files that are no longer one of its settings files. The
    second kind can't be undone.
    """

    count: int
    rows: list[HistoryRow]


class BackupFolder(_Response):
    """The folder that holds the backups. ``real`` differs from ``display`` by link."""

    display: str
    real: str


class EditHistory(_Response):
    """Answer of ``GET /api/edit/history``."""

    server_time: datetime
    rows: list[HistoryRow]
    older: HistoryOlder
    backup_folder: BackupFolder
    edits: EditsState


class OpenWarning(_Response):
    """Answer of ``GET /api/edit/open``: the newest overwritten row not yet seen."""

    server_time: datetime
    row: HistoryRow | None
