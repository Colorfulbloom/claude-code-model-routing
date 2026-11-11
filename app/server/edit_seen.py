"""The "seen" marks of the overwritten warning (m6-build 2, "Overwritten seen").

When another program changes a file Bar Tab saved, the inspector shows a warning. The
owner reads it and the page marks the row seen, so the warning stops coming back. The
mark has to work with edits off, so it can't live in the ledger, which sits outside the
store root and needs edits on to write.

The plan keeps the mark in a ``prefs`` table. No migration makes that table yet (it has
been deferred since M1), so the marks live in one small JSON file in the store root,
``edit-seen.json``, written by temp file and rename. ``SeenMarks`` is the only place
that knows. A later move to a table changes this file and nothing else.

Marks are kept per project, 200 per project, newest last. A file that is missing,
damaged or too big reads as no marks. A write that fails keeps the mark in memory for
the run and logs a fixed line, never a path or an id.
"""

import contextlib
import json
import logging
import os
import secrets
import threading
from pathlib import Path
from typing import Any, cast

import store_paths

logger = logging.getLogger("bartab.edit")

FILE_NAME = "edit-seen.json"
MAX_PER_PROJECT = 200
MAX_BYTES = 256 * 1024
MAX_PROJECTS = 200


class SeenMarks:
    """Which ledger rows the owner has seen, per project."""

    def __init__(self, folder: Path | None) -> None:
        """Make the marks. ``folder`` is the store root, or None for memory only."""
        self._folder = folder
        self._lock = threading.Lock()
        self._marks: dict[str, list[str]] | None = None

    def _load(self) -> dict[str, list[str]]:
        if self._marks is not None:
            return self._marks
        found: dict[str, list[str]] = {}
        if self._folder is not None:
            found = self._read(self._folder / FILE_NAME)
        self._marks = found
        return found

    @staticmethod
    def _read(path: Path) -> dict[str, list[str]]:
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            return {}
        try:
            data = os.read(fd, MAX_BYTES + 1)
        except OSError:
            return {}
        finally:
            os.close(fd)
        return _parse(data) if len(data) <= MAX_BYTES else {}

    def is_seen(self, project: str, row_id: str) -> bool:
        """Return True when the row was marked seen."""
        with self._lock:
            return row_id in self._load().get(project, [])

    def mark(self, project: str, row_id: str) -> None:
        """Mark a row seen. Marking twice changes nothing."""
        with self._lock:
            marks = self._load()
            ids = marks.setdefault(project, [])
            if row_id in ids:
                return
            ids.append(row_id)
            del ids[:-MAX_PER_PROJECT]
            self._save(marks)

    def _save(self, marks: dict[str, list[str]]) -> None:
        if self._folder is None:
            return
        layout = store_paths.StoreLayout(self._folder)
        temp: Path | None = None
        try:
            final = store_paths.writable(layout, self._folder / FILE_NAME)
            temp = store_paths.writable(
                layout, self._folder / f".seen-{secrets.token_hex(8)}.tmp"
            )
            body = json.dumps({"version": 1, "seen": marks}, sort_keys=True)
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(body.encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            temp.replace(final)
        except (OSError, store_paths.StorePathError):
            logger.warning("seen marks not saved")
            if temp is not None:
                with contextlib.suppress(OSError):
                    temp.unlink()


def _parse(data: bytes) -> dict[str, list[str]]:
    """Read the marks file's bytes. Anything that is not the expected shape is empty."""
    try:
        doc: object = json.loads(data.decode("utf-8"))
    except (ValueError, RecursionError):
        return {}
    if not isinstance(doc, dict):
        return {}
    top = cast("dict[str, Any]", doc)
    table: object = top.get("seen")
    if top.get("version") != 1 or not isinstance(table, dict):
        return {}
    out: dict[str, list[str]] = {}
    for project, ids in cast("dict[object, object]", table).items():
        if isinstance(project, str) and isinstance(ids, list):
            items = [i for i in cast("list[object]", ids) if isinstance(i, str)]
            out[project] = items[-MAX_PER_PROJECT:]
    return dict(list(out.items())[:MAX_PROJECTS])
