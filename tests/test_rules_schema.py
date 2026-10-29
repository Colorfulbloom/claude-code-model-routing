"""Tests for dashboard/rules.json and its schema check (dashboard/rules_schema.py).

These tests read only files inside the repo and their own temp folders. They
never touch the real ~/.claude.
"""
import contextlib
import copy
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import rules_schema  # noqa: E402

GOOD_RULE = {
    "rule_id": "effort-level-user-settings-opus-5-5",
    "key": "effortLevel",
    "scope": "main",
    "layer_order": ["managed", "cli", "local", "project", "user"],
    "combine": "highest_layer",
    "conditions": [{"layer": "user", "models": ["claude-opus-5-5"], "status": "ignored"}],
    "reason": "Opus 5.5 ignores effortLevel in {file}.",
    "quotes": [{
        "doc_url": "https://code.claude.com/docs/en/settings-reference#effortlevel",
        "quote": "Opus 5.5 and models released after it ignore it.",
    }],
    "experiment": None,
    "confidence": "documented",
    "verified_on": {"claude_version": "2.1.302", "date": "2026-10-29"},
}


def _catalog_entry(mid, aliases, levels, default):
    return {
        "id": mid, "aliases": aliases, "effort_levels": levels, "default_effort": default,
        "quotes": [{
            "doc_url": "https://code.claude.com/docs/en/model-config",
            "quote": "Made-up quote for the %s entry." % mid,
        }],
        "experiment": None, "confidence": "documented",
    }


# Release order, oldest first.
GOOD_MODELS = [
    _catalog_entry("claude-opus-4-6", [], ["low", "medium", "high"], "high"),
    _catalog_entry("claude-sonnet-5-5", ["sonnet"], ["low", "medium", "high", "xhigh"], "medium"),
    _catalog_entry("claude-opus-5-5", ["opus"], ["low", "medium", "high", "xhigh", "max"], "high"),
    _catalog_entry("claude-fable-5-1", ["fable"], ["low", "medium", "high", "xhigh", "max"], "high"),
]
CATALOG_IDS = [m["id"] for m in GOOD_MODELS]

GOOD_RECORD = {
    "date": "2026-10-29",
    "claude_version": "2.1.302",
    "ran": "claude -p with effortLevel xhigh in User settings, then /effort status",
    "result": "/effort status reported medium",
}


class TempDirMixin:
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="rules-schema-", dir=helpers._tmp_base())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write_record(self, name, record):
        path = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        return name

    def rule(self, **changes):
        rule = copy.deepcopy(GOOD_RULE)
        for field, value in changes.items():
            if value is DROP:
                rule.pop(field, None)
            else:
                rule[field] = value
        return rule

    def model(self, **changes):
        model = copy.deepcopy(GOOD_MODELS[2])
        for field, value in changes.items():
            if value is DROP:
                model.pop(field, None)
            else:
                model[field] = value
        return model

    def errors(self, rule):
        return rules_schema.check_rule(rule, self.tmp, CATALOG_IDS)

    def model_errors(self, model):
        return rules_schema.check_model(model, self.tmp)

    def document(self, **changes):
        data = {"schema_version": 3, "models": copy.deepcopy(GOOD_MODELS),
                "rules": [self.rule()]}
        data.update(changes)
        return data

    def assertModelRejected(self, model, fragment):
        errs = self.model_errors(model)
        self.assertTrue(any(fragment in e for e in errs),
                        "expected an error containing %r, got %r" % (fragment, errs))

    def assertDocRejected(self, data, fragment):
        errs = rules_schema.validate(data, self.tmp)
        self.assertTrue(any(fragment in e for e in errs),
                        "expected an error containing %r, got %r" % (fragment, errs))

    def assertRejected(self, rule, fragment):
        errs = self.errors(rule)
        self.assertTrue(any(fragment in e for e in errs),
                        "expected an error containing %r, got %r" % (fragment, errs))


DROP = object()


class RealRulesFileTest(unittest.TestCase):
    def test_rules_json_exists(self):
        self.assertTrue(os.path.isfile(rules_schema.RULES_PATH))

    def test_every_entry_passes_the_schema(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertIsInstance(data.get("rules"), list)
        for rule in data["rules"]:
            with self.subTest(rule=rule.get("rule_id")):
                self.assertEqual(rules_schema.check_rule(rule), [])
        self.assertEqual(rules_schema.load_and_validate(), [])

    def test_tested_entries_point_to_a_complete_record(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        for rule in data["rules"]:
            if rule.get("confidence") == "tested":
                with self.subTest(rule=rule["rule_id"]):
                    path = os.path.join(os.path.dirname(rules_schema.RULES_PATH),
                                        rule["experiment"])
                    self.assertEqual(rules_schema.check_experiment(path), [])

    def test_every_model_has_a_levels_table_quote_as_well(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        for model in data["models"]:
            # A model with no effort levels has no row in the levels table, so its
            # one quote ("Models not listed here do not support effort") is enough.
            if not model["effort_levels"]:
                continue
            with self.subTest(model=model["id"]):
                self.assertGreaterEqual(len(model["quotes"]), 2)
                self.assertTrue(any("`low`, `medium`, `high`" in q["quote"]
                                    for q in model["quotes"][1:]))

    def test_settings_values_rule_points_to_the_set_the_effort_level_section(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        rule = next(r for r in data["rules"] if r["rule_id"] == "effort-level-settings-values")
        self.assertEqual([q["doc_url"] for q in rule["quotes"]],
                         ["https://code.claude.com/docs/en/model-config#set-the-effort-level"])

    def test_flag_rule_leaves_ultracode_out_but_says_why(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        rule = next(r for r in data["rules"] if r["rule_id"] == "effort-flag-values")
        for cond in rule["conditions"]:
            self.assertNotIn("ultracode", cond.get("values", []))
        self.assertIn("ultracode", rule["reason"])
        self.assertIn("wasn't tested on 2.1.302", rule["reason"])

    def test_cli_reports_ok(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(rules_schema.main(["rules_schema.py"]), 0)
        self.assertEqual(out.getvalue(), "ok\n")


class VocabularyTest(unittest.TestCase):
    def test_seven_status_words(self):
        self.assertEqual(
            sorted(rules_schema.STATUS_WORDS.values()),
            sorted(["In effect", "Overridden", "Ignored", "Invalid", "Lowered",
                    "Default", "Unknown"]))

    def test_three_confidence_words(self):
        self.assertEqual(sorted(rules_schema.CONFIDENCE_WORDS.values()),
                         ["Assumed", "Documented", "Tested"])

    def test_data_names_map_to_screen_words(self):
        self.assertEqual(rules_schema.STATUS_WORDS["in_effect"], "In effect")
        self.assertEqual(rules_schema.CONFIDENCE_WORDS["tested"], "Tested")


class ReasonAndSourceTest(TempDirMixin, unittest.TestCase):
    def test_good_rule_passes(self):
        self.assertEqual(self.errors(self.rule()), [])

    def test_missing_reason_fails(self):
        self.assertRejected(self.rule(reason=DROP), "missing field reason")

    def test_empty_reason_fails(self):
        self.assertRejected(self.rule(reason="  "), "reason is empty")

    def test_null_reason_fails(self):
        self.assertRejected(self.rule(reason=None), "reason is empty")

    def test_no_quote_and_no_experiment_fails(self):
        rule = self.rule(quotes=[], confidence="documented")
        self.assertRejected(rule, "no source")

    def test_tested_with_no_source_fails(self):
        rule = self.rule(quotes=[], confidence="tested")
        self.assertRejected(rule, "no source")

    def test_assumed_needs_no_source(self):
        rule = self.rule(quotes=[], confidence="assumed")
        self.assertEqual(self.errors(rule), [])

    def test_assumed_bad_quote_item_still_fails(self):
        rule = self.rule(quotes=[dict(GOOD_RULE["quotes"][0], doc_url="http://example.com")],
                         confidence="assumed")
        self.assertRejected(rule, "quotes[0]: doc_url must be an https link")

    def test_documented_with_empty_quotes_fails(self):
        self.assertRejected(self.rule(quotes=[], confidence="documented"), "no source")

    def test_tested_with_empty_quotes_and_a_record_passes(self):
        name = self.write_record("experiments/effort.json", GOOD_RECORD)
        rule = self.rule(quotes=[], experiment=name, confidence="tested")
        self.assertEqual(self.errors(rule), [])

    def test_two_quotes_pass(self):
        second = {"doc_url": "https://code.claude.com/docs/en/model-config",
                  "quote": "A second made-up quote."}
        self.assertEqual(self.errors(self.rule(quotes=[GOOD_RULE["quotes"][0], second])), [])

    def test_quote_item_missing_doc_url_fails(self):
        self.assertRejected(self.rule(quotes=[{"quote": "Some text."}]),
                            "quotes[0]: missing field doc_url")

    def test_quote_item_missing_quote_fails(self):
        self.assertRejected(self.rule(quotes=[{"doc_url": "https://example.com/a"}]),
                            "quotes[0]: missing field quote")

    def test_quote_item_with_http_link_fails(self):
        item = {"doc_url": "http://example.com", "quote": "Some text."}
        self.assertRejected(self.rule(quotes=[item]), "quotes[0]: doc_url must be an https link")

    def test_quote_item_with_empty_quote_fails(self):
        item = {"doc_url": "https://example.com/a", "quote": "  "}
        self.assertRejected(self.rule(quotes=[item]), "quotes[0]: quote must be a non-empty")

    def test_quote_item_with_extra_key_fails(self):
        item = dict(GOOD_RULE["quotes"][0], page="intro")
        self.assertRejected(self.rule(quotes=[item]), "quotes[0]: unknown field page")

    def test_error_names_the_index_of_the_bad_item(self):
        bad = {"doc_url": "http://example.com", "quote": "Some text."}
        self.assertRejected(self.rule(quotes=[GOOD_RULE["quotes"][0], bad]), "quotes[1]:")

    def test_quotes_must_be_a_list(self):
        self.assertRejected(self.rule(quotes=GOOD_RULE["quotes"][0]), "quotes must be a list")
        self.assertRejected(self.rule(quotes=None), "quotes must be a list")

    def test_quote_item_must_be_an_object(self):
        self.assertRejected(self.rule(quotes=["text"]), "quotes[0]: must be an object")

    def test_repeated_quote_item_fails(self):
        item = GOOD_RULE["quotes"][0]
        self.assertRejected(self.rule(quotes=[item, dict(item)]), "quotes[1]: repeats")

    def test_old_doc_url_and_quote_fields_are_unknown(self):
        rule = self.rule()
        rule["doc_url"] = "https://example.com/a"
        rule["quote"] = "Some text."
        self.assertRejected(rule, "unknown field doc_url")
        self.assertRejected(rule, "unknown field quote")

    def test_quotes_is_required(self):
        self.assertRejected(self.rule(quotes=DROP), "missing field quotes")

    def test_assumed_with_quote_passes(self):
        self.assertEqual(self.errors(self.rule(confidence="assumed")), [])

    def test_experiment_alone_is_a_source(self):
        name = self.write_record("experiments/effort.json", GOOD_RECORD)
        rule = self.rule(quotes=[], experiment=name, confidence="tested")
        self.assertEqual(self.errors(rule), [])

    def test_documented_needs_quote(self):
        name = self.write_record("experiments/effort.json", GOOD_RECORD)
        rule = self.rule(quotes=[], experiment=name)
        self.assertRejected(rule, "documented rule needs at least one quote")


class ExperimentRecordTest(TempDirMixin, unittest.TestCase):
    def make_tested(self, record):
        name = self.write_record("experiments/x.json", record)
        return self.rule(experiment=name, confidence="tested")

    def test_tested_without_experiment_fails(self):
        self.assertRejected(self.rule(confidence="tested"), "tested rule needs an experiment")

    def test_tested_with_record_passes(self):
        self.assertEqual(self.errors(self.make_tested(GOOD_RECORD)), [])

    def test_record_needs_each_field(self):
        for field in ("date", "claude_version", "ran", "result"):
            with self.subTest(field=field):
                record = dict(GOOD_RECORD)
                del record[field]
                self.assertRejected(self.make_tested(record), "has no %s" % field)

    def test_record_fields_are_checked(self):
        cases = {"date": "October 29", "claude_version": "latest", "ran": "", "result": " "}
        for field, bad in cases.items():
            with self.subTest(field=field):
                record = dict(GOOD_RECORD, **{field: bad})
                self.assertRejected(self.make_tested(record), field)

    def test_missing_record_file_fails(self):
        rule = self.rule(experiment="experiments/nope.json", confidence="tested")
        self.assertRejected(rule, "cannot read experiment record")

    def test_record_path_stays_inside(self):
        for bad in ("/etc/passwd", "../x.json"):
            with self.subTest(path=bad):
                self.assertRejected(self.rule(experiment=bad), "inside the dashboard folder")


class FieldTest(TempDirMixin, unittest.TestCase):
    def test_every_field_is_required(self):
        for field in sorted(rules_schema.RULE_FIELDS):
            with self.subTest(field=field):
                self.assertRejected(self.rule(**{field: DROP}), "missing field %s" % field)

    def test_unknown_field_fails(self):
        rule = self.rule()
        rule["wins"] = True
        self.assertRejected(rule, "unknown field wins")

    def test_scope(self):
        for scope in ("main", "agent", "model"):
            with self.subTest(scope=scope):
                self.assertEqual(self.errors(self.rule(scope=scope)), [])
        self.assertRejected(self.rule(scope="session"), "scope must be")

    def test_rule_id_and_key(self):
        self.assertRejected(self.rule(rule_id="Effort Level"), "rule_id")
        self.assertRejected(self.rule(key=""), "key must be")
        self.assertEqual(self.errors(self.rule(key="experimental.cacheTtl")), [])

    def test_unknown_confidence_fails(self):
        self.assertRejected(self.rule(confidence="observed"), "confidence must be")

    def test_unhashable_confidence_gives_an_error_not_an_exception(self):
        for bad in (["documented"], {"documented": 1}):
            with self.subTest(confidence=bad):
                self.assertRejected(self.rule(confidence=bad), "confidence must be one of")

    def test_layer_order(self):
        self.assertRejected(self.rule(layer_order=[]), "layer_order must be")
        self.assertRejected(self.rule(layer_order=["user", "nowhere"]), "unknown layer")
        self.assertRejected(self.rule(layer_order=["user", "user"]), "repeats")

    def test_flag_and_cli_are_separate_layers(self):
        rule = self.rule(layer_order=["flag", "env", "managed", "cli", "local", "project",
                                      "user", "default"],
                         conditions=[{"layer": "flag", "models": ["*"], "status": "in_effect"}])
        self.assertEqual(self.errors(rule), [])

    def test_verified_on(self):
        self.assertRejected(self.rule(verified_on={"date": "2026-10-29"}),
                            "verified_on has no claude_version")
        self.assertRejected(self.rule(verified_on={"claude_version": "2.1.302"}),
                            "verified_on has no date")
        self.assertRejected(self.rule(verified_on={"claude_version": "2.1",
                                                   "date": "2026-10-29"}),
                            "claude_version must look like")
        self.assertRejected(self.rule(verified_on={"claude_version": "2.1.302",
                                                   "date": "2026-13-01"}),
                            "date must be")


class ConditionTest(TempDirMixin, unittest.TestCase):
    def cond(self, **fields):
        base = {"layer": "user", "models": ["claude-opus-5-5"], "status": "ignored"}
        base.update(fields)
        return self.rule(conditions=[base])

    def test_every_status_is_allowed(self):
        for status in rules_schema.STATUS_WORDS:
            with self.subTest(status=status):
                rule = self.cond(status=status)
                if status == "lowered":
                    rule["conditions"][0]["becomes"] = "high"
                self.assertEqual(self.errors(rule), [])

    def test_screen_word_or_other_name_is_not_a_status(self):
        for bad in ("In effect", "wins", "shadowed", "conflict", "unparsed"):
            with self.subTest(status=bad):
                self.assertRejected(self.cond(status=bad), "status must be")

    def test_condition_layer_must_be_in_the_order(self):
        self.assertRejected(self.cond(layer="env"), "not in layer_order")

    def test_models(self):
        self.assertEqual(self.errors(self.cond(models=["*"])), [])
        self.assertRejected(self.cond(models=[]), "models must be")
        self.assertRejected(self.cond(models=["*", "claude-opus-5-5"]), "stands alone")

    def test_values_and_becomes(self):
        self.assertEqual(self.errors(self.cond(status="invalid", values=["max"])), [])
        self.assertRejected(self.cond(values=[]), "values must be")
        self.assertRejected(self.cond(becomes="high"), "only for a lowered")

    def test_values_must_be_unique_strings(self):
        for bad in ([5], ["max", 5], [True], [None], [["max"]], [{"a": 1}]):
            with self.subTest(values=bad):
                self.assertRejected(self.cond(status="invalid", values=bad), "values must all be")
        self.assertRejected(self.cond(status="invalid", values=["max", "max"]), "values repeat")
        self.assertEqual(self.errors(self.cond(status="invalid", values=["max", "high"])), [])

    def test_unhashable_status_gives_an_error_not_an_exception(self):
        for bad in (["ignored"], {"ignored": 1}):
            with self.subTest(status=bad):
                self.assertRejected(self.cond(status=bad), "status must be one of")

    def test_lowered_needs_becomes(self):
        self.assertRejected(self.cond(status="lowered"), "lowered needs becomes")
        self.assertEqual(self.errors(self.cond(status="lowered", becomes="high")), [])

    def test_empty_conditions_fail(self):
        self.assertRejected(self.rule(conditions=[]), "conditions must be")

    def test_unknown_condition_field_fails(self):
        self.assertRejected(self.cond(why="x"), "unknown field why")


class ReasonTemplateTest(TempDirMixin, unittest.TestCase):
    def test_known_slots_pass(self):
        rule = self.rule(reason="{winner} overrides {key} in {file} for {model}.")
        self.assertEqual(self.errors(rule), [])

    def test_becomes_slot_passes(self):
        rule = self.rule(reason="{key} {value} runs as {becomes} on {model}.")
        self.assertEqual(self.errors(rule), [])

    def test_reason_needs_no_slot(self):
        rule = self.rule(reason="Claude Code ignores this key here.")
        self.assertEqual(self.errors(rule), [])

    def test_unknown_slot_fails(self):
        self.assertRejected(self.rule(reason="Ignored in {path}."), "unknown slot {path}")

    def test_bad_braces_fail(self):
        for bad in ("Ignored in {file.", "Ignored in {}.", "Ignored in {file!r}.",
                    "Ignored in {file:>9}."):
            with self.subTest(reason=bad):
                self.assertRejected(self.rule(reason=bad), "reason template")


class ModelCatalogTest(TempDirMixin, unittest.TestCase):
    def test_good_entries_pass(self):
        for model in GOOD_MODELS:
            with self.subTest(model=model["id"]):
                self.assertEqual(self.model_errors(model), [])

    def test_model_with_no_effort_levels_passes(self):
        model = self.model(effort_levels=[], default_effort=None)
        self.assertEqual(self.model_errors(model), [])

    def test_every_field_is_required(self):
        for field in sorted(rules_schema.MODEL_FIELDS):
            with self.subTest(field=field):
                self.assertModelRejected(self.model(**{field: DROP}), "missing field %s" % field)

    def test_unknown_field_fails(self):
        model = self.model()
        model["family"] = "opus"
        self.assertModelRejected(model, "unknown field family")

    def test_bad_id_fails(self):
        for bad in ("Claude Opus", "claude_opus", "", "-opus", 5):
            with self.subTest(id=bad):
                self.assertModelRejected(self.model(id=bad), "id must be")

    def test_bad_alias_fails(self):
        for bad in (["Opus"], ["opus-1"], [""], [5]):
            with self.subTest(aliases=bad):
                self.assertModelRejected(self.model(aliases=bad), "alias")
        self.assertModelRejected(self.model(aliases="opus"), "aliases must be a list")
        self.assertModelRejected(self.model(aliases=["opus", "opus"]), "aliases repeat")

    def test_effort_levels_out_of_order_fail(self):
        self.assertModelRejected(self.model(effort_levels=["high", "low"], default_effort="low"),
                                 "out of order")

    def test_effort_levels_repeat_fails(self):
        self.assertModelRejected(self.model(effort_levels=["low", "low"], default_effort="low"),
                                 "repeats a level")

    def test_unknown_effort_level_fails(self):
        self.assertModelRejected(self.model(effort_levels=["low", "ultra"], default_effort="low"),
                                 "unknown effort level 'ultra'")

    def test_effort_levels_must_be_a_list(self):
        self.assertModelRejected(self.model(effort_levels="low"), "effort_levels must be a list")

    def test_default_effort_must_be_one_of_the_levels(self):
        model = self.model(effort_levels=["low", "medium"], default_effort="high")
        self.assertModelRejected(model, "default_effort must be one of effort_levels")
        self.assertModelRejected(self.model(default_effort=None),
                                 "default_effort must be one of effort_levels")

    def test_default_effort_with_empty_levels_fails(self):
        model = self.model(effort_levels=[], default_effort="low")
        self.assertModelRejected(model, "default_effort must be null")

    def test_entry_with_no_source_fails_unless_assumed(self):
        bare = self.model(quotes=[])
        self.assertModelRejected(bare, "no source")
        tested = self.model(quotes=[], confidence="tested")
        self.assertModelRejected(tested, "no source")
        self.assertEqual(self.model_errors(self.model(quotes=[],
                                                      confidence="assumed")), [])

    def test_documented_entry_needs_a_quote(self):
        self.assertModelRejected(self.model(quotes=[]), "no source")
        name = self.write_record("experiments/model.json", GOOD_RECORD)
        model = self.model(quotes=[], experiment=name)
        self.assertModelRejected(model, "documented model needs at least one quote")

    def test_tested_entry_needs_a_record(self):
        self.assertModelRejected(self.model(confidence="tested"),
                                 "tested model needs an experiment record")
        name = self.write_record("experiments/model.json", GOOD_RECORD)
        model = self.model(quotes=[], experiment=name, confidence="tested")
        self.assertEqual(self.model_errors(model), [])

    def test_source_fields_are_checked_like_a_rule(self):
        item = {"doc_url": "http://example.com", "quote": "Some text."}
        self.assertModelRejected(self.model(quotes=[item]), "quotes[0]: doc_url must be an https")
        self.assertModelRejected(self.model(quotes=[{"quote": "Some text."}]),
                                 "quotes[0]: missing field doc_url")
        self.assertModelRejected(self.model(quotes=[{"doc_url": "https://example.com/a",
                                                     "quote": ""}]), "quotes[0]: quote must be")
        self.assertModelRejected(self.model(quotes=[dict(GOOD_MODELS[2]["quotes"][0], x=1)]),
                                 "quotes[0]: unknown field x")
        self.assertModelRejected(self.model(quotes="text"), "quotes must be a list")
        self.assertModelRejected(self.model(quotes=GOOD_MODELS[2]["quotes"] * 2),
                                 "quotes[1]: repeats")
        self.assertModelRejected(self.model(experiment="../x.json"), "inside the dashboard folder")
        self.assertModelRejected(self.model(experiment="experiments/nope.json"),
                                 "cannot read experiment record")
        self.assertModelRejected(self.model(confidence="observed"), "confidence must be")

    def test_two_quotes_pass_on_a_model(self):
        second = {"doc_url": "https://example.com/a", "quote": "Another made-up quote."}
        self.assertEqual(self.model_errors(
            self.model(quotes=GOOD_MODELS[2]["quotes"] + [second])), [])

    def test_tested_entry_with_empty_quotes_and_a_record_passes(self):
        name = self.write_record("experiments/model.json", GOOD_RECORD)
        model = self.model(quotes=[], experiment=name, confidence="tested")
        self.assertEqual(self.model_errors(model), [])

    def test_old_doc_url_and_quote_fields_are_unknown_on_a_model(self):
        model = self.model()
        model["doc_url"] = "https://example.com/a"
        model["quote"] = "Some text."
        self.assertModelRejected(model, "unknown field doc_url")
        self.assertModelRejected(model, "unknown field quote")

class ModelsConditionTest(TempDirMixin, unittest.TestCase):
    def cond(self, models, **fields):
        base = {"layer": "user", "models": models, "status": "ignored"}
        base.update(fields)
        return self.rule(conditions=[base])

    def test_from_object_with_a_catalog_id_passes(self):
        self.assertEqual(self.errors(self.cond([{"from": "claude-opus-5-5"}])), [])

    def test_from_object_mixed_with_plain_ids_passes(self):
        rule = self.cond(["claude-opus-4-6", {"from": "claude-opus-5-5"}])
        self.assertEqual(self.errors(rule), [])

    def test_from_with_an_unknown_id_fails(self):
        self.assertRejected(self.cond([{"from": "claude-opus-9-9"}]), "unknown model")

    def test_plain_id_not_in_the_catalog_fails(self):
        self.assertRejected(self.cond(["claude-opus-9-9"]), "unknown model")

    def test_no_catalog_skips_only_the_membership_check(self):
        rule = self.cond([{"from": "claude-opus-9-9"}, "claude-nope-1"])
        self.assertEqual(rules_schema.check_rule(rule, self.tmp), [])
        bad = self.cond([{"from": "claude-opus-9-9", "extra": 1}, ""])
        self.assertTrue(rules_schema.check_rule(bad, self.tmp))

    def test_from_with_an_extra_key_fails(self):
        self.assertRejected(self.cond([{"from": "claude-opus-5-5", "to": "claude-fable-5-1"}]),
                            "exactly one key, from")

    def test_object_without_from_fails(self):
        self.assertRejected(self.cond([{"after": "claude-opus-5-5"}]), "exactly one key, from")

    def test_from_value_must_be_a_model_id(self):
        for bad in ("", 5, None, "*"):
            with self.subTest(value=bad):
                self.assertRejected(self.cond([{"from": bad}]), "from must be a model id")

    def test_star_mixed_with_from_fails(self):
        self.assertRejected(self.cond(["*", {"from": "claude-opus-5-5"}]), "stands alone")

    def test_star_stands_alone_and_passes(self):
        self.assertEqual(self.errors(self.cond(["*"])), [])

    def test_empty_models_and_odd_items_fail(self):
        self.assertRejected(self.cond([]), "models must be")
        self.assertRejected(self.cond("claude-opus-5-5"), "models must be")
        self.assertRejected(self.cond([5]), "models item")

    def test_repeated_plain_id_fails(self):
        self.assertRejected(self.cond(["claude-opus-5-5", "claude-opus-5-5"]),
                            "repeat or overlap on claude-opus-5-5")

    def test_plain_id_inside_a_from_range_fails(self):
        self.assertRejected(self.cond([{"from": "claude-sonnet-5-5"}, "claude-opus-5-5"]),
                            "repeat or overlap on claude-opus-5-5")
        self.assertRejected(self.cond(["claude-fable-5-1", {"from": "claude-opus-5-5"}]),
                            "repeat or overlap on claude-fable-5-1")

    def test_two_from_ranges_overlap_and_repeat_fails(self):
        self.assertRejected(
            self.cond([{"from": "claude-sonnet-5-5"}, {"from": "claude-opus-5-5"}]),
            "repeat or overlap")
        self.assertRejected(
            self.cond([{"from": "claude-opus-5-5"}, {"from": "claude-opus-5-5"}]),
            "repeat or overlap")

    def test_disjoint_plain_id_and_from_range_passes(self):
        self.assertEqual(
            self.errors(self.cond(["claude-opus-4-6", {"from": "claude-sonnet-5-5"}])), [])

    def test_repeats_without_a_catalog_fail_for_identical_items(self):
        dup = self.cond(["claude-nope-1", "claude-nope-1"])
        self.assertTrue(any("repeat" in e for e in rules_schema.check_rule(dup, self.tmp)))
        dup = self.cond([{"from": "claude-nope-1"}, {"from": "claude-nope-1"}])
        self.assertTrue(any("repeat" in e for e in rules_schema.check_rule(dup, self.tmp)))

    def test_expand_models_bad_items_raise_value_error_only(self):
        for bad in ([5], [None], [""], [["claude-opus-5-5"]], [{}], [{"from": 5}],
                    [{"from": ["claude-opus-5-5"]}], [{"after": "claude-opus-5-5"}],
                    [{"from": "claude-opus-5-5", "to": "x"}], "claude-opus-5-5", 5, None):
            with self.subTest(models=bad):
                with self.assertRaises(ValueError):
                    rules_schema.expand_models(bad, CATALOG_IDS)

    def test_expand_models_covers_x_and_later(self):
        got = rules_schema.expand_models([{"from": "claude-sonnet-5-5"}], CATALOG_IDS)
        self.assertEqual(got, ["claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"])

    def test_expand_models_from_the_last_model_is_just_that_model(self):
        got = rules_schema.expand_models([{"from": "claude-fable-5-1"}], CATALOG_IDS)
        self.assertEqual(got, ["claude-fable-5-1"])

    def test_expand_models_star(self):
        self.assertEqual(rules_schema.expand_models(["*"], CATALOG_IDS), ["*"])

    def test_expand_models_plain_ids_and_no_repeats(self):
        got = rules_schema.expand_models(
            ["claude-opus-4-6", {"from": "claude-opus-5-5"}, "claude-fable-5-1"], CATALOG_IDS)
        self.assertEqual(got, ["claude-opus-4-6", "claude-opus-5-5", "claude-fable-5-1"])

    def test_expand_models_unknown_from_raises(self):
        with self.assertRaises(ValueError):
            rules_schema.expand_models([{"from": "claude-opus-9-9"}], CATALOG_IDS)


class CombineTest(TempDirMixin, unittest.TestCase):
    def test_combine_is_required(self):
        self.assertRejected(self.rule(combine=DROP), "missing field combine")

    def test_unknown_combine_fails(self):
        for bad in ("first", "", None, ["highest_layer"]):
            with self.subTest(combine=bad):
                self.assertRejected(self.rule(combine=bad), "combine must be one of")

    def test_highest_layer_passes(self):
        self.assertEqual(self.errors(self.rule(combine="highest_layer")), [])

    def test_lowest_value_with_value_order_passes(self):
        rule = self.rule(combine="lowest_value", value_order=["low", "medium", "high"])
        self.assertEqual(self.errors(rule), [])

    def test_lowest_value_without_value_order_fails(self):
        self.assertRejected(self.rule(combine="lowest_value"), "needs value_order")

    def test_value_order_with_highest_layer_fails(self):
        rule = self.rule(combine="highest_layer", value_order=["low", "high"])
        self.assertRejected(rule, "value_order is only for combine lowest_value")

    def test_value_order_repeats_fail(self):
        rule = self.rule(combine="lowest_value", value_order=["low", "high", "low"])
        self.assertRejected(rule, "value_order repeats")

    def test_bad_value_order_fails(self):
        for bad in ([], "low", ["low", ""], ["low", 5]):
            with self.subTest(value_order=bad):
                rule = self.rule(combine="lowest_value", value_order=bad)
                self.assertRejected(rule, "value_order must be")


class BecomesTest(TempDirMixin, unittest.TestCase):
    def cond(self, status="lowered", **fields):
        base = {"layer": "user", "models": ["claude-opus-5-5"], "status": status}
        base.update(fields)
        return self.rule(conditions=[base])

    def test_computed_cap_and_fallback_pass_on_lowered(self):
        for kind in ("cap", "fallback"):
            with self.subTest(computed=kind):
                self.assertEqual(self.errors(self.cond(becomes={"computed": kind})), [])

    def test_unknown_computed_fails(self):
        self.assertRejected(self.cond(becomes={"computed": "other"}), "computed must be one of")

    def test_becomes_object_with_an_extra_key_fails(self):
        self.assertRejected(self.cond(becomes={"computed": "cap", "to": "low"}),
                            "exactly one key, computed")

    def test_becomes_object_without_computed_fails(self):
        self.assertRejected(self.cond(becomes={"to": "low"}), "exactly one key, computed")

    def test_computed_becomes_on_a_non_lowered_status_fails(self):
        self.assertRejected(self.cond(status="ignored", becomes={"computed": "cap"}),
                            "only for a lowered")

    def test_plain_becomes_still_works(self):
        self.assertEqual(self.errors(self.cond(becomes="high")), [])

    def test_empty_or_odd_becomes_fails(self):
        for bad in ("", " ", 5, None, ["high"]):
            with self.subTest(becomes=bad):
                self.assertRejected(self.cond(becomes=bad), "becomes must be")

    def test_effort_key_becomes_must_be_a_known_level(self):
        for bad in ("ultra", "HIGH", "5"):
            with self.subTest(becomes=bad):
                self.assertRejected(self.cond(becomes=bad), "becomes %r is not one of" % bad)
        for good in rules_schema.EFFORT_LEVELS:
            with self.subTest(becomes=good):
                self.assertEqual(self.errors(self.cond(becomes=good)), [])

    def test_becomes_must_be_in_the_rules_value_order(self):
        rule = self.cond(becomes="xhigh")
        rule.update(combine="lowest_value", value_order=["low", "medium", "high"])
        self.assertRejected(rule, "becomes 'xhigh' is not one of low, medium, high")
        rule["conditions"][0]["becomes"] = "medium"
        self.assertEqual(self.errors(rule), [])

    def test_non_effort_key_without_a_value_order_takes_any_string(self):
        rule = self.cond(becomes="5m")
        rule["key"] = "promptCacheTtl"
        self.assertEqual(self.errors(rule), [])
        rule["key"] = "modelSettings.autoCompactWindow"
        self.assertEqual(self.errors(rule), [])

    def test_effort_key_check_uses_the_last_dotted_part(self):
        rule = self.cond(becomes="ultra")
        rule["key"] = "modelSettings.maxEffortLevel"
        self.assertRejected(rule, "is not one of")

    def test_lowered_without_becomes_still_fails(self):
        self.assertRejected(self.cond(), "lowered needs becomes")


class DocumentTest(TempDirMixin, unittest.TestCase):
    def test_good_document_passes(self):
        self.assertEqual(rules_schema.validate(self.document(), self.tmp), [])

    def test_duplicate_rule_id_fails(self):
        data = self.document(rules=[self.rule(), self.rule()])
        self.assertIn("effort-level-user-settings-opus-5-5: duplicate rule_id",
                      rules_schema.validate(data, self.tmp))

    def test_schema_version_and_shape(self):
        self.assertIn("schema_version must be 3",
                      rules_schema.validate(self.document(schema_version=1), self.tmp))
        data = self.document()
        del data["rules"]
        self.assertIn("rules must be a list", rules_schema.validate(data, self.tmp))
        self.assertIn("top level must be an object", rules_schema.validate([], self.tmp))

    def test_schema_version_must_be_the_int_3(self):
        for bad in (3.0, True, "3", None, 4):
            with self.subTest(schema_version=bad):
                self.assertDocRejected(self.document(schema_version=bad),
                                       "schema_version must be 3")
        self.assertEqual(rules_schema.validate(self.document(schema_version=3), self.tmp), [])

    def test_top_level_is_exactly_three_fields(self):
        self.assertDocRejected(self.document(extra=1), "unknown top-level field extra")
        data = self.document()
        del data["models"]
        self.assertDocRejected(data, "models must be a non-empty list")

    def test_empty_or_non_list_models_fail(self):
        for bad in ([], {}, "claude-opus-5-5"):
            with self.subTest(models=bad):
                self.assertDocRejected(self.document(models=bad), "models must be a non-empty list")

    def test_duplicate_model_id_fails(self):
        models = copy.deepcopy(GOOD_MODELS) + [copy.deepcopy(GOOD_MODELS[0])]
        self.assertDocRejected(self.document(models=models), "duplicate id")

    def test_alias_on_two_models_fails(self):
        models = copy.deepcopy(GOOD_MODELS)
        models[3]["aliases"] = ["opus"]
        self.assertDocRejected(self.document(models=models), "alias opus is also on model")

    def test_rule_naming_a_model_outside_the_catalog_fails_in_a_document(self):
        rule = self.rule(conditions=[{"layer": "user", "models": ["claude-opus-9-9"],
                                      "status": "ignored"}])
        self.assertDocRejected(self.document(rules=[rule]), "unknown model")

    def test_cli_returns_1_on_unhashable_values_without_raising(self):
        rule = self.rule(confidence=["documented"])
        rule["conditions"][0]["status"] = {"ignored": 1}
        path = os.path.join(self.tmp, "rules.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.document(rules=[rule]), fh)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rules_schema.main(["rules_schema.py", path])
        self.assertEqual(code, 1)
        self.assertIn("confidence must be one of", out.getvalue())
        self.assertIn("status must be one of", out.getvalue())

    def test_unreadable_file_is_an_error(self):
        path = os.path.join(self.tmp, "rules.json")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        errs = rules_schema.load_and_validate(path)
        self.assertEqual(len(errs), 1)
        self.assertIn("cannot read", errs[0])


if __name__ == "__main__":
    unittest.main()
