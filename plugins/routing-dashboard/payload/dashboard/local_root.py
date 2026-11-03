"""Which settings.local.json a project's sessions read, and the dashboard writes (#104).

Claude Code 2.1.211 and later keep .claude/settings.local.json at the git repo
root, the main checkout's root for a worktree. A file left in the starting folder
(the leftover file) is still read, under the root file. for_project works this out
once per request. collect, edit_store.target_for and every overlay take its path
strings, so the same file is always the same string.

Path strings. When the root is the project folder itself, every path keeps the
project path as written, as before #104. When the root is elsewhere, the root is
the real path git_check.repo_root returns. outside_project compares real paths.
"""
import collections
import os

import git_check
import version

FIRST_ROOT_VERSION = "2.1.211"
LOCAL_NAME = "settings.local.json"

# place: a git_check.repo_root place, or "old_version" (Claude Code before 2.1.211).
# base: the folder that holds the .claude folder of the local file. path: that file.
# start_base and start_path: the starting folder and its own local file.
# leftover: path is not start_path, so the starting folder's file is a second, lower file.
# locked: the root can't be worked out ("unknown"), so every write locks.
# outside_project: the local file sits outside the project folder (real paths).
Local = collections.namedtuple(
    "Local", "place base path start_base start_path leftover locked outside_project")


def _inside(path, folder):
    folder = folder.rstrip(os.sep) or os.sep
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _real(path):
    try:
        return os.path.realpath(path)
    except (OSError, ValueError):
        return None


def _place(ctx, project_path):
    """Return (place, real root or None) for a project path."""
    installed = version.installed(ctx)
    if installed is not None and version.older(installed, FIRST_ROOT_VERSION):
        return "old_version", None
    bound = getattr(ctx, "root", None)
    place, root = git_check.repo_root(project_path, home=getattr(ctx, "home", None), bound=bound)
    if root is not None and bound is not None:
        # A fixture run, or a test world, reads nothing outside its own folder.
        real_bound = _real(bound)
        if real_bound is None or not _inside(root, real_bound):
            return "unknown", None
    return place, root


def start_only(project_path):
    """Return the Local of a project whose local file stays in the starting folder."""
    start_path = os.path.join(project_path, ".claude", LOCAL_NAME)
    return Local("no_repo", project_path, start_path, project_path, start_path, False, False, False)


def for_project(ctx, project):
    """Return the Local of a listed project. Reads lstat and the bounded .git files only."""
    path = getattr(project, "path", None)
    if not path or getattr(project, "unexpanded", False):
        return start_only(path or "")
    place, root = _place(ctx, path)
    real_project = _real(path)
    base = path
    if root is not None and real_project is not None and root != real_project:
        base = root
    local_path = os.path.join(base, ".claude", LOCAL_NAME)
    start_path = os.path.join(path, ".claude", LOCAL_NAME)
    leftover = local_path != start_path
    real_base = _real(base)
    outside = bool(leftover and real_base is not None and real_project is not None
                   and not _inside(real_base, real_project))
    return Local(place, base, local_path, path, start_path, leftover, place == "unknown", outside)
