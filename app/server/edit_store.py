"""The one writer: a settings edit, checked, backed up first, atomic, and recorded.

The plan is ``docs/rebuild/planning/m6-build.md`` sections 2, 3.3 to 3.7, 3.9 and
4.3. This is the port of ``dashboard/edit_store.py`` for the new app, and it has to
interoperate with it. It uses the same backups folder, the same ledger and lock
files and the same target id. The backups folder is
``<config>/routing-dashboard/backups/<target id>/``. The ledger is ``ledger.json``
version 1, and the lock is ``.lock`` taken with ``fcntl.flock``. The target id is
``sha256(fsencode(realpath(file)))[:16]``.

Security rules, in the order a call meets them.

- Registry only. A ``Target`` can be built only by ``settings_targets`` and
  ``settings_target``, from a project folder and a scope. No path ever comes from a
  client.
- Resolve once. ``resolve_target`` follows every link to a real path and checks it
  against the never-writable list (managed settings, plugin folders, any
  ``.claude.json``, the store and backups folders), against ``link_outside`` and
  ``link_dangling``, and against the checkout in fixture and demo runs.
- Never follow again. ``_walk`` opens a trusted base (the real home folder, the real
  project root or the target's own base) with ``O_DIRECTORY | O_NOFOLLOW`` and opens
  each component below it the same way. A component that became a link, or a folder
  that changed identity, is ``changed``.
- Files are written by absolute path, because the write guard refuses a relative write
  ``open`` (section 3.5). Each file is confirmed with ``fstat`` on the new fd and
  ``os.stat(name, dir_fd=, follow_symlinks=False)`` against the folder fd. Renames and
  removes pass ``dir_fd`` and run under ``write_guard.permit``.
- Order of a save, under the target lock and the ``flock`` (section 3.6). Read once and
  check the token. Back up with ``O_EXCL``. Write the ledger row. Write the temp file.
  Walk again and compare. Rename by ``dir_fd``, fsync, read back. Prune to 20 rows.
  Schedule the rechecks.

A call runs whole in the calling thread, with no ``await``. The permit is thread-local.
The rechecks run later in their own timer threads and write only inside the backups
root.

The token is ``base64url(payload).base64url(HMAC)``. The payload is ``{v, target_id,
dev, ino, sha256, body_sha256, read_at}``. A bad tag, version or target is
``bad_version``, a body that differs is ``preview_mismatch``, and a file that differs
is ``changed``, checked in that order.

A refusal is a ``Refused`` with a code from ``models.EditRefusalCode``. Where the old
code named a cause that list lacks, the code is ``not_undoable``, ``changed`` or
``write_failed`` and ``params`` carries the cause.
"""

# ruff: noqa: N818, PLR0911, PLR0913, PLR0915, PLR0917, PLR2004, TRY301
# ruff: noqa: PTH102, PTH108, PTH112, PTH114, PTH118, PTH119, PTH120, PTH206, PTH208
#
# ``Refused`` keeps the name the old callers catch. The writer's entry points take the
# call's inputs by keyword, and its steps keep the branch and statement counts of the
# old ``_apply`` so the two read side by side. The walk and the guard speak in
# descriptors and path strings, as ``write_guard`` does, and ``os.listdir`` takes an
# fd, which ``pathlib`` can't.

from __future__ import annotations

import base64
import binascii
import collections
import contextlib
import datetime
import errno
import fcntl
import functools
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import stat
import threading
import time
from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NoReturn, TypeVar, cast, get_args

import claude_version
import edit_fields
import edit_switch
import git_root
import json_edit
import masking
import store_paths
import write_guard
from models import (
    EditRefusalCode,
    EditSaveRequest,
    EditScope,
    EditUndoRequest,
    SettingsEditField,
    UndoState,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

__all__ = [
    "ABSENT",
    "BACKUPS_DIR",
    "EditContext",
    "EditStore",
    "FileBytes",
    "Inspected",
    "Plan",
    "Refused",
    "Resolved",
    "RowStatus",
    "SaveResult",
    "Target",
    "UndoResult",
    "canonical_body",
    "choice_key",
    "plan_set",
    "settings_target",
    "settings_targets",
    "target_id_of",
]

LOG = logging.getLogger("bartab.edit")

RETENTION = 20
MAX_FILE = 1024 * 1024
MAX_LEDGER = 4 * MAX_FILE
LOCK_WAIT = 5.0
STORE_DIR = "routing-dashboard"
BACKUPS_DIR = "backups"
LEDGER_FILE = "ledger.json"
LOCK_FILE = ".lock"
MANAGED_FILE = "managed-settings.json"
MANAGED_FOLDER = "managed-settings.d"
CLAUDE_JSON_PREFIX = ".claude.json"
PLUGINS_DIR = "plugins"
ABSENT = "absent"  # a row's hash for a file that is not there; never 64 hex characters
FIRST_ROOT_VERSION = "2.1.211"
TOKEN_VERSION = 1
RECHECK_DELAYS = (2.0, 10.0)
REQUEST_TTL = 600.0
REQUEST_CAP = 512
PREVIEW_CACHE = 64
MAX_CHANGED_KEYS = 50
SCOPES: tuple[EditScope, ...] = ("user", "project", "local")

_BACKUP_RE = re.compile(r"^(\d{6})-[0-9a-f]{16}\.(?:bak|absent)$")
_REAL_BACKUP_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.bak$")
_MARKER_RE = re.compile(r"^\d{6}-[0-9a-f]{16}\.absent$")
_TEMP_RE = re.compile(r"^\.routing-dashboard-[0-9a-f]{16}\.tmp$")
_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CODES = frozenset(get_args(EditRefusalCode))
_ROW_KINDS = frozenset({"edit", "undo", "restore"})
# Temp file names a save in this process has made or is about to make, so another
# save's sweep of the same folder leaves them alone.
_LIVE_TEMPS: set[str] = set()
_LIVE_TEMPS_LOCK = threading.Lock()
# A temp file younger than this is left alone, because another process (the old app
# shares the name) may be between making it and the rename.
TEMP_SWEEP_AGE_SECONDS = 60.0
_ROW_OPS = frozenset({"replace", "insert", "create", "remove"})
_CANONICAL_DROP = ("seq", "version", "request_id")

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY
_SUBDIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_LEAF_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_NEW_FLAGS = os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW

Rows = list[dict[str, Any]]
Scalar = str | int | float | bool | None
Scheduler = Callable[[float, Callable[[], None]], None]
RowKind = Literal["edit", "undo", "restore"]
T = TypeVar("T")


# Errors


@dataclass(frozen=True)
class FileBytes:
    """The bytes of a file, or None for a file that was not there."""

    raw: bytes | None


class Refused(Exception):
    """A call the writer will not make. ``code`` is an ``EditRefusalCode``.

    ``params`` fill the page's string. ``row_id`` names a row the write already made
    (``raced`` and a failed read-back). ``preview`` holds the bytes the preview saw and
    ``current`` the bytes now, for ``changed`` and ``preview_mismatch``. For
    ``changed_since_save``, ``backup`` holds what the undo would write and
    ``undo_version`` the token that confirms "Undo anyway". ``dir_left`` is True when a
    save made a folder it could not take away again. ``real_path`` is where a refused
    link leads (``link_outside`` and ``link_dangling``), so the preview can say so. It
    never goes into an answer as it is, only through the display function.
    """

    def __init__(
        self,
        code: EditRefusalCode,
        params: Mapping[str, str] | None = None,
        *,
        row_id: str | None = None,
        preview: FileBytes | None = None,
        current: FileBytes | None = None,
        real_path: str | None = None,
    ) -> None:
        """Keep the code, its params and what the caller needs to build the answer."""
        super().__init__(code)
        self.code: EditRefusalCode = code
        self.params: dict[str, str] = dict(params or {})
        self.row_id = row_id
        self.preview = preview
        self.current = current
        self.real_path = real_path
        self.backup: FileBytes | None = None
        self.undo_version: str | None = None
        self.dir_left = False


def _from_json(exc: json_edit.Refused) -> Refused:
    """Map a ``json_edit`` refusal to the writer's, keeping its code."""
    code = exc.code
    if code not in _CODES:
        return Refused("oracle_failed")
    return Refused(cast("EditRefusalCode", code))


class _LedgerBadError(ValueError):
    """``ledger.json`` can't be read as rows."""


# Context and registry


@dataclass(frozen=True)
class EditContext:
    """What the writer needs to know about the machine, and never changes.

    Attributes:
        config_dir: The Claude config folder (``CLAUDE_CONFIG_DIR``, else
            ``HOME/.claude``).
        home: The home folder. Links may point below its real path.
        managed_dir: The managed settings folder, never writable. None when unknown.
        claude_version: The installed Claude Code version. Before 2.1.211 the local file
            stays in the project folder (the old ``local_root`` rule). None applies the
            git root rule.
        guard_checkout: True for a fixture or demo run, which may not write inside the
            Bar Tab checkout (``edit_switch.outside_checkout``).
        checkout: The checkout for that guard, for tests. Defaults to this one.
    """

    config_dir: Path
    home: Path
    managed_dir: Path | None = None
    claude_version: str | None = None
    guard_checkout: bool = False
    checkout: Path | None = None

    @property
    def backups_root(self) -> Path:
        """The old app's backups folder."""
        return store_paths.backups_dir(self.config_dir)

    @property
    def store_root(self) -> Path:
        """The Bar Tab store folder."""
        return store_paths.shared_store_root(self.config_dir)


_REGISTRY_KEY = object()


class Target:
    """One settings file: scope, base folder, folders below it and the file name.

    Only the registry builds these. A ``Target`` made any other way raises
    ``TypeError``, so ``EditStore`` can't be handed a path from a client.
    """

    __slots__ = ("base", "leftover", "name", "project_root", "rel", "scope")

    def __init__(
        self,
        key: object,
        scope: EditScope,
        base: str,
        rel: tuple[str, ...],
        name: str,
        *,
        leftover: bool = False,
        project_root: str | None = None,
    ) -> None:
        """Build a target. Only the registry holds ``key``."""
        if key is not _REGISTRY_KEY:
            msg = "a Target comes from the registry"
            raise TypeError(msg)
        self.scope = scope
        self.base = base
        self.rel = rel
        self.name = name
        self.leftover = leftover
        self.project_root = project_root

    @property
    def display_path(self) -> str:
        """The path as built, links not resolved."""
        return os.path.join(self.base, *self.rel, self.name)

    def __repr__(self) -> str:
        """Name the scope and the display path."""
        return f"Target({self.scope}, {self.display_path})"


def _make_target(
    scope: EditScope,
    base: str,
    rel: tuple[str, ...],
    name: str,
    *,
    leftover: bool = False,
    project_root: str | None = None,
) -> Target:
    return Target(
        _REGISTRY_KEY,
        scope,
        base,
        rel,
        name,
        leftover=leftover,
        project_root=project_root,
    )


def settings_targets(
    ctx: EditContext, project_dir: str | os.PathLike[str] | None
) -> list[Target]:
    """Return a project's settings files in scope order, as the old ``project_files``.

    The local layer is the repo root's ``settings.local.json`` when the project sits
    below its git root and Claude Code is 2.1.211 or later. When the root differs from
    the project, the project's own ``settings.local.json`` follows as a fourth target
    with ``leftover`` True. A save never writes it, but undo reaches its old rows.

    Args:
        ctx: The writer context.
        project_dir: The project's folder, or None for the user file alone.

    Returns:
        The targets: user, then project, local and a leftover local when there is a
        project.
    """
    out = [
        _make_target("user", os.fspath(ctx.config_dir), (), "settings.json"),
    ]
    if project_dir is None:
        return out
    project = os.fspath(project_dir)
    real_project = os.path.realpath(project)
    out.append(
        _make_target(
            "project",
            project,
            (".claude",),
            "settings.json",
            project_root=real_project,
        )
    )
    root_file: Path | None = None
    if not claude_version.older(ctx.claude_version, FIRST_ROOT_VERSION):
        root_file = git_root.local_settings_path(project, ctx.home)
    if root_file is None:
        out.append(
            _make_target(
                "local",
                project,
                (".claude",),
                "settings.local.json",
                project_root=real_project,
            )
        )
        return out
    out.append(
        _make_target(
            "local",
            str(root_file.parents[1]),
            (".claude",),
            "settings.local.json",
            project_root=real_project,
        )
    )
    out.append(
        _make_target(
            "local",
            project,
            (".claude",),
            "settings.local.json",
            leftover=True,
            project_root=real_project,
        )
    )
    return out


def settings_target(
    ctx: EditContext, project_dir: str | os.PathLike[str] | None, scope: EditScope
) -> Target:
    """Return the one file a save to ``scope`` would write.

    Raises:
        Refused: ``not_editable`` for a scope the registry doesn't know, or for the
            project scopes with no project.
    """
    if scope not in SCOPES:
        raise Refused("not_editable")
    for target in settings_targets(ctx, project_dir):
        if target.scope == scope and not target.leftover:
            return target
    raise Refused("not_editable")


# Resolving a target, once, at check time


@dataclass(frozen=True)
class Resolved:
    """A target with every link followed.

    Attributes:
        target: The registry target.
        real_path: The real file path.
        target_id: ``sha256(fsencode(real_path))[:16]``, the backups folder's name.
        trusted_base: The folder the walk opens first, with ``O_NOFOLLOW``.
        parts: The folders below the base that hold the file.
        name: The real file's name.
        link: True when a component of the display path is a link.
        may_make_dir: True when the last folder (``.claude``) is not there and a save
            may make it.
    """

    target: Target
    real_path: str
    target_id: str
    trusted_base: str
    parts: tuple[str, ...]
    name: str
    link: bool
    may_make_dir: bool

    @property
    def folder_path(self) -> str:
        """The real folder that holds the file, which may not exist yet."""
        return os.path.dirname(self.real_path)


def target_id_of(real_path: str) -> str:
    """Return the backups folder name for a real file path."""
    return hashlib.sha256(os.fsencode(real_path)).hexdigest()[:16]


def _real(path: str | os.PathLike[str]) -> str:
    return os.path.realpath(path)


def _under(path: str, folder: str) -> bool:
    folder = folder.rstrip(os.sep) or os.sep
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _scan_error(exc: OSError) -> Refused:
    if isinstance(exc, NotADirectoryError):
        return Refused("not_regular")
    if isinstance(exc, PermissionError):
        return Refused("not_owner")
    return Refused("write_failed", {"errno": errno.errorcode.get(exc.errno or 0, "?")})


def _scan(target: Target) -> tuple[str, bool, int | None]:
    """Follow the display path with ``lstat``.

    Returns the real path, whether any component was a link, and the index of the first
    component that is not there (None when all are). A dangling or looping link is
    ``link_dangling``.
    """
    cur = _real(target.base)
    if not os.path.isdir(cur):
        raise Refused("folder_not_found")
    link = False
    missing: int | None = None
    parts = (*target.rel, target.name)
    for index, part in enumerate(parts):
        nxt = os.path.join(cur, part)
        if missing is not None:
            cur = nxt
            continue
        try:
            info = os.lstat(nxt)
        except FileNotFoundError:
            missing = index
            cur = nxt
            continue
        except OSError as exc:
            raise _scan_error(exc) from None
        if stat.S_ISLNK(info.st_mode):
            link = True
            cur = _real(nxt)
            if not os.path.lexists(cur) or os.path.islink(cur):
                raise Refused("link_dangling", real_path=cur)
        else:
            cur = nxt
    return cur, link, missing


def _forbidden(ctx: EditContext, real: str) -> None:
    """Refuse a real path that is never writable. Links are already resolved."""
    name = os.path.basename(real)
    if (
        name == MANAGED_FILE
        or os.path.basename(os.path.dirname(real)) == MANAGED_FOLDER
    ):
        raise Refused("managed")
    if ctx.managed_dir is not None and _under(real, _real(ctx.managed_dir)):
        raise Refused("managed")
    if name.startswith(CLAUDE_JSON_PREFIX):
        raise Refused("forbidden_path")
    config = _real(ctx.config_dir)
    roots = (
        _real(ctx.store_root),
        _real(ctx.backups_root),
        os.path.join(config, STORE_DIR),
        os.path.join(config, PLUGINS_DIR),
    )
    if any(_under(real, root) for root in roots):
        raise Refused("forbidden_path")


def resolve_target(ctx: EditContext, target: Target) -> Resolved:
    """Follow every link of a target once and check the real path.

    Raises:
        Refused: ``folder_not_found``, ``link_dangling``, ``link_outside``,
            ``managed``, ``forbidden_path``, ``not_regular`` or ``not_editable`` (a
            fixture or demo run inside the checkout).
    """
    real, link, missing = _scan(target)
    leaf = len(target.rel)
    may_make = False
    if missing is not None:
        if target.rel and missing == leaf - 1:
            may_make = True
        elif missing != leaf:
            raise Refused("folder_not_found")
    _forbidden(ctx, real)
    home = _real(ctx.home)
    base = _real(target.base)
    if link:
        allowed = [home, *([target.project_root] if target.project_root else [])]
        if target.scope == "local":
            allowed.append(base)
        if not any(_under(real, root) for root in allowed):
            raise Refused("link_outside", real_path=real)
    if ctx.guard_checkout and not (
        edit_switch.outside_checkout(real, ctx.checkout)
        and edit_switch.outside_checkout(ctx.backups_root, ctx.checkout)
    ):
        raise Refused("not_editable", {"reason": "checkout"})
    folder = os.path.dirname(real)
    candidates = [
        c for c in (home, target.project_root, base) if c and _under(folder, c)
    ]
    if not candidates:  # pragma: no cover - the link rule above makes this unreachable
        raise Refused("link_outside")
    trusted = max(candidates, key=len)
    rel_folder = os.path.relpath(folder, trusted)
    parts = () if rel_folder == "." else tuple(rel_folder.split(os.sep))
    return Resolved(
        target=target,
        real_path=real,
        target_id=target_id_of(real),
        trusted_base=trusted,
        parts=parts,
        name=os.path.basename(real),
        link=link,
        may_make_dir=may_make,
    )


# The descriptor walk


@dataclass
class Snapshot:
    """One walk's result. The fds are valid only inside the ``with`` block."""

    folder_fd: int | None
    parent_fd: int | None
    raw: bytes | None
    mode: int | None
    dev: int
    ino: int
    folder_dev: int
    folder_ino: int
    missing_dir: bool

    @property
    def folder_id(self) -> tuple[int, int]:
        """The identity of the folder that holds the file, or of its parent."""
        return (self.folder_dev, self.folder_ino)


def _walk_error(exc: OSError, *, base: bool = False) -> Refused:
    code = exc.errno
    if code == errno.ENOENT:
        return Refused("folder_not_found" if base else "changed")
    if code in (errno.ELOOP, errno.ENOTDIR):
        return Refused("changed")
    if code in (errno.EACCES, errno.EPERM):
        return Refused("not_owner")
    if code in (errno.ENXIO, errno.EOPNOTSUPP, errno.ENODEV):
        return Refused("not_regular")
    return Refused("write_failed", {"errno": errno.errorcode.get(code or 0, "?")})


def _open_child(name: str, dir_fd: int, flags: int) -> int | None:
    """Open ``name`` under ``dir_fd``. None only when it is not there."""
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise _walk_error(exc) from None


def _read_capped(fd: int, cap: int) -> bytes:
    """Read up to ``cap`` + 1 bytes from ``fd``, in a loop."""
    chunks: list[bytes] = []
    total = 0
    while total <= cap:
        chunk = os.read(fd, cap + 1 - total)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
    return b"".join(chunks)


def _check_leaf(leaf: int) -> tuple[bytes, int, int, int]:
    """Check the opened file and read it. Returns bytes, mode, dev and ino."""
    info = os.fstat(leaf)
    if not stat.S_ISREG(info.st_mode):
        raise Refused("not_regular")
    if info.st_nlink != 1:
        raise Refused("hard_link")
    if info.st_uid != os.geteuid():
        raise Refused("not_owner")
    if info.st_size > MAX_FILE:
        raise Refused("too_large")
    raw = _read_capped(leaf, MAX_FILE)
    if len(raw) > MAX_FILE:
        raise Refused("too_large")
    return raw, stat.S_IMODE(info.st_mode), info.st_dev, info.st_ino


@contextlib.contextmanager
def _walk(rs: Resolved) -> Generator[Snapshot]:
    """Open the target by descriptors from the trusted base and yield a ``Snapshot``.

    Every folder opens with ``O_NOFOLLOW``, so a component that became a link fails
    with ``changed``. A missing last folder (``.claude``) or a missing file is a normal
    answer. Every fd closes when the block ends.
    """
    fds: list[int] = []
    try:
        try:
            dir_fd = os.open(rs.trusted_base, _SUBDIR_FLAGS)
        except OSError as exc:
            raise _walk_error(exc, base=True) from None
        fds.append(dir_fd)
        parent_fd: int | None = None
        missing_dir = False
        for index, part in enumerate(rs.parts):
            child = _open_child(part, dir_fd, _SUBDIR_FLAGS)
            if child is None:
                if not (rs.may_make_dir and index == len(rs.parts) - 1):
                    raise Refused("changed")
                missing_dir = True
                break
            fds.append(child)
            parent_fd, dir_fd = dir_fd, child
        folder = os.fstat(dir_fd)
        if missing_dir:
            yield Snapshot(
                None, dir_fd, None, None, folder.st_dev, folder.st_ino,
                folder.st_dev, folder.st_ino, True,
            )  # fmt: skip
            return
        leaf = _open_child(rs.name, dir_fd, _LEAF_FLAGS)
        if leaf is None:
            yield Snapshot(
                dir_fd, parent_fd, None, None, folder.st_dev, folder.st_ino,
                folder.st_dev, folder.st_ino, False,
            )  # fmt: skip
            return
        fds.append(leaf)
        raw, mode, dev, ino = _check_leaf(leaf)
        yield Snapshot(
            dir_fd, parent_fd, raw, mode, dev, ino, folder.st_dev, folder.st_ino, False
        )
    finally:
        for fd in fds:
            with contextlib.suppress(OSError):
                os.close(fd)


# Small file helpers


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hash_of(raw: bytes | None) -> str:
    return ABSENT if raw is None else _sha(raw)


def _fullfsync(fd: int) -> None:
    """``F_FULLFSYNC`` where the platform has it and allows it, else ``fsync``."""
    full = getattr(fcntl, "F_FULLFSYNC", None)
    if full is not None:
        with contextlib.suppress(OSError):
            fcntl.fcntl(fd, full)
            return
    os.fsync(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def _same_file(fd: int, name: str, folder_fd: int) -> None:
    """Refuse unless the open ``fd`` is the file ``name`` in the checked folder."""
    info = os.fstat(fd)
    try:
        named = os.stat(name, dir_fd=folder_fd, follow_symlinks=False)
    except OSError:
        raise Refused("changed") from None
    if (named.st_dev, named.st_ino) != (info.st_dev, info.st_ino):
        raise Refused("changed")


def _create_in(
    folder_fd: int,
    folder_path: str,
    name: str,
    data: bytes,
    *,
    mode: int = 0o600,
    final_mode: int | None = None,
) -> None:
    """Create ``name`` exclusively in a folder, write ``data`` and fsync fully.

    The open uses the absolute path, because the guard refuses a relative write open.
    ``fstat`` on the new fd and ``os.stat(name, dir_fd=folder_fd)`` then confirm that
    the file sits in the folder the fd names.
    """
    path = os.path.join(folder_path, name)
    fd = os.open(path, _NEW_FLAGS, mode)
    try:
        try:
            _same_file(fd, name, folder_fd)
        except Refused:
            with contextlib.suppress(OSError):
                os.unlink(path)
            raise
        _write_all(fd, data)
        if final_mode is not None:
            os.fchmod(fd, final_mode)
        _fullfsync(fd)
    finally:
        os.close(fd)


def _read_file(name: str, dir_fd: int, cap: int) -> bytes:
    """Return the bytes of a regular file under ``dir_fd``, not following a link."""
    fd = os.open(name, _LEAF_FLAGS, dir_fd=dir_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        return _read_capped(fd, cap)
    finally:
        os.close(fd)


def _unlink(name: str, dir_fd: int) -> None:
    with contextlib.suppress(OSError):
        os.unlink(name, dir_fd=dir_fd)


def _backup_number(name: object) -> int | None:
    match = _BACKUP_RE.match(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else None


def _valid_backup(name: object) -> bool:
    """A real backup name. A marker is not one: nothing may read it as bytes."""
    return isinstance(name, str) and _REAL_BACKUP_RE.match(name) is not None


def _valid_marker(name: object) -> bool:
    return isinstance(name, str) and _MARKER_RE.match(name) is not None


def _remove_dir(
    name: str, parent_fd: int | None, expected: tuple[int, int] | None
) -> bool:
    """Remove the empty folder ``name`` under ``parent_fd`` if it is still ``expected``.

    Never empties a folder. Returns True only when the folder was removed.
    """
    if parent_fd is None or expected is None:
        return False
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != expected:
            return False
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        return False
    return True


def _trim(rows: Rows, current: str | None) -> Rows:
    """Drop trailing rows that never applied (before matches the file, after not)."""
    if current is None:
        return list(rows)
    keep = list(rows)
    while keep:
        last = keep[-1]
        if last.get("before_sha256") == current and last.get("after_sha256") != current:
            keep.pop()
        else:
            break
    return keep


def _value_at(data: object, key_path: Sequence[str]) -> Scalar:
    """Return the scalar at ``key_path`` in parsed JSON, or None. Never raises.

    A secret-named step gives None, so a hidden parent is left out. So does a value
    that is not a str, int, float or bool.
    """
    node: Any = data
    for step in key_path:
        if (
            masking.is_secret_name(step)
            or not isinstance(node, dict)
            or step not in node
        ):
            return None
        node = cast("dict[str, Any]", node)[step]
    return node if isinstance(node, (str, int, float, bool)) else None


def _value_in(raw: bytes | None, key_path: Sequence[str]) -> Scalar:
    """Return the scalar at ``key_path`` in these bytes, or None."""
    if raw is None:
        return None
    try:
        _text, data = json_edit.parse_strict(raw)
    except json_edit.Refused:
        return None
    value = _value_at(data, key_path)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _key_path_of(row: Mapping[str, Any]) -> list[str]:
    """Return a row's key path as strings, [] when it is not a list."""
    raw: object = row.get("key_path")
    if not isinstance(raw, list):
        return []
    return [str(step) for step in cast("list[object]", raw)]


def _dict_of(value: object) -> dict[str, Any] | None:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def _changed_keys(before: object, after: object, prefix: str = "") -> list[str]:
    """List the dotted key paths whose value differs. Arrays count as one value."""
    left = _dict_of(before)
    right = _dict_of(after)
    if left is None or right is None:
        return [] if json_edit.same_value(before, after) else [prefix]
    keys: list[str] = []
    for key in sorted(set(left) | set(right)):
        path = f"{prefix}.{key}" if prefix else key
        if key not in left or key not in right:
            keys.append(path)
        else:
            keys.extend(_changed_keys(left[key], right[key], path))
    return keys


# Plans


@dataclass(frozen=True)
class Plan:
    """One planned edit: the new bytes and what changed.

    ``op`` is ``replace`` (the key was there), ``insert`` (it was not) or ``create``
    (the file was not there).
    """

    new_raw: bytes
    key_path: tuple[str, ...]
    old_value: Any
    new_value: Any
    op: Literal["replace", "insert", "create"]


def valid_key_path(field_name: SettingsEditField, key_path: Sequence[str]) -> bool:
    """True when ``key_path`` is one the registry allows for the field.

    That is the top-level key, an ``env`` twin, or a ``modelSettings.<model>.<field>``
    entry.
    """
    item = edit_fields.FIELDS[field_name]
    path = tuple(key_path)
    if path == (item.top_key,):
        return True
    if len(path) == 2 and path[0] == "env":
        return path[1] in item.env_twins
    return (
        len(path) == 3
        and path[0] == "modelSettings"
        and bool(path[1])
        and path[2] in item.model_settings_fields
    )


def choose_key_path(
    data: Mapping[str, Any], field_name: SettingsEditField
) -> tuple[str, ...]:
    """Pick the key a save edits when the caller has no resolver path.

    The top-level key when the file sets it, else the first ``env`` twin the file
    sets, else the top-level key (an insert). The preview passes the resolver's path
    instead, which also covers ``modelSettings``.
    """
    item = edit_fields.FIELDS[field_name]
    if item.top_key in data:
        return (item.top_key,)
    env = data.get("env")
    if isinstance(env, dict):
        for twin in item.env_twins:
            if twin in cast("dict[str, Any]", env):
                return ("env", twin)
    return (item.top_key,)


def check_value(
    field_name: SettingsEditField, value: str | int, key_path: Sequence[str]
) -> str | int:
    """Check a save's value and key path, and return the value as the file holds it.

    The value must fit the field (``edit_fields.accepts``), the key path must be one the
    registry allows, and neither may look like a secret, because a ledger row keeps the
    value. A value under ``env`` is written as text.

    Raises:
        Refused: ``bad_value``.
    """
    path = tuple(key_path)
    if not valid_key_path(field_name, path):
        raise Refused("bad_value", {"reason": "key_path"})
    if not edit_fields.accepts(field_name, value, nested=path[0] == "modelSettings"):
        raise Refused("bad_value")
    stored = str(value) if path[0] == "env" else value
    if masking.is_secret_value(stored) or masking.is_secret_name(path[-1]):
        raise Refused("bad_value", {"reason": "secret"})
    return stored


def plan_set(
    raw: bytes | None,
    field_name: SettingsEditField,
    value: str | int,
    key_path: Sequence[str] | None = None,
) -> Plan:
    """Work out the bytes a save of ``value`` would write.

    Pure: nothing is read or written.

    Args:
        raw: The file's bytes, or None when the file is not there.
        field_name: The registry field.
        value: The new value, checked by ``edit_fields.accepts``.
        key_path: The key to edit, from the resolver. None picks one with
            ``choose_key_path``.

    Returns:
        The plan. A value under ``env`` is written as text.

    Raises:
        Refused: ``bad_value``, ``no_change``, ``unparsed``, ``parent_not_object``,
            ``key_present``, ``oracle_failed`` or ``too_large``.
    """
    data: dict[str, Any] = {}
    if raw is not None:
        try:
            _text, data = json_edit.parse_strict(raw)
        except json_edit.Refused as exc:
            raise _from_json(exc) from None
    path = (
        tuple(key_path) if key_path is not None else choose_key_path(data, field_name)
    )
    new_value = check_value(field_name, value, path)
    if raw is None:
        return Plan(_new_file(path, new_value), path, None, new_value, "create")
    try:
        json_edit.value_span(raw, path)
        found = True
    except json_edit.Refused as exc:
        if exc.code != "key_missing":
            raise _from_json(exc) from None
        found = False
    old_value = _value_at(data, path)
    try:
        if found:
            if json_edit.same_value(_node(data, path), new_value):
                raise Refused("no_change")
            new_raw = json_edit.replace_value(raw, path, new_value)
            op: Literal["replace", "insert"] = "replace"
        else:
            new_raw = json_edit.insert_value(raw, path, new_value)
            op = "insert"
    except json_edit.Refused as exc:
        raise _from_json(exc) from None
    if len(new_raw) > MAX_FILE:
        raise Refused("too_large")
    return Plan(new_raw, path, old_value, new_value, op)


def _node(data: Mapping[str, Any], path: Sequence[str]) -> object:
    node: object = data
    for step in path:
        node = cast("dict[str, object]", node)[step]
    return node


def _new_file(path: tuple[str, ...], value: object) -> bytes:
    try:
        return json_edit.new_file(path, value)
    except json_edit.Refused as exc:
        raise _from_json(exc) from None


def _apply_op(
    before: bytes | None, op: str, key_path: tuple[str, ...], value: object
) -> bytes:
    """Apply a row's operation to the bytes before it, as the writer did."""
    try:
        if op == "create" and before is None:
            return json_edit.new_file(key_path, value)
        if before is None:
            raise Refused("cant_rebuild")
        if op == "replace":
            return json_edit.replace_value(before, key_path, value)
        if op == "insert":
            return json_edit.insert_value(before, key_path, value)
    except json_edit.Refused:
        raise Refused("cant_rebuild") from None
    raise Refused("cant_rebuild")


# Canonical body and tokens


def canonical_body(model: BaseModel) -> bytes:
    """Return the request's canonical body (m6-build.md section 2).

    The model dumped with ``model_dump(mode="json")``, without ``seq``, ``version`` and
    ``request_id``, as UTF-8 JSON with sorted keys and no spaces.
    """
    data = model.model_dump(mode="json")
    for name in _CANONICAL_DROP:
        data.pop(name, None)
    text = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return text.encode("utf-8")


def choice_key(model: BaseModel) -> str:
    """Return the sha256 of the canonical body, the preview's ``choice_key``."""
    return _sha(canonical_body(model))


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# Request ids


@dataclass
class _Request:
    body_sha: str
    started: float
    done: threading.Event = field(default_factory=threading.Event)
    finished: float | None = None
    result: object = None
    error: Refused | None = None


class _Requests:
    """The save and undo request ids: one run per id, a repeat gets the first answer."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[str, _Request] = {}

    def _expire(self) -> None:
        now = self._clock()
        stale = [
            rid
            for rid, item in self._items.items()
            if item.finished is not None and now - item.finished > REQUEST_TTL
        ]
        for rid in stale:
            del self._items[rid]
        while len(self._items) > REQUEST_CAP:
            oldest = min(
                (r for r, i in self._items.items() if i.finished is not None),
                key=lambda r: self._items[r].started,
                default=None,
            )
            if oldest is None:
                break
            del self._items[oldest]

    def run(self, request_id: str, body_sha: str, work: Callable[[], T]) -> T:
        """Run ``work`` once for an id. A repeat waits for it and returns its result.

        Raises:
            Refused: ``request_reused`` for the same id with another body, ``lock_busy``
                when the first run doesn't end in time, or the first run's refusal.
        """
        with self._lock:
            self._expire()
            item = self._items.get(request_id)
            owner = item is None
            if item is None:
                item = _Request(body_sha, self._clock())
                self._items[request_id] = item
            elif item.body_sha != body_sha:
                raise Refused("request_reused")
        if not owner:
            if not item.done.wait(timeout=LOCK_WAIT * 2):
                raise Refused("lock_busy")
            if item.error is not None:
                raise item.error
            return cast("T", item.result)
        try:
            result = work()
        except Refused as exc:
            with self._lock:
                self._items.pop(request_id, None)
            item.error = exc
            item.done.set()
            raise
        except BaseException:
            with self._lock:
                self._items.pop(request_id, None)
            item.error = Refused("write_failed")
            item.done.set()
            raise
        item.result = result
        item.finished = self._clock()
        item.done.set()
        return result


# Results


@dataclass(frozen=True)
class Inspected:
    """A target read once: its resolved path, bytes and identity.

    ``dev`` and ``ino`` are the file's, or its folder's when the file is not there.
    """

    resolved: Resolved
    raw: bytes | None
    sha256: str
    dev: int
    ino: int
    mode: int | None
    read_at: str
    missing_dir: bool


@dataclass(frozen=True)
class SaveResult:
    """What a good save returns. ``row`` is the ledger row as written."""

    row_id: str
    saved_at: str
    recheck_after_ms: int
    row: dict[str, Any]


@dataclass(frozen=True)
class UndoResult:
    """What a good undo or restore returns."""

    row_id: str
    row: dict[str, Any]
    removed_file: bool
    removed_dir: bool


@dataclass(frozen=True)
class RowStatus:
    """Whether a ledger row can be undone, worked out from hashes at read time.

    ``undo_state`` is a ``models.UndoState``. ``reason`` is the old app's word when the
    state is ``not_undoable`` (``undo_row``, ``restore_row``, ``not_newest``,
    ``backup_pruned`` or ``backup_damaged``) or the file can't be read.
    ``undo_anyway`` is True when the file changed since the save but the backup is good.
    """

    undo_state: UndoState
    reason: str | None
    undo_anyway: bool


@dataclass(frozen=True)
class DriftBytes:
    """What Bar Tab wrote (``written``) and what the file holds now (``now``)."""

    written: bytes | None
    now: bytes | None


@dataclass
class _Job:
    new_raw: bytes | None
    kind: RowKind
    key_path: list[str]
    layer: str
    old_value: Any
    new_value: Any
    op: str
    restored_from: str | None = None
    restored_from_backup: str | None = None
    source: str | None = None
    remove_dir: bool = False
    extra: dict[str, Any] = field(default_factory=dict[str, Any])


@dataclass
class _Made:
    backup: str | None = None
    ledger: bool = False
    temp: str | None = None
    folder: str | None = None
    folder_id: tuple[int, int] | None = None


@dataclass(frozen=True)
class _Committed:
    row: dict[str, Any]
    removed_dir: bool


@dataclass
class _StoreDir:
    """An open backup folder for one target."""

    fd: int
    path: str

    def close(self) -> None:
        """Close the folder fd."""
        with contextlib.suppress(OSError):
            os.close(self.fd)


def _thread_timer(delay: float, work: Callable[[], None]) -> None:
    timer = threading.Timer(delay, work)
    timer.daemon = True
    timer.start()


# The writer


class EditStore:
    """The only place that writes the owner's settings files.

    One instance serves the whole server. It holds the per-run token secret, the
    preview cache, the request ids and the per-target locks.
    """

    def __init__(
        self,
        ctx: EditContext,
        *,
        clock: Callable[[], datetime.datetime] | None = None,
        scheduler: Scheduler | None = None,
        secret: bytes | None = None,
    ) -> None:
        """Make a writer.

        Args:
            ctx: The machine's folders.
            clock: Returns the current time, for tests. Defaults to UTC now.
            scheduler: Runs ``work`` after a delay in seconds. Defaults to a daemon
                timer thread. Tests pass a recorder.
            secret: The token secret. Defaults to a fresh random one per run.
        """
        self._ctx = ctx
        self._clock = clock or (lambda: datetime.datetime.now(datetime.UTC))
        self._scheduler: Scheduler = scheduler or _thread_timer
        self._secret = secret or secrets.token_bytes(32)
        self._requests = _Requests(time.monotonic)
        self._previews: collections.OrderedDict[str, FileBytes] = (
            collections.OrderedDict()
        )
        self._previews_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self.seam: Callable[[str], None] | None = None  # for tests

    # Reads

    @property
    def context(self) -> EditContext:
        """The context this writer was made with."""
        return self._ctx

    def _now(self) -> str:
        return self._clock().isoformat()

    def _seam(self, name: str) -> None:
        if self.seam is not None:
            self.seam(name)

    def resolve(self, target: Target) -> Resolved:
        """Resolve a target (see ``resolve_target``)."""
        return resolve_target(self._ctx, target)

    def inspect(self, target: Target) -> Inspected:
        """Resolve a target and read it once. Writes nothing and needs no permit.

        Raises:
            Refused: Any refusal of ``resolve_target``, and ``not_regular``,
                ``hard_link``, ``not_owner``, ``too_large`` or ``changed`` from the
                walk.
        """
        rs = self.resolve(target)
        with _walk(rs) as snap:
            return Inspected(
                rs,
                snap.raw,
                _hash_of(snap.raw),
                snap.dev,
                snap.ino,
                snap.mode,
                self._now(),
                snap.missing_dir,
            )

    def make_version(self, seen: Inspected, body: BaseModel) -> str:
        """Return the token for a preview, and keep the preview's bytes.

        The token binds the file's identity and hash to the body's ``choice_key``. A
        refusal later diffs the kept bytes against the file.
        """
        token = self._sign(
            {
                "v": TOKEN_VERSION,
                "target_id": seen.resolved.target_id,
                "dev": seen.dev,
                "ino": seen.ino,
                "sha256": seen.sha256,
                "body_sha256": choice_key(body),
                "read_at": seen.read_at,
            }
        )
        self._remember(token, FileBytes(seen.raw))
        return token

    def preview_bytes(self, version: str) -> FileBytes | None:
        """Return the bytes a preview saw, or None after a restart or an eviction."""
        with self._previews_lock:
            return self._previews.get(version)

    def _remember(self, token: str, kept: FileBytes) -> None:
        if kept.raw is not None and len(kept.raw) > MAX_FILE:
            return
        with self._previews_lock:
            self._previews[token] = kept
            self._previews.move_to_end(token)
            while len(self._previews) > PREVIEW_CACHE:
                self._previews.popitem(last=False)

    def _sign(self, payload: Mapping[str, Any]) -> str:
        body = _b64(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        tag = hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest()
        return f"{body}.{_b64(tag)}"

    def _open_token(self, token: str) -> dict[str, Any]:
        try:
            body, _, tag = token.partition(".")
            want = hmac.new(self._secret, body.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_unb64(tag), want):
                raise Refused("bad_version")
            payload = json.loads(_unb64(body))
        except Refused:
            raise
        except (ValueError, binascii.Error, UnicodeError):
            raise Refused("bad_version") from None
        if not isinstance(payload, dict):
            raise Refused("bad_version")
        return cast("dict[str, Any]", payload)

    def _check_version(
        self, token: str | None, rs: Resolved, body_sha: str, snap: Snapshot
    ) -> None:
        """Check the token: ``bad_version``, ``preview_mismatch``, then ``changed``."""
        if token is None:
            raise Refused("bad_version")
        payload = self._open_token(token)
        if (
            payload.get("v") != TOKEN_VERSION
            or payload.get("target_id") != rs.target_id
        ):
            raise Refused("bad_version")
        kept = self.preview_bytes(token)
        if payload.get("body_sha256") != body_sha:
            raise Refused("preview_mismatch", preview=kept, current=FileBytes(snap.raw))
        now = (snap.dev, snap.ino, _hash_of(snap.raw))
        if (payload.get("dev"), payload.get("ino"), payload.get("sha256")) != now:
            raise Refused("changed", preview=kept, current=FileBytes(snap.raw))

    # Reading the ledger and the backups

    def _open_store(self, rs: Resolved, *, create: bool) -> _StoreDir | None:
        """Open the target's backup folder. None when absent and ``create`` is False.

        Folders are made 0700 by absolute path, which the write guard allows inside the
        backups root, and opened again with ``O_NOFOLLOW`` by descriptor.
        """
        path = _real(self._ctx.config_dir)
        try:
            fd = os.open(path, _DIR_FLAGS)
        except FileNotFoundError:
            if create:
                raise Refused("folder_not_found") from None
            return None
        except OSError as exc:
            raise Refused("write_failed", {"stage": "config"}) from exc
        for name in (STORE_DIR, BACKUPS_DIR, rs.target_id):
            try:
                child = self._child_dir(fd, path, name, create=create)
            finally:
                os.close(fd)
            if child is None:
                return None
            fd = child
            path = os.path.join(path, name)
        return _StoreDir(fd, path)

    def _child_dir(
        self, parent: int, parent_path: str, name: str, *, create: bool
    ) -> int | None:
        fd = self._open_subdir(parent, name)
        if fd is None:
            if not create:
                return None
            # Only a folder that is not there is made, because the write guard judges
            # every mkdir by its path and refuses one outside the backups root.
            try:
                os.mkdir(os.path.join(parent_path, name), 0o700)
            except FileExistsError:
                pass
            except OSError as exc:
                raise Refused("write_failed", {"stage": "backup_folder"}) from exc
            fd = self._open_subdir(parent, name)
            if fd is None:
                raise Refused("write_failed", {"stage": "backup_folder"})
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid():
                raise Refused("write_failed", {"stage": "backup_folder_owner"})
            if create and stat.S_IMODE(info.st_mode) & 0o077:
                os.fchmod(fd, 0o700)
        except BaseException:
            os.close(fd)
            raise
        return fd

    @staticmethod
    def _open_subdir(parent: int, name: str) -> int | None:
        try:
            return os.open(name, _SUBDIR_FLAGS, dir_fd=parent)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise Refused("write_failed", {"stage": "backup_folder"}) from exc

    def _read_ledger(self, store: _StoreDir) -> Rows:
        """Return the ledger's rows, [] when absent. Raises ``_LedgerBadError``."""
        try:
            data = _read_file(LEDGER_FILE, store.fd, MAX_LEDGER)
        except FileNotFoundError:
            return []
        except OSError as exc:
            raise _LedgerBadError from exc
        if len(data) > MAX_LEDGER:
            raise _LedgerBadError
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise _LedgerBadError from exc
        if (
            not isinstance(doc, dict)
            or doc.get("version") != 1  # pyright: ignore[reportUnknownMemberType]
            or not isinstance(doc.get("rows"), list)  # pyright: ignore[reportUnknownMemberType]
        ):
            raise _LedgerBadError
        rows = cast("list[Any]", cast("dict[str, Any]", doc)["rows"])
        if not all(isinstance(row, dict) for row in rows):
            raise _LedgerBadError
        return cast("Rows", rows)

    def _write_ledger(self, store: _StoreDir, rows: Rows) -> None:
        """Write ``ledger.json`` by temp file, fsync and rename by descriptor."""
        data = json.dumps({"version": 1, "rows": rows}, indent=1).encode("utf-8")
        temp = f".ledger-{secrets.token_hex(8)}.tmp"
        try:
            _create_in(store.fd, store.path, temp, data)
            os.rename(temp, LEDGER_FILE, src_dir_fd=store.fd, dst_dir_fd=store.fd)
        except OSError:
            _unlink(temp, store.fd)
            raise
        _fullfsync(store.fd)

    def _acquire_flock(self, store: _StoreDir) -> int:
        """Take the store's ``flock``, retrying for ``LOCK_WAIT`` seconds."""
        path = os.path.join(store.path, LOCK_FILE)
        try:
            fd = os.open(
                path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
            )
        except OSError as exc:
            raise Refused("lock_busy", {"stage": "open"}) from exc
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Refused("lock_busy", {"stage": "not_a_file"})
            _same_file(fd, LOCK_FILE, store.fd)
            deadline = time.monotonic() + LOCK_WAIT
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno not in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                        raise Refused("lock_busy", {"stage": "flock"}) from exc
                else:
                    return fd
                if time.monotonic() >= deadline:
                    raise Refused("lock_busy")
                time.sleep(0.02)
        except BaseException:
            os.close(fd)
            raise

    def _target_lock(self, target_id: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(target_id, threading.Lock())

    def read_rows(self, target: Target) -> Rows:
        """Return the visible ledger rows of a target, oldest first. Reads only.

        A ledger that is absent gives []. A damaged one raises ``ledger_damaged``.
        """
        rs = self.resolve(target)
        store = self._open_store(rs, create=False)
        if store is None:
            return []
        try:
            rows = self._read_ledger(store)
        except _LedgerBadError:
            raise Refused("ledger_damaged") from None
        finally:
            store.close()
        return _trim(rows, self._file_hash(rs))

    def _file_hash(self, rs: Resolved) -> str | None:
        try:
            with _walk(rs) as snap:
                return _hash_of(snap.raw)
        except (Refused, OSError):
            return None

    def backup_state(
        self, store: _StoreDir, row: Mapping[str, Any]
    ) -> tuple[str | None, bytes | None]:
        """Check a row's backup. Returns (reason, data).

        ``reason`` is None, ``backup_pruned`` or ``backup_damaged``. A row that had no
        file pairs with an empty marker, and every other row with a real backup whose
        bytes hash to the row's before hash. ``data`` is None for a marker.
        """
        name = row.get("backup")
        marker = _valid_marker(name)
        if (row.get("before_sha256") == ABSENT) != marker:
            return "backup_damaged", None
        if marker:
            try:
                data = _read_file(cast("str", name), store.fd, 1)
            except FileNotFoundError:
                return "backup_pruned", None
            except OSError:
                return "backup_damaged", None
            return ("backup_damaged", None) if data else (None, None)
        if not _valid_backup(name):
            return "backup_pruned", None
        try:
            data = _read_file(cast("str", name), store.fd, MAX_FILE)
        except FileNotFoundError:
            return "backup_pruned", None
        except OSError:
            return "backup_damaged", None
        if _sha(data) != row.get("before_sha256"):
            return "backup_damaged", None
        return None, data

    def row_status(self, target: Target, row: Mapping[str, Any]) -> RowStatus:
        """Work out whether a visible row can be undone. Reads only.

        Raises:
            Refused: Any refusal of ``read_rows``.
        """
        rows = self.read_rows(target)
        rs = self.resolve(target)
        current = self._file_hash(rs)
        kind = row.get("kind")
        if kind == "undo":
            return RowStatus("not_undoable", "undo_row", False)
        if kind == "restore":
            return RowStatus("not_undoable", "restore_row", False)
        if not rows or rows[-1].get("id") != row.get("id"):
            undone = any(
                item.get("kind") == "undo"
                and item.get("restored_from") == row.get("id")
                for item in rows
            )
            return RowStatus(
                "undone" if undone else "not_undoable",
                None if undone else "not_newest",
                False,
            )
        store = self._open_store(rs, create=False)
        if store is None:
            return RowStatus("not_undoable", "backup_pruned", False)
        try:
            reason, _data = self.backup_state(store, row)
        finally:
            store.close()
        if reason is not None:
            return RowStatus("not_undoable", reason, False)
        if current is None:
            return RowStatus("not_undoable", "file_refused", False)
        if current != row.get("after_sha256"):
            return RowStatus("changed_since", "changed_since_save", True)
        if _valid_marker(row.get("backup")):
            return RowStatus("deletes_file", None, False)
        return RowStatus("can_undo", None, False)

    # Writes

    def save(
        self,
        target: Target,
        body: EditSaveRequest,
        *,
        key_path: Sequence[str] | None = None,
    ) -> SaveResult:
        """Save one settings value. The whole call runs in the calling thread.

        Args:
            target: The registry target for the body's project and scope.
            body: The parsed request, with its token and request id.
            key_path: The key to edit, from the resolver. None picks one from the file.

        Returns:
            The row, once the file is written and read back.

        Raises:
            Refused: A code from ``models.EditRefusalCode``. ``raced`` and a failed
                read-back come after the write, with ``row_id`` set.
        """
        return self._requests.run(
            body.request_id,
            choice_key(body),
            functools.partial(self._save, target, body, key_path),
        )

    def _save(
        self, target: Target, body: EditSaveRequest, key_path: Sequence[str] | None
    ) -> SaveResult:
        if target.leftover or body.scope != target.scope:
            raise Refused("not_editable")
        top = (edit_fields.FIELDS[body.field].top_key,)
        check_value(body.field, body.value, key_path if key_path is not None else top)
        rs = self.resolve(target)
        body_sha = choice_key(body)

        def produce(snap: Snapshot, rows: Rows, current: str, store: _StoreDir) -> _Job:
            del rows, current, store
            self._check_version(body.version, rs, body_sha, snap)
            plan = plan_set(snap.raw, body.field, body.value, key_path)
            return _Job(
                plan.new_raw,
                "edit",
                list(plan.key_path),
                target.scope,
                plan.old_value,
                plan.new_value,
                plan.op,
                extra={
                    "project": body.project,
                    "field": body.field,
                    "subject": {"kind": "main", "name": None},
                    "scope": target.scope,
                    "request_id": body.request_id,
                },
            )

        done = self._commit(rs, produce)
        row = done.row
        return SaveResult(
            str(row["id"]), str(row["time"]), int(RECHECK_DELAYS[0] * 1000), row
        )

    def undo(
        self,
        targets: Sequence[Target],
        project: str,
        body: EditUndoRequest,
    ) -> UndoResult:
        """Put a row's backup back as a new row. The whole call runs in this thread.

        The target is rebuilt from ``targets`` (the registry's, for the project the edit
        key belongs to), and never from the row. A file that changed since the save is
        ``changed_since_save`` unless ``body.anyway`` carries the token a refusal like
        that returned. ``anyway`` skips only the check against the saved row's hash.

        Raises:
            Refused: ``unknown_edit``, ``forged_row``, ``not_undoable``,
                ``changed_since_save``, ``backup_damaged``, a token refusal, or any
                refusal of a save.
        """
        confirm = body.model_copy(update={"anyway": True})
        return self._requests.run(
            body.request_id,
            choice_key(body),
            functools.partial(
                self._row_action,
                "undo",
                targets,
                project,
                body.row_id,
                force=body.anyway,
                version=body.version,
                confirm_sha=choice_key(confirm),
                request_id=body.request_id,
            ),
        )

    def restore(
        self,
        targets: Sequence[Target],
        project: str,
        row_id: str,
        *,
        version: str,
        request_id: str,
    ) -> UndoResult:
        """Put back the backup of any visible row as a new row that is never undoable.

        Like "Undo anyway", it skips the saved-row hash check and needs a token from
        ``restore_version``.
        """
        sha = _sha(self._restore_body(project, row_id))
        return self._requests.run(
            request_id,
            sha,
            functools.partial(
                self._row_action,
                "restore",
                targets,
                project,
                row_id,
                force=True,
                version=version,
                confirm_sha=sha,
                request_id=request_id,
            ),
        )

    @staticmethod
    def _restore_body(project: str, row_id: str) -> bytes:
        text = json.dumps(
            {"project": project, "restore": True, "row_id": row_id},
            sort_keys=True,
            separators=(",", ":"),
        )
        return text.encode("utf-8")

    def restore_version(
        self, targets: Sequence[Target], project: str, row_id: str
    ) -> str:
        """Return the token that confirms a restore of one row, bound to the file."""
        _target, rs, _row = self._find_row(targets, project, row_id)
        with _walk(rs) as snap:
            token = self._sign(
                {
                    "v": TOKEN_VERSION,
                    "target_id": rs.target_id,
                    "dev": snap.dev,
                    "ino": snap.ino,
                    "sha256": _hash_of(snap.raw),
                    "body_sha256": _sha(self._restore_body(project, row_id)),
                    "read_at": self._now(),
                }
            )
        return token

    def _find_row(
        self, targets: Sequence[Target], project: str, row_id: str
    ) -> tuple[Target, Resolved, dict[str, Any]]:
        """Find a row in the ledgers of the registry's targets, and check it is ours.

        Raises:
            Refused: ``unknown_edit`` when no ledger has it, ``forged_row`` when two
                have it or its fields don't match the registry target.
        """
        found: list[tuple[Target, Resolved, dict[str, Any]]] = []
        for target in targets:
            try:
                rs = self.resolve(target)
                store = self._open_store(rs, create=False)
            except Refused:
                continue
            if store is None:
                continue
            try:
                rows = self._read_ledger(store)
            except _LedgerBadError:
                continue
            finally:
                store.close()
            found.extend((target, rs, row) for row in rows if row.get("id") == row_id)
        if not found:
            raise Refused("unknown_edit")
        if len(found) > 1:
            raise Refused("forged_row")
        target, rs, row = found[0]
        _check_row(rs, row, project)
        return target, rs, row

    def _row_action(
        self,
        kind: Literal["undo", "restore"],
        targets: Sequence[Target],
        project: str,
        row_id: str,
        *,
        force: bool,
        version: str | None,
        confirm_sha: str,
        request_id: str,
    ) -> UndoResult:
        target, rs, source = self._find_row(targets, project, row_id)
        if target.leftover and kind == "restore":
            raise Refused("not_editable")

        def produce(snap: Snapshot, rows: Rows, current: str, store: _StoreDir) -> _Job:
            row = next((item for item in rows if item.get("id") == row_id), None)
            if row is None:
                raise Refused("unknown_edit")
            if kind == "undo":
                self._undo_rule(rows, row)
            reason, data = self.backup_state(store, row)
            if reason == "backup_pruned":
                raise Refused("not_undoable", {"reason": "backup_pruned"})
            if reason == "backup_damaged":
                raise Refused("backup_damaged")
            if not force and current != row.get("after_sha256"):
                self._changed_since_save(rs, snap, row, data, confirm_sha)
            if force:
                self._check_version(version, rs, confirm_sha, snap)
                if data is not None:
                    try:
                        json_edit.parse_strict(data)
                    except json_edit.Refused:
                        raise Refused("unparsed", {"which": "backup"}) from None
            key_path = _key_path_of(row)
            marker = _valid_marker(row.get("backup"))
            extra = {
                name: row[name]
                for name in ("project", "field", "subject", "scope")
                if name in row
            }
            extra["request_id"] = request_id
            return _Job(
                None if marker else data,
                kind,
                key_path,
                str(row.get("layer") or target.scope),
                _value_in(snap.raw, key_path),
                _value_in(data, key_path),
                str(row.get("op") or "replace"),
                restored_from=str(row.get("id")),
                restored_from_backup=str(row.get("backup")),
                source=str(row.get("backup")),
                remove_dir=marker and bool(row.get("made_dir")),
                extra=extra,
            )

        remove_dir = _valid_marker(source.get("backup")) and bool(
            source.get("made_dir")
        )
        done = self._commit(rs, produce, remove_dir=remove_dir)
        row = done.row
        return UndoResult(
            str(row["id"]),
            row,
            removed_file=row.get("after_sha256") == ABSENT,
            removed_dir=done.removed_dir,
        )

    @staticmethod
    def _undo_rule(rows: Rows, row: Mapping[str, Any]) -> None:
        """Raise ``not_undoable`` unless the row is an edit and its file's newest."""
        if row.get("kind") == "undo":
            raise Refused("not_undoable", {"reason": "undo_row"})
        if row.get("kind") == "restore":
            raise Refused("not_undoable", {"reason": "restore_row"})
        if rows[-1].get("id") != row.get("id"):
            raise Refused("not_undoable", {"reason": "not_newest"})

    def _changed_since_save(
        self,
        rs: Resolved,
        snap: Snapshot,
        row: Mapping[str, Any],
        data: bytes | None,
        confirm_sha: str,
    ) -> NoReturn:
        """Raise ``changed_since_save`` with the undo's bytes and its token."""
        problem = Refused("changed_since_save", {"row_id": str(row.get("id"))})
        problem.current = FileBytes(snap.raw)
        problem.backup = FileBytes(data)
        problem.undo_version = self._sign(
            {
                "v": TOKEN_VERSION,
                "target_id": rs.target_id,
                "dev": snap.dev,
                "ino": snap.ino,
                "sha256": _hash_of(snap.raw),
                "body_sha256": confirm_sha,
                "read_at": self._now(),
            }
        )
        raise problem

    # The commit

    def _commit(
        self,
        rs: Resolved,
        produce: Callable[[Snapshot, Rows, str, _StoreDir], _Job],
        *,
        remove_dir: bool = False,
    ) -> _Committed:
        """The save order, shared by save, undo and restore.

        ``remove_dir`` is True for the undo of a create that made the folder, so the
        permit names that folder as the one it may take away again.
        """
        try:
            # a target the walk refuses makes no backups folder
            with _walk(rs):
                pass
            with self._target_lock(rs.target_id):
                store = self._open_store(rs, create=True)
                if store is None:
                    raise Refused("write_failed", {"stage": "store"})
                try:
                    lock_fd = self._acquire_flock(store)
                    try:
                        return self._commit_locked(
                            rs, produce, store, remove_dir=remove_dir
                        )
                    finally:
                        os.close(lock_fd)
                finally:
                    store.close()
        except PermissionError as exc:
            raise Refused("write_failed", {"stage": "permission"}) from exc
        except OSError as exc:
            raise Refused(
                "write_failed", {"errno": errno.errorcode.get(exc.errno or 0, "?")}
            ) from exc

    def _commit_locked(
        self,
        rs: Resolved,
        produce: Callable[[Snapshot, Rows, str, _StoreDir], _Job],
        store: _StoreDir,
        *,
        remove_dir: bool,
    ) -> _Committed:
        folder = rs.folder_path if rs.may_make_dir or remove_dir else None
        with contextlib.ExitStack() as stack:
            try:
                held = stack.enter_context(
                    write_guard.permit(rs.real_path, make_dir=folder)
                )
            except PermissionError:
                raise Refused("edits_off") from None
            s1 = stack.enter_context(_walk(rs))
            self._bind(held, s1)
            self._seam("after_read")
            raw = s1.raw
            current = _hash_of(raw)
            try:
                all_rows = self._read_ledger(store)
            except _LedgerBadError:
                raise Refused("ledger_damaged") from None
            rows = _trim(all_rows, current)
            job = produce(s1, rows, current, store)
            if job.new_raw == raw:
                raise Refused("no_change")
            if job.new_raw is not None and len(job.new_raw) > MAX_FILE:
                raise Refused("too_large")
            return self._apply(rs, job, s1, store, all_rows, rows, held)

    @staticmethod
    def _bind(held: write_guard.Permit, snap: Snapshot) -> None:
        """Hand the permit the identity of the folders a walk opened."""
        if snap.folder_fd is not None:
            held.bind_folder(snap.folder_fd)
        if snap.parent_fd is not None and held.make_dir is not None:
            held.bind_parent(snap.parent_fd)

    def _next_number(self, store: _StoreDir, rows: Rows) -> int:
        numbers = [_backup_number(row.get("backup")) for row in rows]
        numbers += [_backup_number(name) for name in os.listdir(store.fd)]
        top = max([n for n in numbers if n is not None] or [0])
        if top + 1 > 999999:
            raise Refused("write_failed", {"stage": "backup_numbers"})
        return top + 1

    def _make_row(
        self,
        rs: Resolved,
        job: _Job,
        edit_id: str,
        backup: str,
        before: bytes | None,
        *,
        made_dir: bool,
    ) -> dict[str, Any]:
        name = job.key_path[-1] if job.key_path else None
        row: dict[str, Any] = {
            "id": edit_id,
            "time": self._now(),
            "kind": job.kind,
            "op": job.op,
            "key_path": list(job.key_path),
            "layer": job.layer,
        }
        # a null value is left out, so it never reaches the page
        if job.old_value is not None:
            row["old_value"] = masking.mask_value(job.old_value, name)
        if job.new_value is not None:
            row["new_value"] = masking.mask_value(job.new_value, name)
        row.update(
            {
                "before_sha256": _hash_of(before),
                "after_sha256": _hash_of(job.new_raw),
                "backup": backup,
                "restored_from": job.restored_from,
                "restored_from_backup": job.restored_from_backup,
            }
        )
        if made_dir:
            row["made_dir"] = True
        row.update(job.extra)
        row.update(
            {
                "display_path": rs.target.display_path,
                "real_path": rs.real_path,
                "app": "bartab",
                "recheck": {
                    "state": "checking",
                    "changed_keys": [],
                    "ours_survived": None,
                    "at": None,
                },
            }
        )
        return row

    def _sweep_temps(self, folder_fd: int) -> None:
        """Remove temp files an earlier save left behind, never one still in use.

        Two files in one folder (``settings.json`` and ``settings.local.json``) have
        their own locks, so another save may sit between making its temp file and the
        rename. Its temp file is in ``_LIVE_TEMPS``, and removing it made that rename
        fail with ENOENT. Another process (the old app writes the same names) has no
        entry there, so a file whose mtime is under ``TEMP_SWEEP_AGE_SECONDS`` old stays
        too, and only an older one goes.
        """
        for name in os.listdir(folder_fd):
            if not _TEMP_RE.match(name):
                continue
            try:
                info = os.stat(name, dir_fd=folder_fd, follow_symlinks=False)
            except OSError:
                continue
            if time.time() - info.st_mtime <= TEMP_SWEEP_AGE_SECONDS:
                continue
            with _LIVE_TEMPS_LOCK:
                if name not in _LIVE_TEMPS:
                    _unlink(name, folder_fd)

    def _apply(
        self,
        rs: Resolved,
        job: _Job,
        s1: Snapshot,
        store: _StoreDir,
        all_rows: Rows,
        rows: Rows,
        held: write_guard.Permit,
    ) -> _Committed:
        """Steps 3 to 9 of section 3.6. Cleans up and raises before the rename."""
        raw = s1.raw
        edit_id = secrets.token_hex(8)
        made = _Made()
        creating = raw is None
        deleting = job.new_raw is None
        leaf_fd = s1.folder_fd
        new_fd: int | None = None
        live_temp: str | None = None
        try:
            try:
                self._seam("before_backup")
                number = self._next_number(store, all_rows)
                backup = f"{number:06d}-{edit_id}." + ("absent" if creating else "bak")
                made.backup = backup
                _create_in(store.fd, store.path, backup, b"" if raw is None else raw)
                if _read_file(backup, store.fd, MAX_FILE) != (raw or b""):
                    raise Refused("write_failed", {"stage": "backup_mismatch"})
                self._seam("after_backup")
                row = self._make_row(
                    rs, job, edit_id, backup, raw, made_dir=s1.missing_dir
                )
                made.ledger = True
                self._write_ledger(store, [*rows, row])
                self._seam("after_ledger")
                made_id: tuple[int, int] | None = None
                if s1.missing_dir:
                    if not rs.parts or s1.parent_fd is None:
                        raise Refused("write_failed", {"stage": "folder"})
                    new_fd, made_id = self._make_folder(rs, s1, made, held)
                    leaf_fd = new_fd
                if leaf_fd is None:
                    raise Refused("write_failed", {"stage": "folder"})
                self._sweep_temps(leaf_fd)
                temp = None
                if job.new_raw is not None:
                    temp = f".routing-dashboard-{secrets.token_hex(8)}.tmp"
                    made.temp = temp
                    live_temp = temp
                    with _LIVE_TEMPS_LOCK:
                        _LIVE_TEMPS.add(temp)
                    _create_in(
                        leaf_fd,
                        rs.folder_path,
                        temp,
                        job.new_raw,
                        final_mode=0o600 if s1.mode is None else s1.mode,
                    )
                    self._seam("after_temp")
                self._seam("before_recheck")
                self._second_walk(
                    rs, s1, raw, made_id, held, leaf_fd, temp, deleting=deleting
                )
                made.temp = None
            except (Refused, OSError) as exc:
                left = self._cleanup(s1, store, made, all_rows, leaf_fd)
                if isinstance(exc, Refused):
                    exc.dir_left = left
                    raise
                failed = Refused(
                    "write_failed", {"errno": errno.errorcode.get(exc.errno or 0, "?")}
                )
                failed.dir_left = left
                raise failed from exc
            self._seam("after_unlink" if deleting else "after_rename")
            fsync_fds = [leaf_fd] + (
                [s1.parent_fd] if s1.missing_dir and s1.parent_fd is not None else []
            )
            self._verify(rs, job, fsync_fds, store, row)
            removed_dir = False
            if deleting and job.remove_dir and rs.parts and s1.parent_fd is not None:
                self._seam("before_rmdir")
                removed_dir = _remove_dir(rs.parts[-1], s1.parent_fd, s1.folder_id)
                if removed_dir:
                    with contextlib.suppress(OSError):
                        _fullfsync(s1.parent_fd)
            self._prune(store, [*rows, row])
            self._schedule_rechecks(rs.target, str(row["id"]))
            return _Committed(row, removed_dir)
        finally:
            if live_temp is not None:
                with _LIVE_TEMPS_LOCK:
                    _LIVE_TEMPS.discard(live_temp)
            if new_fd is not None:
                os.close(new_fd)

    def _make_folder(
        self, rs: Resolved, s1: Snapshot, made: _Made, held: write_guard.Permit
    ) -> tuple[int, tuple[int, int]]:
        """Make the missing ``.claude`` folder by descriptor and open it."""
        name = rs.parts[-1]
        try:
            os.mkdir(name, 0o700, dir_fd=cast("int", s1.parent_fd))
        except FileExistsError:
            raise Refused("changed") from None
        made.folder = name
        fd = os.open(name, _SUBDIR_FLAGS, dir_fd=cast("int", s1.parent_fd))
        try:
            info = os.fstat(fd)
            made.folder_id = (info.st_dev, info.st_ino)
            held.bind_folder(fd)
            self._seam("after_mkdir")
        except BaseException:
            # the caller only owns the fd once this returns, so a failure here closes it
            os.close(fd)
            raise
        return fd, made.folder_id

    def _second_walk(
        self,
        rs: Resolved,
        s1: Snapshot,
        raw: bytes | None,
        made_id: tuple[int, int] | None,
        held: write_guard.Permit,
        leaf_fd: int,
        temp: str | None,
        *,
        deleting: bool,
    ) -> None:
        """Step 6 and the rename: walk again, compare, then rename or unlink."""
        with _walk(rs) as s6:
            self._bind(held, s6)
            if s6.missing_dir or s6.folder_fd is None:
                raise Refused("changed")
            if s6.folder_id != (made_id if made_id is not None else s1.folder_id):
                raise Refused("changed")
            if raw is None:
                if s6.raw is not None:
                    raise Refused("changed")
            elif s6.raw != raw or (s6.dev, s6.ino) != (s1.dev, s1.ino):
                raise Refused("changed")
            if deleting:
                self._seam("before_unlink")
                os.unlink(rs.name, dir_fd=s6.folder_fd)
            elif temp is not None:
                self._seam("before_rename")
                os.rename(temp, rs.name, src_dir_fd=leaf_fd, dst_dir_fd=s6.folder_fd)

    def _cleanup(
        self,
        s1: Snapshot,
        store: _StoreDir,
        made: _Made,
        old_rows: Rows,
        leaf_fd: int | None,
    ) -> bool:
        """Best effort after a failure. Returns True when a made folder stays."""
        if made.temp is not None and leaf_fd is not None:
            _unlink(made.temp, leaf_fd)
        left = False
        if made.folder is not None:
            if made.folder_id is not None:
                left = not _remove_dir(made.folder, s1.parent_fd, made.folder_id)
            elif s1.parent_fd is not None:
                try:
                    os.rmdir(made.folder, dir_fd=s1.parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    left = True
        if made.ledger:
            with contextlib.suppress(OSError):
                self._write_ledger(store, old_rows)
        if made.backup is not None:
            _unlink(made.backup, store.fd)
        return left

    def _verify(
        self,
        rs: Resolved,
        job: _Job,
        folder_fds: Sequence[int],
        store: _StoreDir,
        row: dict[str, Any],
    ) -> None:
        """Step 7: fsync the folders, read back and compare. Raises ``raced``."""
        deleting = job.new_raw is None
        fsync_error: OSError | None = None
        try:
            self._seam("dir_fsync")
            for fd in folder_fds:
                _fullfsync(fd)
        except OSError as exc:
            fsync_error = exc
        try:
            self._seam("reread")
            with _walk(rs) as s7:
                got = s7.raw
        except (OSError, Refused):
            raise Refused(
                "write_failed", {"stage": "reread"}, row_id=str(row["id"])
            ) from None
        raced = got is not None if deleting else got != job.new_raw
        if not raced and job.source is not None and not deleting:
            try:
                again = _read_file(job.source, store.fd, MAX_FILE)
            except OSError:
                again = None
            raced = again != got
        if raced:
            self._mark_raced(store, str(row["id"]))
            raise Refused("raced", row_id=str(row["id"]))
        if fsync_error is not None:
            raise Refused("write_failed", {"stage": "fsync"}, row_id=str(row["id"]))

    def _mark_raced(self, store: _StoreDir, row_id: str) -> None:
        """Best effort: write ``raced`` on the row, so Changes can say so."""
        with contextlib.suppress(OSError, _LedgerBadError):
            rows = self._read_ledger(store)
            for item in rows:
                if item.get("id") == row_id:
                    item["raced"] = True
            self._write_ledger(store, rows)

    def _oldest_mtime(self, store: _StoreDir, rows: Rows) -> int | None:
        for row in rows:
            name = row.get("backup")
            if not _valid_backup(name):
                continue
            try:
                return os.stat(
                    cast("str", name), dir_fd=store.fd, follow_symlinks=False
                ).st_mtime_ns
            except OSError:
                continue
        return None

    def _prune(self, store: _StoreDir, rows: Rows) -> None:
        """Keep the newest ``RETENTION`` rows and their backups. Never fails a save."""
        try:
            kept = rows[-RETENTION:]
            if len(kept) < len(rows):
                try:
                    self._write_ledger(store, kept)
                except OSError:
                    kept = rows
            named = {row.get("backup") for row in kept}
            dropped = {row.get("backup") for row in rows[: len(rows) - len(kept)]}
            floor = self._oldest_mtime(store, kept)
            for name in os.listdir(store.fd):
                if not _BACKUP_RE.match(name) or name in named:
                    continue
                if name in dropped or name.endswith(".absent"):
                    _unlink(name, store.fd)
                    continue
                # A backup no row names is a crash orphan only if it is as new as the
                # ledger. An older one predates a ledger that was moved aside: keep it.
                if floor is None:
                    continue
                try:
                    stamp = os.stat(
                        name, dir_fd=store.fd, follow_symlinks=False
                    ).st_mtime_ns
                except OSError:
                    continue
                if stamp >= floor:
                    _unlink(name, store.fd)
        except OSError:
            pass

    # Rechecks and drift

    def _schedule_rechecks(self, target: Target, row_id: str) -> None:
        for delay in RECHECK_DELAYS:
            self._scheduler(
                delay, functools.partial(self._recheck_quietly, target, row_id)
            )

    def _recheck_quietly(self, target: Target, row_id: str) -> None:
        try:
            self.run_recheck(target, row_id)
        except Exception:  # noqa: BLE001 - a timer thread must never raise
            LOG.warning("recheck failed")

    def rebuild_written(self, store: _StoreDir, row: Mapping[str, Any]) -> bytes | None:
        """Rebuild the bytes a row wrote from its backup and check its hash.

        An edit row applies its operation to the backup. An undo or restore row is the
        backup it restored. The answer is None for a delete.

        Raises:
            Refused: ``cant_rebuild`` when the backup is gone, the value was masked,
                or the rebuilt bytes don't hash to ``after_sha256``.
        """
        try:
            written = self._rebuild(store, row)
        except (Refused, OSError, KeyError, TypeError, ValueError):
            raise Refused("cant_rebuild") from None
        if _hash_of(written) != row.get("after_sha256"):
            raise Refused("cant_rebuild")
        return written

    def _rebuild(self, store: _StoreDir, row: Mapping[str, Any]) -> bytes | None:
        if row.get("after_sha256") == ABSENT:
            return None
        if row.get("kind") in ("undo", "restore"):
            return _read_file(str(row["restored_from_backup"]), store.fd, MAX_FILE)
        reason, before = self.backup_state(store, row)
        if reason is not None:
            raise Refused("cant_rebuild")
        key_path = tuple(str(step) for step in row["key_path"])
        return _apply_op(before, str(row["op"]), key_path, row["new_value"])

    def drift(self, targets: Sequence[Target], project: str, row_id: str) -> DriftBytes:
        """Return the bytes a row wrote and the bytes the file holds now. Reads only.

        The caller masks and diffs them. The target is rebuilt from the registry.

        Raises:
            Refused: ``unknown_edit``, ``forged_row``, ``cant_rebuild`` or a walk
                refusal.
        """
        _target, rs, row = self._find_row(targets, project, row_id)
        store = self._open_store(rs, create=False)
        if store is None:
            raise Refused("cant_rebuild")
        try:
            written = self.rebuild_written(store, row)
        finally:
            store.close()
        with _walk(rs) as snap:
            return DriftBytes(written, snap.raw)

    def run_recheck(self, target: Target, row_id: str) -> dict[str, Any] | None:
        """Read a saved file again and store the result on its ledger row.

        The state is ``confirmed`` when the file still hashes to the row's
        ``after_sha256`` and ``overwritten`` when something else changed it, with the
        keys that differ and whether our value survived. Returns the stored recheck, or
        None when the row or the ledger can't be reached.
        """
        with contextlib.suppress(Refused, OSError):
            rs = self.resolve(target)
            store = self._open_store(rs, create=False)
            if store is None:
                return None
            try:
                rows = self._read_ledger(store)
            except _LedgerBadError:
                return None
            finally:
                store.close()
            row = next((item for item in rows if item.get("id") == row_id), None)
            if row is None:
                return None
            recheck = self._judge(rs, row)
            return self._store_recheck(rs, row_id, recheck)
        return None

    def _judge(self, rs: Resolved, row: Mapping[str, Any]) -> dict[str, Any]:
        """Compare the file now with what the row wrote."""
        try:
            with _walk(rs) as snap:
                now = snap.raw
        except (Refused, OSError):
            return self._recheck_result("overwritten", [], False)
        if _hash_of(now) == row.get("after_sha256"):
            return self._recheck_result("confirmed", [], True)
        keys: list[str] = []
        survived = False
        store = self._open_store(rs, create=False)
        if store is not None:
            try:
                written = self.rebuild_written(store, row)
            except Refused:
                written = None
                rebuilt = False
            else:
                rebuilt = True
            finally:
                store.close()
            if rebuilt:
                keys, survived = self._compare(written, now, row)
        return self._recheck_result("overwritten", keys[:MAX_CHANGED_KEYS], survived)

    @staticmethod
    def _compare(
        written: bytes | None, now: bytes | None, row: Mapping[str, Any]
    ) -> tuple[list[str], bool]:
        def parse(raw: bytes | None) -> dict[str, Any]:
            if raw is None:
                return {}
            try:
                return json_edit.parse_strict(raw)[1]
            except json_edit.Refused:
                return {}

        before, after = parse(written), parse(now)
        key_path = _key_path_of(row)
        keys = _changed_keys(before, after)
        survived = bool(key_path) and _value_at(before, key_path) == _value_at(
            after, key_path
        )
        return keys, survived

    def _recheck_result(
        self, state: str, keys: list[str], survived: bool
    ) -> dict[str, Any]:
        return {
            "state": state,
            "changed_keys": keys,
            "ours_survived": survived,
            "at": self._now(),
        }

    def _store_recheck(
        self, rs: Resolved, row_id: str, recheck: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Write the recheck on the row, under the same locks a save takes."""
        lock = self._target_lock(rs.target_id)
        if not lock.acquire(timeout=LOCK_WAIT):
            return None
        try:
            store = self._open_store(rs, create=False)
            if store is None:
                return None
            try:
                lock_fd = self._acquire_flock(store)
                try:
                    rows = self._read_ledger(store)
                    for item in rows:
                        if item.get("id") == row_id:
                            item["recheck"] = recheck
                            self._write_ledger(store, rows)
                            return recheck
                    return None
                finally:
                    os.close(lock_fd)
            finally:
                store.close()
        except (Refused, OSError, _LedgerBadError):
            return None
        finally:
            lock.release()


def _check_row(rs: Resolved, row: Mapping[str, Any], project: str) -> None:
    """Refuse a row that doesn't belong to the registry target it was found for.

    A row's path is never trusted. The folder it sits in was derived from the registry
    target, so its id matches by construction. The row's own fields must agree, and its
    shape must be one the writer makes. Anything else is ``forged_row``.
    """
    try:
        if not isinstance(row.get("id"), str) or not _ID_RE.match(row["id"]):
            raise Refused("forged_row")
        if (
            row.get("kind") not in _ROW_KINDS
            or row.get("op", "replace") not in _ROW_OPS
        ):
            raise Refused("forged_row")
        key_path: object = row.get("key_path") or []
        if not isinstance(key_path, list) or not all(
            isinstance(s, str) for s in cast("list[object]", key_path)
        ):
            raise Refused("forged_row")
        for name in ("before_sha256", "after_sha256"):
            value = row.get(name)
            if value != ABSENT and not (
                isinstance(value, str) and _SHA_RE.match(value)
            ):
                raise Refused("forged_row")
        backup = row.get("backup")
        if not (_valid_backup(backup) or _valid_marker(backup)):
            raise Refused("forged_row")
        source = row.get("restored_from_backup")
        if source is not None and not (_valid_backup(source) or _valid_marker(source)):
            raise Refused("forged_row")
        if "project" in row and row["project"] != project:
            raise Refused("forged_row")
        for name, want in (
            ("layer", rs.target.scope),
            ("scope", rs.target.scope),
            ("real_path", rs.real_path),
        ):
            if name in row and row[name] != want:
                raise Refused("forged_row")
    except (KeyError, TypeError):
        raise Refused("forged_row") from None
    if target_id_of(_real(rs.target.display_path)) != rs.target_id:
        raise Refused("forged_row")
