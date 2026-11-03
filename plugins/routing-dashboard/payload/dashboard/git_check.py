"""Where a project folder sits in a git checkout, and whether git ignores its local settings.

Claude Code 2.1.211 and later read settings.local.json at the repo root. The
dashboard reads and writes that file (see local_root), and the edit routes lock
only when repo_root can't work the root out ("unknown"). repo_place is the older
lstat-only check: root, linked, subfolder or no_repo.

repo_place uses os.lstat alone. It reads no file a repo controls, starts no
process and opens nothing. repo_root (#104) is the reader that names the repo
root, the main checkout's root for a worktree. It starts no process and uses no
open() builtin. It opens only a regular file it has already seen with os.lstat,
with O_NOFOLLOW and O_NONBLOCK, checks the opened descriptor is still a regular
file, and reads at most 4097 bytes. That is how a .git file, a commondir file and
a gitdir back link get read, and it is why a symlink, a FIFO or a device named
.git is never opened. ignore_state is the one call here that starts a
process, a single `git check-ignore`. It builds its environment from nothing and
turns off the two git settings that can run a program a repo names (see the
comment at the command). It lives in this module, apart from api_edit.py, so
that file keeps starting no process of its own.
"""
import os
import shutil
import stat
import subprocess

_SETTINGS_LOCAL = ".claude/settings.local.json"
_MAX_LINE = 4096
_MAX_CONFIG = 65536  # the common dir's config, read only to see core.bare
# Python opens every descriptor non-inheritable (PEP 446), so no O_CLOEXEC. The flags are a module
# constant because tests/test_edit_security.py reads them to prove this open is read-only.
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_WINDOWS = os.name == "nt"  # a module constant, so tests patch it and never os.name


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


class _Refused(Exception):
    """A .git chain that repo_root will not follow."""


def _read_small(path, limit):
    """Return the bytes of a small regular file, or raise _Refused when it is over limit bytes.

    lstat first and refuse anything that is not a regular file, so a FIFO or a
    device is never opened. Then open with O_NOFOLLOW and O_NONBLOCK, fstat the
    descriptor, and read at most limit + 1 bytes in all. A missing file raises
    FileNotFoundError.
    """
    if not stat.S_ISREG(os.lstat(path).st_mode):
        raise _Refused("not a regular file")
    fd = os.open(path, _READ_FLAGS)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _Refused("not a regular file")
        chunks = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, limit + 1 - total)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    finally:
        os.close(fd)
    if total > limit:
        raise _Refused("too long")
    return b"".join(chunks)


def _read_line(path):
    """Return the one line of a small regular file, without its newline.

    A file over _MAX_LINE bytes, text that is not utf-8, an empty file and a file
    with more than one line are refused. A missing file raises FileNotFoundError.
    """
    text = _read_small(path, _MAX_LINE).decode("utf-8")
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    if not text or "\n" in text or "\r" in text:
        raise _Refused("not one line")
    return text


def _is_bare(common):
    """True when the common dir's config sets core.bare to true. A missing config is not bare.

    Reads at most _MAX_CONFIG bytes; a longer or non-utf-8 config is refused.
    """
    try:
        text = _read_small(os.path.join(common, "config"), _MAX_CONFIG).decode("utf-8")
    except FileNotFoundError:
        return False
    section = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("["):
            section = line.split("]", 1)[0][1:].strip().lower()
        elif section == "core":
            key, _, value = line.partition("=")
            if key.strip().lower() == "bare" and value.split("#", 1)[0].split(";", 1)[0].strip().lower() in (
                    "true", "yes", "on", "1"):
                return True
    return False


def _real_dir(base, value):
    """Return the real path of value (relative to base) and require a real folder there."""
    real = os.path.realpath(os.path.join(base, value))
    if not stat.S_ISDIR(os.lstat(real).st_mode):
        raise _Refused("not a folder")
    return real


def _classify_git_file(work):
    """Return (place, root) for a work folder whose .git is a regular file."""
    line = _read_line(os.path.join(work, ".git"))
    if not line.startswith("gitdir: ") or line == "gitdir: ":
        raise _Refused("not a gitdir line")
    git_dir = _real_dir(work, line[len("gitdir: "):])
    try:
        common_value = _read_line(os.path.join(git_dir, "commondir"))
    except FileNotFoundError:
        return "submodule", work
    common = os.path.realpath(os.path.join(git_dir, common_value))
    if os.path.basename(common) != ".git":
        raise _Refused("common dir is not named .git")
    main = os.path.dirname(common)
    seen = os.lstat(common)
    named = os.lstat(os.path.join(main, ".git"))
    if not (stat.S_ISDIR(seen.st_mode) and stat.S_ISDIR(named.st_mode)
            and seen.st_dev == named.st_dev and seen.st_ino == named.st_ino):
        raise _Refused("common dir is not the main .git folder")
    if _is_bare(common):
        raise _Refused("common dir is a bare repo")
    if os.path.dirname(git_dir) != os.path.join(common, "worktrees") or not os.path.basename(git_dir):
        raise _Refused("git dir is not a linked worktree folder")
    back = _read_line(os.path.join(git_dir, "gitdir"))
    if os.path.realpath(os.path.join(git_dir, back)) != os.path.realpath(os.path.join(work, ".git")):
        raise _Refused("no back link")
    return "worktree", main


def _within(path, folder):
    """True when path is folder or below it (both real paths)."""
    folder = folder.rstrip(os.sep) or os.sep
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _find_root(path, bound=None):
    """Return (place, root) before the exceptions: walk up to the nearest folder holding a .git.

    When bound is given and the folder holding the nearest .git is outside its real path,
    the answer is ("unknown", None) and nothing in that folder is opened.
    """
    start = os.path.realpath(path)
    real_bound = os.path.realpath(bound) if bound else None
    here = start
    while True:
        try:
            info = os.lstat(os.path.join(here, ".git"))
        except (FileNotFoundError, NotADirectoryError):
            info = None
        if info is not None:
            if real_bound is not None and not _within(here, real_bound):
                return "unknown", None
            if stat.S_ISDIR(info.st_mode):
                return ("root" if here == start else "subfolder"), here
            if stat.S_ISREG(info.st_mode):
                return _classify_git_file(here)
            raise _Refused("a .git that is not a folder or a file")
        parent = os.path.dirname(here)
        if parent == here:
            return "no_repo", None
        here = parent


def _start_folder(root, home):
    """True when the Claude Code docs say the starting folder's own settings.local.json applies."""
    if _WINDOWS:
        return True
    if home and root == os.path.realpath(home):
        return True
    uid = os.geteuid()
    for entry in (root, os.path.join(root, ".git"), os.path.join(root, ".claude")):
        try:
            info = os.lstat(entry)
        except (FileNotFoundError, NotADirectoryError):
            continue  # .claude is allowed to be absent
        if info.st_uid != uid:
            return True
    return False


def repo_root(path, home=None, bound=None):
    """Return (place, root) for a project path, where Claude Code keeps settings.local.json (#104).

    place is one of
    - "no_repo", None: no path, or no .git entry in the path or any parent.
    - "root", R: the path holds a real .git folder. R is its real path.
    - "subfolder", R: the nearest parent holding .git has a real .git folder.
    - "worktree", R: the nearest folder W holding .git has a .git file that checks
      out as a linked worktree. R is the real path of the main checkout.
    - "submodule", R: W has a .git file whose git dir holds no commondir (a
      submodule, or a repo made with git init --separate-git-dir). R is W.
    - "start_folder", None: an exception in the Claude Code docs applies to R. R is
      the real path of home, the platform is Windows, or R, R/.git or R/.claude
      (when it exists) is not owned by the effective user.
    - "unknown", None: bound is given and the folder holding the nearest .git is not
      inside realpath(bound) (that folder is never read), or anything else, such as a .git symlink, FIFO or device, a .git
      file that can't be read, is over 4096 bytes or is not one "gitdir: <path>"
      line, a broken chain, or any OSError or ValueError. It never raises.

    The chain for a .git file is checked with no process and no git. The file names a
    git dir G (a relative path is relative to W). G/commondir names the common dir C
    (relative to G). The chain holds only when C is named .git, M = dirname(C) has
    a .git folder that is the same inode as C, G sits directly under C/worktrees,
    and G/gitdir (git's own back link) names W/.git.

    A bare repo in a folder named .git passes that chain, so its config is read as well
    (at most 64 KiB, same safe open). core.bare = true reads unknown and the edit routes
    lock, because there is no checkout root to hold the file (owner decision on #104).
    A worktree of a submodule fails it, because C is .git/modules/<name>, and reads
    unknown.
    """
    if not path:
        return "no_repo", None
    try:
        place, root = _find_root(path, bound)
        if root is None:
            return place, None
        if _start_folder(root, home):
            return "start_folder", None
        return place, root
    except (OSError, ValueError, TypeError, _Refused):
        return "unknown", None


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
