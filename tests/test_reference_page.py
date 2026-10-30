"""Tests for dashboard/reference_page.py and the generated docs/rules-reference.md.

These tests read only files inside the repo. They never touch the real ~/.claude.
"""
import json
import os
import re
import sys
import unittest

import helpers

sys.path.insert(0, os.path.join(helpers.REPO, "dashboard"))
import reference_page  # noqa: E402

PAGE = os.path.join(helpers.REPO, "docs", "rules-reference.md")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class ReferencePageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(_read(reference_page.RULES_PATH))
        self.copy = _read(reference_page.COPY_PATH)

    def test_page_exists(self):
        self.assertTrue(os.path.isfile(PAGE), "run /usr/bin/python3 dashboard/reference_page.py")

    def test_page_matches_render(self):
        self.assertEqual(_read(PAGE), reference_page.render(self.data, self.copy),
                         "docs/rules-reference.md is stale; regenerate it")

    def test_every_rule_id_is_a_heading(self):
        page = _read(PAGE)
        headings = set(re.findall(r"^#{1,6} (.+)$", page, re.M))
        for rule in self.data["rules"]:
            self.assertIn(rule["rule_id"], headings)

    def test_every_doc_url_appears(self):
        page = _read(PAGE)
        for rule in self.data["rules"]:
            for q in rule.get("quotes", []):
                self.assertIn(q["doc_url"], page)

    def test_render_small_doc_shows_fields(self):
        rule = {
            "rule_id": "demo-rule", "key": "demoKey", "scope": "main",
            "layer_order": ["cli", "user"], "combine": "highest_layer",
            "conditions": [], "reason": "{model} | uses {file}.",
            "quotes": [{"doc_url": "https://example.com/doc#a", "quote": "Verbatim | text."}],
            "experiment": "experiments/demo.json", "confidence": "tested",
            "verified_on": {"claude_version": "9.9.9", "date": "2026-01-02"},
        }
        page = reference_page.render({"rules": [rule]}, "Intro\n\n" + reference_page.MARKER + "\n")
        self.assertTrue(page.startswith("> "))
        self.assertIn("reference_page.py", page.split("\n")[0])
        self.assertNotIn(reference_page.MARKER, page)
        self.assertIn("### demo-rule", page)
        for text in ("demoKey", "main", "highest_layer", "cli, user", "> {model} | uses {file}.",
                     "[https://example.com/doc#a](https://example.com/doc#a)",
                     "> Verbatim | text.", "../dashboard/experiments/demo.json",
                     "Tested", "9.9.9", "January 2, 2026"):
            self.assertIn(text, page)
        row = [l for l in page.split("\n") if l.startswith("| demo-rule")][0]
        self.assertEqual(row, "| demo-rule | demoKey | main | Tested | 9.9.9 |")
        rule["experiment"] = None
        rule["rule_id"] = "a|b"
        page = reference_page.render({"rules": [rule]}, reference_page.MARKER)
        self.assertIn("| a\\|b |", page)
        self.assertIn("Experiment record: none", page)

    def test_dates_render_month_first(self):
        self.assertEqual(reference_page.month_first("2026-10-29"), "October 29, 2026")
        self.assertEqual(reference_page.month_first("2026-01-02"), "January 2, 2026")
        for odd in ("", "soon", "2026-13-01", None):
            self.assertEqual(reference_page.month_first(odd), odd)

    def test_verified_on_lines_have_no_iso_date(self):
        page = reference_page.render(self.data, self.copy)
        lines = [l for l in page.split("\n") if l.startswith("- Verified on:")]
        self.assertTrue(lines)
        for line in lines:
            self.assertNotRegex(line, r"\d{4}-\d{2}-\d{2}")
            self.assertRegex(line, r", [A-Z][a-z]+ \d{1,2}, \d{4}$")

    def test_copy_has_marker_once(self):
        self.assertEqual(self.copy.count(reference_page.MARKER), 1)

    def test_render_refuses_bad_marker_count(self):
        with self.assertRaises(ValueError):
            reference_page.render({"rules": []}, "no marker")


if __name__ == "__main__":
    unittest.main()
