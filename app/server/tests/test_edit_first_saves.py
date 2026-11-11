# pyright: reportPrivateUsage=false
"""Two first saves at once, to different files (fix round a15).

Task a13 saw two simultaneous first saves to different files in a fresh config folder
fail once with ``write_failed`` and ``ENOENT``. The cause was the temp sweep. Before
every write the writer removed each ``.routing-dashboard-*.tmp`` in the target's folder,
and two files in one folder (``settings.json`` and ``settings.local.json``) each hold
their own target lock, so one save swept the temp file the other had just made and the
other's rename found nothing. The sweep now leaves a temp file that is young, and a
temp file this process is still writing.

These tests run both saves from two or more threads with a barrier, in a fresh
folder each time, so no backups folder exists yet.
"""

import os
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
from edit_helpers import World, make_world

import edit_store
import write_guard
from edit_store import Refused, SaveResult
from models import EditScope

ITERATIONS = int(os.environ.get("BARTAB_FIRST_SAVE_ITERATIONS", "150"))
SCOPES: tuple[EditScope, ...] = ("project", "local")


@pytest.fixture(autouse=True)
def _edits_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(write_guard.STATE, "edits", True)


def fresh_world(root: Path, n: int) -> World:
    """A world with no backups folder and no settings file anywhere."""
    config = root / f"it{n}" / "home" / ".claude"
    project = root / f"it{n}" / "project"
    config.mkdir(parents=True)
    (project / ".claude").mkdir(parents=True)
    return make_world(config.resolve(), project.resolve(), secret=b"s" * 32)


def age(path: Path, seconds: float) -> None:
    """Set a file's mtime ``seconds`` in the past. No test sleeps."""
    stamp = time.time() - seconds
    os.utime(path, (stamp, stamp))


def race(world: World, scopes: tuple[EditScope, ...]) -> list[object]:
    """Save to each scope from its own thread, all released together."""
    bodies = {scope: world.save_body("high", scope) for scope in scopes}
    gate = threading.Barrier(len(scopes))
    outcomes: dict[EditScope, object] = {}

    def run(scope: EditScope) -> None:
        gate.wait()
        try:
            outcomes[scope] = world.store.save(world.target(scope), bodies[scope])
        except Refused as exc:
            outcomes[scope] = exc

    threads = [threading.Thread(target=run, args=(scope,)) for scope in scopes]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return [outcomes[scope] for scope in scopes]


def describe(outcome: object) -> str:
    if isinstance(outcome, Refused):
        return f"{outcome.code} {outcome.params}"
    return "saved"


def test_two_first_saves_in_one_folder_both_succeed(tmp_path: Path) -> None:
    failures: list[str] = []
    for n in range(ITERATIONS):
        world = fresh_world(tmp_path, n)
        assert not world.backups.exists()
        outcomes = race(world, SCOPES)
        bad = [describe(o) for o in outcomes if not isinstance(o, SaveResult)]
        if bad:
            failures.append(f"iteration {n}: {bad}")
        else:
            for scope in SCOPES:
                assert world.path(scope).is_file()
                assert len(world.ledger(scope)) == 1
            assert not [
                p.name
                for p in (world.project / ".claude").iterdir()
                if p.name.startswith(".routing-dashboard-")
            ]
    assert failures == []


def test_a_first_save_to_user_and_project_settings_both_succeed(tmp_path: Path) -> None:
    failures: list[str] = []
    for n in range(ITERATIONS):
        world = fresh_world(tmp_path, n)
        scopes: tuple[EditScope, ...] = ("user", "project", "local")
        outcomes = race(world, scopes)
        bad = [describe(o) for o in outcomes if not isinstance(o, SaveResult)]
        if bad:
            failures.append(f"iteration {n}: {bad}")
    assert failures == []


def test_a_save_leaves_the_temp_file_of_a_save_still_in_flight(tmp_path: Path) -> None:
    world = fresh_world(tmp_path, 0)
    other = world.project / ".claude" / ".routing-dashboard-0123456789abcdef.tmp"
    other.write_text("{}", encoding="utf-8")
    # Old enough to sweep, so only the registry keeps it.
    age(other, 61)
    with edit_store._LIVE_TEMPS_LOCK:
        edit_store._LIVE_TEMPS.add(other.name)
    try:
        world.save("high", "project")
        assert other.exists()
    finally:
        with edit_store._LIVE_TEMPS_LOCK:
            edit_store._LIVE_TEMPS.discard(other.name)


def test_a_save_still_sweeps_a_temp_file_nobody_is_using(tmp_path: Path) -> None:
    world = fresh_world(tmp_path, 0)
    stale = world.project / ".claude" / ".routing-dashboard-0123456789abcdef.tmp"
    stale.write_text("{}", encoding="utf-8")
    age(stale, 61)
    world.save("high", "project")
    assert not stale.exists()


def test_a_fresh_temp_file_from_another_process_survives_a_save(tmp_path: Path) -> None:
    # The old app writes the same temp names. A file it made a moment ago has no entry
    # in this process's registry, so only its age protects it from the sweep.
    world = fresh_world(tmp_path, 0)
    other = world.project / ".claude" / ".routing-dashboard-fedcba9876543210.tmp"
    other.write_text("{}", encoding="utf-8")
    world.save("high", "project")
    assert other.read_text(encoding="utf-8") == "{}"


def test_the_sweep_takes_a_temp_file_over_60_seconds_old_and_keeps_a_younger_one(
    tmp_path: Path,
) -> None:
    world = fresh_world(tmp_path, 0)
    folder = world.project / ".claude"
    young = folder / ".routing-dashboard-fedcba9876543210.tmp"
    stale = folder / ".routing-dashboard-0123456789abcdef.tmp"
    for item, seconds in ((young, 30), (stale, 61)):
        item.write_text("{}", encoding="utf-8")
        age(item, seconds)
    world.save("high", "project")
    assert young.exists()
    assert not stale.exists()


def test_no_temp_name_stays_registered_after_a_save_or_a_refusal(
    tmp_path: Path,
) -> None:
    world = fresh_world(tmp_path, 0)
    world.save("high", "project")
    body = world.save_body("low", "project")
    world.path("project").write_text("{}\n", encoding="utf-8")  # a change under it
    with pytest.raises(Refused):
        world.store.save(world.target("project"), body)
    assert not edit_store._LIVE_TEMPS
