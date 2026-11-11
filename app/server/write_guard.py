"""Runtime write guard for real-data mode and for any server that can edit.

``install(store_root)`` adds a ``sys.addaudithook`` that raises ``PermissionError``
for any file system write outside the store root and the extra roots. Reads are
allowed everywhere. Audit hooks can't be removed once set, so the server installs
this once, early, in real mode and in any mode started with ``--allow-edits``, and
tests run it in subprocesses.

With ``edits=True`` (m6-build.md section 3.5) the hook is stricter and ``permit``
works. A bare name under a ``dir_fd`` is allowed only when ``fstat(dir_fd)`` names a
folder the current thread's permit holds (by device and inode) or a folder inside a
root. A write ``open`` with a relative path is refused, because ``os.open(name,
dir_fd=)`` raises its audit event with no ``dir_fd`` and so can't be judged. The
writer opens every file it writes by absolute path. ``permit(target)`` names the
exact files the current thread may write outside the roots: the real target, temp
files ``.routing-dashboard-<16 hex>.tmp`` in its folder, and for a create the one
folder it may make. ``os.fstat`` raises no audit event, so the hook doesn't re-enter
itself.

The hook does string and path checks only. ``os.path.realpath`` and
``os.path.abspath`` use ``os.lstat``, ``os.readlink`` and ``os.getcwd``, none of
which raises an audit event, so the hook never re-enters itself through them. A
symlink inside a root that points outside is refused, because the path resolves
first. A refusal is logged by a short code through ``logging`` and never names the
path.

Audit events covered, with the arguments the Python 3.13 table lists (section
"Audit events table" of
https://docs.python.org/3.13/library/audit_events.html):

- ``open`` (path, mode, flags). Raised by ``open``, ``io.open`` and ``os.open``, so
  also by ``pathlib`` and ``tempfile``. A write, append, create or truncate mode or
  flag is checked. ``os.open`` passes ``mode=None``, so the flags decide.
- ``os.rename`` (src, dst, src_dir_fd, dst_dir_fd). Also raised by ``os.replace``
  and ``os.renames``. Both paths are checked.
- ``os.remove`` (path, dir_fd). Also raised by ``os.unlink`` and ``os.removedirs``.
- ``os.mkdir`` (path, mode, dir_fd). Also raised by ``os.makedirs``.
- ``os.rmdir`` (path, dir_fd).
- ``os.chmod`` (path, mode, dir_fd). Also raised by ``os.lchmod``.
- ``os.truncate`` (fd, length). Also raised by ``os.ftruncate``. A path is checked.
- ``shutil.copyfile`` (src, dst), ``shutil.copymode`` (src, dst),
  ``shutil.copystat`` (src, dst), ``shutil.copytree`` (src, dst) and
  ``shutil.move`` (src, dst). The destination is checked, and a move checks both.
  ``shutil.copy`` and ``shutil.copy2`` raise the first three.
- ``shutil.rmtree`` (path, dir_fd), ``shutil.make_archive`` (base_name, format,
  root_dir, base_dir), ``shutil.unpack_archive`` (filename, extract_dir, format)
  and ``shutil.chown`` (path, user, group).
- ``os.symlink`` (src, dst, dir_fd), ``os.link`` (src, dst, src_dir_fd,
  dst_dir_fd), ``os.utime`` (path, times, ns, dir_fd), ``os.chown`` (path, uid, gid,
  dir_fd), ``os.chflags`` (path, flags), ``os.setxattr`` (path, attribute, value,
  flags) and ``os.removexattr`` (path, attribute).
- ``sqlite3.connect`` (database). ``:memory:`` is allowed. A ``file:`` URI is read
  as a URI, and any other text as a path.
- ``socket.bind`` (self, address). A Unix socket path is a file, so it is checked.

What the events can't cover, and so what this guard can't stop:

- Anything that takes a file descriptor in place of a path: ``os.truncate`` (and
  ``os.ftruncate``), ``os.fchmod``, ``os.fchown``, ``os.utime`` with an fd, ``mmap``
  (``mmap.__new__`` carries only ``fileno``) and ``os.write``, which has no event.
  The ``open`` that made the fd was checked, so an fd opened for write outside a
  root can't exist, but an fd inherited from before ``install`` is unchecked.
- A name relative to a directory fd (``dir_fd``), with edits off. The fd's
  directory can't be resolved without a file system call, so only a bare name (no
  separator, not ``.`` or ``..``) is allowed, which is what ``shutil.rmtree`` uses
  inside the tree its own event already checked. ``os.open`` raises ``open`` with no
  ``dir_fd``, so a relative write through it is judged against the working folder.
  With edits on, the fd's folder is identified by ``fstat`` and by its path from the
  system, and a relative write ``open`` is refused.
- ``os.mkfifo`` and ``os.mknod``, which have no audit event.
- Child processes (``subprocess.Popen``, ``os.exec``, ``os.system``,
  ``os.posix_spawn``, ``os.spawn``, ``os.fork`` and ``pty.spawn`` raise events, but
  a hook can't follow what the child does).
- SQLite's own ``-wal``, ``-shm`` and ``-journal`` files, which C code writes beside
  the database, so the database path is checked at ``sqlite3.connect`` instead. A
  ``sqlite3.connect`` call doesn't say whether ``uri=True`` was set, so a ``file:``
  string is always read as a URI.
- ``ctypes`` and any other native code.

Two paths are allowed on purpose. ``/dev/null`` is always writable, because
``subprocess.DEVNULL`` and daemonising code open it. Python writing ``.pyc`` files
is refused like any other write, and importlib ignores that, so the server also
sets ``sys.dont_write_bytecode``.
"""

from __future__ import annotations

import contextlib
import errno
import fcntl
import logging
import os
import re
import stat
import sys
import threading
from collections.abc import Callable, Generator, Sequence
from pathlib import Path
from typing import cast
from urllib.parse import unquote

# ruff: noqa: PTH115, PTH117, PTH119, PTH120 - the hook does string work on paths and
# makes no file system call of its own, so it keeps to os.path.

__all__ = ["Permit", "install", "permit"]

LOG = logging.getLogger(__name__)

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_WRITE_MODE_CHARS = frozenset("wax+")
_ALWAYS_WRITABLE = frozenset({os.devnull})
_MEMORY_DATABASES = (":memory:", "file::memory:")
_URI_PREFIX = "file:"
_URI_AUTHORITY = "//"
_TEMP_NAME = re.compile(r"^\.routing-dashboard-[0-9a-f]{16}\.tmp$")
_PATH_BUFFER = 1024

_Check = Callable[[tuple[object, ...]], str | None]


class _State:
    """The roots the hook allows and whether the hook is already installed."""

    def __init__(self) -> None:
        self.roots: tuple[str, ...] = ()
        self.installed = False
        self.edits = False


STATE = _State()
BUSY = threading.local()
PERMITS = threading.local()


def _text(path: object) -> str:
    """Return a path argument as text. Raises TypeError for anything else."""
    if isinstance(path, str):
        return path
    if isinstance(path, bytes):
        return os.fsdecode(path)
    if isinstance(path, os.PathLike):
        return os.fsdecode(os.fspath(cast("os.PathLike[str]", path)))
    msg = "not a path"
    raise TypeError(msg)


def _inside(resolved: str) -> bool:
    """True when an absolute, resolved path is a root or sits below one."""
    return any(
        resolved == root or resolved.startswith(root + os.sep) for root in STATE.roots
    )


class Permit:
    """The exact files one thread may write outside the roots (see ``permit``).

    Folders are bound by ``(st_dev, st_ino)`` taken from the folder fd the writer
    opened, never by name, so a folder swapped for a link after the check is not the
    folder the permit holds.
    """

    def __init__(self, target: str, make_dir: str | None) -> None:
        """Hold the real target and, for a create, the one folder it may make."""
        self.target = target
        self.folder = os.path.dirname(target)
        self.make_dir = make_dir
        self._folders: set[tuple[int, int]] = set()
        self._parents: set[tuple[int, int]] = set()

    def bind_folder(self, fd: int) -> None:
        """Hold the folder an fd names as the one that contains the target.

        Raises:
            NotADirectoryError: When the fd is not a folder.
        """
        self._folders.add(self._folder_identity(fd))

    def bind_parent(self, fd: int) -> None:
        """Hold the folder an fd names as the one the made folder is created in.

        Raises:
            NotADirectoryError: When the fd is not a folder, or the permit makes none.
        """
        if self.make_dir is None:
            raise NotADirectoryError(errno.ENOTDIR, "this permit makes no folder")
        self._parents.add(self._folder_identity(fd))

    @staticmethod
    def _folder_identity(fd: int) -> tuple[int, int]:
        info = os.fstat(fd)
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(errno.ENOTDIR, "not a folder")
        return (info.st_dev, info.st_ino)

    def allows_name(self, identity: tuple[int, int], name: str) -> bool:
        """True when a bare name under a bound folder is one this permit names."""
        if identity in self._folders:
            return name == os.path.basename(self.target) or bool(_TEMP_NAME.match(name))
        if identity in self._parents and self.make_dir is not None:
            return name == os.path.basename(self.make_dir)
        return False

    def allows_path(self, resolved: str) -> bool:
        """True when a resolved absolute path is a file or folder this permit names."""
        if resolved in (self.target, self.make_dir):
            return True
        return os.path.dirname(resolved) == self.folder and bool(
            _TEMP_NAME.match(os.path.basename(resolved))
        )


def _identity(fd: int) -> tuple[int, int] | None:
    """Return ``(st_dev, st_ino)`` of an open fd, or None when it can't be read."""
    try:
        info = os.fstat(fd)
    except OSError:
        return None
    return (info.st_dev, info.st_ino)


def _fd_folder(fd: int) -> str | None:
    """Return the real path of the folder an fd holds, or None when unknown.

    Linux reads ``/proc/self/fd/<fd>``. macOS asks ``fcntl`` for ``F_GETPATH``. Both
    raise no event this hook judges. Anything else gives None, which the caller
    treats as "not inside a root".
    """
    try:
        if sys.platform == "darwin":
            get_path = getattr(fcntl, "F_GETPATH", None)
            if get_path is None:
                return None
            raw = fcntl.fcntl(fd, get_path, b"\0" * _PATH_BUFFER)
            return os.path.realpath(os.fsdecode(raw.split(b"\0", 1)[0]))
        return os.path.realpath(os.readlink(f"/proc/self/fd/{fd}"))
    except (OSError, ValueError):
        return None


def _bare(name: str) -> bool:
    return name not in ("", ".", "..") and os.sep not in name


def _current() -> Permit | None:
    return cast("Permit | None", getattr(PERMITS, "active", None))


def _name_under_fd(name: str, dir_fd: int) -> bool:
    """Judge a bare name under a directory fd with edits on."""
    if not _bare(name):
        return False
    identity = _identity(dir_fd)
    if identity is None:
        return False
    held = _current()
    if held is not None and held.allows_name(identity, name):
        return True
    folder = _fd_folder(dir_fd)
    return folder is not None and _inside(folder)


def _allowed(path: object, dir_fd: object = None) -> bool:
    """True when a write to ``path`` is allowed.

    An int is a file descriptor, which an earlier ``open`` already checked. With edits
    off, a bare name below an open directory fd is allowed (see the module
    docstring). With edits on, that name is judged by the fd's folder identity.
    """
    if isinstance(path, int):
        return True
    text = _text(path)
    if isinstance(dir_fd, int) and dir_fd >= 0 and not text.startswith(os.sep):
        if STATE.edits:
            return _name_under_fd(text, dir_fd)
        return _bare(text)
    if text in _ALWAYS_WRITABLE:
        return True
    resolved = os.path.realpath(text)
    if _inside(resolved):
        return True
    held = _current()
    return held is not None and held.allows_path(resolved)


def writes(mode: object, flags: object) -> bool:
    """True when an ``open`` event's mode or flags write, append, create or truncate."""
    if not isinstance(flags, int):
        return True
    if flags & _WRITE_FLAGS:
        return True
    return isinstance(mode, str) and any(c in _WRITE_MODE_CHARS for c in mode)


def _check_open(args: tuple[object, ...]) -> str | None:
    path, mode, flags = args[0], args[1], args[2]
    if not writes(mode, flags):
        return None
    # os.open(name, dir_fd=) raises this event with no dir_fd, so a relative name can't
    # be judged by its folder. With edits on the writer opens by absolute path.
    if STATE.edits and not isinstance(path, int) and not _text(path).startswith(os.sep):
        return "open"
    return None if _allowed(path) else "open"


def _check_rename(args: tuple[object, ...]) -> str | None:
    src, dst, src_fd, dst_fd = args[0], args[1], args[2], args[3]
    if _allowed(src, src_fd) and _allowed(dst, dst_fd):
        return None
    return "rename"


def _check_remove(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[1]) else "remove"


def _check_mkdir(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[2]) else "mkdir"


def _check_rmdir(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[1]) else "rmdir"


def _check_chmod(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[2]) else "chmod"


def _check_truncate(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0]) else "truncate"


def _check_copy(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[1]) else "copy"


def _check_move(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0]) and _allowed(args[1]) else "move"


def _check_rmtree(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[1]) else "rmtree"


def _check_archive(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0]) else "archive"


def _check_unpack(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[1]) else "archive"


def _check_link_dst(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[1], args[2]) else "link"


def _check_link_both(args: tuple[object, ...]) -> str | None:
    src, dst = args[0], args[1]
    if _allowed(src, args[2]) and _allowed(dst, args[3]):
        return None
    return "link"


def _check_path_only(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0]) else "metadata"


def _check_metadata(args: tuple[object, ...]) -> str | None:
    return None if _allowed(args[0], args[3]) else "metadata"


def _check_sqlite(args: tuple[object, ...]) -> str | None:
    text = _text(args[0])
    if text in _MEMORY_DATABASES:
        return None
    if text.startswith(_URI_PREFIX):
        text = uri_path(text)
    if text and _inside(os.path.realpath(text)):
        return None
    return "sqlite"


def uri_path(uri: str) -> str:
    """The file path of a SQLite ``file:`` URI, with any query dropped."""
    rest = uri[len(_URI_PREFIX) :].split("?", 1)[0]
    if rest.startswith(_URI_AUTHORITY):
        rest = "/" + rest[len(_URI_AUTHORITY) :].partition("/")[2]
    return unquote(rest)


def _check_bind(args: tuple[object, ...]) -> str | None:
    address = args[1]
    if isinstance(address, tuple):
        return None
    if isinstance(address, bytes) and address.startswith(b"\0"):
        return None
    return None if _allowed(address) else "socket"


_CHECKS: dict[str, _Check] = {
    "open": _check_open,
    "os.rename": _check_rename,
    "os.remove": _check_remove,
    "os.mkdir": _check_mkdir,
    "os.rmdir": _check_rmdir,
    "os.chmod": _check_chmod,
    "os.truncate": _check_truncate,
    "shutil.copyfile": _check_copy,
    "shutil.copymode": _check_copy,
    "shutil.copystat": _check_copy,
    "shutil.copytree": _check_copy,
    "shutil.move": _check_move,
    "shutil.rmtree": _check_rmtree,
    "shutil.make_archive": _check_archive,
    "shutil.unpack_archive": _check_unpack,
    "shutil.chown": _check_path_only,
    "os.symlink": _check_link_dst,
    "os.link": _check_link_both,
    "os.utime": _check_metadata,
    "os.chown": _check_metadata,
    "os.chflags": _check_path_only,
    "os.setxattr": _check_path_only,
    "os.removexattr": _check_path_only,
    "sqlite3.connect": _check_sqlite,
    "socket.bind": _check_bind,
}


def _refuse(code: str) -> None:
    """Log the refusal by its code and raise. The message never holds a path."""
    LOG.warning("write guard refused: %s", code)
    raise PermissionError(errno.EPERM, f"write refused ({code})")


def audit(event: str, args: tuple[object, ...]) -> None:
    """The audit hook. Raises PermissionError for a write outside the roots."""
    check = _CHECKS.get(event)
    if check is None or getattr(BUSY, "on", False):
        return
    BUSY.on = True
    try:
        try:
            code = check(args)
        except Exception:  # noqa: BLE001 - an event this can't read fails closed
            code = "unchecked"
        if code is not None:
            _refuse(code)
    finally:
        BUSY.on = False


def _resolve_root(root: Path) -> str:
    return os.path.realpath(os.fspath(root)).rstrip(os.sep) or os.sep


def install(
    store_root: Path, extra_roots: Sequence[Path] = (), *, edits: bool = False
) -> None:
    """Refuse every write outside ``store_root`` and ``extra_roots`` from now on.

    Roots are made absolute and resolved here, so a root that is a symlink or a
    relative path is judged by where it really points. The hook can't be removed.
    A second call with the same roots and mode does nothing, and one with other roots
    or another mode raises ``RuntimeError``, because a hook that stays can't be
    narrowed or widened.

    Args:
        store_root: The Bar Tab store root.
        extra_roots: More folders that stay writable. With edits on, the caller adds
            the backups folder here.
        edits: True for a server that can edit. The hook then judges names under a
            ``dir_fd`` by folder identity, refuses a relative write ``open``, and
            ``permit`` works.
    """
    roots = tuple(dict.fromkeys(_resolve_root(r) for r in (store_root, *extra_roots)))
    if STATE.installed:
        if roots != STATE.roots or edits != STATE.edits:
            msg = "the write guard is already installed with other roots"
            raise RuntimeError(msg)
        return
    STATE.roots = roots
    STATE.edits = edits
    STATE.installed = True
    sys.addaudithook(audit)


@contextlib.contextmanager
def permit(
    target: str | os.PathLike[str], *, make_dir: str | os.PathLike[str] | None = None
) -> Generator[Permit]:
    """Let the current thread write one real file, and nothing else, outside the roots.

    The permit names exact files. They are the real target, temp files matching
    ``.routing-dashboard-<16 hex>.tmp`` in the target's folder, and for a create the
    one folder ``make_dir`` that may be made. It binds folders by identity, so the
    writer calls ``bind_folder`` with the folder fd it opened and ``bind_parent`` with
    the fd of the folder ``make_dir`` is made in. Only ``edit_store.py`` calls this,
    for a target its registry built. The permit is thread-local. A coroutine that
    awaits inside it could resume on another thread, so the writer runs it whole in
    one worker thread. Permits don't nest.

    Args:
        target: The absolute path of the real file to write. A link at the leaf is
            resolved here.
        make_dir: The absolute path of the one folder a create may make, or None.

    Yields:
        The permit, to bind the folder fds to.

    Raises:
        PermissionError: When edits are off, or the guard was not installed with them.
        ValueError: When a path is not absolute.
        RuntimeError: When this thread already holds a permit.
    """
    if not STATE.edits:
        raise PermissionError(errno.EPERM, "edits are off")
    if _current() is not None:
        msg = "a write permit is already held by this thread"
        raise RuntimeError(msg)
    paths = [os.fspath(target)]
    if make_dir is not None:
        paths.append(os.fspath(make_dir))
    if not all(os.path.isabs(p) for p in paths):
        msg = "a permit names absolute paths"
        raise ValueError(msg)
    held = Permit(
        os.path.realpath(paths[0]),
        os.path.realpath(paths[1]) if make_dir is not None else None,
    )
    PERMITS.active = held
    try:
        yield held
    finally:
        PERMITS.active = None
