"""Review sums over ``minute_usage``: totals, agents, models, bars and sessions.

``scan`` reads the store's per-minute cells for a set of transcript folders and a
window once, prices them, and returns every number a Review card needs. It follows
``usage_query`` for the window (whole minutes, see ``usage_query.minute_bounds``),
for the agent and model names, and for pricing (per cell, at the cell's stored tier).
The old ``dashboard/usage.py`` is the oracle, and ``test_differential_review.py``
checks every rule below against its recorded answers.

Rules taken from the old app

* Runs. A run is any agent run, ``(session, run id)`` of a cell, the main session
  included (its run key is ``main``, so it counts once per session). This is the one
  meaning of "Runs" on every page. The old ``Agg.runs`` skipped main, so ``@main`` had
  0 there, and ``test_differential_review.py`` pins the difference.
* Sessions. Distinct sessions with a cell in the window.
* Hit rate. Cache reads over cache reads, both cache writes and input, or None when
  that is 0 (``usage.py _Acc.finish``).
* Cost. The sum over priced requests, split by kind. ``cost`` is None when the group
  has requests and none is priced. A request with no price counts in ``unpriced``
  with its model.
* Share. A group's cost over the total cost, None when either is None or the total is
  0. The old app showed whole percents (largest remainder). The fraction is exact.
* Ran with (``usage.py _agent_rows``). Each run counts once, under the (model, effort)
  pair with the most requests in the run, ties to the pair first seen. ``ran_pairs``
  lists those pairs with their run counts, most runs first, ties to the first seen.
  For ``@main`` a run is the session. ``ran`` is the first pair and ``mixed`` is True
  when there is more than one. A tie inside one minute goes to the pair that sorts
  first by model, because a cell holds the whole minute.
* Sessions (``usage.py _session_rows``). Agents are ordered by cost, then tokens, then
  key. They include ``@main`` when the main session had a request in the window.

Rules that are new

* A session row counts the window only. A session that started before the window
  also carries its whole numbers. It is sorted newest first by its first minute in
  the window and its id, grouped under that minute's local day, and paged by a cursor
  that holds the last row's sort key, so a refetch never moves loaded rows.
* ``no_usage_sessions`` counts sessions whose first and last request span the window
  and that have no cell in it. The store writes a session row only from requests that
  have usage, so a session made only of rows without usage is not in the store and
  cannot be counted. This count is 0 unless a request's cell went to another session.

A bar is one slot of ``review_windows.chart_window``. Cells go to the bar whose start
is the latest at or before the cell's minute.

Reading the hourly rollup. ``scan`` reads ``hour_usage`` (the rollup the single writer
keeps beside ``minute_usage``) for every UTC hour that lies wholly inside the window,
one bar and one local day, and ``minute_usage`` for the rest. A cut is a window edge,
a bar start or a local midnight. An hour that holds a cut at a minute other than its
first (the open hour at T, or a day or bar edge in a zone with a half-hour or 45
minute offset) is read minute by minute, clipped to the window. Every other hour has
all its minutes on the same side of every cut, so its sums land in the same bar and
day as its cells would. The answer equals the minute-only scan (``rollup=False``) in
every count, name and first minute. Costs are the same sums added in another order,
so they may differ in the last bits of a float.
"""

import base64
import binascii
import json
import sqlite3
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import ingest
import timeline
import usage_query
from models import SessionState
from prices import PricesDoc
from review_windows import Bar, wall

MAIN_RUN = "main"
SESSION_PAGE = 50
MINUTE = "%Y-%m-%dT%H:%M"
_MILLION = 1_000_000
_CHUNK = 500
# Both row queries return the same 18 columns. The third is the cell's minute (or the
# hour's first minute) and the last is the earliest minute the row holds.
_ROWS = (
    "SELECT mu.session_id, mu.run_key, mu.minute, mu.model, mu.effort, mu.speed,"
    " mu.service_tier, mu.inference_geo, mu.tier, mu.input, mu.output, mu.cache_read,"
    " mu.cache_write_5m, mu.cache_write_1h, mu.thinking, mu.requests, r.agent_type,"
    " mu.minute"
    " FROM minute_usage mu"
    " JOIN sessions s ON s.session_id = mu.session_id"
    " LEFT JOIN runs r ON r.session_id = mu.session_id AND r.run_id = mu.run_key"
    " WHERE {where}"
)
_HOUR_ROWS = (
    "SELECT mu.session_id, mu.run_key, mu.hour, mu.model, mu.effort, mu.speed,"
    " mu.service_tier, mu.inference_geo, mu.tier, mu.input, mu.output, mu.cache_read,"
    " mu.cache_write_5m, mu.cache_write_1h, mu.thinking, mu.requests, r.agent_type,"
    " mu.first_minute"
    " FROM hour_usage mu"
    " JOIN sessions s ON s.session_id = mu.session_id"
    " LEFT JOIN runs r ON r.session_id = mu.session_id AND r.run_id = mu.run_key"
    " WHERE {where}"
)
_MINUTES = "mu.minute >= ? AND mu.minute < ?"
_HOURS = "mu.hour >= ? AND mu.hour < ?"
_HOUR = timedelta(hours=1)

# Per-token USD rates: input, output, cache read, cache write 5m, cache write 1h.
_Rates = tuple[float, float, float, float, float]
_Key = tuple[str, str, str, str | None, int, date | None]


@dataclass(frozen=True)
class Kinds:
    """Dollars per kind of cost, over priced requests only."""

    input: float = 0.0
    output: float = 0.0
    cache_read: float = 0.0
    cache_write: float = 0.0


@dataclass(frozen=True)
class Unpriced:
    """Requests with no price, and the models they ran on, in catalog order."""

    requests: int = 0
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sums:
    """Token, request and cost sums of one group.

    ``cost`` counts priced requests only, and is None when the group has requests and
    none of them is priced.
    """

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    thinking: int = 0
    requests: int = 0
    runs: int = 0
    sessions: int = 0
    cost: float | None = 0.0
    cost_by_kind: Kinds = Kinds()
    unpriced: Unpriced = Unpriced()

    @property
    def cache_write(self) -> int:
        """Both cache write counts."""
        return self.cache_write_5m + self.cache_write_1h

    @property
    def tokens(self) -> int:
        """Input, output, cache read and both cache writes, as the old views count."""
        return self.input + self.output + self.cache_read + self.cache_write

    @property
    def hit_rate(self) -> float | None:
        """Cache reads over reads, writes and input, or None when that is 0."""
        denom = self.cache_read + self.cache_write + self.input
        return self.cache_read / denom if denom else None


@dataclass(frozen=True)
class PairRuns:
    """A (model, effort) pair and the runs that used it most."""

    model: str
    effort: str | None
    runs: int


@dataclass(frozen=True)
class AgentSums:
    """One agent key's sums, share of cost and what its runs used.

    ``ran`` is the pair most runs used (None when nothing ran), ``ran_pairs`` lists
    every pair, most runs first, and ``mixed`` is True with more than one pair.
    ``model`` is the model with the most requests, ties in catalog order.
    """

    sums: Sums
    share: float | None
    ran_pairs: tuple[PairRuns, ...]
    ran: PairRuns | None
    mixed: bool
    model: str | None = None


@dataclass(frozen=True)
class ModelSums:
    """One model's sums, the agents that used it (biggest cost first) and its share."""

    sums: Sums
    agents: tuple[str, ...]
    share: float | None


@dataclass(frozen=True)
class ModelBar:
    """One model's part of a chart bar. ``cost`` is None when none of it is priced."""

    cost: float | None
    kinds: Kinds
    requests: int
    tokens: int
    unpriced: Unpriced


@dataclass(frozen=True)
class BarSums:
    """What one chart bar holds, per model, and its unpriced requests."""

    models: dict[str, ModelBar]
    unpriced: Unpriced


@dataclass(frozen=True)
class WholeSession:
    """A session's numbers over its whole life."""

    tokens: int
    cost: float | None
    unpriced: Unpriced


@dataclass(frozen=True)
class SessionRow:
    """One session in the window.

    ``started`` is the first request ever and ``last_request`` the last. The counts
    cover the window only. ``first_in_window`` is the first cell's minute in the
    window, which sorts and groups the row. ``whole`` is set when the session started
    before the window.
    """

    id: str
    started: datetime
    last_request: datetime
    first_in_window: datetime
    branch: str | None
    state: SessionState
    agents: tuple[str, ...]
    runs: int
    tokens: int
    cost: float | None
    unpriced: Unpriced
    started_before_range: bool
    whole: WholeSession | None

    @property
    def sort_key(self) -> tuple[str, str]:
        """The (first minute in the window, id) key the list sorts and pages by."""
        return self.first_in_window.strftime(MINUTE), self.id


@dataclass(frozen=True)
class Scan:
    """The answer of ``scan``.

    Attributes:
        total: Sums over the window.
        by_agent: Per agent key, biggest cost first.
        by_model: Per model label, biggest cost first.
        by_day: Per local date. Empty unless ``days`` was asked for.
        bars: One entry per bar passed in. Empty when no bars were passed.
        sessions: The window's sessions, newest first. Empty unless asked for.
        runs: Per agent key, its runs as ``{run_id, model, effort, requests}`` in the
            order they began (``agent_setup.check_agent`` takes them as they are).
            A main run is the session.
    """

    total: Sums
    by_agent: dict[str, AgentSums]
    by_model: dict[str, ModelSums]
    by_day: dict[date, Sums]
    bars: tuple[BarSums, ...]
    sessions: tuple[SessionRow, ...]
    runs: dict[str, list[dict[str, Any]]] = field(
        default_factory=dict[str, list[dict[str, Any]]]
    )


class _Entry:
    """Sums of the cells that share one base key."""

    __slots__ = (
        "cache_read",
        "cw1",
        "cw5",
        "first",
        "input",
        "k_cr",
        "k_cw",
        "k_in",
        "k_out",
        "output",
        "requests",
        "thinking",
        "unpriced",
    )

    def __init__(self, first: str) -> None:
        self.first = first
        self.input = self.output = self.cache_read = self.cw5 = self.cw1 = 0
        self.thinking = self.requests = self.unpriced = 0
        self.k_in = self.k_out = self.k_cr = self.k_cw = 0.0


class _Acc:
    """A running sum for one group, built from entries."""

    __slots__ = (
        "cache_read",
        "cw1",
        "cw5",
        "input",
        "k_cr",
        "k_cw",
        "k_in",
        "k_out",
        "models",
        "output",
        "requests",
        "runs",
        "sessions",
        "thinking",
        "unpriced",
    )

    def __init__(self) -> None:
        self.input = self.output = self.cache_read = self.cw5 = self.cw1 = 0
        self.thinking = self.requests = self.unpriced = 0
        self.k_in = self.k_out = self.k_cr = self.k_cw = 0.0
        self.models: set[str] = set()
        self.runs: set[tuple[str, str]] = set()
        self.sessions: set[str] = set()

    def add(self, entry: _Entry, sid: str, run: str, label: str) -> None:
        self.input += entry.input
        self.output += entry.output
        self.cache_read += entry.cache_read
        self.cw5 += entry.cw5
        self.cw1 += entry.cw1
        self.thinking += entry.thinking
        self.requests += entry.requests
        self.k_in += entry.k_in
        self.k_out += entry.k_out
        self.k_cr += entry.k_cr
        self.k_cw += entry.k_cw
        if entry.unpriced:
            self.unpriced += entry.unpriced
            self.models.add(label)
        self.sessions.add(sid)
        self.runs.add((sid, run))

    def merge(self, other: "_Acc") -> None:
        """Add another group's sums, runs, sessions and unpriced models to this one."""
        self.input += other.input
        self.output += other.output
        self.cache_read += other.cache_read
        self.cw5 += other.cw5
        self.cw1 += other.cw1
        self.thinking += other.thinking
        self.requests += other.requests
        self.k_in += other.k_in
        self.k_out += other.k_out
        self.k_cr += other.k_cr
        self.k_cw += other.k_cw
        self.unpriced += other.unpriced
        self.models |= other.models
        self.runs |= other.runs
        self.sessions |= other.sessions

    @property
    def tokens(self) -> int:
        return self.input + self.output + self.cache_read + self.cw5 + self.cw1

    @property
    def cost(self) -> float | None:
        if self.requests > 0 and self.unpriced == self.requests:
            return None
        return self.k_in + self.k_out + self.k_cr + self.k_cw

    @property
    def kinds(self) -> Kinds:
        return Kinds(self.k_in, self.k_out, self.k_cr, self.k_cw)

    def unpriced_of(self, order: Callable[[str], tuple[int, str]]) -> Unpriced:
        return Unpriced(self.unpriced, tuple(sorted(self.models, key=order)))

    def sums(self, order: Callable[[str], tuple[int, str]]) -> Sums:
        return Sums(
            input=self.input,
            output=self.output,
            cache_read=self.cache_read,
            cache_write_5m=self.cw5,
            cache_write_1h=self.cw1,
            thinking=self.thinking,
            requests=self.requests,
            runs=len(self.runs),
            sessions=len(self.sessions),
            cost=self.cost,
            cost_by_kind=self.kinds,
            unpriced=self.unpriced_of(order),
        )


def _merged(accs: Iterable[_Acc]) -> _Acc:
    """Return one group that holds the sums of all of ``accs``."""
    whole = _Acc()
    for acc in accs:
        whole.merge(acc)
    return whole


def _order_key(catalog_order: Mapping[str, int]) -> Callable[[str], tuple[int, str]]:
    """Sort models in catalog order, then the rest by name."""

    def key(model: str) -> tuple[int, str]:
        return catalog_order.get(model, len(catalog_order)), model

    return key


def _by_cost(acc: _Acc, key: str) -> tuple[float, int, str]:
    """The old agent order (``usage.py _order_key``): cost, then tokens, then key."""
    return -(acc.cost or 0.0), -acc.tokens, key


def _agent_key(run: str, agent_type: object) -> str:
    if run == MAIN_RUN:
        return usage_query.MAIN_AGENT
    return str(agent_type) if agent_type else usage_query.UNNAMED_AGENT


def _share(cost: float | None, total: float | None) -> float | None:
    if cost is None or total is None or total <= 0:
        return None
    return cost / total


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _minute(text: str) -> datetime:
    """Return the UTC instant of a ``MINUTE`` text (``2026-11-01T12:00``)."""
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class _Reader:
    """Reads cells and folds them into entries, pricing each cell once per key."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        price_doc: PricesDoc,
        zone: ZoneInfo,
        *,
        bar_starts: Sequence[str] = (),
        days: bool = False,
    ) -> None:
        self.conn = conn
        self.pricer = usage_query.Pricer(price_doc)
        self.zone = zone
        self.bar_starts = list(bar_starts)
        self.days = days
        # Whether whole-life reads may use hour rows. ``scan`` sets it.
        self.rollup = True
        self.order = _order_key(
            {str(m["id"]): i for i, m in enumerate(self.pricer.catalog)}
        )
        self.priced: dict[tuple[str, ...], tuple[str, _Rates | None]] = {}
        self.agent_of: dict[tuple[str, str], str] = {}
        self.entries: dict[_Key, _Entry] = {}

    def _price(
        self, raw: str, speed: str, tier_name: str, geo: str, tier: str
    ) -> tuple[str, _Rates | None]:
        label = self.pricer.label(raw)[0]
        found: list[float] = []
        for slot in range(5):
            count = [_MILLION if i == slot else 0 for i in range(5)]
            cell = usage_query.Cell(
                model_raw=raw,
                speed=speed or None,
                service_tier=tier_name or None,
                inference_geo=geo or None,
                input=count[0],
                output=count[1],
                cache_read=count[2],
                cache_write_5m=count[3],
                cache_write_1h=count[4],
                thinking=0,
                requests=0,
            )
            parts = self.pricer.parts(cell, int(tier or 0))
            if parts is None:
                return label, None
            kind = ("input", "output", "cache_read", "cache_write", "cache_write")[slot]
            found.append(parts[kind] / _MILLION)
        return label, (found[0], found[1], found[2], found[3], found[4])

    def fold(
        self,
        sql: str,
        args: Sequence[object],
        skip: frozenset[str] = frozenset(),
    ) -> None:
        """Read rows of ``_ROWS`` or ``_HOUR_ROWS`` and add them to ``entries``.

        A row whose time (its third column) is in ``skip`` is left out.
        """
        zone = self.zone
        starts = self.bar_starts
        bar_of: dict[str, int] = {}
        day_of: dict[str, date] = {}
        priced = self.priced
        entries = self.entries
        agent_of = self.agent_of
        for row in self.conn.execute(sql, args):
            (sid, run, minute, raw, effort, speed, tier_name, geo, tier) = row[:9]
            (inp, out, cache_read, w5, w1, thinking, requests, agent_type, first) = row[
                9:
            ]
            if skip and minute in skip:
                continue
            price_key = (raw, speed, tier_name, geo, tier)
            found = priced.get(price_key)
            if found is None:
                found = priced[price_key] = self._price(*price_key)
            label, rates = found
            bar = -1
            if starts:
                bar = bar_of.get(minute, -1)
                if bar < 0:
                    bar = bar_of[minute] = max(bisect_right(starts, minute) - 1, 0)
            day = None
            if self.days:
                day = day_of.get(minute)
                if day is None:
                    day = day_of[minute] = _minute(minute).astimezone(zone).date()
            key = (sid, run, label, effort or None, bar, day)
            entry = entries.get(key)
            if entry is None:
                entry = entries[key] = _Entry(first)
                if (sid, run) not in agent_of:
                    agent_of[sid, run] = _agent_key(run, agent_type)
            elif first < entry.first:
                entry.first = first
            entry.input += inp
            entry.output += out
            entry.cache_read += cache_read
            entry.cw5 += w5
            entry.cw1 += w1
            entry.thinking += thinking
            entry.requests += requests
            if rates is None:
                entry.unpriced += requests
            else:
                entry.k_in += inp * rates[0]
                entry.k_out += out * rates[1]
                entry.k_cr += cache_read * rates[2]
                entry.k_cw += w5 * rates[3] + w1 * rates[4]


def _folders_clause(folders: frozenset[str]) -> tuple[str, list[str]]:
    ordered = sorted(folders)
    return f" AND s.folder IN ({','.join('?' * len(ordered))})", ordered


def _hour_end(hour: str) -> str:
    """Return the minute text of the next UTC hour after ``hour`` (``...T10:00``)."""
    return (_minute(hour) + _HOUR).strftime(MINUTE)


def _hour_ceiling(text: str) -> str:
    """Return the first whole UTC hour at or after a minute text."""
    floor = text[:13] + ":00"
    return floor if text == floor else _hour_end(floor)


def _cuts(
    low: str, high: str, zone: ZoneInfo, bar_starts: Sequence[str], *, days: bool
) -> list[str]:
    """Return the minute texts that cut the window: bar starts and local midnights."""
    cuts = list(bar_starts)
    if days:
        day = _minute(low).astimezone(zone).date()
        last = _minute(high).astimezone(zone).date()
        while day <= last:
            cuts.append(wall(zone, day).strftime(MINUTE))
            day += timedelta(days=1)
    return cuts


def _read_cells(  # noqa: PLR0913 - the window, its cuts and the folder filter
    reader: _Reader,
    low: str,
    high: str,
    cuts: Sequence[str],
    folder_where: tuple[str, list[str]],
    *,
    rollup: bool,
) -> None:
    """Fold the cells of ``[low, high)`` into the reader, from hours where exact.

    Hour rows stand in for the hours that lie wholly inside the window with no cut
    inside them (see the module docstring). Every other minute is read from
    ``minute_usage``. With ``rollup`` False every minute is.
    """
    extra, names = folder_where
    if not rollup:
        reader.fold(_ROWS.format(where=_MINUTES + extra), [low, high, *names])
        return
    partial = {t[:13] + ":00" for t in (low, high, *cuts) if t[14:] != "00"}
    first_hour, last_hour = _hour_ceiling(low), high[:13] + ":00"
    if first_hour < last_hour:
        reader.fold(
            _HOUR_ROWS.format(where=_HOURS + extra),
            [first_hour, last_hour, *names],
            skip=frozenset(partial),
        )
    for hour in sorted(partial):
        begin, end = max(hour, low), min(_hour_end(hour), high)
        if begin < end:
            reader.fold(_ROWS.format(where=_MINUTES + extra), [begin, end, *names])


def _run_reps(reader: _Reader) -> list[tuple[str, str, str, str, str, int]]:
    """Return one ``(began, session, run, model, effort, requests)`` per run.

    A run's model and effort are its (model, effort) pair with the most requests, ties
    to the pair seen first. The runs come in the order they began. ``requests`` is the
    run's total. For ``@main`` a run is the session.
    """
    runs: dict[tuple[str, str], dict[tuple[str, str], list[Any]]] = {}
    for (sid, run, label, effort, _bar, _day), entry in reader.entries.items():
        pairs = runs.setdefault((sid, run), {})
        slot = pairs.get((label, effort or ""))
        if slot is None:
            pairs[label, effort or ""] = [entry.requests, entry.first]
        else:
            slot[0] += entry.requests
            slot[1] = min(slot[1], entry.first)
    reps: list[tuple[str, str, str, str, str, int]] = []
    for (sid, run), pairs in runs.items():
        label, effort = min(
            pairs,
            key=lambda pair, pairs=pairs: (-pairs[pair][0], pairs[pair][1], pair),
        )
        began = min(slot[1] for slot in pairs.values())
        reps.append((began, sid, run, label, effort, sum(s[0] for s in pairs.values())))
    reps.sort()
    return reps


def _agent_runs(
    reader: _Reader, reps: Sequence[tuple[str, str, str, str, str, int]]
) -> dict[str, list[dict[str, Any]]]:
    """Return each agent key's runs as ``agent_setup.check_agent`` takes them.

    One ``{run_id, model, effort, requests}`` per run, in the order the runs began. A
    main run is the session, so its ``run_id`` is the session id.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for _began, sid, run, label, effort, requests in reps:
        out.setdefault(reader.agent_of[sid, run], []).append(
            {
                "run_id": sid if run == MAIN_RUN else run,
                "model": label,
                "effort": effort or None,
                "requests": requests,
            }
        )
    return out


def _ran_pairs(
    reader: _Reader, reps: Sequence[tuple[str, str, str, str, str, int]]
) -> dict[str, list[PairRuns]]:
    """Return each agent key's pairs, most runs first, ties to the first seen."""
    counts: dict[str, dict[tuple[str, str], int]] = {}
    for _began, sid, run, label, effort, _requests in reps:
        agent = counts.setdefault(reader.agent_of[sid, run], {})
        agent[label, effort] = agent.get((label, effort), 0) + 1
    return {
        agent: sorted(
            (
                PairRuns(label, effort or None, n)
                for (label, effort), n in pairs.items()
            ),
            key=lambda pair: -pair.runs,
        )
        for agent, pairs in counts.items()
    }


def _session_rows(  # noqa: PLR0913 - the pass's groups, keyword-only
    reader: _Reader,
    *,
    low: str,
    now: datetime,
    by_session: Mapping[str, _Acc],
    by_session_agent: Mapping[tuple[str, str], _Acc],
    first_minute: Mapping[str, str],
) -> tuple[SessionRow, ...]:
    """Build the window's session rows, newest first."""
    ids = sorted(by_session)
    info: dict[str, tuple[str, str, str | None]] = {}
    for at in range(0, len(ids), _CHUNK):
        chunk = ids[at : at + _CHUNK]
        marks = ",".join("?" * len(chunk))
        for sid, first, last, branch in reader.conn.execute(
            "SELECT session_id, first_ts, last_ts, branch FROM sessions"  # noqa: S608
            f" WHERE session_id IN ({marks})",
            chunk,
        ):
            info[sid] = (first, last, branch)
    before = [sid for sid in ids if info[sid][0][:16] < low]
    whole = _whole_numbers(reader, before)
    agents: dict[str, list[tuple[tuple[float, int, str], str]]] = {}
    for (sid, agent), acc in by_session_agent.items():
        agents.setdefault(sid, []).append((_by_cost(acc, agent), agent))
    rows: list[SessionRow] = []
    for sid in ids:
        first, last, branch = info[sid]
        acc = by_session[sid]
        last_at = _parse(last)
        rows.append(
            SessionRow(
                id=sid,
                started=_parse(first),
                last_request=last_at,
                first_in_window=_minute(first_minute[sid]),
                branch=None if branch is None else str(branch),
                state=timeline.session_state(last_at, now)[2],
                agents=tuple(agent for _key, agent in sorted(agents.get(sid, []))),
                runs=len(acc.runs),
                tokens=acc.tokens,
                cost=acc.cost,
                unpriced=acc.unpriced_of(reader.order),
                started_before_range=sid in whole,
                whole=whole.get(sid),
            )
        )
    rows.sort(key=lambda row: row.sort_key, reverse=True)
    return tuple(rows)


def _whole_numbers(reader: _Reader, ids: Sequence[str]) -> dict[str, WholeSession]:
    """Return each session's numbers over its whole life."""
    out: dict[str, WholeSession] = {}
    for at in range(0, len(ids), _CHUNK):
        chunk = ids[at : at + _CHUNK]
        marks = ",".join("?" * len(chunk))
        sub = _Reader(reader.conn, reader.pricer.doc, reader.zone)
        sub.priced = reader.priced
        # A whole life has no window, bar or day edge, so hour rows are exact.
        rows = _HOUR_ROWS if reader.rollup else _ROWS
        sub.fold(rows.format(where=f"mu.session_id IN ({marks})"), chunk)
        accs: dict[str, _Acc] = {}
        for (sid, run, label, _effort, _bar, _day), entry in sub.entries.items():
            accs.setdefault(sid, _Acc()).add(entry, sid, run, label)
        for sid, acc in accs.items():
            out[sid] = WholeSession(acc.tokens, acc.cost, acc.unpriced_of(reader.order))
    return out


def scan(  # noqa: PLR0913, PLR0915 - the query's own inputs, one pass of groups
    conn: sqlite3.Connection,
    price_doc: PricesDoc,
    *,
    folders: frozenset[str] | None,
    start: datetime,
    end: datetime,
    tz: str,
    now: datetime | None = None,
    bars: Sequence[Bar] = (),
    days: bool = False,
    sessions: bool = False,
    rollup: bool = True,
) -> Scan:
    """Sum ``minute_usage`` for ``folders`` over a window and price it.

    Args:
        conn: A connection to the store. Only reads.
        price_doc: The prices document (``prices.load_prices`` or the live table).
        folders: Transcript folders to include, or None for every folder.
        start: Window start, aware. Floored to its minute.
        end: Window end, aware. See ``usage_query.minute_bounds`` for the edge rule.
        tz: IANA zone name for the days.
        now: T, for a session's state. Defaults to ``end``.
        bars: Chart bars to sum per model, in time order, or none.
        days: Also sum per local date.
        sessions: Also build the session rows. Costs a query for the sessions that
            started before the window.
        rollup: Read ``hour_usage`` for the hours that allow it (see the module
            docstring). False reads ``minute_usage`` only, the reference the tests
            compare the rollup with.

    Returns:
        The sums. A folder set that is empty gives empty sums.
    """
    if folders is not None and not folders:
        return Scan(
            Sums(), {}, {}, {}, tuple(BarSums({}, Unpriced()) for _ in bars), ()
        )
    low, high = usage_query.minute_bounds(start, end)
    folder_where: tuple[str, list[str]] = (
        _folders_clause(folders) if folders is not None else ("", [])
    )
    zone = ZoneInfo(tz)
    bar_starts = [b.start.astimezone(UTC).strftime(MINUTE) for b in bars]
    reader = _Reader(conn, price_doc, zone, bar_starts=bar_starts, days=days)
    reader.rollup = rollup
    cuts = _cuts(low, high, zone, bar_starts, days=days) if rollup else []
    _read_cells(reader, low, high, cuts, folder_where, rollup=rollup)
    order = reader.order
    total = _Acc()
    agents: dict[str, _Acc] = {}
    models: dict[str, _Acc] = {}
    model_agents: dict[str, dict[str, _Acc]] = {}
    day_accs: dict[date, _Acc] = {}
    bar_models: list[dict[str, _Acc]] = [{} for _ in bars]
    by_session: dict[str, _Acc] = {}
    by_session_agent: dict[tuple[str, str], _Acc] = {}
    first_minute: dict[str, str] = {}
    # Each entry is added once, to its (model, agent) group. The totals, agents and
    # models are merged up from those groups, which is far fewer additions.
    cells: dict[tuple[str, str], _Acc] = {}
    agent_of = reader.agent_of
    for (sid, run, label, _effort, bar, day), entry in reader.entries.items():
        agent = agent_of[sid, run]
        pair = (label, agent)
        acc = cells.get(pair)
        if acc is None:
            acc = cells[pair] = _Acc()
        acc.add(entry, sid, run, label)
        if day is not None:
            day_accs.setdefault(day, _Acc()).add(entry, sid, run, label)
        if bar >= 0:
            bar_models[bar].setdefault(label, _Acc()).add(entry, sid, run, label)
        if sessions:
            session_agent = by_session_agent.get((sid, agent))
            if session_agent is None:
                session_agent = by_session_agent[sid, agent] = _Acc()
            session_agent.add(entry, sid, run, label)
            if entry.first < first_minute.get(sid, "~"):
                first_minute[sid] = entry.first
    for (label, agent), acc in cells.items():
        total.merge(acc)
        agents.setdefault(agent, _Acc()).merge(acc)
        models.setdefault(label, _Acc()).merge(acc)
        model_agents.setdefault(label, {})[agent] = acc
    for (sid, _agent), acc in by_session_agent.items():
        by_session.setdefault(sid, _Acc()).merge(acc)
    bar_totals = [_merged(per.values()) for per in bar_models]
    total_cost = total.cost
    reps = _run_reps(reader)
    pairs = _ran_pairs(reader, reps)
    agent_out: dict[str, AgentSums] = {}
    for key in sorted(agents, key=lambda k: _by_cost(agents[k], k)):
        acc = agents[key]
        ran = pairs.get(key, [])
        agent_out[key] = AgentSums(
            sums=acc.sums(order),
            share=_share(acc.cost, total_cost),
            ran_pairs=tuple(ran),
            ran=ran[0] if ran else None,
            mixed=len(ran) > 1,
            model=_top_model(model_agents, key, order),
        )
    model_out: dict[str, ModelSums] = {}
    for label in sorted(models, key=lambda k: _by_cost(models[k], k)):
        acc = models[label]
        used = model_agents[label]
        model_out[label] = ModelSums(
            sums=acc.sums(order),
            agents=tuple(sorted(used, key=lambda a, used=used: _by_cost(used[a], a))),
            share=_share(acc.cost, total_cost),
        )
    bar_out = tuple(
        BarSums(
            models={
                label: ModelBar(
                    acc.cost,
                    acc.kinds,
                    acc.requests,
                    acc.tokens,
                    acc.unpriced_of(order),
                )
                for label, acc in sorted(per.items(), key=lambda kv: order(kv[0]))
            },
            unpriced=whole.unpriced_of(order),
        )
        for per, whole in zip(bar_models, bar_totals, strict=True)
    )
    rows = (
        _session_rows(
            reader,
            low=low,
            now=now or end,
            by_session=by_session,
            by_session_agent=by_session_agent,
            first_minute=first_minute,
        )
        if sessions
        else ()
    )
    return Scan(
        total=total.sums(order),
        by_agent=agent_out,
        by_model=model_out,
        by_day={d: day_accs[d].sums(order) for d in sorted(day_accs)},
        bars=bar_out,
        sessions=rows,
        runs=_agent_runs(reader, reps),
    )


def _top_model(
    model_agents: Mapping[str, Mapping[str, _Acc]],
    agent: str,
    order: Callable[[str], tuple[int, str]],
) -> str | None:
    """Return the model an agent sent the most requests to, ties in catalog order."""
    best: tuple[int, tuple[int, str], str] | None = None
    for label, used in model_agents.items():
        acc = used.get(agent)
        if acc is None:
            continue
        rank = (-acc.requests, order(label), label)
        if best is None or rank < best:
            best = rank
    return None if best is None else best[2]


def oldest_request(
    conn: sqlite3.Connection, folders: frozenset[str] | None
) -> datetime | None:
    """Return the first request ever seen in ``folders`` (None means every folder).

    The time is the earliest ``sessions.first_ts``, which holds a request's own
    timestamp. It is None when nothing is stored for the folders.
    """
    if folders is None:
        row = conn.execute("SELECT MIN(first_ts) FROM sessions").fetchone()
    elif not folders:
        return None
    else:
        marks = ",".join("?" * len(folders))
        row = conn.execute(
            f"SELECT MIN(first_ts) FROM sessions WHERE folder IN ({marks})",  # noqa: S608
            sorted(folders),
        ).fetchone()
    return None if row is None or row[0] is None else _parse(row[0])


def no_usage_sessions(
    conn: sqlite3.Connection,
    folders: frozenset[str] | None,
    start: datetime,
    end: datetime,
) -> int:
    """Count sessions that span the window but have no ``minute_usage`` cell in it.

    A session spans the window when its first request is at or before ``end`` and its
    last is at or after ``start``. See the module docstring for what this can see.
    """
    if folders is not None and not folders:
        return 0
    low, high = usage_query.minute_bounds(start, end)
    sql = (
        "SELECT COUNT(*) FROM sessions s WHERE s.first_ts <= ? AND s.last_ts >= ?"  # noqa: S608
        " AND NOT EXISTS (SELECT 1 FROM minute_usage mu"
        f" WHERE mu.session_id = s.session_id AND {_MINUTES})"
    )
    args: list[object] = [
        ingest.ts_text(end),
        ingest.ts_text(start),
        low,
        high,
    ]
    if folders is not None:
        clause, names = _folders_clause(folders)
        sql += clause
        args += names
    return int(conn.execute(sql, args).fetchone()[0])


def top_sessions(rows: Iterable[SessionRow], count: int = 4) -> list[SessionRow]:
    """Return the ``count`` most expensive sessions, then by tokens and id."""
    return sorted(rows, key=lambda r: (-(r.cost or 0.0), -r.tokens, r.id))[:count]


def encode_cursor(key: tuple[str, str]) -> str:
    """Return the opaque cursor for a session's sort key."""
    raw = json.dumps(list(key), separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """Return the sort key a cursor holds.

    Raises:
        ValueError: The text is not a cursor this module made.
    """
    try:
        data: object = json.loads(
            base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        )
    except (binascii.Error, ValueError) as exc:
        msg = "bad cursor"
        raise ValueError(msg) from exc
    parts = cast("list[object]", data) if isinstance(data, list) else []
    if len(parts) != 2 or not all(isinstance(part, str) for part in parts):  # noqa: PLR2004
        msg = "bad cursor"
        raise ValueError(msg)
    return str(parts[0]), str(parts[1])


def page_sessions(
    rows: Sequence[SessionRow], cursor: str | None, size: int = SESSION_PAGE
) -> tuple[list[SessionRow], str | None]:
    """Return one page of newest-first rows after ``cursor`` and the next cursor.

    The cursor holds the last row's sort key, so rows that arrive at the top or
    change their numbers never move or repeat a loaded row. The next cursor is None
    when no row is left.

    Raises:
        ValueError: ``cursor`` is not a cursor this module made.
    """
    after = None if cursor is None else decode_cursor(cursor)
    rest = [r for r in rows if after is None or r.sort_key < after]
    page = rest[:size]
    more = len(rest) > size
    return page, encode_cursor(page[-1].sort_key) if more and page else None


def sessions_by_day(
    rows: Iterable[SessionRow], tz: str
) -> list[tuple[date, list[SessionRow]]]:
    """Group rows under the local day of their first request in the window.

    Rows keep their order, so each day is one run of rows. A day can continue on the
    next page, which the caller joins.
    """
    zone = ZoneInfo(tz)
    days: list[tuple[date, list[SessionRow]]] = []
    for row in rows:
        day = row.first_in_window.astimezone(zone).date()
        if days and days[-1][0] == day:
            days[-1][1].append(row)
        else:
            days.append((day, [row]))
    return days
