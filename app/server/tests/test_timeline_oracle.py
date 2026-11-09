"""The replay oracle at T: the new timeline equals the old ``/api/live`` at every T.

``app/fixtures/oracle/live`` holds the old answers, recorded for each ``live_flow``
scenario at many clock times. Each scenario is built with the ``flow_build`` fixture,
ingested into a temp store, and the timeline is built at every recorded T. The
projection compares runs, parents, rounds, states, tokens, cost, totals, the last
minute, the latest requests and the buckets of the old 30-minute window. The
differences ``allowed-differences.json`` lists are handled where they apply (state
words, ``label_n``, whole-session buckets, model ids). The recorded minutes carry tokens
and cache reads only, so a bucket's request count and cost are compared against the old
latest-requests list, for each minute that list covers whole.
"""

import json
import math
import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import ingest
import model_catalog
import prices
import store
import timeline
import usage_query
from models import Timeline
from store_paths import StoreLayout

ORACLE = Path(__file__).resolve().parents[2] / "fixtures" / "oracle" / "live"
PROJECT = "tidewater-reporting"
SCENARIOS = ("busy", "many", "unlinked", "empty")
STATE_WORDS = {"working": "working", "idle": "idle", "done": "finished"}


def _load(name: str) -> Any:
    return json.loads((ORACLE / name).read_text(encoding="utf-8"))


def _instant(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def _same(new: float | None, old: float | None) -> bool:
    if new is None or old is None:
        return new is old
    return math.isclose(new, old, rel_tol=1e-9, abs_tol=1e-9)


@pytest.fixture(scope="module")
def stores(
    flow_build: Callable[[str], Path], tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Callable[[str], sqlite3.Connection]]:
    """Ingest each scenario once into its own temp store."""
    opened: dict[str, sqlite3.Connection] = {}

    def get(scenario: str) -> sqlite3.Connection:
        if scenario not in opened:
            base = tmp_path_factory.mktemp(f"oracle-{scenario}")
            conn = store.open_writer(StoreLayout(base / "bartab"))
            store.migrate(conn)
            ingest.Ingestor(conn, flow_build(scenario) / "config").run_pass(
                ingest.PassScope("full")
            )
            opened[scenario] = conn
        return opened[scenario]

    yield get
    for conn in opened.values():
        conn.close()


def _build(conn: sqlite3.Connection, session: str, at: datetime) -> Timeline | None:
    return timeline.build_timeline(
        conn,
        session_id=session,
        project_key=PROJECT,
        folder_keys={
            str(row[0]): PROJECT
            for row in conn.execute("SELECT DISTINCT folder FROM sessions")
        },
        now=at,
        pricer=usage_query.Pricer(prices.load_prices()),
        catalog=model_catalog.load_catalog(),
        model_check_fn=timeline.empty_model_check,
        prices=timeline.bundled_prices(datetime(2026, 10, 30, tzinfo=UTC).date()),
    )


def _check_runs(new: Timeline, old: dict[str, Any], where: str) -> None:
    olds = old["runs"]
    assert [r.run_id for r in new.runs] == [
        "main" if r["run_id"] == "@main" else r["run_id"] for r in olds
    ], where
    for mine, was in zip(new.runs, olds, strict=True):
        at = f"{where} {mine.run_id}"
        parent = "main" if was["parent"] == "@main" else was["parent"]
        assert mine.parent == parent, at
        assert mine.parent_known is was["parent_known"], at
        assert mine.dispatch_order == was["dispatch_order"], at
        assert mine.model == was["model"], at
        assert mine.effort == was["effort"], at
        assert mine.first_request == _instant(was["started"]), at
        assert mine.last_request == _instant(was["last_request"]), at
        assert mine.state == STATE_WORDS[was["state"]], at
        assert mine.agent == was["agent"] or (
            was["agent"] is None and mine.agent in (None, "unnamed")
        ), at
        assert (mine.together is None) == (was["together"] is None), at
        if was["together"] is not None and mine.together is not None:
            assert mine.together.n == was["together"]["n"], at
        assert [(r.n, r.at, r.last_request, r.by) for r in mine.rounds] == [
            (
                r["n"],
                _instant(r["started"]),
                _instant(r["last_request"]),
                "main" if r["by"] == "@main" else r["by"],
            )
            for r in was["rounds"]
        ], at
        reads = mine.cum[-1].cache_read
        assert mine.tokens + reads == was["tokens"], at
        assert _same(mine.cost, was["cost"]), at
        # the last state in the history is the state at T
        assert mine.states[-1].state == mine.state, at


def _check_numbers(new: Timeline, old: dict[str, Any], where: str) -> None:
    totals, was = new.totals, old["totals"]
    assert totals.tokens + totals.cache_read == was["tokens"], where
    for field in ("input", "output", "cache_read", "cache_write", "requests"):
        assert getattr(totals, field) == was[field], f"{where} {field}"
    assert totals.unpriced.requests == was["unpriced_requests"], where
    assert _same(totals.cost, was["cost"]) or (
        totals.cost is None and was["unpriced_requests"] == was["requests"]
    ), where
    assert _same(totals.hit_rate, was["hit_rate"]), where
    assert new.session.requests == was["requests"], where
    last, wlast = new.last_minute, old["last_minute"]
    assert last is not None, where
    assert last.tokens + last.cache_read == wlast["tokens"], where
    assert last.requests == wlast["requests"], where
    assert last.unpriced.requests == wlast["unpriced_requests"], where
    assert _same(last.hit_rate, wlast["hit_rate"]), where
    assert _same(last.cost, wlast["cost"]) or (
        last.cost is None and wlast["unpriced_requests"] == wlast["requests"]
    ), where


def _check_requests(new: Timeline, old: dict[str, Any], where: str) -> None:
    assert len(new.requests) == len(old["requests"]), where
    for mine, was in zip(new.requests, old["requests"], strict=True):
        at = f"{where} {was['id']}"
        assert mine.id == was["id"], at
        assert mine.at == _instant(was["ts"]), at
        assert mine.model == was["model"], at
        assert mine.effort == was["effort"], at
        assert mine.tokens == was["tokens"], at
        assert mine.cache_read == was["cache_read"], at
        assert mine.output == was["output"], at
        assert _same(mine.cost, was["cost"]), at


LATEST_REQUESTS = 8  # the old answer lists this many of the latest requests


def _minute_requests(
    old: dict[str, Any], start: datetime, at: datetime
) -> list[dict[str, Any]] | None:
    """Return the old requests stamped in the minute starting at ``start``, or None.

    The recorded minutes carry tokens and cache reads only, with no cost and no request
    count. The old answer's latest-requests list does carry both, so a minute that
    ended by T is known whole when the list reaches back before the minute began, or
    when the list holds every request of the session.
    """
    listed = old["requests"]
    end = start + timedelta(seconds=60)
    if end > at:
        return None
    whole = len(listed) < LATEST_REQUESTS and len(listed) == old["totals"]["requests"]
    if not whole and not (
        len(listed) == LATEST_REQUESTS
        and min(_instant(r["ts"]) for r in listed) < start
    ):
        return None
    return [r for r in listed if start <= _instant(r["ts"]) < end]


def _check_buckets(new: Timeline, old: dict[str, Any], where: str) -> tuple[int, int]:
    """Compare the old 30 minutes with the new buckets.

    Returns the minutes compared for tokens, and the minutes whose request count and
    cost were compared as well.
    """
    if new.axis.bucket_seconds != 60:
        return 0, 0
    by_start = {b.start: b for b in new.buckets}
    compared = counted = 0
    at_time = new.server_time
    for minute in old["minutes"]:
        start = _instant(minute["start"])
        bucket = by_start.get(start)
        at = f"{where} {start:%H:%M}"
        if bucket is None:  # before the session began, or after the open minute
            assert (minute["tokens"], minute["cache_read"]) == (0, 0), at
            continue
        assert bucket.by_model == minute["by_model"], at
        assert bucket.cache_read == minute["cache_read"], at
        compared += 1
        listed = _minute_requests(old, start, at_time)
        if listed is None:
            continue
        assert bucket.requests == len(listed), f"{at} requests"
        priced = [r["cost"] for r in listed if r["cost"] is not None]
        expected = sum(priced) if priced else (None if listed else bucket.cost)
        assert _same(bucket.cost, expected) or (not listed and not bucket.cost), (
            f"{at} cost {bucket.cost} {expected}"
        )
        counted += 1
    return compared, counted


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_timeline_at_every_recorded_time_equals_the_old_answer(
    scenario: str, stores: Callable[[str], sqlite3.Connection]
) -> None:
    manifest = _load("manifest.json")["scenarios"][scenario]
    conn = stores(scenario)
    session = manifest["session"]
    compared = running = minutes = counted = 0
    for stamp in manifest["sampled"]:
        old = _load(f"{scenario}/at-{stamp}.json")
        at = _instant(old["at"])
        where = f"{scenario} {stamp}"
        new = _build(conn, session, at)
        if old["session"] is None:
            # nothing running in the old answer: no session yet, or it has ended
            assert new is None or not new.session.running, where
            continue
        assert new is not None, where
        assert new.server_time == at, where
        assert new.session.running, where
        assert new.session.started == _instant(old["session"]["started"]), where
        assert new.session.last_request == _instant(old["session"]["last_request"]), (
            where
        )
        assert new.session.active is old["session"]["active"], where
        assert [session] == old["running"], where
        _check_runs(new, old, where)
        _check_numbers(new, old, where)
        _check_requests(new, old, where)
        bucket_minutes, bucket_counted = _check_buckets(new, old, where)
        minutes += bucket_minutes
        counted += bucket_counted
        compared += 1
        running += len(new.runs)
    assert compared > 0
    assert running > 0
    if scenario == "busy":
        assert minutes > 0
        assert counted > 0, "bucket request counts and cost were never compared"
