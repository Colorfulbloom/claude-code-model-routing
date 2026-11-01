"""Where a project folder sits in a git checkout, found with lstat alone.

Claude Code reads settings.local.json at the repo root. When the project is not
that root, a root file the dashboard can't see can beat any line it writes, so
the edit routes lock. repo_place answers the one question: root, linked,
subfolder or no_repo.

The walk uses os.lstat only. It reads no file a repo controls, starts no process
and opens nothing. A later ticket adds a git call to this module, which is why it
lives apart from api_edit.py (that file may start no process).
"""
import os


def _git_kind(folder):
    """Return "dir" for a .git folder, "other" for any other .git entry, None when there is none."""
    try:
        info = os.lstat(os.path.join(folder, ".git"))
    except (FileNotFoundError, NotADirectoryError):
        return None  # no .git here, so keep walking
    except OSError:
        return "other"  # an entry we can't read may be a repo, so it must not read as no .git
    return "dir" if (info.st_mode & 0o170000) == 0o040000 else "other"


def repo_place(path):
    """Return "root", "linked", "subfolder" or "no_repo" for a project path.

    root: the project holds a .git folder. linked: it holds a .git file or symlink
    (a worktree or a submodule, not told apart on purpose). subfolder: a parent
    holds a .git of any kind. no_repo: none found, or no path.
    """
    if not path:
        return "no_repo"
    try:
        here = os.path.realpath(path)
    except (OSError, ValueError):
        return "no_repo"
    kind = _git_kind(here)
    if kind == "dir":
        return "root"
    if kind == "other":
        return "linked"
    while True:
        parent = os.path.dirname(here)
        if parent == here:
            return "no_repo"
        here = parent
        if _git_kind(here) is not None:
            return "subfolder"
