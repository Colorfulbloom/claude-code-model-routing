"""What the two edit routers share: the one writer, the seen marks and the late recheck.

``EditStore`` holds the per-run token secret, the preview cache, the request ids and the
per-target locks, so a server has exactly one. The service builds it on first use from
the first project's inputs, because the Claude folder, the managed folder and the mode
are the same for every project of a run. The always-mounted router (history, rechecks,
drift, seen, open) and the edits-on router (preview, save, undo) get the same service.

A provider that can't say where a project's files are (the canned fixture) has no
``EditHost``. History answers empty for it, and a write is refused ``not_editable``.

A recheck can be lost to a restart. A row that is still ``checking`` past its last due
time has no run left, so a read that finds one runs it then, once at a time per row, and
only with edits on (the recheck writes the ledger, which needs edits on). Without edits
the row keeps saying ``checking``. A read-only judge in ``edit_store`` would remove that
gap.
"""

import logging
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import edit_history
import edit_preview
import edit_seen
from access import AccessState
from edit_preview import EditHost, EditInputs
from edit_store import EditStore, Refused, Scheduler, Target
from provider import Provider, UnknownProjectError

logger = logging.getLogger("bartab.edit")


class EditService:
    """The shared parts of the edit routes for one server."""

    def __init__(
        self,
        provider: Provider,
        state: AccessState,
        *,
        clock: Callable[[], datetime] | None = None,
        scheduler: Scheduler | None = None,
        secret: bytes | None = None,
    ) -> None:
        """Wire the service. Nothing is read until a route asks.

        Args:
            provider: Where the project list and each project's folders come from.
            state: The access state that holds the edits switch.
            clock: The writer's clock, for ``time`` on rows and the late recheck.
            scheduler: Runs a recheck after a delay. Tests pass a recorder.
            secret: The token secret. Defaults to a fresh one per run.
        """
        self.provider = provider
        self.state = state
        self._clock = clock or (lambda: datetime.now(UTC))
        self._scheduler = scheduler
        self._secret = secret
        self._store: EditStore | None = None
        self._seen: edit_seen.SeenMarks | None = None
        self._guard = threading.Lock()
        self._running: set[str] = set()
        self.host: EditHost | None = (
            provider if isinstance(provider, EditHost) else None
        )

    def now(self) -> datetime:
        """Return the writer's clock."""
        return self._clock()

    def inputs(self, project: str) -> EditInputs | None:
        """Return the project's inputs, or None when the provider can't say.

        Raises:
            UnknownProjectError: When ``project`` is not a project key.
        """
        if self.host is None:
            return None
        return self.host.edit_inputs(project)

    def store(self, inputs: EditInputs) -> EditStore:
        """Return the one writer, building it from the first project's inputs."""
        with self._guard:
            if self._store is None:
                self._store = EditStore(
                    edit_preview.base_context(inputs),
                    clock=self._clock,
                    scheduler=self._scheduler,
                    secret=self._secret,
                )
            return self._store

    def seen(self, inputs: EditInputs) -> edit_seen.SeenMarks:
        """Return the seen marks, kept in the store root."""
        with self._guard:
            if self._seen is None:
                self._seen = edit_seen.SeenMarks(inputs.store_root)
            return self._seen

    def reach_inputs(self, project: str) -> Iterator[tuple[str, str, EditInputs]]:
        """Yield the other projects' keys, names and inputs, for a user preview."""
        if self.host is None:
            return
        for item in self.provider.projects().projects:
            if item.key == project:
                continue
            try:
                yield item.key, item.name, self.host.edit_inputs(item.key)
            except (UnknownProjectError, OSError, ValueError):
                continue

    def refresh_checking(
        self, store: EditStore, found: list[edit_history.Found]
    ) -> None:
        """Run the late recheck for rows stuck on ``checking``, and update them.

        At most ``MAX_LATE_RUNS`` rows per call. Does nothing unless edits are on.
        """
        if self.state.edits != "on":
            return
        now = self.now()
        runs = 0
        for item in found:
            if runs >= edit_history.MAX_LATE_RUNS:
                return
            if edit_history.is_stuck(item.row, now) and self._late(
                store, item.target, item.row
            ):
                runs += 1

    def _late(self, store: EditStore, target: Target, row: dict[str, Any]) -> bool:
        row_id = str(row["id"])
        with self._guard:
            if row_id in self._running:
                return False
            self._running.add(row_id)
        try:
            recheck = store.run_recheck(target, row_id)
        except Refused:  # pragma: no cover - run_recheck swallows refusals
            recheck = None
        finally:
            with self._guard:
                self._running.discard(row_id)
        if recheck is None:
            return False
        row["recheck"] = recheck
        logger.info("late recheck ran")
        return True
