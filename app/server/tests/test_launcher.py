"""Tests for app/bin/bartab.py, the stdlib launcher.

The launcher runs as a subprocess, the way the skill and the hooks run it
(L-979a). Each test gets a copy of it in a throwaway checkout under the system
temp folder, with a fake uv and a fake server, so nothing touches the real data
folder, the real uv or port 8377. A BROWSER stub or a recording webbrowser
controller stands in for the browser (I-14ae), so no real tab opens.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pytest

# Launcher tests bind real ports in the 47000 range, so one xdist worker runs them.
pytestmark = pytest.mark.xdist_group("launcher")

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from types import ModuleType

HERE = Path(__file__).resolve().parent
LAUNCHER_SRC = HERE.parent.parent / "bin" / "bartab.py"
PY3 = "/usr/bin/python3" if Path("/usr/bin/python3").exists() else sys.executable
URL_RE = re.compile(r"Bar Tab preview: http://127\.0\.0\.1:(\d+)/#/\?code=([\w.~-]+)")
UV_INSTALL_URL = "https://docs.astral.sh/uv/getting-started/installation/"


def load_fakes() -> ModuleType:
    """Import launcher_fakes.py from this folder."""
    spec = importlib.util.spec_from_file_location(
        "launcher_fakes", HERE / "launcher_fakes.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FAKES = load_fakes()


@pytest.fixture(scope="module")
def bartab() -> Iterator[ModuleType]:
    """The launcher imported in this process, for its cheap functions."""
    spec = importlib.util.spec_from_file_location("bartab_under_test", LAUNCHER_SRC)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["bartab_under_test"] = mod
    # Keep a __pycache__ out of app/bin, which the launcher's own run never makes.
    wrote_bytecode = not sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    spec.loader.exec_module(mod)
    yield mod
    sys.dont_write_bytecode = not wrote_bytecode
    del sys.modules["bartab_under_test"]


def wait_for(check: Callable[[], bool], seconds: float = 20) -> bool:
    """Poll check every 50 ms until it is true or the time is up."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(0.05)
    return check()


def pid_alive(pid: int) -> bool:
    """True when pid is a running process, not a zombie."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    stat = subprocess.run(  # noqa: S603
        ["/bin/ps", "-o", "stat=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return bool(stat) and not stat.startswith("Z")


class Tree:
    """A throwaway checkout with a copy of the launcher, a data folder and fakes."""

    def __init__(self, root: Path) -> None:
        """Lay out root/app/bin, root/app/server, a home, an empty bin and a project."""
        self.root = root
        self.launcher = root / "app" / "bin" / "bartab.py"
        self.launcher.parent.mkdir(parents=True)
        shutil.copy(LAUNCHER_SRC, self.launcher)
        (root / "app" / "server").mkdir()
        (root / "app" / "server" / "serve.py").write_text(FAKES.FAKE_SERVE)
        self.data = root / "data"
        self.home = root / "home"
        self.home.mkdir()
        self.emptybin = root / "emptybin"
        self.emptybin.mkdir()
        self.project = root / "work" / "demo"
        self.project.mkdir(parents=True)
        self.uv_log = root / "uv-log.jsonl"
        self.browser_log = root / "browser.log"

    def install_uv(self, path: Path | None = None) -> Path:
        """Put the fake uv where the launcher looks, or at path."""
        target = path or self.root / ".tools" / "uv" / "uv"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(FAKES.FAKE_UV.replace("@PYTHON@", sys.executable))
        target.chmod(0o755)
        return target

    def install_browser(self, exit_code: int = 0) -> str:
        """Write a BROWSER stub that records its argument. Returns the BROWSER value."""
        stub = self.root / "browser-stub.sh"
        stub.write_text(
            f'#!/bin/sh\necho "$1" >> "{self.browser_log}"\nexit {exit_code}\n'
        )
        stub.chmod(0o755)
        return f"{stub} %s"

    def env(self, **extra: str) -> dict[str, str]:
        """A clean environment with no uv on PATH, an empty home and no SSH."""
        env = {
            "PATH": f"{self.emptybin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "FAKE_UV_LOG": str(self.uv_log),
            "LANG": "C",
        }
        env.update(extra)
        return env

    def run(
        self,
        *args: str,
        session: str | None = None,
        stdin: str | None = None,
        **env: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run the launcher with --data and --default-project set."""
        cmd = [PY3, str(self.launcher), "--data", str(self.data)]
        cmd += ["--default-project", str(self.project)]
        if session is not None:
            cmd += ["--session", session]
        cmd += list(args)
        return subprocess.run(  # noqa: S603
            cmd,
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            env=self.env(**env),
            timeout=120,
            check=False,
        )

    def start(
        self, session: str | None = None, *extra: str, **env: str
    ) -> subprocess.CompletedProcess[str]:
        """Run start with --no-open."""
        return self.run("start", "--no-open", *extra, session=session, **env)

    def record(self) -> dict[str, object] | None:
        """The parsed server.json, or None."""
        path = self.data / "server.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def sessions(self) -> list[str]:
        """The sessions in server.json's owners."""
        rec = self.record()
        assert rec is not None
        return [str(o["session"]) for o in rec["owners"]]  # type: ignore[index]

    def uv_calls(self) -> list[dict[str, object]]:
        """What the fake uv logged."""
        if not self.uv_log.exists():
            return []
        return [json.loads(line) for line in self.uv_log.read_text().splitlines()]

    def pid(self) -> int:
        """The pid in server.json."""
        rec = self.record()
        assert rec is not None
        return int(cast("int", rec["pid"]))

    def serve_argv(self, index: int = 0) -> list[str]:
        """The argv the fake server logged for its index-th start."""
        argv = self.serve_runs()[index]["argv"]
        return [str(word) for word in cast("list[object]", argv)]

    def serve_runs(self) -> list[dict[str, object]]:
        """What each fake server start logged."""
        path = self.data / "serve-runs.log"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.fixture
def tree(tmp_path: Path) -> Iterator[Tree]:
    """A Tree with the fake uv installed. Any server left running is stopped."""
    t = Tree(tmp_path.resolve() / "checkout")
    t.install_uv()
    yield t
    rec = t.record()
    if rec is not None:
        t.run("stop")
        pid = rec["pid"]
        if isinstance(pid, int) and pid_alive(pid):
            os.kill(pid, signal.SIGKILL)


def deny_input(command: object) -> str:
    """A PreToolUse payload for a Bash call."""
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


# --------------------------------------------------------------------------
# Command line


def test_help_prints_usage_and_exits_zero() -> None:
    proc = subprocess.run(  # noqa: S603
        [PY3, "-I", str(LAUNCHER_SRC), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.startswith("usage: bartab.py")


@pytest.mark.parametrize(
    "args",
    [
        ["frobnicate"],
        ["start", "--bogus"],
        ["start", "--no-open", "--no-open"],
        ["stop", "--port", "1"],
        ["start", "--data", "/work/x"],
        ["start", "--port", "abc"],
        ["start", "--port", "0"],
        ["start", "--fixture", "Bad Name"],
        ["status", "extra"],
    ],
)
def test_usage_errors_exit_2_with_one_error_line(tree: Tree, args: list[str]) -> None:
    proc = tree.run(*args)
    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.startswith("error: ")
    assert len(proc.stderr.strip().splitlines()) == 1
    assert tree.record() is None


def test_skill_failures_print_to_stdout_and_exit_zero(tree: Tree) -> None:
    proc = tree.run("frobnicate", session="s1")
    assert proc.returncode == 0
    assert proc.stdout.startswith("error: ")
    assert proc.stderr == ""


def test_the_skill_cannot_run_the_hidden_actions(tree: Tree) -> None:
    for action in ("guard", "session-end"):
        proc = tree.run(action, session="s1")
        assert proc.returncode == 0
        assert proc.stdout.startswith("error: ")


# --------------------------------------------------------------------------
# Guard


@pytest.mark.parametrize(
    "command",
    [
        'python3 "/work/demo/app/bin/bartab.py" start',
        "python3 app/bin/bartab.py status",
        "/usr/bin/python3 -I /work/demo/app/bin/bartab.py stop",
        "FOO=1 python3 /work/demo/app/bin/bartab.py start",
        "cd /work/demo && python3 app/bin/bartab.py start",
        "ls; python3.12 app/bin/bartab.py",
        "echo hi | python3 app/bin/bartab.py",
        "echo $(python3 app/bin/bartab.py status)",
        "sudo python3 /work/demo/app/bin/bartab.py start",
        "exec python3 /work/demo/app/bin/bartab.py start",
        "python3 ${ROOT}/app/bin/bartab.py start",
        "python app/bin/bartab.py start",
        "/opt/homebrew/bin/python3.12 app/bin/bartab.py",
        "/work/demo/.venv/bin/python app/bin/bartab.py",
        "python3 -B -W ignore app/bin/bartab.py",
        "python3 - < app/bin/bartab.py",
        "cd app/bin && python3 bartab.py",
        "app/bin/bartab.py start",
        "/usr/bin/env python3 /work/demo/app/bin/bartab.py start",
        "env python3 app/bin/bartab.py",
        "env -i FOO=1 python3 app/bin/bartab.py",
        "env -u HOME python3 app/bin/bartab.py",
        "env FOO=1 BAR=2 python3.12 app/bin/bartab.py",
        "env -S 'python3 app/bin/bartab.py'",
        "env --split-string 'python3 app/bin/bartab.py'",
        "env --split-string='python3 app/bin/bartab.py'",
        "nice -n 5 python3 app/bin/bartab.py",
        "sudo -u root python3 app/bin/bartab.py",
        "bash -c 'python3 app/bin/bartab.py start'",
        'sh -c "python3 app/bin/bartab.py start"',
        'zsh -c "cd /work/demo; python3 app/bin/bartab.py"',
        "bash -lc 'FOO=\"a;b\" python3 app/bin/bartab.py'",
        "bash -c \"sh -c 'python3 app/bin/bartab.py'\"",
        "bash -c 'python3 app/bin/bartab.py",
        "eval 'python3 app/bin/bartab.py'",
        "uv run app/bin/bartab.py start",
        "uv run python app/bin/bartab.py",
        "uv run --no-project --directory /work/demo/app python3 bin/bartab.py",
        "/work/demo/app/scripts/uvw run app/bin/bartab.py",
        "/work/demo/app/scripts/uvw run --frozen --project /work/demo/app "
        "python bin/bartab.py",
        "uvw run --frozen env python3 app/bin/bartab.py",
    ],
)
def test_guard_denies_a_call_to_the_launcher(command: str) -> None:
    proc = subprocess.run(  # noqa: S603
        [PY3, str(LAUNCHER_SRC), "guard"],
        input=deny_input(command),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse"
    assert out["permissionDecision"] == "deny"
    assert "/bartab-preview" in out["permissionDecisionReason"]


@pytest.mark.parametrize(
    "payload",
    [
        deny_input("ls -la"),
        deny_input("cat /work/demo/app/bin/bartab.py"),
        deny_input("grep -n start /work/demo/app/bin/bartab.py"),
        deny_input("python3 -m pytest app/server/tests"),
        deny_input("python3 -m py_compile app/bin/bartab.py"),
        deny_input("python3 -m ruff check app/bin/bartab.py"),
        deny_input("python3 app/server/serve.py --help"),
        deny_input("sed -n 1,20p app/bin/bartab.py"),
        deny_input("ruff check app/bin/bartab.py"),
        deny_input("pyright app/bin/bartab.py"),
        deny_input("env FOO=1 cat app/bin/bartab.py"),
        deny_input("bash -c 'cat app/bin/bartab.py'"),
        deny_input('sh -c "grep -n guard app/bin/bartab.py"'),
        deny_input("uv run pytest server/tests/test_launcher.py"),
        deny_input("uvw run --project /work/demo/app ruff check bin/bartab.py"),
        deny_input("uv run ruff format --check app/bin/bartab.py"),
        deny_input("echo don't touch bartab.py"),
        deny_input("git status && echo done"),
        json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/work/x"}}),
    ],
)
def test_guard_allows_other_calls(payload: str) -> None:
    proc = subprocess.run(  # noqa: S603
        [PY3, str(LAUNCHER_SRC), "guard"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout == ""


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[1, 2]",
        "null",
        '"python3"',
        json.dumps({"tool_name": "Bash"}),
        json.dumps({"tool_name": "Bash", "tool_input": "ls"}),
        deny_input(7),
        deny_input(None),
        "\xff\xfe",
    ],
)
def test_guard_fails_closed_on_unreadable_input(payload: str) -> None:
    proc = subprocess.run(  # noqa: S603
        [PY3, str(LAUNCHER_SRC), "guard"],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# --------------------------------------------------------------------------
# Finding uv


def test_missing_uv_is_one_error_line_and_exit_2(tree: Tree) -> None:
    (tree.root / ".tools" / "uv" / "uv").unlink()
    proc = tree.start()
    assert proc.returncode == 2
    assert proc.stdout == ""
    lines = proc.stderr.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("error: uv not found")
    assert UV_INSTALL_URL in lines[0]
    assert tree.record() is None


def test_missing_uv_in_the_skill_is_a_stdout_line_and_exit_0(tree: Tree) -> None:
    (tree.root / ".tools" / "uv" / "uv").unlink()
    proc = tree.start("s1")
    assert proc.returncode == 0
    assert proc.stdout.startswith("error: uv not found")


def test_uv_is_found_in_the_contract_order(tree: Tree) -> None:
    tree.start().check_returncode()
    (tree.data / "uv" / "synced").unlink()
    tree.run("stop")
    # BARTAB_UV wins over the checkout's .tools/uv/uv.
    other = tree.install_uv(tree.root / "elsewhere" / "uv")
    other_log = tree.root / "other-log.jsonl"
    proc = tree.start(None, BARTAB_UV=str(other), FAKE_UV_LOG=str(other_log))
    assert proc.returncode == 0
    assert other_log.exists()
    tree.run("stop")
    # With the checkout's copy gone, uv on PATH is next, then ~/.local/bin.
    (tree.root / ".tools" / "uv" / "uv").unlink()
    (tree.data / "uv" / "synced").unlink()
    tree.install_uv(tree.home / ".local" / "bin" / "uv")
    assert tree.start().returncode == 0
    tree.run("stop")
    (tree.home / ".local" / "bin" / "uv").unlink()
    (tree.data / "uv" / "synced").unlink()
    path_uv = tree.install_uv(tree.root / "pathbin" / "uv")
    proc = tree.start(None, PATH=f"{path_uv.parent}:/usr/bin:/bin")
    assert proc.returncode == 0


def test_a_joining_session_needs_no_uv(tree: Tree) -> None:
    tree.start("a").check_returncode()
    (tree.root / ".tools" / "uv" / "uv").unlink()
    proc = tree.start("b")
    assert proc.returncode == 0
    assert URL_RE.search(proc.stdout)
    assert tree.sessions() == ["a", "b"]


# --------------------------------------------------------------------------
# First run, step lines and uv's environment


def test_first_run_prints_the_two_step_lines_and_starts(tree: Tree) -> None:
    proc = tree.start("s1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    lines = proc.stdout.splitlines()
    assert lines[0] == "Download Python: done"
    assert lines[1] == "Install the dashboard's packages: done"
    match = URL_RE.fullmatch(lines[2])
    assert match is not None
    assert (tree.data / "uv" / "synced").is_file()
    rec = tree.record()
    assert rec is not None
    assert rec["port"] == int(match.group(1))
    assert 47000 <= int(match.group(1)) <= 47999
    assert (tree.data / "port").read_text().strip() == match.group(1)


def test_uv_runs_frozen_under_the_data_folder(tree: Tree) -> None:
    tree.start().check_returncode()
    calls = tree.uv_calls()
    assert len(calls) == 1
    argv = calls[0]["argv"]
    app = tree.root / "app"
    assert argv == ["sync", "--frozen", "--project", str(app), "--no-dev"]
    env = calls[0]["env"]
    uv = tree.data / "uv"
    assert env["UV_CACHE_DIR"] == str(uv / "cache")  # type: ignore[index]
    assert env["UV_PYTHON_INSTALL_DIR"] == str(uv / "python")  # type: ignore[index]
    assert env["UV_PROJECT_ENVIRONMENT"] == str(uv / "env")  # type: ignore[index]
    assert env["UV_PYTHON_BIN_DIR"] == str(uv / "bin")  # type: ignore[index]
    assert env["UV_TOOL_DIR"] == str(uv / "tools")  # type: ignore[index]
    assert env["UV_PYTHON_INSTALL_BIN"] == "0"  # type: ignore[index]
    assert env["UV_PYTHON_PREFERENCE"] == "only-managed"  # type: ignore[index]


def test_a_later_start_has_no_step_lines_and_keeps_uv_offline(tree: Tree) -> None:
    tree.start().check_returncode()
    tree.run("stop").check_returncode()
    proc = tree.start(None, UV_OFFLINE="1")
    assert proc.returncode == 0
    assert "Download Python" not in proc.stdout
    assert URL_RE.search(proc.stdout)
    last = tree.uv_calls()[-1]
    assert last["argv"][:2] == ["sync", "--frozen"]  # type: ignore[index]
    assert last["env"]["UV_OFFLINE"] == "1"  # type: ignore[index]


def test_a_python_download_failure_says_to_connect_and_retry(tree: Tree) -> None:
    proc = tree.start(None, FAKE_UV_MODE="download_fail")
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["Download Python: failed"]
    err = proc.stderr.strip()
    assert err.startswith("error: couldn't download Python")
    assert "Connect to the internet and run the command again." in err
    assert len(err.splitlines()) == 1
    assert not (tree.data / "uv" / "synced").exists()
    assert tree.record() is None


def test_a_package_failure_marks_the_second_step_failed(tree: Tree) -> None:
    proc = tree.start(None, FAKE_UV_MODE="pkg_fail")
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == [
        "Download Python: done",
        "Install the dashboard's packages: failed",
    ]
    assert proc.stderr.startswith("error: couldn't install the dashboard's packages")
    assert "Connect to the internet" in proc.stderr
    assert not (tree.data / "uv" / "synced").exists()


def test_python_failure_markers(bartab: ModuleType) -> None:
    assert bartab.python_step_failed("error: No interpreter found for Python 3.13")
    assert bartab.python_step_failed("Failed to download https://x/cpython-3.13.tar.gz")
    assert not bartab.python_step_failed("Failed to download `fastapi==1`")
    assert bartab.network_failed("Failed to download `fastapi==1`")
    assert not bartab.network_failed("error: Dependencies are out of date")


# --------------------------------------------------------------------------
# The server, owners and the shared record


def test_the_server_starts_detached_from_app_server_with_the_contract_flags(
    tree: Tree,
) -> None:
    tree.start("s1").check_returncode()
    runs = tree.serve_runs()
    assert len(runs) == 1
    argv = tree.serve_argv()
    flags = dict(zip(argv[0::2], argv[1::2], strict=False))
    assert flags["--data"] == str(tree.data)
    assert flags["--project-dir"] == str(tree.project.resolve())
    assert flags["--idle-exit-minutes"] == "30"
    assert int(flags["--launch-fd"]) >= 3
    assert "--fixture" not in flags
    assert runs[0]["cwd"] == str((tree.root / "app" / "server").resolve())
    rec = tree.record()
    assert rec is not None
    assert rec["pid"] == runs[0]["pid"]
    # Detached, so it leads its own session and the launcher is not its parent.
    assert os.getsid(int(rec["pid"])) == int(rec["pid"])  # type: ignore[arg-type]
    ppid = subprocess.run(  # noqa: S603
        ["/bin/ps", "-o", "ppid=", "-p", str(rec["pid"])],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    assert int(ppid) != os.getpid()


def test_the_fixture_option_reaches_the_server(tree: Tree) -> None:
    tree.start(None, "--fixture", "firstrun").check_returncode()
    argv = tree.serve_argv()
    assert argv[argv.index("--fixture") + 1] == "firstrun"


def test_server_json_stays_private_and_keeps_the_servers_keys(tree: Tree) -> None:
    tree.start("s1").check_returncode()
    path = tree.data / "server.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert tree.data.stat().st_mode & 0o777 == 0o700
    rec = tree.record()
    assert rec is not None
    for key in ("port", "pid", "instance", "mint_secret", "started", "owners"):
        assert key in rec
    assert tree.sessions() == ["s1"]


def test_neither_the_secret_nor_a_second_code_leaks(tree: Tree) -> None:
    first = tree.start("a")
    second = tree.start("b")
    rec = tree.record()
    assert rec is not None
    secret = str(rec["mint_secret"])
    log = (tree.data / "logs" / "server.log").read_text()
    for text in (first.stdout, first.stderr, second.stdout, second.stderr, log):
        assert secret not in text
    code_a = URL_RE.search(first.stdout)
    code_b = URL_RE.search(second.stdout)
    assert code_a is not None
    assert code_b is not None
    assert code_a.group(2) != code_b.group(2)
    assert code_a.group(2) not in log
    assert code_b.group(2) not in log


def test_a_second_session_joins_the_running_server_with_a_fresh_code(
    tree: Tree,
) -> None:
    first = tree.start("a")
    second = tree.start("b")
    assert first.returncode == 0
    assert second.returncode == 0
    url_a = URL_RE.search(first.stdout)
    url_b = URL_RE.search(second.stdout)
    assert url_a is not None
    assert url_b is not None
    assert url_a.group(1) == url_b.group(1)
    assert url_a.group(2) != url_b.group(2)
    assert "Download Python" not in second.stdout
    assert len(tree.serve_runs()) == 1
    assert len(tree.uv_calls()) == 1
    assert tree.sessions() == ["a", "b"]
    mints = (tree.data / "mints.log").read_text().splitlines()
    assert json.loads(mints[0]) == {"project": "demo"}


def test_the_same_session_starting_twice_is_one_owner(tree: Tree) -> None:
    tree.start("a").check_returncode()
    tree.start("a").check_returncode()
    assert tree.sessions() == ["a"]


def test_a_start_by_hand_is_an_owner_no_hook_ends(tree: Tree) -> None:
    tree.start(None).check_returncode()
    assert tree.sessions() == [""]
    tree.run("session-end", stdin=json.dumps({"session_id": "zz", "reason": "other"}))
    time.sleep(1)
    assert tree.record() is not None


def test_requesting_another_port_or_fixture_for_a_running_server_says_so(
    tree: Tree,
) -> None:
    tree.start("a").check_returncode()
    proc = tree.start("b", "--fixture", "demo")
    assert "already running; run stop first" in proc.stdout


def test_a_busy_server_start_retries_on_the_next_port(tree: Tree) -> None:
    proc = tree.start(None, FAKE_SERVE_MODE="busy")
    assert proc.returncode == 1
    assert "the server stopped before it was ready: " in proc.stderr
    assert "could not bind" in proc.stderr
    assert len(tree.serve_runs()) == 3
    ports = [
        tree.serve_argv(i)[tree.serve_argv(i).index("--port") + 1]
        for i in range(len(tree.serve_runs()))
    ]
    assert len(set(ports)) == 3


def test_a_server_that_dies_at_once_is_reported_with_its_last_log_line(
    tree: Tree,
) -> None:
    proc = tree.start(None, FAKE_SERVE_MODE="silent")
    assert proc.returncode == 1
    assert proc.stderr.strip() == "error: the server stopped before it was ready: boom"
    assert len(tree.serve_runs()) == 1
    assert tree.record() is None


def test_a_launch_line_that_is_not_json_stops_the_server(tree: Tree) -> None:
    proc = tree.start(None, FAKE_SERVE_MODE="badline")
    assert proc.returncode == 1
    assert "a reply the launcher doesn't know" in proc.stderr
    runs = tree.serve_runs()
    pid = runs[0]["pid"]
    assert isinstance(pid, int)
    assert wait_for(lambda: not pid_alive(pid))


def test_asking_for_port_8377_picks_another_and_says_so(tree: Tree) -> None:
    proc = tree.start(None, "--port", "8377")
    assert proc.returncode == 0, proc.stderr
    assert "port 8377 is the old dashboard's" in proc.stdout
    match = URL_RE.search(proc.stdout)
    assert match is not None
    assert int(match.group(1)) != 8377
    assert "8377" not in tree.serve_argv()


def test_the_saved_port_is_reused_after_a_stop(tree: Tree) -> None:
    first = URL_RE.search(tree.start().stdout)
    assert first is not None
    tree.run("stop").check_returncode()
    second = URL_RE.search(tree.start().stdout)
    assert second is not None
    assert first.group(1) == second.group(1)


def test_owners_whose_claude_process_is_gone_stop_the_server(tree: Tree) -> None:
    tree.start("a").check_returncode()
    old_pid = tree.pid()
    dead = subprocess.Popen(["/usr/bin/true"])
    dead.wait()
    rec = tree.record()
    assert rec is not None
    rec["owners"] = [{"session": "x", "claude_pid": dead.pid, "claude_started": None}]
    (tree.data / "server.json").write_text(json.dumps(rec))
    proc = tree.start("b")
    assert "stopped the server: every session that used it has ended" in proc.stdout
    assert URL_RE.search(proc.stdout)
    new_pid = tree.pid()
    assert new_pid != old_pid
    assert not pid_alive(old_pid)
    assert tree.sessions() == ["b"]


def test_a_claude_pid_that_is_an_ancestor_is_recorded_as_the_owner(tree: Tree) -> None:
    tree.start("a", CLAUDE_PID=str(os.getpid())).check_returncode()
    rec = tree.record()
    assert rec is not None
    owner = rec["owners"][0]  # type: ignore[index]
    assert owner["claude_pid"] == os.getpid()
    assert owner["claude_started"]


def test_a_claude_pid_that_is_not_an_ancestor_is_ignored(tree: Tree) -> None:
    stranger = subprocess.Popen(["/bin/sleep", "30"])
    try:
        tree.start("a", CLAUDE_PID=str(stranger.pid)).check_returncode()
    finally:
        stranger.kill()
        stranger.wait()
    rec = tree.record()
    assert rec is not None
    assert rec["owners"][0]["claude_pid"] is None  # type: ignore[index]


# --------------------------------------------------------------------------
# code, status and stop


def test_code_without_a_server_is_an_error(tree: Tree) -> None:
    proc = tree.run("code", "--no-open")
    assert proc.returncode == 1
    assert proc.stderr.strip() == "error: no Bar Tab preview is running; run start"


def test_code_mints_a_fresh_link_for_the_running_server(tree: Tree) -> None:
    first = URL_RE.search(tree.start("a").stdout)
    proc = tree.run("code", "--no-open", session="a")
    assert proc.returncode == 0
    again = URL_RE.search(proc.stdout)
    assert first is not None
    assert again is not None
    assert first.group(1) == again.group(1)
    assert first.group(2) != again.group(2)
    assert tree.sessions() == ["a"]


def test_code_sends_the_servers_project_key_for_its_own_folder_only(
    tree: Tree,
) -> None:
    tree.start("a").check_returncode()
    (tree.root / "work" / "other").mkdir()
    tree.run("code", "--no-open", session="a").check_returncode()
    args = ("code", "--no-open", "--project", "../other")
    tree.run(*args, session="a").check_returncode()
    mints = (tree.data / "mints.log").read_text().splitlines()
    sent = [json.loads(line) for line in mints]
    assert sent == [{"project": "demo"}, {"project": None}]


def test_a_project_that_is_not_a_folder_is_an_error(tree: Tree) -> None:
    proc = tree.start(None, "--project", "/work/does-not-exist")
    assert proc.returncode == 1
    assert proc.stderr.startswith("error: not a folder")


def test_status_reports_the_running_server(tree: Tree) -> None:
    assert tree.run("status").stdout.strip() == "No Bar Tab preview is running."
    tree.start("a").check_returncode()
    tree.start("b").check_returncode()
    out = tree.run("status").stdout
    port = tree.record()["port"]  # type: ignore[index]
    assert f"http://127.0.0.1:{port}/" in out
    assert "sessions 2" in out
    assert "code=" not in out


def test_status_cleans_up_a_record_whose_process_is_gone(tree: Tree) -> None:
    tree.start("a").check_returncode()
    rec = tree.record()
    assert rec is not None
    pid = int(rec["pid"])  # type: ignore[arg-type]
    os.kill(pid, signal.SIGKILL)
    assert wait_for(lambda: not pid_alive(pid))
    assert "No Bar Tab preview is running." in tree.run("status").stdout
    assert tree.record() is None


def test_a_pid_that_is_not_the_server_is_never_signalled(tree: Tree) -> None:
    tree.data.mkdir()
    rec: dict[str, object] = {
        "port": 47999,
        "pid": os.getpid(),
        "instance": "x",
        "mint_secret": "y",
        "owners": [],
    }
    (tree.data / "server.json").write_text(json.dumps(rec))
    proc = tree.run("stop")
    assert "No Bar Tab preview is running." in proc.stdout
    assert tree.record() is None
    assert pid_alive(os.getpid())


def test_an_unreadable_server_record_is_removed(tree: Tree) -> None:
    tree.data.mkdir()
    (tree.data / "server.json").write_text("{not json")
    proc = tree.run("status")
    assert "cleaned up an unreadable server record" in proc.stdout
    assert tree.record() is None


def test_stop_ends_the_server_and_leaves_no_process(tree: Tree) -> None:
    tree.start("a").check_returncode()
    rec = tree.record()
    assert rec is not None
    pid = int(rec["pid"])  # type: ignore[arg-type]
    proc = tree.run("stop")
    assert proc.stdout.strip() == f"Stopped Bar Tab (port {rec['port']})."
    assert wait_for(lambda: not pid_alive(pid))
    assert tree.record() is None
    assert tree.run("stop").stdout.strip() == "No Bar Tab preview is running."


def test_guard_denies_a_call_nested_deeper_than_it_looks() -> None:
    command = "python3 app/bin/bartab.py start"
    for _ in range(7):
        command = f"bash -c {shlex.quote(command)}"
    proc = subprocess.run(  # noqa: S603
        [PY3, str(LAUNCHER_SRC), "guard"],
        input=deny_input(command),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


# --------------------------------------------------------------------------
# Whose process it is


def fake_process(
    monkeypatch: pytest.MonkeyPatch,
    bartab: ModuleType,
    command: str,
    *,
    alive: bool = True,
) -> list[int]:
    """Fake one process. Returns the list its signals land in."""
    sent: list[int] = []

    def pid_exists(_pid: int) -> bool:
        return alive

    def ps_command(_pid: int) -> str:
        return command

    def kill(pid: int, _sig: int) -> None:
        sent.append(pid)

    monkeypatch.setattr(bartab, "pid_exists", pid_exists)
    monkeypatch.setattr(bartab, "ps_command", ps_command)
    monkeypatch.setattr(bartab.os, "kill", kill)
    return sent


def test_process_ours_wants_this_serve_and_this_data_folder(
    bartab: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = (tmp_path / "my data").resolve()
    other = (tmp_path / "other").resolve()
    serve = str(bartab.SERVE.resolve())
    ctx = bartab.Ctx(data, None, tmp_path)
    rec = bartab.Record(47001, 4242, "x", "y", [], {})
    cases = {
        f"/p/python -B {serve} --port 47001 --data {data} --launch-fd 5": True,
        f"python -B {serve} --data {data}": True,
        "python -m pytest tests/test_launcher.py tests/test_serve.py": False,
        "vim server/serve.py": False,
        f"python /work/other/app/server/serve.py --data {data}": False,
        f"python {serve} --port 47001 --data {other}": False,
        f"python {serve} --port 47001": False,
        f"python {serve} --data {data}-2": False,
        f"python {serve}x --data {data}": False,
        f"python x{serve} --data {data}": False,
        f"python {serve}": False,
        "": False,
    }
    for command, expected in cases.items():
        fake_process(monkeypatch, bartab, command)
        assert bartab.process_ours(ctx, rec) is expected, command
    fake_process(monkeypatch, bartab, f"python {serve} --data {data}", alive=False)
    assert bartab.process_ours(ctx, rec) is False


def test_stop_never_signals_a_process_that_only_mentions_serve_py(
    bartab: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = bartab.Ctx((tmp_path / "data").resolve(), None, tmp_path)
    rec = bartab.Record(47001, 4242, "x", "y", [], {})
    sent = fake_process(monkeypatch, bartab, "python -m pytest test_serve.py")
    assert bartab.stop_process(ctx, rec) is False
    assert sent == []


@pytest.mark.skipif(
    os.environ.get("BARTAB_NESTED_PYTEST") == "1",
    reason="this is the nested run",
)
def test_launcher_and_serve_tests_pass_when_run_serially() -> None:
    """D1 regression: no `-n`, so pytest itself is the process the old check hit."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "server/tests/test_launcher.py",
            "server/tests/test_serve.py",
        ],
        cwd=HERE.parent.parent,
        env={**os.environ, "BARTAB_NESTED_PYTEST": "1"},
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]


# --------------------------------------------------------------------------
# SessionEnd, spike 2


def end_payload(session: str, reason: str = "other") -> str:
    """The SessionEnd hook's stdin."""
    return json.dumps({"session_id": session, "reason": reason})


def test_session_end_removes_one_owner_and_stops_with_the_last(tree: Tree) -> None:
    tree.start("a").check_returncode()
    tree.start("b").check_returncode()
    rec = tree.record()
    assert rec is not None
    pid = int(rec["pid"])  # type: ignore[arg-type]
    first = tree.run("session-end", stdin=end_payload("a"))
    assert first.returncode == 0
    assert first.stdout == ""
    assert wait_for(lambda: tree.record() is not None and tree.sessions() == ["b"])
    assert pid_alive(pid)
    second = tree.run("session-end", stdin=end_payload("b"))
    assert second.returncode == 0
    assert wait_for(lambda: tree.record() is None)
    assert wait_for(lambda: not pid_alive(pid))


def test_session_end_for_clear_and_resume_changes_nothing(tree: Tree) -> None:
    tree.start("a").check_returncode()
    for reason in ("clear", "resume"):
        tree.run("session-end", stdin=end_payload("a", reason)).check_returncode()
    time.sleep(1)
    assert tree.sessions() == ["a"]


def test_session_end_for_an_unknown_session_changes_nothing(tree: Tree) -> None:
    tree.start("a").check_returncode()
    tree.run("session-end", stdin=end_payload("nobody")).check_returncode()
    time.sleep(1)
    assert tree.sessions() == ["a"]


@pytest.mark.parametrize(
    "payload",
    ["", "not json", "[]", '{"session_id": 5}', '{"session_id": "bad id!"}', "{}"],
)
def test_session_end_ignores_unreadable_input(tree: Tree, payload: str) -> None:
    tree.start("a").check_returncode()
    proc = tree.run("session-end", stdin=payload)
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""
    time.sleep(0.5)
    assert tree.sessions() == ["a"]


def test_session_end_with_no_data_folder_is_silent(tree: Tree) -> None:
    proc = tree.run("session-end", stdin=end_payload("a"))
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert not tree.data.exists()


def test_session_end_by_claude_pid_removes_that_process_owner(tree: Tree) -> None:
    tree.start("a", CLAUDE_PID=str(os.getpid())).check_returncode()
    tree.start("b").check_returncode()
    tree.run(
        "session-end",
        stdin=end_payload("a"),
        CLAUDE_PID=str(os.getpid()),
    ).check_returncode()
    assert wait_for(lambda: tree.sessions() == ["b"])


# --------------------------------------------------------------------------
# Ports, in process


def test_port_choice_never_probes_or_returns_8377(
    bartab: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    probed: list[int] = []

    def fake_free(port: int) -> bool:
        probed.append(port)
        return True

    monkeypatch.setattr(bartab, "port_free", fake_free)
    monkeypatch.setattr(bartab, "PORT_LOW", 8376)
    monkeypatch.setattr(bartab, "PORT_HIGH", 8379)
    ctx = bartab.Ctx(tmp_path, None, tmp_path)
    assert bartab.pick_port(ctx, None) == (8376, "")
    assert bartab.pick_port(ctx, None, (8376,))[0] == 8378
    port, note = bartab.pick_port(ctx, 8377)
    assert port == 8376
    assert "8377" in note
    assert 8377 not in probed


def test_port_choice_skips_busy_ports_and_prefers_the_saved_one(
    bartab: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    busy = {47000, 47001, 47010}

    def free(port: int) -> bool:
        return port not in busy

    monkeypatch.setattr(bartab, "port_free", free)
    ctx = bartab.Ctx(tmp_path, None, tmp_path)
    assert bartab.pick_port(ctx, None)[0] == 47002
    (tmp_path / "port").write_text("47005\n")
    assert bartab.pick_port(ctx, None)[0] == 47005
    (tmp_path / "port").write_text("47010\n")
    assert bartab.pick_port(ctx, None)[0] == 47002
    (tmp_path / "port").write_text("9999\n")
    assert bartab.pick_port(ctx, None)[0] == 47002
    assert bartab.pick_port(ctx, 47003) == (47003, "")


def test_an_asked_port_that_is_busy_is_an_error(
    bartab: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    def free(port: int) -> bool:
        return port != 47123

    monkeypatch.setattr(bartab, "port_free", free)
    ctx = bartab.Ctx(tmp_path, None, tmp_path)
    with pytest.raises(bartab.Fail, match="port 47123 is in use"):
        bartab.pick_port(ctx, 47123)


def test_port_choice_fails_when_the_whole_range_is_busy(
    bartab: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:

    def none_free(port: int) -> bool:
        return False

    monkeypatch.setattr(bartab, "port_free", none_free)
    monkeypatch.setattr(bartab, "PORT_HIGH", bartab.PORT_LOW + 2)
    ctx = bartab.Ctx(tmp_path, None, tmp_path)
    with pytest.raises(bartab.Fail, match="no free port"):
        bartab.pick_port(ctx, None)


def test_port_free_sees_a_listening_socket(bartab: ModuleType) -> None:
    import socket

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        assert not bartab.port_free(port)
    assert bartab.port_free(port)


# --------------------------------------------------------------------------
# Owners, in process


def owner(
    session: str, pid: int | None = None, started: str | None = None
) -> dict[str, Any]:
    """An owner entry."""
    return {"session": session, "claude_pid": pid, "claude_started": started}


def record(bartab: ModuleType, owners: list[dict[str, Any]]) -> Any:
    """A Record with the given owners."""
    return bartab.Record(47000, 1, "i", "s", owners, {})


def test_add_owner_dedupes_by_process_or_by_session(bartab: ModuleType) -> None:
    rec = record(bartab, [])
    bartab.add_owner(rec, owner("a"))
    bartab.add_owner(rec, owner("a"))
    bartab.add_owner(rec, owner("b"))
    assert [o["session"] for o in rec.owners] == ["a", "b"]  # type: ignore[attr-defined]
    bartab.add_owner(rec, owner("c", 99, "t1"))
    bartab.add_owner(rec, owner("d", 99, "t1"))
    bartab.add_owner(rec, owner("e", 99, "t2"))
    assert [o["session"] for o in rec.owners] == ["a", "b", "c", "e"]  # type: ignore[attr-defined]


def test_owner_alive_judges_by_pid_and_start_time(bartab: ModuleType) -> None:
    assert bartab.owner_alive(owner("a"))
    assert bartab.owner_alive(owner("a", os.getpid()))
    assert not bartab.owner_alive(owner("a", os.getpid(), "Mon Jan  1 00:00:00 1990"))
    dead = subprocess.Popen(["/usr/bin/true"])
    dead.wait()
    assert not bartab.owner_alive(owner("a", dead.pid))


def test_valid_record_rejects_a_record_missing_a_field(bartab: ModuleType) -> None:
    good: dict[str, object] = {
        "port": 47000,
        "pid": 5,
        "instance": "i",
        "mint_secret": "s",
        "owners": [],
    }
    assert bartab.valid_record(good) is not None
    for key in ("port", "pid", "instance", "mint_secret"):
        broken = {k: v for k, v in good.items() if k != key}
        assert bartab.valid_record(broken) is None
    assert bartab.valid_record({**good, "port": True}) is None
    assert bartab.valid_record({**good, "port": 70000}) is None
    assert bartab.valid_record([good]) is None
    rec = bartab.valid_record(
        {**good, "owners": [1, {"claude_pid": "x"}, {"session": "s"}]}
    )
    assert [o["session"] for o in rec.owners] == ["s"]


def test_save_record_keeps_keys_the_launcher_does_not_know(
    bartab: ModuleType, tmp_path: Path
) -> None:
    ctx = bartab.Ctx(tmp_path, None, tmp_path)
    raw: dict[str, object] = {
        "port": 47000,
        "pid": 5,
        "instance": "i",
        "mint_secret": "s",
        "owners": [],
        "extra": {"k": 1},
    }
    rec = bartab.valid_record(raw)
    bartab.add_owner(rec, owner("a"))
    bartab.save_record(ctx, rec)
    saved = json.loads((tmp_path / "server.json").read_text())
    assert saved["extra"] == {"k": 1}
    assert saved["owners"] == [owner("a")]
    assert (tmp_path / "server.json").stat().st_mode & 0o777 == 0o600


# --------------------------------------------------------------------------
# Browser


class Recorder:
    """A webbrowser controller that records its calls."""

    def __init__(self, result: bool = True) -> None:
        """Set what open returns."""
        self.result = result
        self.calls: list[tuple[str, int]] = []

    def open(self, url: str, new: int = 0, autoraise: bool = True) -> bool:
        """Record the call."""
        self.calls.append((url, new))
        return self.result


@pytest.fixture
def browsers(monkeypatch: pytest.MonkeyPatch) -> list[Recorder]:
    """Replace webbrowser's registry, and fail if webbrowser.open is called (I-14ae)."""
    monkeypatch.setattr(webbrowser, "_browsers", {})
    monkeypatch.setattr(webbrowser, "_tryorder", [])

    message = "webbrowser.open falls through to the next browser"

    def forbidden(*args: object, **kwargs: object) -> bool:
        raise AssertionError(message)

    monkeypatch.setattr(webbrowser, "open", forbidden)
    monkeypatch.delenv("SSH_CONNECTION", raising=False)
    monkeypatch.delenv("SSH_TTY", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    return []


def test_the_browser_opens_through_get_open(
    bartab: ModuleType, browsers: list[Recorder]
) -> None:
    rec = Recorder()
    webbrowser.register("rec", None, rec, preferred=True)  # type: ignore[arg-type]
    state, line = bartab.open_browser("http://127.0.0.1:47000/#/?code=a.b", False)
    assert (state, line) == ("opened", "")
    assert rec.calls == [("http://127.0.0.1:47000/#/?code=a.b", 2)]


def test_a_failing_browser_does_not_fall_through_to_the_next(
    bartab: ModuleType, browsers: list[Recorder]
) -> None:
    first = Recorder(result=False)
    second = Recorder()
    webbrowser.register("second", None, second)  # type: ignore[arg-type]
    webbrowser.register("first", None, first, preferred=True)  # type: ignore[arg-type]
    state, line = bartab.open_browser("http://127.0.0.1:47000/", False)
    assert (state, line) == ("failed", "Couldn't open a browser.")
    assert len(first.calls) == 1
    assert second.calls == []


def test_no_open_ssh_and_missing_display_skip_the_browser(
    bartab: ModuleType, browsers: list[Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    rec = Recorder()
    webbrowser.register("rec", None, rec, preferred=True)  # type: ignore[arg-type]
    assert bartab.open_browser("http://x/", True) == ("skipped", "")
    monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 1 5.6.7.8 22")
    assert bartab.open_browser("http://x/", False) == (
        "skipped",
        "Not opening a browser over SSH.",
    )
    monkeypatch.delenv("SSH_CONNECTION")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert bartab.open_browser("http://x/", False) == (
        "skipped",
        "No display found, so no browser opened.",
    )
    assert rec.calls == []


def test_start_opens_the_link_through_the_browser_variable(tree: Tree) -> None:
    proc = tree.run("start", session="a", BROWSER=tree.install_browser())
    assert proc.returncode == 0, proc.stderr
    assert "Opened in your browser." in proc.stdout
    match = URL_RE.search(proc.stdout)
    assert match is not None
    opened = tree.browser_log.read_text().splitlines()
    assert opened == [f"http://127.0.0.1:{match.group(1)}/#/?code={match.group(2)}"]


def test_a_failing_browser_is_reported_and_tried_once(tree: Tree) -> None:
    proc = tree.run("start", session="a", BROWSER=tree.install_browser(exit_code=1))
    assert proc.returncode == 0
    assert "Couldn't open a browser." in proc.stdout
    assert len(tree.browser_log.read_text().splitlines()) == 1
    assert URL_RE.search(proc.stdout)


def test_no_open_never_calls_the_browser(tree: Tree) -> None:
    tree.start("a", BROWSER=tree.install_browser()).check_returncode()
    assert not tree.browser_log.exists()


def test_code_opens_a_new_link_in_the_browser(tree: Tree) -> None:
    tree.start("a").check_returncode()
    proc = tree.run("code", session="a", BROWSER=tree.install_browser())
    assert "Opened in your browser." in proc.stdout
    assert len(tree.browser_log.read_text().splitlines()) == 1
