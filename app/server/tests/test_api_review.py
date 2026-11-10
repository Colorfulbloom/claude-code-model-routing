"""Tests for the Review routes, over the demo build served through TestClient.

One server runs for the module, on a store ingested from the demo build and a fixed
data clock at the demo's time (October 30, 2026, 6 PM in New York). The cache and
failure tests start their own server so they can move the clock and break the setup.
"""

import itertools
import json
import math
import re
import sqlite3
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import INDEX_HTML, PORT, _open  # pyright: ignore[reportPrivateUsage]

import agent_setup
import main
import review_answers
import review_query
import serve
import store_provider
from access import AccessState
from data_clock import DataClock
from models import REVIEW_RANGES, SessionList, Summary

PROJECT = "tidewater-reporting"
OTHER_PROJECT = "driftwood"
ZONE = "America/New_York"
JSON_HEADERS = {"Accept-Encoding": "identity"}
ROUTES = ("summary", "cost-chart", "sessions", "agents", "models")
COST = pytest.approx  # costs are sums of floats in different orders
OpenClient = Callable[..., AbstractContextManager[Any]]


@dataclass
class Served:
    """A running demo server and what it needs to be asked things."""

    client: Any
    headers: dict[str, str]
    provider: store_provider.StoreProvider
    clock: DataClock
    now: datetime
    build: Path

    def get(self, path: str) -> Any:
        return self.client.get(path, headers={**self.headers, **JSON_HEADERS})

    def ok(self, path: str) -> Any:
        reply = self.get(path)
        assert reply.status_code == 200, reply.text
        return reply.json()


def _serve(
    base: Path,
    build: Path,
    open_client: OpenClient,
    clock: DataClock,
) -> Iterator[Served]:
    dist = base / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    state = AccessState()
    settings = main.Settings(
        port=PORT,
        data_dir=base / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=build / "config",
        store_dir=base / "store",
        demo=True,
        data_clock=clock,
        price_fetch=False,
    )
    provider = main.make_provider(settings)
    assert isinstance(provider, store_provider.StoreProvider)
    app = main.create_app(replace(settings, provider=provider))
    with open_client(app) as client:
        headers = {"X-Bartab-Key": state.read_key}
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            info = client.get("/api/app", headers=headers).json()
            if info["ingest"]["state"] == "done":
                break
            time.sleep(0.05)
        else:
            pytest.fail("the demo ingest never finished")
        yield Served(client, headers, provider, clock, serve.scenario_now(build), build)


@pytest.fixture(scope="module")
def served(
    demo_build: Path, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[Served]:
    now = serve.scenario_now(demo_build)
    yield from _serve(
        tmp_path_factory.mktemp("review"), demo_build, _open, DataClock.fixed(now)
    )


@pytest.fixture
def moving(
    demo_build: Path, tmp_path: Path, open_client: OpenClient
) -> Iterator[Served]:
    """A server of its own, on a test clock that a test can move."""
    now = serve.scenario_now(demo_build)
    yield from _serve(tmp_path, demo_build, open_client, DataClock.test(now))


def path_of(route: str, review_range: str, project: str = PROJECT, **more: str) -> str:
    query = "&".join(f"{k}={v}" for k, v in more.items())
    base = f"/api/{route}?project={project}&range={review_range}"
    return f"{base}&{query}" if query else base


def cost_sum(rows: list[dict[str, Any]], key: str = "cost") -> float:
    return sum(row[key] or 0.0 for row in rows)


# ------------------------------------------------------------- every route and range


@pytest.mark.parametrize("review_range", REVIEW_RANGES)
@pytest.mark.parametrize("route", ROUTES)
def test_every_route_answers_for_every_range(
    served: Served, route: str, review_range: str
) -> None:
    body = served.ok(path_of(route, review_range))
    assert body["project"] == PROJECT
    assert body["range"] == review_range
    assert body["unchanged"] is False
    assert body["etag"]
    assert body["errors"] == []
    window = body["window"]
    assert window["tz"] == ZONE
    assert window["end"] == body["server_time"]
    assert window["oldest"] is not None
    assert body["prices"]["as_of"]
    assert body["as_of"] is not None


def test_the_range_defaults_to_thirty_days(served: Served) -> None:
    body = served.ok(f"/api/summary?project={PROJECT}")
    assert body["range"] == "30d"
    assert body["etag"] == served.ok(path_of("summary", "30d"))["etag"]


def test_windows_follow_the_server_zone(served: Served) -> None:
    window = served.ok(path_of("summary", "7d"))["window"]
    start = datetime.fromisoformat(window["start"]).astimezone(ZoneInfo(ZONE))
    assert (start.hour, start.minute) == (0, 0)
    assert start.date() == date(2026, 10, 24)
    today = served.ok(path_of("summary", "today"))["window"]
    assert datetime.fromisoformat(today["start"]).astimezone(ZoneInfo(ZONE)).date() == (
        date(2026, 10, 30)
    )


# ------------------------------------------------------------------ etag, unchanged


@pytest.mark.parametrize("route", ROUTES)
def test_a_matching_etag_gets_the_short_answer(served: Served, route: str) -> None:
    full = served.ok(path_of(route, "30d"))
    short = served.ok(path_of(route, "30d", etag=full["etag"]))
    assert set(short) == {"project", "server_time", "etag", "unchanged"}
    assert short["unchanged"] is True
    assert short["etag"] == full["etag"]
    other = served.ok(path_of(route, "30d", etag="0123456789abcdef"))
    assert other["unchanged"] is False
    assert other["etag"] == full["etag"]
    # an etag for one range is not another range's
    seven = served.ok(path_of(route, "7d", etag=full["etag"]))
    assert seven["unchanged"] is False


def test_the_etag_ignores_the_clock_and_follows_the_numbers() -> None:
    now = datetime(2026, 10, 30, 22, tzinfo=UTC)
    window = {
        "start": now - timedelta(days=1),
        "end": now,
        "prior_start": now - timedelta(days=2),
        "prior_end": now - timedelta(days=1),
        "tz": ZONE,
        "oldest": now - timedelta(days=9),
        "partial": False,
        "prior_partial": False,
    }
    base: dict[str, Any] = {
        "project": PROJECT,
        "range": "today",
        "window": window,
        "server_time": now,
        "as_of": now,
        "etag": "",
        "unchanged": False,
        "prices": {
            "as_of": "2026-10-30",
            "source": "bundled",
            "cross_check_state": "agree",
        },
        "errors": [],
        "count": 0,
        "days": [],
        "next": None,
    }
    first = SessionList.model_validate(base)
    later = SessionList.model_validate(
        {
            **base,
            "server_time": now + timedelta(minutes=5),
            "as_of": now + timedelta(minutes=5),
            "window": {
                **window,
                "end": now + timedelta(minutes=5),
                "prior_end": now - timedelta(days=1) + timedelta(minutes=5),
            },
        }
    )
    changed = SessionList.model_validate({**base, "count": 1})
    assert review_answers.etag_of(first) == review_answers.etag_of(later)
    assert review_answers.etag_of(first) != review_answers.etag_of(changed)


# -------------------------------------------------------------------- bad requests


@pytest.mark.parametrize(
    ("suffix", "field"),
    [
        ("&range=forever", "range"),
        ("&range=", "range"),
        ("&range=7d&range=30d", "range"),
        ("&etag=a&etag=b", "etag"),
        ("&cursor=not-a-cursor", "cursor"),
        ("&cursor=", "cursor"),
        ("&cursor=a&cursor=b", "cursor"),
        ("&end=yesterday", "end"),
        ("&end=2026-13-45", "end"),
        ("&end=2026-1-5", "end"),
        ("&end=2026-10-30&end=2026-10-29", "end"),
    ],
)
def test_a_bad_parameter_is_bad_request_with_its_field(
    served: Served, suffix: str, field: str
) -> None:
    route = {"cursor": "sessions", "end": "cost-chart"}.get(field, "summary")
    reply = served.get(f"/api/{route}?project={PROJECT}{suffix}")
    assert reply.status_code == 400, reply.text
    assert reply.json() == {"code": "bad_request", "path": ["query", field]}


def test_a_missing_or_repeated_project_is_bad_request(served: Served) -> None:
    for path in (
        "/api/summary",
        "/api/summary?range=7d",
        f"/api/summary?project={PROJECT}&project={OTHER_PROJECT}",
    ):
        reply = served.get(path)
        assert reply.status_code == 400, path
        assert reply.json() == {"code": "bad_request", "path": ["query", "project"]}


def test_a_cursor_the_other_routes_ignore_is_not_checked(served: Served) -> None:
    assert served.get(f"/api/models?project={PROJECT}&cursor=zzz").status_code == 200
    assert served.get(f"/api/models?project={PROJECT}&end=nope").status_code == 200


@pytest.mark.parametrize("route", ROUTES)
def test_an_unknown_project_is_unknown_project(served: Served, route: str) -> None:
    reply = served.get(path_of(route, "30d", project="no-such"))
    assert reply.status_code == 404
    assert reply.json()["code"] == "unknown_project"


@pytest.mark.parametrize("route", ROUTES)
def test_the_fixture_provider_has_no_review_data(
    client: Any, key_headers: dict[str, str], route: str
) -> None:
    reply = client.get(path_of(route, "30d", project="no-such"), headers=key_headers)
    assert reply.status_code == 404
    assert reply.json()["code"] == "unknown_project"


@pytest.mark.parametrize("route", ROUTES)
def test_the_review_routes_need_the_read_key(served: Served, route: str) -> None:
    path = path_of(route, "30d")
    assert served.client.get(path).status_code == 401
    assert served.client.get(path, headers={"X-Bartab-Key": "wrong"}).status_code == 401


def test_the_sessions_route_does_not_meet_the_timeline_route(served: Served) -> None:
    listing = served.ok(path_of("sessions", "30d"))
    first = listing["days"][0]["sessions"][0]["id"]
    timeline = served.ok(f"/api/sessions/{first}/timeline?project={PROJECT}")
    assert timeline["session"]["id"] == first


# ------------------------------------------------------------------ the money adds up


@pytest.mark.parametrize("project", [PROJECT, OTHER_PROJECT])
@pytest.mark.parametrize("review_range", REVIEW_RANGES)
def test_the_cost_tile_equals_the_chart_legend_and_the_agent_costs(
    served: Served, project: str, review_range: str
) -> None:
    summary = served.ok(path_of("summary", review_range, project))
    chart = served.ok(path_of("cost-chart", review_range, project))
    agents = served.ok(path_of("agents", review_range, project))
    models = served.ok(path_of("models", review_range, project))
    tile = summary["tiles"]["cost"]["value"]
    assert chart["chart"]["newest"] is True
    assert cost_sum(chart["legend"]) == COST(tile, abs=1e-9)
    assert cost_sum(agents["ran"]) == COST(tile, abs=1e-9)
    assert cost_sum(models["rows"]) == COST(tile, abs=1e-9)
    assert cost_sum(summary["money"]) == COST(tile, abs=1e-9)
    kinds = chart["kinds"]
    assert sum(kinds.values()) == COST(tile, abs=1e-9)
    assert chart["unpriced"] == summary["tiles"]["cost"]["unpriced"]
    assert (
        sum(b["unpriced"]["requests"] for b in chart["bars"])
        == (chart["unpriced"]["requests"])
    )
    assert cost_sum(
        [
            {"cost": sum((p["cost"] or 0.0) for p in b["by_model"].values())}
            for b in chart["bars"]
        ]
    ) == COST(tile, abs=1e-9)
    requests = sum(row["requests"] for row in agents["ran"])
    assert requests == sum(row["requests"] for row in models["rows"])
    assert requests == sum(row["requests"] for row in summary["money"])


# ------------------------------------------------------------------------- summary


def test_summary_tiles_money_and_sessions(served: Served) -> None:
    body = served.ok(path_of("summary", "30d"))
    tiles = body["tiles"]
    assert tiles["cost"]["value"] > 0
    assert tiles["cost"]["prior"] is not None
    assert tiles["cost"]["change_abs"] == COST(
        tiles["cost"]["value"] - tiles["cost"]["prior"]
    )
    assert tiles["cost"]["change_pct"] == COST(
        (tiles["cost"]["value"] - tiles["cost"]["prior"]) / tiles["cost"]["prior"]
    )
    assert tiles["cost"]["prior_unpriced"] is not None
    assert tiles["sessions"]["value"] == body["session_count"]
    assert tiles["tokens"]["value"] > 0
    assert 0 < tiles["cache_share"]["value"] <= 1
    assert tiles["cache_share"]["change_abs"] == COST(
        tiles["cache_share"]["value"] - tiles["cache_share"]["prior"]
    )
    assert "change_pct" not in tiles["cache_share"]
    money = body["money"]
    costs = [row["cost"] for row in money]
    assert costs == sorted(costs, reverse=True)
    assert sum(row["share"] or 0 for row in money) == COST(1.0)
    assert {row["agent"] for row in money} >= {"@main"}
    assert all(row["model"] for row in money)
    top = body["top_sessions"]
    assert 1 <= len(top) <= 4
    assert [s["cost"] for s in top] == sorted((s["cost"] for s in top), reverse=True)
    assert body["no_usage_sessions"] >= 0


def test_summary_model_check_has_the_timeline_row_shape(served: Served) -> None:
    check = served.ok(path_of("summary", "30d"))["model_check"]
    assert check is not None
    assert check["rows"]
    assert check["in_effect_count"] == sum(
        1 for row in check["rows"] if row["status"] == "in_effect"
    )
    assert set(check["rows"][0]) == {
        "agent",
        "set",
        "ran",
        "status",
        "reason_code",
        "params",
        "runs",
        "mismatched_runs",
    }
    assert any(row["agent"] is None for row in check["rows"])  # the main session


def test_all_has_no_prior_window_and_no_changes(served: Served) -> None:
    body = served.ok(path_of("summary", "all"))
    window = body["window"]
    assert window["prior_start"] is None
    assert window["prior_end"] is None
    assert window["partial"] is False
    for name in ("cost", "sessions", "tokens"):
        tile = body["tiles"][name]
        assert (tile["prior"], tile["change_pct"], tile["change_abs"]) == (
            None,
            None,
            None,
        )
    cache = body["tiles"]["cache_share"]
    assert (cache["prior"], cache["change_abs"]) == (None, None)
    assert body["tiles"]["cost"]["prior_unpriced"] is None


@pytest.mark.parametrize("project", [PROJECT, OTHER_PROJECT])
def test_a_partial_prior_nulls_every_change(served: Served, project: str) -> None:
    """The demo holds about 62 days, so 90 days has a prior that starts before it."""
    body = served.ok(path_of("summary", "90d", project))
    window = body["window"]
    assert window["partial"] is True
    assert window["prior_partial"] is True
    assert datetime.fromisoformat(window["oldest"]) > datetime.fromisoformat(
        window["prior_start"]
    )
    tiles = body["tiles"]
    for name in ("cost", "sessions", "tokens"):
        assert tiles[name]["change_pct"] is None
        assert tiles[name]["change_abs"] is None
    assert tiles["cache_share"]["change_abs"] is None
    # the prior stays, so the page can say what the partial prior was
    assert tiles["sessions"]["prior"] is not None
    assert tiles["cost"]["prior"] is not None
    # a whole prior keeps its changes (Driftwood has less history, so not for it)
    if project == PROJECT:
        whole = served.ok(path_of("summary", "30d", project))
        assert whole["window"]["prior_partial"] is False
        assert whole["window"]["partial"] is False
        assert whole["tiles"]["cost"]["change_pct"] is not None


def test_the_change_is_none_when_the_prior_is_zero(served: Served) -> None:
    """Today's prior is yesterday up to the same time, and a quiet window has none."""
    body = served.ok(path_of("summary", "today", OTHER_PROJECT))
    for name in ("cost", "sessions", "tokens"):
        tile = body["tiles"][name]
        if tile["prior"] == 0:
            assert tile["change_pct"] is None
        elif tile["prior"] is not None:
            assert tile["change_pct"] is not None


# ---------------------------------------------------------------------- cost chart


def test_the_chart_window_units_and_pager_on_the_newest_page(served: Served) -> None:
    units = {
        "today": "hour",
        "7d": "day",
        "30d": "day",
        "90d": "week",
        "12m": "month",
        "all": "week",  # the demo holds 62 days: more than 31, at most 13 weeks
    }
    for review_range, unit in units.items():
        body = served.ok(path_of("cost-chart", review_range))
        chart = body["chart"]
        assert chart["unit"] == unit
        assert chart["newest"] is True
        assert chart["has_later"] is False
        assert chart["later_reason"] == "newest"
        assert chart["start"] == body["window"]["start"]
        assert chart["end"] == body["window"]["end"]
        bars = body["bars"]
        assert bars[-1]["open"] is True
        assert [b["open"] for b in bars].count(True) == 1
        assert bars[0]["start"] == chart["start"]
        assert bars[-1]["end"] == chart["end"]
    thirty = served.ok(path_of("cost-chart", "30d"))
    assert thirty["chart"]["has_earlier"] is True
    assert thirty["chart"]["earlier_reason"] is None
    assert len(thirty["bars"]) == 30
    everything = served.ok(path_of("cost-chart", "all"))["chart"]
    assert (everything["has_earlier"], everything["has_later"]) == (False, False)
    assert everything["earlier_reason"] == "no_earlier_data"


def test_the_end_date_pages_back_by_one_window(served: Served) -> None:
    newest = served.ok(path_of("cost-chart", "7d"))
    previous_end = (date(2026, 10, 30) - timedelta(days=7)).isoformat()
    older = served.ok(path_of("cost-chart", "7d", end=previous_end))
    assert older["chart"]["newest"] is False
    assert older["chart"]["has_later"] is True
    assert older["chart"]["later_reason"] is None
    assert older["chart"]["end"] == newest["chart"]["start"]
    assert len(older["bars"]) == 7
    assert all(not bar["open"] for bar in older["bars"])
    assert older["etag"] != newest["etag"]
    # a date in the future is the newest page, and a date inside it is too
    assert (
        served.ok(path_of("cost-chart", "7d", end="2030-01-01"))["etag"]
        == (newest["etag"])
    )
    assert (
        served.ok(path_of("cost-chart", "7d", end="2026-10-30"))["etag"]
        == (newest["etag"])
    )
    # the last date of an earlier answer asks for the same page again
    again = served.ok(path_of("cost-chart", "7d", end=previous_end))
    assert again["etag"] == older["etag"]
    # all has one page
    assert (
        served.ok(path_of("cost-chart", "all", end="2026-01-01"))["chart"]["newest"]
        is True
    )


def test_an_earlier_page_before_the_oldest_request_has_no_records(
    served: Served,
) -> None:
    body = served.ok(path_of("cost-chart", "30d", end="2026-08-01"))
    assert body["chart"]["has_earlier"] is False
    assert body["chart"]["earlier_reason"] == "no_earlier_data"
    assert any(bar["no_records"] for bar in body["bars"])
    assert cost_sum(body["legend"]) == 0.0


def test_the_legend_keeps_every_model_and_the_bars_add_up(served: Served) -> None:
    body = served.ok(path_of("cost-chart", "30d"))
    legend = {row["model"]: row for row in body["legend"]}
    assert legend
    in_bars = {m for bar in body["bars"] for m in bar["by_model"]}
    assert in_bars == set(legend)
    for model, row in legend.items():
        from_bars = sum(
            bar["by_model"][model]["cost"] or 0.0
            for bar in body["bars"]
            if model in bar["by_model"]
        )
        assert from_bars == COST(row["cost"] or 0.0, abs=1e-9)
        assert row["requests"] == sum(
            bar["by_model"][model]["requests"]
            for bar in body["bars"]
            if model in bar["by_model"]
        )
        kinds = [
            sum(
                bar["by_model"][model]["kinds"][k]
                for bar in body["bars"]
                if model in bar["by_model"]
            )
            for k in ("input", "output", "cache_read", "cache_write")
        ]
        assert sum(kinds) == COST(row["cost"] or 0.0, abs=1e-9)


def test_y_ticks_are_nice_dollar_steps_up_to_the_tallest_bar(served: Served) -> None:
    for review_range in REVIEW_RANGES:
        body = served.ok(path_of("cost-chart", review_range))
        ticks = body["y_ticks"]
        tallest = max(
            sum((p["cost"] or 0.0) for p in bar["by_model"].values())
            for bar in body["bars"]
        )
        assert ticks[0] == 0
        assert ticks[-1] >= tallest
        assert 1 <= len(ticks) - 1 <= 5
        step = ticks[1] - ticks[0]
        assert [round(t - u, 9) for u, t in itertools.pairwise(ticks)] == [
            round(step, 9)
        ] * (len(ticks) - 1)
        mantissa = step / 10 ** math.floor(math.log10(step))
        assert round(mantissa, 6) in (1.0, 2.0, 5.0), step


@pytest.mark.parametrize(
    ("top", "ticks"),
    [
        (0.0, [0.0, 0.01]),
        (0.8, [0.0, 0.2, 0.4, 0.6, 0.8]),
        (1.0, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]),
        (4.2, [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]),
        (7.0, [0.0, 2.0, 4.0, 6.0, 8.0]),
        (12.5, [0.0, 5.0, 10.0, 15.0]),
        (101.0, [0.0, 50.0, 100.0, 150.0]),
        (0.034, [0.0, 0.01, 0.02, 0.03, 0.04]),
    ],
)
def test_y_ticks_unit(top: float, ticks: list[float]) -> None:
    assert review_answers.y_ticks(top) == ticks


# --------------------------------------------------------------------------- sessions


def test_sessions_page_by_cursor_with_stable_rows(served: Served) -> None:
    first = served.ok(path_of("sessions", "30d"))
    assert first["count"] >= 51
    rows = [s for day in first["days"] for s in day["sessions"]]
    assert len(rows) == 50
    assert first["next"] is not None
    second = served.ok(path_of("sessions", "30d", cursor=first["next"]))
    more = [s for day in second["days"] for s in day["sessions"]]
    assert len(rows) + len(more) == first["count"]
    assert {s["id"] for s in rows}.isdisjoint(s["id"] for s in more)
    assert second["next"] is None
    assert second["count"] == first["count"]
    assert second["etag"] != first["etag"]
    # one query of the cursor is cached on its own
    assert (
        served.ok(path_of("sessions", "30d", cursor=first["next"]))["etag"]
        == (second["etag"])
    )


def test_sessions_are_newest_first_and_grouped_by_local_day(served: Served) -> None:
    body = served.ok(path_of("sessions", "7d"))
    days = [day["day"] for day in body["days"]]
    assert days == sorted(days, reverse=True)
    assert len(days) == len(set(days))
    started = [s["started"] for day in body["days"] for s in day["sessions"]]
    assert body["count"] == len(started)
    assert body["next"] is None
    for day in body["days"]:
        assert day["sessions"]
        for session in day["sessions"]:
            assert session["state"] in {"working", "idle", "ended"}
            assert session["runs"] >= 0
            assert session["tokens"] > 0
            assert session["agents"]
            assert isinstance(session["unpriced"]["requests"], int)


def test_a_session_that_started_before_the_range_carries_its_whole_numbers(
    served: Served,
) -> None:
    for review_range in ("today", "7d", "30d"):
        rows = [
            s
            for day in served.ok(path_of("sessions", review_range))["days"]
            for s in day["sessions"]
        ]
        for row in rows:
            assert (row["whole"] is not None) == row["started_before_range"]
            if row["whole"] is not None:
                assert row["whole"]["tokens"] >= row["tokens"]
                assert row["whole"]["cost"] >= row["cost"] - 1e-9
    # an all-time list starts at the oldest request, so no row started before it
    first = served.ok(path_of("sessions", "all"))
    assert all(s["whole"] is None for day in first["days"] for s in day["sessions"])


def test_the_session_count_equals_the_summary_and_the_tile(served: Served) -> None:
    for review_range in REVIEW_RANGES:
        count = served.ok(path_of("sessions", review_range))["count"]
        summary = served.ok(path_of("summary", review_range))
        assert count == summary["session_count"]
        assert count == summary["tiles"]["sessions"]["value"]


# ---------------------------------------------------------------------- agents, models


def test_agents_ran_holds_every_agent_with_its_setup_and_its_runs(
    served: Served,
) -> None:
    body = served.ok(path_of("agents", "30d"))
    ran = body["ran"]
    keys = [row["agent"] for row in ran]
    assert len(keys) == len(set(keys))
    assert "@main" in keys
    costs = [row["cost"] for row in ran]
    assert costs == sorted(costs, reverse=True)
    by_key = {row["agent"]: row for row in ran}
    assert by_key["@main"]["scope"] == "main"
    assert by_key["@main"]["runs"] == 0
    for key, row in by_key.items():
        assert row["scope"] in {"user", "project", "main", "unnamed", "no_file"}
        assert row["requests"] > 0
        pairs = row["ran_pairs"]
        assert pairs == sorted(pairs, key=lambda p: -p["runs"])
        assert row["ran"]["mixed"] is (len(pairs) > 1)
        assert row["ran"]["model"] == pairs[0]["model"]
        if row["status"] is None:
            assert row["runs_as_set"] is None
            assert row["runs_not_as_set"] is None
        else:
            assert row["runs_as_set"] + row["runs_not_as_set"] == sum(
                p["runs"] for p in pairs
            )
        if row["set"] is None:
            assert row["set_reason"] in {"no_file", "sets_nothing"}
        else:
            assert row["set_reason"] is None
        if key not in ("@main", "@unnamed"):
            assert row["runs"] == sum(p["runs"] for p in pairs)
    assert any(row["status"] is not None for row in ran)
    never = body["never_ran"]
    assert not {row["agent"] for row in never} & set(keys)
    for row in never:
        assert row["scope"] in {"user", "project"}


def test_agents_share_and_the_old_oracle_runs(served: Served) -> None:
    ran = served.ok(path_of("agents", "30d"))["ran"]
    assert sum(row["share"] or 0 for row in ran) == COST(1.0)
    oracle = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "fixtures"
            / "oracle"
            / "demo"
            / f"usage-30d-{PROJECT}.json"
        ).read_text(encoding="utf-8")
    )["views"]["30d"]["by_agent"]
    old = {row["route_key"]: row for row in oracle}
    assert {row["agent"] for row in ran} == set(old)
    for row in ran:
        assert row["runs"] == old[row["agent"]]["runs"]
        assert row["sessions"] == old[row["agent"]]["sessions"]


def test_models_rows_kinds_and_legend_agree(served: Served) -> None:
    body = served.ok(path_of("models", "30d"))
    rows = body["rows"]
    assert rows
    assert [r["cost"] for r in rows] == sorted((r["cost"] for r in rows), reverse=True)
    assert [k["model"] for k in body["kinds"]] == [r["model"] for r in rows]
    assert sum(r["share"] or 0 for r in rows) == COST(1.0)
    agents = {row["agent"] for row in served.ok(path_of("agents", "30d"))["ran"]}
    for row, kinds in zip(rows, body["kinds"], strict=True):
        assert row["tokens"] > 0
        assert row["requests"] > 0
        assert 0 <= row["cache_share"] <= 1
        assert row["used_by"]
        assert set(row["used_by"]) <= agents
        assert row["unpriced"] == kinds["unpriced"]
        assert sum(
            kinds[k] for k in ("input", "output", "cache_read", "cache_write")
        ) == (COST(row["cost"] or 0.0, abs=1e-9))
    for kind in ("input", "output", "cache_read", "cache_write"):
        assert body["legend"][kind] == COST(sum(k[kind] for k in body["kinds"]))
    assert sum(body["legend"].values()) == COST(
        served.ok(path_of("summary", "30d"))["tiles"]["cost"]["value"]
    )


# ------------------------------------------------------------ nothing private leaves


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in cast("dict[object, object]", value).items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            yield from _strings(item)


def _private_texts(build: Path) -> tuple[set[str], set[str]]:
    """Return the cwd strings and a sample of message and description texts."""
    cwds: set[str] = set()
    texts: set[str] = set()
    for path in (build / "config" / "projects").rglob("*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = cast("dict[str, Any]", json.loads(line))
            if isinstance(row.get("cwd"), str):
                cwds.add(row["cwd"])
            message = cast("dict[str, Any]", row.get("message") or {})
            content = message.get("content")
            if isinstance(content, str) and len(content) >= 12:
                texts.add(content)
            elif isinstance(content, list):
                for part in cast("list[Any]", content):
                    text = (
                        cast("dict[str, Any]", part).get("text")
                        if isinstance(part, dict)
                        else None
                    )
                    if isinstance(text, str) and len(text) >= 12:
                        texts.add(text)
        if len(texts) > 200:
            break
    for path in build.rglob("*.md"):
        for found in re.findall(
            r"^description:\s*(.+)$", path.read_text(encoding="utf-8"), re.M
        ):
            if len(found.strip()) >= 8:
                texts.add(found.strip())
    return cwds, texts


def test_no_answer_carries_a_cwd_a_message_or_a_description(served: Served) -> None:
    cwds, texts = _private_texts(served.build)
    assert cwds
    assert texts
    seen = 0
    for project in (PROJECT, OTHER_PROJECT):
        for review_range in REVIEW_RANGES:
            for route in ROUTES:
                reply = served.get(path_of(route, review_range, project))
                assert reply.status_code == 200
                text = reply.text
                seen += 1
                assert str(served.build) not in text
                assert "cwd" not in text
                assert "description" not in text
                for cwd in cwds:
                    assert cwd not in text
                for private in texts:
                    assert private not in text
                for value in _strings(reply.json()):
                    assert not value.startswith(("/", "\\")), value
    assert seen == 60


# ------------------------------------------------------------------ setup failures


@pytest.mark.parametrize("error", [OSError("gone"), ValueError("bad rules")])
def test_a_setup_that_cannot_be_read_fails_its_cards_and_keeps_the_numbers(
    moving: Served, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    good = moving.ok(path_of("summary", "30d"))
    good_agents = moving.ok(path_of("agents", "30d"))
    assert good["errors"] == []

    def broken(*_args: object, **_kwargs: object) -> agent_setup.AgentSetup:
        raise error

    monkeypatch.setattr(agent_setup, "from_entries", broken)
    moving.provider._reviews = review_answers.ReviewCache()  # pyright: ignore[reportPrivateUsage]
    summary = moving.ok(path_of("summary", "30d"))
    assert summary["model_check"] is None
    assert summary["errors"] == [{"card": "model_check", "code": "setup_unreadable"}]
    assert summary["tiles"] == good["tiles"]
    assert summary["money"] == good["money"]
    assert summary["top_sessions"] == good["top_sessions"]
    agents = moving.ok(path_of("agents", "30d"))
    assert agents["errors"] == [{"card": "agent_setup", "code": "setup_unreadable"}]
    assert agents["never_ran"] == []
    assert len(agents["ran"]) == len(good_agents["ran"])
    for row, was in zip(agents["ran"], good_agents["ran"], strict=True):
        assert row["agent"] == was["agent"]
        assert row["set"] is None
        assert row["set_reason"] == "read_failed"
        assert row["status"] is None
        assert row["runs_as_set"] is None
        assert row["cost"] == was["cost"]
    assert {row["agent"]: row["scope"] for row in agents["ran"]}["@main"] == "main"
    # the cards that read no setup stay clean
    assert moving.ok(path_of("models", "30d"))["errors"] == []


def test_a_setup_read_that_raises_in_the_resolver_is_the_same_failure(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**_kwargs: object) -> list[Any]:
        raise OSError("gone")

    monkeypatch.setattr(store_provider.model_check, "resolve_entries", broken)
    summary = moving.ok(path_of("summary", "7d"))
    assert summary["model_check"] is None
    assert summary["errors"] == [{"card": "model_check", "code": "setup_unreadable"}]
    assert summary["tiles"]["cost"]["value"] > 0


# --------------------------------------------------------------------------- the cache


class Counter:
    """Counts the scans an answer makes."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        real = review_query.scan

        def counting(*args: Any, **kwargs: Any) -> review_query.Scan:
            self.calls += 1
            return real(*args, **kwargs)

        monkeypatch.setattr(review_query, "scan", counting)


def test_an_unchanged_store_is_not_scanned_twice(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = Counter(monkeypatch)
    first = moving.ok(path_of("agents", "30d"))
    assert counter.calls == 1
    again = moving.ok(path_of("agents", "30d"))
    assert counter.calls == 1
    assert again["etag"] == first["etag"]
    # the clock moved inside the same day, so the answer is the cached one
    moving.clock.set(moving.now + timedelta(minutes=3))
    moved = moving.ok(path_of("agents", "30d"))
    assert counter.calls == 1
    assert moved["server_time"] != first["server_time"]
    assert moved["etag"] == first["etag"]
    # another route, another range or another project is its own answer
    moving.ok(path_of("models", "30d"))
    moving.ok(path_of("agents", "7d"))
    moving.ok(path_of("agents", "30d", OTHER_PROJECT))
    assert counter.calls == 4


def test_a_new_ingest_pass_drops_the_cached_answer(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = Counter(monkeypatch)
    moving.ok(path_of("models", "30d"))
    assert counter.calls == 1
    real = review_answers.pass_marker

    def newer(conn: sqlite3.Connection) -> str:
        return "newer-" + str(real(conn))

    monkeypatch.setattr(review_answers, "pass_marker", newer)
    moving.ok(path_of("models", "30d"))
    assert counter.calls == 2
    moving.ok(path_of("models", "30d"))
    assert counter.calls == 2


def test_a_store_with_no_finished_pass_is_never_cached(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = Counter(monkeypatch)

    def none(_conn: sqlite3.Connection) -> None:
        return None

    monkeypatch.setattr(review_answers, "pass_marker", none)
    moving.ok(path_of("models", "30d"))
    moving.ok(path_of("models", "30d"))
    assert counter.calls == 2


def test_a_new_local_date_drops_the_cached_answer(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = Counter(monkeypatch)
    today = moving.ok(path_of("cost-chart", "today"))
    moving.ok(path_of("cost-chart", "today"))
    assert counter.calls == 1
    # 6 PM in New York plus seven hours is the next local day
    moving.clock.set(moving.now + timedelta(hours=7))
    tomorrow = moving.ok(path_of("cost-chart", "today"))
    assert counter.calls == 2
    assert tomorrow["window"]["start"] != today["window"]["start"]
    assert tomorrow["window"]["start"] > today["window"]["end"]


def test_a_new_price_table_drops_the_cached_answer(
    moving: Served, monkeypatch: pytest.MonkeyPatch
) -> None:
    counter = Counter(monkeypatch)
    provider = moving.provider
    moving.ok(path_of("models", "30d"))
    real = provider._pricer_and_hash  # pyright: ignore[reportPrivateUsage]

    def other(conn: Any) -> Any:
        pricer, _hash = real(conn)
        return pricer, "another-table"

    monkeypatch.setattr(provider, "_pricer_and_hash", other)
    moving.ok(path_of("models", "30d"))
    assert counter.calls == 2


def test_the_cache_keeps_the_last_thirty_two_answers() -> None:
    cache = review_answers.ReviewCache()

    def key(n: int) -> review_answers.CacheKey:
        return ("models", "p", "30d", str(n), date(2026, 10, 30), "m", "h")

    answer = cast("Summary", object())
    for n in range(32):
        cache.put(key(n), answer)
    assert len(cache) == 32
    assert cache.get(key(0)) is answer  # used, so key 1 is now the oldest
    cache.put(key(32), answer)
    assert len(cache) == 32
    assert cache.get(key(1)) is None
    assert cache.get(key(0)) is answer
    assert cache.get(key(32)) is answer
    assert review_answers.CACHE_SIZE == 32
