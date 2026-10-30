"""The /api/settings route: the resolved value of every setting, as JSON.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON. Nothing here caches, so each request reads the files again.

Standard library only, Python 3.9. It reads only the folders the Context names
and never looks at os.environ or the home folder.
"""
import collect
import projects
import resolve


def settings(ctx, query):
    """Return (200, {"project", "state", "entries"}) for one listed project.

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
        return 200, {"project": project.key, "state": project.state, "entries": []}
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
    return 200, {"project": project.key, "state": project.state,
                 "entries": resolve.resolve(inputs, ctx.rules, ctx.agent_fields)}
