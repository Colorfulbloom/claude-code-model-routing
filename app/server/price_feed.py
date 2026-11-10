"""The price feed. Fetch, check, keep, cross-check and answer.

The price table has four sources, in this order, per model.

1. ``model_pricing``. Rates from the ``modelPricing`` setting in Claude Code's
   managed settings file, when a path is given.
2. ``litellm``. The newest LiteLLM copy that passed every check, when it is also the
   newest attempt and was fetched within 48 hours.
3. ``last_good``. That same copy when the newest attempt failed or none ran in 48
   hours. It lives in ``bartab/prices/last-good.json``.
4. ``bundled``. The dated copy shipped in ``data/prices/``, when no fetch ever
   passed (or the last good file is gone or damaged).

Every document has the shape of ``data/prices-old.json``, so ``prices.price_parts``
prices a request with it unchanged. Costs are never stored. The server prices at
query time with ``price_table()``, and ``PriceTable.hash`` is what query caches key on.

Network work runs on the ``PriceFeed`` thread. It hands each result to the store
writer as a job (``submit``), and the job writes the ``price_copies`` row and the last
good file. The OpenRouter cross-check only flags a disagreement. It never changes a
price.

Nothing here reads the environment. The clock, the transport, the sleep and the
managed settings path are all passed in.
"""

import copy
import hashlib
import json
import logging
import re
import sqlite3
import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

import model_catalog
import platform_os
import prices
import store_paths
from price_transport import (
    DEFAULT_TIMEOUT,
    LITELLM_URL,
    OPENROUTER_URL,
    FetchError,
    Transport,
)
from store_paths import StoreLayout

logger = logging.getLogger(__name__)

ReasonCode = Literal[
    "not_json",
    "too_large",
    "missing_model",
    "out_of_range",
    "cache_ratio",
    "fetch_failed",
    "redirect_refused",
    "timeout",
]
Source = Literal["model_pricing", "litellm", "last_good", "bundled"]
CrossState = Literal["agree", "disagree", "not_checked"]
Job = Callable[[sqlite3.Connection], None]
Submit = Callable[[Job], None]

BUNDLED_DIR = model_catalog.DATA_DIR / "prices"
UNIT = "USD per million tokens"
UNKNOWN_DATE = "1970-01-01"

# Size caps are four times the files as measured on November 8, 2026 (LiteLLM
# 3,474,076 bytes, OpenRouter 829,400 bytes).
LITELLM_MAX_BYTES = 4 * 3_474_076
OPENROUTER_MAX_BYTES = 4 * 829_400
MANAGED_SETTINGS_MAX_BYTES = 1024 * 1024

# Ranges in USD per million tokens, applied to every rate of a catalog model.
INPUT_RANGE = (0.05, 100.0)
OUTPUT_RANGE = (0.2, 500.0)
CACHE_WRITE_MAX = 1000.0
# Cache read as a share of input. The owner's rule was "about 10 percent", but the
# November 8 file has 10 percent for most models, 5 percent for opus-5-5 and
# sonnet-5-5, and 2.5 percent for fable-5-1. A band of 1 to 12 percent accepts that
# file and still rejects a unit slip (0.1 percent or 100 percent).
CACHE_RATIO_RANGE = (0.01, 0.12)
# Division of two converted rates can land a hair outside an exact band edge.
RATIO_EPSILON = 1e-9
MODIFIER_MULTIPLIER_MAX = 10.0
CROSS_CHECK_TOLERANCE = 0.01

ACTIVE_WINDOW_SECONDS = 48 * 3600
FETCH_INTERVAL_SECONDS = 24 * 3600
# After a pass that raised (a store error, say), try again in 15 minutes. A pass that
# failed before it fetched anything owes the first fetch, so waiting a day would skip
# it, and trying at every poll would hammer a store that is not well. A fetch that
# fails but is recorded as a failed copy is not this case and waits the full day.
FAILURE_BACKOFF_SECONDS = 15 * 60
POLL_SECONDS = 60.0
REQUIRED_WINDOW_SECONDS = 30 * 24 * 3600

PRICE_FIELDS = prices.PRICE_FIELDS
_LITELLM_FIELDS = {
    "input": "input_cost_per_token",
    "output": "output_cost_per_token",
    "cache_read": "cache_read_input_token_cost",
    "cache_write_5m": "cache_creation_input_token_cost",
    "cache_write_1h": "cache_creation_input_token_cost_above_1hr",
}
_TIER_FIELD = re.compile(
    r"^(input_cost_per_token|output_cost_per_token|cache_read_input_token_cost"
    r"|cache_creation_input_token_cost|cache_creation_input_token_cost_above_1hr)"
    r"_above_(\d+)k_tokens$"
)
_TIER_BASE_TO_FIELD = {base: name for name, base in _LITELLM_FIELDS.items()}
_SONNET = re.compile(r"^claude-sonnet-(\d+)(?:-(\d+))?$")
_MILLION = Decimal(1_000_000)


# ---------------------------------------------------------------------------
# Small JSON helpers


def _as_obj(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast("list[object]", value)
    return None


def _number(value: object) -> float | None:
    """Return a finite number as a float. Booleans and everything else give None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if number == number and abs(number) != float("inf") else None  # noqa: PLR0124


def _per_mtok(value: float) -> float:
    """Convert USD per token to USD per million tokens without float noise."""
    return float(Decimal(repr(value)) * _MILLION)


def _scaled(value: float, factor: float) -> float:
    """Multiply two rates without float noise."""
    return float(Decimal(repr(value)) * Decimal(repr(factor)))


def canonical_json(document: object) -> bytes:
    """Return the one byte form of a document, so equal tables hash equal."""
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def table_hash(document: prices.PricesDoc) -> str:
    """Return the SHA-256 (hex) of a prices document's rates and modifiers.

    The header (source, verified_on, unit) is left out, so a new copy with the same
    prices hashes the same and query caches keep their answers.
    """
    priced = {key: document[key] for key in ("models", "modifiers") if key in document}
    return hashlib.sha256(canonical_json(priced)).hexdigest()


class TooDeepError(ValueError):
    """A JSON body nested too deep to parse."""


def _reject_constant(name: str) -> object:
    raise ValueError(name)


def _loads(data: bytes) -> object:
    """Parse JSON, refusing NaN and Infinity. Raises ValueError for bad input."""
    try:
        return json.loads(data, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise TooDeepError from exc


# ---------------------------------------------------------------------------
# LiteLLM parsing and checks


@dataclass(frozen=True)
class CheckResult:
    """What the checks said about one LiteLLM body.

    ``detail`` names the catalog ids behind a failure, for the log and the tests.
    ``document`` is set only when ``ok`` is True.
    """

    ok: bool
    reason_code: ReasonCode | None
    document: prices.PricesDoc | None = None
    models: int = 0
    detail: tuple[str, ...] = ()


def _fail(code: ReasonCode, *detail: str) -> CheckResult:
    return CheckResult(ok=False, reason_code=code, detail=tuple(detail))


def _pick_rows(
    rows: Mapping[str, dict[str, object]], catalog: model_catalog.Catalog
) -> dict[str, dict[str, object]]:
    """Map catalog ids to one LiteLLM row each.

    A canonical key beats an alias, which beats a dated key. Among dated keys the
    newest date wins.
    """
    rank = {"canonical": 0, "alias": 1}
    best: dict[str, tuple[int, dict[str, object]]] = {}
    for key in sorted(rows, reverse=True):
        model_id, form = model_catalog.normalize_model(key, catalog)
        if model_id is None or form is None:
            continue
        order = rank.get(form, 2)
        if model_id not in best or order < best[model_id][0]:
            best[model_id] = (order, rows[key])
    return {model_id: row for model_id, (_, row) in best.items()}


def _rates(
    source: Mapping[str, object], names: Mapping[str, str]
) -> dict[str, float] | None:
    """Read the five rates under ``names`` (price field to row field), per MTok.

    Returns None when a field is missing, not a number, or not above zero.
    """
    out: dict[str, float] = {}
    for name in PRICE_FIELDS:
        raw = _number(source.get(names[name]))
        if raw is None or raw <= 0:
            return None
        out[name] = _per_mtok(raw)
    return out


def _in_range(rates: Mapping[str, float]) -> bool:
    return (
        INPUT_RANGE[0] <= rates["input"] <= INPUT_RANGE[1]
        and OUTPUT_RANGE[0] <= rates["output"] <= OUTPUT_RANGE[1]
        and rates["cache_write_5m"] <= CACHE_WRITE_MAX
        and rates["cache_write_1h"] <= CACHE_WRITE_MAX
        and rates["cache_read"] <= rates["input"]
    )


def _tier_thresholds(row: Mapping[str, object]) -> list[int]:
    found = {
        int(match.group(2)) * 1000
        for key in row
        if (match := _TIER_FIELD.match(key)) is not None
    }
    return sorted(found)


def _row_entry(row: Mapping[str, object]) -> dict[str, Any] | None:
    """Build one document entry from a LiteLLM row, or None when it is malformed."""
    base = _rates(row, _LITELLM_FIELDS)
    if base is None or not _in_range(base):
        return None
    entry: dict[str, Any] = dict(base)
    tiers: list[dict[str, Any]] = []
    for over in _tier_thresholds(row):
        names = {
            name: f"{field_name}_above_{over // 1000}k_tokens"
            for name, field_name in _LITELLM_FIELDS.items()
        }
        tier = _rates(row, names)
        if tier is None or not _in_range(tier):
            return None
        tiers.append({"prompt_tokens_over": over, **tier})
    if tiers:
        entry["tiers"] = tiers
    return entry


def _cache_ratio_ok(rates: Mapping[str, float]) -> bool:
    ratio = rates["cache_read"] / rates["input"]
    low, high = CACHE_RATIO_RANGE
    return low - RATIO_EPSILON <= ratio <= high + RATIO_EPSILON


class _BadModifierError(ValueError):
    """A modifier value is malformed, or the models disagree on its multiplier."""


_Modifier = tuple[float, list[str]]


def _modifier_models(
    picked: Mapping[str, dict[str, object]], name: str
) -> _Modifier | None:
    """Collect one ``provider_specific_entry`` modifier across models.

    Returns None when no model carries it, else ``(multiplier, ids)``.

    Raises:
        _BadModifierError: When a value is malformed or the models disagree. One
            document value cannot hold two multipliers.
    """
    seen: dict[str, float] = {}
    for model_id, row in picked.items():
        entry = _as_obj(row.get("provider_specific_entry"))
        if entry is None or name not in entry:
            continue
        mult = _number(entry[name])
        if mult is None or not 1.0 <= mult <= MODIFIER_MULTIPLIER_MAX:
            raise _BadModifierError
        seen[model_id] = mult
    if not seen:
        return None
    if len(set(seen.values())) != 1:
        raise _BadModifierError
    return next(iter(seen.values())), sorted(seen)


def parse_litellm(
    data: bytes,
    *,
    required: set[str],
    fetched_at: str | None = None,
    catalog: model_catalog.Catalog | None = None,
) -> CheckResult:
    """Check a LiteLLM price file and build a prices document from it.

    Checks run in order and the first failure wins. ``not_json`` when the body is not
    a JSON object. Then only rows with ``litellm_provider`` "anthropic" are kept and
    their keys map to catalog ids. ``missing_model`` when a model in ``required`` has
    no row. ``out_of_range`` when a rate is missing or outside its range (input 0.05
    to 100, output 0.2 to 500 USD per million tokens, tiers included), or a modifier
    is malformed. ``cache_ratio`` when cache read is not 1 to 12 percent of input.

    Args:
        data: The response body.
        required: Catalog ids the copy must list.
        fetched_at: The fetch time as ISO text. Its date becomes ``verified_on``.
        catalog: The model catalog. The default is the bundled rules file.

    Returns:
        A ``CheckResult``. ``document`` has the shape of ``data/prices-old.json``.
    """
    models_catalog = catalog if catalog is not None else model_catalog.load_catalog()
    try:
        parsed = _loads(data)
    except ValueError:
        return _fail("not_json")
    top = _as_obj(parsed)
    if top is None:
        return _fail("not_json")
    rows: dict[str, dict[str, object]] = {}
    for key, value in top.items():
        row = _as_obj(value)
        if row is not None and row.get("litellm_provider") == "anthropic":
            rows[key] = row
    picked = _pick_rows(rows, models_catalog)

    missing = sorted(required - set(picked))
    if missing:
        return _fail("missing_model", *missing)

    entries: dict[str, dict[str, Any]] = {}
    bad: list[str] = []
    for model_id in sorted(picked):
        entry = _row_entry(picked[model_id])
        if entry is None:
            bad.append(model_id)
        else:
            entries[model_id] = entry
    modifiers: dict[str, _Modifier | None] = {}
    for name in ("fast", "us"):
        try:
            modifiers[name] = _modifier_models(picked, name)
        except _BadModifierError:
            bad.append(f"modifier:{name}")
    if bad:
        return _fail("out_of_range", *bad)

    off = sorted(
        model_id
        for model_id, entry in entries.items()
        if not _cache_ratio_ok(entry)
        or any(not _cache_ratio_ok(tier) for tier in entry.get("tiers", []))
    )
    if off:
        return _fail("cache_ratio", *off)

    document = _document(entries, modifiers, fetched_at)
    return CheckResult(
        ok=True, reason_code=None, document=document, models=len(entries)
    )


def _document(
    entries: Mapping[str, dict[str, Any]],
    modifiers: Mapping[str, _Modifier | None],
    fetched_at: str | None,
) -> prices.PricesDoc:
    speed: dict[str, Any] = {"standard": 1}
    geo: dict[str, Any] = {"global": 1, "not_available": 1}
    fast = modifiers["fast"]
    if fast:
        speed["fast"] = {"multiplier": fast[0], "models": fast[1]}
    us = modifiers["us"]
    if us:
        geo["us"] = {"multiplier": us[0], "models": us[1]}
    return {
        "schema_version": prices.SCHEMA_VERSION,
        "source": LITELLM_URL,
        "verified_on": fetched_at[:10] if fetched_at else UNKNOWN_DATE,
        "unit": UNIT,
        "models": dict(entries),
        "modifiers": {
            "speed": speed,
            "service_tier": {"standard": 1},
            "inference_geo": geo,
        },
    }


# ---------------------------------------------------------------------------
# OpenRouter cross-check


@dataclass(frozen=True)
class CrossCheck:
    """The OpenRouter cross-check. ``models`` lists the ids that disagree."""

    state: CrossState = "not_checked"
    models: tuple[str, ...] = ()


def parse_openrouter(
    data: bytes, catalog: model_catalog.Catalog | None = None
) -> dict[str, tuple[float, float]] | None:
    """Read OpenRouter's models list into ``{catalog id: (input, output)}`` per MTok.

    Only ``anthropic/*`` ids are read. Ids use dots (``claude-opus-4.8``), and the
    ``:batch`` rows are skipped.

    Args:
        data: The response body.
        catalog: The model catalog. The default is the bundled rules file.

    Returns:
        The rates, or None when the body is not an OpenRouter list.
    """
    models_catalog = catalog if catalog is not None else model_catalog.load_catalog()
    try:
        parsed = _loads(data)
    except ValueError:
        return None
    top = _as_obj(parsed)
    items = _as_list(top.get("data")) if top is not None else None
    if items is None:
        return None
    out: dict[str, tuple[float, float]] = {}
    for item in items:
        rate = _openrouter_row(item, models_catalog)
        if rate is not None and rate[0] not in out:
            out[rate[0]] = (rate[1], rate[2])
    return out


def _openrouter_row(
    item: object, catalog: model_catalog.Catalog
) -> tuple[str, float, float] | None:
    row = _as_obj(item)
    if row is None:
        return None
    raw_id = row.get("id")
    if (
        not isinstance(raw_id, str)
        or not raw_id.startswith("anthropic/")
        or ":" in raw_id
    ):
        return None
    model_id, _form = model_catalog.normalize_model(
        raw_id.removeprefix("anthropic/").replace(".", "-"), catalog
    )
    pricing = _as_obj(row.get("pricing"))
    if model_id is None or pricing is None:
        return None
    try:
        prompt = float(Decimal(str(pricing["prompt"])) * _MILLION)
        completion = float(Decimal(str(pricing["completion"])) * _MILLION)
    except (KeyError, InvalidOperation):
        return None
    return model_id, prompt, completion


def cross_check(
    active_doc: prices.PricesDoc, rates: Mapping[str, tuple[float, float]] | None
) -> CrossCheck:
    """Compare OpenRouter's input and output rates with the active document.

    ``disagree`` when any model's input or output differs by more than 1 percent.
    ``not_checked`` when there are no OpenRouter rates or no model in common. This
    never changes a price.

    Args:
        active_doc: The prices document in use, before any ``modelPricing`` layer.
        rates: ``parse_openrouter`` output, or None.

    Returns:
        The state and the ids that disagree, sorted.
    """
    if rates is None:
        return CrossCheck()
    models = _as_obj(active_doc.get("models")) or {}
    compared = 0
    differ: list[str] = []
    for model_id in sorted(rates):
        entry = _as_obj(models.get(model_id))
        if entry is None:
            continue
        compared += 1
        for ours, theirs in zip(
            (_number(entry.get("input")), _number(entry.get("output"))),
            rates[model_id],
            strict=True,
        ):
            if ours is None or abs(theirs - ours) > CROSS_CHECK_TOLERANCE * abs(ours):
                differ.append(model_id)
                break
    if compared == 0:
        return CrossCheck()
    return CrossCheck("disagree" if differ else "agree", tuple(differ))


# ---------------------------------------------------------------------------
# The managed modelPricing layer


@dataclass(frozen=True)
class ModelOverride:
    """One model's rates from ``modelPricing.overrides``, USD per million tokens.

    Claude Code requires all four rates, so there are no defaults. ``cache_write``
    covers both the 5 minute and the 1 hour write.
    """

    input: float
    output: float
    cache_read: float
    cache_write: float


@dataclass(frozen=True)
class ModelPricingLayer:
    """The ``modelPricing`` setting, read from the managed settings file."""

    multiplier: float = 1.0
    overrides: Mapping[str, ModelOverride] = field(
        default_factory=dict[str, ModelOverride]
    )

    @property
    def empty(self) -> bool:
        """True when the layer changes nothing."""
        return self.multiplier == 1.0 and not self.overrides


# Claude Code accepts an override rate from 0 to 10000 USD per million tokens.
OVERRIDE_RATE_MAX = 10000.0

_OVERRIDE_KEYS = {
    "input": "input",
    "output": "output",
    "cacheRead": "cache_read",
    "cacheWrite": "cache_write",
}


def _override(raw: object) -> ModelOverride | None:
    """Return the override row, or None unless all four rates are 0 to 10000."""
    spec = _as_obj(raw)
    if spec is None:
        return None
    values: dict[str, float] = {}
    for key, name in _OVERRIDE_KEYS.items():
        number = _number(spec.get(key))
        if number is None or not 0 <= number <= OVERRIDE_RATE_MAX:
            return None
        values[name] = number
    return ModelOverride(**values)


def model_pricing_layer(
    managed_settings_path: Path | None,
    catalog: model_catalog.Catalog | None = None,
) -> ModelPricingLayer:
    """Read ``modelPricing`` from a managed settings file.

    Claude Code reads this setting from managed sources only, so the caller passes
    the managed file and no user or project file. The shape is ``{"multiplier":
    number above 0 up to 10, "overrides": {<model id>: {"input", "output",
    "cacheRead", "cacheWrite"}}}`` in USD per million tokens. An override row needs
    all four rates, each from 0 to 10000. A missing, unreadable or malformed file
    gives an empty layer. A bad multiplier is ignored, and a bad (missing, out of
    range or non-numeric rate) or unknown override is skipped. The rest of the layer
    still applies.

    Args:
        managed_settings_path: The file, or None (the M1 default) to read nothing.
        catalog: The model catalog that maps override keys to ids.

    Returns:
        The layer.
    """
    if managed_settings_path is None:
        return ModelPricingLayer()
    try:
        if managed_settings_path.stat().st_size > MANAGED_SETTINGS_MAX_BYTES:
            return ModelPricingLayer()
        settings = _as_obj(_loads(managed_settings_path.read_bytes()))
    except (OSError, ValueError):
        return ModelPricingLayer()
    return model_pricing_from(settings, catalog)


def model_pricing_from(
    settings: Mapping[str, object] | None,
    catalog: model_catalog.Catalog | None = None,
) -> ModelPricingLayer:
    """Read ``modelPricing`` from managed settings that are already parsed.

    The setup read side reads the managed files through ``read_scope`` and hands the
    merged document here (``PriceSettings.managed_pricing``). The rules are those of
    ``model_pricing_layer``.

    Args:
        settings: The managed settings document, or None for none.
        catalog: The model catalog that maps override keys to ids.

    Returns:
        The layer, empty when the document has no usable ``modelPricing``.
    """
    models_catalog = catalog if catalog is not None else model_catalog.load_catalog()
    block = _as_obj(settings.get("modelPricing")) if settings is not None else None
    if block is None:
        return ModelPricingLayer()
    multiplier = _number(block.get("multiplier"))
    if multiplier is None or not 0 < multiplier <= MODIFIER_MULTIPLIER_MAX:
        multiplier = 1.0
    overrides: dict[str, ModelOverride] = {}
    for key, raw in (_as_obj(block.get("overrides")) or {}).items():
        model_id, _form = model_catalog.normalize_model(key, models_catalog)
        override = _override(raw)
        if model_id is not None and override is not None:
            overrides[model_id] = override
    return ModelPricingLayer(multiplier, overrides)


def _scale_rates(rates: dict[str, Any], factor: float) -> None:
    for name in PRICE_FIELDS:
        rates[name] = _scaled(float(rates[name]), factor)


def apply_layer(
    document: prices.PricesDoc, layer: ModelPricingLayer
) -> tuple[prices.PricesDoc, set[str]]:
    """Apply a ``modelPricing`` layer over a document.

    The multiplier scales every model's rates, tiers included, and scales an override
    row's rates too. An override replaces the model's rates and drops its tiers,
    because it states one flat rate. The row is marked ``flat_rate``, so
    ``prices.price_parts`` skips the modifiers (fast-mode surcharge, US-only
    inference rate) for that model, as Claude Code does.

    Args:
        document: The base prices document. It is not changed.
        layer: The layer.

    Returns:
        A new document and the ids of the models the layer touched.
    """
    out = copy.deepcopy(document)
    if layer.empty:
        return out, set()
    touched: set[str] = set()
    models = _as_obj(out.get("models")) or {}
    for model_id, raw in models.items():
        entry = cast("dict[str, Any]", raw)
        override = layer.overrides.get(model_id)
        if override is not None:
            _apply_override(entry, override, layer.multiplier)
            touched.add(model_id)
        elif layer.multiplier != 1.0:
            _scale_rates(entry, layer.multiplier)
            for tier in entry.get("tiers", []):
                _scale_rates(tier, layer.multiplier)
            touched.add(model_id)
    return out, touched


def _apply_override(
    entry: dict[str, Any], override: ModelOverride, multiplier: float
) -> None:
    entry.pop("tiers", None)
    entry["input"] = override.input
    entry["output"] = override.output
    entry["cache_read"] = override.cache_read
    entry["cache_write_5m"] = override.cache_write
    entry["cache_write_1h"] = override.cache_write
    if multiplier != 1.0:
        _scale_rates(entry, multiplier)
    entry[prices.FLAT_RATE] = True


# ---------------------------------------------------------------------------
# Source order and the answer


@dataclass(frozen=True)
class PriceSettings:
    """Where the price sources are.

    ``managed_pricing`` returns the parsed managed settings (the setup read side's
    ``collect_settings.ManagedPricing``, which reads through ``read_scope``). When it
    is set it wins over ``managed_settings_path``, which tests still use.
    """

    layout: StoreLayout
    managed_settings_path: Path | None = None
    catalog: model_catalog.Catalog | None = None
    bundled_dir: Path = BUNDLED_DIR
    managed_pricing: Callable[[], Mapping[str, object] | None] | None = None

    def models(self) -> model_catalog.Catalog:
        """Return the catalog, loading the bundled rules file when none was given."""
        return (
            self.catalog if self.catalog is not None else model_catalog.load_catalog()
        )


@dataclass(frozen=True)
class PriceTier:
    """A prompt-size tier. A request with more prompt tokens uses these rates."""

    prompt_tokens_over: int
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


@dataclass(frozen=True)
class PriceRow:
    """One model's effective rates, USD per million tokens.

    ``modifiers`` maps a field to the multipliers this model has, for example
    ``{"speed": {"fast": 2.0}, "inference_geo": {"us": 1.1}}``. ``relative`` is
    (input + output) over the same sum for the newest Sonnet in the catalog.
    """

    model: str
    source: Source
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    tiers: tuple[PriceTier, ...]
    modifiers: dict[str, dict[str, float]]
    relative: float | None


@dataclass(frozen=True)
class PricesAnswer:
    """What ``GET /api/prices`` serves.

    ``source`` is the source most rows use (ties go to the copy underneath the
    ``modelPricing`` layer). ``as_of`` is the date of that copy, as YYYY-MM-DD.
    ``etag`` is the hash of the effective table.
    """

    source: Source
    as_of: str
    etag: str
    cross_check: CrossCheck
    models: tuple[PriceRow, ...]


@dataclass(frozen=True)
class PriceTable:
    """The effective prices document and its hash, for query-time pricing."""

    document: prices.PricesDoc
    hash: str


@dataclass(frozen=True)
class _Base:
    document: prices.PricesDoc
    source: Literal["litellm", "last_good", "bundled"]
    as_of: str


@dataclass(frozen=True)
class _Effective:
    document: prices.PricesDoc
    hash: str
    base: _Base
    touched: frozenset[str]


_bundled_cache: dict[Path, tuple[prices.PricesDoc, str]] = {}


class BundledPricesError(RuntimeError):
    """The shipped bundled copy is unreadable or fails its own checks."""

    def __init__(self, why: str) -> None:
        """Say why. This is a build defect, not a runtime condition."""
        super().__init__(f"bundled prices: {why}")


def load_bundled(
    bundled_dir: Path = BUNDLED_DIR, catalog: model_catalog.Catalog | None = None
) -> tuple[prices.PricesDoc, str]:
    """Return the bundled copy's document and its fetch date (YYYY-MM-DD).

    The file is the manifest's ``file``, parsed with the same checks as a fetch.

    Raises:
        BundledPricesError: When the shipped copy fails its own checks.
    """
    cached = _bundled_cache.get(bundled_dir)
    if cached is not None and catalog is None:
        return cached
    manifest = _as_obj(
        json.loads((bundled_dir / "manifest.json").read_text(encoding="utf-8"))
    )
    if manifest is None or not isinstance(manifest.get("file"), str):
        raise BundledPricesError("manifest is malformed")  # noqa: TRY003
    fetched_at = str(manifest.get("fetched_at", UNKNOWN_DATE))
    body = (bundled_dir / str(manifest["file"])).read_bytes()
    result = parse_litellm(body, required=set(), fetched_at=fetched_at, catalog=catalog)
    if not result.ok or result.document is None or result.models == 0:
        raise BundledPricesError(f"checks failed with {result.reason_code}")  # noqa: TRY003
    loaded = (result.document, fetched_at[:10])
    if catalog is None:
        _bundled_cache[bundled_dir] = loaded
    return loaded


def _utc_text(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch(text: str) -> float | None:
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _read_last_good(settings: PriceSettings) -> prices.PricesDoc | None:
    try:
        parsed = _loads(settings.layout.last_good_prices.read_bytes())
    except (OSError, ValueError):
        return None
    if prices.check(parsed, settings.models()):
        return None
    return cast("prices.PricesDoc", parsed)


def _resolve_base(
    conn: sqlite3.Connection, settings: PriceSettings, now: float
) -> _Base:
    """Pick litellm, last_good or bundled from the ``price_copies`` rows."""
    newest = conn.execute(
        "SELECT fetched_at, check_ok FROM price_copies WHERE source = 'litellm' "
        "ORDER BY fetched_at DESC, id DESC LIMIT 1"
    ).fetchone()
    passing = conn.execute(
        "SELECT fetched_at FROM price_copies WHERE source = 'litellm' AND check_ok = 1 "
        "ORDER BY fetched_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if passing is not None:
        document = _read_last_good(settings)
        if document is not None:
            fetched_at = str(passing[0])
            stamp = _epoch(fetched_at)
            fresh = (
                newest is not None
                and bool(newest[1])
                and str(newest[0]) == fetched_at
                and stamp is not None
                and now - stamp <= ACTIVE_WINDOW_SECONDS
            )
            return _Base(document, "litellm" if fresh else "last_good", fetched_at[:10])
    document, as_of = load_bundled(settings.bundled_dir)
    return _Base(document, "bundled", as_of)


def _effective(
    conn: sqlite3.Connection, settings: PriceSettings, now: float
) -> _Effective:
    base = _resolve_base(conn, settings, now)
    if settings.managed_pricing is not None:
        layer = model_pricing_from(settings.managed_pricing(), settings.catalog)
    else:
        layer = model_pricing_layer(settings.managed_settings_path, settings.catalog)
    document, touched = apply_layer(base.document, layer)
    return _Effective(document, table_hash(document), base, frozenset(touched))


def price_table(
    conn: sqlite3.Connection, settings: PriceSettings, *, now: float
) -> PriceTable:
    """Return the effective prices document and its hash.

    The document works with ``prices.price_parts`` as it is. Callers that price many
    requests keep the result and key their caches on ``hash``.

    Args:
        conn: A connection to the store (a read connection is enough).
        settings: Where the sources are.
        now: Epoch seconds from the injected clock.
    """
    effective = _effective(conn, settings, now)
    return PriceTable(effective.document, effective.hash)


def _newest_sonnet(model_ids: list[str]) -> str | None:
    best: tuple[int, int] | None = None
    best_id: str | None = None
    for model_id in model_ids:
        match = _SONNET.match(model_id)
        if match is None:
            continue
        version = (int(match.group(1)), int(match.group(2) or 0))
        if best is None or version > best:
            best, best_id = version, model_id
    return best_id


def _row_modifiers(
    document: prices.PricesDoc, model_id: str
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    models = _as_obj(document.get("models")) or {}
    row = _as_obj(models.get(model_id)) or {}
    if row.get(prices.FLAT_RATE) is True:
        return out
    modifiers = _as_obj(document.get("modifiers")) or {}
    for field_name in prices.MODIFIER_FIELDS:
        for name, raw in (_as_obj(modifiers.get(field_name)) or {}).items():
            spec = _as_obj(raw)
            listed = _as_list(spec.get("models")) if spec is not None else None
            multiplier = _number(spec.get("multiplier")) if spec is not None else None
            if listed is not None and multiplier is not None and model_id in listed:
                out.setdefault(field_name, {})[name] = multiplier
    return out


def _row(
    document: prices.PricesDoc, model_id: str, source: Source, reference: float | None
) -> PriceRow:
    entry = cast("dict[str, Any]", (_as_obj(document["models"]) or {})[model_id])
    tiers = tuple(
        PriceTier(
            int(tier["prompt_tokens_over"]),
            *(float(tier[name]) for name in PRICE_FIELDS),
        )
        for tier in entry.get("tiers", [])
    )
    blended = float(entry["input"]) + float(entry["output"])
    return PriceRow(
        model=model_id,
        source=source,
        input=float(entry["input"]),
        output=float(entry["output"]),
        cache_read=float(entry["cache_read"]),
        cache_write_5m=float(entry["cache_write_5m"]),
        cache_write_1h=float(entry["cache_write_1h"]),
        tiers=tiers,
        modifiers=_row_modifiers(document, model_id),
        relative=round(blended / reference, 4) if reference else None,
    )


def _stored_cross_check(conn: sqlite3.Connection, now: float) -> CrossCheck:
    row = conn.execute(
        "SELECT fetched_at, cross_check_state, cross_check_models FROM price_copies "
        "WHERE source = 'openrouter' AND check_ok = 1 "
        "ORDER BY fetched_at DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return CrossCheck()
    stamp = _epoch(str(row[0]))
    if stamp is None or now - stamp > ACTIVE_WINDOW_SECONDS:
        return CrossCheck()
    state = str(row[1])
    if state not in ("agree", "disagree"):
        return CrossCheck()
    try:
        listed = _as_list(json.loads(str(row[2] or "[]"))) or []
    except ValueError:
        listed = []
    return CrossCheck(cast("CrossState", state), tuple(str(item) for item in listed))


def current_prices(
    conn: sqlite3.Connection, settings: PriceSettings, *, now: float
) -> PricesAnswer:
    """Return the answer ``GET /api/prices`` serves.

    Rows come from the effective table, one per catalog model with a price, in
    catalog order. Each row's ``source`` is ``model_pricing`` when the managed layer
    touched it, else the copy underneath.

    Args:
        conn: A connection to the store (a read connection is enough).
        settings: Where the sources are.
        now: Epoch seconds from the injected clock.
    """
    effective = _effective(conn, settings, now)
    document = effective.document
    in_table = _as_obj(document["models"]) or {}
    ordered = [str(m["id"]) for m in settings.models() if str(m.get("id")) in in_table]
    sonnet = _newest_sonnet(ordered)
    reference: float | None = None
    if sonnet is not None:
        entry = cast("dict[str, Any]", in_table[sonnet])
        reference = float(entry["input"]) + float(entry["output"])
    rows = tuple(
        _row(
            document,
            model_id,
            "model_pricing" if model_id in effective.touched else effective.base.source,
            reference,
        )
        for model_id in ordered
    )
    counts: Counter[Source] = Counter(row.source for row in rows)
    base_source: Source = effective.base.source
    source: Source = base_source
    for name in counts:
        if counts[name] > counts[source]:
            source = name
    return PricesAnswer(
        source=source,
        as_of=effective.base.as_of,
        etag=effective.hash,
        cross_check=_stored_cross_check(conn, now),
        models=rows,
    )


def required_models(
    conn: sqlite3.Connection,
    now: float,
    catalog: model_catalog.Catalog | None = None,
) -> set[str]:
    """Return the ids a LiteLLM copy must list.

    That is every catalog model plus every catalog model the store has requests for
    in the last 30 days.
    """
    models_catalog = catalog if catalog is not None else model_catalog.load_catalog()
    needed = {str(m["id"]) for m in models_catalog}
    since = _utc_text(now - REQUIRED_WINDOW_SECONDS)
    for (raw,) in conn.execute(
        "SELECT DISTINCT model FROM requests WHERE ts >= ?", (since,)
    ):
        model_id, _form = model_catalog.normalize_model(raw, models_catalog)
        if model_id is not None:
            needed.add(model_id)
    return needed


# ---------------------------------------------------------------------------
# The fetch schedule


@dataclass(frozen=True)
class _Fetched:
    """One fetch, ready to record."""

    source: Literal["litellm", "openrouter"]
    fetched_at: str
    sha256: str
    size: int
    ok: bool
    reason_code: str | None
    models: int
    cross: CrossCheck
    last_good: bytes | None = None


def _insert_copy(conn: sqlite3.Connection, row: _Fetched) -> None:
    conn.execute(
        "INSERT INTO price_copies (fetched_at, source, sha256, bytes, check_ok, "
        "reason_code, models, cross_check_state, cross_check_models) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            row.fetched_at,
            row.source,
            row.sha256,
            row.size,
            int(row.ok),
            row.reason_code,
            row.models,
            row.cross.state if row.source == "openrouter" else None,
            json.dumps(list(row.cross.models)) if row.source == "openrouter" else None,
        ),
    )


def _record_job(layout: StoreLayout, row: _Fetched) -> Job:
    """Build the writer job for one fetch.

    The job writes ``last-good.json`` first (a passing LiteLLM copy only), then the
    row, so a row that says "passed" always has its file. A write error propagates to
    the writer, and no row is recorded.
    """

    def job(conn: sqlite3.Connection) -> None:
        if row.last_good is not None:
            platform_os.mkdir_private(
                store_paths.writable(layout, layout.prices_dir), parents=True
            )
            platform_os.atomic_write(
                store_paths.writable(layout, layout.last_good_prices), row.last_good
            )
        own_transaction = not conn.in_transaction
        if own_transaction:
            conn.execute("BEGIN IMMEDIATE")
        try:
            _insert_copy(conn, row)
        except BaseException:
            if own_transaction:
                conn.execute("ROLLBACK")
            raise
        if own_transaction:
            conn.execute("COMMIT")

    return job


class PriceFeed:
    """The daily fetch. Network work runs here, writes run on the store writer.

    ``tick()`` fetches when a fetch is due and returns whether it did. ``start()``
    runs ``run_loop()`` on a daemon thread. A fetch is due at start when the newest
    ``price_copies`` row is over 24 hours old (or there is none), then every 24 hours.
    ``enabled=False`` makes ``start()`` do nothing (the ``--no-price-fetch`` flag).
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        transport: Transport,
        submit: Submit,
        settings: PriceSettings,
        open_reader: Callable[[], sqlite3.Connection],
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] | None = None,
        enabled: bool = True,
    ) -> None:
        """Wire the feed. Nothing runs until ``start``, ``tick`` or ``run_once``.

        Args:
            transport: The injected network. Tests pass a fake.
            submit: Queues a job on the store writer.
            settings: Where the sources are.
            open_reader: Opens a read connection to the store. The feed closes it.
            clock: Epoch seconds.
            sleep: Waits between polls. The default waits on the stop event.
            enabled: False turns the thread off.
        """
        self._transport = transport
        self._submit = submit
        self._settings = settings
        self._open_reader = open_reader
        self._clock = clock
        self._stop = threading.Event()
        self._sleep = sleep if sleep is not None else self._wait
        self._enabled = enabled
        self._next_due: float | None = None
        self._thread: threading.Thread | None = None

    def _wait(self, seconds: float) -> None:
        self._stop.wait(seconds)

    def _last_attempt(self, conn: sqlite3.Connection) -> float | None:
        row = conn.execute("SELECT MAX(fetched_at) FROM price_copies").fetchone()
        return _epoch(str(row[0])) if row is not None and row[0] else None

    def due(self) -> bool:
        """Return True when a fetch is due now."""
        now = self._clock()
        if self._next_due is None:
            conn = self._open_reader()
            try:
                last = self._last_attempt(conn)
            finally:
                conn.close()
            self._next_due = now if last is None else last + FETCH_INTERVAL_SECONDS
        return now >= self._next_due

    def tick(self) -> bool:
        """Fetch when due. Returns True when it did."""
        if not self.due():
            return False
        self.run_once()
        return True

    def run_once(self) -> None:
        """Fetch LiteLLM, then OpenRouter, and submit one writer job for each.

        A passing LiteLLM copy is the document OpenRouter is checked against. When
        LiteLLM failed, the check runs against the document now in use (the last good
        copy, else the bundled one). The next fetch is due 24 hours on once both jobs
        are submitted, a failed fetch recorded as a failed copy included. A pass that
        raises first leaves it ``FAILURE_BACKOFF_SECONDS`` on.
        """
        now = self._clock()
        # Until both jobs are submitted, a raise leaves the short backoff in place.
        self._next_due = now + FAILURE_BACKOFF_SECONDS
        stamp = _utc_text(now)
        conn = self._open_reader()
        try:
            required = required_models(conn, now, self._settings.catalog)
            litellm, document = self._fetch_litellm(stamp, required)
            self._submit(_record_job(self._settings.layout, litellm))
            active = (
                document
                if document is not None
                else _resolve_base(conn, self._settings, now).document
            )
        finally:
            conn.close()
        openrouter = self._fetch_openrouter(stamp, active)
        self._submit(_record_job(self._settings.layout, openrouter))
        self._next_due = now + FETCH_INTERVAL_SECONDS

    def _fetch_litellm(
        self, stamp: str, required: set[str]
    ) -> tuple[_Fetched, prices.PricesDoc | None]:
        try:
            body = self._transport.fetch(
                LITELLM_URL, timeout=DEFAULT_TIMEOUT, max_bytes=LITELLM_MAX_BYTES
            )
        except FetchError as exc:
            return _failed("litellm", stamp, exc.reason_code), None
        result = parse_litellm(
            body,
            required=required,
            fetched_at=stamp,
            catalog=self._settings.catalog,
        )
        digest = hashlib.sha256(body).hexdigest()
        if not result.ok or result.document is None:
            logger.warning("litellm copy refused: %s", result.reason_code)
            return (
                _Fetched(
                    "litellm",
                    stamp,
                    digest,
                    len(body),
                    ok=False,
                    reason_code=result.reason_code,
                    models=0,
                    cross=CrossCheck(),
                ),
                None,
            )
        return (
            _Fetched(
                "litellm",
                stamp,
                digest,
                len(body),
                ok=True,
                reason_code=None,
                models=result.models,
                cross=CrossCheck(),
                last_good=canonical_json(result.document) + b"\n",
            ),
            result.document,
        )

    def _fetch_openrouter(self, stamp: str, active: prices.PricesDoc) -> _Fetched:
        try:
            body = self._transport.fetch(
                OPENROUTER_URL, timeout=DEFAULT_TIMEOUT, max_bytes=OPENROUTER_MAX_BYTES
            )
        except FetchError as exc:
            return _failed("openrouter", stamp, exc.reason_code)
        digest = hashlib.sha256(body).hexdigest()
        rates = parse_openrouter(body, self._settings.catalog)
        if rates is None:
            return _Fetched(
                "openrouter",
                stamp,
                digest,
                len(body),
                ok=False,
                reason_code="not_json",
                models=0,
                cross=CrossCheck(),
            )
        return _Fetched(
            "openrouter",
            stamp,
            digest,
            len(body),
            ok=True,
            reason_code=None,
            models=len(rates),
            cross=cross_check(active, rates),
        )

    def start(self) -> None:
        """Start the feed thread. Does nothing when disabled or already started."""
        if not self._enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self.run_loop, name="price_feed", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Ask the loop to end and wait for the thread."""
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=DEFAULT_TIMEOUT * 3)

    def run_loop(self) -> None:
        """Poll until ``stop``. A failed pass is logged and never ends the loop."""
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.warning("price feed pass failed", exc_info=True)
            if self._stop.is_set():
                break
            self._sleep(POLL_SECONDS)


def _failed(
    source: Literal["litellm", "openrouter"], stamp: str, reason: str
) -> _Fetched:
    """A fetch that returned no body. Its hash is empty."""
    return _Fetched(
        source,
        stamp,
        "",
        0,
        ok=False,
        reason_code=reason,
        models=0,
        cross=CrossCheck(),
    )
