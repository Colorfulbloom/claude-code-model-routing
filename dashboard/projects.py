"""The project list and the /api/projects route.

The list comes from routing-dashboard.json in the config dir:

    {"projects": [{"name": "...", "path": "..."}], "plan": "subscription"}

`plan` is optional and is subscription, api_key or cloud_provider. The file is
read again on every request, so a hand edit needs no restart.

A path may be absolute, "~" or "~/...", or relative. "~" expands with ctx.home;
with no home it stays as written and the project reads as missing_folder. A
relative path resolves against the folder that holds routing-dashboard.json.

With no usable file the list holds the current project only. An explicit
--project that is not listed is added at the front. A fixture run falls back to
FOLDER/dashboard.json for the plan when routing-dashboard.json gives none.

A route is a function (ctx, query) -> (status, payload). A project's path goes
into a response only as path_display: relative to the fixture root, as "~/..."
inside the home folder, and in full when it lies outside both. No route in this
module puts the path of routing-dashboard.json or any file content into a
response. api_usage.api_projects adds that path to its answer as
config_file_display, in the same display form. Every stderr line is fixed text.

Standard library only, Python 3.9.
"""
import json
import os
import re
import sys

import resolve

CONFIG_FILE = "routing-dashboard.json"
FIXTURE_CONFIG_FILE = "dashboard.json"
PLANS = ("subscription", "api_key", "cloud_provider")
ALL_KEY = "all"
STATE_OK = "ok"
STATE_MISSING = "missing_folder"
STATE_NO_CLAUDE = "no_claude_folder"


class Project:
    """One listed project. path is the resolved path; implicit marks the fallback."""

    __slots__ = ("key", "name", "path", "state", "implicit", "unexpanded")

    def __init__(self, name, path, unexpanded=False, implicit=False):
        self.key = None
        self.name = name
        self.path = path
        self.unexpanded = unexpanded
        self.implicit = implicit
        self.state = _state(path, unexpanded)


class ProjectList:
    """The projects in order, the current one's key, and the plan (or None)."""

    def __init__(self, projects, current, plan):
        self.projects = projects
        self.current = current
        self.plan = plan

    def find(self, key):
        for project in self.projects:
            if project.key == key:
                return project
        return None


def _warn(text):
    sys.stderr.write("projects: %s\n" % text)
    sys.stderr.flush()


def _state(path, unexpanded):
    if unexpanded or not os.path.isdir(path):
        return STATE_MISSING
    if not os.path.isdir(os.path.join(path, ".claude")):
        return STATE_NO_CLAUDE
    return STATE_OK


def _read_object(path, report):
    """Return the JSON object in a file, or None. report=True warns on a bad file."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        return None
    except (OSError, ValueError, RecursionError):
        if report:
            _warn("cannot read %s, using the current project only" % CONFIG_FILE)
        return None
    if not isinstance(data, dict):
        if report:
            _warn("%s is not a JSON object, using the current project only" % CONFIG_FILE)
        return None
    return data


def _resolve_path(text, ctx):
    """Return (path, unexpanded). Pure string work, no file system call."""
    if text == "~" or text.startswith("~/"):
        if not isinstance(ctx.home, str) or ctx.home == "":
            return text, True
        text = ctx.home.rstrip("/") + text[1:]
    elif not os.path.isabs(text):
        text = os.path.join(ctx.config_dir, text)
    return os.path.normpath(text), False


def _entries(data, ctx):
    """Return the valid, de-duplicated Projects in the file's list."""
    items = data.get("projects")
    if items is None:
        return []
    found, seen = [], set()
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name, path = item.get("name"), item.get("path")
            if not (isinstance(name, str) and name.strip()
                    and isinstance(path, str) and path.strip()):
                continue
            resolved, unexpanded = _resolve_path(path.strip(), ctx)
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(Project(name.strip(), resolved, unexpanded))
    if not found:
        _warn("%s has no valid project entry, using the current project only" % CONFIG_FILE)
    return found


def _plan_from(value, source):
    """Return value when it is a plan word, else None. A present bad value warns."""
    if value is None:
        return None
    if isinstance(value, str) and value in PLANS:
        return value
    _warn("%s has an unknown plan, treating it as unset" % source)
    return None


def slug(name):
    text = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return text or "project"


def _assign_keys(projects):
    used = {ALL_KEY}
    for project in projects:
        base = slug(project.name)
        key, n = base, 1
        while key in used:
            n += 1
            key = "%s-%d" % (base, n)
        used.add(key)
        project.key = key


def load(ctx):
    """Read routing-dashboard.json now and return the ProjectList for ctx."""
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
        here = Project(os.path.basename(current_path) or current_path, current_path,
                       implicit=True)
        projects.append(here)
    elif here is None and ctx.project_explicit:
        here = Project(os.path.basename(current_path) or current_path, current_path)
        projects.insert(0, here)
    _assign_keys(projects)
    current = here if here is not None else projects[0]
    return ProjectList(projects, current.key, plan)


def api_projects(ctx, query):
    """Return (200, {"projects": [...], "current": key})."""
    listing = load(ctx)
    rows = [{
        "key": p.key,
        "name": p.name,
        "path_display": resolve.display_path(p.path, home=ctx.home, root=ctx.root),
        "state": p.state,
    } for p in listing.projects]
    return 200, {"projects": rows, "current": listing.current}
