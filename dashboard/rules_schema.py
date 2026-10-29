"""Schema check for dashboard/rules.json. Standard library only.

rules.json holds every precedence and validity rule the dashboard applies, as
data. The resolver reads it and never hard-codes a rule. This module is the
schema: it lists the allowed values and checks each entry.

Run it directly to check the real file:

    /usr/bin/python3 dashboard/rules_schema.py [path/to/rules.json]

Top level:

    {"schema_version": 1, "rules": [<rule>, ...]}

A rule:

    rule_id       unique, lowercase words joined by hyphens
    key           the setting, as a dotted path (effortLevel, experimental.cacheTtl)
    scope         main, agent or model
    layer_order   layer ids, highest precedence first
    conditions    list of {layer, models, [values], status, [becomes]}; each one
                  says what status a candidate set in `layer` yields when the
                  model is in `models` ("*" means any model) and, if given, the
                  raw value is in `values`. `becomes` is the value a Lowered
                  candidate runs as. The resolver takes the first condition
                  that matches, so list the narrow ones first.
    reason        the sentence shown on screen, with {slot} placeholders
    doc_url       https link to the doc section, or null
    quote         verbatim doc text that backs the rule, or null
    experiment    path to an experiment record, relative to this folder, or null
    confidence    documented, tested or assumed
    verified_on   {claude_version: "2.1.302", date: "2026-10-29"}

Every rule needs a reason. Documented and Tested rules also need a source: a
doc quote (doc_url and quote) or an experiment record. Documented needs the
quote; Tested needs the record. An Assumed rule may have neither, because
Assumed means no source backs it yet. A quote still needs its doc_url.

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
SCHEMA_VERSION = 1

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

# Places a value can be set. The order between them is per rule (layer_order),
# because the discovery tickets settle it key by key.
#   cli      a file passed with --settings, which ranks with the settings files
#   flag     a session flag such as --model, --effort or --autocompact
#   env      the process environment: the shell, overwritten by settings env
#            blocks, which the resolver works out first (rule env-block-order)
#   default  Claude Code's own value, or the main model for an agent
LAYERS = ("managed", "cli", "flag", "env", "local", "project", "user", "agent", "default")

# Slots a reason template may use.
REASON_SLOTS = ("key", "value", "file", "layer", "model", "agent", "winner")

ANY_MODEL = "*"

RULE_FIELDS = {
    "rule_id", "key", "scope", "layer_order", "conditions", "reason",
    "doc_url", "quote", "experiment", "confidence", "verified_on",
}
CONDITION_REQUIRED = {"layer", "models", "status"}
CONDITION_FIELDS = CONDITION_REQUIRED | {"values", "becomes"}
VERIFIED_FIELDS = {"claude_version", "date"}
EXPERIMENT_FIELDS = {"date", "claude_version", "ran", "result"}

RULE_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
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


def check_rule(rule, base_dir=HERE):
    """Check one rule entry. Returns a list of error strings."""
    if not isinstance(rule, dict):
        return ["rule is not an object"]
    rid = rule.get("rule_id") if isinstance(rule.get("rule_id"), str) else "?"
    errors = []

    def err(msg):
        errors.append("%s: %s" % (rid, msg))

    for field in sorted(RULE_FIELDS - set(rule)):
        err("missing field %s" % field)
    for field in sorted(set(rule) - RULE_FIELDS):
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

    conditions = rule.get("conditions")
    if "conditions" in rule:
        if not isinstance(conditions, list) or not conditions:
            err("conditions must be a non-empty list")
        else:
            for i, cond in enumerate(conditions):
                errors.extend("%s: condition %d: %s" % (rid, i, m)
                              for m in _check_condition(cond, order))

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

    doc_url, quote, experiment = rule.get("doc_url"), rule.get("quote"), rule.get("experiment")
    for field, value in (("doc_url", doc_url), ("quote", quote), ("experiment", experiment)):
        if field in rule and value is not None and not _text(value):
            err("%s must be a non-empty string or null" % field)
    if _text(doc_url) and not doc_url.startswith("https://"):
        err("doc_url must be an https link")
    has_quote = _text(doc_url) and _text(quote)
    if _text(quote) and not _text(doc_url):
        err("quote has no doc_url")
    if _text(experiment):
        if os.path.isabs(experiment) or ".." in experiment.split("/"):
            err("experiment must be a path inside the dashboard folder")
        else:
            rec_errors = check_experiment(os.path.join(base_dir, experiment))
            errors.extend("%s: %s" % (rid, m) for m in rec_errors)
    if (not has_quote and not _text(experiment)
            and rule.get("confidence") != "assumed"):
        err("no source: needs a doc quote (doc_url and quote) or an experiment record")

    confidence = rule.get("confidence")
    if "confidence" in rule:
        if not isinstance(confidence, str) or confidence not in CONFIDENCE_WORDS:
            err("confidence must be one of %s" % ", ".join(CONFIDENCE_WORDS))
        elif confidence == "documented" and not has_quote:
            err("documented rule needs doc_url and quote")
        elif confidence == "tested" and not _text(experiment):
            err("tested rule needs an experiment record")

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


def _check_condition(cond, order):
    if not isinstance(cond, dict):
        return ["not an object"]
    errors = []
    for field in sorted(CONDITION_REQUIRED - set(cond)):
        errors.append("missing field %s" % field)
    for field in sorted(set(cond) - CONDITION_FIELDS):
        errors.append("unknown field %s" % field)
    if "layer" in cond and cond["layer"] not in order:
        errors.append("layer %r is not in layer_order" % (cond["layer"],))
    models = cond.get("models")
    if "models" in cond and not (isinstance(models, list) and models
                                 and all(_text(m) for m in models)):
        errors.append("models must be a non-empty list of model ids, or [\"*\"]")
    elif isinstance(models, list) and ANY_MODEL in models and len(models) > 1:
        errors.append("models: \"*\" stands alone")
    if "values" in cond and not (isinstance(cond["values"], list) and cond["values"]):
        errors.append("values must be a non-empty list")
    status = cond.get("status")
    if "status" in cond and not (isinstance(status, str) and status in STATUS_WORDS):
        errors.append("status must be one of %s" % ", ".join(STATUS_WORDS))
    if "becomes" in cond and status != "lowered":
        errors.append("becomes is only for a lowered status")
    if status == "lowered" and "becomes" not in cond:
        errors.append("lowered needs becomes")
    return errors


def validate(data, base_dir=HERE):
    """Check a parsed rules.json document. Returns a list of error strings."""
    if not isinstance(data, dict):
        return ["top level must be an object"]
    errors = []
    for field in sorted(set(data) - {"schema_version", "rules"}):
        errors.append("unknown top-level field %s" % field)
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be %d" % SCHEMA_VERSION)
    rules = data.get("rules")
    if not isinstance(rules, list):
        return errors + ["rules must be a list"]
    seen = set()
    for rule in rules:
        errors.extend(check_rule(rule, base_dir))
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
