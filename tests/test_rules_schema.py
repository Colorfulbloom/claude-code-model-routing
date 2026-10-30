"""Tests for dashboard/rules.json and its schema check (dashboard/rules_schema.py).

These tests read only files inside the repo and their own temp folders. They
never touch the real ~/.claude.
"""
import contextlib
import copy
import glob
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
        "id": mid, "display_name": mid.replace("claude-", "").replace("-", " ").title(),
        "aliases": aliases, "effort_levels": levels, "default_effort": default,
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
        index = rules_schema.variable_index(data["variables"])
        for rule in data["rules"]:
            with self.subTest(rule=rule.get("rule_id")):
                self.assertEqual(rules_schema.check_rule(rule, variables=index), [])
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

    def real_rules(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            return {r["rule_id"]: r for r in json.load(fh)["rules"]}

    def test_agent_file_order_is_split_into_a_tested_and_a_documented_rule(self):
        rules = self.real_rules()
        tested = rules["agent-file-project-over-user"]
        self.assertEqual(tested["confidence"], "tested")
        self.assertEqual(tested["layer_order"], ["project", "user"])
        self.assertEqual(sorted(c["layer"] for c in tested["conditions"]), ["project", "user"])
        self.assertTrue(tested["experiment"].endswith("2026-10-29-agent-files.json"))
        documented = rules["agent-file-location-order"]
        self.assertEqual(documented["confidence"], "documented")
        self.assertEqual(documented["layer_order"],
                         ["managed", "flag", "project", "user", "plugin"])
        self.assertIsNone(documented["experiment"])
        self.assertEqual(len(documented["quotes"]), 1)
        self.assertIn("higher-priority location", documented["quotes"][0]["quote"])
        self.assertEqual(rules_schema.check_rule(documented), [])

    def test_fixture_rule_ids_are_real_rules(self):
        rules = self.real_rules()
        paths = glob.glob(os.path.join(helpers.REPO, "tests", "fixtures", "resolution",
                                       "*", "expected.json"))
        self.assertTrue(paths)
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                expected = json.load(fh)
            for rule_id in expected["rule_ids"]:
                with self.subTest(fixture=expected["fixture"], rule=rule_id):
                    self.assertIn(rule_id, rules)

    def test_force_5m_fixture_agrees_with_the_env_condition_of_its_rules(self):
        rules = self.real_rules()
        path = os.path.join(helpers.REPO, "tests", "fixtures", "resolution",
                            "prompt-cache-force-5m-over-everything", "expected.json")
        with open(path, encoding="utf-8") as fh:
            expected = json.load(fh)
        self.assertNotIn("note", expected)
        seen = 0
        for entry in expected["expect"]:
            if entry["layer"] != "env":
                continue
            rule = next(r for r in (rules[i] for i in expected["rule_ids"])
                        if r["key"] == entry["key"] and r["scope"] == entry["scope"])
            # The first env condition that matches the entry's variable. A
            # condition with no via covers every variable the earlier ones don't.
            cond = next(c for c in rule["conditions"]
                        if c["layer"] == "env"
                        and c.get("via", entry["via"]) == entry["via"])
            with self.subTest(via=entry["via"], key=entry["key"]):
                self.assertEqual(entry["status"], cond["status"])
            seen += 1
        # FORCE_PROMPT_CACHING_5M and the TTL variable, for the main and agent rows.
        self.assertEqual(seen, 4)

    def test_reader_rejected_but_loads_shows_unknown_and_parse_error_stays_invalid(self):
        rules = self.real_rules()
        rule = rules["agent-file-reader-rejected"]
        self.assertEqual(rules_schema.check_rule(rule), [])
        self.assertEqual(rule["key"], "agentFile")
        conds = rule["conditions"]
        self.assertEqual(sorted(c["layer"] for c in conds), ["project", "user"])
        for cond in conds:
            self.assertEqual(cond["when"], "reader_rejected_but_loads")
            self.assertEqual(cond["status"], "unknown")
        self.assertIn("{file}", rule["reason"])
        self.assertIn("loads in Claude Code", rule["reason"])
        self.assertIn("can't read its frontmatter safely", rule["reason"])
        # The narrow case comes before the rule that says the file does not load.
        order = list(rules)
        self.assertLess(order.index("agent-file-reader-rejected"), order.index("agent-file-skipped"))
        for cond in rules["agent-file-skipped"]["conditions"]:
            if cond["when"] == "parse_error":
                self.assertEqual(cond["status"], "invalid")
            self.assertNotEqual(cond["when"], "reader_rejected_but_loads")

    def test_auto_compact_window_reason_says_only_what_was_observed(self):
        reason = self.real_rules()["auto-compact-window-values"]["reason"]
        self.assertIn("On 2.1.302, 200k ran at 100000, and the k suffix needs v2.1.304.", reason)
        self.assertNotIn("200 tokens", reason)
        self.assertIn("{file}", reason)
        self.assertIn("{value}", reason)

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


class PluginLayerAndAllCombineTest(TempDirMixin, unittest.TestCase):
    def test_plugin_layer_is_accepted_in_layer_order(self):
        rule = self.rule(layer_order=["project", "user", "plugin"],
                         conditions=[{"layer": "plugin", "models": ["*"], "status": "in_effect"}])
        self.assertEqual(self.errors(rule), [])

    def test_plugin_is_a_known_layer(self):
        self.assertIn("plugin", rules_schema.LAYERS)

    def test_combine_all_is_accepted(self):
        self.assertEqual(self.errors(self.rule(combine="all")), [])

    def test_combine_all_with_value_order_fails(self):
        rule = self.rule(combine="all", value_order=["low", "high"])
        self.assertRejected(rule, "value_order is only for combine lowest_value")


class PlansConditionTest(TempDirMixin, unittest.TestCase):
    def cond(self, **fields):
        base = {"layer": "user", "models": ["*"], "status": "unknown"}
        base.update(fields)
        return self.rule(conditions=[base])

    def test_valid_plans_pass(self):
        for plans in (["subscription"], ["api_key", "cloud_provider"], list(rules_schema.PLANS)):
            with self.subTest(plans=plans):
                self.assertEqual(self.errors(self.cond(plans=plans)), [])

    def test_plans_must_be_a_non_empty_list(self):
        for bad in ("subscription", None, 5, {"a": 1}, []):
            with self.subTest(plans=bad):
                self.assertRejected(self.cond(plans=bad), "plans must be a non-empty list")

    def test_unknown_plan_fails(self):
        for bad in ("free", "", 5, None):
            with self.subTest(plan=bad):
                self.assertRejected(self.cond(plans=["subscription", bad]), "unknown plan")

    def test_repeated_plan_fails(self):
        self.assertRejected(self.cond(plans=["api_key", "api_key"]), "plans repeat a plan")


class WhenConditionTest(TempDirMixin, unittest.TestCase):
    def cond(self, key=DROP, **fields):
        base = {"layer": "user", "models": ["*"], "status": "ignored"}
        base.update(fields)
        return self.rule(layer_order=["managed", "cli", "local", "project", "user", "env",
                                      "default"], conditions=[base],
                         **({} if key is DROP else {"key": key}))

    def test_every_when_case_passes(self):
        for case in rules_schema.WHEN_CASES:
            with self.subTest(when=case):
                status = ("unknown" if case in ("reader_rejected_but_loads", "reader_rejected_untested",
                                                "unreadable")
                          else "overridden" if case == "replaced_in_source" else "ignored")
                key = "maxEffortLevel" if case == "replaced_in_source" else DROP
                self.assertEqual(self.errors(self.cond(when=case, status=status, key=key)), [])

    def test_unknown_when_fails(self):
        for bad in ("other", "", "NOT_MD_FILE"):
            with self.subTest(when=bad):
                self.assertRejected(self.cond(when=bad), "when must be one of")

    def test_non_string_when_fails(self):
        for bad in (5, None, ["not_md_file"], {"a": 1}, True):
            with self.subTest(when=bad):
                self.assertRejected(self.cond(when=bad), "when must be one of")

    def test_reader_rejected_but_loads_is_a_when_case(self):
        self.assertIn("reader_rejected_but_loads", rules_schema.WHEN_CASES)

    def test_reader_rejected_but_loads_needs_status_unknown(self):
        self.assertEqual(self.errors(self.cond(when="reader_rejected_but_loads",
                                               status="unknown")), [])
        for status in ("ignored", "invalid", "in_effect", "overridden"):
            with self.subTest(status=status):
                self.assertRejected(self.cond(when="reader_rejected_but_loads", status=status),
                                    "when reader_rejected_but_loads needs status unknown")

    def test_model_unknown_is_allowed_on_the_default_layer(self):
        for status in ("default", "unknown"):
            with self.subTest(status=status):
                self.assertEqual(self.errors(self.cond(when="model_unknown", layer="default",
                                                       status=status)), [])

    def test_model_unknown_is_allowed_on_other_layers(self):
        for layer in ("user", "project", "env"):
            with self.subTest(layer=layer):
                self.assertEqual(self.errors(self.cond(when="model_unknown", layer=layer,
                                                       status="unknown")), [])

    def test_file_key_rule_with_when_passes(self):
        rule = self.cond(when="not_md_file")
        rule["key"] = "agentFile"
        rule["reason"] = "{file} doesn't load as an agent."
        self.assertEqual(self.errors(rule), [])


class DefaultValueConditionTest(TempDirMixin, unittest.TestCase):
    def cond(self, status="default", **fields):
        base = {"layer": "user", "models": ["*"], "status": status}
        base.update(fields)
        return self.rule(conditions=[base])

    def test_default_value_on_a_default_status_passes(self):
        rule = self.cond(default_value="5m")
        rule["key"] = "promptCacheTtl"
        self.assertEqual(self.errors(rule), [])

    def test_default_value_on_another_status_fails(self):
        rule = self.cond(status="in_effect", default_value="5m")
        rule["key"] = "promptCacheTtl"
        self.assertRejected(rule, "default_value is only for a default status")

    def test_empty_default_value_fails(self):
        for bad in ("", " ", 5, None, ["5m"]):
            with self.subTest(default_value=bad):
                rule = self.cond(default_value=bad)
                rule["key"] = "promptCacheTtl"
                self.assertRejected(rule, "default_value must be a non-empty string")

    def test_effort_key_default_value_must_be_a_known_level(self):
        self.assertRejected(self.cond(default_value="ultra"), "default_value 'ultra' is not one of")
        for good in rules_schema.EFFORT_LEVELS:
            with self.subTest(default_value=good):
                self.assertEqual(self.errors(self.cond(default_value=good)), [])

    def test_default_value_must_be_in_the_rules_value_order(self):
        rule = self.cond(default_value="xhigh")
        rule.update(combine="lowest_value", value_order=["low", "medium", "high"])
        self.assertRejected(rule, "default_value 'xhigh' is not one of low, medium, high")
        rule["conditions"][0]["default_value"] = "medium"
        self.assertEqual(self.errors(rule), [])


class OtherFileSlotTest(TempDirMixin, unittest.TestCase):
    def test_other_file_slot_passes(self):
        rule = self.rule(reason="{file} and {other_file} both name {agent}.")
        self.assertEqual(self.errors(rule), [])

    def test_unknown_slot_still_fails_beside_other_file(self):
        rule = self.rule(reason="{other_file} and {third_file}.")
        self.assertRejected(rule, "unknown slot {third_file}")


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
        for bad in ("", " ", 1.5, True, None, ["high"]):
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


def _var(name="FORCE_PROMPT_CACHING_5M", value="5m", rows=DROP):
    if rows is DROP:
        rows = [{"key": "promptCacheTtl", "scope": "main", "layer": "env"}]
    return {"name": name, "value": value, "rows": rows}


class VariablesTest(TempDirMixin, unittest.TestCase):
    def cache_rule(self, conditions=None, **changes):
        rule = self.rule(
            key="promptCacheTtl", scope="main", layer_order=["env", "user", "default"],
            conditions=conditions or [{"layer": "env", "models": ["*"], "status": "in_effect"}])
        rule.update(changes)
        return rule

    def doc(self, variables, rules=None):
        data = self.document(rules=rules or [self.cache_rule()])
        if variables is not DROP:
            data["variables"] = variables
        return data

    def test_document_without_variables_still_passes(self):
        self.assertEqual(rules_schema.validate(self.doc(DROP), self.tmp), [])

    def test_good_variables_pass(self):
        variables = [
            _var(),
            _var("CLAUDE_CODE_PROMPT_CACHE_TTL", None),
            _var("SOME_SWITCH", None, []),
            _var("ENABLE_PROMPT_CACHING_1H", "1h",
                 [{"key": "promptCacheTtl", "scope": "main", "layer": "default"}]),
        ]
        self.assertEqual(rules_schema.validate(self.doc(variables), self.tmp), [])

    def test_variables_must_be_a_list(self):
        for bad in ({}, "FORCE", None, 5):
            with self.subTest(variables=bad):
                self.assertDocRejected(self.doc(bad), "variables must be a list")

    def test_variable_must_be_an_object(self):
        self.assertDocRejected(self.doc(["FORCE"]), "variables[0]: not an object")

    def test_variable_fields_are_exact(self):
        self.assertDocRejected(self.doc([{"name": "A_B", "value": None}]),
                               "variable A_B: missing field rows")
        self.assertDocRejected(self.doc([dict(_var("A_B", None, []), extra=1)]),
                               "variable A_B: unknown field extra")

    def test_name_shape_and_uniqueness(self):
        for bad in ("force", "1ABC", "A-B", "", None, 5):
            with self.subTest(name=bad):
                self.assertDocRejected(self.doc([_var(bad, None, [])]), "name must be capital")
        self.assertDocRejected(self.doc([_var("A_B", None, []), _var("A_B", None, [])]),
                               "variable A_B: duplicate name")

    def test_value_is_null_or_a_non_empty_string(self):
        for good in (None, "5m"):
            self.assertEqual(rules_schema.validate(
                self.doc([_var(value=good)]), self.tmp), [])
        for bad in ("", " ", 5, True, ["5m"]):
            with self.subTest(value=bad):
                self.assertDocRejected(self.doc([_var(value=bad)]),
                                       "value must be null or a non-empty string")

    def test_rows_must_be_a_list_and_may_be_empty(self):
        self.assertEqual(rules_schema.validate(self.doc([_var(rows=[])]), self.tmp), [])
        self.assertDocRejected(self.doc([_var(rows={})]), "rows must be a list")

    def test_row_fields_are_checked(self):
        row = {"key": "promptCacheTtl", "scope": "main", "layer": "env"}
        self.assertDocRejected(self.doc([_var(rows=["x"])]), "rows[0]: not an object")
        self.assertDocRejected(self.doc([_var(rows=[{"key": "promptCacheTtl", "scope": "main"}])]),
                               "rows[0]: missing field layer")
        self.assertDocRejected(self.doc([_var(rows=[dict(row, extra=1)])]),
                               "rows[0]: unknown field extra")
        self.assertDocRejected(self.doc([_var(rows=[dict(row, key="a b")])]),
                               "rows[0]: key must be")
        self.assertDocRejected(self.doc([_var(rows=[dict(row, scope="team")])]),
                               "rows[0]: scope must be one of")
        for layer in ("user", "flag", "bogus", None):
            with self.subTest(layer=layer):
                self.assertDocRejected(self.doc([_var(rows=[dict(row, layer=layer)])]),
                                       "rows[0]: layer must be one of env, default")

    def test_repeated_row_fails(self):
        row = {"key": "promptCacheTtl", "scope": "main", "layer": "env"}
        self.assertDocRejected(self.doc([_var(rows=[row, dict(row)])]),
                               "rows[1]: repeats an earlier row")

    def test_row_naming_no_rule_fails(self):
        for row in ({"key": "noSuchKey", "scope": "main", "layer": "env"},
                    {"key": "promptCacheTtl", "scope": "agent", "layer": "env"},
                    {"key": "promptCacheTtl", "scope": "main", "layer": "default"}):
            with self.subTest(row=row):
                # promptCacheTtl/main has env in its order but not default in this doc
                rule = self.cache_rule(layer_order=["env", "user"])
                self.assertDocRejected(self.doc([_var(rows=[row])], [rule]),
                                       "matches no rule")

    def test_top_level_still_rejects_other_unknown_fields(self):
        data = self.doc([_var()])
        data["extra"] = 1
        self.assertDocRejected(data, "unknown top-level field extra")


class ViaAndIfSetTest(TempDirMixin, unittest.TestCase):
    INDEX = {
        "FORCE_PROMPT_CACHING_5M": {("promptCacheTtl", "main", "env")},
        "ENABLE_PROMPT_CACHING_1H": {("promptCacheTtl", "main", "default")},
        "SWITCH": set(),
    }

    def rule_with(self, **cond):
        base = {"layer": "env", "models": ["*"], "status": "in_effect"}
        base.update(cond)
        return self.rule(key="promptCacheTtl", scope="main",
                         layer_order=["env", "user", "default"], conditions=[base])

    def errs(self, rule, index=INDEX):
        return rules_schema.check_rule(rule, self.tmp, CATALOG_IDS, index)

    def assertBad(self, rule, fragment, index=INDEX):
        errs = self.errs(rule, index)
        self.assertTrue(any(fragment in e for e in errs),
                        "expected %r in %r" % (fragment, errs))

    def test_via_passes_with_a_matching_row(self):
        self.assertEqual(self.errs(self.rule_with(via="FORCE_PROMPT_CACHING_5M")), [])
        rule = self.rule_with(layer="default", via="ENABLE_PROMPT_CACHING_1H")
        self.assertEqual(self.errs(rule), [])

    def test_via_without_the_variables_list_fails(self):
        self.assertBad(self.rule_with(via="FORCE_PROMPT_CACHING_5M"),
                       "via needs the variables list", None)

    def test_via_names_an_unknown_variable(self):
        self.assertBad(self.rule_with(via="NOT_THERE"), "via NOT_THERE is not in the variables")

    def test_via_must_be_a_string(self):
        for bad in (5, None, ["A"], {"a": 1}):
            with self.subTest(via=bad):
                self.assertBad(self.rule_with(via=bad), "via must be a variable name")

    def test_via_on_the_wrong_layer_fails(self):
        self.assertBad(self.rule_with(layer="user", via="FORCE_PROMPT_CACHING_5M"),
                       "via is only for a condition on the env or default layer")

    def test_via_needs_a_row_for_the_key_scope_and_layer(self):
        # The variable has an env row, not a default row.
        self.assertBad(self.rule_with(layer="default", via="FORCE_PROMPT_CACHING_5M"),
                       "variable FORCE_PROMPT_CACHING_5M has no row for promptCacheTtl, main, default")
        # A switch has no rows, so it cannot be named by via.
        self.assertBad(self.rule_with(via="SWITCH"), "has no row for")
        rule = self.rule_with(via="FORCE_PROMPT_CACHING_5M")
        rule["scope"] = "agent"
        self.assertBad(rule, "has no row for promptCacheTtl, agent, env")

    def test_via_with_a_non_string_key_or_scope_returns_errors(self):
        for bad in ([], ["a"], {}, {"a": 1}, 5, None):
            for field in ("key", "scope"):
                with self.subTest(field=field, value=bad):
                    rule = self.rule_with(via="FORCE_PROMPT_CACHING_5M")
                    rule[field] = bad
                    errs = self.errs(rule)
                    self.assertTrue(errs)
                    self.assertTrue(any("via needs the rule key and scope to be strings" in e
                                        for e in errs), errs)

    def test_if_set_with_a_non_string_key_or_scope_does_not_raise(self):
        for bad in ([], ["a"], {}, {"a": 1}, 5, None):
            for field in ("key", "scope"):
                with self.subTest(field=field, value=bad):
                    rule = self.rule_with(if_set=["SWITCH"])
                    rule[field] = bad
                    self.assertIsInstance(self.errs(rule), list)

    def test_if_set_passes_for_any_listed_variable_including_switches(self):
        for names in (["FORCE_PROMPT_CACHING_5M"], ["SWITCH", "ENABLE_PROMPT_CACHING_1H"]):
            with self.subTest(if_set=names):
                self.assertEqual(self.errs(self.rule_with(if_set=names)), [])

    def test_if_set_on_any_layer_passes(self):
        rule = self.rule_with(layer="user", if_set=["FORCE_PROMPT_CACHING_5M"],
                              status="overridden")
        self.assertEqual(self.errs(rule), [])

    def test_if_set_without_the_variables_list_fails(self):
        self.assertBad(self.rule_with(if_set=["SWITCH"]), "if_set needs the variables list", None)

    def test_if_set_must_be_a_non_empty_list(self):
        for bad in ([], "SWITCH", None, 5, {"a": 1}):
            with self.subTest(if_set=bad):
                self.assertBad(self.rule_with(if_set=bad),
                               "if_set must be a non-empty list of variable names")

    def test_if_set_items_are_checked(self):
        self.assertBad(self.rule_with(if_set=["NOT_THERE"]),
                       "if_set NOT_THERE is not in the variables")
        self.assertBad(self.rule_with(if_set=[5]), "if_set item 5 must be a variable name")
        self.assertBad(self.rule_with(if_set=["SWITCH", "SWITCH"]), "if_set repeats a variable")


class RangeAndBecomesIntTest(TempDirMixin, unittest.TestCase):
    def rule_with(self, **cond):
        base = {"layer": "user", "models": ["*"], "status": "in_effect"}
        base.update(cond)
        return self.rule(key="autoCompactWindow", conditions=[base])

    def test_range_forms_pass(self):
        for rng in ({"min": 100000, "max": 1000000}, {"max": 99999}, {"min": 1000001},
                    {"min": 5, "max": 5}, {"min": -3}):
            with self.subTest(range=rng):
                self.assertEqual(self.errors(self.rule_with(range=rng)), [])

    def test_range_must_be_an_object(self):
        for bad in ([], [1, 2], "100000", 5, None):
            with self.subTest(range=bad):
                self.assertRejected(self.rule_with(range=bad), "range must be an object")

    def test_range_needs_a_bound_and_no_other_key(self):
        self.assertRejected(self.rule_with(range={}), "range needs min, max or both")
        self.assertRejected(self.rule_with(range={"min": 1, "step": 2}),
                            "range has unknown key step")

    def test_range_bounds_are_integers_not_booleans(self):
        for bad in ("5", 1.5, True, None, [1]):
            with self.subTest(min=bad):
                self.assertRejected(self.rule_with(range={"min": bad}),
                                    "range min must be an integer")
            with self.subTest(max=bad):
                self.assertRejected(self.rule_with(range={"max": bad}),
                                    "range max must be an integer")

    def test_range_min_above_max_fails(self):
        self.assertRejected(self.rule_with(range={"min": 10, "max": 9}), "range min is above max")

    def test_integer_becomes_with_a_range_passes_on_lowered_and_in_effect(self):
        for status in ("lowered", "in_effect"):
            with self.subTest(status=status):
                rule = self.rule_with(range={"max": 99999}, becomes=100000, status=status)
                self.assertEqual(self.errors(rule), [])

    def test_integer_becomes_without_a_range_fails(self):
        for status in ("lowered", "in_effect"):
            with self.subTest(status=status):
                self.assertRejected(self.rule_with(becomes=100000, status=status),
                                    "an integer becomes needs a range")

    def test_integer_becomes_on_other_statuses_fails(self):
        for status in ("ignored", "overridden", "invalid", "default", "unknown"):
            with self.subTest(status=status):
                self.assertRejected(
                    self.rule_with(range={"max": 1}, becomes=5, status=status),
                    "an integer becomes is only for a lowered or in_effect status")

    def test_boolean_becomes_is_not_an_integer(self):
        self.assertRejected(self.rule_with(range={"max": 1}, becomes=True, status="lowered"),
                            "becomes must be")

    def test_string_becomes_with_a_range_still_needs_lowered(self):
        self.assertRejected(self.rule_with(range={"max": 1}, becomes="100000"),
                            "becomes is only for a lowered status")
        self.assertEqual(self.errors(
            self.rule_with(range={"max": 1}, becomes="100000", status="lowered")), [])

    def test_integer_becomes_skips_the_value_order_check(self):
        rule = self.rule_with(range={"max": 1}, becomes=7, status="lowered")
        rule.update(combine="lowest_value", value_order=["a", "b"])
        self.assertEqual(self.errors(rule), [])


class CeilingCombineTest(TempDirMixin, unittest.TestCase):
    ORDER = ["env", "agent", "user", "default"]

    def ceiling(self, **changes):
        rule = self.rule(layer_order=list(self.ORDER), combine="ceiling", ceiling_layer="agent",
                         conditions=[{"layer": "user", "models": ["*"], "status": "in_effect"}])
        rule.update(changes)
        return rule

    def test_ceiling_with_a_middle_layer_passes(self):
        self.assertIn("ceiling", rules_schema.COMBINE_MODES)
        self.assertEqual(self.errors(self.ceiling()), [])

    def test_ceiling_needs_ceiling_layer(self):
        rule = self.ceiling()
        del rule["ceiling_layer"]
        self.assertRejected(rule, "combine ceiling needs ceiling_layer")

    def test_ceiling_layer_without_ceiling_fails(self):
        self.assertRejected(self.ceiling(combine="highest_layer"),
                            "ceiling_layer is only for combine ceiling")

    def test_ceiling_layer_must_be_in_layer_order(self):
        self.assertRejected(self.ceiling(ceiling_layer="flag"),
                            "ceiling_layer 'flag' is not in layer_order")
        self.assertRejected(self.ceiling(ceiling_layer=["agent"]), "ceiling_layer")

    def test_ceiling_layer_is_not_the_first_or_last_layer(self):
        for layer in ("env", "default"):
            with self.subTest(layer=layer):
                self.assertRejected(self.ceiling(ceiling_layer=layer),
                                    "must not be the first or last layer")


class NameFormTest(TempDirMixin, unittest.TestCase):
    def rule_with(self, key="modelSettings", **cond):
        base = {"layer": "user", "models": ["*"], "status": "in_effect"}
        base.update(cond)
        return self.rule(key=key, scope="model", conditions=[base])

    def test_every_name_form_passes_on_model_settings_rules(self):
        self.assertEqual(rules_schema.NAME_FORMS,
                         ("canonical", "alias", "dated", "context_1m", "provider"))
        for key in ("modelSettings", "modelSettings.autoCompactWindow"):
            for form in rules_schema.NAME_FORMS:
                with self.subTest(key=key, form=form):
                    self.assertEqual(self.errors(self.rule_with(key, name_form=form)), [])

    def test_unknown_name_form_fails(self):
        for bad in ("Canonical", "", "other", 5, None, ["alias"]):
            with self.subTest(name_form=bad):
                self.assertRejected(self.rule_with(name_form=bad), "name_form must be one of")

    def test_name_form_on_another_rule_fails(self):
        for key in ("effortLevel", "modelSettingsX", "model"):
            with self.subTest(key=key):
                self.assertRejected(self.rule_with(key, name_form="canonical"),
                                    "name_form is only for a modelSettings rule")


class ReaderRejectedUntestedTest(TempDirMixin, unittest.TestCase):
    def rule_with(self, status):
        rule = self.rule(key="agentFile", scope="agent", reason="{file} may not load.",
                         conditions=[{"layer": "user", "models": ["*"], "status": status,
                                      "when": "reader_rejected_untested"}])
        return rule

    def test_is_a_when_case(self):
        self.assertIn("reader_rejected_untested", rules_schema.WHEN_CASES)

    def test_status_unknown_passes(self):
        self.assertEqual(self.errors(self.rule_with("unknown")), [])

    def test_other_statuses_fail(self):
        for status in ("ignored", "invalid", "in_effect", "overridden", "lowered", "default"):
            with self.subTest(status=status):
                self.assertRejected(self.rule_with(status),
                                    "when reader_rejected_untested needs status unknown")


class DisplayNameTest(TempDirMixin, unittest.TestCase):
    def test_good_model_passes(self):
        self.assertEqual(self.model_errors(self.model()), [])

    def test_missing_display_name_fails(self):
        self.assertModelRejected(self.model(display_name=DROP), "missing field display_name")

    def test_empty_or_non_string_display_name_fails(self):
        for bad in ("", "   ", None, 5, ["Opus"], True):
            with self.subTest(display_name=bad):
                self.assertModelRejected(self.model(display_name=bad),
                                         "display_name must be a non-empty string")

    def test_duplicate_display_name_fails_in_a_document(self):
        models = copy.deepcopy(GOOD_MODELS)
        models[1]["display_name"] = models[0]["display_name"]
        self.assertDocRejected(self.document(models=models), "display_name")
        self.assertDocRejected(self.document(models=models), "is also on model")

    def test_every_real_model_has_a_display_name(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        names = [m["display_name"] for m in data["models"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(dict((m["id"], m["display_name"]) for m in data["models"])["claude-fable-5-1"],
                         "Fable 5.1")


class SettingsFileCasesTest(TempDirMixin, unittest.TestCase):
    ORDER = ["managed", "local", "project", "user"]

    def rule_with(self, when, status, layer="user"):
        return self.rule(key="settingsFile", reason="{file} can't be used.",
                         layer_order=self.ORDER, combine="all",
                         conditions=[{"layer": layer, "models": ["*"], "status": status,
                                      "when": when}])

    def test_new_cases_are_when_cases(self):
        self.assertIn("unparsed", rules_schema.WHEN_CASES)
        self.assertIn("unreadable", rules_schema.WHEN_CASES)

    def test_unparsed_passes_with_ignored_and_unknown(self):
        for status in ("ignored", "unknown"):
            with self.subTest(status=status):
                self.assertEqual(self.errors(self.rule_with("unparsed", status)), [])

    def test_unreadable_passes_with_unknown(self):
        self.assertEqual(self.errors(self.rule_with("unreadable", "unknown")), [])

    def test_unreadable_with_other_statuses_fails(self):
        for status in ("ignored", "invalid", "in_effect", "overridden", "lowered", "default"):
            with self.subTest(status=status):
                self.assertRejected(self.rule_with("unreadable", status),
                                    "when unreadable needs status unknown")

    def test_real_settings_file_rules_validate(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        ids = ["settings-file-unreadable", "settings-file-unreadable-untested",
               "settings-file-managed-unparsed", "settings-file-unparsed-skipped"]
        found = [r for r in data["rules"] if r["rule_id"] in ids]
        self.assertEqual([r["rule_id"] for r in found], ids)
        for rule in found:
            with self.subTest(rule=rule["rule_id"]):
                self.assertEqual((rule["key"], rule["scope"], rule["combine"]),
                                 ("settingsFile", "main", "all"))
                self.assertEqual(rule["layer_order"], self.ORDER)
        self.assertEqual(rules_schema.load_and_validate(), [])

    def test_unreadable_is_split_between_managed_and_the_untested_layers(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            rules = {r["rule_id"]: r for r in json.load(fh)["rules"]}
        tested = rules["settings-file-unreadable"]
        untested = rules["settings-file-unreadable-untested"]
        self.assertEqual([c["layer"] for c in tested["conditions"]], ["managed"])
        self.assertEqual(tested["confidence"], "documented")
        self.assertTrue(tested["quotes"])
        self.assertEqual([c["layer"] for c in untested["conditions"]],
                         ["local", "project", "user"])
        for cond in untested["conditions"]:
            self.assertEqual((cond["status"], cond["when"]), ("unknown", "unreadable"))
        self.assertEqual((untested["confidence"], untested["quotes"], untested["experiment"]),
                         ("assumed", [], None))
        # The two reasons share their first sentence. Each then names its own check.
        first = "The dashboard can't read {file}, so it can't tell which values that file sets."
        self.assertTrue(tested["reason"].startswith(first))
        self.assertTrue(untested["reason"].startswith(first))
        self.assertNotEqual(untested["reason"], tested["reason"])
        self.assertEqual(untested["verified_on"], tested["verified_on"])
        self.assertEqual((untested["layer_order"], untested["combine"]),
                         (tested["layer_order"], tested["combine"]))


class ReplacedInSourceTest(TempDirMixin, unittest.TestCase):
    ORDER = ["managed", "local", "project", "user"]

    def rule_with(self, key, status):
        return self.rule(key=key, reason="{value} in {file} is replaced.",
                         layer_order=self.ORDER, combine="all",
                         conditions=[{"layer": "user", "models": ["*"], "status": status,
                                      "when": "replaced_in_source"}])

    def test_it_is_a_when_case(self):
        self.assertIn("replaced_in_source", rules_schema.WHEN_CASES)

    def test_passes_with_overridden_on_max_effort_level(self):
        self.assertEqual(self.errors(self.rule_with("maxEffortLevel", "overridden")), [])

    def test_other_statuses_fail(self):
        for status in ("ignored", "invalid", "in_effect", "unknown", "lowered", "default"):
            with self.subTest(status=status):
                self.assertRejected(self.rule_with("maxEffortLevel", status),
                                    "when replaced_in_source needs status overridden")

    def test_other_keys_fail(self):
        for key in ("effortLevel", "settingsFile", "modelSettings.maxEffortLevel"):
            with self.subTest(key=key):
                self.assertRejected(self.rule_with(key, "overridden"),
                                    "and key maxEffortLevel")

    def test_real_rule_validates(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        found = [r for r in data["rules"]
                 if r["rule_id"] == "max-effort-level-replaced-in-file"]
        self.assertEqual(len(found), 1)


class Step3RealRulesTest(unittest.TestCase):
    def setUp(self):
        with open(rules_schema.RULES_PATH, encoding="utf-8") as fh:
            self.data = json.load(fh)
        self.rules = {r["rule_id"]: r for r in self.data["rules"]}
        self.variables = {v["name"]: v for v in self.data["variables"]}

    def test_the_model_unknown_effort_rule_is_documented_not_tested(self):
        # No run had no model, so the rule rests on its quotes. Its fixture says documented too.
        rule = self.rules["effort-level-user-settings-model-unknown"]
        self.assertEqual(rule["confidence"], "documented")
        self.assertTrue(rule["quotes"])

    def test_variables_follow_models_in_the_spec_order(self):
        self.assertEqual(list(self.data), ["schema_version", "models", "variables", "rules"])
        self.assertEqual(list(self.variables), [
            "FORCE_PROMPT_CACHING_5M", "CLAUDE_CODE_PROMPT_CACHE_TTL",
            "CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL", "ENABLE_PROMPT_CACHING_1H",
            "CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "CLAUDE_CODE_SUBAGENT_MODEL",
            "ANTHROPIC_MODEL", "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_AUTO_COMPACT_WINDOW"])
        self.assertEqual(self.variables["FORCE_PROMPT_CACHING_5M"]["value"], "5m")
        self.assertEqual(self.variables["ENABLE_PROMPT_CACHING_1H"]["value"], "1h")
        self.assertEqual(self.variables["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"]["rows"], [])

    def test_force_5m_rules_name_the_variable_and_override_the_rest(self):
        for rid in ("prompt-cache-force-5m", "subagent-prompt-cache-force-5m"):
            conds = self.rules[rid]["conditions"]
            with self.subTest(rule=rid):
                self.assertEqual(conds[0], {"layer": "env", "models": ["*"],
                                            "via": "FORCE_PROMPT_CACHING_5M",
                                            "status": "in_effect"})
                for cond in conds[1:]:
                    self.assertEqual(cond["status"], "overridden")
                    self.assertEqual(cond["if_set"], ["FORCE_PROMPT_CACHING_5M"])

    def test_enable_1h_rules_name_their_variable(self):
        for rid in ("prompt-cache-enable-1h", "subagent-prompt-cache-enable-1h"):
            with self.subTest(rule=rid):
                self.assertEqual(self.rules[rid]["conditions"][0]["via"],
                                 "ENABLE_PROMPT_CACHING_1H")

    def test_subagent_model_force_conditions(self):
        self.assertEqual(self.rules["subagent-model-force"]["conditions"], [
            {"layer": "env", "models": ["*"], "via": "CLAUDE_CODE_SUBAGENT_MODEL",
             "if_set": ["CLAUDE_CODE_SUBAGENT_MODEL_FORCE"], "status": "in_effect"},
            {"layer": "agent", "models": ["*"],
             "if_set": ["CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "CLAUDE_CODE_SUBAGENT_MODEL"],
             "status": "ignored"}])

    def test_auto_compact_window_values_conditions(self):
        conds = self.rules["auto-compact-window-values"]["conditions"]
        self.assertEqual(conds[0]["range"], {"min": 100000, "max": 1000000})
        self.assertEqual((conds[1]["range"], conds[1]["becomes"], conds[1]["status"]),
                         ({"max": 99999}, 100000, "in_effect"))
        self.assertEqual((conds[2]["range"], conds[2]["becomes"], conds[2]["status"]),
                         ({"min": 1000001}, 1000000, "lowered"))
        self.assertEqual((conds[3]["layer"], conds[3]["status"], "range" in conds[3]),
                         ("env", "ignored", False))
        self.assertEqual((conds[4]["layer"], conds[4]["status"]), ("flag", "in_effect"))
        rest = conds[5:]
        self.assertEqual([c["layer"] for c in rest[::2]],
                         ["managed", "cli", "local", "project", "user"])
        for low, ok in zip(rest[::2], rest[1::2]):
            self.assertEqual((low["range"], low["status"]), ({"max": 99999}, "ignored"))
            self.assertEqual((ok["layer"], ok["status"], "range" in ok),
                             (low["layer"], "in_effect", False))
        self.assertEqual(len(conds), 15)

    def test_auto_compact_window_default_conditions(self):
        rule = self.rules["auto-compact-window-default"]
        self.assertEqual(rule["conditions"], [
            {"layer": "default", "models": ["claude-opus-5-5"], "status": "default",
             "default_value": "1000000"},
            {"layer": "default", "models": ["*"], "status": "unknown"}])
        order = self.rules["auto-compact-window-order"]
        self.assertEqual((rule["layer_order"], rule["combine"]),
                         (order["layer_order"], order["combine"]))

    def test_agent_auto_compact_window_is_a_ceiling_and_still_assumed(self):
        rule = self.rules["agent-auto-compact-window"]
        self.assertEqual((rule["combine"], rule["ceiling_layer"], rule["confidence"]),
                         ("ceiling", "agent", "assumed"))

    def test_model_settings_name_matching_ranks_canonical_first_per_layer(self):
        rule = self.rules["model-settings-name-matching"]
        expected = []
        for layer in rule["layer_order"]:
            expected.append({"layer": layer, "models": ["*"], "name_form": "canonical",
                             "status": "in_effect"})
            expected.append({"layer": layer, "models": ["*"], "status": "in_effect"})
        self.assertEqual(rule["conditions"], expected)

    def test_untested_reader_rule_follows_the_tested_one(self):
        order = list(self.rules)
        self.assertEqual(order.index("agent-file-reader-rejected-untested"),
                         order.index("agent-file-reader-rejected") + 1)
        rule = self.rules["agent-file-reader-rejected-untested"]
        self.assertEqual((rule["key"], rule["scope"], rule["layer_order"], rule["combine"]),
                         ("agentFile", "agent", ["project", "user"], "highest_layer"))
        self.assertEqual([(c["layer"], c["when"], c["status"]) for c in rule["conditions"]],
                         [("project", "reader_rejected_untested", "unknown"),
                          ("user", "reader_rejected_untested", "unknown")])
        self.assertEqual((rule["confidence"], rule["experiment"], rule["quotes"]),
                         ("assumed", None, []))


if __name__ == "__main__":
    unittest.main()
