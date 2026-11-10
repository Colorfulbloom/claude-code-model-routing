"""Exception handlers that answer with the one error envelope.

The envelope is ``{"code": str, "path": list | null}``. It never echoes the request's
input, and it never carries a file path or exception text.
"""

import logging
import re

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

_CODE = re.compile(r"^[a-z][a-z_]{0,40}$")
_STATUS_CODES = {
    400: "bad_request",
    404: "not_found",
    405: "method_not_allowed",
    422: "invalid_request",
}
_MAX_PATH = 6


class FieldError(StarletteHTTPException):
    """An HTTP error whose envelope names the request field that caused it.

    ``path`` follows the 422 envelope, such as ``["query", "range"]``. It holds field
    names the server chose, never what the client sent.
    """

    def __init__(self, status_code: int, detail: str, path: list[str | int]) -> None:
        """Make the error. ``detail`` is the envelope's ``code``."""
        super().__init__(status_code=status_code, detail=detail)
        self.path = path


def _envelope(
    status: int, code: str, path: list[str | int] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"code": code, "path": path},
        headers={"Cache-Control": "no-store"},
    )


def _safe_path(loc: tuple[int | str, ...], error_type: str) -> list[str | int]:
    """Return the field location without any name the client chose."""
    parts = list(loc)
    if error_type == "extra_forbidden" and parts:
        parts.pop()
    return parts[:_MAX_PATH]


async def _validation_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    path: list[str | int] | None = None
    if isinstance(exc, RequestValidationError):
        errors = exc.errors()
        if errors:
            first = errors[0]
            path = _safe_path(first["loc"], first["type"])
    return _envelope(422, "invalid_request", path)


async def _http_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    status = 500
    detail: object = None
    path: list[str | int] | None = None
    if isinstance(exc, StarletteHTTPException):
        status = exc.status_code
        detail = exc.detail
        if isinstance(exc, FieldError):
            path = exc.path
    if isinstance(detail, str) and _CODE.match(detail):
        code = detail
    else:
        code = _STATUS_CODES.get(status, "error")
    return _envelope(status, code, path)


async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:
    del request
    logger.error("unhandled error of type %s", type(exc).__name__)
    return _envelope(500, "internal_error")


def install(app: FastAPI) -> None:
    """Register the handlers on the app.

    Args:
        app: The FastAPI app.
    """
    app.add_exception_handler(RequestValidationError, _validation_handler)
    # FastAPI's HTTPException subclasses Starlette's, which Starlette raises for 404.
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unexpected_handler)
