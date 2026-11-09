"""Command line entry that runs the Bar Tab server.

``serve.py --port N --data DIR --launch-fd 3 --project-dir PATH [--fixture NAME]``
serves the fixture scenario. With ``--demo`` or ``--claude-dir PATH`` it serves the
store instead (``--store PATH``, default ``DIR/store``), fills it from the Claude
folder and runs the price feed. ``--demo`` builds the demo set into ``DIR/demo`` when
it is not there and reads ``DIR/demo/config``. ``--ingest-pace-ms N`` slows the demo
ingest so first run is watchable and is refused without ``--demo``. ``--flow SCENARIO``
(busy, many, unlinked, empty) builds a ``live_flow`` scenario into ``DIR/flow-SCENARIO``
and serves it the way ``--demo`` does, with the data clock fixed at the scenario's
``now``. ``--clock-rate N`` (with ``--flow``) runs that clock N times real time from the
session start and holds at the scenario clock. ``--test-clock`` (with ``--flow`` or
``--demo``) mounts ``POST /api/dev/clock``, which sets the data clock. ``--flow`` is
refused with ``--demo``, ``--claude-dir`` and ``--ingest-pace-ms``, and ``--clock-rate``
and ``--test-clock`` refuse each other. ``--no-price-fetch``
(or ``BARTAB_OFFLINE=1``) turns the live price fetch off. The server binds
127.0.0.1, starts uvicorn, then writes ``DIR/server.json`` (mode 0600) and one
JSON launch line to the launch fd, and closes that fd. SIGTERM and SIGINT stop uvicorn
the normal way, so the lifespan shutdown runs and logs ``shutdown complete``. The
server stops by itself after ``--idle-exit-minutes`` with no request (0 turns that
off), and it removes ``server.json`` on a clean stop.
"""

import argparse
import asyncio
import contextlib
import errno
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Generator, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

import fixture_provider
import platform_os
import store_paths
import write_guard
from access import AccessState
from data_clock import DataClock
from gate import GateMiddleware
from main import Settings, create_app, make_provider

logger = logging.getLogger("bartab.serve")

HOST = "127.0.0.1"
DEFAULT_IDLE_MINUTES = 30.0
FORBIDDEN_PORT = 8377
DEFAULT_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_BUILDER = REPO_ROOT / "tests" / "fixtures" / "demo" / "build_demo.py"
FLOW_BUILDER = REPO_ROOT / "tests" / "fixtures" / "live_flow" / "build_flow.py"
FLOW_SCENARIOS = ("busy", "many", "unlinked", "empty")
FLOW_BUILD_SECONDS = 180
FLOW_MARKER = "flow.json"
SESSION_JSON = "session.json"
DEMO_NOW = "2026-10-30T18:00"
DEMO_TZ = "America/New_York"
DEMO_BUILD_SECONDS = 120
OFFLINE_ENV = "BARTAB_OFFLINE"
SERVER_JSON = "server.json"
RUN_FOLDER = "run"
TMP_FOLDER = "tmp"
_IDLE_POLL_SECONDS = 1.0
_GRACEFUL_SHUTDOWN_SECONDS = 3


@dataclass(frozen=True)
class Args:
    """Parsed command line."""

    port: int
    data: Path
    launch_fd: int | None
    project_dir: Path | None
    fixture: str
    idle_exit_minutes: float
    dist: Path
    claude_dir: Path | None = None
    store: Path | None = None
    demo: bool = False
    ingest_pace_ms: int = 0
    no_price_fetch: bool = False
    flow: str | None = None
    clock_rate: float | None = None
    test_clock: bool = False
    real: bool = False


def real_folders(
    parser: argparse.ArgumentParser,
) -> tuple[Path, Path]:
    """Work out ``<config>`` and the store root for ``--real``, or exit with an error.

    ``<config>`` is ``CLAUDE_CONFIG_DIR``, else ``$HOME/.claude`` (``store_paths``). It
    must be absolute, so the folder never depends on the working folder.

    Args:
        parser: The parser that reports the error.

    Returns:
        ``(<config>, <store root>)``, both normalised.
    """
    config = store_paths.config_dir_default()
    if not config.is_absolute():
        parser.error(
            "--real needs an absolute Claude folder: set CLAUDE_CONFIG_DIR to an "
            "absolute path"
        )
    config = Path(os.path.normpath(config))
    return config, store_paths.shared_store_root(config)


def _given(ns: argparse.Namespace) -> dict[str, bool]:
    """Say which of the flags ``--real`` refuses were given."""
    return {
        "--data": ns.data is not None,
        "--claude-dir": ns.claude_dir is not None,
        "--store": ns.store is not None,
        "--demo": ns.demo,
        "--flow": ns.flow is not None,
        "--fixture": ns.fixture is not None,
        "--test-clock": ns.test_clock,
        "--clock-rate": ns.clock_rate is not None,
        "--ingest-pace-ms": ns.ingest_pace_ms is not None,
    }


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Parse the command line.

    Args:
        argv: Arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(prog="serve.py", description="Run the server.")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--data", type=Path, default=None, help="data folder")
    parser.add_argument("--launch-fd", type=int, default=None)
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--fixture", choices=fixture_provider.SCENARIOS, default=None)
    parser.add_argument("--idle-exit-minutes", type=float, default=DEFAULT_IDLE_MINUTES)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST_DIR)
    parser.add_argument("--claude-dir", type=Path, default=None)
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--ingest-pace-ms", type=int, default=None)
    parser.add_argument("--no-price-fetch", action="store_true")
    parser.add_argument("--flow", choices=FLOW_SCENARIOS, default=None)
    parser.add_argument("--clock-rate", type=float, default=None)
    parser.add_argument("--test-clock", action="store_true")
    parser.add_argument("--real", action="store_true")
    ns = parser.parse_args(argv)
    if ns.port == FORBIDDEN_PORT:
        parser.error(f"port {FORBIDDEN_PORT} is reserved and is never used")
    offline = ns.no_price_fetch or os.environ.get(OFFLINE_ENV) == "1"
    if ns.real:
        for flag, given in _given(ns).items():
            if given:
                parser.error(f"--real can't be used with {flag}")
        config, root = real_folders(parser)
        return Args(
            port=ns.port,
            data=root / RUN_FOLDER,
            launch_fd=ns.launch_fd,
            project_dir=ns.project_dir,
            fixture="demo",
            idle_exit_minutes=ns.idle_exit_minutes,
            dist=ns.dist,
            claude_dir=config,
            store=root,
            no_price_fetch=offline,
            real=True,
        )
    if ns.data is None:
        parser.error("--data is required unless --real is given")
    if ns.ingest_pace_ms is not None and ns.ingest_pace_ms < 0:
        parser.error("--ingest-pace-ms must not be negative")
    _check_flow_flags(parser, ns)
    if ns.ingest_pace_ms and not ns.demo:
        parser.error("--ingest-pace-ms is for the demo build only, add --demo")
    if ns.demo and ns.claude_dir is not None:
        parser.error("--demo and --claude-dir can't be used together")
    return Args(
        port=ns.port,
        data=ns.data,
        launch_fd=ns.launch_fd,
        project_dir=ns.project_dir,
        fixture=ns.fixture or "demo",
        idle_exit_minutes=ns.idle_exit_minutes,
        dist=ns.dist,
        claude_dir=ns.claude_dir,
        store=ns.store,
        demo=ns.demo,
        ingest_pace_ms=ns.ingest_pace_ms or 0,
        no_price_fetch=offline,
        flow=ns.flow,
        clock_rate=ns.clock_rate,
        test_clock=ns.test_clock,
    )


def _check_flow_flags(parser: argparse.ArgumentParser, ns: argparse.Namespace) -> None:
    """Refuse the flag mixes the flow and clock flags do not allow."""
    if ns.flow is not None:
        for flag, bad in (
            ("--demo", ns.demo),
            ("--claude-dir", ns.claude_dir is not None),
            ("--ingest-pace-ms", bool(ns.ingest_pace_ms)),
        ):
            if bad:
                parser.error(f"--flow and {flag} can't be used together")
    if ns.clock_rate is not None:
        if ns.flow is None:
            parser.error("--clock-rate is for the flow demo only, add --flow")
        if ns.clock_rate <= 0:
            parser.error("--clock-rate must be above zero")
    if ns.test_clock and ns.flow is None and not ns.demo:
        parser.error("--test-clock is for the flow or demo build only, add --flow")
    if ns.test_clock and ns.clock_rate is not None:
        parser.error("--clock-rate and --test-clock can't be used together")


def make_real_folders(config: Path, root: Path) -> Path:
    """Make the folders real mode needs, and return the tmp folder.

    This runs before the write guard, because the guard refuses a folder outside the
    store root. Only a missing folder is made, one level at a time, mode 0700, and
    never ``config`` itself: ``routing-dashboard`` (the old app's folder, made only
    when it is not there, as the launcher does), the store root, ``run`` and ``tmp``.

    Args:
        config: The Claude config folder, which must exist.
        root: The store root, ``<config>/routing-dashboard/bartab``.

    Returns:
        The tmp folder, ``<root>/tmp``.

    Raises:
        OSError: When a folder can't be made, or one of them is not a folder.
    """
    for folder in (root.parent, root, root / RUN_FOLDER, root / TMP_FOLDER):
        platform_os.mkdir_private(folder)
        if not folder.is_dir():
            raise NotADirectoryError(errno.ENOTDIR, "not a folder")
    return root / TMP_FOLDER


def enter_real_mode(args: Args) -> bool:
    """Lock the process to the store root, before anything opens a file.

    Sets ``sys.dont_write_bytecode``, makes the folders, points ``TMPDIR`` and
    ``tempfile.tempdir`` at ``<store root>/tmp/`` and installs the write guard. A
    missing Claude folder is not created: the server stops instead.

    Args:
        args: The parsed command line, with ``--real`` set.

    Returns:
        True when the guard is on, False after logging why the server can't start.
    """
    config, root = args.claude_dir, args.store
    if config is None or root is None:
        raise ValueError("real mode needs both folders")  # noqa: TRY003
    sys.dont_write_bytecode = True
    if not config.is_dir():
        logger.error("the Claude folder does not exist")
        return False
    try:
        tmp = make_real_folders(config, root)
    except OSError:
        logger.error("could not make the Bar Tab folders")  # noqa: TRY400
        return False
    os.environ["TMPDIR"] = str(tmp)
    tempfile.tempdir = str(tmp)
    write_guard.install(root)
    return True


def ensure_demo(data: Path) -> Path:
    """Build the demo set into ``data/demo`` unless it is built, and return its config.

    The builder writes ``truth.json`` last, so that file marks a finished build. A
    folder left by an interrupted build is removed and built again.

    Args:
        data: The data folder.

    Returns:
        The demo's Claude config folder, ``data/demo/config``.
    """
    out = data / "demo"
    if not (out / "truth.json").is_file():
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-B",
                str(DEMO_BUILDER),
                str(out),
                "--now",
                DEMO_NOW,
                "--tz",
                DEMO_TZ,
            ],
            check=True,
            timeout=DEMO_BUILD_SECONDS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
    return out / "config"


def ensure_flow(data: Path, scenario: str) -> Path:
    """Build a ``live_flow`` scenario into ``data/flow-<scenario>`` unless it is built.

    The builder writes ``flow.json`` last, so that file marks a finished build. A
    folder left by an interrupted build is removed and built again.

    Args:
        data: The data folder.
        scenario: One of ``FLOW_SCENARIOS``.

    Returns:
        The built folder, which holds ``config/``, ``session.json`` and ``flow.json``.
    """
    out = data / f"flow-{scenario}"
    if not (out / FLOW_MARKER).is_file():
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run(  # noqa: S603
            [sys.executable, "-B", str(FLOW_BUILDER), str(out), scenario],
            check=True,
            timeout=FLOW_BUILD_SECONDS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )
    return out


def _read_json(path: Path) -> dict[str, object]:
    found = cast("object", json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(found, dict):
        raise ValueError("not a JSON object")  # noqa: TRY003, TRY004
    return cast("dict[str, object]", found)


def scenario_now(out: Path) -> datetime:
    """Read the built scenario's clock, ``now`` in its ``session.json``.

    Args:
        out: The built demo or flow folder.

    Returns:
        The clock as an aware UTC time.
    """
    text = _read_json(out / SESSION_JSON).get("now")
    if not isinstance(text, str):
        raise ValueError("session.json has no now")  # noqa: TRY003, TRY004
    at = datetime.fromisoformat(text)
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    return at.astimezone(UTC)


def session_start(out: Path) -> datetime:
    """Return the time of the flow session's earliest request.

    The session is the one ``flow.json`` names. Its main file and its subagent files
    are read, and the earliest row that carries token usage wins.

    Args:
        out: The built flow folder.

    Returns:
        The earliest request time as an aware UTC time.
    """
    session = _read_json(out / FLOW_MARKER).get("session")
    if not isinstance(session, str):
        raise ValueError("flow.json has no session")  # noqa: TRY003, TRY004
    files = [
        *(out / "config" / "projects").glob(f"*/{session}.jsonl"),
        *(out / "config" / "projects").glob(f"*/{session}/subagents/*.jsonl"),
    ]
    earliest: datetime | None = None
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if '"usage"' not in line:
                continue
            row = cast("object", json.loads(line))
            if not isinstance(row, dict):
                continue
            stamp = cast("dict[str, object]", row).get("timestamp")
            if isinstance(stamp, str):
                at = datetime.fromisoformat(stamp)
                if earliest is None or at < earliest:
                    earliest = at
    if earliest is None:
        raise ValueError("the flow session has no request")  # noqa: TRY003
    return earliest.astimezone(UTC)


def flow_clock(args: Args, out: Path) -> DataClock | None:
    """Pick the data clock for a flow or demo build, or None for the real clock.

    Args:
        args: The parsed command line.
        out: The built flow or demo folder.

    Returns:
        A rate clock with ``--clock-rate``, a test clock with ``--test-clock``, a
        fixed clock for ``--flow``, else None.
    """
    if args.flow is None:
        return DataClock.test(scenario_now(out)) if args.test_clock else None
    end = scenario_now(out)
    if args.clock_rate is not None:
        return DataClock.rate(session_start(out), args.clock_rate, end)
    if args.test_clock:
        return DataClock.test(end)
    return DataClock.fixed(end)


class ActivityMiddleware:
    """Remember when the last HTTP request arrived, for the idle exit."""

    def __init__(
        self, app: ASGIApp, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Wrap an ASGI app.

        Args:
            app: The app to wrap.
            clock: Seconds source for the last-request time.
        """
        self.app = app
        self.clock = clock
        self.last = clock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call."""
        if scope["type"] == "http":
            self.last = self.clock()
        await self.app(scope, receive, send)


def create_tracked_app(
    settings: Settings, clock: Callable[[], float] = time.monotonic
) -> tuple[ASGIApp, ActivityMiddleware]:
    """Build the app with the activity tracker behind the gate.

    A request the gate refuses never reaches the tracker, so a stray or hostile
    client cannot keep an idle server alive.

    Args:
        settings: Port, folders, fixture name and clock.
        clock: Seconds source for the last-request time.

    Returns:
        The gate-fronted app and the tracker that sits behind the gate.
    """
    gated = create_app(settings)
    if not isinstance(gated, GateMiddleware):
        raise TypeError("create_app must return the gate")  # noqa: TRY003
    tracker = ActivityMiddleware(gated.app, clock)
    gated.app = tracker
    return gated, tracker


@dataclass(frozen=True)
class ServerInfo:
    """The facts ``server.json`` records."""

    port: int
    pid: int
    instance: str
    mint_secret: str
    started: str


def write_server_json(data_dir: Path, info: ServerInfo) -> Path:
    """Write ``server.json`` atomically with mode 0600.

    Args:
        data_dir: The data folder.
        info: The facts to record. The file also holds an empty ``owners`` list.

    Returns:
        The path of the file.
    """
    target = data_dir / SERVER_JSON
    payload: dict[str, object] = {**asdict(info), "owners": []}
    fd, tmp_name = tempfile.mkstemp(dir=data_dir, prefix=".server-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(tmp_name).chmod(0o600)
        Path(tmp_name).replace(target)
    except BaseException:
        with contextlib.suppress(OSError):
            Path(tmp_name).unlink()
        raise
    return target


def remove_server_json(data_dir: Path, pid: int) -> None:
    """Remove ``server.json`` when it still belongs to this process.

    Args:
        data_dir: The data folder.
        pid: This process id.
    """
    target = data_dir / SERVER_JSON
    try:
        current = cast("object", json.loads(target.read_text(encoding="utf-8")))
        if isinstance(current, dict):
            found = cast("dict[str, object]", current).get("pid")
            if found == pid:
                target.unlink()
    except (OSError, ValueError):
        return


def emit_launch_line(fd: int, payload: dict[str, object]) -> None:
    """Write one JSON line to the launch fd and close it.

    Args:
        fd: The file descriptor the launcher passed.
        payload: The launch line fields.
    """
    line = (json.dumps(payload) + "\n").encode("utf-8")
    try:
        view = memoryview(line)
        while view:
            view = view[os.write(fd, view) :]
    except OSError:
        logger.warning("could not write the launch line")
    finally:
        with contextlib.suppress(OSError):
            os.close(fd)


def bind_socket(port: int) -> socket.socket:
    """Bind a listening socket on 127.0.0.1.

    Args:
        port: The port, or 0 for a free one.

    Returns:
        The bound socket.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
    except OSError:
        sock.close()
        raise
    return sock


class _Server(uvicorn.Server):
    """Uvicorn server that handles signals itself and exits cleanly."""

    @contextlib.contextmanager
    def capture_signals(self) -> Generator[None, None, None]:
        """Turn SIGINT and SIGTERM into a normal shutdown, with no re-raise."""
        if threading.current_thread() is not threading.main_thread():
            yield
            return
        loop = asyncio.get_running_loop()
        handled = (signal.SIGINT, signal.SIGTERM)
        for sig in handled:
            loop.add_signal_handler(sig, self.handle_exit, sig, None)
        try:
            yield
        finally:
            for sig in handled:
                loop.remove_signal_handler(sig)


async def watch_idle(
    server: uvicorn.Server,
    tracker: ActivityMiddleware,
    limit_seconds: float,
    poll_seconds: float = _IDLE_POLL_SECONDS,
) -> None:
    """Stop the server once no request has arrived for ``limit_seconds``.

    Args:
        server: The running server.
        tracker: The activity tracker in front of the app.
        limit_seconds: Idle time that triggers the stop.
        poll_seconds: How often to check.
    """
    while not server.should_exit:
        await asyncio.sleep(poll_seconds)
        if tracker.clock() - tracker.last >= limit_seconds:
            logger.info("idle limit reached, stopping")
            server.should_exit = True


@dataclass(frozen=True)
class World:
    """What the demo, flow or Claude folder flags resolve to."""

    claude_dir: Path | None
    store: Path | None
    data_clock: DataClock | None


async def prepare_world(args: Args) -> World | None:
    """Build the demo or flow set when asked, and pick the folders and data clock.

    Args:
        args: The parsed command line.

    Returns:
        The resolved world, or None after logging why the build or the clock failed.
    """
    claude_dir = args.claude_dir
    store = args.store
    built: Path | None = None
    try:
        if args.demo:
            claude_dir = await asyncio.to_thread(ensure_demo, args.data)
            built = claude_dir.parent
        elif args.flow is not None:
            built = await asyncio.to_thread(ensure_flow, args.data, args.flow)
            claude_dir = built / "config"
            store = store or built / "store"
    except (OSError, subprocess.SubprocessError):
        logger.error("could not build the demo set")  # noqa: TRY400
        return None
    if built is None:
        return World(claude_dir, store, None)
    try:
        data_clock = await asyncio.to_thread(flow_clock, args, built)
    except (OSError, ValueError):
        logger.error("could not read the scenario clock")  # noqa: TRY400
        return None
    return World(claude_dir, store, data_clock)


async def run(args: Args) -> int:
    """Start the server and run it until it stops.

    Args:
        args: The parsed command line.

    Returns:
        The process exit code.
    """
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    world = await prepare_world(args)
    if world is None:
        return 1
    state = AccessState()
    try:
        sock = bind_socket(args.port)
    except OSError:
        logger.error("could not bind %s:%d", HOST, args.port)  # noqa: TRY400
        return 1
    port = int(sock.getsockname()[1])
    settings = Settings(
        port=port,
        data_dir=args.data,
        dist_dir=args.dist,
        fixture=args.fixture,
        project_dir=args.project_dir,
        idle_exit_minutes=args.idle_exit_minutes,
        access_state=state,
        claude_dir=world.claude_dir,
        store_dir=world.store,
        demo=args.demo,
        flow=args.flow is not None,
        real=args.real,
        data_clock=world.data_clock,
        test_clock=args.test_clock,
        ingest_pace_ms=args.ingest_pace_ms,
        price_fetch=not args.no_price_fetch,
    )
    provider = make_provider(settings)
    project = provider.resolve_project(
        args.project_dir, first_if_none=args.demo or args.flow is not None
    )
    settings = replace(settings, provider=provider)
    app, tracker = create_tracked_app(settings)
    config = uvicorn.Config(
        app,
        host=HOST,
        port=port,
        http="h11",
        ws="none",
        lifespan="on",
        proxy_headers=False,
        log_config=None,
        log_level="info",
        access_log=False,
        server_header=False,
        timeout_graceful_shutdown=_GRACEFUL_SHUTDOWN_SECONDS,
    )
    server = _Server(config)
    pid = os.getpid()
    serving = asyncio.create_task(server.serve(sockets=[sock]))
    watcher: asyncio.Task[None] | None = None
    try:
        while not server.started and not serving.done():  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        if not server.started:
            await serving
            return 1
        write_server_json(
            args.data,
            ServerInfo(
                port=port,
                pid=pid,
                instance=state.instance,
                mint_secret=state.mint_secret,
                started=datetime.now(UTC).isoformat(),
            ),
        )
        if args.launch_fd is not None:
            emit_launch_line(
                args.launch_fd,
                {
                    "port": port,
                    "pid": pid,
                    "instance": state.instance,
                    "code": state.mint_code(project),
                    "project": project,
                },
            )
        if args.idle_exit_minutes > 0:
            watcher = asyncio.create_task(
                watch_idle(server, tracker, args.idle_exit_minutes * 60)
            )
        await serving
    except SystemExit as err:
        return int(err.code) if isinstance(err.code, int) else 1
    finally:
        if watcher is not None:
            watcher.cancel()
        remove_server_json(args.data, pid)
        sock.close()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server from the command line.

    Args:
        argv: Arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The process exit code.
    """
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = parse_args(argv)
    if args.real and not enter_real_mode(args):
        return 1
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
