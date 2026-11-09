"""Tests for write_guard.py, the runtime write guard.

An audit hook can't be removed, so the hook itself runs only in subprocesses that
start ``sys.executable`` with the server folder on ``sys.path`` and an explicit
environment with a temp HOME. The in-process tests call the check functions
directly with the allowed roots patched in, and never install the hook.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

import write_guard as wg

SERVER_DIR = Path(__file__).resolve().parents[1]

# Each case runs in the child after install. R is the store root, X an extra root and
# O a folder outside both. The child makes the files below before it installs.
ALLOWED = {
    "write_inside": 'open(R + "/w.txt", "w").close()',
    "append_inside": 'open(R + "/a.txt", "a").close()',
    "read_write_inside": 'open(R + "/a.txt", "r+").close()',
    "binary_inside": 'open(R + "/wb.bin", "wb").close()',
    "exclusive_inside": 'open(R + "/x.txt", "x").close()',
    "os_open_inside": (
        "os.close(os.open(R + '/o.txt', os.O_CREAT | os.O_WRONLY, 0o600))"
    ),
    "pathlib_inside": 'pathlib.Path(R, "p.txt").write_text("x")',
    "extra_root": 'open(X + "/e.txt", "w").close()',
    "dev_null": "open(os.devnull, 'w').close()",
    "read_outside": 'open(O + "/b.txt").read()',
    "read_outside_binary": 'open(O + "/b.txt", "rb").read()',
    "os_open_read_outside": "os.close(os.open(O + '/b.txt', os.O_RDONLY))",
    "list_and_stat_outside": 'os.listdir(O); os.stat(O + "/b.txt")',
    "pathlib_read_outside": 'pathlib.Path(O, "b.txt").read_text()',
    "mkdir_inside": 'os.mkdir(R + "/nd")',
    "makedirs_inside": 'os.makedirs(R + "/n1/n2/n3")',
    "rename_inside": 'open(R + "/r1", "w").close(); os.rename(R + "/r1", R + "/r2")',
    "replace_inside": 'open(R + "/r3", "w").close(); os.replace(R + "/r3", R + "/r4")',
    "remove_inside": 'open(R + "/r5", "w").close(); os.remove(R + "/r5")',
    "unlink_inside": 'open(R + "/r6", "w").close(); os.unlink(R + "/r6")',
    "rmdir_inside": 'os.mkdir(R + "/rd"); os.rmdir(R + "/rd")',
    "chmod_inside": 'os.chmod(R + "/a.txt", 0o600)',
    "truncate_inside": 'os.truncate(R + "/a.txt", 0)',
    "ftruncate_fd": (
        'fd = os.open(R + "/a.txt", os.O_RDWR); os.ftruncate(fd, 0); os.close(fd)'
    ),
    "copyfile_into_root": 'shutil.copyfile(O + "/b.txt", R + "/cf")',
    "copy_into_root": 'shutil.copy(O + "/b.txt", R + "/cp")',
    "copy2_into_root": 'shutil.copy2(O + "/b.txt", R + "/cp2")',
    "copytree_into_root": 'shutil.copytree(O + "/o_tree", R + "/ct")',
    "move_inside": (
        'open(R + "/mv_a", "w").close(); shutil.move(R + "/mv_a", R + "/mv_b")'
    ),
    "rmtree_inside": 'os.makedirs(R + "/rt/sub"); shutil.rmtree(R + "/rt")',
    "sqlite_memory": 'sqlite3.connect(":memory:").close()',
    "sqlite_file_inside": 'sqlite3.connect(R + "/s.db").close()',
    "sqlite_path_inside": 'sqlite3.connect(pathlib.Path(R, "s2.db")).close()',
    "sqlite_uri_inside": (
        'sqlite3.connect("file:" + urllib.parse.quote(R + "/u.db") + "?mode=rwc",'
        " uri=True).close()"
    ),
    "mkstemp_inside": "os.close(tempfile.mkstemp(dir=R)[0])",
    "named_temp_inside": "tempfile.NamedTemporaryFile(dir=R).close()",
    "relative_inside": (
        "cwd = os.getcwd(); os.chdir(R)\n"
        "try:\n"
        '    open("rel.txt", "w").close()\n'
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "symlink_dst_inside": 'os.symlink(O + "/b.txt", R + "/newlink")',
    "unix_socket_inside": (
        "cwd = os.getcwd(); os.chdir(R)\n"
        "try:\n"
        "    s = socket.socket(socket.AF_UNIX)\n"
        '    s.bind("s.sock")\n'
        "    s.close()\n"
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "tcp_bind": 's = socket.socket(); s.bind(("127.0.0.1", 0)); s.close()',
    "utime_inside": 'os.utime(R + "/a.txt", None)',
}
REFUSED = {
    "open_write": 'open(O + "/nw.txt", "w")',
    "open_append": 'open(O + "/b.txt", "a")',
    "open_exclusive": 'open(O + "/nx.txt", "x")',
    "open_read_write": 'open(O + "/b.txt", "r+")',
    "open_binary_write": 'open(O + "/nb.bin", "wb")',
    "os_open_create": "os.open(O + '/nc.txt', os.O_CREAT | os.O_RDONLY)",
    "os_open_write_only": "os.open(O + '/b.txt', os.O_WRONLY)",
    "os_open_read_write": "os.open(O + '/b.txt', os.O_RDWR)",
    "os_open_truncate": "os.open(O + '/b.txt', os.O_RDONLY | os.O_TRUNC)",
    "os_open_append": "os.open(O + '/b.txt', os.O_WRONLY | os.O_APPEND)",
    "pathlib_write": 'pathlib.Path(O, "pw.txt").write_text("x")',
    "mkstemp_outside": "tempfile.mkstemp(dir=O)",
    "relative_outside": (
        "cwd = os.getcwd(); os.chdir(O)\n"
        "try:\n"
        '    open("rel.txt", "w")\n'
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "dotdot_escape": 'open(R + "/../" + os.path.basename(O) + "/dd.txt", "w")',
    "symlink_dir_escape": 'open(R + "/link/sl.txt", "w")',
    "symlink_file_escape": 'open(R + "/flink", "w")',
    "symlink_file_remove": 'os.remove(R + "/flink")',
    "symlink_dir_mkdir": 'os.mkdir(R + "/link/nd")',
    "rename_dst_outside": (
        'open(R + "/rn1", "w").close(); os.rename(R + "/rn1", O + "/rn1")'
    ),
    "rename_src_outside": 'os.rename(O + "/src1", R + "/src1")',
    "replace_dst_outside": (
        'open(R + "/rp1", "w").close(); os.replace(R + "/rp1", O + "/rp1")'
    ),
    "replace_src_outside": 'os.replace(O + "/src2", R + "/src2")',
    "remove_outside": 'os.remove(O + "/b3.txt")',
    "unlink_outside": 'os.unlink(O + "/b4.txt")',
    "mkdir_outside": 'os.mkdir(O + "/nd")',
    "makedirs_outside": 'os.makedirs(O + "/n1/n2")',
    "rmdir_outside": 'os.rmdir(O + "/o_rm")',
    "chmod_outside": 'os.chmod(O + "/b.txt", 0o644)',
    "truncate_outside": 'os.truncate(O + "/b.txt", 0)',
    "copyfile_outside": 'shutil.copyfile(R + "/a.txt", O + "/cf")',
    "copy_outside": 'shutil.copy(R + "/a.txt", O + "/cp")',
    "copy2_outside": 'shutil.copy2(R + "/a.txt", O + "/cp2")',
    "copymode_outside": 'shutil.copymode(R + "/a.txt", O + "/b.txt")',
    "copystat_outside": 'shutil.copystat(R + "/a.txt", O + "/b.txt")',
    "copytree_outside": 'shutil.copytree(R + "/tree", O + "/ct")',
    "move_dst_outside": 'shutil.move(R + "/tree", O + "/mv")',
    "move_src_outside": 'shutil.move(O + "/mv_o", R + "/mv_in")',
    "rmtree_outside": 'shutil.rmtree(O + "/o_tree2")',
    "sqlite_file_outside": 'sqlite3.connect(O + "/s.db")',
    "sqlite_path_outside": 'sqlite3.connect(pathlib.Path(O, "s2.db"))',
    "sqlite_uri_outside": (
        'sqlite3.connect("file:" + urllib.parse.quote(O + "/u.db"), uri=True)'
    ),
    "sqlite_uri_dotdot": (
        'sqlite3.connect("file:" + R + "/../" + os.path.basename(O) + "/u.db",'
        " uri=True)"
    ),
    "sqlite_empty": 'sqlite3.connect("")',
    "sqlite_relative_outside": (
        "cwd = os.getcwd(); os.chdir(O)\n"
        "try:\n"
        '    sqlite3.connect("rel.db")\n'
        "finally:\n"
        "    os.chdir(cwd)"
    ),
    "symlink_dst_outside": 'os.symlink(R + "/a.txt", O + "/sl")',
    "link_dst_outside": 'os.link(R + "/a.txt", O + "/hl")',
    "link_src_outside": 'os.link(O + "/b.txt", R + "/hl")',
    "utime_outside": 'os.utime(O + "/b.txt", None)',
    "chown_outside": 'os.chown(O + "/b.txt", -1, -1)',
    "shutil_chown_outside": 'shutil.chown(O + "/b.txt", user=os.getuid())',
    "make_archive_outside": 'shutil.make_archive(O + "/arch", "tar", R + "/tree")',
    "unpack_archive_outside": 'shutil.unpack_archive(R + "/z.tar", O + "/ex")',
    "unix_socket_outside": (
        "cwd = os.getcwd(); os.chdir(O)\n"
        "try:\n"
        "    s = socket.socket(socket.AF_UNIX)\n"
        '    s.bind("s.sock")\n'
        "finally:\n"
        "    s.close()\n"
        "    os.chdir(cwd)"
    ),
}

SETUP = """
os.makedirs(R + "/tree/sub")
open(R + "/tree/sub/f.txt", "w").write("x")
open(R + "/a.txt", "w").write("x")
os.makedirs(O + "/o_tree/sub")
open(O + "/o_tree/sub/f.txt", "w").write("x")
os.makedirs(O + "/o_tree2/sub")
os.mkdir(O + "/o_rm")
for name in ("b.txt", "b3.txt", "b4.txt", "src1", "src2", "mv_o"):
    open(O + "/" + name, "w").write("x")
os.symlink(O, R + "/link")
os.symlink(O + "/b.txt", R + "/flink")
shutil.make_archive(R + "/z", "tar", R + "/tree")
"""

CHILD = """
import json, logging, os, pathlib, shutil, socket, sqlite3, sys, tempfile
import urllib.parse
sys.path.insert(0, {server!r})
import write_guard
R, X, O = {root!r}, {extra!r}, {outside!r}
{setup}
write_guard.install(pathlib.Path(R), [pathlib.Path(X)])
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


def run_child(
    script: str, home: Path, **extra: str
) -> subprocess.CompletedProcess[str]:
    """Run a child Python with the server folder on sys.path."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        env={**child_env(home), **extra},
        timeout=120,
        check=False,
    )


class World:
    """The three folders the child works in."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "store"
        self.extra = base / "extra"
        self.outside = base / "outside"
        self.home = base / "home"
        for folder in (self.root, self.extra, self.outside, self.home):
            folder.mkdir(parents=True)


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> World:
    return World(tmp_path_factory.mktemp("guard").resolve())


@pytest.fixture(scope="module")
def results(world: World) -> dict[str, str]:
    """Run every case once in one child and return {case name: outcome}."""
    script = CHILD.format(
        server=str(SERVER_DIR),
        root=str(world.root),
        extra=str(world.extra),
        outside=str(world.outside),
        setup=SETUP,
        cases={**ALLOWED, **REFUSED},
    )
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# The hook in a subprocess


@pytest.mark.parametrize("name", sorted(ALLOWED))
def test_allowed_work_succeeds_after_install(
    results: dict[str, str], name: str
) -> None:
    assert results[name] == "ok"


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_a_write_outside_the_roots_is_refused(
    results: dict[str, str], name: str
) -> None:
    assert results[name].startswith("refused: [Errno 1] write refused (")


def test_no_case_was_dropped(results: dict[str, str]) -> None:
    assert set(results) == set(ALLOWED) | set(REFUSED)


def test_a_refused_write_changes_nothing_outside(
    world: World, results: dict[str, str]
) -> None:
    # The refused cases ran in the module's one child. Nothing they asked for exists.
    for name in ("nw.txt", "nx.txt", "nc.txt", "nb.bin", "pw.txt", "cf", "cp", "hl"):
        assert not (world.outside / name).exists()
    assert (world.outside / "b.txt").read_text() == "x"


def test_a_refusal_names_a_code_and_never_a_path(world: World) -> None:
    folder = "secret-folder-name"
    script = f"""
import logging, os, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
records = []
class Keep(logging.Handler):
    def emit(self, record):
        records.append(record.getMessage())
logging.getLogger("write_guard").addHandler(Keep())
write_guard.install(__import__("pathlib").Path({str(world.root)!r}))
try:
    open({str(world.outside / folder)!r}, "w")
except PermissionError as exc:
    sys.stdout.write(repr(str(exc)) + "|" + "|".join(records))
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "'[Errno 1] write refused (open)'|write guard refused: open"
    assert folder not in proc.stdout
    assert str(world.outside) not in proc.stdout + proc.stderr


def test_a_logging_file_handler_cannot_loop_the_hook(world: World) -> None:
    log_path = world.outside / "guard.log"
    script = f"""
import logging, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
handler = logging.FileHandler({str(log_path)!r}, delay=True)
logging.getLogger("write_guard").addHandler(handler)
write_guard.install(__import__("pathlib").Path({str(world.root)!r}))
try:
    open({str(world.outside / "x.txt")!r}, "w")
except PermissionError:
    sys.stdout.write("refused")
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "refused"
    assert "write guard refused: open" in log_path.read_text()


def test_resolving_a_symlinked_path_raises_no_audit_event(world: World) -> None:
    (world.root / "evlink").symlink_to(world.outside)
    script = f"""
import os, sys
events = []
sys.addaudithook(lambda event, args: events.append(event))
resolved = os.path.realpath({str(world.root / "evlink" / "x")!r})
sys.stdout.write(resolved + "|" + ",".join(events))
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == f"{world.outside / 'x'}|"


def test_a_root_given_as_a_symlink_is_judged_by_where_it_points(world: World) -> None:
    link = world.base / "rootlink"
    link.symlink_to(world.root)
    script = f"""
import sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import pathlib, write_guard
write_guard.install(pathlib.Path({str(link)!r}))
open({str(world.root / "via-link.txt")!r}, "w").close()
sys.stdout.write("ok")
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "ok"


def test_install_twice_with_the_same_roots_is_a_no_op_and_other_roots_raise(
    world: World,
) -> None:
    script = f"""
import pathlib, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
root = pathlib.Path({str(world.root)!r})
write_guard.install(root)
write_guard.install(root)
try:
    write_guard.install(root, [pathlib.Path({str(world.extra)!r})])
except RuntimeError:
    sys.stdout.write("raised")
"""
    proc = run_child(script, world.home)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "raised"


def test_importing_the_module_installs_nothing(world: World) -> None:
    script = f"""
import sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import write_guard
open({str(world.outside / "free.txt")!r}, "w").close()
sys.stdout.write("ok")
"""
    proc = run_child(script, world.home)
    assert proc.stdout == "ok"


# --------------------------------------------------------------------------
# The checks in this process, with the roots patched in and no hook installed


@pytest.fixture
def roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    root = (tmp_path / "root").resolve()
    extra = (tmp_path / "extra").resolve()
    outside = (tmp_path / "out").resolve()
    for folder in (root, extra, outside):
        folder.mkdir()
    monkeypatch.setattr(wg.STATE, "roots", (str(root), str(extra)))
    return root, extra, outside


def test_audit_raises_permission_error_with_a_code_and_logs_it(
    roots: tuple[Path, Path, Path], caplog: pytest.LogCaptureFixture
) -> None:
    _, _, outside = roots
    with (
        caplog.at_level(logging.WARNING, logger="write_guard"),
        pytest.raises(PermissionError) as info,
    ):
        wg.audit("os.remove", (str(outside / "f"), -1))
    assert "write refused (remove)" in str(info.value)
    assert [r.getMessage() for r in caplog.records] == ["write guard refused: remove"]
    assert str(outside) not in str(info.value) + caplog.text


def test_audit_ignores_events_it_does_not_check(
    roots: tuple[Path, Path, Path],
) -> None:
    _, _, outside = roots
    wg.audit("os.listdir", (str(outside),))
    wg.audit("import", ("json",))


def test_audit_refuses_an_event_it_cannot_read(
    roots: tuple[Path, Path, Path],
) -> None:
    with pytest.raises(PermissionError, match=r"unchecked"):
        wg.audit("os.remove", (object(), -1))
    with pytest.raises(PermissionError, match=r"unchecked"):
        wg.audit("os.remove", ())


def test_audit_skips_events_raised_while_it_logs(
    roots: tuple[Path, Path, Path],
) -> None:
    _, _, outside = roots
    wg.BUSY.on = True
    try:
        wg.audit("os.remove", (str(outside / "f"), -1))
    finally:
        wg.BUSY.on = False


@pytest.mark.parametrize(
    ("mode", "flags", "writes"),
    [
        ("r", os.O_RDONLY, False),
        ("rb", os.O_RDONLY | os.O_CLOEXEC, False),
        ("w", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, True),
        ("a", os.O_WRONLY | os.O_APPEND, True),
        ("x", os.O_WRONLY | os.O_CREAT | os.O_EXCL, True),
        ("r+", os.O_RDWR, True),
        (None, os.O_RDONLY, False),
        (None, os.O_RDONLY | os.O_CREAT, True),
        (None, os.O_RDONLY | os.O_TRUNC, True),
        ("r", "not an int", True),
        ("w", os.O_RDONLY, True),
    ],
)
def test_writes_reads_the_mode_and_the_flags(
    mode: object, flags: object, writes: bool
) -> None:
    assert wg.writes(mode, flags) is writes


def test_a_bare_name_below_a_directory_fd_is_allowed_and_a_path_is_not(
    roots: tuple[Path, Path, Path],
) -> None:
    wg.audit("os.rmdir", ("child", 5))
    wg.audit("os.remove", ("name.txt", 7))
    for bad in ("../up", "a/b", "..", ".", ""):
        with pytest.raises(PermissionError):
            wg.audit("os.remove", (bad, 7))


def test_a_relative_path_with_no_directory_fd_is_judged_by_the_working_folder(
    roots: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _, outside = roots
    monkeypatch.chdir(root)
    wg.audit("os.mkdir", ("rel", 0o777, -1))
    monkeypatch.chdir(outside)
    with pytest.raises(PermissionError):
        wg.audit("os.mkdir", ("rel", 0o777, -1))


def test_a_file_descriptor_and_dev_null_pass(roots: tuple[Path, Path, Path]) -> None:
    wg.audit("open", (3, "w", os.O_WRONLY))
    wg.audit("os.truncate", (3, 0))
    wg.audit("os.chmod", (3, 0o600, -1))
    wg.audit("open", (os.devnull, "w", os.O_WRONLY | os.O_CREAT))
    with pytest.raises(PermissionError):
        wg.audit("open", ("/dev/zero", "w", os.O_WRONLY))


def test_a_path_that_only_starts_like_a_root_is_outside(
    roots: tuple[Path, Path, Path],
) -> None:
    root, _, _ = roots
    with pytest.raises(PermissionError):
        wg.audit("os.mkdir", (str(root) + "-sibling", 0o777, -1))
    wg.audit("os.mkdir", (str(root), 0o777, -1))
    wg.audit("os.mkdir", (str(root / "inner"), 0o777, -1))


def test_bytes_and_path_like_arguments_are_checked(
    roots: tuple[Path, Path, Path],
) -> None:
    root, _, outside = roots
    wg.audit("os.remove", (os.fsencode(root / "f"), -1))
    wg.audit("os.remove", (root / "f", -1))
    with pytest.raises(PermissionError):
        wg.audit("os.remove", (os.fsencode(outside / "f"), -1))
    with pytest.raises(PermissionError):
        wg.audit("os.remove", (outside / "f", -1))


@pytest.mark.parametrize(
    ("uri", "path"),
    [
        ("file:/a/b.db", "/a/b.db"),
        ("file:/a/b%20c.db?mode=rw", "/a/b c.db"),
        ("file:///a/b.db", "/a/b.db"),
        ("file://localhost/a/b.db?x=1", "/a/b.db"),
        ("file:rel.db", "rel.db"),
    ],
)
def test_uri_path_drops_the_scheme_authority_and_query(uri: str, path: str) -> None:
    assert wg.uri_path(uri) == path


def test_sqlite_checks_memory_paths_and_uris(roots: tuple[Path, Path, Path]) -> None:
    root, _, outside = roots
    wg.audit("sqlite3.connect", (":memory:",))
    wg.audit("sqlite3.connect", (str(root / "s.db"),))
    wg.audit("sqlite3.connect", (f"file:{root}/s.db?mode=rw",))
    for bad in (str(outside / "s.db"), "", f"file:{outside}/s.db"):
        with pytest.raises(PermissionError, match=r"sqlite"):
            wg.audit("sqlite3.connect", (bad,))


def test_socket_bind_checks_only_unix_paths(roots: tuple[Path, Path, Path]) -> None:
    root, _, outside = roots
    wg.audit("socket.bind", (None, ("127.0.0.1", 0)))
    wg.audit("socket.bind", (None, b"\0abstract"))
    wg.audit("socket.bind", (None, str(root / "s")))
    with pytest.raises(PermissionError, match=r"socket"):
        wg.audit("socket.bind", (None, str(outside / "s")))


def test_move_and_link_check_both_ends(roots: tuple[Path, Path, Path]) -> None:
    root, _, outside = roots
    wg.audit("shutil.move", (str(root / "a"), str(root / "b")))
    for src, dst in ((root / "a", outside / "b"), (outside / "a", root / "b")):
        with pytest.raises(PermissionError, match=r"move"):
            wg.audit("shutil.move", (str(src), str(dst)))
        with pytest.raises(PermissionError, match=r"link"):
            wg.audit("os.link", (str(src), str(dst), -1, -1))
        with pytest.raises(PermissionError, match=r"rename"):
            wg.audit("os.rename", (str(src), str(dst), -1, -1))


def test_archive_and_metadata_events_check_their_target(
    roots: tuple[Path, Path, Path],
) -> None:
    root, _, outside = roots
    wg.audit("shutil.make_archive", (str(root / "z"), "tar", None, None))
    wg.audit("shutil.unpack_archive", (str(outside / "z.tar"), str(root), None))
    wg.audit("os.setxattr", (str(root / "f"), "k", b"v", 0))
    wg.audit("os.chflags", (str(root / "f"), 0))
    wg.audit("os.utime", (str(root / "f"), None, None, -1))
    wg.audit("os.chown", (str(root / "f"), -1, -1, -1))
    with pytest.raises(PermissionError, match=r"archive"):
        wg.audit("shutil.make_archive", (str(outside / "z"), "tar", None, None))
    with pytest.raises(PermissionError, match=r"archive"):
        wg.audit("shutil.unpack_archive", (str(root / "z.tar"), str(outside), None))
    for event, args in (
        ("os.setxattr", (str(outside / "f"), "k", b"v", 0)),
        ("os.removexattr", (str(outside / "f"), "k")),
        ("os.chflags", (str(outside / "f"), 0)),
        ("os.utime", (str(outside / "f"), None, None, -1)),
        ("os.chown", (str(outside / "f"), -1, -1, -1)),
        ("shutil.chown", (str(outside / "f"), "u", None)),
    ):
        with pytest.raises(PermissionError, match=r"metadata"):
            wg.audit(event, args)
