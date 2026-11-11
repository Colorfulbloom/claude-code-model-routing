"""Shared helpers for the write core tests (``test_edit_store*.py``).

A ``World`` is one throwaway machine under ``tmp_path``: a config folder, a project, a
writer with a recording scheduler (so no timer thread outlives a test), and shortcuts
that take a preview token the way the preview route will. Nothing here touches the real
Claude folder.
"""

import json
import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import edit_store
from edit_store import EditContext, EditStore, SaveResult, Target
from models import EditPreviewRequest, EditSaveRequest, EditScope, EditUndoRequest

PROJECT_KEY = "edit-project"
FIELD = "effortLevel"


def request_id() -> str:
    """Return a fresh request id the models accept."""
    return uuid.uuid4().hex


@dataclass
class World:
    """The folders and the writer of one test."""

    config: Path
    home: Path
    project: Path
    store: EditStore
    ctx: EditContext
    timers: list[tuple[float, Callable[[], None]]] = field(
        default_factory=list[tuple[float, Callable[[], None]]]
    )

    @property
    def backups(self) -> Path:
        """The old app's backups folder under the throwaway config folder."""
        return self.config / "routing-dashboard" / "backups"

    def targets(self) -> list[Target]:
        """The project's settings targets, as the registry builds them."""
        return edit_store.settings_targets(self.ctx, self.project)

    def target(self, scope: EditScope = "project") -> Target:
        """The target a save to ``scope`` writes."""
        return edit_store.settings_target(self.ctx, self.project, scope)

    def path(self, scope: EditScope = "project") -> Path:
        """The display path of a scope's file."""
        return Path(self.target(scope).display_path)

    def ledger_dir(self, scope: EditScope = "project") -> Path:
        """The backups folder of a scope's file (named by the real path's hash)."""
        real = os.path.realpath(self.path(scope))
        return self.backups / edit_store.target_id_of(real)

    def ledger(self, scope: EditScope = "project") -> list[dict[str, Any]]:
        """The ledger rows of a scope's file, as stored."""
        raw = (self.ledger_dir(scope) / "ledger.json").read_bytes()
        rows: list[dict[str, Any]] = json.loads(raw)["rows"]
        return rows

    def preview_body(
        self, value: str | int, scope: EditScope = "project", field_name: str = FIELD
    ) -> EditPreviewRequest:
        """A preview body for a settings value."""
        return EditPreviewRequest.model_validate(
            {
                "project": PROJECT_KEY,
                "op": "set",
                "scope": scope,
                "field": field_name,
                "value": value,
                "seq": 1,
            }
        )

    def version(
        self, value: str | int, scope: EditScope = "project", field_name: str = FIELD
    ) -> str:
        """The token a preview of this value would return, for the file as it is now."""
        seen = self.store.inspect(self.target(scope))
        return self.store.make_version(
            seen, self.preview_body(value, scope, field_name)
        )

    def save_body(
        self,
        value: str | int,
        scope: EditScope = "project",
        *,
        field_name: str = FIELD,
        version: str | None = None,
        rid: str | None = None,
    ) -> EditSaveRequest:
        """A save body. The token is the current one unless ``version`` is given."""
        token = (
            version if version is not None else self.version(value, scope, field_name)
        )
        return EditSaveRequest.model_validate(
            {
                "project": PROJECT_KEY,
                "op": "set",
                "scope": scope,
                "field": field_name,
                "value": value,
                "seq": 2,
                "version": token,
                "request_id": rid or request_id(),
            }
        )

    def save(
        self,
        value: str | int,
        scope: EditScope = "project",
        *,
        field_name: str = FIELD,
        key_path: Sequence[str] | None = None,
    ) -> SaveResult:
        """Preview and save a value in one step."""
        body = self.save_body(value, scope, field_name=field_name)
        return self.store.save(self.target(scope), body, key_path=key_path)

    def undo_body(
        self,
        row_id: str,
        *,
        anyway: bool = False,
        version: str | None = None,
        rid: str | None = None,
    ) -> EditUndoRequest:
        """An undo body."""
        return EditUndoRequest.model_validate(
            {
                "project": PROJECT_KEY,
                "row_id": row_id,
                "request_id": rid or request_id(),
                "version": version,
                "anyway": anyway,
            }
        )

    def undo(self, row_id: str, **kwargs: Any) -> edit_store.UndoResult:
        """Undo a row through the registry's targets."""
        return self.store.undo(
            self.targets(), PROJECT_KEY, self.undo_body(row_id, **kwargs)
        )

    def run_timers(self, index: int | None = None) -> None:
        """Run the recorded rechecks (all of them, or one by position)."""
        chosen = self.timers if index is None else [self.timers[index]]
        for _delay, work in list(chosen):
            work()


def make_world(
    config: Path,
    project: Path,
    *,
    ctx: EditContext | None = None,
    secret: bytes | None = None,
) -> World:
    """Build a world over the ``edit_config`` and ``edit_project`` fixtures."""
    home = config.parent
    context = ctx or EditContext(config_dir=config, home=home)
    timers: list[tuple[float, Callable[[], None]]] = []

    def scheduler(delay: float, work: Callable[[], None]) -> None:
        timers.append((delay, work))

    store = EditStore(context, scheduler=scheduler, secret=secret)
    # the store folder the real server makes before any edit
    (config / "routing-dashboard" / "bartab").mkdir(parents=True, exist_ok=True)
    return World(config, home, project, store, context, timers)


def write_json(path: Path, text: str, mode: int = 0o644) -> Path:
    """Write a settings file the way a person would have, with a chosen mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path
