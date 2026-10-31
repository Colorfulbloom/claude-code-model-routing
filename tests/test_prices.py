"""Tests for the list prices (dashboard/prices.json, dashboard/prices.py).

The price table below is typed out as literal numbers, so a wrong edit to
prices.json fails here. Every run reads only the repo.
"""
import copy
import os
import subprocess
import sys
import unittest
from types import SimpleNamespace

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import prices as prices_mod  # noqa: E402
import resolve  # noqa: E402

PRICES = prices_mod.load_prices()
CATALOG = resolve.load_rules()["models"]
CATALOG_IDS = [m["id"] for m in CATALOG]

# id: (input, 5-minute cache write, 1-hour cache write, cache read, output)
TABLE = {
    "claude-fable-5-1": (10, 12.50, 20, 0.25, 50),
    "claude-fable-5": (10, 12.50, 20, 1, 50),
    "claude-opus-5-5": (4, 5, 8, 0.20, 20),
    "claude-opus-5": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-8": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-7": (5, 6.25, 10, 0.50, 25),
    "claude-opus-4-6": (5, 6.25, 10, 0.50, 25),
    "claude-sonnet-5-5": (2, 2.50, 4, 0.10, 10),
    "claude-sonnet-5": (2, 2.50, 4, 0.20, 10),
    "claude-sonnet-4-6": (3, 3.75, 6, 0.30, 15),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-haiku-4-5": (1, 1.25, 2, 0.10, 5),
}
HAIKU_TIER = (0.50, 0.625, 1, 0.05, 2.50)
FAST_MODELS = ["claude-opus-5-5", "claude-opus-5", "claude-opus-4-8"]
NO_US = ["claude-haiku-4-5"]


def rec(model="claude-opus-5-5", input=0, output=0, cache_read=0,
        cache_write_5m=0, cache_write_1h=0, speed=None, service_tier=None,
        inference_geo=None):
    return SimpleNamespace(
        model_raw=model, input=input, output=output, cache_read=cache_read,
        cache_write_5m=cache_write_5m, cache_write_1h=cache_write_1h,
        speed=speed, service_tier=service_tier, inference_geo=inference_geo)


def cost(record, prices=PRICES):
    return prices_mod.price(record, prices, CATALOG)


def parts(record, prices=PRICES):
    return prices_mod.price_parts(record, prices, CATALOG)


def per_million(rates, tokens):
    """Expected USD for `tokens` of each kind at the given table row."""
    return sum(rate * tokens / 1e6 for rate in rates)


class TableTests(unittest.TestCase):
    def test_table_covers_the_catalog(self):
        self.assertEqual(sorted(TABLE), sorted(CATALOG_IDS))
        self.assertEqual(len(TABLE), 12)

    def test_every_model_matches_the_table(self):
        # 20,000 of each kind is 80,000 prompt tokens, under the Haiku 5.5 tier.
        for mid, (inp, w5, w1, read, out) in TABLE.items():
            with self.subTest(model=mid):
                r = rec(mid, input=20000, output=20000, cache_read=20000,
                        cache_write_5m=20000, cache_write_1h=20000)
                p = parts(r)
                self.assertAlmostEqual(p["input"], inp * 20000 / 1e6)
                self.assertAlmostEqual(p["output"], out * 20000 / 1e6)
                self.assertAlmostEqual(p["cache_read"], read * 20000 / 1e6)
                self.assertAlmostEqual(p["cache_write"], (w5 + w1) * 20000 / 1e6)
                self.assertAlmostEqual(cost(r), per_million(TABLE[mid], 20000))

    def test_each_kind_alone(self):
        # One kind at a time, one million tokens, on a model with no tier.
        inp, w5, w1, read, out = TABLE["claude-opus-5"]
        cases = {
            "input": (rec("claude-opus-5", input=1000000), inp),
            "output": (rec("claude-opus-5", output=1000000), out),
            "cache_read": (rec("claude-opus-5", cache_read=1000000), read),
            "cache_write": (rec("claude-opus-5", cache_write_5m=1000000), w5),
        }
        for kind, (r, expected) in cases.items():
            with self.subTest(kind=kind):
                p = parts(r)
                self.assertAlmostEqual(p[kind], expected)
                self.assertAlmostEqual(sum(p.values()), expected)
        self.assertAlmostEqual(
            parts(rec("claude-opus-5", cache_write_1h=1000000))["cache_write"], w1)

    def test_parts_keys_and_sum(self):
        r = rec(input=1000, output=2000, cache_read=3000, cache_write_5m=400,
                cache_write_1h=500)
        p = parts(r)
        self.assertEqual(sorted(p), ["cache_read", "cache_write", "input", "output"])
        self.assertAlmostEqual(cost(r), sum(p.values()), places=12)

    def test_zero_tokens_cost_zero(self):
        self.assertEqual(cost(rec()), 0)

    def test_file_header(self):
        self.assertEqual(PRICES["schema_version"], 1)
        self.assertEqual(PRICES["unit"], "USD per million tokens")
        self.assertEqual(PRICES["verified_on"], "2026-10-30")
        self.assertEqual(PRICES["source"],
                         "https://platform.claude.com/docs/en/about-claude/pricing")
        self.assertEqual(sorted(PRICES["models"]), sorted(CATALOG_IDS))


class TierTests(unittest.TestCase):
    def test_haiku_5_5_tier_boundary(self):
        base = TABLE["claude-haiku-5-5"]
        at = rec("claude-haiku-5-5", input=100000)
        over = rec("claude-haiku-5-5", input=100001)
        self.assertAlmostEqual(cost(at), 100000 * base[0] / 1e6)
        self.assertAlmostEqual(cost(over), 100001 * HAIKU_TIER[0] / 1e6)

    def test_prompt_counts_cache_reads_and_writes(self):
        base = TABLE["claude-haiku-5-5"]
        mixes = [
            dict(input=40000, cache_read=30000, cache_write_5m=20000, cache_write_1h=10000),
            dict(input=0, cache_read=100000),
            dict(cache_write_5m=100000),
            dict(cache_write_1h=100000),
        ]
        for mix in mixes:
            with self.subTest(mix=mix):
                at = rec("claude-haiku-5-5", **mix)
                self.assertAlmostEqual(cost(at), sum(
                    (mix.get(k, 0) * base[i]) / 1e6 for i, k in enumerate(
                        ["input", "cache_write_5m", "cache_write_1h", "cache_read"])))
        for field in ("input", "cache_read", "cache_write_5m", "cache_write_1h"):
            with self.subTest(over=field):
                over = rec("claude-haiku-5-5", **{field: 100001})
                index = {"input": 0, "cache_write_5m": 1, "cache_write_1h": 2,
                         "cache_read": 3}[field]
                self.assertAlmostEqual(cost(over), 100001 * HAIKU_TIER[index] / 1e6)

    def test_output_does_not_count_toward_the_prompt(self):
        base = TABLE["claude-haiku-5-5"]
        r = rec("claude-haiku-5-5", input=1000, output=500000)
        self.assertAlmostEqual(cost(r), 1000 * base[0] / 1e6 + 500000 * base[4] / 1e6)

    def test_whole_request_uses_the_tier(self):
        r = rec("claude-haiku-5-5", input=60000, cache_read=60000, output=1000000)
        expected = (60000 * HAIKU_TIER[0] + 60000 * HAIKU_TIER[3]
                    + 1000000 * HAIKU_TIER[4]) / 1e6
        self.assertAlmostEqual(cost(r), expected)

    def test_other_models_have_no_tier(self):
        for mid in CATALOG_IDS:
            if mid == "claude-haiku-5-5":
                continue
            with self.subTest(model=mid):
                self.assertNotIn("tiers", PRICES["models"][mid])
                big = rec(mid, input=500000)
                self.assertAlmostEqual(cost(big), 500000 * TABLE[mid][0] / 1e6)

    def test_highest_tier_passed_wins(self):
        doc = copy.deepcopy(PRICES)
        entry = doc["models"]["claude-haiku-5-5"]
        entry["tiers"].append(dict(entry["tiers"][0], prompt_tokens_over=200000, input=9))
        self.assertAlmostEqual(cost(rec("claude-haiku-5-5", input=150000), doc),
                               150000 * HAIKU_TIER[0] / 1e6)
        self.assertAlmostEqual(cost(rec("claude-haiku-5-5", input=200001), doc),
                               200001 * 9 / 1e6)


class ModifierTests(unittest.TestCase):
    def test_us_geo_is_1_1_on_every_kind(self):
        for mid in CATALOG_IDS:
            if mid in NO_US:
                continue
            with self.subTest(model=mid):
                kw = dict(input=20000, output=20000, cache_read=20000,
                          cache_write_5m=20000, cache_write_1h=20000)
                self.assertAlmostEqual(cost(rec(mid, inference_geo="us", **kw)),
                                       per_million(TABLE[mid], 20000) * 1.1)

    def test_us_geo_on_the_haiku_5_5_tier(self):
        r = rec("claude-haiku-5-5", input=100001, output=1000, inference_geo="us")
        expected = (100001 * HAIKU_TIER[0] + 1000 * HAIKU_TIER[4]) / 1e6 * 1.1
        self.assertAlmostEqual(cost(r), expected)

    def test_us_geo_on_haiku_4_5_is_not_priced(self):
        self.assertIsNone(cost(rec("claude-haiku-4-5", input=1000, inference_geo="us")))
        self.assertIsNone(parts(rec("claude-haiku-4-5", input=1000, inference_geo="us")))

    def test_global_geo_is_standard(self):
        for geo in (None, "global"):
            with self.subTest(geo=geo):
                self.assertAlmostEqual(
                    cost(rec("claude-haiku-4-5", input=1000000, inference_geo=geo)), 1)

    def test_not_available_geo_is_standard(self):
        for mid in ("claude-opus-4-6", "claude-sonnet-5-5", "claude-haiku-4-5"):
            with self.subTest(model=mid):
                self.assertAlmostEqual(
                    cost(rec(mid, input=1000000, inference_geo="not_available")),
                    cost(rec(mid, input=1000000)))
                self.assertIsNotNone(
                    cost(rec(mid, input=1000, inference_geo="not_available")))

    def test_unknown_geo_is_not_priced(self):
        for geo in ("eu", "US", "", "asia", "not-available", "NOT_AVAILABLE"):
            with self.subTest(geo=geo):
                self.assertIsNone(cost(rec(input=1000, inference_geo=geo)))

    def test_fast_is_2x_on_every_kind(self):
        for mid in FAST_MODELS:
            with self.subTest(model=mid):
                kw = dict(input=20000, output=20000, cache_read=20000,
                          cache_write_5m=20000, cache_write_1h=20000)
                self.assertAlmostEqual(cost(rec(mid, speed="fast", **kw)),
                                       per_million(TABLE[mid], 20000) * 2)

    def test_fast_matches_the_docs_prices(self):
        # Fast mode is $8 and $40 on Opus 5.5, $10 and $50 on Opus 5 and 4.8.
        for mid, inp, out in (("claude-opus-5-5", 8, 40), ("claude-opus-5", 10, 50),
                              ("claude-opus-4-8", 10, 50)):
            with self.subTest(model=mid):
                p = parts(rec(mid, input=1000000, output=1000000, speed="fast"))
                self.assertAlmostEqual(p["input"], inp)
                self.assertAlmostEqual(p["output"], out)

    def test_fast_on_a_model_not_listed_is_not_priced(self):
        for mid in CATALOG_IDS:
            if mid in FAST_MODELS:
                continue
            with self.subTest(model=mid):
                self.assertIsNone(cost(rec(mid, input=1000, speed="fast")))

    def test_standard_speed_and_unset_speed_are_standard(self):
        for speed in (None, "standard"):
            with self.subTest(speed=speed):
                self.assertAlmostEqual(
                    cost(rec("claude-sonnet-4-6", input=1000000, speed=speed)), 3)

    def test_unknown_speed_is_not_priced(self):
        for speed in ("slow", "Fast", "", "turbo"):
            with self.subTest(speed=speed):
                self.assertIsNone(cost(rec(input=1000, speed=speed)))

    def test_fast_reads_speed_never_service_tier(self):
        self.assertIsNone(cost(rec(input=1000, service_tier="fast")))
        self.assertAlmostEqual(
            cost(rec("claude-opus-5-5", input=1000000, service_tier="standard")), 4)

    def test_both_modifiers_stack(self):
        r = rec("claude-opus-5-5", input=1000000, output=1000000, cache_read=1000000,
                cache_write_5m=1000000, cache_write_1h=1000000,
                speed="fast", inference_geo="us")
        self.assertAlmostEqual(cost(r), (4 + 5 + 8 + 0.20 + 20) * 2 * 1.1)
        p = parts(r)
        self.assertAlmostEqual(p["input"], 4 * 2 * 1.1)
        self.assertAlmostEqual(p["cache_write"], 13 * 2 * 1.1)

    def test_service_tier_standard_and_unset_are_standard(self):
        for tier in (None, "standard"):
            with self.subTest(tier=tier):
                self.assertAlmostEqual(
                    cost(rec("claude-opus-5", input=1000000, service_tier=tier)), 5)

    def test_service_tier_priority_is_not_priced(self):
        r = rec(input=1000, service_tier="priority")
        self.assertIsNone(cost(r))
        self.assertIsNone(parts(r))

    def test_other_service_tiers_are_not_priced(self):
        for tier in ("batch", "auto", "", "Standard"):
            with self.subTest(tier=tier):
                self.assertIsNone(cost(rec(input=1000, service_tier=tier)))

    def test_non_string_modifier_values_are_not_priced(self):
        for field in ("speed", "service_tier", "inference_geo"):
            for value in (1, True, ["fast"]):
                with self.subTest(field=field, value=value):
                    self.assertIsNone(cost(rec(input=1000, **{field: value})))


class ModelNameTests(unittest.TestCase):
    def test_name_forms_reach_the_catalog_price(self):
        names = [
            "claude-opus-5-5",
            "claude-opus-5-5-20261001",
            "claude-opus-5-5[1m]",
            "us.anthropic.claude-opus-5-5-v1:0",
            "claude-opus-5-5@20261001",
            "opus",
        ]
        expected = None
        for name in names:
            with self.subTest(name=name):
                norm, _form = resolve.normalize_model(name, CATALOG)
                if norm != "claude-opus-5-5":
                    # An alias may point at a different model; skip the price match.
                    self.assertIsNotNone(norm)
                    continue
                value = cost(rec(name, input=1000000))
                expected = value if expected is None else expected
                self.assertAlmostEqual(value, 4)

    def test_1m_names_have_no_surcharge(self):
        plain = cost(rec("claude-sonnet-5-5", input=900000, output=1000))
        long_ctx = cost(rec("claude-sonnet-5-5[1m]", input=900000, output=1000))
        self.assertEqual(plain, long_ctx)
        self.assertAlmostEqual(plain, (900000 * 2 + 1000 * 10) / 1e6)

    def test_dated_haiku_5_5_still_tiers(self):
        r = rec("claude-haiku-5-5-20261001", input=100001)
        self.assertAlmostEqual(cost(r), 100001 * HAIKU_TIER[0] / 1e6)

    def test_unknown_model_is_not_priced(self):
        for name in ("gpt-5", "claude-opus-9", "", None, 42, "<synthetic>"):
            with self.subTest(name=name):
                self.assertIsNone(cost(rec(name, input=1000)))

    def test_catalog_model_without_a_price_entry_is_not_priced(self):
        doc = copy.deepcopy(PRICES)
        del doc["models"]["claude-opus-5-5"]
        self.assertIsNone(cost(rec("claude-opus-5-5", input=1000), doc))
        self.assertIsNotNone(cost(rec("claude-opus-5", input=1000), doc))


class PurityTests(unittest.TestCase):
    def test_price_does_not_change_its_inputs(self):
        doc = copy.deepcopy(PRICES)
        r = rec("claude-haiku-5-5", input=150000, speed=None)
        before = vars(r).copy()
        cost(r, doc)
        self.assertEqual(doc, PRICES)
        self.assertEqual(vars(r), before)

    def test_price_reads_no_file(self):
        from unittest import mock
        with mock.patch("builtins.open", side_effect=AssertionError("file read")):
            self.assertIsNotNone(cost(rec(input=1000)))


class CheckTests(unittest.TestCase):
    def check(self, doc):
        return prices_mod.check(doc, CATALOG)

    def edited(self, edit):
        doc = copy.deepcopy(PRICES)
        edit(doc)
        return doc

    def assertFails(self, edit, fragment):
        errors = self.check(self.edited(edit))
        self.assertTrue(any(fragment in e for e in errors), errors)

    def test_real_file_is_clean(self):
        self.assertEqual(self.check(PRICES), [])

    def test_not_an_object(self):
        self.assertEqual(self.check([]), ["prices is not an object"])

    def test_missing_top_level_field(self):
        for field in ("schema_version", "source", "verified_on", "unit", "models",
                      "modifiers"):
            with self.subTest(field=field):
                self.assertFails(lambda d: d.pop(field), "missing field %s" % field)

    def test_unknown_top_level_field(self):
        self.assertFails(lambda d: d.update(extra=1), "unknown field extra")

    def test_schema_version(self):
        self.assertFails(lambda d: d.update(schema_version=2), "schema_version")

    def test_source_must_be_a_url(self):
        for bad in ("pricing page", "", None, 5):
            with self.subTest(source=bad):
                self.assertFails(lambda d: d.update(source=bad), "source must be a URL")

    def test_verified_on_must_be_a_date(self):
        for bad in ("October 30, 2026", "2026-13-01", "2026-10-3", "", None, 20261030):
            with self.subTest(verified_on=bad):
                self.assertFails(lambda d: d.update(verified_on=bad), "verified_on")

    def test_unit(self):
        self.assertFails(lambda d: d.update(unit=""), "unit")

    def test_key_not_in_the_catalog(self):
        self.assertFails(
            lambda d: d["models"].update({"claude-nope-1": d["models"]["claude-opus-5"]}),
            "claude-nope-1: not a catalog id")

    def test_catalog_model_without_an_entry(self):
        self.assertFails(lambda d: d["models"].pop("claude-sonnet-4-6"),
                         "claude-sonnet-4-6: no price entry")

    def test_negative_number(self):
        self.assertFails(lambda d: d["models"]["claude-opus-5"].update(input=-1),
                         "must not be negative")

    def test_negative_tier_number(self):
        self.assertFails(
            lambda d: d["models"]["claude-haiku-5-5"]["tiers"][0].update(output=-0.5),
            "must not be negative")

    def test_non_number_price(self):
        for bad in ("5", None, True):
            with self.subTest(value=bad):
                self.assertFails(lambda d: d["models"]["claude-opus-5"].update(output=bad),
                                 "output must be a number")

    def test_missing_price_field(self):
        self.assertFails(lambda d: d["models"]["claude-opus-5"].pop("cache_read"),
                         "cache_read must be a number")

    def test_unknown_entry_field(self):
        self.assertFails(lambda d: d["models"]["claude-opus-5"].update(extra=1),
                         "unknown field extra")

    def test_tiers_must_ascend(self):
        def edit(d):
            tier = d["models"]["claude-haiku-5-5"]["tiers"][0]
            d["models"]["claude-haiku-5-5"]["tiers"].append(
                dict(tier, prompt_tokens_over=50000))
        self.assertFails(edit, "tiers must ascend")

    def test_equal_tier_thresholds_fail(self):
        def edit(d):
            tier = d["models"]["claude-haiku-5-5"]["tiers"][0]
            d["models"]["claude-haiku-5-5"]["tiers"].append(dict(tier))
        self.assertFails(edit, "tiers must ascend")

    def test_tier_threshold_must_be_a_number(self):
        self.assertFails(
            lambda d: d["models"]["claude-haiku-5-5"]["tiers"][0].update(
                prompt_tokens_over="100000"),
            "prompt_tokens_over")

    def test_modifier_model_not_in_the_catalog(self):
        self.assertFails(
            lambda d: d["modifiers"]["speed"]["fast"]["models"].append("claude-nope-1"),
            "claude-nope-1 is not a catalog id")

    def test_modifier_default_must_be_one(self):
        self.assertFails(lambda d: d["modifiers"]["service_tier"].update(standard=2),
                         "must be 1")

    def test_modifier_default_must_exist(self):
        self.assertFails(lambda d: d["modifiers"]["inference_geo"].pop("global"),
                         "must list global")

    def test_modifier_multiplier_must_be_a_number(self):
        self.assertFails(
            lambda d: d["modifiers"]["speed"]["fast"].update(multiplier="2"),
            "multiplier")

    def test_us_list_is_every_catalog_id_except_haiku_4_5(self):
        listed = PRICES["modifiers"]["inference_geo"]["us"]["models"]
        self.assertEqual(sorted(listed),
                         sorted(i for i in CATALOG_IDS if i not in NO_US))

    def test_fast_list(self):
        listed = PRICES["modifiers"]["speed"]["fast"]["models"]
        self.assertEqual(sorted(listed), sorted(FAST_MODELS))
        self.assertEqual(PRICES["modifiers"]["speed"]["fast"]["multiplier"], 2)
        self.assertEqual(PRICES["modifiers"]["inference_geo"]["us"]["multiplier"], 1.1)
        self.assertNotIn("priority", PRICES["modifiers"]["service_tier"])


class CommandTests(unittest.TestCase):
    SCRIPT = os.path.join(helpers.REPO, "dashboard", "prices.py")

    def run_check(self, *extra):
        return subprocess.run(
            [sys.executable, self.SCRIPT, "check"] + list(extra),
            capture_output=True, text=True, timeout=60)

    def test_check_command_passes_on_the_real_file(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_check_command_fails_on_a_bad_file(self):
        import json
        import tempfile
        doc = copy.deepcopy(PRICES)
        doc["models"]["claude-opus-5"]["input"] = -1
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prices.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh)
            result = self.run_check(path)
        self.assertEqual(result.returncode, 1)
        self.assertIn("must not be negative", result.stdout)

    def test_check_command_fails_on_a_missing_file(self):
        result = self.run_check(os.path.join(helpers.REPO, "no-such-prices.json"))
        self.assertEqual(result.returncode, 1)

    def test_unknown_command_exits_2(self):
        result = subprocess.run([sys.executable, self.SCRIPT, "bogus"],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
