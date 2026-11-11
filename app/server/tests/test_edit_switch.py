"""Tests for the edit switch: ``serve.py --allow-edits`` and ``edit_switch.py``.

Fixture and demo runs refuse edits unless every folder sits outside the Bar Tab
checkout and the git work tree that holds it (m6-build.md section 3.1). The pure checks
run in process. The write guard and the server run in subprocesses, because an audit
hook can't be removed. Every folder is under ``tmp_path``, outside any git work tree,
and every server binds a port from 47000 to 47999.
"""

import json
import os
import select
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx2
import pytest

import edit_switch
import main
import project_map
import projects
import serve
import store_provider
from access import AccessState

SERVER_DIR = Path(__file__).resolve().parents[1]
CHECKOUT = edit_switch.REPO_ROOT
PORT_FIRST = 47000
PORT_LAST = 47999
ORIGIN_FMT = "http://127.0.0.1:{port}"


def folders(tmp_path: Path) -> dict[str, Path]:
    """Made-up Claude, data and project folders under tmp_path."""
    made = {
        "claude": tmp_path / "cfg" / ".claude",
        "data": tmp_path / "data",
        "project": tmp_path / "proj",
    }
    for folder in made.values():
        folder.mkdir(parents=True)
    return {name: folder.resolve() for name, folder in made.items()}


# ------------------------------------------------------------------ outside_checkout


def test_a_temp_folder_is_outside_the_checkout(tmp_path: Path) -> None:
    assert edit_switch.outside_checkout(tmp_path)


@pytest.mark.parametrize(
    "rel",
    [
        "",
        "app/server",
        "app/fixtures/oracle",
        "tests/fixtures/demo",
        "app/.data/demo/config",
        "not/yet/made",
    ],
)
def test_the_checkout_and_everything_in_it_is_inside(rel: str) -> None:
    assert not edit_switch.outside_checkout(CHECKOUT / rel)


def test_a_sibling_whose_name_starts_like_the_checkout_is_outside() -> None:
    twin = CHECKOUT.parent / (CHECKOUT.name + "-twin") / "x"
    assert edit_switch.outside_checkout(twin)


def test_a_link_into_the_checkout_is_inside(tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(CHECKOUT / "app")
    assert not edit_switch.outside_checkout(link)
    assert not edit_switch.outside_checkout(link / "server")


def test_the_git_work_tree_that_holds_the_checkout_is_inside(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    checkout = tree / "sub" / "checkout"
    checkout.mkdir(parents=True)
    (tree / ".git").mkdir()
    beside = tmp_path / "beside"
    beside.mkdir()
    assert not edit_switch.outside_checkout(checkout / "a", checkout)
    # The work tree holds the checkout, so its other folders count too.
    assert not edit_switch.outside_checkout(tree / "docs", checkout)
    assert not edit_switch.outside_checkout(tree / "sub" / "elsewhere", checkout)
    assert edit_switch.outside_checkout(beside, checkout)


def test_a_checkout_that_is_its_own_work_tree_adds_nothing(tmp_path: Path) -> None:
    checkout = tmp_path / "own"
    checkout.mkdir()
    (checkout / ".git").write_text("gitdir: /work/main/.git/worktrees/own\n")
    assert edit_switch.checkout_roots(checkout) == (str(checkout.resolve()),)
    assert edit_switch.outside_checkout(tmp_path / "other", checkout)


# -------------------------------------------------------------------- resolve_state


def test_no_flag_means_off(tmp_path: Path) -> None:
    made = folders(tmp_path)
    for real in (False, True):
        state = edit_switch.resolve_state(
            requested=False, real=real, claude_dir=made["claude"], folders=[]
        )
        assert state == "off"


def test_real_mode_gets_edits_as_asked() -> None:
    state = edit_switch.resolve_state(
        requested=True, real=True, claude_dir=CHECKOUT / "app", folders=[CHECKOUT]
    )
    assert state == "on"


def test_a_run_with_no_claude_folder_is_unavailable() -> None:
    state = edit_switch.resolve_state(
        requested=True, real=False, claude_dir=None, folders=[]
    )
    assert state == "unavailable"


def test_outside_folders_are_on(tmp_path: Path) -> None:
    made = folders(tmp_path)
    state = edit_switch.resolve_state(
        requested=True,
        real=False,
        claude_dir=made["claude"],
        folders=[made["data"], None, made["project"]],
    )
    assert state == "on"


@pytest.mark.parametrize("where", ["claude", "data", "store", "project"])
def test_any_folder_in_the_checkout_is_unavailable(tmp_path: Path, where: str) -> None:
    made = folders(tmp_path)
    inside = CHECKOUT / "app" / ".data" / where
    claude = inside if where == "claude" else made["claude"]
    others = {
        "data": inside if where == "data" else made["data"],
        "store": inside if where == "store" else None,
        "project": inside if where == "project" else made["project"],
    }
    state = edit_switch.resolve_state(
        requested=True,
        real=False,
        claude_dir=claude,
        folders=list(others.values()),
    )
    assert state == "unavailable"


def test_a_refusal_logs_a_reason_and_no_path(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    made = folders(tmp_path)
    edit_switch.resolve_state(
        requested=True,
        real=False,
        claude_dir=made["claude"],
        folders=[CHECKOUT / "app"],
    )
    assert "edits unavailable" in caplog.text
    assert str(CHECKOUT) not in caplog.text


def no_install(*_args: object, **_kwargs: object) -> None:
    """Stand in for the write guard, which an in-process test must not install."""


def refusal_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "edits unavailable" in r.message]


@pytest.mark.parametrize(
    ("where", "word"),
    [
        ("claude", "Claude"),
        ("data", "data"),
        ("store", "store"),
        ("project", "project"),
    ],
)
def test_a_refusal_names_the_folder_that_sits_in_the_checkout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, where: str, word: str
) -> None:
    caplog.set_level("INFO")
    made = folders(tmp_path)
    inside = CHECKOUT / "app" / ".data" / where
    edit_switch.resolve_state(
        requested=True,
        real=False,
        claude_dir=inside if where == "claude" else made["claude"],
        folders={
            "data": inside if where == "data" else made["data"],
            "store": inside if where == "store" else None,
            "project": inside if where == "project" else made["project"],
        },
    )
    assert refusal_lines(caplog) == [
        f"edits unavailable: the {word} folder sits in the Bar Tab checkout"
    ]
    assert str(CHECKOUT) not in caplog.text
    assert str(tmp_path) not in caplog.text


def test_a_refusal_names_the_git_work_tree_that_holds_the_checkout(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    tree = tmp_path / "tree"
    checkout = tree / "app"
    checkout.mkdir(parents=True)
    (tree / ".git").mkdir()
    beside = tree / "other"
    beside.mkdir()
    made = folders(tmp_path)
    state = edit_switch.resolve_state(
        requested=True,
        real=False,
        claude_dir=made["claude"],
        folders={"data": beside},
        checkout=checkout,
    )
    assert state == "unavailable"
    assert refusal_lines(caplog) == [
        "edits unavailable: the data folder sits in the git work tree that holds"
        " the Bar Tab checkout"
    ]
    assert str(tmp_path) not in caplog.text


def test_a_refusal_for_a_run_with_no_claude_folder_names_the_flag(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    state = edit_switch.resolve_state(
        requested=True, real=False, claude_dir=None, folders=[]
    )
    assert state == "unavailable"
    assert refusal_lines(caplog) == [
        "edits unavailable: this fixture run has no Claude folder to edit"
        " (pass --claude-dir)"
    ]


def test_a_run_that_does_not_ask_for_edits_logs_no_refusal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level("INFO")
    edit_switch.resolve_state(requested=False, real=False, claude_dir=None, folders=[])
    assert refusal_lines(caplog) == []


# ----------------------------------------------------------------------- root_watch


def test_root_watch_turns_edits_off_for_good_and_drops_keys(tmp_path: Path) -> None:
    state = AccessState(edits="on")
    code = state.mint_code("proj")
    assert state.swap(code).edit_keys["proj"]
    watch = edit_switch.root_watch(state)
    watch([str(tmp_path), "/work/never-made"])
    assert state.edits == "on"
    watch([str(tmp_path), str(CHECKOUT / "app")])
    assert state.edits == "unavailable"
    assert state.edit_key_matches("proj", b"anything") is False
    assert state.swap(state.mint_code("proj")).edit_keys == {}
    watch([str(tmp_path)])
    assert state.edits == "unavailable"


def test_root_watch_leaves_off_alone() -> None:
    state = AccessState(edits="off")
    edit_switch.root_watch(state)([str(CHECKOUT)])
    assert state.edits == "off"


# --------------------------------------------------------------------------- serve.py


def test_parse_args_takes_allow_edits() -> None:
    assert serve.parse_args(["--data", "/work/data"]).allow_edits is False
    assert serve.parse_args(["--data", "/work/data", "--allow-edits"]).allow_edits


def test_parse_args_takes_allow_edits_with_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/work/cfg/.claude")
    args = serve.parse_args(["--real", "--allow-edits"])
    assert args.real
    assert args.allow_edits
    assert (
        serve.resolve_edits(args, serve.World(args.claude_dir, args.store, None))
        == "on"
    )


def test_resolve_edits_for_a_fixture_run_with_no_claude_folder(tmp_path: Path) -> None:
    args = serve.parse_args(["--data", str(tmp_path), "--allow-edits"])
    assert serve.resolve_edits(args, serve.World(None, None, None)) == "unavailable"


def test_resolve_edits_refuses_a_data_folder_in_the_checkout(tmp_path: Path) -> None:
    made = folders(tmp_path)
    args = serve.parse_args(
        ["--data", str(CHECKOUT / "app" / ".data-never"), "--allow-edits"]
    )
    world = serve.World(made["claude"], None, None)
    assert serve.resolve_edits(args, world) == "unavailable"


def test_resolve_edits_refuses_a_launch_project_in_the_checkout(tmp_path: Path) -> None:
    made = folders(tmp_path)
    args = serve.parse_args(
        [
            "--data",
            str(made["data"]),
            "--project-dir",
            str(CHECKOUT / "app"),
            "--allow-edits",
        ]
    )
    world = serve.World(made["claude"], None, None)
    assert serve.resolve_edits(args, world) == "unavailable"


def test_resolve_edits_accepts_outside_folders(tmp_path: Path) -> None:
    made = folders(tmp_path)
    args = serve.parse_args(
        [
            "--data",
            str(made["data"]),
            "--project-dir",
            str(made["project"]),
            "--claude-dir",
            str(made["claude"]),
            "--allow-edits",
        ]
    )
    world = serve.World(made["claude"], None, None)
    assert serve.resolve_edits(args, world) == "on"


# ------------------------------------------------------- the guard, in a child process


GUARD_CHILD = """
import os, sys
sys.path.insert(0, {server!r})
import serve, write_guard
args = serve.parse_args({argv!r})
{enter}
roots = write_guard.STATE.roots
out = {{"edits": write_guard.STATE.edits, "tmpdir": os.environ.get("TMPDIR", "")}}
for name, path in {probes!r}.items():
    try:
        open(path, "w").close()
        out[name] = "ok"
    except PermissionError:
        out[name] = "refused"
with write_guard.permit({target!r}):
    pass
out["permit"] = "ok"
sys.stdout.write(__import__("json").dumps(out))
"""


def run_guard_child(script: str, home: Path, env: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "PYTHONDONTWRITEBYTECODE": "1",
            "LANG": "C",
            **env,
        },
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_a_fixture_run_with_edits_installs_the_guard_with_the_backups_root(
    tmp_path: Path,
) -> None:
    made = folders(tmp_path)
    backups = made["claude"] / "routing-dashboard" / "backups"
    backups.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    probes = {
        "data": str(made["data"] / "inside.txt"),
        "store": str(made["data"] / "store" / "x.txt"),
        "backups": str(backups / "x.txt"),
        "outside": str(outside / "x.txt"),
        "project": str(made["project"] / "x.txt"),
        "claude": str(made["claude"] / "settings.json"),
    }
    (made["data"] / "store").mkdir()
    script = GUARD_CHILD.format(
        server=str(SERVER_DIR),
        argv=[
            "--data",
            str(made["data"]),
            "--claude-dir",
            str(made["claude"]),
            "--allow-edits",
        ],
        enter="world = serve.World(args.claude_dir, None, None)\n"
        "assert serve.enter_edit_mode(args, world)",
        probes=probes,
        target=str(made["project"] / ".claude" / "settings.json"),
    )
    found = run_guard_child(script, tmp_path / "home", {})
    assert found["edits"] is True
    assert found["data"] == "ok"
    assert found["store"] == "ok"
    assert found["backups"] == "ok"
    assert found["outside"] == "refused"
    assert found["project"] == "refused"
    assert found["claude"] == "refused"
    assert found["permit"] == "ok"
    assert found["tmpdir"] == str(made["data"] / "tmp")


def test_a_fixture_run_with_edits_makes_the_old_apps_folder_and_nothing_else(
    tmp_path: Path,
) -> None:
    """The guard allows the backups folder but not its parent, so serve.py makes it."""
    made = folders(tmp_path)
    parent = made["claude"] / "routing-dashboard"
    backups = parent / "backups"
    assert not parent.exists()
    enter = f"""world = serve.World(args.claude_dir, None, None)
assert serve.enter_edit_mode(args, world)
import stat
assert stat.S_IMODE(os.stat({str(parent)!r}).st_mode) == 0o700
os.mkdir({str(backups)!r}, 0o700)
for other in ({str(parent / "other")!r}, {str(made["claude"] / "projects")!r}):
    try:
        os.mkdir(other)
    except PermissionError:
        pass
    else:
        raise SystemExit("the guard let " + other + " be made")
"""
    script = GUARD_CHILD.format(
        server=str(SERVER_DIR),
        argv=[
            "--data",
            str(made["data"]),
            "--claude-dir",
            str(made["claude"]),
            "--allow-edits",
        ],
        enter=enter,
        probes={"backups": str(backups / "x.txt")},
        target=str(made["project"] / ".claude" / "settings.json"),
    )
    found = run_guard_child(script, tmp_path / "home", {})
    assert found["backups"] == "ok"
    assert parent.is_dir()
    assert sorted(p.name for p in parent.iterdir()) == ["backups"]
    assert not (made["claude"] / "projects").exists()


def test_a_fixture_run_with_edits_keeps_an_existing_old_app_folder_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = folders(tmp_path)
    parent = made["claude"] / "routing-dashboard"
    parent.mkdir(mode=0o755)
    (parent / "keep.txt").write_text("kept", encoding="utf-8")
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    monkeypatch.setattr(serve.write_guard, "install", no_install)
    monkeypatch.setenv("TMPDIR", os.environ.get("TMPDIR", str(tmp_path)))
    monkeypatch.setattr(serve.tempfile, "tempdir", serve.tempfile.tempdir)
    args = serve.parse_args(
        ["--data", str(made["data"]), "--claude-dir", str(made["claude"])]
    )
    world = serve.World(made["claude"], None, None)
    assert serve.enter_edit_mode(args, world)
    assert (parent / "keep.txt").read_text(encoding="utf-8") == "kept"
    assert parent.stat().st_mode & 0o777 == 0o755


def test_a_fixture_run_with_edits_stops_when_the_claude_folder_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    made = folders(tmp_path)
    gone = made["claude"] / "never-made" / ".claude"
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    monkeypatch.setattr(serve.write_guard, "install", no_install)
    monkeypatch.setenv("TMPDIR", os.environ.get("TMPDIR", str(tmp_path)))
    monkeypatch.setattr(serve.tempfile, "tempdir", serve.tempfile.tempdir)
    args = serve.parse_args(["--data", str(made["data"]), "--claude-dir", str(gone)])
    world = serve.World(gone, None, None)
    assert serve.enter_edit_mode(args, world) is False
    assert not gone.exists()
    assert "could not make the Bar Tab folders" in caplog.text


def test_real_mode_with_edits_installs_the_guard_with_the_backups_root(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    config = home / ".claude"
    config.mkdir(parents=True)
    store = config / "routing-dashboard" / "bartab"
    backups = config / "routing-dashboard" / "backups"
    project = tmp_path / "proj"
    project.mkdir()
    probes = {
        "store": str(store / "x.txt"),
        "backups": str(backups / "x.txt"),
        "config": str(config / "settings.json"),
        "project": str(project / "x.txt"),
    }
    script = GUARD_CHILD.format(
        server=str(SERVER_DIR),
        argv=["--real", "--allow-edits"],
        enter=f"assert serve.enter_real_mode(args)\nos.makedirs({str(backups)!r})",
        probes=probes,
        target=str(project / ".claude" / "settings.json"),
    )
    found = run_guard_child(script, home, {"CLAUDE_CONFIG_DIR": str(config)})
    assert found["edits"] is True
    assert found["store"] == "ok"
    assert found["backups"] == "ok"
    assert found["config"] == "refused"
    assert found["project"] == "refused"
    assert found["permit"] == "ok"


def test_real_mode_without_edits_keeps_the_backups_folder_closed(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    config = home / ".claude"
    config.mkdir(parents=True)
    backups = config / "routing-dashboard" / "backups"
    script = f"""
import os, sys
sys.path.insert(0, {str(SERVER_DIR)!r})
import serve, write_guard
args = serve.parse_args(["--real"])
assert serve.enter_real_mode(args)
os.makedirs({str(backups.parent)!r}, exist_ok=True)
try:
    open({str(backups / "x.txt")!r}, "w")
    sys.stdout.write("open")
except (PermissionError, FileNotFoundError) as exc:
    sys.stdout.write(type(exc).__name__)
try:
    with write_guard.permit("/work/cfg/a.json"):
        sys.stdout.write("|permit")
except PermissionError:
    sys.stdout.write("|no-permit")
"""
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-I", "-c", script],
        capture_output=True,
        text=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(config),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "PermissionError|no-permit"


# ------------------------------------------------------------- a real server process


def free_port() -> int:
    """A free port from 47000 to 47999, never 8377."""
    start = PORT_FIRST + (os.getpid() * 7) % (PORT_LAST - PORT_FIRST)
    for offset in range(PORT_LAST - PORT_FIRST + 1):
        port = PORT_FIRST + (start - PORT_FIRST + offset) % (PORT_LAST - PORT_FIRST + 1)
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    pytest.fail("no free port in 47000 to 47999")


def read_launch_line(fd: int, timeout: float = 120.0) -> dict[str, Any]:
    buffer = b""
    deadline = time.monotonic() + timeout
    while b"\n" not in buffer:
        left = deadline - time.monotonic()
        assert left > 0, "no launch line"
        ready, _, _ = select.select([fd], [], [], left)
        assert ready, "no launch line"
        chunk = os.read(fd, 4096)
        assert chunk, "launch fd closed without a line"
        buffer += chunk
    return json.loads(buffer.split(b"\n", 1)[0])


@contextmanager
def running_server(
    tmp_path: Path, extra: list[str], dist: Path, log: list[str] | None = None
) -> Generator[tuple[int, dict[str, Any], Path]]:
    """Start serve.py in a temp tree. Yields (port, launch line, data folder).

    When ``log`` is a list, the server's log (its stderr) is appended to it once the
    server has stopped.
    """
    data = tmp_path / "data"
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    port = free_port()
    read_fd, write_fd = os.pipe()
    process = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(SERVER_DIR / "serve.py"),
            "--port",
            str(port),
            "--data",
            str(data),
            "--launch-fd",
            str(write_fd),
            "--dist",
            str(dist),
            "--idle-exit-minutes",
            "0",
            "--no-price-fetch",
            *extra,
        ],
        pass_fds=(write_fd,),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        cwd=SERVER_DIR,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "BARTAB_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    )
    os.close(write_fd)
    try:
        yield port, read_launch_line(read_fd), data
        process.send_signal(signal.SIGTERM)
        _out, err = process.communicate(timeout=20)
        if log is not None:
            log.append(err.decode("utf-8", "replace"))
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
        os.close(read_fd)


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    folder = tmp_path / "dist"
    folder.mkdir()
    (folder / "index.html").write_text(
        "<!doctype html><html><head></head><body></body></html>", encoding="utf-8"
    )
    return folder


def swap(port: int, code: str) -> dict[str, Any]:
    response = httpx2.post(
        f"http://127.0.0.1:{port}/api/access/swap", json={"code": code}, timeout=10
    )
    assert response.status_code == 200
    return response.json()


def app_edits(port: int, read_key: str) -> dict[str, Any]:
    answer = httpx2.get(
        f"http://127.0.0.1:{port}/api/app",
        headers={"X-Bartab-Key": read_key},
        timeout=10,
    )
    assert answer.status_code == 200
    return answer.json()


def post_preview(port: int, read_key: str, edit_key: str | None, project: str) -> Any:
    headers = {
        "X-Bartab-Key": read_key,
        "Origin": ORIGIN_FMT.format(port=port),
    }
    if edit_key is not None:
        headers["X-Bartab-Edit"] = edit_key
    body = {
        "project": project,
        "op": "set",
        "scope": "user",
        "field": "model",
        "value": "claude-sonnet-5-5",
        "seq": 1,
    }
    return httpx2.post(
        f"http://127.0.0.1:{port}/api/edit/preview",
        json=body,
        headers=headers,
        timeout=10,
    )


def test_a_demo_server_outside_the_checkout_runs_with_edits_on(
    tmp_path: Path, dist: Path
) -> None:
    project = tmp_path / "launch-project"
    project.mkdir()
    with running_server(
        tmp_path, ["--demo", "--allow-edits", "--project-dir", str(project)], dist
    ) as (port, line, data):
        assert line["project"]
        keys = swap(port, line["code"])
        assert set(keys["edit_keys"]) == {line["project"]}
        body = app_edits(port, keys["read_key"])
        assert body["edits"] == {"state": "on", "instance": line["instance"]}
        assert line["project"] in body["editable_projects"]
        record = json.loads((data / "server.json").read_text())
        assert record["edits"] is True
        good = post_preview(
            port, keys["read_key"], keys["edit_keys"][line["project"]], line["project"]
        )
        assert good.status_code == 200  # past the gate, a real preview of the user file
        assert good.json()["target"]["scope"] == "user"
        bad = post_preview(port, keys["read_key"], "wrong", line["project"])
        assert bad.status_code in (401, 403)
        assert keys["edit_keys"][line["project"]] not in bad.text


def test_a_demo_server_whose_launch_project_is_in_the_checkout_refuses_edits(
    tmp_path: Path, dist: Path
) -> None:
    log: list[str] = []
    with running_server(
        tmp_path,
        ["--demo", "--allow-edits", "--project-dir", str(CHECKOUT / "app")],
        dist,
        log,
    ) as (port, line, data):
        keys = swap(port, line["code"])
        assert keys["edit_keys"] == {}
        body = app_edits(port, keys["read_key"])
        assert body["edits"] == {"state": "unavailable", "instance": line["instance"]}
        assert body["editable_projects"] == []
        assert json.loads((data / "server.json").read_text())["edits"] is False
        refused = post_preview(port, keys["read_key"], "k", "any-project")
        assert refused.status_code == 403
        assert refused.json()["code"] == "edits_off"
    # the server log names the cause in one line, with no path
    causes = [row for row in log[0].splitlines() if "edits unavailable" in row]
    assert len(causes) == 1
    assert causes[0].endswith(
        "edits unavailable: the project folder sits in the Bar Tab checkout"
    )
    assert str(CHECKOUT) not in log[0]


def test_a_canned_fixture_run_refuses_edits(tmp_path: Path, dist: Path) -> None:
    log: list[str] = []
    with running_server(
        tmp_path, ["--fixture", "demo", "--allow-edits"], dist, log
    ) as (
        port,
        line,
        _data,
    ):
        keys = swap(port, line["code"])
        assert keys["edit_keys"] == {}
        body = app_edits(port, keys["read_key"])
        assert body["edits"]["state"] == "unavailable"
        assert body["editable_projects"] == []
    causes = [row for row in log[0].splitlines() if "edits unavailable" in row]
    assert len(causes) == 1
    assert causes[0].endswith(
        "edits unavailable: this fixture run has no Claude folder to edit"
        " (pass --claude-dir)"
    )


def test_a_server_started_without_the_flag_has_edits_off(
    tmp_path: Path, dist: Path
) -> None:
    with running_server(tmp_path, ["--fixture", "demo"], dist) as (port, line, data):
        keys = swap(port, line["code"])
        assert keys["edit_keys"] == {}
        assert app_edits(port, keys["read_key"])["edits"]["state"] == "off"
        assert json.loads((data / "server.json").read_text())["edits"] is False


# --------------------------------------------- the store provider's project watch


def test_the_store_provider_runs_the_watch_on_every_mapping(
    tmp_path: Path,
    dist: Path,
    demo_build: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.copytree(demo_build, tmp_path / "demo")
    state = AccessState(edits="on")
    settings = main.Settings(
        port=PORT_FIRST,
        data_dir=tmp_path / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=tmp_path / "demo" / "config",
        store_dir=tmp_path / "store",
        demo=True,
        price_fetch=False,
        edits="on",
    )
    provider = main.make_provider(settings)
    assert isinstance(provider, store_provider.StoreProvider)
    # The demo's projects sit at made-up /work paths, outside the checkout.
    assert provider.projects().projects
    assert state.edits == "on"
    inside = project_map.MappedProject(
        key="inside",
        name="inside",
        display_path="inside",
        state="ok",
        folders=frozenset(),
        listed=True,
        path=str(CHECKOUT / "app"),
    )

    def fake_map(
        _ctx: projects.ProjectsContext, _conn: sqlite3.Connection
    ) -> list[project_map.MappedProject]:
        return [inside]

    monkeypatch.setattr(project_map, "map_projects", fake_map)
    provider._mapped = None  # pyright: ignore[reportPrivateUsage]
    assert provider.projects().projects
    assert state.edits == "unavailable"


def test_real_mode_has_no_project_watch(
    tmp_path: Path, dist: Path, demo_build: Path
) -> None:
    shutil.copytree(demo_build, tmp_path / "demo")
    state = AccessState(edits="on")
    settings = main.Settings(
        port=PORT_FIRST,
        data_dir=tmp_path / "data",
        dist_dir=dist,
        access_state=state,
        claude_dir=tmp_path / "demo" / "config",
        store_dir=tmp_path / "store",
        demo=True,
        price_fetch=False,
        real=True,
        edits="on",
    )
    provider = main.make_provider(settings)
    assert isinstance(provider, store_provider.StoreProvider)
    assert provider._root_watch is None  # pyright: ignore[reportPrivateUsage]
