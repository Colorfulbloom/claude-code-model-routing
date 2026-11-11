"""Ask git whether one file is tracked, with no program of the repo able to run.

The Shared project line of the edit rail shows only when
``git ls-files --error-unmatch`` lists the file (m6-build.md section 2, "Shared project
line"). The call follows the old app's hardening (``dashboard/git_check.py``,
``ignore_state``), because a project's own ``.git/config`` is not trusted.

- ``-c core.fsmonitor=false`` stops git running a program named in the repo's config,
  one that arrives through ``include.path`` too.
- ``-c core.hooksPath=/dev/null`` leaves no hook to run. ``ls-files`` runs none, so this
  only keeps that true if git ever changes.
- ``--no-lazy-fetch`` and ``GIT_NO_LAZY_FETCH=1`` stop a partial clone fetching a
  missing blob, which runs ``core.sshCommand``. Both are set, so one still holds if the
  other is dropped.
- The argument list is fixed and ends in ``--``, so a file name can't be read as an
  option. The environment holds only ``PATH``, ``HOME`` and ``GIT_NO_LAZY_FETCH``. Git
  runs in the file's own folder with no stdin, no output kept, and a 2 s timeout.

A file that is not there is not tracked and starts no process. The answer is cached on
the file's stat signature and the repo's index signature, so ``git add`` shows up and a
page that polls does not start a process each time.
"""

import collections
import logging
import os
import shutil
import stat
import subprocess
import threading
from pathlib import Path

import git_root

logger = logging.getLogger("bartab.edit")

TIMEOUT_SECONDS = 2.0
CACHE_MAX = 256
DEFAULT_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"

# ruff: noqa: PTH118 - the paths here are strings, as ``git_root`` handles them.

Signature = tuple[int, int, int, int] | None
_CACHE: collections.OrderedDict[tuple[str, Signature, Signature], bool] = (
    collections.OrderedDict()
)
_LOCK = threading.Lock()


def _signature(path: str) -> Signature:
    """Return (device, inode, size, mtime) of a path without following a link."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def _index_signature(folder: str) -> Signature:
    """Return the signature of the repo's index, or None when it isn't a plain repo."""
    root = git_root.find_root(folder)
    if root is None:
        return None
    return _signature(os.path.join(root, ".git", "index"))


def _command(git: str, folder: str, name: str) -> list[str]:
    return [
        git,
        "--no-lazy-fetch",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=/dev/null",
        "-C",
        folder,
        "ls-files",
        "--error-unmatch",
        "--",
        name,
    ]


def is_tracked(
    path: str | os.PathLike[str],
    *,
    path_env: str | None = None,
    home: str | None = None,
) -> bool:
    """Return True when git lists the file. Never raises.

    Args:
        path: The file. Links resolve first, so a link into a dotfiles repo asks that
            repo.
        path_env: The ``PATH`` that finds git and goes to the child. Defaults to the
            server's own.
        home: The ``HOME`` the child gets. Defaults to the server's own.

    Returns:
        False for a file that is not there, a folder that is not in a repo, no git
        and any failure.
    """
    try:
        real = os.path.realpath(path)
        info = os.lstat(real)
        if not stat.S_ISREG(info.st_mode):
            return False
        search = path_env or os.environ.get("PATH") or DEFAULT_PATH
        git = shutil.which("git", path=search)
        if not git or not Path(git).is_absolute():
            return False
        folder, name = os.path.split(real)
        key = (real, _signature(real), _index_signature(folder))
        with _LOCK:
            if key in _CACHE:
                _CACHE.move_to_end(key)
                return _CACHE[key]
        env = {"PATH": search, "GIT_NO_LAZY_FETCH": "1"}
        found_home = home if home is not None else os.environ.get("HOME")
        if found_home:
            env["HOME"] = found_home
        done = subprocess.run(  # noqa: S603 - a fixed argument list, no shell
            _command(git, folder, name),
            env=env,
            timeout=TIMEOUT_SECONDS,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        tracked = done.returncode == 0
    except (subprocess.SubprocessError, OSError, ValueError):
        return False
    with _LOCK:
        _CACHE[key] = tracked
        while len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)
    return tracked


def clear_cache() -> None:
    """Forget every cached answer. Tests use it."""
    with _LOCK:
        _CACHE.clear()
