"""Routes for Live: one session's timeline and the running-session list.

Both answer with the full body, or with the short ``unchanged`` body when the ``etag``
the page sends still matches. A missing or repeated ``project`` or ``etag`` is a
``bad_request`` (400) rather than the 422 of a bad value, so the page sees one code for
a request it built wrong. The answers never carry a ``cwd`` or an absolute path.
``ApiGzipMiddleware`` compresses the ``/api/`` answers over 1 KB.
"""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from models import (
    INVALID_REQUEST_RESPONSE,
    PROJECT_KEY_PATTERN,
    ErrorEnvelope,
    LiveSessions,
    LiveSessionsUnchanged,
    Timeline,
    Unchanged,
)
from provider import Provider, UnknownProjectError, UnknownSessionError

SESSION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"
ETAG_PATTERN = r"^[A-Za-z0-9_.-]{0,64}$"
GZIP_MINIMUM_BYTES = 1024
ProjectQuery = Annotated[str | None, Query(pattern=PROJECT_KEY_PATTERN, max_length=63)]
EtagQuery = Annotated[str | None, Query(pattern=ETAG_PATTERN, max_length=64)]


class ApiGzipMiddleware:
    """Gzip the ``/api/`` answers over 1 KB, and leave every other path alone."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap ``app``."""
        self._app = app
        self._gzip = GZipMiddleware(app, minimum_size=GZIP_MINIMUM_BYTES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Route an API request through gzip and the rest straight through."""
        if scope["type"] == "http" and str(scope.get("path", "")).startswith("/api/"):
            await self._gzip(scope, receive, send)
        else:
            await self._app(scope, receive, send)


def _bad_request() -> HTTPException:
    return HTTPException(status_code=400, detail="bad_request")


def _params(request: Request, project: str | None) -> None:
    """Fail with ``bad_request`` for a missing or repeated ``project`` or ``etag``."""
    query = request.query_params
    if project is None or len(query.getlist("project")) != 1:
        raise _bad_request()
    if len(query.getlist("etag")) > 1:
        raise _bad_request()


def _unknown(code: str) -> HTTPException:
    return HTTPException(status_code=404, detail=code)


def build_router(provider: Provider) -> APIRouter:
    """Build the router for the Live reads.

    Args:
        provider: Where the answers come from.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["live"],
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: INVALID_REQUEST_RESPONSE,
        },
    )

    @router.get(
        "/sessions/{session_id}/timeline",
        response_model=Timeline | Unchanged,
        name="get_timeline",
    )
    def get_timeline(
        request: Request,
        session_id: Annotated[str, Path(pattern=SESSION_ID_PATTERN, max_length=128)],
        project: ProjectQuery = None,
        etag: EtagQuery = None,
    ) -> Timeline | Unchanged:
        _params(request, project)
        assert project is not None  # noqa: S101 - _params rejected None
        try:
            return provider.timeline(project, session_id, etag)
        except UnknownProjectError:
            raise _unknown("unknown_project") from None
        except UnknownSessionError:
            raise _unknown("unknown_session") from None

    @router.get(
        "/live/sessions",
        response_model=LiveSessions | LiveSessionsUnchanged,
        name="get_live_sessions",
    )
    def get_live_sessions(
        request: Request, project: ProjectQuery = None, etag: EtagQuery = None
    ) -> LiveSessions | LiveSessionsUnchanged:
        _params(request, project)
        assert project is not None  # noqa: S101 - _params rejected None
        try:
            return provider.live_sessions(project, etag)
        except UnknownProjectError:
            raise _unknown("unknown_project") from None

    return router
