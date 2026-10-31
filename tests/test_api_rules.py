"""Tests for the /api/rules route (dashboard/api_settings.py), the data behind the Rules reference page (#64).

The route is called through server.ROUTES with server.fixture_context on one resolution fixture, which has no
installed version unless a test sets one. One test asks a real server over HTTP. Every run reads only the
repo.
"""
import dataclasses
import json
import os
import re
import sys
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import api_settings  # noqa: E402
import resolve  # noqa: E402
import server  # noqa: E402
import test_server  # noqa: E402

FIXTURE = os.path.join(helpers.FIXTURES, "resolution", "effort-lowered-by-cap")
RULES = resolve.load_rules()
FIELDS = resolve.load_agent_fields()
ROUTE = server.ROUTES["/api/rules"]
REFERENCE_PAGE = os.path.join(helpers.REPO, "docs", "rules-reference.md")
RECORD_KEYS = {"rule_id", "confidence", "verified_on", "due", "quotes", "experiment", "experiment_url",
               "reference_url", "reason"}


def context(**replace):
    ctx = server.fixture_context(FIXTURE, None, None, RULES, FIELDS)
    return dataclasses.replace(ctx, **replace) if replace else ctx


def github_slug(heading):
    """The anchor GitHub makes from a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class RulesRoute(unittest.TestCase):
    def test_the_route_is_listed(self):
        self.assertIs(ROUTE, api_settings.rules)

    def test_every_rule_comes_back_sorted_by_id(self):
        status, payload = ROUTE(context(), {})
        self.assertEqual(status, 200)
        self.assertEqual(set(payload), {"installed", "rules"})
        ids = [r["rule_id"] for r in payload["rules"]]
        self.assertEqual(len(ids), len(RULES["rules"]))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(set(ids), {r["rule_id"] for r in RULES["rules"]})

    def test_each_record_has_the_trail_fields_and_the_reason(self):
        known = {r["rule_id"]: r for r in RULES["rules"]}
        for record in ROUTE(context(), {})[1]["rules"]:
            self.assertEqual(set(record), RECORD_KEYS, record["rule_id"])
            rule = known[record["rule_id"]]
            self.assertEqual(record["confidence"], rule["confidence"])
            self.assertEqual(record["verified_on"], {"claude_version": rule["verified_on"]["claude_version"],
                                                      "date": rule["verified_on"]["date"]})
            self.assertEqual(record["reason"], rule["reason"])
            self.assertEqual(record["experiment"], rule.get("experiment") or None)
            self.assertEqual([q["quote"] for q in record["quotes"]], [q["quote"] for q in rule.get("quotes", [])])
            self.assertIs(record["due"], False)
            self.assertEqual(record["reference_url"], api_settings.REFERENCE_URL + "#" + record["rule_id"])

    def test_a_record_is_the_trail_record_plus_the_reason(self):
        rule = RULES["rules"][0]
        record = [r for r in ROUTE(context(), {})[1]["rules"] if r["rule_id"] == rule["rule_id"]][0]
        expected = api_settings._rule_record(rule, None)
        expected["reason"] = rule["reason"]
        self.assertEqual(record, expected)

    def test_a_fixture_has_no_installed_version(self):
        self.assertIsNone(ROUTE(context(), {})[1]["installed"])

    def test_installed_sits_at_the_top_and_decides_due(self):
        payload = ROUTE(context(claude_version="2.1.1000"), {})[1]
        self.assertEqual(payload["installed"], "2.1.1000")
        self.assertTrue(payload["rules"])
        for record in payload["rules"]:
            self.assertIs(record["due"], True, record["rule_id"])
        payload = ROUTE(context(claude_version="2.1.302"), {})[1]
        self.assertEqual(payload["installed"], "2.1.302")
        for record in payload["rules"]:
            self.assertIs(record["due"], False, record["rule_id"])

    def test_the_answer_does_not_depend_on_the_project_query(self):
        self.assertEqual(ROUTE(context(), {"project": ["all"]}), ROUTE(context(), {}))

    def test_the_context_rules_are_what_it_lists(self):
        few = {"rules": RULES["rules"][:3]}
        payload = ROUTE(context(rules=few), {})[1]
        self.assertEqual(len(payload["rules"]), 3)
        self.assertEqual([r["rule_id"] for r in payload["rules"]], sorted(r["rule_id"] for r in few["rules"]))


class RuleIdsAreAnchors(unittest.TestCase):
    """The rule id links go to docs/rules-reference.md#<rule id>, so each id must be a heading anchor there."""

    @classmethod
    def setUpClass(cls):
        with open(REFERENCE_PAGE, encoding="utf-8") as fh:
            cls.headings = [line[4:].rstrip("\n") for line in fh if line.startswith("### ")]

    def test_every_rule_id_has_a_heading_on_the_reference_page(self):
        missing = [r["rule_id"] for r in RULES["rules"] if r["rule_id"] not in self.headings]
        self.assertEqual(missing, [])

    def test_a_github_slug_of_each_id_is_the_id(self):
        for rule in RULES["rules"]:
            self.assertEqual(github_slug(rule["rule_id"]), rule["rule_id"])

    def test_the_slug_helper(self):
        self.assertEqual(github_slug("Which field"), "which-field")
        self.assertEqual(github_slug("model-main-default"), "model-main-default")
        self.assertEqual(github_slug("What the field can't prove"), "what-the-field-cant-prove")


class SweepTexts(unittest.TestCase):
    """tests/e2e_checks/rules.json names texts the demo set shows. Check them against the route, no browser."""

    def test_the_texts_match_the_demo_answer(self):
        with open(os.path.join(helpers.REPO, "tests", "e2e_checks", "rules.json"), encoding="utf-8") as fh:
            checks = json.load(fh)
        demo = server.fixture_context(os.path.join(helpers.FIXTURES, "demo"), None, None, RULES, FIELDS)
        payload = ROUTE(demo, {})[1]
        rules = payload["rules"]
        first = rules[0]
        counts = {c: sum(1 for r in rules if r["confidence"] == c) for c in ("tested", "documented", "assumed")}
        texts = checks["routes"][0]["texts"]
        self.assertEqual(payload["installed"], "2.1.310")
        self.assertEqual(first["rule_id"], "agent-auto-compact-window")
        self.assertIn("All %d" % len(rules), texts)
        for word, key in (("Tested", "tested"), ("Documented", "documented"), ("Assumed", "assumed")):
            self.assertIn("%s %d" % (word, counts[key]), texts)
        self.assertEqual(first["confidence"], "assumed")
        self.assertIn("agent-auto-compact-window", texts)
        self.assertTrue(first["reason"].startswith("{winner} sets the auto-compact window for {agent}."))
        self.assertIn("The winning source sets the auto-compact window for the agent.", texts)
        self.assertIn("From the docs (%d)" % len(first["quotes"]), texts)
        self.assertIn("Checked on Claude Code %s, October 29, 2026" % first["verified_on"]["claude_version"], texts)
        self.assertEqual(first["verified_on"]["date"], "2026-10-29")
        self.assertIs(first["due"], True)
        self.assertIn("You have %s, so this rule is due for a new check." % payload["installed"], texts)
        self.assertTrue(all(r["due"] for r in rules), "the demo's install is newer than every rule")


class OverHttp(test_server.TempCase):
    def test_a_real_request_returns_the_same_answer(self):
        expected = json.loads(json.dumps(ROUTE(context(), {})[1]))
        proc = self.start(["--fixture", FIXTURE], name="rules")
        status, _, body = proc.request("GET", "/api/rules")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), expected)
        self.assertEqual(len(json.loads(body)["rules"]), len(RULES["rules"]))


if __name__ == "__main__":
    unittest.main()
