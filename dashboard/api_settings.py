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

MAIN_AGENT = "@main"  # the agent key of the main session's rows
REPO_BLOB = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/"
REFERENCE_URL = REPO_BLOB + "docs/rules-reference.md"
EXPERIMENT_BASE = REPO_BLOB + "dashboard/"


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


def _rows(entries):
    """Return one item per row of entries, in entry order.

    A row is the agent ("@main" for the main session) and the setting key. Its
    "entries" are indexes into the entry list, in entry order, so the first is the
    winner. "rule_ids" joins the rule_ids of those entries, first seen first.
    """
    rows = {}
    for index, entry in enumerate(entries):
        agent = entry.get("agent") or MAIN_AGENT
        row = rows.get((agent, entry["key"]))
        if row is None:
            row = {"agent": agent, "setting": entry["key"], "scope": entry["scope"],
                   "entries": [], "rule_ids": []}
            rows[(agent, entry["key"])] = row
        row["entries"].append(index)
        for rule_id in entry.get("rule_ids") or []:
            if rule_id not in row["rule_ids"]:
                row["rule_ids"].append(rule_id)
    return list(rows.values())


def _rule_record(rule):
    """Return the part of one rule the trail shows, with its two page links."""
    experiment = rule.get("experiment")
    return {
        "rule_id": rule["rule_id"],
        "confidence": rule["confidence"],
        "verified_on": {"claude_version": rule["verified_on"]["claude_version"],
                        "date": rule["verified_on"]["date"]},
        "quotes": [{"doc_url": quote["doc_url"], "quote": quote["quote"]}
                   for quote in rule.get("quotes", [])],
        "experiment": experiment or None,
        "experiment_url": EXPERIMENT_BASE + experiment if experiment else None,
        "reference_url": REFERENCE_URL + "#" + rule["rule_id"],
    }


def _rules_for(ctx, rows):
    """Return {rule_id: record} for every rule the rows name."""
    known = {rule["rule_id"]: rule for rule in ctx.rules.get("rules", [])}
    out = {}
    for row in rows:
        for rule_id in row["rule_ids"]:
            if rule_id in known and rule_id not in out:
                out[rule_id] = _rule_record(known[rule_id])
    return out


def _files(ctx, collected, entries):
    """Return the settings files that exist, each with its layer, display path and status.

    A file that did not parse or read also carries entry_status, the status of its
    settingsFile entry, when the resolver made one.
    """
    problems = {(entry["layer"], entry["file"]): entry["status"]
                for entry in entries if entry["key"] == "settingsFile"}
    out = []
    for record in collected["settings_files"]:
        item = {"layer": record["layer"], "path": _display(ctx, record["path"]), "status": record["status"]}
        status = problems.get((item["layer"], item["path"]))
        if status is not None:
            item["entry_status"] = status
        out.append(item)
    return out


def settings(ctx, query):
    """Return (200, {"project", "state", "entries", ...}) for one listed project.

    Besides those three, the answer carries shell_label (the file text of a shell
    value), path_display, config_dir_display and config_file_display, models
    (display names by id and alias) and no_user_settings (true when the config
    folder has no settings.json). A folder that is missing carries the display
    fields and no entries.

    The trail reads three more fields. rows has one item per resolver row, with
    the indexes of its entries (the first is the winner) and the rule ids they
    name. rules holds those rules by id, with their confidence, the version they
    were checked on, their doc quotes, their experiment and their links on the
    rules reference page. files lists the settings files that exist, with their
    status.

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
        answer = {"project": project.key, "state": project.state, "entries": [],
                  "rows": [], "rules": {}, "files": []}
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
    entries = resolve.resolve(inputs, ctx.rules, ctx.agent_fields)
    rows = _rows(entries)
    answer = {"project": project.key, "state": project.state, "entries": entries,
              "no_user_settings": not any(
                  record["layer"] == "user" for record in collected["settings_files"]),
              "rows": rows, "rules": _rules_for(ctx, rows),
              "files": _files(ctx, collected, entries)}
    answer.update(_display_fields(ctx, project))
    return 200, answer
