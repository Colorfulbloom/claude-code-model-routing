"""Helpers shared by the ported tests.

These are the few pieces of ``tests/helpers.py`` that the ported transcript, usage,
price and project tests need. The old fixtures under the repository's
``tests/fixtures/`` are read in place through ``FIXTURES``.

A test file imports this module by name. Pytest runs with ``--import-mode=importlib``,
so the test folder is not on ``sys.path``, and each ported test file adds it first.
"""

# ruff: noqa: PTH100 - home_guard compares os.path strings, as the old guard did.

import builtins
import contextlib
import io
import os
import pathlib
import shutil
import tempfile
from collections.abc import Callable, Collection, Generator
from pathlib import Path
from typing import Any, cast
from unittest import mock

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures"


def refuse_git_tree(folder: str) -> None:
    """Raise RuntimeError when ``folder``, or any folder above its real path, holds a
    ``.git`` entry.

    A project path inside a git work tree resolves to that repo's real
    ``.claude/settings.local.json``, so a test base must never sit in one.

    Args:
        folder: The folder to check.

    Raises:
        RuntimeError: When a ``.git`` entry sits at or above the folder, or cannot be
            ruled out.
    """
    here = Path(folder).resolve()
    while True:
        try:
            (here / ".git").lstat()
        except (FileNotFoundError, NotADirectoryError):
            pass
        except OSError as exc:
            msg = f"refusing to run: cannot rule out a git repo at {here}"
            raise RuntimeError(msg) from exc
        else:
            msg = (
                f"refusing to run: the test temp base {folder} sits inside a git "
                f"work tree at {here}"
            )
            raise RuntimeError(msg)
        if here.parent == here:
            return
        here = here.parent


def tmp_base() -> str | None:
    """Return the base folder for throwaway test folders, or None for the system one.

    ``MR_TEST_TMP`` sets the base and is created when missing. A base inside a git
    work tree is refused.
    """
    base = os.environ.get("MR_TEST_TMP") or None
    refuse_git_tree(base or tempfile.gettempdir())
    if base:
        Path(base).mkdir(parents=True, exist_ok=True)
    return base


def rmtree_force(path: str) -> None:
    """Remove a folder tree even when a test made some folders read only."""
    for dirpath, dirnames, _ in os.walk(path):
        for name in dirnames:
            full = Path(dirpath) / name
            with contextlib.suppress(OSError):
                if not full.is_symlink():
                    full.chmod(0o755)
    with contextlib.suppress(OSError):
        Path(path).chmod(0o755)
    shutil.rmtree(path, ignore_errors=True)


@contextlib.contextmanager
def home_guard(
    homes: Collection[str | os.PathLike[str]], allowed: Collection[object] = ()
) -> Generator[list[str]]:
    """Record every path under ``homes`` that code touches, and refuse home lookups.

    Yields the list of paths seen. Each path is judged by ``os.path.realpath`` as
    well as ``os.path.abspath``, so a symlink into a home fails like the home does.
    Paths under ``allowed`` (the repo) are skipped. The guard wraps the builtin
    ``open``, ``io.open``, the ``os`` calls that read the file system and the
    ``pathlib`` methods that read or resolve a path. ``Path.home`` and
    ``os.path.expanduser`` raise, because calling them is the lookup the resolver
    must never make.

    Args:
        homes: The home folders to watch.
        allowed: Folders under which a touch is fine.

    Yields:
        The list of watched paths the code touched.
    """
    roots: set[str] = set()
    for home in homes:
        roots.update({os.path.abspath(home), os.path.realpath(home)})
    skip = {os.path.realpath(str(a)) for a in allowed} | {
        os.path.abspath(str(a)) for a in allowed
    }
    seen: list[str] = []
    busy: list[bool] = []

    def inside(full: str, bases: set[str]) -> bool:
        return any(full == b or full.startswith(b + os.sep) for b in bases)

    def note(path: object) -> None:
        if busy or isinstance(path, int):
            return
        busy.append(True)
        try:
            try:
                text = os.fsdecode(cast("str", path))
            except TypeError:
                return
            for full in {os.path.abspath(text), os.path.realpath(text)}:
                if inside(full, roots) and not inside(full, skip):
                    seen.append(full)
                    return
        finally:
            busy.pop()

    def watch_function(owner: Any, name: str) -> Any:
        original = getattr(owner, name)

        def wrapper(path: object = ".", *args: Any, **kwargs: Any) -> Any:
            note(path)
            return original(path, *args, **kwargs)

        return mock.patch.object(owner, name, wrapper)

    def watch_method(name: str) -> Any:
        original = getattr(pathlib.Path, name)

        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            note(str(self))
            return original(self, *args, **kwargs)

        return mock.patch.object(pathlib.Path, name, wrapper)

    def refuse(label: str) -> Callable[..., None]:
        def fail(*_args: object, **_kwargs: object) -> None:
            msg = "resolve called " + label
            raise AssertionError(msg)

        return fail

    with contextlib.ExitStack() as stack:
        for owner, name in (
            (builtins, "open"),
            (io, "open"),
            (os, "open"),
            (os, "scandir"),
            (os, "listdir"),
            (os, "stat"),
            (os, "lstat"),
            (os, "access"),
            (os, "walk"),
        ):
            stack.enter_context(watch_function(owner, name))
        for name in (
            "read_text",
            "read_bytes",
            "iterdir",
            "exists",
            "open",
            "stat",
            "is_dir",
            "is_file",
            "glob",
            "rglob",
            "resolve",
        ):
            stack.enter_context(watch_method(name))
        stack.enter_context(
            mock.patch.object(os.path, "expanduser", refuse("os.path.expanduser"))
        )
        stack.enter_context(
            mock.patch.object(pathlib.Path, "home", refuse("Path.home"))
        )
        yield seen
