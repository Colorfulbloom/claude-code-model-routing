"""Routes for Review: the Summary, the cost chart, Sessions, Agents and Models.

Every route takes ``project`` (required), ``range`` (default ``30d``) and ``etag``. It
answers with the full body, or with the shared ``Unchanged`` body when the ``etag`` the
page sends still matches. A missing or repeated parameter, an unknown range, a bad
cursor or a bad ``end`` date is a ``bad_request`` (400) whose ``path`` names the field,
such as ``["query", "range"]``, and an unknown project is ``unknown_project`` (404).
``range`` is a plain string in the schema, not an enum, so a wrong value is a 400 here
and not the 422 a type error would give. The answers never carry a ``cwd``, a message
or an agent description.

``/api/sessions`` has no path parameter, so it never meets
``/api/sessions/{session_id}/timeline``.
"""

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

import errors
import review_query
from api_live import EtagQuery, ProjectQuery
from models import (
    DEFAULT_REVIEW_RANGE,
    INVALID_REQUEST_RESPONSE,
    REVIEW_RANGES,
    AgentList,
    CostChart,
    ErrorEnvelope,
    ModelList,
    ReviewRange,
    SessionList,
    Summary,
    Unchanged,
)
from provider import Provider, UnknownProjectError

END_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RangeQuery = Annotated[
    str | None,
    Query(
        description="One of today, 7d, 30d, 90d, 12m and all. Default 30d.",
        max_length=64,
    ),
]
CursorQuery = Annotated[
    str | None,
    Query(description="The opaque `next` of the previous page.", max_length=512),
]
EndQuery = Annotated[
    str | None,
    Query(description="The chart's last local date, as YYYY-MM-DD.", max_length=10),
]


def _bad(name: str) -> errors.FieldError:
    return errors.FieldError(400, "bad_request", ["query", name])


def _single(request: Request, name: str) -> str | None:
    """Return the one value of ``name``, None when it is absent.

    Raises:
        FieldError: ``bad_request`` when ``name`` is given more than once.
    """
    values = request.query_params.getlist(name)
    if len(values) > 1:
        raise _bad(name)
    return values[0] if values else None


def _params(request: Request, project: str | None, *extra: str) -> ReviewRange:
    """Check the shared parameters and return the range.

    Raises:
        FieldError: ``bad_request`` for a missing or repeated ``project``, a repeated
            ``etag`` or ``extra`` parameter, or an unknown ``range``.
    """
    if project is None or request.query_params.getlist("project") != [project]:
        raise _bad("project")
    for name in ("etag", *extra):
        _single(request, name)
    found = _single(request, "range")
    if found is None:
        return DEFAULT_REVIEW_RANGE
    if found not in REVIEW_RANGES:
        raise _bad("range")
    return found


def _unknown() -> HTTPException:
    return HTTPException(status_code=404, detail="unknown_project")


def build_router(provider: Provider) -> APIRouter:
    """Build the router for the Review reads.

    Args:
        provider: Where the answers come from.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["review"],
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: INVALID_REQUEST_RESPONSE,
        },
    )

    @router.get("/summary", response_model=Summary | Unchanged, name="get_summary")
    def get_summary(
        request: Request,
        project: ProjectQuery = None,
        range: RangeQuery = None,
        etag: EtagQuery = None,
    ) -> Summary | Unchanged:
        del range
        review_range = _params(request, project)
        assert project is not None  # noqa: S101 - _params rejected None
        try:
            return provider.summary(project, review_range, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get(
        "/cost-chart", response_model=CostChart | Unchanged, name="get_cost_chart"
    )
    def get_cost_chart(
        request: Request,
        project: ProjectQuery = None,
        range: RangeQuery = None,
        end: EndQuery = None,
        etag: EtagQuery = None,
    ) -> CostChart | Unchanged:
        del range
        review_range = _params(request, project, "end")
        assert project is not None  # noqa: S101 - _params rejected None
        stop: date | None = None
        if end is not None:
            if END_PATTERN.match(end) is None:
                raise _bad("end")
            try:
                stop = date.fromisoformat(end)
            except ValueError:
                raise _bad("end") from None
        try:
            return provider.cost_chart(project, review_range, stop, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get(
        "/sessions", response_model=SessionList | Unchanged, name="get_sessions"
    )
    def get_sessions(
        request: Request,
        project: ProjectQuery = None,
        range: RangeQuery = None,
        cursor: CursorQuery = None,
        etag: EtagQuery = None,
    ) -> SessionList | Unchanged:
        del range
        review_range = _params(request, project, "cursor")
        assert project is not None  # noqa: S101 - _params rejected None
        if cursor is not None:
            try:
                review_query.decode_cursor(cursor)
            except ValueError:
                raise _bad("cursor") from None
        try:
            return provider.sessions(project, review_range, cursor, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get("/agents", response_model=AgentList | Unchanged, name="get_agents")
    def get_agents(
        request: Request,
        project: ProjectQuery = None,
        range: RangeQuery = None,
        etag: EtagQuery = None,
    ) -> AgentList | Unchanged:
        del range
        review_range = _params(request, project)
        assert project is not None  # noqa: S101 - _params rejected None
        try:
            return provider.agents(project, review_range, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get("/models", response_model=ModelList | Unchanged, name="get_models")
    def get_models(
        request: Request,
        project: ProjectQuery = None,
        range: RangeQuery = None,
        etag: EtagQuery = None,
    ) -> ModelList | Unchanged:
        del range
        review_range = _params(request, project)
        assert project is not None  # noqa: S101 - _params rejected None
        try:
            return provider.models(project, review_range, etag)
        except UnknownProjectError:
            raise _unknown() from None

    return router
