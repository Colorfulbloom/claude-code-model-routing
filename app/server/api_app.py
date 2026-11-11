"""Routes for the app-wide reads: app, projects and prices."""

from typing import Annotated

from fastapi import APIRouter, Query

from access import AccessState
from models import (
    INVALID_REQUEST_RESPONSE,
    PROJECT_KEY_PATTERN,
    AppInfo,
    EditsState,
    ErrorEnvelope,
    PricesInfo,
    ProjectList,
)
from provider import Provider


def build_router(
    provider: Provider, instance: str, state: AccessState | None = None
) -> APIRouter:
    """Build the router for the app-wide reads.

    Args:
        provider: Where the answers come from.
        instance: The server instance id the answer reports.
        state: The access state that holds the edits switch. Without one, edits are
            off.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["app"],
        responses={401: {"model": ErrorEnvelope}, 422: INVALID_REQUEST_RESPONSE},
    )

    @router.get("/app", response_model=AppInfo, name="get_app")
    def get_app(
        project: Annotated[
            str | None, Query(pattern=PROJECT_KEY_PATTERN, max_length=63)
        ] = None,
    ) -> AppInfo:
        info = provider.app_info(instance, project)
        mode = "off" if state is None else state.edits
        # The switch is the server's, not the provider's. With edits off or
        # unavailable no project is editable, so the list is empty. With edits on it
        # holds every project that has no block (only a missing folder blocks one).
        editable = (
            [
                item.key
                for item in provider.projects().projects
                if item.edit_block is None
            ]
            if mode == "on"
            else []
        )
        return info.model_copy(
            update={
                "edits": EditsState(state=mode, instance=instance),
                "editable_projects": editable,
            }
        )

    @router.get("/projects", response_model=ProjectList, name="get_projects")
    def get_projects() -> ProjectList:
        return provider.projects()

    @router.get("/prices", response_model=PricesInfo, name="get_prices")
    def get_prices() -> PricesInfo:
        return provider.prices()

    return router
