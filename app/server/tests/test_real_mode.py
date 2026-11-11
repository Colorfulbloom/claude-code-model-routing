"""Tests for ``serve.py --real``, the server side of Bar Tab's real-data mode.

Real mode reads the owner's own Claude folder, so every server here runs as a
subprocess against a fake HOME inside ``tmp_path``, with an explicit environment that
names that HOME and CLAUDE_CONFIG_DIR and nothing else of the parent's. The write
guard is a Python audit hook that can't be removed, so it never runs in the test
process. The tests check that nothing outside ``.claude/routing-dashboard/bartab/``
is written, and that a write outside it is refused.
"""

import ast
import hashlib
import json
import os
import random
import select
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h

import main
import serve
import store_provider

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO = SERVER_DIR.parents[1]
SERVE = SERVER_DIR / "serve.py"
PRICE_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prices"
PORT_RANGE = (47000, 47999)
STORE = Path(".claude") / "routing-dashboard" / "bartab"
OLD_APP_DIR = Path(".claude") / "routing-dashboard"
CRAFTED_VERSION = "2.1.999"
CRAFTED_FOLDER = "-work-real-check"
CRAFTED_SESSION = "44444444-4444-4444-8444-444444444444"
INDEX = "<!doctype html><html><head></head><body></body></html>"
GUARD_LOG_MARK = "write guard refused"


# ------------------------------------------------------------------ the fake home


@dataclass(frozen=True)
class Home:
    """A fake HOME with a Claude folder in it, all inside ``tmp_path``."""

    root: Path
    home: Path
    config: Path
    dist: Path
    project: Path

    @property
    def store(self) -> Path:
        return self.config / "routing-dashboard" / "bartab"

    def env(self) -> dict[str, str]:
        """An explicit environment. Nothing of the parent's HOME is inherited."""
        return {
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.config),
            "BARTAB_OFFLINE": "1",
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
        }


def crafted_row() -> bytes:
    """One assistant row that carries a top-level ``version``."""
    row = json.loads(h.assistant(0, "msg_version", sid=CRAFTED_SESSION, cwd="/work/x"))
    row["timestamp"] = "2026-10-29T12:00:00.000Z"
    row["version"] = CRAFTED_VERSION
    return json.dumps(row).encode()


def make_home(tmp_path: Path, demo_build: Path, *, with_projects: bool = True) -> Home:
    """Build a fake HOME holding the demo's transcripts and a set of old-app files."""
    home = tmp_path.resolve() / "home"
    config = home / ".claude"
    config.mkdir(parents=True)
    if with_projects:
        shutil.copytree(demo_build / "config" / "projects", config / "projects")
        crafted = config / "projects" / CRAFTED_FOLDER / f"{CRAFTED_SESSION}.jsonl"
        crafted.parent.mkdir()
        crafted.write_bytes(crafted_row() + b"\n")
    (config / "settings.json").write_text('{"model": "claude-sonnet-5-5"}\n')
    (config / "agents").mkdir()
    (config / "agents" / "x.md").write_text("---\nname: x\n---\nA test agent.\n")
    old = config / "routing-dashboard"
    (old / "backups" / "a").mkdir(parents=True)
    (old / "backups" / "a" / "ledger.json").write_text("[]\n")
    (old / ".lock").write_bytes(b"")
    (old / "x.bak").write_text("old\n")
    (config / "routing-dashboard.json").write_text(
        json.dumps({"projects": [], "plan": "subscription"}) + "\n"
    )
    (home / ".claude.json").write_text('{"userID": "x"}\n')
    dist = tmp_path.resolve() / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    project = tmp_path.resolve() / "work" / "real-check"
    return Home(tmp_path.resolve(), home, config, dist, project)


def listing(home: Home) -> dict[str, tuple[Any, ...]]:
    """Everything under the HOME except the Bar Tab store, as a comparable map.

    A file keeps its bytes (a hash), size and mtime. A folder keeps its mtime, so an
    entry added or removed shows. The old app's folder is skipped for its mtime only,
    because the store folder is made inside it.
    """
    out: dict[str, tuple[Any, ...]] = {"": ("d", home.home.stat().st_mtime_ns)}
    for base, folders, files in os.walk(home.home):
        for name in sorted(folders):
            full = Path(base) / name
            rel = full.relative_to(home.home)
            if rel == STORE:
                folders.remove(name)
                continue
            mtime = None if rel == OLD_APP_DIR else full.stat().st_mtime_ns
            out[str(rel)] = ("d", mtime)
        for name in sorted(files):
            full = Path(base) / name
            data = full.read_bytes()
            out[str(full.relative_to(home.home))] = (
                "f",
                hashlib.sha256(data).hexdigest(),
                len(data),
                full.stat().st_mtime_ns,
            )
    return out


def git_status() -> str:
    """The checkout's status over the server and launcher code, as git prints it."""
    done = subprocess.run(
        ["git", "status", "--porcelain", "--", "app/server", "app/bin"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return done.stdout


# ------------------------------------------------------------------ the server


def free_port() -> int:
    """A port in 47000-47999 that binds right now."""
    ports = list(range(PORT_RANGE[0], PORT_RANGE[1] + 1))
    random.shuffle(ports)
    for port in ports:
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    pytest.fail("no free port in 47000-47999")


def read_line(fd: int, timeout: float = 60.0) -> dict[str, Any]:
    """Read one JSON line from the launch pipe."""
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


@dataclass
class Server:
    """A running ``serve.py --real`` and what its launch line gave."""

    process: subprocess.Popen[bytes]
    log: Path
    port: int
    key: str
    project: str | None

    def get(self, path: str) -> Any:
        reply = httpx2.get(
            f"http://127.0.0.1:{self.port}{path}",
            headers={"X-Bartab-Key": self.key},
            timeout=10,
        )
        assert reply.status_code == 200, (path, reply.status_code)
        return reply.json()

    def wait_until(
        self, check: Callable[[], bool], what: str, seconds: float = 90.0
    ) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            assert self.process.poll() is None, f"the server stopped ({what})"
            if check():
                return
            time.sleep(0.1)
        pytest.fail(f"timed out waiting for {what}")

    def stop(self) -> int:
        """SIGTERM the server and wait for the clean stop. Returns the exit code."""
        self.process.send_signal(signal.SIGTERM)
        return self.process.wait(timeout=60)


RUNNER = """
import dataclasses
import pathlib
import socket
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, {server_dir!r})

import price_transport
import serve

FIXTURES = pathlib.Path({fixtures!r})
real_connect = socket.socket.connect


def loopback_only(self, address):
    if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1"):
        raise RuntimeError("the runner reaches no network")
    return real_connect(self, address)


socket.socket.connect = loopback_only


class OfflineTransport:
    def fetch(self, url, *, timeout, max_bytes):
        name = "litellm_good.json" if "litellm" in url else "openrouter_agree.json"
        return (FIXTURES / name).read_bytes()


price_transport.UrllibTransport = OfflineTransport
parse = serve.parse_args
serve.parse_args = lambda argv=None: dataclasses.replace(
    parse(argv), no_price_fetch=False
)
sys.exit(serve.main())
"""


@contextmanager
def running(
    home: Home, tmp_path: Path, *, runner: bool = False, **env: str
) -> Generator[Server]:
    """Start ``--real`` the way the launcher does, and stop it on exit.

    With ``runner`` the server starts through a small script that swaps the price
    network for a canned one, so a price copy can happen with no network. It calls
    ``serve.main``, so everything else is the same code.
    """
    assert home.config.resolve().is_relative_to(tmp_path.resolve())
    assert home.home.resolve().is_relative_to(tmp_path.resolve())
    log = tmp_path.resolve() / "server.log"
    script = tmp_path.resolve() / "runner.py"
    script.write_text(
        textwrap.dedent(RUNNER).format(
            server_dir=str(SERVER_DIR), fixtures=str(PRICE_FIXTURES)
        )
    )
    entry = script if runner else SERVE
    process: subprocess.Popen[bytes] | None = None
    read_fd = -1
    line: dict[str, Any] = {}
    for _attempt in range(3):
        port = free_port()
        read_fd, write_fd = os.pipe()
        with log.open("ab") as log_file:
            process = subprocess.Popen(  # noqa: S603
                [
                    sys.executable,
                    "-B",
                    str(entry),
                    "--real",
                    "--port",
                    str(port),
                    "--project-dir",
                    str(home.project),
                    "--idle-exit-minutes",
                    "30",
                    "--launch-fd",
                    str(write_fd),
                    "--dist",
                    str(home.dist),
                ],
                cwd=SERVER_DIR,
                env={**home.env(), **env},
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=log_file,
                pass_fds=(write_fd,),
            )
        os.close(write_fd)
        try:
            line = read_line(read_fd)
            break
        except AssertionError:
            process.kill()
            process.wait()
            os.close(read_fd)
            if "could not bind" not in log.read_text(errors="replace"):
                raise
    assert process is not None
    keys = httpx2.post(
        f"http://127.0.0.1:{line['port']}/api/access/swap",
        json={"code": line["code"]},
        timeout=10,
    ).json()
    server = Server(process, log, line["port"], keys["read_key"], line["project"])
    try:
        yield server
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(read_fd)


def exercise(server: Server, home: Home) -> None:
    """First run, the app, the session list and one timeline, as a page would."""
    server.wait_until(
        lambda: server.get("/api/app")["ingest"]["state"] == "done", "first run"
    )
    app = server.get("/api/app")
    assert app["mode"] == "real"
    assert app["clock"]["kind"] == "real"
    assert app["claude_version"] == CRAFTED_VERSION
    assert app["history"]["first_ingest"] is not None
    assert (home.store / "run" / "health.json").is_file()
    projects = server.get("/api/projects")["projects"]
    assert server.project in {p["key"] for p in projects}
    # The project mapping is cached for 5 s, so a project can read as empty at first.
    ended: dict[str, Any] = {}

    def find_ended() -> bool:
        for item in server.get("/api/projects")["projects"]:
            live = server.get(f"/api/live/sessions?project={item['key']}")
            assert live["sessions"] == []  # the demo's transcripts are days old
            if live["latest_ended"] is not None:
                ended.update(live["latest_ended"], project=item["key"])
                return True
        return False

    server.wait_until(find_ended, "an ended session", seconds=30)
    timeline = server.get(
        f"/api/sessions/{ended['id']}/timeline?project={ended['project']}"
    )
    assert timeline["session"]["id"] == ended["id"]
    assert timeline["totals"]["requests"] > 0


def finish(server: Server, home: Home, before: dict[str, tuple[Any, ...]]) -> None:
    """Stop the server and check that nothing outside the store changed."""
    assert server.stop() == 0
    log = server.log.read_text(errors="replace")
    assert "shutdown complete" in log
    assert GUARD_LOG_MARK not in log
    assert "Traceback" not in log
    after = listing(home)
    assert after == before, sorted(
        {k for k in {*before, *after} if before.get(k) != after.get(k)}
    )
    new = {
        p.relative_to(home.home)
        for p in home.home.rglob("*")
        if p.relative_to(home.home).parts[:3] == STORE.parts
    }
    assert Path(".claude/routing-dashboard/bartab/bartab.db") in new
    assert Path(".claude/routing-dashboard/bartab/writer.lock") in new
    store = home.store
    assert not (store / "run" / "server.json").exists()
    assert any((store / "db-backups").iterdir())
    assert (store / "tmp").is_dir()
    assert (store / "run" / "health.json").is_file()


@pytest.fixture
def home(tmp_path: Path, demo_build: Path) -> Home:
    return make_home(tmp_path, demo_build)


# ------------------------------------------------------------------ the server runs


def test_real_server_reads_the_fake_home_and_writes_only_its_store(
    home: Home, tmp_path: Path
) -> None:
    before = listing(home)
    status = git_status()
    with running(home, tmp_path) as server:
        exercise(server, home)
        health = json.loads((home.store / "run" / "health.json").read_text())
        assert set(health) == {"at", "hot_pass_ms", "cold_pass_ms", "lag_ms"}
        for name in ("hot_pass_ms", "cold_pass_ms"):
            assert isinstance(health[name], int)
        assert str(home.home) not in json.dumps(health)
        finish(server, home, before)
    assert git_status() == status


def test_real_server_makes_a_price_copy_and_a_backup_with_no_network(
    home: Home, tmp_path: Path
) -> None:
    before = listing(home)
    status = git_status()
    with running(home, tmp_path, runner=True) as server:
        exercise(server, home)
        server.wait_until(
            (home.store / "prices" / "last-good.json").is_file,
            "the price copy",
        )
        prices = server.get("/api/prices")
        assert prices["source"] != "bundled"
        finish(server, home, before)
    assert git_status() == status


def test_a_claude_folder_with_no_projects_reports_config_dir_missing(
    tmp_path: Path, demo_build: Path
) -> None:
    home = make_home(tmp_path, demo_build, with_projects=False)
    before = listing(home)
    with running(home, tmp_path) as server:
        server.wait_until(
            lambda: server.get("/api/app")["ingest"]["state"] == "failed", "the failure"
        )
        error = server.get("/api/app")["ingest"]["error"]
        assert error["code"] == "config_dir_missing"
        assert server.stop() == 0
    log = server.log.read_text(errors="replace")
    assert GUARD_LOG_MARK not in log
    after = listing(home)
    assert after == before


def test_a_missing_claude_folder_stops_the_server_and_creates_nothing(
    tmp_path: Path,
) -> None:
    home = tmp_path.resolve() / "home"
    home.mkdir()
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-B", str(SERVE), "--real", "--port", str(free_port())],
        cwd=SERVER_DIR,
        env={
            "HOME": str(home),
            "CLAUDE_CONFIG_DIR": str(home / ".claude"),
            "PATH": "/usr/bin:/bin",
        },
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 1
    assert "the Claude folder does not exist" in done.stderr
    assert list(home.iterdir()) == []


# ------------------------------------------------------------------ the guard


GUARD_SCRIPT = """
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, {server_dir!r})

import serve

args = serve.parse_args(["--real", "--idle-exit-minutes", "0"])
assert serve.enter_real_mode(args)
config = Path(os.environ["CLAUDE_CONFIG_DIR"])
outside = {{
    "settings": lambda: (config / "settings.json").write_text("{{}}"),
    "new_file": lambda: (config / "new.txt").write_text("x"),
    "old_app_file": lambda: (config / "routing-dashboard" / "x.bak").write_text("x"),
    "old_app_json": lambda: (config / "routing-dashboard.json").write_text("{{}}"),
    "mkdir": lambda: (config / "made").mkdir(),
    "rename": lambda: os.replace(
        config / "routing-dashboard" / "x.bak", config / "bartab-took-it"
    ),
    "unlink": lambda: (config / "routing-dashboard" / ".lock").unlink(),
    "sqlite": lambda: sqlite3.connect(str(config / "outside.db")).execute(
        "CREATE TABLE t (x)"
    ),
    "home_file": lambda: (config.parent / "stray.txt").write_text("x"),
}}
refused = {{}}
for name, attempt in outside.items():
    try:
        attempt()
    except PermissionError:
        refused[name] = True
    else:
        refused[name] = False
inside = args.store / "tmp" / "inside.txt"
inside.write_text("ok")
print(
    json.dumps(
        {{
            "refused": refused,
            "inside": inside.read_text(),
            "read": (config / "settings.json").read_text(),
            "tmpdir": os.environ["TMPDIR"],
            "tempdir": tempfile.tempdir,
            "no_bytecode": sys.dont_write_bytecode,
            "tmp_mode": (args.store / "tmp").stat().st_mode & 0o777,
            "run_mode": (args.store / "run").stat().st_mode & 0o777,
        }}
    )
)
"""


def test_the_guard_refuses_a_write_outside_the_store_root(
    home: Home, tmp_path: Path
) -> None:
    script = tmp_path / "guard_script.py"
    script.write_text(GUARD_SCRIPT.format(server_dir=str(SERVER_DIR)))
    assert home.config.resolve().is_relative_to(tmp_path.resolve())
    before = listing(home)
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-B", str(script)],
        cwd=SERVER_DIR,
        env=home.env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    result = json.loads(done.stdout)
    assert result["refused"] == dict.fromkeys(result["refused"], True)
    assert len(result["refused"]) == 9
    assert result["inside"] == "ok"
    assert result["read"] == '{"model": "claude-sonnet-5-5"}\n'
    # Real mode points every temp file at its own folder and writes no bytecode.
    assert result["tmpdir"] == str(home.store / "tmp")
    assert result["tempdir"] == str(home.store / "tmp")
    assert result["no_bytecode"] is True
    assert (result["tmp_mode"], result["run_mode"]) == (0o700, 0o700)
    assert listing(home) == before
    assert GUARD_LOG_MARK in done.stderr
    assert str(home.home) not in done.stderr  # a refusal never names the path


def test_the_guard_script_would_see_a_write_succeed_without_the_guard(
    home: Home, tmp_path: Path
) -> None:
    """Prove the guard script's probes bite: with no guard the same write works."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import os, pathlib\n"
        "p = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / 'new.txt'\n"
        "p.write_text('x')\n"
    )
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-B", str(probe)],
        env=home.env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0
    assert (home.config / "new.txt").is_file()


# ------------------------------------------------------------------ the flags


@pytest.mark.parametrize(
    "extra",
    [
        ["--data", "/work/x"],
        ["--claude-dir", "/work/x"],
        ["--store", "/work/x"],
        ["--demo"],
        ["--flow", "busy"],
        ["--fixture", "demo"],
        ["--test-clock"],
        ["--clock-rate", "2"],
        ["--ingest-pace-ms", "0"],
        ["--ingest-pace-ms", "30"],
    ],
)
def test_real_refuses_the_demo_and_path_flags(
    extra: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as caught:
        serve.parse_args(["--real", *extra])
    assert caught.value.code == 2
    assert f"--real can't be used with {extra[0]}" in capsys.readouterr().err


def test_real_works_out_the_folders_from_the_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "cfg"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    args = serve.parse_args(["--real", "--port", "47001"])
    root = config / "routing-dashboard" / "bartab"
    assert args.real
    assert args.claude_dir == config
    assert args.store == root
    assert args.data == root / "run"
    assert not args.demo
    assert args.flow is None
    assert args.test_clock is False
    assert not config.exists()  # parsing makes nothing


def test_real_falls_back_to_home_dot_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    args = serve.parse_args(["--real"])
    assert args.claude_dir == tmp_path / ".claude"


def test_real_refuses_a_relative_config_dir(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "relative/config")
    with pytest.raises(SystemExit) as caught:
        serve.parse_args(["--real"])
    assert caught.value.code == 2
    assert "absolute" in capsys.readouterr().err


def test_real_refuses_port_8377(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        serve.parse_args(["--real", "--port", "8377"])
    assert "8377" in capsys.readouterr().err


def test_data_is_still_required_without_real(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        serve.parse_args(["--port", "47001"])
    assert caught.value.code == 2
    assert "--data is required" in capsys.readouterr().err


def test_the_demo_flags_keep_their_defaults(tmp_path: Path) -> None:
    args = serve.parse_args(["--data", str(tmp_path)])
    assert (args.fixture, args.ingest_pace_ms, args.real) == ("demo", 0, False)
    assert args.demo is False


def test_make_real_folders_makes_only_the_missing_ones_and_never_the_config(
    tmp_path: Path,
) -> None:
    config = tmp_path / "cfg"
    root = config / "routing-dashboard" / "bartab"
    with pytest.raises(FileNotFoundError):
        serve.make_real_folders(config, root)
    assert not config.exists()
    config.mkdir()
    old = config / "routing-dashboard"
    old.mkdir(mode=0o755)
    old.chmod(0o755)
    tmp = serve.make_real_folders(config, root)
    assert tmp == root / "tmp"
    assert (old.stat().st_mode & 0o777) == 0o755  # the old app's folder keeps its mode
    for folder in (root, root / "run", root / "tmp"):
        assert (folder.stat().st_mode & 0o777) == 0o700
    assert serve.make_real_folders(config, root) == tmp  # a second call changes nothing


# ------------------------------------------------------ real wiring, in process


def real_provider(tmp_path: Path) -> store_provider.StoreProvider:
    """Build (not start) the provider ``--real`` builds, over made-up folders."""
    config = tmp_path / "cfg"
    config.mkdir(exist_ok=True)
    settings = main.Settings(
        port=47001,
        data_dir=tmp_path / "run",
        dist_dir=tmp_path / "dist",
        claude_dir=config,
        store_dir=tmp_path / "store",
        real=True,
        price_fetch=False,
    )
    made = main.make_provider(settings)
    assert isinstance(made, store_provider.StoreProvider)
    return made


@pytest.mark.parametrize(
    ("platform", "folder"),
    [
        ("darwin", "/Library/Application Support/ClaudeCode"),
        ("linux", "/etc/claude-code"),
        ("win32", r"C:\Program Files\ClaudeCode"),
        ("freebsd14", None),
    ],
)
def test_real_mode_passes_the_platform_managed_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
    folder: str | None,
) -> None:
    # Only main reads the platform. A global sys.platform of win32 breaks ssl.
    monkeypatch.setattr(main, "sys", SimpleNamespace(platform=platform))
    made = real_provider(tmp_path)
    want = None if folder is None else Path(folder)
    assert made._managed_dir == want  # pyright: ignore[reportPrivateUsage]


def test_the_managed_folder_table_matches_the_old_app() -> None:
    """Read ``MANAGED_DIRS`` out of dashboard/server.py (read only, not imported)."""
    tree = ast.parse((REPO / "dashboard" / "server.py").read_text(encoding="utf-8"))
    old: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and [
            t.id for t in node.targets if isinstance(t, ast.Name)
        ] == ["MANAGED_DIRS"]:
            old = ast.literal_eval(node.value)
    assert old
    assert old == store_provider.MANAGED_DIRS
    for platform in ("darwin", "linux", "linux2", "win32", "freebsd14", "cygwin"):
        want = next(
            (f for prefix, f in old.items() if platform.startswith(prefix)), None
        )
        got = store_provider.managed_dir_for(platform)
        assert (None if got is None else str(got)) == want, platform


def test_a_demo_build_keeps_no_managed_folder_unless_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config = tmp_path / "cfg"
    config.mkdir()
    settings = main.Settings(
        port=47001,
        data_dir=tmp_path / "run",
        dist_dir=tmp_path / "dist",
        claude_dir=config,
        store_dir=tmp_path / "store",
        price_fetch=False,
    )
    made = main.make_provider(settings)
    assert isinstance(made, store_provider.StoreProvider)
    assert made._managed_dir is None  # pyright: ignore[reportPrivateUsage]
    # Every mode hands over HOME, so real paths show with "~" on a demo server too.
    assert made._home == str(tmp_path / "home")  # pyright: ignore[reportPrivateUsage]


def test_real_mode_hands_the_provider_the_home_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    made = real_provider(tmp_path)
    assert made._home == str(tmp_path / "home")  # pyright: ignore[reportPrivateUsage]
    monkeypatch.delenv("HOME")
    assert real_provider(tmp_path)._home is None  # pyright: ignore[reportPrivateUsage]
