"""Tests for the edit side of write_guard.py: ``permit`` and the ``dir_fd`` rules.

An audit hook can't be removed, so the hook runs only in subprocesses that start
``sys.executable`` with the server folder on ``sys.path`` and a temp HOME. The
in-process tests never install the hook. They set ``write_guard.STATE.edits`` for the
test and call ``permit`` and the check functions directly.

The three refusals the plan names (m6-build.md section 3.5) are cases here: a rename by
``dir_fd`` into a folder the permit doesn't hold, a bare-name write under an fd for an
outside folder, and a relative write ``open``.
"""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

import write_guard as wg

SERVER_DIR = Path(__file__).resolve().parents[1]
TEMP = ".routing-dashboard-0123456789abcdef.tmp"
BAD_TEMP = ".routing-dashboard-0123456789abcde.tmp"

# Each case runs in the child after install. R is the store root, X the backups root,
# O a folder outside every root, P a project's .claude folder (not a root), Q another
# outside folder that holds a settings.json, and N a project folder with no .claude
# agents folder. dirfd(path) opens a folder for reading, which is always allowed.
ALLOWED = {
    "permit_atomic_write": (
        "T = P + '/settings.json'\n"
        "with write_guard.permit(T) as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        f"    w = os.open(P + '/{TEMP}',"
        " os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)\n"
        "    os.write(w, b'{}')\n"
        "    os.close(w)\n"
        f"    os.rename('{TEMP}', 'settings.json', src_dir_fd=fd, dst_dir_fd=fd)\n"
        "    os.close(fd)\n"
        "assert open(T).read() == '{}'"
    ),
    "permit_remove_temp_by_fd": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        f"    w = os.open(P + '/{TEMP}', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "    os.close(w)\n"
        f"    os.remove('{TEMP}', dir_fd=fd)\n"
        "    os.close(fd)"
    ),
    "permit_chmod_temp_by_fd": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        f"    w = os.open(P + '/{TEMP}', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "    os.close(w)\n"
        f"    os.chmod('{TEMP}', 0o600, dir_fd=fd)\n"
        f"    os.remove(P + '/{TEMP}')\n"
        "    os.close(fd)"
    ),
    "permit_create_with_make_dir": (
        "T = N + '/agents/new.md'\n"
        "D = N + '/agents'\n"
        "with write_guard.permit(T, make_dir=D) as pm:\n"
        "    pfd = dirfd(N)\n"
        "    pm.bind_parent(pfd)\n"
        "    os.mkdir('agents', dir_fd=pfd)\n"
        "    ffd = dirfd(D)\n"
        "    pm.bind_folder(ffd)\n"
        "    w = os.open(T, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "    os.close(w)\n"
        "    os.remove('new.md', dir_fd=ffd)\n"
        "    os.rmdir('agents', dir_fd=pfd)\n"
        "    os.close(ffd)\n"
        "    os.close(pfd)\n"
        "assert not os.path.exists(D)"
    ),
    "permit_target_by_absolute_path": (
        "with write_guard.permit(P + '/settings.json'):\n"
        "    open(P + '/settings.json', 'w').close()"
    ),
    "bare_name_under_a_store_folder_fd": (
        "fd = dirfd(R + '/sub')\n"
        "os.mkdir('made', dir_fd=fd)\n"
        "os.rename('made', 'moved', src_dir_fd=fd, dst_dir_fd=fd)\n"
        "os.rmdir('moved', dir_fd=fd)\n"
        "os.close(fd)"
    ),
    "bare_name_under_a_backups_folder_fd": (
        "fd = dirfd(X + '/ledger')\n"
        "os.mkdir('made', dir_fd=fd)\n"
        "os.rmdir('made', dir_fd=fd)\n"
        "os.close(fd)"
    ),
    "absolute_write_in_a_root": 'open(R + "/w.txt", "w").close()',
    "absolute_write_in_the_backups_root": 'open(X + "/e.txt", "w").close()',
    "read_outside": 'open(O + "/b.txt").read()',
}
REFUSED = {
    "rename_by_dir_fd_into_a_folder_the_permit_does_not_hold": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        f"    w = os.open(P + '/{TEMP}', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)\n"
        "    os.close(w)\n"
        "    qfd = dirfd(Q)\n"
        "    try:\n"
        f"        os.rename('{TEMP}', 'settings.json', src_dir_fd=fd, dst_dir_fd=qfd)\n"
        "    finally:\n"
        f"        os.remove(P + '/{TEMP}')"
    ),
    "rename_by_dir_fd_with_no_permit": (
        "fd = dirfd(O)\nos.rename('b.txt', 'c.txt', src_dir_fd=fd, dst_dir_fd=fd)"
    ),
    "bare_name_mkdir_under_an_outside_fd": ("fd = dirfd(O)\nos.mkdir('nd', dir_fd=fd)"),
    "bare_name_remove_under_an_outside_fd": (
        "fd = dirfd(O)\nos.remove('b.txt', dir_fd=fd)"
    ),
    "bare_name_rmdir_under_an_outside_fd": (
        "fd = dirfd(O)\nos.rmdir('o_rm', dir_fd=fd)"
    ),
    "bare_name_chmod_under_an_outside_fd": (
        "fd = dirfd(O)\nos.chmod('b.txt', 0o644, dir_fd=fd)"
    ),
    "bare_name_write_open_under_an_outside_fd": (
        "fd = dirfd(O)\nos.open('new.txt', os.O_WRONLY | os.O_CREAT, 0o600, dir_fd=fd)"
    ),
    "relative_write_open_in_a_root": (
        "cwd = os.getcwd(); os.chdir(R)\n"
        "try:\n"
        "    open('rel.txt', 'w')\n"
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "relative_write_os_open_in_a_root": (
        "cwd = os.getcwd(); os.chdir(R)\n"
        "try:\n"
        "    os.open('rel2.txt', os.O_WRONLY | os.O_CREAT, 0o600)\n"
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "relative_write_open_of_the_permitted_target": (
        "cwd = os.getcwd(); os.chdir(P)\n"
        "try:\n"
        "    with write_guard.permit(P + '/settings.json'):\n"
        "        open('settings.json', 'w')\n"
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "absolute_write_outside": 'open(O + "/nw.txt", "w")',
    "another_file_in_the_permitted_folder": (
        "with write_guard.permit(P + '/settings.json'):\n"
        "    open(P + '/other.json', 'w')"
    ),
    "a_misnamed_temp_file": (
        "with write_guard.permit(P + '/settings.json'):\n"
        f"    open(P + '/{BAD_TEMP}', 'w')"
    ),
    "a_temp_file_in_another_folder": (
        f"with write_guard.permit(P + '/settings.json'):\n    open(Q + '/{TEMP}', 'w')"
    ),
    "a_misnamed_bare_name_in_the_held_folder": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        "    os.remove('other.json', dir_fd=fd)"
    ),
    "a_bad_temp_bare_name_in_the_held_folder": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        f"    os.mkdir('{BAD_TEMP}', dir_fd=fd)"
    ),
    "a_path_with_a_separator_under_a_held_fd": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        "    os.mkdir('sub/settings.json', dir_fd=fd)"
    ),
    "a_dotdot_name_under_a_held_fd": (
        "with write_guard.permit(P + '/settings.json') as pm:\n"
        "    fd = dirfd(P)\n"
        "    pm.bind_folder(fd)\n"
        "    os.rename('..', 'settings.json', src_dir_fd=fd, dst_dir_fd=fd)"
    ),
    "the_target_after_the_permit_ends": (
        "with write_guard.permit(P + '/settings.json'):\n"
        "    pass\n"
        "open(P + '/settings.json', 'w')"
    ),
    "the_target_from_another_thread": (
        "box = []\n"
        "def other():\n"
        "    try:\n"
        "        open(P + '/settings.json', 'w')\n"
        "    except PermissionError as exc:\n"
        "        box.append(exc)\n"
        "with write_guard.permit(P + '/settings.json'):\n"
        "    t = threading.Thread(target=other)\n"
        "    t.start()\n"
        "    t.join()\n"
        "raise box[0]"
    ),
    "a_folder_swapped_for_a_link_after_the_bind": (
        "with write_guard.permit(S + '/f/settings.json') as pm:\n"
        "    pm.bind_folder(dirfd(S + '/f'))\n"
        "    subprocess.run(['/bin/mv', S + '/f', S + '/f.old'], check=True)\n"
        "    subprocess.run(['/bin/ln', '-s', Q, S + '/f'], check=True)\n"
        "    fd = dirfd(S + '/f')\n"
        "    os.rename('settings.json', 'settings.json', src_dir_fd=fd, dst_dir_fd=fd)"
    ),
    "make_dir_in_a_parent_the_permit_does_not_hold": (
        "with write_guard.permit(N + '/agents/new.md', make_dir=N + '/agents') as pm:\n"
        "    pm.bind_parent(dirfd(N))\n"
        "    os.mkdir('agents', dir_fd=dirfd(O))"
    ),
    "make_dir_of_another_name": (
        "with write_guard.permit(N + '/agents/new.md', make_dir=N + '/agents') as pm:\n"
        "    pfd = dirfd(N)\n"
        "    pm.bind_parent(pfd)\n"
        "    os.mkdir('skills', dir_fd=pfd)"
    ),
    "a_second_folder_by_absolute_path": (
        "with write_guard.permit(N + '/agents/new.md', make_dir=N + '/agents'):\n"
        "    os.mkdir(N + '/skills')"
    ),
    "a_root_name_that_only_starts_like_a_root": ("open(R + '-twin/w.txt', 'w')"),
    "dotdot_out_of_a_root": 'open(R + "/../" + os.path.basename(O) + "/dd.txt", "w")',
    "a_store_folder_link_out": ("fd = dirfd(R + '/link')\nos.mkdir('nd', dir_fd=fd)"),
}

SETUP = """
os.makedirs(R + "/sub")
os.makedirs(R + "-twin")
os.makedirs(X + "/ledger")
os.makedirs(O + "/o_rm")
open(O + "/b.txt", "w").write("x")
os.makedirs(P)
open(P + "/settings.json", "w").write("old")
open(Q + "/settings.json", "w").write("other")
os.makedirs(N)
os.makedirs(S + "/f")
open(S + "/f/settings.json", "w").write("x")
os.symlink(O, R + "/link")
"""

CHILD = """
import json, os, pathlib, subprocess, sys, threading
sys.path.insert(0, {server!r})
import write_guard
R, X, O, P, Q, N, S = {folders!r}
{setup}
write_guard.install(pathlib.Path(R), [pathlib.Path(X)], edits={edits!r})
def dirfd(path):
    return os.open(path, os.O_RDONLY | os.O_DIRECTORY)
cases = {cases!r}
results = {{}}
for name, code in cases.items():
    try:
        exec(code, globals())
    except PermissionError as exc:
        results[name] = "refused: " + str(exc)
    except Exception as exc:
        results[name] = "error: " + type(exc).__name__ + " " + str(exc)
    else:
        results[name] = "ok"
sys.stdout.write(json.dumps(results))
"""


def child_env(home: Path) -> dict[str, str]:
    """An explicit environment. HOME is a temp folder, never the real one."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "PYTHONDONTWRITEBYTECODE": "1",
        "LANG": "C",
    }


def run_child(script: str, home: Path) -> subprocess.CompletedProcess[str]:
    """Run a child Python with the server folder on sys.path."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        env=child_env(home),
        timeout=120,
        check=False,
    )


class World:
    """The folders the child works in, all in one temp tree."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "store"
        self.backups = base / "backups"
        self.outside = base / "outside"
        self.project = base / "project" / ".claude"
        self.other = base / "other"
        self.bare = base / "bare-project"
        self.swap = base / "swap"
        self.home = base / "home"
        self.home.mkdir(parents=True)
        for folder in (self.root.parent, self.other):
            folder.mkdir(parents=True, exist_ok=True)

    @property
    def folders(self) -> list[str]:
        return [
            str(p)
            for p in (
                self.root,
                self.backups,
                self.outside,
                self.project,
                self.other,
                self.bare,
                self.swap,
            )
        ]


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    return World(tmp_path_factory.mktemp("edit-guard").resolve())


@pytest.fixture(scope="module")
def results(world: World) -> dict[str, str]:
    """Run every case once in one child and return {case name: outcome}."""
    script = CHILD.format(
        server=str(SERVER_DIR),
        folders=world.folders,
        setup=SETUP,
        edits=True,
        cases={**ALLOWED, **REFUSED},
    )
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# The hook in a subprocess, edits on


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_permitted_and_in_root_work_succeeds(
    results: dict[str, str], name: str
) -> None:
    assert results[name] == "ok"


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_everything_else_is_refused(results: dict[str, str], name: str) -> None:
    assert results[name].startswith("refused: [Errno 1] write refused ("), results[name]


def test_the_three_refusals_the_plan_names_are_among_the_cases() -> None:
    assert "rename_by_dir_fd_into_a_folder_the_permit_does_not_hold" in REFUSED
    assert "bare_name_mkdir_under_an_outside_fd" in REFUSED
    assert "relative_write_open_in_a_root" in REFUSED


def test_no_case_was_dropped(results: dict[str, str]) -> None:
    assert set(results) == set(ALLOWED) | set(REFUSED)


def test_a_refused_case_changed_nothing_outside(
    world: World, results: dict[str, str]
) -> None:
    assert results
    assert (world.outside / "b.txt").read_text() == "x"
    assert (world.other / "settings.json").read_text() == "other"
    assert not (world.outside / "nd").exists()
    assert not (world.outside / "new.txt").exists()
    assert not (world.outside / "c.txt").exists()
    assert not (world.outside / "nw.txt").exists()
    assert not (world.root / "rel.txt").exists()
    assert not (world.root / "rel2.txt").exists()
    assert not (world.project / "other.json").exists()
    assert not (world.project / BAD_TEMP).exists()
    assert not (world.other / TEMP).exists()
    assert not (world.bare / "skills").exists()
    assert not (world.root.parent / "store-twin" / "w.txt").exists()


def test_permitted_writes_landed_where_the_permit_named(
    world: World, results: dict[str, str]
) -> None:
    assert results["permit_atomic_write"] == "ok"
    assert (world.project / "settings.json").is_file()
    assert not (world.project / TEMP).exists()


def test_a_refusal_names_a_code_and_never_a_path(world: World) -> None:
    script = f"""
import os, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
write_guard.install(__import__("pathlib").Path({str(world.root)!r}), edits=True)
fd = os.open({str(world.outside)!r}, os.O_RDONLY | os.O_DIRECTORY)
try:
    os.mkdir("secret-folder-name", dir_fd=fd)
except PermissionError as exc:
    sys.stdout.write(repr(str(exc)))
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "'[Errno 1] write refused (mkdir)'"
    assert "secret-folder-name" not in proc.stdout + proc.stderr
    assert str(world.outside) not in proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Edits off: permit raises, and the old rules stay


def test_permit_raises_in_a_child_installed_without_edits(world: World) -> None:
    script = CHILD.format(
        server=str(SERVER_DIR),
        folders=world.folders,
        setup='os.makedirs(R + "/sub", exist_ok=True)',
        edits=False,
        cases={
            "permit": "with write_guard.permit(P + '/settings.json'): pass",
            "bare_name_under_an_fd_stays_allowed_with_edits_off": (
                "fd = dirfd(R + '/sub'); os.mkdir('off-made', dir_fd=fd)"
            ),
            "relative_open_in_a_root_stays_allowed_with_edits_off": (
                "cwd = os.getcwd(); os.chdir(R)\n"
                "try:\n"
                "    open('rel-off.txt', 'w').close()\n"
                "finally:\n"
                "    os.chdir(cwd)"
            ),
        },
    )
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    found = json.loads(proc.stdout)
    assert found["permit"] == "refused: [Errno 1] edits are off"
    assert found["bare_name_under_an_fd_stays_allowed_with_edits_off"] == "ok"
    assert found["relative_open_in_a_root_stays_allowed_with_edits_off"] == "ok"


def test_a_second_install_with_another_mode_raises(world: World) -> None:
    script = f"""
import pathlib, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
root = pathlib.Path({str(world.root)!r})
write_guard.install(root)
write_guard.install(root)
try:
    write_guard.install(root, edits=True)
except RuntimeError:
    sys.stdout.write("raised")
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "raised"


def test_permit_raises_in_this_process_with_edits_off() -> None:
    assert wg.STATE.edits is False
    with pytest.raises(PermissionError), wg.permit("/work/cfg/settings.json"):
        pytest.fail("the permit must not open")


# --------------------------------------------------------------------------
# In process, no hook: the permit's own rules


@pytest.fixture
def edits_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make ``permit`` work in this process without installing the hook."""
    monkeypatch.setattr(wg.STATE, "edits", True)
    yield
    assert wg._current() is None  # pyright: ignore[reportPrivateUsage]


@pytest.mark.usefixtures("edits_on")
def test_a_permit_needs_absolute_paths() -> None:
    with pytest.raises(ValueError, match="absolute"), wg.permit("settings.json"):
        pytest.fail("the permit must not open")
    with (
        pytest.raises(ValueError, match="absolute"),
        wg.permit("/work/cfg/a.md", make_dir="agents"),
    ):
        pytest.fail("the permit must not open")


@pytest.mark.usefixtures("edits_on")
def test_permits_do_not_nest_and_clear_on_exit_and_on_error() -> None:
    with wg.permit("/work/cfg/settings.json"):
        with pytest.raises(RuntimeError), wg.permit("/work/cfg/other.json"):
            pytest.fail("the permit must not open")
        assert wg._current() is not None  # pyright: ignore[reportPrivateUsage]
    assert wg._current() is None  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(KeyError), wg.permit("/work/cfg/settings.json"):
        raise KeyError
    assert wg._current() is None  # pyright: ignore[reportPrivateUsage]


@pytest.mark.usefixtures("edits_on")
def test_the_permit_is_thread_local() -> None:
    import threading

    seen: list[object] = []
    with wg.permit("/work/cfg/settings.json"):
        worker = threading.Thread(target=lambda: seen.append(wg._current()))  # pyright: ignore[reportPrivateUsage]
        worker.start()
        worker.join()
    assert seen == [None]


@pytest.mark.usefixtures("edits_on")
def test_the_permit_resolves_a_link_at_the_leaf(tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    real.write_text("{}")
    link = tmp_path / "link.json"
    link.symlink_to(real)
    with wg.permit(link) as held:
        assert held.target == os.path.realpath(real)
        assert held.allows_path(os.path.realpath(real))


@pytest.mark.usefixtures("edits_on")
def test_folder_binding_is_by_identity_not_by_name(tmp_path: Path) -> None:
    mine = tmp_path / "mine"
    other = tmp_path / "other"
    mine.mkdir()
    other.mkdir()
    with wg.permit(mine / "settings.json") as held:
        fd = os.open(mine, os.O_RDONLY | os.O_DIRECTORY)
        other_fd = os.open(other, os.O_RDONLY | os.O_DIRECTORY)
        try:
            held.bind_folder(fd)
            mine_id = wg._identity(fd)  # pyright: ignore[reportPrivateUsage]
            other_id = wg._identity(other_fd)  # pyright: ignore[reportPrivateUsage]
            assert mine_id is not None
            assert other_id is not None
            assert held.allows_name(mine_id, "settings.json")
            assert held.allows_name(mine_id, TEMP)
            assert not held.allows_name(mine_id, "other.json")
            assert not held.allows_name(mine_id, BAD_TEMP)
            assert not held.allows_name(other_id, "settings.json")
        finally:
            os.close(fd)
            os.close(other_fd)


@pytest.mark.usefixtures("edits_on")
def test_bind_refuses_a_file_and_a_permit_with_no_made_folder(tmp_path: Path) -> None:
    plain = tmp_path / "file.txt"
    plain.write_text("x")
    with wg.permit(tmp_path / "settings.json") as held:
        fd = os.open(plain, os.O_RDONLY)
        folder = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with pytest.raises(NotADirectoryError):
                held.bind_folder(fd)
            with pytest.raises(NotADirectoryError):
                held.bind_parent(folder)
        finally:
            os.close(fd)
            os.close(folder)
