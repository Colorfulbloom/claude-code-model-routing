"""The clock that data answers read, apart from the wall clock.

Access keys, the writer's pass schedule, backups and the price feed keep the wall
clock. Only answers about the data (now, running sessions, ``as_of``) read a
``DataClock``. It has four kinds. ``real`` follows the wall clock. ``fixed`` holds one
time. ``rate`` starts at a given time and runs N times real time, and holds at an
optional end time. ``test`` is set by hand, through ``set``. Every reading is an aware
UTC datetime.
"""

import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime

from models import ClockInfo, ClockKind


def _utc(at: datetime) -> datetime:
    """Return an aware time in UTC, or raise when the time has no offset."""
    if at.tzinfo is None or at.utcoffset() is None:
        msg = "a clock time needs a UTC offset"
        raise ValueError(msg)
    return at.astimezone(UTC)


class DataClock:
    """One reading of "now" for data answers. Build one with a class method."""

    def __init__(
        self,
        kind: ClockKind,
        *,
        start: datetime | None = None,
        rate_n: float | None = None,
        end: datetime | None = None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        """Wire a clock. Prefer ``real``, ``fixed``, ``rate`` and ``test``.

        Args:
            kind: Which behaviour the clock has.
            start: The held time (fixed and test) or the starting time (rate).
            rate_n: How many times real time a rate clock runs.
            end: Where a rate clock holds, or None to run on.
            wall: Epoch seconds, injectable so tests move the wall clock.

        Raises:
            ValueError: When the kind needs a field that is missing or out of range.
        """
        if kind != "real" and start is None:
            msg = "this clock kind needs a start time"
            raise ValueError(msg)
        if kind == "rate" and (rate_n is None or rate_n <= 0):
            msg = "a rate clock needs a rate above zero"
            raise ValueError(msg)
        self.kind: ClockKind = kind
        self.rate_n = rate_n if kind == "rate" else None
        self._wall = wall
        self._start = None if start is None else _utc(start)
        self._end = None if end is None else _utc(end)
        self._origin = wall()
        self._held = self._start
        self._lock = threading.Lock()

    @classmethod
    def real(cls, wall: Callable[[], float] = time.time) -> "DataClock":
        """Follow the wall clock."""
        return cls("real", wall=wall)

    @classmethod
    def fixed(cls, at: datetime) -> "DataClock":
        """Hold one time."""
        return cls("fixed", start=at)

    @classmethod
    def rate(
        cls,
        start: datetime,
        rate_n: float,
        end: datetime | None = None,
        wall: Callable[[], float] = time.time,
    ) -> "DataClock":
        """Start at ``start`` and run ``rate_n`` times real time, holding at ``end``."""
        return cls("rate", start=start, rate_n=rate_n, end=end, wall=wall)

    @classmethod
    def test(cls, at: datetime) -> "DataClock":
        """Hold ``at`` until ``set`` moves it."""
        return cls("test", start=at)

    def now(self) -> datetime:
        """Return the clock's time as an aware UTC datetime."""
        if self.kind == "real":
            return datetime.fromtimestamp(self._wall(), tz=UTC)
        with self._lock:
            held = self._held
        if held is None:
            raise RuntimeError("clock has no time")  # noqa: TRY003
        if self.kind != "rate" or self.rate_n is None:
            return held
        elapsed = (self._wall() - self._origin) * self.rate_n
        reading = datetime.fromtimestamp(held.timestamp() + elapsed, tz=UTC)
        if self._end is not None and reading > self._end:
            return self._end
        return reading

    def set(self, at: datetime) -> datetime:
        """Move a test clock to ``at`` and return the stored UTC time.

        Raises:
            ValueError: When the clock is not a test clock, or ``at`` has no offset.
        """
        if self.kind != "test":
            msg = "only a test clock can be set"
            raise ValueError(msg)
        moved = _utc(at)
        with self._lock:
            self._held = moved
        return moved

    def info(self) -> ClockInfo:
        """Return the ``clock`` field of ``/api/app``."""
        return ClockInfo(kind=self.kind, rate_n=self.rate_n)
