"""Tests for the flow demo mode, the data clock in ``/api/app`` and the clock flags.

The server runs in store mode on a built ``live_flow`` scenario. The data clock is
fixed, a rate clock, or a test clock, while the wall clock keeps the access keys.
"""

import json
import shutil
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from conftest import PORT

import main
import serve
from access import AccessState
from data_clock import DataClock

OpenClient = Callable[..., AbstractContextManager[Any]]
BUSY_NOW = datetime(2026, 10, 30, 22, 40, tzinfo=UTC)
JSON = {"Content-Type": "application/json"}


class Wall:
    """Epoch seconds the test moves by hand."""

    def __init__(self, at: float) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at

    def advance(self, seconds: float) -> None:
        self.at += seconds


@dataclass
class Flow:
    """One server over a built scenario."""

    settings: main.Settings
    state: AccessState
    session: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Bartab-Key": self.state.read_key}


def make_flow(  # noqa: PLR0913 - test wiring, keyword-only tail
    tmp_path: Path,
    dist_dir: Path,
    built: Path,
    clock: DataClock,
    *,
    test_clock: bool = False,
    wall: Callable[[], float] = time.time,
) -> Flow:
    state = AccessState(clock=wall)
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        clock=wall,
        access_state=state,
        claude_dir=built / "config",
        store_dir=tmp_path / "store",
        flow=True,
        data_clock=clock,
        test_clock=test_clock,
        price_fetch=False,
    )
    session = json.loads((built / "flow.json").read_text(encoding="utf-8"))["session"]
    return Flow(settings, state, session)


def get(client: Any, flow: Flow, path: str) -> Any:
    reply = client.get(path, headers=flow.headers)
    assert reply.status_code == 200, reply.text
    return reply.json()


def wait_done(client: Any, flow: Flow) -> Any:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        info = get(client, flow, "/api/app")
        if info["ingest"]["state"] == "done":
            return info
        time.sleep(0.05)
    pytest.fail("timed out")


def wait_running(client: Any, flow: Flow) -> Any:
    """Poll until the flow session shows in ``running[]``.

    The provider caches the project mapping for 5 s of wall time, and the first read
    can come before the store has any sessions, so ``running[]`` can lag ``done``.
    """
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        info = get(client, flow, "/api/app")
        if flow.session in [item["session"] for item in info["running"]]:
            return info
        time.sleep(0.05)
    pytest.fail("the flow session never showed as running")


def set_clock(client: Any, flow: Flow, body: object) -> Any:
    return client.post("/api/dev/clock", headers={**flow.headers, **JSON}, json=body)


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


# ------------------------------------------------------------------ flow mode


def test_flow_reaches_done_on_busy_with_the_fixed_clock(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    flow = make_flow(
        tmp_path, dist_dir, built, DataClock.fixed(serve.scenario_now(built))
    )
    with open_client(main.create_app(flow.settings)) as client:
        wait_done(client, flow)
        info = wait_running(client, flow)
    assert info["mode"] == "flow"
    assert info["clock"] == {"kind": "fixed", "rate_n": None}
    assert parse(info["server_time"]) == BUSY_NOW
    assert parse(info["as_of"]) == BUSY_NOW
    assert info["claude_version"] == "2.1.310"
    assert [item["session"] for item in info["running"]].count(flow.session) == 1
    held = next(item for item in info["running"] if item["session"] == flow.session)
    assert held["project"] == "tidewater-reporting"


def test_the_clock_decides_which_sessions_are_running(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    clock = DataClock.test(BUSY_NOW)
    flow = make_flow(tmp_path, dist_dir, built, clock)
    with open_client(main.create_app(flow.settings)) as client:
        wait_done(client, flow)
        wait_running(client, flow)
        clock.set(BUSY_NOW + timedelta(hours=2))
        later = get(client, flow, "/api/app")
        assert flow.session not in [item["session"] for item in later["running"]]
        assert parse(later["as_of"]) == BUSY_NOW + timedelta(hours=2)
        clock.set(BUSY_NOW)
        assert flow.session in [
            item["session"] for item in get(client, flow, "/api/app")["running"]
        ]


def test_the_rate_clock_runs_from_the_session_start_and_holds_at_the_end(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    start = serve.session_start(built)
    assert datetime(2026, 10, 30, 22, 10, tzinfo=UTC) <= start < BUSY_NOW
    wall = Wall(time.time())
    clock = DataClock.rate(start, 60, serve.scenario_now(built), wall)
    flow = make_flow(tmp_path, dist_dir, built, clock)
    with open_client(main.create_app(flow.settings)) as client:
        first = wait_done(client, flow)
        wait_running(client, flow)
        assert first["clock"] == {"kind": "rate", "rate_n": 60}
        assert start <= parse(first["server_time"]) < start + timedelta(minutes=5)
        before = parse(first["server_time"])
        wall.advance(10)
        later = get(client, flow, "/api/app")
        assert parse(later["server_time"]) >= before + timedelta(minutes=10)
        assert parse(later["server_time"]) < BUSY_NOW
        assert later["etag"] != first["etag"]
        wall.advance(3600)
        held = get(client, flow, "/api/app")
        assert parse(held["server_time"]) == BUSY_NOW
        assert parse(held["as_of"]) == BUSY_NOW
        assert flow.session in [item["session"] for item in held["running"]]


def test_the_data_clock_does_not_move_the_access_keys(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    wall = Wall(time.time())
    flow = make_flow(tmp_path, dist_dir, built, DataClock.fixed(BUSY_NOW), wall=wall)
    code = flow.state.mint_code(None)
    fresh = flow.state.mint_code(None)
    with open_client(main.create_app(flow.settings)) as client:
        wait_done(client, flow)
        wall.advance(121)
        expired = client.post("/api/access/swap", json={"code": code}, headers=JSON)
        assert expired.status_code == 403
        assert expired.json()["code"] == "code_expired"
        info = get(client, flow, "/api/app")
        assert parse(info["server_time"]) == BUSY_NOW
        assert fresh != code


# ------------------------------------------------------------------ dev clock


def test_the_dev_clock_sets_t(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    clock = DataClock.test(serve.scenario_now(built))
    flow = make_flow(tmp_path, dist_dir, built, clock, test_clock=True)
    with open_client(main.create_app(flow.settings)) as client:
        first = wait_done(client, flow)
        wait_running(client, flow)
        assert first["clock"] == {"kind": "test", "rate_n": None}
        moved = set_clock(client, flow, {"now": "2026-10-30T18:20:00-04:00"})
        assert moved.status_code == 200, moved.text
        body = moved.json()
        assert body["kind"] == "test"
        assert parse(body["now"]) == datetime(2026, 10, 30, 22, 20, tzinfo=UTC)
        info = get(client, flow, "/api/app")
        assert parse(info["server_time"]) == datetime(2026, 10, 30, 22, 20, tzinfo=UTC)
        assert parse(info["as_of"]) == datetime(2026, 10, 30, 22, 20, tzinfo=UTC)
        assert info["etag"] != first["etag"]
        assert flow.session in [item["session"] for item in info["running"]]


def test_the_dev_clock_refuses_a_time_without_an_offset(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    clock = DataClock.test(BUSY_NOW)
    flow = make_flow(tmp_path, dist_dir, built, clock, test_clock=True)
    with open_client(main.create_app(flow.settings)) as client:
        for body in (
            {"now": "2026-10-30T22:20:00"},
            {"now": "not a time"},
            {"now": 5},
            {},
            {"now": "2026-10-30T22:20:00Z", "extra": 1},
        ):
            reply = set_clock(client, flow, body)
            assert reply.status_code == 422, body
            assert reply.json()["code"] == "invalid_request"
        assert clock.now() == BUSY_NOW


def test_the_dev_clock_sits_behind_the_read_key(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    clock = DataClock.test(BUSY_NOW)
    flow = make_flow(tmp_path, dist_dir, built, clock, test_clock=True)
    body = {"now": "2026-10-30T22:20:00Z"}
    with open_client(main.create_app(flow.settings)) as client:
        assert client.post("/api/dev/clock", json=body, headers=JSON).status_code == 401
        wrong = {"X-Bartab-Key": "wrong", **JSON}
        assert (
            client.post("/api/dev/clock", json=body, headers=wrong).status_code == 401
        )
    assert clock.now() == BUSY_NOW


def test_the_dev_clock_route_does_not_exist_without_the_flag(
    open_client: OpenClient,
    tmp_path: Path,
    dist_dir: Path,
    flow_build: Callable[[str], Path],
) -> None:
    built = flow_build("busy")
    flow = make_flow(tmp_path, dist_dir, built, DataClock.test(BUSY_NOW))
    with open_client(main.create_app(flow.settings)) as client:
        reply = set_clock(client, flow, {"now": "2026-10-30T22:20:00Z"})
        assert reply.status_code == 404
    schema = main.build_app(flow.settings).openapi()
    assert "/api/dev/clock" not in schema["paths"]


def test_the_test_clock_flag_needs_a_test_clock(
    tmp_path: Path, dist_dir: Path, flow_build: Callable[[str], Path]
) -> None:
    built = flow_build("busy")
    flow = make_flow(
        tmp_path, dist_dir, built, DataClock.fixed(BUSY_NOW), test_clock=True
    )
    with pytest.raises(ValueError, match="test data clock"):
        main.build_app(flow.settings)


# ------------------------------------------------------------------ serve flags


def args_for(tmp_path: Path, *flags: str) -> serve.Args:
    return serve.parse_args(["--data", str(tmp_path / "d"), *flags])


def test_the_flow_flags_parse(tmp_path: Path) -> None:
    flow = args_for(tmp_path, "--flow", "busy")
    assert flow.flow == "busy"
    assert flow.clock_rate is None
    assert not flow.test_clock
    rate = args_for(tmp_path, "--flow", "many", "--clock-rate", "30")
    assert (rate.flow, rate.clock_rate) == ("many", 30)
    test = args_for(tmp_path, "--flow", "empty", "--test-clock")
    assert test.test_clock
    assert args_for(tmp_path, "--demo", "--test-clock").test_clock
    plain = args_for(tmp_path)
    assert plain.flow is None
    assert not plain.test_clock


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (["--flow", "busy", "--demo"], "--flow and --demo"),
        (["--flow", "busy", "--claude-dir", "/work/c"], "--flow and --claude-dir"),
        (["--flow", "busy", "--ingest-pace-ms", "30"], "--flow and --ingest-pace-ms"),
        (["--clock-rate", "30"], "--clock-rate is for the flow demo only"),
        (["--demo", "--clock-rate", "30"], "--clock-rate is for the flow demo only"),
        (["--flow", "busy", "--clock-rate", "0"], "--clock-rate must be above zero"),
        (["--flow", "busy", "--clock-rate", "-2"], "--clock-rate must be above zero"),
        (["--test-clock"], "--test-clock is for the flow or demo build only"),
        (
            ["--flow", "busy", "--clock-rate", "30", "--test-clock"],
            "--clock-rate and --test-clock can't be used together",
        ),
        (["--flow", "nope"], "invalid choice"),
    ],
)
def test_the_flow_flag_refusals(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    flags: list[str],
    message: str,
) -> None:
    with pytest.raises(SystemExit) as err:
        args_for(tmp_path, *flags)
    assert err.value.code == 2
    assert message in capsys.readouterr().err


# ------------------------------------------------------------------ the build


def test_ensure_flow_builds_once_and_rebuilds_a_half_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: object) -> None:
        calls.append(argv)
        out = Path(argv[3])
        assert not (out / "config" / "old.txt").exists()
        (out / "config").mkdir(parents=True)
        (out / serve.FLOW_MARKER).write_text("{}", encoding="utf-8")

    stale = tmp_path / "flow-busy" / "config"
    stale.mkdir(parents=True)
    (stale / "old.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    first = serve.ensure_flow(tmp_path, "busy")
    second = serve.ensure_flow(tmp_path, "busy")
    assert first == second == tmp_path / "flow-busy"
    assert len(calls) == 1
    assert calls[0][0] == sys.executable
    assert calls[0][1] == "-B"
    assert calls[0][2] == str(serve.FLOW_BUILDER)
    assert calls[0][4] == "busy"


def test_a_built_scenario_gives_each_clock(
    tmp_path: Path, flow_build: Callable[[str], Path]
) -> None:
    shutil.copytree(flow_build("busy"), tmp_path / "flow-busy")
    out = serve.ensure_flow(tmp_path, "busy")
    fixed = serve.flow_clock(args_for(tmp_path, "--flow", "busy"), out)
    assert fixed is not None
    assert (fixed.kind, fixed.now()) == ("fixed", BUSY_NOW)
    rate = serve.flow_clock(
        args_for(tmp_path, "--flow", "busy", "--clock-rate", "30"), out
    )
    assert rate is not None
    assert (rate.kind, rate.rate_n) == ("rate", 30)
    test = serve.flow_clock(args_for(tmp_path, "--flow", "busy", "--test-clock"), out)
    assert test is not None
    assert (test.kind, test.now()) == ("test", BUSY_NOW)
    assert serve.flow_clock(args_for(tmp_path, "--demo"), out) is None


def test_the_demo_test_clock_starts_at_the_demo_clock(
    tmp_path: Path, demo_build: Path
) -> None:
    clock = serve.flow_clock(args_for(tmp_path, "--demo", "--test-clock"), demo_build)
    assert clock is not None
    assert clock.kind == "test"
    assert clock.now() == datetime(2026, 10, 30, 22, 0, tzinfo=UTC)


def test_a_failed_flow_build_exits_with_one(
    tmp_path: Path, dist_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    def boom(_data: Path, _scenario: str) -> Path:
        raise OSError(28, "disk full")

    monkeypatch.setattr(serve, "ensure_flow", boom)
    args = serve.parse_args(
        ["--data", str(tmp_path / "d"), "--flow", "busy", "--dist", str(dist_dir)]
    )
    assert asyncio.run(serve.run(args)) == 1


def test_the_flow_store_defaults_beside_the_build_and_the_store_flag_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flow_build: Callable[[str], Path]
) -> None:
    import asyncio

    built = flow_build("busy")

    def fake_build(_data: Path, _scenario: str) -> Path:
        return built

    monkeypatch.setattr(serve, "ensure_flow", fake_build)
    plain = asyncio.run(serve.prepare_world(args_for(tmp_path, "--flow", "busy")))
    assert plain is not None
    assert plain.claude_dir == built / "config"
    assert plain.store == built / "store"
    assert plain.data_clock is not None
    assert plain.data_clock.kind == "fixed"
    other = tmp_path / "elsewhere"
    chosen = asyncio.run(
        serve.prepare_world(args_for(tmp_path, "--flow", "busy", "--store", str(other)))
    )
    assert chosen is not None
    assert chosen.store == other
