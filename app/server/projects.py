"""The project list.

The list comes from ``routing-dashboard.json`` in the config dir::

    {"projects": [{"name": "...", "path": "..."}], "plan": "subscription"}

``plan`` is optional and is subscription, api_key or cloud_provider. The file is
read again on every ``load``, so a hand edit needs no restart.

A path may be absolute, "~" or "~/...", or relative. "~" expands with
``ProjectsContext.home``; with no home it stays as written and the project reads as
``folder_not_found``. A relative path resolves against the folder that holds
routing-dashboard.json.

With no usable file the list holds the current project only. An explicit project
that is not listed is added at the front. A fixture run falls back to
``FOLDER/dashboard.json`` for the plan when routing-dashboard.json gives none.

``load`` takes a small frozen ``ProjectsContext`` of paths, not the old server
context. Every stderr line is fixed text and never carries a path or file content.
"""

# ruff: noqa: PTH112, PTH117, PTH118, PTH119 - the port keeps os.path string handling,
# so normpath, isabs and join behave exactly as the old list did.
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import cast

CONFIG_FILE = "routing-dashboard.json"
FIXTURE_CONFIG_FILE = "dashboard.json"
PLANS = ("subscription", "api_key", "cloud_provider")
ALL_KEY = "all"
STATE_OK = "ok"
STATE_FOLDER_NOT_FOUND = "folder_not_found"
STATE_NO_CLAUDE = "no_claude_folder"


@dataclass(frozen=True)
class ProjectsContext:
    """What ``load`` reads.

    Attributes:
        config_dir: The Claude config folder that holds routing-dashboard.json.
        project_dir: The current project's folder.
        project_explicit: True when the project was named on the command line.
        root: A fixture folder to read the plan fallback from, or None.
        home: The home folder that "~" expands to, or None for no expansion.
    """

    config_dir: str
    project_dir: str
    project_explicit: bool = False
    root: str | None = None
    home: str | None = None


def _state(path: str, unexpanded: bool) -> str:
    if unexpanded or not os.path.isdir(path):
        return STATE_FOLDER_NOT_FOUND
    if not os.path.isdir(os.path.join(path, ".claude")):
        return STATE_NO_CLAUDE
    return STATE_OK


class Project:
    """One listed project.

    ``path`` is the resolved path; ``implicit`` marks the fallback.
    """

    __slots__ = ("implicit", "key", "name", "path", "state", "unexpanded")

    def __init__(
        self,
        name: str,
        path: str,
        unexpanded: bool = False,
        implicit: bool = False,
    ) -> None:
        """Make a project and work out its state."""
        self.key: str | None = None
        self.name = name
        self.path = path
        self.unexpanded = unexpanded
        self.implicit = implicit
        self.state = _state(path, unexpanded)


class ProjectList:
    """The projects in order, the current one's key, and the plan (or None)."""

    def __init__(
        self, projects: list[Project], current: str | None, plan: str | None
    ) -> None:
        """Hold the list."""
        self.projects = projects
        self.current = current
        self.plan = plan

    def find(self, key: str) -> Project | None:
        """Return the project with this key, or None."""
        for project in self.projects:
            if project.key == key:
                return project
        return None


def _warn(text: str) -> None:
    sys.stderr.write(f"projects: {text}\n")
    sys.stderr.flush()


def _read_object(path: str, report: bool) -> dict[str, object] | None:
    """Return the JSON object in a file, or None. ``report`` warns on a bad file."""
    try:
        with open(path, encoding="utf-8") as fh:  # noqa: PTH123
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError):
        if report:
            _warn(f"cannot read {CONFIG_FILE}, using the current project only")
        return None
    if not isinstance(data, dict):
        if report:
            _warn(f"{CONFIG_FILE} is not a JSON object, using the current project only")
        return None
    return cast("dict[str, object]", data)


def _resolve_path(text: str, ctx: ProjectsContext) -> tuple[str, bool]:
    """Return ``(path, unexpanded)``. Pure string work, no file system call."""
    if text == "~" or text.startswith("~/"):
        if not isinstance(ctx.home, str) or ctx.home == "":
            return text, True
        text = ctx.home.rstrip("/") + text[1:]
    elif not os.path.isabs(text):
        text = os.path.join(ctx.config_dir, text)
    return os.path.normpath(text), False


def _entries(data: dict[str, object], ctx: ProjectsContext) -> list[Project]:
    """Return the valid, de-duplicated Projects in the file's list."""
    items = data.get("projects")
    if items is None:
        return []
    found: list[Project] = []
    seen: set[str] = set()
    if isinstance(items, list):
        for raw in cast("list[object]", items):
            if not isinstance(raw, dict):
                continue
            item = cast("dict[str, object]", raw)
            name, path = item.get("name"), item.get("path")
            if not (
                isinstance(name, str)
                and name.strip()
                and isinstance(path, str)
                and path.strip()
            ):
                continue
            resolved, unexpanded = _resolve_path(path.strip(), ctx)
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(Project(name.strip(), resolved, unexpanded))
    if not found:
        _warn(
            f"{CONFIG_FILE} has no valid project entry, using the current project only"
        )
    return found


def _plan_from(value: object, source: str) -> str | None:
    """Return value when it is a plan word, else None. A present bad value warns."""
    if value is None:
        return None
    if isinstance(value, str) and value in PLANS:
        return value
    _warn(f"{source} has an unknown plan, treating it as unset")
    return None


def slug(name: str) -> str:
    """Return the key text for a project name, or "project" when nothing is left."""
    text = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return text or "project"


def _assign_keys(projects: list[Project]) -> None:
    used = {ALL_KEY}
    for project in projects:
        base = slug(project.name)
        key, n = base, 1
        while key in used:
            n += 1
            key = f"{base}-{n}"
        used.add(key)
        project.key = key


def load(ctx: ProjectsContext) -> ProjectList:
    """Read routing-dashboard.json now and return the ``ProjectList`` for ``ctx``.

    Args:
        ctx: The folders to read.

    Returns:
        The projects, the current project's key and the plan.
    """
    data = _read_object(os.path.join(ctx.config_dir, CONFIG_FILE), True)
    listed = _entries(data, ctx) if data is not None else []
    given = data.get("plan") if data is not None else None
    plan = _plan_from(given, CONFIG_FILE)
    if given is None and ctx.root is not None:
        fixture = _read_object(os.path.join(ctx.root, FIXTURE_CONFIG_FILE), False)
        if fixture is not None:
            plan = _plan_from(fixture.get("plan"), FIXTURE_CONFIG_FILE)
    current_path = os.path.normpath(ctx.project_dir)
    here = None
    for project in listed:
        if project.path == current_path:
            here = project
            break
    projects = list(listed)
    if not projects:
        here = Project(
            os.path.basename(current_path) or current_path, current_path, implicit=True
        )
        projects.append(here)
    elif here is None and ctx.project_explicit:
        here = Project(os.path.basename(current_path) or current_path, current_path)
        projects.insert(0, here)
    _assign_keys(projects)
    current = here if here is not None else projects[0]
    return ProjectList(projects, current.key, plan)
