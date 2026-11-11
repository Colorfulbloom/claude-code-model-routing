"""The new write core and the old app share one backups folder (task a4).

The old writer, ``dashboard/edit_store.py``, runs in a separate ``/usr/bin/python3 -B``
process (``interop_old.py``) with a throwaway HOME and ``CLAUDE_CONFIG_DIR``, a working
folder outside the repo and ``PYTHONDONTWRITEBYTECODE=1``. Both apps use the same
backups folder, ``ledger.json`` version 1, ``.lock`` and target id, so each must read,
undo and rebuild what the other wrote, and each must wait for the other's lock.

Pinned here, because both apps depend on it.

- Row field names. Every row has ``id``, ``time``, ``kind``, ``op``, ``key_path``,
  ``layer``, ``before_sha256``, ``after_sha256``, ``backup``, ``restored_from`` and
  ``restored_from_backup``. ``old_value``, ``new_value`` and ``made_dir`` come and go.
  The new app adds fields, and the old app keeps them when it rewrites a ledger.
- Words. ``kind`` is ``edit``, ``undo`` or ``restore``. ``op`` is ``replace``,
  ``insert``, ``create`` or ``remove``. ``time`` is UTC ``isoformat``. A backup is
  ``NNNNNN-<16 hex>.bak``, or ``.absent`` for a file that was not there.
- Order. History sorts rows by (time, backup number), newest first, as
  ``dashboard/api_edit.py`` does.

Nothing here touches ``dashboard/`` except to run it. Each call to the old app checks
that no ``__pycache__`` appeared there.
"""

# pyright: reportPrivateUsage=false

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_helpers import PROJECT_KEY, World, make_world, request_id, write_json

import edit_store
import git_root
import write_guard
from edit_store import EditContext, Refused

REPO = Path(__file__).resolve().parents[3]
DASHBOARD = REPO / "dashboard"
DRIVER = Path(__file__).resolve().with_name("interop_old.py")
PYTHON = "/usr/bin/python3"
FIELD = "model"

SETTINGS = '{\n  "model": "low",\n  "env": {"NOTE": "a"}\n}\n'
HIGH = SETTINGS.replace('"low"', '"high"')

CORE_FIELDS = {
    "id",
    "time",
    "kind",
    "op",
    "key_path",
    "layer",
    "before_sha256",
    "after_sha256",
    "backup",
    "restored_from",
    "restored_from_backup",
}
OPTIONAL_FIELDS = {"old_value", "new_value", "made_dir"}
NEW_ONLY_FIELDS = {
    "project",
    "field",
    "subject",
    "scope",
    "request_id",
    "display_path",
    "real_path",
    "app",
    "recheck",
}
KINDS = {"edit", "undo", "restore"}
OPS = {"replace", "insert", "create", "remove"}
TIME_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?\+00:00$")
BACKUP_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.bak$")
MARKER_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.absent$")

pytestmark = pytest.mark.skipif(
    not Path(PYTHON).exists(), reason="the old app runs under /usr/bin/python3"
)


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


# The old app, in its own process


def pycaches() -> set[str]:
    return {str(p) for p in DASHBOARD.rglob("__pycache__")}


def child_env(world: World) -> dict[str, str]:
    return {
        "HOME": str(world.home),
        "CLAUDE_CONFIG_DIR": str(world.config),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
    }


def request_for(world: World, op: str, **extra: Any) -> dict[str, Any]:
    return {
        "dashboard": str(DASHBOARD),
        "cfg": str(world.config),
        "home": str(world.home),
        "proj": str(world.project),
        "op": op,
        **extra,
    }


def start_old(world: World, op: str, **extra: Any) -> subprocess.Popen[str]:
    """Start the old app on a request and give back the running process."""
    proc = subprocess.Popen(  # noqa: S603 - a fixed system Python and our own driver
        [PYTHON, "-I", "-B", str(DRIVER)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=child_env(world),
        cwd=world.home.parent,
    )
    assert proc.stdin is not None
    proc.stdin.write(json.dumps(request_for(world, op, **extra)))
    proc.stdin.close()
    return proc


def finish_old(proc: subprocess.Popen[str]) -> dict[str, Any]:
    out, err = proc.communicate(timeout=60)
    assert proc.returncode == 0, err
    answer: dict[str, Any] = json.loads(out.strip().splitlines()[-1])
    return answer


Old = Callable[..., dict[str, Any]]


@pytest.fixture
def old(world: World) -> Old:
    """``old("save", layer=..., ...)`` runs the old app once and gives its answer."""

    def run(op: str, **extra: Any) -> dict[str, Any]:
        before = pycaches()
        answer = finish_old(start_old(world, op, **extra))
        assert pycaches() == before, "the old app wrote bytecode into dashboard/"
        return answer

    return run


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    made = make_world(edit_config, edit_project, secret=b"s" * 32)
    for scope in ("user", "project", "local"):
        write_json(made.path(scope), SETTINGS)
    return made


# Helpers on the new side


def save(w: World, value: str, scope: str = "project") -> dict[str, Any]:
    return w.save(value, scope, field_name=FIELD).row  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def rows(w: World, scope: str = "project") -> list[dict[str, Any]]:
    return w.store.read_rows(w.target(scope))  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def status(w: World, row: dict[str, Any]) -> str:
    return w.store.row_status(w.target(), row).undo_state


def read(path: str | Path) -> str:
    return Path(path).read_text()


def refused(call: Callable[[], object]) -> Refused:
    with pytest.raises(Refused) as caught:
        call()
    return caught.value


def numbers(w: World) -> list[int]:
    return [int(r["backup"][:6]) for r in w.ledger()]


# Target ids and the backups folder


def test_the_target_id_and_the_backups_folder_agree_for_every_settings_file(
    world: World, old: Old
) -> None:
    listed = old("files")["files"]
    assert [(f["layer"], f["leftover"]) for f in listed] == [
        ("user", False),
        ("project", False),
        ("local", False),
    ]
    for item in listed:
        path = Path(item["path"])
        scope = item["layer"]
        assert path == world.path(scope)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        # the id the old app hashes, the id the new app hashes, and the folder it uses
        assert item["id"] == edit_store.target_id_of(os.path.realpath(path))
        saved = save(world, "high", scope)  # type: ignore[arg-type]
        assert (world.backups / item["id"] / saved["backup"]).is_file()
        assert world.ledger_dir(scope).name == item["id"]  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]


def test_the_target_id_ignores_a_link_on_the_way_to_the_project(
    world: World, old: Old
) -> None:
    alias = world.home.parent / "alias-project"
    alias.symlink_to(world.project)
    ours = edit_store.settings_targets(world.ctx, alias)[1]
    real = edit_store.resolve_target(world.ctx, ours)
    assert real.target_id == edit_store.target_id_of(
        str(world.project / ".claude" / "settings.json")
    )
    listed = {f["layer"]: f for f in old("files")["files"]}
    assert listed["project"]["id"] == real.target_id


# Vocabulary


def test_both_apps_write_the_same_row_fields_words_and_names(
    world: World, old: Old
) -> None:
    claude = world.project / ".claude"
    # the old app: replace, insert, undo, restore, create and remove
    made_by_old: list[dict[str, Any]] = []
    first = old("save", layer="project", key_path=["model"], value="high")["row"]
    made_by_old.append(first)
    made_by_old.append(
        old("save", layer="project", key_path=["maxEffortLevel"], value="max")["row"]
    )
    removed = old(
        "save", layer="project", key_path=["maxEffortLevel"], value=None, remove=True
    )["row"]
    made_by_old.append(removed)
    undone = old("undo", layer="project", row_id=removed["id"])["row"]
    made_by_old.append(undone)
    put = old("undo", layer="project", row_id=first["id"], force=True, kind="restore")
    made_by_old.append(put["row"])
    shutil.rmtree(claude)
    made_by_old.append(
        old("save", layer="project", key_path=["model"], value="x")["row"]
    )

    # the new app: replace, insert, create, undo and restore
    shutil.rmtree(claude, ignore_errors=True)
    made_by_new: list[dict[str, Any]] = [save(world, "high", "user")]
    made_by_new.append(save(world, "medium", "user"))
    (world.path("local").parent).mkdir(exist_ok=True)
    write_json(world.path("local"), "{}\n")
    made_by_new.append(
        world.save("medium", "local", field_name="effortLevel").row,
    )
    made_by_new.append(world.undo(made_by_new[-1]["id"]).row)
    world.path("user").unlink()
    made_by_new.append(save(world, "first", "user"))
    token = world.store.restore_version(
        world.targets(), PROJECT_KEY, made_by_new[0]["id"]
    )
    del token  # the first user row is gone from the target's ledger view below

    for row in made_by_old:
        assert set(row) >= CORE_FIELDS, row
        assert set(row) <= CORE_FIELDS | OPTIONAL_FIELDS, set(row) - CORE_FIELDS
        assert TIME_RE.match(row["time"]), row["time"]
        assert row["kind"] in KINDS
        assert row["op"] in OPS
        assert BACKUP_RE.match(row["backup"]) or MARKER_RE.match(row["backup"])
    for row in made_by_new:
        assert set(row) >= CORE_FIELDS, row
        assert set(row) <= CORE_FIELDS | OPTIONAL_FIELDS | NEW_ONLY_FIELDS
        assert TIME_RE.match(row["time"]), row["time"]
        assert row["kind"] in KINDS
        assert row["op"] in OPS
        assert BACKUP_RE.match(row["backup"]) or MARKER_RE.match(row["backup"])
    # the words each app writes are the words the other reads
    assert {r["kind"] for r in made_by_old} == KINDS
    assert {r["op"] for r in made_by_old} == OPS
    assert {r["kind"] for r in made_by_new} >= {"edit", "undo"}
    assert {r["op"] for r in made_by_new} >= {"replace", "create"}
    # the new app reads every word the old one writes
    assert edit_store._ROW_KINDS == KINDS
    assert edit_store._ROW_OPS == OPS


def test_the_ledger_file_is_version_one_in_both_apps(world: World, old: Old) -> None:
    mine = save(world, "high")
    doc = json.loads((world.ledger_dir() / "ledger.json").read_text())
    assert set(doc) == {"version", "rows"}
    assert doc["version"] == 1
    theirs = old("save", layer="local", key_path=["model"], value="high")["row"]
    local_doc = json.loads((world.ledger_dir("local") / "ledger.json").read_text())
    assert set(local_doc) == {"version", "rows"}
    assert local_doc["version"] == 1
    assert [r["id"] for r in local_doc["rows"]] == [theirs["id"]]
    assert mine["id"] in {r["id"] for r in doc["rows"]}


# New writes, old reads and undoes


def test_new_saves_and_old_reads_and_undoes(world: World, old: Old) -> None:
    row = save(world, "high")
    seen = old("rows", layer="project")
    assert seen["damaged"] is False
    assert seen["rows"] == [row]  # the old app keeps the new app's extra fields
    assert seen["states"][row["id"]] is None
    undone = old("undo", layer="project", row_id=row["id"])
    assert undone["matches_backup"] is True
    assert read(world.path()) == SETTINGS
    assert undone["row"]["kind"] == "undo"
    assert undone["row"]["restored_from"] == row["id"]
    assert undone["row"]["restored_from_backup"] == row["backup"]
    # the new app reads both rows, calls the edit undone, and the extras survived
    found = rows(world)
    assert [r["id"] for r in found] == [row["id"], undone["row"]["id"]]
    assert found[0] == row
    assert status(world, found[0]) == "undone"
    # the old undo_state reads hashes and backups only, so it is silent on an undo row;
    # the row kind is what makes an undo row not undoable, and the new app says so
    assert old("rows", layer="project")["states"][undone["row"]["id"]] is None
    assert world.store.row_status(world.target(), found[1]).reason == "undo_row"


def test_new_creates_and_old_undoes_the_create_and_the_folder_it_made(
    world: World, old: Old
) -> None:
    shutil.rmtree(world.project / ".claude")
    row = save(world, "high")
    assert row["made_dir"] is True
    assert row["backup"].endswith(".absent")
    seen = old("rows", layer="project")
    assert seen["rows"] == [row]
    assert seen["states"][row["id"]] is None
    undone = old("undo", layer="project", row_id=row["id"])
    assert undone["removed_file"] is True
    assert undone["removed_dir"] is True
    assert not (world.project / ".claude").exists()
    # the old undo row is one the new app can read and rebuild
    found = rows(world)
    assert [r["kind"] for r in found] == ["edit", "undo"]
    assert found[1]["after_sha256"] == "absent"


def test_old_undoes_anyway_a_new_row_after_a_hand_edit(world: World, old: Old) -> None:
    row = save(world, "high")
    world.path().write_text('{"model": "by hand"}\n')
    assert old("rows", layer="project")["states"][row["id"]] == "changed_since_save"
    assert old("undo", layer="project", row_id=row["id"])["error"] == "ChangedSinceSave"
    old("undo", layer="project", row_id=row["id"], force=True)
    assert read(world.path()) == SETTINGS
    assert [r["kind"] for r in rows(world)] == ["edit", "undo"]


def test_old_reads_a_new_restore_row(world: World, old: Old) -> None:
    first = save(world, "high")
    save(world, "medium")
    token = world.store.restore_version(world.targets(), PROJECT_KEY, first["id"])
    result = world.store.restore(
        world.targets(),
        PROJECT_KEY,
        first["id"],
        version=token,
        request_id=request_id(),
    )
    assert read(world.path()) == SETTINGS
    seen = old("rows", layer="project")
    assert [r["kind"] for r in seen["rows"]][-1] == "restore"
    assert seen["rows"][-1]["id"] == result.row_id
    assert seen["rows"][-1] == result.row


# Old writes, new reads, undoes and rebuilds drift


def test_old_saves_and_new_reads_and_undoes(world: World, old: Old) -> None:
    row = old("save", layer="project", key_path=["model"], value="high")["row"]
    assert read(world.path()) == HIGH
    found = rows(world)
    assert found == [row]
    assert status(world, row) == "can_undo"
    result = world.undo(row["id"])
    assert read(world.path()) == SETTINGS
    assert result.row["kind"] == "undo"
    assert result.row["restored_from"] == row["id"]
    assert result.row["layer"] == "project"
    # the old app reads the new undo row and calls the edit undone
    seen = old("rows", layer="project")
    assert [r["id"] for r in seen["rows"]] == [row["id"], result.row_id]


def test_old_saves_and_new_rebuilds_the_drift_for_every_kind_of_write(
    world: World, old: Old
) -> None:
    other = '{"model": "someone else", "env": {"NOTE": "a"}, "extra": true}\n'
    cases: list[tuple[str, dict[str, Any]]] = [
        ("replace", {"key_path": ["model"], "value": "high"}),
        ("insert", {"key_path": ["maxEffortLevel"], "value": "max"}),
    ]
    for op, args in cases:
        write_json(world.path(), SETTINGS)
        shutil.rmtree(world.backups, ignore_errors=True)
        row = old("save", layer="project", **args)["row"]
        assert row["op"] == op
        written = world.path().read_bytes()
        world.path().write_text(other)
        drift = world.store.drift(world.targets(), PROJECT_KEY, row["id"])
        assert drift.written == written, op
        assert drift.now == other.encode(), op
        recheck = world.store.run_recheck(world.target(), row["id"])
        assert recheck is not None
        assert recheck["state"] == "overwritten", op
        assert "extra" in recheck["changed_keys"] or recheck["changed_keys"], op
    # a create, in a project that had no .claude folder
    shutil.rmtree(world.backups, ignore_errors=True)
    shutil.rmtree(world.project / ".claude")
    row = old("save", layer="project", key_path=["model"], value="high")["row"]
    assert row["op"] == "create"
    assert row["made_dir"] is True
    written = world.path().read_bytes()
    world.path().write_text(other)
    drift = world.store.drift(world.targets(), PROJECT_KEY, row["id"])
    assert drift.written == written
    assert drift.now == other.encode()


def test_a_remove_row_from_the_old_app_is_read_and_undone_but_not_rebuilt(
    world: World, old: Old
) -> None:
    row = old("save", layer="project", key_path=["env"], value=None, remove=True)["row"]
    assert row["op"] == "remove"
    assert status(world, row) == "can_undo"
    assert (
        code_of(lambda: world.store.drift(world.targets(), PROJECT_KEY, row["id"]))
        == "cant_rebuild"
    )
    world.undo(row["id"])
    assert read(world.path()) == SETTINGS


def code_of(call: Callable[[], object]) -> str:
    return refused(call).code


def test_new_undoes_an_old_create_with_the_folder_the_old_app_made(
    world: World, old: Old
) -> None:
    shutil.rmtree(world.project / ".claude")
    row = old("save", layer="project", key_path=["model"], value="high")["row"]
    assert row["made_dir"] is True
    result = world.undo(row["id"])
    assert result.removed_file is True
    assert result.removed_dir is True
    assert not (world.project / ".claude").exists()


def test_new_undoes_anyway_an_old_row_after_a_hand_edit(world: World, old: Old) -> None:
    row = old("save", layer="project", key_path=["model"], value="high")["row"]
    world.path().write_text('{"model": "by hand"}\n')
    err = refused(lambda: world.undo(row["id"]))
    assert err.code == "changed_since_save"
    world.undo(row["id"], anyway=True, version=err.undo_version)
    assert read(world.path()) == SETTINGS


# The shared lock


def wait_for(path: Path, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"{path.name} never appeared"
        time.sleep(0.02)


def test_the_old_app_holding_the_lock_makes_the_new_app_lock_busy(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = world.home.parent / "old-ready"
    go = world.home.parent / "old-go"
    holder = start_old(
        world,
        "save",
        layer="project",
        key_path=["model"],
        value="from-old",
        hold={"ready": str(ready), "go": str(go)},
    )
    try:
        wait_for(ready)
        monkeypatch.setattr(edit_store, "LOCK_WAIT", 0.3)
        err = refused(lambda: world.save("high", field_name=FIELD))
        assert err.code == "lock_busy"
        assert read(world.path()) == SETTINGS
    finally:
        go.write_text("go")
        answer = finish_old(holder)
    assert answer["row"]["new_value"] == "from-old"
    monkeypatch.setattr(edit_store, "LOCK_WAIT", 5.0)
    # once the old app is done, the new one takes the lock and sees the old row
    row = save(world, "high")
    assert [r["id"] for r in rows(world)] == [answer["row"]["id"], row["id"]]
    assert numbers(world) == [1, 2]


def test_the_new_app_holding_the_lock_makes_the_old_app_fail_to_take_it(
    world: World, old: Old
) -> None:
    started = threading.Event()
    release = threading.Event()
    outcome: dict[str, Any] = {}

    def hold(name: str) -> None:
        if name == "after_read":
            started.set()
            release.wait(30)

    def run() -> None:
        try:
            outcome["row"] = save(world, "high")
        except Refused as exc:  # pragma: no cover - the test fails on it below
            outcome["error"] = exc

    world.store.seam = hold
    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert started.wait(20)
        answer = old(
            "save", layer="project", key_path=["model"], value="from-old", lock_wait=0.3
        )
        assert answer["error"] == "WriteFailed"
        assert "locked by another writer" in answer["message"]
        assert read(world.path()) == SETTINGS
    finally:
        release.set()
        worker.join(30)
    assert "error" not in outcome
    assert read(world.path()) == HIGH
    # the old app takes the lock once the new one lets go
    after = old("save", layer="project", key_path=["model"], value="again")
    assert after["row"]["old_value"] == "high"
    assert numbers(world) == [1, 2]


# Order


def test_history_sorts_both_apps_rows_by_time_and_backup_number(
    world: World, old: Old
) -> None:
    order: list[str] = []
    order.append(save(world, "v1")["id"])
    order.append(
        old("save", layer="project", key_path=["model"], value="v2")["row"]["id"]
    )
    order.append(save(world, "v3")["id"])
    order.append(
        old("save", layer="project", key_path=["model"], value="v4")["row"]["id"]
    )
    order.append(save(world, "v5")["id"])
    ledger = world.ledger()
    assert [r["id"] for r in ledger] == order
    assert numbers(world) == [1, 2, 3, 4, 5]
    # api_edit.history: newest first by (time, backup number)
    newest_first = sorted(
        ledger, key=lambda r: (r["time"], int(r["backup"][:6])), reverse=True
    )
    assert [r["id"] for r in newest_first] == list(reversed(order))
    times = [r["time"] for r in ledger]
    assert times == sorted(times)
    assert all(TIME_RE.match(t) for t in times)


# Local layer parity


class Fixture:
    """One tree for the local-layer comparison."""

    def __init__(self, root: Path, name: str, version: str | None = None) -> None:
        self.root = root / name
        self.version = version
        self.home = root / (name + "-user")
        self.home.mkdir(parents=True)
        self.root.mkdir(parents=True)
        self.project = self.root

    def make_repo(self, folder: Path) -> None:
        (folder / ".git").mkdir(parents=True)

    def make_project(self, folder: Path) -> Path:
        (folder / ".claude").mkdir(parents=True, exist_ok=True)
        self.project = folder
        return folder


def build_plain(fx: Fixture) -> None:
    fx.make_project(fx.root / "app")


def build_root_is_project(fx: Fixture) -> None:
    fx.make_repo(fx.root / "app")
    fx.make_project(fx.root / "app")


def build_nested(fx: Fixture) -> None:
    fx.make_repo(fx.root / "mono")
    fx.make_project(fx.root / "mono" / "packages" / "web")


def build_nested_with_leftover(fx: Fixture) -> None:
    build_nested(fx)
    (fx.project / ".claude" / "settings.local.json").write_text("{}\n")


def build_root_is_home(fx: Fixture) -> None:
    fx.home = fx.root / "tilde"
    fx.make_repo(fx.home)
    fx.make_project(fx.home / "proj")


def build_git_symlink(fx: Fixture) -> None:
    folder = fx.root / "linked"
    folder.mkdir(parents=True)
    (folder / ".git").symlink_to(fx.root)
    fx.make_project(folder / "sub")


def build_old_claude_code(fx: Fixture) -> None:
    build_nested(fx)
    fx.version = "2.1.200"


def build_submodule(fx: Fixture) -> None:
    """A ``.git`` file whose git dir has no ``commondir``, so the folder is the root."""
    outer = fx.root / "outer"
    inner = outer / "modules" / "lib"
    (outer / ".git" / "modules" / "lib").mkdir(parents=True)
    inner.mkdir(parents=True)
    (inner / ".git").write_text(f"gitdir: {outer / '.git' / 'modules' / 'lib'}\n")
    fx.make_project(inner / "src")


def build_worktree(fx: Fixture) -> None:
    """A linked worktree of a main checkout, with a valid git chain."""
    main = fx.root / "main"
    work = fx.root / "wt"
    admin = main / ".git" / "worktrees" / "wt"
    admin.mkdir(parents=True)
    (admin / "commondir").write_text("../..\n")
    (admin / "gitdir").write_text(f"{work / '.git'}\n")
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {admin}\n")
    fx.make_project(work / "sub")


def build_broken_git_file(fx: Fixture) -> None:
    folder = fx.root / "odd"
    folder.mkdir(parents=True)
    (folder / ".git").write_text("not a gitdir line\n")
    fx.make_project(folder / "sub")


SAME_AS_OLD = {
    "plain": build_plain,
    "root_is_project": build_root_is_project,
    "nested": build_nested,
    "nested_with_leftover": build_nested_with_leftover,
    "root_is_home": build_root_is_home,
    "git_symlink": build_git_symlink,
    "old_claude_code": build_old_claude_code,
    "submodule": build_submodule,
}
# The one known difference. ``git_root.py`` stops at a linked worktree's own folder and
# does not follow its ``gitdir`` chain to the main checkout (its docstring says why),
# and the old app locks writes when the chain is broken. The new app picks the folder.
DIFFERS_FROM_OLD = {
    "worktree": build_worktree,
    "broken_git_file": build_broken_git_file,
}


def old_choice(world: World, fx: Fixture, old: Old) -> list[tuple[str, str, bool]]:
    """What the old app picks for the fixture, run against the fixture's own folders."""
    request = request_for(
        world,
        "files",
        proj=str(fx.project),
        home=str(fx.home),
        claude_version=fx.version,
    )
    before = pycaches()
    proc = subprocess.run(  # noqa: S603 - a fixed system Python and our own driver
        [PYTHON, "-I", "-B", str(DRIVER)],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        env=child_env(world),
        cwd=world.home.parent,
        check=True,
        timeout=60,
    )
    assert pycaches() == before
    files = json.loads(proc.stdout.strip().splitlines()[-1])["files"]
    return [(f["layer"], f["path"], f["leftover"]) for f in files]


def new_choice(world: World, fx: Fixture) -> list[tuple[str, str, bool]]:
    ctx = EditContext(config_dir=world.config, home=fx.home, claude_version=fx.version)
    return [
        (t.scope, t.display_path, t.leftover)
        for t in edit_store.settings_targets(ctx, fx.project)
    ]


def real(path: Path) -> Path:
    return Path(os.path.realpath(path))


@pytest.mark.parametrize("name", sorted(SAME_AS_OLD))
def test_the_local_file_is_the_one_the_old_app_picks_and_git_root_names(
    world: World, old: Old, tmp_path: Path, name: str
) -> None:
    fx = Fixture(real(tmp_path) / "parity", name)
    SAME_AS_OLD[name](fx)
    fx.project = real(fx.project)
    fx.home = real(fx.home)
    ours = new_choice(world, fx)
    assert ours == old_choice(world, fx, old), name
    # git_root.local_settings_path is where the new app takes the root file from
    root_file = (
        None if fx.version else git_root.local_settings_path(fx.project, fx.home)
    )
    local = next(item for item in ours if item[0] == "local" and not item[2])
    if root_file is None:
        assert local[1] == str(fx.project / ".claude" / "settings.local.json"), name
        assert not any(item[2] for item in ours), name
    else:
        assert local[1] == str(root_file), name
        leftovers = [item for item in ours if item[2]]
        assert leftovers == [
            ("local", str(fx.project / ".claude" / "settings.local.json"), True)
        ]


@pytest.mark.parametrize("name", sorted(DIFFERS_FROM_OLD))
def test_the_two_known_local_file_differences_stay_what_the_docstring_says(
    world: World, old: Old, tmp_path: Path, name: str
) -> None:
    fx = Fixture(real(tmp_path) / "parity", name)
    DIFFERS_FROM_OLD[name](fx)
    fx.project = real(fx.project)
    fx.home = real(fx.home)
    ours = new_choice(world, fx)
    theirs = old_choice(world, fx, old)
    assert ours != theirs, name
    if name == "worktree":
        # the old app follows the chain to the main checkout, the new one stops at the
        # worktree's own folder
        assert [p for _s, p, left in theirs if not left and "settings.local" in p] == [
            str(real(fx.root / "main") / ".claude" / "settings.local.json")
        ]
        assert [p for _s, p, left in ours if not left and "settings.local" in p] == [
            str(real(fx.root / "wt") / ".claude" / "settings.local.json")
        ]
    else:
        # the old app can't work the root out and starts in the project, and the new
        # one takes the folder that holds the ``.git`` file
        assert [p for _s, p, _left in theirs if "settings.local" in p] == [
            str(fx.project / ".claude" / "settings.local.json")
        ]
        assert [p for _s, p, left in ours if not left and "settings.local" in p] == [
            str(real(fx.root / "odd") / ".claude" / "settings.local.json")
        ]


def test_no_bytecode_appeared_in_dashboard_after_all_of_it(
    world: World, old: Old
) -> None:
    before = pycaches()
    old("files")
    old("save", layer="project", key_path=["model"], value="high")
    old("rows", layer="project")
    assert pycaches() == before
