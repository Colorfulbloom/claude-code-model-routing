"""Content security policy, security headers and the per-request index rewrite.

``dist/index.html`` is read again when its mtime or size changes (see ``IndexSource``),
so a rebuild shows without a restart. Each request gets a fresh nonce, which goes on
every script and link tag, into a ``csp-nonce`` meta tag and into the CSP header. Two
more meta tags carry the server instance id and the launch command. None of the three
is a secret.
"""

import html
import logging
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

LAUNCH_COMMAND = "/bartab-preview"

_TAG = re.compile(r"<(?:script|link)\b[^>]*>", re.IGNORECASE)
_NONCE_ATTR = re.compile(
    r"""\snonce\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE
)
_OWN_META = re.compile(
    r"""<meta\s+name\s*=\s*["'](?:csp-nonce|bartab-instance|bartab-command)["'][^>]*>""",
    re.IGNORECASE,
)
_HEAD_OPEN = re.compile(r"<head\b[^>]*>", re.IGNORECASE)

MISSING_BUILD_PAGE = (
    "<!doctype html>\n"
    '<html lang="en">\n'
    "<head>\n"
    '<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    "<title>Bar Tab</title>\n"
    "</head>\n"
    "<body>\n"
    "<h1>The build is missing</h1>\n"
    "<p>This server has no built web app to serve. Build the web app, "
    "then start the server again.</p>\n"
    "</body>\n"
    "</html>\n"
)

_STATIC_HEADERS: dict[bytes, bytes] = {
    b"x-content-type-options": b"nosniff",
    b"referrer-policy": b"no-referrer",
}


def new_nonce() -> str:
    """Return a fresh URL-safe nonce."""
    return secrets.token_urlsafe(16)


def build_csp(nonce: str) -> str:
    """Return the production Content-Security-Policy for one nonce.

    Args:
        nonce: The per-request nonce.

    Returns:
        The header value.
    """
    return (
        "default-src 'none'; "
        f"script-src 'self' 'nonce-{nonce}'; "
        f"style-src 'self' 'nonce-{nonce}'; "
        "img-src 'self' data:; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'none'"
    )


def page_headers(nonce: str) -> dict[str, str]:
    """Return the headers an HTML page carries.

    Args:
        nonce: The per-request nonce.

    Returns:
        Header names and values, including the CSP and ``no-store``.
    """
    return {
        "Content-Security-Policy": build_csp(nonce),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }


def _add_nonce(match: re.Match[str], nonce: str) -> str:
    tag = _NONCE_ATTR.sub("", match.group(0))
    name_end = re.match(r"<\w+", tag)
    if name_end is None:  # pragma: no cover - the tag pattern always starts so
        return tag
    cut = name_end.end()
    return f'{tag[:cut]} nonce="{nonce}"{tag[cut:]}'


@dataclass(frozen=True)
class IndexPage:
    """The index document, ready to be rewritten per request."""

    source: str
    found: bool

    def render(self, nonce: str, instance: str, command: str = LAUNCH_COMMAND) -> bytes:
        """Return the page for one request.

        Args:
            nonce: The per-request nonce.
            instance: The server instance id.
            command: The launch command shown on the locked and stopped pages.

        Returns:
            The rewritten document as UTF-8 bytes.
        """
        if not self.found:
            return self.source.encode("utf-8")
        text = _OWN_META.sub("", self.source)
        text = _TAG.sub(lambda m: _add_nonce(m, nonce), text)
        metas = (
            f'<meta name="csp-nonce" content="{html.escape(nonce)}">'
            f'<meta name="bartab-instance" content="{html.escape(instance)}">'
            f'<meta name="bartab-command" content="{html.escape(command)}">'
        )
        head = _HEAD_OPEN.search(text)
        if head is None:
            return (metas + text).encode("utf-8")
        return (text[: head.end()] + metas + text[head.end() :]).encode("utf-8")


def load_index(dist_dir: Path) -> IndexPage:
    """Read ``index.html`` from the dist folder once.

    Args:
        dist_dir: The folder the web build wrote.

    Returns:
        The page, or a built-in page that says the build is missing.
    """
    try:
        source = (dist_dir / "index.html").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("web build not found, serving the built-in notice")
        return IndexPage(MISSING_BUILD_PAGE, found=False)
    return IndexPage(source, found=True)


class IndexSource:
    """The index document, re-read when ``dist/index.html`` changes on disk.

    A rebuild writes new asset hashes. A server that kept the first read would serve an
    index that points at deleted files, so each request checks the file's mtime and size
    and re-reads it when either moved.
    """

    def __init__(self, dist_dir: Path) -> None:
        """Read the index once.

        Args:
            dist_dir: The folder the web build wrote.
        """
        self._dist_dir = dist_dir
        self._path = dist_dir / "index.html"
        self._page = load_index(dist_dir)
        self._stamp = self._stat()

    def _stat(self) -> tuple[int, int] | None:
        try:
            info = self._path.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size)

    @property
    def page(self) -> IndexPage:
        """The current page, re-read first when the file changed."""
        stamp = self._stat()
        if stamp != self._stamp:
            self._page = load_index(self._dist_dir)
            self._stamp = stamp
        return self._page


class SecurityHeadersMiddleware:
    """Add the fixed security headers to every HTTP response.

    API answers also get ``Cache-Control: no-store``.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Wrap an ASGI app.

        Args:
            app: The app to wrap.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI call."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope["path"])
        is_api = path == "/api" or path.startswith("/api/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                pairs: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                present = {name.lower() for name, _ in pairs}
                extra = dict(_STATIC_HEADERS)
                if is_api:
                    extra[b"cache-control"] = b"no-store"
                for name, value in extra.items():
                    if name not in present:
                        pairs.append((name, value))
                message = {**message, "headers": pairs}
            await send(message)

        await self.app(scope, receive, send_with_headers)
