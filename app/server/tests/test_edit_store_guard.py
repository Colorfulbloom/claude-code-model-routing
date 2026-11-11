"""A full save under the real write guard, in a subprocess (m6-build.md 3.5, 3.10).

An audit hook can't be removed, so the hook runs only in a child that installs it with
edits on, and whose HOME is a temp folder. The child makes a writer and runs a replace,
a create (which makes ``.claude``), an undo of each (which removes it again), a save
through a link, a user-scope save and the rechecks. Every one has to pass the hook with
nothing but the permit and the ``dir_fd`` flow of the writer. The child also checks that
a plain write to the same folder, outside any permit, is still refused.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]

CHILD = r"""
import json, os, pathlib, subprocess, sys

sys.path.insert(0, sys.argv[1])
folders = json.loads(sys.argv[2])
import write_guard, edit_store
from models import EditPreviewRequest, EditSaveRequest, EditUndoRequest

CONFIG, PROJECT, BARE, HOME = (pathlib.Path(p) for p in folders)
store_root = CONFIG / "routing-dashboard" / "bartab"
backups = CONFIG / "routing-dashboard" / "backups"
store_root.mkdir(parents=True)
write_guard.install(store_root, [backups], edits=True)

ctx = edit_store.EditContext(config_dir=CONFIG, home=HOME)
timers = []
store = edit_store.EditStore(ctx, scheduler=lambda delay, work: timers.append(work))
results = {}
counter = [0]


def rid():
    counter[0] += 1
    return "request-%04d" % counter[0]


def preview(scope, field, value):
    return EditPreviewRequest.model_validate(
        {"project": "p", "op": "set", "scope": scope, "field": field,
         "value": value, "seq": 1}
    )


def save(project, scope, field, value, key_path=None):
    target = edit_store.settings_target(ctx, project, scope)
    token = store.make_version(store.inspect(target), preview(scope, field, value))
    body = EditSaveRequest.model_validate(
        {"project": "p", "op": "set", "scope": scope, "field": field, "value": value,
         "seq": 2, "version": token, "request_id": rid()}
    )
    return store.save(target, body, key_path=key_path)


def undo(project, row_id):
    body = EditUndoRequest.model_validate(
        {"project": "p", "row_id": row_id, "request_id": rid(), "anyway": False}
    )
    return store.undo(edit_store.settings_targets(ctx, project), "p", body)


def step(name, work):
    try:
        work()
    except Exception as exc:
        results[name] = type(exc).__name__ + ": " + str(exc)
    else:
        results[name] = "ok"


def plain_write_is_refused():
    try:
        open(PROJECT / ".claude" / "other.txt", "w")
    except PermissionError:
        return
    raise AssertionError("a write outside a permit was allowed")


def replace_in_existing_file():
    row = save(PROJECT, "project", "effortLevel", "high").row
    assert row["op"] == "insert"
    state["replace"] = row["id"]


def create_makes_the_folder():
    row = save(BARE, "project", "effortLevel", "low").row
    assert row["made_dir"] is True
    state["create"] = row["id"]


def undo_of_the_create_removes_the_folder():
    done = undo(BARE, state["create"])
    assert done.removed_file and done.removed_dir
    assert not (BARE / ".claude").exists()


def undo_of_the_replace():
    undo(PROJECT, state["replace"])


def save_through_a_link():
    real = HOME / "dotfiles" / "settings.json"
    link = PROJECT / ".claude" / "settings.local.json"
    assert link.is_symlink()
    save(PROJECT, "local", "effortLevel", "high")
    assert link.is_symlink()
    assert '"high"' in real.read_text()


def user_scope():
    save(PROJECT, "user", "model", "sonnet")


def rechecks_write_the_ledger():
    for work in timers:
        work()
    assert timers


def a_swapped_folder_is_refused_and_nothing_leaks():
    seen = []
    target = edit_store.settings_target(ctx, PROJECT, "project")

    def seam(name):
        if name == "before_recheck":
            # another program, not this one, so the hook doesn't see it
            folder, aside = str(PROJECT / ".claude"), str(PROJECT / ".claude-aside")
            subprocess.run(["/bin/mv", folder, aside], check=True)
            subprocess.run(["/bin/ln", "-s", aside, folder], check=True)

    store.seam = seam
    try:
        save(PROJECT, "project", "effortLevel", "xhigh")
    except edit_store.Refused as exc:
        seen.append(exc.code)
    finally:
        store.seam = None
    assert seen == ["changed"], seen


state = {}
step("a plain write outside a permit is refused", plain_write_is_refused)
step("replace in an existing file", replace_in_existing_file)
step("create makes the folder", create_makes_the_folder)
step("undo of the create removes the folder", undo_of_the_create_removes_the_folder)
step("undo of the replace", undo_of_the_replace)
step("save through a link", save_through_a_link)
step("user scope", user_scope)
step("rechecks write the ledger", rechecks_write_the_ledger)
step("a swapped folder is refused", a_swapped_folder_is_refused_and_nothing_leaks)
sys.stdout.write(json.dumps(results))
"""


def run_child(base: Path) -> dict[str, str]:
    """Run the child in a throwaway HOME and return its step results."""
    home = base / "home"
    config = home / ".claude"
    project = base / "project"
    bare = base / "bare"
    (project / ".claude").mkdir(parents=True)
    (project / ".claude" / "settings.json").write_text('{"model": "opus"}\n')
    bare.mkdir()
    home.mkdir(exist_ok=True)
    (home / "dotfiles").mkdir()
    (home / "dotfiles" / "settings.json").write_text('{"effortLevel": "low"}\n')
    (project / ".claude" / "settings.local.json").symlink_to(
        home / "dotfiles" / "settings.json"
    )
    folders = [str(p.resolve()) for p in (config, project, bare, home)]
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C",
    }
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", CHILD, str(SERVER_DIR), json.dumps(folders)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_full_save_passes_the_real_write_guard(edit_config: Path) -> None:
    base = edit_config.parent.parent / "guard-run"
    base.mkdir()
    results = run_child(base)
    assert {name: out for name, out in results.items() if out != "ok"} == {}
    assert len(results) == 9
    assert (base / "project" / ".claude" / "settings.json").read_text() == (
        '{"model": "opus"}\n'
    )
    assert not (base / "bare" / ".claude").exists()
    assert (base / "project" / ".claude-aside" / "settings.json").is_file()
    backups = base / "home" / ".claude" / "routing-dashboard" / "backups"
    folders = [p for p in backups.iterdir() if p.is_dir()]
    assert len(folders) >= 4
    assert all((p / "ledger.json").is_file() for p in folders)
    user = json.loads((base / "home" / ".claude" / "settings.json").read_text())
    assert user == {"model": "sonnet"}
    leaked = [
        p.name
        for p in (base / "project" / ".claude-aside").iterdir()
        if p.name.startswith(".routing-dashboard-")
    ]
    assert leaked == []
    assert os.environ.get("HOME") != str(base / "home")
