"""Tests for the store provider and the serve flags that switch it on.

The server runs in store mode on a copy of the demo build, with a clock the test
moves by hand and the live price fetch off (the network guard covers the rest).
"""

import asyncio
import shutil
import sqlite3
import sys
import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
from conftest import PORT

import main
import price_feed
import price_transport
import serve
import store
import store_provider
import store_writer
from access import AccessState
from store_paths import StoreLayout

OpenClient = Callable[..., AbstractContextManager[Any]]
NOW = h.T0 + timedelta(minutes=10)


class MovingClock:
    """Epoch seconds the test moves by hand."""

    def __init__(self, start: datetime = NOW) -> None:
        self.now = start.timestamp()

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingTransport:
    """A price transport that records its calls and never answers."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        del timeout, max_bytes
        self.urls.append(url)
        raise price_transport.FetchError("fetch_failed")


@dataclass
class World:
    """One server in store mode over its own copy of the demo build."""

    root: Path
    claude_dir: Path
    settings: main.Settings
    state: AccessState
    clock: MovingClock

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Bartab-Key": self.state.read_key}

    @property
    def store(self) -> Path:
        return self.root / "store"


def wait_for(check: Callable[[], bool], seconds: float = 30.0) -> None:
    """Poll until ``check`` is true, or fail with a timeout."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.05)
    pytest.fail("timed out")


def make_world(
    tmp_path: Path,
    dist_dir: Path,
    source: Path | None,
    *,
    price_fetch: bool = False,
    transport: price_transport.Transport | None = None,
) -> World:
    claude_dir = tmp_path / "demo" / "config"
    if source is not None:
        shutil.copytree(source, tmp_path / "demo")
    state = AccessState()
    clock = MovingClock()
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        clock=clock,
        access_state=state,
        claude_dir=claude_dir,
        store_dir=tmp_path / "store",
        demo=True,
        price_fetch=price_fetch,
        transport=transport,
    )
    return World(tmp_path, claude_dir, settings, state, clock)


@pytest.fixture
def world(tmp_path: Path, dist_dir: Path, demo_build: Path) -> World:
    return make_world(tmp_path, dist_dir, demo_build)


def get(client: Any, world: World, path: str) -> Any:
    reply = client.get(path, headers=world.headers)
    assert reply.status_code == 200, reply.text
    return reply.json()


def app_info(client: Any, world: World) -> Any:
    return get(client, world, "/api/app")


def wait_done(client: Any, world: World) -> Any:
    wait_for(lambda: app_info(client, world)["ingest"]["state"] == "done", 60)
    return app_info(client, world)


def tidewater_folder(claude_dir: Path) -> str:
    return next(
        p.name for p in (claude_dir / "projects").iterdir() if "tidewater" in p.name
    )


def test_store_mode_reaches_done_with_real_counts_and_history(
    open_client: OpenClient, world: World
) -> None:
    with open_client(main.create_app(world.settings)) as client:
        info = wait_done(client, world)
    ingest = info["ingest"]
    assert ingest["files_total"] > 0
    assert ingest["files_done"] == ingest["files_total"]
    assert ingest["bytes_total"] > 0
    assert ingest["bytes_done"] == ingest["bytes_total"]
    assert ingest["error"] is None
    assert ingest["retrying"] is False
    assert info["history"]["first_ingest"] is not None
    assert info["history"]["oldest"] is not None
    assert info["history"]["last_backup"] is not None
    assert info["as_of"] is not None
    assert info["claude_version"] == "2.1.310"
    assert info["to_fix_count"] is None
    assert info["editable_projects"] == []
    assert info["etag"].startswith("1-")


def test_the_first_poll_before_the_store_exists_says_waiting(
    tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    world = make_world(tmp_path, dist_dir, demo_build)
    provider = main.make_provider(world.settings)
    assert isinstance(provider, store_provider.StoreProvider)
    info = provider.app_info("abcd1234", None)
    assert info.ingest.state == "waiting"
    assert info.ingest.files_total is None
    assert info.as_of is None
    assert info.history.first_ingest is None
    assert provider.projects().projects
    assert provider.prices().source == "bundled"


def test_projects_lists_the_mapped_projects(
    open_client: OpenClient, world: World
) -> None:
    with open_client(main.create_app(world.settings)) as client:
        wait_done(client, world)
        listed = get(client, world, "/api/projects")["projects"]
    states = {row["key"]: row["state"] for row in listed}
    assert states == {
        "tidewater-reporting": "ok",
        "driftwood": "ok",
        "harbor-light": "no_claude_folder",
        "saltmarsh": "ok",
        "lantern": "folder_not_found",
    }
    assert not any(row["running"] for row in listed)


def test_prices_answer_from_the_bundled_copy_with_fetch_off(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    transport = RecordingTransport()
    world = make_world(tmp_path, dist_dir, demo_build, transport=transport)
    with open_client(main.create_app(world.settings)) as client:
        wait_done(client, world)
        prices = get(client, world, "/api/prices")
        again = get(client, world, "/api/prices")
    assert prices["source"] == "bundled"
    assert prices["as_of"]
    assert prices["models"]
    assert prices == again
    assert transport.urls == []


def test_the_price_feed_runs_when_the_fetch_is_on(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    transport = RecordingTransport()
    world = make_world(
        tmp_path, dist_dir, demo_build, price_fetch=True, transport=transport
    )
    with open_client(main.create_app(world.settings)) as client:
        wait_for(lambda: len(transport.urls) >= 1)
        wait_done(client, world)
        prices = get(client, world, "/api/prices")
    assert prices["source"] == "bundled"


class FakeWriter:
    """A writer that keeps its ready callbacks until the test fires them."""

    def __init__(self) -> None:
        self.callbacks: list[Callable[[], None]] = []
        self.starts = 0
        self.stops = 0

    def on_ready(self, callback: Callable[[], None]) -> None:
        self.callbacks.append(callback)

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def become_ready(self) -> None:
        for callback in self.callbacks:
            callback()


class FakeFeed:
    def __init__(self) -> None:
        self.starts = 0
        self.stops = 0

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1


def fake_provider(
    tmp_path: Path, *, hold_seconds: float = 0.0
) -> tuple[store_provider.StoreProvider, FakeWriter, FakeFeed]:
    layout = StoreLayout(tmp_path / "store")
    writer = FakeWriter()
    feed = FakeFeed()
    provider = store_provider.StoreProvider(
        layout=layout,
        claude_dir=tmp_path / "config",
        writer=writer,  # pyright: ignore[reportArgumentType]
        price_settings=price_feed.PriceSettings(layout=layout),
        feed=feed,  # pyright: ignore[reportArgumentType]
        hold_seconds=hold_seconds,
    )
    return provider, writer, feed


def test_the_feed_starts_only_when_the_writer_says_the_store_is_ready(
    tmp_path: Path,
) -> None:
    provider, writer, feed = fake_provider(tmp_path)
    provider.start()
    assert writer.starts == 1
    assert feed.starts == 0
    writer.become_ready()
    assert feed.starts == 1
    provider.stop()
    assert feed.stops == 1
    assert writer.stops == 1


def test_the_feed_waits_for_the_writer_through_the_hold(tmp_path: Path) -> None:
    provider, writer, feed = fake_provider(tmp_path, hold_seconds=3600)
    provider.start()
    assert writer.starts == 0  # held back
    assert feed.starts == 0
    assert len(writer.callbacks) == 1
    provider.stop()
    assert writer.starts == 0
    assert feed.starts == 0
    assert feed.stops == 1


def test_a_stop_before_the_store_is_ready_means_the_feed_never_starts(
    tmp_path: Path,
) -> None:
    provider, writer, feed = fake_provider(tmp_path)
    provider.start()
    provider.stop()
    writer.become_ready()  # a startup that finished just after the stop
    assert feed.starts == 0
    assert all(t.name != "price_feed" for t in threading.enumerate())


def test_a_provider_without_a_feed_registers_no_callback(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "store")
    writer = FakeWriter()
    provider = store_provider.StoreProvider(
        layout=layout,
        claude_dir=tmp_path / "config",
        writer=writer,  # pyright: ignore[reportArgumentType]
        price_settings=price_feed.PriceSettings(layout=layout),
    )
    provider.start()
    provider.stop()
    assert writer.callbacks == []


def test_the_real_feed_does_not_read_the_store_before_the_writer_migrated_it(
    tmp_path: Path, demo_build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shutil.copytree(demo_build, tmp_path / "demo")
    entered = threading.Event()
    release = threading.Event()
    first_read = threading.Event()
    reads: list[tuple[bool, bool]] = []  # (migration released, requests table exists)
    real_migrate = store.migrate
    real_open_read = store_provider.open_read

    def held_migrate(conn: sqlite3.Connection, **kw: Any) -> int:
        entered.set()
        assert release.wait(30)
        return real_migrate(conn, **kw)

    def watching_open_read(layout: StoreLayout) -> sqlite3.Connection:
        conn = real_open_read(layout)
        if threading.current_thread().name == "price_feed":
            found = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name = 'requests'"
            ).fetchone()
            reads.append((release.is_set(), found is not None))
            first_read.set()
        return conn

    monkeypatch.setattr(store, "migrate", held_migrate)
    monkeypatch.setattr(store_provider, "open_read", watching_open_read)
    transport = RecordingTransport()
    provider = store_provider.create(
        claude_dir=tmp_path / "demo" / "config",
        store_dir=tmp_path / "store",
        demo=True,
        pace_ms=0,
        price_fetch=True,
        transport=transport,
        clock=MovingClock(),
    )
    try:
        provider.start()
        assert entered.wait(30)  # the writer is inside migrate, the store is empty
        assert not any(t.name == "price_feed" for t in threading.enumerate())
        release.set()
        assert first_read.wait(30)
        wait_for(lambda: len(transport.urls) >= 1)
    finally:
        release.set()
        provider.stop()
    assert reads
    assert all(released and found for released, found in reads)


def test_a_store_failure_after_first_run_keeps_the_first_failure_time(
    tmp_path: Path, demo_build: Path
) -> None:
    shutil.copytree(demo_build, tmp_path / "demo")
    claude_dir = tmp_path / "demo" / "config"
    layout = StoreLayout(tmp_path / "store")
    clock = MovingClock()
    writer = store_writer.StoreWriter(
        layout, claude_dir, clock=lambda: datetime.fromtimestamp(clock(), tz=UTC)
    )
    provider = store_provider.StoreProvider(
        layout=layout,
        claude_dir=claude_dir,
        writer=writer,
        price_settings=price_feed.PriceSettings(layout=layout),
        clock=clock,
    )

    def unwritable(_conn: sqlite3.Connection) -> None:
        raise OSError(28, "no space left on device")

    try:
        writer.tick()
        assert provider.app_info("test", None).history.pass_error is None
        failed_at = datetime.fromtimestamp(clock(), tz=UTC)
        writer.submit(unwritable)
        writer.tick()  # a store_ code tears the connection down: no meta row
        first = provider.app_info("test", None).history.pass_error
        assert first is not None
        assert first.code == "store_unwritable"
        assert first.since == failed_at
        clock.advance(7)
        second = provider.app_info("test", None).history.pass_error
        clock.advance(3600)
        third = provider.app_info("test", None).history.pass_error
        assert second is not None
        assert third is not None
        assert second.since == failed_at
        assert third.since == failed_at
        clock.advance(300)
        writer.tick()  # the retry works, so the error and its time clear
        assert provider.app_info("test", None).history.pass_error is None
    finally:
        writer.stop()


def test_etag_changes_after_new_transcript_rows_and_the_session_is_running(
    open_client: OpenClient, world: World
) -> None:
    with open_client(main.create_app(world.settings)) as client:
        before = wait_done(client, world)
        folder = tidewater_folder(world.claude_dir)
        path = world.claude_dir / "projects" / folder / f"{h.S3}.jsonl"
        path.write_bytes(
            h.assistant(60, "msg-new-1", sid=h.S3, cwd=None, req="req-new-1") + b"\n"
        )
        world.clock.advance(11)
        wait_for(lambda: app_info(client, world)["etag"] != before["etag"])
        after = app_info(client, world)
        listed = get(client, world, "/api/projects")["projects"]
    assert after["as_of"] != before["as_of"] or after["etag"] != before["etag"]
    assert {"project": "tidewater-reporting", "session": h.S3} in after["running"]
    assert next(r for r in listed if r["key"] == "tidewater-reporting")["running"]
    assert after["ingest"]["state"] == "done"


def test_a_later_pass_failure_leaves_state_done_and_sets_pass_error(
    open_client: OpenClient, world: World
) -> None:
    with open_client(main.create_app(world.settings)) as client:
        wait_done(client, world)
        (world.claude_dir / "projects").rename(world.claude_dir / "projects-gone")
        world.clock.advance(11)
        wait_for(lambda: app_info(client, world)["history"]["pass_error"] is not None)
        info = app_info(client, world)
        assert info["ingest"]["state"] == "done"
        assert info["ingest"]["error"] is None
        assert info["history"]["pass_error"]["code"] == "config_dir_missing"
        assert info["history"]["first_ingest"] is not None
        (world.claude_dir / "projects-gone").rename(world.claude_dir / "projects")
        world.clock.advance(15)
        wait_for(lambda: app_info(client, world)["history"]["pass_error"] is None)


def test_mint_nudges_a_failed_ingest_to_retry(
    open_client: OpenClient, tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    world = make_world(tmp_path, dist_dir, None)
    world.claude_dir.mkdir(parents=True)
    with open_client(main.create_app(world.settings)) as client:
        wait_for(lambda: app_info(client, world)["ingest"]["state"] == "failed")
        failed = app_info(client, world)["ingest"]
        assert failed["error"]["code"] == "config_dir_missing"
        assert failed["retry_at"] is not None
        shutil.copytree(
            demo_build / "config" / "projects", world.claude_dir / "projects"
        )
        reply = client.post(
            "/api/access/mint",
            json={"project": None},
            headers={"X-Bartab-Mint": world.state.mint_secret},
        )
        assert reply.status_code == 200
        info = wait_done(client, world)
    assert info["ingest"]["error"] is None


def test_a_paced_demo_holds_the_writer_back_so_counting_shows(
    open_client: OpenClient, world: World
) -> None:
    world.settings = replace(world.settings, ingest_pace_ms=1)
    with open_client(main.create_app(world.settings)) as client:
        first = app_info(client, world)["ingest"]
        assert first["state"] == "waiting"
        assert first["files_total"] is None
        info = wait_done(client, world)
    assert info["ingest"]["files_total"] > 0


def test_stopping_during_the_hold_never_starts_the_writer(
    open_client: OpenClient, world: World
) -> None:
    world.settings = replace(world.settings, ingest_pace_ms=1)
    with open_client(main.create_app(world.settings)) as client:
        assert app_info(client, world)["ingest"]["state"] == "waiting"
    assert not (world.store / "bartab.db").exists()


def test_the_lifespan_stops_the_writer_and_releases_the_store(
    open_client: OpenClient, world: World
) -> None:
    with open_client(main.create_app(world.settings)) as client:
        wait_done(client, world)
    handle = store_provider.store_writer.platform_os.try_lock_exclusive(
        world.store / "writer.lock"
    )
    assert handle is not None
    handle.release()


def test_resolve_project_matches_a_path_or_a_slug(
    tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    world = make_world(tmp_path, dist_dir, demo_build)
    provider = main.make_provider(world.settings)
    assert provider.resolve_project(None) is None
    assert (
        provider.resolve_project(tmp_path / "demo" / "projects" / "driftwood")
        == "driftwood"
    )
    assert provider.resolve_project(Path("/work/Tidewater Reporting")) == (
        "tidewater-reporting"
    )
    assert provider.resolve_project(Path("/work/elsewhere")) is None


def test_resolve_project_falls_back_to_the_first_project_only_when_asked(
    tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    world = make_world(tmp_path, dist_dir, demo_build)
    provider = main.make_provider(world.settings)
    elsewhere = Path("/work/elsewhere")
    assert provider.resolve_project(elsewhere) is None
    assert provider.resolve_project(elsewhere, first_if_none=True) == (
        "tidewater-reporting"
    )
    assert provider.resolve_project(None, first_if_none=True) is None
    assert (
        provider.resolve_project(
            tmp_path / "demo" / "projects" / "driftwood", first_if_none=True
        )
        == "driftwood"
    )


def test_the_demo_version_is_empty_without_a_session_file(tmp_path: Path) -> None:
    assert store_provider.demo_claude_version(tmp_path / "config") == ""
    (tmp_path / "session.json").write_text("[]", encoding="utf-8")
    assert store_provider.demo_claude_version(tmp_path / "config") == ""
    (tmp_path / "session.json").write_text('{"claude_version": 3}', encoding="utf-8")
    assert store_provider.demo_claude_version(tmp_path / "config") == ""


def test_a_claude_dir_that_is_not_the_demo_reports_no_version(
    tmp_path: Path, dist_dir: Path, demo_build: Path
) -> None:
    world = make_world(tmp_path, dist_dir, demo_build)
    settings = main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        claude_dir=world.claude_dir,
        store_dir=tmp_path / "store2",
        clock=world.clock,
        price_fetch=False,
    )
    provider = main.make_provider(settings)
    assert provider.app_info("abcd1234", None).claude_version == ""


# ------------------------------------------------------------------ serve flags


def args_for(tmp_path: Path, *flags: str) -> serve.Args:
    return serve.parse_args(["--data", str(tmp_path / "d"), *flags])


def test_the_new_flags_parse(tmp_path: Path) -> None:
    args = args_for(
        tmp_path,
        "--demo",
        "--ingest-pace-ms",
        "30",
        "--no-price-fetch",
        "--store",
        str(tmp_path / "s"),
    )
    assert args.demo
    assert args.ingest_pace_ms == 30
    assert args.no_price_fetch
    assert args.store == tmp_path / "s"
    plain = args_for(tmp_path)
    assert not plain.demo
    assert plain.claude_dir is None
    assert not plain.no_price_fetch


def test_ingest_pace_without_demo_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as err:
        args_for(tmp_path, "--ingest-pace-ms", "30")
    assert err.value.code == 2
    assert "--ingest-pace-ms is for the demo build only" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        args_for(tmp_path, "--demo", "--ingest-pace-ms", "-1")


def test_demo_and_claude_dir_exclude_each_other(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        args_for(tmp_path, "--demo", "--claude-dir", str(tmp_path))
    assert args_for(tmp_path, "--claude-dir", str(tmp_path)).claude_dir == tmp_path


def test_bartab_offline_turns_the_price_fetch_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BARTAB_OFFLINE", "1")
    assert args_for(tmp_path).no_price_fetch
    monkeypatch.setenv("BARTAB_OFFLINE", "0")
    assert not args_for(tmp_path).no_price_fetch


def test_ensure_demo_builds_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: object) -> None:
        calls.append(argv)
        out = Path(argv[3])
        (out / "config").mkdir(parents=True)
        (out / "truth.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    first = serve.ensure_demo(tmp_path)
    second = serve.ensure_demo(tmp_path)
    assert first == second == tmp_path / "demo" / "config"
    assert len(calls) == 1
    assert calls[0][4:] == ["--now", serve.DEMO_NOW, "--tz", serve.DEMO_TZ]
    assert calls[0][0] == sys.executable


def test_ensure_demo_rebuilds_an_interrupted_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "demo" / "config"
    stale.mkdir(parents=True)
    (stale / "old.txt").write_text("x", encoding="utf-8")

    def fake_run(argv: list[str], **_kw: object) -> None:
        assert not (Path(argv[3]) / "config" / "old.txt").exists()
        (Path(argv[3]) / "truth.json").parent.mkdir(parents=True, exist_ok=True)
        (Path(argv[3]) / "truth.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(serve.subprocess, "run", fake_run)
    serve.ensure_demo(tmp_path)
    assert (tmp_path / "demo" / "truth.json").is_file()


def test_a_failed_demo_build_exits_with_one(
    tmp_path: Path, dist_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_data: Path) -> Path:
        raise OSError(28, "disk full")

    monkeypatch.setattr(serve, "ensure_demo", boom)
    args = serve.parse_args(
        ["--data", str(tmp_path / "d"), "--demo", "--dist", str(dist_dir)]
    )
    assert asyncio.run(serve.run(args)) == 1


def test_a_read_before_the_migrations_finish_sees_an_empty_store(
    tmp_path: Path,
) -> None:
    layout = StoreLayout(tmp_path / "store")
    layout.db.parent.mkdir(parents=True)
    raw = sqlite3.connect(layout.db, isolation_level=None)
    raw.execute("PRAGMA journal_mode = WAL")
    raw.execute("CREATE TABLE half_made (x INTEGER)")
    raw.close()
    conn = store_provider.open_read(layout)
    try:
        assert store.user_version(conn) == store.latest_version()
        assert conn.execute("SELECT COUNT(*) FROM requests").fetchone() == (0,)
    finally:
        conn.close()


def test_a_read_of_a_migrated_store_uses_the_file(tmp_path: Path) -> None:
    layout = StoreLayout(tmp_path / "store")
    layout.db.parent.mkdir(parents=True)
    raw = sqlite3.connect(layout.db, isolation_level=None)
    store.migrate(raw)
    raw.execute("CREATE TABLE marker (x INTEGER)")
    raw.close()
    conn = store_provider.open_read(layout)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'marker'"
        ).fetchone() == (1,)
    finally:
        conn.close()


def test_one_reader_sees_one_snapshot_even_when_the_writer_commits_between_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "snap.sqlite"
    writer_conn = sqlite3.connect(db, isolation_level=None)
    writer_conn.execute("PRAGMA journal_mode=WAL")
    writer_conn.execute("CREATE TABLE t (x INTEGER)")
    writer_conn.execute("INSERT INTO t VALUES (1)")

    def open_snapshot_db(_layout: StoreLayout) -> sqlite3.Connection:
        return sqlite3.connect(db, isolation_level=None)

    monkeypatch.setattr(store_provider, "open_read", open_snapshot_db)
    layout = StoreLayout(tmp_path / "store")
    provider = store_provider.StoreProvider(
        layout=layout,
        claude_dir=tmp_path / "config",
        writer=FakeWriter(),  # pyright: ignore[reportArgumentType]
        price_settings=price_feed.PriceSettings(layout=layout),
    )
    with provider._reader() as conn:  # pyright: ignore[reportPrivateUsage]
        first = conn.execute("SELECT count(*) FROM t").fetchone()[0]
        writer_conn.execute("INSERT INTO t VALUES (2)")
        second = conn.execute("SELECT count(*) FROM t").fetchone()[0]
        assert conn.in_transaction
    writer_conn.close()
    assert (first, second) == (1, 1)
