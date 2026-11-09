"""List prices for the usage views. Standard library only.

``data/prices-old.json`` holds API list prices in USD per million tokens, keyed by
the catalog ids in ``data/rules.json``. Every cost on screen is an estimate at those
prices. This module loads and checks the file and prices one request.

* ``load_prices(path=None)``: the prices document.
* ``check(prices, catalog)``: a list of error strings, empty when clean.
* ``price_parts(record, prices, catalog)``: per-kind USD for one request, or None.
* ``price(record, prices, catalog)``: the sum of ``price_parts``, or None.

``catalog`` is the rules.json ``models`` list. A record is any object with these
attributes (see ``PricedRecord``): model_raw, input, output, cache_read,
cache_write_5m, cache_write_1h, speed, service_tier, inference_geo.

Only ``load_prices`` reads a file. Nothing here reads a clock or the environment.

The document::

    {"schema_version": 1, "source": <URL>, "verified_on": "YYYY-MM-DD",
     "unit": <string>, "models": {<id>: <entry>}, "modifiers": {...}}

An entry has input, output, cache_read, cache_write_5m and cache_write_1h
(non-negative numbers), and optional tiers: a list of objects with
``prompt_tokens_over`` plus the same five prices, ascending. When a request's
prompt tokens (input + cache_read + cache_write_5m + cache_write_1h) pass
``prompt_tokens_over``, the whole request uses that tier's prices.

An entry may also carry ``"flat_rate": true``. The managed ``modelPricing`` layer sets
it on an override row, whose rates apply exactly as written: ``price_parts`` then
skips the modifiers (fast mode, US-only inference) for that model.

``modifiers`` maps a record field (speed, service_tier, inference_geo) to its
allowed values. A value is a number, or ``{"multiplier": n, "models": [ids]}`` that
applies only to the listed models. A missing field counts as the first value, which
is 1. A value that is not listed gives no price.
"""

import datetime
import json
import re
from pathlib import Path
from typing import Any, Protocol, TypeGuard, cast

import model_catalog

# The prices document is a JSON object that check() exists to validate, so its values
# are untyped on purpose.
PricesDoc = dict[str, Any]

PRICES_PATH = model_catalog.DATA_DIR / "prices-old.json"
SCHEMA_VERSION = 1
PRICE_FIELDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
MODIFIER_FIELDS = ("speed", "service_tier", "inference_geo")
# An entry key that makes price_parts skip the modifiers for that model.
FLAT_RATE = "flat_rate"
# The default (unset) value for each modifier field.
MODIFIER_DEFAULTS = {
    "speed": "standard",
    "service_tier": "standard",
    "inference_geo": "global",
}
MILLION = 1000000.0


class PricedRecord(Protocol):
    """The attributes ``price_parts`` reads from a request record."""

    @property
    def model_raw(self) -> str | None:
        """The model name as written in the transcript."""
        ...

    @property
    def input(self) -> int:
        """Input tokens."""
        ...

    @property
    def output(self) -> int:
        """Output tokens."""
        ...

    @property
    def cache_read(self) -> int:
        """Cache read tokens."""
        ...

    @property
    def cache_write_5m(self) -> int:
        """Five minute cache write tokens."""
        ...

    @property
    def cache_write_1h(self) -> int:
        """One hour cache write tokens."""
        ...

    @property
    def speed(self) -> str | None:
        """The speed label."""
        ...

    @property
    def service_tier(self) -> str | None:
        """The service tier label."""
        ...

    @property
    def inference_geo(self) -> str | None:
        """The inference geography label."""
        ...


def load_prices(path: Path | str | None = None) -> PricesDoc:
    """Return the prices document. It does not validate; ``check`` does.

    Args:
        path: A prices file. The default is ``data/prices-old.json``.

    Returns:
        The parsed document.
    """
    with Path(path or PRICES_PATH).open(encoding="utf-8") as fh:
        return json.load(fh)


def _obj(value: object) -> dict[str, object] | None:
    """Narrow a parsed JSON value to an object, else None."""
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _items(value: object) -> list[object] | None:
    """Narrow a parsed JSON value to a list, else None."""
    if isinstance(value, list):
        return cast("list[object]", value)
    return None


def _is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _catalog_ids(catalog: model_catalog.Catalog) -> list[str]:
    return [m["id"] for m in catalog if isinstance(m.get("id"), str)]


def _check_prices(obj: dict[str, object], where: str, errors: list[str]) -> None:
    for field in PRICE_FIELDS:
        value = obj.get(field)
        if not _is_number(value):
            errors.append(f"{where}: {field} must be a number")
        elif value < 0:
            errors.append(f"{where}: {field} must not be negative")


def _check_entry(mid: str, raw_entry: object, errors: list[str]) -> None:
    entry = _obj(raw_entry)
    if entry is None:
        errors.append(f"model {mid}: entry is not an object")
        return
    allowed = set(PRICE_FIELDS) | {"tiers", FLAT_RATE}
    for field in sorted(set(entry) - allowed):
        errors.append(f"model {mid}: unknown field {field}")
    if FLAT_RATE in entry and not isinstance(entry[FLAT_RATE], bool):
        errors.append(f"model {mid}: {FLAT_RATE} must be true or false")
    _check_prices(entry, f"model {mid}", errors)
    tiers = _items(entry.get("tiers", []))
    if tiers is None:
        errors.append(f"model {mid}: tiers must be a list")
        return
    last: int | float = 0
    for i, raw_tier in enumerate(tiers):
        where = f"model {mid} tier {i}"
        tier = _obj(raw_tier)
        if tier is None:
            errors.append(f"{where}: not an object")
            continue
        for field in sorted(set(tier) - set(PRICE_FIELDS) - {"prompt_tokens_over"}):
            errors.append(f"{where}: unknown field {field}")
        _check_prices(tier, where, errors)
        over = tier.get("prompt_tokens_over")
        if not _is_number(over) or over < 0:
            errors.append(f"{where}: prompt_tokens_over must be a non-negative number")
        elif over <= last:
            errors.append(f"{where}: tiers must ascend by prompt_tokens_over")
        else:
            last = over


def _check_modifier_spec(
    where: str, raw_spec: object, ids: list[str], errors: list[str]
) -> None:
    if _is_number(raw_spec):
        if raw_spec < 0:
            errors.append(f"{where} must not be negative")
        return
    spec = _obj(raw_spec)
    if spec is None:
        errors.append(f"{where} must be a number or an object")
        return
    for key in sorted(set(spec) - {"multiplier", "models"}):
        errors.append(f"{where}: unknown field {key}")
    mult = spec.get("multiplier")
    if not _is_number(mult) or mult < 0:
        errors.append(f"{where}: multiplier must be a non-negative number")
    models = _items(spec.get("models"))
    if not models:
        errors.append(f"{where}: models must be a non-empty list")
        return
    errors.extend(
        f"{where}: {mid} is not a catalog id" for mid in models if mid not in ids
    )


def _check_modifiers(raw_modifiers: object, ids: list[str], errors: list[str]) -> None:
    modifiers = _obj(raw_modifiers)
    if modifiers is None:
        errors.append("modifiers must be an object")
        return
    for field in sorted(set(modifiers) - set(MODIFIER_FIELDS)):
        errors.append(f"modifiers: unknown field {field}")
    for field in MODIFIER_FIELDS:
        values = _obj(modifiers.get(field))
        if not values:
            errors.append(f"modifiers.{field} must be a non-empty object")
            continue
        default = MODIFIER_DEFAULTS[field]
        if default not in values:
            errors.append(f"modifiers.{field} must list {default}")
        elif values[default] != 1:
            errors.append(f"modifiers.{field}.{default} must be 1")
        for name, spec in values.items():
            _check_modifier_spec(f"modifiers.{field}.{name}", spec, ids, errors)


def _check_header(prices: dict[str, object], errors: list[str]) -> None:
    """Check schema_version, source, verified_on and unit."""
    if "schema_version" in prices and prices["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    source = prices.get("source")
    if "source" in prices and not (
        isinstance(source, str) and re.match(r"^https?://\S+$", source)
    ):
        errors.append("source must be a URL")
    verified = prices.get("verified_on")
    if "verified_on" in prices:
        try:
            if not (
                isinstance(verified, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", verified)
            ):
                raise ValueError(verified)  # noqa: TRY301
            datetime.date.fromisoformat(verified)
        except ValueError:
            errors.append("verified_on must be a date as YYYY-MM-DD")
    unit = prices.get("unit")
    if "unit" in prices and not (isinstance(unit, str) and unit):
        errors.append("unit must be a non-empty string")


def check(prices: object, catalog: model_catalog.Catalog) -> list[str]:
    """Check a prices document against the model catalog.

    Args:
        prices: The parsed prices document, or anything else a file might hold.
        catalog: The rules.json ``models`` list.

    Returns:
        Error strings, empty when the document is clean.
    """
    doc = _obj(prices)
    if doc is None:
        return ["prices is not an object"]
    errors: list[str] = []
    ids = _catalog_ids(catalog)
    allowed = {"schema_version", "source", "verified_on", "unit", "models", "modifiers"}
    errors.extend(f"missing field {field}" for field in sorted(allowed - set(doc)))
    errors.extend(f"unknown field {field}" for field in sorted(set(doc) - allowed))
    _check_header(doc, errors)

    if "models" in doc:
        models = _obj(doc["models"])
        if models is None:
            errors.append("models must be an object")
        else:
            for mid in sorted(models):
                if mid not in ids:
                    errors.append(f"model {mid}: not a catalog id")
                _check_entry(mid, models[mid], errors)
            errors.extend(
                f"model {mid}: no price entry" for mid in ids if mid not in models
            )
    if "modifiers" in doc:
        _check_modifiers(doc["modifiers"], ids, errors)
    return errors


def _multiplier(
    modifiers: dict[str, object], field: str, value: object, model_id: str
) -> float | None:
    """Return the multiplier for a modifier value, or None when it has no price."""
    if value is None:
        value = MODIFIER_DEFAULTS[field]
    values = _obj(modifiers.get(field))
    if not isinstance(value, str) or values is None or value not in values:
        return None
    spec = values[value]
    if _is_number(spec):
        return float(spec)
    spec_obj = _obj(spec)
    if spec_obj is not None and model_id in (_items(spec_obj.get("models", [])) or []):
        return float(cast("float", spec_obj["multiplier"]))
    return None


def _rates(entry: dict[str, object], prompt: int) -> dict[str, object]:
    """Return the price table that applies to a request of ``prompt`` tokens.

    That is the entry itself, or the tier with the highest ``prompt_tokens_over``
    that the prompt passes.
    """
    rates = entry
    top: float | None = None
    for raw_tier in _items(entry.get("tiers", [])) or []:
        tier = _obj(raw_tier)
        if tier is None:
            continue
        over = cast("float", tier["prompt_tokens_over"])
        if prompt > over and (top is None or over > top):
            top = over
            rates = tier
    return rates


def price_parts(
    record: PricedRecord, prices: PricesDoc, catalog: model_catalog.Catalog
) -> dict[str, float] | None:
    """Return the USD cost of one request by kind, or None when it has no price.

    Keys are input, output, cache_read and cache_write (5-minute plus 1-hour).
    Values are unrounded and include every modifier, except for an entry marked
    ``flat_rate``, which skips them. The result is None for an unknown model, a model
    with no entry, or (without ``flat_rate``) a modifier value that is not listed for
    the model.

    Args:
        record: The request.
        prices: The prices document.
        catalog: The rules.json ``models`` list.

    Returns:
        The cost by kind, or None.
    """
    model_id, _form = model_catalog.normalize_model(record.model_raw, catalog)
    if model_id is None:
        return None
    entry = _obj((_obj(prices.get("models")) or {}).get(model_id))
    if entry is None:
        return None
    modifiers = _obj(prices.get("modifiers")) or {}
    factor = 1.0
    labels: dict[str, object] = {
        "speed": record.speed,
        "service_tier": record.service_tier,
        "inference_geo": record.inference_geo,
    }
    if entry.get(FLAT_RATE) is not True:
        for field in MODIFIER_FIELDS:
            mult = _multiplier(modifiers, field, labels[field], model_id)
            if mult is None:
                return None
            factor *= mult

    prompt = (
        record.input + record.cache_read + record.cache_write_5m + record.cache_write_1h
    )
    rates = _rates(entry, prompt)

    def usd(tokens: int, field: str) -> float:
        return tokens * cast("float", rates[field]) / MILLION * factor

    return {
        "input": usd(record.input, "input"),
        "output": usd(record.output, "output"),
        "cache_read": usd(record.cache_read, "cache_read"),
        "cache_write": (
            usd(record.cache_write_5m, "cache_write_5m")
            + usd(record.cache_write_1h, "cache_write_1h")
        ),
    }


def price(
    record: PricedRecord, prices: PricesDoc, catalog: model_catalog.Catalog
) -> float | None:
    """Return the USD cost of one request, or None when it has no price.

    Args:
        record: The request.
        prices: The prices document.
        catalog: The rules.json ``models`` list.

    Returns:
        The sum of ``price_parts``, or None.
    """
    parts = price_parts(record, prices, catalog)
    if parts is None:
        return None
    return sum(parts.values())
