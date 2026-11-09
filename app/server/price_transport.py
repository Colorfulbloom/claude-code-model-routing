"""The injected transport for the price feed, and the real urllib one.

The price feed makes the app's only outbound calls, two GETs a day to two fixed
HTTPS URLs. Everything that touches a socket sits behind ``Transport``, so tests
pass a fake and no test reaches the network.

``UrllibTransport`` sends a custom User-Agent (the default one gets 403 on some
hosts), keeps no cookies, refuses any URL that is not one of the two fixed ones, and
refuses a redirect to another host. It reads at most ``max_bytes + 1`` bytes, so a
body past the cap is refused without being held in memory.
"""

import urllib.error
import urllib.request
from collections.abc import Mapping
from http.client import HTTPMessage
from typing import IO, Literal, Protocol
from urllib.parse import urlsplit

import version

LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
ALLOWED_URLS = frozenset({LITELLM_URL, OPENROUTER_URL})

DEFAULT_TIMEOUT = 10.0
USER_AGENT = f"BarTab/{version.VERSION} (price feed; local app; no cookies)"
_CHUNK = 64 * 1024

FetchReason = Literal["fetch_failed", "too_large", "redirect_refused", "timeout"]


class FetchError(Exception):
    """A fetch that did not return a body. ``reason_code`` says why."""

    def __init__(self, reason_code: FetchReason) -> None:
        """Keep the reason code. It is the only detail, so no URL or body leaks."""
        super().__init__(reason_code)
        self.reason_code: FetchReason = reason_code


class Transport(Protocol):
    """What the price feed needs from the network. Tests inject a fake."""

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        """Return the body of a GET, or raise ``FetchError``."""
        ...


class _Response(Protocol):
    """The part of an HTTP response the transport reads."""

    @property
    def status(self) -> int:
        """The HTTP status code."""
        ...

    @property
    def headers(self) -> Mapping[str, str] | HTTPMessage:
        """The response headers."""
        ...

    def read(self, amt: int = ..., /) -> bytes:
        """Read up to ``amt`` bytes."""
        ...

    def close(self) -> None:
        """Close the response."""
        ...


class _Opener(Protocol):
    """The part of ``urllib.request.OpenerDirector`` the transport calls."""

    def open(
        self, fullurl: urllib.request.Request, data: None = None, timeout: float = ...
    ) -> _Response:
        """Open a request."""
        ...


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when it stays on the same host over HTTPS."""

    def redirect_request(  # noqa: PLR0913, PLR0917
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Return the redirected request, or raise ``FetchError`` for another host."""
        target = urlsplit(newurl)
        origin = urlsplit(req.full_url)
        if target.scheme != "https" or target.hostname != origin.hostname:
            raise FetchError("redirect_refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def build_opener(
    *extra: urllib.request.BaseHandler,
) -> urllib.request.OpenerDirector:
    """Build the opener. It refuses redirects to another host and keeps no cookies.

    ``build_opener`` adds no cookie handler of its own, so none is kept or sent.
    ``extra`` handlers are for tests.
    """
    return urllib.request.build_opener(SameHostRedirect(), *extra)


class UrllibTransport:
    """HTTPS GET to the two fixed price URLs, over urllib."""

    def __init__(self, opener: _Opener | None = None) -> None:
        """Use ``opener`` (a fake in tests) or build the real one."""
        self._opener: _Opener = opener if opener is not None else build_opener()

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        """Return the body of a GET.

        Args:
            url: One of the two fixed URLs. Any other URL raises ``fetch_failed``.
            timeout: Seconds for the connection and for each read.
            max_bytes: The body cap. A longer body raises ``too_large``.

        Returns:
            The response body.

        Raises:
            FetchError: With ``fetch_failed``, ``too_large``, ``redirect_refused`` or
                ``timeout``.
        """
        if url not in ALLOWED_URLS:
            raise FetchError("fetch_failed")
        request = urllib.request.Request(  # noqa: S310
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
        try:
            response = self._opener.open(request, timeout=timeout)
        except FetchError:
            raise
        except TimeoutError as exc:
            raise FetchError("timeout") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise FetchError("timeout") from exc
            raise FetchError("fetch_failed") from exc
        except OSError as exc:
            raise FetchError("fetch_failed") from exc
        try:
            return self._read(response, max_bytes)
        finally:
            response.close()

    @staticmethod
    def _read(response: _Response, max_bytes: int) -> bytes:
        if response.status != 200:  # noqa: PLR2004
            raise FetchError("fetch_failed")
        declared = response.headers.get("Content-Length")
        if declared is not None and declared.isdigit() and int(declared) > max_bytes:
            raise FetchError("too_large")
        chunks: list[bytes] = []
        total = 0
        try:
            while total <= max_bytes:
                chunk = response.read(min(_CHUNK, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
        except TimeoutError as exc:
            raise FetchError("timeout") from exc
        except OSError as exc:
            raise FetchError("fetch_failed") from exc
        if total > max_bytes:
            raise FetchError("too_large")
        return b"".join(chunks)
