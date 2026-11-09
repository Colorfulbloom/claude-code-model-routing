"""The session timeline: what one session looked like at clock T.

``build_timeline`` answers from the SQLite store alone. It reads the requests of one
session with ``ts <= T`` and ignores everything after T, so a fake or replayed clock
needs no transcript writes. The rules are ported from the old ``/api/live``
(``dashboard/api_live.py``), which is the oracle at T.

Where the numbers come from

* Whole minutes (before the minute that holds T) come from ``minute_usage`` cells,
  priced per cell by their tier key. That sums to the same cost as pricing each
  request.
* The minute that holds T, and the rolling 60 seconds before T, come from the
  winning request rows with ``ts <= T``, because a cell holds the whole minute and
  would leak requests after T.
* Exact times (first and last request of a run, round ends, the latest eight
  requests) come from one light pass over the session's winning requests. A request
  wins its key when no other copy has a larger (output, ts, path), which is the
  ``best_requests`` view's rule, tested per row so no query ranks the whole table.

Run rules (old line numbers in ``dashboard/api_live.py``)

* Window (``:75-78``, ``:587-594``). Running is a request after T minus 30 minutes,
  strict. Active is a request after T minus 60 seconds.
* State (``:356-369``). Finished when done, else working while T minus ``active_at``
  is under 60 seconds, else idle. ``active_at`` is the later of the last request and
  the start of the latest round.
* Done (``:307-336``). A finished stop at or before T, no round started after it,
  every child done. Main is never done. ``states`` replays the same rule at every
  earlier time, counting a child only once it has a request and its link.
* Parents (``:178-203``). The earliest launch link at or before T names the parent.
  A link to itself or to an ancestor is dropped. The parent must be a run with
  requests in the session, else the run hangs under main with ``parent_known`` false.
* Together (``:285-305``), dispatch order (``:272-276``) and rounds (``:206-232``)
  follow the old code. ``label_n`` is stored by the ingest and never renamed.

Nothing here returns ``cwd``, message text, tool data or a description.
"""

import bisect
import hashlib
import json
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

import history
import ingest
import model_catalog
import usage
import usage_query
from models import (
    Cum,
    LatestRequest,
    ModelCheck,
    ModelTokens,
    Round,
    RoundByKind,
    RunState,
    Segment,
    SessionState,
    StateAt,
    Timeline,
    TimelineAxis,
    TimelineBucket,
    TimelinePrices,
    TimelineRun,
    TimelineSession,
    TimelineTotals,
    Together,
    Unpriced,
    Window,
)
from prices import price_parts

MAIN = "main"
UNNAMED = "unnamed"
RUNNING_WINDOW = timedelta(minutes=30)
ACTIVE_WINDOW = timedelta(seconds=60)
TOGETHER_WINDOW = timedelta(seconds=5)
SETTLE_WINDOW = timedelta(minutes=5)
LATEST = 8
BUCKET_SECONDS = (60, 120, 300, 600, 900, 1800, 3600)
MAX_BUCKETS = 60
TICK_STEPS = (300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400)
MAX_TICKS = 6
ETAG_HEX = 16

ModelCheckFn = Callable[[str, Sequence[TimelineRun]], ModelCheck]
PricesFn = Callable[[], TimelinePrices]

# A request wins its key when no other copy has a larger (output, ts, path). This is
# the ``best_requests`` view's ranking, written per row so the planner can use the
# ``requests_key`` index instead of ranking every row in the store.
BEST_SQL = (
    "NOT EXISTS (SELECT 1 FROM requests AS o JOIN files AS g ON g.id = o.file_id"
    " WHERE o.key = r.key AND o.file_id <> r.file_id"
    " AND (o.output, o.ts, g.path) > (r.output, r.ts, f.path))"
)
_REFS_SQL = (
    "SELECT r.ts, COALESCE(f.run_id, 'main'), r.file_id, r.key"  # noqa: S608
    " FROM requests AS r JOIN files AS f ON f.id = r.file_id"
    f" WHERE f.session_id = ? AND r.ts <= ? AND {BEST_SQL}"
    " ORDER BY r.ts, f.path, r.key"
)
_ROWS_SQL = (
    "SELECT r.ts, COALESCE(f.run_id, 'main'), r.model, r.effort, r.speed,"  # noqa: S608
    " r.service_tier, r.inference_geo, r.input, r.output, r.cache_read,"
    " r.cache_write_5m, r.cache_write_1h"
    " FROM requests AS r JOIN files AS f ON f.id = r.file_id"
    f" WHERE f.session_id = ? AND r.ts >= ? AND r.ts <= ? AND {BEST_SQL}"
    " ORDER BY r.ts, f.path, r.key"
)
_RUN_SQL = (
    "SELECT r.model, r.effort FROM requests AS r JOIN files AS f ON f.id = r.file_id"
    " WHERE f.session_id = ? AND COALESCE(f.run_id, 'main') = ? AND r.ts <= ?"
    " AND {best} ORDER BY r.ts, f.path, r.key"
)
_CELLS_SQL = (
    "SELECT run_key, minute, model, effort, speed, service_tier, inference_geo, tier,"
    " input, output, cache_read, cache_write_5m, cache_write_1h, requests"
    " FROM minute_usage WHERE session_id = ? AND minute < ?"
    " ORDER BY minute, run_key, model, effort, speed, service_tier, inference_geo, tier"
)


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class _Ref:
    """A winning request at or before T, by its place in the store."""

    ts: str
    run: str
    file_id: int
    key: str


@dataclass(frozen=True)
class _Event:
    """A launch, brief or stop row at or before T."""

    run: str
    kind: str
    at: str
    finished: bool
    by_kind: str | None
    by_run: str | None


@dataclass(frozen=True)
class SessionData:
    """What the store holds about one session up to T."""

    session_id: str
    branch: str | None
    refs: list[_Ref]
    events: list[_Event]
    agent_types: dict[str, str | None]
    labels: dict[str, int | None]

    @property
    def first(self) -> datetime:
        """The time of the first request."""
        return parse_ts(self.refs[0].ts)

    @property
    def last(self) -> datetime:
        """The time of the last request."""
        return parse_ts(self.refs[-1].ts)


def parse_ts(text: str) -> datetime:
    """Parse the store's UTC text into an aware datetime."""
    return datetime.fromisoformat(text)


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(UTC)


def load_session(
    conn: sqlite3.Connection,
    session_id: str,
    t: datetime,
    *,
    project_key: str | None,
    folder_keys: Mapping[str, str] | None = None,
) -> SessionData | None:
    """Read a session up to ``t``, or None when it is unknown or has no request yet.

    ``project_key`` None skips the project check. Otherwise the session's transcript
    folder must map to ``project_key`` in ``folder_keys`` (the provider's
    folder-to-project map). A folder that is not in the map, or maps to another
    project, reads as unknown.
    """
    row = conn.execute(
        "SELECT folder, branch FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        return None
    if project_key is not None and (folder_keys or {}).get(str(row[0])) != project_key:
        return None
    at = ingest.ts_text(t)
    refs = [
        _Ref(str(r[0]), str(r[1]), int(r[2]), str(r[3]))
        for r in conn.execute(_REFS_SQL, (session_id, at))
    ]
    if not refs:
        return None
    events = [
        _Event(str(r[0]), str(r[1]), str(r[2]), bool(r[3]), r[4], r[5])
        for r in conn.execute(
            "SELECT run_key, kind, at, finished, by_kind, by_run FROM run_events"
            " WHERE session_id = ? AND at IS NOT NULL AND at <= ?"
            " ORDER BY at, file_id, seq",
            (session_id, at),
        )
    ]
    types: dict[str, str | None] = {}
    labels: dict[str, int | None] = {}
    for run_id, agent_type, label_n in conn.execute(
        "SELECT run_id, agent_type, label_n FROM runs WHERE session_id = ?",
        (session_id,),
    ):
        types[str(run_id)] = str(agent_type) if agent_type else None
        labels[str(run_id)] = None if label_n is None else int(label_n)
    return SessionData(
        session_id,
        None if row[1] is None else str(row[1]),
        refs,
        events,
        types,
        labels,
    )


# ------------------------------------------------------------------------- runs


@dataclass
class _Round:
    at: datetime
    last: datetime
    by: str | None
    by_kind: RoundByKind | None


@dataclass
class _Run:
    """One run at T, with the facts the answer and the state rules need."""

    key: str
    run_id: str
    agent_type: str | None
    label_n: int
    ts: list[str]
    first: datetime
    last: datetime
    active_at: datetime
    parent_key: str | None = None
    known: bool = True
    linked_at: datetime | None = None
    depth: int = 0
    order: int = 0
    together: Together | None = None
    rounds: list[_Round] = field(default_factory=list[_Round])
    stops: list[tuple[datetime, bool]] = field(
        default_factory=list[tuple[datetime, bool]]
    )
    done: list[tuple[datetime, bool]] = field(
        default_factory=list[tuple[datetime, bool]]
    )
    finished: bool = False
    finished_at: datetime | None = None
    state: RunState = "idle"


def run_id_of(key: str) -> str:
    """Return a run key's run id, 12 hex of a sha256 (``main`` for main)."""
    if key == MAIN:
        return MAIN
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _parents(events: Sequence[_Event]) -> dict[str, tuple[str, datetime]]:
    """Return ``{child key: (dispatcher key, link time)}`` from the launch rows.

    The earliest link wins. A link from a run to itself, or to one of its own
    ancestors, is dropped, so there is no cycle. The dispatcher is ``main`` for the
    main session.
    """
    found = sorted(
        (
            (e.at, "" if e.run == MAIN else e.run, e.run, e.by_run)
            for e in events
            if e.kind == "launch" and e.by_run
        ),
        key=lambda f: (f[0], f[1], f[3]),
    )
    parent_of: dict[str, tuple[str, datetime]] = {}
    for at, _tie, dispatcher, child in found:
        if child in parent_of or child == dispatcher:
            continue
        up, cycle = dispatcher, False
        while up != MAIN:
            if up == child:
                cycle = True
                break
            up = parent_of[up][0] if up in parent_of else MAIN
        if not cycle:
            parent_of[child] = (dispatcher, parse_ts(at))
    return parent_of


def _value_at(changes: Sequence[tuple[datetime, bool]], moment: datetime) -> bool:
    """Return the value a change list holds at ``moment`` (False before the first)."""
    index = bisect.bisect_right([c[0] for c in changes], moment) - 1
    return changes[index][1] if index >= 0 else False


def _gate(child: _Run) -> datetime:
    """The time from which ``child`` holds up its parent's done state.

    A child counts once it has a request and its link, so an earlier replay time
    reads as the old route read it then.
    """
    return max(child.first, child.linked_at or child.first)


def _done_value(
    run: _Run,
    children: Sequence[_Run],
    moment: datetime,
    stop_times: Sequence[datetime],
    starts: Sequence[datetime],
) -> bool:
    """The old done rule for ``run`` at ``moment``."""
    index = bisect.bisect_right(stop_times, moment) - 1
    if index < 0:
        return False
    stop_at, finished = run.stops[index]
    if not finished:
        return False
    j = bisect.bisect_right(starts, moment) - 1
    if j >= 0 and starts[j] > stop_at:
        return False
    return all(_value_at(c.done, moment) for c in children if moment >= _gate(c))


def _done_changes(run: _Run, children: Sequence[_Run]) -> list[tuple[datetime, bool]]:
    """Return where ``run``'s done value changes, as ``(time, value)`` pairs."""
    stop_times = [s[0] for s in run.stops]
    starts = [r.at for r in run.rounds]
    times = set(stop_times) | set(starts)
    for child in children:
        times.add(_gate(child))
        times.update(c[0] for c in child.done)
    out: list[tuple[datetime, bool]] = []
    value = False
    for moment in sorted(times):
        now_value = _done_value(run, children, moment, stop_times, starts)
        if now_value != value:
            out.append((moment, now_value))
            value = now_value
    return out


def _by_kind(value: str | None) -> RoundByKind | None:
    if value == "coordinator":
        return "coordinator"
    if value == "human":
        return "human"
    if value == "peer":
        return "peer"
    return None


def _round_list(
    key: str,
    ts: list[str],
    parent: str | None,
    briefs: Sequence[_Event],
    ids: Mapping[str, str],
) -> list[_Round]:
    """Round 1 from the first request, then one per brief, with each last request."""
    starts: list[tuple[str, str | None, RoundByKind | None]] = [(ts[0], parent, None)]
    for brief in briefs:
        by: str | None = None
        kind = _by_kind(brief.by_kind)
        if kind == "coordinator":
            by = MAIN
        elif kind == "peer" and brief.by_run and brief.by_run != key:
            by = ids.get(brief.by_run)
        starts.append((brief.at, by, kind))
    out: list[_Round] = []
    for i, (at, by, kind) in enumerate(starts):
        low = bisect.bisect_left(ts, at)
        high = (
            bisect.bisect_left(ts, starts[i + 1][0]) if i + 1 < len(starts) else len(ts)
        )
        last = ts[high - 1] if high > low else at
        out.append(_Round(parse_ts(at), parse_ts(last), by, kind))
    return out


def _idle_marks(
    points: Sequence[datetime],
    t: datetime,
    *,
    ended_after: timedelta | None,
) -> list[tuple[datetime, str]]:
    """Return ``(time, state)`` changes for activity at ``points`` up to ``t``.

    The state is working for 60 seconds after a point, idle after that, and ended
    once ``ended_after`` has passed with no new point (when it is set). A new point
    makes it working again. Only changes at or before ``t`` are listed.
    """
    out: list[tuple[datetime, str]] = []
    ordered = sorted(set(points))
    for i, point in enumerate(ordered):
        out.append((point, "working"))
        following = ordered[i + 1] if i + 1 < len(ordered) else None
        horizon = following if following is not None else t
        for after, word in (
            (ACTIVE_WINDOW, "idle"),
            (ended_after, "ended"),
        ):
            if after is None:
                continue
            at = point + after
            if at < horizon or (following is None and at <= horizon):
                out.append((at, word))
    # A repeated state is no change, and the last mark at one time wins.
    cleaned: list[tuple[datetime, str]] = []
    for at, word in out:
        if cleaned and cleaned[-1][0] == at:
            cleaned.pop()
        if not cleaned or cleaned[-1][1] != word:
            cleaned.append((at, word))
    return cleaned


def _state_value(marks: Sequence[tuple[datetime, str]], moment: datetime) -> str:
    index = bisect.bisect_right([m[0] for m in marks], moment) - 1
    return marks[index][1] if index >= 0 else "idle"


def _run_states(run: _Run, t: datetime) -> list[StateAt]:
    """Return the run's state history up to ``t``: working, idle and finished."""
    points = [r.at for r in run.rounds]
    points.extend(parse_ts(x) for x in run.ts)
    marks = _idle_marks(points, t, ended_after=None)
    times = {m[0] for m in marks} | {c[0] for c in run.done}
    out: list[StateAt] = []
    previous: str | None = None
    for moment in sorted(times):
        if moment < run.first:
            continue
        word = (
            "finished" if _value_at(run.done, moment) else _state_value(marks, moment)
        )
        if word != previous:
            out.append(StateAt(at=moment, state=word))
            previous = word
    return out


def _link_parents(
    runs: Mapping[str, _Run], parent_of: Mapping[str, tuple[str, datetime]]
) -> None:
    """Set each agent run's parent from the links, or main with ``known`` false."""
    for key, run in runs.items():
        if key == MAIN:
            continue
        found = parent_of.get(key)
        if found is not None and (found[0] == MAIN or found[0] in runs):
            run.parent_key, run.known, run.linked_at = found[0], True, found[1]
        else:
            run.parent_key, run.known, run.linked_at = MAIN, False, None


def _settle(runs: Mapping[str, _Run], t: datetime) -> None:
    """Set each run's done history, finished flag and state at ``t``."""
    children: dict[str, list[_Run]] = defaultdict(list)
    for run in runs.values():
        if run.key != MAIN and run.known and run.parent_key is not None:
            children[run.parent_key].append(run)
    for run in sorted(runs.values(), key=lambda r: -r.depth):
        if run.key != MAIN:
            run.done = _done_changes(run, children.get(run.key, ()))
    for run in runs.values():
        run.active_at = max(run.last, run.rounds[-1].at)
        run.finished = run.key != MAIN and _value_at(run.done, t)
        if run.finished:
            run.finished_at = run.done[-1][0]
            run.state = "finished"
        elif t - run.active_at < ACTIVE_WINDOW:
            run.state = "working"
        else:
            run.state = "idle"


def analyze_runs(data: SessionData, t: datetime) -> list[_Run]:
    """Work out every run of the session at ``t``, in dispatch order (main first)."""
    by_run: dict[str, list[str]] = defaultdict(list)
    for ref in data.refs:
        by_run[ref.run].append(ref.ts)
    ids = {key: run_id_of(key) for key in by_run}
    runs: dict[str, _Run] = {}
    for key, ts in by_run.items():
        agent_type = data.agent_types.get(key)
        label = data.labels.get(key)
        runs[key] = _Run(
            key=key,
            run_id=ids[key],
            agent_type=agent_type,
            label_n=label if label is not None else 1,
            ts=ts,
            first=parse_ts(ts[0]),
            last=parse_ts(ts[-1]),
            active_at=parse_ts(ts[-1]),
        )
    _link_parents(runs, _parents(data.events))
    agents = sorted(
        (r for r in runs.values() if r.key != MAIN),
        key=lambda r: (r.ts[0], r.run_id),
    )
    ordered = ([runs[MAIN]] if MAIN in runs else []) + agents
    base = 0 if MAIN in runs else 1
    for place, run in enumerate(ordered):
        run.order = place + base
    _depths(runs)
    _together(agents)
    stops: dict[str, list[tuple[datetime, bool]]] = defaultdict(list)
    briefs: dict[str, list[_Event]] = defaultdict(list)
    for event in data.events:
        if event.kind == "stop" and event.run != MAIN:
            stops[event.run].append((parse_ts(event.at), event.finished))
        elif event.kind == "brief" and event.run != MAIN:
            briefs[event.run].append(event)
    for key, run in runs.items():
        parent_id = (
            None
            if key == MAIN
            else MAIN
            if run.parent_key == MAIN
            else ids.get(run.parent_key or "")
        )
        run.rounds = _round_list(key, run.ts, parent_id, briefs.get(key, ()), ids)
        run.stops = stops.get(key, [])
    _settle(runs, t)
    return ordered


def _depths(runs: Mapping[str, _Run]) -> None:
    """Set each run's depth: 0 for main, 1 for a child of main, and so on."""
    for run in runs.values():
        steps, key = 0, run.key if run.key != MAIN else None
        while key is not None and steps <= len(runs):
            key = runs[key].parent_key if key in runs else None
            if key == MAIN:
                key = None
            steps += 1
        run.depth = steps


def _together(agents: Sequence[_Run]) -> None:
    """Mark siblings launched within five seconds of the sibling before them."""
    siblings: dict[str, list[_Run]] = defaultdict(list)
    for run in agents:
        siblings[run.parent_key or MAIN].append(run)
    for members in siblings.values():
        launch = {
            r.key: min(r.linked_at, r.first) if r.linked_at is not None else r.first
            for r in members
        }
        members.sort(key=lambda r: (launch[r.key], r.run_id))
        chains: list[list[_Run]] = []
        for run in members:
            if (
                chains
                and launch[run.key] - launch[chains[-1][-1].key] <= TOGETHER_WINDOW
            ):
                chains[-1].append(run)
            else:
                chains.append([run])
        for chain in chains:
            if len(chain) > 1:
                for run in chain:
                    run.together = Together(key=chain[0].run_id, n=len(chain))


def parent_state(run: _Run, t: datetime) -> Literal["known", "waiting", "unknown"]:
    """Say whether a run's starter is known, still expected, or gone for good."""
    if run.key == MAIN or run.known:
        return "known"
    if not run.finished or run.finished_at is None:
        return "waiting"
    return "waiting" if t - run.finished_at < SETTLE_WINDOW else "unknown"


# ----------------------------------------------------------------------- numbers


@dataclass(slots=True)
class _Acc:
    """Running sums for one group of requests."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    requests: int = 0
    unpriced: int = 0
    cost: float = 0.0
    models: set[str] = field(default_factory=set[str])

    def add(  # noqa: PLR0913, PLR0917 - the sums of one cell or request
        self,
        label: str,
        input_: int,
        output: int,
        cache_read: int,
        cache_write: int,
        requests: int,
        cost: float | None,
    ) -> None:
        """Add one cell or request. ``cost`` None counts the requests as unpriced."""
        self.input += input_
        self.output += output
        self.cache_read += cache_read
        self.cache_write += cache_write
        self.requests += requests
        if cost is None:
            self.unpriced += requests
            self.models.add(label)
        else:
            self.cost += cost

    @property
    def new_tokens(self) -> int:
        """Input, output and both cache writes, with no cache reads."""
        return self.input + self.output + self.cache_write

    def merged(self, other: "_Acc") -> "_Acc":
        """Return the sum of two groups."""
        return _Acc(
            self.input + other.input,
            self.output + other.output,
            self.cache_read + other.cache_read,
            self.cache_write + other.cache_write,
            self.requests + other.requests,
            self.unpriced + other.unpriced,
            self.cost + other.cost,
            self.models | other.models,
        )

    def hit_rate(self) -> float | None:
        """Cache reads over reads, writes and input, or None when that is zero."""
        denom = self.cache_read + self.cache_write + self.input
        return self.cache_read / float(denom) if denom else None

    def priced_cost(self) -> float | None:
        """The summed cost, or None when every request in the group is unpriced."""
        if self.requests > 0 and self.unpriced == self.requests:
            return None
        return self.cost


def _order_of(catalog: model_catalog.Catalog) -> dict[str, int]:
    return {str(m["id"]): i for i, m in enumerate(catalog)}


def _model_key(order: Mapping[str, int]) -> Callable[[str], tuple[int, str]]:
    def key(model: str) -> tuple[int, str]:
        return order.get(model, len(order)), model

    return key


def _unpriced(acc: _Acc, order: Mapping[str, int]) -> Unpriced:
    return Unpriced(
        requests=acc.unpriced, models=sorted(acc.models, key=_model_key(order))
    )


def _window(acc: _Acc, order: Mapping[str, int]) -> Window:
    return Window(
        tokens=acc.new_tokens,
        cost=acc.priced_cost(),
        cache_read=acc.cache_read,
        hit_rate=acc.hit_rate(),
        requests=acc.requests,
        unpriced=_unpriced(acc, order),
    )


def choose_bucket_seconds(span: timedelta) -> int:
    """Return the smallest bucket size that keeps the axis to 60 buckets."""
    seconds = span.total_seconds()
    for size in BUCKET_SECONDS:
        if int(seconds // size) + 1 <= MAX_BUCKETS:
            return size
    return BUCKET_SECONDS[-1]


def _ticks(start: datetime, end: datetime, bucket_seconds: int) -> list[datetime]:
    """Return clock-aligned label times on the axis, six at most."""
    first = int(start.timestamp())
    last = int(end.timestamp())
    for step in TICK_STEPS:
        if step < bucket_seconds:
            continue
        marks = list(range(-(-first // step) * step, last + 1, step))
        if len(marks) <= MAX_TICKS:
            return [datetime.fromtimestamp(m, UTC) for m in marks]
    return []


def request_id(key: str, ts: datetime, session_id: str, run: str) -> str:
    """Return the old 12-hex id of a request, from its dedupe key.

    The store keeps the message id as the key, ``r|<request id>`` for a row with only
    a request id, and ``n|<file>|<offset>`` for a row with neither. The old route
    hashed ``[0, message id]``, ``[1, request id]`` or ``[2, time, session, run]``.
    """
    if key.startswith("r|"):
        parts: list[object] = [1, key[2:]]
    elif key.startswith("n|"):
        parts = [2, ts.isoformat(), session_id, None if run == MAIN else run]
    else:
        parts = [0, key]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()[:12]


def as_of(conn: sqlite3.Connection, now: datetime) -> datetime | None:
    """The end of the last good pass, held back to ``now`` on an earlier clock."""
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (history.KEY_AS_OF,)
    ).fetchone()
    if row is None:
        return None
    try:
        stamp = history.parse_utc(str(row[0]))
    except ValueError:
        return None
    return min(stamp, now)


def etag_of(answer: Timeline) -> str:
    """Return the etag: 16 hex of a sha256 over the answer without T-driven fields.

    The hash leaves out ``server_time``, ``etag`` and ``as_of`` (the end of the last
    pass, which moves every pass and says nothing about this session), the axis end
    and the end of each working run's open segment. The last two are the clock T
    while the session runs, so on a moving clock they differ on every poll without a
    change. A new request, a state change or a new bucket still changes the hash,
    because the rows, the totals, the states and the bucket list change with it.
    """
    body = answer.model_dump(mode="json", exclude={"server_time", "etag", "as_of"})
    body["axis"].pop("end", None)
    for run in body["runs"]:
        if run["state"] == "working" and run["segments"]:
            run["segments"][-1].pop("end", None)
    return _digest(body)


def _digest(body: object) -> str:
    text = json.dumps(body, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:ETAG_HEX]


def digest(body: object) -> str:
    """Return the 16 hex etag of any JSON-ready body."""
    return _digest(body)


def session_state(last: datetime, t: datetime) -> tuple[bool, bool, SessionState]:
    """Return ``(running, active, state)`` for a session last heard from at ``last``."""
    running = last > t - RUNNING_WINDOW
    active = last > t - ACTIVE_WINDOW
    state: SessionState = "working" if active else "idle" if running else "ended"
    return running, active, state


def _session_states(refs: Sequence[_Ref], t: datetime) -> list[StateAt]:
    points = sorted({parse_ts(r.ts) for r in refs})
    marks = _idle_marks(points, t, ended_after=RUNNING_WINDOW)
    return [StateAt(at=at, state=word) for at, word in marks]


def _fetch_rows(
    conn: sqlite3.Connection, session_id: str, low: datetime, t: datetime
) -> list[tuple[Any, ...]]:
    return [
        tuple(r)
        for r in conn.execute(
            _ROWS_SQL, (session_id, ingest.ts_text(low), ingest.ts_text(t))
        )
    ]


@dataclass
class _Sums:
    """Every group the answer needs, filled from cells and open-minute requests."""

    bucket: dict[int, _Acc] = field(default_factory=dict[int, _Acc])
    bucket_models: dict[int, dict[str, int]] = field(
        default_factory=dict[int, dict[str, int]]
    )
    run_bucket: dict[tuple[str, int], _Acc] = field(
        default_factory=dict[tuple[str, int], _Acc]
    )
    run: dict[str, _Acc] = field(default_factory=dict[str, _Acc])
    pairs: dict[str, dict[tuple[str, str | None], int]] = field(
        default_factory=dict[str, dict[tuple[str, str | None], int]]
    )
    total: _Acc = field(default_factory=_Acc)

    def add(  # noqa: PLR0913, PLR0917 - one cell or request with its place
        self,
        index: int,
        run: str,
        label: str,
        effort: str | None,
        values: tuple[int, int, int, int, int],
        cost: float | None,
    ) -> None:
        """Add ``(input, output, cache read, cache write, requests)`` to every group."""
        input_, output, cache_read, cache_write, requests = values
        for acc in (
            self.bucket.setdefault(index, _Acc()),
            self.run_bucket.setdefault((run, index), _Acc()),
            self.run.setdefault(run, _Acc()),
            self.total,
        ):
            acc.add(label, input_, output, cache_read, cache_write, requests, cost)
        fresh = input_ + output + cache_write
        if fresh > 0:
            slot = self.bucket_models.setdefault(index, {})
            slot[label] = slot.get(label, 0) + fresh
        pair = self.pairs.setdefault(run, {})
        key = (label, effort)
        pair[key] = pair.get(key, 0) + requests


def _best_pair(
    pairs: Mapping[tuple[str, str | None], int],
) -> list[tuple[str, str | None]]:
    """Return the (model, effort) pairs with the most requests, first seen first."""
    top = max(pairs.values(), default=0)
    return [pair for pair, n in pairs.items() if n == top and n > 0]


def _first_seen(  # noqa: PLR0913, PLR0917 - one run's tie, with what the query needs
    conn: sqlite3.Connection,
    session_id: str,
    run: str,
    t: datetime,
    tied: Sequence[tuple[str, str | None]],
    pricer: usage_query.Pricer,
) -> tuple[str, str | None]:
    """Return the tied pair whose first request came first.

    A cell holds a whole minute, so a tie inside one minute needs the rows.
    """
    for row in conn.execute(
        _RUN_SQL.format(best=BEST_SQL), (session_id, run, ingest.ts_text(t))
    ):
        pair = (pricer.label(str(row[0]))[0], row[1] or None)
        if pair in tied:
            return pair
    return tied[0]


def _five(values: Sequence[Any]) -> tuple[int, int, int, int, int]:
    """Read five token columns as ints."""
    a, b, c, d, e = (int(v) for v in values)
    return a, b, c, d, e


def _cell(  # noqa: PLR0913, PLR0917 - the columns of a cell
    model: object,
    speed: object,
    tier_name: object,
    geo: object,
    tokens: tuple[int, int, int, int, int],
    requests: int,
) -> usage_query.Cell:
    """Build the priced-record view of a cell or one request."""
    return usage_query.Cell(
        str(model),
        speed or None,  # pyright: ignore[reportArgumentType]
        tier_name or None,  # pyright: ignore[reportArgumentType]
        geo or None,  # pyright: ignore[reportArgumentType]
        *tokens,
        0,
        requests,
    )


def _request_cost(pricer: usage_query.Pricer, cell: usage_query.Cell) -> float | None:
    parts = price_parts(cell, pricer.doc, pricer.catalog)
    return None if parts is None else sum(parts.values())


@dataclass(frozen=True)
class _Grid:
    """The bucket grid: where the axis starts, how wide a bucket is and how many."""

    start: datetime
    step: timedelta
    count: int
    end: datetime

    @property
    def seconds(self) -> int:
        """The bucket width in seconds."""
        return int(self.step.total_seconds())

    def index_of(self, moment: datetime) -> int:
        """Return the bucket that holds a moment."""
        return int((moment - self.start) // self.step)


def _grid(first: datetime, last: datetime, t: datetime, *, running: bool) -> _Grid:
    start = first.replace(second=0, microsecond=0)
    anchor = t if running else last
    step = timedelta(seconds=choose_bucket_seconds(anchor - start))
    count = int((anchor - start) // step) + 1
    return _Grid(start, step, count, t if running else start + count * step)


def _gather(
    conn: sqlite3.Connection,
    session_id: str,
    t: datetime,
    pricer: usage_query.Pricer,
    grid: _Grid,
) -> tuple[_Sums, _Acc]:
    """Sum the whole minutes from cells and the open minute from request rows.

    Returns the sums for every group and the rolling 60 seconds before ``t``.
    """
    sums = _Sums()
    minute_cache: dict[str, int] = {}

    def index_of(minute: str) -> int:
        found = minute_cache.get(minute)
        if found is None:
            moment = datetime.fromisoformat(minute).replace(tzinfo=UTC)
            found = minute_cache[minute] = grid.index_of(moment)
        return found

    t_minute = t.replace(second=0, microsecond=0)
    for cell in conn.execute(
        _CELLS_SQL, (session_id, t_minute.strftime("%Y-%m-%dT%H:%M"))
    ):
        run_key, minute, model, effort, speed, tier_name, geo, tier = cell[:8]
        tokens = _five(cell[8:13])
        requests = int(cell[13])
        label, _known = pricer.label(str(model))
        cost = pricer.cost(
            _cell(model, speed, tier_name, geo, tokens, requests), int(tier or 0)
        )
        sums.add(
            index_of(str(minute)),
            str(run_key),
            label,
            effort or None,
            (tokens[0], tokens[1], tokens[2], tokens[3] + tokens[4], requests),
            cost,
        )
    window = _Acc()
    window_after = t - ACTIVE_WINDOW
    for row in _fetch_rows(conn, session_id, min(t_minute, window_after), t):
        ts_text, run_key, model, effort, speed, tier_name, geo = row[:7]
        tokens = _five(row[7:12])
        label, _known = pricer.label(str(model))
        cost = _request_cost(pricer, _cell(model, speed, tier_name, geo, tokens, 1))
        values = (tokens[0], tokens[1], tokens[2], tokens[3] + tokens[4], 1)
        at = parse_ts(str(ts_text))
        if at >= t_minute:
            sums.add(
                index_of(str(ts_text)[:16]),
                str(run_key),
                label,
                effort or None,
                values,
                cost,
            )
        if at > window_after:
            window.add(label, *values, cost)
    return sums, window


def _bucket_answers(
    sums: _Sums, grid: _Grid, order: Mapping[str, int]
) -> tuple[list[TimelineBucket], list[ModelTokens], list[int]]:
    """Return the bars, the legend and the token ticks."""
    buckets: list[TimelineBucket] = []
    top = 0
    legend: dict[str, int] = defaultdict(int)
    for i in range(grid.count):
        acc = sums.bucket.get(i, _Acc())
        by_model = dict(sums.bucket_models.get(i, {}))
        top = max(top, sum(by_model.values()))
        for model, tokens in by_model.items():
            legend[model] += tokens
        buckets.append(
            TimelineBucket(
                start=grid.start + i * grid.step,
                by_model=by_model,
                cache_read=acc.cache_read,
                cost=acc.priced_cost(),
                requests=acc.requests,
                unpriced=_unpriced(acc, order),
            )
        )
    key = _model_key(order)
    models = [
        ModelTokens(model=m, tokens=n)
        for m, n in sorted(legend.items(), key=lambda kv: key(kv[0]))
        if n > 0
    ]
    return buckets, models, usage.token_ticks(top)[1]


def _run_answer(  # noqa: PLR0913, PLR0917 - one run's inputs
    conn: sqlite3.Connection,
    session_id: str,
    run: _Run,
    sums: _Sums,
    grid: _Grid,
    t: datetime,
    order: Mapping[str, int],
    pricer: usage_query.Pricer,
) -> TimelineRun:
    acc = sums.run.get(run.key, _Acc())
    tied = _best_pair(sums.pairs.get(run.key, {}))
    if len(tied) > 1:
        model, effort = _first_seen(conn, session_id, run.key, t, tied, pricer)
    else:
        model, effort = tied[0] if tied else (None, None)
    segments = [Segment(start=r.at, end=r.last) for r in run.rounds]
    if run.state == "working":
        segments[-1] = Segment(start=segments[-1].start, end=t)
    running_total = _Acc()
    cum: list[Cum] = []
    for i in range(grid.count):
        running_total = running_total.merged(sums.run_bucket.get((run.key, i), _Acc()))
        cum.append(
            Cum(
                tokens=running_total.new_tokens,
                cache_read=running_total.cache_read,
                cost=running_total.priced_cost(),
            )
        )
    parent = (
        None
        if run.key == MAIN
        else MAIN
        if run.parent_key == MAIN
        else run_id_of(run.parent_key or MAIN)
    )
    return TimelineRun(
        run_id=run.run_id,
        agent=None if run.key == MAIN else run.agent_type or UNNAMED,
        label_n=run.label_n,
        parent=parent,
        parent_known=run.known or run.key == MAIN,
        parent_state=parent_state(run, t),
        parent_at=run.linked_at,
        depth=run.depth,
        dispatch_order=run.order,
        together=run.together,
        model=model,
        effort=effort,
        first_request=run.first,
        last_request=run.last,
        state=run.state,
        states=_run_states(run, t),
        rounds=[
            Round(n=n + 1, at=r.at, last_request=r.last, by=r.by, by_kind=r.by_kind)
            for n, r in enumerate(run.rounds)
        ],
        segments=segments,
        tokens=acc.new_tokens,
        cost=acc.priced_cost(),
        unpriced=_unpriced(acc, order),
        cum=cum,
    )


def _latest(
    conn: sqlite3.Connection,
    data: SessionData,
    pricer: usage_query.Pricer,
) -> list[LatestRequest]:
    """Return the newest requests, newest first."""
    latest: list[LatestRequest] = []
    for ref in reversed(data.refs[-LATEST:]):
        row = conn.execute(
            "SELECT model, effort, speed, service_tier, inference_geo, input, output,"
            " cache_read, cache_write_5m, cache_write_1h FROM requests"
            " WHERE file_id = ? AND key = ?",
            (ref.file_id, ref.key),
        ).fetchone()
        model, effort, speed, tier_name, geo = row[:5]
        tokens = _five(row[5:10])
        input_, output, cache_read, cw5, cw1 = tokens
        label, _known = pricer.label(str(model))
        cost = _request_cost(pricer, _cell(model, speed, tier_name, geo, tokens, 1))
        at = parse_ts(ref.ts)
        latest.append(
            LatestRequest(
                id=request_id(ref.key, at, data.session_id, ref.run),
                at=at,
                run_id=run_id_of(ref.run),
                model=label,
                effort=effort or None,
                tokens=input_ + output + cache_read + cw5 + cw1,
                new_tokens=input_ + output + cw5 + cw1,
                cache_read=cache_read,
                output=output,
                cost=cost,
            )
        )
    return latest


def build_timeline(  # noqa: PLR0913 - the whole answer, keyword-only inputs
    conn: sqlite3.Connection,
    *,
    session_id: str,
    project_key: str,
    folder_keys: Mapping[str, str],
    now: datetime,
    pricer: usage_query.Pricer,
    catalog: model_catalog.Catalog,
    model_check_fn: ModelCheckFn,
    prices: PricesFn,
) -> Timeline | None:
    """Build the timeline of one session at clock ``now``, or None for an unknown one.

    Args:
        conn: A read connection to the store.
        session_id: The session to describe.
        project_key: The project the caller asked in. A session whose folder maps to
            another project, or to none, reads as unknown.
        folder_keys: The project key of each transcript folder, from the provider.
        now: The clock T, aware. Requests after it are ignored.
        pricer: Prices cells (``usage_query.Pricer``) and single requests.
        catalog: The model catalog, for the legend order.
        model_check_fn: Builds the answer's ``model_check`` from the project key and
            the runs.
        prices: Returns the price facts for the cost label.

    Returns:
        The full answer. The caller compares its ``etag`` with the one it was sent.
    """
    t = _utc(now)
    data = load_session(
        conn, session_id, t, project_key=project_key, folder_keys=folder_keys
    )
    if data is None:
        return None
    order = _order_of(catalog)
    first, last = data.first, data.last
    running, active, state = session_state(last, t)
    grid = _grid(first, last, t, running=running)
    sums, window = _gather(conn, session_id, t, pricer, grid)
    buckets, models, token_ticks = _bucket_answers(sums, grid, order)
    out_runs = [
        _run_answer(conn, session_id, r, sums, grid, t, order, pricer)
        for r in analyze_runs(data, t)
    ]
    total = sums.total
    answer = Timeline(
        project=project_key,
        server_time=t,
        as_of=as_of(conn, t),
        etag="",
        unchanged=False,
        session=TimelineSession(
            id=session_id,
            project=project_key,
            branch=data.branch,
            started=first,
            last_request=last,
            running=running,
            active=active,
            state=state,
            states=_session_states(data.refs, t),
            ended_at=None if running else last,
            requests=len(data.refs),
            unpriced=_unpriced(total, order),
        ),
        axis=TimelineAxis(
            start=grid.start,
            end=grid.end,
            bucket_seconds=grid.seconds,
            ticks=_ticks(grid.start, grid.end, grid.seconds),
            token_ticks=token_ticks,
        ),
        buckets=buckets,
        models=models,
        last_minute=_window(window, order) if running else None,
        totals=TimelineTotals(
            tokens=total.new_tokens,
            input=total.input,
            output=total.output,
            cache_read=total.cache_read,
            cache_write=total.cache_write,
            cost=total.priced_cost(),
            hit_rate=total.hit_rate(),
            requests=total.requests,
            runs=len(out_runs),
            runs_working=sum(1 for r in out_runs if r.state == "working"),
            runs_finished=sum(1 for r in out_runs if r.state == "finished"),
            unpriced=_unpriced(total, order),
        ),
        runs=out_runs,
        requests=_latest(conn, data, pricer),
        model_check=model_check_fn(project_key, out_runs),
        prices=prices(),
    )
    return answer.model_copy(update={"etag": etag_of(answer)})


def empty_model_check(_project_key: str, _runs: Sequence[TimelineRun]) -> ModelCheck:
    """Return a model check with no rows, for tests and callers with no resolver."""
    return ModelCheck(rows=[], in_effect_count=0)


def bundled_prices(as_of: date) -> PricesFn:
    """Return a ``prices`` callable that reports the bundled table as of ``as_of``."""

    def facts() -> TimelinePrices:
        return TimelinePrices(
            as_of=as_of, source="bundled", cross_check_state="not_checked"
        )

    return facts
