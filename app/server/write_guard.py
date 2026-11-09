"""Runtime write guard for real-data mode.

``install(store_root)`` adds a ``sys.addaudithook`` that raises ``PermissionError``
for any file system write outside the store root and the extra roots. Reads are
allowed everywhere. Audit hooks can't be removed once set, so the server installs
this once, early, in real mode only, and tests run it in subprocesses.

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
- A name relative to a directory fd (``dir_fd``). The fd's directory can't be
  resolved without a file system call, so only a bare name (no separator, not
  ``.`` or ``..``) is allowed, which is what ``shutil.rmtree`` uses inside the tree
  its own event already checked. ``os.open`` raises ``open`` with no ``dir_fd``, so a
  relative write through it is judged against the working folder.
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

import errno
import logging
import os
import sys
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import cast
from urllib.parse import unquote

__all__ = ["install"]

LOG = logging.getLogger(__name__)

_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_WRITE_MODE_CHARS = frozenset("wax+")
_ALWAYS_WRITABLE = frozenset({os.devnull})
_MEMORY_DATABASES = (":memory:", "file::memory:")
_URI_PREFIX = "file:"
_URI_AUTHORITY = "//"

_Check = Callable[[tuple[object, ...]], str | None]


class _State:
    """The roots the hook allows and whether the hook is already installed."""

    def __init__(self) -> None:
        self.roots: tuple[str, ...] = ()
        self.installed = False


STATE = _State()
BUSY = threading.local()


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


def _allowed(path: object, dir_fd: object = None) -> bool:
    """True when a write to ``path`` is allowed.

    An int is a file descriptor, which an earlier ``open`` already checked. A bare
    name below an open directory fd is allowed (see the module docstring).
    """
    if isinstance(path, int):
        return True
    text = _text(path)
    if isinstance(dir_fd, int) and dir_fd >= 0 and not text.startswith(os.sep):
        return text not in ("", ".", "..") and os.sep not in text
    if text in _ALWAYS_WRITABLE:
        return True
    return _inside(os.path.realpath(text))


def writes(mode: object, flags: object) -> bool:
    """True when an ``open`` event's mode or flags write, append, create or truncate."""
    if not isinstance(flags, int):
        return True
    if flags & _WRITE_FLAGS:
        return True
    return isinstance(mode, str) and any(c in _WRITE_MODE_CHARS for c in mode)


def _check_open(args: tuple[object, ...]) -> str | None:
    path, mode, flags = args[0], args[1], args[2]
    if writes(mode, flags) and not _allowed(path):
        return "open"
    return None


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


def install(store_root: Path, extra_roots: Sequence[Path] = ()) -> None:
    """Refuse every write outside ``store_root`` and ``extra_roots`` from now on.

    Roots are made absolute and resolved here, so a root that is a symlink or a
    relative path is judged by where it really points. The hook can't be removed.
    A second call with the same roots does nothing, and one with other roots raises
    ``RuntimeError``, because a hook that stays can't be narrowed or widened.
    """
    roots = tuple(dict.fromkeys(_resolve_root(r) for r in (store_root, *extra_roots)))
    if STATE.installed:
        if roots != STATE.roots:
            msg = "the write guard is already installed with other roots"
            raise RuntimeError(msg)
        return
    STATE.roots = roots
    STATE.installed = True
    sys.addaudithook(audit)
