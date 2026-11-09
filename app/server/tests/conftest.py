"""Shared pytest fixtures for the Bar Tab server tests."""

import asyncio
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
