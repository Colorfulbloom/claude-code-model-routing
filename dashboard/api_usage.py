"""The /api/usage route, the extra fields of /api/projects and the reader warm-up.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON.

The transcript reader keeps its parsed files in memory, on the Cache that hangs
off the Context. start_warm reads every transcript once on a daemon thread when
the server starts. A /api/usage request waits on the same lock, so no file is
parsed twice. Nothing else takes that lock: /api/projects reports the reader's
state without waiting for it, and /api/settings never touches it.

One All projects build takes a couple of seconds on 150,000 records, so a built
answer is kept per scope. The reader runs on every request, but it only stats
files that did not change. A kept answer is reused while the reader's signature,
the shown project rows, the resolver entries and the local date are the same,
and for at most MAX_AGE_SECONDS, so the "today" and "7d" windows never lag more
than a minute.

Zone. local_zone picks the zone the page shows: TZ when it names a zone, else
the zone the /etc/localtime link points at, else a fixed offset (notes.tz_fixed).
A fixture run supplies the clock (ctx.fixed_now) and the zone name from
session.json, so the tests do not depend on the machine.

No response holds message text, tool data or an agent description: the reader
keeps none, and this module adds only counts, names from the project list and
the pin check's settings data. Every stderr line is fixed text or a class name.

Standard library only, Python 3.9. Nothing here writes a file.
"""
import datetime
import hashlib
import json
import os
import sys
import threading
import zoneinfo

import api_settings
import collect
import pincheck
import prices as price_list
import projects
import resolve
import transcripts
import usage as usage_views

MAX_AGE_SECONDS = 60
ZONEINFO_MARKER = "zoneinfo/"


class Cache(object):
    """What the usage routes keep between requests. lock guards every field below it.

    reader is None until the first read starts. warm turns True when a read ends.
    skipped is the old-file count of the last finished read (None before that).
    built maps a scope (a project key, or "all") to (fingerprint, payload, built_at).
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.reader = None
        self.warm = False
        self.skipped = None
        self.built = {}
        self.prices = None


# --------------------------------------------------------------------------
# Zone and clock

def local_zone(tz_name, localtime_link):
    """Return (tzinfo, label, fixed) for the zone the page shows.

    1. tz_name (a leading ":" is dropped) when it names a zone.
    2. The key after "zoneinfo/" in the target of the localtime_link symlink.
    3. The machine's current UTC offset as a fixed zone, with fixed True.
    """
    name = tz_name[1:] if isinstance(tz_name, str) and tz_name.startswith(":") else tz_name
    if isinstance(name, str) and name:
        try:
            zone = zoneinfo.ZoneInfo(name)
            return zone, zone.key, False
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
            pass
    if localtime_link is not None:
        try:
            target = os.readlink(localtime_link)
        except OSError:
            target = ""
        _head, found, key = target.partition(ZONEINFO_MARKER)
        if found and key:
            try:
                zone = zoneinfo.ZoneInfo(key)
                return zone, zone.key, False
            except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
                pass
    here = datetime.datetime.now().astimezone()
    return here.tzinfo, here.tzname(), True


def _zone(ctx):
    return local_zone(ctx.tz_name, ctx.localtime_link)


def _now(ctx, tz):
    """The current moment in tz: the fixture's fixed clock when it has one."""
    moment = ctx.fixed_now if ctx.fixed_now is not None else datetime.datetime.now(tz)
    return moment.astimezone(tz)


# --------------------------------------------------------------------------
# The reader and its warm-up

def _read(ctx, cache, now):
    """Read the transcripts. The caller holds cache.lock."""
    if cache.reader is None:
        cache.reader = transcripts.Reader(ctx.config_dir)
    result = cache.reader.read(now)
    cache.warm = True
    cache.skipped = result.notes["skipped_old_files"]
    return result


def warm(ctx):
    """Read every transcript once. A failure logs its class name and leaves warm False."""
    cache = ctx.usage_cache
    try:
        tz = _zone(ctx)[0]
        with cache.lock:
            _read(ctx, cache, _now(ctx, tz))
    except Exception as exc:  # no str(exc): it could hold a path
        sys.stderr.write("usage: warm-up failed (%s)\n" % type(exc).__name__)
        sys.stderr.flush()


def start_warm(ctx):
    """Start warm(ctx) on a daemon thread and return the thread."""
    thread = threading.Thread(target=warm, args=(ctx,), name="usage-warm", daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------------
# /api/projects

def api_projects(ctx, query):
    """Return projects.api_projects plus tz, now, transcripts_dir_display,
    config_file_display, reader and version.

    It never takes the cache lock and never calls Reader.read, so it answers
    while the reader is busy. files is None until the first scan has counted
    them, and skipped is None until the first read ends. config_file_display
    is the display form of routing-dashboard.json in the config dir. readable
    is a stat at request time: True when <config_dir>/projects is a directory
    the process can read and enter, else False.
    """
    status, payload = projects.api_projects(ctx, query)
    tz, label, _fixed = _zone(ctx)
    cache = ctx.usage_cache
    reader = cache.reader
    payload = dict(payload)
    payload["version"] = api_settings.version_field(ctx)
    payload["tz"] = label
    payload["now"] = _now(ctx, tz).isoformat()
    payload["transcripts_dir_display"] = resolve.display_path(
        os.path.join(ctx.config_dir, "projects"), home=ctx.home, root=ctx.root)
    folder = os.path.join(ctx.config_dir, "projects")
    payload["config_file_display"] = resolve.display_path(
        os.path.join(ctx.config_dir, projects.CONFIG_FILE), home=ctx.home, root=ctx.root)
    payload["reader"] = {
        "readable": os.path.isdir(folder) and os.access(folder, os.R_OK | os.X_OK),
        "warm": cache.warm,
        "files": reader.files_found if reader is not None else None,
        "skipped": cache.skipped,
    }
    return status, payload


# --------------------------------------------------------------------------
# /api/usage

def _entries(ctx, listing, project):
    """The resolver entries for one listed project, as api_settings.settings builds them."""
    if project.state == projects.STATE_MISSING and not project.implicit:
        return []
    collected = collect.collect(
        config_dir=ctx.config_dir,
        project_dir=project.path,
        managed_dir=ctx.managed_dir,
        shell_env=ctx.shell_env,
        rules=ctx.rules)
    extra = {} if ctx.shell_label is None else {"shell_label": ctx.shell_label}
    inputs = resolve.Inputs(
        collected=collected,
        flags=list(ctx.flags),
        cli_settings=ctx.cli_settings,
        plan=listing.plan,
        home=ctx.home,
        root=ctx.root,
        **extra)
    return resolve.resolve(inputs, ctx.rules, ctx.agent_fields)


def _unreadable(ctx, result, project):
    """The display path of what the reader could not use for this scope, or None.

    The projects folder when it could not be listed, for every scope. Else, for a
    listed project, its own transcript folder when it could not be listed or all
    its files failed to open. All projects shows what it could read, so one failed
    folder does not show there.
    """
    top = os.path.join(ctx.config_dir, "projects")
    if result.top_unreadable:
        return resolve.display_path(top, home=ctx.home, root=ctx.root)
    if project is not None and project.path:
        folder = transcripts.unreadable_folder(project.path, result.unreadable)
        if folder is not None:
            return resolve.display_path(os.path.join(top, folder), home=ctx.home, root=ctx.root)
    return None


def usage(ctx, query):
    """Return (200, {"project", "generated_at", "no_usage", "unreadable", "views", "model_names", "prices"}).

    unreadable is None, or the display path of the folder the reader could not
    use (see _unreadable). The page then says it can't read the transcripts
    there, not that no usage ran. no_usage keeps its meaning, so it is still
    true for a project whose folder failed.

    model_names maps every catalog model id to its display name (the id itself
    when the catalog has no name), so the page can name a model that a view
    does not list, such as the most common model of an agent.

    ?project=<key> picks a listed project, "all" picks every transcript folder,
    and no value means the current project. A key that is not listed gets 404
    and no data. A project with no transcript folder still gets views (all
    zero) and no_usage true, so the payload keeps one shape.
    """
    asked = query.get("project") or []
    if len(asked) > 1:
        return 400, {"error": "bad_request"}
    listing = projects.load(ctx)
    scope = asked[0] if asked else listing.current
    project = None
    if scope != usage_views.ALL:
        project = listing.find(scope)
        if project is None:
            return 404, {"error": "unknown_project"}
    entries = _entries(ctx, listing, project) if project is not None else None
    catalog = ctx.rules["models"]
    tz, _label, fixed = _zone(ctx)
    cache = ctx.usage_cache
    with cache.lock:
        now = _now(ctx, tz)
        result = _read(ctx, cache, now)
        if cache.prices is None:
            cache.prices = price_list.load_prices()
        rows = [{"key": p.key, "name": p.name, "path": p.path} for p in listing.projects]
        folders = transcripts.project_folders(rows, result.records)
        shown = [{"key": r["key"], "name": r["name"], "folder": folders[r["key"]]} for r in rows]
        fingerprint = (
            result.signature,
            result.unreadable,
            result.top_unreadable,
            tuple((r["key"], r["name"], r["folder"]) for r in shown),
            hashlib.sha256(json.dumps(entries, sort_keys=True).encode("utf-8")).hexdigest(),
            now.date().isoformat(),
            str(tz.utcoffset(now)),
        )
        kept = cache.built.get(scope)
        if kept is not None and kept[0] == fingerprint:
            age = (now - kept[2]).total_seconds()
            if 0 <= age < MAX_AGE_SECONDS:
                return 200, kept[1]
        views = usage_views.build_views(
            result.records, scope, now, tz, cache.prices, catalog, result.oldest_by_folder,
            projects=shown, reader_notes=result.notes, tz_fixed=fixed,
            pin_fn=pincheck.checker(entries, catalog) if project is not None else None)
        if project is not None:
            no_usage = folders[project.key] is None
        else:
            no_usage = not result.records
        payload = {
            "project": scope,
            "generated_at": now.isoformat(),
            "no_usage": no_usage,
            "unreadable": _unreadable(ctx, result, project),
            "views": views,
            "model_names": {m["id"]: m.get("display_name") or m["id"] for m in catalog},
            "prices": {"verified_on": cache.prices.get("verified_on"),
                       "source": cache.prices.get("source")},
        }
        cache.built[scope] = (fingerprint, payload, now)
    return 200, payload
