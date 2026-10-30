"""The /api/settings route: the resolved value of every setting, as JSON.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON. Nothing here caches, so each request reads the files again.

Standard library only, Python 3.9. It reads only the folders the Context names
and never looks at os.environ or the home folder.
"""
import collect
import resolve


def settings(ctx, query):
    """Return (200, {"entries": [...]}) for the folders and session in ctx."""
    collected = collect.collect(
        config_dir=ctx.config_dir,
        project_dir=ctx.project_dir,
        managed_dir=ctx.managed_dir,
        shell_env=ctx.shell_env,
        rules=ctx.rules)
    extra = {} if ctx.shell_label is None else {"shell_label": ctx.shell_label}
    inputs = resolve.Inputs(
        collected=collected,
        flags=list(ctx.flags),
        cli_settings=ctx.cli_settings,
        home=ctx.home,
        root=ctx.root,
        **extra)
    return 200, {"entries": resolve.resolve(inputs, ctx.rules, ctx.agent_fields)}
