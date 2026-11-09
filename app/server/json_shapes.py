"""Type guards for values read from JSON.

The ported resolver code checks every value it reads with ``isinstance``. Pyright
narrows ``object`` to ``dict[Unknown, Unknown]`` on that check, so these guards
narrow to ``dict[str, Any]`` and ``list[Any]`` instead. Each one is the same
``isinstance`` test the old code ran, so behaviour does not change.
"""

from typing import Any, TypeGuard


def is_dict(value: object) -> TypeGuard[dict[str, Any]]:
    """Return True when ``value`` is a dict, narrowing it to ``dict[str, Any]``."""
    return isinstance(value, dict)


def is_list(value: object) -> TypeGuard[list[Any]]:
    """Return True when ``value`` is a list, narrowing it to ``list[Any]``."""
    return isinstance(value, list)
