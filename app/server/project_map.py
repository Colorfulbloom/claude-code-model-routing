"""The project map: which transcript folders belong to which project.

``map_projects`` answers "what projects does this store hold" for ``/api/projects``
and for the totals query. It joins two sources.

* Listed projects come from ``projects.load`` with its order, keys and states. Each one
  claims the store folders that ``transcripts.folder_matches`` ties to its path, the
  way the old app tied a project path to its transcript folder (the dashed real path,
  and for a path over 200 units the 200-unit prefix plus the first cwd).
* Every store folder that no listed project claims becomes an unlisted project. Its
  name is the last part of the folder's most common session cwd, its key is the
  readable ``projects.slug`` of that name (suffix ``-2``, ``-3`` on a clash), and its
  state says whether that cwd exists and has a ``.claude`` folder. Its display path
  is the cwd shortened against home, or just the name when that would still be an
  absolute path. Its ``path`` is never read for settings (the model check skips it).

The old app counted these as part of "All projects" without listing them. The map is
pure apart from the connection it reads and the ``is_dir`` checks on the unlisted
cwd paths. It writes nothing.
"""

import re
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import projects
import transcripts

_PATH_SPLIT = re.compile(r"[\\/]")


@dataclass(frozen=True)
class MappedProject:
    """One project of the map.

    Attributes:
        key: The project key, unique in the map and never ``all``.
        name: The name to show.
        display_path: The project path shortened for display (see ``display_path``).
        state: ``ok``, ``no_claude_folder`` or ``folder_not_found``.
        folders: The store transcript folders that belong to it. Empty for a listed
            project with no transcripts.
        listed: True for a project in the routing-dashboard.json list (or the
            implicit current project), False for one found only in the store.
        path: The project's real folder (a listed project's resolved path, an unlisted
            one's most common cwd), or None when none is known. Server side only, for
            reads that need the folder. It is never sent to the page.
    """

    key: str
    name: str
    display_path: str
    state: str
    folders: frozenset[str]
    listed: bool
    path: str | None = None


def _below(path: str, base: str | None) -> str | None:
    """Return the part of ``path`` under ``base`` ("" for base itself), or None.

    Pure string work. The boundary is a whole folder name, so "/x/a" does not hold
    "/x/ab".
    """
    if base is None:
        return None
    base = base.rstrip("/")
    if base == "":
        return None
    if path == base:
        return ""
    if path.startswith(base + "/"):
        return path[len(base) + 1 :]
    return None


def display_path(path: str, home: str | None = None, root: str | None = None) -> str:
    """Return the text a project shows for its path.

    Ported from ``dashboard/resolve.py display_path``. A path inside ``root`` shows
    relative to it with "/" separators ("." for the root itself). Else a path inside
    ``home`` shows as "~/" and the rest ("~" for home itself). Else it shows in full.
    It calls no file system function.

    Args:
        path: The path to shorten.
        home: The home folder, or None.
        root: A fixture root, or None.

    Returns:
        The display text.
    """
    rest = _below(path, root)
    if rest is not None:
        return rest or "."
    rest = _below(path, home)
    if rest is not None:
        return "~/" + rest if rest else "~"
    return path


def _name_from_cwd(cwd: str | None, folder: str) -> str:
    """Return the last part of a cwd, or the folder name when nothing is left."""
    if cwd is None:
        return folder
    parts = [p for p in _PATH_SPLIT.split(cwd.rstrip("/\\")) if p]
    return parts[-1] if parts else folder


def _unlisted_display(cwd: str | None, name: str, ctx: projects.ProjectsContext) -> str:
    """Return the path text for an unlisted project, never an absolute path.

    A cwd under the home folder (or the fixture root) shows in its shortened form
    ("~/work/x"). Any other cwd would show in full, so the folder-derived name shows
    instead. With no cwd the name is the store folder's name.
    """
    if cwd is None:
        return name
    shown = display_path(cwd, ctx.home, ctx.root)
    return name if shown == cwd else shown


def _state_of(path: str | None) -> str:
    """Return the project state for a folder path on disk."""
    if path is None or not Path(path).is_dir():
        return projects.STATE_FOLDER_NOT_FOUND
    if not (Path(path) / ".claude").is_dir():
        return projects.STATE_NO_CLAUDE
    return projects.STATE_OK


def _store_folders(
    conn: sqlite3.Connection,
) -> tuple[list[str], dict[str, str | None], dict[str, Counter[str]]]:
    """Return the store's folders (sorted), each one's first cwd and its cwd counts."""
    first_cwd: dict[str, str | None] = {}
    counts: dict[str, Counter[str]] = {}
    for folder, cwd in conn.execute(
        "SELECT folder, cwd FROM sessions ORDER BY first_ts, session_id"
    ):
        name = str(folder)
        if first_cwd.get(name) is None:
            first_cwd[name] = None if cwd is None else str(cwd)
        if cwd is not None:
            counts.setdefault(name, Counter())[str(cwd)] += 1
    for (folder,) in conn.execute("SELECT DISTINCT folder FROM files"):
        first_cwd.setdefault(str(folder), None)
    return sorted(first_cwd), first_cwd, counts


def _unique_key(base: str, used: set[str]) -> str:
    key, n = base, 1
    while key in used:
        n += 1
        key = f"{base}-{n}"
    used.add(key)
    return key


def map_projects(
    ctx: projects.ProjectsContext, conn: sqlite3.Connection
) -> list[MappedProject]:
    """Return the listed projects in list order, then the unlisted ones.

    Args:
        ctx: Where the project list lives (``projects.load`` reads it now).
        conn: A connection to the store. Only ``sessions`` and ``files`` are read.

    Returns:
        Every listed project with its folders, then one project per store folder no
        listed project claims, sorted by name and then folder so the keys are stable.
    """
    listing = projects.load(ctx)
    folders, first_cwd, counts = _store_folders(conn)
    claimed: set[str] = set()
    used: set[str] = {projects.ALL_KEY}
    out: list[MappedProject] = []
    for project in listing.projects:
        key = project.key or projects.slug(project.name)
        used.add(key)
        mine = frozenset(
            f
            for f in folders
            if f not in claimed
            and transcripts.folder_matches(project.path, f, first_cwd.get(f))
        )
        claimed |= mine
        out.append(
            MappedProject(
                key=key,
                name=project.name,
                display_path=display_path(project.path, ctx.home, ctx.root),
                state=project.state,
                folders=mine,
                listed=True,
                path=project.path,
            )
        )

    unlisted: list[tuple[str, str, str | None]] = []
    for folder in folders:
        if folder in claimed:
            continue
        common = counts.get(folder)
        cwd = common.most_common(1)[0][0] if common else None
        unlisted.append((_name_from_cwd(cwd, folder), folder, cwd))
    for name, folder, cwd in sorted(unlisted, key=lambda u: (u[0].lower(), u[1])):
        out.append(
            MappedProject(
                key=_unique_key(projects.slug(name), used),
                name=name,
                display_path=_unlisted_display(cwd, name, ctx),
                state=_state_of(cwd),
                folders=frozenset({folder}),
                listed=False,
                path=cwd,
            )
        )
    return out
