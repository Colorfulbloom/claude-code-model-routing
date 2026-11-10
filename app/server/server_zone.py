"""The server's time zone: where Review's local days and windows are counted.

A demo or flow build carries its zone in ``session.json`` (``tz``), which is what the
M1 differential counts in. Real mode uses the machine's zone, found in this order: the
``TZ`` environment variable when it names a valid zone, then the ``/etc/localtime``
symlink target (the part after ``zoneinfo/``), then UTC. Nothing else is read.
"""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC_ZONE = "UTC"
LOCALTIME = Path("/etc/localtime")
SESSION_JSON = "session.json"
_ZONEINFO = "zoneinfo/"


def _valid(name: str) -> ZoneInfo | None:
    """Return the zone a name makes, or None when it is not a valid IANA name."""
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None


def machine_zone(environ: Mapping[str, str], localtime: Path = LOCALTIME) -> ZoneInfo:
    """Return the machine's IANA zone, or UTC when none can be found.

    Args:
        environ: The environment. Only ``TZ`` is read. A leading ``:`` is dropped, as
            POSIX allows.
        localtime: The symlink that names the system zone, ``/etc/localtime``.

    Returns:
        The zone from ``TZ`` when valid, else from the symlink's target after
        ``zoneinfo/``, else UTC.
    """
    found = _valid(environ.get("TZ", "").removeprefix(":"))
    if found is not None:
        return found
    try:
        target = str(localtime.readlink())
    except OSError:
        target = ""
    _head, mark, name = target.partition(_ZONEINFO)
    found = _valid(name) if mark else None
    return found if found is not None else ZoneInfo(UTC_ZONE)


def session_zone(build_dir: Path) -> ZoneInfo:
    """Return the zone a demo or flow build names in its ``session.json``.

    Args:
        build_dir: The folder that holds ``session.json`` (the build's root, beside
            its ``config`` folder).

    Returns:
        The ``tz`` zone, or UTC when the file or the key is missing or not a zone.
    """
    try:
        data = cast(
            "object",
            json.loads((build_dir / SESSION_JSON).read_text(encoding="utf-8")),
        )
    except (OSError, ValueError):
        return ZoneInfo(UTC_ZONE)
    name = cast("dict[str, object]", data).get("tz") if isinstance(data, dict) else None
    found = _valid(name) if isinstance(name, str) else None
    return found if found is not None else ZoneInfo(UTC_ZONE)
