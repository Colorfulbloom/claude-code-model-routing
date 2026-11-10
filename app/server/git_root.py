"""Find a project's git root by looking for ``.git``, with no git process.

Ported from ``dashboard/git_check.py`` ``_find_root`` and ``_start_folder``. Claude
Code keeps ``.claude/settings.local.json`` at the repo root, so a project below its
root reads the root's file (owner answer 5, m4-build.md section 15). The walk only
calls ``lstat`` on ``<folder>/.git`` up the ancestors. It never opens a file, never
reads another repo, and never runs git.

One difference from ``dashboard/local_root.py``. For a linked worktree (a ``.git``
that is a file) the old code follows the ``gitdir`` chain to the main checkout. This
port stops at the worktree folder itself, because the main checkout is another repo
and reading it goes past owner answer 5. A worktree therefore keeps its own
``.claude/settings.local.json``.
"""

import os
import stat
from pathlib import Path

# ruff: noqa: PTH118, PTH120 - the walk is string work on real paths.

LOCAL_SETTINGS = Path(".claude") / "settings.local.json"


def _real(path: str | os.PathLike[str]) -> str | None:
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None


def find_root(start: str | os.PathLike[str]) -> Path | None:
    """Return the folder that holds the nearest ``.git``, or None.

    A ``.git`` folder and a ``.git`` file (a linked worktree or a submodule) both
    make their parent the root. Anything else named ``.git`` (a symlink, a pipe) and
    an unreadable ancestor give None, so nothing in that folder is trusted.

    Args:
        start: The project folder. Its real path is where the walk starts.

    Returns:
        The real path of the root, or None when no ancestor holds ``.git``.
    """
    here = _real(start)
    if here is None:
        return None
    while True:
        try:
            info = os.lstat(os.path.join(here, ".git"))
        except (FileNotFoundError, NotADirectoryError):
            info = None
        except OSError:
            return None
        if info is not None:
            if stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode):
                return Path(here)
            return None
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def _owned_elsewhere(root: Path, home: str | os.PathLike[str] | None) -> bool:
    """True when the docs' start-folder exception applies to the root.

    That is when the root is the home folder, or when the root, its ``.git`` or its
    ``.claude`` belongs to another user. A file owned by someone else is never read.
    """
    if home is not None and str(root) == _real(home):
        return True
    uid = os.geteuid()
    for entry in (root, root / ".git", root / ".claude"):
        try:
            info = os.lstat(entry)
        except (FileNotFoundError, NotADirectoryError):
            continue
        except OSError:
            return True
        if info.st_uid != uid:
            return True
    return False


def local_settings_path(
    project: str | os.PathLike[str], home: str | os.PathLike[str] | None = None
) -> Path | None:
    """Return the repo-root ``settings.local.json`` when it is not the project's own.

    Args:
        project: The listed project's folder.
        home: The home folder, or None. A root that is the home folder keeps the
            project's own file.

    Returns:
        ``<root>/.claude/settings.local.json`` when a git root exists, differs from
        the project and is not owned by another user. Otherwise None, and the
        project's own ``.claude/settings.local.json`` is the only local file.
    """
    root = find_root(project)
    real_project = _real(project)
    if root is None or real_project is None or str(root) == real_project:
        return None
    if _owned_elsewhere(root, home):
        return None
    return root / LOCAL_SETTINGS
