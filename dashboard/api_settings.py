"""The settings routes: /api/settings (the resolved value of every setting),
/api/rules (the rules reference) and /api/files (the installed files), as JSON.

A route is a function (ctx, query) -> (status, payload). ctx is the server's
Context and query is the parsed query string. The server turns the payload into
JSON. Nothing here caches, so each request reads the files again.

Standard library only, Python 3.9. It reads only the folders the Context names
(the config folder, the project, the managed folder and, for /api/files, the
repo folder) and never looks at os.environ or the home folder. It writes
nothing.
"""
import json
import os

import agent_frontmatter
import collect
import projects
import resolve
import version

# #65, /api/files: the installer's own plan. install.py sits at the repo root, and importing collect above
# already put that folder on the path.
import install  # noqa: E402

MAIN_AGENT = "@main"  # the agent key of the main session's rows
REPO_BLOB = "https://github.com/Colorfulbloom/claude-code-model-routing/blob/main/"
REFERENCE_URL = REPO_BLOB + "docs/rules-reference.md"
EXPERIMENT_BASE = REPO_BLOB + "dashboard/"
ATTENTION_ORDER = ("unknown", "lowered", "ignored", "overridden", "invalid")  # the groups of Needs attention


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


def _agent_fields_version():
    """Return the claude_version agent_fields.json was checked on, or None.

    resolve.load_agent_fields keeps only the field names, so the JSON is read
    again here.
    """
    try:
        with open(agent_frontmatter.FIELDS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        text = data["verified_on"]["claude_version"]
    except (OSError, ValueError, RecursionError, KeyError, TypeError):
        return None
    return text if isinstance(text, str) else None


def version_field(ctx):
    """Return {"installed", "rules_oldest"} for the version chip and the due marks.

    installed is the Claude Code version on this machine, or None. rules_oldest
    is the oldest version any rule, or the agent field table, was checked on.
    The field table counts because it decides Ignored for frontmatter and no
    rule reports its age.
    """
    checked = [rule.get("verified_on", {}).get("claude_version") for rule in ctx.rules.get("rules", [])]
    checked.append(_agent_fields_version())
    return {"installed": version.installed(ctx), "rules_oldest": version.oldest(checked)}


def _rule_record(rule, installed):
    """Return the part of one rule the trail shows, with its two page links.

    due is true when the installed version is newer than the one the rule was
    checked on.
    """
    experiment = rule.get("experiment")
    return {
        "rule_id": rule["rule_id"],
        "confidence": rule["confidence"],
        "verified_on": {"claude_version": rule["verified_on"]["claude_version"],
                        "date": rule["verified_on"]["date"]},
        "due": version.older(rule["verified_on"]["claude_version"], installed),
        "quotes": [{"doc_url": quote["doc_url"], "quote": quote["quote"]}
                   for quote in rule.get("quotes", [])],
        "experiment": experiment or None,
        "experiment_url": EXPERIMENT_BASE + experiment if experiment else None,
        "reference_url": REFERENCE_URL + "#" + rule["rule_id"],
    }


def _rules_for(ctx, rows, installed):
    """Return {rule_id: record} for every rule the rows name."""
    known = {rule["rule_id"]: rule for rule in ctx.rules.get("rules", [])}
    out = {}
    for row in rows:
        for rule_id in row["rule_ids"]:
            if rule_id in known and rule_id not in out:
                out[rule_id] = _rule_record(known[rule_id], installed)
    return out


def _equals_winner(entry, winner):
    """Return True when an overridden entry holds the same value as the winner.

    Hidden values cannot be compared and a null value says nothing, so those
    are never equal.
    """
    value = entry["value"]
    return (entry["status"] == "overridden" and value is not None
            and value != collect.HIDDEN and value == winner)


def _attention_walk(entries, rows):
    """Return (groups, equal): the attention rows by status and how many were left out.

    Resolver rows and their entries are walked in order. equal counts the
    overridden entries left out because they equal the winner's value (the
    row's first entry), because nothing was lost.
    """
    groups = {status: [] for status in ATTENTION_ORDER}
    equal = 0
    for row in rows:
        winner = entries[row["entries"][0]]["value"]
        for index in row["entries"]:
            entry = entries[index]
            status = entry["status"]
            if status not in groups:
                continue
            if _equals_winner(entry, winner):
                equal += 1
                continue
            groups[status].append({"entry": index,
                                   "route": {"agent": row["agent"], "setting": row["setting"]}})
    return groups, equal


def _attention(entries, rows):
    """Return the groups of Needs attention, in the order of ATTENTION_ORDER.

    A group is {"status", "rows"} and is left out when it has no rows. A row is
    {"entry": index into entries, "route": {"agent", "setting"}}, the route the
    page hands to the trail link. Resolver rows and their entries are walked in
    order, so a row of several entries gives several attention rows.

    An overridden entry is left out when its value equals the winner's (the
    row's first entry), because nothing was lost. Hidden values cannot be
    compared and a null value says nothing, so those stay.
    """
    groups, _equal = _attention_walk(entries, rows)
    return [{"status": status, "rows": groups[status]} for status in ATTENTION_ORDER if groups[status]]


def _attention_equal(entries, rows):
    """Return how many overridden entries _attention leaves out because they equal the winner."""
    return _attention_walk(entries, rows)[1]


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

    installed is the Claude Code version on this machine, or null. Each rule
    record carries due, true when that version is newer than the one the rule
    was checked on. attention holds the groups of the Needs attention page, each
    with its rows (an entry index and the trail route), and is empty for a
    folder that is missing. attention_equal counts the overridden entries left
    out of attention because they equal the winner (0 for a missing folder).

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
                  "rows": [], "rules": {}, "files": [], "installed": version.installed(ctx),
                  "attention": [], "attention_equal": 0}
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
    installed = version.installed(ctx)
    answer = {"project": project.key, "state": project.state, "entries": entries,
              "no_user_settings": not any(
                  record["layer"] == "user" for record in collected["settings_files"]),
              "rows": rows, "rules": _rules_for(ctx, rows, installed),
              "files": _files(ctx, collected, entries), "installed": installed,
              "attention": _attention(entries, rows),
              "attention_equal": _attention_equal(entries, rows)}
    answer.update(_display_fields(ctx, project))
    return 200, answer


# ---------------------------------------------------------------- #64 /api/rules

def rules(ctx, query):
    """Return (200, {"installed", "rules"}) for the Rules reference page.

    rules holds every rule of ctx.rules, sorted by rule_id. Each is the record
    the trail shows (see _rule_record) plus "reason", the rule's own sentence
    with its slots still in braces, which the page words. installed is the
    Claude Code version on this machine, or null.
    """
    installed = version.installed(ctx)
    out = []
    for rule in sorted(ctx.rules.get("rules", []), key=lambda r: r["rule_id"]):
        record = _rule_record(rule, installed)
        record["reason"] = rule["reason"]
        out.append(record)
    return 200, {"installed": installed, "rules": out}


# ---------------------------------------------------------------- #65 /api/files

FILE_MATCH = "match"
FILE_DIFFERS = "differs"
FILE_MISSING = "missing"


def _file_state(path, data):
    """Return how the file at path compares with data: match, differs or missing.

    The file is opened for reading in binary and read up to len(data) + 1 bytes,
    so a longer file differs without being read whole. A file or a folder that
    is not there, including a link that points nowhere, is missing. Any other
    failure to read, or other bytes, is differs.
    """
    try:
        with open(path, "rb") as fh:
            found = fh.read(len(data) + 1)
    except (FileNotFoundError, NotADirectoryError):
        return FILE_MISSING
    except OSError:
        return FILE_DIFFERS
    return FILE_MATCH if found == data else FILE_DIFFERS


def files(ctx, query):
    """Return (200, {"files": [...]}) for the Installed files page.

    The installer's plan is built in memory from the repo folder (ctx.repo_dir)
    and the choices saved in the config folder, the way install.py builds it. For
    each entry, in plan order, the file is {"path", "state"}. path is the config
    folder's file in the display form of an entry. state is "match" when the
    installed file holds exactly the bytes the plan would write, "differs" when
    it holds other bytes or cannot be read, and "missing" when it is not there.
    File modes are not compared.

    model-routing-manifest.txt and the hook entries in settings.json are not in
    the plan, so they do not show. A repo the installer cannot plan, or a repo
    file it cannot read, gives (500, {"error": "installer"}). Nothing is
    written.

    The answer also carries choices, {"status", "bad", "path"}. status is the
    saved choices file's status from install.load_choices (ok, missing or bad),
    bad lists the agents with no usable saved choice and path is the file in
    display form. A file gets "caution": true, only when the installer would
    not keep what is installed. That holds for an agents/<name>.md file in the
    state differs when name is affected (every agent when status is not ok,
    else the names in bad), and for the choices file in the state differs or
    missing when status is not ok or bad is not empty. Otherwise the key is
    left out.
    """
    choices_path = os.path.join(ctx.config_dir, install.CHOICES_NAME)
    try:
        agents = install.list_agents(ctx.repo_dir)
        defaults = install.load_agent_defaults(ctx.repo_dir, agents)
        choices, status, bad = install.load_choices(choices_path, agents, defaults)
        plan = install.build_plan(ctx.repo_dir, choices)
    except (OSError, install.InstallError, install.MissingFieldsError):
        return 500, {"error": "installer"}
    affected = set(agents) if status != "ok" else set(bad)
    unsure = status != "ok" or bool(bad)
    out = []
    for entry in plan:
        path = os.path.join(ctx.config_dir, *entry.rel.split("/"))
        state = _file_state(path, entry.data)
        item = {"path": _display(ctx, path), "state": state}
        if state == FILE_DIFFERS and entry.rel.startswith("agents/") and entry.rel.endswith(".md"):
            if entry.rel[len("agents/"):-len(".md")] in affected:
                item["caution"] = True
        elif entry.rel == install.CHOICES_NAME and state in (FILE_DIFFERS, FILE_MISSING) and unsure:
            item["caution"] = True
        out.append(item)
    return 200, {"files": out,
                 "choices": {"status": status, "bad": list(bad), "path": _display(ctx, choices_path)}}
