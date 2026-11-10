"""A decoy HOME and the read-audit assertion, shared by the read-scope tests.

``build_decoys`` makes a fake HOME inside ``tmp_path`` with everything the real-mode
read rule has to tell apart (m4-build.md section 7). Some files are allowed and some
are decoys that no server read may open or list. ``audited_server`` starts the server
through ``read_audit_child.py`` and ``assert_reads_allowed`` checks its log. Tasks 4 to
9 add their setup routes to ``test_real_reads.py`` with these two functions, so a new
collector is held to the same rule.

Allowed for a read, besides the scope's own answer: the app's code and its virtual
environment, the Python install, the store root, the static folder the test names, and
a short list of system files (``SYSTEM_PATHS``).
"""

import json
import os
import re
import subprocess
import sys
import sysconfig
import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/ is not on sys.path
import ingest_helpers as h
import test_real_mode as rm

import read_scope
import setup_contract
import store_provider
from models import SETUP_PARTS

HERE = Path(__file__).resolve().parent
SERVER_DIR = HERE.parent
APP_DIR = SERVER_DIR.parent
CHILD = HERE / "read_audit_child.py"
LOG_ENV = "BARTAB_READ_AUDIT_LOG"
SID_LISTED = "55555555-5555-4555-8555-555555555555"
SID_UNLISTED = "66666666-6666-4666-8666-666666666666"
DECOY_TEXT = "DECOY-CONTENT-MUST-NEVER-BE-READ"

# System files a Python server reads. Each is a path prefix, matched on a whole name.
SYSTEM_PATHS = (
    "/dev",
    "/etc/localtime",
    "/etc/mime.types",
    "/etc/apache2/mime.types",
    "/usr/share/zoneinfo",
    "/var/db/timezone",
    "/private/var/db/timezone",
    "/usr/lib",
    "/System",
)


def dashed(path: Path) -> str:
    """Return the transcript folder name Claude Code gives a project path."""
    return re.sub(r"[^a-zA-Z0-9]", "-", str(path))


@dataclass(frozen=True)
class Decoys:
    """A decoy HOME, with the paths a read may and may not touch.

    Attributes:
        root: The temp folder that holds everything.
        home: The fake HOME.
        config: ``<home>/.claude``.
        project: The one listed project, below a git root.
        outer: The git root, a parent of the project, with its own allowed and decoy
            files.
        unlisted: A project with transcripts that is not in the list.
        outside: A folder outside every root, the target of the symlinks.
        dist: The static folder the server is told to serve.
        allowed_files: Files a read may open, outside the scope's plain roots.
        decoys: Files and folders no read may open or list.
        followed: The real target of the single-file symlink in the project (allowed
            to read through the link, and reported by its real path).
    """

    root: Path
    home: Path
    config: Path
    project: Path
    outer: Path
    unlisted: Path
    outside: Path
    dist: Path
    allowed_files: tuple[Path, ...]
    decoys: tuple[Path, ...]
    followed: Path

    @property
    def store(self) -> Path:
        return self.config / "routing-dashboard" / "bartab"

    @property
    def listed_folder(self) -> Path:
        """The listed project's transcript folder."""
        return self.config / "projects" / dashed(self.project)

    def env(self) -> dict[str, str]:
        """An explicit environment: HOME, CLAUDE_CONFIG_DIR and what Python needs."""
        return {
            "HOME": str(self.home),
            "CLAUDE_CONFIG_DIR": str(self.config),
            "BARTAB_OFFLINE": "1",
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
        }

    def context(self, *, listed: bool = True) -> setup_contract.SetupContext:
        """The ``SetupContext`` a collector would get for the listed (or no) project."""
        return setup_contract.SetupContext(
            project_key="proj",
            config_dir=self.config,
            home=self.home,
            project_dir=self.project if listed else None,
            managed_dir=store_provider.managed_dir_for(sys.platform),
            real_mode=True,
        )

    def scope(self, *, listed: bool = True) -> read_scope.Scope:
        return read_scope.Scope(self.context(listed=listed))


def _write(path: Path, text: str = DECOY_TEXT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _transcript(folder: Path, sid: str, cwd: Path) -> None:
    rows = [
        h.assistant(0, "msg_a", sid=sid, cwd=str(cwd)),
        h.assistant(5, "msg_b", sid=sid, cwd=str(cwd)),
    ]
    _write(folder / f"{sid}.jsonl", b"\n".join(rows).decode() + "\n")


def build_decoys(tmp_path: Path) -> Decoys:  # noqa: PLR0915 - one tree, one list
    """Build the decoy tree in ``tmp_path``. Nothing in it is real."""
    root = tmp_path.resolve()
    home = root / "home"
    config = home / ".claude"
    outer = root / "work" / "outer"
    project = outer / "proj"
    unlisted = root / "work" / "unlisted"
    outside = root / "outside"
    dist = root / "dist"
    allowed: list[Path] = []
    decoys: list[Path] = []

    # The config folder, with the files a setup read may open.
    _write(config / "settings.json", '{"model": "claude-sonnet-5-5"}\n')
    _write(config / "agents" / "user-agent.md", "---\nname: user-agent\n---\nBody.\n")
    _write(config / "rules" / "style.md", "# style\n")
    _write(config / "CLAUDE.md", "# user memory file\n")
    allowed += [config / "settings.json", config / "agents" / "user-agent.md"]
    _write(
        config / "routing-dashboard.json",
        json.dumps({"projects": [{"name": "proj", "path": str(project)}]}) + "\n",
    )
    _write(config / "plugins" / "installed_plugins.json", "{}\n")
    _write(config / "plugins" / "cache" / "ok" / "plugin.json", '{"name": "ok"}\n')
    # A plugin whose install path points outside <config>/plugins/.
    elsewhere = _write(outside / "plugin-elsewhere" / "plugin.json", DECOY_TEXT)
    _write(
        config / "plugins" / "installed_plugins.json",
        json.dumps(
            {
                "version": 2,
                "plugins": {
                    "elsewhere@market": [
                        {"scope": "user", "installPath": str(elsewhere.parent)}
                    ]
                },
            }
        )
        + "\n",
    )
    decoys.append(elsewhere.parent)
    # Settings and CLAUDE.md files that sit in the home folder, plus an SSH-like key.
    _write(home / ".claude.json", '{"userID": "x"}\n')
    allowed.append(home / ".claude.json")
    decoys += [
        _write(home / ".ssh" / "id_rsa", "-----BEGIN FAKE KEY-----\n"),
        _write(home / "id_ed25519"),
        _write(home / "notes.txt"),
    ]

    # Transcripts, and the auto memory file that sits beside the listed project's.
    _transcript(config / "projects" / dashed(project), SID_LISTED, project)
    memory = _write(config / "projects" / dashed(project) / "memory" / "MEMORY.md")
    _transcript(config / "projects" / dashed(unlisted), SID_UNLISTED, unlisted)
    decoys.append(memory.parent)

    # The git root above the project: its CLAUDE.md files and local settings are
    # allowed, everything else in it is a decoy.
    (outer / ".git").mkdir(parents=True)
    _write(outer / "CLAUDE.md", "# outer\n")
    _write(outer / "CLAUDE.local.md", "# outer local\n")
    _write(outer / ".claude" / "settings.local.json", '{"effortLevel": "high"}\n')
    allowed += [
        outer / "CLAUDE.md",
        outer / "CLAUDE.local.md",
        outer / ".claude" / "settings.local.json",
    ]
    decoys += [
        _write(outer / "secrets.txt"),
        _write(outer / ".claude" / "settings.json", '{"model": "decoy"}\n'),
        _write(outer / ".claude" / "agents" / "decoy.md", "---\nname: decoy\n---\n"),
        _write(outer / "sibling" / "CLAUDE.md"),
    ]
    # An ancestor above the git root: its CLAUDE.md is allowed, its other files are not.
    allowed.append(_write(root / "work" / "CLAUDE.md", "# work folder\n"))
    decoys.append(_write(root / "work" / "stray.txt"))

    # The listed project.
    _write(project / ".claude" / "settings.json", '{"effort": "high"}\n')
    _write(project / ".claude" / "agents" / "mine.md", "---\nname: mine\n---\nBody.\n")
    _write(project / "CLAUDE.md", "# project\n")
    _write(project / "sub" / "CLAUDE.md", "# nested\n")
    allowed += [project / ".claude" / "settings.json", project / "CLAUDE.md"]

    # The unlisted project: nothing under it is read, though transcripts point at it.
    decoys += [
        _write(unlisted / ".claude" / "settings.json", '{"model": "decoy"}\n'),
        _write(unlisted / ".claude" / "agents" / "x.md", "---\nname: x\n---\n"),
        _write(unlisted / "CLAUDE.md"),
        unlisted,
    ]

    # Symlinks that lead outside. A folder is never entered. A single file is read.
    target = outside / "linked-target"
    decoys += [
        _write(target / "evil.md", "---\nname: evil\n---\n"),
        target,
    ]
    (project / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
    (project / ".claude" / "agents" / "linked").symlink_to(target)
    (project / "linked-folder").symlink_to(target)
    followed = _write(outside / "dotfiles" / "CLAUDE.md", "# from a dotfiles repo\n")
    (project / "linked-file.md").symlink_to(followed)
    # A link inside the config folder to the memory file.
    (project / "memory-link.md").symlink_to(memory)

    dist.mkdir()
    _write(dist / "index.html", rm.INDEX)
    return Decoys(
        root=root,
        home=home,
        config=config,
        project=project,
        outer=outer,
        unlisted=unlisted,
        outside=outside,
        dist=dist,
        allowed_files=tuple(allowed),
        decoys=tuple(decoys),
        followed=followed,
    )


# ------------------------------------------------------------------ the server


@dataclass
class AuditedServer:
    """A running audited server and the log its hook writes."""

    server: rm.Server
    log: Path


@contextmanager
def audited_server(
    decoys: Decoys, *, extra_args: Iterable[str] = ()
) -> Generator[AuditedServer]:
    """Start ``--real`` through ``read_audit_child.py`` and stop it on exit.

    The environment is explicit: HOME, CLAUDE_CONFIG_DIR, the offline switch, PATH, LANG
    and the log's path. The project folder is the listed project, so the model check
    reads it.
    """
    log = decoys.root / "reads.log"
    server_log = decoys.root / "server.log"
    process: subprocess.Popen[bytes] | None = None
    read_fd = -1
    line: dict[str, object] = {}
    for _attempt in range(3):
        port = rm.free_port()
        read_fd, write_fd = os.pipe()
        with server_log.open("ab") as out:
            process = subprocess.Popen(  # noqa: S603
                [
                    sys.executable,
                    "-B",
                    str(CHILD),
                    "--real",
                    "--port",
                    str(port),
                    "--project-dir",
                    str(decoys.project),
                    "--idle-exit-minutes",
                    "30",
                    "--launch-fd",
                    str(write_fd),
                    "--dist",
                    str(decoys.dist),
                    *extra_args,
                ],
                cwd=SERVER_DIR,
                env={**decoys.env(), LOG_ENV: str(log)},
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=out,
                pass_fds=(write_fd,),
            )
        os.close(write_fd)
        try:
            line = rm.read_line(read_fd)
            break
        except AssertionError:
            process.kill()
            process.wait()
            os.close(read_fd)
            if "could not bind" not in server_log.read_text(errors="replace"):
                raise
    assert process is not None
    keys = httpx2.post(
        f"http://127.0.0.1:{line['port']}/api/access/swap",
        json={"code": line["code"]},
        timeout=10,
    ).json()
    server = rm.Server(
        process, server_log, int(str(line["port"])), keys["read_key"], None
    )
    try:
        yield AuditedServer(server, log)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(read_fd)


def poll_the_pages(audited: AuditedServer) -> None:
    """First run, the app, the projects, the timeline, Agents, Summary and Setup.

    The Setup routes (task 9) read the config folders on every cold request, so the
    audit sees every file they open.
    """
    server = audited.server
    server.wait_until(
        lambda: server.get("/api/app")["ingest"]["state"] == "done", "first run"
    )
    # The project mapping is cached for 5 s, so the unlisted project shows up late.
    server.wait_until(
        lambda: len(server.get("/api/projects")["projects"]) >= 2,
        "the listed and the unlisted project",
        seconds=30,
    )
    projects = server.get("/api/projects")["projects"]
    deadline = time.monotonic() + 30
    keys = [p["key"] for p in projects]
    ended: list[tuple[str, str]] = []
    while time.monotonic() < deadline and len(ended) < len(keys):
        ended = []
        for key in keys:
            live = server.get(f"/api/live/sessions?project={key}")
            if live["latest_ended"] is not None:
                ended.append((key, live["latest_ended"]["id"]))
        if len(ended) < len(keys):
            time.sleep(0.2)
    assert ended, "no ended session"
    for key, session in ended:
        server.get(f"/api/sessions/{session}/timeline?project={key}")
    for key in keys:
        server.get(f"/api/agents?project={key}")
        server.get(f"/api/summary?project={key}")
        server.get(f"/api/setup?project={key}")
        server.get(f"/api/problems?project={key}")
        for part in SETUP_PARTS:
            server.get(f"/api/setup/{part}?project={key}")


# ------------------------------------------------------------------ the assertion


def read_log(path: Path) -> list[tuple[str, str]]:
    """Return the hook's log as ``(event, absolute path)`` pairs."""
    pairs: list[tuple[str, str]] = []
    for text in path.read_text(encoding="utf-8", errors="replace").splitlines():
        event, _tab, target = text.partition("\t")
        if target:
            pairs.append((event, target))
    return pairs


def _prefixes(extra: Iterable[Path]) -> list[str]:
    """Return the non-scope places a Python server may read."""
    found: set[str] = {str(APP_DIR), str(APP_DIR.resolve())}
    for value in (
        sys.prefix,
        sys.base_prefix,
        sys.exec_prefix,
        sys.base_exec_prefix,
        *sysconfig.get_paths().values(),
    ):
        found.add(value)
        found.add(os.path.realpath(value))
    found.update(SYSTEM_PATHS)
    found.update(str(p) for p in extra)
    return sorted(found)


def _under(path: str, base: str) -> bool:
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def assert_reads_allowed(
    entries: Iterable[tuple[str, str]],
    decoys: Decoys,
    *,
    scope: read_scope.Scope,
    extra_roots: Iterable[Path] = (),
    followed: Iterable[Path] = (),
) -> None:
    """Fail when any logged read is outside the allowed places or touches a decoy.

    A read is fine when the scope allows it, when it is under the app, the Python
    install, a system file in ``SYSTEM_PATHS`` or one of ``extra_roots`` (the store
    root, and the static folder), or when it is the real target of an allowed
    single-file symlink in ``followed``. A read of a decoy fails even if one of those
    would allow it.

    Args:
        entries: ``read_log`` pairs.
        decoys: The tree, for the decoy list.
        scope: The scope for the listed project (``decoys.scope()``).
        extra_roots: Places beyond the scope that the server owns.
        followed: Real paths of single-file symlinks a collector followed.
    """
    others = _prefixes([*extra_roots, *followed])
    decoy_paths = [str(p) for p in decoys.decoys]
    bad: list[str] = []
    for event, path in entries:
        if any(_under(path, decoy) for decoy in decoy_paths):
            bad.append(f"DECOY {event} {path}")
            continue
        if scope.allows(path, folder=event != "open"):
            continue
        if any(_under(path, base) for base in others):
            continue
        bad.append(f"OUTSIDE {event} {path}")
    if bad:
        pytest.fail("reads outside the allowed places:\n" + "\n".join(sorted(set(bad))))
