"""Speed of the Review routes on a year of heavy history.

A generated store holds one project with 365 days of work: 6 sessions a day, 10 runs
each (the main session and 9 subagents of 5 agent types), and a ``minute_usage`` cell
every minute of every run's 90 minutes. That is about 1.97 million cells. The cells go
straight into SQLite under migration 7, the way the writer would leave them after an
ingest pass, so no transcript is written. Migration 8 then builds ``hour_usage`` from
them, as it does when an existing store upgrades, so the routes read the hourly rollup
(about 44,000 rows for the year).

Each of the five routes is asked at ``30d``, ``12m`` and ``all`` through TestClient.
Every timed call starts with an empty review cache, so it is a cold compute, and
``CALLS`` of them give the median and the 95th percentile. One more call after them
is a warm one, a cache hit. The plan's target (m3-build sections 2 and 7) is a 95th
percentile under 250 ms for every route and range. The numbers are printed first and
then the target is asserted, so a miss still shows what it measured.

The measuring runs in a child process, as the M2 timeline test does, so a coverage
tracer in the test process can't slow the calls it times.
"""

import json
import os
import sqlite3
import statistics
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path

import history
import ingest
import main
import price_feed
import store
import store_provider
from access import AccessState
from data_clock import DataClock
from store_paths import StoreLayout

DAYS = 365
SESSIONS_PER_DAY = 6
RUNS_PER_SESSION = 10
MINUTES_PER_RUN = 90
GENERATION_LIMIT_S = 60.0  # over this, halve MINUTES_PER_RUN and say so in the report
# A cold call takes 0.1 to 0.2 s at 12m and all, so 20 calls on every route take about
# a minute. The suite takes 5, which adds about 25 s. REVIEW_SIZE_CALLS=20 takes the
# full sample.
CALLS = int(os.environ.get("REVIEW_SIZE_CALLS", "5"))
TARGET_P95_MS = 250.0
CI_SLACK = 3.0  # a two-vCPU shared runner is a few times slower than a laptop
RANGES = ("30d", "12m", "all")
ROUTES = ("summary", "cost-chart", "sessions", "agents", "models")
ZONE = "America/New_York"
NOW = datetime(2026, 11, 9, 17, 0, tzinfo=UTC)  # noon in New York
PORT = 47123
PROJECT = "bigproject"
FOLDER = "-work-bigproject"
CWD = "/work/bigproject"
AGENT_TYPES = ("scout", "worker", "reviewer", "builder", "planner")
PRICED = ("claude-opus-5-5", "claude-sonnet-5-5")
MIXED = ("claude-sonnet-5-5", "mystery-model")  # the second one has no price
MINUTE = "%Y-%m-%dT%H:%M"
INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    '<title>Bar Tab</title></head><body><div id="root"></div></body></html>'
)

CELL_SQL = (
    "INSERT INTO minute_usage (session_id, run_key, minute, model, effort, input,"
    " output, cache_read, cache_write_5m, requests)"
    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)"
)


class IdleWriter:
    """A writer that does nothing, so the server never ingests over the store."""

    def on_ready(self, callback: object) -> None:
        del callback

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def percentile(values: list[float], share: float) -> float:
    """The value at ``share`` (0 to 1) of the sorted values, nearest rank."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(share * (len(ordered) - 1)))]


def cells_of(
    sid: str, start: datetime, minutes: int, pair: tuple[str, str]
) -> Iterator[tuple[object, ...]]:
    """Yield one session's cells, run keys in key order so inserts stay near sorted."""
    keys = sorted(["main", *(f"{sid}-a{r}" for r in range(1, RUNS_PER_SESSION))])
    for key in keys:
        r = 0 if key == "main" else int(key.rsplit("a", 1)[1])
        model = pair[r % 2]
        effort = "high" if r % 3 else "medium"
        first = start + timedelta(minutes=2 * r)
        for m in range(minutes):
            at = (first + timedelta(minutes=m)).strftime(MINUTE)
            yield (
                sid,
                key,
                at,
                model,
                effort,
                50 + m % 7,
                20 + m % 5,
                3000 + (m % 11) * 10,
                200,
            )


def generate(conn: sqlite3.Connection, minutes: int) -> int:
    """Fill the store with the year and return the number of cells."""
    conn.execute("BEGIN")
    conn.execute(
        "INSERT INTO files (id, path, kind, folder, first_seen, last_seen)"
        " VALUES (1, '/work/big.jsonl', 'main', ?, '2025-01-01', '2025-01-01')",
        (FOLDER,),
    )
    first_day = (NOW - timedelta(days=DAYS - 1)).replace(hour=0, minute=0)
    cells = 0
    for d in range(DAYS):
        day = first_day + timedelta(days=d)
        for k in range(SESSIONS_PER_DAY):
            sid = f"s{d:03d}{k}"
            start = day + timedelta(hours=2 + 2 * k)
            pair = MIXED if (d + k) % 3 == 0 else PRICED
            last = start + timedelta(minutes=2 * (RUNS_PER_SESSION - 1) + minutes)
            conn.execute(
                "INSERT INTO sessions (session_id, folder, project_key, first_ts,"
                " last_ts, cwd, branch) VALUES (?, ?, NULL, ?, ?, ?, 'main')",
                (sid, FOLDER, ingest.ts_text(start), ingest.ts_text(last), CWD),
            )
            conn.executemany(
                "INSERT INTO runs (session_id, run_id, file_id, agent_type)"
                " VALUES (?, ?, 1, ?)",
                [
                    (sid, f"{sid}-a{r}", AGENT_TYPES[(r - 1) % len(AGENT_TYPES)])
                    for r in range(1, RUNS_PER_SESSION)
                ],
            )
            before = conn.total_changes
            conn.executemany(CELL_SQL, cells_of(sid, start, minutes, pair))
            cells += conn.total_changes - before
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?)",
        (history.KEY_AS_OF, history.utc_text(NOW)),
    )
    conn.execute("COMMIT")
    return cells


def build_store(base: Path, minutes: int) -> tuple[StoreLayout, int, float]:
    """Make the store through its migrations and fill it.

    Returns the layout, the number of cells and the generation time in seconds.
    """
    layout = StoreLayout(base / "store")
    began = time.perf_counter()
    conn = store.open_writer(layout)
    try:
        # The cells go in under migration 7. Migration 8 then builds the hourly rollup
        # from them, as it does when an existing store upgrades.
        store.migrate(conn, target=7)
        cells = generate(conn, minutes)
        store.migrate(conn)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    return layout, cells, time.perf_counter() - began


def make_client(base: Path, layout: StoreLayout) -> tuple[Any, dict[str, str], Any]:
    """Return a TestClient with the lifespan running, its key headers and provider."""
    from starlette.testclient import TestClient

    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    state = AccessState()
    provider = store_provider.StoreProvider(
        layout=layout,
        claude_dir=base / "config",
        writer=IdleWriter(),  # pyright: ignore[reportArgumentType]
        price_settings=price_feed.PriceSettings(layout=layout),
        data_clock=DataClock.fixed(NOW),
        mode="demo",
        tz=ZoneInfo(ZONE),
    )
    settings = main.Settings(
        port=PORT,
        data_dir=base / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=base / "config",
        store_dir=layout.root,
        data_clock=DataClock.fixed(NOW),
        provider=provider,
        price_fetch=False,
    )
    client = TestClient(
        main.create_app(settings),
        base_url=f"http://127.0.0.1:{PORT}",
        raise_server_exceptions=False,
    )
    client.__enter__()
    return (
        client,
        {"X-Bartab-Key": state.read_key, "Accept-Encoding": "identity"},
        provider,
    )


def clear_cache(provider: Any) -> None:
    """Empty the review cache, so the next call is a cold compute."""
    provider._reviews._items.clear()  # pyright: ignore[reportPrivateUsage]


def measure(
    base: str, calls: int = CALLS, minutes: int = MINUTES_PER_RUN
) -> dict[str, Any]:
    """Build the store in ``base`` and time every route at every range."""
    root = Path(base)
    layout, cells, generation_s = build_store(root, minutes)
    client, headers, provider = make_client(root, layout)
    try:
        found = client.get("/api/projects", headers=headers).json()
        assert PROJECT in [p["key"] for p in found["projects"]], found
        rows: dict[str, dict[str, float]] = {}
        for route in ROUTES:
            for review_range in RANGES:
                path = f"/api/{route}?project={PROJECT}&range={review_range}"

                def call(path: str = path) -> float:
                    began = time.perf_counter()
                    reply = client.get(path, headers=headers)
                    took = (time.perf_counter() - began) * 1000
                    assert reply.status_code == 200, reply.text
                    return took

                clear_cache(provider)
                call()  # warm the connection and the price table, not timed
                cold: list[float] = []
                for _ in range(calls):
                    clear_cache(provider)
                    cold.append(call())
                warm = call()
                rows[f"{route} {review_range}"] = {
                    "median_ms": statistics.median(cold),
                    "p95_ms": percentile(cold, 0.95),
                    "max_ms": max(cold),
                    "warm_ms": warm,
                }
    finally:
        client.__exit__(None, None, None)
    return {
        "cells": cells,
        "generation_s": generation_s,
        "minutes_per_run": minutes,
        "calls": calls,
        "rows": rows,
    }


CHILD = (
    "import json, sys; sys.path[:0] = [{server!r}, {tests!r}]; "
    "import test_review_size as m; print(json.dumps(m.measure(sys.argv[1])))"
)


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build the year once and measure every route, in a child without a tracer."""
    base = tmp_path_factory.mktemp("review_size")
    here = Path(__file__).resolve().parent
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("COV_CORE", "COVERAGE"))  # no tracer in the child
    }
    done = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-B",
            "-c",
            CHILD.format(server=str(here.parent), tests=str(here)),
            str(base),
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=3000,
        check=True,
    )
    found: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    print(  # noqa: T201
        f"\nreview size: {found['cells']:,} cells, generated in "
        f"{found['generation_s']:.1f} s ({found['minutes_per_run']} minutes per run); "
        f"{found['calls']} cold calls each"
    )
    print(f"{'route range':<18}{'median':>9}{'p95':>9}{'max':>9}{'warm':>9}")  # noqa: T201
    for name, row in found["rows"].items():
        print(  # noqa: T201
            f"{name:<18}{row['median_ms']:>9.1f}{row['p95_ms']:>9.1f}"
            f"{row['max_ms']:>9.1f}{row['warm_ms']:>9.1f}"
        )
    return found


@pytest.mark.slow
def test_the_year_is_big_and_every_route_answers(result: dict[str, Any]) -> None:
    expected = DAYS * SESSIONS_PER_DAY * RUNS_PER_SESSION * result["minutes_per_run"]
    assert result["cells"] == expected
    assert len(result["rows"]) == len(ROUTES) * len(RANGES)
    for row in result["rows"].values():
        assert row["warm_ms"] < row["median_ms"]  # a cache hit beats a compute


@pytest.mark.slow
def test_every_route_and_range_stays_under_the_target(result: dict[str, Any]) -> None:
    limit = TARGET_P95_MS * (CI_SLACK if os.environ.get("CI") else 1.0)
    over = {n: r["p95_ms"] for n, r in result["rows"].items() if r["p95_ms"] >= limit}
    assert not over, f"95th percentile at or over {limit:.0f} ms: {over}"
