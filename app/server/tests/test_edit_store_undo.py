"""Undo, "Undo anyway", restore, forged rows, rechecks and drift (m6-build.md 3.6, 3.7).

An undo is a new row whose bytes are a checked backup. "Anyway" skips only the check
against the saved row's hash, never the token. Undo, restore and drift rebuild their
target from the registry and never trust a row's path. Rechecks and drift rebuild the
bytes a save wrote and check them against ``after_sha256``.
"""

# pyright: reportPrivateUsage=false
# These tests reach into the writer's helpers to set up a state or read one.

import dataclasses
import json
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_helpers import PROJECT_KEY, World, make_world, write_json

import edit_store
import write_guard
from edit_store import FileBytes, Refused

OLD = (
    '{\n  "model": "opus",\n  "effortLevel": "low",\n  "env": {\n    "A": "1"\n  }\n}\n'
)
HIGH = OLD.replace('"low"', '"high"')


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    return make_world(edit_config, edit_project, secret=b"s" * 32)


def settings(world: World, text: str = OLD) -> Path:
    return write_json(world.path(), text)


def tamper(
    world: World, change: Callable[[list[dict[str, Any]]], None], scope: str = "project"
) -> None:
    """Edit the stored ledger rows in place."""
    ledger = world.ledger_dir(scope) / "ledger.json"  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    doc = json.loads(ledger.read_bytes())
    change(doc["rows"])
    ledger.write_text(json.dumps(doc, indent=1))


def refused(call: Callable[[], object]) -> Refused:
    with pytest.raises(Refused) as caught:
        call()
    return caught.value


def other_program_writes(path: Path, text: str) -> None:
    """Replace a file the way another program does, atomically."""
    temp = path.with_name("other.tmp")
    write_json(temp, text)
    temp.replace(path)


# Undo


def test_an_undo_puts_the_old_bytes_back_as_a_new_row(world: World) -> None:
    path = settings(world)
    path.chmod(0o640)
    saved = world.save("high")
    done = world.undo(saved.row_id)
    assert path.read_text() == OLD
    assert stat.S_IMODE(path.stat().st_mode) == 0o640
    row = done.row
    assert done.row_id == row["id"]
    assert (done.removed_file, done.removed_dir) == (False, False)
    assert row["kind"] == "undo"
    assert row["restored_from"] == saved.row_id
    assert row["restored_from_backup"] == saved.row["backup"]
    assert row["op"] == "replace"
    assert row["key_path"] == ["effortLevel"]
    assert row["old_value"] == "high"
    assert row["new_value"] == "low"
    assert row["project"] == PROJECT_KEY
    assert row["before_sha256"] == saved.row["after_sha256"]
    assert row["after_sha256"] == saved.row["before_sha256"]
    backup = world.ledger_dir() / row["backup"]
    assert backup.read_text() == HIGH
    assert [r["kind"] for r in world.ledger()] == ["edit", "undo"]


def test_an_undo_row_and_an_older_row_are_not_undoable(world: World) -> None:
    settings(world)
    first = world.save("high")
    second = world.save("medium")
    err = refused(lambda: world.undo(first.row_id))
    assert (err.code, err.params) == ("not_undoable", {"reason": "not_newest"})
    undone = world.undo(second.row_id)
    err = refused(lambda: world.undo(undone.row_id))
    assert (err.code, err.params) == ("not_undoable", {"reason": "undo_row"})
    assert refused(lambda: world.undo("0" * 16)).code == "unknown_edit"
    assert world.path().read_text() == HIGH


def test_the_undo_of_a_create_deletes_the_file_and_the_folder_the_save_made(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)
    saved = world.save("high")
    done = world.undo(saved.row_id)
    assert not (bare / ".claude").exists()
    assert (done.removed_file, done.removed_dir) == (True, True)
    assert done.row["after_sha256"] == "absent"
    assert world.ledger()[-1]["backup"].endswith(".bak")


def test_the_undo_of_a_create_keeps_a_folder_that_was_already_there(
    world: World,
) -> None:
    saved = world.save("high")
    done = world.undo(saved.row_id)
    assert not world.path().exists()
    assert (world.project / ".claude").is_dir()
    assert (done.removed_file, done.removed_dir) == (True, False)


def test_an_undo_of_a_create_with_an_unrelated_file_beside_it_leaves_the_folder(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)
    saved = world.save("high")
    (bare / ".claude" / "keep.txt").write_text("mine")
    done = world.undo(saved.row_id)
    assert (done.removed_file, done.removed_dir) == (True, False)
    assert (bare / ".claude" / "keep.txt").read_text() == "mine"


# A file that changed since the save


def changed_since_save(world: World) -> tuple[Refused, str, Path]:
    path = settings(world)
    saved = world.save("high")
    path.write_text(HIGH.replace("opus", "sonnet"))
    err = refused(lambda: world.undo(saved.row_id))
    return err, saved.row_id, path


def test_a_changed_file_is_changed_since_save_with_what_the_undo_would_write(
    world: World,
) -> None:
    err, row_id, path = changed_since_save(world)
    assert err.code == "changed_since_save"
    assert err.params == {"row_id": row_id}
    assert err.current == FileBytes(HIGH.replace("opus", "sonnet").encode())
    assert err.backup == FileBytes(OLD.encode())
    assert err.undo_version
    assert path.read_text() == HIGH.replace("opus", "sonnet")
    assert len(world.ledger()) == 1


def test_undo_anyway_with_the_token_writes_the_backup_over_the_changed_file(
    world: World,
) -> None:
    err, row_id, path = changed_since_save(world)
    done = world.undo(row_id, anyway=True, version=err.undo_version)
    assert path.read_text() == OLD
    assert done.row["kind"] == "undo"
    held = world.ledger_dir() / done.row["backup"]
    assert held.read_text() == HIGH.replace("opus", "sonnet")


def test_undo_anyway_never_skips_the_token(world: World) -> None:
    _err, row_id, path = changed_since_save(world)
    assert refused(lambda: world.undo(row_id, anyway=True)).code == "bad_version"
    assert (
        refused(lambda: world.undo(row_id, anyway=True, version="x")).code
        == "bad_version"
    )
    assert path.read_text() == HIGH.replace("opus", "sonnet")


def test_a_token_for_another_row_is_preview_mismatch(world: World) -> None:
    err, row_id, path = changed_since_save(world)
    other = world.undo_body("1" * 16, anyway=True)
    wrong = world.store._sign(
        {
            **world.store._open_token(err.undo_version or ""),
            "body_sha256": edit_store.choice_key(other),
        }
    )
    assert (
        refused(lambda: world.undo(row_id, anyway=True, version=wrong)).code
        == "preview_mismatch"
    )
    assert path.read_text() == HIGH.replace("opus", "sonnet")


def test_a_file_that_changes_again_after_the_token_is_changed(world: World) -> None:
    err, row_id, path = changed_since_save(world)
    path.write_text("{}\n")
    assert (
        refused(lambda: world.undo(row_id, anyway=True, version=err.undo_version)).code
        == "changed"
    )
    assert path.read_text() == "{}\n"


def test_undo_anyway_on_an_unchanged_file_still_needs_the_token(world: World) -> None:
    path = settings(world)
    saved = world.save("high")
    assert refused(lambda: world.undo(saved.row_id, anyway=True)).code == "bad_version"
    assert path.read_text() == HIGH


def test_a_row_whose_file_already_holds_its_backup_never_applied(world: World) -> None:
    _err, row_id, path = changed_since_save(world)
    path.write_text(OLD)
    assert refused(lambda: world.undo(row_id)).code == "unknown_edit"
    assert world.store.read_rows(world.target()) == []


def test_a_damaged_backup_refuses_even_with_anyway(world: World) -> None:
    err, row_id, path = changed_since_save(world)
    backup = world.ledger_dir() / world.ledger()[0]["backup"]
    backup.write_text("tampered")
    assert refused(lambda: world.undo(row_id)).code == "backup_damaged"
    assert (
        refused(lambda: world.undo(row_id, anyway=True, version=err.undo_version)).code
        == "backup_damaged"
    )
    assert path.read_text() == HIGH.replace("opus", "sonnet")


def test_a_pruned_backup_is_not_undoable(world: World) -> None:
    _err, row_id, _path = changed_since_save(world)
    (world.ledger_dir() / world.ledger()[0]["backup"]).unlink()
    err = refused(lambda: world.undo(row_id))
    assert (err.code, err.params) == ("not_undoable", {"reason": "backup_pruned"})


def test_a_backup_that_is_not_json_is_unparsed_under_anyway(world: World) -> None:
    err, row_id, path = changed_since_save(world)
    row = world.ledger()[0]
    backup = world.ledger_dir() / row["backup"]
    backup.write_text("not json")
    new_hash = edit_store._sha(b"not json")
    tamper(world, lambda rows: rows[0].update(before_sha256=new_hash))
    fresh = refused(lambda: world.undo(row_id))
    assert fresh.code == "changed_since_save"
    bad = refused(lambda: world.undo(row_id, anyway=True, version=fresh.undo_version))
    assert (bad.code, bad.params) == ("unparsed", {"which": "backup"})
    assert err.undo_version
    assert path.read_text() == HIGH.replace("opus", "sonnet")


def test_a_marker_that_pairs_with_a_real_backup_is_damaged(world: World) -> None:
    saved = world.save("high")  # a create: before is absent
    tamper(world, lambda rows: rows[0].update(backup="000001-" + "a" * 16 + ".bak"))
    assert refused(lambda: world.undo(saved.row_id)).code == "backup_damaged"


def test_a_marker_that_holds_bytes_is_damaged(world: World) -> None:
    saved = world.save("high")
    (world.ledger_dir() / saved.row["backup"]).write_text("x")
    assert refused(lambda: world.undo(saved.row_id)).code == "backup_damaged"


def test_a_missing_marker_is_pruned(world: World) -> None:
    saved = world.save("high")
    (world.ledger_dir() / saved.row["backup"]).unlink()
    err = refused(lambda: world.undo(saved.row_id))
    assert err.params == {"reason": "backup_pruned"}


# Restore


def test_a_restore_puts_back_the_backup_of_any_visible_row(world: World) -> None:
    path = settings(world)
    first = world.save("high")
    world.save("medium")
    token = world.store.restore_version(world.targets(), PROJECT_KEY, first.row_id)
    done = world.store.restore(
        world.targets(),
        PROJECT_KEY,
        first.row_id,
        version=token,
        request_id="restore-0001",
    )
    assert path.read_text() == OLD
    assert done.row["kind"] == "restore"
    assert done.row["restored_from"] == first.row_id
    err = refused(lambda: world.undo(done.row_id))
    assert err.params == {"reason": "restore_row"}


def test_a_restore_needs_its_token(world: World) -> None:
    settings(world)
    first = world.save("high")

    def restore(version: str) -> Refused:
        return refused(
            lambda: world.store.restore(
                world.targets(),
                PROJECT_KEY,
                first.row_id,
                version=version,
                request_id="restore-0002",
            )
        )

    assert restore("x").code == "bad_version"
    assert restore(world.version("low")).code == "preview_mismatch"
    assert world.path().read_text() == HIGH


def test_a_restore_of_a_create_deletes_the_file(world: World) -> None:
    first = world.save("high")
    token = world.store.restore_version(world.targets(), PROJECT_KEY, first.row_id)
    done = world.store.restore(
        world.targets(),
        PROJECT_KEY,
        first.row_id,
        version=token,
        request_id="restore-0003",
    )
    assert not world.path().exists()
    assert done.removed_file is True


def test_a_leftover_local_file_can_not_be_restored(
    edit_config: Path, tmp_path: Path
) -> None:
    repo = (tmp_path / "repo").resolve()
    (repo / ".git").mkdir(parents=True)
    sub = repo / "sub"
    sub.mkdir()
    world = make_world(edit_config, sub)
    leftover = world.targets()[3]
    folder = world.backups / edit_store.target_id_of(
        os.path.realpath(leftover.display_path)
    )
    folder.mkdir(parents=True)
    row: dict[str, Any] = {
        "id": "a" * 16,
        "kind": "edit",
        "op": "create",
        "key_path": ["effortLevel"],
        "layer": "local",
        "before_sha256": "absent",
        "after_sha256": "0" * 64,
        "backup": "000001-" + "a" * 16 + ".absent",
    }
    (folder / "ledger.json").write_text(json.dumps({"version": 1, "rows": [row]}))
    (folder / row["backup"]).write_bytes(b"")
    err = refused(
        lambda: world.store.restore(
            [leftover], PROJECT_KEY, "a" * 16, version="x", request_id="restore-0004"
        )
    )
    assert err.code == "not_editable"


# Forged rows


@pytest.mark.parametrize(
    "change",
    [
        {"project": "another-project"},
        {"real_path": "/work/cfg/elsewhere.json"},
        {"scope": "user"},
        {"layer": "user"},
        {"id": "../../../etc/passwd"},
        {"id": "short"},
        {"kind": "delete"},
        {"op": "rm -rf"},
        {"key_path": "effortLevel"},
        {"key_path": [1, 2]},
        {"before_sha256": "nope"},
        {"after_sha256": None},
        {"backup": "../../x.bak"},
        {"backup": "000001-ABC.bak"},
        {"backup": None},
        {"restored_from_backup": "../x"},
    ],
)
def test_a_row_that_does_not_fit_the_registry_target_is_forged(
    world: World, change: dict[str, Any]
) -> None:
    settings(world)
    saved = world.save("high")
    tamper(world, lambda rows: rows[0].update(change))
    row_id = change.get("id", saved.row_id)
    assert refused(lambda: world.undo(row_id)).code == "forged_row"
    assert world.path().read_text() == HIGH


def test_a_row_whose_id_is_not_text_is_found_by_nobody(world: World) -> None:
    settings(world)
    world.save("high")
    tamper(world, lambda rows: rows[0].update(id=7))
    assert refused(lambda: world.undo("7")).code == "unknown_edit"


def test_a_row_with_another_path_never_moves_the_write(
    world: World, tmp_path: Path
) -> None:
    settings(world)
    saved = world.save("high")
    victim = write_json(tmp_path / "victim.json", '{"effortLevel": "low"}\n')
    tamper(
        world,
        lambda rows: rows[0].update(real_path=str(victim), display_path=str(victim)),
    )
    assert refused(lambda: world.undo(saved.row_id)).code == "forged_row"
    assert victim.read_text() == '{"effortLevel": "low"}\n'
    assert world.path().read_text() == HIGH


def test_a_row_copied_into_another_targets_ledger_is_forged(world: World) -> None:
    settings(world)
    saved = world.save("high")
    write_json(world.path("user"), '{"model": "x"}\n')
    world.save("sonnet", "user", field_name="model")
    user_ledger = world.ledger_dir("user") / "ledger.json"
    doc = json.loads(user_ledger.read_bytes())
    doc["rows"].append(world.ledger()[0])
    user_ledger.write_text(json.dumps(doc))
    assert refused(lambda: world.undo(saved.row_id)).code == "forged_row"
    assert (
        refused(
            lambda: world.store.drift(world.targets(), PROJECT_KEY, saved.row_id)
        ).code
        == "forged_row"
    )
    assert world.path().read_text() == HIGH


def test_a_row_in_a_ledger_no_registry_target_owns_is_unknown(
    world: World, tmp_path: Path
) -> None:
    other = (tmp_path / "other").resolve()
    (other / ".claude").mkdir(parents=True)
    foreign = make_world(world.config, other)
    foreign.save("high")
    row_id = foreign.ledger()[0]["id"]
    assert refused(lambda: world.undo(row_id)).code == "unknown_edit"


def test_a_row_is_checked_against_the_path_the_target_resolves_to_now(
    world: World,
) -> None:
    settings(world)
    world.save("high")
    resolved = world.store.resolve(world.target())
    row = world.ledger()[0]
    bad = dataclasses.replace(resolved, target_id="0" * 16)
    with pytest.raises(Refused) as caught:
        edit_store._check_row(bad, row, PROJECT_KEY)
    assert caught.value.code == "forged_row"
    edit_store._check_row(resolved, row, PROJECT_KEY)


def test_a_ledger_that_is_damaged_hides_its_rows_from_the_search(world: World) -> None:
    settings(world)
    saved = world.save("high")
    (world.ledger_dir() / "ledger.json").write_text("junk")
    assert refused(lambda: world.undo(saved.row_id)).code == "unknown_edit"


# Row status


def status(world: World, index: int = -1) -> edit_store.RowStatus:
    rows = world.store.read_rows(world.target())
    return world.store.row_status(world.target(), rows[index])


def test_the_state_of_each_row_is_worked_out_from_hashes(world: World) -> None:
    path = settings(world)
    first = world.save("high")
    assert status(world) == edit_store.RowStatus("can_undo", None, False)
    second = world.save("medium")
    assert status(world, 0) == edit_store.RowStatus("not_undoable", "not_newest", False)
    path.write_text("{}\n")
    assert status(world) == edit_store.RowStatus(
        "changed_since", "changed_since_save", True
    )
    path.write_text(OLD.replace('"low"', '"medium"'))
    done = world.undo(second.row_id)
    rows = world.store.read_rows(world.target())
    assert [r["id"] for r in rows] == [first.row_id, second.row_id, done.row_id]
    assert world.store.row_status(world.target(), rows[2]).reason == "undo_row"
    assert world.store.row_status(world.target(), rows[1]) == edit_store.RowStatus(
        "undone", None, False
    )
    assert world.store.row_status(world.target(), rows[0]).reason == "not_newest"


def test_the_state_of_a_create_and_of_a_restore(world: World) -> None:
    first = world.save("high")
    assert status(world) == edit_store.RowStatus("deletes_file", None, False)
    token = world.store.restore_version(world.targets(), PROJECT_KEY, first.row_id)
    world.store.restore(
        world.targets(),
        PROJECT_KEY,
        first.row_id,
        version=token,
        request_id="restore-0005",
    )
    assert status(world).undo_state == "not_undoable"
    assert status(world).reason == "restore_row"


def test_a_missing_or_damaged_backup_and_an_unreadable_file_show_in_the_state(
    world: World,
) -> None:
    path = settings(world)
    world.save("high")
    backup = world.ledger_dir() / world.ledger()[0]["backup"]
    backup.write_text("x")
    assert status(world).reason == "backup_damaged"
    backup.unlink()
    assert status(world).reason == "backup_pruned"
    path.unlink()
    os.mkfifo(path)
    assert status(world).reason == "backup_pruned"
    backup.write_text(OLD)
    assert status(world).reason == "file_refused"


def test_a_target_with_no_backups_folder_has_no_rows_and_nothing_to_undo(
    world: World,
) -> None:
    assert world.store.read_rows(world.target()) == []
    row = {"id": "a" * 16, "kind": "edit"}
    assert world.store.row_status(world.target(), row).reason == "not_newest"
    tamper_target = world.target()
    assert world.store.rebuild_written  # the method exists for the drift route
    assert tamper_target.scope == "project"


# Raced and unverified


def test_a_file_changed_by_another_writer_after_the_rename_is_raced(
    world: World,
) -> None:
    path = settings(world)

    def seam(name: str) -> None:
        if name == "reread":
            other_program_writes(path, "{}\n")

    world.store.seam = seam
    err = refused(lambda: world.save("high"))
    assert err.code == "raced"
    assert err.row_id == world.ledger()[0]["id"]
    assert world.ledger()[0]["raced"] is True
    assert path.read_text() == "{}\n"


def test_a_delete_that_is_undone_by_another_writer_is_raced(world: World) -> None:
    saved = world.save("high")
    path = world.path()

    def seam(name: str) -> None:
        if name == "reread":
            write_json(path, "{}\n")

    world.store.seam = seam
    assert refused(lambda: world.undo(saved.row_id)).code == "raced"


def test_a_restore_that_does_not_match_its_backup_on_the_second_read_is_raced(
    world: World,
) -> None:
    settings(world)
    saved = world.save("high")
    world.save("medium")
    token = world.store.restore_version(world.targets(), PROJECT_KEY, saved.row_id)
    backup = world.ledger_dir() / saved.row["backup"]

    def seam(name: str) -> None:
        if name == "reread":
            backup.write_text("changed after the write")

    world.store.seam = seam
    err = refused(
        lambda: world.store.restore(
            world.targets(),
            PROJECT_KEY,
            saved.row_id,
            version=token,
            request_id="restore-0006",
        )
    )
    assert err.code == "raced"


def test_a_failed_read_back_is_write_failed_and_keeps_the_row(world: World) -> None:
    settings(world)

    def seam(name: str) -> None:
        if name == "reread":
            folder = world.project / ".claude"
            folder.rename(world.project / ".claude-aside")
            folder.symlink_to(world.project / ".claude-aside")

    world.store.seam = seam
    err = refused(lambda: world.save("high"))
    assert (err.code, err.params) == ("write_failed", {"stage": "reread"})
    assert err.row_id


def test_a_failed_fsync_is_write_failed_and_keeps_the_row(world: World) -> None:
    path = settings(world)

    def seam(name: str) -> None:
        if name == "dir_fsync":
            raise OSError(5, "fsync")

    world.store.seam = seam
    err = refused(lambda: world.save("high"))
    assert (err.code, err.params) == ("write_failed", {"stage": "fsync"})
    assert path.read_text() == HIGH


# Rechecks


def test_the_first_recheck_confirms_a_file_nobody_touched(world: World) -> None:
    settings(world)
    saved = world.save("high")
    result = world.store.run_recheck(world.target(), saved.row_id)
    assert result is not None
    assert result["state"] == "confirmed"
    assert result["changed_keys"] == []
    assert result["ours_survived"] is True
    assert result["at"]
    assert world.ledger()[0]["recheck"] == result
    world.run_timers()
    assert world.ledger()[0]["recheck"]["state"] == "confirmed"


def test_a_recheck_names_the_keys_another_program_changed_and_whether_ours_survived(
    world: World,
) -> None:
    path = settings(world)
    saved = world.save("high")
    other_program_writes(path, HIGH.replace("opus", "sonnet"))
    result = world.store.run_recheck(world.target(), saved.row_id)
    assert result == {
        "state": "overwritten",
        "changed_keys": ["model"],
        "ours_survived": True,
        "at": result["at"] if result else None,
    }
    other_program_writes(path, HIGH.replace('"high"', '"max"'))
    again = world.store.run_recheck(world.target(), saved.row_id)
    assert again is not None
    assert (again["state"], again["changed_keys"], again["ours_survived"]) == (
        "overwritten",
        ["effortLevel"],
        False,
    )
    other_program_writes(path, HIGH)
    assert (world.store.run_recheck(world.target(), saved.row_id) or {})[
        "state"
    ] == "confirmed"


def test_a_recheck_of_a_file_that_is_gone_or_unreadable_is_overwritten(
    world: World,
) -> None:
    path = settings(world)
    saved = world.save("high")
    path.unlink()
    gone = world.store.run_recheck(world.target(), saved.row_id)
    assert gone is not None
    assert (gone["state"], gone["ours_survived"]) == ("overwritten", False)
    os.mkfifo(path)
    odd = world.store.run_recheck(world.target(), saved.row_id)
    assert odd is not None
    assert (odd["state"], odd["changed_keys"], odd["ours_survived"]) == (
        "overwritten",
        [],
        False,
    )
    path.unlink()
    write_json(path, "not json")
    broken = world.store.run_recheck(world.target(), saved.row_id)
    assert broken is not None
    assert broken["state"] == "overwritten"
    assert broken["ours_survived"] is False


def test_the_changed_keys_are_capped(world: World) -> None:
    path = settings(world)
    saved = world.save("high")
    many = {f"k{index:03d}": index for index in range(80)}
    other_program_writes(path, json.dumps({"effortLevel": "high", **many}))
    result = world.store.run_recheck(world.target(), saved.row_id)
    assert result is not None
    assert len(result["changed_keys"]) == edit_store.MAX_CHANGED_KEYS


def test_a_recheck_with_no_backup_to_rebuild_from_still_says_overwritten(
    world: World,
) -> None:
    path = settings(world)
    saved = world.save("high")
    (world.ledger_dir() / saved.row["backup"]).unlink()
    other_program_writes(path, "{}\n")
    result = world.store.run_recheck(world.target(), saved.row_id)
    assert result is not None
    assert (result["state"], result["changed_keys"], result["ours_survived"]) == (
        "overwritten",
        [],
        False,
    )


def test_a_recheck_of_an_undo_row_compares_with_the_restored_bytes(
    world: World,
) -> None:
    path = settings(world)
    saved = world.save("high")
    done = world.undo(saved.row_id)
    assert (world.store.run_recheck(world.target(), done.row_id) or {})[
        "state"
    ] == "confirmed"
    other_program_writes(path, OLD.replace("opus", "haiku"))
    result = world.store.run_recheck(world.target(), done.row_id)
    assert result is not None
    assert (result["state"], result["changed_keys"]) == ("overwritten", ["model"])


def test_a_recheck_that_can_not_reach_the_row_returns_nothing(world: World) -> None:
    settings(world)
    saved = world.save("high")
    assert world.store.run_recheck(world.target(), "f" * 16) is None
    assert world.store.run_recheck(world.target("user"), saved.row_id) is None
    (world.ledger_dir() / "ledger.json").write_text("junk")
    assert world.store.run_recheck(world.target(), saved.row_id) is None


def test_a_recheck_after_the_target_stopped_resolving_returns_nothing(
    world: World, tmp_path: Path
) -> None:
    settings(world)
    saved = world.save("high")
    folder = world.project / ".claude"
    folder.rename(world.project / ".claude-aside")
    outside = tmp_path / "outside"
    outside.mkdir()
    folder.symlink_to(outside)
    assert world.store.run_recheck(world.target(), saved.row_id) is None


def test_a_recheck_gives_up_when_a_save_holds_the_lock(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings(world)
    saved = world.save("high")
    monkeypatch.setattr(edit_store, "LOCK_WAIT", 0.05)
    resolved = world.store.resolve(world.target())
    lock = world.store._target_lock(resolved.target_id)
    with lock:
        assert world.store.run_recheck(world.target(), saved.row_id) is None
    assert world.ledger()[0]["recheck"]["state"] == "checking"


def test_a_recheck_that_loses_its_row_before_it_writes_returns_nothing(
    world: World,
) -> None:
    settings(world)
    saved = world.save("high")
    resolved = world.store.resolve(world.target())
    assert (
        world.store._store_recheck(resolved, "f" * 16, {"state": "confirmed"}) is None
    )
    (world.ledger_dir() / "ledger.json").write_text("junk")
    assert (
        world.store._store_recheck(resolved, saved.row_id, {"state": "confirmed"})
        is None
    )


# Drift: the bytes Bar Tab wrote against the bytes now


def test_drift_returns_what_was_written_and_what_is_there_now(world: World) -> None:
    path = settings(world)
    saved = world.save("high")
    other_program_writes(path, HIGH.replace("opus", "sonnet"))
    drift = world.store.drift(world.targets(), PROJECT_KEY, saved.row_id)
    assert drift.written == HIGH.encode()
    assert drift.now == HIGH.replace("opus", "sonnet").encode()


def test_drift_of_a_create_and_of_an_undo(world: World) -> None:
    created = world.save("high")
    drift = world.store.drift(world.targets(), PROJECT_KEY, created.row_id)
    assert drift.written == b'{\n  "effortLevel": "high"\n}\n'
    done = world.undo(created.row_id)
    gone = world.store.drift(world.targets(), PROJECT_KEY, done.row_id)
    assert (gone.written, gone.now) == (None, None)
    write_json(world.path(), OLD)
    saved = world.save("high")
    undone = world.undo(saved.row_id)
    assert (
        world.store.drift(world.targets(), PROJECT_KEY, undone.row_id).written
        == OLD.encode()
    )


def test_drift_that_can_not_be_rebuilt_is_cant_rebuild(world: World) -> None:
    settings(world)
    saved = world.save("high")
    ids = (world.targets(), PROJECT_KEY, saved.row_id)
    tamper(world, lambda rows: rows[0].update(after_sha256="1" * 64))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].update(after_sha256=saved.row["after_sha256"]))
    assert world.store.drift(*ids).written == HIGH.encode()
    tamper(world, lambda rows: rows[0].update(new_value="hidden"))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].update(new_value="high", op="insert"))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].update(op="create"))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].update(op="remove"))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].update(op="replace", key_path=["a", "b", "c"]))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    tamper(world, lambda rows: rows[0].pop("key_path"))
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"
    (world.ledger_dir() / saved.row["backup"]).unlink()
    assert refused(lambda: world.store.drift(*ids)).code == "cant_rebuild"


def test_drift_with_no_backups_folder_or_an_unknown_row_is_refused(
    world: World,
) -> None:
    assert (
        refused(lambda: world.store.drift(world.targets(), PROJECT_KEY, "a" * 16)).code
        == "unknown_edit"
    )


def test_the_masked_value_of_a_secret_shape_is_never_saved(world: World) -> None:
    body = world.save_body("high", version="x")
    assert body.value == "high"
    err = refused(lambda: world.save("sk-live-abc", field_name="model"))
    assert err.params == {"reason": "secret"}
    assert not world.path().exists()
    assert "sk-live-abc" not in json.dumps(
        [p.read_text() for p in world.config.rglob("*") if p.is_file()]
    )
