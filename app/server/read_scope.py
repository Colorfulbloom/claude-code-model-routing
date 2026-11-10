"""The one read path for the setup read side, and the real-mode read rule it holds.

Every setup collector opens files, lists folders and fingerprints paths through this
module and no other (m4-build.md section 7). A ``Scope`` is built from a
``SetupContext`` and knows the project's allowed roots. Each path is checked after
``realpath``, so ``..`` tricks and a symlink inside a root that points out of it are
caught. A refusal or a failure is an ``UnreadableFile`` with a reason, never an
exception.

Allowed, for one project (owner answers in m4-build.md section 15):

- The config folder, but never ``projects/*/memory/`` (answer 8, no auto memory).
- The listed project's folder. An unlisted project has none, so nothing under its
  ``cwd`` is read.
- The managed settings folder, and ``<config>/plugins/``.
- Exactly ``CLAUDE.md`` and ``CLAUDE.local.md`` in each ancestor of the listed
  project up to the filesystem root, and ``.claude/settings.local.json`` in the git
  root when that root is not the project (answer 5; ``git_root`` finds it by
  ``lstat`` alone).
- One Claude settings file next to the home folder (``claude_json_path``).

Symlinks (answer 7). A single file whose real path leaves the roots is followed and
read, and ``Snapshot.real_path`` reports where it really is. A symlinked folder whose
real path leaves the roots is not entered (``outside_scope``). ``walk`` never enters
a symlinked folder at all, so a link cycle cannot loop it.

A read is one byte snapshot: the file is opened once, ``fstat`` says it is a regular
file, and at most the cap plus one byte is read (research 26-08). ``read_text`` retries
the read once when its parse callback fails, because Claude Code rewrites some of
these files in place. ``stat_signature`` only calls ``lstat`` (and ``stat`` on a
followed link's target) and never opens anything.
"""

# ruff: noqa: PTH100, PTH113, PTH114, PTH116, PTH118, PTH120, PTH208 - paths are
# checked as strings after realpath, so the string forms of abspath, join, dirname,
# islink, isfile, stat and listdir are the point.

import hashlib
import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import git_root
from models import SetupScope, UnreadableFile, UnreadableReason
from setup_contract import (
    WALK_MAX_DEPTH,
    WALK_MAX_FOLDERS,
    WALK_SKIP_NAMES,
    SetupContext,
)

ANCESTOR_FILES = ("CLAUDE.md", "CLAUDE.local.md")
CLAUDE_JSON = ".claude.json"
_CHUNK = 64 * 1024
_MEMORY_DEPTH = 2  # projects/<folder>/memory: the third part of a path

PathLike = str | os.PathLike[str]
WalkKind = Literal["claude_md", "claude_local_md", "skills"]


def _abs(path: PathLike) -> str:
    """Return the path as an absolute string with ``..`` collapsed (no symlinks)."""
    return os.path.abspath(str(os.fspath(path)))


def _real(path: str) -> str:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return os.path.abspath(path)


def _under(path: str, base: str) -> bool:
    """True when path is base or below it. The boundary is a whole folder name."""
    return path == base or path.startswith(base.rstrip(os.sep) + os.sep)


def _rel(path: str, base: str) -> str | None:
    """Return the posix part of path below base ("" for base itself), or None."""
    if not _under(path, base):
        return None
    if path == base:
        return ""
    return Path(os.path.relpath(path, base)).as_posix()


@dataclass(frozen=True)
class Access:
    """A path the scope allows.

    Attributes:
        path: What to open: the real path.
        followed_out: True when a single-file symlink led out of the roots, so
            ``path`` is the real path the page should report.
    """

    path: str
    followed_out: bool


@dataclass(frozen=True)
class Snapshot:
    """One snapshot of a file.

    Attributes:
        data: The bytes read.
        real_path: The real path, only when a single-file symlink led out of the
            allowed roots. None otherwise.
    """

    data: bytes
    real_path: str | None


@dataclass(frozen=True)
class WalkHit:
    """One file or folder the capped walk found. ``path`` is a real path."""

    kind: WalkKind
    path: str


@dataclass
class WalkResult:
    """What ``walk`` found.

    Attributes:
        hits: CLAUDE.md, CLAUDE.local.md and ``.claude/skills`` hits, in walk order.
        stopped: True when a cap cut the walk short (``walk_stopped``, Can't tell).
        unreadable: A start folder outside the roots, or a folder that would not list.
        folders: How many folders were listed.
        touched: Every folder listed, for the signature.
    """

    hits: list[WalkHit] = field(default_factory=list[WalkHit])
    stopped: bool = False
    unreadable: list[UnreadableFile] = field(default_factory=list[UnreadableFile])
    folders: int = 0
    touched: list[str] = field(default_factory=list[str])


class Scope:
    """The allowed roots for one project, built from its ``SetupContext``."""

    def __init__(self, ctx: SetupContext) -> None:
        """Work out the roots and the exact files. Only ``lstat`` calls are made.

        Args:
            ctx: The project's context. Nothing is read from the environment.
        """
        self.ctx = ctx
        self._config = _real(str(ctx.config_dir))
        self._home = _real(str(ctx.home)) if ctx.home is not None else None
        self._project = (
            _real(str(ctx.project_dir)) if ctx.project_dir is not None else None
        )
        self._managed = (
            _real(str(ctx.managed_dir)) if ctx.managed_dir is not None else None
        )
        self._plugins = _real(os.path.join(self._config, "plugins"))
        roots = [self._config, self._plugins]
        if self._project is not None:
            roots.append(self._project)
        if self._managed is not None:
            roots.append(self._managed)
        self._roots = tuple(dict.fromkeys(roots))
        self._local_file: str | None = None
        files: list[str] = []
        if self._project is not None:
            here = self._project
            while (parent := os.path.dirname(here)) != here:
                here = parent
                files.extend(os.path.join(here, name) for name in ANCESTOR_FILES)
            local = git_root.local_settings_path(self._project, self._home)
            if local is not None:
                self._local_file = str(local)
                files.append(self._local_file)
        json_path = self.claude_json_path()
        if json_path is not None:
            files.append(_real(str(json_path)))
        self._files = frozenset(files)

    # ------------------------------------------------------------ what is allowed

    @property
    def roots(self) -> tuple[str, ...]:
        """The allowed roots, as real paths."""
        return self._roots

    @property
    def files(self) -> frozenset[str]:
        """The exact files allowed outside the roots, as real paths."""
        return self._files

    def claude_json_path(self) -> Path | None:
        """Return the one settings file the scope allows beside the config folder.

        With the default config folder (``<home>/.claude``) it is
        ``<home>/.claude.json``. With any other config folder (``CLAUDE_CONFIG_DIR``
        set) it is ``<config>/.claude.json``, because Claude Code then ignores the
        home file (research 26-08 line 9), so the home file is never read. Without a
        home folder the config folder's file is the only candidate. The answer never
        depends on which files exist.
        """
        inside = Path(self._config) / CLAUDE_JSON
        if self._home is None:
            return inside
        if self._config == _real(os.path.join(self._home, ".claude")):
            return Path(self._home) / CLAUDE_JSON
        return inside

    def _is_memory(self, path: str) -> bool:
        rel = _rel(path, self._config)
        if not rel:
            return False
        parts = rel.split("/")
        return (
            len(parts) > _MEMORY_DEPTH
            and parts[0] == "projects"
            and parts[_MEMORY_DEPTH] == "memory"
        )

    def _inside(self, path: str) -> bool:
        if path in self._files:
            return True
        return any(_under(path, root) for root in self._roots)

    def access(self, path: PathLike, *, folder: bool = False) -> Access | None:
        """Check one path after ``realpath``.

        Args:
            path: The path to check. ``..`` parts are collapsed before the check.
            folder: True for a folder. A symlinked folder that leads out of the roots
                is refused, where a symlinked file is followed.

        Returns:
            The real path to use, or None when the scope refuses it.
        """
        try:
            lexical = _abs(path)
        except (OSError, ValueError, TypeError):
            return None
        head, tail = os.path.split(lexical)
        candidate = os.path.join(_real(head), tail) if tail else _real(head)
        if self._is_memory(candidate) or not self._inside(candidate):
            return None
        real = _real(candidate)
        if self._is_memory(real):
            return None
        if self._inside(real):
            return Access(real, followed_out=False)
        if not folder and os.path.islink(candidate) and os.path.isfile(real):
            return Access(real, followed_out=True)
        return None

    def allows(self, path: PathLike, *, folder: bool = False) -> bool:
        """True when ``access`` allows the path."""
        return self.access(path, folder=folder) is not None

    # ------------------------------------------------------------ what to show

    def display(self, path: PathLike) -> str:
        """Return a display path: project relative, ``~/...``, or the managed name.

        An ancestor file the scope allows (CLAUDE.md above the project, the git root's
        local settings) shows relative to the project (``../CLAUDE.md``). Any other
        path outside every known folder shows its last part only, never an absolute
        path.
        """
        lexical = _abs(path)
        head, tail = os.path.split(lexical)
        forms = (lexical, os.path.join(_real(head), tail) if tail else lexical)
        zones: list[tuple[tuple[str, ...], Callable[[str], str]]] = []
        if self.ctx.project_dir is not None and self._project is not None:
            bases = (os.path.abspath(str(self.ctx.project_dir)), self._project)
            zones.append((bases, lambda rel: rel or "."))
        config_name = Path(self._config).name
        config_bases = (os.path.abspath(str(self.ctx.config_dir)), self._config)
        zones.append((config_bases, lambda rel: f"~/{config_name}/{rel}".rstrip("/")))
        if self.ctx.managed_dir is not None and self._managed is not None:
            managed_name = Path(self._managed).name
            managed_bases = (
                os.path.abspath(str(self.ctx.managed_dir)),
                self._managed,
            )
            zones.append(
                (managed_bases, lambda rel: f"{managed_name}/{rel}".rstrip("/"))
            )
        if self.ctx.home is not None and self._home is not None:
            home_bases = (os.path.abspath(str(self.ctx.home)), self._home)
            zones.append((home_bases, lambda rel: f"~/{rel}".rstrip("/")))
        for bases, show in zones:
            for form in forms:
                for base in bases:
                    rel = _rel(form, base)
                    if rel is not None:
                        return show(rel)
        if self._project is not None and forms[1] in self._files:
            return Path(os.path.relpath(forms[1], self._project)).as_posix()
        return tail or lexical

    def scope_of(self, path: PathLike) -> SetupScope | None:
        """Return which setup scope a path belongs to, or None when it fits none."""
        lexical = _abs(path)
        head, tail = os.path.split(lexical)
        candidate = os.path.join(_real(head), tail) if tail else lexical
        local = os.path.join(".claude", "settings.local.json")
        project_local = (
            self._project is not None
            and candidate == os.path.join(self._project, local)
        ) or candidate == self._local_file
        if project_local:
            return "project_local"
        if self._managed is not None and _under(candidate, self._managed):
            return "managed"
        if _under(candidate, self._plugins):
            return "plugin"
        if _under(candidate, self._config):
            return "user"
        if self._project is not None and _under(candidate, self._project):
            return "project"
        return None

    def unreadable(
        self, path: PathLike, reason: UnreadableReason, *, plugin: bool = False
    ) -> UnreadableFile:
        """Build the answer row for a file that could not be read.

        Args:
            path: The path that failed.
            reason: Why.
            plugin: True for a plugin install path. A refusal then says
                ``plugin_outside_plugins`` instead of ``outside_scope``.

        Returns:
            The row. ``problem`` is None, because the problems feed fills it in.
        """
        if plugin and reason == "outside_scope":
            reason = "plugin_outside_plugins"
        return UnreadableFile(
            file=self.display(path),
            full_path=_abs(path),
            scope=self.scope_of(path),
            reason=reason,
            problem=None,
        )


# ---------------------------------------------------------------- reading


def _read_open(fd: int, cap: int) -> bytes | UnreadableReason:
    """Read an open file descriptor, at most ``cap`` bytes."""
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode):
        return "vanished"
    if info.st_size > cap:
        return "too_large"
    chunks: list[bytes] = []
    total = 0
    while chunk := os.read(fd, min(_CHUNK, cap + 1 - total)):
        chunks.append(chunk)
        total += len(chunk)
        if total > cap:
            return "too_large"
    return b"".join(chunks)


def _snapshot(real: str, cap: int) -> bytes | UnreadableReason:
    """Open ``real`` once and read at most ``cap`` bytes, or say why not."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(real, flags)
    except (FileNotFoundError, NotADirectoryError):
        return "vanished"
    except OSError:
        return "permission"
    try:
        return _read_open(fd, cap)
    except OSError:
        return "permission"
    finally:
        os.close(fd)


def read_snapshot(
    scope: Scope, path: PathLike, cap: int, *, plugin: bool = False
) -> Snapshot | UnreadableFile:
    """Read one file as one byte snapshot.

    Args:
        scope: The project's scope.
        path: The file.
        cap: The most bytes to accept, from ``setup_contract``. A file over it is
            ``too_large``.
        plugin: True for a plugin install path, so a refusal reads
            ``plugin_outside_plugins``.

    Returns:
        The snapshot, or an ``UnreadableFile`` with ``outside_scope``, ``permission``,
        ``too_large`` or ``vanished``. It never raises.
    """
    allowed = scope.access(path)
    if allowed is None:
        return scope.unreadable(path, "outside_scope", plugin=plugin)
    got = _snapshot(allowed.path, cap)
    if isinstance(got, str):
        return scope.unreadable(path, got)
    return Snapshot(got, allowed.path if allowed.followed_out else None)


def read_bytes(
    scope: Scope, path: PathLike, cap: int, *, plugin: bool = False
) -> bytes | UnreadableFile:
    """Read one file's bytes. See ``read_snapshot``; this drops the real path."""
    got = read_snapshot(scope, path, cap, plugin=plugin)
    return got.data if isinstance(got, Snapshot) else got


def _decode(
    scope: Scope, path: PathLike, cap: int, *, plugin: bool
) -> str | UnreadableFile:
    got = read_bytes(scope, path, cap, plugin=plugin)
    if isinstance(got, UnreadableFile):
        return got
    try:
        return got.decode("utf-8")
    except UnicodeDecodeError:
        return scope.unreadable(path, "not_utf8")


def read_text(
    scope: Scope,
    path: PathLike,
    cap: int,
    *,
    parse: Callable[[str], object] | None = None,
    plugin: bool = False,
) -> str | UnreadableFile:
    """Read one file as strict UTF-8 text.

    Args:
        scope: The project's scope.
        path: The file.
        cap: The most bytes to accept.
        parse: An optional check the text must pass. It raises ``ValueError`` (which
            ``json.JSONDecodeError`` is) for text it cannot parse. When it does, the
            file is read once more, because Claude Code may have been mid-write
            (research 26-08), and that second text is returned whether or not it
            parses. The caller parses it again and reports the failure.
        plugin: True for a plugin install path.

    Returns:
        The text, or an ``UnreadableFile``. Bytes that are not UTF-8 are ``not_utf8``.
    """
    text = _decode(scope, path, cap, plugin=plugin)
    if parse is None or isinstance(text, UnreadableFile):
        return text
    try:
        parse(text)
    except ValueError:
        return _decode(scope, path, cap, plugin=plugin)
    return text


def list_dir(
    scope: Scope, path: PathLike, *, plugin: bool = False
) -> list[str] | UnreadableFile:
    """List a folder's entry names, sorted.

    Returns:
        The names, or an ``UnreadableFile``. A symlinked folder that leads out of the
        roots is ``outside_scope``, a missing one is ``vanished`` and one that will
        not list is ``folder_unlistable``.
    """
    allowed = scope.access(path, folder=True)
    if allowed is None:
        return scope.unreadable(path, "outside_scope", plugin=plugin)
    try:
        return sorted(os.listdir(allowed.path))
    except (FileNotFoundError, NotADirectoryError):
        return scope.unreadable(path, "vanished")
    except OSError:
        return scope.unreadable(path, "folder_unlistable")


def symlink_target(scope: Scope, path: PathLike) -> str | None:
    """Return the display path of a symlink's real target, or None for a plain path."""
    lexical = _abs(path)
    try:
        if not os.path.islink(lexical):
            return None
    except OSError:
        return None
    return scope.display(_real(lexical))


# ---------------------------------------------------------------- the walk


def _skills_folder(base: str) -> str | None:
    """Return ``<base>/.claude/skills`` when it is a real folder, else None."""
    skills = os.path.join(base, ".claude", "skills")
    try:
        if stat.S_ISDIR(os.lstat(skills).st_mode):
            return skills
    except OSError:
        return None
    return None


def _scan(base: str) -> list[os.DirEntry[str]]:
    with os.scandir(base) as entries:
        return sorted(entries, key=lambda entry: entry.name)


def _is_dir(entry: os.DirEntry[str]) -> bool:
    try:
        return entry.is_dir(follow_symlinks=False)
    except OSError:
        return False


def _is_file(entry: os.DirEntry[str]) -> bool:
    try:
        return entry.is_file()
    except OSError:
        return False


def _note_files(base: str, entries: list[os.DirEntry[str]], out: WalkResult) -> None:
    """Add the CLAUDE.md, CLAUDE.local.md and ``.claude/skills`` hits of one folder."""
    for entry in entries:
        if entry.name == "CLAUDE.md" and _is_file(entry):
            out.hits.append(WalkHit("claude_md", entry.path))
        elif entry.name == "CLAUDE.local.md" and _is_file(entry):
            out.hits.append(WalkHit("claude_local_md", entry.path))
        elif entry.name == ".claude" and _is_dir(entry):
            skills = _skills_folder(base)
            if skills is not None:
                out.hits.append(WalkHit("skills", skills))


def walk(scope: Scope, start: PathLike, *, plugin: bool = False) -> WalkResult:
    """Walk a folder tree for nested CLAUDE.md files and ``.claude/skills`` folders.

    The walk lists folders and returns only CLAUDE.md, CLAUDE.local.md and
    ``.claude/skills`` hits. It skips dot folders other than ``.claude`` (which it
    looks into for ``skills`` but does not list), the names in ``WALK_SKIP_NAMES`` and
    every symlinked folder. It goes ``WALK_MAX_DEPTH`` levels deep and lists at most
    ``WALK_MAX_FOLDERS`` folders. When a cap leaves folders unlisted, ``stopped`` is
    True.

    Args:
        scope: The project's scope.
        start: The folder to walk, inside the allowed roots.
        plugin: True for a plugin install path.

    Returns:
        The result. A start folder outside the roots is one ``outside_scope`` row in
        ``unreadable`` and no hits.
    """
    out = WalkResult()
    allowed = scope.access(start, folder=True)
    if allowed is None:
        out.unreadable.append(scope.unreadable(start, "outside_scope", plugin=plugin))
        return out
    pending: list[tuple[str, int]] = [(allowed.path, 0)]
    while pending:
        base, depth = pending.pop()
        if out.folders >= WALK_MAX_FOLDERS:
            out.stopped = True
            break
        out.folders += 1
        out.touched.append(base)
        try:
            entries = _scan(base)
        except OSError:
            out.unreadable.append(scope.unreadable(base, "folder_unlistable"))
            continue
        _note_files(base, entries, out)
        children = [
            entry.path
            for entry in entries
            if _is_dir(entry)
            and not entry.name.startswith(".")
            and entry.name not in WALK_SKIP_NAMES
        ]
        if children and depth >= WALK_MAX_DEPTH:
            out.stopped = True
            continue
        pending.extend((child, depth + 1) for child in reversed(children))
    return out


# ---------------------------------------------------------------- the signature


def _state(info: os.stat_result) -> str:
    return f"{info.st_mode:o}:{info.st_size}:{info.st_mtime_ns}:{info.st_ino}"


def stat_signature(scope: Scope, paths: Iterable[PathLike]) -> str:
    """Return a fingerprint of the given paths from ``lstat`` alone.

    No file is opened. A symlink adds its target's ``stat``. A path the scope refuses
    adds a fixed mark and no stat call. The same paths in any order give the same
    answer, so a caller may pass a set.

    Args:
        scope: The project's scope.
        paths: The files and folders the last read touched.

    Returns:
        A hex digest. It changes when a path appears, vanishes or changes mode, size
        or modification time.
    """
    digest = hashlib.sha256()
    for raw in sorted({_abs(p) for p in paths}):
        allowed = scope.access(raw)
        if allowed is None and scope.access(raw, folder=True) is None:
            state = "outside"
        else:
            try:
                info = os.lstat(raw)
                state = _state(info)
                if stat.S_ISLNK(info.st_mode):
                    state += "->" + _state(os.stat(raw))
            except (FileNotFoundError, NotADirectoryError):
                state = "-"
            except OSError:
                state = "!"
        digest.update(f"{raw}\0{state}\n".encode())
    return digest.hexdigest()
