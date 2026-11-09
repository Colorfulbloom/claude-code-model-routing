"""Read key, mint secret and single-use codes for the Bar Tab server.

The server makes an instance id, a read key and a mint secret at start. The launcher
gets a code, and the page swaps it for the read key. A code is
``<instance>.<random>``, works once and lives 120 seconds. The clock is injectable so
tests step time without sleeping.
"""

import hashlib
import re
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, HTTPException

from models import (
    ErrorEnvelope,
    MintRequest,
    MintResponse,
    SwapRequest,
    SwapResponse,
)

CODE_LIFETIME_SECONDS = 120.0
_FORGET_AFTER_SECONDS = 3600.0
_INSTANCE_PATTERN = re.compile(r"^[0-9a-f]{8}$")

SwapFailure = Literal["code_used", "code_expired", "code_unknown", "server_restarted"]


class SwapError(Exception):
    """A code could not be swapped. ``reason`` is one of the contract's codes."""

    def __init__(self, reason: SwapFailure) -> None:
        """Keep the machine-readable reason.

        Args:
            reason: The contract code that explains the refusal.
        """
        super().__init__(reason)
        self.reason: SwapFailure = reason


@dataclass
class _CodeEntry:
    """What the store remembers about one minted code."""

    expires: float
    project: str | None
    used: bool = False


@dataclass(frozen=True)
class SwapResult:
    """A successful swap."""

    read_key: str
    instance: str
    project: str | None


@dataclass
class AccessState:
    """Secrets and the code store of one server run."""

    instance: str = field(default_factory=lambda: secrets.token_hex(4))
    read_key: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    mint_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    clock: Callable[[], float] = time.time
    _codes: dict[str, _CodeEntry] = field(default_factory=dict[str, _CodeEntry])
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def mint_code(self, project: str | None) -> str:
        """Make a fresh single-use code.

        Args:
            project: The project key the page should open, or None.

        Returns:
            The code, shaped ``<instance>.<random>``.
        """
        with self._lock:
            now = self.clock()
            self._purge(now)
            code = f"{self.instance}.{secrets.token_urlsafe(24)}"
            self._codes[_digest(code)] = _CodeEntry(
                now + CODE_LIFETIME_SECONDS, project
            )
            return code

    def swap(self, code: str) -> SwapResult:
        """Trade a code for the read key. The code works once.

        The check and the mark run under one lock, because the route runs in the
        threadpool and two swaps of one code must not both succeed.

        Args:
            code: The code text from the page.

        Returns:
            The read key, the instance id and the project the code carried.

        Raises:
            SwapError: When the code is used, expired, unknown or from another run.
        """
        with self._lock:
            now = self.clock()
            self._purge(now)
            prefix, dot, _ = code.partition(".")
            if not dot or not _INSTANCE_PATTERN.match(prefix):
                raise SwapError("code_unknown")
            if prefix != self.instance:
                raise SwapError("server_restarted")
            entry = self._codes.get(_digest(code))
            if entry is None:
                raise SwapError("code_unknown")
            if entry.used:
                raise SwapError("code_used")
            if now >= entry.expires:
                raise SwapError("code_expired")
            entry.used = True
            return SwapResult(self.read_key, self.instance, entry.project)

    def _purge(self, now: float) -> None:
        """Forget entries long past their lifetime so the store stays small."""
        stale = [
            key
            for key, entry in self._codes.items()
            if now - entry.expires > _FORGET_AFTER_SECONDS
        ]
        for key in stale:
            del self._codes[key]


def _digest(code: str) -> str:
    """Return the store key for a code, so lookups never compare the raw text."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def build_router(
    state: AccessState, on_mint: Callable[[], None] | None = None
) -> APIRouter:
    """Build the router for ``/api/access/swap`` and ``/api/access/mint``.

    Args:
        state: The access state of this server run.
        on_mint: Called after each mint. The store provider uses it to start a retry
            of a failed ingest, so the first-run "try again" command works.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(prefix="/api/access", tags=["access"])

    @router.post(
        "/swap",
        response_model=SwapResponse,
        name="swap_code",
        responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )
    def swap_code(body: SwapRequest) -> SwapResponse:
        try:
            result = state.swap(body.code)
        except SwapError as err:
            raise HTTPException(status_code=403, detail=err.reason) from None
        return SwapResponse(
            read_key=result.read_key,
            edit_keys={},
            instance=result.instance,
            project=result.project,
        )

    @router.post(
        "/mint",
        response_model=MintResponse,
        name="mint_code",
        responses={401: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
    )
    def mint_code(body: MintRequest) -> MintResponse:
        code = state.mint_code(body.project)
        if on_mint is not None:
            on_mint()
        return MintResponse(code=code)

    return router
