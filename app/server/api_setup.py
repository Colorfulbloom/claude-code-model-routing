"""Routes for Setup: the map, one part, and the problems feed.

``GET /api/setup``, ``GET /api/setup/{part}`` and ``GET /api/problems`` take
``project`` (required) and ``etag``. They answer with the full body, or with the shared
``Unchanged`` body when the ``etag`` the page sends still matches the cached read. A
missing or repeated ``project`` or ``etag`` is a ``bad_request`` (400) whose ``path``
names the field, an unknown project is ``unknown_project`` (404) and a part outside the
ten is ``unknown_part`` (404). The page's ``scopes`` switch lives in its URL only, so
the routes take no such parameter. The answers carry no file body, no ``cwd``, and no
absolute path outside the ``full_path`` fields (and the copy targets that are paths).
"""

from typing import Annotated, get_args

from fastapi import APIRouter, HTTPException, Path, Request

import errors
from api_live import EtagQuery, ProjectQuery
from models import (
    INVALID_REQUEST_RESPONSE,
    ErrorEnvelope,
    ProblemList,
    SetupMap,
    SetupPart,
    SetupPartAnswer,
    Unchanged,
)
from provider import Provider, UnknownProjectError

PartPath = Annotated[
    str, Path(max_length=32, description="One of the ten setup parts.")
]


def _bad(name: str) -> errors.FieldError:
    return errors.FieldError(400, "bad_request", ["query", name])


def _check(request: Request, project: str | None) -> str:
    """Check the shared parameters and return the project.

    Raises:
        FieldError: ``bad_request`` for a missing or repeated ``project`` or ``etag``.
    """
    query = request.query_params
    if project is None or query.getlist("project") != [project]:
        raise _bad("project")
    if len(query.getlist("etag")) > 1:
        raise _bad("etag")
    return project


def _unknown() -> HTTPException:
    return HTTPException(status_code=404, detail="unknown_project")


def _part(name: str) -> SetupPart:
    """Return ``name`` as a setup part.

    Raises:
        HTTPException: ``unknown_part`` (404) when it is none of the ten.
    """
    for part in get_args(SetupPart):
        if part == name:
            return part
    raise HTTPException(status_code=404, detail="unknown_part")


def build_router(provider: Provider) -> APIRouter:
    """Build the router for the Setup reads.

    Args:
        provider: Where the answers come from.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["setup"],
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: INVALID_REQUEST_RESPONSE,
        },
    )

    @router.get("/setup", response_model=SetupMap | Unchanged, name="get_setup")
    def get_setup(
        request: Request, project: ProjectQuery = None, etag: EtagQuery = None
    ) -> SetupMap | Unchanged:
        found = _check(request, project)
        try:
            return provider.setup_map(found, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get(
        "/setup/{part}",
        response_model=SetupPartAnswer | Unchanged,
        name="get_setup_part",
    )
    def get_setup_part(
        request: Request,
        part: PartPath,
        project: ProjectQuery = None,
        etag: EtagQuery = None,
    ) -> SetupPartAnswer | Unchanged:
        found = _check(request, project)
        named = _part(part)
        try:
            return provider.setup_part(found, named, etag)
        except UnknownProjectError:
            raise _unknown() from None

    @router.get(
        "/problems", response_model=ProblemList | Unchanged, name="get_problems"
    )
    def get_problems(
        request: Request, project: ProjectQuery = None, etag: EtagQuery = None
    ) -> ProblemList | Unchanged:
        found = _check(request, project)
        try:
            return provider.problems(found, etag)
        except UnknownProjectError:
            raise _unknown() from None

    return router
