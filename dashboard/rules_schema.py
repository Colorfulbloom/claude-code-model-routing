"""Schema check for dashboard/rules.json. Standard library only.

rules.json holds every precedence and validity rule the dashboard applies, as
data. The resolver reads it and never hard-codes a rule. This module is the
schema: it lists the allowed values and checks each entry.

Run it directly to check the real file:

    /usr/bin/python3 dashboard/rules_schema.py [path/to/rules.json]

Top level (these three fields, and the optional variables list):

    {"schema_version": 3, "models": [<model>, ...], "rules": [<rule>, ...],
     "variables": [<variable>, ...]}

models is the model catalog: a non-empty list in release order, oldest first.
A model:

    id              unique, lowercase words joined by hyphens (claude-opus-5-5)
    display_name    the name shown on screen ("Opus 5.5"): a non-empty string,
                    unique across the catalog
    aliases         list, may be empty, of names that mean this model (opus).
                    Each alias is lowercase letters only, and no alias may
                    appear on two models.
    effort_levels   list, may be empty, of the effort levels the model offers.
                    Each is one of EFFORT_LEVELS, with no repeats, in that
                    order (low first).
    default_effort  null when effort_levels is empty, else one of effort_levels
    quotes, experiment, confidence
                    the source of the entry, with the same rules as a rule

variables is optional. It lists the environment variables that feed a row, so a
condition can name one (`via`, `if_set`) and the resolver never hard-codes a
name. A variable:

    name          ^[A-Z][A-Z0-9_]*$, unique across the list
    value         null when the variable's own value is the candidate value, or
                  a non-empty string when the variable counts as a fixed value
                  (such as "5m" for FORCE_PROMPT_CACHING_5M). The variable
                  counts when it is set to any non-empty value.
    rows          list, may be empty (an empty list is a switch, named only by
                  `if_set`) of {key, scope, layer}: key is a setting key, scope
                  is one of SCOPES and layer is env or default. No item repeats.
                  Some rule must have that key and scope, and its layer_order
                  must hold that layer.

The order of the list is precedence inside one layer for one row: an earlier
variable beats a later one.

A rule:

    rule_id       unique, lowercase words joined by hyphens
    key           the setting, as a dotted path (effortLevel, experimental.cacheTtl),
                  or a kind of file the dashboard lists (agentFile, rulesFile, settingsFile)
    scope         main, agent or model
    layer_order   layer ids, highest precedence first
    combine       how the candidates for the key combine. highest_layer: the
                  first layer in layer_order with a valid candidate wins.
                  lowest_value: the lowest candidate by `value_order` wins,
                  wherever it is set. all: every candidate loads and none
                  wins, such as rules files, which are listed with their layer.
                  ceiling: a candidate in a layer before `ceiling_layer` wins
                  as in highest_layer. Otherwise the `ceiling_layer` candidate
                  wins when its number is lower than the best candidate below
                  it, or when none is below. If not, the candidate below wins.
    ceiling_layer only with combine ceiling, and then required: a layer in
                  layer_order that is neither the first nor the last
    value_order   only with combine lowest_value, and then required: a
                  non-empty list of unique non-empty strings, lowest first.
    conditions    list of {layer, models, [values], [plans], [when], [via],
                  [if_set], [range], [name_form], status, [becomes],
                  [default_value]}; each one says what status a
                  candidate set in `layer` yields when the model is in `models`
                  and, if given, the raw value is in `values`, the plan is in
                  `plans`, the file case is `when`, and so on for the fields
                  below. `values` is a non-empty
                  list of unique strings. The resolver takes the first
                  condition that matches, so list the narrow ones first.
    reason        the sentence shown on screen, with {slot} placeholders
    quotes        list, may be empty, of {doc_url, quote}: doc_url is an https
                  link to the doc section, quote is verbatim doc text that
                  backs the rule. Both are required in each item, and no
                  other key is allowed. No two items may be identical.
    experiment    path to an experiment record, relative to this folder, or null
    confidence    documented, tested or assumed
    verified_on   {claude_version: "2.1.302", date: "2026-10-29"}

A condition's `models` is a non-empty list. Each item is one of:

    "*"                 any model; it stands alone in the list
    "<model id>"        that model
    {"from": "<id>"}    that model and every model after it in the catalog
                        ("this model and later ones")

With a catalog, every plain id and every `from` id must be in it, and no model
may be covered by two items (a repeated id, or a plain id inside a `from` range).
Without a catalog, only a repeated plain id or a repeated `from` id is refused.
Use expand_models(models, catalog_ids) to get the ids a list covers; it raises
ValueError for any item it cannot read.

A condition's `via` is a variable name from the top-level variables list. The
condition matches only a candidate that came through that variable. It is only
for a condition on the env or default layer, and the variable must list a row
with the rule's key, scope and the condition's layer. Without a variables list,
any `via` is an error.

A condition's `if_set` is a non-empty list of unique variable names, all from
the variables list (switches included). The condition matches only when every
one of those variables is set to a non-empty value.

A condition's `range` is an object with `min`, `max` or both, as integers (not
booleans), with min no more than max, and no other key. The condition matches
only a value that reads as a number: a JSON integer, or a string whose leading
decimal digits are read as the integer, so "200k" reads as 200, which is how
2.1.302 ran it (experiment record 2026-10-29-auto-compact-window.json, a13).
"abc" and "" do not read as a number. Bounds are inclusive.

A condition's `name_form` is one of NAME_FORMS. It matches a modelSettings
candidate whose entry name has that form for the model, and only rules whose key
is modelSettings or starts with "modelSettings." may use it. In one file, entries
for one model rank by NAME_FORMS order, canonical first. Only canonical over
alias is tested (experiment record 2026-10-29-model-settings-name-matching.json,
cases ms-canon-and-alias-canon-first and ms-alias-and-canon-alias-first). The
other forms rank by the same order on an assumption.

A condition's `becomes` is the value a Lowered candidate runs as. It is either
a non-empty string, an object with exactly one key, `computed`, or, only with a
`range`, an integer (a clamp, not a boolean). A string must
be one of the rule's `value_order` when it has one. Without a value_order, a
rule on an effort key (effortLevel, effort, maxEffortLevel, last dotted part)
needs one of EFFORT_LEVELS, and any other key takes any non-empty string.

    {"computed": "cap"}       the cap in effect for the model (the
                              maxEffortLevel resolution). The condition matches
                              only when the value is above that cap.
    {"computed": "fallback"}  the highest level in the model's catalog
                              effort_levels at or below the value. The
                              condition matches only when the model's
                              effort_levels is not empty and lacks the value.

A string or computed `becomes` is only for the lowered status, and lowered
always needs it. An integer `becomes` needs a `range` and is allowed with the
lowered or in_effect status.

A condition's `plans` is a non-empty list of unique PLANS items. It matches the
`plan` field of the dashboard config: subscription, api_key or cloud_provider,
and unset when the config has no `plan` field. Without `plans`, any plan
matches.

A condition's `when` is one of WHEN_CASES. It names the file case the condition
covers, for keys about files rather than values (agentFile, rulesFile,
settingsFile):

    same_name_in_layer  two or more files in the layer declare the same name
    not_md_file         the file name does not end in .md
    no_name             the frontmatter has no name
    no_description      the frontmatter has a name but no description
    parse_error         the frontmatter does not parse and Claude Code does not
                        load the file. Experiment 2026-10-29-agent-files.json
                        (f2) shows this for a tab in an indent, an unterminated
                        quote and a bad list indent.
    reader_rejected_but_loads
                        the dashboard's strict reader (agent_frontmatter.py)
                        rejects the frontmatter, but Claude Code loads the file.
                        f2 shows this for an unclosed [, a second colon in a
                        value and a repeated key. The status is unknown, because
                        the reader cannot say which values Claude Code took.
    reader_rejected_untested
                        the strict reader rejects the frontmatter with a kind f2
                        did not test, so nobody knows whether Claude Code loads
                        the file. The status is unknown, as above.
    unknown_field       the frontmatter sets a field Claude Code does not read
    unparsed            a settings file (settingsFile) that is not valid JSON, or
                        whose top level is not an object
    unreadable          a settings file (settingsFile) that exists but cannot be
                        read, for example a permission error. The dashboard
                        cannot say what the file sets, so the status is unknown.
    model_unknown       the row's model is unknown, so a default cannot be named.
                        A condition on any layer may use it.
    replaced_in_source  a maxEffortLevel set at the top level of a settings file
                        that the same file replaces for this model with its own
                        modelSettings maxEffortLevel. Needs status overridden.

A condition's `default_value` is only for the default status: the value the
default yields, as a non-empty string. With a value_order or an effort key it
must be one of those values, as for `becomes`.

Every rule needs a reason. Documented and Tested rules also need a source: at
least one doc quote in `quotes`, or an experiment record. Documented needs at
least one quote; Tested needs the record. An Assumed rule may have neither,
because Assumed means no source backs it yet. Each quote item is checked on its
own, so a bad item is reported as quotes[1]: ... with its index. A model entry
follows the same source rules.

An experiment record (JSON):

    {"date": "YYYY-MM-DD", "claude_version": "x.y.z",
     "ran": "<what was run>", "result": "<what came back>"}
"""
import datetime
import json
import os
import re
import string
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "rules.json")
SCHEMA_VERSION = 3

# Data name -> the word on screen. The owner fixed these seven on October 29.
STATUS_WORDS = {
    "in_effect": "In effect",
    "overridden": "Overridden",
    "ignored": "Ignored",
    "invalid": "Invalid",
    "lowered": "Lowered",
    "default": "Default",
    "unknown": "Unknown",
}

# Data name -> the word on screen. Fixed by the owner on October 29.
CONFIDENCE_WORDS = {
    "documented": "Documented",
    "tested": "Tested",
    "assumed": "Assumed",
}

SCOPES = ("main", "agent", "model")

# Layers a variable row can name: the environment, or the default a variable
# switches on (ENABLE_PROMPT_CACHING_1H).
VARIABLE_LAYERS = ("env", "default")

# Forms of a modelSettings entry name, in rank order inside one file (canonical
# first). Only canonical over alias is tested.
NAME_FORMS = ("canonical", "alias", "dated", "context_1m", "provider")

# Places a value can be set. The order between them is per rule (layer_order),
# because the discovery tickets settle it key by key.
#   cli      a file passed with --settings, which ranks with the settings files
#   flag     a session flag such as --model, --effort or --autocompact
#   env      the process environment: the shell, overwritten by settings env
#            blocks, which the resolver works out first (rule env-block-order)
#   plugin   a file shipped by an enabled plugin, such as a plugin's agents/
#   default  Claude Code's own value, or the main model for an agent
LAYERS = ("managed", "cli", "flag", "env", "local", "project", "user", "plugin", "agent",
          "default")

# Slots a reason template may use.
REASON_SLOTS = ("key", "value", "file", "layer", "model", "agent", "winner", "becomes",
                "other_file")

# Effort levels a model can offer, lowest first.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

# How the candidates for a key combine into one winner.
COMBINE_MODES = ("highest_layer", "lowest_value", "all", "ceiling")

# Values of the dashboard config's `plan` field a condition can match. unset
# matches a config with no `plan` field.
PLANS = ("subscription", "api_key", "cloud_provider", "unset")

# File cases a condition's `when` can name.
WHEN_CASES = ("same_name_in_layer", "not_md_file", "no_name", "no_description",
              "parse_error", "reader_rejected_but_loads", "reader_rejected_untested",
              "unknown_field", "unparsed", "unreadable", "model_unknown",
              "replaced_in_source")

# What a computed `becomes` works out.
COMPUTED_BECOMES = ("cap", "fallback")

# Last dotted part of a rule key whose values are effort levels.
EFFORT_KEYS = ("effortLevel", "effort", "maxEffortLevel")

ANY_MODEL = "*"

TOP_FIELDS = {"schema_version", "models", "rules"}
TOP_OPTIONAL_FIELDS = {"variables"}
VARIABLE_FIELDS = {"name", "value", "rows"}
VARIABLE_ROW_FIELDS = {"key", "scope", "layer"}
RANGE_FIELDS = {"min", "max"}
MODEL_FIELDS = {
    "id", "display_name", "aliases", "effort_levels", "default_effort",
    "quotes", "experiment", "confidence",
}
RULE_FIELDS = {
    "rule_id", "key", "scope", "layer_order", "combine", "conditions", "reason",
    "quotes", "experiment", "confidence", "verified_on",
}
RULE_OPTIONAL_FIELDS = {"value_order", "ceiling_layer"}
CONDITION_REQUIRED = {"layer", "models", "status"}
CONDITION_FIELDS = CONDITION_REQUIRED | {"values", "becomes", "plans", "when", "default_value",
                                         "via", "if_set", "range", "name_form"}
VERIFIED_FIELDS = {"claude_version", "date"}
EXPERIMENT_FIELDS = {"date", "claude_version", "ran", "result"}

RULE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MODEL_ID_RE = RULE_ID_RE
ALIAS_RE = re.compile(r"^[a-z]+$")
VARIABLE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _text(value):
    return isinstance(value, str) and value.strip() != ""


def _check_date(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        return False
    return re.match(r"^\d{4}-\d{2}-\d{2}$", value) is not None


def reason_slots(template):
    """Return the slot names in a reason template. Raises ValueError on bad braces."""
    names = []
    for _literal, field, spec, conv in string.Formatter().parse(template):
        if field is None:
            continue
        if field == "" or spec or conv:
            raise ValueError("slots are plain {name}, no positional, format or conversion")
        names.append(field)
    return names


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_variables(variables):
    """Check the top-level `variables` list. Returns a list of error strings.

    The cross-check against the rules (some rule has each row's key and scope
    and holds its layer) is in validate().
    """
    if not isinstance(variables, list):
        return ["variables must be a list"]
    errors = []
    seen = set()
    for i, var in enumerate(variables):
        if not isinstance(var, dict):
            errors.append("variables[%d]: not an object" % i)
            continue
        name = var.get("name")
        label = name if isinstance(name, str) else "variables[%d]" % i

        def err(msg, label=label):
            errors.append("variable %s: %s" % (label, msg))

        for field in sorted(VARIABLE_FIELDS - set(var)):
            err("missing field %s" % field)
        for field in sorted(set(var) - VARIABLE_FIELDS):
            err("unknown field %s" % field)
        if "name" in var:
            if not (isinstance(name, str) and VARIABLE_NAME_RE.match(name)):
                err("name must be capital letters, digits and underscores, starting with a letter")
            elif name in seen:
                err("duplicate name")
            if isinstance(name, str):
                seen.add(name)
        if "value" in var and var["value"] is not None and not _text(var["value"]):
            err("value must be null or a non-empty string")
        if "rows" in var:
            rows = var["rows"]
            if not isinstance(rows, list):
                err("rows must be a list")
                continue
            kept = []
            for j, row in enumerate(rows):
                if not isinstance(row, dict):
                    err("rows[%d]: not an object" % j)
                    continue
                for field in sorted(VARIABLE_ROW_FIELDS - set(row)):
                    err("rows[%d]: missing field %s" % (j, field))
                for field in sorted(set(row) - VARIABLE_ROW_FIELDS):
                    err("rows[%d]: unknown field %s" % (j, field))
                if "key" in row and not (isinstance(row["key"], str) and KEY_RE.match(row["key"])):
                    err("rows[%d]: key must be a setting name or dotted path" % j)
                if "scope" in row and row["scope"] not in SCOPES:
                    err("rows[%d]: scope must be one of %s" % (j, ", ".join(SCOPES)))
                if "layer" in row and row["layer"] not in VARIABLE_LAYERS:
                    err("rows[%d]: layer must be one of %s" % (j, ", ".join(VARIABLE_LAYERS)))
                if set(row) == VARIABLE_ROW_FIELDS:
                    if row in kept:
                        err("rows[%d]: repeats an earlier row" % j)
                    kept.append(row)
    return errors


def variable_index(variables):
    """Return {name: {(key, scope, layer), ...}} for the well-formed variables.

    Pass it to check_rule as `variables`. A bad entry is skipped here, because
    check_variables reports it. A switch maps to an empty set.
    """
    index = {}
    if not isinstance(variables, list):
        return index
    for var in variables:
        if not (isinstance(var, dict) and isinstance(var.get("name"), str)):
            continue
        rows = set()
        if isinstance(var.get("rows"), list):
            for row in var["rows"]:
                if (isinstance(row, dict) and set(row) == VARIABLE_ROW_FIELDS
                        and all(isinstance(row[f], str) for f in VARIABLE_ROW_FIELDS)):
                    rows.add((row["key"], row["scope"], row["layer"]))
        index.setdefault(var["name"], rows)
    return index


def check_experiment(path):
    """Check one experiment record file. Returns a list of error strings."""
    try:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["cannot read experiment record %s: %s" % (path, exc)]
    if not isinstance(record, dict):
        return ["experiment record %s is not an object" % path]
    errors = []
    for field in sorted(EXPERIMENT_FIELDS - set(record)):
        errors.append("experiment record %s has no %s" % (path, field))
    if "date" in record and not _check_date(record["date"]):
        errors.append("experiment record %s: date must be YYYY-MM-DD" % path)
    if "claude_version" in record and not (
            isinstance(record["claude_version"], str)
            and VERSION_RE.match(record["claude_version"])):
        errors.append("experiment record %s: claude_version must look like 2.1.302" % path)
    for field in ("ran", "result"):
        if field in record and not _text(record[field]):
            errors.append("experiment record %s: %s is empty" % (path, field))
    return errors


QUOTE_FIELDS = {"doc_url", "quote"}


def _check_quotes(quotes, err):
    """Check a `quotes` list. Returns True when it holds at least one valid item."""
    if not isinstance(quotes, list):
        err("quotes must be a list")
        return False
    ok = bool(quotes)
    seen = []
    for i, item in enumerate(quotes):
        def qerr(msg, i=i):
            err("quotes[%d]: %s" % (i, msg))
        if not isinstance(item, dict):
            qerr("must be an object with doc_url and quote")
            ok = False
            continue
        bad = False
        for field in sorted(QUOTE_FIELDS - set(item)):
            qerr("missing field %s" % field)
            bad = True
        for field in sorted(set(item) - QUOTE_FIELDS):
            qerr("unknown field %s" % field)
            bad = True
        if "doc_url" in item:
            url = item["doc_url"]
            if not _text(url) or not url.startswith("https://"):
                qerr("doc_url must be an https link")
                bad = True
        if "quote" in item and not _text(item["quote"]):
            qerr("quote must be a non-empty string")
            bad = True
        if not bad:
            if item in seen:
                qerr("repeats an earlier item")
                bad = True
            seen.append(item)
        ok = ok and not bad
    return ok


def _check_source(entry, noun, err, base_dir):
    """Check the quotes, experiment and confidence fields of a rule or model.

    `noun` ("rule" or "model") is used in the confidence messages. `err` takes a
    message and records it against the entry.
    """
    experiment = entry.get("experiment")
    has_quote = False
    if "quotes" in entry:
        has_quote = _check_quotes(entry["quotes"], err)
    if "experiment" in entry and experiment is not None and not _text(experiment):
        err("experiment must be a non-empty string or null")
    if _text(experiment):
        if os.path.isabs(experiment) or ".." in experiment.split("/"):
            err("experiment must be a path inside the dashboard folder")
        else:
            for msg in check_experiment(os.path.join(base_dir, experiment)):
                err(msg)
    if (not has_quote and not _text(experiment)
            and entry.get("confidence") != "assumed"):
        err("no source: needs a doc quote or an experiment record")

    confidence = entry.get("confidence")
    if "confidence" in entry:
        if not isinstance(confidence, str) or confidence not in CONFIDENCE_WORDS:
            err("confidence must be one of %s" % ", ".join(CONFIDENCE_WORDS))
        elif confidence == "documented" and not has_quote:
            err("documented %s needs at least one quote" % noun)
        elif confidence == "tested" and not _text(experiment):
            err("tested %s needs an experiment record" % noun)


def check_model(model, base_dir=HERE):
    """Check one model catalog entry. Returns a list of error strings.

    Cross-entry checks (unique ids, aliases on two models) are in validate().
    """
    if not isinstance(model, dict):
        return ["model is not an object"]
    mid = model.get("id") if isinstance(model.get("id"), str) else "?"
    errors = []

    def err(msg):
        errors.append("model %s: %s" % (mid, msg))

    for field in sorted(MODEL_FIELDS - set(model)):
        err("missing field %s" % field)
    for field in sorted(set(model) - MODEL_FIELDS):
        err("unknown field %s" % field)

    if "id" in model and not (isinstance(model["id"], str) and MODEL_ID_RE.match(model["id"])):
        err("id must be lowercase words joined by hyphens")

    if "display_name" in model and not _text(model["display_name"]):
        err("display_name must be a non-empty string")

    if "aliases" in model:
        aliases = model["aliases"]
        if not isinstance(aliases, list):
            err("aliases must be a list")
        else:
            for alias in aliases:
                if not (isinstance(alias, str) and ALIAS_RE.match(alias)):
                    err("alias %r must be lowercase letters only" % (alias,))
            if len(set(map(str, aliases))) != len(aliases):
                err("aliases repeat a name")

    levels = model.get("effort_levels")
    levels_ok = False
    if "effort_levels" in model:
        if not isinstance(levels, list):
            err("effort_levels must be a list")
        else:
            unknown = [lv for lv in levels if not (isinstance(lv, str) and lv in EFFORT_LEVELS)]
            for lv in unknown:
                err("unknown effort level %r in effort_levels" % (lv,))
            if len(set(map(str, levels))) != len(levels):
                err("effort_levels repeats a level")
            elif not unknown:
                ranks = [EFFORT_LEVELS.index(lv) for lv in levels]
                if ranks != sorted(ranks):
                    err("effort_levels out of order, must run %s" % ", ".join(EFFORT_LEVELS))
            levels_ok = True

    if "default_effort" in model:
        default = model["default_effort"]
        if levels_ok and not levels:
            if default is not None:
                err("default_effort must be null when effort_levels is empty")
        elif levels_ok:
            if not (isinstance(default, str) and default in levels):
                err("default_effort must be one of effort_levels")
        elif default is not None and not (isinstance(default, str) and default in EFFORT_LEVELS):
            err("default_effort must be null or an effort level")

    _check_source(model, "model", err, base_dir)
    return errors


def check_rule(rule, base_dir=HERE, model_ids=None, variables=None):
    """Check one rule entry. Returns a list of error strings.

    model_ids is the list of catalog ids. With it, every model a condition names
    must be in it. With None, only that membership check is skipped.

    variables is variable_index(...) of the document's variables list, or None
    when the document has none. A condition's `via` and `if_set` are checked
    against it, and with None any of them is an error.
    """
    if not isinstance(rule, dict):
        return ["rule is not an object"]
    rid = rule.get("rule_id") if isinstance(rule.get("rule_id"), str) else "?"
    errors = []

    def err(msg):
        errors.append("%s: %s" % (rid, msg))

    for field in sorted(RULE_FIELDS - set(rule)):
        err("missing field %s" % field)
    for field in sorted(set(rule) - RULE_FIELDS - RULE_OPTIONAL_FIELDS):
        err("unknown field %s" % field)

    if "rule_id" in rule and not (isinstance(rule["rule_id"], str)
                                  and RULE_ID_RE.match(rule["rule_id"])):
        err("rule_id must be lowercase words joined by hyphens")
    if "key" in rule and not (isinstance(rule["key"], str) and KEY_RE.match(rule["key"])):
        err("key must be a setting name or dotted path")
    if "scope" in rule and rule["scope"] not in SCOPES:
        err("scope must be one of %s" % ", ".join(SCOPES))

    order = rule.get("layer_order")
    if "layer_order" in rule:
        if not isinstance(order, list) or not order:
            err("layer_order must be a non-empty list")
            order = []
        else:
            for layer in order:
                if layer not in LAYERS:
                    err("unknown layer %r in layer_order" % (layer,))
            if len(set(map(str, order))) != len(order):
                err("layer_order repeats a layer")
    else:
        order = []

    combine = rule.get("combine")
    if "combine" in rule and not (isinstance(combine, str) and combine in COMBINE_MODES):
        err("combine must be one of %s" % ", ".join(COMBINE_MODES))
    if combine == "lowest_value" and "value_order" not in rule:
        err("combine lowest_value needs value_order")
    if "ceiling_layer" in rule:
        ceiling_layer = rule["ceiling_layer"]
        if combine != "ceiling":
            err("ceiling_layer is only for combine ceiling")
        elif ceiling_layer not in order:
            err("ceiling_layer %r is not in layer_order" % (ceiling_layer,))
        elif ceiling_layer in (order[0], order[-1]):
            err("ceiling_layer must not be the first or last layer in layer_order")
    elif combine == "ceiling":
        err("combine ceiling needs ceiling_layer")
    if "value_order" in rule:
        value_order = rule["value_order"]
        if combine != "lowest_value":
            err("value_order is only for combine lowest_value")
        elif not (isinstance(value_order, list) and value_order
                  and all(_text(v) for v in value_order)):
            err("value_order must be a non-empty list of non-empty strings")
        elif len(set(value_order)) != len(value_order):
            err("value_order repeats a value")

    levels = None
    value_order = rule.get("value_order")
    if (combine == "lowest_value" and isinstance(value_order, list)
            and all(isinstance(v, str) for v in value_order)):
        levels = tuple(value_order)
    elif "value_order" not in rule and isinstance(rule.get("key"), str) \
            and rule["key"].split(".")[-1] in EFFORT_KEYS:
        levels = EFFORT_LEVELS

    conditions = rule.get("conditions")
    if "conditions" in rule:
        if not isinstance(conditions, list) or not conditions:
            err("conditions must be a non-empty list")
        else:
            for i, cond in enumerate(conditions):
                errors.extend("%s: condition %d: %s" % (rid, i, m)
                              for m in _check_condition(cond, order, model_ids, levels,
                                                        rule.get("key"), rule.get("scope"),
                                                        variables))

    reason = rule.get("reason")
    if "reason" in rule:
        if not _text(reason):
            err("reason is empty")
        else:
            try:
                for slot in reason_slots(reason):
                    if slot not in REASON_SLOTS:
                        err("reason uses unknown slot {%s}" % slot)
            except ValueError as exc:
                err("reason template: %s" % exc)

    _check_source(rule, "rule", err, base_dir)

    verified = rule.get("verified_on")
    if "verified_on" in rule:
        if not isinstance(verified, dict):
            err("verified_on must be an object")
        else:
            for field in sorted(VERIFIED_FIELDS - set(verified)):
                err("verified_on has no %s" % field)
            for field in sorted(set(verified) - VERIFIED_FIELDS):
                err("verified_on has unknown field %s" % field)
            ver = verified.get("claude_version")
            if "claude_version" in verified and not (isinstance(ver, str) and VERSION_RE.match(ver)):
                err("verified_on.claude_version must look like 2.1.302")
            if "date" in verified and not _check_date(verified["date"]):
                err("verified_on.date must be YYYY-MM-DD")
    return errors


def expand_models(models, catalog_ids):
    """Return the model ids a condition's `models` list covers.

    ["*"] returns ["*"]. {"from": X} covers X and every model after X in
    catalog_ids (release order). Plain ids come back as given. The result keeps
    first-seen order with no repeats. Raises ValueError for a `from` id that is
    not in the catalog, and for any item that is not a non-empty string or an
    object with exactly one key, from, holding a string. It never raises
    KeyError or TypeError.
    """
    if not isinstance(models, (list, tuple)):
        raise ValueError("models must be a list")
    out = []
    for item in models:
        if isinstance(item, str) and item == ANY_MODEL:
            return [ANY_MODEL]
        if isinstance(item, dict):
            if set(item) != {"from"} or not isinstance(item["from"], str):
                raise ValueError("models object must be {\"from\": <model id>}, got %r" % (item,))
            start = item["from"]
            if start not in catalog_ids:
                raise ValueError("unknown model %r" % (start,))
            covered = list(catalog_ids[list(catalog_ids).index(start):])
        elif _text(item):
            covered = [item]
        else:
            raise ValueError("models item %r must be a model id or a from object" % (item,))
        for mid in covered:
            if mid not in out:
                out.append(mid)
    return out


def _check_models_list(models, model_ids):
    if not (isinstance(models, list) and models):
        return ["models must be a non-empty list of model ids, \"from\" objects, or [\"*\"]"]
    errors = []
    for item in models:
        if isinstance(item, dict):
            if set(item) != {"from"}:
                errors.append("models object must have exactly one key, from")
                continue
            ident, label = item["from"], "from"
        elif _text(item):
            if item == ANY_MODEL:
                continue
            ident, label = item, "model"
        else:
            errors.append("models item %r must be a model id, a from object, or \"*\"" % (item,))
            continue
        if not _text(ident) or ident == ANY_MODEL:
            errors.append("models from must be a model id")
        elif model_ids is not None and ident not in model_ids:
            errors.append("unknown model %r in models" % (ident,))
    if ANY_MODEL in models and len(models) > 1:
        errors.append("models: \"*\" stands alone")
    errors.extend(_overlap_errors(models, model_ids))
    return errors


def _overlap_errors(models, model_ids):
    """Report a model covered by two items of a models list, or by one item twice.

    With a catalog, each item is expanded and a shared id is an overlap. Without
    one, only an identical plain id or an identical `from` id can be told.
    """
    if ANY_MODEL in models:
        return []
    errors = []
    if model_ids is not None:
        covered = {}
        for i, item in enumerate(models):
            try:
                ids = expand_models([item], model_ids)
            except ValueError:
                continue
            for mid in ids:
                if mid in covered:
                    msg = "models repeat or overlap on %s" % mid
                    if msg not in errors:
                        errors.append(msg)
                covered.setdefault(mid, i)
        return errors
    seen = []
    for item in models:
        if isinstance(item, dict):
            key = ("from", item.get("from")) if set(item) == {"from"} else None
        elif _text(item):
            key = ("model", item)
        else:
            key = None
        if key is None or not _text(key[1]):
            continue
        if key in seen:
            msg = "models repeat %s" % key[1]
            if msg not in errors:
                errors.append(msg)
        seen.append(key)
    return errors


def _check_condition(cond, order, model_ids=None, levels=None, key=None, scope=None,
                     variables=None):
    """Check one condition. `levels` is the tuple a plain `becomes` must be in, or None.

    key and scope are the rule's, for the `via` row check and `name_form`.
    variables is variable_index(...) or None when the document has no variables list.
    """
    if not isinstance(cond, dict):
        return ["not an object"]
    errors = []
    for field in sorted(CONDITION_REQUIRED - set(cond)):
        errors.append("missing field %s" % field)
    for field in sorted(set(cond) - CONDITION_FIELDS):
        errors.append("unknown field %s" % field)
    if "layer" in cond and cond["layer"] not in order:
        errors.append("layer %r is not in layer_order" % (cond["layer"],))
    if "models" in cond:
        errors.extend(_check_models_list(cond["models"], model_ids))
    if "values" in cond:
        values = cond["values"]
        if not (isinstance(values, list) and values):
            errors.append("values must be a non-empty list")
        else:
            if not all(isinstance(v, str) for v in values):
                errors.append("values must all be strings")
            elif len(set(values)) != len(values):
                errors.append("values repeat a value")
    status = cond.get("status")
    if "status" in cond and not (isinstance(status, str) and status in STATUS_WORDS):
        errors.append("status must be one of %s" % ", ".join(STATUS_WORDS))
    if "range" in cond:
        errors.extend(_check_range(cond["range"]))
    if "becomes" in cond:
        becomes = cond["becomes"]
        if _is_int(becomes):
            if "range" not in cond:
                errors.append("an integer becomes needs a range")
            if status not in ("lowered", "in_effect"):
                errors.append("an integer becomes is only for a lowered or in_effect status")
        elif status != "lowered":
            errors.append("becomes is only for a lowered status")
        if _is_int(becomes):
            pass
        elif isinstance(becomes, dict):
            if set(becomes) != {"computed"}:
                errors.append("becomes object must have exactly one key, computed")
            elif not (isinstance(becomes["computed"], str)
                      and becomes["computed"] in COMPUTED_BECOMES):
                errors.append("becomes computed must be one of %s" % ", ".join(COMPUTED_BECOMES))
        elif not _text(becomes):
            errors.append("becomes must be a non-empty string, a computed object or an integer")
        elif levels is not None and becomes not in levels:
            errors.append("becomes %r is not one of %s" % (becomes, ", ".join(levels)))
    if status == "lowered" and "becomes" not in cond:
        errors.append("lowered needs becomes")
    if "plans" in cond:
        plans = cond["plans"]
        if not (isinstance(plans, list) and plans):
            errors.append("plans must be a non-empty list")
        else:
            for plan in plans:
                if not (isinstance(plan, str) and plan in PLANS):
                    errors.append("unknown plan %r, must be one of %s" % (plan, ", ".join(PLANS)))
            if len(set(map(str, plans))) != len(plans):
                errors.append("plans repeat a plan")
    if "when" in cond:
        when = cond["when"]
        if not (isinstance(when, str) and when in WHEN_CASES):
            errors.append("when must be one of %s" % ", ".join(WHEN_CASES))
        elif when in ("reader_rejected_but_loads", "reader_rejected_untested") \
                and status != "unknown":
            errors.append("when %s needs status unknown" % when)
        elif when == "unreadable" and status != "unknown":
            errors.append("when unreadable needs status unknown")
        elif when == "replaced_in_source" and (status != "overridden"
                                               or key != "maxEffortLevel"):
            errors.append("when replaced_in_source needs status overridden "
                          "and key maxEffortLevel")
    if "via" in cond:
        errors.extend(_check_via(cond["via"], cond.get("layer"), key, scope, variables))
    if "if_set" in cond:
        errors.extend(_check_if_set(cond["if_set"], variables))
    if "name_form" in cond:
        form = cond["name_form"]
        if not (isinstance(form, str) and form in NAME_FORMS):
            errors.append("name_form must be one of %s" % ", ".join(NAME_FORMS))
        if not (isinstance(key, str) and (key == "modelSettings"
                                          or key.startswith("modelSettings."))):
            errors.append("name_form is only for a modelSettings rule")
    if "default_value" in cond:
        value = cond["default_value"]
        if status != "default":
            errors.append("default_value is only for a default status")
        if not _text(value):
            errors.append("default_value must be a non-empty string")
        elif levels is not None and value not in levels:
            errors.append("default_value %r is not one of %s" % (value, ", ".join(levels)))
    return errors


def _check_range(rng):
    if not isinstance(rng, dict):
        return ["range must be an object with min, max or both"]
    errors = []
    for field in sorted(set(rng) - RANGE_FIELDS):
        errors.append("range has unknown key %s" % field)
    if not (set(rng) & RANGE_FIELDS):
        errors.append("range needs min, max or both")
    for field in sorted(set(rng) & RANGE_FIELDS):
        if not _is_int(rng[field]):
            errors.append("range %s must be an integer" % field)
    if (_is_int(rng.get("min")) and _is_int(rng.get("max")) and rng["min"] > rng["max"]):
        errors.append("range min is above max")
    return errors


def _check_via(via, layer, key, scope, variables):
    if variables is None:
        return ["via needs the variables list"]
    errors = []
    if layer not in VARIABLE_LAYERS:
        errors.append("via is only for a condition on the env or default layer")
    if not isinstance(via, str):
        return errors + ["via must be a variable name"]
    if via not in variables:
        return errors + ["via %s is not in the variables list" % via]
    if not (isinstance(key, str) and isinstance(scope, str)):
        errors.append("via needs the rule key and scope to be strings")
    elif layer in VARIABLE_LAYERS and (key, scope, layer) not in variables[via]:
        errors.append("variable %s has no row for %s, %s, %s" % (via, key, scope, layer))
    return errors


def _check_if_set(names, variables):
    if variables is None:
        return ["if_set needs the variables list"]
    if not (isinstance(names, list) and names):
        return ["if_set must be a non-empty list of variable names"]
    errors = []
    for name in names:
        if not isinstance(name, str):
            errors.append("if_set item %r must be a variable name" % (name,))
        elif name not in variables:
            errors.append("if_set %s is not in the variables list" % name)
    if len(set(map(str, names))) != len(names):
        errors.append("if_set repeats a variable")
    return errors


def validate(data, base_dir=HERE):
    """Check a parsed rules.json document. Returns a list of error strings."""
    if not isinstance(data, dict):
        return ["top level must be an object"]
    errors = []
    for field in sorted(set(data) - TOP_FIELDS - TOP_OPTIONAL_FIELDS):
        errors.append("unknown top-level field %s" % field)
    version = data.get("schema_version")
    if type(version) is not int or version != SCHEMA_VERSION:
        errors.append("schema_version must be %d" % SCHEMA_VERSION)

    models = data.get("models")
    catalog_ids = None
    if not isinstance(models, list) or not models:
        errors.append("models must be a non-empty list")
    else:
        catalog_ids = []
        seen_ids = set()
        alias_owner = {}
        name_owner = {}
        for model in models:
            errors.extend(check_model(model, base_dir))
            if not isinstance(model, dict):
                continue
            mid = model.get("id")
            if isinstance(mid, str):
                if mid in seen_ids:
                    errors.append("model %s: duplicate id" % mid)
                seen_ids.add(mid)
                catalog_ids.append(mid)
            name = model.get("display_name")
            if _text(name):
                owner = name_owner.get(name)
                if owner is not None:
                    errors.append("model %s: display_name %s is also on model %s"
                                  % (mid, name, owner))
                name_owner.setdefault(name, mid)
            aliases = model.get("aliases")
            if isinstance(aliases, list):
                for alias in aliases:
                    if not isinstance(alias, str):
                        continue
                    owner = alias_owner.get(alias)
                    if owner is not None and owner != mid:
                        errors.append("model %s: alias %s is also on model %s" % (mid, alias, owner))
                    alias_owner.setdefault(alias, mid)

    rules = data.get("rules")
    if not isinstance(rules, list):
        return errors + ["rules must be a list"]
    index = None
    if "variables" in data:
        errors.extend(check_variables(data["variables"]))
        index = variable_index(data["variables"])
        for name, var_rows in index.items():
            for key, scope, layer in sorted(var_rows):
                if not any(isinstance(r, dict) and r.get("key") == key
                           and r.get("scope") == scope
                           and isinstance(r.get("layer_order"), list)
                           and layer in r["layer_order"] for r in rules):
                    errors.append("variable %s: row %s, %s, %s matches no rule"
                                  % (name, key, scope, layer))
    seen = set()
    for rule in rules:
        errors.extend(check_rule(rule, base_dir, catalog_ids, index))
        rid = rule.get("rule_id") if isinstance(rule, dict) else None
        if isinstance(rid, str):
            if rid in seen:
                errors.append("%s: duplicate rule_id" % rid)
            seen.add(rid)
    return errors


def load_and_validate(path=RULES_PATH):
    """Read and check a rules.json file. Experiment paths resolve beside it."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return ["cannot read %s: %s" % (path, exc)]
    return validate(data, os.path.dirname(os.path.abspath(path)))


def main(argv):
    path = argv[1] if len(argv) > 1 else RULES_PATH
    errors = load_and_validate(path)
    for line in errors:
        print(line)
    if not errors:
        print("ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
