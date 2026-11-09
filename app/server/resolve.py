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
    model_permitted(name, allowed, catalog) -> True, False or None (can't tell)

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
       promptCacheTtl, alwaysThinkingEnabled, availableModels, fallbackModel,
       rulesFile. effortLevel needs the main model and the cap. The thinking row
       needs the main model. fallbackModel needs the availableModels row, which
       fills ctx.allowed, because Claude Code drops chain entries the list
       blocks.
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

# ruff: noqa: PLR0911, PLR0912, PLR0913, PLR0915, PLR0917, PTH100, PTH113, PTH118
# ruff: noqa: PTH119, PTH120, PTH123, PTH208, SIM103, SIM105, TRY003, UP031
#
# Ported unchanged so the old tests keep passing. The old code builds paths as
# strings with os.path, formats messages with %, raises ValueError with its own
# messages, and keeps its long row functions.

import dataclasses
import json
import os
import re
import sys
from collections.abc import Iterable
from typing import Any, TextIO, cast

import agent_frontmatter
import collect
import rules_schema
from json_shapes import is_dict, is_list
from model_catalog import Catalog, normalize_model
from usage import Row

# A rule and one of its conditions that voted for a candidate.
Vote = tuple[Row, Row]

RULES_PATH = rules_schema.RULES_PATH
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    "--fallback-model": [("fallbackModel", "main")],
}

# The settings key that feeds each row: (scope, row key) -> settings key.
SETTINGS_KEYS = {
    ("main", "model"): "model",
    ("main", "maxEffortLevel"): "maxEffortLevel",
    ("main", "effortLevel"): "effortLevel",
    ("main", "autoCompactWindow"): "autoCompactWindow",
    ("main", "promptCacheTtl"): "promptCacheTtl",
    ("main", "alwaysThinkingEnabled"): "alwaysThinkingEnabled",
    ("main", "fallbackModel"): "fallbackModel",
    ("main", "availableModels"): "availableModels",
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
MODEL_ROWS = (
    "maxEffortLevel",
    "effortLevel",
    "effort",
    "autoCompactWindow",
    "alwaysThinkingEnabled",
)
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
READER_CASES = ("parse_error", *UNREADABLE_CASES)

# What a vote means for the candidate that wins, strongest first.
WINNER_PRECEDENCE = ("unknown", "lowered", "default", "in_effect")
EXCLUDING = ("invalid", "ignored")


@dataclasses.dataclass(frozen=True)
class Inputs:
    """What resolve works from. See the module docstring for each field."""

    collected: dict[str, Any]
    flags: list[str] = dataclasses.field(default_factory=list[str])
    cli_settings: object = None
    plan: object = None
    home: object = None
    root: object = None
    shell_label: str = LIVE_SHELL_LABEL


# --------------------------------------------------------------------------
# Loading


def load_rules(path: str = RULES_PATH) -> dict[str, Any]:
    """Return the rules.json document. It does not validate; rules_schema does."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_json(path: str) -> dict[str, Any] | None:
    """Return the object in a JSON file, or None when it is missing or not an object."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if is_dict(data) else None


def load_agent_fields(path: str = agent_frontmatter.FIELDS_PATH) -> list[str]:
    """Return the field names Claude Code reads in agent frontmatter."""
    data = _read_json(path) or {}
    return [item["field"] for item in data.get("fields", []) if is_dict(item)]


def load_fixture(
    folder: str, rules: dict[str, Any] | None = None
) -> tuple[Inputs, Any]:
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
        rules=rules,
    )
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


def read_number(value: object) -> int | None:
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
# The model allowlist

FAMILIES = ("opus", "sonnet", "haiku", "fable")
_FAMILY_RE = re.compile(r"claude-(%s)(?![a-z])" % "|".join(FAMILIES))


def _family_in(text: str) -> str | None:
    """The family a lower-case model name embeds, or None.

    A family alias is its own family. For "claude-<family>-..." the family is
    the second hyphen segment, and an id that embeds one (such as a provider id
    "anthropic.claude-<family>-...") names the same family.
    """
    if text in FAMILIES:
        return text
    match = _FAMILY_RE.search(text)
    return match.group(1) if match else None


def model_permitted(name: object, allowed: object, catalog: Catalog) -> bool | None:
    """Say whether an availableModels list permits a model name.

    Returns True, False, or None when the dashboard can't tell. `allowed` is
    the list that runs, `catalog` the models list of rules.json. Names compare
    in lower case. The basis is the model configuration page (Restrict model
    selection, Merge behavior and Mantle model IDs):

    - A family alias (a catalog alias, or opus, sonnet, haiku, fable) is
      permitted when the list holds that alias or any entry naming the family,
      because Claude Code swaps a blocked alias for the newest permitted
      version of the family. Otherwise it is not.
    - A name that starts with "claude-" is permitted when an entry equals it or
      is a version prefix of it (the entry plus "-"). A family alias entry
      counts only when no entry in the list is specific to that family, because
      a specific entry disables that family's wildcard. With no match the name
      is not permitted, unless the list holds an entry that is neither a family
      alias nor a "claude-" name (such as anthropic.*), and then the answer is
      None. A "claude-" name with no family in it (claude-3-...) that no entry
      matches is None too, because no family entry can be matched to it.
    - Any other name, "default" included, is None.
    """
    allowed_names = cast("Iterable[object]", allowed or [])
    entries = [e.lower() for e in allowed_names if isinstance(e, str)]
    if not isinstance(name, str):
        return None
    name = name.lower()
    aliases = set(FAMILIES)
    for model in catalog:
        aliases.update(a.lower() for a in model.get("aliases", []))
    if name in aliases:
        family = _family_in(name)
        if family is None:
            model = next(
                (
                    m
                    for m in catalog
                    if name in [a.lower() for a in m.get("aliases", [])]
                ),
                None,
            )
            family = _family_in(model["id"]) if model else None
        return any(
            e == name or (family is not None and _family_in(e) == family)
            for e in entries
        )
    if not name.startswith("claude-"):
        return None
    rid = re.sub(r"\[1m\]$", "", name)
    if any(e == rid or rid.startswith(e + "-") for e in entries):
        return True
    family = _family_in(rid)
    if family is None:
        # An id with no family in it (an old claude-3-... id): the list's family
        # entries can't be matched to it, so the dashboard can't tell.
        return None
    specific = any(e not in aliases and _family_in(e) == family for e in entries)
    if family in entries and not specific:
        return True
    if any(e not in aliases and not e.startswith("claude-") for e in entries):
        return None
    return False


# --------------------------------------------------------------------------
# Sources


def _below(path: object, base: object) -> str | None:
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
        return path[len(base) + 1 :]
    return None


def display_path(path: str, home: object = None, root: object = None) -> str:
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


def split_chain(text: str) -> list[str]:
    """Split a --fallback-model value on commas: strip spaces, drop empty items."""
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_flags(flags: object) -> dict[str, Any]:
    """Return {flag: value} for the flags in FLAGS. The last use of a flag wins.

    --fallback-model takes a comma-separated list, so its value is a list of
    names (see split_chain). Every other value is the word as it was given.
    """
    out: dict[str, Any] = {}
    flag_words = cast("Iterable[object]", flags or [])
    words = [w for w in flag_words if isinstance(w, str)]
    for i, word in enumerate(words):
        name, sep, inline = word.partition("=")
        if name not in FLAGS:
            continue
        if sep:
            out[name] = inline
        elif i + 1 < len(words):
            out[name] = words[i + 1]
        else:
            continue
        if name == "--fallback-model":
            out[name] = split_chain(out[name])
    return out


def _frontmatter_kinds(errors: list[str]) -> list[str]:
    kinds: list[Any] = []
    for error in errors:
        kind = error.split(": ", 1)[1] if ": " in error else error
        if kind not in kinds:
            kinds.append(kind)
    return kinds


def _reader_case(kinds: list[str]) -> str:
    """Map the reader's error kinds to a file case."""
    if any(k in PARSE_ERROR_KINDS for k in kinds):
        return "parse_error"
    if all(k in LOADS_ANYWAY_KINDS for k in kinds):
        return "reader_rejected_but_loads"
    return "reader_rejected_untested"


def _stem(path: str) -> str:
    return os.path.basename(path).split(".")[0]


def _first_error_line(errors: list[str]) -> int:
    """Return the line the reader's first error names, or 1."""
    match = re.match(r"line (\d+)", errors[0]) if errors else None
    return int(match.group(1)) if match else 1


def read_agent_files(inputs: Inputs) -> list[Row]:
    """Return one dict per agent file: layer, file, name, case, fields, loadable.

    The files come from inputs.collected["agents"]. Cases are decided per file
    in this order: not_md_file, the reader's errors, no_name, no_description,
    then same_name_in_layer across the files of one layer. other_file is set on
    a same_name_in_layer file. `line` is the line the file's entry shows: the
    name line when the file loads, the reader's first error when the reader
    rejected the file, else 1. `lines` maps a frontmatter path to its line.
    """
    files: list[Any] = []
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
        elif not (
            isinstance(fields.get("description"), str)
            and fields["description"].strip() != ""
        ):
            case = "no_description"
        files.append(
            {
                "layer": rec["layer"],
                "path": path,
                "file": display_path(path, inputs.home, inputs.root),
                "name": cast("str", name).strip() if readable else _stem(path),
                "case": case,
                "fields": fields if not errors else {},
                "lines": rec.get("lines") or {},
                "line": _first_error_line(errors) if case in READER_CASES else 1,
                "loadable": False,
                "other_file": None,
            }
        )
    for layer in ("project", "user"):
        groups: dict[Any, Any] = {}
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

    def __init__(
        self, inputs: Inputs, rules: dict[str, Any], agent_fields: Iterable[str]
    ) -> None:
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
        self.env: dict[
            str, Row
        ] = {}  # name -> {"value", "file", "line", "status"} of the env.<name> winner
        self.unknown_files: list[
            Row
        ] = []  # settingsFile entries whose status is unknown
        self.main_model: str | None = None  # catalog id
        self.main_model_value: object = None
        # What the availableModels row says, for the fallbackModel row after it.
        self.allowed: list[str] | None = (
            None  # the list that runs, or None when nothing sets one
        )
        self.allowed_unclear = False  # the dashboard can't say which list runs
        self.model_blocks_unclear = False  # managed settings block models another way
        self.caps: dict[str | None, str | None] = {}
        self._covers: dict[str, list[str]] = {}

    def show(self, path: str) -> str:
        """The text an entry shows for a file path."""
        return display_path(path, self.inputs.home, self.inputs.root)

    def _sources(self) -> list[Row]:
        """The settings sources, highest first, with the --settings content added.

        Each is {"layer", "data", "where", "label"}. `label` names the file of
        a value that has no entry in `where`.
        """
        found = [
            dict(src, label=src["layer"]) for src in self.collected.get("settings", [])
        ]
        cli = self.inputs.cli_settings
        if is_dict(cli):
            at = sum(1 for src in found if src["layer"] == "managed")
            found.insert(
                at, {"layer": "cli", "data": cli, "where": {}, "label": LABEL_CLI}
            )
        return found

    def spot(self, src: Row, path: tuple[str, ...]) -> tuple[str, int | None]:
        """Return (file, line) for the key `path` (a tuple) of a settings source."""
        where = src["where"].get(path)
        if where is None:
            return src["label"], None
        return self.show(where["path"]), where["line"]

    def rules_for(self, scope: str, key: str) -> list[Row]:
        return [r for r in self.rules if r["scope"] == scope and r["key"] == key]

    def covers(self, models: object) -> list[str]:
        key = json.dumps(models, sort_keys=True)
        if key not in self._covers:
            self._covers[key] = rules_schema.expand_models(models, self.catalog_ids)
        return self._covers[key]

    def env_is_set(self, name: str) -> bool:
        return name in self.env and self.env[name]["value"] != ""


def _rule_key(key: str) -> str:
    return "env" if key.startswith("env.") else key


def _is_variable_rule(rule: Row) -> bool:
    """A rule whose every condition names a variable (via or if_set)."""
    return all("via" in c or "if_set" in c for c in rule["conditions"])


def _is_subsequence(small: list[str], big: list[str]) -> bool:
    it = iter(big)
    return all(item in it for item in small)


# --------------------------------------------------------------------------
# Candidates


def _candidate(
    layer: str,
    file: str | None,
    value: object,
    line: int | None = None,
    **extra: object,
) -> Row:
    cand = {
        "layer": layer,
        "file": file,
        "value": value,
        "line": line,
        "rank": (1, 0, 0),
    }
    cand.update(extra)
    return cand


def _show_value(row: Row, value: object) -> object:
    """Digits-only strings on an autoCompactWindow row show as integers.

    A list (fallbackModel, availableModels) shows as a copy, so an entry never
    shares the list the collectors hold. A --fallback-model flag value is
    already a list (parse_flags splits it).
    """
    if (
        row["key"] == "autoCompactWindow"
        and isinstance(value, str)
        and value.isdigit()
        and value.isascii()
    ):
        return int(value)
    if is_list(value):
        return list(value)
    return value


def _dig(data: object, path: tuple[str, ...]) -> object:
    for part in path:
        if not is_dict(data) or part not in data:
            return None
        data = data[part]
    return data


def settings_candidates(ctx: _Context, row: Row) -> list[Row]:
    """Candidates from the settings files, flags and modelSettings for one row."""
    out: list[Any] = []
    skey = SETTINGS_KEYS.get((row["scope"], row["key"]))
    field = MODEL_SETTINGS_FIELDS.get(row["key"])
    for src in ctx.settings:
        top = None
        if skey is not None and src["data"].get(skey) is not None:
            file, line = ctx.spot(src, (skey,))
            top = _candidate(
                src["layer"], file, _show_value(row, src["data"][skey]), line
            )
            out.append(top)
        table = src["data"].get("modelSettings")
        if field is not None and row.get("model") and is_dict(table):
            # Entries for this model in this file: (name form index, value).
            found: list[Any] = []
            for name, entry in table.items():
                model_id, form = normalize_model(name, ctx.catalog)
                if (
                    model_id != row["model"]
                    or not is_dict(entry)
                    or entry.get(field) is None
                ):
                    continue
                rule_key = (
                    "modelSettings"
                    if field == "effortLevel"
                    else "modelSettings." + field
                )
                file, line = ctx.spot(src, ("modelSettings", name, field))
                out.append(
                    _candidate(
                        src["layer"],
                        file,
                        _show_value(row, entry[field]),
                        line,
                        path="modelSettings.%s.%s" % (name, field),
                        name_form=form,
                        model=model_id,
                        rule_key=rule_key,
                        rule_scope="model",
                        rank=(0, rules_schema.NAME_FORMS.index(form), 0),
                    )
                )
                found.append((rules_schema.NAME_FORMS.index(form), entry[field]))
            if top is not None and row["key"] == "maxEffortLevel" and found:
                # A valid per-model cap replaces this file's top-level cap for the
                # model. If several name forms match, the lowest NAME_FORMS index
                # decides, and on a tie any valid entry counts. A value that is
                # not a level replaces nothing.
                best = min(index for index, _value in found)
                if any(
                    index == best
                    and isinstance(value, str)
                    and value in rules_schema.EFFORT_LEVELS
                    for index, value in found
                ):
                    top["replaced_in_source"] = True
    for flag, rows in FLAGS.items():
        if flag in ctx.flags and (row["key"], row["scope"]) in rows:
            out.append(
                _candidate(
                    "flag", LABEL_FLAGS, _show_value(row, ctx.flags[flag]), flag=flag
                )
            )
    return out


def variable_candidates(ctx: _Context, row: Row) -> list[Row]:
    """One candidate for each variable in the rules' variables list that is set."""
    out: list[Any] = []
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
            out.append(
                _candidate(
                    layer,
                    file,
                    _show_value(row, value),
                    line,
                    via=name,
                    rank=(2, 0, index),
                )
            )
    return out


def frontmatter_candidates(ctx: _Context, row: Row, files: list[Row]) -> list[Row]:
    """Candidates from the frontmatter of the agent files that load for this agent."""
    path = FRONTMATTER_KEYS.get(row["key"])
    if path is None:
        return []
    out: list[Any] = []
    for f in files:
        value = _dig(f["fields"], path)
        if not isinstance(value, str) or value == "":
            continue
        cand = _candidate(
            "agent",
            f["file"],
            _show_value(row, value),
            f["lines"].get(".".join(path)),
            ambiguous=f["case"] == "same_name_in_layer",
        )
        if row["key"] == "model" and value == "inherit":
            cand["raw"] = "inherit"
            cand["value"] = ctx.main_model_value
        out.append(cand)
    return out


# --------------------------------------------------------------------------
# File cases for the thinking and model-list rows

CHAIN_LIMIT = 3  # Claude Code keeps at most three distinct models in a fallback chain
CASE_KEYS = ("alwaysThinkingEnabled", "fallbackModel", "availableModels")


def _is_text_list(value: object) -> bool:
    return is_list(value) and all(isinstance(item, str) for item in value)


def _wrong_type(key: str, cand: Row) -> bool:
    """True when a candidate's value has a type Claude Code does not read for the key.

    alwaysThinkingEnabled reads a boolean from a file, and from
    MAX_THINKING_TOKENS a string of ASCII digits (an empty string is wrong too).
    fallbackModel and availableModels read a list of strings. A whole value
    that reads "hidden" is a masked string, because the masking hides a list
    item by item, so it has the wrong type for these keys. An item "hidden"
    inside a list is still a string, and the list is fine.
    """
    value = cand["value"]
    if key == "alwaysThinkingEnabled":
        if cand.get("via"):
            return not (
                isinstance(value, str)
                and value != ""
                and value.isascii()
                and value.isdigit()
            )
        return not isinstance(value, bool)
    return not _is_text_list(value)


def _chain_case(ctx: _Context, value: list[Any]) -> tuple[str | None, list[str] | None]:
    """Return (case, chain) for a fallbackModel list: how Claude Code cuts it.

    Claude Code removes duplicate entries, drops entries the availableModels
    list does not permit and keeps at most three (CHAIN_LIMIT). The case is
    chain_limited when that changes the list, with the chain that runs;
    chain_unclear when the dashboard can't work the chain out; else None.

    The allowlist comes first, then the cap: the settings reference says Claude
    Code "keeps at most three distinct allowed models from the list". Entries
    that no rule can place are unclear, and so is any chain while managed
    settings block models another way (deniedModels, availableModelsMatch) or
    the allowlist is unclear. "default" expands to a model the dashboard can't
    name, so a chain of more than three with "default" in it is unclear even
    with no allowlist, because it hides which three stay.
    """
    unique: list[Any] = []
    seen: set[Any] = set()
    for name in value:
        marker = normalize_model(name, ctx.catalog)[0] or name
        if marker not in seen:
            seen.add(marker)
            unique.append(name)
    if ctx.model_blocks_unclear or ctx.allowed_unclear:
        return "chain_unclear", None
    if len(unique) > CHAIN_LIMIT and any(name.lower() == "default" for name in unique):
        return "chain_unclear", None
    if ctx.allowed is None:
        kept = unique[:CHAIN_LIMIT]
    else:
        verdicts = [model_permitted(name, ctx.allowed, ctx.catalog) for name in unique]
        if any(v is None for v in verdicts):
            return "chain_unclear", None
        kept = [name for name, v in zip(unique, verdicts, strict=False) if v][
            :CHAIN_LIMIT
        ]
    if kept != value:
        return "chain_limited", kept
    return None, None


def set_cases(ctx: _Context, key: str, cands: list[Row]) -> None:
    """Set cand["case"] (and cand["chain"]) on the candidates of the key's row.

    wrong_type for alwaysThinkingEnabled, fallbackModel and availableModels.
    For a fallbackModel list of the right type: chain_limited or chain_unclear
    (see _chain_case). It must run after the availableModels row, which fills
    ctx.allowed.
    """
    if key not in CASE_KEYS:
        return
    for cand in cands:
        if _wrong_type(key, cand):
            cand["case"] = "wrong_type"
        elif key == "alwaysThinkingEnabled" and cand.get("via"):
            # A digit string through the variable is a number: "00" is the "0"
            # the rules name.
            try:
                cand["value"] = str(int(cand["value"]))
            except ValueError:
                pass
        elif key == "fallbackModel":
            case, chain = _chain_case(ctx, cand["value"])
            if case is not None:
                cand["case"] = case
            if chain is not None:
                cand["chain"] = chain


# --------------------------------------------------------------------------
# Votes


def _candidate_text(cand: Row) -> str:
    """What a candidate shows when a reason names it as the winner."""
    if cand.get("via"):
        return cand["via"]
    if cand.get("flag"):
        return cand["flag"]
    if cand["layer"] == "default" and not cand.get("file"):
        return "Claude Code's default"
    return cand.get("file") or cand["layer"]


def _match_value(cand: Row) -> str | None:
    """The value a condition's `values` list is compared with, as a string."""
    value = cand.get("raw", cand["value"])
    if value is None:
        return None
    return value if isinstance(value, str) else json.dumps(value)


def _effort_cap(ctx: _Context, model_id: str | None) -> str | None:
    """Return the maxEffortLevel in effect for a model, or None."""
    if model_id not in ctx.caps:
        row = {
            "key": "maxEffortLevel",
            "scope": "main",
            "agent": None,
            "model": model_id,
        }
        entries = resolve_row(ctx, row, settings_candidates(ctx, row))
        winner = _winner(entries)
        ctx.caps[model_id] = (
            winner["value"] if winner and winner["status"] == "in_effect" else None
        )
    return ctx.caps[model_id]


def _computed_becomes(ctx: _Context, row: Row, cand: Row, kind: str) -> object:
    """Return what a computed `becomes` works out for a candidate, or None."""
    if kind == "chain":
        # The fallbackModel chain that runs: the names, or "nothing" when every
        # entry is dropped. It has no effort level to check.
        chain = cand.get("chain")
        if chain is None:
            return None
        return ", ".join(chain) or "nothing"
    levels = rules_schema.EFFORT_LEVELS
    value = cand["value"]
    if not isinstance(value, str) or value not in levels:
        return None
    if kind == "cap":
        # With no model known, only the top-level caps count (no modelSettings
        # line has a model to match). A "max" or invalid cap lowers nothing.
        cap = _effort_cap(ctx, row.get("model"))
        if cap in levels and levels.index(value) > levels.index(cap):
            return cap
        return None
    model = ctx.models.get(row.get("model"))
    if model is None:
        return None
    offered = model["effort_levels"]
    if not offered or value in offered:
        return None
    below = [lv for lv in offered if levels.index(lv) <= levels.index(value)]
    return below[-1] if below else None


def _model_unknown(ctx: _Context, row: Row) -> bool:
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


def _condition_matches(ctx: _Context, row: Row, cand: Row, cond: Row) -> bool:
    if cond["layer"] != cand["layer"]:
        return False
    if (
        cond["layer"] == "default"
        and cond["status"] in ("default", "unknown")
        and not cand.get("synth")
    ):
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
    if cand.get("case") == "wrong_type" and cond.get("when") != "wrong_type":
        # A value of the wrong type is judged by the wrong_type rule alone. The
        # other rules read the value (false, 0, a chain), which means nothing here.
        return False
    if cond.get("when") == "model_unknown":
        if cond["layer"] == "default" and not cand.get("synth"):
            return False
        if not _model_unknown(ctx, row):
            return False
    elif cond.get("when") == "replaced_in_source":
        if not cand.get("replaced_in_source"):
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
        if (
            number is None
            or (low is not None and number < low)
            or (high is not None and number > high)
        ):
            return False
    if "name_form" in cond and cand.get("name_form") != cond["name_form"]:
        return False
    becomes = cond.get("becomes")
    if (
        is_dict(becomes)
        and becomes["computed"] == "cap"
        and cond.get("when") != "model_unknown"
        and _model_unknown(ctx, row)
    ):
        # With no model, the model_unknown cap rule alone lowers the row. The
        # other cap rules keep their old answer (nothing lowered).
        return False
    if (
        is_dict(becomes)
        and _computed_becomes(ctx, row, cand, becomes["computed"]) is None
    ):
        return False
    return True


def _drop_shadowed(votes: list[Vote]) -> list[Vote]:
    """Drop a vote that another vote on the same candidate makes redundant.

    Two conditions on one layer with one status, where the second names every
    variable of the first in `if_set` and more, are one answer. The one that
    names more variables is the precise one, so it stays. A condition with a
    `becomes` or a `default_value` always stays, because it carries a value.
    """
    kept: list[Any] = []
    for rule, cond in votes:
        mine = set(cond.get("if_set", []))
        shadowed = (
            "becomes" not in cond
            and "default_value" not in cond
            and any(
                other is not cond
                and other["layer"] == cond["layer"]
                and other["status"] == cond["status"]
                and set(other.get("if_set", [])) > mine
                for _r, other in votes
            )
        )
        if not shadowed:
            kept.append((rule, cond))
    return kept


def votes_for(ctx: _Context, row: Row, cand: Row) -> list[Vote]:
    """Return [(rule, condition)]: each rule's first matching condition.

    The rules come in rules.json order.
    """
    scope = cand.get("rule_scope", row["scope"])
    key = cand.get("rule_key", _rule_key(row["key"]))
    votes: list[Any] = []
    for rule in ctx.rules_for(scope, key):
        for cond in rule["conditions"]:
            if _condition_matches(ctx, row, cand, cond):
                votes.append((rule, cond))
                break
    return _drop_shadowed(votes)


def _status_of(votes: list[Vote]) -> str:
    """The status a candidate takes from its votes if it is not excluded."""
    present = {cond["status"] for _rule, cond in votes}
    for status in WINNER_PRECEDENCE:
        if status in present:
            return status
    return "unknown"


def _becomes_of(
    ctx: _Context, row: Row, cand: Row, votes: list[Vote], status: str
) -> object:
    """The `becomes` of an entry: a computed cap or fallback, or an integer clamp."""
    found: list[Any] = []
    for _rule, cond in votes:
        if cond["status"] != status or "becomes" not in cond:
            continue
        becomes = cond["becomes"]
        if is_dict(becomes):
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


def _row_rules(ctx: _Context, row: Row, cands: list[Row]) -> list[Row]:
    wanted = {(row["scope"], _rule_key(row["key"]))}
    for cand in cands:
        wanted.add(
            (
                cand.get("rule_scope", row["scope"]),
                cand.get("rule_key", _rule_key(row["key"])),
            )
        )
    return [r for r in ctx.rules if (r["scope"], r["key"]) in wanted]


def _row_plan(
    ctx: _Context, row: Row, cands: list[Row]
) -> tuple[list[str], Row | None]:
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
            raise ValueError(
                "rules %s and %s order the layers of %s differently"
                % (
                    rule["rule_id"],
                    next(r["rule_id"] for r in rules if r["layer_order"] == longest),
                    row["key"],
                )
            )
    primary = [
        r
        for r in rules
        if r["scope"] == row["scope"] and r["key"] == _rule_key(row["key"])
    ]
    combines = {r["combine"] for r in (primary or rules)}
    if len(combines) > 1:
        raise ValueError(
            "rules for %s combine in different ways: %s"
            % (row["key"], ", ".join(sorted(combines)))
        )

    def breadth(rule: Row) -> tuple[int, int]:
        layers = {c["layer"] for c in rule["conditions"] if c["status"] == "in_effect"}
        return (len(rule["layer_order"]), len(layers))

    chosen = max(primary or rules, key=breadth)
    return list(longest), chosen


def _sort_key(order: list[str], cand: Row) -> tuple[int, Any, str]:
    layer = cand["layer"]
    index = order.index(layer) if layer in order else len(order)
    return (index, cand["rank"], cand.get("file") or "")


def _select_lowest(order: list[str], eligible: list[Row], rule: Row) -> list[Row]:
    ranked = rule.get("value_order", [])

    def key(cand: Row) -> tuple[Any, ...]:
        value = cand["value"]
        pos = ranked.index(value) if value in ranked else len(ranked)
        return (pos, *_sort_key(order, cand))

    return sorted(eligible, key=key)


def _effective_number(
    ctx: _Context, row: Row, cand: Row, votes: list[Vote]
) -> int | None:
    """The number a window candidate runs as: its clamp (becomes) when it has one."""
    becomes = _becomes_of(ctx, row, cand, votes, _status_of(votes))
    return read_number(becomes if becomes is not None else cand["value"])


def _synth_candidate(ctx: _Context, row: Row) -> Row:
    value = None
    if row["key"] in EFFORT_ROWS and ctx.models.get(row.get("model")):
        value = ctx.models[row["model"]]["default_effort"]
    elif row["scope"] == "agent" and row["key"] == "model":
        value = ctx.main_model_value
    return _candidate("default", None, value, synth=True)


def _synth_default(ctx: _Context, row: Row) -> tuple[Row, list[Vote], str]:
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


def _rank_ceiling(
    ctx: _Context,
    row: Row,
    order: list[str],
    eligible: list[Row],
    votes_of: dict[int, list[Vote]],
    rule: Row,
) -> tuple[list[Row], list[Vote] | None]:
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

    def position(cand: Row) -> int:
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


def _make_entry(
    ctx: _Context,
    row: Row,
    cand: Row,
    status: str,
    votes: list[Vote],
    becomes: object = None,
) -> Row:
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
    if (
        row["key"] == "fallbackModel"
        and status == "lowered"
        and cand.get("chain") is not None
    ):
        # The list that runs, as availableModels does; the written list stays in value.
        entry["merged"] = list(cand["chain"])
    if cand.get("other_file"):
        entry["other_file"] = cand["other_file"]
    if cand.get("field"):
        entry["field"] = cand["field"]
    entry["_votes"] = votes
    entry["_cand"] = cand
    return entry


WINNING = ("in_effect", "lowered", "default", "unknown")


def _winner(entries: list[Row]) -> Row | None:
    for entry in entries:
        if entry["status"] in WINNING:
            return entry
    return None


def _merged_list(managed: Row | None, ranked: list[Row]) -> list[str] | None:
    """The list that runs on a managed_or_merge row, or None when no list does.

    A managed candidate's list applies as it is. Otherwise the lists of the
    candidates in layer order join, with duplicates removed and the first one
    kept. A candidate whose value is not a list adds nothing, and only the
    string items of a list count, because Claude Code reads only names.
    """

    def names(value: list[Any]) -> list[str]:
        return [item for item in value if isinstance(item, str)]

    if managed is not None:
        return names(managed["value"]) if is_list(managed["value"]) else None
    lists = [c["value"] for c in ranked if is_list(c["value"])]
    if not lists:
        return None
    out: list[Any] = []
    seen: set[Any] = set()
    for value in lists:
        for item in names(value):
            if item not in seen:
                seen.add(item)
                out.append(item)
    return out


def resolve_row(ctx: _Context, row: Row, cands: list[Row]) -> list[Row]:
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

    A managed_or_merge row (availableModels) works on layer order. An eligible
    managed candidate wins whole and every other candidate is overridden. With
    none, every eligible candidate stays in the row with its own vote status
    and none is overridden. The first entry carries `merged`, the list that
    runs (see _merged_list). A row with no eligible candidate takes the
    synthesized default as usual.
    """
    order, combine_rule = _row_plan(ctx, row, cands)
    combine = combine_rule["combine"] if combine_rule else "highest_layer"
    order_id = combine_rule["rule_id"] if combine_rule else None
    excluded: list[Any] = []
    eligible: list[Any] = []
    votes_of: dict[int, list[Vote]] = {}
    for cand in cands:
        votes = votes_for(ctx, row, cand)
        statuses = {cond["status"] for _rule, cond in votes}
        status = next((s for s in EXCLUDING if s in statuses), None)
        if status is None and cand.get("replaced_in_source"):
            # The same file's per-model cap replaces this one. It stays in the
            # row as overridden and never joins the lowest-value selection.
            status = "overridden"
        if status:
            excluded.append(_make_entry(ctx, row, cand, status, votes))
        else:
            eligible.append(cand)
            votes_of[id(cand)] = votes

    def entry_for(cand: Row, status: str | None = None) -> Row:
        votes = votes_of[id(cand)]
        status = status or _status_of(votes)
        return _make_entry(
            ctx, row, cand, status, votes, _becomes_of(ctx, row, cand, votes, status)
        )

    if combine == "all":
        entries = [entry_for(c) for c in eligible] + excluded
        return _finish(ctx, entries, order_id, None)
    session_unknown = None
    if combine == "lowest_value":
        ranked = _select_lowest(order, eligible, cast("Row", combine_rule))
    elif combine == "managed_or_merge":
        ranked = sorted(eligible, key=lambda c: _sort_key(order, c))
    elif combine == "ceiling":
        ranked, session_unknown = _rank_ceiling(
            ctx, row, order, eligible, votes_of, cast("Row", combine_rule)
        )
    else:
        ranked = sorted(eligible, key=lambda c: _sort_key(order, c))
    if not ranked and row["key"] in FILE_ROWS:
        return _finish(ctx, excluded, order_id, None)
    if not ranked:
        synth, votes, status = _synth_default(ctx, row)
        entry = _make_entry(
            ctx, row, synth, status, votes, _becomes_of(ctx, row, synth, votes, status)
        )
        return _finish(ctx, [entry, *excluded], order_id, None)
    winner = ranked[0]
    if combine == "managed_or_merge":
        managed = next((c for c in ranked if c["layer"] == "managed"), None)
        if managed is not None:
            head = [entry_for(managed)]
            rest = [entry_for(c, "overridden") for c in ranked if c is not managed]
        else:
            head = [entry_for(c) for c in ranked]
            rest: list[Any] = []
        merged = _merged_list(managed, ranked)
        if merged is not None:
            head[0]["merged"] = merged
        return _finish(ctx, head + rest + excluded, order_id, managed or winner)
    status = _status_of(votes_of[id(winner)])
    if session_unknown is not None:
        # The session's window is unknown, so what the frontmatter lowers is.
        votes_of[id(winner)] = session_unknown
        status = "unknown"
    group: list[Any] = []
    if combine == "highest_layer":
        for peer in ranked[1:]:
            if peer["layer"] != winner["layer"] or peer["rank"] != winner["rank"]:
                continue
            both_unknown = (
                status == "unknown" and _status_of(votes_of[id(peer)]) == "unknown"
            )
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


def _finish(
    ctx: _Context, entries: list[Row], order_id: str | None, winner: Row | None
) -> list[Row]:
    """Add rule ids and the reason to each entry, and drop the private fields.

    rule_id is the first rule that explains the entry and the reason uses it.
    rule_ids holds every rule that voted the entry's final status, then the
    row's order rule (order_id) for a winner or an overridden entry.

    An overridden entry is explained by the order rule, because the row's order
    is why it lost, unless a rule voted overridden with a `when` (a file case
    such as replaced_in_source). That rule explains it instead. rule_ids also
    holds any rule that voted overridden. A
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
            # A vote that names a file case (when) says why this entry lost, so
            # it stands for the entry instead of the order rule.
            cased = [
                r["rule_id"]
                for r, c in votes
                if c["status"] == "overridden" and "when" in c
            ]
            entry["rule_id"] = cased[0] if cased else order_id
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
            if (
                entry["status"] in WINNING
                and order_id is not None
                and order_id not in ids
            ):
                ids = [*ids, order_id]
            entry["rule_ids"] = ids
        entry["reason"] = _reason(ctx, entry, winner_text)
    return entries


class _Slots(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


def _reason(ctx: _Context, entry: Row, winner_text: str) -> str:
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
            slots[slot] = (
                "The shell" if template.startswith("{%s}" % slot) else "the shell"
            )
    return template.format_map(slots)


# --------------------------------------------------------------------------
# Rows


def _env_rows(ctx: _Context) -> list[Row]:
    """Resolve the env blocks and the shell into process env rows."""
    if not ctx.rules_for("main", "env"):
        raise ValueError("the rules have no env-block rule (key env, scope main)")
    names: dict[Any, Any] = {}
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
    block = cli.get("env") if is_dict(cli) else None
    if is_dict(block):
        for name, value in block.items():
            if isinstance(value, (str, int, float)) and not isinstance(value, bool):
                names.setdefault(name, []).append(
                    _candidate("cli", LABEL_CLI, str(value))
                )
    entries: list[Any] = []
    for name in sorted(names):
        row = {"key": "env." + name, "scope": "main", "agent": None, "model": None}
        got = resolve_row(ctx, row, names[name])
        _mark_unreadable_files(ctx, got, row, names[name])
        entries.extend(got)
        winner = _winner(got)
        if winner is not None:
            ctx.env[name] = {
                "value": winner["value"],
                "file": winner["file"],
                "line": winner.get("line"),
                "status": winner["status"],
            }
    return entries


def _agent_file_rows(ctx: _Context) -> tuple[list[Row], dict[str, list[Row]]]:
    """Entries for the agentFile rows, and {agent name: files that load}."""
    by_name: dict[str, list[Row]] = {}
    for f in ctx.agent_files:
        by_name.setdefault(f["name"], []).append(f)
    entries: list[Row] = []
    active: dict[str, list[Row]] = {}
    for name in sorted(by_name):
        files = by_name[name]
        row = {"key": "agentFile", "scope": "agent", "agent": name, "model": None}
        cands = [
            _candidate(
                f["layer"],
                f["file"],
                None,
                f["line"],
                case=f["case"],
                other_file=f["other_file"],
            )
            for f in files
        ]
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


def _unknown_field_entry(ctx: _Context, row: Row, f: Row, field: str) -> Row:
    """The entry for a frontmatter field Claude Code does not read."""
    cand = _candidate(
        f["layer"],
        f["file"],
        None,
        f["lines"].get(field, 1),
        case="unknown_field",
        field=field,
    )
    votes = votes_for(ctx, row, cand)
    statuses = {cond["status"] for _rule, cond in votes}
    status = next((s for s in EXCLUDING if s in statuses), None) or _status_of(votes)
    return _finish(ctx, [_make_entry(ctx, row, cand, status, votes)], None, None)[0]


def _rules_file_rows(ctx: _Context) -> list[Row]:
    cands: list[Any] = []
    for rec in ctx.collected.get("rules_files", []):
        case = None if rec["path"].endswith(".md") else "not_md_file"
        cands.append(
            _candidate(rec["layer"], ctx.show(rec["path"]), None, 1, case=case)
        )
    if not cands:
        return []
    row = {"key": "rulesFile", "scope": "main", "agent": None, "model": None}
    return resolve_row(ctx, row, cands)


def _settings_file_rows(ctx: _Context) -> list[Row]:
    """Entries for the settingsFile row: each settings file that did not parse or read.

    The rules decide each one's status and reason. The entries whose status is
    unknown are kept in ctx.unknown_files, highest layer first, for
    _mark_unreadable_files.
    """
    cands = [
        _candidate(
            rec["layer"],
            ctx.show(rec["path"]),
            None,
            rec["line"] or 1,
            case=rec["status"],
        )
        for rec in ctx.collected.get("settings_files", [])
        if rec["status"] != "ok"
    ]
    if not cands:
        return []
    row = {"key": "settingsFile", "scope": "main", "agent": None, "model": None}
    got = resolve_row(ctx, row, cands)
    ctx.unknown_files = [e for e in got if e["status"] == "unknown"]
    return got


_KEEP = object()  # run() keeps the model the row would carry


def _thinking_model(ctx: _Context) -> str | None:
    """The model the extended thinking row depends on, as a catalog id or None.

    The allowlist can replace the model: a blocked `model` setting is replaced at
    startup and the session starts on the default model, and a blocked alias is
    swapped for a permitted version (model-config.md, Restrict model
    selection). So the row trusts the model only when the allowlist is clear and
    permits the catalog id. The id is checked, not the alias, because any alias
    passes model_permitted by substitution. Needs the availableModels row run.
    """
    if ctx.allowed_unclear or ctx.model_blocks_unclear:
        return None
    if (
        ctx.allowed is not None
        and model_permitted(ctx.main_model, ctx.allowed, ctx.catalog) is not True
    ):
        return None
    return ctx.main_model


def _main_rows(ctx: _Context) -> list[Row]:
    entries: list[Row] = []

    def run(key: str, model: object = _KEEP) -> tuple[list[Row], bool]:
        if model is _KEEP:
            model = ctx.main_model if key in MODEL_ROWS else None
        row: Row = {"key": key, "scope": "main", "agent": None, "model": model}
        cands = settings_candidates(ctx, row) + variable_candidates(ctx, row)
        set_cases(ctx, key, cands)
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
    got, marked = run("availableModels")
    managed = next((src for src in ctx.settings if src["layer"] == "managed"), None)
    ctx.allowed = got[0].get("merged")
    ctx.allowed_unclear = marked or any(e["status"] == "unknown" for e in got)
    ctx.model_blocks_unclear = managed is not None and any(
        key in managed["data"] for key in ("deniedModels", "availableModelsMatch")
    )
    run("alwaysThinkingEnabled", model=_thinking_model(ctx))
    run("fallbackModel")
    entries.extend(_rules_file_rows(ctx))
    return entries


def _ranks_above(ctx: _Context, entry: Row, order: list[str], layer: str) -> bool:
    """True when `layer` ranks above a winning entry.

    The entry's own reason rule says it when its layer_order holds both layers
    (CLAUDE_CODE_SUBAGENT_MODEL_FORCE puts the variable above the frontmatter),
    else the row's order does.
    """
    rule = next((r for r in ctx.rules if r["rule_id"] == entry["rule_id"]), None)
    if (
        rule is not None
        and layer in rule["layer_order"]
        and entry["layer"] in rule["layer_order"]
    ):
        order = rule["layer_order"]
    return (
        layer in order
        and entry["layer"] in order
        and order.index(layer) < order.index(entry["layer"])
    )


def _become_unknown(winner: Row, source: Row) -> None:
    """Make a winning entry Unknown, with the rule ids and reason of `source`.

    It keeps its value, layer, file and line, and it drops `becomes` and
    `merged`.
    """
    winner["status"] = "unknown"
    winner.pop("becomes", None)
    winner.pop("merged", None)
    winner["rule_id"] = source["rule_id"]
    winner["rule_ids"] = list(source["rule_ids"])
    winner["reason"] = source["reason"]


def _mark_unreadable(
    ctx: _Context, entries: list[Row], order: list[str], unreadable: Row | None
) -> None:
    """Make the winner of an agent row Unknown when unreadable frontmatter outranks it.

    `unreadable` is the agentFile entry of a file the reader rejected. Its rule
    ids and reason say why the dashboard can't read the frontmatter, and they
    become the winner's. A row with only a default has the agent layer above it.
    """
    winner = _winner(entries)
    if (
        unreadable is None
        or winner is None
        or not _ranks_above(ctx, winner, order, "agent")
    ):
        return
    _become_unknown(winner, unreadable)


def _mark_unreadable_files(
    ctx: _Context, entries: list[Row], row: Row, cands: list[Row]
) -> bool:
    """Make the winner of a row Unknown when a settings file it reads is unknown.

    This is the same mechanism agents use (_mark_unreadable), applied to the
    settingsFile entries whose status is unknown (an unreadable file, or a
    managed file that is not JSON). Their status, rule ids and reason come from
    rules.json, and the winner takes the ones of the highest-ranked such file.
    The code only decides whether that file could have set the winner's value.
    For a file in layer L, it could when any of these holds:

      a. the row takes the lowest value (combine lowest_value) or merges lists
         (combine managed_or_merge) and L is in the row's order, because any
         file might hold a lower value or add to the list. A managed_or_merge
         row whose winner is on the managed layer is the exception: the managed
         list applies as it is, so only an unreadable managed file counts;
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
    lowest = rule is not None and rule["combine"] in (
        "lowest_value",
        "managed_or_merge",
    )
    managed_wins = (
        rule is not None
        and rule["combine"] == "managed_or_merge"
        and winner["layer"] == "managed"
    )
    via_name = winner.get("via")
    via = ctx.env.get(via_name) if via_name is not None else None
    if winner["layer"] == "env" and via is not None:
        env_covers = via.get("status") == "unknown"
    else:
        env_covers = winner["layer"] == "env" or _ranks_above(ctx, winner, order, "env")
    for source in ctx.unknown_files:
        layer = source["layer"]
        in_order = layer in order
        if managed_wins:
            if in_order and layer == "managed":
                _become_unknown(winner, source)
                return True
            continue
        if (
            (lowest and in_order)
            or (
                in_order
                and (
                    winner["layer"] == "default"
                    or _ranks_above(ctx, winner, order, layer)
                )
            )
            or ("env" in order and env_covers)
        ):
            _become_unknown(winner, source)
            return True
    return False


def _agent_rows(
    ctx: _Context, name: str, files: list[Row], file_entries: list[Row]
) -> list[Row]:
    entries: list[Any] = []
    unreadable = next(
        (
            e
            for f in files
            if f["case"] in UNREADABLE_CASES
            for e in file_entries
            if e["key"] == "agentFile"
            and e.get("agent") == name
            and e["file"] == f["file"]
            and e["status"] == "unknown"
        ),
        None,
    )
    model_row: Row = {"key": "model", "scope": "agent", "agent": name, "model": None}
    cands = frontmatter_candidates(ctx, model_row, files) + variable_candidates(
        ctx, model_row
    )
    got = resolve_row(ctx, model_row, cands)
    marked = _mark_unreadable_files(ctx, got, model_row, cands)
    _mark_unreadable(ctx, got, _row_plan(ctx, model_row, cands)[0], unreadable)
    entries.extend(got)
    winner = _winner(got)
    agent_model = (
        normalize_model(winner["value"], ctx.catalog)[0]
        if winner and not marked
        else None
    )
    for key in ("effort", "autoCompactWindow", "subagentPromptCacheTtl"):
        row: Row = {
            "key": key,
            "scope": "agent",
            "agent": name,
            "model": agent_model if key in MODEL_ROWS else None,
        }
        if key == "autoCompactWindow":
            # The window an agent inherits is the session's, so the default
            # depends on the main model, not on the model of the agent.
            row["default_model"] = ctx.main_model
        cands = (
            frontmatter_candidates(ctx, row, files)
            + settings_candidates(ctx, row)
            + variable_candidates(ctx, row)
        )
        got = resolve_row(ctx, row, cands)
        _mark_unreadable_files(ctx, got, row, cands)
        _mark_unreadable(ctx, got, _row_plan(ctx, row, cands)[0], unreadable)
        entries.extend(got)
    return entries


def resolve(
    inputs: Inputs, rules: dict[str, Any], agent_fields: Iterable[str]
) -> list[Row]:
    """Return the resolution of every row as a list of entry dicts.

    `inputs` holds what the collectors found (see Inputs). `rules` is the
    rules.json document (see load_rules). `agent_fields` is the list of
    frontmatter fields Claude Code reads (see load_agent_fields). resolve opens
    no file. Entries hold key, value, status, layer, file and scope always, and
    line, agent, model, via, path, raw, becomes, other_file, field and merged
    when they apply, then rule_id, rule_ids and reason.

    merged is only on the first entry of an availableModels row: the list that
    runs. With a managed list it is that list. Otherwise it joins the lists of
    the files in layer order, duplicates removed, first one kept. A default
    entry has no merged. A fallbackModel entry whose chain Claude Code cuts has
    status lowered and becomes holding the names that run, joined by ", " (or
    "nothing"). It also has merged, the kept list that runs (empty when every
    entry is dropped); its value stays the list as written.
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


def _row_of(entry: Row) -> tuple[str, str, str | None]:
    return (entry["key"], entry["scope"], entry.get("agent"))


def _row_text(row: tuple[str, str, str | None]) -> str:
    key, scope, agent = row
    return "%s/%s%s" % (key, scope, "/" + agent if agent else "")


def _differences(expected: Row, got: Row) -> list[str]:
    return [f for f in expected if f not in got or got[f] != expected[f]]


def _pair(expected_list: list[Row], got_list: list[Row]) -> dict[int, int]:
    """Pair expected entries with runner entries one to one.

    Returns {expected index: got index}.
    """
    match: dict[int, int] = {}
    taken: dict[int, int] = {}

    def try_expected(i: int, seen: set[int]) -> bool:
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


def compare(entries: list[Row], expected: Row) -> list[str]:
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
    messages: list[Any] = []
    want: dict[Any, Any] = {}
    for item in expected.get("expect", []):
        want.setdefault(_row_of(item), []).append(item)
    have: dict[Any, Any] = {}
    for entry in entries:
        have.setdefault(_row_of(entry), []).append(entry)
    for row, items in want.items():
        got_list = have.get(row, [])
        where = "%s: row %s" % (name, _row_text(row))
        paired = _pair(items, got_list)
        if len(items) != len(got_list):
            messages.append(
                "%s: expected %d entries, got %d" % (where, len(items), len(got_list))
            )
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
                messages.append(
                    "%s: no entry for %s" % (where, json.dumps(item, sort_keys=True))
                )
                continue
            for field in best[1]:
                messages.append(
                    "%s: %s expected %s, got %s"
                    % (
                        where,
                        field,
                        json.dumps(item[field]),
                        json.dumps(best[2][field]) if field in best[2] else "nothing",
                    )
                )
    seen: set[Any] = set()
    for row in want:
        for entry in have.get(row, []):
            seen.update(entry.get("rule_ids", []))
    for rule_id in expected.get("rule_ids", []):
        if rule_id not in seen:
            messages.append(
                "%s: rule_ids: %s is in no rule_ids of the rows the file names"
                % (name, rule_id)
            )
    return messages


# --------------------------------------------------------------------------
# Command line


def run_fixtures(folder: str, out: TextIO | None = None) -> int:
    """Run every fixture folder in `folder`. Returns the number that failed."""
    stream = out or sys.stdout
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
        except Exception as exc:  # noqa: BLE001 - a broken fixture should not stop the rest
            messages = ["%s: %s: %s" % (name, exc.__class__.__name__, exc)]
        if messages:
            failed += 1
            stream.write("%s: FAIL\n" % name)
            for line in messages:
                stream.write("  %s\n" % line)
        else:
            stream.write("%s: ok\n" % name)
    return failed


def main(argv: list[str]) -> int:
    """Run the fixtures in the folder named on the command line, or the default one."""
    folder = argv[1] if len(argv) > 1 else FIXTURES_PATH
    return 1 if run_fixtures(folder) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
