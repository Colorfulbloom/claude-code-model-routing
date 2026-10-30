"""The /api/settings route: the resolved value of every setting, as JSON.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON. Nothing here caches, so each request reads the files again.

Standard library only, Python 3.9. It reads only the folders the Context names
and never looks at os.environ or the home folder.
"""
import os

import collect
import projects
import resolve


def _display(ctx, path):
    """Return path in the display form an entry uses."""
    return resolve.display_path(path, home=ctx.home, root=ctx.root)


def _models(ctx):
    """Return {id or alias: display name} for the model catalog."""
    out = {}
    for model in ctx.rules.get("models", []):
        out[model["id"]] = model["display_name"]
        for alias in model.get("aliases", []):
            out[alias] = model["display_name"]
    return out


def _display_fields(ctx, project):
    """Return the fields that name the project and the files the page talks about."""
    return {
        "shell_label": resolve.LIVE_SHELL_LABEL if ctx.shell_label is None else ctx.shell_label,
        "path_display": _display(ctx, project.path),
        "config_dir_display": _display(ctx, ctx.config_dir),
        "config_file_display": _display(ctx, os.path.join(ctx.config_dir, projects.CONFIG_FILE)),
        "models": _models(ctx),
    }


def settings(ctx, query):
    """Return (200, {"project", "state", "entries", ...}) for one listed project.

    Besides those three, the answer carries shell_label (the file text of a shell
    value), path_display, config_dir_display and config_file_display, models
    (display names by id and alias) and no_user_settings (true when the config
    folder has no settings.json). A folder that is missing carries the display
    fields and no entries.

    ?project=<key> picks the project and no value means the current one. The
    answer for a key that is not listed, or for "all", carries no settings data.
    """
    asked = query.get("project") or []
    if len(asked) > 1:
        return 400, {"error": "bad_request"}
    listing = projects.load(ctx)
    if asked and asked[0] == projects.ALL_KEY:
        return 400, {"error": "pick_project"}
    project = listing.find(asked[0] if asked else listing.current)
    if project is None:
        return 404, {"error": "unknown_project"}
    if project.state == projects.STATE_MISSING and not project.implicit:
        answer = {"project": project.key, "state": project.state, "entries": []}
        answer.update(_display_fields(ctx, project))
        return 200, answer
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
    answer = {"project": project.key, "state": project.state,
              "entries": resolve.resolve(inputs, ctx.rules, ctx.agent_fields),
              "no_user_settings": not any(
                  record["layer"] == "user" for record in collected["settings_files"])}
    answer.update(_display_fields(ctx, project))
    return 200, answer
