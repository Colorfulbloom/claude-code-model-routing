"""Command line entry that runs the Bar Tab server.

``serve.py --port N --data DIR --launch-fd 3 --project-dir PATH [--fixture NAME]``
binds 127.0.0.1, starts uvicorn, then writes ``DIR/server.json`` (mode 0600) and one
JSON launch line to the launch fd, and closes that fd. SIGTERM and SIGINT stop uvicorn
the normal way, so the lifespan shutdown runs and logs ``shutdown complete``. The
server stops by itself after ``--idle-exit-minutes`` with no request (0 turns that
off), and it removes ``server.json`` on a clean stop.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import os
import signal
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Generator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import uvicorn
from starlette.types import ASGIApp, Receive, Scope, Send

import fixture_provider
from access import AccessState
from gate import GateMiddleware
from main import Settings, create_app

logger = logging.getLogger("bartab.serve")

HOST = "127.0.0.1"
DEFAULT_IDLE_MINUTES = 30.0
FORBIDDEN_PORT = 8377
DEFAULT_DIST_DIR = Path(__file__).resolve().parent.parent / "web" / "dist"
SERVER_JSON = "server.json"
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


def parse_args(argv: Sequence[str] | None = None) -> Args:
    """Parse the command line.

    Args:
        argv: Arguments without the program name. Defaults to ``sys.argv[1:]``.

    Returns:
        The parsed arguments.
    """
    parser = argparse.ArgumentParser(prog="serve.py", description="Run the server.")
    parser.add_argument("--port", type=int, default=0, help="0 picks a free port")
    parser.add_argument("--data", type=Path, required=True, help="data folder")
    parser.add_argument("--launch-fd", type=int, default=None)
    parser.add_argument("--project-dir", type=Path, default=None)
    parser.add_argument("--fixture", choices=fixture_provider.SCENARIOS, default="demo")
    parser.add_argument("--idle-exit-minutes", type=float, default=DEFAULT_IDLE_MINUTES)
    parser.add_argument("--dist", type=Path, default=DEFAULT_DIST_DIR)
    ns = parser.parse_args(argv)
    if ns.port == FORBIDDEN_PORT:
        parser.error(f"port {FORBIDDEN_PORT} is reserved and is never used")
    return Args(
        port=ns.port,
        data=ns.data,
        launch_fd=ns.launch_fd,
        project_dir=ns.project_dir,
        fixture=ns.fixture,
        idle_exit_minutes=ns.idle_exit_minutes,
        dist=ns.dist,
    )


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


async def run(args: Args) -> int:
    """Start the server and run it until it stops.

    Args:
        args: The parsed command line.

    Returns:
        The process exit code.
    """
    args.data.mkdir(parents=True, exist_ok=True, mode=0o700)
    state = AccessState()
    try:
        sock = bind_socket(args.port)
    except OSError:
        logger.error("could not bind %s:%d", HOST, args.port)  # noqa: TRY400
        return 1
    port = int(sock.getsockname()[1])
    project = fixture_provider.FixtureProvider(args.fixture).resolve_project(
        args.project_dir
    )
    settings = Settings(
        port=port,
        data_dir=args.data,
        dist_dir=args.dist,
        fixture=args.fixture,
        project_dir=args.project_dir,
        idle_exit_minutes=args.idle_exit_minutes,
        access_state=state,
    )
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
    return asyncio.run(run(parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
