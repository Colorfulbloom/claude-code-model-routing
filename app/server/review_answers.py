"""The five Review answers, built from one read of the store.

``StoreProvider`` opens the read connection, finds the project and fills a ``Context``.
Each ``build_*`` function turns that into a full answer with an empty etag, and
``finish`` hashes it. The numbers come from ``review_query.scan`` (the window and, for
Summary, the prior window), the setup from ``agent_setup`` and the windows from
``review_windows``. Nothing here reads a ``cwd``, a message or an agent description.

The etag (``etag_of``) is a digest of the answer body without the fields that move with
the clock and say nothing about the data: ``server_time``, ``as_of``, ``window.end`` and
``window.prior_end`` (both follow T under the default prior rule), and on the cost chart
the newest page's end and the open bar's end. A new request, a changed state or a price
change still changes it.

``ReviewCache`` keeps the last 32 full answers. Its key is ``(route, project, range,
variant, local date, pass marker, price table hash)``.

* ``variant`` is the cursor on Sessions and the chart's page on the cost chart, else "".
* ``local date`` is T's date in the server's zone, so an answer never lives past
  midnight (Today and every window start move then).
* ``pass marker`` is the store's ``last_pass`` stamp, the end of the last finished
  ingest pass, so a new pass drops every answer. With no finished pass there is no
  marker and nothing is cached.
* ``price table hash`` is ``PriceTable.hash``, so a new price drops every answer.
"""

import math
import sqlite3
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import agent_setup
import history
import model_check
import pincheck
import review_query as rq
import review_windows as rw
import timeline
from models import (
    AgentList,
    AgentMoney,
    AgentRow,
    CardError,
    ChartBar,
    ChartWindow,
    CostChart,
    CostTile,
    CountTile,
    KindCosts,
    ModelBarCost,
    ModelCheck,
    ModelCost,
    ModelKinds,
    ModelList,
    ModelRow,
    PairRuns,
    RanPair,
    ReviewRange,
    ReviewSession,
    ReviewWindow,
    SessionDay,
    SessionList,
    SessionWhole,
    ShareTile,
    Summary,
    SummaryTiles,
    TimelinePrices,
    Unpriced,
)
from prices import PricesDoc
from usage import Row

CACHE_SIZE = 32
TOP_SESSIONS = 4
TICK_STEPS = 5
_MANTISSAS = (1, 2, 5)
_EPSILON = 1e-9
_DECIMALS = 10

Answer = Summary | CostChart | SessionList | AgentList | ModelList
CacheKey = tuple[str, str, str, str, date, str, str]


@dataclass(frozen=True)
class Context:
    """What every Review answer reads, fixed for one request.

    ``order`` ranks model ids in catalog order, then by name.
    """

    conn: sqlite3.Connection
    project: str
    folders: frozenset[str]
    review_range: ReviewRange
    now: datetime
    tz: str
    oldest: datetime | None
    window: rw.Window
    doc: PricesDoc
    catalog_ids: Sequence[str]
    prices: TimelinePrices
    as_of: datetime | None


class ReviewCache:
    """The last ``CACHE_SIZE`` full answers, least recently used out first."""

    def __init__(self, size: int = CACHE_SIZE) -> None:
        """Make an empty cache that keeps ``size`` answers."""
        self._size = size
        self._items: OrderedDict[CacheKey, Answer] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: CacheKey) -> Answer | None:
        """Return the answer for ``key`` and mark it used, or None."""
        with self._lock:
            found = self._items.get(key)
            if found is not None:
                self._items.move_to_end(key)
            return found

    def put(self, key: CacheKey, answer: Answer) -> None:
        """Keep ``answer`` under ``key``, dropping the least recently used one."""
        with self._lock:
            self._items[key] = answer
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        """Return how many answers are kept."""
        with self._lock:
            return len(self._items)


def pass_marker(conn: sqlite3.Connection) -> str | None:
    """Return the end of the last finished ingest pass as stored, or None."""
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", (history.KEY_AS_OF,)
    ).fetchone()
    return None if row is None else str(row[0])


# ------------------------------------------------------------------ shared


def _unpriced(found: rq.Unpriced) -> Unpriced:
    return Unpriced(requests=found.requests, models=list(found.models))


def _kinds(found: rq.Kinds) -> KindCosts:
    return KindCosts(
        input=found.input,
        output=found.output,
        cache_read=found.cache_read,
        cache_write=found.cache_write,
    )


def _order(ctx: Context) -> Callable[[str], tuple[int, str]]:
    """Return the sort key for model ids, catalog order first and then the name."""
    ranks = {model: n for n, model in enumerate(ctx.catalog_ids)}
    size = len(ranks)

    def key(model: str) -> tuple[int, str]:
        return ranks.get(model, size), model

    return key


def review_window(ctx: Context) -> ReviewWindow:
    """Return the answer's ``window`` from the context."""
    found = ctx.window
    return ReviewWindow(
        start=found.start,
        end=found.end,
        prior_start=found.prior_start,
        prior_end=found.prior_end,
        tz=ctx.tz,
        oldest=ctx.oldest,
        partial=found.partial,
        prior_partial=found.prior_partial,
    )


def _shared(ctx: Context, errors: list[CardError]) -> dict[str, object]:
    return {
        "project": ctx.project,
        "range": ctx.review_range,
        "window": review_window(ctx),
        "server_time": ctx.now,
        "as_of": ctx.as_of,
        "etag": "",
        "unchanged": False,
        "prices": ctx.prices,
        "errors": errors,
    }


def _scan(ctx: Context, start: datetime, end: datetime, **kwargs: object) -> rq.Scan:
    return rq.scan(
        ctx.conn,
        ctx.doc,
        folders=ctx.folders,
        start=start,
        end=end,
        tz=ctx.tz,
        now=ctx.now,
        **kwargs,  # pyright: ignore[reportArgumentType]
    )


def _setup_errors(
    setup: agent_setup.AgentSetup, card: Literal["model_check", "agent_setup"]
) -> list[CardError]:
    if setup.failed:
        return [CardError(card=card, code="setup_unreadable")]
    return []


# ------------------------------------------------------------------ sessions


def session_of(row: rq.SessionRow) -> ReviewSession:
    """Return a session row as the API model."""
    whole = row.whole
    return ReviewSession(
        id=row.id,
        started=row.started,
        last_request=row.last_request,
        branch=row.branch,
        state=row.state,
        agents=list(row.agents),
        runs=row.runs,
        tokens=row.tokens,
        cost=row.cost,
        unpriced=_unpriced(row.unpriced),
        started_before_range=row.started_before_range,
        whole=None
        if whole is None
        else SessionWhole(
            tokens=whole.tokens, cost=whole.cost, unpriced=_unpriced(whole.unpriced)
        ),
    )


# ------------------------------------------------------------------ summary


def _change(
    value: float | None, prior: float | None, *, hidden: bool
) -> tuple[float | None, float | None]:
    """Return ``(change_pct, change_abs)``, both None when ``hidden`` or a side is None.

    ``change_pct`` is also None when the prior is 0.
    """
    if hidden or value is None or prior is None:
        return None, None
    pct = None if prior == 0 else (value - prior) / prior
    return pct, value - prior


def _count_tile(value: int, prior: int | None, *, hidden: bool) -> CountTile:
    pct, diff = _change(value, prior, hidden=hidden)
    return CountTile(
        value=value,
        prior=prior,
        change_pct=pct,
        change_abs=None if diff is None else round(diff),
    )


def _money(by_agent: Mapping[str, rq.AgentSums]) -> list[AgentMoney]:
    return [
        AgentMoney(
            agent=key,
            model=found.model,
            cost=found.sums.cost,
            share=found.share,
            requests=found.sums.requests,
            unpriced=_unpriced(found.sums.unpriced),
        )
        for key, found in by_agent.items()
    ]


def _check_runs(
    runs: Mapping[str, Sequence[Mapping[str, object]]],
) -> dict[str | None, list[Row]]:
    """Return the runs as ``build_model_check_from_runs`` takes them.

    The model check reads only ``run_id``, ``model`` and ``effort`` of a run. The
    timeline names the main session ``None`` and an unnamed agent ``unnamed``, and
    the check keeps those names.
    """
    out: dict[str | None, list[Row]] = {}
    for key, rows in runs.items():
        agent = (
            None
            if key == pincheck.MAIN
            else "unnamed"
            if key == pincheck.UNNAMED
            else key
        )
        out[agent] = [
            {"run_id": r["run_id"], "model": r["model"], "effort": r["effort"]}
            for r in rows
        ]
    return out


def build_summary(ctx: Context, setup: agent_setup.AgentSetup) -> Summary:
    """Build the Summary answer. A failed setup nulls ``model_check`` and says so."""
    window = ctx.window
    cur = _scan(ctx, window.start, window.end, sessions=True)
    prior = (
        None
        if window.prior_start is None or window.prior_end is None
        else _scan(ctx, window.prior_start, window.prior_end)
    )
    hidden = prior is None or window.prior_partial
    total = cur.total
    cost_pct, cost_abs = _change(
        total.cost, None if prior is None else prior.total.cost, hidden=hidden
    )
    cache_prior = None if prior is None else prior.total.hit_rate
    _pct, cache_abs = _change(total.hit_rate, cache_prior, hidden=hidden)
    tiles = SummaryTiles(
        cost=CostTile(
            value=total.cost,
            prior=None if prior is None else prior.total.cost,
            change_pct=cost_pct,
            change_abs=cost_abs,
            unpriced=_unpriced(total.unpriced),
            prior_unpriced=None if prior is None else _unpriced(prior.total.unpriced),
        ),
        sessions=_count_tile(
            total.sessions,
            None if prior is None else prior.total.sessions,
            hidden=hidden,
        ),
        tokens=_count_tile(
            total.tokens,
            None if prior is None else prior.total.tokens,
            hidden=hidden,
        ),
        cache_share=ShareTile(
            value=total.hit_rate, prior=cache_prior, change_abs=cache_abs
        ),
    )
    check: ModelCheck | None = None
    if not setup.failed:
        check = model_check.build_model_check_from_runs(
            entries=setup.entries,
            runs_by_agent=_check_runs(cur.runs),
            catalog=setup.catalog,
        )
    return Summary(
        **_shared(ctx, _setup_errors(setup, "model_check")),  # pyright: ignore[reportArgumentType]
        tiles=tiles,
        money=_money(cur.by_agent),
        model_check=check,
        top_sessions=[
            session_of(row) for row in rq.top_sessions(cur.sessions, TOP_SESSIONS)
        ],
        session_count=total.sessions,
        no_usage_sessions=rq.no_usage_sessions(
            ctx.conn, ctx.folders, window.start, window.end
        ),
    )


# ------------------------------------------------------------------ cost chart


def y_ticks(top: float) -> list[float]:
    """Return dollar ticks from 0 to at least ``top``, in steps of 1, 2 or 5 times 10^n.

    The smallest such step that needs at most ``TICK_STEPS`` steps wins. A ``top`` of 0
    or less gives 0 and the smallest step, one cent.
    """
    if top <= 0:
        return [0.0, 0.01]
    power = math.floor(math.log10(top / TICK_STEPS))
    for exponent in (power, power + 1):
        for mantissa in _MANTISSAS:
            step = mantissa * 10.0**exponent
            steps = max(math.ceil(top / step - _EPSILON), 1)
            if steps <= TICK_STEPS:
                return [round(n * step, _DECIMALS) for n in range(steps + 1)]
    msg = "no tick step found"  # unreachable: 10 ** (power + 1) always fits
    raise AssertionError(msg)


def build_cost_chart(ctx: Context, page: int) -> CostChart:
    """Build the cost chart for a page. Page 0 is the range's own window."""
    chart = rw.chart_window(ctx.review_range, ctx.now, ctx.tz, ctx.oldest, page)
    found = _scan(ctx, chart.start, chart.end, bars=chart.bars)
    order = _order(ctx)
    bars: list[ChartBar] = []
    for span, sums in zip(chart.bars, found.bars, strict=True):
        bars.append(
            ChartBar(
                start=span.start,
                end=span.end,
                by_model={
                    label: ModelBarCost(
                        cost=part.cost,
                        kinds=_kinds(part.kinds),
                        requests=part.requests,
                        unpriced=_unpriced(part.unpriced),
                    )
                    for label, part in sums.models.items()
                },
                unpriced=_unpriced(sums.unpriced),
                open=span.open,
                holds_oldest=span.holds_oldest,
                no_records=span.no_records,
            )
        )
    tallest = max(
        (sum(part.cost or 0.0 for part in bar.by_model.values()) for bar in bars),
        default=0.0,
    )
    return CostChart(
        **_shared(ctx, []),  # pyright: ignore[reportArgumentType]
        chart=ChartWindow(
            start=chart.start,
            end=chart.end,
            unit=chart.unit,
            has_earlier=chart.has_earlier,
            has_later=chart.has_later,
            earlier_reason=chart.earlier_reason,
            later_reason=chart.later_reason,
            newest=chart.newest,
        ),
        bars=bars,
        legend=[
            ModelCost(
                model=label,
                cost=part.sums.cost,
                requests=part.sums.requests,
                unpriced=_unpriced(part.sums.unpriced),
            )
            for label, part in sorted(
                found.by_model.items(), key=lambda item: order(item[0])
            )
        ],
        kinds=_kinds(found.total.cost_by_kind),
        unpriced=_unpriced(found.total.unpriced),
        y_ticks=y_ticks(tallest),
    )


# ------------------------------------------------------------------ sessions list


def build_sessions(ctx: Context, cursor: str | None) -> SessionList:
    """Build one page of the session list.

    Raises:
        ValueError: ``cursor`` is not a cursor ``review_query`` made.
    """
    window = ctx.window
    found = _scan(ctx, window.start, window.end, sessions=True)
    page, following = rq.page_sessions(found.sessions, cursor)
    return SessionList(
        **_shared(ctx, []),  # pyright: ignore[reportArgumentType]
        count=len(found.sessions),
        days=[
            SessionDay(day=day, sessions=[session_of(row) for row in rows])
            for day, rows in rq.sessions_by_day(page, ctx.tz)
        ],
        next=following,
    )


# ------------------------------------------------------------------ agents


def build_agents(ctx: Context, setup: agent_setup.AgentSetup) -> AgentList:
    """Build the Agents answer. A failed setup gives every row ``read_failed``."""
    window = ctx.window
    found = _scan(ctx, window.start, window.end)
    rows: list[AgentRow] = []
    for key, agent in found.by_agent.items():
        check = agent_setup.check_agent(setup, key, found.runs.get(key, []))
        ran = agent.ran
        rows.append(
            AgentRow(
                agent=key,
                scope=check.scope,
                set=check.set,
                set_reason=check.set_reason,
                ran=RanPair(
                    model=None if ran is None else ran.model,
                    effort=None if ran is None else ran.effort,
                    mixed=agent.mixed,
                ),
                ran_pairs=[
                    PairRuns(model=pair.model, effort=pair.effort, runs=pair.runs)
                    for pair in agent.ran_pairs
                ],
                status=check.status,
                reason_code=check.reason_code,
                params=check.params,
                runs=agent.sums.runs,
                runs_as_set=check.runs_as_set,
                runs_not_as_set=check.runs_not_as_set,
                sessions=agent.sums.sessions,
                cost=agent.sums.cost,
                share=agent.share,
                requests=agent.sums.requests,
                unpriced=_unpriced(agent.sums.unpriced),
            )
        )
    return AgentList(
        **_shared(ctx, _setup_errors(setup, "agent_setup")),  # pyright: ignore[reportArgumentType]
        ran=rows,
        never_ran=agent_setup.never_ran(setup, list(found.by_agent)),
    )


# ------------------------------------------------------------------ models


def build_models(ctx: Context) -> ModelList:
    """Build the Models answer: a row and a kinds line per model, biggest cost first."""
    window = ctx.window
    found = _scan(ctx, window.start, window.end)
    rows: list[ModelRow] = []
    kinds: list[ModelKinds] = []
    for label, model in found.by_model.items():
        sums = model.sums
        rows.append(
            ModelRow(
                model=label,
                cost=sums.cost,
                share=model.share,
                tokens=sums.tokens,
                requests=sums.requests,
                cache_share=sums.hit_rate,
                used_by=list(model.agents),
                unpriced=_unpriced(sums.unpriced),
            )
        )
        part = sums.cost_by_kind
        kinds.append(
            ModelKinds(
                model=label,
                input=part.input,
                output=part.output,
                cache_read=part.cache_read,
                cache_write=part.cache_write,
                unpriced=_unpriced(sums.unpriced),
            )
        )
    return ModelList(
        **_shared(ctx, []),  # pyright: ignore[reportArgumentType]
        rows=rows,
        kinds=kinds,
        legend=_kinds(found.total.cost_by_kind),
        unpriced=_unpriced(found.total.unpriced),
    )


# ------------------------------------------------------------------ etag


def etag_of(answer: Answer) -> str:
    """Return the etag of a full answer. See the module docstring for what it skips."""
    body = answer.model_dump(mode="json", exclude={"server_time", "etag", "as_of"})
    body["window"].pop("end", None)
    body["window"].pop("prior_end", None)
    if isinstance(answer, CostChart):
        if body["chart"]["newest"]:
            body["chart"].pop("end", None)
        for bar in body["bars"]:
            if bar["open"]:
                bar.pop("end", None)
    return timeline.digest(body)


def finish(answer: Answer) -> Answer:
    """Return ``answer`` with its etag set."""
    return answer.model_copy(update={"etag": etag_of(answer)})
