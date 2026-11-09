"""The test-only clock route, mounted only when the server starts with ``--test-clock``.

``POST /api/dev/clock`` with ``{"now": "<ISO time with an offset>"}`` sets the data
clock. It sits behind the same gate and read key as every other ``/api`` route.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, field_validator

from data_clock import DataClock
from models import INVALID_REQUEST_RESPONSE, ClockInfo, ErrorEnvelope


class SetClockRequest(BaseModel):
    """Body of ``POST /api/dev/clock``. The time must carry a UTC offset."""

    model_config = ConfigDict(extra="forbid", strict=True)

    now: str

    @field_validator("now")
    @classmethod
    def _aware(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            msg = "needs a UTC offset"
            raise ValueError(msg)
        return value


class DevClock(ClockInfo):
    """The clock after the change, with the time it now reads."""

    now: datetime


def build_router(clock: DataClock) -> APIRouter:
    """Build the router for ``/api/dev/clock``.

    Args:
        clock: The test clock the server's provider reads.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api/dev",
        tags=["dev"],
        responses={401: {"model": ErrorEnvelope}, 422: INVALID_REQUEST_RESPONSE},
    )

    @router.post("/clock", response_model=DevClock, name="set_dev_clock")
    def set_dev_clock(body: SetClockRequest) -> DevClock:
        moved = clock.set(datetime.fromisoformat(body.now))
        info = clock.info()
        return DevClock(kind=info.kind, rate_n=info.rate_n, now=moved)

    return router


def build_absent_router() -> APIRouter:
    """Answer ``POST /api/dev/clock`` with 404 when the server has no test clock.

    The static fall-through route only takes GET and HEAD, so without this a POST to
    the dev path would read as 405, which says the route exists.
    """
    router = APIRouter()

    @router.post("/api/dev/clock", include_in_schema=False)
    def absent() -> None:
        raise HTTPException(status_code=404, detail="not_found")

    return router
