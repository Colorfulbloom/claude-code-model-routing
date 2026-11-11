"""Run the OLD app's writer for the interop test (task a4, ``test_ledger_interop.py``).

The new write core must share a backups folder, a ledger, a lock and a target id with
``dashboard/edit_store.py``. The only honest check is to run that code, so
``test_ledger_interop.py`` starts this script in a separate process with the system
Python (``/usr/bin/python3 -B``), a throwaway HOME and ``CLAUDE_CONFIG_DIR``, a working
folder outside the repo and ``PYTHONDONTWRITEBYTECODE=1``. Only ``dashboard/`` is on the
import path, and the script writes no bytecode there.

It reads one JSON request from standard input and prints one JSON answer. Every
request names ``dashboard`` (the folder to import from), ``cfg`` (the config folder),
``home``, ``proj`` (the project folder) and ``op``.

Operations.

- ``files``: the project's settings files as the old ``project_files`` lists them, each
  with its target id.
- ``save``: set ``key_path`` to ``value`` the way the old edit route does (replace,
  insert or create, or cut the key out with ``remove``). ``lock_wait`` shortens the
  old lock wait. ``hold`` makes the save
  stop after its read, create the ``ready`` file and wait for the ``go`` file, so a test
  can hold the lock.
- ``rows``: the visible rows of a layer's ledger and the old ``undo_state`` of each.
- ``undo``: put a row's backup back, with ``force`` for "undo anyway" and ``kind`` for
  a restore.
- ``hash``: the file's hash as the old walk reads it.

The script has to run on the Python 3.9 that macOS ships, so it uses no newer syntax.
"""

# ruff: noqa: E501, PLR0915, TRY003, TRY301, T201, PTH110, PTH123 - a standalone
# script that answers on standard output, written for the old app's plain style.

from __future__ import annotations

import importlib
import json
import os
import sys
import time
from typing import Any


class Ctx:
    """The little the old ``projects`` and ``local_root`` modules read from a context."""

    def __init__(self, request: dict[str, Any]) -> None:
        self.config_dir = request["cfg"]
        self.project_dir = request["proj"]
        self.managed_dir = None
        self.home = request["home"]
        self.root = None
        self.project_explicit = True
        self.claude_version = request.get("claude_version")
        self.path_env = None


def answer_error(exc: BaseException) -> dict[str, Any]:
    return {
        "error": type(exc).__name__,
        "message": str(exc),
        "code": getattr(exc, "code", None),
        "reason": getattr(exc, "reason", None),
    }


def value_at(raw: bytes, key_path: list[str]) -> Any:
    try:
        node: Any = json.loads(raw.decode("utf-8"))
        for step in key_path:
            node = node[step]
    except (KeyError, TypeError, ValueError):
        return None
    return node


def main() -> None:
    request: dict[str, Any] = json.loads(sys.stdin.read())
    sys.path.insert(0, request["dashboard"])
    es: Any = importlib.import_module("edit_store")
    je: Any = importlib.import_module("json_edit")
    projects: Any = importlib.import_module("projects")
    ctx = Ctx(request)
    if "lock_wait" in request:
        es.LOCK_WAIT = request["lock_wait"]
    key = projects.load(ctx).current
    files = es.project_files(ctx, key)
    store = es.Store(request["cfg"])
    op = request["op"]

    def pick() -> Any:
        want_leftover = bool(request.get("leftover", False))
        for layer, target, leftover in files:
            if layer == request.get("layer") and leftover == want_leftover:
                return target
        raise SystemExit("no such layer")

    if op == "files":
        out = [
            {
                "layer": layer,
                "path": target.path,
                "leftover": leftover,
                "id": store.target_id(target),
            }
            for layer, target, leftover in files
        ]
        print(json.dumps({"files": out}))
        return
    target = pick()
    try:
        if op == "save":
            key_path = list(request["key_path"])
            value = request["value"]

            def plan_fn(raw: bytes | None) -> Any:
                path = tuple(key_path)
                if raw is None:
                    return es.Plan(
                        je.new_file(path, value), key_path, None, value, "create"
                    )
                try:
                    je.value_span(raw, path)
                    found = True
                except je.Refused as exc:
                    if exc.code != "key_missing":
                        raise
                    found = False
                old = value_at(raw, key_path)
                if request.get("remove"):
                    return es.Plan(
                        je.remove_key(raw, path), key_path, old, None, "remove"
                    )
                if found:
                    return es.Plan(
                        je.replace_value(raw, path, value),
                        key_path,
                        old,
                        value,
                        "replace",
                    )
                return es.Plan(
                    je.insert_value(raw, path, value), key_path, old, value, "insert"
                )

            hold = request.get("hold")
            if hold:

                def seam(name: str) -> None:
                    if name != "after_read":
                        return
                    with open(hold["ready"], "w", encoding="utf-8") as fh:
                        fh.write("ready")
                    deadline = time.time() + 30
                    while not os.path.exists(hold["go"]) and time.time() < deadline:
                        time.sleep(0.02)

                store.seam = seam
            row = store.save(target, plan_fn, allow_absent=True)
            print(json.dumps({"row": row}))
        elif op == "rows":
            rows = store.rows(target)
            states = {row["id"]: store.undo_state(target, row) for row in rows}
            print(
                json.dumps(
                    {
                        "rows": rows,
                        "states": states,
                        "damaged": store.ledger_damaged(target),
                    }
                )
            )
        elif op == "undo":
            done = store.restore(
                target,
                request["row_id"],
                force=bool(request.get("force", False)),
                kind=request.get("kind", "undo"),
            )
            print(
                json.dumps(
                    {
                        "row": done.row,
                        "removed_file": done.removed_file,
                        "removed_dir": done.removed_dir,
                        "matches_backup": done.matches_backup,
                    }
                )
            )
        elif op == "hash":
            print(json.dumps({"hash": store.file_hash(target)}))
        else:
            raise SystemExit("unknown op")
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - every old refusal is an answer
        print(json.dumps(answer_error(exc)))


if __name__ == "__main__":
    main()
