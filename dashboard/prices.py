"""List prices for the usage dashboard. Standard library only.

prices.json holds API list prices in USD per million tokens, keyed by the
catalog ids in rules.json. Every cost on screen is an estimate at those prices.
This module loads and checks the file and prices one request.

    load_prices(path=None)               the prices.json document
    check(prices, catalog)               list of error strings, empty when clean
    price_parts(record, prices, catalog) per-kind USD for one request, or None
    price(record, prices, catalog)       the sum of price_parts, or None

catalog is the rules.json `models` list. A record is any object with these
attributes: model_raw, input, output, cache_read, cache_write_5m,
cache_write_1h, speed, service_tier, inference_geo.

Only load_prices reads a file. Nothing here reads a clock or the environment.

Run the check on the real file:

    /usr/bin/python3 dashboard/prices.py check [path/to/prices.json]

prices.json:

    {"schema_version": 1, "source": <URL>, "verified_on": "YYYY-MM-DD",
     "unit": <string>, "models": {<id>: <entry>}, "modifiers": {...}}

An entry has input, output, cache_read, cache_write_5m and cache_write_1h
(non-negative numbers), and optional tiers: a list of objects with
prompt_tokens_over plus the same five prices, ascending. When a request's
prompt tokens (input + cache_read + cache_write_5m + cache_write_1h) pass
prompt_tokens_over, the whole request uses that tier's prices.

modifiers maps a record field (speed, service_tier, inference_geo) to its
allowed values. A value is a number, or {"multiplier": n, "models": [ids]}
that applies only to the listed models. A missing field counts as the first
value, which is 1. A value that is not listed gives no price.
"""
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import resolve  # noqa: E402

PRICES_PATH = os.path.join(HERE, "prices.json")
SCHEMA_VERSION = 1
PRICE_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
MODIFIER_FIELDS = ("speed", "service_tier", "inference_geo")
# The default (unset) value for each modifier field.
MODIFIER_DEFAULTS = {"speed": "standard", "service_tier": "standard", "inference_geo": "global"}
MILLION = 1000000.0


def load_prices(path=None):
    """Return the prices.json document. It does not validate; check() does."""
    with open(path or PRICES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _catalog_ids(catalog):
    return [m["id"] for m in catalog if isinstance(m, dict) and isinstance(m.get("id"), str)]


def _check_prices(obj, where, errors):
    for field in PRICE_FIELDS:
        value = obj.get(field)
        if not _is_number(value):
            errors.append("%s: %s must be a number" % (where, field))
        elif value < 0:
            errors.append("%s: %s must not be negative" % (where, field))


def _check_entry(mid, entry, errors):
    if not isinstance(entry, dict):
        errors.append("model %s: entry is not an object" % mid)
        return
    allowed = set(PRICE_FIELDS) | {"tiers"}
    for field in sorted(set(entry) - allowed):
        errors.append("model %s: unknown field %s" % (mid, field))
    _check_prices(entry, "model %s" % mid, errors)
    tiers = entry.get("tiers", [])
    if not isinstance(tiers, list):
        errors.append("model %s: tiers must be a list" % mid)
        return
    last = 0
    for i, tier in enumerate(tiers):
        where = "model %s tier %d" % (mid, i)
        if not isinstance(tier, dict):
            errors.append("%s: not an object" % where)
            continue
        for field in sorted(set(tier) - set(PRICE_FIELDS) - {"prompt_tokens_over"}):
            errors.append("%s: unknown field %s" % (where, field))
        _check_prices(tier, where, errors)
        over = tier.get("prompt_tokens_over")
        if not _is_number(over) or over < 0:
            errors.append("%s: prompt_tokens_over must be a non-negative number" % where)
        elif over <= last:
            errors.append("%s: tiers must ascend by prompt_tokens_over" % where)
        else:
            last = over


def _check_modifiers(modifiers, ids, errors):
    if not isinstance(modifiers, dict):
        errors.append("modifiers must be an object")
        return
    for field in sorted(set(modifiers) - set(MODIFIER_FIELDS)):
        errors.append("modifiers: unknown field %s" % field)
    for field in MODIFIER_FIELDS:
        values = modifiers.get(field)
        if not isinstance(values, dict) or not values:
            errors.append("modifiers.%s must be a non-empty object" % field)
            continue
        default = MODIFIER_DEFAULTS[field]
        if default not in values:
            errors.append("modifiers.%s must list %s" % (field, default))
        elif values[default] != 1:
            errors.append("modifiers.%s.%s must be 1" % (field, default))
        for name, spec in values.items():
            where = "modifiers.%s.%s" % (field, name)
            if _is_number(spec):
                if spec < 0:
                    errors.append("%s must not be negative" % where)
                continue
            if not isinstance(spec, dict):
                errors.append("%s must be a number or an object" % where)
                continue
            for key in sorted(set(spec) - {"multiplier", "models"}):
                errors.append("%s: unknown field %s" % (where, key))
            mult = spec.get("multiplier")
            if not _is_number(mult) or mult < 0:
                errors.append("%s: multiplier must be a non-negative number" % where)
            models = spec.get("models")
            if not isinstance(models, list) or not models:
                errors.append("%s: models must be a non-empty list" % where)
                continue
            for mid in models:
                if mid not in ids:
                    errors.append("%s: %s is not a catalog id" % (where, mid))


def check(prices, catalog):
    """Check a prices document against the model catalog. Returns error strings."""
    if not isinstance(prices, dict):
        return ["prices is not an object"]
    errors = []
    ids = _catalog_ids(catalog)
    allowed = {"schema_version", "source", "verified_on", "unit", "models", "modifiers"}
    for field in sorted(allowed - set(prices)):
        errors.append("missing field %s" % field)
    for field in sorted(set(prices) - allowed):
        errors.append("unknown field %s" % field)

    if "schema_version" in prices and prices["schema_version"] != SCHEMA_VERSION:
        errors.append("schema_version must be %d" % SCHEMA_VERSION)
    source = prices.get("source")
    if "source" in prices and not (isinstance(source, str) and re.match(r"^https?://\S+$", source)):
        errors.append("source must be a URL")
    verified = prices.get("verified_on")
    if "verified_on" in prices:
        try:
            if not (isinstance(verified, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", verified)):
                raise ValueError(verified)
            datetime.date.fromisoformat(verified)
        except ValueError:
            errors.append("verified_on must be a date as YYYY-MM-DD")
    unit = prices.get("unit")
    if "unit" in prices and not (isinstance(unit, str) and unit):
        errors.append("unit must be a non-empty string")

    models = prices.get("models")
    if "models" in prices:
        if not isinstance(models, dict):
            errors.append("models must be an object")
        else:
            for mid in sorted(models):
                if mid not in ids:
                    errors.append("model %s: not a catalog id" % mid)
                _check_entry(mid, models[mid], errors)
            for mid in ids:
                if mid not in models:
                    errors.append("model %s: no price entry" % mid)
    if "modifiers" in prices:
        _check_modifiers(prices["modifiers"], ids, errors)
    return errors


def _multiplier(modifiers, field, value, model_id):
    """Return the multiplier for a modifier value, or None when it has no price."""
    if value is None:
        value = MODIFIER_DEFAULTS[field]
    values = modifiers.get(field)
    if not isinstance(value, str) or not isinstance(values, dict) or value not in values:
        return None
    spec = values[value]
    if _is_number(spec):
        return float(spec)
    if isinstance(spec, dict) and model_id in spec.get("models", []):
        return float(spec["multiplier"])
    return None


def price_parts(record, prices, catalog):
    """Return the USD cost of one request by kind, or None when it has no price.

    Keys: input, output, cache_read, cache_write (5-minute plus 1-hour). Values
    are unrounded and include every modifier. None for an unknown model, a
    model with no entry, or a modifier value that is not listed for the model.
    """
    model_id, _form = resolve.normalize_model(record.model_raw, catalog)
    if model_id is None:
        return None
    entry = prices.get("models", {}).get(model_id)
    if not isinstance(entry, dict):
        return None
    modifiers = prices.get("modifiers", {})
    factor = 1.0
    for field in MODIFIER_FIELDS:
        mult = _multiplier(modifiers, field, getattr(record, field), model_id)
        if mult is None:
            return None
        factor *= mult

    prompt = (record.input + record.cache_read
              + record.cache_write_5m + record.cache_write_1h)
    rates = entry
    top = None
    for tier in entry.get("tiers", []):
        if prompt > tier["prompt_tokens_over"] and (top is None or tier["prompt_tokens_over"] > top):
            top = tier["prompt_tokens_over"]
            rates = tier

    def usd(tokens, field):
        return tokens * rates[field] / MILLION * factor

    return {
        "input": usd(record.input, "input"),
        "output": usd(record.output, "output"),
        "cache_read": usd(record.cache_read, "cache_read"),
        "cache_write": (usd(record.cache_write_5m, "cache_write_5m")
                        + usd(record.cache_write_1h, "cache_write_1h")),
    }


def price(record, prices, catalog):
    """Return the USD cost of one request, or None when it has no price."""
    parts = price_parts(record, prices, catalog)
    if parts is None:
        return None
    return sum(parts.values())


def main(argv):
    if len(argv) < 2 or argv[1] != "check":
        print("usage: prices.py check [path/to/prices.json]")
        return 2
    path = argv[2] if len(argv) > 2 else PRICES_PATH
    try:
        errors = check(load_prices(path), resolve.load_rules()["models"])
    except (OSError, ValueError) as exc:
        errors = ["cannot read %s: %s" % (path, exc)]
    for line in errors:
        print(line)
    if not errors:
        print("ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
