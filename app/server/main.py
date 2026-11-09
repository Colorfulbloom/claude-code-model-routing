"""Application factory for the Bar Tab server.

``create_app`` returns the ASGI app the server runs: the gate, then the security
headers, then FastAPI. ``build_app`` returns the FastAPI app alone, which tests and the
OpenAPI export use. Both read ``dist/index.html`` once and rewrite it per request.
"""

import logging
import time
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from starlette.types import ASGIApp

import access
import api_app
import csp
import errors
import fixture_provider
import gate
import version
from access import AccessState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    """Everything the app needs from its caller."""

    port: int
    data_dir: Path
    dist_dir: Path
    fixture: str = "demo"
    project_dir: Path | None = None
    idle_exit_minutes: float = 0
    clock: Callable[[], float] = time.time
    access_state: AccessState | None = None
    fixtures_dir: Path | None = None


def _operation_id(route: APIRoute) -> str:
    return route.name


def _static_router(dist_dir: Path, index: csp.IndexPage, instance: str) -> APIRouter:
    """Serve the built files, and the rewritten index for `/` and unknown paths."""
    router = APIRouter()
    root = dist_dir.resolve()

    def page() -> Response:
        nonce = csp.new_nonce()
        return Response(
            content=index.render(nonce, instance),
            status_code=200 if index.found else 503,
            media_type="text/html",
            headers=csp.page_headers(nonce),
        )

    @router.api_route(
        "/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False
    )
    def serve_path(full_path: str) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not_found")
        if full_path in ("", "index.html"):
            return page()
        try:
            candidate = (root / full_path).resolve()
        except (OSError, ValueError):
            return page()
        if candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return page()

    return router


def build_app(settings: Settings) -> FastAPI:
    """Build the FastAPI app.

    Args:
        settings: Port, folders, fixture name and clock.

    Returns:
        The FastAPI app with every router included.
    """
    state = settings.access_state or AccessState(clock=settings.clock)
    provider = fixture_provider.FixtureProvider(
        settings.fixture, settings.clock, settings.fixtures_dir
    )
    index = csp.load_index(settings.dist_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        logger.info("startup complete")
        try:
            yield
        finally:
            logger.info("shutdown complete")

    app = FastAPI(
        title=version.APP_NAME,
        version=version.VERSION,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        generate_unique_id_function=_operation_id,
    )
    errors.install(app)
    app.include_router(access.build_router(state))
    app.include_router(api_app.build_router(provider, state.instance))
    app.include_router(_static_router(settings.dist_dir, index, state.instance))
    return app


def create_app(settings: Settings) -> ASGIApp:
    """Build the ASGI app the server runs, gate included.

    Args:
        settings: Port, folders, fixture name and clock.

    Returns:
        The gate wrapped around the security headers wrapped around FastAPI.
    """
    state = settings.access_state or AccessState(clock=settings.clock)
    resolved = replace(settings, access_state=state)
    inner = csp.SecurityHeadersMiddleware(build_app(resolved))
    return gate.GateMiddleware(inner, settings.port, state)
