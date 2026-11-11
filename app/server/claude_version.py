"""Claude Code version numbers: parse them and compare them.

Ported from the old dashboard's ``version.py``. It does not read the installed
version, because the provider already knows it. Standard library only.
"""

import re
from collections.abc import Iterable

_LEADING = re.compile(r"[0-9]+(?:\.[0-9]+)*")


def parse(text: object) -> tuple[int, ...] | None:
    """Return the leading dotted number of ``text`` as a tuple of ints, or None.

    ``"2.1.302"`` and ``"2.1.302 (Claude Code)"`` both give ``(2, 1, 302)``. Text that
    does not start with digits and dots, or that is not a ``str``, gives None.

    Args:
        text: A version text, or anything.

    Returns:
        The numeric parts, or None.
    """
    if not isinstance(text, str):
        return None
    match = _LEADING.match(text)
    if match is None:
        return None
    return tuple(int(part) for part in match.group(0).split("."))


def _padded(
    left: tuple[int, ...], right: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Return both tuples padded with zeros to the same length."""
    size = max(len(left), len(right))
    return (
        left + (0,) * (size - len(left)),
        right + (0,) * (size - len(right)),
    )


def older(a: object, b: object) -> bool:
    """Return True when both parse and ``a`` is older than ``b``, part by part.

    A missing part counts as 0. Anything that does not parse gives False.

    Args:
        a: The version that may be older.
        b: The version it is compared with.

    Returns:
        Whether ``a`` is older than ``b``.
    """
    left, right = parse(a), parse(b)
    if left is None or right is None:
        return False
    left, right = _padded(left, right)
    return left < right


def oldest(versions: Iterable[object]) -> str | None:
    """Return the oldest of the versions that parse, as the original text, or None.

    Args:
        versions: Version texts, any of which may be junk.

    Returns:
        The oldest parsable text, or None when none parses.
    """
    best: str | None = None
    for text in versions:
        if not isinstance(text, str) or parse(text) is None:
            continue
        if best is None or older(text, best):
            best = text
    return best
