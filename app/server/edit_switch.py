"""The edit switch: whether this server may write the owner's files.

``serve.py --allow-edits`` asks for edits. Real mode (``--real``) gets them. A fixture
or demo run gets them only when every folder it touches sits outside the Bar Tab
checkout and outside the git work tree that holds the checkout, so a test or a demo can
never write into ``tests/fixtures/`` or ``app/fixtures/`` (m6-build.md section 3.1).
Otherwise the state is ``unavailable``. The check is the one ``_tmp_base`` makes for the
old suite (fact T-c826), kept to the two roots the plan names.

The startup check sees the Claude folder, the store, the data folder and the launch
project. A project root is known only once the store has mapped it, so
``root_watch`` re-checks each mapping and turns edits from on to unavailable for good
when one sits in the checkout. A refusal logs a fixed reason, never a path.
"""

import logging
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

import git_root
from access import AccessState
from models import EditsMode

logger = logging.getLogger("bartab.serve")

REPO_ROOT = Path(__file__).resolve().parents[2]


def checkout_roots(checkout: Path | None = None) -> tuple[str, ...]:
    """Return the real paths a fixture or demo run may not edit inside.

    Args:
        checkout: The Bar Tab checkout. Defaults to the one this file sits in.

    Returns:
        The checkout, and the git work tree that holds it when that is another folder.
    """
    base = os.path.realpath(os.fspath(checkout or REPO_ROOT))
    found = [base]
    tree = git_root.find_root(base)
    if tree is not None and str(tree) != base:
        found.append(str(tree))
    return tuple(found)


def outside_checkout(
    path: str | os.PathLike[str], checkout: Path | None = None
) -> bool:
    """True when ``path`` sits outside the checkout and the work tree holding it.

    Args:
        path: Any path. Links resolve first, and a path that does not exist is judged
            by where it would be.
        checkout: The Bar Tab checkout, for tests. Defaults to this one.
    """
    real: str = os.path.realpath(Path(path))
    return not any(
        real == root or real.startswith(root.rstrip(os.sep) + os.sep)
        for root in checkout_roots(checkout)
    )


def resolve_state(
    *,
    requested: bool,
    real: bool,
    claude_dir: Path | None,
    folders: Sequence[Path | None] | Mapping[str, Path | None],
    checkout: Path | None = None,
) -> EditsMode:
    """Work out the edits state a server starts in.

    Args:
        requested: True when ``--allow-edits`` was given.
        real: True for ``--real``, which edits the owner's own folder.
        claude_dir: The Claude folder the server reads, or None for the canned
            fixture scenario, which has no files to write.
        folders: The other folders the server touches, such as the data folder, the
            store and the launch project. None entries are skipped. A mapping names
            each folder (``data``, ``store``, ``project``) for the log line, and a
            list reads as "a" folder.
        checkout: The Bar Tab checkout, for tests.

    Returns:
        ``off`` without the flag, ``on`` in real mode, ``unavailable`` for a run that
        has no Claude folder or a folder inside the checkout, else ``on``.
    """
    if not requested:
        return "off"
    if real:
        return "on"
    if claude_dir is None:
        logger.warning(
            "edits unavailable: this fixture run has no Claude folder to edit"
            " (pass --claude-dir)"
        )
        return "unavailable"
    named = (
        list(folders.items())
        if isinstance(folders, Mapping)
        else [("a", folder) for folder in folders]
    )
    for label, folder in [("Claude", claude_dir), *named]:
        held = None if folder is None else _holder(folder, checkout)
        if held is not None:
            logger.warning("edits unavailable: the %s folder sits in %s", label, held)
            return "unavailable"
    return "on"


def _holder(path: str | os.PathLike[str], checkout: Path | None) -> str | None:
    """Name the checkout root a path sits in, or None when it sits outside both."""
    real: str = os.path.realpath(Path(path))
    roots = checkout_roots(checkout)
    for number, root in enumerate(roots):
        if real == root or real.startswith(root.rstrip(os.sep) + os.sep):
            if number == 0:
                return "the Bar Tab checkout"
            return "the git work tree that holds the Bar Tab checkout"
    return None


def root_watch(
    state: AccessState, checkout: Path | None = None
) -> Callable[[Iterable[str]], None]:
    """Build the check the store provider runs on every project mapping.

    A mapped project root inside the checkout turns edits from on to unavailable for
    the rest of the run, and so empties the edit keys. Only a fixture or demo run
    gets this watch. Real mode edits the owner's own projects, which may include the
    checkout itself.

    Args:
        state: The access state that holds the switch.
        checkout: The Bar Tab checkout, for tests.

    Returns:
        A function that takes the mapped project paths.
    """

    def watch(paths: Iterable[str]) -> None:
        inside = any(not outside_checkout(path, checkout) for path in paths)
        if inside and state.disable_edits():
            logger.warning("edits unavailable: a project is in the Bar Tab checkout")

    return watch
