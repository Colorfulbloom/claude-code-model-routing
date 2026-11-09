"""Pure ASGI gate that stands in front of the whole app.

It runs before FastAPI sees a request, over the raw scope headers. It refuses a bad
Host, a bad Origin, a cross-site fetch, an unsupported method, a POST without a JSON
content type, a body over 64 KiB, a body that does not arrive within 3 seconds, and a
missing or wrong key. A refusal is a small JSON answer built from fixed codes, so no
input is ever echoed back. Ported from the research spike for the write gate.

Key rules by path:

- ``/api/access/swap`` needs no key, because the page has none yet.
- ``/api/access/mint`` needs ``X-Bartab-Mint``.
- Every other ``/api/*`` path needs ``X-Bartab-Key``.
- Static files and the index page need no key.

An Origin header is checked whenever it is present. A browser always sends one on a
POST, so a POST that carries ``Sec-Fetch-Site`` but no Origin is refused. A client that
sends neither header (the launcher) may omit it.
"""

import asyncio
import hmac
import json
from typing import cast

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from access import AccessState

BODY_CAP = 64 * 1024
BODY_TIMEOUT_SECONDS = 3.0

SWAP_PATH = "/api/access/swap"
MINT_PATH = "/api/access/mint"
KEY_HEADER = b"x-bartab-key"
MINT_HEADER = b"x-bartab-mint"

_MAX_DIGITS = 10
_METHODS = frozenset({"GET", "HEAD", "POST"})
_FETCH_SITES = frozenset({b"same-origin", b"none"})
_Headers = list[tuple[bytes, bytes]]


def _values(headers: _Headers, name: bytes) -> list[bytes]:
    """Return every value of one header. Raw names are already lower case."""
    return [value for key, value in headers if key == name]


def _one(headers: _Headers, name: bytes) -> bytes | None:
    """Return the single value of a header, or None when absent or repeated."""
    found = _values(headers, name)
    return found[0] if len(found) == 1 else None


def _is_api(path: str) -> bool:
    return path == "/api" or path.startswith("/api/")


def _check_shape(headers: _Headers, method: str) -> tuple[int, str] | None:
    """Check the content type of a POST, or that another method has no body."""
    if method == "POST":
        media = (_one(headers, b"content-type") or b"").split(b";")[0]
        if media.strip().lower() != b"application/json":
            return 415, "bad_content_type"
        return None
    lengths = _values(headers, b"content-length")
    if lengths not in ([], [b"0"]) or _values(headers, b"transfer-encoding"):
        return 400, "bad_length"
    return None


def _declared_length(headers: _Headers) -> int | tuple[int, str]:
    """Return the declared body size, or (status, code) when it is not acceptable."""
    if _values(headers, b"transfer-encoding"):
        return 400, "bad_length"
    lengths = _values(headers, b"content-length")
    text = lengths[0].strip() if len(lengths) == 1 else b""
    if not (text.isascii() and text.isdigit() and len(text) <= _MAX_DIGITS):
        return 411, "bad_length"
    declared = int(text)
    if declared > BODY_CAP:
        return 413, "too_large"
    return declared


class GateMiddleware:
    """Refuse requests that do not come from the page on this origin."""

    def __init__(
        self,
        app: ASGIApp,
        port: int,
        access: AccessState,
        body_timeout: float = BODY_TIMEOUT_SECONDS,
    ) -> None:
        """Configure the gate.

        Args:
            app: The app behind the gate.
            port: The port the server is bound to.
            access: The access state that holds the read key and mint secret.
            body_timeout: Seconds a body may take to arrive.
        """
        self.app = app
        self.access = access
        self.body_timeout = body_timeout
        self._hosts = frozenset(
            {f"127.0.0.1:{port}".encode(), f"localhost:{port}".encode()}
        )
        self._origins = frozenset(
            {f"http://127.0.0.1:{port}".encode(), f"http://localhost:{port}".encode()}
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call."""
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await send({"type": "websocket.close", "code": 1008})
            return
        headers = cast("_Headers", scope["headers"])
        refusal = self._check_headers(scope, headers)
        if refusal is not None:
            await self._refuse(send, *refusal)
            return
        if scope["method"] == "POST":
            body = await self._read_body(headers, receive)
            if isinstance(body, tuple):
                await self._refuse(send, *body)
                return
            await self.app(scope, _replay(body, receive), send)
            return
        await self.app(scope, receive, send)

    def _check_headers(self, scope: Scope, headers: _Headers) -> tuple[int, str] | None:
        """Return (status, code) for a refusal, or None when the headers pass."""
        method = str(scope["method"])
        host = _one(headers, b"host")
        refusal: tuple[int, str] | None = None
        if method not in _METHODS:
            refusal = 405, "bad_method"
        elif host is None or host.strip().lower() not in self._hosts:
            refusal = 400, "bad_host"
        else:
            refusal = self._check_origin(headers, method)
        if refusal is None:
            refusal = _check_shape(headers, method)
        if refusal is None:
            refusal = self._check_key(str(scope["path"]), headers)
        return refusal

    def _check_origin(self, headers: _Headers, method: str) -> tuple[int, str] | None:
        """Check Origin and Sec-Fetch-Site."""
        origins = _values(headers, b"origin")
        sites = _values(headers, b"sec-fetch-site")
        if len(origins) > 1 or (origins and origins[0].lower() not in self._origins):
            return 403, "bad_origin"
        if len(sites) > 1 or (sites and sites[0].lower() not in _FETCH_SITES):
            return 403, "bad_fetch_site"
        if method == "POST" and sites and not origins:
            return 403, "bad_origin"
        return None

    def _check_key(self, path: str, headers: _Headers) -> tuple[int, str] | None:
        """Apply the key rules for the path."""
        if not _is_api(path) or path == SWAP_PATH:
            return None
        if path == MINT_PATH:
            name, secret = MINT_HEADER, self.access.mint_secret
        else:
            name, secret = KEY_HEADER, self.access.read_key
        sent = _values(headers, name)
        if len(sent) != 1 or not sent[0]:
            return 401, "no_key"
        if not hmac.compare_digest(sent[0], secret.encode()):
            return 401, "bad_key"
        return None

    async def _read_body(
        self, headers: _Headers, receive: Receive
    ) -> bytes | tuple[int, str]:
        """Read the declared body, or return (status, code) for a refusal."""
        declared = _declared_length(headers)
        if isinstance(declared, tuple):
            return declared
        try:
            body = await asyncio.wait_for(
                _collect(receive, declared), self.body_timeout
            )
        except TimeoutError:
            return 408, "body_timeout"
        return body

    @staticmethod
    async def _refuse(send: Send, status: int, code: str) -> None:
        """Send a fixed JSON refusal and ask the server to close the connection."""
        payload = json.dumps({"code": code, "path": None}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


async def _collect(receive: Receive, declared: int) -> bytes | tuple[int, str]:
    """Read ``declared`` bytes from the receive channel."""
    body = b""
    while len(body) < declared:
        message = await receive()
        if message["type"] == "http.disconnect":
            return 400, "short_body"
        body += message.get("body", b"")
        if len(body) > BODY_CAP:
            return 413, "too_large"
    if len(body) != declared:
        return 400, "bad_length"
    return body


def _replay(body: bytes, receive: Receive) -> Receive:
    """Return a receive callable that hands the app the body already read."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay
