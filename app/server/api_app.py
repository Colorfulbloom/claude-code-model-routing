"""Routes for the app-wide reads: app, projects and prices."""

from typing import Annotated

from fastapi import APIRouter, Query

from models import PROJECT_KEY_PATTERN, AppInfo, ErrorEnvelope, PricesInfo, ProjectList
from provider import Provider


def build_router(provider: Provider, instance: str) -> APIRouter:
    """Build the router for the app-wide reads.

    Args:
        provider: Where the answers come from.
        instance: The server instance id the answer reports.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["app"],
        responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )

    @router.get("/app", response_model=AppInfo, name="get_app")
    def get_app(
        project: Annotated[
            str | None, Query(pattern=PROJECT_KEY_PATTERN, max_length=63)
        ] = None,
    ) -> AppInfo:
        return provider.app_info(instance, project)

    @router.get("/projects", response_model=ProjectList, name="get_projects")
    def get_projects() -> ProjectList:
        return provider.projects()

    @router.get("/prices", response_model=PricesInfo, name="get_prices")
    def get_prices() -> PricesInfo:
        return provider.prices()

    return router
