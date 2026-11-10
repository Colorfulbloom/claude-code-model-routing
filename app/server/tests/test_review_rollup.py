"""The hourly rollup gives the answers the minute-only scan gives.

``review_query.scan`` reads ``hour_usage`` for the UTC hours that sit wholly inside the
window, one bar and one local day, and ``minute_usage`` for the rest. ``rollup=False``
is the reference that reads minutes only. Every case here scans the same window both
ways and compares the two answers whole: every count, name, first minute and order
exactly, and every dollar within a float's rounding (the same sums added in a different
order).

Stores. The demo build and the long build (400 days) are ingested as the differential
tests do, and read in the New York, Kolkata (+5:30) and Kathmandu (+5:45) zones. A
crafted store holds a year of sparse rows with cells planted on both sides of every
zone's day edge and around the New York clock changes of March 8 and November 1, read
in six zones with a T that is not on an hour. The trace test shows which tables each
scan reads, so a test that passes cannot be one that never touched the rollup.
"""

import math
import random
import re
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
import timeline_helpers as t
from timeline_helpers import MYSTERY, OPUS, SONNET, World

import ingest
import prices
import review_query as rq
import review_windows as rw
import store
from models import REVIEW_RANGES, ReviewRange
from store_paths import StoreLayout

NY = "America/New_York"
KOLKATA = "Asia/Kolkata"
KATHMANDU = "Asia/Kathmandu"
ZONES = (NY, KOLKATA, KATHMANDU)
CRAFTED_ZONES = (
    "UTC",
    NY,
    KOLKATA,
    KATHMANDU,
    "Australia/Lord_Howe",  # a half-hour clock change
    "Pacific/Chatham",  # +12:45 and +13:45
)
DEMO_NOW = datetime(2026, 10, 30, 22, 0, tzinfo=UTC)
ODD_NOW = datetime(2026, 10, 30, 22, 17, 30, tzinfo=UTC)
HOUR = 3600
DAY = 86400


# ---------------------------------------------------------------- comparing


def _diff(path: str, rolled: Any, minutes: Any) -> list[str]:
    """Return the differences of two ``asdict`` trees, in the words of a failure."""
    found: list[str] = []
    if isinstance(rolled, dict) and isinstance(minutes, dict):
        left, right = cast("dict[Any, Any]", rolled), cast("dict[Any, Any]", minutes)
        if list(left) != list(right):
            return [f"{path}: keys {list(left)} != {list(right)}"]
        for key in left:
            found += _diff(f"{path}.{key}", left[key], right[key])
        return found
    if isinstance(rolled, list | tuple) and isinstance(minutes, list | tuple):
        many, other = cast("Sequence[Any]", rolled), cast("Sequence[Any]", minutes)
        if len(many) != len(other):
            return [f"{path}: {len(many)} items != {len(other)}"]
        for n, (a, b) in enumerate(zip(many, other, strict=True)):
            found += _diff(f"{path}[{n}]", a, b)
        return found
    if isinstance(rolled, float) and isinstance(minutes, float):
        same = math.isclose(rolled, minutes, rel_tol=1e-9, abs_tol=1e-12)
        return [] if same else [f"{path}: {rolled!r} != {minutes!r}"]
    return [] if rolled == minutes else [f"{path}: {rolled!r} != {minutes!r}"]


def _scan_both(  # noqa: PLR0913 - the scan's own inputs
    conn: sqlite3.Connection,
    doc: prices.PricesDoc,
    *,
    folders: frozenset[str] | None,
    start: datetime,
    end: datetime,
    tz: str,
    now: datetime,
    bars: Sequence[rw.Bar] = (),
    days: bool = False,
    sessions: bool = False,
) -> list[str]:
    """Scan one window with and without the rollup and return what differs."""
    answers = [
        rq.scan(
            conn,
            doc,
            folders=folders,
            start=start,
            end=end,
            tz=tz,
            now=now,
            bars=bars,
            days=days,
            sessions=sessions,
            rollup=rollup,
        )
        for rollup in (True, False)
    ]
    return _diff("scan", asdict(answers[0]), asdict(answers[1]))


def _compare_every_view(  # noqa: PLR0913 - the compared views' own inputs
    conn: sqlite3.Connection,
    doc: prices.PricesDoc,
    *,
    zone: str,
    now: datetime,
    folders: frozenset[str] | None,
    ranges: Sequence[ReviewRange] = REVIEW_RANGES,
    pages: bool = True,
) -> int:
    """Compare every scan the Review routes make, and return how many were compared.

    A failure names the range and the scan.
    """
    oldest = rq.oldest_request(conn, folders)
    count = 0
    for name in ranges:
        window = rw.review_window(name, now, zone, oldest)
        chart = rw.chart_window(name, now, zone, oldest)
        views: list[tuple[str, dict[str, Any]]] = [
            (
                "window",
                {
                    "start": window.start,
                    "end": window.end,
                    "bars": chart.bars,
                    "days": True,
                    "sessions": True,
                },
            )
        ]
        if window.prior_start is not None and window.prior_end is not None:
            views.append(
                ("prior", {"start": window.prior_start, "end": window.prior_end})
            )
        if pages and name != "all":
            older = rw.chart_window(name, now, zone, oldest, 1)
            views.append(
                (
                    "page 1",
                    {
                        "start": older.start,
                        "end": older.end,
                        "bars": older.bars,
                        "days": True,
                    },
                )
            )
        for label, kwargs in views:
            diff = _scan_both(conn, doc, folders=folders, tz=zone, now=now, **kwargs)
            assert not diff, f"{zone} {name} {label}: {diff[:5]}"
            count += 1
    return count


# ---------------------------------------------------------------- built worlds


def _ingest(build: Path, base: Path) -> sqlite3.Connection:
    conn = store.open_writer(StoreLayout(base / "bartab"))
    store.migrate(conn)
    ingest.Ingestor(
        conn,
        build / "config",
        clock=lambda: datetime(2026, 10, 30, 22, 0, tzinfo=UTC),
    ).run_pass(ingest.PassScope("full"))
    h.assert_hours_follow_minutes(conn)
    return conn


@pytest.fixture(scope="module")
def demo_conn(
    demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[sqlite3.Connection]:
    conn = _ingest(demo_build, tmp_path_factory.mktemp("rollup-demo"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def long_conn(
    long_demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[sqlite3.Connection]:
    conn = _ingest(long_demo_build, tmp_path_factory.mktemp("rollup-long"))
    yield conn
    conn.close()


def _first_folder(conn: sqlite3.Connection) -> frozenset[str]:
    row = conn.execute("SELECT MIN(folder) FROM sessions").fetchone()
    return frozenset({str(row[0])})


@pytest.mark.parametrize("now", [DEMO_NOW, ODD_NOW], ids=["on_the_hour", "mid_hour"])
@pytest.mark.parametrize("zone", ZONES)
def test_the_demo_build_reads_the_same_with_and_without_the_rollup(
    demo_conn: sqlite3.Connection, zone: str, now: datetime
) -> None:
    for folders in (None, _first_folder(demo_conn)):
        got = _compare_every_view(
            demo_conn, prices.load_prices(), zone=zone, now=now, folders=folders
        )
        assert got >= 15


@pytest.mark.parametrize(
    ("zone", "now"),
    [
        (NY, DEMO_NOW),
        (NY, ODD_NOW),
        (KOLKATA, DEMO_NOW),
        (KOLKATA, ODD_NOW),
        (KATHMANDU, DEMO_NOW),
        (KATHMANDU, ODD_NOW),
    ],
)
def test_the_long_build_reads_the_same_with_and_without_the_rollup(
    long_conn: sqlite3.Connection, zone: str, now: datetime
) -> None:
    got = _compare_every_view(
        long_conn, prices.load_prices(), zone=zone, now=now, folders=None
    )
    assert got >= 15
    one = _compare_every_view(
        long_conn,
        prices.load_prices(),
        zone=zone,
        now=now,
        folders=_first_folder(long_conn),
        ranges=("30d", "12m", "all"),
        pages=False,
    )
    assert one == 5  # 30d and 12m with a prior each, and all


# ---------------------------------------------------------------- crafted store


@pytest.fixture(scope="module")
def crafted(tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    """A year of sparse rows with cells planted at every zone's day edge.

    The clock is 12:17:30 UTC on November 1, 2026 (not on an hour). The rows cover 400
    days, so March 8 (the New York spring change) and November 1 (the fall change)
    both fall inside, and three sessions with subagent runs of three agent types
    spread over two folders, with a model that has no price.
    """
    world = World(tmp_path_factory.mktemp("rollup-crafted"), now=17 * 60 + 30)
    rng = random.Random(20261101)  # noqa: S311 - a repeatable store, not a secret
    sessions = (
        (h.S1, h.FOLDER),
        (h.S2, h.FOLDER),
        (h.S3, t.OTHER_FOLDER),
    )
    count = 0

    def put(when: datetime) -> None:
        nonlocal count
        count += 1
        sid, folder = sessions[count % 3]
        run = None if count % 4 == 0 else f"{sid[:2]}-run{count % 5}"
        agent = None if run is None else ("scout", "judge", "writer")[count % 3]
        model = (OPUS, SONNET, MYSTERY)[count % 7 % 3]
        ago = (world.moment() - when).total_seconds()
        world.add(
            ago,
            f"r{count}",
            rng.randint(1, 900),
            rng.randint(1, 90),
            rng.randint(0, 5000),
            rng.randint(0, 400),
            model=model,
            effort=(None, "high", "medium")[count % 3],
            run=run,
            agent=agent,
            sid=sid,
            folder=folder,
        )

    clock = world.moment()
    for _ in range(700):  # anywhere in the last 400 days, to the second
        put(clock - timedelta(seconds=rng.uniform(0, 400 * DAY)))
    for d in range(0, 400, 3):
        day = (clock - timedelta(days=d)).replace(hour=0, minute=0, second=0)
        for minute in (5, 25, 45):  # either side of the +5:30 and +5:45 day edges
            put(day + timedelta(hours=18, minutes=minute, seconds=rng.randint(0, 59)))
        put(day + timedelta(hours=4, minutes=rng.randint(0, 59)))  # the New York edge
    # both sides of the New York clock changes, on the hour and off it
    for edge in (
        datetime(2026, 11, 1, 6, tzinfo=UTC),
        datetime(2026, 3, 8, 7, tzinfo=UTC),
    ):
        for minutes in (-90, -31, -1, 0, 1, 29, 31, 59, 61, 119):
            put(edge + timedelta(minutes=minutes, seconds=7))
    yield world
    world.close()


@pytest.mark.parametrize("zone", CRAFTED_ZONES)
def test_a_crafted_store_reads_the_same_with_and_without_the_rollup(
    crafted: World, zone: str
) -> None:
    conn = crafted.conn()
    h.assert_hours_follow_minutes(conn)
    doc = prices.load_prices()
    now = crafted.moment()
    got = _compare_every_view(conn, doc, zone=zone, now=now, folders=None)
    got += _compare_every_view(
        conn,
        doc,
        zone=zone,
        now=now,
        folders=frozenset({h.FOLDER}),
        ranges=("7d", "90d", "all"),
    )
    assert got >= 18


def test_new_york_clock_change_days_and_odd_windows_match(crafted: World) -> None:
    """Windows that start and end off the hour, around both clock changes."""
    conn = crafted.conn()
    doc = prices.load_prices()
    now = crafted.moment()
    fall, spring = (2026, 11, 1), (2026, 3, 8)
    edges = [
        (_utc(*fall, 3, 40, 12), _utc(*fall, 9, 15)),
        (_utc(*spring, 4, 59), _utc(*spring, 8, 1)),
        (_utc(2026, 3, 7, 12), _utc(2026, 3, 9, 12)),
        (_utc(*fall, 5), _utc(*fall, 6)),
        (_utc(*fall, 5, 20), _utc(*fall, 5, 50)),
    ]
    for zone in (NY, KOLKATA, KATHMANDU):
        for start, end in edges:
            hours = rw.chart_window("today", end, zone, None).bars
            diff = _scan_both(
                conn,
                doc,
                folders=None,
                start=start,
                end=end,
                tz=zone,
                now=now,
                bars=hours,
                days=True,
                sessions=True,
            )
            assert not diff, f"{zone} {start} {end}: {diff[:5]}"


# ---------------------------------------------------------------- which tables


_AT = r"'(\d{4}-\d\d-\d\dT\d\d:\d\d)'"
_MINUTE_READ = re.compile(rf"mu\.minute >= {_AT} AND mu\.minute < {_AT}")


def _utc(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=UTC)


def _trace(conn: sqlite3.Connection, call: Any) -> list[str]:
    statements: list[str] = []
    conn.set_trace_callback(statements.append)
    try:
        call()
    finally:
        conn.set_trace_callback(None)
    return statements


def _minute_spans(statements: Sequence[str]) -> list[tuple[str, str]]:
    return [m.groups() for s in statements if (m := _MINUTE_READ.search(s))]  # pyright: ignore[reportReturnType]


def test_whole_hours_come_from_the_rollup_and_only_edge_hours_from_minutes(
    crafted: World,
) -> None:
    conn = crafted.conn()
    doc = prices.load_prices()
    now = crafted.moment()  # 12:17:30, so the open hour is read by the minute
    oldest = rq.oldest_request(conn, None)

    def scan(zone: str, name: ReviewRange) -> None:
        window = rw.review_window(name, now, zone, oldest)
        chart = rw.chart_window(name, now, zone, oldest)
        rq.scan(
            conn,
            doc,
            folders=None,
            start=window.start,
            end=window.end,
            tz=zone,
            now=now,
            bars=chart.bars,
            days=True,
        )

    on_the_hour = _trace(conn, lambda: scan(NY, "12m"))
    assert any("FROM hour_usage" in s for s in on_the_hour)
    spans = _minute_spans(on_the_hour)
    assert len(spans) == 1  # only the open hour, 12:00 to 12:18
    assert spans[0] == ("2026-11-01T12:00", "2026-11-01T12:18")

    half = _trace(conn, lambda: scan(KOLKATA, "12m"))
    spans = _minute_spans(half)
    # one hour a local day (18:00 UTC), clipped to the hour, and the open hour
    for begin, end in spans:  # every read sits inside one UTC hour
        last = datetime.strptime(end, rq.MINUTE) - timedelta(minutes=1)
        assert begin[:13] == last.strftime(rq.MINUTE)[:13], (begin, end)
    assert len(spans) <= 366 + 12 + 2
    assert len(spans) > 300
    minute_cells = sum(
        int(
            conn.execute(
                "SELECT COUNT(*) FROM minute_usage WHERE minute >= ? AND minute < ?",
                (a, b),
            ).fetchone()[0]
        )
        for a, b in spans
    )
    total_cells = int(conn.execute("SELECT COUNT(*) FROM minute_usage").fetchone()[0])
    # The store plants cells in the edge hours, so this is a third of it. A real year
    # has about one edge hour in 24, which test_review_size measures.
    assert minute_cells < total_cells // 2

    reference = _trace(
        conn,
        lambda: rq.scan(
            conn,
            doc,
            folders=None,
            start=rw.review_window("12m", now, NY, oldest).start,
            end=now,
            tz=NY,
            rollup=False,
        ),
    )
    assert not any("hour_usage" in s for s in reference)
    assert len(_minute_spans(reference)) == 1
