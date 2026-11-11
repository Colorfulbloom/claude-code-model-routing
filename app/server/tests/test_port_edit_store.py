"""The old ``tests/test_edit_store.py`` classes, ported to the new write core (task a4).

Ported classes: Walk, Save, Hostile, Crash, Restore, Raced, Retention, ReadOnly,
Create, CreateCrash, PruneMarker, UndoCreateCrash, UndoCreate, CreateDescriptor,
Force, ForgedRow, ForceCrash and ForceDescriptor. Each class below keeps the old
name and order, and each test keeps the old test's name where it still means the same
thing. The header of a class lists what was left out and why.

How the old API maps to the new one.

- ``Store.save(target, plan_fn)`` is ``World.save(value)`` on the ``model`` field. The
  ``model`` field takes any printable name, so the old tests' made-up values still
  work. The settings file is ``{"model": "low", "env": {"NOTE": "a"}}``.
- ``Store.restore(target, id)`` is ``World.undo(id)`` and a forced one is the two step
  "Undo anyway" (a refusal with a token, then ``anyway`` with that token). The old
  ``kind="restore"`` is ``EditStore.restore`` with a token from ``restore_version``.
- ``Store.rows`` is ``read_rows``. ``undo_state`` is ``row_status``, which also knows
  that an older row is ``not_newest``.
- An old cause that the new code lists no code for maps as the writer says. A link at
  the leaf or at ``.claude`` is written through, or ``link_outside`` and
  ``link_dangling``. A folder or link swapped under the walk is ``changed``. A missing
  base is ``folder_not_found``. An I/O failure is ``write_failed`` with params. A
  damaged ledger is ``ledger_damaged``. A forged backup name is ``forged_row``.
"""

# pyright: reportPrivateUsage=false
# ruff: noqa: E501, PTH208 - the tests list folders by os.listdir as the old tests did,
# and the prune test patches that very function.

import datetime
import hashlib
import json
import os
import re
import shutil
import stat
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
import write_guard
from edit_store import EditContext, EditStore, Refused, SaveResult, UndoResult
from models import EditScope

SETTINGS = b'{\n  "model": "low",\n  "env": {"NOTE": "a"}\n}\n'
HIGH = SETTINGS.replace(b'"low"', b'"high"')
NEW = b'{\n  "model": "high"\n}\n'
HAND = b'{"model": "hand", "env": {"NOTE": "by hand"}}\n'
HEX16 = "0123456789abcdef"
BAK_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.bak$")
FIELD = "model"


class Crash(BaseException):
    """Raised by a seam to stop the process at a step. No cleanup handler catches it."""


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    made = make_world(edit_config, edit_project, secret=b"s" * 32)
    for scope in ("user", "project", "local"):
        write_json(made.path(scope), SETTINGS.decode())
    return made


# Helpers


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(path: str | Path) -> bytes:
    return Path(path).read_bytes()


def write(path: str | Path, data: bytes) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def mode_of(path: str | Path) -> int:
    return stat.S_IMODE(Path(path).stat().st_mode)


def refused(call: Callable[[], object]) -> Refused:
    with pytest.raises(Refused) as caught:
        call()
    return caught.value


def code_of(call: Callable[[], object]) -> str:
    return refused(call).code


def save(w: World, value: str, scope: EditScope = "project") -> SaveResult:
    return w.save(value, scope, field_name=FIELD)


def rows(w: World, scope: EditScope = "project") -> list[dict[str, Any]]:
    return w.store.read_rows(w.target(scope))


def undo_state(
    w: World, row: dict[str, Any], scope: EditScope = "project"
) -> str | None:
    """The old ``undo_state`` words: None, changed_since_save, backup_pruned..."""
    status = w.store.row_status(w.target(scope), row)
    if status.undo_state in ("can_undo", "deletes_file"):
        return None
    if status.undo_state == "changed_since":
        return "changed_since_save"
    return status.reason or status.undo_state


def backup_reason(
    w: World, row: dict[str, Any], scope: EditScope = "project"
) -> tuple[str | None, bytes | None]:
    rs = w.store.resolve(w.target(scope))
    folder = w.store._open_store(rs, create=False)
    if folder is None:
        return "backup_pruned", None
    try:
        return w.store.backup_state(folder, row)
    finally:
        folder.close()


def raw_of(w: World, scope: EditScope = "project") -> bytes | None:
    return w.store.inspect(w.target(scope)).raw


def store_dir(w: World, scope: EditScope = "project") -> Path:
    return w.ledger_dir(scope)


def baks(w: World, scope: EditScope = "project") -> list[str]:
    folder = store_dir(w, scope)
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if BAK_RE.match(p.name))


def markers(w: World) -> list[str]:
    folder = store_dir(w)
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.name.endswith(".absent"))


def leftovers(w: World) -> list[str]:
    claude = w.project / ".claude"
    if not claude.is_dir():
        return []
    return sorted(
        p.name for p in claude.iterdir() if p.name.startswith(".routing-dashboard-")
    )


def age_temps(w: World) -> None:
    """Make every temp file in the project's folder look 61 s old.

    The sweep leaves a temp file under 60 s old alone, because another process may be
    mid-save. A crash test stands for a crash that happened a while ago.
    """
    claude = w.project / ".claude"
    if not claude.is_dir():
        return
    old = time.time() - 61
    for p in claude.iterdir():
        if p.name.startswith(".routing-dashboard-"):
            os.utime(p, (old, old))


def ledger_rows(w: World, scope: EditScope = "project") -> list[dict[str, Any]]:
    return w.ledger(scope)


def rewrite_ledger(w: World, edit: Callable[[list[dict[str, Any]]], None]) -> None:
    path = store_dir(w) / "ledger.json"
    doc = json.loads(read(path))
    edit(doc["rows"])
    write(path, json.dumps(doc).encode())


def project_file(w: World) -> Path:
    return w.path("project")


def at(w: World, name: str, fn: Callable[[], object]) -> None:
    """Run ``fn`` when the store reaches the seam called ``name``."""

    def seam(seen: str) -> None:
        if seen == name:
            fn()

    w.store.seam = seam


def crash_at(w: World, name: str) -> None:
    def boom() -> None:
        raise Crash(name)

    at(w, name, boom)


def restart(w: World) -> None:
    """A new writer over the same folders, as after a crashed process."""

    def scheduler(delay: float, work: Callable[[], None]) -> None:
        w.timers.append((delay, work))

    w.store = EditStore(w.ctx, scheduler=scheduler, secret=b"r" * 32)


def clean_store(w: World) -> None:
    """Take the backups folder away, so a loop starts from a world with no history."""
    shutil.rmtree(w.backups, ignore_errors=True)


def tree(root: Path) -> list[str]:
    return sorted(str(p) for p in root.rglob("*"))


def tree_hash(folder: Path) -> list[Any]:
    """Names, modes and bytes of everything under ``folder``."""
    found: list[Any] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        rel = os.path.relpath(dirpath, folder)
        found.append((rel, mode_of(dirpath)))
        for name in sorted(filenames):
            path = Path(dirpath) / name
            found.append((f"{rel}/{name}", mode_of(path), read(path)))
    return found


def force(w: World, row_id: str) -> UndoResult:
    """Undo, and when the file changed since the save, "Undo anyway" with its token."""
    try:
        return w.undo(row_id)
    except Refused as exc:
        if exc.code != "changed_since_save":
            raise
        token = exc.undo_version
    return w.undo(row_id, anyway=True, version=token)


def put_back(w: World, row_id: str) -> UndoResult:
    token = w.store.restore_version(w.targets(), PROJECT_KEY, row_id)
    return w.store.restore(
        w.targets(), PROJECT_KEY, row_id, version=token, request_id=request_id()
    )


def edited(w: World, value: str = "high") -> dict[str, Any]:
    return save(w, value).row


# Walk. The old walk refused every link. The new one resolves a link once and then
# writes through it, so the link cases take the new codes. Left out: the old
# ``read_target`` (there is no strict read, ``inspect`` takes its place).


class TestWalk:
    def code(self, w: World, scope: EditScope = "project") -> str:
        return code_of(lambda: w.store.inspect(w.target(scope)))

    def empty_claude(self, w: World) -> Path:
        claude = w.project / ".claude"
        shutil.rmtree(claude)
        return claude

    def test_a_plain_file_reads(self, world: World) -> None:
        assert raw_of(world, "project") == SETTINGS
        assert raw_of(world, "user") == SETTINGS

    def test_claude_folder_as_a_symlink_outside_home_and_project(
        self, world: World
    ) -> None:
        elsewhere = world.home.parent / "elsewhere"
        write(elsewhere / "settings.json", SETTINGS)
        claude = self.empty_claude(world)
        claude.symlink_to(elsewhere)
        assert self.code(world) == "link_outside"

    def test_claude_folder_as_a_symlink_inside_the_project_is_read_through(
        self, world: World
    ) -> None:
        inside = world.project / "real-claude"
        write(inside / "settings.json", SETTINGS)
        claude = self.empty_claude(world)
        claude.symlink_to(inside)
        assert raw_of(world) == SETTINGS

    def test_claude_folder_as_a_plain_file(self, world: World) -> None:
        claude = self.empty_claude(world)
        write(claude, b"x")
        assert self.code(world) == "not_regular"

    def test_missing_claude_folder_and_missing_file(self, world: World) -> None:
        project_file(world).unlink()
        seen = world.store.inspect(world.target("project"))
        assert seen.raw is None
        assert seen.missing_dir is False
        assert seen.sha256 == "absent"
        (world.project / ".claude" / "settings.local.json").unlink()
        (world.project / ".claude").rmdir()
        seen = world.store.inspect(world.target("project"))
        assert seen.raw is None
        assert seen.missing_dir is True

    def test_missing_base_folder(self, world: World) -> None:
        shutil.rmtree(world.project)
        assert self.code(world) == "folder_not_found"

    def test_leaf_symlink_project_and_user(self, world: World) -> None:
        outside = write(world.home.parent / "outside.json", SETTINGS)
        for scope in ("project", "user"):
            path = world.path(scope)
            path.unlink()
            path.symlink_to(outside)
            assert self.code(world, scope) == "link_outside", scope
        assert read(outside) == SETTINGS

    def test_dangling_leaf_symlink(self, world: World) -> None:
        path = project_file(world)
        path.unlink()
        path.symlink_to(world.home.parent / "nowhere.json")
        assert self.code(world) == "link_dangling"

    def test_leaf_hard_link(self, world: World) -> None:
        os.link(project_file(world), world.home.parent / "twin.json")
        assert self.code(world) == "hard_link"

    def test_leaf_directory(self, world: World) -> None:
        path = project_file(world)
        path.unlink()
        path.mkdir()
        assert self.code(world) == "not_regular"

    def test_leaf_fifo_returns_without_hanging(self, world: World) -> None:
        path = project_file(world)
        path.unlink()
        os.mkfifo(path)
        outcome: dict[str, str] = {}

        def run() -> None:
            try:
                world.store.inspect(world.target("project"))
                outcome["code"] = "read"
            except Refused as exc:
                outcome["code"] = exc.code

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(10)
        assert not worker.is_alive(), "the walk hung on a FIFO"
        assert outcome.get("code") == "not_regular"

    def test_leaf_fifo_in_a_save_creates_no_store_folder(self, world: World) -> None:
        path = project_file(world)
        path.unlink()
        os.mkfifo(path)
        body = world.save_body("high", field_name=FIELD, version="x")
        outcome: dict[str, str] = {}

        def run() -> None:
            try:
                world.store.save(world.target("project"), body)
            except Refused as exc:
                outcome["code"] = exc.code

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(10)
        assert not worker.is_alive(), "the save hung on a FIFO"
        assert outcome.get("code") == "not_regular"
        assert not world.backups.exists()

    def test_a_file_that_is_not_ours(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mine = os.geteuid()
        monkeypatch.setattr(os, "geteuid", lambda: mine + 1)
        assert self.code(world) == "not_owner"

    @pytest.mark.skipif(os.geteuid() == 0, reason="root can open any file")
    def test_an_unreadable_file_is_not_owner(self, world: World) -> None:
        path = project_file(world)
        path.chmod(0)
        try:
            assert self.code(world) == "not_owner"
        finally:
            path.chmod(0o600)

    def test_size_limit(self, world: World) -> None:
        path = project_file(world)
        write(path, b" " * edit_store.MAX_FILE)
        assert len(raw_of(world) or b"") == edit_store.MAX_FILE
        write(path, b" " * (edit_store.MAX_FILE + 1))
        assert self.code(world) == "too_large"

    def test_a_save_that_grows_the_file_past_the_cap_is_too_large(
        self, world: World
    ) -> None:
        path = project_file(world)
        raw = b"{}" + b" " * (edit_store.MAX_FILE - 2)
        write(path, raw)
        assert code_of(lambda: save(world, "high")) == "too_large"
        assert read(path) == raw
        assert baks(world) == []
        assert rows(world) == []

    def test_a_file_that_grows_during_the_read_is_too_large(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = project_file(world)
        write(path, b" " * 10)
        real_fstat = os.fstat

        def small_fstat(fd: int) -> os.stat_result:
            info = real_fstat(fd)
            if stat.S_ISREG(info.st_mode):
                write(path, b" " * (edit_store.MAX_FILE + 5))
            return os.stat_result(
                (
                    info.st_mode, info.st_ino, info.st_dev, info.st_nlink,
                    info.st_uid, info.st_gid, 10, int(info.st_atime),
                    int(info.st_mtime), int(info.st_ctime),
                )
            )  # fmt: skip

        monkeypatch.setattr(os, "fstat", small_fstat)
        assert self.code(world) == "too_large"

    def test_every_walk_closes_its_descriptors(self, world: World) -> None:
        os.link(world.path("local"), world.home.parent / "twin.json")
        before = fd_count()
        for _ in range(20):
            world.store.inspect(world.target("project"))
            assert self.code(world, "local") == "hard_link"
        assert fd_count() == before


# Save. Left out: a plan function that raises (the new API takes a value, not a plan
# function), and the old ``backup_path`` display helper (the ledger folder is read
# through ``World.ledger_dir``).


class TestSave:
    def test_save_splices_and_keeps_every_other_byte(self, world: World) -> None:
        row = edited(world)
        assert read(project_file(world)) == HIGH
        assert row["kind"] == "edit"
        assert row["key_path"] == ["model"]
        assert row["layer"] == "project"
        assert row["old_value"] == "low"
        assert row["new_value"] == "high"
        assert row["before_sha256"] == sha(SETTINGS)
        assert row["after_sha256"] == sha(read(project_file(world)))
        assert row["restored_from"] is None
        assert row["restored_from_backup"] is None
        assert re.match(r"^000001-[0-9a-f]{16}\.bak$", row["backup"])
        assert read(store_dir(world) / row["backup"]) == SETTINGS
        assert rows(world) == [row]

    def test_all_three_layers_save_into_the_config_folder(self, world: World) -> None:
        ids: set[str] = set()
        for scope in ("user", "project", "local"):
            row = save(world, "high", scope).row
            ids.add(store_dir(world, scope).name)
            assert read(world.path(scope)) == HIGH, scope
            assert baks(world, scope) == [row["backup"]], scope
        assert len(ids) == 3
        assert (world.config / "routing-dashboard").is_dir()
        assert os.listdir(world.project) == [".claude"]

    def test_nothing_lands_in_the_project_folder_but_the_file(
        self, world: World
    ) -> None:
        before = sorted(os.listdir(world.project / ".claude"))
        save(world, "high", "local")
        assert sorted(os.listdir(world.project / ".claude")) == before

    def test_modes_are_kept_and_the_store_is_private(self, world: World) -> None:
        project_file(world).chmod(0o640)
        row = edited(world)
        assert mode_of(project_file(world)) == 0o640
        folder = store_dir(world)
        for part in (world.config / "routing-dashboard", world.backups, folder):
            assert mode_of(part) == 0o700, part
        for name in (row["backup"], "ledger.json", ".lock"):
            assert mode_of(folder / name) == 0o600, name

    def test_a_wide_store_folder_is_narrowed(self, world: World) -> None:
        folder = store_dir(world)
        folder.mkdir(parents=True)
        folder.chmod(0o755)
        edited(world)
        assert mode_of(folder) == 0o700

    def test_the_ledger_stores_values_masked(self, world: World) -> None:
        write(project_file(world), b'{"model": "sk-planted-one", "env": {"A": "b"}}\n')
        row = edited(world, "low")
        assert row["old_value"] == "hidden"
        assert row["new_value"] == "low"
        # a value that looks like a secret is never saved, so no row ever holds one
        err = refused(lambda: save(world, "sk-planted-x"))
        assert err.code == "bad_value"
        assert b"planted" not in read(store_dir(world) / "ledger.json")

    def test_time_comes_from_the_clock_the_writer_was_given(self, world: World) -> None:
        stamp = datetime.datetime(2026, 10, 31, 12, 0, 0, tzinfo=datetime.UTC)
        world.store = EditStore(world.ctx, clock=lambda: stamp, secret=b"s" * 32)
        assert edited(world)["time"] == "2026-10-31T12:00:00+00:00"
        world.store = EditStore(world.ctx, secret=b"s" * 32)
        live = edited(world, "low")
        assert re.match(r"^\d{4}-\d\d-\d\dT.*\+00:00$", live["time"])

    def test_the_ledger_file_shape(self, world: World) -> None:
        row = edited(world)
        doc = json.loads(read(store_dir(world) / "ledger.json"))
        assert doc == {"version": 1, "rows": [row]}
        old_fields = {
            "id", "time", "kind", "op", "key_path", "layer", "old_value", "new_value",
            "before_sha256", "after_sha256", "backup", "restored_from",
            "restored_from_backup",
        }  # fmt: skip
        new_fields = {
            "project", "field", "subject", "scope", "request_id", "display_path",
            "real_path", "app", "recheck",
        }  # fmt: skip
        assert set(row) == old_fields | new_fields

    def test_backup_numbers_count_up_past_every_name_in_the_folder(
        self, world: World
    ) -> None:
        edited(world)
        write(store_dir(world) / ("000007-" + "a" * 16 + ".bak"), b"orphan")
        row = edited(world, "low")
        assert row["backup"].startswith("000008-"), row["backup"]

    def test_no_change_is_refused_and_writes_no_backup(self, world: World) -> None:
        assert code_of(lambda: save(world, "low")) == "no_change"
        assert baks(world) == []
        assert read(project_file(world)) == SETTINGS
        assert rows(world) == []

    def test_the_value_is_planned_from_the_bytes_read_under_the_lock(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[bytes | None] = []
        real = edit_store.plan_set

        def spy(raw: bytes | None, *args: Any, **kwargs: Any) -> edit_store.Plan:
            seen.append(raw)
            return real(raw, *args, **kwargs)

        monkeypatch.setattr(edit_store, "plan_set", spy)
        edited(world)
        assert seen == [SETTINGS]

    def test_a_refused_target_creates_no_store_folder(self, world: World) -> None:
        claude = world.project / ".claude"
        shutil.rmtree(claude)
        write(claude, b"x")
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "not_regular"
        )
        assert not world.backups.exists()

    def test_save_refuses_a_hard_linked_file_without_touching_it(
        self, world: World
    ) -> None:
        twin = world.home.parent / "twin.json"
        os.link(project_file(world), twin)
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "hard_link"
        )
        assert read(twin) == SETTINGS
        assert read(project_file(world)) == SETTINGS

    def test_leftover_temp_files_go_on_the_next_save(self, world: World) -> None:
        claude = world.project / ".claude"
        write(claude / (".routing-dashboard-" + "0" * 16 + ".tmp"), b"junk")
        write(claude / ".routing-dashboard-short.tmp", b"keep")
        write(claude / "notes.tmp", b"keep")
        age_temps(world)
        edited(world)
        assert leftovers(world) == [".routing-dashboard-short.tmp"]
        assert (claude / "notes.tmp").exists()

    def test_the_temp_file_is_gone_after_a_save(self, world: World) -> None:
        edited(world)
        assert leftovers(world) == []

    def test_fullfsync_falls_back_to_fsync(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def no_full(*_args: object) -> None:
            raise OSError(25, "no")

        monkeypatch.setattr(edit_store.fcntl, "fcntl", no_full)
        edited(world)
        assert read(project_file(world)) == HIGH

    def test_descriptors_do_not_grow_over_thirty_saves(self, world: World) -> None:
        edited(world, "v0")
        before = fd_count()
        for n in range(1, 31):
            edited(world, f"v{n}")
            rows(world)
        assert fd_count() == before

    def test_descriptors_do_not_grow_over_refusals_and_failures(
        self, world: World
    ) -> None:
        edited(world, "v0")
        before = fd_count()

        def fail() -> None:
            raise OSError(5, "io")

        for _ in range(5):
            assert code_of(lambda: save(world, "v0")) == "no_change"
            at(world, "after_temp", fail)
            assert code_of(lambda: save(world, "v9")) == "write_failed"
            world.store.seam = None
        assert fd_count() == before

    def test_a_missing_config_folder_is_its_own_refusal_and_creates_nothing(
        self, world: World
    ) -> None:
        gone = world.home.parent / "gone"
        ctx = EditContext(config_dir=gone, home=world.home)
        store = EditStore(ctx)
        target = edit_store.settings_target(ctx, world.project, "project")
        body = world.save_body("high", field_name=FIELD, version="x")
        assert code_of(lambda: store.save(target, body)) == "folder_not_found"
        assert not gone.exists()
        assert read(project_file(world)) == SETTINGS

    def test_concurrent_saves_run_one_after_another(self, world: World) -> None:
        errors: list[BaseException] = []
        done: list[str] = []

        def run(n: int) -> None:
            # a token is bound to the file it was read from, so a save that loses the
            # race is refused and reads again, as the page does
            for _ in range(200):
                try:
                    save(world, f"w{n}")
                except Refused as exc:
                    if exc.code in ("changed", "lock_busy"):
                        continue
                    errors.append(exc)
                    return
                done.append(f"w{n}")
                return

        workers = [threading.Thread(target=run, args=(n,)) for n in range(6)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
        assert errors == []
        assert sorted(done) == [f"w{n}" for n in range(6)]
        assert len(rows(world)) == 6
        assert len(baks(world)) == 6
        assert json.loads(read(project_file(world)))["model"] in done

    def test_two_stores_share_the_flock(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        edited(world)
        other = EditStore(world.ctx, secret=b"o" * 32)
        results: list[object] = []

        def inner() -> None:
            body = world.save_body("low", field_name=FIELD, version="x")
            try:
                other.save(world.target("project"), body)
                results.append("ok")
            except Refused as exc:
                results.append(exc)

        def hold() -> None:
            worker = threading.Thread(target=inner)
            worker.start()
            worker.join(30)

        at(world, "after_read", hold)
        monkeypatch.setattr(edit_store, "LOCK_WAIT", 0.3)
        edited(world, "v1")
        assert len(results) == 1
        assert isinstance(results[0], Refused)
        assert results[0].code == "lock_busy"
        assert len(rows(world)) == 2
        assert read(project_file(world)) == SETTINGS.replace(b'"low"', b'"v1"')

    def test_a_source_lint_keeps_writes_on_descriptors(self) -> None:
        source = Path(edit_store.__file__).read_text(encoding="utf-8")
        assert re.search(r"(?<![\w.])open\(", source) is None
        for banned in (
            r"\bshutil\b",
            r"\bio\.open\b",
            r"\bsubprocess\b",
            r"\bos\.(replace|remove|makedirs|truncate)\(",
            r"\.writelines?\(",
        ):
            assert re.search(banned, source) is None, banned
        # Two calls name an absolute path: the unlink of a half-made file under the
        # write guard's permit, and the mkdir of a backups folder under the backups
        # root. Every other unlink, rename, mkdir and rmdir goes by ``dir_fd``.
        without = [
            call
            for call in re.findall(
                r"\bos\.(?:unlink|rename|mkdir|rmdir)\([^)]*\)", source
            )
            if "dir_fd" not in call
        ]
        assert without == [
            "os.unlink(path)",
            "os.mkdir(os.path.join(parent_path, name)",
        ]


# Hostile. Every swap the old tests made under the walk, with the new codes.


class TestHostile:
    def test_leaf_swapped_for_a_symlink_before_recheck(self, world: World) -> None:
        path = project_file(world)
        outside = write(world.home.parent / "outside.json", b'{"outside": true}\n')
        folder = store_dir(world)  # named by the real path, so take it before the swap

        def swap() -> None:
            path.unlink()
            path.symlink_to(outside)

        at(world, "before_recheck", swap)
        assert code_of(lambda: save(world, "high")) == "changed"
        assert read(outside) == b'{"outside": true}\n'
        assert path.is_symlink()
        assert leftovers(world) == []
        assert [p for p in os.listdir(folder) if BAK_RE.match(p)] == []
        assert json.loads(read(folder / "ledger.json"))["rows"] == []
        # the swapped link now points outside, so the registry refuses to read rows
        assert code_of(lambda: rows(world)) == "link_outside"

    def test_leaf_swapped_for_a_symlink_before_rename_is_replaced(
        self, world: World
    ) -> None:
        path = project_file(world)
        outside = write(world.home.parent / "outside.json", b'{"outside": true}\n')

        def swap() -> None:
            path.unlink()
            path.symlink_to(outside)

        at(world, "before_rename", swap)
        save(world, "high")
        assert not path.is_symlink()
        assert read(path) == HIGH
        assert read(outside) == b'{"outside": true}\n'

    def test_claude_folder_swapped_for_a_link_before_recheck(
        self, world: World
    ) -> None:
        claude = world.project / ".claude"
        hold = world.home.parent / "held"
        elsewhere = world.home.parent / "elsewhere"
        write(elsewhere / "settings.json", b'{"outside": true}\n')

        def swap() -> None:
            claude.rename(hold)
            claude.symlink_to(elsewhere)

        at(world, "before_recheck", swap)
        assert code_of(lambda: save(world, "high")) == "changed"
        assert read(elsewhere / "settings.json") == b'{"outside": true}\n'
        assert sorted(os.listdir(elsewhere)) == ["settings.json"]
        assert read(hold / "settings.json") == SETTINGS
        assert [n for n in os.listdir(hold) if n.startswith(".routing")] == []

    def test_claude_folder_replaced_by_another_folder_is_changed(
        self, world: World
    ) -> None:
        claude = world.project / ".claude"
        hold = world.home.parent / "held"

        def swap() -> None:
            claude.rename(hold)
            write(claude / "settings.json", SETTINGS)

        at(world, "before_recheck", swap)
        assert code_of(lambda: save(world, "high")) == "changed"
        assert read(claude / "settings.json") == SETTINGS
        assert read(hold / "settings.json") == SETTINGS
        assert [n for n in os.listdir(hold) if n.startswith(".routing")] == []

    def test_in_place_race_is_changed_and_the_writers_bytes_survive(
        self, world: World
    ) -> None:
        path = project_file(world)
        theirs = b'{"model": "max", "extra": 1}\n'

        def rewrite() -> None:
            before = path.stat().st_ino
            with path.open("r+b") as fh:
                fh.truncate(0)
                fh.write(theirs)
            assert path.stat().st_ino == before

        at(world, "before_recheck", rewrite)
        assert code_of(lambda: save(world, "high")) == "changed"
        assert read(path) == theirs
        assert leftovers(world) == []
        assert baks(world) == []
        assert rows(world) == []
        assert json.loads(read(store_dir(world) / "ledger.json"))["rows"] == []

    def test_a_rename_race_before_recheck_is_changed_too(self, world: World) -> None:
        path = project_file(world)
        theirs = b'{"model": "max"}\n'

        def swap() -> None:
            write(path.with_name("settings.json.new"), theirs)
            path.with_name("settings.json.new").rename(path)

        at(world, "before_recheck", swap)
        assert code_of(lambda: save(world, "high")) == "changed"
        assert read(path) == theirs

    def test_an_io_failure_at_each_step_leaves_the_file_and_cleans_up(
        self, world: World
    ) -> None:
        for seam_name in (
            "before_backup",
            "after_backup",
            "after_ledger",
            "after_temp",
            "before_recheck",
            "before_rename",
        ):
            write(project_file(world), SETTINGS)
            clean_store(world)

            def fail() -> None:
                raise OSError(5, "simulated")

            at(world, seam_name, fail)
            err = refused(lambda: save(world, "high"))
            assert err.code == "write_failed", seam_name
            assert err.params == {"errno": "EIO"}, seam_name
            assert read(project_file(world)) == SETTINGS, seam_name
            assert leftovers(world) == [], seam_name
            assert baks(world) == [], seam_name
            assert rows(world) == [], seam_name
            world.store.seam = None

    def test_a_short_backup_read_back_fails_the_save(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = edit_store._read_file

        def short(name: str, dir_fd: int, cap: int) -> bytes:
            data = real(name, dir_fd, cap)
            return data[:-1] if name.endswith(".bak") else data

        monkeypatch.setattr(edit_store, "_read_file", short)
        err = refused(lambda: save(world, "high"))
        assert (err.code, err.params) == ("write_failed", {"stage": "backup_mismatch"})
        assert read(project_file(world)) == SETTINGS
        assert baks(world) == []

    def test_store_folder_as_a_link_fails_the_save(self, world: World) -> None:
        elsewhere = world.home.parent / "elsewhere"
        elsewhere.mkdir()
        shutil.rmtree(world.config / "routing-dashboard")
        (world.config / "routing-dashboard").symlink_to(elsewhere)
        assert code_of(lambda: save(world, "high")) == "write_failed"
        assert os.listdir(elsewhere) == []
        assert read(project_file(world)) == SETTINGS

    def test_target_folder_as_a_plain_file_fails_the_save(self, world: World) -> None:
        write(store_dir(world), b"x")
        assert code_of(lambda: save(world, "high")) == "write_failed"
        assert read(project_file(world)) == SETTINGS

    def test_ledger_as_a_link_is_a_damaged_ledger(self, world: World) -> None:
        edited(world)
        ledger = store_dir(world) / "ledger.json"
        outside = write(world.home.parent / "outside.json", b"{}")
        ledger.unlink()
        ledger.symlink_to(outside)
        assert code_of(lambda: save(world, "low")) == "ledger_damaged"
        assert read(outside) == b"{}"
        assert code_of(lambda: rows(world)) == "ledger_damaged"

    def test_a_damaged_ledger_hides_its_rows_and_refuses_a_save(
        self, world: World
    ) -> None:
        edited(world)
        ledger = store_dir(world) / "ledger.json"
        for junk in (
            b"not json",
            b"[]",
            b'{"version": 2, "rows": []}',
            b'{"version": 1, "rows": 5}',
            b'{"version": 1, "rows": [1]}',
            b"\xff\xfe",
        ):
            write(ledger, junk)
            before = read(project_file(world))
            assert code_of(lambda: rows(world)) == "ledger_damaged", junk
            assert code_of(lambda: save(world, "low")) == "ledger_damaged", junk
            assert read(project_file(world)) == before
            assert read(ledger) == junk
        assert len(baks(world)) == 1

    def test_a_sound_or_absent_ledger_is_not_damaged(self, world: World) -> None:
        assert rows(world) == []
        edited(world)
        assert len(rows(world)) == 1

    def test_bad_backup_names_in_the_ledger_are_pruned_to_read_and_forged_to_use(
        self, world: World
    ) -> None:
        row = edited(world)
        for bad in (
            "../../escape.bak",
            "000001-xyz.bak",
            None,
            5,
            "000001-" + "a" * 16 + ".BAK",
        ):
            doc = {"version": 1, "rows": [dict(row, backup=bad)]}
            write(store_dir(world) / "ledger.json", json.dumps(doc).encode())
            current = rows(world)[0]
            assert undo_state(world, current) == "backup_pruned", bad
            assert backup_reason(world, current) == ("backup_pruned", None)
            # the old app said backup_pruned for an undo too. The new core checks the
            # row's shape first, and a name that is not ours is a forged row.
            assert code_of(lambda: world.undo(row["id"])) == "forged_row", bad


# Crash


class TestCrash:
    def crash_then_restart(self, w: World, seam_name: str) -> None:
        crash_at(w, seam_name)
        with pytest.raises(Crash):
            save(w, "high")
        restart(w)
        age_temps(w)

    def reset(self, w: World) -> None:
        write(project_file(w), SETTINGS)
        clean_store(w)
        for name in leftovers(w):
            (w.project / ".claude" / name).unlink()
        restart(w)

    def test_crash_before_anything_is_written(self, world: World) -> None:
        self.crash_then_restart(world, "before_backup")
        assert read(project_file(world)) == SETTINGS
        assert baks(world) == []
        assert rows(world) == []

    def test_crash_after_the_backup_leaves_an_orphan_the_next_save_removes(
        self, world: World
    ) -> None:
        first = edited(world, "first")
        first_raw = read(project_file(world))
        self.crash_then_restart(world, "after_backup")
        assert read(project_file(world)) == first_raw
        orphan = [name for name in baks(world) if name != first["backup"]]
        assert len(orphan) == 1
        assert rows(world) == [first]
        row = edited(world, "low2")
        assert baks(world) == sorted([first["backup"], row["backup"]])
        assert orphan[0] not in baks(world)
        assert rows(world) == [first, row]

    def test_a_crash_with_a_never_applied_row_is_not_the_newest_row(
        self, world: World
    ) -> None:
        for seam_name in ("after_ledger", "after_temp", "before_rename"):
            self.reset(world)
            applied = edited(world, "mid")
            applied_raw = read(project_file(world))
            self.crash_then_restart(world, seam_name)
            assert read(project_file(world)) == applied_raw, seam_name
            on_disk = json.loads(read(store_dir(world) / "ledger.json"))
            assert len(on_disk["rows"]) == 2, seam_name
            # the row on disk is the orphan, and a read hides it
            assert rows(world) == [applied], seam_name
            assert undo_state(world, applied) is None, seam_name
            assert len(baks(world)) == 2, seam_name
            # the next save removes the orphan row and its backup, and the leftover temp
            row = edited(world, "end")
            assert rows(world) == [applied, row], seam_name
            assert baks(world) == sorted([applied["backup"], row["backup"]]), seam_name
            assert leftovers(world) == [], seam_name

    def test_an_applied_edit_survives_a_crash_after_the_rename_and_is_undoable(
        self, world: World
    ) -> None:
        for seam_name in ("after_rename", "dir_fsync", "reread"):
            self.reset(world)
            self.crash_then_restart(world, seam_name)
            assert read(project_file(world)) == HIGH, seam_name
            found = rows(world)
            assert len(found) == 1, seam_name
            assert undo_state(world, found[0]) is None, seam_name
            world.undo(found[0]["id"])
            assert read(project_file(world)) == SETTINGS, seam_name

    def test_the_file_is_whole_at_every_crash_point(self, world: World) -> None:
        for seam_name in (
            "before_backup",
            "after_backup",
            "after_ledger",
            "after_temp",
            "before_recheck",
            "before_rename",
            "after_rename",
            "dir_fsync",
            "reread",
        ):
            self.reset(world)
            self.crash_then_restart(world, seam_name)
            raw = read(project_file(world))
            assert raw in (SETTINGS, HIGH), seam_name
            json.loads(raw.decode("utf-8"))


# Restore. The old ``Store.restore`` is the new ``undo``. Left out: the old check hook
# (the new rule is ``not_newest``, tested below), and ``matches_backup`` and the path
# fields of the old result (the row carries the backup name instead).


class TestRestore:
    def test_restore_puts_the_bytes_back_with_its_own_backup_and_row(
        self, world: World
    ) -> None:
        row = edited(world)
        edited_bytes = read(project_file(world))
        result = world.undo(row["id"])
        assert read(project_file(world)) == SETTINGS
        undone = result.row
        assert undone["kind"] == "undo"
        assert undone["restored_from"] == row["id"]
        assert undone["restored_from_backup"] == row["backup"]
        assert undone["key_path"] == ["model"]
        assert undone["layer"] == "project"
        assert undone["old_value"] == "high"
        assert undone["new_value"] == "low"
        assert undone["before_sha256"] == sha(edited_bytes)
        assert undone["after_sha256"] == sha(SETTINGS)
        assert undone["backup"] != row["backup"]
        assert read(store_dir(world) / undone["backup"]) == edited_bytes
        assert read(store_dir(world) / row["backup"]) == SETTINGS
        assert rows(world) == [row, undone]

    def test_restore_masks_the_swapped_values(self, world: World) -> None:
        write(project_file(world), b'{"model": "sk-planted-a"}\n')
        row = edited(world, "low")
        assert row["old_value"] == "hidden"
        result = world.undo(row["id"])
        assert result.row["old_value"] == "low"
        assert result.row["new_value"] == "hidden"

    def test_unknown_edit(self, world: World) -> None:
        edited(world)
        for edit_id in ("nope", "0" * 16):
            assert code_of(lambda e=edit_id: world.undo(e)) == "unknown_edit", edit_id
        assert read(project_file(world)) == HIGH

    def test_a_row_that_is_not_the_newest_is_refused(self, world: World) -> None:
        first = edited(world, "mid")
        second = edited(world, "high")
        err = refused(lambda: world.undo(first["id"]))
        assert (err.code, err.params) == ("not_undoable", {"reason": "not_newest"})
        err = refused(lambda: force(world, first["id"]))
        assert err.code == "not_undoable"
        assert read(project_file(world)) == HIGH
        assert rows(world) == [first, second]

    def test_changed_since_save(self, world: World) -> None:
        row = edited(world)
        write(project_file(world), b'{"model": "max"}\n')
        assert undo_state(world, row) == "changed_since_save"
        err = refused(lambda: world.undo(row["id"]))
        assert err.code == "changed_since_save"
        assert err.backup is not None
        assert err.backup.raw == SETTINGS
        assert err.current is not None
        assert err.current.raw == b'{"model": "max"}\n'
        assert err.undo_version
        assert read(project_file(world)) == b'{"model": "max"}\n'
        assert rows(world) == [row]

    def test_an_unreadable_file_is_changed_since_save(self, world: World) -> None:
        row = edited(world)
        project_file(world).unlink()
        assert undo_state(world, row) == "changed_since_save"
        assert rows(world) == [row]

    def test_truncated_backup_is_damaged_and_nothing_is_written(
        self, world: World
    ) -> None:
        row = edited(world)
        bak = store_dir(world) / row["backup"]
        with bak.open("r+b") as fh:
            fh.truncate(5)
        assert undo_state(world, row) == "backup_damaged"
        edited_bytes = read(project_file(world))
        assert code_of(lambda: world.undo(row["id"])) == "backup_damaged"
        assert read(project_file(world)) == edited_bytes
        assert rows(world) == [row]
        assert baks(world) == [row["backup"]]

    def test_an_empty_or_swapped_backup_is_damaged(self, world: World) -> None:
        row = edited(world)
        bak = store_dir(world) / row["backup"]
        for data in (b"", b'{"model": "other"}\n'):
            write(bak, data)
            assert undo_state(world, row) == "backup_damaged"
            assert code_of(lambda: world.undo(row["id"])) == "backup_damaged"

    def test_a_backup_replaced_by_a_link_is_damaged(self, world: World) -> None:
        row = edited(world)
        bak = store_dir(world) / row["backup"]
        outside = write(world.home.parent / "outside.bak", SETTINGS)
        bak.unlink()
        bak.symlink_to(outside)
        assert undo_state(world, row) == "backup_damaged"
        assert code_of(lambda: world.undo(row["id"])) == "backup_damaged"

    def test_a_missing_backup_is_pruned(self, world: World) -> None:
        row = edited(world)
        (store_dir(world) / row["backup"]).unlink()
        assert undo_state(world, row) == "backup_pruned"
        err = refused(lambda: world.undo(row["id"]))
        assert (err.code, err.params) == ("not_undoable", {"reason": "backup_pruned"})

    def test_undo_state_is_none_for_a_healthy_row(self, world: World) -> None:
        assert undo_state(world, edited(world)) is None

    def test_after_an_undo_the_older_row_is_undone_and_the_newest_is_undoable(
        self, world: World
    ) -> None:
        row = edited(world)
        world.undo(row["id"])
        # the file is back at the pre-edit bytes, and the edit row is marked undone
        assert (
            world.store.row_status(world.target("project"), row).undo_state == "undone"
        )
        second = edited(world, "mid")
        third = edited(world, "end")
        assert undo_state(world, third) is None
        assert undo_state(world, second) == "not_newest"
        result = world.undo(third["id"])
        assert read(project_file(world)) == SETTINGS.replace(b'"low"', b'"mid"')
        assert result.row["kind"] == "undo"


# Raced


class TestRaced:
    def test_a_write_between_rename_and_reread_is_raced_for_a_save(
        self, world: World
    ) -> None:
        theirs = b'{"model": "theirs"}\n'
        at(world, "reread", lambda: write(project_file(world), theirs))
        err = refused(lambda: save(world, "high"))
        assert err.code == "raced"
        assert read(project_file(world)) == theirs
        world.store.seam = None
        found = rows(world)
        assert [r["id"] for r in found] == [err.row_id]
        assert found[0]["raced"] is True
        assert read(store_dir(world) / found[0]["backup"]) == SETTINGS
        # the row and its backup stay, and the row is not undoable
        assert baks(world) == [found[0]["backup"]]
        assert undo_state(world, found[0]) == "changed_since_save"

    def test_a_write_between_rename_and_reread_is_raced_for_an_undo(
        self, world: World
    ) -> None:
        row = edited(world)
        theirs = b'{"model": "theirs"}\n'
        at(world, "reread", lambda: write(project_file(world), theirs))
        err = refused(lambda: world.undo(row["id"]))
        assert err.code == "raced"
        assert read(project_file(world)) == theirs
        last = ledger_rows(world)[-1]
        assert last["kind"] == "undo"
        assert last["raced"] is True
        assert read(store_dir(world) / last["backup"]) == HIGH

    def test_a_backup_that_changes_before_the_undo_reread_is_raced(
        self, world: World
    ) -> None:
        row = edited(world)
        bak = store_dir(world) / row["backup"]
        at(world, "reread", lambda: write(bak, b"changed"))
        assert code_of(lambda: world.undo(row["id"])) == "raced"
        assert read(project_file(world)) == SETTINGS

    def test_a_backup_that_goes_missing_before_the_undo_reread_is_raced(
        self, world: World
    ) -> None:
        row = edited(world)
        bak = store_dir(world) / row["backup"]
        at(world, "reread", bak.unlink)
        assert code_of(lambda: world.undo(row["id"])) == "raced"

    def test_a_raced_save_skips_the_prune(self, world: World) -> None:
        for n in range(edit_store.RETENTION):
            edited(world, f"v{n}")
        at(
            world,
            "reread",
            lambda: write(project_file(world), b'{"model": "theirs"}\n'),
        )
        assert code_of(lambda: save(world, "late")) == "raced"
        assert len(ledger_rows(world)) == edit_store.RETENTION + 1
        assert len(baks(world)) == edit_store.RETENTION + 1


# Retention


class TestRetention:
    def test_the_twenty_first_write_prunes_the_oldest_and_nothing_else(
        self, world: World
    ) -> None:
        folder = store_dir(world)
        saved = [edited(world, f"v{n}") for n in range(edit_store.RETENTION)]
        # files the prune must leave alone
        keepers = {".lock", "ledger.json"}
        for name, data in (
            ("notes.txt", b"mine"),
            ("000001-short.bak", b"no match"),
            (".ledger-0123456789abcdef.tmp", b"x"),
            ("sub", None),
        ):
            if data is None:
                (folder / name).mkdir()
            else:
                write(folder / name, data)
            keepers.add(name)
        other_folder = world.backups / ("f" * 16)
        write(other_folder / ("000001-" + "a" * 16 + ".bak"), b"another target")
        assert len(rows(world)) == edit_store.RETENTION
        assert baks(world)[: edit_store.RETENTION] == [r["backup"] for r in saved]
        newest = edited(world, "v20")
        kept = [*saved[1:], newest]
        assert rows(world) == kept
        assert sorted(r["backup"] for r in kept) == [
            n for n in baks(world) if n != "000001-short.bak"
        ]
        assert saved[0]["backup"] not in os.listdir(folder)
        assert keepers == set(os.listdir(folder)) - {r["backup"] for r in kept}
        assert (other_folder / ("000001-" + "a" * 16 + ".bak")).exists()

    def test_the_newest_is_never_pruned_and_numbers_keep_counting(
        self, world: World
    ) -> None:
        last: dict[str, Any] = {}
        for n in range(edit_store.RETENTION + 5):
            last = edited(world, f"v{n}")
        found = rows(world)
        assert len(found) == edit_store.RETENTION
        assert found[-1] == last
        assert last["backup"].startswith(f"{edit_store.RETENTION + 5:06d}-")
        assert len(baks(world)) == edit_store.RETENTION

    def test_a_backup_no_row_names_goes_on_the_next_prune(self, world: World) -> None:
        edited(world, "v1")
        orphan = "000042-" + "b" * 16 + ".bak"
        write(store_dir(world) / orphan, b"orphan")
        row = edited(world, "v2")
        assert orphan not in baks(world)
        assert len(baks(world)) == 2
        assert row["backup"].startswith("000043-")

    def test_backups_from_before_a_moved_ledger_stay_through_every_save(
        self, world: World
    ) -> None:
        folder = store_dir(world)
        for n in range(5):
            edited(world, f"v{n}")
        old = baks(world)
        assert len(old) == 5
        hour_ago = time.time() - 3600
        for name in old:
            os.utime(folder / name, (hour_ago, hour_ago))
        (folder / "ledger.json").rename(folder / "ledger.json.aside")
        for n in range(3):
            edited(world, f"w{n}")
            assert [name for name in baks(world) if name in old] == old
        assert len(baks(world)) == 8
        assert len(rows(world)) == 3

    def test_a_prune_failure_never_fails_the_save(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for n in range(edit_store.RETENTION):
            edited(world, f"v{n}")
        real = os.listdir
        calls: list[object] = []

        def flaky(path: int) -> list[str]:
            calls.append(path)
            if len(calls) == 3:  # next number, temp files, then the prune
                raise OSError(5, "simulated")
            return real(path)

        body = world.save_body("late", field_name=FIELD)
        monkeypatch.setattr(os, "listdir", flaky)
        row = world.store.save(world.target("project"), body).row
        monkeypatch.undo()
        assert len(calls) == 3
        assert rows(world)[-1] == row
        assert read(project_file(world)) == SETTINGS.replace(b'"low"', b'"late"')

    def test_a_ledger_rewrite_failure_during_prune_keeps_every_backup(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for n in range(edit_store.RETENTION):
            edited(world, f"v{n}")
        real = EditStore._write_ledger
        calls: list[int] = []

        def flaky(self: EditStore, folder: Any, found: list[dict[str, Any]]) -> None:
            calls.append(len(found))
            if len(calls) == 2:
                raise OSError(5, "simulated")
            real(self, folder, found)

        body = world.save_body("late", field_name=FIELD)
        monkeypatch.setattr(EditStore, "_write_ledger", flaky)
        world.store.save(world.target("project"), body)
        monkeypatch.undo()
        assert len(baks(world)) == edit_store.RETENTION + 1
        assert len(ledger_rows(world)) == edit_store.RETENTION + 1


# ReadOnly. Left out: ``backup_path`` (the old display helper has no new counterpart).


class TestReadOnly:
    def test_reads_create_nothing_on_a_fresh_config_folder(self, world: World) -> None:
        row = {
            "id": "x" * 16,
            "backup": "000001-" + "a" * 16 + ".bak",
            "before_sha256": "0",
            "after_sha256": "1",
        }
        before = tree(world.config)
        assert rows(world) == []
        assert undo_state(world, row) == "not_newest"
        assert code_of(lambda: world.undo("x" * 16)) == "unknown_edit"
        assert (
            code_of(lambda: world.store.drift(world.targets(), PROJECT_KEY, "x" * 16))
            == "unknown_edit"
        )
        assert tree(world.config) == before
        assert not world.backups.exists()

    def test_reads_create_nothing_when_the_target_is_missing(
        self, world: World
    ) -> None:
        project_file(world).unlink()
        before = tree(world.config)
        assert rows(world) == []
        assert tree(world.config) == before

    def test_reads_do_not_write_a_trailing_row_away(self, world: World) -> None:
        crash_at(world, "after_ledger")
        with pytest.raises(Crash):
            save(world, "high")
        restart(world)
        ledger = store_dir(world) / "ledger.json"
        before = read(ledger)
        assert rows(world) == []
        assert read(ledger) == before
        assert len(baks(world)) == 1

    def test_reads_with_a_file_that_cannot_be_read_keep_every_row(
        self, world: World
    ) -> None:
        row = edited(world)
        project_file(world).unlink()
        assert rows(world) == [row]
        # a folder where the file was is a file the walk refuses, and the rows stay
        project_file(world).mkdir()
        assert rows(world) == [row]

    def test_a_wide_folder_is_not_narrowed_by_a_read(self, world: World) -> None:
        edited(world)
        folder = store_dir(world)
        folder.chmod(0o755)
        rows(world)
        assert mode_of(folder) == 0o755


# Create. A missing file is the normal case for the new ``save``, so no ``allow_absent``
# flag exists. Left out of the old CreateTests: the default save on an absent file being
# refused, a plan that deletes the file, and a plan of None for an absent file (the new
# API has no plan function).


def bare(w: World) -> None:
    """No .claude folder at all."""
    shutil.rmtree(w.project / ".claude")


def no_file(w: World) -> None:
    """A .claude folder that has no settings.json."""
    project_file(w).unlink()


def create(w: World, scope: EditScope = "project") -> dict[str, Any]:
    return save(w, "high", scope).row


def made(w: World) -> dict[str, Any]:
    """Create the project file in a project with no .claude."""
    bare(w)
    return create(w)


class TestCreate:
    def check_created(
        self, w: World, row: dict[str, Any], scope: EditScope = "project"
    ) -> None:
        path = w.path(scope)
        assert read(path) == NEW
        assert mode_of(path) == 0o600
        assert row["before_sha256"] == "absent"
        assert row["after_sha256"] == sha(NEW)
        assert row["op"] == "create"
        assert row["kind"] == "edit"
        assert row["backup"].endswith(".absent")
        assert read(store_dir(w, scope) / row["backup"]) == b""
        assert "old_value" not in row
        assert row["new_value"] == "high"
        assert rows(w, scope) == [row]
        assert baks(w, scope) == []
        status = w.store.row_status(w.target(scope), row)
        assert status.undo_state == "deletes_file"

    def test_a_file_in_an_existing_claude_folder(self, world: World) -> None:
        no_file(world)
        row = create(world)
        self.check_created(world, row)
        assert "made_dir" not in row
        assert sorted(os.listdir(world.project / ".claude")) == [
            "settings.json",
            "settings.local.json",
        ]
        assert leftovers(world) == []

    def test_a_file_with_no_claude_folder_makes_it_private(self, world: World) -> None:
        bare(world)
        row = create(world)
        self.check_created(world, row)
        assert row["made_dir"] is True
        assert mode_of(world.project / ".claude") == 0o700
        assert os.listdir(world.project / ".claude") == ["settings.json"]

    def test_the_user_layer_creates_in_the_config_folder(self, world: World) -> None:
        world.path("user").unlink()
        row = create(world, "user")
        self.check_created(world, row, "user")
        assert "made_dir" not in row
        assert world.path("user") == world.config / "settings.json"

    def test_a_missing_base_folder_is_refused_and_nothing_is_made(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shutil.rmtree(world.project)

        def no_mkdir(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("mkdir")

        monkeypatch.setattr(edit_store.os, "mkdir", no_mkdir)
        assert (
            code_of(lambda: world.store.inspect(world.target("project")))
            == "folder_not_found"
        )
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "folder_not_found"
        )
        assert not world.project.exists()
        assert not world.backups.exists()

    def test_a_dangling_link_at_claude_is_link_dangling(self, world: World) -> None:
        bare(world)
        (world.project / ".claude").symlink_to(world.home.parent / "nowhere")
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "link_dangling"
        )
        assert (world.project / ".claude").is_symlink()
        assert not world.backups.exists()

    def test_a_dangling_link_at_the_file_is_link_dangling(self, world: World) -> None:
        no_file(world)
        project_file(world).symlink_to(world.home.parent / "nowhere.json")
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "link_dangling"
        )
        assert project_file(world).is_symlink()
        assert not world.backups.exists()

    def test_claude_as_a_regular_file_is_not_regular(self, world: World) -> None:
        bare(world)
        write(world.project / ".claude", b"x")
        body = world.save_body("high", field_name=FIELD, version="x")
        assert (
            code_of(lambda: world.store.save(world.target("project"), body))
            == "not_regular"
        )
        assert read(world.project / ".claude") == b"x"

    def test_a_save_that_finds_the_file_present_gets_its_bytes(
        self, world: World, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[bytes | None] = []
        real = edit_store.plan_set

        def spy(raw: bytes | None, *args: Any, **kwargs: Any) -> edit_store.Plan:
            seen.append(raw)
            return real(raw, *args, **kwargs)

        monkeypatch.setattr(edit_store, "plan_set", spy)
        edited(world)
        assert seen == [SETTINGS]
        no_file(world)
        bare(world)
        create(world)
        assert seen == [SETTINGS, None]


# CreateCrash


class TestCreateCrash:
    def crash_create(self, w: World, seam_name: str) -> None:
        crash_at(w, seam_name)
        with pytest.raises(Crash):
            create(w)
        restart(w)

    def test_crash_after_the_backup_leaves_an_orphan_marker_the_next_save_removes(
        self, world: World
    ) -> None:
        bare(world)
        self.crash_create(world, "after_backup")
        assert not (world.project / ".claude").exists()
        assert len(markers(world)) == 1
        assert rows(world) == []
        orphan = markers(world)[0]
        row = create(world)
        assert markers(world) == [row["backup"]]
        assert orphan != row["backup"]
        assert rows(world) == [row]

    def test_crash_after_the_ledger_leaves_a_row_that_is_not_shown(
        self, world: World
    ) -> None:
        bare(world)
        self.crash_create(world, "after_ledger")
        assert not (world.project / ".claude").exists()
        assert len(ledger_rows(world)) == 1
        assert rows(world) == []
        row = create(world)
        assert markers(world) == [row["backup"]]
        assert rows(world) == [row]
        assert [r["id"] for r in ledger_rows(world)] == [row["id"]]

    def test_crash_after_the_mkdir_leaves_an_empty_folder_and_the_next_create_finds_it(
        self, world: World
    ) -> None:
        bare(world)
        self.crash_create(world, "after_mkdir")
        assert os.listdir(world.project / ".claude") == []
        assert len(ledger_rows(world)) == 1
        assert rows(world) == []
        row = create(world)
        assert read(project_file(world)) == NEW
        assert "made_dir" not in row
        assert rows(world) == [row]
        assert markers(world) == [row["backup"]]

    def test_crash_after_the_temp_leaves_a_temp_the_next_save_sweeps(
        self, world: World
    ) -> None:
        bare(world)
        self.crash_create(world, "after_temp")
        assert len(leftovers(world)) == 1
        assert not project_file(world).exists()
        assert rows(world) == []
        age_temps(world)
        row = create(world)
        assert leftovers(world) == []
        assert os.listdir(world.project / ".claude") == ["settings.json"]
        assert rows(world) == [row]

    def test_crash_after_the_rename_leaves_a_row_that_is_newest_and_undoable(
        self, world: World
    ) -> None:
        bare(world)
        self.crash_create(world, "after_rename")
        assert read(project_file(world)) == NEW
        found = rows(world)
        assert len(found) == 1
        assert found[0]["made_dir"] is True
        assert undo_state(world, found[0]) is None
        result = world.undo(found[0]["id"])
        assert result.removed_file is True
        assert result.removed_dir is True
        assert not (world.project / ".claude").exists()

    def test_the_file_is_whole_or_absent_at_every_create_crash_point(
        self, world: World
    ) -> None:
        for seam_name in (
            "before_backup",
            "after_backup",
            "after_ledger",
            "after_mkdir",
            "after_temp",
            "before_recheck",
            "before_rename",
            "after_rename",
            "dir_fsync",
            "reread",
        ):
            restart(world)
            clean_store(world)
            shutil.rmtree(world.project / ".claude", ignore_errors=True)
            self.crash_create(world, seam_name)
            if project_file(world).exists():
                assert read(project_file(world)) == NEW, seam_name


# PruneMarker


class TestPruneMarker:
    def orphan(
        self, w: World, name: str = "000007-" + HEX16 + ".absent", age: float = 0
    ) -> str:
        path = write(store_dir(w) / name, b"")
        if age:
            stamp = time.time() - age
            os.utime(path, (stamp, stamp))
        return name

    def test_an_orphan_marker_with_no_rows_at_all_goes(self, world: World) -> None:
        name = self.orphan(world)
        row = edited(world)
        assert name not in os.listdir(store_dir(world))
        assert row["backup"].startswith("000008-")

    def test_an_orphan_marker_older_than_the_floor_goes(self, world: World) -> None:
        edited(world, "v1")
        name = self.orphan(world, age=3600)
        edited(world, "v2")
        assert name not in os.listdir(store_dir(world))

    def test_a_marker_only_ledger_has_no_floor_so_a_real_orphan_stays_and_a_marker_goes(
        self, world: World
    ) -> None:
        no_file(world)
        name = self.orphan(world)
        real = "000042-" + HEX16 + ".bak"
        write(store_dir(world) / real, b"older ledger")
        row = create(world)
        listing = os.listdir(store_dir(world))
        assert name not in listing
        assert real in listing
        assert row["backup"] in listing

    def test_a_real_orphan_older_than_the_floor_stays(self, world: World) -> None:
        edited(world, "v1")
        edited(world, "v2")
        real = "000042-" + HEX16 + ".bak"
        path = write(store_dir(world) / real, b"old")
        stamp = time.time() - 3600
        os.utime(path, (stamp, stamp))
        edited(world, "v3")
        assert real in os.listdir(store_dir(world))

    def test_numbers_count_past_a_marker(self, world: World) -> None:
        self.orphan(world, "000042-" + HEX16 + ".absent")
        row = edited(world)
        assert row["backup"].startswith("000043-")

    def test_a_marker_a_row_names_is_kept_whatever_its_age(self, world: World) -> None:
        no_file(world)
        row = create(world)
        stamp = time.time() - 7200
        os.utime(store_dir(world) / row["backup"], (stamp, stamp))
        edited(world, "v2")
        assert markers(world) == [row["backup"]]

    def test_a_marker_never_sets_the_floor(self, world: World) -> None:
        no_file(world)
        first = create(world)
        stamp = time.time() - 7200
        os.utime(store_dir(world) / first["backup"], (stamp, stamp))
        rs = world.store.resolve(world.target("project"))
        folder = world.store._open_store(rs, create=False)
        assert folder is not None
        try:
            assert world.store._oldest_mtime(folder, [first]) is None
        finally:
            folder.close()


# UndoCreateCrash


class TestUndoCreateCrash:
    def crash_undo(self, w: World, seam_name: str, row: dict[str, Any]) -> None:
        crash_at(w, seam_name)
        with pytest.raises(Crash):
            w.undo(row["id"])
        restart(w)

    def test_crash_before_the_unlink_keeps_the_file_and_the_create_undoable(
        self, world: World
    ) -> None:
        row = made(world)
        self.crash_undo(world, "before_unlink", row)
        assert read(project_file(world)) == NEW
        assert rows(world) == [row]
        assert len(ledger_rows(world)) == 2
        assert undo_state(world, row) is None
        result = world.undo(row["id"])
        assert result.removed_file is True
        assert not project_file(world).exists()

    def test_crash_after_the_unlink_keeps_the_undo_row(self, world: World) -> None:
        row = made(world)
        self.crash_undo(world, "after_unlink", row)
        assert not project_file(world).exists()
        found = rows(world)
        assert len(found) == 2
        assert found[0] == row
        undone = found[1]
        assert undone["kind"] == "undo"
        assert undone["after_sha256"] == "absent"
        assert undone["before_sha256"] == sha(NEW)
        assert (world.project / ".claude").is_dir()

    def test_crash_before_the_rmdir_leaves_a_harmless_empty_folder(
        self, world: World
    ) -> None:
        row = made(world)
        self.crash_undo(world, "before_rmdir", row)
        assert not project_file(world).exists()
        assert os.listdir(world.project / ".claude") == []
        assert len(rows(world)) == 2
        again = create(world)
        assert read(project_file(world)) == NEW
        assert "made_dir" not in again


# UndoCreate. Left out: ``result.matches_backup`` and the path fields (no new
# counterpart). The row's backup name and the ledger folder say the same.


class TestUndoCreate:
    def test_the_whole_project_folder_is_back_as_it_was(self, world: World) -> None:
        bare(world)
        before = tree_hash(world.project)
        row = create(world)
        assert tree_hash(world.project) != before
        result = world.undo(row["id"])
        assert result.removed_file is True
        assert result.removed_dir is True
        assert tree_hash(world.project) == before

    def test_the_undo_row_backs_up_the_created_bytes(self, world: World) -> None:
        row = made(world)
        undone = world.undo(row["id"]).row
        assert undone["kind"] == "undo"
        assert undone["op"] == "create"
        assert undone["before_sha256"] == sha(NEW)
        assert undone["after_sha256"] == "absent"
        assert undone["backup"].endswith(".bak")
        assert read(store_dir(world) / undone["backup"]) == NEW
        assert undone["restored_from"] == row["id"]
        assert undone["restored_from_backup"] == row["backup"]
        assert undone["old_value"] == "high"
        assert "new_value" not in undone
        assert "made_dir" not in undone
        assert rows(world) == [row, undone]

    def test_a_stray_file_in_claude_keeps_the_folder(self, world: World) -> None:
        row = made(world)
        stray = write(world.project / ".claude" / ".DS_Store", b"junk")
        result = world.undo(row["id"])
        assert result.removed_file is True
        assert result.removed_dir is False
        assert os.listdir(world.project / ".claude") == [".DS_Store"]
        assert read(stray) == b"junk"
        assert not project_file(world).exists()

    def test_a_leftover_temp_does_not_block_the_folder_removal(
        self, world: World
    ) -> None:
        row = made(world)
        write(
            world.project / ".claude" / (".routing-dashboard-" + HEX16 + ".tmp"), b"x"
        )
        age_temps(world)
        result = world.undo(row["id"])
        assert result.removed_dir is True
        assert not (world.project / ".claude").exists()

    def test_a_folder_that_was_already_there_stays(self, world: World) -> None:
        no_file(world)
        row = create(world)
        result = world.undo(row["id"])
        assert result.removed_file is True
        assert result.removed_dir is False
        assert os.listdir(world.project / ".claude") == ["settings.local.json"]

    def test_the_user_layer_has_no_folder_to_remove(self, world: World) -> None:
        user = world.path("user")
        user.unlink()
        row = create(world, "user")
        result = world.store.undo(
            world.targets(), PROJECT_KEY, world.undo_body(row["id"])
        )
        assert result.removed_file is True
        assert result.removed_dir is False
        assert world.config.is_dir()
        assert not user.exists()

    def test_a_folder_swapped_for_another_before_the_rmdir_stays(
        self, world: World
    ) -> None:
        row = made(world)
        claude = world.project / ".claude"
        held = world.home.parent / "held"

        def swap() -> None:
            claude.rename(held)
            claude.mkdir()

        at(world, "before_rmdir", swap)
        result = world.undo(row["id"])
        assert result.removed_file is True
        assert result.removed_dir is False
        assert claude.is_dir()
        assert held.is_dir()

    def test_restoring_the_undo_makes_the_file_again(self, world: World) -> None:
        row = made(world)
        undone = world.undo(row["id"]).row
        again = put_back(world, undone["id"])
        assert read(project_file(world)) == NEW
        assert again.removed_file is False
        assert again.row["before_sha256"] == "absent"
        assert again.row["backup"].endswith(".absent")
        assert again.row["made_dir"] is True
        assert mode_of(project_file(world)) == 0o600

    def test_a_default_undo_on_a_hand_deleted_edit_is_changed_since_save(
        self, world: World
    ) -> None:
        row = edited(world)
        project_file(world).unlink()
        assert undo_state(world, row) == "changed_since_save"
        assert code_of(lambda: world.undo(row["id"])) == "changed_since_save"
        assert not project_file(world).exists()
        assert rows(world) == [row]


# CreateDescriptor. Left out: the save with no ``allow_absent``, which no longer exists.


class TestCreateDescriptor:
    def test_no_descriptor_leaks_over_a_create_and_an_undo(self, world: World) -> None:
        bare(world)
        row = create(world)
        world.undo(row["id"])
        before = fd_count()
        for _ in range(5):
            row = create(world)
            world.undo(row["id"])
            rows(world)
        assert fd_count() == before

    def test_no_descriptor_leaks_over_failed_creates(self, world: World) -> None:
        bare(world)
        before = fd_count()

        def fail() -> None:
            raise OSError(5, "simulated")

        for seam_name in ("after_mkdir", "after_temp", "before_recheck"):
            at(world, seam_name, fail)
            assert code_of(lambda: create(world)) == "write_failed", seam_name
        world.store.seam = None
        assert fd_count() == before

    def test_no_descriptor_leaks_over_a_changed_create(self, world: World) -> None:
        bare(world)
        before = fd_count()
        at(world, "before_recheck", lambda: write(project_file(world), b"{}\n"))
        assert code_of(lambda: create(world)) == "changed"
        world.store.seam = None
        assert fd_count() == before


# Force (undo anyway, and restore). Left out of the old ForceTests: the three gate
# tests. The old ``gate`` callback had no caller in the new design. The token from the
# refusal binds the same two things, the bytes now and the bytes the undo would write,
# and the token tests in ``test_edit_store_undo.py`` cover them. The old ``check``
# hook test is ``test_a_row_that_is_not_the_newest_is_refused`` above.


def reset(w: World) -> None:
    """A clean world: SETTINGS in the project file, an empty .claude, no store folder."""
    clean_store(w)
    shutil.rmtree(w.project / ".claude")
    (w.project / ".claude").mkdir()
    write(project_file(w), SETTINGS)
    restart(w)


def hand(w: World, data: bytes) -> None:
    write(project_file(w), data)


class TestForce:
    def test_force_writes_over_a_hand_edit_and_backs_the_hand_edit_up(
        self, world: World
    ) -> None:
        row = edited(world)
        hand(world, HAND)
        hand_copy = bytes(HAND)
        result = force(world, row["id"])
        assert read(project_file(world)) == SETTINGS
        undone = result.row
        assert undone["kind"] == "undo"
        assert undone["restored_from"] == row["id"]
        assert undone["restored_from_backup"] == row["backup"]
        assert undone["before_sha256"] == sha(hand_copy)
        assert undone["after_sha256"] == sha(SETTINGS)
        assert read(store_dir(world) / undone["backup"]) == hand_copy
        assert rows(world) == [row, undone]

    def test_without_force_the_same_hand_edit_still_refuses(self, world: World) -> None:
        row = edited(world)
        hand(world, HAND)
        assert code_of(lambda: world.undo(row["id"])) == "changed_since_save"
        assert read(project_file(world)) == HAND
        assert rows(world) == [row]

    def test_force_without_the_token_is_refused(self, world: World) -> None:
        row = edited(world)
        hand(world, HAND)
        assert code_of(lambda: world.undo(row["id"], anyway=True)) == "bad_version"
        assert read(project_file(world)) == HAND

    def test_force_keeps_the_values_read_from_the_bytes(self, world: World) -> None:
        row = edited(world)
        hand(world, HAND)
        undone = force(world, row["id"]).row
        assert undone["old_value"] == "hand"
        assert undone["new_value"] == "low"

    def test_force_does_not_pass_a_pruned_backup(self, world: World) -> None:
        row = edited(world)
        hand(world, HAND)
        (store_dir(world) / row["backup"]).unlink()
        err = refused(lambda: force(world, row["id"]))
        assert (err.code, err.params) == ("not_undoable", {"reason": "backup_pruned"})
        assert read(project_file(world)) == HAND
        assert rows(world) == [row]

    def test_force_does_not_pass_a_damaged_backup(self, world: World) -> None:
        row = edited(world)
        hand(world, HAND)
        write(store_dir(world) / row["backup"], b"not what was saved")
        assert code_of(lambda: force(world, row["id"])) == "backup_damaged"
        assert read(project_file(world)) == HAND
        assert rows(world) == [row]

    def test_force_on_a_create_row_after_a_hand_edit_deletes_the_file(
        self, world: World
    ) -> None:
        row = made(world)
        hand(world, HAND)
        result = force(world, row["id"])
        assert not project_file(world).exists()
        assert result.removed_file is True
        assert result.removed_dir is True
        assert not (world.project / ".claude").exists()
        assert BAK_RE.match(result.row["backup"])
        assert read(store_dir(world) / result.row["backup"]) == HAND
        assert result.row["kind"] == "undo"

    def test_force_on_a_create_row_leaves_the_project_as_before_the_create(
        self, world: World
    ) -> None:
        bare(world)
        before = tree_hash(world.project)
        row = create(world)
        hand(world, HAND)
        force(world, row["id"])
        assert tree_hash(world.project) == before

    def test_force_on_a_create_row_keeps_a_claude_folder_that_holds_a_stray_file(
        self, world: World
    ) -> None:
        row = made(world)
        hand(world, HAND)
        stray = write(world.project / ".claude" / "notes.txt", b"mine")
        result = force(world, row["id"])
        assert not project_file(world).exists()
        assert result.removed_file is True
        assert result.removed_dir is False
        assert read(stray) == b"mine"

    def test_force_on_a_replace_row_after_the_file_went_writes_it_back_and_marks_the_gap(
        self, world: World
    ) -> None:
        row = edited(world)
        project_file(world).unlink()
        result = force(world, row["id"])
        assert read(project_file(world)) == SETTINGS
        assert result.row["before_sha256"] == "absent"
        assert result.row["backup"].endswith(".absent")
        assert read(store_dir(world) / result.row["backup"]) == b""
        assert "made_dir" not in result.row
        assert mode_of(project_file(world)) == 0o600  # a mode is not in a backup
        assert result.removed_file is False

    def test_force_on_a_replace_row_after_the_folder_went_makes_it_again(
        self, world: World
    ) -> None:
        row = edited(world)
        shutil.rmtree(world.project / ".claude")
        result = force(world, row["id"])
        assert read(project_file(world)) == SETTINGS
        assert result.row["before_sha256"] == "absent"
        assert result.row["made_dir"] is True
        assert mode_of(project_file(world)) == 0o600
        assert mode_of(world.project / ".claude") == 0o700


# ForgedRow. A forged backup name is a ``forged_row`` now, because the registry checks
# the row's shape before it opens anything. A name that is fine but whose file is a
# link, a folder or the wrong bytes is still ``backup_damaged``.


class TestForgedRow:
    @pytest.fixture
    def forged(self, world: World) -> dict[str, Any]:
        row = edited(world)
        world.timers.clear()
        # decoys outside the store folder that hold exactly the bytes the row's hash wants
        self.decoy = write(world.config / "routing-dashboard" / "x.bak", SETTINGS)
        self.decoy_far = write(world.home.parent / "far.bak", SETTINGS)
        self.edited_bytes = read(project_file(world))
        self.watch = {self.decoy: SETTINGS, self.decoy_far: SETTINGS}
        return row

    def forge(self, w: World, name: Any) -> dict[str, Any]:
        rewrite_ledger(w, lambda found: found[0].update(backup=name))
        return rows(w)[0]

    def run_both(self, w: World, row: dict[str, Any], codes: set[str]) -> None:
        for hand_edit in (False, True):
            write(project_file(w), HAND if hand_edit else self.edited_bytes)
            before_project = tree_hash(w.project)
            for call in (
                lambda: w.undo(row["id"]),
                lambda: w.undo(row["id"], anyway=True, version="not-a-token"),
                lambda: put_back(w, row["id"]),
            ):
                err = refused(call)
                assert err.code in codes, err.code
            assert tree_hash(w.project) == before_project
        for path, data in self.watch.items():
            assert read(path) == data
        assert backup_reason(w, row)[1] is None

    def test_a_relative_name_with_dots(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        row = self.forge(world, "../../x.bak")
        assert backup_reason(world, row) == ("backup_pruned", None)
        self.run_both(world, row, {"forged_row"})

    def test_an_absolute_name(self, world: World, forged: dict[str, Any]) -> None:
        row = self.forge(world, str(self.decoy_far))
        assert backup_reason(world, row) == ("backup_pruned", None)
        self.run_both(world, row, {"forged_row"})

    def test_a_valid_name_followed_by_a_path(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        row = self.forge(world, "000001-aaaaaaaaaaaaaaaa.bak/../x")
        assert backup_reason(world, row) == ("backup_pruned", None)
        self.run_both(world, row, {"forged_row"})

    def test_a_symlink_at_a_valid_name_that_points_outside(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        bak = store_dir(world) / forged["backup"]
        bak.unlink()
        bak.symlink_to(self.decoy_far)
        row = rows(world)[0]
        assert backup_reason(world, row) == ("backup_damaged", None)
        self.run_both(
            world, row, {"backup_damaged", "changed_since_save", "bad_version"}
        )
        assert bak.is_symlink()

    def test_a_folder_at_a_valid_name(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        bak = store_dir(world) / forged["backup"]
        bak.unlink()
        bak.mkdir()
        row = rows(world)[0]
        assert backup_reason(world, row) == ("backup_damaged", None)
        self.run_both(
            world, row, {"backup_damaged", "changed_since_save", "bad_version"}
        )

    def test_a_hard_link_to_a_file_with_other_bytes(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        bak = store_dir(world) / forged["backup"]
        other = write(world.home.parent / "other.bak", b'{"model": "other"}\n')
        bak.unlink()
        os.link(other, bak)
        row = rows(world)[0]
        assert backup_reason(world, row) == ("backup_damaged", None)
        self.watch[other] = b'{"model": "other"}\n'
        self.run_both(
            world, row, {"backup_damaged", "changed_since_save", "bad_version"}
        )

    def test_a_marker_name_that_points_outside(
        self, world: World, forged: dict[str, Any]
    ) -> None:
        row = self.forge(world, "../../x.absent")
        assert backup_reason(world, row) == ("backup_pruned", None)
        self.run_both(world, row, {"forged_row"})


# ForceCrash. A crash at each seam of a forced undo or a restore. The file is whole and
# the rows tell the truth. The old seam ``after_rmdir`` has no new counterpart (the new
# writer has no step after the folder is removed).

SEAMS_ALL = (
    "after_read", "before_backup", "after_backup", "after_ledger", "after_mkdir",
    "after_temp", "before_recheck", "before_rename", "before_unlink", "after_rename",
    "after_unlink", "dir_fsync", "reread", "before_rmdir",
)  # fmt: skip
# the seams where the file has not changed yet
BEFORE_LANDING = (
    "after_read", "before_backup", "after_backup", "after_ledger", "after_mkdir",
    "after_temp", "before_recheck", "before_rename", "before_unlink",
)  # fmt: skip


class TestForceCrash:
    def later_save(self, w: World) -> None:
        save(w, "later")

    def matrix(
        self,
        w: World,
        setup: Callable[[], tuple[dict[str, Any], bytes | None, bytes | None]],
        run: Callable[[str], UndoResult],
        seams: list[str],
        new_kind: str,
    ) -> None:
        """``setup()`` gives (source row, old bytes or None, new bytes or None)."""
        for seam_name in seams:
            reset(w)
            source, old, new = setup()
            base_rows = rows(w)
            crash_at(w, seam_name)
            with pytest.raises(Crash):
                run(source["id"])
            restart(w)
            raw = raw_of(w)
            landed = seam_name not in BEFORE_LANDING
            assert raw == (new if landed else old), seam_name
            found = rows(w)
            if landed:
                assert base_rows == found[:-1], seam_name
                last = found[-1]
                assert last["kind"] == new_kind, seam_name
                assert last["restored_from"] == source["id"], seam_name
                # the old bytes are still reachable, in the new row's backup
                assert backup_reason(w, last)[0] is None, seam_name
                if old is None:
                    assert last["backup"].endswith(".absent"), seam_name
                else:
                    assert read(store_dir(w) / last["backup"]) == old, seam_name
                assert last["after_sha256"] == (
                    sha(new) if new is not None else "absent"
                )
            else:
                assert base_rows == found, seam_name
            # no half state reads as undoable: an older row is undoable only while it is
            # the newest and the file is its after bytes
            current = w.store.inspect(w.target("project")).sha256
            for older in base_rows:
                state = w.store.row_status(w.target("project"), older).undo_state
                want = (
                    bool(found)
                    and found[-1]["id"] == older["id"]
                    and current == older["after_sha256"]
                )
                assert (state in ("can_undo", "deletes_file")) == want, (
                    seam_name,
                    state,
                )
            # a retry, or a later save, works and sweeps the temp file
            age_temps(w)
            if not landed:
                retry = run(source["id"])
                assert raw_of(w) == new, seam_name
                assert retry.row["kind"] == new_kind, seam_name
            if (w.project / ".claude").is_dir() or raw_of(w) is None:
                self.later_save(w)
                assert leftovers(w) == [], seam_name
                assert project_file(w).exists(), seam_name

    def test_a_forced_undo_over_a_hand_edit_at_every_seam(self, world: World) -> None:
        def setup() -> tuple[dict[str, Any], bytes | None, bytes | None]:
            row = edited(world)
            hand(world, HAND)
            return row, HAND, SETTINGS

        seams = [
            n for n in SEAMS_ALL
            if n not in ("after_mkdir", "before_unlink", "after_unlink", "before_rmdir")
        ]  # fmt: skip
        self.matrix(world, setup, lambda row_id: force(world, row_id), seams, "undo")

    def test_a_forced_undo_of_a_create_at_every_seam(self, world: World) -> None:
        def setup() -> tuple[dict[str, Any], bytes | None, bytes | None]:
            bare(world)
            row = create(world)
            hand(world, HAND)
            return row, HAND, None

        seams = [
            n for n in SEAMS_ALL
            if n not in ("after_mkdir", "after_temp", "before_rename", "after_rename")
        ]  # fmt: skip
        self.matrix(world, setup, lambda row_id: force(world, row_id), seams, "undo")

    def test_a_restore_of_a_real_backup_at_every_seam(self, world: World) -> None:
        def setup() -> tuple[dict[str, Any], bytes | None, bytes | None]:
            row = edited(world)
            return row, read(project_file(world)), SETTINGS

        seams = [
            n for n in SEAMS_ALL
            if n not in ("after_mkdir", "before_unlink", "after_unlink", "before_rmdir")
        ]  # fmt: skip
        self.matrix(
            world, setup, lambda row_id: put_back(world, row_id), seams, "restore"
        )

    def test_a_restore_of_a_marker_at_every_seam(self, world: World) -> None:
        def setup() -> tuple[dict[str, Any], bytes | None, bytes | None]:
            bare(world)
            row = create(world)
            return row, NEW, None

        seams = [
            n for n in SEAMS_ALL
            if n not in ("after_mkdir", "after_temp", "before_rename", "after_rename")
        ]  # fmt: skip
        self.matrix(
            world, setup, lambda row_id: put_back(world, row_id), seams, "restore"
        )

    def test_a_restore_onto_an_absent_file_with_the_folder_gone_at_every_seam(
        self, world: World
    ) -> None:
        def setup() -> tuple[dict[str, Any], bytes | None, bytes | None]:
            row = edited(world)
            shutil.rmtree(world.project / ".claude")
            return row, None, SETTINGS

        seams = [
            n for n in SEAMS_ALL
            if n not in ("before_unlink", "after_unlink", "before_rmdir")
        ]  # fmt: skip
        self.matrix(
            world, setup, lambda row_id: put_back(world, row_id), seams, "restore"
        )


# ForceDescriptor


class TestForceDescriptor:
    def test_no_descriptor_leaks_over_forced_and_restore_writes(
        self, world: World
    ) -> None:
        bare(world)
        row = create(world)
        force(world, row["id"])
        before = fd_count()
        for _ in range(3):
            row = create(world)
            hand(world, HAND)
            force(world, row["id"])
            row = create(world)
            put_back(world, row["id"])
            backup_reason(world, row)
            world.store.inspect(world.target("project"))
        assert fd_count() == before
