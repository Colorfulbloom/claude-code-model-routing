"""A save through the write core: backup first, atomic, recorded (m6-build.md 3.6, 3.7).

Covers the order of steps, the row and the backup it leaves, create, prune, failure
clean-up, the token, canonical body and request ids. Links and file refusals are in
``test_edit_store_targets.py``, undo and rechecks in ``test_edit_store_undo.py``.
"""

# pyright: reportPrivateUsage=false
# These tests reach into the writer's helpers to set up a state or read one.

import base64
import errno
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_helpers import FIELD, PROJECT_KEY, World, make_world, request_id, write_json

import edit_store
import write_guard
from edit_store import FileBytes, Refused
from models import EditPreviewRequest

OLD = (
    '{\n  "model": "opus",\n  "effortLevel": "low",\n  "env": {\n    "A": "1"\n  }\n}\n'
)
BACKUP_NAME = re.compile(r"^\d{6}-[0-9a-f]{16}\.(bak|absent)$")


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    return make_world(edit_config, edit_project, secret=b"s" * 32)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def settings(world: World, text: str, mode: int = 0o644) -> Path:
    return write_json(world.path(), text, mode)


def temps(folder: Path) -> list[str]:
    return [
        p.name for p in folder.iterdir() if p.name.startswith(".routing-dashboard-")
    ]


def mode_of(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def open_fds() -> int:
    return len(os.listdir("/dev/fd"))  # noqa: PTH208


# What a good save leaves


def test_a_replace_changes_only_the_value_and_backs_up_the_old_file_first(
    world: World,
) -> None:
    path = settings(world, OLD)
    ledger_dir = world.ledger_dir()
    seen: dict[str, object] = {}

    def seam(name: str) -> None:
        if name == "after_backup":
            seen["after_backup_files"] = sorted(p.name for p in ledger_dir.iterdir())
            seen["after_backup_target"] = path.read_text()
        if name == "after_ledger":
            seen["rows_before_write"] = len(world.ledger())
            seen["target_before_write"] = path.read_text()
        if name == "after_temp":
            seen["temp_names"] = temps(path.parent)
            seen["target_with_temp"] = path.read_text()

    world.store.seam = seam
    result = world.save("high")
    new = OLD.replace('"low"', '"high"')
    assert path.read_text() == new
    assert seen["after_backup_target"] == OLD
    assert seen["target_before_write"] == OLD
    assert seen["target_with_temp"] == OLD
    assert seen["rows_before_write"] == 1
    assert len(seen["temp_names"]) == 1  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    assert temps(path.parent) == []
    row = result.row
    backup = ledger_dir / row["backup"]
    assert BACKUP_NAME.match(row["backup"])
    assert backup.read_bytes() == OLD.encode()
    assert mode_of(backup) == 0o600
    assert mode_of(ledger_dir) == 0o700
    assert row["before_sha256"] == sha(OLD.encode())
    assert row["after_sha256"] == sha(new.encode())
    assert result.row_id == row["id"]
    assert result.saved_at == row["time"]


def test_the_row_carries_the_old_fields_and_the_new_ones(world: World) -> None:
    settings(world, OLD)
    row = world.save("high").row
    assert row["kind"] == "edit"
    assert row["op"] == "replace"
    assert row["key_path"] == ["effortLevel"]
    assert row["layer"] == "project"
    assert row["old_value"] == "low"
    assert row["new_value"] == "high"
    assert row["restored_from"] is None
    assert row["restored_from_backup"] is None
    assert row["project"] == PROJECT_KEY
    assert row["field"] == FIELD
    assert row["scope"] == "project"
    assert row["subject"] == {"kind": "main", "name": None}
    assert row["app"] == "bartab"
    assert re.match(r"^[0-9a-f]{32}$", row["request_id"])
    assert row["display_path"] == str(world.path())
    assert row["real_path"] == os.path.realpath(world.path())
    assert row["recheck"] == {
        "state": "checking",
        "changed_keys": [],
        "ours_survived": None,
        "at": None,
    }
    assert "made_dir" not in row


def test_the_ledger_is_the_old_apps_version_1_shape_in_the_old_apps_folder(
    world: World,
) -> None:
    settings(world, OLD)
    world.save("high")
    folder = world.backups / edit_store.target_id_of(os.path.realpath(world.path()))
    doc = json.loads((folder / "ledger.json").read_bytes())
    assert set(doc) == {"version", "rows"}
    assert doc["version"] == 1
    assert (folder / "ledger.json").read_bytes() == json.dumps(doc, indent=1).encode()
    assert (folder / ".lock").is_file()
    assert mode_of(folder / ".lock") == 0o600
    assert mode_of(folder / "ledger.json") == 0o600
    assert (
        edit_store.target_id_of(os.path.realpath(world.path()))
        == hashlib.sha256(os.fsencode(os.path.realpath(world.path()))).hexdigest()[:16]
    )


def test_an_insert_keeps_the_layout_of_the_file(world: World) -> None:
    settings(world, OLD.replace('  "effortLevel": "low",\n', ""))
    result = world.save("high")
    assert result.row["op"] == "insert"
    assert world.path().read_text() == (
        '{\n  "model": "opus",\n  "env": {\n    "A": "1"\n  },\n'
        '  "effortLevel": "high"\n}\n'
    )


def test_a_value_under_env_is_written_as_text(world: World) -> None:
    settings(world, '{"env": {"A": "1"}}\n')
    result = world.save(
        200000,
        field_name="autoCompactWindow",
        key_path=("env", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"),
    )
    assert (
        json.loads(world.path().read_text())["env"]["CLAUDE_CODE_AUTO_COMPACT_WINDOW"]
        == "200000"
    )
    assert result.row["new_value"] == "200000"


def test_the_window_under_model_settings_may_be_auto(world: World) -> None:
    settings(world, '{"modelSettings": {"opus": {"effort": "low"}}}\n')
    world.save(
        "auto",
        field_name="autoCompactWindow",
        key_path=("modelSettings", "opus", "autoCompactWindow"),
    )
    assert json.loads(world.path().read_text())["modelSettings"]["opus"] == {
        "effort": "low",
        "autoCompactWindow": "auto",
    }


def test_the_default_key_is_the_env_twin_when_only_that_is_set(world: World) -> None:
    settings(world, '{"env": {"CLAUDE_CODE_EFFORT_LEVEL": "low"}}\n')
    result = world.save("high")
    assert result.row["key_path"] == ["env", "CLAUDE_CODE_EFFORT_LEVEL"]
    assert (
        json.loads(world.path().read_text())["env"]["CLAUDE_CODE_EFFORT_LEVEL"]
        == "high"
    )
    assert edit_store.choose_key_path(
        {"effortLevel": "x", "env": {}}, "effortLevel"
    ) == ("effortLevel",)
    assert edit_store.choose_key_path({"env": []}, "model") == ("model",)


def test_the_files_mode_is_kept(world: World) -> None:
    path = settings(world, OLD, mode=0o640)
    world.save("high")
    assert mode_of(path) == 0o640


def test_the_temp_file_is_private_until_it_takes_the_old_mode(world: World) -> None:
    path = settings(world, OLD, mode=0o640)
    seen: dict[str, int] = {}

    def seam(name: str) -> None:
        if name == "after_temp":
            (name_,) = temps(path.parent)
            seen["mode"] = mode_of(path.parent / name_)

    world.store.seam = seam
    world.save("high")
    assert seen["mode"] == 0o640


# Create


def test_a_missing_file_is_created_with_an_absent_marker(world: World) -> None:
    path = world.path()
    assert not path.exists()
    result = world.save("high")
    assert path.read_text() == '{\n  "effortLevel": "high"\n}\n'
    assert mode_of(path) == 0o600
    row = result.row
    assert row["op"] == "create"
    assert row["before_sha256"] == "absent"
    assert row["backup"].endswith(".absent")
    marker = world.ledger_dir() / row["backup"]
    assert marker.read_bytes() == b""
    assert "made_dir" not in row


def test_a_missing_claude_folder_is_made_private_and_recorded(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)
    result = world.save("high")
    assert mode_of(bare / ".claude") == 0o700
    assert (
        bare / ".claude" / "settings.json"
    ).read_text() == '{\n  "effortLevel": "high"\n}\n'
    assert result.row["made_dir"] is True


def test_a_file_that_appears_after_the_read_is_never_overwritten(world: World) -> None:
    path = world.path()

    def seam(name: str) -> None:
        if name == "before_recheck":
            path.write_text("{}\n")

    world.store.seam = seam
    with pytest.raises(Refused) as caught:
        world.save("high")
    assert caught.value.code == "changed"
    assert path.read_text() == "{}\n"
    assert temps(path.parent) == []
    assert [
        p.name for p in world.ledger_dir().iterdir() if BACKUP_NAME.match(p.name)
    ] == []


def test_a_claude_folder_that_appears_after_the_read_is_not_taken_over(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)

    def seam(name: str) -> None:
        if name == "after_ledger":
            (bare / ".claude").mkdir()

    world.store.seam = seam
    with pytest.raises(Refused) as caught:
        world.save("high")
    assert caught.value.code == "changed"
    assert list((bare / ".claude").iterdir()) == []
    assert caught.value.dir_left is False


# Failures clean up


def test_a_failure_before_the_rename_leaves_everything_as_it_was(
    world: World,
) -> None:
    path = settings(world, OLD)
    first = world.save("high")
    ledger_dir = world.ledger_dir()
    before = (ledger_dir / "ledger.json").read_bytes()
    files = sorted(p.name for p in ledger_dir.iterdir())

    def seam(name: str) -> None:
        if name == "after_temp":
            raise OSError(errno.ENOSPC, "disk full")

    world.store.seam = seam
    with pytest.raises(Refused) as caught:
        world.save("low")
    assert caught.value.code == "write_failed"
    assert caught.value.params == {"errno": "ENOSPC"}
    assert path.read_text() == OLD.replace('"low"', '"high"')
    assert (ledger_dir / "ledger.json").read_bytes() == before
    assert sorted(p.name for p in ledger_dir.iterdir()) == files
    assert temps(path.parent) == []
    assert first.row["id"] in before.decode()


def test_a_failure_after_a_made_folder_takes_the_folder_away_again(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)

    def seam(name: str) -> None:
        if name == "after_temp":
            raise OSError(errno.EIO, "boom")

    world.store.seam = seam
    with pytest.raises(Refused) as caught:
        world.save("high")
    assert caught.value.code == "write_failed"
    assert caught.value.dir_left is False
    assert not (bare / ".claude").exists()


def test_a_made_folder_that_cannot_be_removed_is_reported(
    edit_config: Path, tmp_path: Path
) -> None:
    bare = (tmp_path / "bare").resolve()
    bare.mkdir()
    world = make_world(edit_config, bare)

    def seam(name: str) -> None:
        if name == "after_temp":
            (bare / ".claude" / "stray.txt").write_text("x")
            raise OSError(errno.EIO, "boom")

    world.store.seam = seam
    with pytest.raises(Refused) as caught:
        world.save("high")
    assert caught.value.dir_left is True
    assert (bare / ".claude" / "stray.txt").exists()
    assert temps(bare / ".claude") == []


def test_a_refusal_after_the_ledger_write_rolls_the_row_back(world: World) -> None:
    settings(world, OLD)

    def seam(name: str) -> None:
        if name == "after_backup":
            raise Refused("write_failed")

    world.store.seam = seam
    with pytest.raises(Refused):
        world.save("high")
    ledger_dir = world.ledger_dir()
    assert not any(BACKUP_NAME.match(p.name) for p in ledger_dir.iterdir())


def test_a_stale_temp_file_is_swept(world: World) -> None:
    path = settings(world, OLD)
    stale = path.parent / ".routing-dashboard-0123456789abcdef.tmp"
    stale.write_text("old crash")
    old = time.time() - 61
    os.utime(stale, (old, old))
    keep = path.parent / "notes.txt"
    keep.write_text("mine")
    world.save("high")
    assert not stale.exists()
    assert keep.read_text() == "mine"


def test_no_descriptor_leaks_through_a_save_or_a_refusal(world: World) -> None:
    settings(world, OLD)
    world.save("high")  # warm up
    before = open_fds()
    world.save("medium")
    with pytest.raises(Refused):
        world.save("medium")  # no_change
    assert open_fds() == before


# Backup numbering and prune


def test_backups_are_numbered_in_order(world: World) -> None:
    settings(world, OLD)
    names = [world.save(v).row["backup"] for v in ("high", "low", "high")]
    assert [n[:6] for n in names] == ["000001", "000002", "000003"]


def test_prune_keeps_the_newest_twenty_rows_and_their_backups(world: World) -> None:
    settings(world, OLD)
    for index in range(25):
        world.save("high" if index % 2 == 0 else "low")
    rows = world.ledger()
    assert len(rows) == 20
    on_disk = sorted(
        p.name for p in world.ledger_dir().iterdir() if BACKUP_NAME.match(p.name)
    )
    assert on_disk == sorted(row["backup"] for row in rows)
    assert on_disk[0].startswith("000006")


def test_prune_removes_a_stray_marker_and_a_new_stray_backup_but_keeps_an_old_one(
    world: World,
) -> None:
    settings(world, OLD)
    world.save("high")
    ledger_dir = world.ledger_dir()
    marker = ledger_dir / "000900-0123456789abcdef.absent"
    marker.write_bytes(b"")
    fresh = ledger_dir / "000901-0123456789abcdef.bak"
    fresh.write_bytes(b"x")
    ancient = ledger_dir / "000902-0123456789abcdef.bak"
    ancient.write_bytes(b"x")
    os.utime(ancient, (1_000_000, 1_000_000))
    world.save("low")
    assert not marker.exists()
    assert not fresh.exists()
    assert ancient.exists()


def test_a_ledger_row_that_never_applied_is_not_visible(world: World) -> None:
    path = settings(world, OLD)
    world.save("high")
    ledger = world.ledger_dir() / "ledger.json"
    doc = json.loads(ledger.read_bytes())
    current = sha(path.read_bytes())
    doc["rows"].append(
        {
            "id": "f" * 16,
            "kind": "edit",
            "before_sha256": current,
            "after_sha256": "0" * 64,
            "backup": "000099-" + "f" * 16 + ".bak",
        }
    )
    ledger.write_text(json.dumps(doc))
    assert [row["id"] for row in world.store.read_rows(world.target())] != ["f" * 16]
    assert len(world.store.read_rows(world.target())) == 1


@pytest.mark.parametrize(
    "junk",
    [
        b"not json",
        b"[]",
        b'{"version": 2, "rows": []}',
        b'{"version": 1, "rows": "x"}',
        b'{"version": 1, "rows": [1]}',
        b'{"version": 1, "rows": [], "pad": "' + b"x" * (4 * 1024 * 1024) + b'"}',
        b"\xff\xfe",
    ],
)
def test_a_damaged_ledger_stops_every_write(world: World, junk: bytes) -> None:
    path = settings(world, OLD)
    world.save("high")
    (world.ledger_dir() / "ledger.json").write_bytes(junk)
    with pytest.raises(Refused) as caught:
        world.save("low")
    assert caught.value.code == "ledger_damaged"
    assert path.read_text() == OLD.replace('"low"', '"high"')
    with pytest.raises(Refused) as caught:
        world.store.read_rows(world.target())
    assert caught.value.code == "ledger_damaged"


def test_a_ledger_that_is_a_link_is_damaged(world: World) -> None:
    settings(world, OLD)
    world.save("high")
    ledger = world.ledger_dir() / "ledger.json"
    ledger.unlink()
    ledger.symlink_to(world.home / "x.json")
    with pytest.raises(Refused) as caught:
        world.save("low")
    assert caught.value.code == "ledger_damaged"


def test_a_backup_folder_that_is_a_link_is_refused(world: World) -> None:
    settings(world, OLD)
    folder = world.ledger_dir()
    folder.parent.mkdir(parents=True, exist_ok=True)
    elsewhere = world.home / "elsewhere"
    elsewhere.mkdir()
    folder.symlink_to(elsewhere)
    with pytest.raises(Refused) as caught:
        world.save("high")
    assert caught.value.code == "write_failed"
    assert list(elsewhere.iterdir()) == []


def test_a_backup_folder_that_is_not_ours_is_refused(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings(world, OLD)
    world.save("high")
    monkeypatch.setattr(os, "geteuid", lambda: os.getuid() + 1)
    with pytest.raises(Refused) as caught:
        world.store.read_rows(world.target())
    assert caught.value.code == "write_failed"


def test_a_loose_backup_folder_is_made_private_when_it_is_made(world: World) -> None:
    settings(world, OLD)
    world.save("high")
    assert mode_of(world.backups) == 0o700
    assert mode_of(world.config / "routing-dashboard") != 0o000


# The token


def test_a_preview_for_another_value_is_preview_mismatch(world: World) -> None:
    settings(world, OLD)
    version = world.version("high")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("medium", version=version))
    assert caught.value.code == "preview_mismatch"
    assert caught.value.preview == FileBytes(OLD.encode())
    assert caught.value.current == FileBytes(OLD.encode())
    assert world.path().read_text() == OLD


def test_a_file_that_changed_after_the_preview_is_changed(world: World) -> None:
    path = settings(world, OLD)
    body = world.save_body("high")
    path.write_text(OLD.replace("opus", "sonnet"))
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "changed"
    assert caught.value.preview == FileBytes(OLD.encode())
    assert caught.value.current == FileBytes(OLD.replace("opus", "sonnet").encode())
    assert path.read_text() == OLD.replace("opus", "sonnet")


def test_an_atomic_rewrite_with_the_same_bytes_is_still_changed(world: World) -> None:
    path = settings(world, OLD)
    body = world.save_body("high")
    other = path.with_name("x.json")
    write_json(other, OLD)
    other.replace(path)
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "changed"


def test_a_file_that_appeared_after_a_preview_of_no_file_is_changed(
    world: World,
) -> None:
    body = world.save_body("high")
    settings(world, "{}\n")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), body)
    assert caught.value.code == "changed"
    assert caught.value.preview == FileBytes(None)


def test_the_checks_run_in_a_fixed_order(world: World) -> None:
    path = settings(world, OLD)
    version = world.version("high")
    path.write_text(OLD.replace("opus", "sonnet"))
    # the body differs and the file changed: the body wins
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("medium", version=version))
    assert caught.value.code == "preview_mismatch"
    # a bad tag beats both
    bad = version[:-4] + ("AAAA" if not version.endswith("AAAA") else "BBBB")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("medium", version=bad))
    assert caught.value.code == "bad_version"


def sign_by_hand(secret: bytes, payload: bytes) -> str:
    body = base64.urlsafe_b64encode(payload).rstrip(b"=")
    tag = base64.urlsafe_b64encode(hmac.new(secret, body, hashlib.sha256).digest())
    return body.decode() + "." + tag.rstrip(b"=").decode()


@pytest.mark.parametrize(
    "version",
    ["x", "no-dot", "a.b", ".", "é.é", "e30.e30"],
)
def test_a_token_that_is_not_ours_is_bad_version(world: World, version: str) -> None:
    settings(world, OLD)
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("high", version=version))
    assert caught.value.code == "bad_version"


def test_a_token_from_another_run_is_bad_version(
    world: World, edit_config: Path, edit_project: Path
) -> None:
    settings(world, OLD)
    other = make_world(edit_config, edit_project, secret=b"t" * 32)
    foreign = other.version("high")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("high", version=foreign))
    assert caught.value.code == "bad_version"


def test_a_token_for_another_file_is_bad_version(world: World) -> None:
    settings(world, OLD)
    other = world.version("high", "user")
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("high", version=other))
    assert caught.value.code == "bad_version"


@pytest.mark.parametrize(
    "payload", [b"[1]", b'{"v": 2}', b"\xff", b'{"v": 1, "target_id": "x"}']
)
def test_a_signed_payload_that_is_not_a_good_token_is_bad_version(
    world: World, payload: bytes
) -> None:
    settings(world, OLD)
    version = sign_by_hand(b"s" * 32, payload)
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("high", version=version))
    assert caught.value.code == "bad_version"


def test_a_token_spent_on_a_save_is_changed_afterwards(world: World) -> None:
    settings(world, OLD)
    version = world.version("high")
    world.store.save(world.target(), world.save_body("high", version=version))
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("high", version=version))
    assert caught.value.code == "changed"


def test_the_preview_cache_keeps_bytes_by_token_and_forgets_the_oldest(
    world: World,
) -> None:
    settings(world, OLD)
    seen = world.store.inspect(world.target())
    first = world.store.make_version(seen, world.preview_body("high"))
    assert world.store.preview_bytes(first) == FileBytes(OLD.encode())
    assert world.store.preview_bytes("nope") is None
    for index in range(edit_store.PREVIEW_CACHE):
        world.store.make_version(
            seen, world.preview_body(f"m{index}", field_name="model")
        )
    assert world.store.preview_bytes(first) is None


def test_a_new_run_forgets_every_preview(
    world: World, edit_config: Path, edit_project: Path
) -> None:
    settings(world, OLD)
    version = world.version("high")
    fresh = make_world(edit_config, edit_project, secret=b"s" * 32)
    assert fresh.store.preview_bytes(version) is None
    # the same secret still verifies the token, so the save sees a plain change
    body = world.save_body("high", version=version)
    assert fresh.store.save(fresh.target(), body).row_id


def test_a_preview_of_no_file_and_a_big_one_are_cached_correctly(world: World) -> None:
    seen = world.store.inspect(world.target())
    version = world.store.make_version(seen, world.preview_body("high"))
    assert world.store.preview_bytes(version) == FileBytes(None)
    world.store._remember("big", FileBytes(b"x" * (edit_store.MAX_FILE + 1)))
    assert world.store.preview_bytes("big") is None


def test_the_canonical_body_is_sorted_compact_utf8_without_the_volatile_fields(
    world: World,
) -> None:
    body = EditPreviewRequest.model_validate(
        {
            "project": "pé",
            "op": "set",
            "scope": "user",
            "field": "model",
            "value": "café",
            "seq": 41,
        }
    )
    raw = edit_store.canonical_body(body)
    assert (
        raw
        == (
            '{"field":"model","op":"set","project":"pé","scope":"user","value":"café"}'
        ).encode()
    )
    assert edit_store.choice_key(body) == sha(raw)
    save = world.save_body("high", version="v1", rid="a" * 12)
    again = world.save_body("high", version="v2", rid="b" * 12)
    assert edit_store.choice_key(save) == edit_store.choice_key(again)
    assert edit_store.choice_key(save) == edit_store.choice_key(
        world.preview_body("high")
    )
    assert edit_store.choice_key(save) != edit_store.choice_key(
        world.preview_body("low")
    )
    assert b"seq" not in edit_store.canonical_body(save)
    assert b"request_id" not in edit_store.canonical_body(save)


# Request ids


def test_a_repeat_of_a_request_returns_the_first_result_and_writes_nothing(
    world: World,
) -> None:
    settings(world, OLD)
    body = world.save_body("high", rid="r" * 12)
    first = world.store.save(world.target(), body)
    second = world.store.save(world.target(), body)
    assert second is first
    assert len(world.ledger()) == 1
    assert len(world.timers) == 2


def test_the_same_id_with_another_body_is_request_reused(world: World) -> None:
    settings(world, OLD)
    world.store.save(world.target(), world.save_body("high", rid="r" * 12))
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), world.save_body("low", rid="r" * 12))
    assert caught.value.code == "request_reused"
    assert world.path().read_text() == OLD.replace('"low"', '"high"')


def test_a_refused_request_is_not_remembered(world: World) -> None:
    path = settings(world, OLD)
    stale = world.save_body("high", rid="r" * 12)
    path.write_text(OLD.replace("opus", "sonnet"))
    with pytest.raises(Refused) as caught:
        world.store.save(world.target(), stale)
    assert caught.value.code == "changed"
    fresh = world.save_body("high", rid="r" * 12)
    assert world.store.save(world.target(), fresh).row_id


def test_a_repeat_while_the_first_is_running_waits_and_gets_its_result(
    world: World,
) -> None:
    settings(world, OLD)
    body = world.save_body("high", rid="r" * 12)
    inside = threading.Event()
    release = threading.Event()

    def seam(name: str) -> None:
        if name == "after_read":
            inside.set()
            assert release.wait(5)

    world.store.seam = seam
    results: list[object] = []

    def run() -> None:
        results.append(world.store.save(world.target(), body))

    first = threading.Thread(target=run)
    second = threading.Thread(target=run)
    first.start()
    assert inside.wait(5)
    second.start()
    time.sleep(0.2)
    assert second.is_alive()
    release.set()
    first.join(5)
    second.join(5)
    assert len(results) == 2
    assert results[0] is results[1]
    assert len(world.ledger()) == 1


def test_a_repeat_of_a_failed_run_gets_the_same_refusal(world: World) -> None:
    path = settings(world, OLD)
    stale = world.save_body("high", rid="r" * 12)
    path.write_text(OLD.replace("opus", "sonnet"))
    inside = threading.Event()
    release = threading.Event()

    def seam(name: str) -> None:
        if name == "after_read":
            inside.set()
            assert release.wait(5)

    world.store.seam = seam
    errors: list[Refused] = []

    def run() -> None:
        try:
            world.store.save(world.target(), stale)
        except Refused as exc:
            errors.append(exc)

    first = threading.Thread(target=run)
    second = threading.Thread(target=run)
    first.start()
    assert inside.wait(5)
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(5)
    second.join(5)
    assert [e.code for e in errors] == ["changed", "changed"]
    assert errors[0] is errors[1]


def test_an_unexpected_error_in_the_first_run_reaches_a_waiting_repeat() -> None:
    requests = edit_store._Requests(time.monotonic)
    started = threading.Event()
    release = threading.Event()

    def work() -> int:
        started.set()
        assert release.wait(5)
        raise RuntimeError("boom")

    outcome: list[str] = []

    def owner() -> None:
        try:
            requests.run("a" * 10, "sha", work)
        except RuntimeError:
            outcome.append("owner")

    def waiter() -> None:
        try:
            requests.run("a" * 10, "sha", work)
        except Refused as exc:
            outcome.append(exc.code)

    first = threading.Thread(target=owner)
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=waiter)
    second.start()
    time.sleep(0.2)
    release.set()
    first.join(5)
    second.join(5)
    assert sorted(outcome) == ["owner", "write_failed"]


def test_finished_requests_expire_after_ten_minutes_and_the_table_is_capped() -> None:
    now = [0.0]
    requests = edit_store._Requests(lambda: now[0])
    calls: list[int] = []

    def work() -> int:
        calls.append(1)
        return len(calls)

    assert requests.run("a" * 10, "sha", work) == 1
    assert requests.run("a" * 10, "sha", work) == 1
    now[0] = edit_store.REQUEST_TTL + 1
    assert requests.run("a" * 10, "sha", work) == 2
    for index in range(edit_store.REQUEST_CAP + 20):
        now[0] += 0.001
        requests.run(f"id{index:08d}", "sha", work)
    assert len(requests._items) <= edit_store.REQUEST_CAP + 1


# Threads, permits and the recheck schedule


def test_a_save_runs_whole_in_the_calling_thread_and_leaves_no_permit(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings(world, OLD)
    idents: list[int] = []
    real = write_guard.permit

    def spy(*args: object, **kwargs: object):
        idents.append(threading.get_ident())
        return real(*args, **kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]

    monkeypatch.setattr(write_guard, "permit", spy)
    threads = threading.active_count()
    world.save("high")
    assert idents == [threading.get_ident()]
    assert threading.active_count() == threads
    assert getattr(write_guard.PERMITS, "active", None) is None
    with pytest.raises(Refused):
        world.save("high")
    assert getattr(write_guard.PERMITS, "active", None) is None


def test_a_save_schedules_two_rechecks_and_names_the_first_delay(world: World) -> None:
    settings(world, OLD)
    result = world.save("high")
    assert [delay for delay, _work in world.timers] == [2.0, 10.0]
    assert result.recheck_after_ms == 2000


def test_the_default_scheduler_runs_the_work_in_a_daemon_timer() -> None:
    done = threading.Event()
    edit_store._thread_timer(0.01, done.set)
    assert done.wait(5)


def test_a_recheck_that_raises_is_swallowed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(world.store, "run_recheck", boom)
    world.store._recheck_quietly(world.target(), "x")


def test_a_request_id_is_made_of_safe_characters() -> None:
    assert re.match(r"^[0-9a-f]{32}$", request_id())
