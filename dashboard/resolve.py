#!/usr/bin/env python3
"""The dashboard's first resolver. Standard library only.

It works out, for every setting the dashboard shows, which candidate value
wins and why, using only the rules in dashboard/rules.json. The rules hold
every precedence and validity decision. This module holds the plumbing: it
takes what the collectors found, lines the candidates up, asks the rules for a
vote on each one and combines the votes.

    /usr/bin/python3 dashboard/resolve.py [fixtures_dir]

runs every fixture folder in fixtures_dir (default tests/fixtures/resolution),
prints "<name>: ok" or the mismatches, and exits 1 when any fixture fails.

Public functions:

    resolve(inputs, rules, agent_fields) -> list of entry dicts
    load_rules(path=RULES_PATH) -> the rules.json document
    load_agent_fields(path) -> the field names Claude Code reads in frontmatter
    load_fixture(folder, rules=None) -> (Inputs, expected)
    display_path(path, home=None, root=None) -> the text an entry shows for a path
    compare(entries, expected) -> list of mismatch messages

resolve is a pure function of its inputs. It opens no file, lists no folder,
writes nothing, uses no network and never looks up the home folder. The caller
loads the rules and the agent field list (dashboard/agent_fields.json) and
passes both in.

Where values come from. dashboard/collect.py reads the files and returns one
dict, Inputs.collected, and resolve works only from that:

    settings        the sources that parsed, highest first (merged managed,
                    local, project, user). Each holds the masked data and a
                    "where" map from a key path, such as ("env", "FOO"), to the
                    file and line the value came from.
    settings_files  every settings file that exists, with its status (ok,
                    unparsed or unreadable) and the line of a parse problem.
    env             each variable that rules.json names or an env block sets,
                    with its settings records and its shell record.
    agents          each agent file, with its masked frontmatter fields, the
                    reader's errors and the line of every field.
    rules_files     every file under the two rules folders.

Three inputs exist only in fixtures, because the dashboard cannot see them in
live use: flags (the session flags, as a list of words), cli_settings (the
content of a --settings file) and shell_label. In live use flags is empty,
cli_settings is None and no entry has the layer flag or cli. The other inputs:

    plan         subscription, api_key or cloud_provider, or None when unset
    home         the home folder the caller looked up. resolve never does.
    root         fixtures only: paths display relative to this folder
    shell_label  what an entry names as the file of a shell value. The default
                 is "Shell". Fixtures use "session.json:shell_env".

Where a candidate comes from (the `file` field of an entry):

    user      the settings.json in the config folder
    project   .claude/settings.json in the project
    local     .claude/settings.local.json in the project
    managed   the managed file that holds the key, managed-settings.json or a
              file in managed-settings.d
    cli       session.json:cli_settings (fixtures only)
    flag      session.json:flags (fixtures only)
    env       the shell (inputs.shell_label), or the settings file whose env
              block set the variable. The layer is still env for a row such as
              effortLevel, because the process environment is one layer.
    default   no file (null)
    agent     the agent file, in the user or project agents folder

How a path shows (display_path, pure string work with no file system calls). A
path inside root shows relative to it, with "/" separators. Otherwise a path
inside home shows as "~/" and the rest. Anything else shows in full. Every
file and other_file in an entry, and so every reason, uses this one text.

Lines. An entry whose value came from a real file carries "line", an integer:
the line of the key in a settings file, of the variable in an env block, of the
field in agent frontmatter, of the name in an agent file that loads, of the
reader's first error in a file it rejected, and 1 for a file with no better
line (a rules file, a file that is not .md). A shell value has no line and a
default has no file and no line. Fixture-only sources carry no line.

Order of work:

    1. Settings files. A file whose status is not ok becomes a candidate of the
       settingsFile row. The rules decide whether it is ignored or unknown.
    2. Env blocks. The process environment is the shell overwritten by the
       settings env blocks (rule env-block-order). Every variable set anywhere
       gets a row env.<VAR>.
    3. Agent files. Each file gets one case (not_md_file, parse_error, ...) and
       the agentFile row of its agent name.
    4. Main rows: model, maxEffortLevel, effortLevel, autoCompactWindow,
       promptCacheTtl, rulesFile. effortLevel needs the main model and the cap.
    5. Agent rows, for each agent that loads: model, effort, autoCompactWindow,
       subagentPromptCacheTtl. They need the main model and the agent's own.

Each row gathers its candidates, each candidate collects the votes of the rules
for its key and scope, and the row's combine rule picks the winner. See
resolve_row.

Why an entry says what it says (rule_id, rule_ids, reason):

    A winner is explained by the rule that voted its status, the most specific
    voter first (a condition with becomes, via, if_set, range, when or
    name_form). A value that lost is explained by the row's order rule, the
    rule that supplies the row's layer order and combine. Every default has a
    rule too, and an unknown model has its own default rules (when:
    model_unknown). A reason shows a model by its display name from the
    catalog, such as Opus 5.5, while the entry's model field keeps the id.

Unknown rows. Two kinds of file can hide a value from the dashboard, and both
work the same way. An agent whose frontmatter the reader rejected has no
readable model, effort, window or cache value, so the winner of those rows is
Unknown with the agent file's rule and reason when the agent layer ranks above
it. A settings file that is unreadable, or a managed file that is not JSON,
makes the settingsFile row Unknown, and the winner of every row such a file can
feed becomes Unknown with that row's rule and reason (see
_mark_unreadable_files). The status and the reason always come from rules.json.
"""
import dataclasses
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import agent_frontmatter  # noqa: E402
import collect  # noqa: E402
import rules_schema  # noqa: E402

RULES_PATH = rules_schema.RULES_PATH
REPO = os.path.dirname(HERE)
FIXTURES_PATH = os.path.join(REPO, "tests", "fixtures", "resolution")

# Where an entry says a value came from when it did not come from a file.
LABEL_SHELL = "session.json:shell_env"
LABEL_FLAGS = "session.json:flags"
LABEL_CLI = "session.json:cli_settings"

# What a live entry names as the file of a shell value.
LIVE_SHELL_LABEL = "Shell"

# Session flags and the rows they feed: flag -> [(row key, scope)].
FLAGS = {
    "--model": [("model", "main")],
    "--effort": [("effortLevel", "main"), ("effort", "agent")],
    "--autocompact": [("autoCompactWindow", "main"), ("autoCompactWindow", "agent")],
}

# The settings key that feeds each row: (scope, row key) -> settings key.
SETTINGS_KEYS = {
    ("main", "model"): "model",
    ("main", "maxEffortLevel"): "maxEffortLevel",
    ("main", "effortLevel"): "effortLevel",
    ("main", "autoCompactWindow"): "autoCompactWindow",
    ("main", "promptCacheTtl"): "promptCacheTtl",
    ("agent", "effort"): "effortLevel",
    ("agent", "autoCompactWindow"): "autoCompactWindow",
    ("agent", "subagentPromptCacheTtl"): "subagentPromptCacheTtl",
}

# The field of a modelSettings entry that feeds each row.
MODEL_SETTINGS_FIELDS = {
    "maxEffortLevel": "maxEffortLevel",
    "effortLevel": "effortLevel",
    "effort": "effortLevel",
    "autoCompactWindow": "autoCompactWindow",
}

# The frontmatter path that feeds each agent row.
FRONTMATTER_KEYS = {
    "model": ("model",),
    "effort": ("effort",),
    "autoCompactWindow": ("autoCompactWindow",),
    "subagentPromptCacheTtl": ("experimental", "cacheTtl"),
}

# Rows that carry a model: the rule conditions' `models` are matched against it.
MODEL_ROWS = ("maxEffortLevel", "effortLevel", "effort", "autoCompactWindow")
EFFORT_ROWS = ("effortLevel", "effort")

# Rows that list files. A file that does not load leaves them empty, and an
# empty row has no default entry.
FILE_ROWS = ("agentFile", "rulesFile", "settingsFile")

# Frontmatter reader errors and the file case each one means. Experiment record
# dashboard/experiments/2026-10-29-agent-files.json#f2 loaded these files:
# an unclosed [, a second colon in a value and a repeated key, so the strict
# reader rejects frontmatter that Claude Code accepts. The same record did not
# load a tab in an indent, an unterminated quote or a bad list indent. The
# kind strings are the ones agent_frontmatter.read_frontmatter returns.
PARSE_ERROR_KINDS = {
    "tab in an indent",
    "unclosed quote",
    "inconsistent indent",
    "unexpected indent",
    # Record #f1 (file nofence.md): a file with no closing --- did not load.
    # Added beside the three f2 kinds, because #f1 shows it directly.
    "missing closing fence",
}
LOADS_ANYWAY_KINDS = {"unclosed bracket", "unquoted colon in a value", "duplicate key"}

# Agent files whose frontmatter the reader rejected and Claude Code may still
# load. The rows that frontmatter feeds are unknown while one of these loads.
UNREADABLE_CASES = ("reader_rejected_but_loads", "reader_rejected_untested")
UNREADABLE_ROWS = ("model", "effort", "autoCompactWindow", "subagentPromptCacheTtl")

# The file cases that come from the reader's errors.
READER_CASES = ("parse_error",) + UNREADABLE_CASES

# What a vote means for the candidate that wins, strongest first.
WINNER_PRECEDENCE = ("unknown", "lowered", "default", "in_effect")
EXCLUDING = ("invalid", "ignored")


@dataclasses.dataclass(frozen=True)
class Inputs:
    """What resolve works from. See the module docstring for each field."""

    collected: dict
    flags: list = dataclasses.field(default_factory=list)
    cli_settings: object = None
    plan: object = None
    home: object = None
    root: object = None
    shell_label: str = LIVE_SHELL_LABEL


# --------------------------------------------------------------------------
# Loading

def load_rules(path=RULES_PATH):
    """Return the rules.json document. It does not validate; rules_schema does."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_json(path):
    """Return the object in a JSON file, or None when it is missing or not an object."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_agent_fields(path=agent_frontmatter.FIELDS_PATH):
    """Return the field names Claude Code reads in agent frontmatter."""
    data = _read_json(path) or {}
    return [item["field"] for item in data.get("fields", []) if isinstance(item, dict)]


def load_fixture(folder, rules=None):
    """Return (Inputs, expected) for one fixture folder.

    The folder's files go through the collectors first, as they do in live use.
    Its managed/ folder stands in for the managed settings folder, and
    session.json:shell_env for the shell, so a fixture never reads the real
    ones. Flags and --settings content come from session.json. The --settings
    content is masked here, as live use masks it, so a fixture secret never
    reaches an entry.
    """
    folder = os.path.abspath(folder)
    rules = rules if rules is not None else load_rules()
    session = _read_json(os.path.join(folder, "session.json")) or {}
    dashboard = _read_json(os.path.join(folder, "dashboard.json")) or {}
    collected = collect.collect(
        config_dir=os.path.join(folder, "config"),
        project_dir=os.path.join(folder, "project"),
        managed_dir=os.path.join(folder, "managed"),
        shell_env=dict(session.get("shell_env") or {}),
        rules=rules)
    inputs = Inputs(
        collected=collected,
        flags=list(session.get("flags") or []),
        cli_settings=collect.mask(session.get("cli_settings")),
        plan=dashboard.get("plan"),
        home=None,
        root=folder,
        shell_label=LABEL_SHELL,
    )
    with open(os.path.join(folder, "expected.json"), encoding="utf-8") as fh:
        expected = json.load(fh)
    return inputs, expected


# --------------------------------------------------------------------------
# Model names

def normalize_model(name, catalog):
    """Return (catalog id, name form) for a model name, or (None, None).

    Forms, in the order of rules_schema.NAME_FORMS: canonical (the catalog id),
    alias, dated (<id>-YYYYMMDD), context_1m (<id>[1m]) and provider
    (<region>.anthropic.<id>-v<n>:<n> or <id>@<date>).
    """
    if not isinstance(name, str) or name == "":
        return None, None
    ids = {m["id"] for m in catalog}
    if name in ids:
        return name, "canonical"
    for model in catalog:
        if name in model.get("aliases", []):
            return model["id"], "alias"
    patterns = (
        (r"^(.+)\[1m\]$", "context_1m"),
        (r"^(.+)-\d{8}$", "dated"),
        (r"^(?:[a-z0-9-]+\.)?anthropic\.(.+)-v\d+:\d+$", "provider"),
        (r"^(.+)@\d{8}$", "provider"),
    )
    for pattern, form in patterns:
        match = re.match(pattern, name)
        if match and match.group(1) in ids:
            return match.group(1), form
    return None, None


def read_number(value):
    """Read a value as an integer the way a range condition does, or None.

    A JSON integer counts. A string counts through its leading decimal digits,
    so "200k" reads as 200. Booleans, "abc" and "" do not read as a number.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        match = re.match(r"^[0-9]+", value)
        if match:
            return int(match.group(0))
    return None


# --------------------------------------------------------------------------
# Sources

def _below(path, base):
    """Return the part of path under base ("" for base itself), or None.

    Pure string work. The boundary is a whole folder name, so "/x/a" does not
    hold "/x/ab".
    """
    if not isinstance(path, str) or not isinstance(base, str):
        return None
    base = base.rstrip(os.sep)
    if base == "":
        return None
    if path == base:
        return ""
    if path.startswith(base + os.sep):
        return path[len(base) + 1:]
    return None


def display_path(path, home=None, root=None):
    """Return the text an entry shows for a file path.

    A path inside root shows relative to it, with "/" separators. Else a path
    inside home shows as "~/" and the rest. Else it shows in full. It calls no
    file system function and never looks the home folder up.
    """
    rest = _below(path, root)
    if rest is not None:
        return rest.replace(os.sep, "/") if rest else "."
    rest = _below(path, home)
    if rest is not None:
        return "~/" + rest if rest else "~"
    return path


def parse_flags(flags):
    """Return {flag: value} for the flags in FLAGS. The last use of a flag wins."""
    out = {}
    words = [w for w in (flags or []) if isinstance(w, str)]
    for i, word in enumerate(words):
        name, sep, inline = word.partition("=")
        if name not in FLAGS:
            continue
        if sep:
            out[name] = inline
        elif i + 1 < len(words):
            out[name] = words[i + 1]
    return out


def _frontmatter_kinds(errors):
    kinds = []
    for error in errors:
        kind = error.split(": ", 1)[1] if ": " in error else error
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def _reader_case(kinds):
    """Map the reader's error kinds to a file case."""
    if any(k in PARSE_ERROR_KINDS for k in kinds):
        return "parse_error"
    if all(k in LOADS_ANYWAY_KINDS for k in kinds):
        return "reader_rejected_but_loads"
    return "reader_rejected_untested"


def _stem(path):
    return os.path.basename(path).split(".")[0]


def _first_error_line(errors):
    """Return the line the reader's first error names, or 1."""
    match = re.match(r"line (\d+)", errors[0]) if errors else None
    return int(match.group(1)) if match else 1


def read_agent_files(inputs):
    """Return one dict per agent file: layer, file, name, case, fields, loadable.

    The files come from inputs.collected["agents"]. Cases are decided per file
    in this order: not_md_file, the reader's errors, no_name, no_description,
    then same_name_in_layer across the files of one layer. other_file is set on
    a same_name_in_layer file. `line` is the line the file's entry shows: the
    name line when the file loads, the reader's first error when the reader
    rejected the file, else 1. `lines` maps a frontmatter path to its line.
    """
    files = []
    for rec in inputs.collected.get("agents", []):
        path = rec["path"]
        fields = rec["fields"]
        errors = rec["errors"]
        kinds = _frontmatter_kinds(errors)
        name = fields.get("name") if not errors else None
        readable = isinstance(name, str) and name.strip() != ""
        case = None
        if not os.path.basename(path).endswith(".md"):
            case = "not_md_file"
        elif errors:
            case = _reader_case(kinds)
        elif not readable:
            case = "no_name"
        elif not (isinstance(fields.get("description"), str)
                  and fields["description"].strip() != ""):
            case = "no_description"
        files.append({
            "layer": rec["layer"],
            "path": path,
            "file": display_path(path, inputs.home, inputs.root),
            "name": name.strip() if readable else _stem(path),
            "case": case,
            "fields": fields if not errors else {},
            "lines": rec.get("lines") or {},
            "line": _first_error_line(errors) if case in READER_CASES else 1,
            "loadable": False,
            "other_file": None,
        })
    for layer in ("project", "user"):
        groups = {}
        for f in files:
            if f["layer"] == layer and f["case"] is None:
                groups.setdefault(f["name"], []).append(f)
        for group in groups.values():
            if len(group) > 1:
                for i, f in enumerate(group):
                    f["case"] = "same_name_in_layer"
                    f["other_file"] = group[(i + 1) % len(group)]["file"]
    for f in files:
        f["loadable"] = f["case"] in (None, "same_name_in_layer")
        if f["loadable"]:
            f["line"] = f["lines"].get("name", 1)
    return files


# --------------------------------------------------------------------------
# The resolver context

class _Context:
    """Everything a row needs: the rules, the sources and the answers so far."""

    def __init__(self, inputs, rules, agent_fields):
        self.inputs = inputs
        self.rules = rules["rules"]
        self.catalog = rules["models"]
        self.catalog_ids = [m["id"] for m in self.catalog]
        self.models = {m["id"]: m for m in self.catalog}
        self.variables = list(rules.get("variables", []))
        self.agent_fields = set(agent_fields)
        self.plan = inputs.plan or "unset"
        self.collected = inputs.collected
        self.settings = self._sources()
        self.flags = parse_flags(inputs.flags)
        self.agent_files = read_agent_files(inputs)
        self.env = {}  # name -> {"value", "file", "line", "status"} of the env.<name> winner
        self.unknown_files = []  # settingsFile entries whose status is unknown
        self.main_model = None  # catalog id
        self.main_model_value = None
        self._caps = {}
        self._covers = {}

    def show(self, path):
        """The text an entry shows for a file path."""
        return display_path(path, self.inputs.home, self.inputs.root)

    def _sources(self):
        """The settings sources, highest first, with the --settings content added.

        Each is {"layer", "data", "where", "label"}. `label` names the file of
        a value that has no entry in `where`.
        """
        found = [dict(src, label=src["layer"]) for src in self.collected.get("settings", [])]
        cli = self.inputs.cli_settings
        if isinstance(cli, dict):
            at = sum(1 for src in found if src["layer"] == "managed")
            found.insert(at, {"layer": "cli", "data": cli, "where": {}, "label": LABEL_CLI})
        return found

    def spot(self, src, path):
        """Return (file, line) for the key `path` (a tuple) of a settings source."""
        where = src["where"].get(path)
        if where is None:
            return src["label"], None
        return self.show(where["path"]), where["line"]

    def rules_for(self, scope, key):
        return [r for r in self.rules if r["scope"] == scope and r["key"] == key]

    def covers(self, models):
        key = json.dumps(models, sort_keys=True)
        if key not in self._covers:
            self._covers[key] = rules_schema.expand_models(models, self.catalog_ids)
        return self._covers[key]

    def env_is_set(self, name):
        return name in self.env and self.env[name]["value"] != ""


def _rule_key(key):
    return "env" if key.startswith("env.") else key


def _is_variable_rule(rule):
    """A rule whose every condition names a variable (via or if_set)."""
    return all("via" in c or "if_set" in c for c in rule["conditions"])


def _is_subsequence(small, big):
    it = iter(big)
    return all(item in it for item in small)


# --------------------------------------------------------------------------
# Candidates

def _candidate(layer, file, value, line=None, **extra):
    cand = {"layer": layer, "file": file, "value": value, "line": line, "rank": (1, 0, 0)}
    cand.update(extra)
    return cand


def _show_value(row, value):
    """Digits-only strings on an autoCompactWindow row show as integers."""
    if row["key"] == "autoCompactWindow" and isinstance(value, str) and value.isdigit() \
            and value.isascii():
        return int(value)
    return value


def _dig(data, path):
    for part in path:
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def settings_candidates(ctx, row):
    """Candidates from the settings files, flags and modelSettings for one row."""
    out = []
    skey = SETTINGS_KEYS.get((row["scope"], row["key"]))
    field = MODEL_SETTINGS_FIELDS.get(row["key"])
    for src in ctx.settings:
        if skey is not None and src["data"].get(skey) is not None:
            file, line = ctx.spot(src, (skey,))
            out.append(_candidate(src["layer"], file, _show_value(row, src["data"][skey]),
                                  line))
        table = src["data"].get("modelSettings")
        if field is not None and row.get("model") and isinstance(table, dict):
            for name, entry in table.items():
                model_id, form = normalize_model(name, ctx.catalog)
                if model_id != row["model"] or not isinstance(entry, dict) \
                        or entry.get(field) is None:
                    continue
                rule_key = "modelSettings" if field == "effortLevel" else "modelSettings." + field
                file, line = ctx.spot(src, ("modelSettings", name, field))
                out.append(_candidate(
                    src["layer"], file, _show_value(row, entry[field]), line,
                    path="modelSettings.%s.%s" % (name, field),
                    name_form=form, model=model_id, rule_key=rule_key, rule_scope="model",
                    rank=(0, rules_schema.NAME_FORMS.index(form), 0)))
    for flag, rows in FLAGS.items():
        if flag in ctx.flags and (row["key"], row["scope"]) in rows:
            out.append(_candidate("flag", LABEL_FLAGS, _show_value(row, ctx.flags[flag]),
                                  flag=flag))
    return out


def variable_candidates(ctx, row):
    """One candidate for each variable in the rules' variables list that is set."""
    out = []
    for index, var in enumerate(ctx.variables):
        for vrow in var["rows"]:
            if vrow["key"] != row["key"] or vrow["scope"] != row["scope"]:
                continue
            name = var["name"]
            if var["value"] is None:
                if name not in ctx.env:
                    continue
                value = ctx.env[name]["value"]
            else:
                if not ctx.env_is_set(name):
                    continue
                value = var["value"]
            layer = vrow["layer"]
            file = line = None
            if layer == "env":
                file, line = ctx.env[name]["file"], ctx.env[name]["line"]
            out.append(_candidate(layer, file, _show_value(row, value), line, via=name,
                                  rank=(2, 0, index)))
    return out


def frontmatter_candidates(ctx, row, files):
    """Candidates from the frontmatter of the agent files that load for this agent."""
    path = FRONTMATTER_KEYS.get(row["key"])
    if path is None:
        return []
    out = []
    for f in files:
        value = _dig(f["fields"], path)
        if not isinstance(value, str) or value == "":
            continue
        cand = _candidate("agent", f["file"], _show_value(row, value),
                          f["lines"].get(".".join(path)),
                          ambiguous=f["case"] == "same_name_in_layer")
        if row["key"] == "model" and value == "inherit":
            cand["raw"] = "inherit"
            cand["value"] = ctx.main_model_value
        out.append(cand)
    return out


# --------------------------------------------------------------------------
# Votes

def _candidate_text(cand):
    """What a candidate shows when a reason names it as the winner."""
    if cand.get("via"):
        return cand["via"]
    if cand.get("flag"):
        return cand["flag"]
    if cand["layer"] == "default" and not cand.get("file"):
        return "Claude Code's default"
    return cand.get("file") or cand["layer"]


def _match_value(cand):
    """The value a condition's `values` list is compared with, as a string."""
    value = cand.get("raw", cand["value"])
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def _effort_cap(ctx, model_id):
    """Return the maxEffortLevel in effect for a model, or None."""
    if model_id not in ctx._caps:
        row = {"key": "maxEffortLevel", "scope": "main", "agent": None, "model": model_id}
        entries = resolve_row(ctx, row, settings_candidates(ctx, row))
        winner = _winner(entries)
        ctx._caps[model_id] = winner["value"] if winner and winner["status"] == "in_effect" \
            else None
    return ctx._caps[model_id]


def _computed_becomes(ctx, row, cand, kind):
    """Return what a computed `becomes` works out for a candidate, or None."""
    levels = rules_schema.EFFORT_LEVELS
    value = cand["value"]
    if not isinstance(value, str) or value not in levels:
        return None
    model = ctx.models.get(row.get("model"))
    if model is None:
        return None
    if kind == "cap":
        cap = _effort_cap(ctx, row["model"])
        if cap in levels and levels.index(value) > levels.index(cap):
            return cap
        return None
    offered = model["effort_levels"]
    if not offered or value in offered:
        return None
    below = [lv for lv in offered if levels.index(lv) <= levels.index(value)]
    return below[-1] if below else None


def _model_unknown(ctx, row):
    """True when the model a row's default depends on is unknown.

    A row that carries a model (MODEL_ROWS) depends on that model. The agent
    model row depends on the main session's model, which is what an agent runs
    on when nothing else sets one.
    """
    if row["key"] in MODEL_ROWS:
        return row.get("model") is None
    if row["scope"] == "agent" and row["key"] == "model":
        return ctx.main_model_value is None
    return False


def _condition_matches(ctx, row, cand, cond):
    if cond["layer"] != cand["layer"]:
        return False
    if cond["layer"] == "default" and cond["status"] in ("default", "unknown") \
            and not cand.get("synth"):
        # These describe the fallback when nothing is set, so only the
        # synthesized default candidate takes them. A default-layer candidate
        # from a variable (ENABLE_PROMPT_CACHING_1H) is a real value.
        return False
    covered = ctx.covers(cond["models"])
    if rules_schema.ANY_MODEL not in covered and row.get("model") not in covered:
        return False
    if "values" in cond and _match_value(cand) not in cond["values"]:
        return False
    if "plans" in cond and ctx.plan not in cond["plans"]:
        return False
    if cond.get("when") == "model_unknown":
        if cond["layer"] == "default" and not cand.get("synth"):
            return False
        if not _model_unknown(ctx, row):
            return False
    elif "when" in cond and cand.get("case") != cond["when"]:
        return False
    if "via" in cond and cand.get("via") != cond["via"]:
        return False
    if "if_set" in cond and not all(ctx.env_is_set(n) for n in cond["if_set"]):
        return False
    if "range" in cond:
        number = read_number(cand["value"])
        low = cond["range"].get("min")
        high = cond["range"].get("max")
        if number is None or (low is not None and number < low) \
                or (high is not None and number > high):
            return False
    if "name_form" in cond and cand.get("name_form") != cond["name_form"]:
        return False
    becomes = cond.get("becomes")
    if isinstance(becomes, dict) and _computed_becomes(
            ctx, row, cand, becomes["computed"]) is None:
        return False
    return True


def _drop_shadowed(votes):
    """Drop a vote that another vote on the same candidate makes redundant.

    Two conditions on one layer with one status, where the second names every
    variable of the first in `if_set` and more, are one answer. The one that
    names more variables is the precise one, so it stays. A condition with a
    `becomes` or a `default_value` always stays, because it carries a value.
    """
    kept = []
    for rule, cond in votes:
        mine = set(cond.get("if_set", []))
        shadowed = "becomes" not in cond and "default_value" not in cond and any(
            other is not cond and other["layer"] == cond["layer"]
            and other["status"] == cond["status"]
            and set(other.get("if_set", [])) > mine
            for _r, other in votes)
        if not shadowed:
            kept.append((rule, cond))
    return kept


def votes_for(ctx, row, cand):
    """Return [(rule, condition)]: each rule's first matching condition, in rules.json order."""
    scope = cand.get("rule_scope", row["scope"])
    key = cand.get("rule_key", _rule_key(row["key"]))
    votes = []
    for rule in ctx.rules_for(scope, key):
        for cond in rule["conditions"]:
            if _condition_matches(ctx, row, cand, cond):
                votes.append((rule, cond))
                break
    return _drop_shadowed(votes)


def _status_of(votes):
    """The status a candidate takes from its votes if it is not excluded."""
    present = {cond["status"] for _rule, cond in votes}
    for status in WINNER_PRECEDENCE:
        if status in present:
            return status
    return "unknown"


def _becomes_of(ctx, row, cand, votes, status):
    """The `becomes` of an entry: a computed cap or fallback, or an integer clamp."""
    found = []
    for _rule, cond in votes:
        if cond["status"] != status or "becomes" not in cond:
            continue
        becomes = cond["becomes"]
        if isinstance(becomes, dict):
            becomes = _computed_becomes(ctx, row, cand, becomes["computed"])
        if becomes is not None:
            found.append(becomes)
    if not found:
        return None
    levels = rules_schema.EFFORT_LEVELS
    if all(isinstance(b, str) and b in levels for b in found):
        return min(found, key=levels.index)
    return found[0]


# --------------------------------------------------------------------------
# One row

def _row_rules(ctx, row, cands):
    wanted = {(row["scope"], _rule_key(row["key"]))}
    for cand in cands:
        wanted.add((cand.get("rule_scope", row["scope"]), cand.get("rule_key", _rule_key(row["key"]))))
    return [r for r in ctx.rules if (r["scope"], r["key"]) in wanted]


def _row_plan(ctx, row, cands):
    """Return (layer order, order rule or None) for a row.

    The order is the longest layer_order among the row's rules, leaving out the
    rules that only name variables. Every other order must be a subsequence of
    it, else the rules disagree and this raises ValueError.

    The order rule is the one that supplies the row's order and combine: the
    row's own rule with the longest layer_order, and among those the one whose
    conditions give a value to the most layers (in_effect), so a narrow rule
    such as a default or a cap never stands for the row. A tie keeps the first
    in rules.json.
    """
    rules = [r for r in _row_rules(ctx, row, cands) if not _is_variable_rule(r)]
    if not rules:
        return list(rules_schema.LAYERS), None
    longest = max(rules, key=lambda r: len(r["layer_order"]))["layer_order"]
    for rule in rules:
        if not _is_subsequence(rule["layer_order"], longest):
            raise ValueError("rules %s and %s order the layers of %s differently" % (
                rule["rule_id"], next(r["rule_id"] for r in rules if r["layer_order"] == longest),
                row["key"]))
    primary = [r for r in rules if r["scope"] == row["scope"] and r["key"] == _rule_key(row["key"])]
    combines = {r["combine"] for r in (primary or rules)}
    if len(combines) > 1:
        raise ValueError("rules for %s combine in different ways: %s" % (
            row["key"], ", ".join(sorted(combines))))
    def breadth(rule):
        layers = {c["layer"] for c in rule["conditions"] if c["status"] == "in_effect"}
        return (len(rule["layer_order"]), len(layers))
    chosen = max(primary or rules, key=breadth)
    return list(longest), chosen


def _sort_key(order, cand):
    layer = cand["layer"]
    index = order.index(layer) if layer in order else len(order)
    return (index, cand["rank"], cand.get("file") or "")


def _select_lowest(order, eligible, rule):
    ranked = rule.get("value_order", [])

    def key(cand):
        value = cand["value"]
        pos = ranked.index(value) if value in ranked else len(ranked)
        return (pos,) + _sort_key(order, cand)
    return sorted(eligible, key=key)


def _effective_number(ctx, row, cand, votes):
    """The number a window candidate runs as: its clamp (becomes) when it has one."""
    becomes = _becomes_of(ctx, row, cand, votes, _status_of(votes))
    return read_number(becomes if becomes is not None else cand["value"])


def _synth_candidate(ctx, row):
    value = None
    if row["key"] in EFFORT_ROWS and ctx.models.get(row.get("model")):
        value = ctx.models[row["model"]]["default_effort"]
    elif row["scope"] == "agent" and row["key"] == "model":
        value = ctx.main_model_value
    return _candidate("default", None, value, synth=True)


def _synth_default(ctx, row):
    """Return (candidate, votes, status) for the default of a row.

    A row may name the model its default depends on in `default_model`. The
    agent auto-compact window does: it is the session's window, so the main
    model decides it, not the model of the agent.
    """
    drow = dict(row, model=row.get("default_model", row.get("model")))
    synth = _synth_candidate(ctx, drow)
    votes = votes_for(ctx, drow, synth)
    status = _status_of(votes) if votes else "default"
    for _rule, cond in votes:
        if cond["status"] == status and "default_value" in cond:
            synth["value"] = _show_value(row, cond["default_value"])
    if status == "unknown":
        synth["value"] = None
    return synth, votes, status


def _rank_ceiling(ctx, row, order, eligible, votes_of, rule):
    """Rank the candidates of a ceiling row. Returns (ranked, unknown votes or None).

    A candidate before the ceiling layer wins as in highest_layer. Otherwise
    the ceiling layer candidate (an agent's frontmatter) can only lower the
    session's window. The session's window is the best candidate below the
    ceiling layer, else the default window the row's rules give. The frontmatter
    wins when its number is lower, else the session's window wins. Clamped
    numbers (becomes) are the ones compared. When the session's window is
    unknown, the frontmatter wins as Unknown and the second item is the votes
    of the default that said so.
    """
    index = order.index(rule["ceiling_layer"])
    ranked = sorted(eligible, key=lambda c: _sort_key(order, c))

    def position(cand):
        return order.index(cand["layer"]) if cand["layer"] in order else len(order)
    if any(position(c) < index for c in ranked):
        return ranked, None
    ceilings = [c for c in ranked if c["layer"] == rule["ceiling_layer"]]
    below = [c for c in ranked if position(c) > index]
    if not ceilings:
        return below, None
    if below:
        session = below[0]
    else:
        session, votes, status = _synth_default(ctx, row)
        if status == "unknown":
            return ceilings, votes
        votes_of[id(session)] = votes
        below = [session]
    low = _effective_number(ctx, row, ceilings[0], votes_of[id(ceilings[0])])
    high = _effective_number(ctx, row, session, votes_of[id(session)])
    if low is not None and (high is None or low < high):
        return ceilings + below, None
    return below + ceilings, None


def _make_entry(ctx, row, cand, status, votes, becomes=None):
    entry = {
        "key": row["key"],
        "value": cand["value"],
        "status": status,
        "layer": cand["layer"],
        "file": cand.get("file"),
        "scope": row["scope"],
    }
    if cand.get("line") is not None:
        entry["line"] = cand["line"]
    if row.get("agent") is not None:
        entry["agent"] = row["agent"]
    model = cand.get("model", row.get("model"))
    if model is not None and (row["key"] in MODEL_ROWS or cand.get("model")):
        entry["model"] = model
    for field in ("via", "path", "raw"):
        if cand.get(field) is not None:
            entry[field] = cand[field]
    if becomes is not None:
        entry["becomes"] = becomes
    if cand.get("other_file"):
        entry["other_file"] = cand["other_file"]
    if cand.get("field"):
        entry["field"] = cand["field"]
    entry["_votes"] = votes
    entry["_cand"] = cand
    return entry


WINNING = ("in_effect", "lowered", "default", "unknown")


def _winner(entries):
    for entry in entries:
        if entry["status"] in WINNING:
            return entry
    return None


def resolve_row(ctx, row, cands):
    """Resolve one row. Returns its entries, the winner first.

    1. Each candidate collects the votes of the rules for its key and scope.
    2. A candidate with an invalid vote is invalid, else with an ignored vote
       ignored. It never wins.
    3. The row's combine rule picks the winner among the others. The rest are
       overridden. Candidates tied with the winner in one layer keep unknown
       when both vote unknown.
    4. With no winner, a synthesized default candidate takes the votes.

    A ceiling row (the auto-compact window of an agent) compares the layer
    that can only lower the value with the session's value, see _rank_ceiling.
    """
    order, combine_rule = _row_plan(ctx, row, cands)
    combine = combine_rule["combine"] if combine_rule else "highest_layer"
    order_id = combine_rule["rule_id"] if combine_rule else None
    excluded = []
    eligible = []
    votes_of = {}
    for cand in cands:
        votes = votes_for(ctx, row, cand)
        statuses = {cond["status"] for _rule, cond in votes}
        status = next((s for s in EXCLUDING if s in statuses), None)
        if status:
            excluded.append(_make_entry(ctx, row, cand, status, votes))
        else:
            eligible.append(cand)
            votes_of[id(cand)] = votes

    def entry_for(cand, status=None):
        votes = votes_of[id(cand)]
        status = status or _status_of(votes)
        return _make_entry(ctx, row, cand, status, votes,
                           _becomes_of(ctx, row, cand, votes, status))

    if combine == "all":
        entries = [entry_for(c) for c in eligible] + excluded
        return _finish(ctx, entries, order_id, None)
    session_unknown = None
    if combine == "lowest_value":
        ranked = _select_lowest(order, eligible, combine_rule)
    elif combine == "ceiling":
        ranked, session_unknown = _rank_ceiling(ctx, row, order, eligible, votes_of, combine_rule)
    else:
        ranked = sorted(eligible, key=lambda c: _sort_key(order, c))
    if not ranked and row["key"] in FILE_ROWS:
        return _finish(ctx, excluded, order_id, None)
    if not ranked:
        synth, votes, status = _synth_default(ctx, row)
        entry = _make_entry(ctx, row, synth, status, votes,
                            _becomes_of(ctx, row, synth, votes, status))
        return _finish(ctx, [entry] + excluded, order_id, None)
    winner = ranked[0]
    status = _status_of(votes_of[id(winner)])
    if session_unknown is not None:
        # The session's window is unknown, so what the frontmatter lowers is.
        votes_of[id(winner)] = session_unknown
        status = "unknown"
    group = []
    if combine == "highest_layer":
        for peer in ranked[1:]:
            if peer["layer"] != winner["layer"] or peer["rank"] != winner["rank"]:
                continue
            both_unknown = status == "unknown" and _status_of(votes_of[id(peer)]) == "unknown"
            if both_unknown or (winner.get("ambiguous") and peer.get("ambiguous")):
                group.append(peer)
    if group and winner.get("ambiguous"):
        status = "unknown"
    head = [entry_for(winner, status)] + [entry_for(p, "unknown") for p in group]
    taken = {id(winner)} | {id(p) for p in group}
    losers = [entry_for(c, "overridden") for c in ranked if id(c) not in taken]
    return _finish(ctx, head + losers + excluded, order_id, winner)


# A condition that carries one of these says something a plain order rule
# cannot: a clamp, a forced value, a number range, a file case or a name form.
SPECIFIC_KEYS = ("becomes", "via", "if_set", "range", "when", "name_form")


def _finish(ctx, entries, order_id, winner):
    """Add rule ids and the reason to each entry, and drop the private fields.

    rule_id is the first rule that explains the entry and the reason uses it.
    rule_ids holds every rule that voted the entry's final status, then the
    row's order rule (order_id) for a winner or an overridden entry.

    An overridden entry is explained by the order rule, because the row's order
    is why it lost, and rule_ids also holds any rule that voted overridden. A
    winning entry (in_effect, lowered, default or unknown) lists its voters,
    the most specific first (see SPECIFIC_KEYS), then rules.json order, and the
    order rule follows them with no repeats.
    """
    winner_text = _candidate_text(winner) if winner is not None else ""
    for entry in entries:
        votes = entry.pop("_votes")
        entry.pop("_cand")
        if entry["status"] == "overridden":
            ids = {r["rule_id"] for r, c in votes if c["status"] == "overridden"}
            ids.add(order_id)
            entry["rule_id"] = order_id
            entry["rule_ids"] = [r["rule_id"] for r in ctx.rules if r["rule_id"] in ids]
        else:
            matched = [(r, c) for r, c in votes if c["status"] == entry["status"]]
            matched.sort(key=lambda rc: not any(k in rc[1] for k in SPECIFIC_KEYS))
            ids = [r["rule_id"] for r, _c in matched]
            if not ids and votes:
                # The status was set by the row (a tie that stays unknown), so
                # name the rules that voted for the candidate instead.
                ids = [r["rule_id"] for r, _c in votes]
            entry["rule_id"] = ids[0] if ids else None
            if entry["status"] in WINNING and order_id is not None and order_id not in ids:
                ids = ids + [order_id]
            entry["rule_ids"] = ids
        entry["reason"] = _reason(ctx, entry, winner_text)
    return entries


class _Slots(dict):
    def __missing__(self, key):
        return ""


def _reason(ctx, entry, winner_text):
    rule = next((r for r in ctx.rules if r["rule_id"] == entry["rule_id"]), None)
    if rule is None:
        return ""
    slots = _Slots()
    for slot in rules_schema.REASON_SLOTS:
        value = entry.get(slot)
        slots[slot] = "" if value is None else str(value)
    # A reason names a model as the screen does. The entry keeps the catalog id.
    model = ctx.models.get(entry.get("model"))
    if model is not None and model.get("display_name"):
        slots["model"] = model["display_name"]
    slots["winner"] = winner_text
    # A reason reads "the shell" where an entry's source label is the shell
    # label. The entry keeps the label. A slot that opens the sentence gets a capital.
    template = rule["reason"]
    for slot in ("file", "other_file"):
        if entry.get(slot) is not None and entry[slot] == ctx.inputs.shell_label:
            slots[slot] = "The shell" if template.startswith("{%s}" % slot) else "the shell"
    return template.format_map(slots)


# --------------------------------------------------------------------------
# Rows

def _env_rows(ctx):
    """Resolve the env blocks and the shell into process env rows."""
    if not ctx.rules_for("main", "env"):
        raise ValueError("the rules have no env-block rule (key env, scope main)")
    names = {}
    for name, records in ctx.collected.get("env", {}).items():
        for rec in records:
            if rec["origin"] == "shell":
                cand = _candidate("env", ctx.inputs.shell_label, rec["value"])
            else:
                file = ctx.show(rec["path"]) if rec.get("path") else rec["layer"]
                cand = _candidate(rec["layer"], file, rec["value"], rec.get("line"))
            names.setdefault(name, []).append(cand)
    # The --settings content is not collected, so its env block joins here.
    cli = ctx.inputs.cli_settings
    block = cli.get("env") if isinstance(cli, dict) else None
    if isinstance(block, dict):
        for name, value in block.items():
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                names.setdefault(name, []).append(_candidate("cli", LABEL_CLI, str(value)))
    entries = []
    for name in sorted(names):
        row = {"key": "env." + name, "scope": "main", "agent": None, "model": None}
        got = resolve_row(ctx, row, names[name])
        _mark_unreadable_files(ctx, got, row, names[name])
        entries.extend(got)
        winner = _winner(got)
        if winner is not None:
            ctx.env[name] = {"value": winner["value"], "file": winner["file"],
                             "line": winner.get("line"), "status": winner["status"]}
    return entries


def _agent_file_rows(ctx):
    """Entries for the agentFile rows, and {agent name: files that load}."""
    by_name = {}
    for f in ctx.agent_files:
        by_name.setdefault(f["name"], []).append(f)
    entries = []
    active = {}
    for name in sorted(by_name):
        files = by_name[name]
        row = {"key": "agentFile", "scope": "agent", "agent": name, "model": None}
        cands = [_candidate(f["layer"], f["file"], None, f["line"], case=f["case"],
                            other_file=f["other_file"]) for f in files]
        got = resolve_row(ctx, row, cands)
        # A file whose agentFile is in effect, or unknown, loads in Claude Code.
        loads = {e["file"] for e in got if e["status"] in ("in_effect", "unknown")}
        if loads:
            active[name] = [f for f in files if f["file"] in loads]
        winner = next((e for e in got if e["status"] == "in_effect"), None)
        loser = next((e for e in got if e["status"] == "overridden"), None)
        for entry in got:
            if "other_file" in entry:
                continue
            if entry is winner and loser is not None:
                entry["other_file"] = loser["file"]
            elif entry["status"] == "overridden" and winner is not None:
                entry["other_file"] = winner["file"]
        for f in files:
            if f["loadable"]:
                for field in sorted(set(f["fields"]) - ctx.agent_fields):
                    got.append(_unknown_field_entry(ctx, row, f, field))
        entries.extend(got)
    return entries, active


def _unknown_field_entry(ctx, row, f, field):
    """The entry for a frontmatter field Claude Code does not read."""
    cand = _candidate(f["layer"], f["file"], None, f["lines"].get(field, 1),
                      case="unknown_field", field=field)
    votes = votes_for(ctx, row, cand)
    statuses = {cond["status"] for _rule, cond in votes}
    status = next((s for s in EXCLUDING if s in statuses), None) or _status_of(votes)
    return _finish(ctx, [_make_entry(ctx, row, cand, status, votes)], None, None)[0]


def _rules_file_rows(ctx):
    cands = []
    for rec in ctx.collected.get("rules_files", []):
        case = None if rec["path"].endswith(".md") else "not_md_file"
        cands.append(_candidate(rec["layer"], ctx.show(rec["path"]), None, 1, case=case))
    if not cands:
        return []
    row = {"key": "rulesFile", "scope": "main", "agent": None, "model": None}
    return resolve_row(ctx, row, cands)


def _settings_file_rows(ctx):
    """Entries for the settingsFile row: each settings file that did not parse or read.

    The rules decide each one's status and reason. The entries whose status is
    unknown are kept in ctx.unknown_files, highest layer first, for
    _mark_unreadable_files.
    """
    cands = [_candidate(rec["layer"], ctx.show(rec["path"]), None, rec["line"] or 1,
                        case=rec["status"])
             for rec in ctx.collected.get("settings_files", []) if rec["status"] != "ok"]
    if not cands:
        return []
    row = {"key": "settingsFile", "scope": "main", "agent": None, "model": None}
    got = resolve_row(ctx, row, cands)
    ctx.unknown_files = [e for e in got if e["status"] == "unknown"]
    return got


def _main_rows(ctx):
    entries = []

    def run(key):
        row = {"key": key, "scope": "main", "agent": None,
               "model": ctx.main_model if key in MODEL_ROWS else None}
        cands = settings_candidates(ctx, row) + variable_candidates(ctx, row)
        got = resolve_row(ctx, row, cands)
        marked = _mark_unreadable_files(ctx, got, row, cands)
        entries.extend(got)
        return got, marked

    got, marked = run("model")
    winner = _winner(got)
    if winner is not None and not marked:
        ctx.main_model_value = winner["value"]
        ctx.main_model = normalize_model(winner["value"], ctx.catalog)[0]
    for key in ("maxEffortLevel", "effortLevel", "autoCompactWindow", "promptCacheTtl"):
        run(key)
    entries.extend(_rules_file_rows(ctx))
    return entries


def _ranks_above(ctx, entry, order, layer):
    """True when `layer` ranks above a winning entry.

    The entry's own reason rule says it when its layer_order holds both layers
    (CLAUDE_CODE_SUBAGENT_MODEL_FORCE puts the variable above the frontmatter),
    else the row's order does.
    """
    rule = next((r for r in ctx.rules if r["rule_id"] == entry["rule_id"]), None)
    if rule is not None and layer in rule["layer_order"] \
            and entry["layer"] in rule["layer_order"]:
        order = rule["layer_order"]
    return layer in order and entry["layer"] in order \
        and order.index(layer) < order.index(entry["layer"])


def _become_unknown(winner, source):
    """Make a winning entry Unknown, with the rule ids and reason of `source`.

    It keeps its value, layer, file and line, and it drops `becomes`.
    """
    winner["status"] = "unknown"
    winner.pop("becomes", None)
    winner["rule_id"] = source["rule_id"]
    winner["rule_ids"] = list(source["rule_ids"])
    winner["reason"] = source["reason"]


def _mark_unreadable(ctx, entries, order, unreadable):
    """Make the winner of an agent row Unknown when frontmatter it cannot read ranks above it.

    `unreadable` is the agentFile entry of a file the reader rejected. Its rule
    ids and reason say why the dashboard can't read the frontmatter, and they
    become the winner's. A row with only a default has the agent layer above it.
    """
    winner = _winner(entries)
    if unreadable is None or winner is None or not _ranks_above(ctx, winner, order, "agent"):
        return
    _become_unknown(winner, unreadable)


def _mark_unreadable_files(ctx, entries, row, cands):
    """Make the winner of a row Unknown when a settings file it could come from is unknown.

    This is the same mechanism agents use (_mark_unreadable), applied to the
    settingsFile entries whose status is unknown (an unreadable file, or a
    managed file that is not JSON). Their status, rule ids and reason come from
    rules.json, and the winner takes the ones of the highest-ranked such file.
    The code only decides whether that file could have set the winner's value.
    For a file in layer L, it could when any of these holds:

      a. the row takes the lowest value (combine lowest_value) and L is in the
         row's order, because any file might hold a lower value;
      b. L is in the order and the winner ranks below L, or the winner is a
         default;
      c. env is in the order and the winner ranks at or below env, because the
         file's env block could set the variable behind the winner (rule
         env-block-order). A winner on the env layer that has a via is the
         exception. The env.<VAR> row already weighed every env block against
         it, so the file counts only when that row's winner is unknown
         (ctx.env[via]["status"]). A winner below env has no such row to lean
         on, because the variable is unset and any file's block could set it.

    The order is the row's, with the winner's own reason rule taking over when
    its layer_order holds both layers (see _ranks_above). Call it for rows a
    settings file can feed: the main and agent rows of the model, effort,
    window and cache keys, and every env.<VAR> row. Returns True when it
    marked the winner.
    """
    winner = _winner(entries)
    if winner is None or not ctx.unknown_files:
        return False
    order, rule = _row_plan(ctx, row, cands)
    lowest = rule is not None and rule["combine"] == "lowest_value"
    via = ctx.env.get(winner.get("via"))
    if winner["layer"] == "env" and via is not None:
        env_covers = via.get("status") == "unknown"
    else:
        env_covers = winner["layer"] == "env" or _ranks_above(ctx, winner, order, "env")
    for source in ctx.unknown_files:
        layer = source["layer"]
        in_order = layer in order
        if (lowest and in_order) \
                or (in_order and (winner["layer"] == "default"
                                  or _ranks_above(ctx, winner, order, layer))) \
                or ("env" in order and env_covers):
            _become_unknown(winner, source)
            return True
    return False


def _agent_rows(ctx, name, files, file_entries):
    entries = []
    unreadable = next((e for f in files if f["case"] in UNREADABLE_CASES
                       for e in file_entries
                       if e["key"] == "agentFile" and e.get("agent") == name
                       and e["file"] == f["file"] and e["status"] == "unknown"), None)
    model_row = {"key": "model", "scope": "agent", "agent": name, "model": None}
    cands = frontmatter_candidates(ctx, model_row, files) + variable_candidates(ctx, model_row)
    got = resolve_row(ctx, model_row, cands)
    marked = _mark_unreadable_files(ctx, got, model_row, cands)
    _mark_unreadable(ctx, got, _row_plan(ctx, model_row, cands)[0], unreadable)
    entries.extend(got)
    winner = _winner(got)
    agent_model = normalize_model(winner["value"], ctx.catalog)[0] \
        if winner and not marked else None
    for key in ("effort", "autoCompactWindow", "subagentPromptCacheTtl"):
        row = {"key": key, "scope": "agent", "agent": name,
               "model": agent_model if key in MODEL_ROWS else None}
        if key == "autoCompactWindow":
            # The window an agent inherits is the session's, so the default
            # depends on the main model, not on the model of the agent.
            row["default_model"] = ctx.main_model
        cands = (frontmatter_candidates(ctx, row, files) + settings_candidates(ctx, row)
                 + variable_candidates(ctx, row))
        got = resolve_row(ctx, row, cands)
        _mark_unreadable_files(ctx, got, row, cands)
        _mark_unreadable(ctx, got, _row_plan(ctx, row, cands)[0], unreadable)
        entries.extend(got)
    return entries


def resolve(inputs, rules, agent_fields):
    """Return the resolution of every row as a list of entry dicts.

    `inputs` holds what the collectors found (see Inputs). `rules` is the
    rules.json document (see load_rules). `agent_fields` is the list of
    frontmatter fields Claude Code reads (see load_agent_fields). resolve opens
    no file. Entries hold key, value, status, layer, file and scope always, and
    line, agent, model, via, path, raw, becomes, other_file and field when they
    apply, then rule_id, rule_ids and reason.
    """
    ctx = _Context(inputs, rules, agent_fields)
    entries = _settings_file_rows(ctx)
    entries.extend(_env_rows(ctx))
    file_entries, active = _agent_file_rows(ctx)
    entries.extend(_main_rows(ctx))
    entries.extend(file_entries)
    for name in sorted(active):
        entries.extend(_agent_rows(ctx, name, active[name], file_entries))
    return entries


# --------------------------------------------------------------------------
# Comparison

def _row_of(entry):
    return (entry["key"], entry["scope"], entry.get("agent"))


def _row_text(row):
    key, scope, agent = row
    return "%s/%s%s" % (key, scope, "/" + agent if agent else "")


def _differences(expected, got):
    return [f for f in expected if f not in got or got[f] != expected[f]]


def _pair(expected_list, got_list):
    """Pair expected entries with runner entries one to one. Returns {expected index: got index}."""
    match = {}
    taken = {}

    def try_expected(i, seen):
        for j, got in enumerate(got_list):
            if j in seen or _differences(expected_list[i], got):
                continue
            seen.add(j)
            if j not in taken or try_expected(taken[j], seen):
                taken[j] = i
                match[i] = j
                return True
        return False

    for i in range(len(expected_list)):
        try_expected(i, set())
    return match


def compare(entries, expected):
    """Compare resolve() output with an expected.json document. Returns messages.

    Rows are (key, scope, agent). For each row the expected file names, the
    runner's entries must pair one to one with the expected entries, and each
    expected field must equal the runner's field (the runner may carry extra
    fields, rule_id and reason among them: an expected entry that carries
    them has them checked). Rows the file does not name are not checked. Every
    id in the expected rule_ids must appear in the rule_ids of an entry in a
    row the file names, so the list holds the rules that voted the final
    status of those entries, and the order rules of the rows.
    """
    name = expected.get("fixture", "fixture")
    messages = []
    want = {}
    for item in expected.get("expect", []):
        want.setdefault(_row_of(item), []).append(item)
    have = {}
    for entry in entries:
        have.setdefault(_row_of(entry), []).append(entry)
    for row, items in want.items():
        got_list = have.get(row, [])
        where = "%s: row %s" % (name, _row_text(row))
        paired = _pair(items, got_list)
        if len(items) != len(got_list):
            messages.append("%s: expected %d entries, got %d" % (where, len(items), len(got_list)))
        for i, item in enumerate(items):
            if i in paired:
                continue
            best = None
            for j, got in enumerate(got_list):
                if j in paired.values():
                    continue
                diff = _differences(item, got)
                if best is None or len(diff) < len(best[1]):
                    best = (j, diff, got)
            if best is None:
                messages.append("%s: no entry for %s" % (where, json.dumps(item, sort_keys=True)))
                continue
            for field in best[1]:
                messages.append("%s: %s expected %s, got %s" % (
                    where, field, json.dumps(item[field]),
                    json.dumps(best[2][field]) if field in best[2] else "nothing"))
    seen = set()
    for row in want:
        for entry in have.get(row, []):
            seen.update(entry.get("rule_ids", []))
    for rule_id in expected.get("rule_ids", []):
        if rule_id not in seen:
            messages.append("%s: rule_ids: %s is in no rule_ids of the rows the file names"
                            % (name, rule_id))
    return messages


# --------------------------------------------------------------------------
# Command line

def run_fixtures(folder, out=None):
    """Run every fixture folder in `folder`. Returns the number that failed."""
    out = out or sys.stdout
    rules = load_rules()
    fields = load_agent_fields()
    failed = 0
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if not os.path.isfile(os.path.join(path, "expected.json")):
            continue
        try:
            inputs, expected = load_fixture(path, rules)
            messages = compare(resolve(inputs, rules, fields), expected)
        except Exception as exc:  # a broken fixture should not stop the rest
            messages = ["%s: %s: %s" % (name, exc.__class__.__name__, exc)]
        if messages:
            failed += 1
            out.write("%s: FAIL\n" % name)
            for line in messages:
                out.write("  %s\n" % line)
        else:
            out.write("%s: ok\n" % name)
    return failed


def main(argv):
    folder = argv[1] if len(argv) > 1 else FIXTURES_PATH
    return 1 if run_fixtures(folder) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
