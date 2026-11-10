"""Review windows and the cost chart's pages, as pure functions of a clock and a zone.

Nothing here reads SQLite or the clock. Callers pass ``now`` (the data clock's T),
the zone's IANA name and the oldest stored request, and get aware UTC datetimes back.
They are UTC on purpose. Two aware datetimes that share one ``ZoneInfo`` compare and
subtract by their wall fields, so the repeated hour of a clock change would compare as
equal. Instants in UTC always compare by elapsed time. Local dates come from the zone.

Windows (``review_window``). The five ranges that have a length work in local days
(``RANGE_DAYS``, with 12 months as 365 days).

* ``today`` runs from local midnight to T.
* ``7d``, ``30d``, ``90d`` and ``12m`` start at local midnight ``N - 1`` days before
  today, so they end today and hold ``N`` local days.
* ``all`` starts at the oldest stored request (T when there is none) and has no
  prior window.

The prior window starts at local midnight ``2N - 1`` days before today, and
``PRIOR_RULE`` picks where it ends.

* ``same_time`` (the default, and the old app's rule, ``dashboard/usage.py:165-171``)
  ends it at ``today - N`` at T's local wall time. Today compares with yesterday up
  to the same time of day.
* ``whole_days`` ends it at the midnight that starts the current window, so both
  windows hold ``N`` whole days (the current one up to T).

A wall time is built from its fields, so a clock change between two days never moves
the hours. A time that does not exist (spring forward) lands just after the gap.

The cost chart (``chart_window``) has its own window, its bars and its pager. Page 0
is the range's window. Page ``k`` above 0 is a whole window of the same length
ending where page ``k - 1`` starts. ``all`` is one page.

Chart units. ``hour`` for today, ``day`` for 7 and 30 days, ``week`` (Monday start,
local) for 90 days, and ``month`` for 12 months. All takes its unit from the stored
span, from the oldest request to T (``all_unit``). A span of 31 days or less gives
``day``, 13 weeks or less gives ``week`` and anything longer gives ``month``. A bar is
clipped to the window, so the first and last bars may be short. A bar's end is
exclusive, and a bar with no length is never made. On page 0 the last bar ends at T
and is ``open``. Hours are real hours, so a day with a clock change has 23 or 25 hour
bars.

The API takes the chart's end as a local date. ``page_for_end`` maps it to a page.
"""

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from models import ChartUnit, PagerReason, ReviewRange

PriorRule = Literal["same_time", "whole_days"]

# The prior window's end. See the module docstring. A test switches it per call.
PRIOR_RULE: PriorRule = "same_time"

# Local days in each range that has a length. ``all`` has none.
RANGE_DAYS: dict[ReviewRange, int] = {
    "today": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "12m": 365,
}

# The unit of each range with a length. ``all`` has none here: ``all_unit`` picks it.
CHART_UNITS: dict[ReviewRange, ChartUnit] = {
    "today": "hour",
    "7d": "day",
    "30d": "day",
    "90d": "week",
    "12m": "month",
}

# All's unit by the stored span (oldest request to T): days up to this many, then
# weeks up to the next, then months.
ALL_DAY_SPAN = timedelta(days=31)
ALL_WEEK_SPAN = timedelta(weeks=13)

_MIDNIGHT = time(0)
_ONE_DAY = timedelta(days=1)
_HOUR_SECONDS = 3600
_WEEK_DAYS = 7
_DECEMBER = 12


@dataclass(frozen=True)
class Window:
    """A range's window and the one it compares with.

    ``end`` is T. ``prior_start`` and ``prior_end`` are None for ``all``.
    ``partial`` is True when ``oldest`` falls after ``start``, so the range holds less
    history than its name. ``prior_partial`` is True when ``oldest`` falls after
    ``prior_start``. Both are False when there is no oldest request.
    """

    start: datetime
    end: datetime
    prior_start: datetime | None
    prior_end: datetime | None
    partial: bool
    prior_partial: bool


@dataclass(frozen=True)
class Bar:
    """One bar's span, clipped to the chart window.

    ``open`` marks the bar that ends at T on the newest page. ``holds_oldest`` marks
    the bar that holds the oldest stored request. ``no_records`` marks a bar that ends
    at or before it, or any bar when nothing is stored.
    """

    start: datetime
    end: datetime
    open: bool
    holds_oldest: bool
    no_records: bool


@dataclass(frozen=True)
class ChartWindow:
    """The chart's window, its bars and its pager state.

    Attributes:
        start: First instant of the window. Page 0 uses the range's start.
        end: End of the window (T on page 0, else a local midnight).
        unit: The bar unit.
        page: 0 is the newest page.
        bars: Bars in time order. Empty when the window has no length.
        has_earlier: True when data may lie before ``start``.
        earlier_reason: ``no_earlier_data`` when ``has_earlier`` is False.
        has_later: True on every page but the newest.
        later_reason: ``newest`` when ``has_later`` is False.
        newest: True on page 0.
        tz: The zone's IANA name, for ``last_date``.
    """

    start: datetime
    end: datetime
    unit: ChartUnit
    page: int
    bars: tuple[Bar, ...]
    has_earlier: bool
    earlier_reason: PagerReason | None
    has_later: bool
    later_reason: PagerReason | None
    newest: bool
    tz: str

    @property
    def last_date(self) -> date:
        """The window's last local date, which is what the API calls ``end``."""
        last = self.end if self.newest else self.end - timedelta(microseconds=1)
        return last.astimezone(ZoneInfo(self.tz)).date()


def wall(zone: ZoneInfo, day: date, clock: time = _MIDNIGHT) -> datetime:
    """Return the UTC instant of a date and a wall time in ``zone``.

    It is built from the fields, so a clock change between two days does not move the
    hours. A time that does not exist lands just after the gap. A repeated time takes
    its first occurrence.
    """
    naive = datetime.combine(day, clock.replace(fold=0))
    return naive.replace(tzinfo=zone).astimezone(UTC)


def review_window(
    review_range: ReviewRange,
    now: datetime,
    tz: str,
    oldest: datetime | None,
    rule: PriorRule | None = None,
) -> Window:
    """Return the window and the prior window of a range.

    Args:
        review_range: The range name.
        now: T, aware.
        tz: IANA zone name.
        oldest: The oldest stored request, aware, or None when nothing is stored.
        rule: Where the prior window ends. None reads ``PRIOR_RULE`` at call time.

    Returns:
        The window, in UTC.
    """
    rule = rule or PRIOR_RULE
    zone = ZoneInfo(tz)
    now_local = now.astimezone(zone)
    now_utc = now.astimezone(UTC)
    oldest_utc = None if oldest is None else oldest.astimezone(UTC)
    if review_range == "all":
        return Window(
            now_utc if oldest_utc is None else oldest_utc,
            now_utc,
            None,
            None,
            False,
            False,
        )
    days = RANGE_DAYS[review_range]
    today = now_local.date()
    start = wall(zone, today - timedelta(days=days - 1))
    prior_start = wall(zone, today - timedelta(days=2 * days - 1))
    if rule == "whole_days":
        prior_end = start
    else:
        prior_end = wall(zone, today - timedelta(days=days), now_local.time())
    return Window(
        start,
        now_utc,
        prior_start,
        prior_end,
        oldest_utc is not None and oldest_utc > start,
        oldest_utc is not None and oldest_utc > prior_start,
    )


def all_unit(now: datetime, oldest: datetime | None) -> ChartUnit:
    """Return the chart unit of All, from the stored span.

    Args:
        now: T, aware.
        oldest: The oldest stored request, aware, or None when nothing is stored.

    Returns:
        ``day`` for a span of 31 days or less, ``week`` for 13 weeks or less, else
        ``month``. With nothing stored the span is 0, so the unit is ``day``. The
        chart then has no bars.
    """
    span = timedelta(0) if oldest is None else now - oldest
    if span <= ALL_DAY_SPAN:
        return "day"
    return "week" if span <= ALL_WEEK_SPAN else "month"


def _edge(unit: ChartUnit, moment: datetime, zone: ZoneInfo) -> datetime:
    """Return the first bar boundary after ``moment``, as a UTC instant."""
    local = moment.astimezone(zone)
    if unit == "hour":
        offset = (local.utcoffset() or timedelta(0)).total_seconds()
        floor = math.floor((moment.timestamp() + offset) / _HOUR_SECONDS)
        edge = floor * _HOUR_SECONDS - offset + _HOUR_SECONDS
        return datetime.fromtimestamp(edge, UTC)
    day = local.date()
    if unit == "day":
        return wall(zone, day + _ONE_DAY)
    if unit == "week":
        monday = day - timedelta(days=day.weekday())
        return wall(zone, monday + timedelta(days=_WEEK_DAYS))
    year = day.year + (day.month == _DECEMBER)
    return wall(zone, date(year, day.month % _DECEMBER + 1, 1))


def _spans(
    unit: ChartUnit, start: datetime, end: datetime, zone: ZoneInfo
) -> list[tuple[datetime, datetime]]:
    """Cut ``[start, end)`` at the unit's boundaries."""
    spans: list[tuple[datetime, datetime]] = []
    cursor = start
    while cursor < end:
        edge = _edge(unit, cursor, zone)
        spans.append((cursor, min(edge, end)))
        cursor = edge
    return spans


def chart_window(
    review_range: ReviewRange,
    now: datetime,
    tz: str,
    oldest: datetime | None,
    page: int = 0,
) -> ChartWindow:
    """Return the cost chart's window, bars and pager state for a page.

    Args:
        review_range: The range name.
        now: T, aware.
        tz: IANA zone name.
        oldest: The oldest stored request, aware, or None when nothing is stored.
        page: 0 for the range's own window, ``k`` for the whole window ``k`` windows
            earlier.

    Returns:
        The chart window.

    Raises:
        ValueError: ``page`` is negative, or above 0 for ``all``, which has one page.
    """
    if page < 0 or (page > 0 and review_range == "all"):
        msg = f"no chart page {page} for {review_range}"
        raise ValueError(msg)
    zone = ZoneInfo(tz)
    oldest_utc = None if oldest is None else oldest.astimezone(UTC)
    unit = (
        all_unit(now, oldest_utc)
        if review_range == "all"
        else CHART_UNITS[review_range]
    )
    if page == 0:
        window = review_window(review_range, now, tz, oldest)
        start, end = window.start, window.end
    else:
        days = RANGE_DAYS[review_range]
        today = now.astimezone(zone).date()
        start = wall(zone, today - timedelta(days=days * (page + 1) - 1))
        end = wall(zone, today - timedelta(days=days * page - 1))
    bars = tuple(
        Bar(
            s,
            e,
            open=page == 0 and e == end,
            holds_oldest=oldest_utc is not None and s <= oldest_utc < e,
            no_records=oldest_utc is None or e <= oldest_utc,
        )
        for s, e in _spans(unit, start, end, zone)
    )
    has_earlier = oldest_utc is not None and oldest_utc < start
    return ChartWindow(
        start=start,
        end=end,
        unit=unit,
        page=page,
        bars=bars,
        has_earlier=has_earlier,
        earlier_reason=None if has_earlier else "no_earlier_data",
        has_later=page > 0,
        later_reason=None if page > 0 else "newest",
        newest=page == 0,
        tz=tz,
    )


def page_for_end(review_range: ReviewRange, now: datetime, tz: str, end: date) -> int:
    """Return the chart page whose window holds the local date ``end``.

    The API sends the ``last_date`` an earlier answer returned, which is always the
    last date of some page, so the mapping is exact for it. Any other date lands on
    the page that holds it, and a date after today lands on page 0. ``all`` has one
    page.
    """
    if review_range == "all":
        return 0
    today = now.astimezone(ZoneInfo(tz)).date()
    back = (today - end).days
    return max(back, 0) // RANGE_DAYS[review_range]
