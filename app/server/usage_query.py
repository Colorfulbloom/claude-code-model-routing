"""Usage totals over ``minute_usage``, priced when asked.

``totals`` sums the store's per-minute cells for a set of transcript folders and a
window, then prices each cell with ``prices.price_parts``. Nothing priced is stored,
so a new price table changes every answer at once.

What it matches in the old ``dashboard/usage.py build_views`` (checked on the demo
build by ``tests/test_differential.py``)

* Agent names. A cell whose ``run_key`` is ``main`` is ``@main`` (the old "run_id is
  None"). A subagent cell is its ``runs.agent_type``, and ``@unnamed`` when the run
  has none (the old ``MAIN_KEY`` and ``UNNAMED_KEY``). The display words ("Main
  session", "Unnamed agent") are not part of this module.
* Model names. ``model_catalog.normalize_model`` id when the name is known, else the
  raw name, else ``unknown``.
* Pricing. ``price_parts`` per request. A cell sums requests of one model, speed,
  service tier, geo and price tier, so the cell is priced at its stored tier's rates
  (the tier index is part of the key). Cost counts only priced requests, and a request
  with no price counts in ``unpriced_requests``.
* Days. The local date of the request in ``tz`` (the old ``_day_buckets``). A window
  of one day gives one entry, which is what the old hour buckets add up to.
* Windows. The old window is ``start <= ts <= end``. ``minute`` is the finest grain
  the store keeps, so the window is whole minutes. The start is floored to its
  minute. An end on a whole minute excludes that minute (only a request at that exact
  instant could differ, and the old window would count it). An end with seconds
  includes its minute, so requests up to 59 seconds after ``end`` count. Callers pass
  ``end`` as the clock's now, so the demo and real windows end on or just after a
  request, and the demo build agrees with the old answer exactly.

Not in the totals: ``runs`` and ``sessions`` counts, hit rates and cost by kind.
``thinking`` is 0 where the old answer says null.
"""

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any, cast
from zoneinfo import ZoneInfo

import model_catalog
import prices

MAIN_AGENT = "@main"
UNNAMED_AGENT = "@unnamed"
UNKNOWN_MODEL = "unknown"
_MINUTE = "%Y-%m-%dT%H:%M"

_CELLS = (
    "SELECT mu.minute,"
    " CASE WHEN mu.run_key = 'main' THEN '@main'"
    " WHEN r.agent_type IS NULL OR r.agent_type = '' THEN '@unnamed'"
    " ELSE r.agent_type END AS agent,"
    " mu.model, mu.speed, mu.service_tier, mu.inference_geo, mu.tier,"
    " SUM(mu.input), SUM(mu.output), SUM(mu.cache_read), SUM(mu.cache_write_5m),"
    " SUM(mu.cache_write_1h), SUM(mu.thinking), SUM(mu.requests)"
    " FROM minute_usage mu"
    " JOIN sessions s ON s.session_id = mu.session_id"
    " LEFT JOIN runs r ON r.session_id = mu.session_id AND r.run_id = mu.run_key"
    " WHERE mu.minute >= ? AND mu.minute < ?{folders}"
    " GROUP BY mu.minute, agent, mu.model, mu.speed, mu.service_tier,"
    " mu.inference_geo, mu.tier"
)


@dataclass(frozen=True)
class Usage:
    """Token, request and cost sums for one group."""

    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    thinking: int = 0
    requests: int = 0
    cost: float = 0.0
    unpriced_requests: int = 0

    @property
    def tokens(self) -> int:
        """Input, output, cache read and both cache writes, as the old views count."""
        return (
            self.input
            + self.output
            + self.cache_read
            + self.cache_write_5m
            + self.cache_write_1h
        )


@dataclass(frozen=True)
class DayUsage:
    """One local day: its sums and its tokens per model."""

    usage: Usage
    tokens_by_model: dict[str, int]


@dataclass(frozen=True)
class Totals:
    """The answer of ``totals``.

    Attributes:
        total: The sums over the window.
        by_agent: Sums per agent name (``@main``, ``@unnamed`` or the agent type).
        by_model: Sums per model label.
        by_day: Sums per local date (``YYYY-MM-DD``). Days with no usage are absent.
    """

    total: Usage
    by_agent: dict[str, Usage]
    by_model: dict[str, Usage]
    by_day: dict[str, DayUsage]


class _Sum:
    """A running sum for one group."""

    __slots__ = (
        "cache_read",
        "cost",
        "cw1",
        "cw5",
        "input",
        "output",
        "requests",
        "thinking",
        "unpriced",
    )

    def __init__(self) -> None:
        self.input = self.output = self.cache_read = self.cw5 = self.cw1 = 0
        self.thinking = self.requests = self.unpriced = 0
        self.cost = 0.0

    def add(self, cell: "_Cell", cost: float | None) -> None:
        self.input += cell.input
        self.output += cell.output
        self.cache_read += cell.cache_read
        self.cw5 += cell.cache_write_5m
        self.cw1 += cell.cache_write_1h
        self.thinking += cell.thinking
        self.requests += cell.requests
        if cost is None:
            self.unpriced += cell.requests
        else:
            self.cost += cost

    def finish(self) -> Usage:
        return Usage(
            self.input,
            self.output,
            self.cache_read,
            self.cw5,
            self.cw1,
            self.thinking,
            self.requests,
            self.cost,
            self.unpriced,
        )


@dataclass(frozen=True)
class _Cell:
    """The sums of one grouped row. It reads as a ``prices.PricedRecord``."""

    model_raw: str
    speed: str | None
    service_tier: str | None
    inference_geo: str | None
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    thinking: int
    requests: int


@cache
def _catalog() -> list[model_catalog.CatalogEntry]:
    return model_catalog.load_catalog()


def _minute_floor(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(second=0, microsecond=0)


def _bounds(start: datetime, end: datetime) -> tuple[str, str]:
    """Return ``(low, high)`` minute texts, ``low <= minute < high``."""
    high = _minute_floor(end)
    if high != end.astimezone(UTC):
        high += timedelta(minutes=1)
    return _minute_floor(start).strftime(_MINUTE), high.strftime(_MINUTE)


def _flat(doc: prices.PricesDoc, model_id: str, tier: int) -> prices.PricesDoc | None:
    """Return ``doc`` with ``model_id`` fixed to its tier's rates, or None.

    ``price_parts`` picks a tier from one record's prompt size. A cell holds many
    requests, so the stored tier index decides the rates and the entry loses its
    ``tiers``.
    """
    models = cast("dict[str, object]", doc.get("models") or {})
    entry = models.get(model_id)
    if not isinstance(entry, dict):
        return None
    base = cast("dict[str, Any]", entry)
    rates = base
    raw_tiers = base.get("tiers")
    tiers = sorted(
        (
            cast("dict[str, Any]", t)
            for t in (
                cast("list[object]", raw_tiers) if isinstance(raw_tiers, list) else []
            )
            if isinstance(t, dict)
        ),
        key=lambda t: float(t.get("prompt_tokens_over", 0)),
    )
    if tier > 0 and tiers:
        rates = tiers[min(tier, len(tiers)) - 1]
    flat = {field: rates[field] for field in prices.PRICE_FIELDS if field in rates}
    if base.get(prices.FLAT_RATE) is True:
        flat[prices.FLAT_RATE] = True
    return {**doc, "models": {**models, model_id: flat}}


class _Pricer:
    """Prices cells at one prices document, caching the flattened documents."""

    def __init__(self, doc: prices.PricesDoc) -> None:
        self.doc = doc
        self.catalog = _catalog()
        self.docs: dict[tuple[str, int], prices.PricesDoc | None] = {}
        self.labels: dict[str, tuple[str, str | None]] = {}

    def label(self, raw: str) -> tuple[str, str | None]:
        """Return ``(model label, catalog id or None)`` for a raw model name."""
        found = self.labels.get(raw)
        if found is None:
            known, _form = model_catalog.normalize_model(raw, self.catalog)
            found = self.labels[raw] = (known or raw or UNKNOWN_MODEL, known)
        return found

    def cost(self, cell: _Cell, tier: int) -> float | None:
        """Return the cell's USD cost, or None when it has no price."""
        _label, known = self.label(cell.model_raw)
        if known is None:
            return None
        key = (known, tier)
        if key not in self.docs:
            self.docs[key] = _flat(self.doc, known, tier)
        flat = self.docs[key]
        if flat is None:
            return None
        parts = prices.price_parts(cell, flat, self.catalog)
        return None if parts is None else sum(parts.values())


# Public names for callers that price one request or one cell (the timeline).
Pricer = _Pricer
Cell = _Cell


def totals(  # noqa: PLR0913 - the query's own inputs, keyword-only after the doc
    conn: sqlite3.Connection,
    price_doc: prices.PricesDoc,
    *,
    folders: frozenset[str] | None,
    start: datetime,
    end: datetime,
    tz: str,
) -> Totals:
    """Sum ``minute_usage`` for ``folders`` over a window and price it.

    Args:
        conn: A connection to the store. Only reads.
        price_doc: The prices document (``price_feed.price_table(...).document``).
        folders: Transcript folders to include, or None for every folder.
        start: Window start, aware. Floored to its minute.
        end: Window end, aware. See the module docstring for the edge rule.
        tz: IANA zone name for the day buckets.

    Returns:
        The totals and their groups.
    """
    if folders is not None and not folders:
        return Totals(Usage(), {}, {}, {})
    low, high = _bounds(start, end)
    where = ""
    args: list[object] = [low, high]
    if folders is not None:
        ordered = sorted(folders)
        where = f" AND s.folder IN ({','.join('?' * len(ordered))})"
        args += ordered
    zone = ZoneInfo(tz)
    pricer = _Pricer(price_doc)
    days: dict[str, str] = {}
    total = _Sum()
    by_agent: dict[str, _Sum] = {}
    by_model: dict[str, _Sum] = {}
    by_day: dict[str, _Sum] = {}
    day_models: dict[str, dict[str, int]] = {}
    for row in conn.execute(_CELLS.format(folders=where), args):
        minute, agent, model, speed, tier_name, geo, tier = row[:7]
        cell = _Cell(
            str(model),
            speed or None,
            tier_name or None,
            geo or None,
            *(int(v) for v in row[7:]),
        )
        cost = pricer.cost(cell, int(tier or 0))
        day = days.get(minute)
        if day is None:
            moment = datetime.strptime(minute, _MINUTE).replace(tzinfo=UTC)
            day = days[minute] = moment.astimezone(zone).date().isoformat()
        label = pricer.label(cell.model_raw)[0]
        total.add(cell, cost)
        by_agent.setdefault(str(agent), _Sum()).add(cell, cost)
        by_model.setdefault(label, _Sum()).add(cell, cost)
        by_day.setdefault(day, _Sum()).add(cell, cost)
        tokens = day_models.setdefault(day, {})
        tokens[label] = tokens.get(label, 0) + (
            cell.input
            + cell.output
            + cell.cache_read
            + cell.cache_write_5m
            + cell.cache_write_1h
        )
    return Totals(
        total.finish(),
        {k: v.finish() for k, v in by_agent.items()},
        {k: v.finish() for k, v in by_model.items()},
        {k: DayUsage(v.finish(), day_models[k]) for k, v in by_day.items()},
    )
