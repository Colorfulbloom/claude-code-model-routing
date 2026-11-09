"""Tests for price_feed, on fixture files and a fake transport. No network."""

import copy
import hashlib
import itertools
import json
import sqlite3
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import model_catalog
import platform_os
import price_feed
import prices
import store
import usage_query
from price_feed import (
    CheckResult,
    PriceFeed,
    PriceSettings,
    cross_check,
    current_prices,
    model_pricing_layer,
    parse_litellm,
    parse_openrouter,
    price_table,
)
from price_transport import LITELLM_URL, OPENROUTER_URL, FetchError, FetchReason
from store_paths import StoreLayout

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "prices"
CATALOG = model_catalog.load_catalog()
CATALOG_IDS = {str(m["id"]) for m in CATALOG}
T0 = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC).timestamp()
HOUR = 3600.0
STAMP = "2026-11-08T12:00:00Z"


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def good_doc() -> prices.PricesDoc:
    result = parse_litellm(fixture("litellm_good.json"), required=CATALOG_IDS)
    assert result.document is not None
    return result.document


def raw_good() -> dict[str, Any]:
    return json.loads(fixture("litellm_good.json"))


def encode(data: object) -> bytes:
    return json.dumps(data).encode()


def check(data: dict[str, Any], required: set[str] | None = None) -> CheckResult:
    return parse_litellm(
        encode(data), required=CATALOG_IDS if required is None else required
    )


# --- parse_litellm: the good file -------------------------------------------


def test_the_good_file_passes_and_builds_a_clean_document() -> None:
    result = parse_litellm(
        fixture("litellm_good.json"), required=CATALOG_IDS, fetched_at=STAMP
    )
    assert result.ok
    assert result.reason_code is None
    assert result.models == 12
    assert result.document is not None
    assert prices.check(result.document, CATALOG) == []
    assert result.document["verified_on"] == "2026-11-08"
    assert result.document["source"] == LITELLM_URL
    assert result.document["unit"] == "USD per million tokens"


def test_rates_are_converted_to_per_million_without_float_noise() -> None:
    models = good_doc()["models"]
    assert models["claude-opus-5-5"] == {
        "input": 4,
        "output": 20,
        "cache_read": 0.2,
        "cache_write_5m": 5,
        "cache_write_1h": 8,
    }
    assert models["claude-haiku-5-5"]["input"] == 0.1
    assert models["claude-haiku-5-5"]["cache_write_5m"] == 0.125
    assert models["claude-fable-5-1"]["cache_read"] == 0.25


def test_the_haiku_tier_comes_through_with_its_threshold() -> None:
    tiers = good_doc()["models"]["claude-haiku-5-5"]["tiers"]
    assert tiers == [
        {
            "prompt_tokens_over": 100000,
            "input": 0.5,
            "output": 2.5,
            "cache_read": 0.05,
            "cache_write_5m": 0.625,
            "cache_write_1h": 1,
        }
    ]
    assert "tiers" not in good_doc()["models"]["claude-opus-5"]


def test_the_modifiers_follow_provider_specific_entry() -> None:
    modifiers = good_doc()["modifiers"]
    assert modifiers["speed"]["fast"] == {
        "multiplier": 2.0,
        "models": ["claude-opus-4-8", "claude-opus-5", "claude-opus-5-5"],
    }
    us = modifiers["inference_geo"]["us"]
    assert us["multiplier"] == 1.1
    assert "claude-haiku-4-5" not in us["models"]
    assert len(us["models"]) == 11
    assert modifiers["service_tier"] == {"standard": 1}
    assert modifiers["inference_geo"]["global"] == 1


def test_rows_of_other_providers_and_models_outside_the_catalog_are_dropped() -> None:
    models = good_doc()["models"]
    assert set(models) == CATALOG_IDS
    # claude-mythos-5 is an Anthropic row that is not in the catalog.
    assert "claude-mythos-5" in raw_good()
    assert "gpt-fixture-4" not in models
    # The Vertex row for claude-opus-5 must not replace the Anthropic one.
    assert models["claude-opus-5"]["input"] == 5


def test_a_dated_key_is_used_when_the_plain_key_is_missing() -> None:
    data = raw_good()
    del data["claude-haiku-4-5"]
    result = check(data)
    assert result.ok
    assert result.document is not None
    assert result.document["models"]["claude-haiku-4-5"]["input"] == 1


def test_the_plain_key_beats_a_dated_one() -> None:
    data = raw_good()
    data["claude-haiku-4-5-20251001"]["input_cost_per_token"] = 2e-06
    data["claude-haiku-4-5-20251001"]["cache_read_input_token_cost"] = 2e-07
    result = check(data)
    assert result.document is not None
    assert result.document["models"]["claude-haiku-4-5"]["input"] == 1


def test_the_newest_dated_key_wins_among_dated_keys() -> None:
    data = raw_good()
    del data["claude-haiku-4-5"]
    older = copy.deepcopy(data["claude-haiku-4-5-20251001"])
    older["input_cost_per_token"] = 3e-06
    older["cache_read_input_token_cost"] = 3e-07
    data["claude-haiku-4-5-20240101"] = older
    result = check(data)
    assert result.document is not None
    assert result.document["models"]["claude-haiku-4-5"]["input"] == 1


def test_a_file_with_no_modifiers_has_no_fast_or_us_list() -> None:
    data = raw_good()
    for row in data.values():
        row.pop("provider_specific_entry", None)
    result = check(data)
    assert result.ok
    assert result.document is not None
    assert "fast" not in result.document["modifiers"]["speed"]
    assert "us" not in result.document["modifiers"]["inference_geo"]
    assert prices.check(result.document, CATALOG) == []


def test_a_missing_fetch_time_gives_a_placeholder_date() -> None:
    result = parse_litellm(fixture("litellm_good.json"), required=set())
    assert result.document is not None
    assert result.document["verified_on"] == "1970-01-01"


# --- parse_litellm: the failures -------------------------------------------


def test_missing_model_fixture() -> None:
    result = parse_litellm(fixture("litellm_missing_model.json"), required=CATALOG_IDS)
    assert not result.ok
    assert result.reason_code == "missing_model"
    assert result.detail == ("claude-opus-5-5",)
    assert result.document is None


def test_out_of_range_fixture() -> None:
    result = parse_litellm(fixture("litellm_out_of_range.json"), required=CATALOG_IDS)
    assert result.reason_code == "out_of_range"
    assert result.detail == ("claude-sonnet-5",)


def test_cache_ratio_fixture() -> None:
    result = parse_litellm(fixture("litellm_cache_ratio.json"), required=CATALOG_IDS)
    assert result.reason_code == "cache_ratio"
    assert result.detail == ("claude-opus-4-6",)


def test_malformed_fixture() -> None:
    result = parse_litellm(fixture("litellm_malformed.json"), required=CATALOG_IDS)
    assert result.reason_code == "not_json"
    assert result.document is None


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b'"text"',
        b"42",
        b"null",
        b'{"a": NaN}',
        b'{"a": Infinity}',
        b"\xff\xfe\x00",
        b"[" * 100_000,
    ],
)
def test_a_body_that_is_not_a_json_object_is_not_json(body: bytes) -> None:
    assert parse_litellm(body, required=set()).reason_code == "not_json"


def test_an_object_with_no_anthropic_rows_is_missing_models() -> None:
    result = parse_litellm(
        b'{"gpt-4": {"litellm_provider": "openai"}}', required={"claude-opus-5"}
    )
    assert result.reason_code == "missing_model"


def test_a_row_that_is_not_an_object_is_ignored() -> None:
    data = raw_good()
    data["claude-weird"] = [1, 2, 3]
    data["sample_spec"] = "text"
    assert check(data).ok


def test_required_models_beyond_the_catalog_must_be_present() -> None:
    result = check(raw_good(), required=CATALOG_IDS | {"claude-opus-9"})
    assert result.reason_code == "missing_model"
    assert result.detail == ("claude-opus-9",)


def test_an_empty_required_set_asks_for_nothing() -> None:
    assert parse_litellm(b"{}", required=set()).ok


def test_the_checks_run_in_order() -> None:
    data = raw_good()
    del data["claude-opus-5-5"]
    data["claude-sonnet-5"]["input_cost_per_token"] = 0.002
    data["claude-opus-4-6"]["cache_read_input_token_cost"] = 5e-06
    assert check(data).reason_code == "missing_model"
    data["claude-opus-5-5"] = raw_good()["claude-opus-5-5"]
    assert check(data).reason_code == "out_of_range"
    data["claude-sonnet-5"] = raw_good()["claude-sonnet-5"]
    assert check(data).reason_code == "cache_ratio"
    data["claude-opus-4-6"] = raw_good()["claude-opus-4-6"]
    assert check(data).ok


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("input_cost_per_token", 4e-08),
        ("input_cost_per_token", 1.01e-04),
        ("input_cost_per_token", 0),
        ("input_cost_per_token", -1e-06),
        ("input_cost_per_token", "0.000005"),
        ("input_cost_per_token", None),
        ("input_cost_per_token", True),
        ("output_cost_per_token", 1.9e-07),
        ("output_cost_per_token", 5.1e-04),
        ("output_cost_per_token", None),
        ("cache_creation_input_token_cost", None),
        ("cache_creation_input_token_cost", 0),
        ("cache_creation_input_token_cost", 1.1e-03),
        ("cache_creation_input_token_cost_above_1hr", None),
        ("cache_read_input_token_cost", None),
    ],
)
def test_a_bad_rate_is_out_of_range(field: str, value: object) -> None:
    data = raw_good()
    data["claude-opus-5"][field] = value
    if field == "input_cost_per_token" and isinstance(value, float) and value > 0:
        # Keep the cache ratio sane so the range check is what fires.
        data["claude-opus-5"]["cache_read_input_token_cost"] = value / 10
    result = check(data)
    assert result.reason_code == "out_of_range"
    assert "claude-opus-5" in result.detail


@pytest.mark.parametrize(
    ("input_rate", "output_rate"),
    [(5.0e-08, 2.0e-07), (1.0e-04, 5.0e-04)],
)
def test_the_range_edges_are_inclusive(input_rate: float, output_rate: float) -> None:
    data = raw_good()
    row = data["claude-opus-5"]
    row["input_cost_per_token"] = input_rate
    row["output_cost_per_token"] = output_rate
    row["cache_read_input_token_cost"] = input_rate / 10
    row["cache_creation_input_token_cost"] = input_rate * 1.25
    row["cache_creation_input_token_cost_above_1hr"] = input_rate * 2
    assert check(data).ok


@pytest.mark.parametrize(
    ("ratio", "ok"),
    [(0.005, False), (0.01, True), (0.12, True), (0.13, False), (1.0, False)],
)
def test_the_cache_ratio_band_is_one_to_twelve_percent(ratio: float, ok: bool) -> None:
    data = raw_good()
    data["claude-opus-5"]["cache_read_input_token_cost"] = 5e-06 * ratio
    result = check(data)
    assert result.ok is ok
    if not ok:
        assert result.reason_code == "cache_ratio"


def test_the_band_accepts_every_ratio_in_the_real_november_8_file() -> None:
    models = good_doc()["models"]
    ratios = {m: e["cache_read"] / e["input"] for m, e in models.items()}
    assert min(ratios.values()) == pytest.approx(0.025)
    assert max(ratios.values()) == pytest.approx(0.10)


def test_a_tier_that_is_out_of_range_fails_the_copy() -> None:
    data = raw_good()
    data["claude-haiku-5-5"]["input_cost_per_token_above_100k_tokens"] = 5e-03
    result = check(data)
    assert result.reason_code == "out_of_range"
    assert result.detail == ("claude-haiku-5-5",)


def test_a_tier_with_a_bad_cache_ratio_fails_the_copy() -> None:
    data = raw_good()
    data["claude-haiku-5-5"]["cache_read_input_token_cost_above_100k_tokens"] = 5e-07
    assert check(data).reason_code == "cache_ratio"


def test_a_tier_missing_a_field_fails_the_copy() -> None:
    data = raw_good()
    del data["claude-haiku-5-5"][
        "cache_creation_input_token_cost_above_1hr_above_100k_tokens"
    ]
    assert check(data).reason_code == "out_of_range"


def test_batch_prices_never_reach_the_document() -> None:
    data = raw_good()
    data["claude-opus-5"]["input_cost_per_token_batches"] = 2.5e-06
    data["claude-opus-5"]["input_cost_per_token_above_100k_tokens_batches"] = 9e-06
    result = check(data)
    assert result.document is not None
    assert "tiers" not in result.document["models"]["claude-opus-5"]


@pytest.mark.parametrize("value", [0.5, 11, "2", True, -2])
def test_a_bad_modifier_value_is_out_of_range(value: object) -> None:
    data = raw_good()
    data["claude-opus-5"]["provider_specific_entry"]["fast"] = value
    result = check(data)
    assert result.reason_code == "out_of_range"
    assert result.detail == ("modifier:fast",)


def test_models_that_disagree_on_a_multiplier_are_out_of_range() -> None:
    data = raw_good()
    data["claude-opus-5"]["provider_specific_entry"]["fast"] = 3
    result = check(data)
    assert result.reason_code == "out_of_range"
    assert result.detail == ("modifier:fast",)


# --- the bundled copy -------------------------------------------------------


BUNDLED = price_feed.BUNDLED_DIR


def test_the_manifest_matches_the_bundled_file() -> None:
    manifest = json.loads((BUNDLED / "manifest.json").read_text(encoding="utf-8"))
    body = (BUNDLED / manifest["file"]).read_bytes()
    assert manifest["file"] == "litellm-anthropic-2026-11-08.json"
    assert hashlib.sha256(body).hexdigest() == manifest["file_sha256"]
    assert manifest["url"] == LITELLM_URL
    assert manifest["fetched_at"] == "2026-11-08T21:52:58-05:00"
    assert len(manifest["download_sha256"]) == 64
    assert manifest["download_bytes"] == 3474076
    rows = json.loads(body)
    assert manifest["rows"] == len(rows) == 22
    assert body.endswith(b"}\n")
    assert body == (json.dumps(rows, sort_keys=True, indent=2) + "\n").encode()


def test_every_bundled_row_is_anthropic() -> None:
    manifest = json.loads((BUNDLED / "manifest.json").read_text(encoding="utf-8"))
    rows = json.loads((BUNDLED / manifest["file"]).read_bytes())
    assert {row["litellm_provider"] for row in rows.values()} == {"anthropic"}


def test_the_bundled_copy_loads_with_its_fetch_date() -> None:
    document, as_of = price_feed.load_bundled()
    assert as_of == "2026-11-08"
    assert prices.check(document, CATALOG) == []
    assert set(document["models"]) == CATALOG_IDS


def test_a_damaged_bundled_copy_is_a_build_defect(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text(
        json.dumps({"file": "x.json", "fetched_at": "2026-11-08T00:00:00Z"}),
        encoding="utf-8",
    )
    (tmp_path / "x.json").write_text("{}", encoding="utf-8")
    with pytest.raises(price_feed.BundledPricesError):
        price_feed.load_bundled(tmp_path, CATALOG)
    (tmp_path / "manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(price_feed.BundledPricesError):
        price_feed.load_bundled(tmp_path, CATALOG)


def rec(model: str, **fields: Any) -> Any:
    base = {
        "input": 0,
        "output": 0,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
        "speed": None,
        "service_tier": None,
        "inference_geo": None,
    }
    return SimpleNamespace(model_raw=model, **{**base, **fields})


TOKEN_SIZES = [
    {
        "input": 1000,
        "output": 500,
        "cache_read": 2000,
        "cache_write_5m": 300,
        "cache_write_1h": 40,
    },
    {
        "input": 90_000,
        "output": 10,
        "cache_read": 5_000,
        "cache_write_5m": 4_000,
        "cache_write_1h": 900,
    },
    # Over 100,000 prompt tokens, so the Haiku 5.5 tier applies.
    {
        "input": 60_000,
        "output": 7_000,
        "cache_read": 50_000,
        "cache_write_5m": 1_000,
        "cache_write_1h": 2_000,
    },
    {
        "input": 100_001,
        "output": 1,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    },
    {
        "input": 100_000,
        "output": 1,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    },
]
SPEEDS = [None, "standard", "fast", "turbo"]
TIERS = [None, "standard", "priority"]
GEOS = [None, "global", "us", "not_available", "eu"]


def test_the_bundled_copy_prices_like_prices_old_for_every_case() -> None:
    old = prices.load_prices()
    new, _ = price_feed.load_bundled()
    cases = 0
    for model, tokens, speed, tier, geo in itertools.product(
        sorted(CATALOG_IDS), TOKEN_SIZES, SPEEDS, TIERS, GEOS
    ):
        record = rec(model, speed=speed, service_tier=tier, inference_geo=geo, **tokens)
        assert prices.price_parts(record, new, CATALOG) == prices.price_parts(
            record, old, CATALOG
        ), (model, speed, tier, geo, tokens)
        cases += 1
    assert cases == 12 * 5 * 4 * 3 * 5


def test_the_old_and_new_tables_agree_on_every_rate_and_modifier_list() -> None:
    old = prices.load_prices()
    new, _ = price_feed.load_bundled()
    assert new["models"] == old["models"]
    for field, key in (("speed", "fast"), ("inference_geo", "us")):
        assert (
            new["modifiers"][field][key]["multiplier"]
            == old["modifiers"][field][key]["multiplier"]
        )
        assert sorted(new["modifiers"][field][key]["models"]) == sorted(
            old["modifiers"][field][key]["models"]
        )


def test_an_unlisted_model_or_modifier_still_has_no_price() -> None:
    new, _ = price_feed.load_bundled()
    assert (
        prices.price_parts(rec("claude-opus-4-7", speed="fast"), new, CATALOG) is None
    )
    assert (
        prices.price_parts(rec("claude-haiku-4-5", inference_geo="us"), new, CATALOG)
        is None
    )
    assert prices.price_parts(rec("claude-unknown-1"), new, CATALOG) is None


# --- OpenRouter and the cross-check ----------------------------------------


def test_openrouter_ids_map_to_catalog_ids() -> None:
    rates = parse_openrouter(fixture("openrouter_agree.json"))
    assert rates is not None
    # opus-4.5, opus-4.1 and sonnet-4.5 are in the file but not in the catalog.
    assert set(rates) == CATALOG_IDS
    assert rates["claude-opus-4-8"] == (5.0, 25.0)
    assert rates["claude-fable-5-1"] == (10.0, 50.0)
    assert rates["claude-haiku-5-5"] == (0.1, 0.5)


def test_batch_rows_and_other_providers_are_skipped() -> None:
    rates = parse_openrouter(fixture("openrouter_agree.json"))
    assert rates is not None
    # The :batch row for opus-4.8 is half the price. If it leaked in, this would be 2.5.
    assert rates["claude-opus-4-8"][0] == 5.0
    assert not any("gpt" in key for key in rates)


@pytest.mark.parametrize(
    "body",
    [b"", b"[]", b'{"data": 3}', b'{"other": []}', b"{", b'{"data": NaN}'],
)
def test_a_body_that_is_not_an_openrouter_list_is_none(body: bytes) -> None:
    assert parse_openrouter(body) is None


def test_a_row_with_a_bad_price_is_skipped() -> None:
    body = encode(
        {
            "data": [
                {
                    "id": "anthropic/claude-opus-5",
                    "pricing": {"prompt": "free", "completion": "1"},
                },
                {"id": "anthropic/claude-sonnet-5", "pricing": {"prompt": "0.000002"}},
                {
                    "id": "anthropic/claude-opus-4.8",
                    "pricing": {"prompt": "0.000005", "completion": "0.000025"},
                },
                "junk",
                {"id": 5},
            ]
        }
    )
    assert parse_openrouter(body) == {"claude-opus-4-8": (5.0, 25.0)}


def test_the_agree_fixture_agrees_with_the_good_copy() -> None:
    rates = parse_openrouter(fixture("openrouter_agree.json"))
    result = cross_check(good_doc(), rates)
    assert result.state == "agree"
    assert result.models == ()


def test_the_disagree_fixture_names_the_model() -> None:
    rates = parse_openrouter(fixture("openrouter_disagree.json"))
    result = cross_check(good_doc(), rates)
    assert result.state == "disagree"
    assert result.models == ("claude-opus-5-5",)


@pytest.mark.parametrize(
    ("theirs", "state"),
    [(5.049, "agree"), (4.95, "agree"), (5.051, "disagree"), (4.9, "disagree")],
)
def test_the_tolerance_is_one_percent(theirs: float, state: str) -> None:
    result = cross_check(good_doc(), {"claude-opus-5": (theirs, 25.0)})
    assert result.state == state


def test_a_difference_in_output_alone_disagrees() -> None:
    result = cross_check(good_doc(), {"claude-opus-5": (5.0, 30.0)})
    assert result.state == "disagree"


def test_no_rates_or_no_common_model_is_not_checked() -> None:
    assert cross_check(good_doc(), None).state == "not_checked"
    assert cross_check(good_doc(), {}).state == "not_checked"
    assert cross_check(good_doc(), {"claude-other": (1.0, 2.0)}).state == "not_checked"


def test_the_cross_check_never_changes_the_document() -> None:
    doc = good_doc()
    before = price_feed.table_hash(doc)
    cross_check(doc, parse_openrouter(fixture("openrouter_disagree.json")))
    assert price_feed.table_hash(doc) == before


# --- the modelPricing layer -------------------------------------------------


def write_settings(tmp_path: Path, data: object) -> Path:
    path = tmp_path / "managed-settings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def full_row(**changes: float) -> dict[str, float]:
    """An override row with all four rates, which Claude Code requires."""
    return {"input": 1, "output": 2, "cacheRead": 0.1, "cacheWrite": 1.5} | changes


def test_no_path_reads_nothing() -> None:
    assert model_pricing_layer(None).empty


def test_a_missing_or_bad_file_gives_an_empty_layer(tmp_path: Path) -> None:
    assert model_pricing_layer(tmp_path / "nope.json").empty
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert model_pricing_layer(bad).empty
    bad.write_text("[]", encoding="utf-8")
    assert model_pricing_layer(bad).empty
    assert model_pricing_layer(tmp_path).empty  # a folder, not a file


def test_a_file_over_the_size_cap_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_settings(tmp_path, {"modelPricing": {"multiplier": 2}})
    monkeypatch.setattr(price_feed, "MANAGED_SETTINGS_MAX_BYTES", 5)
    assert model_pricing_layer(path).empty


def test_a_file_without_model_pricing_gives_an_empty_layer(tmp_path: Path) -> None:
    assert model_pricing_layer(write_settings(tmp_path, {"model": "opus"})).empty
    assert model_pricing_layer(write_settings(tmp_path, {"modelPricing": 3})).empty


def test_the_multiplier_and_overrides_are_read(tmp_path: Path) -> None:
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {
                "model": "opus",
                "modelPricing": {
                    "multiplier": 0.5,
                    "overrides": {
                        "claude-opus-5": {
                            "input": 1,
                            "output": 2,
                            "cacheRead": 0.1,
                            "cacheWrite": 1.5,
                        }
                    },
                },
            },
        )
    )
    assert layer.multiplier == 0.5
    assert layer.overrides == {
        "claude-opus-5": price_feed.ModelOverride(1, 2, 0.1, 1.5)
    }
    assert not layer.empty


@pytest.mark.parametrize("bad", [0, -1, 10.5, "2", True, None, [2]])
def test_a_bad_multiplier_is_ignored(tmp_path: Path, bad: object) -> None:
    layer = model_pricing_layer(
        write_settings(tmp_path, {"modelPricing": {"multiplier": bad}})
    )
    assert layer.multiplier == 1.0


@pytest.mark.parametrize("good", [0.01, 1, 10])
def test_multiplier_edges_are_inclusive_of_ten_and_exclusive_of_zero(
    tmp_path: Path, good: float
) -> None:
    layer = model_pricing_layer(
        write_settings(tmp_path, {"modelPricing": {"multiplier": good}})
    )
    assert layer.multiplier == good


def test_override_keys_resolve_through_the_catalog(tmp_path: Path) -> None:
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {
                "modelPricing": {
                    "overrides": {
                        "claude-opus-4-8-20260101": full_row(),
                        "opus": full_row(output=3),
                        "claude-unknown-9": full_row(),
                    }
                }
            },
        )
    )
    assert set(layer.overrides) == {"claude-opus-4-8", "claude-opus-5-5"}


def test_a_bad_override_is_skipped_and_the_rest_still_apply(tmp_path: Path) -> None:
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {
                "modelPricing": {
                    "multiplier": 2,
                    "overrides": {
                        "claude-opus-5": full_row(input=-1),
                        "claude-sonnet-5": full_row(input="3"),  # type: ignore[arg-type]
                        "claude-fable-5": [1],
                        "claude-opus-4-8": {},
                        "claude-haiku-4-5": full_row(input=1.5),
                    },
                }
            },
        )
    )
    assert layer.multiplier == 2
    assert layer.overrides == {
        "claude-haiku-4-5": price_feed.ModelOverride(1.5, 2, 0.1, 1.5)
    }


@pytest.mark.parametrize("key", ["input", "output", "cacheRead", "cacheWrite"])
def test_an_override_row_missing_a_rate_is_rejected(tmp_path: Path, key: str) -> None:
    row = full_row()
    del row[key]
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {
                "modelPricing": {
                    "overrides": {"claude-opus-5": row, "claude-haiku-4-5": full_row()}
                }
            },
        )
    )
    assert set(layer.overrides) == {"claude-haiku-4-5"}


@pytest.mark.parametrize("key", ["input", "output", "cacheRead", "cacheWrite"])
@pytest.mark.parametrize("bad", [-0.01, -1, 10000.01, 20000])
def test_an_override_rate_out_of_range_is_rejected(
    tmp_path: Path, key: str, bad: float
) -> None:
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {
                "modelPricing": {
                    "overrides": {
                        "claude-opus-5": full_row(**{key: bad}),
                        "claude-haiku-4-5": full_row(),
                    }
                }
            },
        )
    )
    assert set(layer.overrides) == {"claude-haiku-4-5"}


@pytest.mark.parametrize("key", ["input", "output", "cacheRead", "cacheWrite"])
@pytest.mark.parametrize("edge", [0, 10000])
def test_an_override_rate_of_zero_or_ten_thousand_is_accepted(
    tmp_path: Path, key: str, edge: float
) -> None:
    layer = model_pricing_layer(
        write_settings(
            tmp_path,
            {"modelPricing": {"overrides": {"claude-opus-5": full_row(**{key: edge})}}},
        )
    )
    assert set(layer.overrides) == {"claude-opus-5"}


def test_the_multiplier_scales_every_model_and_tier_without_noise() -> None:
    doc = good_doc()
    out, touched = price_feed.apply_layer(
        doc, price_feed.ModelPricingLayer(multiplier=1.5)
    )
    assert touched == CATALOG_IDS
    assert out["models"]["claude-opus-5"]["input"] == 7.5
    assert out["models"]["claude-haiku-5-5"]["input"] == 0.15
    assert out["models"]["claude-haiku-5-5"]["tiers"][0]["output"] == 3.75
    assert doc["models"]["claude-opus-5"]["input"] == 5


def test_an_override_replaces_the_rates_and_drops_tiers() -> None:
    layer = price_feed.ModelPricingLayer(
        overrides={"claude-haiku-5-5": price_feed.ModelOverride(0.2, 0.9, 0.02, 0.3)}
    )
    out, touched = price_feed.apply_layer(good_doc(), layer)
    assert touched == {"claude-haiku-5-5"}
    assert out["models"]["claude-haiku-5-5"] == {
        "input": 0.2,
        "output": 0.9,
        "cache_read": 0.02,
        "cache_write_5m": 0.3,
        "cache_write_1h": 0.3,
        "flat_rate": True,
    }
    assert out["models"]["claude-opus-5"] == good_doc()["models"]["claude-opus-5"]


def test_an_override_sets_all_four_rates() -> None:
    layer = price_feed.ModelPricingLayer(
        overrides={"claude-opus-5": price_feed.ModelOverride(6, 7, 0.6, 8)}
    )
    out, _ = price_feed.apply_layer(good_doc(), layer)
    assert out["models"]["claude-opus-5"]["input"] == 6
    assert out["models"]["claude-opus-5"]["output"] == 7


def test_the_multiplier_scales_override_rows_too() -> None:
    layer = price_feed.ModelPricingLayer(
        multiplier=2,
        overrides={"claude-opus-5": price_feed.ModelOverride(6, 7, 0.5, 8)},
    )
    out, touched = price_feed.apply_layer(good_doc(), layer)
    assert touched == CATALOG_IDS
    row = out["models"]["claude-opus-5"]
    assert (row["input"], row["output"], row["cache_read"]) == (12, 14, 1)
    assert (row["cache_write_5m"], row["cache_write_1h"]) == (16, 16)
    assert "tiers" not in row
    assert out["models"]["claude-opus-4-8"]["input"] == 10


def test_an_override_with_a_multiplier_has_no_float_noise() -> None:
    layer = price_feed.ModelPricingLayer(
        multiplier=0.85,
        overrides={"claude-opus-5": price_feed.ModelOverride(2.4, 12, 0.24, 3)},
    )
    out, _ = price_feed.apply_layer(good_doc(), layer)
    row = out["models"]["claude-opus-5"]
    assert (row["input"], row["output"], row["cache_read"]) == (2.04, 10.2, 0.204)
    assert row["cache_write_5m"] == 2.55


def test_override_rows_skip_the_fast_and_us_surcharges() -> None:
    layer = price_feed.ModelPricingLayer(
        overrides={"claude-opus-5": price_feed.ModelOverride(10, 40, 1, 12)}
    )
    out, _ = price_feed.apply_layer(good_doc(), layer)
    assert out["models"]["claude-opus-5"][prices.FLAT_RATE] is True
    assert prices.check(out, CATALOG) == []
    for fields in ({"speed": "fast"}, {"inference_geo": "us"}, {}):
        parts = prices.price_parts(
            rec("claude-opus-5", input=1_000_000, output=1_000_000, **fields),
            out,
            CATALOG,
        )
        assert parts is not None
        assert parts["input"] == 10
        assert parts["output"] == 40


def test_the_usage_query_flattening_keeps_the_flat_rate_mark() -> None:
    layer = price_feed.ModelPricingLayer(
        overrides={"claude-opus-5": price_feed.ModelOverride(10, 40, 1, 12)}
    )
    out, _ = price_feed.apply_layer(good_doc(), layer)
    flat = usage_query._flat(out, "claude-opus-5", 0)  # pyright: ignore[reportPrivateUsage]
    assert flat is not None
    parts = prices.price_parts(
        rec("claude-opus-5", input=1_000_000, speed="fast", inference_geo="us"),
        flat,
        CATALOG,
    )
    assert parts is not None
    assert parts["input"] == 10


def test_check_accepts_only_a_boolean_flat_rate() -> None:
    doc = good_doc()
    doc["models"]["claude-opus-5"][prices.FLAT_RATE] = "yes"
    assert prices.check(doc, CATALOG) == [
        "model claude-opus-5: flat_rate must be true or false"
    ]


def test_a_model_without_an_override_still_gets_the_surcharges() -> None:
    layer = price_feed.ModelPricingLayer(
        overrides={"claude-opus-5": price_feed.ModelOverride(10, 40, 1, 12)}
    )
    out, _ = price_feed.apply_layer(good_doc(), layer)
    assert prices.FLAT_RATE not in out["models"]["claude-opus-4-8"]
    parts = prices.price_parts(
        rec("claude-opus-4-8", input=1_000_000, speed="fast"), out, CATALOG
    )
    assert parts is not None
    assert parts["input"] == 10


def test_an_empty_layer_touches_nothing() -> None:
    doc = good_doc()
    out, touched = price_feed.apply_layer(doc, price_feed.ModelPricingLayer())
    assert touched == set()
    assert out == doc
    assert out is not doc


# --- store, feed and source order ------------------------------------------


class Store:
    """A migrated store in a temp folder, with its writer connection."""

    def __init__(self, root: Path) -> None:
        self.layout = StoreLayout(root / "bartab")
        self.conn = store.open_writer(self.layout)
        store.migrate(self.conn)
        self.jobs: list[Callable[[sqlite3.Connection], None]] = []

    def submit(self, job: Callable[[sqlite3.Connection], None]) -> None:
        self.jobs.append(job)

    def drain(self) -> int:
        jobs, self.jobs = self.jobs, []
        for job in jobs:
            job(self.conn)
        return len(jobs)

    def open_reader(self) -> sqlite3.Connection:
        return store.open_reader(self.layout)

    def rows(self, source: str | None = None) -> list[sqlite3.Row]:
        self.conn.row_factory = sqlite3.Row
        query = "SELECT * FROM price_copies"
        args: tuple[str, ...] = ()
        if source:
            query += " WHERE source = ?"
            args = (source,)
        return self.conn.execute(query + " ORDER BY id", args).fetchall()


@pytest.fixture
def st(tmp_path: Path) -> Iterator[Store]:
    holder = Store(tmp_path)
    yield holder
    holder.conn.close()


class FakeTransport:
    """Serves scripted bodies per URL and records every call."""

    def __init__(
        self, litellm: bytes | FetchError, openrouter: bytes | FetchError
    ) -> None:
        self.script: dict[str, bytes | FetchError] = {
            LITELLM_URL: litellm,
            OPENROUTER_URL: openrouter,
        }
        self.calls: list[tuple[str, float, int]] = []

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        self.calls.append((url, timeout, max_bytes))
        outcome = self.script[url]
        if isinstance(outcome, FetchError):
            raise outcome
        if len(outcome) > max_bytes:
            raise FetchError("too_large")
        return outcome


def good_transport() -> FakeTransport:
    return FakeTransport(fixture("litellm_good.json"), fixture("openrouter_agree.json"))


def make_feed(  # noqa: PLR0913
    st: Store,
    transport: FakeTransport,
    clock: FakeClock,
    *,
    managed: Path | None = None,
    sleep: Callable[[float], None] | None = None,
    enabled: bool = True,
) -> PriceFeed:
    return PriceFeed(
        transport=transport,
        submit=st.submit,
        settings=PriceSettings(st.layout, managed),
        open_reader=st.open_reader,
        clock=clock,
        sleep=sleep,
        enabled=enabled,
    )


def settings_for(st: Store, managed: Path | None = None) -> PriceSettings:
    return PriceSettings(st.layout, managed)


def answer(
    st: Store, now: float, managed: Path | None = None
) -> price_feed.PricesAnswer:
    conn = st.open_reader()
    try:
        return current_prices(conn, settings_for(st, managed), now=now)
    finally:
        conn.close()


def table(st: Store, now: float, managed: Path | None = None) -> price_feed.PriceTable:
    conn = st.open_reader()
    try:
        return price_table(conn, settings_for(st, managed), now=now)
    finally:
        conn.close()


def fetch_into(
    st: Store, transport: FakeTransport, clock: FakeClock, at: float
) -> PriceFeed:
    clock.now = at
    feed = make_feed(st, transport, clock)
    feed.run_once()
    st.drain()
    return feed


def count_sources(a: price_feed.PricesAnswer) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in a.models:
        out[row.source] = out.get(row.source, 0) + 1
    return out


def sources(a: price_feed.PricesAnswer) -> dict[str, str]:
    return {row.model: row.source for row in a.models}


def test_an_empty_store_serves_the_bundled_copy(st: Store) -> None:
    a = answer(st, T0)
    assert a.source == "bundled"
    assert a.as_of == "2026-11-08"
    assert len(a.models) == 12
    assert {r.model for r in a.models} == CATALOG_IDS
    assert set(sources(a).values()) == {"bundled"}
    assert a.cross_check.state == "not_checked"
    assert a.cross_check.models == ()
    assert not st.layout.last_good_prices.exists()


def test_the_answer_rows_carry_rates_tiers_and_modifiers(st: Store) -> None:
    rows = {r.model: r for r in answer(st, T0).models}
    opus = rows["claude-opus-5-5"]
    assert (opus.input, opus.output, opus.cache_read) == (4, 20, 0.2)
    assert (opus.cache_write_5m, opus.cache_write_1h) == (5, 8)
    assert opus.tiers == ()
    assert opus.modifiers == {"speed": {"fast": 2.0}, "inference_geo": {"us": 1.1}}
    haiku = rows["claude-haiku-5-5"]
    assert haiku.tiers == (price_feed.PriceTier(100000, 0.5, 2.5, 0.05, 0.625, 1),)
    assert haiku.modifiers == {"inference_geo": {"us": 1.1}}
    assert rows["claude-haiku-4-5"].modifiers == {}


def test_an_override_row_shows_no_modifiers_in_the_answer(
    st: Store, tmp_path: Path
) -> None:
    managed = write_settings(
        tmp_path, {"modelPricing": {"overrides": {"claude-opus-5-5": full_row()}}}
    )
    rows = {r.model: r for r in answer(st, T0, managed).models}
    assert rows["claude-opus-5-5"].modifiers == {}
    assert rows["claude-opus-4-8"].modifiers != {}


def test_rows_follow_catalog_order(st: Store) -> None:
    assert [r.model for r in answer(st, T0).models] == [str(m["id"]) for m in CATALOG]


def test_relative_is_the_blended_rate_over_the_newest_sonnet(st: Store) -> None:
    rows = {r.model: r for r in answer(st, T0).models}
    assert rows["claude-sonnet-5-5"].relative == 1.0
    assert rows["claude-opus-5-5"].relative == 2.0
    assert rows["claude-sonnet-4-6"].relative == 1.5
    assert rows["claude-haiku-5-5"].relative == 0.05
    assert rows["claude-fable-5-1"].relative == 5.0


def test_the_etag_is_the_hash_of_the_effective_table(st: Store) -> None:
    a = answer(st, T0)
    t = table(st, T0)
    assert a.etag == t.hash == price_feed.table_hash(t.document)
    assert len(a.etag) == 64


def test_the_hash_ignores_the_header_so_equal_prices_hash_equal(
    st: Store, clock: FakeClock
) -> None:
    doc = good_doc()
    other = copy.deepcopy(doc)
    other["verified_on"] = "2030-01-01"
    other["source"] = "https://example.invalid/"
    assert price_feed.table_hash(doc) == price_feed.table_hash(other)
    other["models"]["claude-opus-5"]["input"] = 5.5
    assert price_feed.table_hash(doc) != price_feed.table_hash(other)
    # The November 8 fixture has the bundled copy's prices, so a fetch on another day
    # leaves the etag where it was.
    bundled_etag = answer(st, T0).etag
    fetch_into(st, good_transport(), clock, T0 + 24 * HOUR)
    assert answer(st, T0 + 25 * HOUR).etag == bundled_etag


def test_price_table_prices_a_request(st: Store) -> None:
    t = table(st, T0)
    parts = prices.price_parts(
        rec("claude-opus-5-5", input=1_000_000, output=1_000_000), t.document, CATALOG
    )
    assert parts is not None
    assert parts["input"] == 4
    assert parts["output"] == 20


def test_a_passing_fetch_becomes_the_litellm_source(
    st: Store, clock: FakeClock
) -> None:
    feed = make_feed(st, good_transport(), clock)
    clock.now = T0
    feed.run_once()
    assert len(st.jobs) == 2
    assert st.drain() == 2
    a = answer(st, T0 + HOUR)
    assert a.source == "litellm"
    assert a.as_of == "2026-11-08"
    assert set(sources(a).values()) == {"litellm"}
    assert a.cross_check.state == "agree"
    litellm, openrouter = st.rows("litellm"), st.rows("openrouter")
    assert len(litellm) == len(openrouter) == 1
    assert litellm[0]["check_ok"] == 1
    assert litellm[0]["reason_code"] is None
    assert litellm[0]["models"] == 12
    assert (
        litellm[0]["sha256"] == hashlib.sha256(fixture("litellm_good.json")).hexdigest()
    )
    assert litellm[0]["bytes"] == len(fixture("litellm_good.json"))
    assert litellm[0]["fetched_at"] == STAMP
    assert openrouter[0]["cross_check_state"] == "agree"
    assert openrouter[0]["cross_check_models"] == "[]"


def test_the_last_good_file_is_written_private_and_holds_the_document(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    path = st.layout.last_good_prices
    assert path.stat().st_mode & 0o777 == platform_os.FILE_MODE
    doc = json.loads(path.read_bytes())
    assert doc == good_doc() | {"verified_on": "2026-11-08"}
    assert prices.check(doc, CATALOG) == []
    assert sorted(p.name for p in path.parent.iterdir()) == ["last-good.json"]


def test_the_copy_is_litellm_for_48_hours_then_last_good(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    assert answer(st, T0 + 47 * HOUR).source == "litellm"
    assert answer(st, T0 + 48 * HOUR).source == "litellm"
    late = answer(st, T0 + 48 * HOUR + 1)
    assert late.source == "last_good"
    assert late.as_of == "2026-11-08"
    assert late.etag == answer(st, T0).etag


def test_a_failed_check_keeps_the_last_good_copy_and_records_why(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    kept = st.layout.last_good_prices.read_bytes()
    before = answer(st, T0 + HOUR)
    bad = FakeTransport(
        fixture("litellm_missing_model.json"), fixture("openrouter_agree.json")
    )
    fetch_into(st, bad, clock, T0 + 24 * HOUR)
    assert st.layout.last_good_prices.read_bytes() == kept
    failed = st.rows("litellm")[-1]
    assert failed["check_ok"] == 0
    assert failed["reason_code"] == "missing_model"
    assert failed["models"] == 0
    after = answer(st, T0 + 25 * HOUR)
    assert after.source == "last_good"
    assert after.etag == before.etag
    assert after.as_of == "2026-11-08"


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("litellm_missing_model.json", "missing_model"),
        ("litellm_out_of_range.json", "out_of_range"),
        ("litellm_cache_ratio.json", "cache_ratio"),
        ("litellm_malformed.json", "not_json"),
    ],
)
def test_each_failed_check_leaves_no_last_good_and_serves_bundled(
    st: Store, clock: FakeClock, name: str, code: str
) -> None:
    transport = FakeTransport(fixture(name), fixture("openrouter_agree.json"))
    fetch_into(st, transport, clock, T0)
    row = st.rows("litellm")[0]
    assert (row["check_ok"], row["reason_code"]) == (0, code)
    assert row["sha256"] == hashlib.sha256(fixture(name)).hexdigest()
    assert not st.layout.last_good_prices.exists()
    assert answer(st, T0 + HOUR).source == "bundled"


def test_an_oversized_body_is_refused_by_the_transport_cap(
    st: Store, clock: FakeClock, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = fixture("litellm_oversized.json")
    monkeypatch.setattr(price_feed, "LITELLM_MAX_BYTES", 65536)
    transport = FakeTransport(body, fixture("openrouter_agree.json"))
    fetch_into(st, transport, clock, T0)
    row = st.rows("litellm")[0]
    assert (row["check_ok"], row["reason_code"], row["sha256"], row["bytes"]) == (
        0,
        "too_large",
        "",
        0,
    )
    assert transport.calls[0][2] == 65536
    # The same body passes when the cap is real, so size is the only fault.
    assert parse_litellm(body, required=CATALOG_IDS).ok


@pytest.mark.parametrize(
    "code", ["timeout", "fetch_failed", "redirect_refused", "too_large"]
)
def test_a_transport_failure_is_recorded_with_its_code(
    st: Store, clock: FakeClock, code: FetchReason
) -> None:
    transport = FakeTransport(FetchError(code), FetchError(code))
    fetch_into(st, transport, clock, T0)
    for source in ("litellm", "openrouter"):
        row = st.rows(source)[0]
        assert (row["check_ok"], row["reason_code"], row["sha256"], row["bytes"]) == (
            0,
            code,
            "",
            0,
        )
    assert answer(st, T0 + HOUR).source == "bundled"


def test_a_failed_newest_fetch_serves_last_good_even_within_48_hours(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    down = FakeTransport(FetchError("timeout"), FetchError("timeout"))
    fetch_into(st, down, clock, T0 + 24 * HOUR)
    a = answer(st, T0 + 25 * HOUR)
    assert a.source == "last_good"
    assert a.as_of == "2026-11-08"
    # A later good fetch brings litellm back.
    fetch_into(st, good_transport(), clock, T0 + 48 * HOUR)
    assert answer(st, T0 + 49 * HOUR).source == "litellm"


def test_a_missing_or_damaged_last_good_file_falls_back_to_bundled(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    path = st.layout.last_good_prices
    path.write_text("{", encoding="utf-8")
    assert answer(st, T0 + HOUR).source == "bundled"
    path.write_text(json.dumps({"models": {}}), encoding="utf-8")
    assert answer(st, T0 + HOUR).source == "bundled"
    path.unlink()
    assert answer(st, T0 + HOUR).source == "bundled"


def test_the_fresh_litellm_values_differ_from_the_bundled_ones_when_prices_move(
    st: Store, clock: FakeClock
) -> None:
    data = raw_good()
    data["claude-opus-5"]["input_cost_per_token"] = 6e-06
    data["claude-opus-5"]["cache_read_input_token_cost"] = 6e-07
    transport = FakeTransport(encode(data), fixture("openrouter_agree.json"))
    fetch_into(st, transport, clock, T0)
    a = answer(st, T0 + HOUR)
    rows = {r.model: r for r in a.models}
    assert rows["claude-opus-5"].input == 6
    assert table(st, T0 + HOUR).hash != price_feed.table_hash(
        price_feed.load_bundled()[0]
    )


def test_model_pricing_wins_per_model_over_every_other_source(
    st: Store, clock: FakeClock, tmp_path: Path
) -> None:
    managed = write_settings(
        tmp_path,
        {"modelPricing": {"overrides": {"claude-opus-5": full_row()}}},
    )
    states: list[tuple[str, Callable[[], object]]] = [
        ("bundled", lambda: None),
        ("litellm", lambda: fetch_into(st, good_transport(), clock, T0)),
    ]
    for expected, setup in states:
        setup()
        a = answer(st, T0 + HOUR, managed)
        by_model = sources(a)
        assert by_model["claude-opus-5"] == "model_pricing"
        others = {s for m, s in by_model.items() if m != "claude-opus-5"}
        assert others == {expected}
        assert a.source == expected
    a = answer(st, T0 + 60 * HOUR, managed)
    assert sources(a)["claude-opus-5"] == "model_pricing"
    assert {s for m, s in sources(a).items() if m != "claude-opus-5"} == {"last_good"}
    assert a.source == "last_good"
    row = {r.model: r for r in a.models}["claude-opus-5"]
    assert (row.input, row.output) == (1, 2)


def test_the_override_changes_the_priced_table_and_the_etag(
    st: Store, tmp_path: Path
) -> None:
    managed = write_settings(
        tmp_path, {"modelPricing": {"overrides": {"claude-opus-5": full_row()}}}
    )
    plain, layered = table(st, T0), table(st, T0, managed)
    assert plain.hash != layered.hash
    assert layered.document["models"]["claude-opus-5"]["input"] == 1
    assert plain.document["models"]["claude-opus-5"]["input"] == 5
    assert answer(st, T0, managed).etag == layered.hash


def test_a_multiplier_for_every_model_makes_model_pricing_the_main_source(
    st: Store, tmp_path: Path
) -> None:
    managed = write_settings(tmp_path, {"modelPricing": {"multiplier": 0.5}})
    a = answer(st, T0, managed)
    assert a.source == "model_pricing"
    assert set(sources(a).values()) == {"model_pricing"}
    assert a.as_of == "2026-11-08"
    rows = {r.model: r for r in a.models}
    assert rows["claude-opus-5"].input == 2.5
    assert rows["claude-sonnet-5-5"].relative == 1.0


def test_a_tie_goes_to_the_copy_under_the_layer(st: Store, tmp_path: Path) -> None:
    ids = sorted(CATALOG_IDS)[:6]
    managed = write_settings(
        tmp_path, {"modelPricing": {"overrides": {m: full_row() for m in ids}}}
    )
    a = answer(st, T0, managed)
    assert count_sources(a) == {"model_pricing": 6, "bundled": 6}
    assert a.source == "bundled"


def test_the_openrouter_disagreement_sets_the_state_and_changes_no_price(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    before = answer(st, T0 + HOUR)
    table_before = table(st, T0 + HOUR)
    transport = FakeTransport(
        fixture("litellm_good.json"), fixture("openrouter_disagree.json")
    )
    fetch_into(st, transport, clock, T0 + 24 * HOUR)
    after = answer(st, T0 + 25 * HOUR)
    assert after.cross_check.state == "disagree"
    assert after.cross_check.models == ("claude-opus-5-5",)
    assert after.etag == before.etag
    now_doc = table(st, T0 + 25 * HOUR).document
    assert now_doc["models"] == table_before.document["models"]
    assert now_doc["modifiers"] == table_before.document["modifiers"]
    assert [(r.model, r.input, r.output) for r in after.models] == [
        (r.model, r.input, r.output) for r in before.models
    ]
    row = st.rows("openrouter")[-1]
    assert row["cross_check_state"] == "disagree"
    assert json.loads(row["cross_check_models"]) == ["claude-opus-5-5"]


def test_a_stale_cross_check_reads_as_not_checked(st: Store, clock: FakeClock) -> None:
    fetch_into(st, good_transport(), clock, T0)
    assert answer(st, T0 + 48 * HOUR).cross_check.state == "agree"
    assert answer(st, T0 + 48 * HOUR + 1).cross_check.state == "not_checked"


def test_an_openrouter_failure_leaves_litellm_alone(
    st: Store, clock: FakeClock
) -> None:
    transport = FakeTransport(fixture("litellm_good.json"), FetchError("timeout"))
    fetch_into(st, transport, clock, T0)
    a = answer(st, T0 + HOUR)
    assert a.source == "litellm"
    assert a.cross_check.state == "not_checked"
    row = st.rows("openrouter")[0]
    assert (row["check_ok"], row["reason_code"]) == (0, "timeout")


def test_a_bad_openrouter_body_is_not_json(st: Store, clock: FakeClock) -> None:
    transport = FakeTransport(fixture("litellm_good.json"), b"<html>")
    fetch_into(st, transport, clock, T0)
    row = st.rows("openrouter")[0]
    assert (row["check_ok"], row["reason_code"]) == (0, "not_json")


def test_the_cross_check_runs_against_the_last_good_copy_when_litellm_fails(
    st: Store, clock: FakeClock
) -> None:
    fetch_into(st, good_transport(), clock, T0)
    transport = FakeTransport(
        FetchError("timeout"), fixture("openrouter_disagree.json")
    )
    fetch_into(st, transport, clock, T0 + 24 * HOUR)
    assert st.rows("openrouter")[-1]["cross_check_state"] == "disagree"


def test_the_cross_check_runs_against_the_bundled_copy_when_nothing_else_exists(
    st: Store, clock: FakeClock
) -> None:
    transport = FakeTransport(FetchError("timeout"), fixture("openrouter_agree.json"))
    fetch_into(st, transport, clock, T0)
    assert st.rows("openrouter")[0]["cross_check_state"] == "agree"


def test_the_cross_check_uses_the_new_copy_and_not_the_managed_layer(
    st: Store, clock: FakeClock, tmp_path: Path
) -> None:
    managed = write_settings(tmp_path, {"modelPricing": {"multiplier": 3}})
    clock.now = T0
    feed = make_feed(st, good_transport(), clock, managed=managed)
    feed.run_once()
    st.drain()
    assert st.rows("openrouter")[0]["cross_check_state"] == "agree"


# --- required models --------------------------------------------------------


def seed_requests(st: Store, rows: list[tuple[str, str]]) -> None:
    st.conn.execute(
        "INSERT INTO files (id, path, kind, folder, first_seen, last_seen) "
        "VALUES (1, '/work/a.jsonl', 'main', 'f', ?, ?)",
        (STAMP, STAMP),
    )
    for i, (model, ts) in enumerate(rows):
        st.conn.execute(
            "INSERT INTO requests (file_id, key, ts, model) VALUES (1, ?, ?, ?)",
            (f"k{i}", ts, model),
        )


def test_required_models_are_the_catalog_ids_and_ignore_names_it_cannot_map(
    st: Store,
) -> None:
    seed_requests(
        st,
        [
            ("claude-sonnet-5-20261001", "2026-10-20T00:00:00Z"),
            ("claude-unknown-9", "2026-11-01T00:00:00Z"),
            ("<synthetic>", "2026-11-01T00:00:00Z"),
        ],
    )
    assert price_feed.required_models(st.conn, T0) == CATALOG_IDS
    subset = [m for m in CATALOG if m["id"] in {"claude-opus-5", "claude-haiku-4-5"}]
    assert price_feed.required_models(st.conn, T0, subset) == {
        "claude-opus-5",
        "claude-haiku-4-5",
    }


# --- the scheduler ----------------------------------------------------------


def insert_attempt(st: Store, at: float, source: str = "litellm", ok: int = 1) -> None:
    st.conn.execute(
        "INSERT INTO price_copies (fetched_at, source, sha256, check_ok) "
        "VALUES (?, ?, 'x', ?)",
        (datetime.fromtimestamp(at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), source, ok),
    )


def test_a_fetch_is_due_at_start_with_no_history(st: Store, clock: FakeClock) -> None:
    clock.now = T0
    transport = good_transport()
    feed = make_feed(st, transport, clock)
    assert feed.due()
    assert feed.tick()
    assert [c[0] for c in transport.calls] == [LITELLM_URL, OPENROUTER_URL]
    assert all(c[1] == 10.0 for c in transport.calls)
    assert transport.calls[0][2] == price_feed.LITELLM_MAX_BYTES == 4 * 3_474_076
    assert transport.calls[1][2] == price_feed.OPENROUTER_MAX_BYTES == 4 * 829_400
    assert len(st.jobs) == 2


def test_the_two_jobs_go_to_the_writer_in_order(st: Store, clock: FakeClock) -> None:
    clock.now = T0
    make_feed(st, good_transport(), clock).run_once()
    st.drain()
    assert [r["source"] for r in st.rows()] == ["litellm", "openrouter"]


def test_a_fetch_is_not_due_when_the_last_attempt_is_under_24_hours_old(
    st: Store, clock: FakeClock
) -> None:
    insert_attempt(st, T0 - 23 * HOUR)
    clock.now = T0
    transport = good_transport()
    feed = make_feed(st, transport, clock)
    assert not feed.tick()
    assert transport.calls == []
    assert st.jobs == []


def test_a_fetch_is_due_when_the_last_attempt_is_over_24_hours_old(
    st: Store, clock: FakeClock
) -> None:
    insert_attempt(st, T0 - 25 * HOUR)
    clock.now = T0
    feed = make_feed(st, good_transport(), clock)
    assert feed.tick()


def test_a_failed_attempt_counts_as_an_attempt(st: Store, clock: FakeClock) -> None:
    insert_attempt(st, T0 - HOUR, ok=0)
    insert_attempt(st, T0 - HOUR, source="openrouter", ok=0)
    clock.now = T0
    assert not make_feed(st, good_transport(), clock).tick()


def test_the_next_fetch_comes_24_hours_after_the_last_one(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    transport = good_transport()
    feed = make_feed(st, transport, clock)
    assert feed.tick()
    for later in (HOUR, 12 * HOUR, 24 * HOUR - 1):
        clock.now = T0 + later
        assert not feed.tick()
    assert len(transport.calls) == 2
    clock.now = T0 + 24 * HOUR
    assert feed.tick()
    assert len(transport.calls) == 4
    clock.now = T0 + 24 * HOUR + 60
    assert not feed.tick()


def test_a_restart_waits_for_the_recorded_attempt_not_for_a_full_day(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    first = make_feed(st, good_transport(), clock)
    first.tick()
    st.drain()
    clock.now = T0 + 6 * HOUR
    second = make_feed(st, good_transport(), clock)
    assert not second.tick()
    clock.now = T0 + 24 * HOUR
    assert second.tick()


def test_a_disabled_feed_starts_no_thread_and_never_fetches(
    st: Store, clock: FakeClock
) -> None:
    transport = good_transport()
    feed = make_feed(st, transport, clock, enabled=False)
    feed.start()
    feed.stop()
    assert transport.calls == []
    assert st.jobs == []
    assert all(t.name != "price_feed" for t in threading.enumerate())


def test_the_loop_polls_with_the_injected_sleep_and_fetches_once(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    transport = good_transport()
    sleeps: list[float] = []
    holder: list[PriceFeed] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.advance(seconds)
        if len(sleeps) == 5:
            holder[0].stop()

    feed = make_feed(st, transport, clock, sleep=sleep)
    holder.append(feed)
    feed.run_loop()
    assert sleeps == [price_feed.POLL_SECONDS] * 5
    assert len(transport.calls) == 2
    assert len(st.jobs) == 2


def test_the_loop_fetches_again_after_24_hours(st: Store, clock: FakeClock) -> None:
    clock.now = T0
    transport = good_transport()
    holder: list[PriceFeed] = []
    seen = {"polls": 0}

    def sleep(_seconds: float) -> None:
        seen["polls"] += 1
        clock.advance(HOUR)
        if seen["polls"] == 25:
            holder[0].stop()

    feed = make_feed(st, transport, clock, sleep=sleep)
    holder.append(feed)
    feed.run_loop()
    assert len(transport.calls) == 4


def test_a_pass_that_raises_does_not_end_the_loop(st: Store, clock: FakeClock) -> None:
    clock.now = T0

    class Boom:
        def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
            raise RuntimeError(url)

    holder: list[PriceFeed] = []
    count = {"n": 0}

    def sleep(_seconds: float) -> None:
        count["n"] += 1
        if count["n"] == 3:
            holder[0].stop()

    feed = PriceFeed(
        transport=Boom(),
        submit=st.submit,
        settings=PriceSettings(st.layout),
        open_reader=st.open_reader,
        clock=clock,
        sleep=sleep,
    )
    holder.append(feed)
    feed.run_loop()
    assert count["n"] == 3


class CountingBoom:
    """A transport whose fetch raises a plain error, counting its calls."""

    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, url: str, *, timeout: float, max_bytes: int) -> bytes:
        self.calls += 1
        raise RuntimeError(url)


def feed_over(st: Store, clock: FakeClock, transport: Any) -> PriceFeed:
    return PriceFeed(
        transport=transport,
        submit=st.submit,
        settings=PriceSettings(st.layout),
        open_reader=st.open_reader,
        clock=clock,
    )


def test_a_run_that_raises_retries_after_the_failure_backoff_not_a_day(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    boom = CountingBoom()
    feed = feed_over(st, clock, boom)
    assert price_feed.FAILURE_BACKOFF_SECONDS < price_feed.FETCH_INTERVAL_SECONDS
    with pytest.raises(RuntimeError):
        feed.tick()
    assert boom.calls == 1
    clock.now = T0 + price_feed.FAILURE_BACKOFF_SECONDS - 1
    assert not feed.tick()
    assert boom.calls == 1
    clock.now = T0 + price_feed.FAILURE_BACKOFF_SECONDS
    with pytest.raises(RuntimeError):
        feed.tick()
    assert boom.calls == 2
    assert st.jobs == []


def test_a_run_that_raises_on_the_store_read_also_backs_off_briefly(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    transport = good_transport()
    broken = {"on": True}
    opened: list[int] = []

    def open_reader() -> sqlite3.Connection:
        if broken["on"] and opened:
            msg = "no such table: requests"
            raise sqlite3.OperationalError(msg)
        opened.append(1)
        return st.open_reader()

    feed = PriceFeed(
        transport=transport,
        submit=st.submit,
        settings=PriceSettings(st.layout),
        open_reader=open_reader,
        clock=clock,
    )
    with pytest.raises(sqlite3.OperationalError):
        feed.tick()  # due() reads once, run_once then fails to open its reader
    assert transport.calls == []
    broken["on"] = False
    clock.now = T0 + price_feed.FAILURE_BACKOFF_SECONDS
    assert feed.tick()
    assert len(transport.calls) == 2


def test_a_run_that_submits_both_jobs_is_next_due_in_24_hours(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    transport = good_transport()
    feed = feed_over(st, clock, transport)
    assert feed.tick()
    assert len(st.jobs) == 2
    clock.now = T0 + price_feed.FETCH_INTERVAL_SECONDS - 1
    assert not feed.tick()
    clock.now = T0 + price_feed.FETCH_INTERVAL_SECONDS
    assert feed.tick()


def test_a_failed_fetch_that_is_recorded_waits_the_full_day(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    transport = FakeTransport(FetchError("fetch_failed"), FetchError("fetch_failed"))
    feed = feed_over(st, clock, transport)
    assert feed.tick()
    assert len(st.jobs) == 2
    clock.now = T0 + price_feed.FAILURE_BACKOFF_SECONDS
    assert not feed.tick()
    clock.now = T0 + price_feed.FETCH_INTERVAL_SECONDS
    assert feed.tick()


def test_a_due_check_that_raises_leaves_no_schedule_behind(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    calls = {"n": 0}

    def open_reader() -> sqlite3.Connection:
        calls["n"] += 1
        if calls["n"] == 1:
            msg = "no such table: price_copies"
            raise sqlite3.OperationalError(msg)
        return st.open_reader()

    feed = PriceFeed(
        transport=good_transport(),
        submit=st.submit,
        settings=PriceSettings(st.layout),
        open_reader=open_reader,
        clock=clock,
    )
    with pytest.raises(sqlite3.OperationalError):
        feed.due()
    assert feed.due()  # the next poll asks again and finds a fetch owed


def test_the_thread_runs_stops_and_joins(st: Store, clock: FakeClock) -> None:
    clock.now = T0
    done = threading.Event()
    seen: list[str] = []

    def submit(job: Callable[[sqlite3.Connection], None]) -> None:
        seen.append(threading.current_thread().name)
        st.jobs.append(job)
        if len(st.jobs) == 2:
            done.set()

    feed = PriceFeed(
        transport=good_transport(),
        submit=submit,
        settings=PriceSettings(st.layout),
        open_reader=st.open_reader,
        clock=clock,
    )
    feed.start()
    feed.start()  # a second start does nothing
    assert done.wait(10)
    feed.stop()
    assert seen == ["price_feed", "price_feed"]
    assert all(t.name != "price_feed" for t in threading.enumerate())


# --- the writer job ---------------------------------------------------------


def test_a_job_runs_inside_a_transaction_the_writer_already_opened(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    make_feed(st, good_transport(), clock).run_once()
    st.conn.execute("BEGIN IMMEDIATE")
    st.drain()
    assert st.conn.in_transaction
    st.conn.execute("COMMIT")
    assert len(st.rows()) == 2


def test_a_job_commits_when_it_opens_its_own_transaction(
    st: Store, clock: FakeClock
) -> None:
    clock.now = T0
    make_feed(st, good_transport(), clock).run_once()
    st.drain()
    assert not st.conn.in_transaction
    reader = st.open_reader()
    try:
        assert reader.execute("SELECT COUNT(*) FROM price_copies").fetchone()[0] == 2
    finally:
        reader.close()


def test_a_failed_last_good_write_records_no_row(st: Store, clock: FakeClock) -> None:
    clock.now = T0
    make_feed(st, good_transport(), clock).run_once()
    st.layout.prices_dir.rmdir()
    st.layout.prices_dir.write_text("in the way", encoding="utf-8")
    with pytest.raises(OSError):  # noqa: PT011
        st.drain()
    assert st.rows("litellm") == []


def test_nothing_is_written_outside_the_store_root(
    tmp_path: Path, clock: FakeClock
) -> None:
    config = tmp_path / "config"
    old_file = config / "routing-dashboard" / "ledger.json"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("{}", encoding="utf-8")
    old_mtime = old_file.stat().st_mtime_ns
    holder = Store(config / "routing-dashboard")
    try:
        clock.now = T0
        make_feed(holder, good_transport(), clock).run_once()
        holder.drain()
        assert holder.layout.last_good_prices.is_file()
    finally:
        holder.conn.close()
    assert old_file.read_text(encoding="utf-8") == "{}"
    assert old_file.stat().st_mtime_ns == old_mtime
    top = sorted(p.name for p in (config / "routing-dashboard").iterdir())
    assert top == ["bartab", "ledger.json"]
