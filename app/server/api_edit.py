"""Routes for edits and the Changes page (m6-build.md section 4.2).

Two routers, because the edits switch decides which ones exist.

``build_always_router`` holds the routes that write nothing outside the store root. They
stay mounted with edits off, so Changes works on the default start. They are history,
the recheck read, the drift read, a row's "seen" mark and the open warning.

``build_edits_router`` holds ``preview``, ``save`` and ``undo``. It is mounted only with
edits on. With edits off, ``build_off_router`` answers the same three paths with
``{code: "edits_off"}`` instead of a bare 404. The gate already refuses an edit write
before a router sees it, so these answers back the gate up. Every handler of the edits
router also checks the switch at call time, because it can turn from on to unavailable
after the routes were mounted.

Each handler is a plain ``def``, so the server runs it whole in one worker thread. That
is what the write permit needs (m6-build.md section 3.5): no ``await`` inside it.

Answers. A refusal of the writer is 422 with ``{server_time, code, params}``
(``EditError``). A file or body that changed since the preview is 409 with a fresh
preview (``EditConflict``). An undo of a file that changed since the save is 409 with
the undo diff and its own token (``UndoConflict``). ``unknown_edit`` is 404 and
``edits_off`` is 403, both in the shared error envelope. A masked diff, a changed key
and a ledger value never carry a secret or an edit key. Logs name a refusal code and
nothing else.
"""

# ruff: noqa: PLR0913, PLR0915, PLR0917 - a router builder holds one closure per
# route, and a request's parts are many.

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

import edit_diff
import edit_history
import edit_preview
import edit_store
import errors
import project_map
import read_scope
import store_paths
from access import AccessState
from api_live import ProjectQuery
from edit_preview import EditInputs
from edit_service import EditService
from edit_store import EditStore, Refused, RowStatus
from models import (
    INVALID_REQUEST_RESPONSE,
    BackupFolder,
    DriftAnswer,
    EditConflict,
    EditError,
    EditHistory,
    EditPreview,
    EditPreviewRequest,
    EditSaved,
    EditSaveRequest,
    EditsState,
    EditUndoRequest,
    ErrorEnvelope,
    HistoryOlder,
    HistoryRow,
    MarkSeenRequest,
    OpenWarning,
    RecheckAnswer,
    UndoConflict,
    UndoDone,
    UndoPreview,
)
from provider import Provider, UnknownProjectError

logger = logging.getLogger("bartab.edit")

RowId = Annotated[str, PathParam(min_length=1, max_length=200)]
ItemQuery = Annotated[str | None, Query(max_length=200)]
_FIXTURE_BACKUPS = "~/.claude/routing-dashboard/backups"
_NO_STORE = {"Cache-Control": "no-store"}

_WRITE_RESPONSES: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorEnvelope},
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": EditConflict},
    422: {"model": EditError},
}


def _edits_off() -> HTTPException:
    return HTTPException(status_code=403, detail="edits_off")


def _unknown_project() -> HTTPException:
    return HTTPException(status_code=404, detail="unknown_project")


def _unknown_edit() -> HTTPException:
    return HTTPException(status_code=404, detail="unknown_edit")


def _require_project(provider: Provider, project: str | None) -> str:
    """Return the project key, or raise ``bad_request`` or ``unknown_project``."""
    if project is None:
        raise errors.FieldError(400, "bad_request", ["query", "project"])
    if project not in {item.key for item in provider.projects().projects}:
        raise _unknown_project()
    return project


def _backup_folder(config_dir: Path | None) -> BackupFolder:
    """The folder the backups live in. A run with no Claude folder names the default."""
    if config_dir is None:
        return BackupFolder(display=_FIXTURE_BACKUPS, real=_FIXTURE_BACKUPS)
    folder = store_paths.backups_dir(config_dir)
    home = os.environ.get("HOME") or None
    return BackupFolder(
        display=project_map.display_path(str(folder), home),
        real=os.path.realpath(folder),
    )


def _answer(status: int, body: EditError | EditConflict | UndoConflict) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=body.model_dump(mode="json", by_alias=True),
        headers=_NO_STORE,
    )


def _refused(service: EditService, exc: Refused) -> JSONResponse:
    """Answer a refusal of the writer: 404 for an unknown row, else 422."""
    if exc.code == "unknown_edit":
        raise _unknown_edit()
    if exc.code == "edits_off":
        raise _edits_off()
    params = dict(exc.params)
    if exc.row_id is not None:
        params["row_id"] = exc.row_id
    logger.info("edit refused: %s", exc.code)
    return _answer(
        422,
        EditError(server_time=service.provider.now(), code=exc.code, params=params),
    )


def _status_of(
    store: EditStore, target: edit_store.Target, row: dict[str, object]
) -> RowStatus:
    try:
        return store.row_status(target, row)
    except Refused:
        return RowStatus("not_undoable", "file_refused", False)


def _history_rows(
    service: EditService,
    store: EditStore,
    inputs: EditInputs,
    project: str,
    found: list[edit_history.Found],
    targets: list[edit_store.Target],
) -> tuple[list[HistoryRow], list[HistoryRow]]:
    seen = service.seen(inputs)
    show = read_scope.Scope(inputs.setup).display
    by_file: dict[str, list[HistoryRow]] = {}
    for item in found:
        row = edit_history.history_row(
            item.target,
            item.row,
            _status_of(store, item.target, item.row),
            item.siblings,
            seen,
            project,
            show,
        )
        by_file.setdefault(item.target.display_path, []).append(row)
    newest: list[HistoryRow] = []
    older: list[HistoryRow] = []
    for rows in by_file.values():
        ordered = edit_history.newest_first(rows)
        newest.extend(ordered[: edit_history.PER_FILE])
        older.extend(ordered[edit_history.PER_FILE :])
    covered = {_target_id(store, target) for target in targets}
    backups = str(store.context.backups_root)
    for row in edit_history.scan_other_rows(backups, covered, project):
        older.append(edit_history.history_row(None, row, None, [], seen, project, show))
    return edit_history.newest_first(newest), edit_history.newest_first(older)


def _target_id(store: EditStore, target: edit_store.Target) -> str:
    try:
        return store.resolve(target).target_id
    except Refused:
        return edit_store.target_id_of(os.path.realpath(target.display_path))


def build_always_router(
    provider: Provider,
    state: AccessState,
    claude_dir: Path | None = None,
    service: EditService | None = None,
) -> APIRouter:
    """Build the edit routes that stay mounted with edits off.

    Args:
        provider: Where the project list and each project's folders come from.
        state: The access state that holds the edits switch.
        claude_dir: The Claude folder, for the backups folder a run with no project
            inputs names.
        service: The shared writer and marks. Built here when None.

    Returns:
        A router ready for ``include_router``.
    """
    shared = service or EditService(provider, state)
    router = APIRouter(
        prefix="/api/edit",
        tags=["edit"],
        responses={
            400: {"model": ErrorEnvelope},
            401: {"model": ErrorEnvelope},
            404: {"model": ErrorEnvelope},
            422: INVALID_REQUEST_RESPONSE,
        },
    )

    def inputs_of(project: str) -> EditInputs | None:
        try:
            return shared.inputs(project)
        except UnknownProjectError:
            raise _unknown_project() from None

    def row_of(
        project: str, row_id: str
    ) -> tuple[EditStore, EditInputs, edit_history.Found]:
        inputs = inputs_of(project)
        if inputs is None:
            raise _unknown_edit()
        store = shared.store(inputs)
        targets = edit_preview.targets_of(store, inputs)
        item = edit_history.find_row(store, targets, project, row_id)
        if item is None:
            raise _unknown_edit()
        return store, inputs, item

    @router.get("/history", response_model=EditHistory, name="get_edit_history")
    def get_history(project: ProjectQuery = None) -> EditHistory:
        key = _require_project(provider, project)
        inputs = inputs_of(key)
        edits = EditsState(state=state.edits, instance=state.instance)
        if inputs is None:
            return EditHistory(
                server_time=provider.now(),
                rows=[],
                older=HistoryOlder(count=0, rows=[]),
                backup_folder=_backup_folder(claude_dir),
                edits=edits,
            )
        store = shared.store(inputs)
        targets = edit_preview.targets_of(store, inputs)
        found = edit_history.read_found(store, targets, key)
        shared.refresh_checking(store, found)
        rows, older = _history_rows(shared, store, inputs, key, found, targets)
        return EditHistory(
            server_time=provider.now(),
            rows=rows,
            older=HistoryOlder(count=len(older), rows=older),
            backup_folder=_backup_folder(inputs.setup.config_dir),
            edits=edits,
        )

    @router.get("/open", response_model=OpenWarning, name="get_edit_open")
    def get_open(project: ProjectQuery = None, item: ItemQuery = None) -> OpenWarning:
        key = _require_project(provider, project)
        inputs = inputs_of(key)
        none = OpenWarning(server_time=provider.now(), row=None)
        field = edit_history.field_of_item(item)
        if inputs is None or (item is not None and field is None):
            return none
        store = shared.store(inputs)
        targets = edit_preview.targets_of(store, inputs)
        seen = shared.seen(inputs)
        show = read_scope.Scope(inputs.setup).display
        best: HistoryRow | None = None
        for found in edit_history.read_found(store, targets, key):
            row = found.row
            recheck = edit_history.recheck_of(row, seen, key)
            if recheck is None or recheck.state != "overwritten" or recheck.seen:
                continue
            made = edit_history.history_row(
                found.target,
                row,
                _status_of(store, found.target, row),
                found.siblings,
                seen,
                key,
                show,
            )
            if field is not None and made.field != field:
                continue
            if best is None or (made.time, made.id) > (best.time, best.id):
                best = made
        return OpenWarning(server_time=provider.now(), row=best)

    @router.get("/rows/{row_id}", response_model=RecheckAnswer, name="get_edit_row")
    def get_row(row_id: RowId, project: ProjectQuery = None) -> RecheckAnswer:
        key = _require_project(provider, project)
        store, inputs, found = row_of(key, row_id)
        shared.refresh_checking(store, [found])
        return edit_history.recheck_answer(
            found.row, shared.seen(inputs), key, provider.now()
        )

    @router.get(
        "/rows/{row_id}/drift",
        response_model=DriftAnswer,
        name="get_edit_drift",
        responses={422: {"model": EditError}},
    )
    def get_drift(
        row_id: RowId, project: ProjectQuery = None
    ) -> DriftAnswer | JSONResponse:
        key = _require_project(provider, project)
        inputs = inputs_of(key)
        if inputs is None:
            raise _unknown_edit()
        store = shared.store(inputs)
        targets = edit_preview.targets_of(store, inputs)
        try:
            data = store.drift(targets, key, row_id)
        except Refused as exc:
            if exc.code == "cant_rebuild":
                return DriftAnswer(
                    server_time=provider.now(), lines=None, code="cant_rebuild"
                )
            return _refused(shared, exc)
        return DriftAnswer(
            server_time=provider.now(),
            lines=edit_diff.diff_lines(data.written, data.now),
            code=None,
        )

    @router.post(
        "/rows/{row_id}/seen", response_model=RecheckAnswer, name="mark_edit_seen"
    )
    def mark_seen(row_id: RowId, body: MarkSeenRequest) -> RecheckAnswer:
        key = _require_project(provider, body.project)
        _store, inputs, found = row_of(key, row_id)
        marks = shared.seen(inputs)
        marks.mark(key, row_id)
        return edit_history.recheck_answer(found.row, marks, key, provider.now())

    return router


def _fresh_preview(
    service: EditService,
    store: EditStore,
    inputs: EditInputs,
    body: EditPreviewRequest,
    server_time: datetime,
) -> EditPreview:
    project = body.project
    return edit_preview.build_preview(
        store,
        inputs,
        body,
        server_time=server_time,
        now_iso=service.now().isoformat(),
        reach_inputs=lambda: service.reach_inputs(project),
    )


def build_edits_router(
    state: AccessState,
    provider: Provider,
    service: EditService | None = None,
) -> APIRouter:
    """Build the routes mounted only with edits on: preview, save and undo.

    Args:
        state: The access state. Each handler checks it again at call time.
        provider: Where the project list and each project's folders come from.
        service: The shared writer and marks. Built here when None.

    Returns:
        A router ready for ``include_router``.
    """
    shared = service or EditService(provider, state)
    router = APIRouter(prefix="/api/edit", tags=["edit"], responses=_WRITE_RESPONSES)

    def check_on() -> None:
        if state.edits != "on":
            raise _edits_off()

    def inputs_of(project: str) -> EditInputs | None:
        try:
            return shared.inputs(project)
        except UnknownProjectError:
            raise _unknown_project() from None

    @router.post("/preview", response_model=EditPreview, name="post_edit_preview")
    def post_preview(body: EditPreviewRequest) -> EditPreview | JSONResponse:
        check_on()
        key = _require_project(provider, body.project)
        inputs = inputs_of(key)
        if inputs is None:
            return _refused(shared, Refused("not_editable"))
        store = shared.store(inputs)
        return _fresh_preview(shared, store, inputs, body, provider.now())

    @router.post("/save", response_model=EditSaved, name="post_edit_save")
    def post_save(body: EditSaveRequest) -> EditSaved | JSONResponse:
        check_on()
        key = _require_project(provider, body.project)
        inputs = inputs_of(key)
        if inputs is None:
            return _refused(shared, Refused("not_editable"))
        store = shared.store(inputs)
        path: tuple[str, ...] = ()
        try:
            target, path = edit_preview.save_target(store, inputs, body)
            done = store.save(target, body, key_path=path)
        except Refused as exc:
            if exc.code in ("changed", "preview_mismatch"):
                return _conflict(shared, store, inputs, body, path, exc)
            return _refused(shared, exc)
        return EditSaved(
            server_time=provider.now(),
            row_id=done.row_id,
            saved_at=done.saved_at,
            recheck_after_ms=done.recheck_after_ms,
        )

    def _conflict(
        service: EditService,
        store: EditStore,
        inputs: EditInputs,
        body: EditSaveRequest,
        path: tuple[str, ...],
        exc: Refused,
    ) -> JSONResponse:
        logger.info("edit refused: %s", exc.code)
        server_time = provider.now()
        fresh: EditPreview | None
        try:
            fresh = _fresh_preview(service, store, inputs, body, server_time)
        except Refused:
            fresh = None
        keys: list[str] = []
        if exc.preview is not None and exc.current is not None:
            keys = edit_diff.changed_keys(exc.preview.raw, exc.current.raw)
        return _answer(
            409,
            EditConflict(
                server_time=server_time,
                code=exc.code,
                preview=fresh,
                changed_keys=keys,
                edited_key_changed=edit_diff.touches(keys, path),
            ),
        )

    @router.post(
        "/undo",
        response_model=UndoDone,
        name="post_edit_undo",
        responses={409: {"model": UndoConflict}},
    )
    def post_undo(body: EditUndoRequest) -> UndoDone | JSONResponse:
        check_on()
        key = _require_project(provider, body.project)
        inputs = inputs_of(key)
        if inputs is None:
            return _refused(shared, Refused("not_editable"))
        store = shared.store(inputs)
        targets = edit_preview.targets_of(store, inputs)
        try:
            done = store.undo(targets, key, body)
        except Refused as exc:
            if exc.code == "changed_since_save" and exc.undo_version is not None:
                logger.info("edit refused: %s", exc.code)
                current = None if exc.current is None else exc.current.raw
                backup = None if exc.backup is None else exc.backup.raw
                return _answer(
                    409,
                    UndoConflict(
                        server_time=provider.now(),
                        code=exc.code,
                        undo_preview=UndoPreview(
                            diff=edit_diff.edit_diff(current, backup),
                            version=exc.undo_version,
                        ),
                    ),
                )
            return _refused(shared, exc)
        return UndoDone(server_time=provider.now(), row_id=done.row_id)

    return router


def build_off_router() -> APIRouter:
    """Build the routes mounted with edits off. Each answers ``edits_off``.

    Returns:
        A router ready for ``include_router``.
    """
    router = APIRouter(
        prefix="/api/edit",
        tags=["edit"],
        include_in_schema=False,
        responses={403: {"model": ErrorEnvelope}},
    )

    @router.post("/preview", name="post_edit_preview")
    def post_preview() -> None:
        raise _edits_off()

    @router.post("/save", name="post_edit_save")
    def post_save() -> None:
        raise _edits_off()

    @router.post("/undo", name="post_edit_undo")
    def post_undo() -> None:
        raise _edits_off()

    return router
