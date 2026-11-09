#!/usr/bin/env python3
"""Start, find and stop the Bar Tab preview server for Claude Code sessions.

The bartab-preview skill runs this as
python3 "<checkout>/app/bin/bartab.py" [global options] [action] [args].
Python 3.9 standard library only, and no imports from the repo.

Global options come before the action: --data DIR (else env BARTAB_DATA, else
app/.data in the checkout), --default-project DIR (else the working folder),
--session ID, --demo (the server reads the demo build) and --ingest-pace-ms N
(demo only, slows the first read so first run is watchable). Only start uses the
last two. After the action only that action's own options are allowed, so the
skill's $ARGUMENTS can't override a global option.

Actions
  start [--project DIR] [--no-open] [--port N] [--fixture NAME]   the default
  code [--project DIR] [--no-open]
  stop
  status
  session-end   hidden, SessionEnd hook JSON on stdin
  guard         hidden, PreToolUse hook JSON on stdin

Run with --session (the skill path) the launcher always exits 0 and reports a
failure as one stdout line that starts "error: ", because a non-zero exit aborts
the skill. Run by hand it exits 1 for a failure and 2 for a usage error or a
missing uv, and writes the error to stderr.

One server serves every project. State lives in the data folder, folder 0700 and
files 0600: server.json (the server writes it, this launcher adds and removes
owners), port, launcher.lock, logs/server.log and uv/ (uv's cache, Python
installs and the packages' environment).

The server is started detached as <data>/uv/env/bin/python serve.py after
`uv sync --frozen`. Spike 3 showed `uv run` adds a second process and nothing else.
A one-time code is printed in the link, so the launcher never logs it.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import http.client
import json
import os
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, NoReturn, TextIO, TypedDict, cast

if TYPE_CHECKING:
    from collections.abc import Generator

sys.dont_write_bytecode = True

APP = Path(__file__).resolve().parent.parent
SERVER_DIR = APP / "server"
SERVE = SERVER_DIR / "serve.py"
NEVER_PORT = 8377
BUSY_MARKS = ("in use", "errno 48", "errno 98", "could not bind")
PORT_LOW = 47000
PORT_HIGH = 47999
IDLE_EXIT_MINUTES = 30
LOCK_WAIT = 300
END_LOCK_WAIT = 60
LAUNCH_WAIT = 30
STOP_WAIT = 5
SYNC_TIMEOUT = 900
LOG_LIMIT = 1024 * 1024
LOG_KEEP = 256 * 1024
HTTP_TIMEOUT = 5
MAX_PORT = 65535
LAUNCH_LINE_MAX = 4096
SESSION_RE = re.compile(r"[A-Za-z0-9_-]{0,128}")
FIXTURE_RE = re.compile(r"[a-z0-9_]{1,40}")
PACE_RE = re.compile(r"[0-9]{1,5}")
CODE_RE = re.compile(r"[A-Za-z0-9_.~-]{1,300}")
UV_URL = "https://docs.astral.sh/uv/getting-started/installation/"
USAGE = (
    "usage: bartab.py [--data DIR] [--default-project DIR] [--session ID] "
    "[--demo] [--ingest-pace-ms N] "
    "[start [--project DIR] [--no-open] [--port N] [--fixture NAME] | "
    "code [--project DIR] [--no-open] | stop | status]"
)
CONNECT_HINT = "Connect to the internet and run the command again."
SANDBOX_MESSAGE = "Claude Code's sandbox blocked the Bar Tab launcher."

GLOBAL_OPTIONS = ("--data", "--default-project", "--session", "--ingest-pace-ms")
GLOBAL_FLAGS = ("--demo",)
# action -> (options as {name: takes a value}, number of positional words)
ACTIONS: dict[str, tuple[dict[str, bool], int]] = {
    "start": (
        {"--project": True, "--no-open": False, "--port": True, "--fixture": True},
        0,
    ),
    "code": ({"--project": True, "--no-open": False}, 0),
    "stop": ({}, 0),
    "status": ({}, 0),
    "session-end": ({}, 0),
    "guard": ({}, 0),
    "_end": (
        {"--session": True, "--claude-pid": True, "--claude-started": True},
        0,
    ),
}
QUIET_ACTIONS = ("session-end", "guard", "_end")
GUARD_REASON = (
    "The Bar Tab launcher runs only from the user's /bartab-preview command. "
    "Ask the user to run that command instead."
)
GUARD_STDIN_LIMIT = 1024 * 1024
GUARD_HARD_SPLIT = re.compile(r"\n|;|&&|\|\||\||&")
GUARD_SOFT_SPLIT = re.compile(r"\$\(|`|\(|\)|\{|\}")
# Wrapper words the guard looks through, with the options that take a value.
GUARD_WRAPPERS: dict[str, tuple[str, ...]] = {
    "exec": (),
    "command": (),
    "nohup": (),
    "time": ("-f", "-o"),
    "nice": ("-n",),
    "sudo": ("-u", "-g", "-C", "-h", "-p", "-r", "-t", "-U", "-D"),
}
GUARD_ENV_VALUE_OPTIONS = ("-u", "-C", "--unset", "--chdir")
GUARD_ENV_STRING_OPTIONS = ("-S", "--split-string")
GUARD_SHELLS = ("bash", "sh", "zsh", "dash", "ksh")
GUARD_PYTHON = re.compile(r"python[0-9.]*")
GUARD_PYTHON_VALUE_OPTIONS = ("-W", "-X")
# uv and uvw options that take a separate value, for `uv [options] run [options]`.
GUARD_UV_VALUE_OPTIONS = (
    "--project",
    "--directory",
    "--config-file",
    "--cache-dir",
    "--python",
    "-p",
    "--with",
    "--with-editable",
    "--with-requirements",
    "--group",
    "--extra",
    "--package",
    "--env-file",
    "--index",
    "--default-index",
    "--index-url",
    "-i",
    "--find-links",
    "-f",
    "--exclude-newer",
    "--refresh-package",
    "--reinstall-package",
    "--upgrade-package",
    "-P",
)
GUARD_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=")
GUARD_SHELL_WORD = re.compile(r"\b(?:ba|z|da|k)?sh\b|\beval\b")
GUARD_PUNCTUATION = frozenset(";&|()<>")
GUARD_MARK = "bin/bartab.py"
GUARD_NAME = "bartab.py"
GUARD_MAX_DEPTH = 4


class Usage(Exception):  # noqa: N818
    """A bad command line. The text is ours and holds no code or secret."""


class Fail(Exception):  # noqa: N818
    """A failure to report. The text is ours and holds no code or secret."""

    def __init__(self, message: str, code: int = 1) -> None:
        """Keep the message and the exit code a hand run uses."""
        super().__init__(message)
        self.code = code


def fail(message: str, code: int = 1) -> NoReturn:
    """Raise Fail with message."""
    raise Fail(message, code)


def usage(message: str) -> NoReturn:
    """Raise Usage with message."""
    raise Usage(message)


class Owner(TypedDict):
    """One Claude Code session that uses the server."""

    session: str
    claude_pid: int | None
    claude_started: str | None


@dataclass
class Record:
    """What server.json says, plus every key the launcher doesn't know."""

    port: int
    pid: int
    instance: str
    mint_secret: str
    owners: list[Owner]
    raw: dict[str, object]


@dataclass
class Launch:
    """The server's one JSON line on the launch fd."""

    port: int
    pid: int
    instance: str
    code: str
    project: str | None


class Ctx:
    """What one run knows, where the data is, who is calling, which folder it means."""

    def __init__(self, data: Path, session: str | None, default_project: Path) -> None:
        """Set the data folder, the calling session (None by hand) and the project."""
        self.data = data
        self.session = session
        self.default_project = default_project
        self.skill = session is not None
        self.owner: Owner | None = None
        self.demo = False
        self.pace_ms: str | None = None

    @property
    def server_json(self) -> Path:
        """The shared server record."""
        return self.data / "server.json"

    @property
    def port_file(self) -> Path:
        """The port this data folder used last."""
        return self.data / "port"

    @property
    def log_file(self) -> Path:
        """The server's stdout and stderr."""
        return self.data / "logs" / "server.log"

    @property
    def uv_dir(self) -> Path:
        """Everything uv keeps for this data folder."""
        return self.data / "uv"

    @property
    def python_bin(self) -> Path:
        """The packages' environment's Python."""
        return self.uv_dir / "env" / "bin" / "python"


def say(line: str) -> None:
    """Print one line."""
    sys.stdout.write(line + "\n")


def clean(text: object, limit: int = 80) -> str:
    """Make text one printable line of at most limit characters."""
    out = "".join(ch if ch.isprintable() else "?" for ch in str(text))
    return out if len(out) <= limit else out[:limit] + "..."


def as_dict(raw: object) -> dict[str, object] | None:
    """Return raw as a dict with str keys, or None."""
    if not isinstance(raw, dict):
        return None
    return cast("dict[str, object]", raw)


def is_int(value: object) -> bool:
    """True for an int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def int_field(data: dict[str, object], key: str, high: int | None = None) -> int | None:
    """Return data[key] when it is an int from 1 up to high, else None."""
    value = data.get(key)
    if not isinstance(value, int) or not is_int(value) or value < 1:
        return None
    return value if high is None or value <= high else None


def str_field(data: dict[str, object], key: str) -> str | None:
    """Return data[key] when it is a non-empty string, else None."""
    value = data.get(key)
    return value if isinstance(value, str) and value else None


# --------------------------------------------------------------------------
# Command line


def parse_globals(
    argv: list[str], state: dict[str, bool]
) -> tuple[dict[str, str], list[str]]:
    """Read the global options. Returns (globals, the words left)."""
    glob: dict[str, str] = {}
    i = 0
    while i < len(argv) and (argv[i] in GLOBAL_OPTIONS or argv[i] in GLOBAL_FLAGS):
        name = argv[i]
        if name == "--session":
            state["skill"] = True
        if name in glob:
            usage(f"{name} was given twice")
        if name in GLOBAL_FLAGS:
            glob[name] = "1"
            i += 1
            continue
        if i + 1 >= len(argv):
            usage(f"{name} needs a value")
        glob[name] = argv[i + 1]
        i += 2
    return glob, argv[i:]


def parse_options(action: str, words: list[str]) -> dict[str, str | bool]:
    """Read the action's own options. Any other word is a usage error."""
    spec = ACTIONS[action][0]
    opts: dict[str, str | bool] = {}
    j = 0
    while j < len(words):
        word = words[j]
        if word not in spec:
            if word.startswith("--"):
                usage(f"{clean(word)} is not an option of {action}")
            usage(f"{action} takes no word after it, got {clean(word)}")
        if word in opts:
            usage(f"{word} was given twice")
        if spec[word]:
            if j + 1 >= len(words):
                usage(f"{word} needs a value")
            opts[word] = words[j + 1]
            j += 2
        else:
            opts[word] = True
            j += 1
    return opts


def parse_args(
    argv: list[str], state: dict[str, bool]
) -> tuple[dict[str, str], str, dict[str, str | bool]]:
    """Return (globals, action, options). Global options come first."""
    glob, rest = parse_globals(argv, state)
    action = "start"
    if rest and not rest[0].startswith("--"):
        action, rest = rest[0], rest[1:]
    if action not in ACTIONS:
        usage(f"unknown action {clean(action)}")
    if action in QUIET_ACTIONS:
        if state["skill"]:
            usage(f"{action} is not an action the skill can run")
        state["quiet"] = True
    return glob, action, parse_options(action, rest)


def parse_port(opts: dict[str, str | bool]) -> int | None:
    """Return --port as an int, or None when it was not given."""
    text = opts.get("--port")
    if text is None:
        return None
    if (
        not isinstance(text, str)
        or not re.fullmatch(r"[0-9]{1,5}", text)
        or not 1 <= int(text) <= MAX_PORT
    ):
        usage(f"--port needs a number from 1 to {MAX_PORT}")
    return int(text)


def data_folder(glob: dict[str, str]) -> Path:
    """Resolve the data folder, --data, else BARTAB_DATA, else app/.data."""
    text = glob.get("--data") or os.environ.get("BARTAB_DATA") or ""
    return Path(text).resolve() if text else APP / ".data"


def build_ctx(glob: dict[str, str]) -> Ctx:
    """Make the run's context from the global options."""
    session = glob.get("--session")
    if session is not None and not SESSION_RE.fullmatch(session):
        usage("--session takes letters, digits, - and _ (up to 128)")
    default = Path(glob.get("--default-project") or Path.cwd()).resolve()
    ctx = Ctx(data_folder(glob), session, default)
    ctx.demo = "--demo" in glob
    pace = glob.get("--ingest-pace-ms")
    if pace is not None:
        if not PACE_RE.fullmatch(pace):
            usage("--ingest-pace-ms takes a number of milliseconds, up to 99999")
        if not ctx.demo:
            usage("--ingest-pace-ms is for the demo build only, add --demo")
        ctx.pace_ms = pace
    return ctx


# --------------------------------------------------------------------------
# Processes


def run_ps(*args: str) -> str:
    """Run ps and return its stdout, or "" when it finds nothing."""
    try:
        proc = subprocess.run(  # noqa: S603
            ("ps", "-ww", *args),  # noqa: S607
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            text=True,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def ps_command(pid: int) -> str:
    """The command line of pid, or ""."""
    return run_ps("-o", "command=", "-p", str(pid))


def proc_info(pid: int) -> tuple[str, str] | None:
    """Return (stat, lstart) for a pid, or None when ps doesn't know it."""
    parts = run_ps("-o", "stat=", "-o", "lstart=", "-p", str(pid)).split(None, 1)
    if len(parts) <= 1:
        return None
    return parts[0], parts[1].strip()


def parent_of(pid: int) -> int:
    """The parent pid of pid, or 0."""
    text = run_ps("-o", "ppid=", "-p", str(pid))
    return int(text) if text.isdigit() else 0


def pid_exists(pid: int) -> bool:
    """True when a process with this pid exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def claude_identity() -> tuple[int | None, str | None]:
    """Return (claude_pid, claude_started) from env CLAUDE_PID, or (None, None).

    CLAUDE_PID is undocumented, so it counts only when it names one of this
    process's ancestors, up to 8 levels above the parent.
    """
    raw = os.environ.get("CLAUDE_PID", "")
    if not re.fullmatch(r"[0-9]{1,10}", raw) or int(raw) <= 0:
        return None, None
    pid = int(raw)
    cur = os.getppid()
    for _ in range(8):
        if cur == pid:
            info = proc_info(pid)
            return pid, (info[1] if info else None)
        if cur <= 1:
            break
        cur = parent_of(cur)
    return None, None


def owner_alive(owner: Owner) -> bool:
    """False only when the owner's Claude Code process is known to be gone."""
    pid = owner["claude_pid"]
    if pid is None:
        return True
    if not pid_exists(pid):
        return False
    info = proc_info(pid)
    if info is None or info[0].startswith("Z"):
        return False
    started = owner["claude_started"]
    return started is None or info[1] == started


def argv_has(command: str, *words: str) -> bool:
    """True when the words appear in command as whole, consecutive arguments.

    ps gives one joined line, so an argument counts when whitespace or the line
    edge sits on both sides of it. A path that merely contains another is no match.
    """
    needle = r"\s+".join(re.escape(word) for word in words)
    return re.search(rf"(?:^|\s){needle}(?=\s|$)", command) is not None


def process_ours(ctx: Ctx, rec: Record) -> bool:
    """True when rec's pid is alive and runs this checkout's serve.py on this data.

    The command line must hold the resolved path of SERVE as one argument and
    --data followed by this run's resolved data folder. A process that only
    mentions serve.py, or serves another data folder, is not ours.
    """
    if not pid_exists(rec.pid):
        return False
    command = ps_command(rec.pid)
    return argv_has(command, str(SERVE.resolve())) and argv_has(
        command, "--data", str(ctx.data.resolve())
    )


def wait_gone(pid: int, seconds: float) -> bool:
    """Wait up to seconds for pid to end. A zombie counts as ended."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if not pid_exists(pid):
            return True
        time.sleep(0.05)
    if not pid_exists(pid):
        return True
    info = proc_info(pid)
    return info is None or info[0].startswith("Z")


def stop_process(ctx: Ctx, rec: Record) -> bool:
    """SIGTERM, wait, SIGKILL. Signals only a pid that runs our serve.py.

    Returns True when a process was signalled.
    """
    if not process_ours(ctx, rec):
        return False
    try:
        os.kill(rec.pid, signal.SIGTERM)
    except ProcessLookupError:
        return False
    if not wait_gone(rec.pid, STOP_WAIT) and process_ours(ctx, rec):
        with contextlib.suppress(ProcessLookupError):
            os.kill(rec.pid, signal.SIGKILL)
        wait_gone(rec.pid, 3)
    return True


class Request(NamedTuple):
    """One request for http_call."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes | None


def http_call(
    port: int, request: Request, timeout: float = 2
) -> tuple[int, bytes] | None:
    """Send request to 127.0.0.1:port. Returns (status, body), or None on an error."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.putrequest(
            request.method, request.path, skip_host=True, skip_accept_encoding=True
        )
        conn.putheader("Host", f"127.0.0.1:{port}")
        for name, value in request.headers.items():
            conn.putheader(name, value)
        if request.body is not None:
            conn.putheader("Content-Length", str(len(request.body)))
        conn.endheaders(request.body)
        resp = conn.getresponse()
        return resp.status, resp.read(1024 * 1024)
    except (OSError, http.client.HTTPException):
        return None
    finally:
        conn.close()


def probe_http(port: int, timeout: float = 2) -> bool:
    """True when GET / on 127.0.0.1:port answers with any HTTP response."""
    return http_call(port, Request("GET", "/", {}, None), timeout) is not None


# --------------------------------------------------------------------------
# State under the data folder


def ensure_data(data: Path) -> None:
    """Make the data folder and its logs folder, mode 0700."""
    try:
        data.mkdir(mode=0o700, parents=True, exist_ok=True)
        data.chmod(0o700)
        logs = data / "logs"
        logs.mkdir(mode=0o700, exist_ok=True)
        logs.chmod(0o700)
    except (FileExistsError, NotADirectoryError):
        fail(f"the data path is not a folder: {clean(data, 200)}")


class Lock:
    """An exclusive flock on launcher.lock, polled every 50 ms."""

    def __init__(self, folder: Path, wait: float) -> None:
        """Take the lock, or raise Fail after wait seconds."""
        self.fd = os.open(folder / "launcher.lock", os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if not isinstance(exc, BlockingIOError) and exc.errno != errno.EACCES:
                    os.close(self.fd)
                    raise
            else:
                return
            if time.monotonic() >= deadline:
                os.close(self.fd)
                fail("another launcher is busy, try again")
            time.sleep(0.05)

    def release(self) -> None:
        """Drop the lock."""
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
        finally:
            os.close(self.fd)


def write_private(path: Path, data: bytes) -> None:
    """Write bytes to a new 0600 file next to path, fsync, then rename it over path."""
    tmp = path.with_name(f"{path.name}.tmp{os.getpid()}")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def valid_owners(raw: object) -> list[Owner]:
    """Keep the entries of raw that are owners."""
    owners: list[Owner] = []
    if not isinstance(raw, list):
        return owners
    for item in cast("list[object]", raw):
        entry = as_dict(item)
        if entry is None:
            continue
        pid = entry.get("claude_pid")
        started = entry.get("claude_started")
        session = entry.get("session")
        if pid is not None and not is_int(pid):
            continue
        owners.append(
            {
                "session": session if isinstance(session, str) else "",
                "claude_pid": cast("int | None", pid),
                "claude_started": started if isinstance(started, str) else None,
            }
        )
    return owners


def valid_record(raw: object) -> Record | None:
    """Return a Record when raw holds every field the launcher needs, else None."""
    data = as_dict(raw)
    if data is None:
        return None
    port = int_field(data, "port", MAX_PORT)
    pid = int_field(data, "pid")
    instance = str_field(data, "instance")
    secret = str_field(data, "mint_secret")
    if port is None or pid is None or instance is None or secret is None:
        return None
    return Record(port, pid, instance, secret, valid_owners(data.get("owners")), data)


def load_record(ctx: Ctx) -> Record | None:
    """Return the server record. A file that isn't one is deleted."""
    try:
        text = ctx.server_json.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        rec = valid_record(json.loads(text))
    except ValueError:
        rec = None
    if rec is None:
        forget(ctx)
        say("cleaned up an unreadable server record")
    return rec


def save_record(ctx: Ctx, rec: Record) -> None:
    """Write the record back with its current owners, keeping the keys it came with."""
    out = dict(rec.raw)
    out["owners"] = list(rec.owners)
    text = json.dumps(out, indent=2, sort_keys=True) + "\n"
    write_private(ctx.server_json, text.encode("utf-8"))


def forget(ctx: Ctx) -> None:
    """Delete server.json."""
    ctx.server_json.unlink(missing_ok=True)


def add_owner(rec: Record, owner: Owner) -> None:
    """Add owner unless the same process, or the same session with no pid, is in."""
    for have in rec.owners:
        if owner["claude_pid"] is not None:
            if (
                have["claude_pid"] == owner["claude_pid"]
                and have["claude_started"] == owner["claude_started"]
            ):
                return
        elif have["claude_pid"] is None and have["session"] == owner["session"]:
            return
    rec.owners.append(owner)


def caller_owner(ctx: Ctx) -> Owner:
    """The calling session as an owner. A run by hand has no session id."""
    if ctx.owner is None:
        pid, started = (None, None) if not ctx.skill else claude_identity()
        ctx.owner = {
            "session": ctx.session or "",
            "claude_pid": pid,
            "claude_started": started,
        }
    return ctx.owner


def live_server(ctx: Ctx) -> Record | None:
    """Return the running server's record, or None. A stale record is deleted.

    Owners whose Claude Code process is gone are dropped first. A server left
    with none is stopped. A server whose process is ours but whose port doesn't
    answer twice is stopped too.
    """
    rec = load_record(ctx)
    if rec is None:
        return None
    if not process_ours(ctx, rec):
        forget(ctx)
        return None
    keep = [o for o in rec.owners if owner_alive(o)]
    if len(keep) != len(rec.owners):
        rec.owners = keep
        if not keep:
            stop_process(ctx, rec)
            forget(ctx)
            say("stopped the server: every session that used it has ended")
            return None
        save_record(ctx, rec)
    if probe_http(rec.port) or probe_http(rec.port, timeout=HTTP_TIMEOUT):
        return rec
    stop_process(ctx, rec)
    forget(ctx)
    say("stopped a server that stopped answering")
    return None


# --------------------------------------------------------------------------
# uv and the packages


def find_uv() -> str:
    """Find uv in the contract's order, and fail with exit code 2 when there is none."""
    candidates: list[str | None] = [
        os.environ.get("BARTAB_UV"),
        str(APP.parent / ".tools" / "uv" / "uv"),
        shutil.which("uv"),
        str(Path.home() / ".local" / "bin" / "uv"),
        str(Path.home() / ".cargo" / "bin" / "uv"),
    ]
    for item in candidates:
        if item and Path(item).is_file() and os.access(item, os.X_OK):
            return item
    fail(
        f"uv not found. Install it from {UV_URL} or set BARTAB_UV to its path.",
        2,
    )


def uv_env(ctx: Ctx) -> dict[str, str]:
    """The environment for uv and the server, every uv folder under <data>/uv."""
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    uv = ctx.uv_dir
    env.update(
        {
            "UV_CACHE_DIR": str(uv / "cache"),
            "UV_PYTHON_INSTALL_DIR": str(uv / "python"),
            "UV_PROJECT_ENVIRONMENT": str(uv / "env"),
            "UV_PYTHON_BIN_DIR": str(uv / "bin"),
            "UV_PYTHON_INSTALL_BIN": "0",
            "UV_TOOL_DIR": str(uv / "tools"),
            "UV_PYTHON_PREFERENCE": "only-managed",
            "UV_NO_MODIFY_PATH": "1",
            "PYTHONPATH": str(SERVER_DIR),
        }
    )
    return env


def last_line(text: str) -> str:
    """The last non-empty line of text, cleaned."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return clean(lines[-1], 200) if lines else ""


def python_step_failed(text: str) -> bool:
    """True when uv's output says the Python download or lookup failed."""
    low = text.lower()
    if "no interpreter found" in low:
        return True
    return "failed to download" in low and (
        "cpython" in low or "python-build-standalone" in low
    )


def network_failed(text: str) -> bool:
    """True when uv's output looks like a connection problem."""
    low = text.lower()
    marks = ("failed to download", "failed to fetch", "dns error", "error sending")
    return python_step_failed(text) or any(m in low for m in marks)


def run_sync(ctx: Ctx, uv: str) -> tuple[int, str]:
    """Run uv sync --frozen --no-dev for the checkout. Returns (exit code, output)."""
    argv = [uv, "sync", "--frozen", "--project", str(APP), "--no-dev"]
    try:
        proc = subprocess.run(  # noqa: S603
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=uv_env(ctx),
            timeout=SYNC_TIMEOUT,
            text=True,
            check=False,
        )
    except subprocess.TimeoutExpired:
        fail(f"uv sync took longer than {SYNC_TIMEOUT} seconds. {CONNECT_HINT}")
    except OSError as exc:
        fail(f"couldn't run uv ({clean(exc.strerror or type(exc).__name__)})")
    return proc.returncode, proc.stdout


def ensure_packages(ctx: Ctx, uv: str) -> None:
    """Run uv sync --frozen. The first run prints its two step lines."""
    marker = ctx.uv_dir / "synced"
    first = not marker.is_file()
    code, out = run_sync(ctx, uv)
    if code == 0:
        if not ctx.python_bin.exists():
            fail("uv finished but the Python environment is missing")
        if first:
            say("Download Python: done")
            say("Install the dashboard's packages: done")
            ctx.uv_dir.mkdir(parents=True, exist_ok=True)
            marker.write_text("ok\n", encoding="utf-8")
        return
    detail = last_line(out)
    if python_step_failed(out):
        say("Download Python: failed")
        fail(f"couldn't download Python ({detail}). {CONNECT_HINT}")
    if first:
        say("Download Python: done")
        say("Install the dashboard's packages: failed")
    hint = f" {CONNECT_HINT}" if network_failed(out) else ""
    fail(f"couldn't install the dashboard's packages ({detail}).{hint}")


# --------------------------------------------------------------------------
# Ports


def port_free(port: int) -> bool:
    """True when nothing listens on 127.0.0.1:port and the port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.3)
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        # The server binds with SO_REUSEADDR, so a port in TIME_WAIT after a stop
        # counts as free. A port with a listener still fails to bind.
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def saved_port(ctx: Ctx) -> int | None:
    """The port in <data>/port, when it is in range."""
    try:
        text = ctx.port_file.read_text(encoding="ascii").strip()
    except (OSError, UnicodeDecodeError):
        return None
    if re.fullmatch(r"[0-9]{1,5}", text) and PORT_LOW <= int(text) <= PORT_HIGH:
        return int(text)
    return None


def pick_port(
    ctx: Ctx, asked: int | None, taken: tuple[int, ...] = ()
) -> tuple[int, str]:
    """Choose the port. Returns (port, note). Never 8377, even when asked.

    asked is --port. A busy asked port is an error. Otherwise the saved port is
    tried first, then the first free one from PORT_LOW to PORT_HIGH. taken lists
    ports that just failed.
    """
    note = ""
    if asked == NEVER_PORT:
        note = f"port {NEVER_PORT} is the old dashboard's, so another port was chosen"
        asked = None
    if asked is not None:
        if asked in taken or not port_free(asked):
            fail(f"port {asked} is in use")
        return asked, note
    first = saved_port(ctx)
    order = ([first] if first is not None else []) + list(
        range(PORT_LOW, PORT_HIGH + 1)
    )
    for port in order:
        if port != NEVER_PORT and port not in taken and port_free(port):
            return port, note
    fail(f"no free port from {PORT_LOW} to {PORT_HIGH}")


# --------------------------------------------------------------------------
# Browser


def browser_blocked() -> str | None:
    """Return None when a browser may open, else the line to say ("" for none)."""
    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_TTY"):
        return "Not opening a browser over SSH."
    if sys.platform.startswith("linux") and not (
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    ):
        return "No display found, so no browser opened."
    return None


@contextlib.contextmanager
def quiet_output() -> Generator[None, None, None]:
    """Point stdout and stderr at /dev/null, so a browser can't keep our pipe open."""
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        saved = (os.dup(1), os.dup(2))
        null = os.open(os.devnull, os.O_RDWR)
    except OSError:
        yield
        return
    try:
        os.dup2(null, 1)
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in (null, *saved):
            os.close(fd)


def open_browser(url: str, no_open: bool) -> tuple[str, str]:
    """Return (state, line), state is opened, skipped or failed. line may be empty."""
    if no_open:
        return "skipped", ""
    reason = browser_blocked()
    if reason is not None:
        return "skipped", reason
    try:
        with quiet_output():
            # get().open, not webbrowser.open. The latter goes on to the next
            # browser when the first fails, which would open a second tab.
            ok = webbrowser.get().open(url, new=2)
    except Exception:  # noqa: BLE001
        ok = False
    if ok:
        return "opened", ""
    return "failed", "Couldn't open a browser."


def announce(port: int, code: str, no_open: bool) -> None:
    """Print the link and open it."""
    url = f"http://127.0.0.1:{port}/#/?code={code}"
    say(f"Bar Tab preview: {url}")
    state, line = open_browser(url, no_open)
    if state == "opened":
        say("Opened in your browser.")
    elif line:
        say(line)


# --------------------------------------------------------------------------
# Starting the server


def open_log(ctx: Ctx) -> int:
    """Open the server log for append. Over 1 MB it first keeps only its last 256 KB."""
    path = ctx.log_file
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        size = 0
    if size > LOG_LIMIT:
        with path.open("rb") as fh:
            fh.seek(size - LOG_KEEP)
            tail = fh.read()
        write_private(path, tail)
    return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)


def last_log_line(ctx: Ctx) -> str:
    """The last line of the server log, cleaned."""
    try:
        with ctx.log_file.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - 4096))
            text = fh.read().decode("utf-8", "replace")
    except OSError:
        return ""
    return last_line(text)


def kill_child(proc: subprocess.Popen[bytes]) -> None:
    """Kill a server that failed to start and reap it."""
    with contextlib.suppress(OSError):
        proc.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(5)


def parse_launch(line: str) -> Launch | None:
    """Parse the launch line, or None when it isn't the contract's shape."""
    try:
        data = as_dict(json.loads(line))
    except ValueError:
        return None
    if data is None:
        return None
    port = int_field(data, "port", MAX_PORT)
    pid = int_field(data, "pid")
    instance = str_field(data, "instance")
    code = str_field(data, "code")
    if port is None or pid is None or instance is None or code is None:
        return None
    if not CODE_RE.fullmatch(code):
        return None
    return Launch(port, pid, instance, code, str_field(data, "project"))


def read_launch_line(ctx: Ctx, fd: int, proc: subprocess.Popen[bytes]) -> Launch | None:
    """Read the server's one line from the pipe.

    Returns None when the server stopped before it was ready. The code in the
    line is handed back to the caller and kept out of every message.
    """
    buf = b""
    deadline = time.monotonic() + LAUNCH_WAIT
    while b"\n" not in buf and len(buf) < LAUNCH_LINE_MAX:
        left = deadline - time.monotonic()
        if left <= 0:
            kill_child(proc)
            fail(
                f"the server didn't report its address in {LAUNCH_WAIT} seconds; "
                f"see the log at {clean(ctx.log_file, 300)}"
            )
        ready, _, _ = select.select([fd], [], [], left)
        if not ready:
            continue
        chunk = os.read(fd, LAUNCH_LINE_MAX)
        if not chunk:
            break
        buf += chunk
    if b"\n" not in buf:
        kill_child(proc)
        return None
    launch = parse_launch(buf.split(b"\n", 1)[0].decode("ascii", "replace"))
    if launch is None:
        kill_child(proc)
        fail(
            "the server sent a reply the launcher doesn't know; "
            f"see the log at {clean(ctx.log_file, 300)}"
        )
    return launch


def spawn_once(
    ctx: Ctx,
    port: int,
    project: Path,
    fixture: str | None,
    extra: tuple[str, ...] = (),
) -> Launch | None:
    """Start one server on port. Returns None when it stopped before it was ready."""
    argv = [
        str(ctx.python_bin),
        "-B",
        str(SERVE),
        "--port",
        str(port),
        "--data",
        str(ctx.data),
        "--project-dir",
        str(project),
        "--idle-exit-minutes",
        str(IDLE_EXIT_MINUTES),
    ]
    if fixture:
        argv += ["--fixture", fixture]
    argv += extra
    r, w = os.pipe()
    try:
        argv += ["--launch-fd", str(w)]
        log_fd = open_log(ctx)
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log_fd,
                stderr=log_fd,
                cwd=SERVER_DIR,
                env=uv_env(ctx),
                start_new_session=True,
                pass_fds=(w,),
            )
        finally:
            os.close(log_fd)
    except BaseException:
        os.close(r)
        raise
    finally:
        os.close(w)
    try:
        return read_launch_line(ctx, r, proc)
    finally:
        os.close(r)


def bring_up(
    ctx: Ctx,
    project: Path,
    asked: int | None,
    fixture: str | None,
    extra: tuple[str, ...] = (),
) -> tuple[Launch, str]:
    """Start the server, trying up to 3 ports. Returns (launch, note)."""
    taken: tuple[int, ...] = ()
    note = ""
    for attempt in range(3):
        port, pick_note = pick_port(ctx, asked, taken)
        note = note or pick_note
        launch = spawn_once(ctx, port, project, fixture, extra)
        if launch is not None:
            return launch, note
        detail = last_log_line(ctx)
        busy = any(m in detail.lower() for m in BUSY_MARKS)
        if asked is not None or not busy or attempt == 2:  # noqa: PLR2004
            fail(
                "the server stopped before it was ready"
                + (f": {detail}" if detail else "")
            )
        taken += (port,)
    fail("no free port found")


def adopt_record(ctx: Ctx, launch: Launch, project: Path) -> Record:
    """Read the server's server.json, check it is this server's, add the caller.

    The launch line's project key is kept beside the folder it came from, because
    the mint call takes a project key and only the server knows how to make one.
    """
    deadline = time.monotonic() + 3
    rec = None
    while time.monotonic() < deadline:
        with contextlib.suppress(FileNotFoundError, ValueError):
            rec = valid_record(json.loads(ctx.server_json.read_text(encoding="utf-8")))
        if rec is not None:
            break
        time.sleep(0.05)
    if rec is None or rec.pid != launch.pid or rec.instance != launch.instance:
        with contextlib.suppress(OSError):
            os.kill(launch.pid, signal.SIGTERM)
        fail(
            "the server didn't write server.json; "
            f"see the log at {clean(ctx.log_file, 300)}"
        )
    rec.raw["launcher_project_dir"] = str(project)
    rec.raw["launcher_project"] = launch.project
    add_owner(rec, caller_owner(ctx))
    save_record(ctx, rec)
    return rec


def mint_code(rec: Record, project: Path) -> str:
    """Ask the running server for a fresh single-use code.

    The code names the project key the server gave this folder when it started.
    Any other folder gets a code with no project.
    """
    key = None
    if rec.raw.get("launcher_project_dir") == str(project):
        key = str_field(rec.raw, "launcher_project")
    body = json.dumps({"project": key}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Bartab-Mint": rec.mint_secret,
    }
    request = Request("POST", "/api/access/mint", headers, body)
    result = http_call(rec.port, request, timeout=HTTP_TIMEOUT)
    if result is None:
        fail("the server didn't answer the request for a new link")
    status, payload = result
    if status != 200:  # noqa: PLR2004
        fail(f"the server refused the request for a new link (status {status})")
    try:
        data = as_dict(json.loads(payload.decode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        data = None
    code = data.get("code") if data else None
    if not isinstance(code, str) or not CODE_RE.fullmatch(code):
        fail("the server sent a new link the launcher doesn't know")
    return code


# --------------------------------------------------------------------------
# Actions


def resolve_project(ctx: Ctx, opts: dict[str, str | bool]) -> Path:
    """The project folder, --project (relative to the default) or the default."""
    word = opts.get("--project")
    if isinstance(word, str):
        path = Path(word)
        if not path.is_absolute():
            path = ctx.default_project / path
    else:
        path = ctx.default_project
    path = path.resolve()
    if not path.is_dir():
        fail(f"not a folder: {clean(word if isinstance(word, str) else path, 200)}")
    return path


def do_start(ctx: Ctx, opts: dict[str, str | bool]) -> None:
    """Start the server, or add this session to the one that is running."""
    project = resolve_project(ctx, opts)
    asked = parse_port(opts)
    fixture = opts.get("--fixture")
    if fixture is not None and (
        not isinstance(fixture, str) or not FIXTURE_RE.fullmatch(fixture)
    ):
        usage("--fixture takes lowercase letters, digits and _")
    extra: tuple[str, ...] = ("--demo",) if ctx.demo else ()
    if ctx.pace_ms is not None:
        extra += ("--ingest-pace-ms", ctx.pace_ms)
    no_open = "--no-open" in opts
    rec = live_server(ctx)
    if rec is not None:
        add_owner(rec, caller_owner(ctx))
        save_record(ctx, rec)
        code = mint_code(rec, project)
        announce(rec.port, code, no_open)
        if (asked and asked != rec.port) or fixture:
            say("already running; run stop first to change the port or fixture")
        return
    uv = find_uv()
    ensure_packages(ctx, uv)
    launch, note = bring_up(
        ctx, project, asked, fixture if isinstance(fixture, str) else None, extra
    )
    adopt_record(ctx, launch, project)
    with contextlib.suppress(OSError):
        ctx.port_file.write_text(f"{launch.port}\n", encoding="ascii")
    if note:
        say(note)
    announce(launch.port, launch.code, no_open)


def do_code(ctx: Ctx, opts: dict[str, str | bool]) -> None:
    """Mint a fresh code for the running server and show the link."""
    project = resolve_project(ctx, opts)
    rec = live_server(ctx)
    if rec is None:
        fail("no Bar Tab preview is running; run start")
    add_owner(rec, caller_owner(ctx))
    save_record(ctx, rec)
    announce(rec.port, mint_code(rec, project), "--no-open" in opts)


def do_stop(ctx: Ctx) -> None:
    """Stop the server whatever its owners."""
    rec = load_record(ctx)
    if rec is not None and stop_process(ctx, rec):
        say(f"Stopped Bar Tab (port {rec.port}).")
    else:
        say("No Bar Tab preview is running.")
    forget(ctx)


def do_status(ctx: Ctx) -> None:
    """Say whether the server runs, where, and for how many sessions."""
    rec = live_server(ctx)
    if rec is None:
        say("No Bar Tab preview is running.")
        return
    started = rec.raw.get("started")
    say(
        f"Bar Tab preview  http://127.0.0.1:{rec.port}/  "
        f"started {started if isinstance(started, str) else 'unknown'}  "
        f"sessions {len(rec.owners)}"
    )


def run_locked(ctx: Ctx, work: str, opts: dict[str, str | bool]) -> None:
    """Run one action under the launcher lock."""
    ensure_data(ctx.data)
    lock = Lock(ctx.data, LOCK_WAIT)
    try:
        if work == "start":
            do_start(ctx, opts)
        elif work == "code":
            do_code(ctx, opts)
        elif work == "stop":
            do_stop(ctx)
        else:
            do_status(ctx)
    finally:
        lock.release()


# --------------------------------------------------------------------------
# The SessionEnd hook


def read_stdin_capped() -> bytes:
    """Read up to 64 KB from stdin, giving up after 0.3 s."""
    try:
        fd = sys.stdin.fileno()
    except (OSError, ValueError, AttributeError):
        return b""
    buf = b""
    deadline = time.monotonic() + 0.3
    while len(buf) < 65536:  # noqa: PLR2004
        left = deadline - time.monotonic()
        if left <= 0:
            break
        try:
            ready, _, _ = select.select([fd], [], [], left)
            if not ready:
                break
            chunk = os.read(fd, 65536 - len(buf))
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    return buf


def session_end(glob: dict[str, str]) -> None:
    """Hand the cleanup to a detached worker and return at once. Never prints."""
    try:
        data = as_dict(json.loads(read_stdin_capped().decode("utf-8")))
    except (ValueError, UnicodeDecodeError):
        return
    if data is None:
        return
    session = data.get("session_id")
    if not isinstance(session, str) or not session or not SESSION_RE.fullmatch(session):
        return
    if data.get("reason") in ("clear", "resume"):
        return
    folder = data_folder(glob)
    if not (folder / "server.json").is_file():
        return
    pid, started = claude_identity()
    subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "--data",
            str(folder),
            "_end",
            "--session",
            session,
            "--claude-pid",
            str(pid) if pid else "",
            "--claude-started",
            started or "",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


def end_session(glob: dict[str, str], opts: dict[str, str | bool]) -> None:
    """The detached worker. Drop this session's owners, stop a server left with none."""
    session = opts.get("--session")
    if not isinstance(session, str) or not SESSION_RE.fullmatch(session):
        return
    ctx = Ctx(data_folder(glob), None, Path.cwd())
    if not ctx.data.is_dir():
        return
    raw_pid = opts.get("--claude-pid")
    claude_pid = (
        int(raw_pid) if isinstance(raw_pid, str) and raw_pid.isdigit() else None
    )
    started = opts.get("--claude-started")
    claude_started = started if isinstance(started, str) and started else None
    lock = Lock(ctx.data, END_LOCK_WAIT)
    try:
        rec = load_record(ctx)
        if rec is None:
            return
        if not process_ours(ctx, rec):
            forget(ctx)
            return
        keep: list[Owner] = []
        for owner in rec.owners:
            mine = (
                claude_pid is not None
                and owner["claude_pid"] == claude_pid
                and owner["claude_started"] == claude_started
            ) or (
                bool(session)
                and owner["claude_pid"] is None
                and owner["session"] == session
            )
            if not mine and owner_alive(owner):
                keep.append(owner)
        if len(keep) == len(rec.owners):
            return
        rec.owners = keep
        if keep:
            save_record(ctx, rec)
            return
        stop_process(ctx, rec)
        forget(ctx)
    finally:
        lock.release()


# --------------------------------------------------------------------------
# The PreToolUse guard


def names_launcher(word: str) -> bool:
    """True when a word is the launcher script, by path or by bare file name."""
    return Path(word).name == GUARD_NAME or GUARD_MARK in word


def python_runs(args: list[str]) -> bool:
    """True when python run with args executes the launcher.

    Interpreter options are skipped. -m and a plain read of the file (pytest,
    ruff and the like run through -m) don't count. -c counts when its code names
    the launcher, and so does a script word or a < redirect that names it.
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            break
        if not arg.startswith("-") or arg == "-":
            break
        if arg.startswith("-c"):
            code = arg[2:] or (args[i + 1] if i + 1 < len(args) else "")
            return GUARD_NAME in code
        if arg == "-m":
            module = args[i + 1] if i + 1 < len(args) else ""
            return module == "runpy" and any(names_launcher(a) for a in args[i + 2 :])
        if arg.startswith("-m"):
            return False
        i += 2 if arg in GUARD_PYTHON_VALUE_OPTIONS else 1
    if i < len(args) and names_launcher(args[i]):
        return True
    for k, arg in enumerate(args):
        if not arg.startswith("<"):
            continue
        target = arg.lstrip("<") or (args[k + 1] if k + 1 < len(args) else "")
        if names_launcher(target):
            return True
    return False


def shell_string(args: list[str]) -> str | None:
    """The command string of `sh -c STRING`, or None when args hold no -c."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-o", "+o"):
            i += 2
            continue
        if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
            return args[i + 1] if i + 1 < len(args) else None
        if arg.startswith(("-", "+")):
            i += 1
            continue
        return None
    return None


def uv_runs(args: list[str], depth: int) -> bool:
    """True when `uv [options] run [options] COMMAND` runs the launcher."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 2 if args[i] in GUARD_UV_VALUE_OPTIONS else 1
    if i >= len(args) or args[i] != "run":
        return False
    j = i + 1
    while j < len(args) and args[j].startswith("-"):
        if args[j] == "--script":
            return j + 1 < len(args) and names_launcher(args[j + 1])
        j += 2 if args[j] in GUARD_UV_VALUE_OPTIONS else 1
    if words_run(args[j:], depth):
        return True
    # An option this list doesn't know may have hidden the command word.
    return any(
        GUARD_PYTHON.fullmatch(Path(word).name) and python_runs(args[k + 1 :])
        for k, word in enumerate(args[i + 1 :], start=i + 1)
    )


def strip_wrappers(words: list[str]) -> tuple[list[str], str | None]:
    """Drop leading NAME=value words and wrapper words (GUARD_WRAPPERS, env).

    Returns the words left and, for `env -S STRING`, that string.
    """
    i = 0
    while i < len(words):
        name = Path(words[i]).name
        if GUARD_ASSIGN.match(words[i]):
            i += 1
        elif name == "env":
            i += 1
            while i < len(words) and (
                words[i].startswith("-") or GUARD_ASSIGN.match(words[i])
            ):
                word = words[i]
                if word in GUARD_ENV_STRING_OPTIONS:
                    return [], " ".join(words[i + 1 :])
                if word.startswith("--split-string="):
                    return [], " ".join([word.partition("=")[2], *words[i + 1 :]])
                if word.startswith("-S"):
                    return [], " ".join([word[2:], *words[i + 1 :]])
                i += 2 if word in GUARD_ENV_VALUE_OPTIONS else 1
        elif name in GUARD_WRAPPERS:
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in GUARD_WRAPPERS[name] else 1
        else:
            break
    return words[i:], None


def words_run(words: list[str], depth: int) -> bool:
    """True when one simple command, already split into words, runs the launcher.

    Wrapper words and uv run are looked through. The command word left is the
    launcher itself, python (python3, python3.12, any path to one), a shell with
    -c, eval or uv.
    """
    rest, string = strip_wrappers(words)
    if string is not None:
        return command_runs(string, depth + 1)
    if not rest:
        return False
    exe, args = Path(rest[0]).name, rest[1:]
    if exe == GUARD_NAME:
        return True
    if GUARD_PYTHON.fullmatch(exe):
        return python_runs(args)
    if exe in GUARD_SHELLS or exe == "eval":
        text = " ".join(args) if exe == "eval" else shell_string(args)
        return text is not None and command_runs(text, depth + 1)
    return exe in ("uv", "uvw") and uv_runs(args, depth)


def segment_runs(segment: str, depth: int = 0) -> bool:
    """True when the command segment runs the launcher (see words_run).

    A segment that shlex can't read (a quote cut by the split) falls back to a
    plain split with the quote marks stripped.
    """
    try:
        words = shlex.split(segment)
    except ValueError:
        words = [w.strip("'\"") for w in segment.split()]
    return words_run(words, depth)


def token_groups(command: str) -> list[list[str]] | None:
    """The simple commands of a line, split with shell quoting, as word lists.

    A quoted string that holds ; or | stays one word. Returns None when the line
    can't be tokenised, such as an unterminated quote.
    """
    lex = shlex.shlex(command.replace("`", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        tokens = list(lex)
    except ValueError:
        return None
    groups: list[list[str]] = [[]]
    for token in tokens:
        if set(token) <= GUARD_PUNCTUATION:
            groups.append([])
        else:
            groups[-1].append(token)
    return groups


def command_runs(command: str, depth: int = 0) -> bool:
    """True when a Bash command line runs this launcher.

    The line is split into command segments on newlines, ; && || | and &. Each
    segment is checked whole, and again after a split on $( ` ( ) { }, so a call
    inside a substitution or subshell is its own segment while a path built with
    $(...) or ${...} still counts for the segment around it. That split ignores
    quotes, so the line is also tokenised with shell quoting and each simple
    command checked again. The string after sh -c, bash -c, zsh -c or eval is
    checked as a command line of its own, up to GUARD_MAX_DEPTH levels deep. A line
    that names bartab.py but is too deep, or has a shell word and can't be
    tokenised, counts as a launcher call.
    """
    if GUARD_NAME not in command:
        return False
    if depth > GUARD_MAX_DEPTH:
        return True
    for hard in GUARD_HARD_SPLIT.split(command):
        for segment in [hard, *GUARD_SOFT_SPLIT.split(hard)]:
            if segment_runs(segment, depth):
                return True
    groups = token_groups(command)
    if groups is None:
        return GUARD_SHELL_WORD.search(command) is not None
    return any(words_run(group, depth) for group in groups)


def guard_denies(stream: TextIO) -> bool:
    """True when the PreToolUse input on stream is a Bash call that runs this launcher.

    Anything that is not a JSON object, or a Bash call without a text command,
    counts as a launcher call, so the guard fails closed.
    """
    try:
        data = as_dict(json.loads(stream.read(GUARD_STDIN_LIMIT)))
    except ValueError:
        return True
    if data is None:
        return True
    if data.get("tool_name") != "Bash":
        return False
    tool_input = as_dict(data.get("tool_input"))
    command = tool_input.get("command") if tool_input is not None else None
    if not isinstance(command, str):
        return True
    return command_runs(command)


def guard() -> int:
    """The hidden PreToolUse action. Print one deny line for a launcher call.

    Exit 0, except 1 when the deny line cannot be written, so the hook's
    onFailure block still blocks.
    """
    try:
        deny = guard_denies(sys.stdin)
    except Exception:  # noqa: BLE001
        deny = True
    if deny:
        try:
            say(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": GUARD_REASON,
                        }
                    }
                )
            )
            sys.stdout.flush()
        except (OSError, ValueError):
            return 1
    return 0


# --------------------------------------------------------------------------
# Entry point


def report(state: dict[str, bool], message: str, code: int) -> int:
    """Print an error. The skill path prints to stdout and exits 0."""
    if state["quiet"]:
        return 0
    if state["skill"]:
        say("error: " + message)
        return 0
    sys.stderr.write("error: " + message + "\n")
    return code


def run(argv: list[str], state: dict[str, bool]) -> int:
    """Parse the command line and run the action."""
    if any(word in ("-h", "--help") for word in argv):
        say(USAGE)
        return 0
    glob, action, opts = parse_args(argv, state)
    if action == "guard":
        return guard()
    if action == "session-end":
        session_end(glob)
        return 0
    if action == "_end":
        end_session(glob, opts)
        return 0
    run_locked(build_ctx(glob), action, opts)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the launcher and turn every failure into one error line."""
    args = list(sys.argv[1:] if argv is None else argv)
    state = {"skill": False, "quiet": False}
    try:
        return run(args, state)
    except Usage as exc:
        return report(state, f"{exc}. {USAGE}", 2)
    except Fail as exc:
        return report(state, str(exc), exc.code)
    except PermissionError:
        return report(state, SANDBOX_MESSAGE, 1)
    except KeyboardInterrupt:
        return report(state, "interrupted", 1)
    except Exception as exc:  # noqa: BLE001
        return report(state, "unexpected " + type(exc).__name__, 1)
    finally:
        with contextlib.suppress(OSError, ValueError):
            sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
