"""The write race (docs/rebuild/research/26-08-write-races.md), as tests (task a4).

Claude Code writes ``settings.json`` and ``settings.local.json`` itself, takes no lock,
and replaces the file with a temp file and a rename. So another writer can change the
file at any step of a save. The rule is that no lost update is silent. A save either
refuses with ``changed`` and writes nothing, or reports ``raced`` and keeps its row, or
the recheck says ``overwritten``.

The first group puts a hostile writer at every seam of the writer, with three ways to
change the file (an in-place rewrite, an atomic replace with a new inode, and a delete),
during a save and during an undo. The expected outcome follows the order of section 3.6.

- Before the second walk (``after_read`` to ``before_recheck``) the second walk sees the
  change and the write is refused with ``changed``. Nothing is written, and the other
  program's bytes stand.
- After the rename (``after_rename``, ``dir_fsync``, ``reread``) the read-back sees it
  and the write reports ``raced``. The row stays and says so.
- Between the second walk and the rename (``before_rename``) nothing can see it. A
  rename has no compare-and-swap, so our rename replaces what the other program wrote,
  and the file then holds our bytes, so the recheck says ``confirmed``. Section 3.6 says
  this window "can't be closed". The test pins that behaviour as it is, so a change
  that closes the window shows up here as a failing test to update on purpose.

The second group is the timed run. A writer replaces the file every 20 ms, as the probe
in 26-08 did, and saves run beside it.
"""

# ruff: noqa: PLR0915 - the timed run is one story, from the first save to the last check.

import hashlib
import json
import shutil
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import timing_policy
from edit_helpers import World, make_world, write_json

import write_guard
from edit_store import Refused, SaveResult, UndoResult

OLD = '{\n  "model": "low",\n  "env": {"NOTE": "a"}\n}\n'
OURS = OLD.replace('"low"', '"high"')
THEIRS = '{\n  "model": "theirs",\n  "env": {"NOTE": "other program"}\n}\n'
FIELD = "model"

CHANGED_SEAMS = (
    "after_read",
    "before_backup",
    "after_backup",
    "after_ledger",
    "after_temp",
    "before_recheck",
)
RACED_SEAMS = ("after_rename", "dir_fsync", "reread")
ACTIONS = ("rewrite", "replace", "delete")
OPERATIONS = ("save", "undo")
LATE_CODES = ("changed", "raced", "lock_busy", "hard_link")


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


@pytest.fixture
def world(edit_config: Path, edit_project: Path) -> World:
    made = make_world(edit_config, edit_project, secret=b"s" * 32)
    write_json(made.path(), OLD)
    return made


def hostile(path: Path, action: str) -> None:
    """Change the file the way another program would."""
    if action == "rewrite":
        with path.open("r+b") as fh:
            fh.truncate(0)
            fh.write(THEIRS.encode())
    elif action == "replace":
        temp = path.with_name(path.name + ".other")
        temp.write_text(THEIRS)
        temp.replace(path)
    else:
        path.unlink()


def scenario(
    world: World, operation: str, seam_name: str, action: str
) -> tuple[Refused | None, SaveResult | UndoResult | None, list[str]]:
    """Run a save, or an undo of an earlier save, with a hostile write at one seam.

    Returns the refusal, the result and the seams where the hostile write fired.
    """
    path = world.path()
    fired: list[str] = []

    def seam(name: str) -> None:
        if name == seam_name and not fired:
            fired.append(name)
            hostile(path, action)

    try:
        if operation == "save":
            world.store.seam = seam
            result: SaveResult | UndoResult = world.save("high", field_name=FIELD)
        else:
            earlier = world.save("high", field_name=FIELD)
            world.store.seam = seam
            result = world.undo(earlier.row_id)
    except Refused as exc:
        return exc, None, fired
    return None, result, fired


def temps(world: World) -> list[str]:
    return [
        p.name
        for p in (world.project / ".claude").iterdir()
        if p.name.startswith(".routing-dashboard-")
    ]


def backups(world: World) -> list[str]:
    return [p.name for p in world.ledger_dir().iterdir() if p.name.endswith(".bak")]


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("seam_name", CHANGED_SEAMS)
def test_a_change_before_the_second_walk_refuses_the_write_and_keeps_the_other_bytes(
    world: World, operation: str, action: str, seam_name: str
) -> None:
    path = world.path()
    err, result, fired = scenario(world, operation, seam_name, action)
    assert fired == [seam_name]
    assert result is None
    assert err is not None
    assert err.code == "changed"
    # their bytes stand, and the writer left nothing behind
    if action == "delete":
        assert not path.exists()
    else:
        assert path.read_text() == THEIRS
    assert temps(world) == []
    kept = 1 if operation == "undo" else 0  # an undo has the earlier save's row
    assert len(world.ledger()) == kept  # the row of the refused write is gone
    assert len(backups(world)) == kept


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("seam_name", RACED_SEAMS)
def test_a_change_after_the_rename_is_raced_and_the_row_says_so(
    world: World, operation: str, action: str, seam_name: str
) -> None:
    path = world.path()
    err, result, fired = scenario(world, operation, seam_name, action)
    assert fired == [seam_name]
    assert result is None
    assert err is not None
    assert err.code == "raced"
    assert err.row_id
    if action == "delete":
        assert not path.exists()
    else:
        assert path.read_text() == THEIRS
    row = next(r for r in world.ledger() if r["id"] == err.row_id)
    assert row["raced"] is True
    # the backup of what was there before our write is kept, so nothing is lost
    assert (world.ledger_dir() / row["backup"]).exists()


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("action", ACTIONS)
def test_the_window_between_the_second_walk_and_the_rename_is_the_one_known_gap(
    world: World, operation: str, action: str
) -> None:
    """Nothing can see a write that lands here, because no rename compares first."""
    path = world.path()
    err, result, fired = scenario(world, operation, "before_rename", action)
    assert fired == ["before_rename"]
    assert err is None
    assert result is not None
    # our bytes replaced theirs, and the row is a plain row with no ``raced`` mark
    assert path.read_text() == (OURS if operation == "save" else OLD)
    row = world.ledger()[-1]
    assert row["id"] == result.row_id
    assert "raced" not in row
    outcome = world.store.run_recheck(world.target(), result.row_id)
    assert outcome is not None
    assert outcome["state"] == "confirmed"
    # the writer kept the bytes it read before the write, in the row's backup
    assert (world.ledger_dir() / row["backup"]).read_bytes() in (
        OLD.encode(),
        OURS.encode(),
    )


def test_a_change_after_the_save_returned_is_overwritten_for_the_recheck(
    world: World,
) -> None:
    saved = world.save("high", field_name=FIELD)
    hostile(world.path(), "replace")
    world.run_timers()
    row = world.ledger()[-1]
    assert row["id"] == saved.row_id
    assert row["recheck"]["state"] == "overwritten"
    assert row["recheck"]["ours_survived"] is False
    assert "model" in row["recheck"]["changed_keys"]


def test_a_change_to_a_different_key_is_overwritten_and_ours_survived(
    world: World,
) -> None:
    saved = world.save("high", field_name=FIELD)
    world.path().write_text(OURS.replace('"NOTE": "a"', '"NOTE": "b"'))
    world.run_timers()
    row = world.ledger()[-1]
    assert row["id"] == saved.row_id
    assert row["recheck"]["state"] == "overwritten"
    assert row["recheck"]["ours_survived"] is True
    assert row["recheck"]["changed_keys"] == ["env.NOTE"]


def test_whatever_the_seam_the_file_is_one_of_the_two_whole_files(
    world: World,
) -> None:
    """A lost race leaves the other program's file or ours, never a mix."""
    path = world.path()
    for seam_name in (*CHANGED_SEAMS, *RACED_SEAMS):
        write_json(path, OLD)
        shutil.rmtree(world.backups, ignore_errors=True)
        err, _result, _fired = scenario(world, "save", seam_name, "replace")
        assert err is not None, seam_name
        assert path.read_text() in (THEIRS, OURS), seam_name
        json.loads(path.read_text())


# The timed run


@pytest.mark.timing
def test_a_writer_that_replaces_the_file_every_20_ms_never_hides_a_lost_update(
    world: World,
) -> None:
    path = world.path()
    stop = threading.Event()
    writes: list[int] = []
    errors: list[BaseException] = []

    def other_program() -> None:
        """Read, change one key and replace the file, as Claude Code does."""
        count = 0
        while not stop.is_set():
            count += 1
            try:
                try:
                    current: dict[str, Any] = json.loads(path.read_text())
                except (OSError, ValueError):
                    current = {}
                current["counter"] = count
                temp = path.with_name("settings.json.other")
                temp.write_text(json.dumps(current, indent=2) + "\n")
                temp.replace(path)
                writes.append(count)
            except OSError as exc:  # pragma: no cover - the test folder is ours alone
                errors.append(exc)
                return
            stop.wait(0.02)

    # The writer's pause in seconds, at the step before its second walk. The mix makes
    # some saves collide with the other program and some not, on any machine.
    pauses = (0.0, 0.005, 0.012, 0.03, 0.0, 0.008, 0.025, 0.002)
    turn = {"n": 0}

    def slow_step(name: str) -> None:
        if name == "after_temp":
            time.sleep(pauses[turn["n"] % len(pauses)])
            turn["n"] += 1

    world.store.seam = slow_step
    outcomes: Counter[str] = Counter()
    saved: list[SaveResult] = []
    deadline = time.monotonic() + timing_policy.wait_limit(30.0)

    def try_save(value: str) -> None:
        refusal: Refused | None = None
        result: SaveResult | None = None
        try:
            result = world.save(value, field_name=FIELD)
        except Refused as exc:
            refusal = exc
        if refusal is not None:
            # A refusal is loud, and these are the ones this race can cause. A
            # ``write_failed`` that holds a row id is a read-back the other program's
            # rename made fail after our rename: the row stays, and Changes shows it.
            kind = (
                "unverified"
                if refusal.code == "write_failed" and refusal.row_id
                else refusal.code
            )
            outcomes[kind] += 1
            assert kind in (*LATE_CODES, "unverified"), (
                refusal.code,
                refusal.params,
            )
            return
        assert result is not None
        outcomes["saved"] += 1
        saved.append(result)
        now = world.store.run_recheck(world.target(), result.row_id)
        assert now is not None
        assert now["state"] in ("confirmed", "overwritten")

    thread = threading.Thread(target=other_program, daemon=True)
    thread.start()
    try:
        for attempt in range(16):
            if time.monotonic() >= deadline:
                break
            try_save(f"m{attempt}")
        # keep trying until one save lands, so the checks below always have a row
        while not saved and time.monotonic() < deadline:
            try_save("late")
    finally:
        stop.set()
        thread.join(5)
    assert errors == []
    assert writes, "the other program never wrote"
    assert saved, f"no save landed in the time allowed: {dict(outcomes)}"
    assert outcomes["changed"] >= 1, dict(outcomes)

    # the file is whole JSON, and the ledger holds one row for each save and each race
    final_text = path.read_text()
    json.loads(final_text)
    rows = world.ledger()
    assert len([r for r in rows if r.get("raced")]) == outcomes["raced"]
    assert len(rows) == len(saved) + outcomes["raced"] + outcomes["unverified"]
    # every backup belongs to a row, and every temp file is gone
    assert set(backups(world)) == {r["backup"] for r in rows}
    assert temps(world) == []

    # with the other program stopped, the recheck tells the truth about every saved row
    for result in saved:
        recheck = world.store.run_recheck(world.target(), result.row_id)
        assert recheck is not None
        row = next(r for r in world.ledger() if r["id"] == result.row_id)
        holds_ours = sha(path.read_bytes()) == row["after_sha256"]
        assert (recheck["state"] == "confirmed") == holds_ours
    last = next(r for r in world.ledger() if r["id"] == saved[-1].row_id)
    if json.loads(final_text).get("model") != last["new_value"]:
        assert last["recheck"]["state"] == "overwritten"
        assert last["recheck"]["ours_survived"] is False
