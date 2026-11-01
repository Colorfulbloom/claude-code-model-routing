"""Where a project folder sits in a git checkout, and whether git ignores its local settings.

Claude Code reads settings.local.json at the repo root. When the project is not
that root, a root file the dashboard can't see can beat any line it writes, so
the edit routes lock. repo_place answers the one question: root, linked,
subfolder or no_repo.

repo_place uses os.lstat alone. It reads no file a repo controls, starts no
process and opens nothing. ignore_state is the one call here that starts a
process, a single `git check-ignore`. It builds its environment from nothing and
turns off the two git settings that can run a program a repo names (see the
comment at the command). It lives in this module, apart from api_edit.py, so
that file keeps starting no process of its own.
"""
import os
import shutil
import subprocess

_SETTINGS_LOCAL = ".claude/settings.local.json"


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


def ignore_state(project_path, path_env, home, xdg_config_home=None):
    """Return "no_repo", "ignored", "not_ignored" or "unknown" for .claude/settings.local.json.

    Asks git whether it ignores the file, and never raises. Git is found with
    shutil.which on path_env (None under --fixture), so the caller's own
    environment is never read. The child gets a new environment holding only what
    the caller passed.
    """
    if repo_place(project_path) == "no_repo":
        return "no_repo"
    if not path_env:
        return "unknown"
    try:
        git = shutil.which("git", path=path_env)
    except (OSError, ValueError, TypeError):
        return "unknown"
    if not git or not os.path.isabs(git):
        return "unknown"
    # Two settings keep a repo from running a program through this call:
    # - core.fsmonitor=false stops check-ignore running a program named in the
    #   project's .git/config, including one that arrives through include.path.
    # - --no-lazy-fetch and GIT_NO_LAZY_FETCH=1 stop a partial clone fetching a
    #   missing .gitignore blob, which runs core.sshCommand. Both are set, so one
    #   still holds if the other is dropped.
    command = [git, "--no-lazy-fetch", "-c", "core.fsmonitor=false", "-C", project_path,
               "check-ignore", "-q", "--", _SETTINGS_LOCAL]
    env = {key: value for key, value in (
        ("PATH", path_env),
        ("HOME", home),
        ("GIT_NO_LAZY_FETCH", "1"),
        ("XDG_CONFIG_HOME", xdg_config_home),
    ) if value is not None}
    try:
        done = subprocess.run(command, env=env, timeout=2, stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError, ValueError):
        return "unknown"
    if done.returncode == 0:
        return "ignored"
    if done.returncode == 1:
        return "not_ignored"
    return "unknown"
