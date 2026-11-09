"""Helpers shared by the ported tests.

These are the few pieces of ``tests/helpers.py`` that the ported transcript, usage,
price and project tests need. The old fixtures under the repository's
``tests/fixtures/`` are read in place through ``FIXTURES``.

A test file imports this module by name. Pytest runs with ``--import-mode=importlib``,
so the test folder is not on ``sys.path``, and each ported test file adds it first.
"""

import contextlib
import os
import shutil
import tempfile
from pathlib import Path

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
