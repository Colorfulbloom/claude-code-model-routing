"""Route for the Rules reference: ``GET /api/rules``.

The answer is global, so the route takes no ``project``. It takes ``etag`` and answers
with the full body, or with the short ``RulesUnchanged`` body when the etag the page
sends still matches. A repeated ``etag`` is a ``bad_request`` (400). The answer holds
no sentence: the page words every rule from its ``rule_id`` and ``key``.
"""

from fastapi import APIRouter, Request

import errors
import rules_reference
from api_live import EtagQuery
from models import (
    INVALID_REQUEST_RESPONSE,
    ErrorEnvelope,
    RulesAnswer,
    RulesUnchanged,
)
from provider import Provider


def build_router(provider: Provider) -> APIRouter:
    """Build the router for the Rules reference.

    Args:
        provider: Where the clock and the installed Claude Code version come from.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api",
        tags=["rules"],
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            422: INVALID_REQUEST_RESPONSE,
        },
    )

    @router.get("/rules", response_model=RulesAnswer | RulesUnchanged, name="get_rules")
    def get_rules(
        request: Request, etag: EtagQuery = None
    ) -> RulesAnswer | RulesUnchanged:
        if len(request.query_params.getlist("etag")) > 1:
            raise errors.FieldError(400, "bad_request", ["query", "etag"])
        answer = rules_reference.build_answer(
            provider.claude_version() or None, provider.now()
        )
        if etag is not None and etag == answer.etag:
            return RulesUnchanged(
                server_time=answer.server_time, etag=answer.etag, unchanged=True
            )
        return answer

    return router
