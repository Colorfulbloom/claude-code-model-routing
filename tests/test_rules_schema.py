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
    "conditions": [{"layer": "user", "models": ["claude-opus-5-5"], "status": "ignored"}],
    "reason": "Opus 5.5 ignores effortLevel in {file}.",
    "doc_url": "https://code.claude.com/docs/en/settings-reference#effortlevel",
    "quote": "Opus 5.5 and models released after it ignore it.",
    "experiment": None,
    "confidence": "documented",
    "verified_on": {"claude_version": "2.1.302", "date": "2026-10-29"},
}

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

    def errors(self, rule):
        return rules_schema.check_rule(rule, self.tmp)

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
        rule = self.rule(quote=None, doc_url=None, confidence="documented")
        self.assertRejected(rule, "no source")

    def test_tested_with_no_source_fails(self):
        rule = self.rule(quote=None, doc_url=None, confidence="tested")
        self.assertRejected(rule, "no source")

    def test_assumed_needs_no_source(self):
        rule = self.rule(quote=None, doc_url=None, confidence="assumed")
        self.assertEqual(self.errors(rule), [])

    def test_assumed_quote_still_needs_doc_url(self):
        self.assertRejected(self.rule(doc_url=None, confidence="assumed"),
                            "quote has no doc_url")

    def test_assumed_doc_url_must_still_be_https(self):
        rule = self.rule(quote=None, doc_url="http://example.com", confidence="assumed")
        self.assertRejected(rule, "https")

    def test_doc_url_without_quote_is_no_source(self):
        self.assertRejected(self.rule(quote=None, confidence="documented"), "no source")

    def test_quote_without_doc_url_fails(self):
        self.assertRejected(self.rule(doc_url=None), "quote has no doc_url")

    def test_assumed_with_quote_passes(self):
        self.assertEqual(self.errors(self.rule(confidence="assumed")), [])

    def test_experiment_alone_is_a_source(self):
        name = self.write_record("experiments/effort.json", GOOD_RECORD)
        rule = self.rule(quote=None, doc_url=None, experiment=name, confidence="tested")
        self.assertEqual(self.errors(rule), [])

    def test_documented_needs_quote(self):
        name = self.write_record("experiments/effort.json", GOOD_RECORD)
        rule = self.rule(quote=None, doc_url=None, experiment=name)
        self.assertRejected(rule, "documented rule needs doc_url and quote")

    def test_doc_url_must_be_https(self):
        self.assertRejected(self.rule(doc_url="http://example.com"), "https")


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


class DocumentTest(TempDirMixin, unittest.TestCase):
    def test_duplicate_rule_id_fails(self):
        data = {"schema_version": 1, "rules": [self.rule(), self.rule()]}
        self.assertIn("effort-level-user-settings-opus-5-5: duplicate rule_id",
                      rules_schema.validate(data, self.tmp))

    def test_schema_version_and_shape(self):
        self.assertIn("schema_version must be 1",
                      rules_schema.validate({"schema_version": 2, "rules": []}, self.tmp))
        self.assertIn("rules must be a list",
                      rules_schema.validate({"schema_version": 1}, self.tmp))
        self.assertIn("top level must be an object", rules_schema.validate([], self.tmp))

    def test_cli_returns_1_on_unhashable_values_without_raising(self):
        rule = self.rule(confidence=["documented"])
        rule["conditions"][0]["status"] = {"ignored": 1}
        path = os.path.join(self.tmp, "rules.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"schema_version": 1, "rules": [rule]}, fh)
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
