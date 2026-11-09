"""The one place for OS calls the store needs.

File locks, fsync, file identity, private folders and atomic writes live here, so a
port to another platform changes this file only. Callers pass paths that
``store_paths.writable`` has already approved.
"""

import fcntl
import os
import tempfile
from pathlib import Path
from typing import NamedTuple

DIR_MODE = 0o700
FILE_MODE = 0o600


class FileIdentity(NamedTuple):
    """What ``os.stat`` says identifies a file between passes."""

    dev: int
    inode: int
    size: int
    mtime_ns: int


class LockHandle:
    """A held exclusive lock. Release it, or let the process end."""

    def __init__(self, fd: int) -> None:
        """Wrap an open file descriptor that holds the flock."""
        self._fd: int | None = fd

    @property
    def held(self) -> bool:
        """Return True until ``release`` runs."""
        return self._fd is not None

    def release(self) -> None:
        """Drop the lock and close the file. Safe to call twice."""
        fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)

    def __enter__(self) -> "LockHandle":
        """Return the handle itself."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Release the lock."""
        self.release()


def try_lock_exclusive(path: Path) -> LockHandle | None:
    """Take a non-blocking exclusive flock on ``path``, creating it at 0600.

    Returns the held handle, or None when another open file description holds it.
    """
    fd = os.open(path, os.O_RDWR | os.O_CREAT, FILE_MODE)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except OSError:
        os.close(fd)
        raise
    return LockHandle(fd)


def fsync_file(path: Path) -> None:
    """Flush one file's data to disk."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    """Flush a folder's entries to disk, so a rename or new file survives a crash."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def file_identity(path: Path) -> FileIdentity:
    """Return (dev, inode, size, mtime_ns) from ``os.stat``."""
    st = path.stat()
    return FileIdentity(st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns)


def mkdir_private(path: Path, *, parents: bool = False) -> None:
    """Create a folder at mode 0700. An existing folder keeps its mode."""
    if path.is_dir():
        return
    if parents and not path.parent.is_dir():
        mkdir_private(path.parent, parents=True)
    try:
        path.mkdir(mode=DIR_MODE)
    except FileExistsError:
        if not path.is_dir():
            raise
        return
    path.chmod(DIR_MODE)


def create_private_file(path: Path) -> None:
    """Create an empty file at mode 0600 if it does not exist."""
    os.close(os.open(path, os.O_RDWR | os.O_CREAT, FILE_MODE))


def atomic_write(path: Path, data: bytes, *, tmp_prefix: str = ".incoming-") -> None:
    """Write ``data`` to ``path`` through a temp file in the same folder.

    The temp file is fsynced, renamed over the target with ``os.replace`` and the
    folder is fsynced. The result is mode 0600.
    """
    fd, tmp_name = tempfile.mkstemp(prefix=tmp_prefix, suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.chmod(FILE_MODE)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    fsync_dir(path.parent)
