"""Shared pytest fixtures for the Bar Tab server tests."""

import asyncio
import ipaddress
import os
import socket
import subprocess
import sys
from collections.abc import Awaitable, Callable, Generator, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Message

import main
from access import AccessState

PORT = 47123

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_BUILDER = REPO_ROOT / "tests" / "fixtures" / "demo" / "build_demo.py"
# The demo build every M1 test reads. Same arguments give the same bytes, and the
# oracle recorder in app/oracle uses the same pair.
DEMO_NOW = "2026-10-30T18:00"
DEMO_TZ = "America/New_York"
FLOW_BUILDER = REPO_ROOT / "tests" / "fixtures" / "live_flow" / "build_flow.py"
FLOW_SCENARIOS = ("busy", "many", "unlinked", "empty")


# Real-data guard. Tests never read the owner's Claude folder. The real folder is
# worked out once, before any fixture moves HOME, and an audit hook refuses any open
# under it for the rest of the process. Audit hooks cannot be removed, so the hook is
# installed once per process and stays cheap: a string check, no file system calls.
def _real_config_dirs() -> tuple[str, ...]:
    found: list[str] = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    home = os.environ.get("HOME")
    # os.path on purpose: the audit hook below compares plain strings, so the
    # prefixes are built the way it normalises a path, with no file system calls.
    claude = os.path.join(home, ".claude") if home else None  # noqa: PTH118
    for raw in (env, claude):
        if not raw:
            continue
        for candidate in {os.path.abspath(raw), os.path.realpath(raw)}:  # noqa: PTH100
            found.append(candidate.rstrip(os.sep) + os.sep)
    real_json = os.path.join(home, ".claude.json") if home else None  # noqa: PTH118
    if real_json:
        found.append(os.path.abspath(real_json))  # noqa: PTH100
    return tuple(sorted(set(found)))


# A test that does `from conftest import X` loads this file a second time under the
# bare name. The guard must be set up once per process: the second copy reuses the
# first copy's prefixes and installs nothing, or its realpath on the real folder would
# trip the first copy's stat wrapper.
_GUARD_KEY = "_bartab_real_data_guard"
_installed: tuple[str, ...] | None = getattr(sys, _GUARD_KEY, None)
REAL_CONFIG_PREFIXES: tuple[str, ...] = (
    _installed if _installed is not None else _real_config_dirs()
)


# Audit events that name a path in args[0]. os.stat and os.lstat raise no audit event
# (checked on 3.13), so they are wrapped below instead.
_GUARDED_EVENTS = frozenset(
    {"open", "os.listdir", "os.scandir", "os.walk", "sqlite3.connect"}
)


def _refuse_real(target: object) -> None:
    if isinstance(target, os.PathLike):
        target = cast("str | bytes", os.fspath(cast("os.PathLike[str]", target)))
    if isinstance(target, bytes):
        target = target.decode("utf-8", "replace")
    if not isinstance(target, str) or target.startswith("file:"):
        if isinstance(target, str):  # a sqlite3 URI: file:/path?mode=ro
            target = target[5:].split("?", 1)[0]
        else:
            return
    if not target or target == ":memory:":
        return
    full = os.path.abspath(target)  # noqa: PTH100 - string only, runs on every call
    for prefix in REAL_CONFIG_PREFIXES:
        if full == prefix.rstrip(os.sep) or full.startswith(prefix):
            msg = (
                f"real-data guard: tests must not open the real Claude folder ({full})"
            )
            raise RuntimeError(msg)


def _real_data_audit(event: str, args: tuple[object, ...]) -> None:
    if event in _GUARDED_EVENTS and args:
        _refuse_real(args[0])


_real_stat = os.stat
_real_lstat = os.lstat


def _guarded_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
    _refuse_real(path)
    return _real_stat(path, *args, **kwargs)


def _guarded_lstat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
    _refuse_real(path)
    return _real_lstat(path, *args, **kwargs)


# pathlib, os.path.exists and isdir look os.stat up at call time, so they go through
# the wrapper too. C code that calls stat directly does not.
if _installed is None:
    sys.addaudithook(_real_data_audit)
    os.stat = _guarded_stat
    os.lstat = _guarded_lstat
    setattr(sys, _GUARD_KEY, REAL_CONFIG_PREFIXES)

# Tests import old-app modules (dashboard/, agent_md.py, the demo builder). Without
# this, Python writes cpython-313 __pycache__ folders beside them, outside app/.
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"


@pytest.fixture(scope="session")
def real_config_prefixes() -> tuple[str, ...]:
    """The real Claude folder paths the audit hook refuses."""
    return REAL_CONFIG_PREFIXES


@pytest.fixture(autouse=True, scope="session")
def fake_home(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Point HOME and CLAUDE_CONFIG_DIR at a temp folder for the whole session."""
    home = tmp_path_factory.mktemp("home")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("HOME", str(home))
        patch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
        yield home


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _loopback_only(address: object) -> None:
    """Refuse any socket address that is not loopback or a Unix socket."""
    if isinstance(address, (str, bytes)):
        return
    if isinstance(address, tuple) and address:
        host = str(cast("tuple[object, ...]", address)[0])
        if host in {"127.0.0.1", "::1", "localhost"}:
            return
    msg = f"network guard: tests must not reach the network ({address!r})"
    raise RuntimeError(msg)


def _guarded_connect(self: socket.socket, address: object) -> None:
    _loopback_only(address)
    _real_connect(self, address)  # pyright: ignore[reportArgumentType]


def _guarded_connect_ex(self: socket.socket, address: object) -> int:
    _loopback_only(address)
    return _real_connect_ex(self, address)  # pyright: ignore[reportArgumentType]


def _loopback_host(host: object) -> bool:
    """Return True for no host, localhost or a numeric loopback address."""
    if host is None:
        return True
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if not isinstance(host, str):
        return False
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _guarded_getaddrinfo(host: object, *args: Any, **kwargs: Any) -> Any:
    """Resolve loopback names only, so a test cannot send a DNS query."""
    if not _loopback_host(host):
        msg = f"network guard: tests must not resolve names ({host!r})"
        raise RuntimeError(msg)
    return _real_getaddrinfo(host, *args, **kwargs)  # pyright: ignore[reportArgumentType]


@pytest.fixture(autouse=True, scope="session")
def network_guard() -> Iterator[None]:
    """No test reaches the network. Loopback and Unix sockets connect or resolve."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(socket.socket, "connect", _guarded_connect)
        patch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
        patch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
        yield


@pytest.fixture(scope="session")
def demo_build(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the demo fixture once per test process and return its folder.

    The folder holds ``config/`` (the Claude config dir, transcripts under
    ``config/projects/``), ``truth.json`` and ``session.json``. Treat it as read only;
    copy it first when a test changes files.
    """
    out = tmp_path_factory.mktemp("demo") / "demo"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(DEMO_BUILDER),
            str(out),
            "--now",
            DEMO_NOW,
            "--tz",
            DEMO_TZ,
        ],
        check=True,
        timeout=120,
        capture_output=True,
    )
    return out


@pytest.fixture(scope="session")
def flow_build(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """Return a function that builds a ``live_flow`` scenario once and gives its folder.

    The folder holds ``config/``, ``session.json`` (with the scenario clock in
    ``now``) and ``flow.json`` (clock, session id, runs). Treat it as read only.
    """
    built: dict[str, Path] = {}

    def build(scenario: str) -> Path:
        if scenario not in FLOW_SCENARIOS:
            msg = f"unknown live_flow scenario {scenario!r}"
            raise ValueError(msg)
        if scenario not in built:
            out = tmp_path_factory.mktemp(f"flow-{scenario}") / scenario
            subprocess.run(  # noqa: S603
                [sys.executable, str(FLOW_BUILDER), str(out), scenario],
                check=True,
                timeout=180,
                capture_output=True,
            )
            built[scenario] = out
        return built[scenario]

    return build


BASE_URL = f"http://127.0.0.1:{PORT}"

INDEX_HTML = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">'
    "<title>Bar Tab</title>"
    '<script type="module" crossorigin src="/assets/app.js"></script>'
    '<link rel="modulepreload" crossorigin href="/assets/chunk.js">'
    '<link rel="stylesheet" crossorigin href="/assets/app.css">'
    '</head><body><div id="root"></div></body></html>'
)


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass
class AsgiResult:
    """What a raw ASGI call produced."""

    status: int | None = None
    headers: dict[str, str] = field(default_factory=dict[str, str])
    body: bytes = b""


AsgiCaller = Callable[..., Awaitable[AsgiResult]]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def state(clock: FakeClock) -> AccessState:
    return AccessState(clock=clock)


@pytest.fixture
def dist_dir(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export {};\n", encoding="utf-8")
    return dist


@pytest.fixture
def settings(
    tmp_path: Path, dist_dir: Path, clock: FakeClock, state: AccessState
) -> main.Settings:
    return main.Settings(
        port=PORT,
        data_dir=tmp_path / "data",
        dist_dir=dist_dir,
        fixture="demo",
        clock=clock,
        access_state=state,
    )


@pytest.fixture
def app(settings: main.Settings) -> ASGIApp:
    return main.create_app(settings)


@contextmanager
def _open(app: ASGIApp, port: int = PORT) -> Generator[Any]:
    """Open a test client on the loopback origin, with lifespan running.

    Starlette's TestClient is typed against ``httpx2``, which is not installed, so
    pyright sees its methods as unknown. The client is handed out as ``Any``.
    """
    with TestClient(
        app, base_url=f"http://127.0.0.1:{port}", raise_server_exceptions=False
    ) as test:
        yield cast("Any", test)


@pytest.fixture
def open_client() -> Callable[..., AbstractContextManager[Any]]:
    return _open


@pytest.fixture
def client(app: ASGIApp) -> Iterator[Any]:
    with _open(app) as test:
        yield test


@pytest.fixture
def key_headers(state: AccessState) -> dict[str, str]:
    return {"X-Bartab-Key": state.read_key}


@pytest.fixture
def asgi_call() -> AsgiCaller:
    """Return a coroutine function that calls an ASGI app with a hand-built request."""

    async def call(  # noqa: PLR0913
        app: ASGIApp,
        *,
        method: str = "GET",
        path: str = "/",
        headers: Sequence[tuple[str, str]] = (),
        messages: Sequence[Message] | None = None,
        hang: bool = False,
    ) -> AsgiResult:
        raw = [(k.lower().encode(), v.encode()) for k, v in headers]
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw,
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", PORT),
        }
        queue = list(messages or [])
        result = AsgiResult()

        async def receive() -> Message:
            if queue:
                return queue.pop(0)
            if hang:
                await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                result.status = message["status"]
                result.headers = {
                    k.decode().lower(): v.decode() for k, v in message["headers"]
                }
            elif message["type"] == "http.response.body":
                result.body += message.get("body", b"")

        await app(scope, receive, send)
        return result

    return call
